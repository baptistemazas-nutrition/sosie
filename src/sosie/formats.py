import csv
import datetime as dt
import inspect
import io
import json
import math
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

EXTENSIONS = {
    ".csv": "csv", ".tsv": "csv", ".txt": "csv", ".tab": "csv", ".dat": "csv",
    ".xlsx": "xlsx", ".xlsm": "xlsx", ".xls": "xls",
    ".parquet": "parquet", ".pq": "parquet", ".feather": "feather", ".arrow": "feather",
    ".sav": "sav", ".zsav": "sav", ".dta": "dta", ".xpt": "xpt", ".sas7bdat": "sas7bdat",
    ".rds": "rds", ".rdata": "rdata", ".rda": "rdata",
    ".json": "json", ".jsonl": "jsonl", ".ndjson": "jsonl",
    ".sqlite": "sqlite", ".sqlite3": "sqlite", ".db": "sqlite",
}

NOMS_FORMATS = {
    "csv": "texte délimité (CSV)", "xlsx": "Excel", "xls": "Excel ancien (.xls)", "parquet": "Parquet",
    "feather": "Feather/Arrow", "sav": "SPSS", "dta": "Stata", "xpt": "SAS transport (XPT)",
    "sas7bdat": "SAS (sas7bdat)", "rds": "R (RDS)", "rdata": "R (RData)", "json": "JSON",
    "jsonl": "JSON lignes", "sqlite": "SQLite",
}

JETONS_MANQUANTS = {"", "NA", "N/A", "n/a", "NaN", "nan", "NULL", "null", "Null", ".", "None", "#N/A", "<NA>"}

TEXTE_TITRE_MASQUE = "[ligne de titre masquée par sosie]"

RE_DECIMAL_TEXTE = re.compile(r"^[+-]?\d+[.,]\d+$")
RE_LONG_ENTIER = re.compile(r"^[+-]?\d{5,}$")
RE_DATE_TEXTE = re.compile(r"^\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?.*)?$")
RE_HEURE_TEXTE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?$")
RE_EMAIL_TEXTE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
RE_TEL_TEXTE = re.compile(r"^(?:\+33\s?|0033\s?|0)[1-9](?:[\s.-]?\d{2}){4}$")
MAJ = "A-ZÀ-ÖØ-Þ"
MIN = "a-zß-öø-ÿ"
RE_NOM_PERSONNE = re.compile(
    rf"^(?:(?:M|Mme|Mlle|Dr|Pr|Mr|Mrs|Ms)\.?\s+)?"
    rf"(?:[{MAJ}][{MAJ}'\-]+(?:\s+[{MAJ}][{MIN}'\-]+)+|[{MAJ}][{MIN}'\-]+(?:\s+[{MAJ}][{MAJ}'\-]+)+)$"
)
RE_SEP_EXCEL = re.compile(r"^\s*sep=(.)\s*$", re.IGNORECASE)


class FormatNonPrisEnCharge(Exception):
    pass


@dataclass
class Table:
    fichier: str
    feuille: str | None
    format: str
    noms: list
    donnees: pd.DataFrame
    stockages: list
    options: dict = field(default_factory=dict)

    @property
    def nom_affiche(self):
        if self.feuille is None:
            return self.fichier
        return f"{self.fichier} [{self.feuille}]"

    @property
    def n_lignes(self):
        return len(self.donnees)


def format_de(chemin):
    return EXTENSIONS.get(Path(chemin).suffix.lower())


def est_manquant(v):
    if v is None or v is pd.NA or v is pd.NaT:
        return True
    if isinstance(v, (float, np.floating)):
        return bool(np.isnan(v))
    if isinstance(v, (np.datetime64,)):
        return bool(np.isnat(v))
    return False


MOTS_ETIQUETTES = {"nom", "noms", "prenom", "prenoms", "name", "names", "firstname", "lastname", "surname", "first",
                   "last", "given", "family", "identite", "patient", "patiente", "medecin", "docteur", "naissance",
                   "usage", "jeune", "fille", "complet", "full"}
RE_TITRE_NOM = re.compile(r"\b(?:Dr|Pr|Docteur|Professeur|M|Mme|Mlle|Mr|Mrs|Ms)\.?\s+[A-ZÀ-ÖØ-Þ][\w'\-]+")
ACRONYMES_LONGS = {"TOTAL", "SCORE", "APACHE", "NIHSS", "EUROSCORE", "KARNOFSKY", "SEMASEARCH", "INSERM", "SNIIRAM",
                   "CEPIDC", "HBA1C", "GLOBAL", "MOYEN", "MOYENNE", "VISITE", "INCLUSION", "BASELINE", "CTCAE",
                   "ECOG", "NYHA", "EORTC", "HOMA", "SOFA", "WOMAC", "GLASGOW", "CHARLSON", "MMSE", "PHQ9",
                   "GAD7", "HADS", "BPRS", "PANSS", "MADRS", "EDSS", "MRC", "RANKIN", "CHILD", "PUGH", "MELD",
                   "CKD", "MDRD", "TOTAL", "SCORE", "GRADE", "STADE", "ECHELLE", "CLASSE", "TYPE"}


def ressemble_nom_personne(v, longueur=4):
    if not isinstance(v, str) or not RE_NOM_PERSONNE.match(v.strip()):
        return False
    import unicodedata
    mots = {"".join(c for c in unicodedata.normalize("NFKD", m) if not unicodedata.combining(c)).casefold()
            for m in re.split(r"[\s.\-']+", v) if m}
    if mots & MOTS_ETIQUETTES:
        return False
    majuscules = [m for m in re.split(r"[\s.']+", v) if m.isupper() and len(m.replace("-", "")) >= longueur and m not in ACRONYMES_LONGS]
    return bool(majuscules)


def libelle_suspect(texte, sensibles=frozenset()):
    s = str(texte)
    if RE_TITRE_NOM.search(s) or re.search(r"\d{5,}", s) or re.search(r"[^@\s]+@[^@\s]+\.\w{2,}", s):
        return True
    if sensibles:
        import unicodedata
        plie = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()
        if any(m in sensibles for m in re.findall(r"[a-z0-9]+", plie)):
            return True
    return ressemble_nom_personne(s, 5)


def cellule_donnee(v):
    if est_manquant(v):
        return False
    if isinstance(v, (bool, np.bool_)):
        return True
    if isinstance(v, (int, np.integer)):
        return abs(int(v)) >= 10000
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return not f.is_integer() or abs(f) >= 10000
    if isinstance(v, (dt.datetime, dt.date, dt.time, pd.Timestamp)):
        return True
    s = str(v).strip()
    return bool(RE_DECIMAL_TEXTE.match(s) or RE_LONG_ENTIER.match(s) or RE_DATE_TEXTE.match(s)
                or RE_HEURE_TEXTE.match(s) or RE_EMAIL_TEXTE.match(s) or RE_TEL_TEXTE.match(s))


def cellule_entete(v):
    if est_manquant(v):
        return None
    if isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_)):
        return 1900 <= int(v) <= 2100
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return f.is_integer() and 1900 <= f <= 2100
    if not isinstance(v, str):
        return False
    s = v.strip()
    if s == "" or s in JETONS_MANQUANTS:
        return None
    return not cellule_donnee(s)


def ligne_type_entete(cellules):
    etats = [cellule_entete(c) for c in cellules]
    remplies = [e for e in etats if e is not None]
    if not remplies or not all(remplies):
        return False
    vides = len(etats) - len(remplies)
    if vides > max(1, 0.2 * len(etats)):
        return False
    lettres = sum(1 for c in cellules if isinstance(c, str) and any(ch.isalpha() for ch in c))
    return lettres >= 0.5 * len(remplies)


def ligne_type_donnees(cellules):
    return any(cellule_donnee(c) for c in cellules)


def choisir_entete(lignes, comptes):
    if not lignes:
        return 0
    mode = Counter(comptes[:500]).most_common(1)[0][0]
    minimum = mode - 1 if mode >= 3 else max(1, mode)
    eligibles = [i for i in range(min(len(lignes), 30)) if comptes[i] >= minimum]
    if not eligibles:
        return 0
    donnees = [ligne_type_donnees(lignes[i]) for i in eligibles]
    debut = None
    for k, i in enumerate(eligibles):
        if donnees[k] and (k + 1 >= len(eligibles) or donnees[k + 1]):
            debut = i
            break
    if debut is None:
        for i in eligibles:
            if ligne_type_entete(lignes[i]):
                return i
        return eligibles[0]
    candidats = [i for i in eligibles if i < debut and ligne_type_entete(lignes[i])]
    if candidats:
        sains = [i for i in candidats if not entete_suspecte([c for c in lignes[i] if isinstance(c, str)])]
        return sains[0] if sains else candidats[0]
    if debut == eligibles[0]:
        return None
    return eligibles[0]


def entete_suspecte(noms):
    for n in noms:
        s = str(n).strip()
        if not s:
            continue
        if ressemble_nom_personne(s, 5) or RE_TITRE_NOM.search(s) or re.search(r"\d{5,}", s) or RE_EMAIL_TEXTE.match(s) or RE_TEL_TEXTE.match(s):
            return True
    return False


