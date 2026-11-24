import datetime as dt
import math
import re
import unicodedata
from collections import Counter

import numpy as np
import pandas as pd

from .formats import JETONS_MANQUANTS, RE_TITRE_NOM, est_manquant, ressemble_nom_personne

ID_FORTS = {
    "id", "ident", "identifiant", "identifier", "idt", "ipp", "nip", "nda", "subjid", "usubjid", "uuid", "guid",
    "psa", "enq", "dossier", "sejour", "rss", "rsa", "matricule", "pseudo", "pseudonyme", "ano", "anonymat", "anonyme",
}
ID_FAIBLES = {
    "num", "numero", "no", "nr", "n", "code", "cle", "key", "ref", "reference", "patient", "patients", "sujet",
    "subject", "participant", "individu", "inclusion", "personne",
}
ID_CLES = {"pat", "mrn", "initiales", "initiale", "subj", "malade", "identite"}
NON_ID = {
    "age", "ages", "date", "dt", "poids", "taille", "imc", "bmi", "duree", "delai", "score", "dose", "nombre", "nb",
    "nbre", "taux", "valeur", "mesure", "annee", "an", "mois", "jour", "heure", "temps", "volume", "debit", "pression",
    "frequence", "glycemie", "hba1c", "cholesterol", "ldl", "hdl", "tg", "creatinine", "dfg", "pas", "pad", "fc",
    "tension", "perimetre", "tour", "masse", "pourcentage", "pct", "ratio", "concentration", "resultat", "qte",
    "quantite", "montant", "prix", "cout", "somme", "total", "rang", "ordre",
}
MOTS_VIDES = {"de", "du", "des", "d", "la", "le", "l", "les", "of", "the", "a", "au", "aux", "en", "et", "par", "pour"}
NOMENCLATURE = {
    "cim", "cim10", "icd", "icd10", "atc", "cip", "cip13", "cip7", "ucd", "ccam", "ngap", "lpp", "ghm", "ghs",
    "diag", "diagnostic", "diagnostics", "dp", "dr", "das", "acte", "actes", "molecule", "molecules", "medicament",
    "medicaments", "specialite", "specialites", "produit", "dci", "libelle", "lib", "traitement", "traitements",
    "pathologie", "pathologies", "analyte", "analyse", "examen", "unite", "loinc", "finess", "service", "profession",
    "categorie", "classe", "type", "motif", "famille", "germe", "bacterie", "antibiotique", "marque", "pays",
    "nationalite", "departement", "dpt", "region", "etablissement", "hopital", "centre", "prs", "nat", "spe", "pse",
    "cod", "groupe", "bras", "visite", "statut", "etat", "niveau", "stade", "grade", "mode", "voie", "forme",
}
PROFESSIONNELS = {
    "medecin", "praticien", "prescripteur", "infirmier", "infirmiere", "investigateur", "referent", "chirurgien",
    "operateur", "operatrice", "anesthesiste", "interne", "redacteur", "redactrice", "auteur", "signataire", "soignant",
    "correspondant", "demandeur", "preleveur", "valideur", "biologiste", "pharmacien", "titulaire", "tuteur", "aidant",
    "proche", "contact", "docteur", "generaliste", "saisi", "utilisateur", "user", "login", "secretaire",
    "dieteticien", "dieteticienne", "psychologue", "kine", "kinesitherapeute", "sagefemme", "specialiste",
}
NOM = {"nom", "noms", "name", "lastname", "surname", "patronyme", "nomnaissance", "nomusage"} | PROFESSIONNELS
FAUX_SPECIALISTES = {"catalogue", "dialogue", "analogue", "prologue", "epilogue", "homologue", "monologue"}
EXCLUSIONS_NOM = {
    "medicament", "molecule", "produit", "specialite", "centre", "etablissement", "service", "hopital", "etude",
    "variable", "fichier", "analyse", "examen", "test", "labo", "laboratoire", "commune", "ville", "pays", "maladie",
    "pathologie", "germe", "bacterie", "feuille", "site", "unite", "dci", "classe", "famille", "marque", "programme",
    "protocole", "groupe", "bras", "visite", "questionnaire", "item", "echelle", "score", "type", "nombre", "nb",
}
PRENOM = {"prenom", "prenoms", "firstname", "givenname", "forename"}
NOMS_PATIENT = {"nom", "noms", "name", "lastname", "surname", "patronyme", "nomnaissance", "nomusage", "prenom",
                "prenoms", "firstname", "givenname", "forename", "identite", "patient", "patiente", "malade"}
EMAIL = {"email", "mail", "courriel", "emails", "mel", "e_mail"}
TEL = {"tel", "telephone", "phone", "portable", "mobile", "fixe", "gsm", "fax"}
ADRESSE = {"adresse", "adresses", "address", "rue", "voie_adresse", "addr", "domicile", "adr"}
CP = {"cp", "codepostal", "postal", "zip", "zipcode", "codepost"}
VILLE = {"ville", "commune", "city", "localite", "town"}
NIR = {"nir", "nss", "secu", "insee", "ins", "numsecu", "securite"}
NAISSANCE = {"naissance", "ddn", "dob", "birth", "birthdate", "birthday", "naiss", "nais", "datenaissance", "datenais"}
INDICE_DATE = {"date", "dt", "dte", "dat", "jour", "dtd", "dtf", "naissance", "ddn", "dob", "debut", "fin"}
ATTRIBUTS_PERSONNE = {"sexe", "sex", "genre", "gender", "naissance", "ddn", "dob", "birth", "birthdate", "datenaissance"}
PREFERENCES_ANCRE = [
    {"inclusion", "inclu", "randomisation", "randomization", "rando", "baseline", "j0", "index", "consentement"},
    {"entree", "debut", "admission", "start"},
    {"diagnostic", "diag", "decouverte"},
]
CLES_PATIENT = {"patient", "patiente", "pat", "sujet", "subject", "subj", "subjid", "usubjid", "individu",
                "participant", "personne", "malade", "mrn", "ipp", "nip", "ben", "psa", "beneficiaire", "benef",
                "identite", "initiales", "initiale"}
CLES_PATIENT_NUMERIQUES = {"patient", "pat", "sujet", "subject", "subj", "individu", "participant", "malade", "mrn",
                           "ipp", "nip"}
EXCLUS_INDIVIDU = {
    "centre", "center", "etablissement", "eta", "site", "service", "hopital", "finess", "uf", "unite", "lot", "batch",
    "medecin", "praticien", "prescripteur", "investigateur", "visite", "region", "departement", "dpt", "ville",
    "commune", "pays", "labo", "laboratoire", "examen", "analyse", "prelevement", "echantillon", "tube", "plaque",
    "puits", "appareil", "machine", "capteur", "lit", "chambre", "equipe", "groupe", "bras", "strate", "cluster",
    "famille", "medicament", "produit", "visit", "timepoint", "temps", "periode", "phase", "cycle", "semaine",
    "mois", "jour", "annee", "pays", "country", "nationalite",
}
SECONDAIRES = {"sejour", "rss", "rsa", "nda", "venue", "hospitalisation", "hospit", "sej", "passage", "consultation",
               "prescription", "ordonnance", "dct", "acte", "episode", "rum", "admission", "visit", "rdv", "examen"}
TEXTE_LIBRE = {
    "commentaire", "commentaires", "comment", "comments", "remarque", "remarques", "observation", "observations",
    "note", "notes", "texte", "text", "libre", "compte", "rendu", "cr", "conclusion", "conclusions", "description",
    "histoire", "anamnese", "synthese", "courrier", "precision", "precisions", "preciser", "verbatim", "resume",
    "detail", "details", "autre", "autres", "evolution", "plainte",
}

RE_NOMBRE = re.compile(r"^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?$")
RE_MILLIERS = re.compile(r"^[+-]?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?$")
RE_ZERO_TETE = re.compile(r"^[+-]?0\d")
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
RE_TEL = re.compile(r"^(?:\+33\s?|0033\s?|0)[1-9](?:[\s.-]?\d{2}){4}$")
RE_NIR = re.compile(r"^[12]\s?\d{2}\s?\d{2}\s?(?:\d{2}|2A|2B)\s?\d{3}\s?\d{3}(?:\s?\d{2})?$")
RE_HEURE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$")
RE_CENSURE = re.compile(r"^[<>≤≥]=?\s*[+-]?\d+(?:[.,]\d+)?$")
RE_INITIALES = re.compile(r"^[A-Z]\.\s?-?[A-Z]\.(?:\s?-?[A-Z]\.)?$")
RE_FORME_CLE = re.compile(r"^(?:[A-Za-z]{1,4}[-_ ]?\d{1,7}|[A-Z]\.\s?[A-Z]\.(?:\s?[A-Z]\.)?)$")

FORMATS_DATES = [
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%y",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M%z", "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z", "%d%b%Y", "%d%b%Y:%H:%M:%S", "%Y%m%d", "%Y-%m", "%m/%Y",
]

GENRES_MAPPES = {"identifiant", "nir", "code", "telephone"}
GENRES_PERSONNES = {"nom", "prenom", "email", "adresse"}
GENRES_DATES = {"date", "date_naissance"}

MAX_CATEGORIES = 50
MAX_DISCRET = 15
PART_SENTINELLE = 0.03
SENTINELLE = "MODALITE_RARE"
SENTINELLE_VALEUR = "VALEUR_RARE"
SENTINELLE_UNIQUE = "MODALITE_UNIQUE"
EPOQUE = dt.datetime(1970, 1, 1)
SEC_MIN = (dt.datetime(1850, 1, 1) - EPOQUE).total_seconds()
SEC_MAX = (dt.datetime(2150, 1, 1) - EPOQUE).total_seconds()
DATES_SENTINELLES = {"1900-01-01", "1899-12-30", "1899-12-31", "1800-01-01", "1970-01-01", "2099-12-31", "2999-12-31",
                     "9999-12-31", "9999-01-01", "3000-01-01", "2100-01-01", "1901-01-01"}
CODES_NUMERIQUES = {9, 99, 999, 9999, 99999, 999999, 88, 888, 8888, 88888, 77, 777, 7777, 66, 666, 6666,
                    -1, -9, -99, -999, -9999, -8, -88, -888, -7, -77, -777}
SEP_CLE = "\x1f"

GENERIQUES = {
    "nr", "nd", "nc", "na", "nk", "ns", "nsp", "inconnu", "inconnue", "inc", "?", "-", "--", "manquant", "manquante",
    "non renseigne", "non renseignee", "non fait", "nf", "non applicable", "sans objet", "so", "non evalue",
    "non evaluable", "ne", "x", "nan", "null", "vide", "missing", "unknown", "nr.", "n.r.", "n.d.",
}


def sans_accents(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c))


def jetons_nom(nom):
    s = sans_accents(nom)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    jetons = [p for p in re.split(r"[^A-Za-z0-9]+", s.lower()) if p]
    utiles = [p for p in jetons if p not in MOTS_VIDES]
    return utiles or jetons


def a_indice(jetons, ensemble):
    return any(j in ensemble for j in jetons)


def colle(jetons):
    return "".join(jetons)


def est_id_nomme(jetons):
    if a_indice(jetons, NON_ID) and not a_indice(jetons, CLES_PATIENT):
        return False
    if a_indice(jetons, ID_FORTS):
        return True
    c = colle(jetons)
    if re.match(r"^(id|num|no|n|code|ident|ref)(patient|pat|sujet|dossier|inclusion|individu|participant|personne)s?$", c):
        return True
    if re.match(r"^(patient|sujet|dossier|individu|participant)(id|num|no|n|code|ref)$", c):
        return True
    if a_indice(jetons, NOMENCLATURE) or a_indice(jetons, NON_ID):
        return False
    if a_indice(jetons, ID_CLES) and len(jetons) <= 2:
        return True
    if len(jetons) >= 2 and jetons[-1] in {"num", "cle", "key", "ident"}:
        return True
    return a_indice(jetons, ID_FAIBLES) and len(jetons) <= 2


