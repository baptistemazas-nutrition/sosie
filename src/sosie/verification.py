import datetime as dt
import gzip
import html
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DOSSIER_DONNEES, DOSSIER_VERIFIES, ErreurSosie, cle_nom
from .execution import MANIFESTE_EXECUTION
from .listes import MOTS_COURANTS
from .formats import est_manquant, fichier_ignore, lire_fichier, lister_fichiers
from .profil import (
    GENRES_DATES, codes_entite, entites_completes, est_generique, frequences_sures, jetons_nom, preparer_dates,
    profiler, sans_accents,
)

EXT_TABLEAUX = {".csv", ".tsv", ".tab", ".dat", ".xlsx", ".xlsm", ".xls", ".parquet", ".feather", ".arrow", ".sav",
                ".dta", ".json", ".jsonl", ".rds", ".rdata", ".rda"}
EXT_IMAGES = {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".tif", ".tiff", ".gif", ".eps", ".emf", ".wmf", ".bmp", ".webp"}
EXT_BUREAUTIQUE = {".docx", ".pptx", ".odt", ".odp", ".xlsx", ".xlsm"}
EXT_OBJETS = {".pkl", ".pickle", ".joblib", ".h5", ".hdf5", ".npy", ".npz", ".sqlite", ".db", ".sqlite3", ".pt",
              ".onnx", ".model", ".xpt", ".sas7bdat", ".zip", ".gz", ".rdb", ".rdx", ".fst", ".qs", ".bin", ".duckdb"}
EXT_DONNEES_INDIVIDUELLES = {".rds", ".rdata", ".rda", ".parquet", ".feather", ".arrow", ".sav", ".dta", ".xpt",
                             ".csv", ".tsv", ".pkl", ".pickle", ".joblib", ".fst", ".qs", ".sqlite", ".db", ".rdb", ".rdx"}
EXT_BIBLIOTHEQUES = {".js", ".css", ".map", ".woff", ".woff2", ".ttf", ".eot", ".otf"}
JETONS_EFFECTIF = {"n", "nb", "nbr", "nombre", "effectif", "effectifs", "count", "counts", "freq", "frequence",
                   "frequency", "total", "cas", "patients", "individus", "sujets", "events", "evenements", "nobs",
                   "hommes", "femmes", "deces", "malades", "personnes", "participants", "support", "vp", "fp", "fn",
                   "vn", "tp", "tn", "risk", "event", "censor", "censored", "obs", "observations"}
NON_COMPTES = {"annee", "year", "an", "df", "ddl", "rang", "rank", "ordre", "order", "num", "numero", "id", "k", "fold",
               "iter", "iteration", "epoch", "seed", "graine", "age", "visite", "mois", "jour", "semaine", "duree",
               "delai", "heure", "minute", "seconde", "ligne", "colonne", "index", "niveau", "stade", "grade", "code",
               "classe", "cluster", "groupe", "version", "dose", "score", "decile", "quartile", "quintile", "tercile",
               "centile", "percentile", "lag", "step", "etape", "modele", "model", "degre", "degree", "nbins", "bins",
               "time", "temps", "figure", "fig", "table", "tableau", "page", "chapitre", "section", "mediane", "median",
               "moyenne", "mean", "moy", "q1", "q3", "quartile", "quartiles", "min", "max", "minimum", "maximum", "sd",
               "et", "ecart", "iqr", "p25", "p75", "p5", "p95", "ic", "ci", "lower", "upper", "inf", "sup", "or", "hr",
               "rr", "beta", "coef", "estimate", "estimation", "se", "pvalue", "p", "auc", "sensibilite", "specificite",
               "vpp", "vpn", "precision", "recall", "f1", "score", "pct", "pourcentage", "prop", "proportion", "taux"}
TAILLE_MAX = 50 * 1024 * 1024
TAILLE_PARTIELLE = 16 * 1024 * 1024

RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
RE_JETON = re.compile(r"[\w@.+\-]+", re.UNICODE)
RE_CHIFFRES = re.compile(r"(?<![\d])\d(?:[  .\-/]?\d){6,}(?![\d])")
RE_TEL_SORTIE = re.compile(r"(?<!\d)(?:\+33\s?|0033\s?|0)?[1-9](?:[\s.-]?\d{2}){4}(?!\d)")
RE_N_EGAL = re.compile(r"\b[nN]\s*[=:]\s*(\d+)\b(?![.,]\d)")
RE_N_POURCENT = re.compile(r"(?<![\d.,])(\d+)\s*\(\s*\d+(?:[.,]\d+)?\s*%\s*\)")
RE_FRACTION = re.compile(r"(?<![\d.,/])(\d+)\s*/\s*(\d+)(?![\d.,/])")
RE_MOT_EFFECTIF = re.compile(
    r"(?<![\d.,])(\d+)\s+(patients?|patientes?|sujets?|individus?|personnes?|cas|hommes?|femmes?|participants?|"
    r"d[ée]c[èe]s|[ée]v[ée]nements?|malades?|enfants?)\b", re.IGNORECASE)
RE_LIBELLE_EFFECTIF = re.compile(r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 '’()\-]{1,60}?)\s*:\s*(\d+)\s*$")
RE_CELLULE_N_POURCENT = re.compile(r"^\s*(\d+)\s*\(\s*\d+(?:[.,]\d+)?\s*%?\s*\)\s*$")
RE_CELLULE_FRACTION = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
RE_CELLULE_N_EGAL = re.compile(r"\(\s*[nN]\s*=\s*(\d+)\s*\)")
RE_DATE_JMA = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})(?!\d)")
RE_DATE_JMA_COURT = re.compile(r"(?<![\d/.\-])(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2})(?![\d/.\-])")
RE_DATE_AMJ = re.compile(r"(?<!\d)(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})(?!\d)")
RE_DATE_COMPACTE = re.compile(r"(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)")
MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "septembre": 9,
        "octobre": 10, "novembre": 11, "decembre": 12, "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
        "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12, "jan": 1,
        "feb": 2, "fev": 2, "mar": 3, "apr": 4, "avr": 4, "jun": 6, "jul": 7, "juil": 7, "aug": 8, "sep": 9, "sept": 9,
        "oct": 10, "nov": 11, "dec": 12}
RE_DATE_TEXTE = re.compile(r"\b(\d{1,2})(?:er)?\s+([a-z]{3,9})\.?\s+(\d{4})\b")
RE_DATE_TEXTE_US = re.compile(r"\b([a-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b")
RE_DECIMAL = re.compile(r"(?<![\d.,])-?\d+[.,]\d+(?![.,]?\d)")
RE_NOMBRE = re.compile(r"(?<![\w.,])-?\d+(?:[.,]\d+)?(?![\w.,]?\d)")
RE_ENTIER_SEUL = re.compile(r"^[+-]?\d+$")
RE_ENTIER_FLOTTANT = re.compile(r"^[+-]?\d+(?:\.0+)?(?:[eE][+-]?\d+)?$")
RE_WIDGET = re.compile(r"htmlwidget|data-for=|plotly|<canvas|vega-embed|bokeh|highcharts|leaflet|datatables|ojs|pagedtable", re.IGNORECASE)
RE_FIGURE = re.compile(r"<img\b[^>]*src=\"(?!data:image/svg)|<figure\b|class=\"[^\"]*figure", re.IGNORECASE)
RE_PROGRESSION = re.compile(
    r"^\s*(?:\d+/\d+\s*(?:\[[^\]]*\])?|\|[\s.=>*]*\|\s*\d+%.*|processing file.*|output file.*|label:.*|"
    r"quitting from lines.*|executing .*\.qmd.*|\[\d+/\d+\].*|cell \d+/\d+.*|# (?:a tibble|a data frame|groups|source|ℹ|…).*|"
    r"(?:<[a-z]{2,5}>\s*)+)\s*$", re.IGNORECASE)
RE_NUMERO_OBJET = re.compile(r"\b(figure|fig\.?|table|tableau|tab\.?|annexe|chapitre|section|page|ligne|étape|etape)\s*(\d+)", re.IGNORECASE)
RE_MINMAX = re.compile(r"\b(min|max|minimum|maximum|minimale?|maximale?|range|étendue|etendue|extr[êe]mes?)\b\.?", re.IGNORECASE)
RE_RESIDUS = re.compile(r"Residuals:\s*\n\s*Min\s+1Q\s+Median\s+3Q\s+Max", re.IGNORECASE)

OK, REVOIR, BLOQUE, VOIR = "✅", "⚠️", "⛔", "👁"
ORDRE = {OK: 0, VOIR: 1, REVOIR: 2, BLOQUE: 3}
LIBELLES = {
    OK: "partageable",
    VOIR: "non vérifiable automatiquement : à regarder toi-même",
    REVOIR: "à revoir avant de partager",
    BLOQUE: "bloqué : contient des informations identifiantes des vraies données",
}