def stockage_objets(serie):
    valeurs = [v for v in serie.tolist() if not est_manquant(v)]
    if not valeurs:
        return "texte", pd.Series([None] * len(serie), dtype=object)
    genres = set()
    entiers = True
    for v in valeurs:
        if isinstance(v, (bool, np.bool_)):
            genres.add("b")
        elif isinstance(v, (int, np.integer)):
            genres.add("n")
        elif isinstance(v, (float, np.floating)):
            genres.add("n")
            if not float(v).is_integer():
                entiers = False
        elif isinstance(v, (pd.Timestamp, dt.datetime)):
            genres.add("t")
        elif isinstance(v, dt.date):
            genres.add("d")
        elif isinstance(v, dt.time):
            genres.add("h")
        elif isinstance(v, dt.timedelta):
            genres.add("u")
        elif isinstance(v, (bytes, bytearray, memoryview)):
            genres.add("y")
        elif isinstance(v, str):
            genres.add("s")
        else:
            genres.add("o")
    liste = serie.tolist()
    if genres == {"b"}:
        return "booleen", pd.Series([None if est_manquant(v) else bool(v) for v in liste], dtype="boolean")
    if genres == {"n"}:
        if entiers:
            entiers_py = [None if est_manquant(v) else int(v) for v in liste]
            try:
                return "entier", pd.Series(entiers_py, dtype="Int64")
            except (OverflowError, TypeError, ValueError):
                return "entier", pd.Series(entiers_py, dtype=object)
        return "decimal", pd.Series([np.nan if est_manquant(v) else float(v) for v in liste], dtype="float64")
    if genres == {"t"}:
        try:
            return "datetime", pd.to_datetime(pd.Series([None if est_manquant(v) else v for v in liste], dtype=object))
        except (ValueError, OverflowError, TypeError):
            return "mixte", pd.Series([None if est_manquant(v) else v for v in liste], dtype=object)
    if genres == {"d"}:
        return "date", pd.Series([None if est_manquant(v) else v for v in liste], dtype=object)
    if genres == {"h"}:
        return "heure", pd.Series([None if est_manquant(v) else v for v in liste], dtype=object)
    if genres == {"u"}:
        return "duree", pd.Series([None if est_manquant(v) else v for v in liste], dtype=object)
    if genres == {"y"}:
        return "binaire", pd.Series([None if est_manquant(v) else bytes(v) for v in liste], dtype=object)
    if genres == {"s"}:
        return "texte", pd.Series([None if est_manquant(v) else v for v in liste], dtype=object)
    return "mixte", pd.Series([None if est_manquant(v) else v for v in liste], dtype=object)


def stockage_serie(serie):
    dtype = serie.dtype
    if isinstance(dtype, pd.CategoricalDtype):
        return "categorie", serie
    if pd.api.types.is_bool_dtype(dtype):
        return "booleen", serie
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime", serie
    if pd.api.types.is_timedelta64_dtype(dtype):
        return "duree", serie
    if pd.api.types.is_integer_dtype(dtype):
        return "entier", serie
    if pd.api.types.is_float_dtype(dtype):
        return "decimal", serie
    if isinstance(dtype, pd.StringDtype):
        return "texte", pd.Series([None if est_manquant(v) else v for v in serie.tolist()], dtype=object)
    return stockage_objets(serie)


def table_typee(fichier, feuille, fmt, df, options=None):
    noms = [str(c) for c in df.columns]
    colonnes = {}
    stockages = []
    for j, nom in enumerate(df.columns):
        st, s = stockage_serie(df.iloc[:, j].reset_index(drop=True))
        stockages.append(st)
        colonnes[j] = s
    donnees = pd.DataFrame(colonnes) if colonnes else pd.DataFrame(index=range(len(df)))
    return Table(fichier, feuille, fmt, noms, donnees, stockages, options or {})


def score_francais(texte):
    lettres = sum(texte.count(c) for c in "éèàùâêîôûçëïüœÉÈÀÇÊÔ")
    bruit = sum(1 for c in texte if "\x80" <= c <= "\x9f")
    return lettres - 5 * bruit


def detecter_encodage(octets):
    if octets.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if octets.startswith(b"\xff\xfe") or octets.startswith(b"\xfe\xff"):
        return "utf-16"
    debut = octets[:4000]
    if len(debut) >= 8:
        pairs, impairs = debut[0::2], debut[1::2]
        if impairs.count(0) > 0.3 * len(impairs) and pairs.count(0) < 0.05 * len(pairs):
            return "utf-16-le"
        if pairs.count(0) > 0.3 * len(pairs) and impairs.count(0) < 0.05 * len(impairs):
            return "utf-16-be"
    try:
        octets.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    meilleur = None
    for rang, enc in enumerate(("cp1252", "mac_roman", "latin-1")):
        try:
            texte = octets[:400000].decode(enc)
        except UnicodeDecodeError:
            continue
        score = (score_francais(texte), -rang)
        if meilleur is None or score > meilleur[0]:
            meilleur = (score, enc)
    return meilleur[1] if meilleur else "latin-1"


def compter_champs(lignes, sep):
    try:
        return [len(r) for r in csv.reader(lignes, delimiter=sep, quotechar='"')]
    except csv.Error:
        return None


def separateur_brut(lignes):
    meilleur, score_max = None, -1
    for sep in [";", ",", "\t", "|"]:
        comptes = [l.count(sep) for l in lignes]
        valeur, frequence = Counter(comptes).most_common(1)[0]
        if valeur < 1:
            continue
        score = frequence * 1000 + valeur
        if score > score_max:
            meilleur, score_max = sep, score
    return meilleur


def detecter_separateur(echantillon):
    lignes = [l for l in echantillon.splitlines()[:300] if l.strip()]
    if lignes and RE_SEP_EXCEL.match(lignes[0]):
        lignes = lignes[1:]
    if not lignes:
        return ","
    texte = "\n".join(lignes)
    scores = {}
    avale = False
    for sep in [";", ",", "\t", "|"]:
        try:
            rangees = [r for r in csv.reader(io.StringIO(texte, newline=""), delimiter=sep) if r]
        except csv.Error:
            continue
        if not rangees:
            continue
        if any(champ_avale(c, sep) for r in rangees for c in r):
            avale = True
            continue
        comptes = [len(r) for r in rangees]
        valeur, frequence = Counter(comptes).most_common(1)[0]
        if valeur >= 2:
            scores[sep] = (frequence / len(comptes), valeur)
    if avale or not scores:
        meilleur = separateur_brut(lignes)
    else:
        meilleur, (ratio, _) = max(scores.items(), key=lambda x: (round(x[1][0], 2), x[1][1]))
        if ratio < 0.5:
            meilleur = separateur_brut(lignes)
    if meilleur is None:
        return None
    if meilleur == "," and lignes[0].count(",") == 0:
        autres = lignes[1:]
        if autres and sum(1 for l in autres if re.fullmatch(r"\s*[+-]?\d+,\d+\s*", l)) >= 0.9 * len(autres):
            return None
    return meilleur


def champ_avale(champ, sep):
    lignes = champ.split("\n")
    return len(lignes) >= 20 and sum(1 for l in lignes if sep in l) >= 0.5 * len(lignes)


def detecter_guillemets(entete_brute, ligne_brute, sep):
    if entete_brute is None:
        return "minimal"
    entete = entete_brute.split(sep)
    entete_citee = bool(entete) and all(p.startswith('"') and p.endswith('"') and len(p) >= 2 for p in entete)
    if ligne_brute is None:
        return "tout" if entete_citee else "minimal"
    morceaux = ligne_brute.split(sep)
    tous = bool(morceaux) and all(p.startswith('"') for p in morceaux if p != "")
    if entete_citee and tous:
        return "tout"
    if entete_citee:
        return "texte"
    return "minimal"


def decouper_csv(texte, sep, guillemets=True):
    lecteur = csv.reader(io.StringIO(texte, newline=""), delimiter=sep, quotechar='"',
                         quoting=csv.QUOTE_MINIMAL if guillemets else csv.QUOTE_NONE)
    lignes = []
    precedente = 0
    for r in lecteur:
        lignes.append((precedente, r))
        precedente = lecteur.line_num
    return lignes