def fin_specialiste(jeton):
    return jeton not in FAUX_SPECIALISTES and len(jeton) >= 7 and (jeton.endswith("logue") or jeton.endswith("iatre"))


def est_professionnel(jetons):
    return a_indice(jetons, PROFESSIONNELS) or any(fin_specialiste(j) for j in jetons)


def est_nom_personne(jetons):
    if a_indice(jetons, INDICE_DATE) or a_indice(jetons, ID_FORTS) or a_indice(jetons, EXCLUSIONS_NOM):
        return False
    return a_indice(jetons, NOM) or any(fin_specialiste(j) for j in jetons)


def nom_de_cle(jetons):
    return bool(jetons) and all(j in CLES_PATIENT | ID_FORTS | ID_FAIBLES | ID_CLES for j in jetons)


def nom_patient(jetons):
    return a_indice(jetons, CLES_PATIENT) and not est_professionnel(jetons) and not a_indice(jetons, EXCLUS_INDIVIDU)


def est_naissance(jetons):
    return a_indice(jetons, NAISSANCE) or "naiss" in colle(jetons) or "ddn" in jetons


def est_code_postal(jetons):
    return a_indice(jetons, CP) or "codepostal" in colle(jetons)


def est_generique(v):
    return sans_accents(str(v)).strip().casefold() in GENERIQUES


def est_censure(v):
    return bool(RE_CENSURE.match(str(v).strip()))


def ressemble_identifiant(v):
    s = str(v).strip()
    chiffres = sum(c.isdigit() for c in s)
    lettres = sum(c.isalpha() for c in s)
    if chiffres >= 5 and lettres == 0 and len(s) - chiffres <= 4:
        return True
    return len(s) >= 5 and chiffres >= 3 and lettres >= 1 and " " not in s


def noms_par_valeurs(valeurs):
    distinctes = echantillon(sorted({str(v) for v in valeurs}), 300)
    if len(distinctes) < 2:
        return False
    oui = sum(1 for v in distinctes if ressemble_nom_personne(v) or RE_TITRE_NOM.search(v))
    return oui >= 0.5 * len(distinctes)


