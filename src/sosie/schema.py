import csv
import datetime as dt
import io
import re
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath

import numpy as np
import pandas as pd

from .formats import Table, detecter_encodage, detecter_separateur, format_de
from .generation import EPOQUE, tirer, vers_serie
from .identifiants import Faussaire, motif
from .profil import cles_liees

COLONNES = ["fichier", "feuille", "colonne", "type", "nature", "format", "modalites", "manquants", "cle"]


def type_dictionnaire(col):
    st, g, p = col["stockage"], col["genre"], col["params"]
    if g in ("date", "date_naissance"):
        return "datetime" if p.get("heure") else "date"
    if g == "numerique":
        return "entier" if p.get("entier") else "decimal"
    if g == "booleen" or st == "booleen":
        return "booleen"
    if g == "discret":
        labels = [v for v, _ in p.get("modalites") or []]
        try:
            nombres = [float(str(v).replace(",", ".")) for v in labels]
            return "entier" if all(x.is_integer() for x in nombres) else "decimal"
        except ValueError:
            return "texte"
    if st in ("entier", "decimal", "categorie"):
        return st
    return "texte"


def motif_lisible(analyse, seuil):
    cles = [c for c in analyse.cles() if c is not None]
    if not cles:
        return ""
    classes = Counter(motif(c) for c in cles)
    principal = classes.most_common(1)[0][0]
    valeurs = [c for c in cles if motif(c) == principal]
    distinctes = set(valeurs)
    sortie = []
    for p, m in enumerate(principal):
        if m.startswith("="):
            sortie.append(echapper_litteral(m[1:]))
            continue
        caracteres = {v[p] for v in distinctes}
        if len(distinctes) >= seuil and len(caracteres) == 1:
            sortie.append(echapper_litteral(next(iter(caracteres))))
        else:
            sortie.append({"D": "#", "U": "X", "L": "x"}[m])
    return "".join(sortie)


def echapper_litteral(c):
    return "\\" + c if c in "#Xx\\" else c


def cles_relations(tables_analyses):
    colonnes = []
    for liste in tables_analyses:
        for a in liste:
            if a.genre in ("identifiant", "nir"):
                colonnes.append((a, set(c for c in a.cles() if c is not None)))
    parent = list(range(len(colonnes)))

    def racine(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(colonnes)):
        for k in range(i + 1, len(colonnes)):
            if cles_liees(colonnes[i][0].nom, colonnes[i][1], colonnes[k][0].nom, colonnes[k][1]):
                parent[racine(i)] = racine(k)
    noms = {}
    resultat = {}
    for i, (a, valeurs) in enumerate(colonnes):
        r = racine(i)
        if r not in noms:
            noms[r] = f"cle{len(noms) + 1}"
        unique = len(valeurs) == a.n_valides
        resultat[id(a)] = noms[r] + (" (unique)" if unique else "")
    return resultat


def exporter(tables, par_table, profil, chemin, avec_modalites=False):
    relations = cles_relations(par_table)
    lignes = []
    for t, liste, tp in zip(tables, par_table, profil["tables"]):
        for a, col in zip(liste, tp["colonnes"]):
            p = col["params"]
            fmt = ""
            if col["genre"] in ("date", "date_naissance"):
                fmt = p.get("format") or ""
            elif col["genre"] == "numerique" and p.get("decimales"):
                fmt = str(p["decimales"])
            elif col["genre"] in ("identifiant", "nir", "code", "telephone"):
                fmt = motif_lisible(a, profil["seuil"])
            modalites = ""
            if avec_modalites:
                if col["genre"] in ("categorie", "discret", "booleen", "ville", "code_postal") and p.get("modalites"):
                    modalites = "|".join(str(v) for v, _ in p["modalites"])
                elif col["genre"] == "booleen":
                    modalites = "TRUE|FALSE"
                elif col["genre"] == "numerique" and p.get("quantiles"):
                    modalites = f"{p['quantiles'][0][1]:.6g}..{p['quantiles'][-1][1]:.6g}"
                elif col["genre"] in ("date", "date_naissance") and p.get("quantiles"):
                    debut = (EPOQUE + dt.timedelta(seconds=p["quantiles"][0][1])).date().isoformat()
                    fin = (EPOQUE + dt.timedelta(seconds=p["quantiles"][-1][1])).date().isoformat()
                    modalites = f"{debut}..{fin}"
            lignes.append({
                "fichier": t.fichier,
                "feuille": t.feuille or "",
                "colonne": col["nom"],
                "type": type_dictionnaire(col),
                "nature": col["genre"],
                "format": fmt,
                "modalites": modalites,
                "manquants": f"{round(col['taux_manquants'] * 20) / 20:.2f}",
                "cle": relations.get(id(a), ""),
            })
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        w.writeheader()
        w.writerows(lignes)
    return len(lignes)