def lire_csv(chemin, rel):
    brut = chemin.read_bytes()
    encodage = detecter_encodage(brut)
    if not encodage.startswith("utf-16") and (b"\x00" in brut[:8192] or brut[:8].startswith(b"\x89PNG") or brut[:4] == b"%PDF"):
        raise FormatNonPrisEnCharge("fichier binaire, pas un texte délimité (extension trompeuse ?)")
    texte = brut.decode(encodage, errors="replace")
    if not texte.strip():
        raise FormatNonPrisEnCharge("fichier vide")
    if "\r\n" in texte[:200000]:
        fin_ligne = "\r\n"
    elif "\r" in texte[:200000] and "\n" not in texte[:200000]:
        fin_ligne = "\r"
    else:
        fin_ligne = "\n"
    physiques = texte.splitlines()
    ligne_sep = None
    if physiques and RE_SEP_EXCEL.match(physiques[0]):
        ligne_sep = physiques[0]
        texte = texte[len(physiques[0]):].lstrip("\r\n")
        physiques = physiques[1:]
    if chemin.suffix.lower() == ".tsv":
        sep = "\t"
    elif ligne_sep:
        sep = RE_SEP_EXCEL.match(ligne_sep).group(1)
    else:
        sep = detecter_separateur(texte[:300000])
    une_colonne = sep is None
    if une_colonne:
        sep = ";" if ";" not in texte else "\t"
    avertissements = []
    sans_guillemets = False
    if une_colonne:
        brutes = [(i, [l]) for i, l in enumerate(physiques)]
    else:
        brutes = decouper_csv(texte, sep)
        geant = any(champ_avale(c, sep) for _, r in brutes for c in r)
        if geant:
            brutes = decouper_csv(texte, sep, guillemets=False)
            sans_guillemets = True
            avertissements.append("guillemet non fermé : fichier relu sans tenir compte des guillemets")
    pleines = [(i, r) for i, r in brutes if r and any(c.strip() for c in r)]
    if not pleines:
        raise FormatNonPrisEnCharge("fichier vide")
    lignes = [r for _, r in pleines]
    comptes = [len(r) for r in lignes]
    h = choisir_entete(lignes, comptes)
    sans_entete = h is None
    preambule = []
    if not sans_entete:
        index_entete = pleines[h][0]
        for i, r in brutes:
            if i >= index_entete:
                break
            if r and any(c.strip() for c in r):
                contenu = sep.join(r).strip()
                preambule.append("commentaire" if contenu.startswith("#") else "texte")
            else:
                preambule.append(f"vide:{max(0, len(r) - 1)}")
    if sans_entete:
        corps_lignes = lignes
        m = Counter(comptes[:500]).most_common(1)[0][0]
        entete = [f"V{j + 1}" for j in range(m)]
    else:
        entete = list(lignes[h])
        corps_lignes = lignes[h + 1:]
        m = len(entete)
    noms_lignes = False
    if corps_lignes and not sans_entete:
        mode_corps = Counter(len(r) for r in corps_lignes[:500]).most_common(1)[0][0]
        if mode_corps == m + 1 and m >= 1:
            noms_lignes = True
            entete = [""] + entete
            m += 1
    if not sans_entete and entete_suspecte(entete):
        raise FormatNonPrisEnCharge(
            "la ligne d'en-tête ressemble à des données personnelles (nom, identifiant, e-mail…) : "
            "vérifie que la première ligne utile contient bien les noms de colonnes"
        )
    corps = []
    irreguliers = 0
    for r in corps_lignes:
        if len(r) != m:
            irreguliers += 1
            r = (r + [""] * m)[:m]
        corps.append(r)
    if irreguliers:
        avertissements.append(f"{irreguliers} ligne(s) n'ont pas le même nombre de champs que l'en-tête (complétées ou tronquées)")
    if une_colonne:
        guillemets = "minimal"
    else:
        position = pleines[h][0] if not sans_entete else None
        brute_entete = physiques[position] if position is not None and position < len(physiques) else None
        position_ligne = pleines[h + 1][0] if not sans_entete and len(pleines) > h + 1 else (pleines[0][0] if sans_entete else None)
        brute_ligne = physiques[position_ligne] if position_ligne is not None and position_ligne < len(physiques) else None
        guillemets = detecter_guillemets(brute_entete if not sans_entete else brute_ligne, brute_ligne, sep)
    options = {
        "encodage": encodage,
        "separateur": sep,
        "fin_ligne": fin_ligne,
        "guillemets": guillemets,
        "irregulier": irreguliers,
        "preambule": preambule,
        "ligne_sep": ligne_sep,
        "sans_entete": sans_entete,
        "noms_lignes": noms_lignes,
        "sans_guillemets": sans_guillemets,
        "avertissements_lecture": avertissements,
    }
    if corps:
        donnees = pd.DataFrame({j: [r[j] for r in corps] for j in range(m)}, dtype=object)
    else:
        donnees = pd.DataFrame({j: pd.Series([], dtype=object) for j in range(m)})
    return [Table(rel, None, "csv", list(entete), donnees, ["texte"] * m, options)]


def formater_champ(v, citer, sep):
    if citer or (sep in v) or ('"' in v) or ("\n" in v) or ("\r" in v):
        return '"' + v.replace('"', '""') + '"'
    return v


def ecrire_csv(chemin, table):
    o = table.options
    sep = o.get("separateur", ",")
    fin = o.get("fin_ligne", "\n")
    mode = o.get("guillemets", "minimal")
    numeriques = set(o.get("colonnes_numeriques", []))
    lignes = []
    if o.get("ligne_sep"):
        lignes.append(o["ligne_sep"])
    for genre in o.get("preambule", []):
        if str(genre).startswith("vide:"):
            lignes.append(sep * int(str(genre).split(":")[1] or 0))
        else:
            lignes.append("# " + TEXTE_TITRE_MASQUE if genre == "commentaire" else TEXTE_TITRE_MASQUE)
    noms = list(table.noms)
    if o.get("noms_lignes"):
        noms = noms[1:]
    if not o.get("sans_entete"):
        lignes.append(sep.join(formater_champ(str(n), mode in ("tout", "texte"), sep) for n in noms))
    colonnes = [table.donnees[j].tolist() for j in range(len(table.noms))]
    for i in range(len(table.donnees)):
        champs = []
        for j, col in enumerate(colonnes):
            v = col[i]
            v = "" if est_manquant(v) else str(v)
            if mode == "tout":
                citer = True
            elif mode == "texte":
                citer = j not in numeriques and v not in JETONS_MANQUANTS
            else:
                citer = False
            champs.append(formater_champ(v, citer, sep))
        lignes.append(sep.join(champs))
    contenu = fin.join(lignes) + fin
    encodage = o.get("encodage", "utf-8")
    chemin.write_bytes(contenu.encode(encodage, errors="replace"))