def cle_valeur(v):
    if est_manquant(v):
        return None
    if isinstance(v, (bool, np.bool_)):
        return str(bool(v))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return str(int(f)) if f.is_integer() else repr(f)
    if isinstance(v, (pd.Timestamp, dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()
    s = str(v).strip()
    return s if s else None


def texte_de(v, garder_espaces=False):
    if isinstance(v, (bool, np.bool_)):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    if isinstance(v, (pd.Timestamp, dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    return str(v) if garder_espaces else str(v).strip()


def vers_float(v):
    s = str(v).strip().replace(" ", "").replace(" ", "")
    if RE_MILLIERS.match(str(v).strip()):
        s = re.sub(r"[   ]", "", str(v).strip())
    return float(s.replace(",", "."))


def est_nombre_texte(v):
    return bool(RE_NOMBRE.match(v) or RE_MILLIERS.match(v))


def vers_secondes(serie):
    s = pd.to_datetime(pd.Series(serie), errors="coerce")
    if getattr(s.dt, "tz", None) is not None:
        s = s.dt.tz_convert("UTC").dt.tz_localize(None)
    resultat = (s - pd.Timestamp("1970-01-01")) / pd.Timedelta(seconds=1)
    return resultat.to_numpy(dtype=float, na_value=np.nan)


def arrondi_significatif(x, chiffres=2):
    if x == 0 or not math.isfinite(x):
        return 0.0
    return round(x, -int(math.floor(math.log10(abs(x)))) + (chiffres - 1))


def quantiles_ponderes(x, w, grille):
    ordre = np.argsort(x, kind="mergesort")
    xs = x[ordre]
    ws = w[ordre]
    cumul = np.cumsum(ws)
    total = cumul[-1]
    positions = (cumul - 0.5 * ws) / total
    return np.interp(grille, positions, xs)


def annee_de(secondes):
    return (EPOQUE + dt.timedelta(seconds=float(secondes))).year


def secondes_de(annee):
    return (dt.datetime(int(annee), 1, 1) - EPOQUE).total_seconds()


def quantiles_surs(x, seuil, n_eff, poids=None, dates=False):
    x = np.asarray(x, dtype=float)
    w = np.ones(len(x)) if poids is None else np.asarray(poids, dtype=float)
    m = np.isfinite(x)
    x, w = x[m], w[m]
    if len(x) == 0:
        return {"vide": True}
    positif = bool(np.min(x) >= 0)
    if n_eff < seuil:
        mediane = float(quantiles_ponderes(x, w, [0.5])[0])
        if dates:
            decennie = max(1850, min(2140, annee_de(mediane) // 10 * 10))
            debut, fin = secondes_de(decennie), secondes_de(decennie + 10)
            return {"centre": (debut + fin) / 2, "dispersion": (fin - debut) / 2, "positif": False}
        centre = arrondi_significatif(mediane, 1)
        dispersion = abs(centre) * 0.2 or 1.0
        return {"centre": centre, "dispersion": dispersion, "positif": positif}
    if n_eff < max(4 * seuil, 40):
        moyenne = float(np.average(x, weights=w))
        ecart = float(np.sqrt(np.average((x - moyenne) ** 2, weights=w)))
        if dates:
            m_arr = round(moyenne / 86400) * 86400.0
            s_arr = max(arrondi_significatif(ecart), 86400.0)
            return {"moyenne": m_arr, "ecart_type": s_arr, "positif": False}
        m_arr = arrondi_significatif(moyenne)
        s_arr = arrondi_significatif(ecart) or abs(m_arr) * 0.1 or 1.0
        return {"moyenne": m_arr, "ecart_type": s_arr, "positif": positif}
    bas = max(0.01, seuil / n_eff)
    haut = 1 - bas
    grille = sorted({bas, haut, *[i / 20 for i in range(1, 20) if bas < i / 20 < haut]})
    valeurs = quantiles_ponderes(x, w, grille)
    return {"quantiles": [[float(q), float(v)] for q, v in zip(grille, valeurs)]}


def decimales_flottants(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)][:5000]
    if len(x) == 0:
        return 0
    echelle = max(1.0, float(np.max(np.abs(x))))
    for d in range(0, 7):
        if np.all(np.abs(np.round(x, d) - x) <= 1e-9 * echelle):
            return d
    return None


def entites_completes(entites, n):
    if entites is None:
        return np.arange(n)
    e = np.asarray(entites).copy()
    seuls = e < 0
    if seuls.any():
        base = (int(e.max()) + 1) if len(e) and e.max() >= 0 else 0
        e[seuls] = base + np.arange(int(seuls.sum()))
    return e


def poids_entites(entites):
    e = np.asarray(entites)
    if len(e) == 0:
        return np.array([], dtype=float)
    _, inverse, comptes = np.unique(e, return_inverse=True, return_counts=True)
    return 1.0 / comptes[inverse]


def frequences_sures(valeurs, entites, seuil):
    comptes = Counter(valeurs)
    total = sum(comptes.values())
    if not total:
        return {"gardees": [], "rares": [], "generiques": [], "autres": [], "singletons": 0, "total": 0,
                "part_autres": 0.0, "entites_autres": 0}
    e = entites_completes(entites, len(valeurs))
    tableau = pd.DataFrame({"v": pd.Series(list(valeurs), dtype=object), "e": e})
    par_valeur = tableau.groupby("v", sort=False)["e"].nunique().to_dict()
    gardees = [[v, n / total] for v, n in comptes.most_common() if par_valeur.get(v, 0) >= seuil]
    rares = [v for v, _ in comptes.most_common() if par_valeur.get(v, 0) < seuil]
    generiques = [v for v in rares if est_generique(v)]
    autres = [v for v in rares if not est_generique(v)]
    lignes_autres = tableau[tableau["v"].isin(autres)] if autres else tableau.iloc[0:0]
    return {
        "gardees": gardees,
        "rares": rares,
        "generiques": generiques,
        "autres": autres,
        "singletons": sum(1 for v in autres if comptes[v] == 1),
        "part_autres": len(lignes_autres) / total,
        "entites_autres": int(lignes_autres["e"].nunique()) if len(lignes_autres) else 0,
        "total": total,
    }


def modalites_sures(res, seuil, sentinelle=SENTINELLE):
    freq = [list(x) for x in res["gardees"]]
    if not res.get("rares"):
        return normaliser(freq), False
    for v in res["generiques"]:
        freq.append([v, PART_SENTINELLE / 3])
    a_sentinelle = False
    if res["autres"]:
        part = res["part_autres"] if res["entites_autres"] >= seuil else PART_SENTINELLE
        freq.append([sentinelle, max(part, 0.005)])
        a_sentinelle = True
    return normaliser(freq), a_sentinelle


def normaliser(freq):
    total = sum(p for _, p in freq)
    if total <= 0:
        return freq
    return [[v, round(p / total, 6)] for v, p in freq]


def cles_liees(nom_a, valeurs_a, nom_b, valeurs_b):
    petit = min(len(valeurs_a), len(valeurs_b))
    if not petit or len(valeurs_a & valeurs_b) < 0.5 * petit:
        return False
    triviales = all(v.isdigit() and len(v) <= 4 for v in valeurs_a) and all(v.isdigit() and len(v) <= 4 for v in valeurs_b)
    if not triviales:
        return True
    return petit / max(len(valeurs_a), len(valeurs_b)) >= 0.8 and jetons_nom(nom_a) == jetons_nom(nom_b)


def departement(v):
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
        return int(str(int(v)).zfill(5)[:2] + "000")
    s = str(v)
    return s[:2] + "0" * max(0, len(s) - 2)


def echantillon(valeurs, taille=400):
    if len(valeurs) <= taille:
        return list(valeurs)
    pas = len(valeurs) / taille
    return [valeurs[int(i * pas)] for i in range(taille)]


RE_DATE_POSSIBLE = re.compile(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}|\d{1,2}[A-Za-z]{3}\d{2,4}")
RE_DATE_COURTE = re.compile(r"^(?:\d{8}|\d{4}-\d{1,2}|\d{1,2}/\d{4})$")


def detecter_format_date(valeurs, indice_date):
    ech = echantillon(valeurs)
    if not ech or sum(any(c.isdigit() for c in v) for v in ech) < 0.5 * len(ech):
        return None
    possibles = sum(1 for v in ech if RE_DATE_POSSIBLE.search(v) or (indice_date and RE_DATE_COURTE.match(v)))
    if possibles < 0.5 * len(ech):
        return None
    meilleur = None
    limite = 0.4 * len(ech)
    for fmt in FORMATS_DATES:
        if fmt == "%Y%m%d" and not indice_date:
            continue
        if fmt in ("%Y-%m", "%m/%Y") and not indice_date:
            continue
        echecs = []
        for v in ech:
            try:
                dt.datetime.strptime(v, fmt)
            except ValueError:
                echecs.append(v)
                if len(echecs) > limite:
                    break
        if len(echecs) > limite:
            continue
        taux = 1 - len(echecs) / len(ech)
        if taux >= 0.6 and (meilleur is None or taux > meilleur[1]):
            meilleur = (fmt, taux, echecs)
            if taux == 1.0:
                break
    if meilleur is None:
        return None
    fmt, taux, echecs = meilleur
    return fmt if (taux >= 0.9 or peu_divers(echecs)) else None


def detecter_format_heure(valeurs):
    ech = echantillon(valeurs)
    if not ech:
        return None
    correspondances = [RE_HEURE.match(v) for v in ech]
    if sum(m is not None for m in correspondances) < 0.9 * len(ech):
        return None
    secondes = any(m is not None and m.group(3) is not None for m in correspondances)
    deux_chiffres = all(m is None or len(m.group(1)) == 2 for m in correspondances)
    return ("%H:%M:%S" if secondes else "%H:%M") if deux_chiffres else ("%-H:%M:%S" if secondes else "%-H:%M")


def peu_divers(valeurs):
    return len(set(valeurs)) <= max(5, 0.2 * len(valeurs))


class Analyse:
    def __init__(self, table, j):
        self.table = table
        self.j = j
        self.nom = table.noms[j]
        self.stockage = table.stockages[j]
        self.serie = table.donnees[j]
        self.jetons = jetons_nom(self.nom)
        self.genre = None
        self.notes = []
        self.params = {}
        self.jeton_manquant = None
        self.jetons_manquants = []
        self.format_date = None
        self.secondes = None
        self.nombres = None
        self._cles = None
        self.constant_par = None
        self.chrono_par = None
        self.rang_par = None
        self.unique_par = None
        self.partage = None
        self.unique_groupe = None
        self.exceptions = {}
        brut = self.serie.tolist()
        self.textes_bruts = None
        if self.stockage in ("texte", "mixte"):
            textes = [None if est_manquant(v) else texte_de(v) for v in brut]
            manquants = [t is None or t in JETONS_MANQUANTS for t in textes]
            jetons = Counter((None if v is None or est_manquant(v) else str(v)) for v, m in zip(brut, manquants) if m)
            if jetons:
                self.jeton_manquant = jetons.most_common(1)[0][0]
                total = sum(jetons.values())
                self.jetons_manquants = [[k, round(c / total, 6)] for k, c in jetons.most_common()]
            self.textes = [None if m else t for t, m in zip(textes, manquants)]
            self.textes_bruts = [None if m else texte_de(v, True) for v, m in zip(brut, manquants)]
        elif self.stockage == "categorie":
            self.textes = [None if est_manquant(v) else texte_de(v) for v in brut]
            self.textes_bruts = [None if est_manquant(v) else texte_de(v, True) for v in brut]
        else:
            self.textes = None
        if self.textes is not None:
            self.manquant = np.array([t is None for t in self.textes], dtype=bool)
        else:
            self.manquant = np.array([est_manquant(v) for v in brut], dtype=bool)
        presents = ~self.manquant
        self.bloc_initial = int(np.argmax(presents)) if presents.any() else len(self.manquant)

    @property
    def n(self):
        return len(self.manquant)

    @property
    def n_valides(self):
        return int((~self.manquant).sum())

    @property
    def taux_manquants(self):
        return float(self.manquant.mean()) if self.n else 0.0

    def cles(self):
        if self._cles is None:
            if self.textes is not None:
                self._cles = [None if t is None else t for t in self.textes]
            else:
                self._cles = [cle_valeur(v) for v in self.serie.tolist()]
        return self._cles

    def valeurs_valides(self):
        if self.textes is not None:
            return [t for t in self.textes if t is not None]
        return [v for v in self.serie.tolist() if not est_manquant(v)]

    def modalites_brutes(self):
        if self.textes_bruts is not None:
            return [t for t in self.textes_bruts if t is not None]
        return self.valeurs_valides()


class Composite:
    def __init__(self, membres):
        self.membres = list(membres)
        self.table = self.membres[0].table
        self.nom = " + ".join(str(m.nom) for m in self.membres)
        self.jetons = [j for m in self.membres for j in m.jetons]
        self.genre = "composite"
        self._cles = None

    @property
    def n(self):
        return self.membres[0].n

    def cles(self):
        if self._cles is None:
            listes = [m.cles() for m in self.membres]
            sortie = []
            for valeurs in zip(*listes):
                if all(v is None for v in valeurs):
                    sortie.append(None)
                else:
                    sortie.append(SEP_CLE.join("" if v is None else sans_accents(v).casefold().strip() for v in valeurs))
            self._cles = sortie
        return self._cles


class EntiteUnique:
    def __init__(self, a):
        self.membres = [a]
        self.table = a.table
        valeurs = [c for c in a.cles() if c is not None]
        self.valeur = valeurs[0] if valeurs else "1"
        self.nom = str(a.nom)
        self.jetons = list(a.jetons)
        self.genre = "unique"

    @property
    def n(self):
        return self.membres[0].n

    def cles(self):
        return [self.valeur] * self.n


class EntiteEtrangere:
    def __init__(self, colonnes, carte, nom):
        self.membres = list(colonnes)
        self.table = self.membres[0].table
        self.carte = carte
        self.nom = nom
        self.jetons = [j for m in self.membres for j in m.jetons]
        self.genre = "etrangere"
        self._cles = None

    @property
    def n(self):
        return self.membres[0].n

    def cles(self):
        if self._cles is None:
            listes = [m.cles() for m in self.membres]
            self._cles = [self.carte.get(cle_tuple(v)) for v in zip(*listes)]
        return self._cles


def cle_tuple(valeurs):
    if any(v is None for v in valeurs):
        return None
    return SEP_CLE.join(valeurs)


def membres_de(entite):
    if entite is None:
        return []
    return list(getattr(entite, "membres", [entite]))


def classer_constante(a, valeur):
    if a_indice(a.jetons, PRENOM) or est_nom_personne(a.jetons) or ressemble_nom_personne(str(valeur)):
        return "nom"
    if isinstance(valeur, str):
        fmt = detecter_format_date([valeur.strip()], a_indice(a.jetons, INDICE_DATE) or est_naissance(a.jetons))
        if fmt and (a_indice(a.jetons, INDICE_DATE) or est_naissance(a.jetons) or not est_nombre_texte(valeur.strip())):
            a.format_date = fmt
            return "date_naissance" if est_naissance(a.jetons) else "date"
    if isinstance(valeur, str) and (ressemble_identifiant(valeur) or RE_EMAIL.match(valeur) or RE_TEL.match(valeur)):
        return "identifiant"
    if len(str(valeur)) > 40:
        return "texte_libre"
    return "constante"


def classer_texte(a, garder):
    vals = a.valeurs_valides()
    if not vals:
        return "vide"
    j = a.jetons
    ech = echantillon(vals, 500)
    frac = lambda motif: sum(bool(motif.match(v)) for v in ech) / len(ech)
    if a_indice(j, EMAIL) or frac(RE_EMAIL) >= 0.5:
        return "email"
    if a_indice(j, TEL) or frac(RE_TEL) >= 0.6:
        return "telephone"
    if a_indice(j, NIR) or frac(RE_NIR) >= 0.8:
        return "nir"
    if a_indice(j, PRENOM) and a_indice(j, NOM):
        return "nom"
    if a_indice(j, PRENOM):
        return "prenom"
    if est_nom_personne(j):
        return "nom"
    if a_indice(j, ADRESSE):
        return "adresse"
    if est_code_postal(j):
        return "code_postal"
    if a_indice(j, VILLE):
        return "ville"
    if a.stockage != "categorie":
        heure = detecter_format_heure(vals)
        if heure:
            a.format_date = heure
            return "heure"
        fmt = detecter_format_date(vals, a_indice(j, INDICE_DATE) or est_naissance(j))
        if fmt:
            a.format_date = fmt
            return "date_naissance" if est_naissance(j) else "date"
        nombres = [v for v in vals if est_nombre_texte(v)]
        autres = [v for v in vals if not est_nombre_texte(v)]
        zero_tete = any(RE_ZERO_TETE.match(v) for v in nombres)
        assez = len(nombres) >= 0.9 * len(vals) or (len(nombres) >= 0.6 * len(vals) and peu_divers(autres))
        if assez and nombres and not zero_tete:
            valeurs = np.array([vers_float(v) for v in nombres])
            entiers = all(("." not in v and "," not in v and "e" not in v.lower()) for v in nombres)
            uniques = len(set(nombres))
            petit = uniques <= 20 and entiers and valeurs.min() >= 0 and valeurs.max() <= 100
            if est_id_nomme(j) and entiers and (not petit or a_indice(j, CLES_PATIENT_NUMERIQUES)):
                return "identifiant"
            if uniques == 1 and not autres:
                return "constante"
            return "discret" if uniques <= MAX_DISCRET else "numerique"
    uniques = set(vals)
    nu = len(uniques)
    longueur = float(np.mean([len(v) for v in ech]))
    mots = float(np.mean([len(v.split()) for v in ech]))
    if nu >= 2 and not a_indice(j, NOMENCLATURE) and noms_par_valeurs(uniques):
        return "nom"
    if nu >= 2 and frac(RE_INITIALES) >= 0.9:
        return "identifiant"
    if est_id_nomme(j):
        return "identifiant"
    if nu == 1:
        return classer_constante(a, next(iter(uniques)))
    if a_indice(j, TEXTE_LIBRE) and (nu >= 10 or longueur >= 20):
        return "texte_libre"
    if longueur >= 40 or (mots >= 6 and nu > 0.5 * len(vals)):
        return "texte_libre"
    if nu >= 0.9 * len(vals) and nu >= 20 and longueur <= 30:
        return "identifiant"
    if nu <= MAX_CATEGORIES or a_indice(j, NOMENCLATURE) or a.nom in garder:
        return "categorie"
    return "code"


def dates_entieres(a, x):
    textes = [str(int(v)) for v in x]
    if not textes or not all(len(t) == 8 for t in textes):
        return False
    reussis = 0
    for t in echantillon(textes, 400):
        try:
            d = dt.datetime.strptime(t, "%Y%m%d")
            if 1850 <= d.year <= 2150:
                reussis += 1
        except ValueError:
            pass
    taux = reussis / min(len(textes), 400)
    indice = a_indice(a.jetons, INDICE_DATE) or est_naissance(a.jetons)
    return taux >= 0.95 if indice else (taux >= 0.98 and len(set(textes)) >= 20 and not est_id_nomme(a.jetons))


def classer_nombre(a, garder):
    x = np.array([float(v) for v in a.valeurs_valides()], dtype=float)
    if len(x) == 0:
        return "vide"
    j = a.jetons
    entiers = bool(np.all(np.mod(x[np.isfinite(x)], 1) == 0))
    if a_indice(j, TEL):
        return "telephone"
    if est_code_postal(j):
        return "code_postal"
    if a_indice(j, NIR) and entiers:
        return "nir"
    if entiers and dates_entieres(a, x):
        a.format_date = "%Y%m%d"
        return "date_naissance" if est_naissance(j) else "date"
    uniques = len(np.unique(x))
    petit = uniques <= 20 and entiers and x.min() >= 0 and x.max() <= 100
    if est_id_nomme(j) and entiers and (not petit or a_indice(j, CLES_PATIENT_NUMERIQUES)):
        return "identifiant"
    if entiers and uniques == len(x) and uniques >= 20 and (x.max() - x.min() + 1) == uniques:
        return "identifiant"
    if uniques == 1:
        return "constante"
    if uniques <= MAX_DISCRET:
        return "discret"
    return "numerique"


def classer(a, garder):
    st = a.stockage
    if a.nom in a.table.options.get("imbriquees", ()):
        a.notes.append("colonne imbriquée (listes ou structures) : non reproduite")
        return "vide"
    if a.n_valides == 0:
        return "vide"
    if st in ("texte", "mixte", "categorie"):
        return classer_texte(a, garder)
    if st in ("entier", "decimal"):
        return classer_nombre(a, garder)
    if st == "booleen":
        return "booleen"
    if st in ("datetime", "date"):
        return "date_naissance" if est_naissance(a.jetons) else "date"
    if st == "heure":
        return "heure"
    if st == "duree":
        return "numerique"
    if st == "binaire":
        a.notes.append("contenu binaire remplacé par des octets fictifs")
        return "binaire"
    return classer_texte(a, garder)


def propager_identifiants(analyses, garder=()):
    garder = set(garder)
    for _ in range(3):
        references = [(a, set(c for c in a.cles() if c is not None)) for a in analyses if a.genre in ("identifiant", "nir")]
        change = False
        for a in analyses:
            if a.nom in garder or a.genre not in ("categorie", "code", "discret", "numerique"):
                continue
            nomme = a_indice(a.jetons, ID_FAIBLES) or a_indice(a.jetons, ID_FORTS) or a_indice(a.jetons, ID_CLES)
            if a.genre in ("discret", "numerique") and not nomme:
                continue
            if a.stockage not in ("texte", "mixte", "categorie") and not nomme:
                continue
            ensemble = set(c for c in a.cles() if c is not None)
            if len(ensemble) < 20:
                continue
            for ref, ens_ref in references:
                if ref is a or not ens_ref:
                    continue
                if len(ensemble & ens_ref) >= 0.8 * len(ensemble):
                    a.genre = "identifiant"
                    a.notes.append(f"valeurs partagées avec « {ref.nom} » ({ref.table.nom_affiche})")
                    change = True
                    break
        if not change:
            break


def codes_entite(a):
    cles = a.cles()
    codes, _ = pd.factorize(pd.Series(cles, dtype=object), use_na_sentinel=True)
    return np.asarray(codes)


def preparer_dates(a):
    if a.secondes is not None:
        return a.secondes
    if a.genre == "heure":
        sortie = []
        for v in (a.textes if a.textes is not None else a.serie.tolist()):
            if v is None or est_manquant(v):
                sortie.append(np.nan)
            elif isinstance(v, dt.time):
                sortie.append(v.hour * 3600 + v.minute * 60 + v.second)
            else:
                m = RE_HEURE.match(str(v))
                sortie.append(np.nan if m is None else int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3) or 0))
        a.secondes = np.array(sortie, dtype=float)
        return a.secondes
    if a.textes is not None:
        textes = pd.Series(a.textes, dtype=object)
        if a.format_date:
            serie = pd.to_datetime(textes, format=a.format_date, errors="coerce", utc="%z" in a.format_date)
        else:
            serie = pd.to_datetime(textes, errors="coerce")
        a.secondes = vers_secondes(serie)
    elif a.format_date and a.stockage in ("entier", "decimal"):
        textes = pd.Series([None if est_manquant(v) else str(int(v)) for v in a.serie.tolist()], dtype=object)
        a.secondes = vers_secondes(pd.to_datetime(textes, format=a.format_date, errors="coerce"))
    else:
        try:
            a.secondes = vers_secondes(a.serie)
        except (OverflowError, ValueError, TypeError):
            sortie = []
            for v in a.serie.tolist():
                try:
                    if est_manquant(v):
                        sortie.append(np.nan)
                    elif isinstance(v, dt.datetime):
                        sortie.append((v.replace(tzinfo=None) - EPOQUE).total_seconds())
                    else:
                        sortie.append((dt.datetime.combine(v, dt.time()) - EPOQUE).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    sortie.append(np.nan)
            a.secondes = np.array(sortie, dtype=float)
    return a.secondes


def valeurs_cles(a):
    return set(c for c in a.cles() if c is not None)


def constance_par_groupe(codes, cles, permissif=False):
    tableau = pd.DataFrame({"e": codes, "v": pd.Series(cles, dtype=object)})
    tableau = tableau[(tableau["e"] >= 0) & tableau["v"].notna()]
    if tableau.empty:
        return None
    tailles = tableau.groupby("e")["v"].size()
    distincts = tableau.groupby("e")["v"].nunique()
    multiples = tailles[tailles >= 2].index
    if len(multiples) == 0:
        return None
    frac = float((distincts.loc[multiples] == 1).mean())
    if len(multiples) < 5:
        return frac if (permissif and frac == 1.0) else None
    return frac


def entite_structurelle(analyses_table, seuil):
    if not analyses_table or analyses_table[0].n < 2 * seuil:
        return None
    candidats = []
    for a in analyses_table:
        if a.genre not in ("categorie", "code", "discret", "numerique"):
            continue
        if a_indice(a.jetons, EXCLUS_INDIVIDU) or a_indice(a.jetons, NON_ID):
            continue
        cles = [c for c in a.cles() if c is not None]
        nu = len(set(cles))
        if nu < seuil or nu > len(cles) / 1.5:
            continue
        candidats.append((nu, a))
    candidats.sort(key=lambda x: -x[0])
    autres_colonnes = [o for o in analyses_table if o.genre not in GENRES_MAPPES | GENRES_PERSONNES | {"vide", "constante"}][:300]
    for nu, c in candidats[:5]:
        distinctes = echantillon(sorted(valeurs_cles(c)), 300)
        forme = sum(1 for v in distinctes if RE_FORME_CLE.match(v) or ressemble_nom_personne(v)) >= 0.9 * len(distinctes)
        if forme and not a_indice(c.jetons, NOMENCLATURE):
            return c
        codes = codes_entite(c)
        constantes, variables, rejet = 0, 0, False
        for o in autres_colonnes:
            if o is c:
                continue
            frac = constance_par_groupe(codes, o.cles())
            if frac is None:
                continue
            personne = a_indice(o.jetons, ATTRIBUTS_PERSONNE) or o.genre == "date_naissance"
            if frac >= 0.95:
                constantes += 1
            elif frac <= 0.5:
                variables += 1
            if personne and frac < 0.9:
                rejet = True
                break
        if not rejet and constantes >= 1 and variables >= 1:
            return c
    return None


def recouvrement(valeurs, autres_ensembles):
    total = 0
    for ensemble in autres_ensembles:
        petit = min(len(valeurs), len(ensemble))
        if petit and len(valeurs & ensemble) >= 0.5 * petit:
            total += 1
    return total


def colonne_choisie(liste, demandes):
    voulus = {sans_accents(str(d)).casefold().strip() for d in demandes}
    return [a for a in liste if sans_accents(str(a.nom)).casefold().strip() in voulus]


def choisir_entite(liste, seuil, demandes, autres_ensembles):
    if not liste:
        return None, "aucune"
    n = liste[0].n
    if demandes:
        choisies = colonne_choisie(liste, demandes)
        if choisies:
            for a in choisies:
                if a.genre not in GENRES_MAPPES | GENRES_PERSONNES | {"date_naissance"}:
                    a.genre = "identifiant"
                a.notes.append("clé d'individu indiquée à sosie (--cle-individu)")
            return (choisies[0] if len(choisies) == 1 else Composite(choisies)), "utilisateur"
        if {sans_accents(str(d)).casefold().strip() for d in demandes} & {"ligne", "lignes"}:
            return None, "lignes"
    if n >= 2:
        for a in liste:
            if a.n_valides < 1 or len(valeurs_cles(a)) != 1:
                continue
            nom_ou_prenom = a.genre in ("nom", "prenom") and not est_professionnel(a.jetons)
            naissance = est_naissance(a.jetons) and a.genre in GENRES_DATES | {"constante"}
            cle = nom_patient(a.jetons) and a.genre in ("identifiant", "nir")
            if nom_ou_prenom or naissance or cle:
                return EntiteUnique(a), "unique"
    candidats = []
    for a in liste:
        par_nom = nom_patient(a.jetons) and nom_de_cle(a.jetons) and a.genre in ("categorie", "discret", "numerique", "code")
        if a.genre not in ("identifiant", "nir", "code") and not par_nom:
            continue
        if a.n_valides < 2:
            continue
        valeurs = valeurs_cles(a)
        nu = len(valeurs)
        if nu < 2 or nu >= a.n_valides:
            continue
        if a.genre == "code" and not (est_id_nomme(a.jetons) or nom_patient(a.jetons)):
            continue
        if a_indice(a.jetons, EXCLUS_INDIVIDU) and not nom_patient(a.jetons):
            continue
        if par_nom and nu < 3:
            continue
        priorite = 2 if nom_patient(a.jetons) else (0 if a_indice(a.jetons, SECONDAIRES) else 1)
        candidats.append(((priorite, recouvrement(valeurs, autres_ensembles), nu >= seuil, -nu), a))
    secondaire = None
    if candidats:
        candidats.sort(key=lambda x: x[0], reverse=True)
        score, choisie = candidats[0]
        if choisie.genre not in GENRES_MAPPES | GENRES_PERSONNES:
            choisie.genre = "identifiant"
        if score[0] >= 1:
            return choisie, "cle"
        secondaire = choisie
    personnes = [a for a in liste if (a.genre in ("nom", "prenom") and not est_professionnel(a.jetons)) or a.genre == "date_naissance"]
    if any(a.genre in ("nom", "prenom") for a in personnes):
        comp = Composite(personnes)
        cles = [c for c in comp.cles() if c is not None]
        if 2 <= len(set(cles)) < len(cles):
            return comp, "personne"
    if secondaire is not None:
        return secondaire, "secondaire"
    naissances = [a for a in personnes if a.genre == "date_naissance"]
    if naissances:
        a = max(naissances, key=lambda x: x.n_valides)
        cles = [c for c in a.cles() if c is not None]
        if len(set(cles)) >= 2 and len(cles) >= 1.5 * len(set(cles)):
            return a, "personne"
    e = entite_structurelle(liste, seuil)
    if e is not None:
        if e.genre not in GENRES_MAPPES | GENRES_PERSONNES:
            e.genre = "identifiant"
        e.notes.append("repérée comme identifiant d'individu (plusieurs lignes par valeur)")
        return e, "structure"
    return None, "aucune"


def carte_fonctionnelle(cles_source, cles_cible):
    tableau = pd.DataFrame({"s": pd.Series(cles_source, dtype=object), "c": pd.Series(cles_cible, dtype=object)}).dropna()
    if tableau.empty:
        return None
    distincts = tableau.groupby("s")["c"].nunique()
    if float((distincts <= 1).mean()) < 0.95:
        return None
    return tableau.drop_duplicates("s").set_index("s")["c"].to_dict()


def propager_entites(par_table, structures):
    parents = []
    for i, (liste, s) in enumerate(zip(par_table, structures)):
        cle = s["entite"] if s["type_entite"] in ("cle", "utilisateur", "personne") else None
        if cle is None:
            uniques = [a for a in liste if a.genre in ("identifiant", "nir") and nom_patient(a.jetons)
                       and a.n_valides >= 2 and len(valeurs_cles(a)) == a.n_valides]
            cle = uniques[0] if uniques else None
        if cle is not None:
            parents.append((i, cle))
    if not parents:
        return
    for i, (liste, s) in enumerate(zip(par_table, structures)):
        if s["type_entite"] not in ("aucune", "secondaire", "structure"):
            continue
        trouve = None
        colonnes = [a for a in liste if a.genre in ("identifiant", "nir", "code")]
        for c in colonnes:
            valeurs = valeurs_cles(c)
            if len(valeurs) < 2:
                continue
            unique_enfant = len(valeurs) == c.n_valides
            generique = set(c.jetons) <= {"id", "num", "numero", "no", "n", "code", "cle", "key", "ref", "identifiant"}
            for k, cle in parents:
                if k == i:
                    continue
                for p in par_table[k]:
                    if p is cle or p.genre not in ("identifiant", "nir", "code") or p in membres_de(cle):
                        continue
                    if unique_enfant and (generique or c.jetons != p.jetons):
                        continue
                    ensemble = valeurs_cles(p)
                    if len(valeurs & ensemble) < 0.8 * len(valeurs) or not cles_liees(c.nom, valeurs, p.nom, ensemble):
                        continue
                    carte = carte_fonctionnelle(p.cles(), cle.cles())
                    if carte:
                        trouve = EntiteEtrangere([c], carte, f"{cle.nom} (via `{c.nom}` ↔ {p.table.nom_affiche})")
                        break
                if trouve:
                    break
            if trouve:
                break
        if trouve is None:
            noms = {a.nom: a for a in liste}
            for k, cle in parents:
                if k == i:
                    continue
                parent = {a.nom: a for a in par_table[k]}
                communs = [nom for nom in noms if nom in parent and parent[nom] not in membres_de(cle)
                           and noms[nom].genre not in ("vide", "texte_libre", "numerique", "booleen")]
                if len(communs) < 2:
                    continue
                source = [cle_tuple(v) for v in zip(*[parent[nom].cles() for nom in communs])]
                enfant = set(cle_tuple(v) for v in zip(*[noms[nom].cles() for nom in communs]))
                enfant.discard(None)
                if len(enfant) < 2 or len(enfant & set(source)) < 0.8 * len(enfant):
                    continue
                carte = carte_fonctionnelle(source, cle.cles())
                if carte:
                    trouve = EntiteEtrangere([noms[nom] for nom in communs], carte,
                                             f"{cle.nom} (via {len(communs)} colonnes communes ↔ {par_table[k][0].table.nom_affiche})")
                    break
        if trouve is not None:
            s["entite"] = trouve
            s["type_entite"] = "etrangere"


def detecter_rang(a, codes):
    if a.textes is not None:
        valeurs = [np.nan if t is None or not RE_NOMBRE.match(t) else vers_float(t) for t in a.textes]
    else:
        valeurs = [np.nan if est_manquant(v) else float(v) for v in a.serie.tolist()]
    x = np.array(valeurs, dtype=float)
    m = (codes >= 0) & ~np.isnan(x)
    if m.sum() < 10 or not np.all(np.mod(x[m], 1) == 0):
        return None
    tableau = pd.DataFrame({"e": codes[m], "v": x[m]})
    g = tableau.groupby("e")["v"]
    tailles = g.size()
    multiples = tailles[tailles >= 2].index
    if len(multiples) < 5:
        return None
    minimum, maximum, distincts = g.min(), g.max(), g.nunique()
    for base in (1, 0):
        ok = (minimum == base) & (maximum == base + tailles - 1) & (distincts == tailles)
        taux = float(ok.loc[multiples].mean())
        if taux >= 0.95:
            return base, taux
    return None


def detecter_unique(a, codes):
    cles = a.cles()
    tableau = pd.DataFrame({"e": codes, "v": pd.Series(cles, dtype=object)})
    tableau = tableau[(tableau["e"] >= 0) & tableau["v"].notna()]
    if tableau.empty:
        return None
    g = tableau.groupby("e")["v"]
    tailles = g.size()
    multiples = tailles[tailles >= 2].index
    if len(multiples) < 5 or float(np.median(tailles.loc[multiples])) < 2:
        return None
    distincts = g.nunique()
    taux = float((distincts.loc[multiples] == tailles.loc[multiples]).mean())
    return taux if taux >= 0.95 else None


def detecter_sequence(a, codes, positions):
    cles = a.cles()
    tableau = pd.DataFrame({"e": codes, "v": pd.Series(cles, dtype=object), "p": positions})
    tableau = tableau[(tableau["e"] >= 0) & tableau["v"].notna() & tableau["p"].notna()]
    if tableau.empty:
        return None
    n_entites = tableau["e"].nunique()
    presence = (tableau.groupby("v")["e"].nunique() / max(1, n_entites)).to_dict()
    tailles = tableau.groupby("e")["v"].transform("size")
    tableau = tableau[tailles >= 2]
    if tableau["e"].nunique() < 5 or tableau["v"].nunique() < 3:
        return None
    tableau = tableau.sort_values(["e", "p"], kind="mergesort")
    rang = tableau.groupby("e").cumcount()
    taille = tableau.groupby("e")["v"].transform("size")
    tableau = tableau.assign(r=rang / (taille - 1))
    ordre = tableau.groupby("v")["r"].mean().sort_values(kind="mergesort")
    position = {v: k for k, v in enumerate(ordre.index)}
    rangs = tableau["v"].map(position).to_numpy()
    entites = tableau["e"].to_numpy()
    meme = entites[1:] == entites[:-1]
    if meme.sum() < 10:
        return None
    croissant = float((rangs[1:] > rangs[:-1])[meme].mean())
    if croissant < 0.9:
        return None
    return list(ordre.index), round(1 - croissant, 4), presence


def detecter_unique_groupe(a, codes, dates):
    cles = a.cles()
    meilleur = None
    for d in dates:
        secondes = preparer_dates(d)
        tableau = pd.DataFrame({"e": codes, "s": secondes, "v": pd.Series(cles, dtype=object)})
        tableau = tableau[(tableau["e"] >= 0) & tableau["v"].notna() & ~np.isnan(tableau["s"].to_numpy())]
        if tableau.empty:
            continue
        g = tableau.groupby(["e", "s"])["v"]
        tailles = g.size()
        multiples = tailles[tailles >= 2]
        if len(multiples) < 10 or len(multiples) < 0.3 * len(tailles):
            continue
        distincts = g.nunique().loc[multiples.index]
        taux = float((distincts == multiples).mean())
        if taux >= 0.95 and (meilleur is None or len(multiples) > meilleur[2]):
            meilleur = (d, taux, len(multiples))
    return meilleur


def ordre_chrono(a, codes, secondes):
    masque = (codes >= 0) & ~np.isnan(secondes)
    if masque.sum() < 10:
        return None
    idx = np.where(masque)[0]
    ordre = idx[np.argsort(codes[idx], kind="stable")]
    g = codes[ordre]
    v = secondes[ordre]
    meme = g[1:] == g[:-1]
    descente = meme & (v[1:] < v[:-1])
    groupes = pd.Series(g).value_counts()
    n_groupes = int((groupes >= 2).sum())
    if n_groupes < 5:
        return None
    groupes_desordre = len(set(g[1:][descente]))
    taux = 1 - groupes_desordre / n_groupes
    return taux if taux >= 0.95 else None


def noter_exception(a, cle, taux):
    if taux is not None and taux < 1:
        a.exceptions[cle] = round(max(1 - taux, 0.0005), 4)


def analyser_structure(liste, entite, seuil):
    unique_entite = isinstance(entite, EntiteUnique)
    repetees = []
    if entite is not None:
        repetees.append(entite)
    autres = []
    for a in liste:
        if a.genre in ("identifiant", "nir") and a.n_valides and a not in membres_de(entite) and a is not entite:
            nu = len(valeurs_cles(a))
            if nu < a.n_valides:
                autres.append((nu, a))
    autres.sort(key=lambda x: x[0])
    repetees += [a for _, a in autres]
    exclues = [entite]
    independantes = [
        a for a in liste
        if a.genre not in GENRES_MAPPES | GENRES_PERSONNES | {"vide", "constante"} and a not in exclues
    ]
    for e in repetees:
        codes = codes_entite(e)
        for a in independantes:
            if a.constant_par is not None:
                continue
            permissif = unique_entite or a_indice(a.jetons, ATTRIBUTS_PERSONNE) or a.genre == "date_naissance"
            frac = constance_par_groupe(codes, a.cles(), permissif and e is entite)
            if frac is not None and frac >= 0.95:
                a.constant_par = e
                noter_exception(a, "constant", frac)
        for a in independantes:
            if a.genre not in GENRES_DATES or a.constant_par is not None or a.chrono_par is not None:
                continue
            taux = ordre_chrono(a, codes, preparer_dates(a))
            if taux is not None:
                a.chrono_par = e
                noter_exception(a, "chrono", taux)
    if entite is not None and not unique_entite:
        codes = codes_entite(entite)
        chrono = [a for a in independantes if a.chrono_par is entite]
        positions = np.arange(len(codes), dtype=float)
        ref_date = None
        if not chrono:
            dates = [a for a in independantes if a.genre == "date" and a.constant_par is None]
            if dates:
                meilleure = max(dates, key=lambda x: x.n_valides)
                positions = preparer_dates(meilleure)
                ref_date = meilleure.nom
        for a in independantes:
            if a.constant_par is not None:
                continue
            if a.genre in ("discret", "numerique"):
                res = detecter_rang(a, codes)
                if res is not None:
                    base, taux = res
                    a.rang_par = (entite, base)
                    noter_exception(a, "rang", taux)
                    a.notes.append(f"rang de {base} à k pour un même `{entite.nom}`")
                    continue
            if a.genre in ("categorie", "discret", "code_postal", "ville"):
                taux = detecter_unique(a, codes)
                if taux is not None:
                    a.unique_par = entite
                    noter_exception(a, "unique", taux)
                elif a.genre in ("categorie", "discret"):
                    dates_groupes = [d for d in independantes if d.genre == "date" and d.constant_par is None]
                    res = detecter_unique_groupe(a, codes, dates_groupes) if dates_groupes else None
                    if res is not None:
                        a.unique_groupe = res[0]
                        noter_exception(a, "unique_groupe", res[1])
                        a.notes.append(f"jamais répétée pour un même `{entite.nom}` à une même `{res[0].nom}`")
                if a.genre in ("categorie", "discret"):
                    seq = detecter_sequence(a, codes, positions)
                    if seq is not None:
                        a.params_sequence = (seq[0], seq[1], ref_date, seq[2])
    dates = [a for a in liste if a.genre in GENRES_DATES]
    chaine, exceptions = [], []
    if len(dates) >= 2:
        secs = {id(a): preparer_dates(a) for a in dates}

        def taux_avant(x, y):
            sx, sy = secs[id(x)], secs[id(y)]
            m = ~np.isnan(sx) & ~np.isnan(sy)
            if m.sum() < 20:
                return None
            return float((sx[m] <= sy[m]).mean())

        tri = sorted(dates, key=lambda a: float(np.nanmedian(secs[id(a)])) if np.isfinite(secs[id(a)]).any() else np.inf)
        for a in tri:
            taux = [taux_avant(b, a) for b in chaine]
            if all(t is not None and t >= 0.98 for t in taux):
                if chaine:
                    exceptions.append(round(1 - taux[-1], 4) if taux[-1] < 1 else 0.0)
                chaine.append(a)
        if len(chaine) < 2:
            chaine, exceptions = [], []
    return chaine, exceptions


def jetons_de_texte(a, ent_valides, seuil, est_jeton, sentinelle):
    vals = [t for t in a.textes if t is not None]
    jetons = [v for v in vals if est_jeton(v)]
    if not jetons:
        return []
    ent_j = None if ent_valides is None else [e for e, v in zip(ent_valides, vals) if est_jeton(v)]
    res = frequences_sures(jetons, ent_j, seuil)
    freq, a_sentinelle = modalites_sures(res, seuil, sentinelle)
    part_jetons = len(jetons) / len(vals)
    if res["autres"]:
        a.notes.append(f"valeurs textuelles rares (moins de {seuil} individus) remplacées" + (f" par « {sentinelle} »" if a_sentinelle else ""))
    if a_sentinelle:
        a.params["sentinelle"] = sentinelle
    garantir(a.params, [v for v in res["generiques"]] + ([sentinelle] if a_sentinelle else []))
    return [[v, round(q * part_jetons, 6)] for v, q in freq]


def garantir(p, valeurs):
    if valeurs:
        liste = p.setdefault("garantis", [])
        for v in valeurs:
            if v not in liste:
                liste.append(v)


def codes_speciaux(x, ents, seuil):
    if len(x) < 20:
        return [], np.zeros(len(x), dtype=bool)
    speciaux, masque = [], np.zeros(len(x), dtype=bool)
    valeurs, comptes = np.unique(x, return_counts=True)
    for v, c in zip(valeurs, comptes):
        if not float(v).is_integer() or int(v) not in CODES_NUMERIQUES:
            continue
        reste = x[x != v]
        if len(reste) < 10:
            continue
        q01, q99 = np.quantile(reste, [0.01, 0.99])
        if q01 <= v <= q99:
            continue
        sel = x == v
        porteurs = len(set(ents[sel].tolist()))
        part = float(c / len(x)) if porteurs >= seuil else 0.01
        speciaux.append([float(v), round(part, 6)])
        masque |= sel
    return speciaux, masque


def dates_speciales(secondes, ents, seuil):
    ok = ~np.isnan(secondes)
    hors = ok & ((secondes < SEC_MIN) | (secondes > SEC_MAX))
    valeurs, comptes = np.unique(secondes[ok], return_counts=True)
    total = int(ok.sum())
    for v, c in zip(valeurs, comptes):
        if not (SEC_MIN <= v <= SEC_MAX):
            continue
        try:
            iso = (EPOQUE + dt.timedelta(seconds=float(v))).date().isoformat()
        except (OverflowError, ValueError):
            continue
        if iso in DATES_SENTINELLES or (c >= 0.01 * total and iso[5:] in ("01-01", "12-31") and (iso < "1910" or iso > "2090")):
            hors |= secondes == v
    return hors


def numerotation(a):
    if a.n < 20 or a.taux_manquants > 0 or a.genre not in ("identifiant", "discret", "numerique"):
        return None
    try:
        x = np.array([float(v) for v in (a.cles() if a.textes is not None else a.valeurs_valides())], dtype=float)
    except (TypeError, ValueError):
        return None
    if len(x) != a.n or not np.all(np.mod(x, 1) == 0):
        return None
    if a.textes is not None and any(t != str(int(float(t))) for t in a.textes if t is not None):
        return None
    base = x[0]
    attendu = base + np.arange(a.n)
    return int(base) if float(np.mean(x == attendu)) >= 0.99 else None


def parametres(a, seuil, entites):
    g = a.genre
    valides = ~a.manquant
    tous = entites_completes(entites, a.n)
    ent_comp = tous[valides]
    n_eff = len(set(ent_comp.tolist())) if len(ent_comp) else 0
    poids = poids_entites(ent_comp)
    p = {}
    a.params = p
    base_numerotation = numerotation(a)
    if base_numerotation is not None:
        p["numerotation"] = base_numerotation
        a.notes.append(f"numérotation des lignes {base_numerotation}, {base_numerotation + 1}, … dans l'ordre du fichier")
    if g == "numerique":
        if a.textes is not None:
            vals = [t for t in a.textes if t is not None]
            nombres = [v for v in vals if est_nombre_texte(v)]
            x = np.array([vers_float(v) for v in nombres])
            masque_nombres = np.array([est_nombre_texte(v) for v in vals], dtype=bool)
            virgules = sum("," in v for v in nombres if not RE_MILLIERS.match(v)) + sum(bool(re.search(r",\d+$", v)) for v in nombres if RE_MILLIERS.match(v))
            points = sum("." in v for v in nombres)
            p["decimale"] = "," if virgules > points else "."
            milliers = [v for v in nombres if RE_MILLIERS.match(v)]
            if len(milliers) >= 0.3 * len(nombres):
                p["milliers"] = Counter(re.findall(r"[   ]", " ".join(milliers))).most_common(1)[0][0]
            scientifiques = [v for v in nombres if "e" in v.lower()]
            if len(scientifiques) >= 0.5 * len(nombres):
                mantisses = [re.split(r"[.,]", v.lower().split("e")[0]) for v in scientifiques]
                p["scientifique"] = max(len(m[1]) if len(m) > 1 else 0 for m in mantisses)
                p["majuscule_e"] = sum("E" in v for v in scientifiques) > len(scientifiques) / 2
            parties = [re.split(r"[.,]", re.sub(r"[   ]", "", v).lower().split("e")[0]) for v in nombres if "e" not in v.lower()]
            decs = [len(pa[-1]) if len(pa) > 1 else 0 for pa in parties]
            p["decimales"] = max(decs) if decs else 0
            p["decimales_fixes"] = bool(decs) and len(set(decs)) == 1 and decs[0] > 0
            p["entier"] = p["decimales"] == 0 and "scientifique" not in p
            if "scientifique" in p:
                p["decimales"] = None
            jetons = jetons_de_texte(a, ent_comp, seuil, lambda v: not est_nombre_texte(v), SENTINELLE_VALEUR)
            if jetons:
                p["jetons"] = jetons
            ent_x = ent_comp[masque_nombres]
            a.nombres = x
        elif a.stockage == "duree":
            x = np.array([pd.Timedelta(v).total_seconds() for v in a.valeurs_valides()], dtype=float)
            p["decimales"] = 0 if np.all(np.mod(x, 1) == 0) else None
            p["entier"] = False
            ent_x = ent_comp
        else:
            x = np.array([float(v) for v in a.valeurs_valides()], dtype=float)
            d = decimales_flottants(x)
            p["decimales"] = d
            p["entier"] = d == 0
            ent_x = ent_comp
        if a.stockage != "duree":
            infinis = np.isinf(x)
            if infinis.any() and a.textes is not None:
                x, ent_x = x[~infinis], ent_x[~infinis]
            elif infinis.any():
                for v in (np.inf, -np.inf):
                    sel = x == v
                    if sel.any():
                        porteurs = len(set(ent_x[sel].tolist()))
                        part = float(sel.sum() / len(x)) if porteurs >= seuil else 0.01
                        p.setdefault("speciales", []).append([float(v), round(part, 6)])
                        garantir(p, [float(v)])
                a.notes.append("valeurs infinies (Inf) reproduites")
                x, ent_x = x[~infinis], ent_x[~infinis]
            speciaux, masque = codes_speciaux(x, ent_x, seuil)
            if speciaux:
                p["speciales"] = p.get("speciales", []) + speciaux
                garantir(p, [v for v, _ in speciaux])
                a.notes.append("codes spéciaux (ex. " + ", ".join(nombre_court(v) for v, _ in speciaux[:3]) + ") hors distribution")
                x, ent_x = x[~masque], ent_x[~masque]
        n_eff_x = len(set(ent_x.tolist()))
        p.update(quantiles_surs(x, seuil, n_eff_x, poids_entites(ent_x)))
        if entites is not None and a.constant_par is None and a.rang_par is None and len(x) >= 10:
            niveaux_repetes(a, x, ent_x, entites, seuil)
    elif g in ("discret", "categorie", "code_postal", "ville"):
        if a.textes is None:
            vals = [v.item() if isinstance(v, np.generic) else v for v in a.valeurs_valides()]
        elif g == "categorie":
            vals = a.modalites_brutes()
        else:
            vals = [t for t in a.textes if t is not None]
        ents = list(ent_comp)
        res = frequences_sures(vals, ents, seuil)
        if g == "code_postal" and res["rares"]:
            gardees = {v for v, _ in res["gardees"]}
            transformes = [v if v in gardees else departement(v) for v in vals]
            res = frequences_sures(transformes, ents, seuil)
            if res["gardees"]:
                a.notes.append("codes postaux rares ramenés au département (ex. 75000)")
        uniques = len(set(vals))
        numerique = a.textes is None or g == "discret" or all(isinstance(v, str) and est_nombre_texte(v) for v in vals)
        categories_numeriques = None
        if a.stockage == "categorie" and isinstance(a.serie.dtype, pd.CategoricalDtype):
            type_cat = a.serie.cat.categories.dtype
            if pd.api.types.is_integer_dtype(type_cat):
                categories_numeriques = "entier"
            elif pd.api.types.is_float_dtype(type_cat):
                categories_numeriques = "decimal"
        if (g == "discret" and numerique) or categories_numeriques:
            freq = [list(x) for x in res["gardees"]]
            if res["autres"]:
                a.notes.append(f"valeurs rares (moins de {seuil} individus) non reproduites")
            textes_rares = [v for v in res["rares"] if isinstance(v, str) and not est_nombre_texte(v)]
            if textes_rares and a.textes is not None and not categories_numeriques:
                for v in [x for x in textes_rares if est_generique(x)]:
                    freq.append([v, PART_SENTINELLE / 3])
                garantir(p, [x for x in textes_rares if est_generique(x)])
                if any(not est_generique(x) for x in textes_rares):
                    freq.append([SENTINELLE_VALEUR, PART_SENTINELLE])
                    p["sentinelle"] = SENTINELLE_VALEUR
                    garantir(p, [SENTINELLE_VALEUR])
            paires = [(v, e) for v, e in zip(vals, ents) if not isinstance(v, str) or est_nombre_texte(v)]
            if not res["gardees"] and paires:
                nombres = np.array([vers_float(v) if isinstance(v, str) else float(v) for v, _ in paires], dtype=float)
                ent_n = np.array([e for _, e in paires])
                p["repli_numerique"] = quantiles_surs(nombres, seuil, len(set(ent_n.tolist())), poids_entites(ent_n))
                p["repli_entier"] = bool(np.all(np.mod(nombres[np.isfinite(nombres)], 1) == 0))
                a.notes.append("toutes les valeurs sont rares : remplacées par des valeurs de même ordre de grandeur")
            freq = normaliser(freq) if freq else []
        elif g in ("code_postal", "ville"):
            freq = normaliser([list(x) for x in res["gardees"]])
            if not freq:
                p["generique"] = True
                a.notes.append("toutes les modalités sont rares : remplacées par des modalités génériques")
            elif res["rares"]:
                a.notes.append(f"modalités rares (moins de {seuil} individus) remplacées")
        else:
            freq, a_sentinelle = modalites_sures(res, seuil)
            if not res["gardees"] and not res.get("generiques"):
                k = max(2, min(uniques, 5)) if uniques >= 2 else 1
                freq = [[f"{SENTINELLE}_{i + 1}" if k > 1 else SENTINELLE, round(1 / k, 6)] for i in range(k)]
                a_sentinelle = False
                a.notes.append(f"toutes les modalités sont rares (moins de {seuil} individus) : remplacées par « {SENTINELLE} »")
            elif res["autres"]:
                a.notes.append(f"modalités rares (moins de {seuil} individus) remplacées par « {SENTINELLE} »")
            if a_sentinelle and (a.unique_par is not None or a.unique_groupe is not None) and len(res["autres"]) >= 2:
                besoin = min(len(res["autres"]), max_lignes_par_entite(entites) - len(res["gardees"]))
                if besoin >= 2:
                    part = dict((str(v), q) for v, q in freq).get(SENTINELLE, PART_SENTINELLE)
                    freq = [x for x in freq if x[0] != SENTINELLE] + [[f"{SENTINELLE}_{k + 1}", round(part / besoin, 6)] for k in range(besoin)]
                    freq = normaliser(freq)
                    a_sentinelle = False
                    garantir(p, [f"{SENTINELLE}_{k + 1}" for k in range(besoin)])
            if a_sentinelle:
                p["sentinelle"] = SENTINELLE
            garantir(p, list(res["generiques"]) + ([SENTINELLE] if a_sentinelle else []))
            if res.get("singletons") and res["gardees"]:
                p["singleton"] = SENTINELLE_UNIQUE
                a.notes.append(f"une modalité n'apparaît que sur une ligne : « {SENTINELLE_UNIQUE} » joue ce rôle")
            if g == "categorie" and a.textes_bruts is not None:
                plies = {sans_accents(v).strip().casefold() for v in set(vals)}
                if len(plies) < uniques:
                    p["variantes"] = True
                    a.notes.append("variantes de casse ou d'espaces (ex. « Oui » / « oui ») : normalise-les dans le code")
        p["modalites"] = freq
        p["n_uniques"] = uniques
        if a.stockage == "categorie" and isinstance(a.serie.dtype, pd.CategoricalDtype):
            gardees = list(dict.fromkeys(str(v) for v, _ in freq))
            rares = {texte_de(v, True) for v in res["rares"]}
            ordre = []
            sentinelle = p.get("sentinelle")
            for c in a.serie.cat.categories:
                s = texte_de(c, True)
                if s in gardees:
                    ordre.append(s)
                elif s in rares:
                    if sentinelle and sentinelle not in ordre:
                        ordre.append(sentinelle)
            ordre += [v for v in gardees if v not in ordre]
            p["categories"] = ordre
            p["ordonne"] = bool(a.serie.cat.ordered)
            if categories_numeriques:
                p["categories_type"] = categories_numeriques
        if a.textes is not None and g == "discret":
            p["numerique_texte"] = True
        sequence = getattr(a, "params_sequence", None)
        if sequence is not None:
            gardees = [cle_valeur(v) for v, _ in freq]
            ordre = [v for v in sequence[0] if v in gardees]
            if len(ordre) >= 3:
                p["sequence"] = ordre + [v for v in gardees if v not in ordre]
                if sequence[2] is not None:
                    p["sequence_date"] = sequence[2]
                obligatoires = [[v, round(float(sequence[3].get(v, 0)), 3)] for v in ordre if sequence[3].get(v, 0) >= 0.9]
                if obligatoires:
                    p["obligatoires"] = obligatoires
                if sequence[1] > 0:
                    a.exceptions["sequence"] = sequence[1]
                a.notes.append("ordre des modalités respecté au fil des lignes d'un même individu")
    elif g == "booleen":
        vals = [bool(v) for v in a.valeurs_valides()]
        p["p_vrai"] = round(sum(vals) / len(vals), 6) if vals else 0.5
        if vals and 0 < sum(vals) < len(vals):
            tableau = pd.DataFrame({"v": vals, "e": ent_comp})
            par = tableau.groupby("v")["e"].nunique().to_dict()
            if min(par.get(True, 0), par.get(False, 0)) < seuil:
                p["p_vrai"] = 0.97 if par.get(True, 0) >= par.get(False, 0) else 0.03
                a.notes.append("modalité rare : fréquence fictive")
            p["deux_valeurs"] = True
    elif g in GENRES_DATES:
        secondes = preparer_dates(a)
        sec_valides = secondes[valides]
        ok = ~np.isnan(sec_valides)
        hors = dates_speciales(sec_valides, ent_comp, seuil)
        normales = np.where(hors, np.nan, sec_valides)
        if hors.any():
            sentinelles = []
            for v in np.unique(sec_valides[hors]):
                try:
                    iso = (EPOQUE + dt.timedelta(seconds=float(v))).date().isoformat()
                except (OverflowError, ValueError):
                    iso = ""
                sel = hors & (sec_valides == v)
                porteurs = len(set(ent_comp[sel].tolist()))
                if porteurs >= seuil:
                    sentinelles.append([float(v), round(float(sel.sum() / max(1, ok.sum())), 6)])
                elif iso in DATES_SENTINELLES:
                    sentinelles.append([float(v), 0.01])
            if sentinelles:
                p["speciales"] = sentinelles
                a.notes.append("dates conventionnelles (ex. " + ", ".join(date_courte(v) for v, _ in sentinelles[:3]) + ") reproduites à part")
            if len(sentinelles) < len(np.unique(sec_valides[hors])):
                a.notes.append("dates hors norme rares non reproduites")
        m_norm = ~np.isnan(normales)
        ent_norm = ent_comp[m_norm]
        p.update(quantiles_surs(normales[m_norm], seuil, len(set(ent_norm.tolist())), poids_entites(ent_norm), dates=True))
        ok_norm = normales[m_norm]
        heures = np.mod(ok_norm, 86400)
        p["heure"] = bool((heures != 0).any())
        p["resolution"] = "seconde" if (np.mod(ok_norm, 60) != 0).any() else ("minute" if p["heure"] else "jour")
        if a.textes is not None:
            vals = [x for x in a.textes if x is not None]
            nan_par_valeur = np.isnan(sec_valides)
            jetons = [v for v, s in zip(vals, nan_par_valeur) if s]
            if jetons:
                ent_j = [e for e, s in zip(ent_comp, nan_par_valeur) if s]
                res = frequences_sures(jetons, ent_j, seuil)
                freq, a_sentinelle = modalites_sures(res, seuil, SENTINELLE_VALEUR)
                part = len(jetons) / len(vals)
                p["jetons"] = [[v, round(q * part, 6)] for v, q in freq]
                if res["autres"]:
                    a.notes.append(f"valeurs textuelles rares (moins de {seuil} individus) remplacées" + (f" par « {SENTINELLE_VALEUR} »" if a_sentinelle else ""))
                if a_sentinelle:
                    p["sentinelle"] = SENTINELLE_VALEUR
                garantir(p, list(res["generiques"]) + ([SENTINELLE_VALEUR] if a_sentinelle else []))
            if a.format_date and "%z" in a.format_date:
                decalages = Counter(m.group(0) for v in vals for m in [re.search(r"[+-]\d{2}:?\d{2}$|Z$", v)] if m)
                if decalages:
                    p["fuseau"] = decalages.most_common(1)[0][0]
        p["format"] = a.format_date
        if a.format_date and "%b" in a.format_date:
            exemples = [t for t in a.textes if t][:50]
            p["majuscules"] = sum(t.isupper() for t in exemples) >= 0.8 * len(exemples)
        if a.stockage == "datetime":
            tz = getattr(a.serie.dt, "tz", None)
            p["tz"] = str(tz) if tz is not None else None
            p["unite"] = str(a.serie.dtype)
    elif g == "heure":
        secondes = preparer_dates(a)[valides]
        m = ~np.isnan(secondes)
        p.update(quantiles_surs(secondes[m], seuil, len(set(ent_comp[m].tolist())), poids_entites(ent_comp[m])))
        p["resolution"] = "seconde" if (np.mod(secondes[m], 60) != 0).any() else "minute"
        p["format"] = a.format_date or ("%H:%M:%S" if p["resolution"] == "seconde" else "%H:%M")
    elif g == "texte_libre":
        longueurs = np.array([len(str(v)) for v in a.valeurs_valides()], dtype=float)
        p.update(quantiles_surs(longueurs, seuil, n_eff, poids))
    elif g == "constante":
        v = a.valeurs_valides()[0]
        v = v.item() if isinstance(v, np.generic) else v
        if n_eff < seuil and not getattr(a, "constante_sure", False):
            if isinstance(v, bool):
                v = True
            elif isinstance(v, int):
                v = int(arrondi_significatif(v, 1))
            elif isinstance(v, float):
                v = float(arrondi_significatif(v, 1))
            elif isinstance(v, str) and est_nombre_texte(v):
                arrondi = arrondi_significatif(vers_float(v), 1)
                v = (str(int(arrondi)) if float(arrondi).is_integer() else str(arrondi)).replace(".", "," if "," in v else ".")
            elif isinstance(v, (pd.Timestamp, dt.datetime)):
                v = type(v)(v.year // 10 * 10, 1, 1) if isinstance(v, dt.datetime) else pd.Timestamp(v.year // 10 * 10, 1, 1)
            elif isinstance(v, dt.date):
                v = dt.date(v.year // 10 * 10, 1, 1)
            else:
                v = "VALEUR"
            a.notes.append(f"valeur présente chez moins de {seuil} individus : remplacée")
        p["valeur"] = v
    elif g in ("nom", "prenom"):
        exemples = [str(v) for v in a.valeurs_valides()[:200]]
        maj = sum(e.isupper() for e in exemples)
        minu = sum(e.islower() for e in exemples)
        p["casse"] = "majuscules" if maj >= 0.8 * len(exemples) else ("minuscules" if minu >= 0.8 * len(exemples) else "titre")
        p["mots"] = int(np.median([len(e.split()) for e in exemples])) if exemples else 1
    elif g == "adresse":
        exemples = [str(v) for v in a.valeurs_valides()[:200]]
        p["avec_cp"] = sum(bool(re.search(r"\b\d{5}\b", e)) for e in exemples) >= 0.5 * len(exemples)
    if a.rang_par is not None:
        p["rang"] = a.rang_par[1]
    if a.unique_par is not None:
        p["unique_par_entite"] = True
    if a.taux_manquants > 0:
        p["au_moins_un_manquant"] = True
        if a.jetons_manquants and len(a.jetons_manquants) > 1:
            p["jetons_manquants"] = a.jetons_manquants
        if a.bloc_initial >= 20 and a.taux_manquants < 0.95 and a.bloc_initial < a.n:
            p["bloc_initial"] = int(arrondi_significatif(a.bloc_initial, 2))
            a.notes.append("bloc de valeurs manquantes en tête de colonne (attention à la détection automatique des types)")
    if a.exceptions:
        p["exceptions"] = dict(a.exceptions)


def max_lignes_par_entite(entites):
    if entites is None:
        return 1
    e = np.asarray(entites)
    e = e[e >= 0]
    if len(e) == 0:
        return 1
    return int(np.bincount(e).max())


def nombre_court(v):
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def date_courte(secondes):
    try:
        return (EPOQUE + dt.timedelta(seconds=float(secondes))).date().isoformat()
    except (OverflowError, ValueError):
        return "date hors norme"


def niveaux_repetes(a, x, ent_x, entites, seuil):
    reelles = ent_x < (entites.max() + 1 if len(entites) and entites.max() >= 0 else 0)
    if reelles.sum() < 10:
        return
    tableau = pd.DataFrame({"e": ent_x[reelles], "x": x[reelles]})
    groupes = tableau.groupby("e")["x"]
    moyennes = groupes.mean()
    tailles = groupes.size()
    if len(moyennes) < 2 * seuil or int((tailles >= 2).sum()) < 5:
        return
    residus = tableau["x"].to_numpy() - moyennes.loc[tableau["e"]].to_numpy()
    multiples = tableau["e"].map(tailles).to_numpy() >= 2
    ddl = int((tailles[tailles >= 2] - 1).sum())
    if ddl <= 0:
        return
    intra = float(np.sqrt(np.sum(residus[multiples] ** 2) / ddl))
    total = float(np.std(tableau["x"].to_numpy()))
    if total <= 0 or intra >= 0.8 * total:
        return
    a.params["niveau"] = quantiles_surs(moyennes.to_numpy(), seuil, len(moyennes))
    a.params["bruit"] = arrondi_significatif(intra, 2)


def cle_attribut(a):
    g = a.genre
    base = colle(a.jetons)
    if g in ("categorie", "discret", "code_postal", "ville"):
        labels = tuple(sorted(str(v) for v, _ in a.params.get("modalites") or []))
        return f"{base}|{g}|{SEP_CLE.join(labels)}" if labels else None
    if g in ("booleen", "date", "date_naissance", "numerique"):
        return f"{base}|{g}"
    return None


def preference_ancre(jetons):
    for rang, ensemble in enumerate(PREFERENCES_ANCRE):
        if a_indice(jetons, ensemble):
            return len(PREFERENCES_ANCRE) - rang
    return 0


def masque_speciales(a):
    secondes = preparer_dates(a)
    speciales = a.params.get("speciales") or []
    masque = np.zeros(len(secondes), dtype=bool)
    for v, _ in speciales:
        masque |= secondes == v
    masque |= (secondes < SEC_MIN) | (secondes > SEC_MAX)
    return masque


def modeles_croises(par_table, structures, seuil):
    ensembles_tables = []
    for liste in par_table:
        ensembles_tables.append([valeurs_cles(a) for a in liste if a.genre in ("identifiant", "nir")])
    for i, (liste, s) in enumerate(zip(par_table, structures)):
        k = s["entite"]
        if k is None:
            autres = [e for t, ens in enumerate(ensembles_tables) if t != i for e in ens]
            uniques = [a for a in liste if a.genre in ("identifiant", "nir") and a.n_valides >= 2
                       and len(valeurs_cles(a)) == a.n_valides]
            uniques.sort(key=lambda a: (-recouvrement(valeurs_cles(a), autres), 0 if nom_patient(a.jetons) else 1))
            k = uniques[0] if uniques else None
            if k is not None and len(uniques) > 1 and recouvrement(valeurs_cles(k), autres) == 0:
                patients = [a for a in uniques if nom_patient(a.jetons)]
                k = patients[0] if patients else k
        s["cle_individu"] = k
        s["espace"] = None
        s["ancre"] = None
        s["sans_individu"] = k is None and s["type_entite"] == "aucune" and liste and liste[0].n >= 2
    indices = [i for i, s in enumerate(structures) if s["cle_individu"] is not None]
    ensembles = {i: valeurs_cles(structures[i]["cle_individu"]) for i in indices}
    parent = {i: i for i in indices}

    def racine(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for x in indices:
        for y in indices:
            if x >= y:
                continue
            petit = min(len(ensembles[x]), len(ensembles[y]))
            if petit >= 5 and len(ensembles[x] & ensembles[y]) >= 0.8 * petit:
                parent[racine(x)] = racine(y)
    for i in indices:
        structures[i]["espace"] = racine(i)
    espaces = {}
    for i in indices:
        espaces.setdefault(structures[i]["espace"], []).append(i)
    for espace, membres in espaces.items():
        meilleur = None
        for i in membres:
            s = structures[i]
            if s["entite"] is not None:
                continue
            for a in par_table[i]:
                if a.genre != "date" or a.n_valides < 0.5 * a.n or a.n_valides < max(2 * seuil, 20):
                    continue
                score = (preference_ancre(a.jetons), a.n_valides)
                if meilleur is None or score > meilleur[0]:
                    meilleur = (score, i, a)
        if meilleur is None:
            continue
        _, i_ancre, ancre = meilleur
        structures[i_ancre]["ancre"] = ancre
        cles_ancre = structures[i_ancre]["cle_individu"].cles()
        secondes_ancre = np.where(masque_speciales(ancre), np.nan, preparer_dates(ancre))
        carte = {}
        for k, sec in zip(cles_ancre, secondes_ancre):
            if k is not None and not np.isnan(sec):
                carte.setdefault(k, sec)
        for i in membres:
            s = structures[i]
            cles = s["cle_individu"].cles()
            codes = codes_entite(s["cle_individu"])
            for a in par_table[i]:
                if a.genre != "date" or a is ancre:
                    continue
                d = np.where(masque_speciales(a), np.nan, preparer_dates(a))
                ancres = np.array([carte.get(k, np.nan) if k is not None else np.nan for k in cles], dtype=float)
                valides_d = ~np.isnan(d)
                ok = valides_d & ~np.isnan(ancres)
                if ok.sum() < max(2 * seuil, 20) or ok.sum() < 0.5 * valides_d.sum():
                    continue
                delta = (d - ancres)[ok]
                ents = entites_completes(codes, len(codes))[ok]
                zero = delta == 0
                tableau = pd.DataFrame({"e": ents, "d": delta})
                premier = np.zeros(len(delta), dtype=bool)
                premier[tableau.groupby("e")["d"].idxmin().to_numpy()] = True
                p0, p0_premier = 0.0, 0.0
                if zero.any():
                    w = poids_entites(ents)
                    if len(set(ents[zero & premier].tolist())) >= seuil:
                        p0_premier = float(np.sum(zero & premier) / np.sum(premier))
                    autres = ~premier
                    if autres.any() and len(set(ents[zero & autres].tolist())) >= seuil:
                        p0 = float(np.sum(w[zero & autres]) / np.sum(w[autres]))
                    elif not autres.any():
                        p0 = p0_premier
                reste = ~zero if (p0 > 0 or p0_premier > 0) else np.ones(len(delta), dtype=bool)
                if reste.sum() == 0:
                    modele = {"vide": True}
                else:
                    ent_reste = ents[reste]
                    modele = quantiles_surs(delta[reste], seuil, len(set(ent_reste.tolist())), poids_entites(ent_reste))
                modele["p0"] = round(p0, 6)
                modele["p0_premier"] = round(p0_premier, 6)
                modele["espace"] = espace
                a.params["delai"] = modele
                if p0 >= 0.999 and p0_premier >= 0.999:
                    a.notes.append(f"identique à `{ancre.nom}` ({ancre.table.nom_affiche}) pour un même individu")
                else:
                    a.notes.append(f"délai par rapport à `{ancre.nom}` ({ancre.table.nom_affiche}) respecté pour un même individu")
    groupes = {}
    for i in indices:
        s = structures[i]
        for a in par_table[i]:
            if "delai" in a.params or a is s.get("ancre"):
                continue
            par_individu = (s["entite"] is not None and a.constant_par is s["entite"]) or (s["entite"] is None)
            if not par_individu:
                continue
            cle = cle_attribut(a)
            if cle is None:
                continue
            groupes.setdefault((s["espace"], cle), []).append((i, a))
    for (espace, cle), membres in groupes.items():
        if len({i for i, _ in membres}) < 2:
            continue
        for i, a in membres:
            a.partage = f"{espace}|{cle}"
            autres = sorted({par_table[k][0].table.nom_affiche for k, _ in membres if k != i})
            a.notes.append("même valeur pour un même individu que dans " + ", ".join(autres))


GENRES_LIENS = {"identifiant", "nir", "code", "date", "date_naissance", "discret", "heure", "constante", "categorie",
                "numerique", "telephone"}
GENRES_LIENS_CLES = {"identifiant", "nir", "code", "date", "date_naissance", "discret", "heure", "telephone"}


def detecter_liens(par_table):
    liens = [[] for _ in par_table]
    for i, enfant in enumerate(par_table):
        noms_enfant = {a.nom: a for a in enfant if a.genre in GENRES_LIENS}
        for k, parent in enumerate(par_table):
            if k == i:
                continue
            noms_parent = {a.nom: a for a in parent if a.genre in GENRES_LIENS}
            communs = [n for n in noms_enfant if n in noms_parent]
            if not communs or all(noms_enfant[n].genre in GENRES_MAPPES and noms_parent[n].genre in GENRES_MAPPES for n in communs):
                continue
            if not any(noms_enfant[n].genre in ("identifiant", "nir", "code", "date") for n in communs):
                continue
            essais = [communs, [n for n in communs if noms_enfant[n].genre in GENRES_LIENS_CLES and noms_parent[n].genre in GENRES_LIENS_CLES]]
            for jeu in essais:
                if not jeu or all(noms_enfant[n].genre in GENRES_MAPPES for n in jeu):
                    continue
                source = set(cle_tuple(v) for v in zip(*[noms_parent[n].cles() for n in jeu]))
                source.discard(None)
                cible = set(cle_tuple(v) for v in zip(*[noms_enfant[n].cles() for n in jeu]))
                cible.discard(None)
                if len(cible) < 5 or len(cible & source) < 0.95 * len(cible):
                    continue
                if len(jeu) == 1 and len(source) < 20:
                    continue
                liens[i].append((k, list(jeu)))
                break
    for i in range(len(liens)):
        liens[i] = [(k, jeu) for k, jeu in liens[i] if not any(i2 == i for i2, _ in liens[k]) or k < i]
    return liens


def constantes_globales(par_table, seuil):
    vues = {}
    for liste in par_table:
        for a in liste:
            if a.genre != "constante":
                continue
            v = a.valeurs_valides()[0]
            cle = (colle(a.jetons), cle_valeur(v))
            vues.setdefault(cle, set()).add(a.table.fichier)
    for liste in par_table:
        for a in liste:
            if a.genre == "constante":
                v = a.valeurs_valides()[0]
                a.constante_sure = len(vues.get((colle(a.jetons), cle_valeur(v)), ())) >= seuil


def profiler(tables, seuil=11, garder=(), cles_individu=()):
    garder = set(garder)
    analyses = []
    par_table = []
    for t in tables:
        liste = []
        for j in range(len(t.noms)):
            a = Analyse(t, j)
            a.genre = classer(a, garder)
            if a.nom in garder and a.genre == "code":
                a.genre = "categorie"
            liste.append(a)
            analyses.append(a)
        par_table.append(liste)
    propager_identifiants(analyses, garder)
    ensembles_tables = [[valeurs_cles(a) for a in liste if a.genre in ("identifiant", "nir")] for liste in par_table]
    structures = []
    for i, liste in enumerate(par_table):
        autres = [e for t, ens in enumerate(ensembles_tables) if t != i for e in ens]
        entite, type_entite = choisir_entite(liste, seuil, cles_individu, autres)
        structures.append({"entite": entite, "type_entite": type_entite})
    propager_entites(par_table, structures)
    for liste, s in zip(par_table, structures):
        chaine, exceptions = analyser_structure(liste, s["entite"], seuil)
        s["chaine"] = chaine
        s["chaine_exceptions"] = exceptions
    constantes_globales(par_table, seuil)
    for liste, s in zip(par_table, structures):
        codes = codes_entite(s["entite"]) if s["entite"] is not None else None
        for a in liste:
            parametres(a, seuil, codes)
    modeles_croises(par_table, structures, seuil)
    for s, liens in zip(structures, detecter_liens(par_table)):
        s["liens"] = liens
    retirer_numerotations_de_cles(par_table)
    return par_table, structures


def canonique_cle(v):
    return (v.lstrip("0") or "0") if v.isdigit() else v.lower()


def retirer_numerotations_de_cles(par_table):
    for i, liste in enumerate(par_table):
        for a in liste:
            if a.params.get("numerotation") is None:
                continue
            valeurs = {canonique_cle(v) for v in valeurs_cles(a)}
            autres = [{canonique_cle(v) for v in valeurs_cles(b)} for k, l in enumerate(par_table) if k != i for b in l
                      if b.genre in ("identifiant", "nir", "code", "discret", "numerique")]
            if any(len(valeurs & e) >= 0.5 * min(len(valeurs), len(e)) for e in autres if e):
                del a.params["numerotation"]
                a.notes = [n for n in a.notes if not n.startswith("numérotation des lignes")]


def profil_serialisable(tables, par_table, structures, seuil):
    sortie = {"seuil": seuil, "tables": []}
    for t, liste, s in zip(tables, par_table, structures):
        colonnes = []
        for a in liste:
            colonnes.append({
                "nom": a.nom,
                "stockage": a.stockage,
                "genre": a.genre,
                "taux_manquants": round(a.taux_manquants, 4),
                "jeton_manquant": a.jeton_manquant,
                "jetons_manquants": [v for v, _ in a.jetons_manquants if v is not None],
                "constant_par": None if a.constant_par is None else a.constant_par.nom,
                "chrono_par": None if a.chrono_par is None else a.chrono_par.nom,
                "rang_par": None if a.rang_par is None else a.rang_par[0].nom,
                "unique_par": None if a.unique_par is None else a.unique_par.nom,
                "unique_groupe": None if a.unique_groupe is None else a.unique_groupe.nom,
                "partage": a.partage,
                "params": a.params,
                "notes": a.notes,
            })
        sortie["tables"].append({
            "fichier": t.fichier,
            "feuille": t.feuille,
            "format": t.format,
            "n_lignes": t.n_lignes,
            "entite": None if s["entite"] is None else s["entite"].nom,
            "type_entite": s.get("type_entite"),
            "cle_individu": None if s.get("cle_individu") is None else s["cle_individu"].nom,
            "sans_individu": bool(s.get("sans_individu")),
            "ancre": None if s.get("ancre") is None else s["ancre"].nom,
            "ordre_dates": [a.nom for a in s["chaine"]],
            "exceptions_dates": s.get("chaine_exceptions") or [],
            "colonnes": colonnes,
        })
    return sortie