def normaliser(texte):
    s = unicodedata.normalize("NFKD", str(texte))
    return "".join(c for c in s if not unicodedata.combining(c)).strip().lower()


def fichier_relatif(texte, numero):
    brut = str(texte).strip().replace("\\", "/")
    if brut.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", brut):
        raise ValueError(f"ligne {numero} : le fichier « {texte} » doit être un nom relatif (ex. visites.csv), pas un chemin complet")
    parties = [x for x in PurePosixPath(brut).parts if x not in ("", ".")]
    if not parties or ".." in parties:
        raise ValueError(f"ligne {numero} : le fichier « {texte} » doit rester dans le dossier du sosie (pas de « .. »)")
    if any(x.startswith(".") for x in parties):
        raise ValueError(f"ligne {numero} : le fichier « {texte} » ne peut pas être un fichier caché")
    return "/".join(parties)


def lire_dictionnaire(chemin):
    brut = Path(chemin).read_bytes()
    texte = brut.decode(detecter_encodage(brut), errors="replace")
    sep = detecter_separateur(texte[:20000]) or ";"
    lecteur = csv.DictReader(io.StringIO(texte, newline=""), delimiter=sep)
    lignes = []
    for numero, ligne in enumerate(lecteur, 2):
        propre = {normaliser(k): (v or "").strip() for k, v in ligne.items() if k is not None}
        if propre.get("colonne") and propre.get("fichier"):
            propre["fichier"] = fichier_relatif(propre["fichier"], numero)
            propre["_ligne"] = numero
            lignes.append(propre)
    if not lignes:
        raise ValueError("dictionnaire vide ou sans colonnes « fichier » et « colonne »")
    return lignes


def format_strftime(fmt):
    if not fmt:
        return None
    if "%" in fmt:
        return fmt
    jetons = [m.group(0) for m in re.finditer(r"([A-Za-z])\1*|[^A-Za-z]+", fmt)]
    sortie = []
    for k, jeton in enumerate(jetons):
        lettre = jeton[0].lower()
        n = len(jeton)
        if not jeton[0].isalpha():
            sortie.append(jeton)
        elif lettre in ("a", "y"):
            sortie.append("%Y" if n >= 3 else "%y")
        elif lettre in ("j", "d"):
            sortie.append("%d")
        elif lettre == "h":
            sortie.append("%H")
        elif lettre == "s":
            sortie.append("%S")
        elif lettre == "i":
            sortie.append("%M")
        elif lettre == "m":
            avant = jetons[k - 2][0].lower() if k >= 2 else ""
            minutes = avant == "h" and k >= 1 and ":" in jetons[k - 1]
            sortie.append("%M" if minutes else "%m")
        else:
            sortie.append(jeton)
    resultat = "".join(sortie)
    try:
        essai = dt.datetime(2021, 3, 4, 5, 6, 7).strftime(resultat)
        dt.datetime.strptime(essai, resultat)
    except ValueError:
        raise ValueError(f"format de date « {fmt} » non reconnu (exemples : jj/mm/aaaa, aaaa-mm-jj, jj/mm/aaaa hh:mm)")
    return resultat