def nom_cellule(v):
    if est_manquant(v):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (pd.Timestamp, dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    return str(v)


def nettoyer_grille(grille):
    if grille.empty:
        return grille
    lignes_pleines = grille.notna().any(axis=1)
    if not lignes_pleines.any():
        return grille.iloc[0:0, 0:0]
    derniere_ligne = int(np.where(lignes_pleines.values)[0].max())
    colonnes_pleines = grille.notna().any(axis=0)
    derniere_colonne = int(np.where(colonnes_pleines.values)[0].max())
    return grille.iloc[: derniere_ligne + 1, : derniere_colonne + 1].reset_index(drop=True)


def ligne_entete(grille):
    n = min(len(grille), 200)
    if n == 0:
        return 0
    lignes = [grille.iloc[i].tolist() for i in range(n)]
    comptes = [sum(1 for v in l if not est_manquant(v) and not (isinstance(v, str) and not v.strip())) for l in lignes]
    pleines = [i for i in range(n) if comptes[i] > 0]
    if not pleines:
        return 0
    sous_lignes = [lignes[i] for i in pleines]
    sous_comptes = [comptes[i] for i in pleines]
    h = choisir_entete(sous_lignes, sous_comptes)
    if h is None:
        return None
    return pleines[h]


def etats_feuilles(chemin, fmt):
    try:
        if fmt == "xls":
            import xlrd

            classeur = xlrd.open_workbook(chemin, on_demand=True)
            try:
                visibilites = list(getattr(classeur, "_sheet_visibility", None) or [])
                return {nom: {1: "hidden", 2: "veryHidden"}.get(visibilites[i] if i < len(visibilites) else 0, "visible")
                        for i, nom in enumerate(classeur.sheet_names())}
            finally:
                classeur.release_resources()
        import openpyxl

        classeur = openpyxl.load_workbook(chemin, read_only=True)
        try:
            return {ws.title: getattr(ws, "sheet_state", "visible") or "visible" for ws in classeur.worksheets}
        finally:
            classeur.close()
    except Exception:
        return {}


def lire_excel(chemin, rel, fmt):
    moteur = "xlrd" if fmt == "xls" else "openpyxl"
    try:
        feuilles = pd.read_excel(chemin, sheet_name=None, header=None, dtype=object, engine=moteur)
    except zipfile.BadZipFile:
        raise FormatNonPrisEnCharge("fichier Excel endommagé, ou protégé par un mot de passe")
    except Exception as e:
        tete = chemin.read_bytes()[:512].lstrip()
        if fmt == "xls" and (tete[:1] == b"<" or b"\t" in tete):
            raise FormatNonPrisEnCharge(
                "ce .xls n'est pas un vrai fichier Excel (souvent une page web ou un texte tabulé exporté) : "
                "ouvre-le dans Excel et enregistre-le au format .xlsx"
            )
        if "encrypted" in str(e).lower() or "password" in str(e).lower():
            raise FormatNonPrisEnCharge("fichier Excel protégé par un mot de passe : enlève la protection")
        raise FormatNonPrisEnCharge(f"fichier Excel illisible ({type(e).__name__})")
    etats = etats_feuilles(chemin, fmt)
    tables = []
    for nom_feuille, grille in feuilles.items():
        etat = etats.get(str(nom_feuille), "visible")
        grille = nettoyer_grille(grille)
        if grille.empty:
            tables.append(Table(rel, str(nom_feuille), fmt, [], pd.DataFrame(), [], {"vide": True, "etat_feuille": etat}))
            continue
        h = ligne_entete(grille)
        avertissements = []
        if h is None:
            entete = [f"V{j + 1}" for j in range(grille.shape[1])]
            corps = grille.reset_index(drop=True)
            lignes_titre, titres_non_vides = 0, []
        else:
            titres_non_vides = [i for i in range(h) if grille.iloc[i].notna().any()]
            entete = [nom_cellule(v) for v in grille.iloc[h].tolist()]
            corps = grille.iloc[h + 1:].reset_index(drop=True)
            lignes_titre = h
            if entete_suspecte(entete):
                raise FormatNonPrisEnCharge(
                    f"feuille « {nom_feuille} » : la ligne d'en-tête ressemble à des données personnelles "
                    "(nom, identifiant, e-mail…) : vérifie que la première ligne utile contient les noms de colonnes"
                )
        vides = corps.isna().all(axis=1)
        if len(corps) > 3 and vides.iloc[:-1].any():
            avertissements.append(f"feuille « {nom_feuille} » : lignes vides au milieu des données (plusieurs tableaux sur la même feuille ?)")
        corps.columns = range(len(entete))
        t = table_typee(rel, str(nom_feuille), fmt, corps, {
            "lignes_titre": lignes_titre, "titres_non_vides": titres_non_vides, "sans_entete": h is None,
            "avertissements_lecture": avertissements, "etat_feuille": etat,
        })
        t.noms = entete
        tables.append(t)
    return tables


def cellule_excel(v):
    if est_manquant(v):
        return None
    if isinstance(v, pd.Timestamp):
        if v.tzinfo is not None:
            v = v.tz_localize(None)
        return v.to_pydatetime()
    if isinstance(v, dt.datetime) and v.tzinfo is not None:
        return v.replace(tzinfo=None)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    return v


def ecrire_excel(chemin, tables):
    import openpyxl
    from openpyxl.cell import WriteOnlyCell

    classeur = openpyxl.Workbook(write_only=True)
    etats = [t.options.get("etat_feuille") if t.options.get("etat_feuille") in ("hidden", "veryHidden") else "visible" for t in tables]
    if etats and "visible" not in etats:
        etats[0] = "visible"
    for t, etat in zip(tables, etats):
        feuille = classeur.create_sheet(title=t.feuille or "Feuille1")
        feuille.sheet_state = etat
        if t.options.get("vide"):
            continue
        titres = set(t.options.get("titres_non_vides", []))
        for i in range(t.options.get("lignes_titre", 0)):
            feuille.append([TEXTE_TITRE_MASQUE] if i in titres else [])
        if not t.options.get("sans_entete"):
            feuille.append(list(t.noms))
        formats_dates = {}
        for j, st in enumerate(t.stockages):
            if st == "date":
                formats_dates[j] = "yyyy-mm-dd"
            elif st == "heure":
                formats_dates[j] = "hh:mm:ss"
            elif st == "duree":
                formats_dates[j] = "[h]:mm:ss"
            elif st == "datetime":
                serie = t.donnees[j]
                avec_heure = False
                if len(serie.dropna()):
                    avec_heure = bool((serie.dropna().dt.normalize() != serie.dropna()).any())
                formats_dates[j] = "yyyy-mm-dd hh:mm:ss" if avec_heure else "yyyy-mm-dd"
        colonnes = [t.donnees[j].tolist() for j in range(len(t.noms))]
        for i in range(len(t.donnees)):
            ligne = []
            for j, col in enumerate(colonnes):
                v = cellule_excel(col[i])
                if j in formats_dates and v is not None and isinstance(v, (dt.date, dt.datetime, dt.time, dt.timedelta)):
                    c = WriteOnlyCell(feuille, value=v)
                    c.number_format = formats_dates[j]
                    ligne.append(c)
                else:
                    ligne.append(v)
            feuille.append(ligne)
    classeur.save(chemin)


CLES_PANDAS_COLONNE = {"name", "field_name", "pandas_type", "numpy_type"}
CLES_META_COLONNE = {"ordered", "timezone", "unit", "precision", "scale"}


def metadonnees_propres(schema):
    meta = schema.metadata or {}
    brut = meta.get(b"pandas")
    if not brut:
        return None
    try:
        p = json.loads(brut)
    except (ValueError, TypeError):
        return None
    colonnes = []
    for c in p.get("columns", []):
        propre = {k: v for k, v in c.items() if k in CLES_PANDAS_COLONNE}
        m = c.get("metadata")
        propre["metadata"] = {k: v for k, v in m.items() if k in CLES_META_COLONNE} if isinstance(m, dict) else None
        colonnes.append(propre)
    sortie = {
        "index_columns": [x for x in p.get("index_columns", []) if isinstance(x, str) or (isinstance(x, dict) and x.get("kind") == "range")],
        "column_indexes": [],
        "columns": colonnes,
        "creator": p.get("creator", {}),
        "pandas_version": p.get("pandas_version"),
    }
    for x in sortie["index_columns"]:
        if isinstance(x, dict):
            x.pop("name", None)
            x["name"] = None
    return {b"pandas": json.dumps(sortie).encode("utf-8")}


def lire_arrow(chemin, rel, fmt):
    import pyarrow as pa
    import pyarrow.feather as pf
    import pyarrow.parquet as pq

    tab = pq.ParquetFile(chemin).read() if fmt == "parquet" else pf.read_table(chemin)
    imbriquees = [f.name for f in tab.schema if pa.types.is_nested(f.type)]
    if imbriquees:
        tab_plate = tab.drop_columns(imbriquees)
        df = tab_plate.to_pandas(ignore_metadata=True)
        for nom in imbriquees:
            df[nom] = pd.Series([None] * tab.num_rows, dtype=object)
        df = df[tab.column_names]
    else:
        df = tab.to_pandas(ignore_metadata=True)
    df.columns = tab.column_names
    champs = [pa.field(f.name, f.type, f.nullable) for f in tab.schema]
    schema = pa.schema(champs)
    options = {"schema": schema, "meta_pandas": metadonnees_propres(tab.schema), "imbriquees": imbriquees}
    if imbriquees:
        options["avertissements_lecture"] = [f"colonne(s) imbriquée(s) (listes, structures) non reproduite(s), vides dans le sosie : {', '.join(imbriquees)}"]
    return [table_typee(rel, None, fmt, df, options)]


def colonne_arrow(serie, type_cible):
    import pyarrow as pa

    valeurs = serie
    if isinstance(serie.dtype, pd.CategoricalDtype) and not pa.types.is_dictionary(type_cible):
        valeurs = serie.astype(object)
    try:
        return pa.array(valeurs, type=type_cible, from_pandas=True), True
    except Exception:
        pass
    try:
        brut = pa.array(valeurs, from_pandas=True)
    except Exception:
        brut = pa.array([None if est_manquant(v) else str(v) for v in serie.tolist()], type=pa.string())
    try:
        return brut.cast(type_cible), True
    except Exception:
        return brut, False


def ecrire_arrow(chemin, table, fmt):
    import pyarrow as pa
    import pyarrow.feather as pf
    import pyarrow.parquet as pq

    schema = table.options.get("schema")
    avertissements = []
    colonnes = []
    champs = []
    fidele = True
    for j, nom in enumerate(table.noms):
        serie = table.donnees[j]
        if schema is not None and j < len(schema):
            tableau, ok = colonne_arrow(serie, schema.field(j).type)
            fidele = fidele and ok
            champs.append(pa.field(nom, tableau.type, schema.field(j).nullable or tableau.null_count > 0))
        else:
            try:
                tableau = pa.array(serie, from_pandas=True)
            except Exception:
                tableau = pa.array([None if est_manquant(v) else str(v) for v in serie.tolist()], type=pa.string())
            champs.append(pa.field(nom, tableau.type))
        colonnes.append(tableau)
    tab = pa.Table.from_arrays(colonnes, schema=pa.schema(champs))
    if not fidele:
        avertissements.append(f"{table.fichier} : types Arrow d'origine non reproduits à l'identique")
    tab = tab.replace_schema_metadata(table.options.get("meta_pandas") or None)
    if fmt == "parquet":
        pq.write_table(tab, chemin)
    else:
        pf.write_feather(tab, chemin)
    return avertissements


LECTEURS_STAT = {"sav": "read_sav", "dta": "read_dta", "xpt": "read_xport", "sas7bdat": "read_sas7bdat"}


def lire_stat(chemin, rel, fmt):
    import pyreadstat

    lecteur = getattr(pyreadstat, LECTEURS_STAT[fmt])
    try:
        df, meta = lecteur(str(chemin), user_missing=True) if fmt == "sav" else lecteur(str(chemin))
    except TypeError:
        df, meta = lecteur(str(chemin))
    except Exception as e:
        raise FormatNonPrisEnCharge(f"fichier {NOMS_FORMATS.get(fmt, fmt)} illisible ou endommagé ({type(e).__name__})")
    noms = [str(c) for c in df.columns]
    labels = dict(zip(noms, meta.column_labels or [None] * len(noms)))
    options = {
        "labels": {k: v for k, v in labels.items() if v},
        "etiquettes": dict(meta.variable_value_labels or {}),
        "formats": dict(meta.original_variable_types or {}),
        "mesures": dict(getattr(meta, "variable_measure", None) or {}),
        "nom_table": getattr(meta, "table_name", None),
        "zsav": chemin.suffix.lower() == ".zsav",
        "manquants_utilisateur": dict(getattr(meta, "missing_ranges", None) or {}) if fmt == "sav" else {},
    }
    if fmt == "xpt":
        with open(chemin, "rb") as f:
            options["version_xpt"] = 8 if b"LIBV8" in f.read(80) else 5
    elif fmt == "sas7bdat":
        options["version_xpt"] = 8 if any(len(n) > 8 for n in noms) else 5
    return [table_typee(rel, None, fmt, df, options)]


def appeler_avec(fonction, *args, **kwargs):
    acceptes = inspect.signature(fonction).parameters
    return fonction(*args, **{k: v for k, v in kwargs.items() if k in acceptes and v not in (None, {}, [])})


def ecrire_stat(chemin, table, fmt):
    import pyreadstat

    colonnes = {}
    for j, (nom, st) in enumerate(zip(table.noms, table.stockages)):
        serie = table.donnees[j]
        if st == "booleen":
            serie = serie.astype("float64")
        elif st == "categorie":
            serie = serie.astype(object)
        elif st == "entier":
            if serie.isna().any() or serie.dtype == object:
                serie = serie.astype("float64")
            elif fmt == "dta" and len(serie) and serie.min() >= -2147483647 and serie.max() <= 2147483620:
                serie = serie.astype("int32")
        elif st == "duree":
            serie = pd.Series([np.nan if est_manquant(v) else pd.Timedelta(v).total_seconds() for v in serie.tolist()], dtype="float64")
        elif st == "binaire":
            serie = pd.Series([None if est_manquant(v) else bytes(v).hex() for v in serie.tolist()], dtype=object)
        elif st == "datetime":
            if getattr(serie.dt, "tz", None) is not None:
                serie = serie.dt.tz_localize(None)
            serie = serie.astype("datetime64[us]")
        colonnes[nom] = serie
    df = pd.DataFrame(colonnes)
    o = table.options
    noms = set(table.noms)
    texte = {n for n, st in zip(table.noms, table.stockages) if st in ("texte", "mixte", "categorie")}
    labels = {k: v for k, v in o.get("labels", {}).items() if k in noms}
    etiquettes = {k: v for k, v in o.get("etiquettes", {}).items() if k in noms and (fmt == "sav" or k not in texte)}
    formats_num = {
        k: v for k, v in o.get("formats", {}).items()
        if k in noms and k not in texte and isinstance(v, str) and not v.upper().startswith("A") and not v.startswith("%-") and "s" not in v.lower()
    }
    if fmt == "sav":
        manquants = {}
        for k, plages in (o.get("manquants_utilisateur") or {}).items():
            if k in noms and k not in texte and isinstance(plages, list):
                propres = []
                for x in plages:
                    if isinstance(x, dict) and isinstance(x.get("lo"), (int, float)) and isinstance(x.get("hi"), (int, float)):
                        propres.append({"lo": x["lo"], "hi": x["hi"]})
                    elif isinstance(x, (int, float)):
                        propres.append(x)
                if propres:
                    manquants[k] = propres
        options = dict(column_labels=labels, variable_value_labels=etiquettes,
                       variable_measure={k: v for k, v in o.get("mesures", {}).items() if k in noms},
                       compress=o.get("zsav", False), missing_ranges=manquants)
        try:
            appeler_avec(pyreadstat.write_sav, df, str(chemin), variable_format=formats_num, **options)
        except Exception:
            try:
                appeler_avec(pyreadstat.write_sav, df, str(chemin), **options)
            except Exception:
                options["variable_value_labels"] = {k: v for k, v in etiquettes.items() if k not in texte}
                appeler_avec(pyreadstat.write_sav, df, str(chemin), **options)
    elif fmt == "dta":
        appeler_avec(pyreadstat.write_dta, df, str(chemin), column_labels=labels, variable_value_labels=etiquettes, version=15)
    else:
        version = o.get("version_xpt", 5)
        longueur = 8 if version == 5 else 32
        nom_table = re.sub(r"[^A-Za-z0-9_]", "_", o.get("nom_table") or "DONNEES")[:longueur] or "DONNEES"
        if nom_table[0].isdigit():
            nom_table = ("T" + nom_table)[:longueur]
        appeler_avec(pyreadstat.write_xport, df, str(chemin), column_labels=labels, table_name=nom_table,
                     file_format_version=version)


def environnement_r():
    import os

    env = dict(os.environ)
    actuel = env.get("LC_ALL") or env.get("LC_CTYPE") or env.get("LANG") or ""
    if "UTF-8" not in actuel.upper() and "UTF8" not in actuel.upper():
        env["LC_ALL"] = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"
    return env


def trouver_rscript():
    candidats = [
        shutil.which("Rscript"),
        "/usr/local/bin/Rscript",
        "/opt/homebrew/bin/Rscript",
        "/Library/Frameworks/R.framework/Resources/bin/Rscript",
        "/usr/bin/Rscript",
    ]
    for c in candidats:
        if c and Path(c).exists():
            return c
    return None


def r_chaine(s):
    morceaux = []
    for ch in str(s):
        o = ord(ch)
        if ch == "\\":
            morceaux.append("\\\\")
        elif ch == '"':
            morceaux.append('\\"')
        elif ch == "\n":
            morceaux.append("\\n")
        elif ch == "\r":
            morceaux.append("\\r")
        elif ch == "\t":
            morceaux.append("\\t")
        elif o < 32:
            morceaux.append(f"\\x{o:02x}")
        elif o > 0xFFFF:
            morceaux.append(f"\\U{{{o:08x}}}")
        elif o > 126:
            morceaux.append(f"\\u{{{o:04x}}}")
        else:
            morceaux.append(ch)
    return '"' + "".join(morceaux) + '"'


SCRIPT_META_R = r"""
args <- commandArgs(TRUE)
f <- args[1]
sortie <- args[2]
if (grepl("\\.rds$", f, ignore.case = TRUE)) {
  objets <- list(`__rds__` = readRDS(f))
} else {
  e <- new.env()
  noms <- load(f, envir = e)
  objets <- mget(noms, envir = e)
}
lignes <- character(0)
for (nom in names(objets)) {
  x <- objets[[nom]]
  lignes <- c(lignes, paste("__objet__", nom, paste(class(x), collapse = ","), sep = "\t"))
  if (is.atomic(x) && !is.null(names(x)) && length(x) <= 200) {
    lignes <- c(lignes, paste("__noms__", nom, paste(gsub("[\t\n\x1f]", " ", names(x)), collapse = "\x1f"), sep = "\t"))
  }
  if (!is.data.frame(x)) next
  for (col in names(x)) {
    v <- x[[col]]
    cl <- class(v)[1]
    niv <- if (is.factor(v)) paste(levels(v), collapse = "\x1f") else ""
    ord <- if (is.ordered(v)) "1" else "0"
    tz <- ""
    if (inherits(v, "POSIXct")) {
      a <- attr(v, "tzone")
      if (!is.null(a)) tz <- a[1]
    }
    toutes <- paste(class(v), collapse = ",")
    unites <- if (inherits(v, "difftime")) as.character(attr(v, "units")) else ""
    etiq <- attr(v, "labels")
    etiq_txt <- if (!is.null(etiq) && length(etiq) && !is.null(names(etiq))) paste(paste(as.character(unname(etiq)), names(etiq), sep = "\x1e"), collapse = "\x1f") else ""
    libelle <- attr(v, "label")
    libelle <- if (is.character(libelle) && length(libelle) == 1) gsub("[\t\n]", " ", libelle) else ""
    lignes <- c(lignes, paste(nom, col, cl, ord, tz, niv, toutes, unites, etiq_txt, libelle, sep = "\t"))
  }
}
writeLines(enc2utf8(lignes), sortie, useBytes = TRUE)
"""


def metadonnees_r(chemin):
    rscript = trouver_rscript()
    if not rscript:
        return {}, {}
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "meta.R"
        sortie = Path(tmp) / "meta.tsv"
        script.write_text(SCRIPT_META_R, encoding="utf-8")
        try:
            subprocess.run([rscript, "--vanilla", str(script), str(chemin), str(sortie)],
                           capture_output=True, timeout=300, check=True, env=environnement_r())
        except Exception:
            return {}, {}
        meta = {}
        classes_objets = {}
        for ligne in sortie.read_text(encoding="utf-8", errors="replace").split("\n"):
            parties = ligne.rstrip("\r").split("\t")
            if parties and parties[0] == "__noms__" and len(parties) >= 3:
                nom = None if parties[1] == "__rds__" else parties[1]
                meta[("__noms__", nom)] = parties[2].split("\x1f")
                continue
            if parties and parties[0] == "__objet__" and len(parties) >= 3:
                nom = None if parties[1] == "__rds__" else parties[1]
                classes_objets[nom] = parties[2].split(",")
                continue
            if len(parties) < 6:
                continue
            objet, col, classe, ordonne, tz, niveaux = parties[:6]
            objet = None if objet == "__rds__" else objet
            supplement = parties[6:10] + [""] * (4 - len(parties[6:10]))
            toutes, unites, etiquettes, libelle = supplement
            meta[(objet, col)] = {
                "classe": classe,
                "ordonne": ordonne == "1",
                "tz": tz,
                "niveaux": niveaux.split("\x1f") if niveaux else [],
                "classes": toutes.split(",") if toutes else [classe],
                "unites": unites,
                "etiquettes": [x.split("\x1e", 1) for x in etiquettes.split("\x1f") if "\x1e" in x] if etiquettes else [],
                "libelle": libelle,
            }
        return meta, classes_objets


def convertir_avec_r(chemin, fmt, cible):
    rscript = trouver_rscript()
    if not rscript:
        return False
    if fmt == "rds":
        code = (f"x <- readRDS({r_chaine(chemin)}); if (is.data.frame(x)) x <- as.data.frame(x[!vapply(x, is.list, logical(1))]); "
                f"saveRDS(x, {r_chaine(cible)})")
    else:
        code = (f"e <- new.env(); n <- load({r_chaine(chemin)}, envir = e); "
                "for (k in n) { v <- get(k, envir = e); if (is.data.frame(v)) assign(k, as.data.frame(v[!vapply(v, is.list, logical(1))]), envir = e) }; "
                f"save(list = n, envir = e, file = {r_chaine(cible)})")
    try:
        r = subprocess.run([rscript, "--vanilla", "-e", code], capture_output=True, timeout=300, env=environnement_r())
    except Exception:
        return False
    return r.returncode == 0 and Path(cible).exists()


def lire_r(chemin, rel, fmt):
    import pyreadr

    try:
        resultat = pyreadr.read_r(str(chemin))
    except Exception as e:
        resultat = None
        with tempfile.TemporaryDirectory() as tmp:
            cible = Path(tmp) / ("x.rds" if fmt == "rds" else "x.RData")
            if convertir_avec_r(chemin, fmt, cible):
                try:
                    resultat = pyreadr.read_r(str(cible))
                except Exception:
                    resultat = None
        if resultat is None:
            raise FormatNonPrisEnCharge(f"objet R illisible ou non tabulaire ({type(e).__name__})")
    if not resultat:
        raise FormatNonPrisEnCharge("aucun tableau de données dans ce fichier R")
    meta, classes_objets = metadonnees_r(chemin)
    tables = []
    for nom_objet, df in resultat.items():
        df = df.reset_index(drop=True)
        t = table_typee(rel, nom_objet if fmt == "rdata" else None, fmt, df,
                        {"objet": nom_objet, "classes_r": {}, "classes_objet": classes_objets.get(nom_objet, []),
                         "noms_vecteur": meta.get(("__noms__", nom_objet if fmt == "rdata" else None)) or []})
        for j, nom in enumerate(t.noms):
            m = meta.get((nom_objet, nom))
            if not m:
                continue
            t.options["classes_r"][nom] = m
            classe = m["classe"]
            serie = t.donnees[j]
            if classe == "integer" and t.stockages[j] in ("decimal", "entier", "texte"):
                t.stockages[j] = "entier"
                t.donnees[j] = pd.Series([None if est_manquant(v) else int(v) for v in serie.tolist()], dtype="Int64")
            elif classe == "numeric" and t.stockages[j] == "entier":
                t.stockages[j] = "decimal"
                t.donnees[j] = serie.astype("float64")
            elif classe in ("factor", "ordered") and t.stockages[j] == "categorie":
                t.donnees[j] = pd.Series(pd.Categorical(serie.astype(object), categories=m["niveaux"], ordered=m["ordonne"]))
        tables.append(t)
    return tables


def valeur_csv_r(v, st):
    if est_manquant(v):
        return "__NA__"
    if st == "entier":
        return str(int(v))
    if st == "decimal":
        return repr(float(v))
    if st == "booleen":
        return "TRUE" if bool(v) else "FALSE"
    if st == "date":
        if isinstance(v, pd.Timestamp):
            return v.date().isoformat()
        return v.isoformat() if isinstance(v, dt.date) else str(v)
    if st == "datetime":
        return pd.Timestamp(v).strftime("%Y-%m-%d %H:%M:%S")
    if st == "heure" and isinstance(v, dt.time):
        return v.strftime("%H:%M:%S")
    return str(v)


ENTIER_R_MAX = 2**31 - 1


def ecrire_r_via_r(chemin, tables, fmt, rscript):
    with tempfile.TemporaryDirectory() as tmp:
        code = ["objets <- list()"]
        for k, t in enumerate(tables):
            fichier_csv = Path(tmp) / f"t{k}.csv"
            with open(fichier_csv, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
                w.writerow(t.noms)
                colonnes = [t.donnees[j].tolist() for j in range(len(t.noms))]
                for i in range(len(t.donnees)):
                    w.writerow([valeur_csv_r(colonnes[j][i], t.stockages[j]) for j in range(len(t.noms))])
            classes = []
            conversions = []
            classes_r = t.options.get("classes_r", {})
            for j, st in enumerate(t.stockages):
                cible = f"d[[{j + 1}]]"
                if st == "entier":
                    grand = any(not est_manquant(v) and abs(int(v)) > ENTIER_R_MAX for v in t.donnees[j].tolist())
                    classes.append('"numeric"' if grand else '"integer"')
                elif st == "decimal":
                    classes.append('"numeric"')
                elif st == "booleen":
                    classes.append('"logical"')
                else:
                    classes.append('"character"')
                if st == "categorie":
                    serie = t.donnees[j]
                    niveaux = list(serie.cat.categories) if isinstance(serie.dtype, pd.CategoricalDtype) else []
                    ordonne = bool(serie.cat.ordered) if isinstance(serie.dtype, pd.CategoricalDtype) else False
                    m = classes_r.get(t.noms[j])
                    if m and m.get("ordonne"):
                        ordonne = True
                    vecteur = "c(" + ", ".join(r_chaine(n) for n in niveaux) + ")" if niveaux else "character(0)"
                    conversions.append(f"{cible} <- factor({cible}, levels = {vecteur}, ordered = {'TRUE' if ordonne else 'FALSE'})")
                elif st == "date":
                    conversions.append(f"{cible} <- as.Date({cible})")
                elif st == "datetime":
                    m = classes_r.get(t.noms[j]) or {}
                    tz = m.get("tz") or "UTC"
                    conversions.append(f'{cible} <- as.POSIXct({cible}, tz = {r_chaine(tz)}, format = "%Y-%m-%d %H:%M:%S")')
                m = classes_r.get(t.noms[j]) or {}
                classes_col = m.get("classes") or []
                if "hms" in classes_col and st in ("entier", "decimal", "duree", "heure"):
                    conversions.append(f'if (requireNamespace("hms", quietly = TRUE)) {cible} <- hms::as_hms(as.numeric({cible}))')
                elif "difftime" in classes_col and st in ("entier", "decimal", "duree") and m.get("unites") in ("secs", "mins", "hours", "days", "weeks"):
                    conversions.append(f'{cible} <- as.difftime(as.numeric({cible}), units = {r_chaine(m["unites"])})')
                elif "haven_labelled" in classes_col and st in ("entier", "decimal"):
                    paires = [(v, l) for v, l in m.get("etiquettes") or [] if re.fullmatch(r"-?\d+(?:\.\d+)?", str(v))]
                    if paires:
                        vecteur = "c(" + ", ".join(f"{r_chaine(l)} = {v}" for v, l in paires) + ")"
                        conversions.append(f'if (requireNamespace("haven", quietly = TRUE)) {cible} <- haven::labelled({cible}, labels = {vecteur})')
                if m.get("libelle"):
                    conversions.append(f'attr({cible}, "label") <- {r_chaine(m["libelle"])}')
            colclasses = "c(" + ", ".join(classes) + ")" if classes else "NULL"
            code.append(
                f"d <- read.csv({r_chaine(fichier_csv)}, colClasses = {colclasses}, na.strings = \"__NA__\", "
                f"check.names = FALSE, fileEncoding = \"UTF-8\", stringsAsFactors = FALSE)"
            )
            code.extend(conversions)
            classes_objet = t.options.get("classes_objet") or []
            if "data.table" in classes_objet:
                code.append('if (requireNamespace("data.table", quietly = TRUE)) d <- data.table::as.data.table(d)')
            elif "tbl_df" in classes_objet:
                code.append('class(d) <- c("tbl_df", "tbl", "data.frame")')
            elif classes_objet and "data.frame" not in classes_objet:
                if "matrix" in classes_objet:
                    code.append("d <- as.matrix(d)")
                elif len(t.noms) == 1:
                    code.append("d <- d[[1]]")
                    noms_vecteur = t.options.get("noms_vecteur") or []
                    if noms_vecteur and len(noms_vecteur) == len(t.donnees):
                        code.append("names(d) <- c(" + ", ".join(r_chaine(n) for n in noms_vecteur) + ")")
            objet = t.options.get("objet") or t.feuille or f"objet{k + 1}"
            code.append(f"objets[[{r_chaine(objet)}]] <- d")
        if fmt == "rds":
            code.append(f"saveRDS(objets[[1]], {r_chaine(chemin)})")
        else:
            code.append("e <- list2env(objets)")
            code.append(f"save(list = names(objets), envir = e, file = {r_chaine(chemin)})")
        script = Path(tmp) / "ecrire.R"
        script.write_text("\n".join(code) + "\n", encoding="utf-8")
        r = subprocess.run([rscript, "--vanilla", str(script)], capture_output=True, timeout=600, env=environnement_r(),
                           text=True, errors="replace")
        if r.returncode != 0:
            raise RuntimeError((r.stderr or "").strip().splitlines()[-1:] or ["erreur inconnue"])


def ecrire_r(chemin, tables, fmt):
    rscript = trouver_rscript()
    raison = "R introuvable"
    if rscript:
        try:
            ecrire_r_via_r(chemin, tables, fmt, rscript)
            return []
        except Exception as e:
            detail = e.args[0][0] if e.args and isinstance(e.args[0], list) and e.args[0] else type(e).__name__
            raison = f"R a échoué ({str(detail)[:150]})"
    import pyreadr

    avertissements = [f"{tables[0].fichier} : {raison} — fichier écrit sans R : facteurs et dates deviennent du texte"]
    if fmt == "rds":
        df = tables[0].donnees.copy()
        df.columns = tables[0].noms
        pyreadr.write_rds(str(chemin), df)
    else:
        for i, t in enumerate(tables):
            df = t.donnees.copy()
            df.columns = t.noms
            pyreadr.write_rdata(str(chemin), df, df_name=t.options.get("objet") or f"objet{i + 1}")
            if len(tables) > 1:
                avertissements.append(f"{t.fichier} : sans R, un seul objet ({t.options.get('objet')}) sur {len(tables)} est écrit dans le RData")
                break
    return avertissements


def lire_json(chemin, rel, fmt):
    texte = chemin.read_text(encoding="utf-8-sig", errors="replace")
    orient = "records"
    try:
        if fmt == "jsonl":
            enregistrements = []
            for numero, l in enumerate(texte.splitlines(), 1):
                if l.strip():
                    try:
                        enregistrements.append(json.loads(l))
                    except json.JSONDecodeError:
                        raise FormatNonPrisEnCharge(f"JSON invalide à la ligne {numero}")
        else:
            objet = json.loads(texte)
    except json.JSONDecodeError as e:
        raise FormatNonPrisEnCharge(f"JSON invalide (ligne {e.lineno})")
    index = None
    if fmt != "jsonl":
        if isinstance(objet, list):
            enregistrements = objet
        elif isinstance(objet, dict) and set(objet) >= {"columns", "data"} and isinstance(objet.get("data"), list):
            orient = "split"
            cles = list(objet["columns"])
            enregistrements = [dict(zip(cles, ligne)) for ligne in objet["data"]]
            index = objet.get("index")
        elif isinstance(objet, dict) and objet and all(isinstance(v, list) for v in objet.values()) \
                and len({len(v) for v in objet.values()}) == 1:
            orient = "columns"
            cles = list(objet.keys())
            enregistrements = [dict(zip(cles, ligne)) for ligne in zip(*objet.values())]
        elif isinstance(objet, dict) and objet and all(isinstance(v, dict) for v in objet.values()) \
                and len({tuple(v.keys()) for v in objet.values()}) == 1:
            orient = "columns_dict"
            cles = list(objet.keys())
            index = list(next(iter(objet.values())).keys())
            enregistrements = [{c: objet[c][i] for c in cles} for i in index]
        else:
            raise FormatNonPrisEnCharge("structure JSON non tabulaire")
    if not all(isinstance(e, dict) for e in enregistrements):
        raise FormatNonPrisEnCharge("structure JSON non tabulaire")
    noms = []
    vus = set()
    for e in enregistrements:
        for k in e:
            if k not in vus:
                vus.add(k)
                noms.append(k)
            if isinstance(e[k], (dict, list)):
                raise FormatNonPrisEnCharge("JSON imbriqué (non pris en charge)")
    df = pd.DataFrame({j: pd.Series([e.get(n) for e in enregistrements], dtype=object) for j, n in enumerate(noms)})
    indent = 2 if "\n " in texte[:2000] else None
    t = table_typee(rel, None, fmt, df, {"orient": orient, "indent": indent, "index_entier": all(str(i).isdigit() for i in (index or []))})
    t.noms = noms
    return [t]


def valeur_json(v):
    if est_manquant(v):
        return None
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) else f
    if isinstance(v, (pd.Timestamp, dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, dt.timedelta):
        return v.total_seconds()
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()
    return v


def valeur_sqlite(v):
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    return valeur_json(v)


def ecrire_json(chemin, table, fmt):
    colonnes = [table.donnees[j].tolist() for j in range(len(table.noms))]
    enregistrements = [
        {n: valeur_json(colonnes[j][i]) for j, n in enumerate(table.noms)} for i in range(len(table.donnees))
    ]
    if fmt == "jsonl":
        chemin.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in enregistrements) + "\n", encoding="utf-8")
        return
    orient = table.options.get("orient")
    if orient == "columns":
        objet = {n: [e[n] for e in enregistrements] for n in table.noms}
    elif orient == "columns_dict":
        objet = {n: {str(i): e[n] for i, e in enumerate(enregistrements)} for n in table.noms}
    elif orient == "split":
        objet = {"columns": list(table.noms), "index": list(range(len(enregistrements))),
                 "data": [[e[n] for n in table.noms] for e in enregistrements]}
    else:
        objet = enregistrements
    chemin.write_text(json.dumps(objet, ensure_ascii=False, indent=table.options.get("indent")), encoding="utf-8")