def plier(texte):
    return sans_accents(str(texte)).casefold()


def mots(texte):
    return re.findall(r"[a-z0-9@]+", plier(texte))


def phrase(texte):
    return " ".join(mots(texte))


def compact(texte):
    return re.sub(r"[^a-z0-9]", "", plier(texte))


def norm_nombre(s):
    s = str(s).strip().replace(",", ".")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", s):
        return None
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    s = s.lstrip("+")
    if s.startswith("-"):
        s = "-" + (s[1:].lstrip("0") or "0")
    else:
        s = s.lstrip("0") or "0"
    if s.startswith("."):
        s = "0" + s
    if s.startswith("-."):
        s = "-0" + s[1:]
    return "0" if s in ("-0", "") else s


def entier_de(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return int(f) if np.isfinite(f) and f.is_integer() else None
    if isinstance(v, str):
        s = v.strip()
        if RE_ENTIER_FLOTTANT.match(s):
            try:
                f = float(s)
            except ValueError:
                return None
            return int(f) if np.isfinite(f) and f.is_integer() else None
    return None


RE_COMPTE_TEXTE = re.compile(r"^[+-]?\d+(?:\.0)?$|^[+-]?\d(?:\.\d+)?[eE][+-]?\d+$")


def entier_compte(c):
    s = str(c).strip()
    if not RE_COMPTE_TEXTE.match(s):
        return None
    return entier_de(s)


def chiffres_seuls(s):
    return re.sub(r"\D", "", str(s))


def date_iso(annee, mois, jour):
    try:
        return dt.date(int(annee), int(mois), int(jour)).isoformat()
    except (ValueError, TypeError):
        return None


def sans_ansi(texte):
    return RE_ANSI.sub("", texte)


class Sensibles:
    def __init__(self):
        self.forts = set()
        self.faibles = set()
        self.chiffres = set()
        self.telephones = set()
        self.phrases = set()
        self.rares = set()
        self.colles = set()
        self.paires = set()
        self.naissances = set()
        self.dates = set()
        self.dates_denses = False
        self.riches = []
        self.extremes = set()
        self.extremes_rares = set()
        self.colonnes = set()
        self.colonnes_dates = set()
        self.jetons_colonnes = set()
        self.publics = set()
        self.mots_publics = set()
        self.n_individus = 0
        self.vide = True
        self._index = None

    def index_phrases(self):
        if self._index is None:
            index = {}
            for genre, ensemble in (("fort", self.phrases), ("rare", self.rares)):
                for p in ensemble:
                    morceaux = p.split()
                    if morceaux:
                        index.setdefault(morceaux[0], []).append((morceaux, len(morceaux), genre))
            self._index = index
        return self._index


def ajouter_identifiant(sensibles, valeur):
    v = plier(valeur).strip()
    if not v:
        return
    chiffres = chiffres_seuls(v)
    lettres = sum(c.isalpha() for c in v)
    sans_zeros = chiffres.lstrip("0") or "0"
    if lettres == 0 and len(sans_zeros) >= 5:
        if len(sans_zeros) >= 7:
            sensibles.chiffres.add(chiffres)
            sensibles.chiffres.add(sans_zeros)
            sensibles.forts.add(chiffres)
            sensibles.forts.add(sans_zeros)
        else:
            sensibles.faibles.add(chiffres)
            sensibles.faibles.add(sans_zeros)
        return
    if lettres == 0:
        return
    if " " in v.strip():
        p = phrase(v)
        if len(p) >= 6:
            sensibles.phrases.add(" ".join(p.split()[:6]))
        for m in mots(v):
            if len(m) >= 4 and not m.isdigit():
                sensibles.faibles.add(m)
        return
    if len(v) >= 4 and any(c.isalpha() for c in v) and any(c.isdigit() for c in v):
        sensibles.forts.add(v)
        if len(sans_zeros) >= 7:
            sensibles.chiffres.add(chiffres)
    elif len(v) >= 6:
        sensibles.forts.add(v)


def construire_sensibles(dossier_donnees, seuil):
    tables = []
    for chemin, rel in lister_fichiers(dossier_donnees):
        try:
            tables.extend(t for t in lire_fichier(chemin, rel) if not t.options.get("vide"))
        except Exception:
            continue
    return sensibles_depuis_tables(tables, seuil)


def densite(valeurs, pas):
    if len(valeurs) < 2:
        return 0.0
    bas, haut = min(valeurs), max(valeurs)
    cases = (haut - bas) / pas + 1
    return len(valeurs) / cases if cases > 0 else 1.0


def ajouter_rare(sensibles, texte):
    texte = str(texte)
    if est_generique(texte):
        return
    p = phrase(texte)
    if len(p) >= 3:
        sensibles.rares.add(" ".join(p.split()[:6]))


def sensibles_depuis_tables(tables, seuil):
    sensibles = Sensibles()
    tables = [t for t in tables if not t.options.get("vide")]
    if not tables:
        return sensibles
    sensibles.vide = False
    par_table, structures = profiler(tables, seuil)
    dates_ordinaires = set()
    for t, liste, s in zip(tables, par_table, structures):
        codes = codes_entite(s["entite"]) if s["entite"] is not None else None
        n = len(set(c for c in codes.tolist() if c >= 0)) if codes is not None else t.n_lignes
        sensibles.n_individus = max(sensibles.n_individus, n)
        sensibles.publics.add(phrase(Path(t.fichier).stem))
        if t.feuille:
            sensibles.publics.add(phrase(t.feuille))
        for nom in t.noms:
            if len(phrase(nom)) >= 2:
                sensibles.colonnes.add(phrase(nom))
                sensibles.publics.add(phrase(nom))
                sensibles.jetons_colonnes |= set(jetons_nom(str(nom)))
        etiquettes = t.options.get("etiquettes") or {}
        noms_par_genre = {}
        for a in liste:
            noms_par_genre.setdefault(a.genre, []).append(a)
        for a in liste:
            g = a.genre
            cles = a.cles()
            distinctes = set(c for c in cles if c is not None)
            if g in ("identifiant", "nir"):
                for c in distinctes:
                    ajouter_identifiant(sensibles, c)
            elif g == "code":
                ents = entites_completes(codes, len(cles))
                valides = [(c, e) for c, e in zip(cles, ents) if c is not None]
                res = frequences_sures([c for c, _ in valides], [e for _, e in valides], seuil)
                for c in res["rares"]:
                    if len(str(c)) >= 5:
                        sensibles.faibles.add(plier(c))
                for c, _ in res["gardees"]:
                    sensibles.publics.add(phrase(c))
            elif g in ("nom", "prenom"):
                porteurs_mots = {}
                for c in distinctes:
                    p = phrase(c)
                    if " " in p:
                        sensibles.phrases.add(p)
                    for m in set(mots(c)):
                        if len(m) >= 3 and not m.isdigit():
                            porteurs_mots[m] = porteurs_mots.get(m, 0) + 1
                for m, k in porteurs_mots.items():
                    if k < seuil:
                        sensibles.faibles.add(m)
            elif g == "email":
                for c in distinctes:
                    sensibles.forts.add(plier(c))
            elif g == "telephone":
                for c in distinctes:
                    chiffres = chiffres_seuls(c)
                    if len(chiffres) >= 8:
                        sensibles.telephones.add(chiffres[-9:])
            elif g == "adresse":
                for c in distinctes:
                    p = phrase(c)
                    if len(p) >= 8:
                        sensibles.phrases.add(" ".join(p.split()[:6]))
                        rue = phrase(str(c).split(",")[0])
                        if len(rue) >= 8:
                            sensibles.phrases.add(" ".join(rue.split()[:6]))
            elif g in GENRES_DATES:
                sensibles.colonnes_dates.add(phrase(a.nom))
                secondes = preparer_dates(a)
                isos = set()
                for s_ in secondes[~np.isnan(secondes)]:
                    try:
                        isos.add((dt.datetime(1970, 1, 1) + dt.timedelta(seconds=float(s_))).date().isoformat())
                    except (OverflowError, ValueError):
                        pass
                if g == "date_naissance":
                    sensibles.naissances |= isos
                else:
                    sensibles.dates |= isos
                    dates_ordinaires |= isos
            elif g == "texte_libre":
                for c in distinctes:
                    p = phrase(c)
                    if not p:
                        continue
                    morceaux = p.split()
                    if len(morceaux) >= 3:
                        sensibles.rares.add(" ".join(morceaux[:6]))
                    elif len(p) >= 3 and not est_generique(c):
                        sensibles.rares.add(p)
            elif g in ("categorie", "discret", "ville", "code_postal", "constante"):
                ents = entites_completes(codes, len(cles))
                valides = [(c, e) for c, e in zip(cles, ents) if c is not None]
                res = frequences_sures([c for c, _ in valides], [e for _, e in valides], seuil)
                for c, _ in res["gardees"]:
                    sensibles.publics.add(phrase(c))
                labels = etiquettes.get(a.nom) or {}
                for c in res["rares"]:
                    texte = str(c)
                    if est_generique(texte):
                        continue
                    for code, libelle in labels.items():
                        if norm_nombre(code) is not None and norm_nombre(code) == norm_nombre(texte) or str(code) == texte:
                            ajouter_rare(sensibles, libelle)
                    nom_compact = compact(a.nom)
                    if len(nom_compact) >= 3:
                        valeur = compact(texte)
                        if valeur:
                            sensibles.colles.add(nom_compact + valeur)
                            if norm_nombre(texte) is not None and "." not in norm_nombre(texte):
                                sensibles.colles.add(nom_compact + valeur + "0")
                    if re.fullmatch(r"[\d\s.,+-]+", texte):
                        if g == "code_postal" and len(chiffres_seuls(texte)) == 5:
                            sensibles.faibles.add(chiffres_seuls(texte))
                        continue
                    ajouter_rare(sensibles, texte)
            if g in ("numerique", "discret"):
                ents = entites_completes(codes, len(cles))
                paires = [(norm_nombre(c), e) for c, e in zip(cles, ents) if c is not None]
                paires = [(v, e) for v, e in paires if v is not None]
                if paires:
                    tableau = pd.DataFrame({"v": [float(v) for v, _ in paires], "e": [e for _, e in paires]})
                    for extreme in (tableau["v"].min(), tableau["v"].max()):
                        porteurs = tableau.loc[tableau["v"] == extreme, "e"].nunique()
                        if porteurs < seuil:
                            texte = norm_nombre(repr(float(extreme)))
                            if texte is not None:
                                sensibles.extremes_rares.add(texte)
                valeurs = {v for v, _ in paires}
                decimales = {v for v in valeurs if "." in v and significatif(v)}
                if g == "numerique" and len(decimales) >= 20 and len(decimales) >= 0.3 * len(valeurs):
                    precision = max(len(v.split(".")[1]) for v in decimales)
                    flottants = [float(v) for v in decimales]
                    if densite(flottants, 10 ** -precision) <= 0.2:
                        sensibles.riches.append((a.nom, decimales))
                        nombres = sorted(float(v) for v in valeurs)
                        for v in (nombres[0], nombres[-1]):
                            texte = norm_nombre(repr(v))
                            if texte and len(re.sub(r"[^\d]", "", texte).lstrip("0")) >= 3:
                                sensibles.extremes.add(texte)
        noms = noms_par_genre.get("nom", [])
        prenoms = noms_par_genre.get("prenom", [])
        for an in noms:
            for ap in prenoms:
                for cn, cp in zip(an.cles(), ap.cles()):
                    if cn is None or cp is None:
                        continue
                    for mn in mots(cn):
                        for mp in mots(cp):
                            if len(mn) >= 2 and len(mp) >= 2:
                                sensibles.paires.add((mn, mp))
    if dates_ordinaires:
        jours = sorted(dt.date.fromisoformat(d).toordinal() for d in dates_ordinaires)
        sensibles.dates_denses = densite(jours, 1) > 0.3
    sensibles.rares = {r for r in sensibles.rares if r not in sensibles.publics and r not in sensibles.colonnes}
    for public in sensibles.publics | sensibles.colonnes:
        sensibles.mots_publics |= set(public.split())
    try:
        sensibles.mots_publics |= set(mots(Path.home().name))
    except (RuntimeError, OSError):
        pass
    sensibles.faibles = {f for f in sensibles.faibles if f not in sensibles.publics and f not in sensibles.mots_publics
                         and f not in MOTS_COURANTS}
    sensibles.paires = {(n, q) for n, q in sensibles.paires if f"{n} {q}" not in sensibles.publics
                        and f"{q} {n}" not in sensibles.publics}
    return sensibles


class Constat:
    def __init__(self):
        self.forts = set()
        self.faibles = set()
        self.rares = set()
        self.naissances = set()
        self.petits = []
        self.individuels = []
        self.extremes = set()
        self.voir = []
        self.partiel = []
        self.revoir = []


def ngrammes(liste_mots, n_max=6):
    sortie = set()
    for n in range(1, n_max + 1):
        for i in range(len(liste_mots) - n + 1):
            sortie.add(" ".join(liste_mots[i:i + n]))
    return sortie


def nettoyer_comptes(texte):
    lignes = []
    for ligne in sans_ansi(texte).splitlines():
        if RE_PROGRESSION.match(ligne):
            continue
        lignes.append(RE_NUMERO_OBJET.sub(lambda m: m.group(1) + " X", ligne))
    return "\n".join(lignes)


def cellules_ligne(brute):
    ligne = brute.replace("[", " ").replace("]", " ")
    cellules = [c.strip().rstrip("\\").strip() for c in re.split(r"[|&\t;]|\s{1,}", ligne.strip())]
    return [c for c in cellules if c and c not in ("-", ":", "--")]


def colonnes_effectif(entete):
    return [k for k, c in enumerate(entete) if set(jetons_nom(c.replace(".", " "))) & JETONS_EFFECTIF
            and not set(jetons_nom(c.replace(".", " "))) & NON_COMPTES]


def positions_jetons(ligne):
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", ligne)]


def valeurs_sous_entete(entete_brute, ligne, colonnes):
    jetons_entete = positions_jetons(entete_brute)
    jetons_ligne = positions_jetons(ligne)
    sortie = []
    for k in colonnes:
        if k >= len(jetons_entete):
            continue
        _, debut, fin = jetons_entete[k]
        meilleur = None
        for texte, d, f in jetons_ligne:
            if f >= debut and d <= fin:
                ecart = abs(f - fin)
                if meilleur is None or ecart < meilleur[0]:
                    meilleur = (ecart, texte)
        if meilleur is not None:
            sortie.append(meilleur[1])
    return sortie


def lignes_comptes(texte, seuil):
    trouves = []
    lignes = texte.splitlines()
    bloc = False
    entete = None
    entete_brute = None
    for k, brute in enumerate(lignes):
        if re.match(r"^\s*\[\d+\]", brute):
            bloc = False
            entete = None
            continue
        cellules = cellules_ligne(brute)
        if len(cellules) < 2:
            bloc = False
            entete = None
            continue
        if all(not RE_ENTIER_FLOTTANT.match(c) and not re.fullmatch(r"-?\d+[.,]\d+", c) for c in cellules) and any(ch.isalpha() for ch in brute):
            entete = cellules
            entete_brute = brute
            bloc = True
            continue
        if entete is not None:
            effectifs = colonnes_effectif(entete)
            if effectifs:
                jetons_entete = [t for t, _, _ in positions_jetons(entete_brute)]
                indices = [i for i, t in enumerate(jetons_entete) if set(jetons_nom(t.replace(".", " "))) & JETONS_EFFECTIF
                           and not set(jetons_nom(t.replace(".", " "))) & NON_COMPTES]
                candidats = valeurs_sous_entete(entete_brute, brute, indices)
                if "|" not in brute and "\t" not in brute and candidats:
                    valeurs = candidats
                else:
                    decalage = len(cellules) - len(entete)
                    valeurs = [cellules[j + decalage] for j in effectifs if 0 <= j + decalage < len(cellules)]
                for c in valeurs:
                    v = entier_compte(c)
                    if v is not None and 1 <= v < seuil:
                        trouves.append(brute.strip()[:120])
                        break
                continue
        suffixe = []
        for c in reversed(cellules):
            if entier_compte(c) is not None:
                suffixe.append(c)
            else:
                break
        suffixe.reverse()
        prefixe = cellules[:len(cellules) - len(suffixe)]
        if not suffixe:
            bloc = any(ch.isalpha() for ch in brute)
            continue
        etiquette = [c for c in prefixe if not RE_ENTIER_SEUL.match(c)]
        matrice = brute.lstrip().startswith("[[") or brute.lstrip().startswith("[")
        if len(suffixe) == 1 and not etiquette:
            bloc = False
            continue
        precedente = lignes[k - 1] if k > 0 else ""
        if not (bloc or matrice or etiquette or any(ch.isalpha() for ch in precedente)):
            continue
        if etiquette and set(jetons_nom(" ".join(etiquette))) & NON_COMPTES:
            continue
        bloc = True
        if any(1 <= entier_compte(c) < seuil for c in suffixe):
            trouves.append(brute.strip()[:120])
    return trouves


def separateur_ligne(ligne):
    if ligne.count("|") >= 2:
        return "|"
    if "\t" in ligne:
        return "\t"
    if ligne.count("&") >= 1 and ligne.rstrip().endswith("\\\\"):
        return "&"
    return None


def comptes_tableaux_texte(texte, seuil):
    trouves = []
    blocs = []
    courant, sep_courant = [], None
    for ligne in texte.splitlines():
        sep = separateur_ligne(ligne)
        if sep and sep == sep_courant:
            courant.append(ligne)
            continue
        if len(courant) >= 2:
            blocs.append((sep_courant, courant))
        courant, sep_courant = ([ligne], sep) if sep else ([], None)
    if len(courant) >= 2:
        blocs.append((sep_courant, courant))
    for sep, lignes in blocs:
        rangees = []
        for ligne in lignes:
            morceau = ligne.strip().rstrip("\\").strip()
            cellules = [c.strip() for c in morceau.strip(sep).split(sep)]
            if all(re.fullmatch(r":?-{2,}:?", c) or c == "" for c in cellules):
                continue
            rangees.append(cellules)
        if len(rangees) < 2:
            continue
        entete = rangees[0]
        colonnes = colonnes_effectif(entete)
        corps = rangees[1:]
        tout_entier = all(entier_compte(c) is not None for r in corps for c in r[1:] if c not in ("", "-")) and any(len(r) > 1 for r in corps)
        if tout_entier and not set(jetons_nom(" ".join(entete))) & {"annee", "year", "age", "an"}:
            colonnes = sorted(set(colonnes) | set(range(1, max(len(r) for r in rangees))))
        for rangee in corps:
            for k in colonnes:
                if k < len(rangee):
                    m = re.match(r"^\s*(\d+)(?![.,]\d)", rangee[k])
                    if m and 1 <= int(m.group(1)) < seuil:
                        trouves.append(" | ".join(rangee)[:120])
                        break
    return trouves


def significatif(v):
    return len(re.sub(r"\D", "", v).lstrip("0")) >= 3


def dates_du_texte(texte, courtes=False):
    trouvees = set()
    for m in RE_DATE_JMA.finditer(texte):
        for iso in (date_iso(m.group(3), m.group(2), m.group(1)), date_iso(m.group(3), m.group(1), m.group(2))):
            if iso:
                trouvees.add(iso)
    for regex in (RE_DATE_AMJ, RE_DATE_COMPACTE):
        for m in regex.finditer(texte):
            iso = date_iso(m.group(1), m.group(2), m.group(3))
            if iso:
                trouvees.add(iso)
    plie = plier(texte)
    for m in RE_DATE_TEXTE.finditer(plie):
        mois = MOIS.get(m.group(2))
        if mois:
            iso = date_iso(m.group(3), mois, m.group(1))
            if iso:
                trouvees.add(iso)
    for m in RE_DATE_TEXTE_US.finditer(plie):
        mois = MOIS.get(m.group(1))
        if mois:
            iso = date_iso(m.group(3), mois, m.group(2))
            if iso:
                trouvees.add(iso)
    if courtes:
        for m in RE_DATE_JMA_COURT.finditer(texte):
            for siecle in ("19", "20"):
                iso = date_iso(siecle + m.group(3), m.group(2), m.group(1))
                if iso:
                    trouvees.add(iso)
    return trouvees


RE_CHEMIN = re.compile(r"(?:[A-Za-z]:)?(?:[/\\](?=[\w.\-~@+]*[A-Za-z])[\w.\-~@+]+){2,}[/\\]?")
RE_POURCENT = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*%")


def pourcentages_petits(texte, seuil, n_individus, constat):
    if not n_individus or n_individus <= 0:
        return
    limite = 100.0 * seuil / n_individus
    for m in RE_POURCENT.finditer(texte):
        v = float(m.group(1).replace(",", "."))
        if 0 < v < limite:
            debut = max(0, m.start() - 40)
            constat.petits.append(texte[debut:m.end() + 10].replace("\n", " ").strip() + f" (moins de {seuil} individus sur {n_individus})")
    for ligne in texte.splitlines():
        nombres = [x.replace(",", ".") for x in re.findall(r"(?<![\w.,])\d+(?:[.,]\d+)?(?![\w.,]?\d)", ligne)]
        if len(nombres) < 2 or not any("." in x for x in nombres):
            continue
        valeurs = [float(x) for x in nombres]
        if abs(sum(valeurs) - 100) <= 0.6 and any(0 < v < limite for v in valeurs):
            constat.petits.append(ligne.strip()[:120] + f" (pourcentages : moins de {seuil} individus sur {n_individus})")


AGREGATS = {"moyenne", "moy", "mean", "mediane", "median", "sd", "et", "ecart", "q1", "q3", "iqr", "ic", "ci", "min", "max",
            "minimum", "maximum", "quartile", "estimate", "coef", "beta", "or", "hr", "rr", "pvalue", "se", "statistic"}
GENERIQUES_COLONNES = {"date", "num", "numero", "type", "code", "id", "n", "nb", "de", "du", "la", "le", "a"}


def tableaux_imprimes(texte, sensibles, constat):
    reels_jetons = sensibles.jetons_colonnes - GENERIQUES_COLONNES
    if len(reels_jetons) < 3:
        return
    lignes = texte.splitlines()
    for k, ligne in enumerate(lignes[:-1]):
        morceaux = ligne.split()
        if len(morceaux) < 3 or len(morceaux) > 60 or any(ch.isdigit() for ch in "".join(morceaux[:1])):
            continue
        jetons = [set(jetons_nom(t)) for t in morceaux]
        if any(j & (JETONS_EFFECTIF | AGREGATS) for j in jetons):
            continue
        reels = [t for t, j in zip(morceaux, jetons) if j & reels_jetons]
        if len(reels) < 3:
            continue
        donnees = 0
        for suite in lignes[k + 1:k + 400]:
            if not suite.strip():
                break
            if re.match(r"^\s*(?:<[a-z]{2,5}>\s*)+$", suite):
                continue
            if re.match(r"^\s*\d+\s", suite) and len(suite.split()) >= 3:
                donnees += 1
            elif len(re.findall(r"-?\d+(?:[.,]\d+)?", suite)) >= 2:
                donnees += 1
            else:
                break
        if donnees >= 1:
            constat.individuels.append(f"tableau imprimé de {donnees} ligne(s) avec les colonnes des vraies données "
                                       f"({', '.join(reels[:4])}) : liste d'individus ?")


def analyser_texte(texte, sensibles, seuil, constat, comptes=True):
    if not texte:
        return
    texte = sans_ansi(texte)
    texte = RE_CHEMIN.sub(" ", texte)
    tableaux_imprimes(texte, sensibles, constat)
    plie = plier(texte)
    for jeton in RE_JETON.findall(plie):
        candidats = {jeton, jeton.strip(".-+"), re.sub(r"\.0+$", "", jeton)}
        for morceau in re.split(r"[_\-.]", jeton):
            if morceau:
                candidats.add(morceau)
        chiffres = chiffres_seuls(jeton)
        if len(chiffres) >= 5:
            candidats.add(chiffres)
            if len(chiffres.lstrip("0")) >= 5:
                candidats.add(chiffres.lstrip("0"))
        for c in candidats:
            if c in sensibles.forts:
                constat.forts.add(c)
            elif c in sensibles.faibles:
                constat.faibles.add(c)
    for m in RE_CHIFFRES.finditer(texte):
        chiffres = chiffres_seuls(m.group(0))
        for c in (chiffres, chiffres.lstrip("0")):
            if c in sensibles.chiffres:
                constat.forts.add(c)
        if len(chiffres) >= 9 and chiffres[-9:] in sensibles.telephones:
            constat.forts.add("téléphone")
    if sensibles.telephones:
        for tel in RE_TEL_SORTIE.findall(texte):
            if chiffres_seuls(tel)[-9:] in sensibles.telephones:
                constat.forts.add("téléphone")
    dates_trouvees = dates_du_texte(texte)
    naissances = (dates_trouvees | dates_du_texte(texte, courtes=True)) & sensibles.naissances
    if naissances:
        constat.naissances |= naissances
    if not sensibles.dates_denses:
        autres = {d for d in dates_trouvees & sensibles.dates if not d.endswith("-01")}
        if len(autres) >= max(5, seuil // 2):
            constat.individuels.append(f"{len(autres)} dates réelles différentes (liste ligne à ligne probable)")
    liste_mots = mots(texte)
    if sensibles.phrases or sensibles.rares:
        index = sensibles.index_phrases()
        for i, m in enumerate(liste_mots):
            candidats = index.get(m)
            if not candidats:
                continue
            for morceaux, n, genre in candidats:
                if liste_mots[i:i + n] == morceaux:
                    (constat.forts if genre == "fort" else constat.rares).add(" ".join(morceaux))
    if sensibles.paires and liste_mots:
        vocabulaire = {x for paire in sensibles.paires for x in paire}
        positions = {}
        for i, m in enumerate(liste_mots):
            if m in vocabulaire:
                positions.setdefault(m, []).append(i)
        for mn, mp in sensibles.paires:
            if mn in positions and mp in positions:
                pn, pp = positions[mn], positions[mp]
                if len(pn) * len(pp) > 100000:
                    pp_ensemble = set(pp)
                    proche = any(j in pp_ensemble for i in pn for j in range(i - 3, i + 4))
                else:
                    proche = any(abs(i - j) <= 3 for i in pn for j in pp)
                if proche:
                    constat.forts.add(f"{mn} {mp}")
    if sensibles.colles:
        texte_compact = compact(texte)
        for motif in sensibles.colles:
            if motif in texte_compact:
                constat.rares.add(motif)
    if sensibles.riches or sensibles.extremes:
        decimales = {norm_nombre(x) for x in RE_DECIMAL.findall(texte)}
        decimales = {d for d in decimales if d is not None and significatif(d)}
        for nom, ensemble in sensibles.riches:
            communs = decimales & ensemble
            if len(communs) >= 20 and len(communs) >= 0.5 * len(decimales):
                constat.individuels.append(f"{len(communs)} valeurs de la colonne réelle « {nom} »")
        constat.extremes |= decimales & sensibles.extremes
    if sensibles.extremes_rares:
        for ligne in texte.splitlines():
            if RE_MINMAX.search(ligne):
                nombres = {norm_nombre(x) for x in RE_NOMBRE.findall(ligne)}
                constat.extremes |= {n for n in nombres if n is not None} & sensibles.extremes_rares
    if RE_RESIDUS.search(texte):
        constat.extremes.add("résidus individuels (Min/Max de summary())")
    if comptes:
        propre = nettoyer_comptes(texte)
        for motif in (RE_N_EGAL, RE_N_POURCENT, RE_MOT_EFFECTIF):
            for m in motif.finditer(propre):
                v = int(m.group(1))
                if 1 <= v < seuil:
                    debut = max(0, m.start() - 40)
                    constat.petits.append(propre[debut:m.end() + 20].replace("\n", " ").strip())
        for m in RE_FRACTION.finditer(propre):
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a < seuil and b >= max(seuil, a) and b < 10**6:
                debut = max(0, m.start() - 40)
                constat.petits.append(propre[debut:m.end() + 20].replace("\n", " ").strip())
        for ligne in propre.splitlines():
            m = RE_LIBELLE_EFFECTIF.search(ligne.strip())
            if m and 1 <= int(m.group(2)) < seuil and not set(jetons_nom(m.group(1))) & NON_COMPTES \
                    and not re.search(r"\d{1,2}\s*$", m.group(1)):
                constat.petits.append(ligne.strip()[:120])
        constat.petits += lignes_comptes(propre, seuil)
        constat.petits += comptes_tableaux_texte(propre, seuil)
        pourcentages_petits(propre, seuil, sensibles.n_individus, constat)


def colonne_comptes(nom, valeurs, tableau_croise):
    jetons = set(jetons_nom(str(nom).replace(".", " ")))
    if jetons & NON_COMPTES:
        return False
    if jetons & JETONS_EFFECTIF:
        return True
    entiers = [v for v in valeurs if v is not None]
    if not entiers or not all(entier_de(v) is not None for v in entiers):
        return False
    return tableau_croise and min(entier_de(v) for v in entiers) >= 0


def jetons_reels(nom, sensibles):
    jetons = set(jetons_nom(str(nom))) - {"n", "id", "nb"}
    return bool(jetons) and (phrase(nom) in sensibles.colonnes or bool(jetons & sensibles.jetons_colonnes))


def analyser_table(t, sensibles, seuil, constat):
    morceaux = [" ".join(map(str, t.noms))]
    colonnes = []
    for j, nom in enumerate(t.noms):
        valeurs = [None if est_manquant(v) else v for v in t.donnees[j].tolist()]
        colonnes.append(valeurs)
        morceaux.append("\n".join(str(v) for v in valeurs if v is not None))
    etiquettes = t.options.get("etiquettes") or {}
    for labels in etiquettes.values():
        morceaux.append("\n".join(str(v) for v in labels.values()))
    for libelle in (t.options.get("labels") or {}).values():
        morceaux.append(str(libelle))
    analyser_texte("\n".join(morceaux), sensibles, seuil, constat, comptes=False)
    for nom in t.noms:
        for regex in (RE_CELLULE_N_EGAL, RE_N_EGAL, RE_N_POURCENT):
            m = regex.search(str(nom))
            if m and 1 <= int(m.group(1)) < seuil:
                constat.petits.append(f"{t.nom_affiche} — en-tête « {nom} »")
                break
    lignes = t.n_lignes
    premiere = colonnes[0] if colonnes else []
    premiere_texte = bool(colonnes) and all(v is None or (isinstance(v, str) and entier_de(v) is None) for v in premiere)
    premiere_annees = bool(colonnes) and (set(jetons_nom(str(t.noms[0]))) & NON_COMPTES or
                                          all(v is None or (entier_de(v) is not None and 1900 <= entier_de(v) <= 2100) for v in premiere))
    tout_entier = bool(colonnes) and all(entier_de(v) is not None for col in colonnes for v in col if v is not None) \
        and any(v is not None for col in colonnes for v in col)
    croise = (premiere_texte or premiere_annees) and len(colonnes) >= 2 and lignes <= 200
    matrice = tout_entier and lignes <= 30 and len(colonnes) <= 30
    for j, (nom, valeurs) in enumerate(zip(t.noms, colonnes)):
        effectif = colonne_comptes(str(nom), valeurs, (croise and j > 0) or matrice)
        for i, v in enumerate(valeurs):
            if v is None or isinstance(v, bool):
                continue
            if isinstance(v, str):
                for regex in (RE_CELLULE_N_POURCENT, RE_CELLULE_N_EGAL, RE_N_EGAL):
                    m = regex.search(v)
                    if m and 1 <= int(m.group(1)) < seuil:
                        constat.petits.append(f"{t.nom_affiche} — ligne {i + 2}, colonne « {nom} » : {v}")
                        break
                else:
                    m = RE_CELLULE_FRACTION.match(v)
                    mot = RE_MOT_EFFECTIF.search(v)
                    e = entier_de(v)
                    if mot and 1 <= int(mot.group(1)) < seuil:
                        constat.petits.append(f"{t.nom_affiche} — ligne {i + 2}, colonne « {nom} » : {v}")
                    elif m and 1 <= int(m.group(1)) < seuil and int(m.group(2)) >= seuil:
                        constat.petits.append(f"{t.nom_affiche} — ligne {i + 2}, colonne « {nom} » : {v}")
                    elif effectif and e is not None and 1 <= e < seuil:
                        constat.petits.append(f"{t.nom_affiche} — ligne {i + 2}, colonne « {nom} » : {v}")
            elif effectif:
                e = entier_de(v)
                if e is not None and 1 <= e < seuil:
                    constat.petits.append(f"{t.nom_affiche} — ligne {i + 2}, colonne « {nom} » : {v}")
    reelles = [j for j, nom in enumerate(t.noms) if jetons_reels(nom, sensibles)]
    for j, valeurs in enumerate(colonnes):
        distinctes = {norm_nombre(v) for v in valeurs if v is not None and not isinstance(v, bool)}
        distinctes = {d for d in distinctes if d is not None and "." in d and significatif(d)}
        if len(distinctes) >= 20:
            for nom, ensemble in sensibles.riches:
                if len(distinctes & ensemble) >= 0.6 * len(distinctes):
                    constat.individuels.append(f"colonne « {t.noms[j]} » : valeurs de la colonne réelle « {nom} »")
                    break
        dates = set()
        for v in valeurs:
            if isinstance(v, (dt.date, dt.datetime, pd.Timestamp)):
                try:
                    dates.add(pd.Timestamp(v).date().isoformat())
                except (ValueError, OverflowError):
                    pass
            elif isinstance(v, str) and len(v) <= 40:
                dates |= dates_du_texte(v)
        if dates & sensibles.naissances:
            constat.naissances |= dates & sensibles.naissances
        if not sensibles.dates_denses and len(dates) >= 5 and len(dates & sensibles.dates) >= 0.6 * len(dates):
            constat.individuels.append(f"colonne « {t.noms[j]} » : dates réelles")
    grand = lignes >= max(20, seuil) and (not sensibles.n_individus or lignes >= 0.2 * sensibles.n_individus)
    statistiques = any(set(jetons_nom(str(nom).replace(".", " "))) & (NON_COMPTES | JETONS_EFFECTIF) for nom in t.noms)
    if 1 <= lignes < max(seuil, 2) and len(reelles) >= 3:
        dates_reelles = [j for j in reelles if phrase(t.noms[j]) in sensibles.colonnes_dates]
        if dates_reelles or not statistiques:
            constat.individuels.append(f"{lignes} ligne(s) avec {len(reelles)} colonnes des vraies données "
                                       f"({', '.join(str(t.noms[k]) for k in reelles[:4])}) : liste d'individus ?")
    if grand and len(colonnes) >= 2:
        if len(reelles) >= 2:
            combos = {tuple(str(colonnes[j][i]) for j in reelles) for i in range(lignes)}
            if len(combos) >= 0.5 * lignes:
                constat.individuels.append(f"{lignes} lignes avec les colonnes des vraies données ({', '.join(str(t.noms[k]) for k in reelles[:4])})")
        for j, valeurs in enumerate(colonnes):
            decimales = [v for v in valeurs if isinstance(v, (float, np.floating)) and not float(v).is_integer()]
            decimales += [v for v in valeurs if isinstance(v, str) and re.fullmatch(r"[+-]?\d+[.,]\d+", v.strip())]
            if len(decimales) >= 0.8 * lignes and len(set(map(str, decimales))) >= 0.8 * lignes:
                constat.individuels.append(f"{lignes} lignes de valeurs toutes différentes (une ligne par individu ?)")
                break


def chaines_json(objet, sortie):
    if isinstance(objet, dict):
        for k, v in objet.items():
            sortie.append(str(k))
            chaines_json(v, sortie)
    elif isinstance(objet, list):
        for v in objet:
            chaines_json(v, sortie)
    elif objet is not None:
        sortie.append(str(objet))


def contenu_scripts(brut):
    morceaux = []
    for attributs, contenu in re.findall(r"(?is)<script\b([^>]*)>(.*?)</script>", brut):
        if re.search(r"src\s*=", attributs) and not contenu.strip():
            continue
        texte = html.unescape(contenu) if "json" in attributs.lower() else contenu
        try:
            chaines = []
            chaines_json(json.loads(texte), chaines)
            morceaux.append("\n".join(chaines))
            continue
        except ValueError:
            pass
        for chaine in re.findall(r"\"((?:[^\"\\\n]|\\.){1,400})\"|'((?:[^'\\\n]|\\.){1,400})'", texte):
            morceaux.append(chaine[0] or chaine[1])
        morceaux.append(" ".join(re.findall(r"-?\d+(?:\.\d+)?", texte))[:2_000_000])
    return "\n".join(morceaux)


def texte_html(brut, pour_comptes=False):
    sans_script = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", brut)
    if pour_comptes:
        sans_script = re.sub(r"(?is)<div\b[^>]*class=\"[^\"]*sourceCode[^\"]*\"[^>]*>.*?</div>", " ", sans_script)
        sans_script = re.sub(r"(?is)<pre\b[^>]*class=\"[^\"]*sourceCode[^\"]*\"[^>]*>.*?</pre>", " ", sans_script)
    lignes = []
    for ligne in re.findall(r"(?is)<tr\b.*?</tr>", sans_script):
        cellules = [html.unescape(re.sub(r"(?s)<[^>]+>", " ", c)).strip() for c in re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", ligne)]
        lignes.append(" | ".join(c if c else "-" for c in cellules))
    texte = html.unescape(re.sub(r"(?s)<[^>]+>", " ", sans_script))
    return texte + "\n" + "\n".join(lignes)


def texte_classeur(donnees):
    import openpyxl

    classeur = openpyxl.load_workbook(io.BytesIO(donnees), read_only=False, data_only=True)
    morceaux = []
    for feuille in classeur.worksheets:
        morceaux.append(str(feuille.title))
        for ligne in feuille.iter_rows(values_only=True):
            cellules = [str(v) for v in ligne if v is not None]
            if cellules:
                morceaux.append(" | ".join(cellules))
        for ligne in feuille.iter_rows():
            for cellule in ligne:
                if cellule.comment is not None:
                    morceaux.append(str(cellule.comment.text))
    for nom in classeur.defined_names:
        try:
            morceaux.append(str(classeur.defined_names[nom].attr_text))
        except Exception:
            pass
    return "\n".join(morceaux)


def texte_bureautique(chemin):
    morceaux = []
    figures = False
    tableaux = False
    with zipfile.ZipFile(chemin) as z:
        for nom in z.namelist():
            minuscule = nom.lower()
            if minuscule.endswith((".xml", ".rels")) and not minuscule.startswith("customxml/"):
                brut = z.read(nom).decode("utf-8", errors="replace")
                figures = figures or "<w:drawing" in brut or "<p:pic" in brut or "draw:image" in brut or "<c:chart" in brut
                tableaux = tableaux or "<w:tbl" in brut or "<a:tbl" in brut or "table:table" in brut
                brut = re.sub(r"</w:tc>|</a:tc>|</table:table-cell>|</c:v>|</c:pt>", " | ", brut)
                brut = re.sub(r"</w:p>|</w:tr>|</a:p>|</a:tr>|</text:p>|</c:ser>|<row\b", "\n", brut)
                morceaux.append(html.unescape(re.sub(r"(?s)<[^>]+>", " ", brut)))
            elif minuscule.endswith((".xlsx", ".xlsm")):
                try:
                    morceaux.append(texte_classeur(z.read(nom)))
                    tableaux = True
                except Exception:
                    morceaux.append(chaines_brutes(z.read(nom)))
            elif minuscule.endswith((".bin", ".csv", ".txt")):
                morceaux.append(chaines_brutes(z.read(nom)))
    return "\n".join(morceaux), figures, tableaux


def chaines_brutes(donnees):
    if donnees[:2] == b"\x1f\x8b":
        try:
            donnees = gzip.decompress(donnees)
        except Exception:
            pass
    ascii_ = [m.decode("latin-1") for m in re.findall(rb"[\x20-\x7e\xa0-\xff]{4,}", donnees)]
    utf16 = []
    for m in re.findall(rb"(?:[\x20-\x7e]\x00){4,}", donnees):
        try:
            utf16.append(m.decode("utf-16-le"))
        except UnicodeDecodeError:
            pass
    utf8 = []
    try:
        utf8 = re.findall(r"[^\x00-\x1f]{4,}", donnees.decode("utf-8", errors="ignore"))
    except Exception:
        pass
    return "\n".join(ascii_ + utf16 + utf8)


def lire_texte(chemin):
    brut = chemin.read_bytes()
    if brut[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return brut.decode("utf-16")
        except UnicodeDecodeError:
            return None
    if b"\x00" in brut[:4096]:
        pairs = brut[1:4096:2]
        if pairs and pairs.count(0) >= 0.8 * len(pairs):
            try:
                return brut.decode("utf-16-le")
            except UnicodeDecodeError:
                return None
        impairs = brut[0:4096:2]
        if impairs and impairs.count(0) >= 0.8 * len(impairs):
            try:
                return brut.decode("utf-16-be")
            except UnicodeDecodeError:
                return None
        return None
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return brut.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def texte_arrow(chemin, extension):
    import pyarrow as pa
    import pyarrow.parquet as pq

    if extension == ".parquet":
        table = pq.ParquetFile(chemin).read()
    else:
        import pyarrow.feather as pf

        table = pf.read_table(chemin)
    morceaux = []
    for nom, colonne in zip(table.column_names, table.columns):
        if pa.types.is_nested(colonne.type) or pa.types.is_dictionary(colonne.type) or pa.types.is_string(colonne.type) \
                or pa.types.is_large_string(colonne.type) or pa.types.is_binary(colonne.type):
            valeurs = colonne.to_pylist()
            morceaux.append("\n".join(json.dumps(v, default=str, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)
                                      for v in valeurs if v is not None))
    return "\n".join(morceaux)


def balayage_brut(chemin, constat, sensibles, seuil, partiel=False):
    with open(chemin, "rb") as f:
        if partiel:
            debut = f.read(TAILLE_PARTIELLE)
            f.seek(max(0, chemin.stat().st_size - TAILLE_PARTIELLE))
            donnees = debut + b"\n" + f.read(TAILLE_PARTIELLE)
        else:
            donnees = f.read()
    analyser_texte(chaines_brutes(donnees), sensibles, seuil, constat, comptes=False)


def verifier_fichier(chemin, rel, sensibles, seuil):
    extension = chemin.suffix.lower()
    constat = Constat()
    taille = chemin.stat().st_size
    if sensibles is None or sensibles.vide:
        constat.revoir.append("impossible de comparer aux vraies données (copie des données de l'exécution introuvable)")
    if taille > TAILLE_MAX:
        balayage_brut(chemin, constat, sensibles, seuil, partiel=True)
        constat.partiel.append("fichier très volumineux : contenu vérifié en partie seulement")
        return resumer(constat, seuil)
    if extension in EXT_IMAGES:
        if extension == ".svg":
            texte = lire_texte(chemin) or ""
            analyser_texte(html.unescape(re.sub(r"(?s)<[^>]+>", " ", texte)), sensibles, seuil, constat)
        else:
            balayage_brut(chemin, constat, sensibles, seuil)
        constat.voir.append("image ou PDF : vérifie qu'aucun point individuel ni effectif < seuil n'y figure")
        return resumer(constat, seuil)
    tables = []
    lisible = False
    if extension in EXT_TABLEAUX:
        try:
            tables = [t for t in lire_fichier(chemin, rel) if not t.options.get("vide")]
            lisible = True
        except Exception:
            tables = []
    for t in tables:
        analyser_table(t, sensibles, seuil, constat)
    if extension in (".rds", ".rdata", ".rda") and not lisible:
        balayage_brut(chemin, constat, sensibles, seuil)
        constat.revoir.append("objet R (modèle, liste…) pouvant contenir des données individuelles")
        return resumer(constat, seuil)
    if extension in EXT_OBJETS:
        balayage_brut(chemin, constat, sensibles, seuil)
        if extension == ".zip":
            try:
                with zipfile.ZipFile(chemin) as z:
                    for nom in z.namelist()[:200]:
                        info = z.getinfo(nom)
                        if info.file_size <= TAILLE_MAX:
                            analyser_texte(chaines_brutes(z.read(nom)), sensibles, seuil, constat, comptes=False)
            except Exception:
                pass
        constat.revoir.append("objet binaire ou archive (modèle, données sérialisées) pouvant contenir des données individuelles")
        return resumer(constat, seuil)
    if extension in (".parquet", ".feather", ".arrow"):
        try:
            analyser_texte(texte_arrow(chemin, extension), sensibles, seuil, constat, comptes=False)
        except Exception:
            balayage_brut(chemin, constat, sensibles, seuil)
            if not lisible:
                constat.partiel.append("fichier Arrow/Parquet illisible : vérifié en partie seulement")
        return resumer(constat, seuil)
    if extension in EXT_BUREAUTIQUE:
        try:
            texte, figures, tableaux_ = texte_bureautique(chemin)
        except Exception:
            balayage_brut(chemin, constat, sensibles, seuil)
            constat.partiel.append("document illisible automatiquement : à regarder toi-même")
            return resumer(constat, seuil)
        analyser_texte(texte, sensibles, seuil, constat, comptes=extension not in (".xlsx", ".xlsm") or not lisible)
        if not lisible and extension in (".xlsx", ".xlsm"):
            constat.partiel.append("tableur lu en partie seulement (structure inhabituelle) : à regarder toi-même")
        if extension not in (".xlsx", ".xlsm"):
            if figures:
                constat.voir.append("contient des figures ou des graphiques : à regarder toi-même")
            if tableaux_:
                constat.voir.append("contient des tableaux : vérifie les effectifs toi-même")
        return resumer(constat, seuil)
    if extension in (".sav", ".dta", ".xls", ".rds", ".rdata", ".rda"):
        balayage_brut(chemin, constat, sensibles, seuil)
        if not lisible:
            constat.partiel.append("fichier illisible automatiquement : à regarder toi-même")
        return resumer(constat, seuil)
    texte = lire_texte(chemin)
    if texte is None:
        balayage_brut(chemin, constat, sensibles, seuil)
        constat.voir.append("format non reconnu : à regarder toi-même")
        return resumer(constat, seuil)
    if extension in (".html", ".htm", ".xhtml"):
        scripts = contenu_scripts(texte)
        analyser_texte(scripts, sensibles, seuil, constat, comptes=False)
        if RE_WIDGET.search(texte):
            constat.voir.append("figure ou tableau interactif (les données de chaque point sont dans la page) : à regarder toi-même")
        elif RE_FIGURE.search(texte):
            constat.voir.append("contient des figures : à regarder toi-même")
        analyser_texte(texte_html(texte), sensibles, seuil, constat, comptes=False)
        analyser_texte(texte_html(texte, pour_comptes=True), sensibles, seuil, Constat_comptes(constat), comptes=True)
        return resumer(constat, seuil)
    if extension in (".json", ".jsonl", ".ndjson", ".geojson"):
        try:
            if extension == ".json" or extension == ".geojson":
                chaines = []
                chaines_json(json.loads(texte), chaines)
                texte = "\n".join(chaines)
            else:
                chaines = []
                for ligne in texte.splitlines():
                    if ligne.strip():
                        chaines_json(json.loads(ligne), chaines)
                texte = "\n".join(chaines)
        except ValueError:
            pass
    analyser_texte(texte, sensibles, seuil, constat, comptes=not (lisible and tables))
    return resumer(constat, seuil)


class Constat_comptes:
    def __init__(self, constat):
        self._constat = constat
        self.forts, self.faibles, self.rares, self.naissances = set(), set(), set(), set()
        self.individuels, self.extremes = [], set()
        self.petits = constat.petits


def resumer(constat, seuil):
    statut = OK
    raisons = []
    details = []

    def monter(nouveau, raison):
        nonlocal statut
        if ORDRE[nouveau] > ORDRE[statut]:
            statut = nouveau
        if raison not in raisons:
            raisons.append(raison)

    if constat.forts:
        monter(BLOQUE, f"{len(constat.forts)} identifiant(s), nom(s) ou coordonnée(s) des vraies données")
        details.append("valeurs identifiantes retrouvées : " + ", ".join(sorted(constat.forts)[:20]))
    if constat.naissances:
        monter(BLOQUE, f"{len(constat.naissances)} date(s) de naissance réelle(s)")
        details.append("dates de naissance retrouvées : " + ", ".join(sorted(constat.naissances)[:20]))
    if constat.faibles:
        monter(REVOIR, f"{len(constat.faibles)} nom(s) ou valeur(s) de colonnes identifiantes possibles")
        details.append("valeurs à vérifier : " + ", ".join(sorted(constat.faibles)[:20]))
    if constat.rares:
        monter(REVOIR, f"{len(constat.rares)} modalité(s) rare(s) ou texte(s) libre(s) des vraies données cité(s)")
        details.append("modalités rares ou textes cités : " + ", ".join(sorted(constat.rares)[:20]))
    petits = list(dict.fromkeys(constat.petits))
    if petits:
        monter(REVOIR, f"{len(petits)} effectif(s) inférieur(s) à {seuil}")
        details += petits[:50]
    if constat.individuels:
        monter(REVOIR, "données individuelles probables")
        details += list(dict.fromkeys(constat.individuels))[:20]
    if constat.extremes:
        monter(REVOIR, f"{len(constat.extremes)} valeur(s) minimale(s) ou maximale(s) réelle(s) (valeurs individuelles)")
        details.append("extrêmes retrouvés : " + ", ".join(sorted(constat.extremes)[:20]))
    for v in dict.fromkeys(constat.revoir):
        monter(REVOIR, v)
    for v in dict.fromkeys(constat.partiel):
        monter(REVOIR, v)
    for v in dict.fromkeys(constat.voir):
        monter(VOIR, v)
    return statut, raisons, details, constat


def capitaliser(texte):
    return texte[:1].upper() + texte[1:] if texte else texte


def conseils(r, seuil, dossier=None):
    c = r.get("constat")
    chemin = f"\"{Path(dossier) / r['fichier']}\"" if dossier else r["fichier"]
    if r["statut"] == BLOQUE:
        if Path(r["fichier"]).suffix.lower() in EXT_DONNEES_INDIVIDUELLES:
            return ("Fichier de données individuelles (sans doute un fichier intermédiaire) : il reste dans le coffre, c'est "
                    "normal. S'il s'agit d'un résultat, retire du script les identifiants, noms et dates de naissance.")
        return "Retire du script les identifiants, noms et dates de naissance (ce fichier ne peut pas être forcé)."
    if r["statut"] == VOIR:
        return f"Ouvre-le (open {chemin}) et vérifie-le toi-même, puis : sosie verifier --forcer {r['fichier']}"
    if r["statut"] != REVOIR or c is None:
        return ""
    morceaux = []
    journal = Path(r["fichier"]).name == "journal.txt"
    if journal and c.rares and not (c.petits or c.individuels or c.extremes or c.faibles):
        return (f"Lis-le (open -e {chemin}) : s'il ne contient que le message d'erreur, sans donnée, force-le : "
                "sosie verifier --forcer journal.txt")
    if c.petits:
        morceaux.append(f"masque les effectifs < {seuil} dans le script (ex. « <{seuil} ») ou regroupe des modalités")
    if c.individuels or c.extremes:
        morceaux.append("n'exporte que des résultats agrégés (pas de lignes individuelles, pas de min/max ni de résidus) ; "
                        "si chaque ligne n'est pas un individu (seuils d'une courbe ROC, itérations…), vérifie puis force")
    if c.rares:
        morceaux.append("regroupe les modalités rares (« Autre ») dans le script")
    if c.faibles:
        morceaux.append("vérifie que les valeurs signalées ne sont pas des noms ou des identifiants")
    if c.partiel or c.revoir:
        morceaux.append(f"ouvre-le (open {chemin}) et vérifie-le toi-même")
    return capitaliser(" ; ".join(morceaux)) + "." if morceaux else ""


def sorties_execution(dossier):
    manifeste = json.loads((dossier / MANIFESTE_EXECUTION).read_text(encoding="utf-8"))
    if not isinstance(manifeste, dict):
        manifeste = {}
    avant = manifeste.get("fichiers_avant", {}) or {}
    sorties, speciaux = [], []
    liens_dossiers = set()
    for chemin in sorted(dossier.rglob("*")):
        rel = chemin.relative_to(dossier).as_posix()
        parties = Path(rel).parts
        if any("/".join(parties[:k]) in liens_dossiers for k in range(1, len(parties))):
            continue
        if chemin.is_symlink() and chemin.is_dir():
            liens_dossiers.add(rel)
        if rel.startswith(DOSSIER_DONNEES + "/") or rel == DOSSIER_DONNEES or parties[0] in ("tmp", "quarantaine"):
            continue
        if rel in (MANIFESTE_EXECUTION, "VERIFICATION_DETAILLEE.md"):
            continue
        if any(p in (".venv", "venv", "renv", "node_modules", ".quarto", "_freeze", "site_libs", ".jupyter_cache") or p.endswith("_cache") for p in parties):
            continue
        if any(p.endswith("_files") for p in parties[:-1]) and any(p in ("libs", "lib") for p in parties):
            continue
        if chemin.is_symlink():
            speciaux.append((chemin, rel, "lien"))
            continue
        if not chemin.is_file():
            continue
        if fichier_ignore(chemin.name) and not chemin.name.startswith("."):
            continue
        if chemin.name in (".DS_Store",) or chemin.name.startswith("._"):
            continue
        stat = chemin.stat()
        if rel in avant and avant[rel] == [stat.st_size, stat.st_mtime_ns]:
            continue
        if any(p.startswith(".") for p in parties):
            speciaux.append((chemin, rel, "cache"))
            continue
        if chemin.suffix.lower() in EXT_BIBLIOTHEQUES and any(p.endswith("_files") for p in parties[:-1]):
            continue
        sorties.append((chemin, rel))
    return manifeste, sorties, speciaux


def nom_masque(rel, sensibles):
    constat = Constat()
    analyser_texte(re.sub(r"[_/\\.]", " ", rel), sensibles, 10**9, constat, comptes=False)
    bloquant = bool(constat.forts or constat.naissances)
    return bloquant, bloquant or bool(constat.faibles or constat.rares)


def resoudre_forcer(demandes, resultats):
    choisis = set()
    inconnus = []
    for demande in demandes:
        cle = cle_nom(demande.strip().removeprefix("./"))
        exacts = [r for r in resultats if cle_nom(r["fichier"]) == cle]
        if not exacts:
            exacts = [r for r in resultats if cle_nom(Path(r["fichier"]).name) == cle]
        if len(exacts) > 1:
            raise ErreurSosie(f"« {demande} » désigne plusieurs fichiers : précise le chemin ("
                              + ", ".join(r["affiche"] for r in exacts[:5]) + ").")
        if not exacts:
            inconnus.append(demande)
            continue
        choisis.add(exacts[0]["fichier"])
    return choisis, inconnus


def verifier(dossier_execution, racine_projet, seuil, forcer=(), donnees_secours=None):
    dossier_execution = Path(dossier_execution)
    manifeste, sorties, speciaux = sorties_execution(dossier_execution)
    copie_donnees = dossier_execution / DOSSIER_DONNEES
    sensibles = construire_sensibles(copie_donnees, seuil) if copie_donnees.exists() else Sensibles()
    if sensibles.vide and donnees_secours is not None and Path(donnees_secours).exists():
        sensibles = construire_sensibles(Path(donnees_secours), seuil)
    resultats = []
    for k, (chemin, rel) in enumerate(sorties, 1):
        try:
            statut, raisons, details, constat = verifier_fichier(chemin, rel, sensibles, seuil)
        except Exception as e:
            constat = Constat()
            try:
                balayage_brut(chemin, constat, sensibles, seuil)
            except Exception:
                pass
            constat.partiel.append(f"vérification impossible ({type(e).__name__}) : à regarder toi-même")
            statut, raisons, details, constat = resumer(constat, seuil)
        bloquant, masque = nom_masque(rel, sensibles)
        if bloquant:
            statut = BLOQUE
            raisons = raisons + ["le nom du fichier contient une valeur identifiante"]
        resultats.append({"fichier": rel, "statut": statut, "raisons": raisons, "details": details, "force": False,
                          "constat": constat, "nom_masque": masque,
                          "affiche": f"fichier n°{k} (nom masqué)" if masque else rel})
    for chemin, rel, genre in speciaux:
        bloquant, masque = nom_masque(rel, sensibles)
        if genre == "lien":
            statut, raisons = BLOQUE, ["lien symbolique : jamais copié"]
        else:
            statut, raisons = REVOIR, ["fichier caché (cache, historique…) : non vérifié, à regarder toi-même"]
        resultats.append({"fichier": rel, "statut": statut, "raisons": raisons, "details": [], "force": False,
                          "constat": Constat(), "nom_masque": masque,
                          "affiche": f"fichier n°{len(resultats) + 1} (nom masqué)" if masque else rel})
    choisis, inconnus = resoudre_forcer(forcer, resultats)
    if inconnus:
        noms = ", ".join(r["affiche"] for r in resultats)[:600]
        raise ErreurSosie(f"Fichier(s) introuvable(s) dans cette exécution : {', '.join(inconnus)}. Fichiers produits : {noms or 'aucun'}")
    refuses = [r["affiche"] for r in resultats if r["fichier"] in choisis and r["statut"] == BLOQUE]
    if refuses:
        raise ErreurSosie(
            "Impossible de forcer un fichier ⛔ (identifiants, noms, dates de naissance réels, ou lien symbolique) : "
            + ", ".join(refuses) + ". Corrige le script, relance sosie executer, puis sosie verifier."
        )
    anciens_forces = set(manifeste.get("forces", []) or [])
    for r in resultats:
        r["force"] = r["statut"] != BLOQUE and (r["fichier"] in choisis or r["fichier"] in anciens_forces)
    destination = Path(racine_projet) / DOSSIER_VERIFIES / dossier_execution.name
    if destination.is_symlink() or (destination.parent.exists() and destination.parent.is_symlink()):
        raise ErreurSosie(f"{destination} est un lien symbolique : supprime-le, puis relance sosie verifier.")
    copies = []
    for r in resultats:
        if r["statut"] == OK or r["force"]:
            copies.append(r["fichier"])
    destination.mkdir(parents=True, exist_ok=True)
    for ancien in manifeste.get("copies", []) or []:
        if ancien not in copies:
            cible = (destination / ancien)
            try:
                if cible.resolve().is_relative_to(destination.resolve()) and cible.is_file():
                    cible.unlink()
            except (OSError, ValueError):
                pass
    for rel in copies:
        cible = destination / rel
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dossier_execution / rel, cible)
    commande = manifeste.get("scripts") or ([manifeste.get("script")] if manifeste.get("script") else [" ".join(manifeste.get("commande", []) or [])])
    entete = [
        f"# Vérification de l'exécution {dossier_execution.name}",
        "",
        f"- Script(s) : {', '.join('`' + c + '`' for c in commande if c)}",
        f"- Vérifiée le {dt.datetime.now().strftime('%d/%m/%Y à %H:%M')} — seuil des petits effectifs : {seuil} individus",
        f"- Code de retour : {manifeste.get('code_retour')}" + (" (le script s'est arrêté sur une erreur)" if manifeste.get("code_retour") not in (0, None) else ""),
        "",
        "| Fichier | Statut | Raisons |",
        "|---|---|---|",
    ]
    publiques = list(entete)
    detaillees = list(entete)
    for r in resultats:
        statut = r["statut"] + (" (forcé après vérification)" if r["force"] and r["statut"] != OK else "")
        raisons = "; ".join(r["raisons"]) or LIBELLES[OK]
        copie = " — copié" if r["fichier"] in copies else " — resté dans le coffre"
        publiques.append(f"| `{r['affiche']}` | {statut} | {raisons}{copie} |")
        detaillees.append(f"| `{r['fichier']}` | {statut} | {raisons}{copie} |")
    publiques += ["", "Les fichiers restés dans le coffre ne sont pas visibles ici. Pour un fichier ⚠️ ou ⛔, adapte le script "
                  "(effectifs masqués, résultats agrégés) puis l'utilisateur relance `sosie executer`."]
    detaillees += ["", "## Détails (reste dans le coffre)", ""]
    for r in resultats:
        if r["details"]:
            detaillees.append(f"### `{r['fichier']}`")
            detaillees += [f"- {d}" for d in r["details"]]
            detaillees.append("")
    (dossier_execution / "VERIFICATION_DETAILLEE.md").write_text("\n".join(detaillees) + "\n", encoding="utf-8")
    (destination / "VERIFICATION.md").write_text("\n".join(publiques) + "\n", encoding="utf-8")
    manifeste["forces"] = sorted({r["fichier"] for r in resultats if r["force"]})
    manifeste["copies"] = copies
    try:
        (dossier_execution / MANIFESTE_EXECUTION).write_text(json.dumps(manifeste, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return resultats, destination, copies