TYPES_SYNONYMES = {
    "texte": "texte", "text": "texte", "chaine": "texte", "caractere": "texte", "caracteres": "texte",
    "character": "texte", "char": "texte", "varchar": "texte", "varchar2": "texte", "nvarchar": "texte",
    "string": "texte", "str": "texte", "object": "texte", "clob": "texte",
    "entier": "entier", "integer": "entier", "int": "entier", "int64": "entier", "int32": "entier",
    "bigint": "entier", "smallint": "entier", "long": "entier",
    "decimal": "decimal", "numerique": "decimal", "numeric": "decimal", "double": "decimal", "float": "decimal",
    "float64": "decimal", "real": "decimal", "reel": "decimal", "nombre": "decimal",
    "date": "date", "datetime": "datetime", "timestamp": "datetime", "posixct": "datetime", "date-heure": "datetime",
    "dateheure": "datetime", "heure": "texte",
    "booleen": "booleen", "boolean": "booleen", "bool": "booleen", "logical": "booleen", "logique": "booleen",
    "categorie": "categorie", "factor": "categorie", "facteur": "categorie", "category": "categorie",
}


def type_normalise(texte, numero=None):
    brut = normaliser(texte)
    if not brut:
        return "texte"
    m = re.fullmatch(r"([a-z0-9_\- ]+?)\s*(?:\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\))?", brut)
    if m:
        base = m.group(1).strip()
        if base == "number":
            return "decimal" if m.group(3) and int(m.group(3)) > 0 else ("entier" if m.group(2) else "decimal")
        if base in TYPES_SYNONYMES:
            return TYPES_SYNONYMES[base]
    lieu = f"ligne {numero} : " if numero else ""
    raise ValueError(f"{lieu}type « {texte} » inconnu (types acceptés : texte, entier, decimal, date, datetime, booleen, categorie, "
                     "ou leurs équivalents : VARCHAR2, NUMBER, integer, numeric, character, logical, factor…)")


def taux_lisible(texte, numero):
    brut = str(texte or "").strip().replace(",", ".")
    if not brut:
        return 0.0
    pourcent = brut.endswith("%")
    try:
        valeur = float(brut.rstrip("%").strip())
    except ValueError:
        raise ValueError(f"ligne {numero} : taux de manquants « {texte} » illisible (ex. 0.1 ou 10 %)")
    if pourcent or valeur > 1:
        valeur = valeur / 100
    return min(max(valeur, 0.0), 1.0)


def date_lisible(texte, fmt, numero):
    texte = str(texte).strip()
    essais = [fmt] if fmt else []
    essais += ["%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%Y"]
    for f in essais:
        try:
            return pd.Timestamp(dt.datetime.strptime(texte, f))
        except (ValueError, TypeError):
            continue
    raise ValueError(f"ligne {numero} : date « {texte} » illisible dans la plage (ex. 2019-01-01..2023-12-31)")


def depuis_motif(motif_texte, n, rng, deja=None):
    deja = set() if deja is None else deja
    if not motif_texte:
        motif_texte = "ID######"
    jetons = []
    i = 0
    while i < len(motif_texte):
        c = motif_texte[i]
        if c == "\\" and i + 1 < len(motif_texte):
            jetons.append(("lit", motif_texte[i + 1]))
            i += 2
            continue
        jetons.append(("var", c) if c in "#Xx" else ("lit", c))
        i += 1
    resultats = []
    essais = 0
    while len(resultats) < n:
        essais += 1
        if essais > n * 50 + 1000:
            jetons.append(("var", "#"))
            essais = 0
        caracteres = []
        for genre, c in jetons:
            if genre == "lit":
                caracteres.append(c)
            elif c == "#":
                caracteres.append(str(int(rng.integers(10))))
            elif c == "X":
                caracteres.append(chr(65 + int(rng.integers(26))))
            else:
                caracteres.append(chr(97 + int(rng.integers(26))))
        v = "".join(caracteres)
        if v not in deja:
            deja.add(v)
            resultats.append(v)
    return resultats


def intervalle(texte):
    if ".." in texte:
        a, b = texte.split("..", 1)
        return a.strip(), b.strip()
    return None