def sql_sans_litteraux(sql, noms_connus=None):
    if not sql:
        return False
    if noms_connus is not None:
        connus = {str(n).casefold() for n in noms_connus}
        for m in re.finditer(r'"((?:[^"]|"")*)"|`([^`]*)`|\[([^\]]*)\]', sql):
            contenu = next(g for g in m.groups() if g is not None).replace('""', '"')
            if contenu.casefold() not in connus:
                return False
    sans_identifiants = re.sub(r'"(?:[^"]|"")*"|`[^`]*`|\[[^\]]*\]', " ", sql)
    if "'" in sans_identifiants or "--" in sans_identifiants or "/*" in sans_identifiants:
        return False
    return not re.search(r"(?<![\w.])\d{4,}", sans_identifiants)


def identifiant_sql(nom):
    return '"' + str(nom).replace('"', '""') + '"'


MOTS_TYPES_SQL = {"INTEGER", "INT", "TINYINT", "SMALLINT", "MEDIUMINT", "BIGINT", "UNSIGNED", "BIG", "INT2", "INT8",
                  "CHARACTER", "VARCHAR", "VARYING", "NCHAR", "NATIVE", "NVARCHAR", "TEXT", "CLOB", "BLOB", "REAL",
                  "DOUBLE", "PRECISION", "FLOAT", "NUMERIC", "DECIMAL", "BOOLEAN", "BOOL", "DATE", "DATETIME",
                  "TIMESTAMP", "TIME", "STRING", "NUMBER", "CHAR"}