def colonne_profil(ligne, fmt_sortie):
    numero = ligne.get("_ligne")
    type_ = type_normalise(ligne.get("type", "texte"), numero)
    nature = normaliser(ligne.get("nature", "")) or ""
    manquants = taux_lisible(ligne.get("manquants"), numero)
    params = {}
    format_col = ligne.get("format", "")
    modalites = ligne.get("modalites", "")
    if ligne.get("cle") and nature not in ("identifiant", "nir", "code", "telephone"):
        nature = "identifiant"
    if type_ in ("date", "datetime") or nature in ("date", "date_naissance"):
        genre = "date_naissance" if nature == "date_naissance" else "date"
        fmt_date = format_strftime(format_col)
        bornes = intervalle(modalites) or ("2015-01-01", "2024-12-31")
        a = (date_lisible(bornes[0], fmt_date, numero) - pd.Timestamp(EPOQUE)) / pd.Timedelta(seconds=1)
        b = (date_lisible(bornes[1], fmt_date, numero) - pd.Timestamp(EPOQUE)) / pd.Timedelta(seconds=1)
        params = {"quantiles": [[0.0, a], [1.0, b]], "heure": type_ == "datetime",
                  "resolution": "minute" if type_ == "datetime" else "jour", "format": fmt_date}
        stockage = {"csv": "texte", "json": "texte", "jsonl": "texte", "sqlite": "texte"}.get(
            fmt_sortie, "datetime" if type_ == "datetime" else "date")
        if stockage == "texte" and not params["format"]:
            params["format"] = "%Y-%m-%d %H:%M:%S" if type_ == "datetime" else "%Y-%m-%d"
    elif nature in ("identifiant", "nir", "code", "telephone", "nom", "prenom", "email", "adresse"):
        genre = nature
        stockage = "texte" if fmt_sortie == "csv" or type_ not in ("entier", "decimal") else type_
        params = {"motif": format_col}
    elif type_ in ("entier", "decimal") and nature not in ("categorie", "discret") and not ("|" in modalites):
        genre = "numerique"
        bornes = intervalle(modalites) or ("0", "100")
        try:
            bornes = (float(str(bornes[0]).replace(",", ".")), float(str(bornes[1]).replace(",", ".")))
        except ValueError:
            raise ValueError(f"ligne {numero} : plage « {modalites} » illisible (ex. 0..100)")
        params = {"quantiles": [[0.0, bornes[0]], [1.0, bornes[1]]],
                  "entier": type_ == "entier", "decimale": ".",
                  "decimales": 0 if type_ == "entier" else (int(format_col) if format_col.isdigit() else 2)}
        stockage = "texte" if fmt_sortie == "csv" else type_
    elif type_ == "booleen" or nature == "booleen":
        genre = "booleen"
        params = {"p_vrai": 0.5, "modalites": [["TRUE", 0.5], ["FALSE", 0.5]]}
        if fmt_sortie == "csv":
            genre = "categorie"
            stockage = "texte"
        else:
            stockage = "booleen"
    elif nature == "texte_libre":
        genre = "texte_libre"
        params = {"quantiles": [[0.0, 20.0], [1.0, 200.0]]}
        stockage = "texte"
    else:
        genre = "categorie"
        labels = [m for m in modalites.split("|") if m] if modalites else []
        if type_ in ("entier", "decimal") and labels:
            try:
                labels = [int(x) if type_ == "entier" else float(x) for x in labels]
            except ValueError:
                pass
        if labels:
            params = {"modalites": [[l, 1 / len(labels)] for l in labels], "categories": [str(l) for l in labels]}
        else:
            params = {"generique": True, "n_uniques": 3}
        if fmt_sortie == "csv":
            stockage = "texte"
        elif type_ in ("entier", "decimal") and labels:
            stockage = type_
        elif fmt_sortie in ("rds", "rdata", "parquet", "feather") and type_ == "categorie":
            stockage = "categorie"
        else:
            stockage = "texte"
    return {"nom": ligne["colonne"], "stockage": stockage, "genre": genre, "taux_manquants": manquants,
            "jeton_manquant": "" if stockage == "texte" else None, "constant_par": None, "chrono_par": None,
            "params": params, "notes": [], "cle": ligne.get("cle", "")}


def options_par_defaut(fmt, nom_table, colonnes):
    if fmt == "csv":
        return {"encodage": "utf-8", "separateur": ",", "fin_ligne": "\n", "guillemets": "minimal"}
    if fmt == "xlsx":
        return {"lignes_titre": 0, "titres_non_vides": []}
    if fmt in ("rds", "rdata"):
        return {"objet": nom_table, "classes_r": {}}
    if fmt == "sqlite":
        types = {"entier": "INTEGER", "decimal": "REAL", "booleen": "INTEGER"}
        definition = ", ".join('"' + c["nom"].replace('"', '""') + '" ' + types.get(c["stockage"], "TEXT") for c in colonnes)
        return {"sql": f'CREATE TABLE "{nom_table}" ({definition})', "sql_annexes": []}
    if fmt in ("sav", "dta", "xpt"):
        return {"labels": {}, "etiquettes": {}, "formats": {}, "mesures": {}, "nom_table": nom_table}
    if fmt in ("json", "jsonl"):
        return {"orient": "records", "indent": 2}
    return {}