def type_sql_propre(declaration):
    d = str(declaration or "").strip()
    if not d:
        return ""
    m = re.fullmatch(r"([A-Za-z][A-Za-z0-9 ]*?)\s*(\(\s*\d{1,4}\s*(?:,\s*\d{1,4}\s*)?\))?", d)
    if m and all(mot.upper() in MOTS_TYPES_SQL for mot in m.group(1).split()):
        return (m.group(1).upper() + (m.group(2) or "").replace(" ", ""))[:40]
    haut = d.upper()
    if "INT" in haut:
        return "INTEGER"
    if any(x in haut for x in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in haut:
        return "BLOB"
    if any(x in haut for x in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def lire_sqlite(chemin, rel):
    uri = Path(chemin).resolve().as_uri() + "?mode=ro"
    try:
        connexion = sqlite3.connect(uri, uri=True)
        objets = connexion.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY rowid"
        ).fetchall()
    except sqlite3.DatabaseError:
        raise FormatNonPrisEnCharge("base SQLite illisible ou endommagée")
    try:
        virtuelles = {nom for type_objet, nom, _, sql in objets
                      if type_objet == "table" and sql and sql.upper().lstrip().startswith("CREATE VIRTUAL")}
        tables = []
        annexes = {"index": [], "vues": []}
        for type_objet, nom, table_parente, sql in objets:
            if type_objet == "table":
                if any(nom != v and nom.startswith(v + "_") for v in virtuelles):
                    continue
                df = pd.read_sql_query(f"SELECT * FROM {identifiant_sql(nom)}", connexion)
                infos = connexion.execute(f"PRAGMA table_xinfo({identifiant_sql(nom)})").fetchall()
                colonnes = [{"nom": r[1], "type": r[2], "pk": r[5], "cache": r[6]} for r in infos]
                tables.append(table_typee(rel, nom, "sqlite", df, {"sqlite": {
                    "colonnes": colonnes,
                    "virtuelle": nom in virtuelles,
                    "sql_virtuelle": sql if nom in virtuelles else None,
                    "sans_rowid": bool(sql and "WITHOUT ROWID" in sql.upper()),
                }}))
            elif type_objet == "index" and sql:
                details = connexion.execute(f"PRAGMA index_info({identifiant_sql(nom)})").fetchall()
                if not details or any(d[1] is None or d[1] < 0 for d in details):
                    continue
                unique = any(l[1] == nom and l[2] for l in connexion.execute(f"PRAGMA index_list({identifiant_sql(table_parente)})").fetchall())
                annexes["index"].append({"nom": nom, "table": table_parente, "colonnes": [d[2] for d in details], "unique": bool(unique)})
            elif type_objet in ("view", "trigger") and sql:
                annexes["vues"].append({"nom": nom, "type": type_objet, "sql": sql})
    finally:
        connexion.close()
    if not tables:
        raise FormatNonPrisEnCharge("base SQLite sans table")
    tables[0].options["sqlite_annexes"] = annexes
    return tables


def ecrire_sqlite(chemin, tables):
    if chemin.exists():
        chemin.unlink()
    avertissements = []
    connexion = sqlite3.connect(str(chemin))
    try:
        for t in tables:
            info = t.options.get("sqlite") or {}
            nom_table = identifiant_sql(t.feuille)
            if info.get("virtuelle") and sql_sans_litteraux(info.get("sql_virtuelle"), {t.feuille} | set(t.noms)):
                try:
                    connexion.execute(info["sql_virtuelle"])
                    cree = True
                except sqlite3.Error:
                    cree = False
            else:
                cree = False
            garder = list(range(len(t.noms)))
            if not cree:
                types = {c["nom"]: c["type"] for c in info.get("colonnes", [])}
                definitions = [f"{identifiant_sql(n)} {type_sql_propre(types.get(n, ''))}".strip() for n in t.noms]
                cles = [c for c in sorted(info.get("colonnes", []), key=lambda c: c["pk"]) if c["pk"] and c["nom"] in t.noms]
                avec_cle = bool(cles) and (info.get("sans_rowid") or (len(cles) == 1 and str(cles[0]["type"]).upper() == "INTEGER"))
                if avec_cle:
                    definitions.append("PRIMARY KEY (" + ", ".join(identifiant_sql(c["nom"]) for c in cles) + ")")
                suffixe = " WITHOUT ROWID" if info.get("sans_rowid") and avec_cle else ""
                connexion.execute(f"CREATE TABLE {nom_table} ({', '.join(definitions)}){suffixe}")
                if info.get("virtuelle"):
                    avertissements.append(f"{t.fichier} : table virtuelle « {t.feuille} » recréée comme table ordinaire")
            if len(t.noms) == 0:
                continue
            colonnes = [t.donnees[j].tolist() for j in range(len(t.noms))]
            lignes = [tuple(valeur_sqlite(colonnes[j][i]) for j in garder) for i in range(len(t.donnees))]
            if not cree:
                cles_noms = [c["nom"] for c in sorted(info.get("colonnes", []), key=lambda c: c["pk"]) if c["pk"] and c["nom"] in t.noms]
                if cles_noms and (info.get("sans_rowid") or len(cles_noms) == 1):
                    positions = [t.noms.index(n) for n in cles_noms]
                    vues = set()
                    uniques = []
                    for l in lignes:
                        cle = tuple(l[p] for p in positions)
                        if cle in vues:
                            continue
                        vues.add(cle)
                        uniques.append(l)
                    if len(uniques) < len(lignes):
                        avertissements.append(f"{t.fichier} : {len(lignes) - len(uniques)} ligne(s) en double sur la clé primaire de « {t.feuille} » retirée(s) du sosie")
                    lignes = uniques
            marques = ", ".join("?" for _ in garder)
            noms = ", ".join(identifiant_sql(t.noms[j]) for j in garder)
            try:
                connexion.executemany(f"INSERT INTO {nom_table} ({noms}) VALUES ({marques})", lignes)
            except sqlite3.Error:
                for l in lignes:
                    try:
                        connexion.execute(f"INSERT INTO {nom_table} ({noms}) VALUES ({marques})", l)
                    except sqlite3.Error:
                        pass
        annexes = tables[0].options.get("sqlite_annexes") or {}
        noms_connus = {t.feuille for t in tables} | {n for t in tables for n in t.noms}
        noms_connus |= {idx["nom"] for idx in annexes.get("index", [])} | {v["nom"] for v in annexes.get("vues", [])}
        for idx in annexes.get("index", []):
            colonnes = ", ".join(identifiant_sql(c) for c in idx["colonnes"])
            for unique in ([True, False] if idx.get("unique") else [False]):
                try:
                    connexion.execute(f"CREATE {'UNIQUE ' if unique else ''}INDEX {identifiant_sql(idx['nom'])} ON {identifiant_sql(idx['table'])} ({colonnes})")
                    break
                except sqlite3.Error:
                    continue
        for vue in annexes.get("vues", []):
            if sql_sans_litteraux(vue["sql"], noms_connus):
                try:
                    connexion.execute(vue["sql"])
                    continue
                except sqlite3.Error:
                    pass
            genre = "vue" if vue["type"] == "view" else "déclencheur"
            avertissements.append(f"{tables[0].fichier} : {genre} « {vue['nom']} » non recopié(e) (contient des valeurs écrites en dur ou des commentaires)")
        connexion.commit()
    finally:
        connexion.close()
    return avertissements


def lire_fichier(chemin, rel):
    fmt = format_de(chemin)
    if fmt is None:
        raise FormatNonPrisEnCharge("extension non reconnue")
    if fmt == "csv":
        return lire_csv(chemin, rel)
    if fmt in ("xlsx", "xls"):
        return lire_excel(chemin, rel, fmt)
    if fmt in ("parquet", "feather"):
        try:
            return lire_arrow(chemin, rel, fmt)
        except FormatNonPrisEnCharge:
            raise
        except Exception as e:
            raise FormatNonPrisEnCharge(f"fichier {NOMS_FORMATS[fmt]} illisible ou endommagé ({type(e).__name__})")
    if fmt in LECTEURS_STAT:
        return lire_stat(chemin, rel, fmt)
    if fmt in ("rds", "rdata"):
        return lire_r(chemin, rel, fmt)
    if fmt in ("json", "jsonl"):
        return lire_json(chemin, rel, fmt)
    if fmt == "sqlite":
        return lire_sqlite(chemin, rel)
    raise FormatNonPrisEnCharge("format inconnu")


def destination_de(rel, fmt):
    chemin = Path(rel)
    if fmt == "xls":
        return str(chemin.with_suffix(".xlsx").as_posix()), "xlsx", "Excel .xls réécrit en .xlsx (format plus récent)"
    if fmt == "sas7bdat":
        return str(chemin.with_suffix(".xpt").as_posix()), "xpt", "SAS .sas7bdat réécrit en .xpt (aucun outil libre n'écrit le .sas7bdat)"
    return rel, fmt, None


def ecrire_fichier(dossier, tables):
    rel, fmt, note = destination_de(tables[0].fichier, tables[0].format)
    racine = Path(dossier).resolve()
    chemin = Path(dossier) / rel
    if Path(rel).is_absolute() or ".." in Path(rel).parts or not chemin.resolve().is_relative_to(racine):
        raise ValueError(f"chemin de sortie refusé (hors du dossier du sosie) : {rel}")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    avertissements = [f"{tables[0].fichier} : {note}"] if note else []
    if fmt == "csv":
        ecrire_csv(chemin, tables[0])
    elif fmt == "xlsx":
        ecrire_excel(chemin, tables)
    elif fmt in ("parquet", "feather"):
        avertissements += ecrire_arrow(chemin, tables[0], fmt)
    elif fmt in ("sav", "dta", "xpt"):
        ecrire_stat(chemin, tables[0], fmt)
    elif fmt in ("rds", "rdata"):
        avertissements += ecrire_r(chemin, tables, fmt)
    elif fmt in ("json", "jsonl"):
        ecrire_json(chemin, tables[0], fmt)
    elif fmt == "sqlite":
        avertissements += ecrire_sqlite(chemin, tables)
    return rel, avertissements


def fichier_ignore(nom):
    return nom.startswith(".") or nom.startswith("~$") or nom.startswith("._") or nom in ("Thumbs.db", "desktop.ini", "Icon\r")


def lister_fichiers(dossier, liens_ignores=None):
    dossier = Path(dossier)
    fichiers = []
    for chemin in sorted(dossier.rglob("*")):
        rel = chemin.relative_to(dossier)
        if any(p.startswith(".") for p in rel.parts[:-1]):
            continue
        if chemin.is_symlink() and chemin.is_dir():
            if liens_ignores is not None:
                liens_ignores.append(rel.as_posix())
            continue
        if not chemin.is_file():
            continue
        if fichier_ignore(chemin.name):
            continue
        fichiers.append((chemin, rel.as_posix()))
    return fichiers