ORIGINES = {"entier": "int64", "decimal": "float64", "datetime": "datetime64[us]", "booleen": "bool"}


def sosie_depuis_dictionnaire(lignes, n_lignes=500, n_individus=100, graine=None):
    rng = np.random.default_rng(graine)
    faussaire = Faussaire(rng)
    groupes = {}
    for l in lignes:
        groupes.setdefault((l["fichier"], l.get("feuille") or None), []).append(l)
    pools = {}
    deja = set()
    tables = []
    profil = {"seuil": 0, "tables": []}
    for (fichier, feuille), lignes_table in groupes.items():
        if not Path(fichier).suffix:
            fichier = fichier + ".csv"
        fmt = format_de(fichier) or "csv"
        if fmt == "sas7bdat":
            fmt = "xpt"
            fichier = str(Path(fichier).with_suffix(".xpt"))
        if fmt == "xls":
            fmt = "xlsx"
            fichier = str(Path(fichier).with_suffix(".xlsx"))
        colonnes = [colonne_profil(l, fmt) for l in lignes_table]
        unique = None
        for c in colonnes:
            if c["cle"] and "unique" in c["cle"].lower():
                unique = c
                break
        n = n_individus if unique else n_lignes
        valeurs_par_colonne = []
        for c in colonnes:
            g = c["genre"]
            if g in ("identifiant", "nir", "code", "telephone"):
                nom_cle = c["cle"].split("(")[0].strip() if c["cle"] else None
                motif_col = c["params"].get("motif") or ("#" * 8 if c["stockage"] in ("entier", "decimal") else "")
                if nom_cle:
                    if nom_cle not in pools:
                        pools[nom_cle] = depuis_motif(motif_col, n_individus, rng, deja)
                    pool = pools[nom_cle]
                    if c is unique:
                        valeurs = list(rng.permutation(pool))[:n]
                    else:
                        valeurs = [pool[i] for i in rng.integers(len(pool), size=n)]
                else:
                    valeurs = depuis_motif(motif_col or ("#" * 10 if g in ("telephone", "nir") else ""), n, rng, deja)
                manque = np.zeros(n, dtype=bool) if c is unique else (rng.random(n) < c["taux_manquants"])
                valeurs_par_colonne.append((valeurs, None, manque))
                continue
            if g in ("nom", "prenom", "email", "adresse"):
                valeurs = [faussaire.generer(g, str(i), {"casse": "titre", "mots": 1}) for i in rng.integers(n_individus, size=n)]
                valeurs_par_colonne.append((valeurs, None, rng.random(n) < c["taux_manquants"]))
                continue
            vals, jetons = tirer(g, c["params"], n, rng, c["stockage"])
            valeurs_par_colonne.append((list(vals), jetons, rng.random(n) < c["taux_manquants"]))
        series = {}
        for j, (c, (valeurs, jetons, manque)) in enumerate(zip(colonnes, valeurs_par_colonne)):
            origine = pd.Series([], dtype=ORIGINES.get(c["stockage"], "object"))
            series[j] = vers_serie(c, valeurs, jetons, manque, origine)
        donnees = pd.DataFrame(series)
        nom_table = feuille or Path(fichier).stem
        options = options_par_defaut(fmt, nom_table, colonnes)
        t = Table(fichier, feuille if fmt in ("xlsx", "rdata", "sqlite") else None, fmt,
                  [c["nom"] for c in colonnes], donnees, [c["stockage"] for c in colonnes], options)
        if fmt == "xlsx" and t.feuille is None:
            t.feuille = "Feuille1"
        if fmt == "sqlite" and t.feuille is None:
            t.feuille = nom_table
        tables.append(t)
        profil["tables"].append({"fichier": fichier, "feuille": t.feuille, "format": fmt, "n_lignes": n,
                                 "entite": None, "ordre_dates": [], "colonnes": colonnes})
    return tables, profil
