import copy
import datetime as dt
import re
import sys
from collections import Counter

import numpy as np
import pandas as pd

from .formats import Table, libelle_suspect
from .identifiants import Faussaire, Remplaceur
from .listes import DOMAINES_EMAIL, LOREM, MOTS_COURANTS, NOMS, NOMS_VOIES, PRENOMS, TYPES_VOIES, VILLES
from .profil import (
    GENRES_DATES, GENRES_MAPPES, GENRES_PERSONNES, RE_NOMBRE, SENTINELLE, SENTINELLE_UNIQUE, SENTINELLE_VALEUR,
    cle_valeur, codes_entite, est_generique, preparer_dates, profil_serialisable, profiler, sans_accents,
)

CODES_POSTAUX_GENERIQUES = ["75011", "69003", "13005", "31000", "44000", "59000", "33000", "67000", "35000", "94000"]
EPOQUE = dt.datetime(1970, 1, 1)
SEC_PLANCHER = (dt.datetime(1, 1, 2) - EPOQUE).total_seconds()
SEC_PLAFOND = (dt.datetime(9999, 12, 31) - EPOQUE).total_seconds()
GENRES_TEMPS = GENRES_DATES | {"heure"}
MASQUE = SENTINELLE


def tirer_continu(params, n, rng):
    if params.get("vide") or n == 0:
        return np.full(n, np.nan)
    if "quantiles" in params:
        qs = np.array([q for q, _ in params["quantiles"]], dtype=float)
        vs = np.array([v for _, v in params["quantiles"]], dtype=float)
        u = rng.uniform(qs[0], qs[-1], n)
        return np.interp(u, qs, vs)
    if "centre" in params:
        c = float(params["centre"])
        d = float(params.get("dispersion", 1.0)) or 1.0
        x = rng.uniform(c - d, c + d, n)
    else:
        m = float(params.get("moyenne", 0.0))
        s = float(params.get("ecart_type", 1.0)) or 1.0
        x = np.clip(rng.normal(m, s, n), m - 2 * s, m + 2 * s)
    if params.get("positif"):
        x = np.abs(x)
    return x


def bornes(params):
    if "quantiles" in params:
        return params["quantiles"][0][1], params["quantiles"][-1][1]
    if "centre" in params:
        return params["centre"] - params["dispersion"], params["centre"] + params["dispersion"]
    if "moyenne" in params:
        return params["moyenne"] - 2 * params["ecart_type"], params["moyenne"] + 2 * params["ecart_type"]
    return -np.inf, np.inf


def arrondir(x, params):
    d = params.get("decimales")
    if params.get("entier") or d == 0:
        return np.round(x)
    if d is None:
        return x
    return np.round(x, d)


def tirer_modalites(params, n, rng, genre, entier_stockage):
    if params.get("repli_numerique"):
        x = tirer_continu(params["repli_numerique"], n, rng)
        if params.get("repli_entier"):
            return [int(round(v)) for v in x]
        return [float(v) for v in x]
    modalites = params.get("modalites") or []
    if params.get("generique") or not modalites:
        if genre == "code_postal":
            choix = CODES_POSTAUX_GENERIQUES
            if entier_stockage:
                choix = [int(c) for c in choix]
        elif genre == "ville":
            choix = VILLES
        else:
            m = max(2, min(int(params.get("n_uniques", 3)), 5))
            choix = [f"MODALITE_RARE_{i + 1}" for i in range(m)]
            if entier_stockage or params.get("categories_type"):
                choix = list(range(1, m + 1))
        idx = rng.integers(len(choix), size=n)
        return [choix[i] for i in idx]
    labels = [v for v, _ in modalites]
    poids = np.array([p for _, p in modalites], dtype=float)
    poids = poids / poids.sum()
    idx = rng.choice(len(labels), size=n, p=poids)
    return [labels[i] for i in idx]


def texte_lorem(longueur, rng):
    longueur = max(1, int(longueur))
    depart = int(rng.integers(len(LOREM)))
    mots = []
    total = 0
    k = depart
    while total < longueur:
        mot = LOREM[k % len(LOREM)]
        mots.append(mot)
        total += len(mot) + 1
        k += 1
    texte = " ".join(mots)[:longueur].rstrip()
    return (texte[:1].upper() + texte[1:]) if texte else "Lorem"


def superposer_jetons(params, n, rng):
    if not params.get("jetons") or n == 0:
        return None
    labels = [v for v, _ in params["jetons"]]
    poids = np.array([p for _, p in params["jetons"]], dtype=float)
    total = float(poids.sum())
    if total <= 0:
        return None
    jetons = [None] * n
    u = rng.random(n)
    choix = rng.choice(len(labels), size=n, p=poids / total)
    for i in np.where(u < total)[0]:
        jetons[i] = labels[choix[i]]
    return jetons


def superposer_speciales(x, params, rng):
    speciales = params.get("speciales")
    if not speciales or len(x) == 0:
        return x
    valeurs = np.array([v for v, _ in speciales], dtype=float)
    poids = np.array([p for _, p in speciales], dtype=float)
    total = float(poids.sum())
    x = np.array(x, dtype=float)
    u = rng.random(len(x))
    choix = rng.choice(len(valeurs), size=len(x), p=poids / total)
    m = u < min(total, 0.9)
    x[m] = valeurs[choix[m]]
    return x


def arrondir_temps(x, params, genre):
    x = np.clip(np.asarray(x, dtype=float), SEC_PLANCHER, SEC_PLAFOND)
    if genre == "heure":
        x = np.mod(x, 86400)
        return np.round(x / 60) * 60 if params.get("resolution") == "minute" else np.round(x)
    if not params.get("heure"):
        return np.floor(x / 86400) * 86400
    if params.get("resolution") == "minute":
        return np.round(x / 60) * 60
    return np.round(x)


def tirer(genre, params, n, rng, stockage, speciales=True):
    if genre == "numerique":
        x = arrondir(tirer_continu(params, n, rng), params)
        if speciales:
            x = superposer_speciales(x, params, rng)
        return x, superposer_jetons(params, n, rng)
    if genre in ("discret", "categorie", "code_postal", "ville"):
        return tirer_modalites(params, n, rng, genre, stockage in ("entier", "decimal")), None
    if genre == "booleen":
        valeurs = list(rng.random(n) < float(params.get("p_vrai", 0.5)))
        if params.get("deux_valeurs") and n >= 2 and len(set(valeurs)) < 2:
            valeurs[int(rng.integers(n))] = not valeurs[0]
        return valeurs, None
    if genre in GENRES_DATES:
        x = arrondir_temps(tirer_continu(params, n, rng), params, genre)
        if speciales:
            x = superposer_speciales(x, params, rng)
        return x, superposer_jetons(params, n, rng)
    if genre == "heure":
        return arrondir_temps(tirer_continu(params, n, rng), params, genre), None
    if genre == "texte_libre":
        longueurs = tirer_continu(params, n, rng)
        return [texte_lorem(l if np.isfinite(l) else 20, rng) for l in longueurs], None
    if genre == "constante":
        return [params.get("valeur")] * n, None
    if genre == "binaire":
        return [bytes(rng.integers(0, 256, 16, dtype=np.uint8)) for _ in range(n)], None
    return [None] * n, None


def grouper_milliers(entier, separateur):
    signe = "-" if entier.startswith("-") else ""
    chiffres = entier.lstrip("-+")
    if not chiffres.isdigit():
        return entier
    return signe + f"{int(chiffres):,}".replace(",", separateur)


def formater_nombre(x, params):
    if not np.isfinite(x):
        return "NA" if np.isnan(x) else ("Inf" if x > 0 else "-Inf")
    if params.get("scientifique") is not None:
        s = f"{x:.{int(params['scientifique'])}e}"
        if params.get("majuscule_e"):
            s = s.upper()
    else:
        d = params.get("decimales")
        if params.get("entier") or d == 0:
            s = str(int(round(x)))
        elif d is None or d > 10:
            s = format(float(x), ".15g")
        elif params.get("decimales_fixes"):
            s = f"{x:.{d}f}"
        else:
            s = f"{x:.{d}f}".rstrip("0").rstrip(".")
        if params.get("milliers"):
            entier, point, fraction = s.partition(".")
            s = grouper_milliers(entier, params["milliers"]) + (point + fraction if point else "")
    if params.get("decimale") == ",":
        s = s.replace(".", ",")
    return s


def secondes_vers_datetime(s):
    s = min(max(float(s), SEC_PLANCHER), SEC_PLAFOND)
    return EPOQUE + dt.timedelta(seconds=s)


def fuseau_fixe(texte):
    if not texte or texte == "Z":
        return dt.timezone.utc
    m = re.match(r"([+-])(\d{2}):?(\d{2})", texte)
    if not m:
        return dt.timezone.utc
    delta = dt.timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
    return dt.timezone(delta if m.group(1) == "+" else -delta)


def formater_texte(v, genre, params):
    if genre == "numerique":
        return formater_nombre(float(v), params)
    if genre == "heure":
        moment = dt.datetime(2000, 1, 1) + dt.timedelta(seconds=float(v) % 86400)
        return moment.strftime(params.get("format") or "%H:%M")
    if genre in GENRES_DATES:
        moment = secondes_vers_datetime(v)
        fmt = params.get("format")
        if not fmt:
            return moment.isoformat(sep=" ") if params.get("heure") else moment.date().isoformat()
        if "%z" in fmt:
            fuseau = params.get("fuseau")
            moment = moment.replace(tzinfo=dt.timezone.utc).astimezone(fuseau_fixe(fuseau))
            if fuseau and ":" in fuseau and sys.version_info >= (3, 12):
                fmt = fmt.replace("%z", "%:z")
        texte = moment.strftime(fmt)
        return texte.upper() if params.get("majuscules") else texte
    return str(v)


def nombre_si_possible(v):
    if isinstance(v, str) and RE_NOMBRE.match(v):
        f = float(v.replace(",", "."))
        return int(f) if ("." not in v and "," not in v and "e" not in v.lower()) else f
    return v


def absent(v):
    return v is None or (isinstance(v, (float, np.floating)) and np.isnan(v))


def vers_entier(v):
    if isinstance(v, (bool, np.bool_)):
        return int(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, str):
        s = v.strip().replace(",", ".")
        if re.fullmatch(r"[+-]?\d+", s):
            return int(s)
        return int(round(float(s)))
    return int(round(float(v)))


def serie_entiere(sortie, origine):
    for dtype in ("Int64", "UInt64"):
        try:
            serie = pd.Series(sortie, dtype=dtype)
            break
        except (OverflowError, TypeError, ValueError):
            serie = None
    if serie is None:
        return pd.Series(sortie, dtype=object)
    if not serie.isna().any() and pd.api.types.is_integer_dtype(origine.dtype) and not isinstance(origine.dtype, pd.api.extensions.ExtensionDtype):
        try:
            serie = serie.astype(origine.dtype)
        except (OverflowError, TypeError, ValueError):
            pass
    return serie


def vers_nombre_categorie(v, type_cat):
    if v is None:
        return None
    try:
        f = float(str(v).replace(",", "."))
    except ValueError:
        return None
    if type_cat == "entier":
        return int(round(f))
    return f


def vers_serie(col, valeurs, jetons, manquant, origine, manques=None):
    st = col["stockage"]
    g = col["genre"]
    p = col["params"]
    n = len(manquant)
    manquant = np.array([bool(manquant[i]) or absent(valeurs[i]) for i in range(n)], dtype=bool)
    temps = g in GENRES_TEMPS
    if st in ("texte", "mixte"):
        manque = col.get("jeton_manquant") if st == "texte" else None
        sortie = []
        for i in range(n):
            if manquant[i] or valeurs[i] is None:
                sortie.append(manques[i] if manques is not None else manque)
            elif jetons is not None and jetons[i] is not None:
                sortie.append(jetons[i])
            elif st == "mixte" and g in GENRES_DATES:
                sortie.append(secondes_vers_datetime(valeurs[i]))
            elif st == "mixte" and g == "heure":
                sortie.append((dt.datetime(2000, 1, 1) + dt.timedelta(seconds=float(valeurs[i]) % 86400)).time())
            else:
                sortie.append(formater_texte(valeurs[i], g, p))
        if st == "mixte":
            sortie = [nombre_si_possible(v) for v in sortie]
        return pd.Series(sortie, dtype=object)
    if st == "entier":
        sortie = []
        for i in range(n):
            v = valeurs[i]
            if manquant[i] or v is None:
                sortie.append(None)
            elif g in GENRES_DATES and p.get("format"):
                sortie.append(int(secondes_vers_datetime(v).strftime(p["format"])))
            else:
                try:
                    sortie.append(vers_entier(v))
                except (TypeError, ValueError):
                    sortie.append(None)
        return serie_entiere(sortie, origine)
    if st == "decimal":
        sortie = []
        for i in range(n):
            v = valeurs[i]
            if manquant[i] or v is None:
                sortie.append(np.nan)
            elif g in GENRES_DATES and p.get("format"):
                sortie.append(float(secondes_vers_datetime(v).strftime(p["format"])))
            else:
                try:
                    sortie.append(float(str(v).replace(",", ".")) if isinstance(v, str) else float(v))
                except (TypeError, ValueError):
                    sortie.append(np.nan)
        serie = pd.Series(sortie, dtype="float64")
        if g == "numerique" and p.get("decimales") is not None:
            serie = serie.round(p["decimales"])
        if origine.dtype == np.float32:
            serie = serie.astype("float32")
        return serie
    if st == "booleen":
        sortie = [None if (manquant[i] or valeurs[i] is None) else bool(valeurs[i] in (True, "True", "TRUE", 1)) for i in range(n)]
        serie = pd.Series(sortie, dtype="boolean")
        if not serie.isna().any() and origine.dtype == bool:
            serie = serie.astype(bool)
        return serie
    if st == "duree":
        sortie = [None if (manquant[i] or valeurs[i] is None) else pd.Timedelta(seconds=float(valeurs[i])) for i in range(n)]
        if pd.api.types.is_timedelta64_dtype(origine.dtype):
            return pd.Series(pd.to_timedelta(pd.Series(sortie, dtype=object)), dtype=origine.dtype)
        return pd.Series([None if v is None else v.to_pytimedelta() for v in sortie], dtype=object)
    if st == "binaire":
        return pd.Series([None if manquant[i] else valeurs[i] for i in range(n)], dtype=object)
    if st in ("datetime", "date", "heure") and not temps:
        return pd.Series([None if manquant[i] else valeurs[i] for i in range(n)], dtype=object)
    if st == "datetime":
        micro = np.array([np.datetime64("NaT") if (manquant[i] or valeurs[i] is None)
                          else np.datetime64(int(round(float(np.clip(valeurs[i], SEC_PLANCHER, SEC_PLAFOND)) * 1e6)), "us")
                          for i in range(n)], dtype="datetime64[us]")
        serie = pd.Series(micro)
        tz = p.get("tz")
        if tz:
            try:
                serie = serie.dt.tz_localize("UTC").dt.tz_convert(tz)
            except Exception:
                pass
        try:
            serie = serie.astype(origine.dtype)
        except (TypeError, ValueError, OverflowError):
            pass
        return serie
    if st == "date":
        sortie = [None if (manquant[i] or valeurs[i] is None) else secondes_vers_datetime(valeurs[i]).date() for i in range(n)]
        return pd.Series(sortie, dtype=object)
    if st == "heure":
        sortie = [None if (manquant[i] or valeurs[i] is None)
                  else (dt.datetime(2000, 1, 1) + dt.timedelta(seconds=float(valeurs[i]) % 86400)).time() for i in range(n)]
        return pd.Series(sortie, dtype=object)
    if st == "categorie":
        type_cat = p.get("categories_type")
        if type_cat:
            labels = [None if (manquant[i] or valeurs[i] is None) else vers_nombre_categorie(valeurs[i], type_cat) for i in range(n)]
            categories = [vers_nombre_categorie(c, type_cat) for c in p.get("categories") or []]
            categories = [c for c in dict.fromkeys(categories) if c is not None]
            for v in labels:
                if v is not None and v not in categories:
                    categories.append(v)
            return pd.Series(pd.Categorical(labels, categories=categories, ordered=bool(p.get("ordonne"))))
        labels = [None if (manquant[i] or valeurs[i] is None) else str(valeurs[i]) for i in range(n)]
        categories = list(dict.fromkeys(p.get("categories") or []))
        connues = set(categories)
        for v in labels:
            if v is not None and v not in connues:
                connues.add(v)
                categories.append(v)
        return pd.Series(pd.Categorical(labels, categories=categories, ordered=bool(p.get("ordonne"))))
    return pd.Series([None if manquant[i] else valeurs[i] for i in range(n)], dtype=object)


def index_groupes(codes):
    codes = np.asarray(codes)
    if len(codes) == 0:
        return {}
    ordre = np.argsort(codes, kind="stable")
    tries = codes[ordre]
    debuts = np.flatnonzero(np.r_[True, tries[1:] != tries[:-1]])
    fins = np.r_[debuts[1:], len(tries)]
    return {int(tries[d]): ordre[d:f] for d, f in zip(debuts, fins) if tries[d] >= 0}


def entites_choisies(groupes, taux, rng):
    multiples = [e for e, lignes in groupes.items() if len(lignes) >= 2]
    if not multiples or not taux:
        return []
    k = min(len(multiples), max(1, int(round(float(taux) * len(multiples)))))
    return [multiples[i] for i in rng.choice(len(multiples), size=k, replace=False)]


def trier_par_entite(valeurs, codes):
    v = np.array(valeurs, dtype=float)
    masque = (codes >= 0) & ~np.isnan(v)
    idx = np.where(masque)[0]
    if len(idx) == 0:
        return v
    g = codes[idx]
    vv = v[idx]
    ordre_positions = np.lexsort((idx, g))
    ordre_valeurs = np.lexsort((vv, g))
    v[idx[ordre_positions]] = vv[ordre_valeurs]
    return v


def rangs_par_entite(codes, base):
    serie = pd.Series(codes)
    rangs = serie.groupby(serie).cumcount().to_numpy() + base
    return rangs


def tirer_sans_remise(params, codes, rng, stockage, genre):
    modalites = params.get("modalites") or []
    n = len(codes)
    if not modalites:
        return tirer_modalites(params, n, rng, genre, stockage in ("entier", "decimal"))
    labels = [v for v, _ in modalites]
    poids = np.array([p for _, p in modalites], dtype=float)
    poids = poids / poids.sum()
    sortie = [None] * n
    for code, lignes in index_groupes(codes).items():
        k = len(lignes)
        sans = min(k, int((poids > 0).sum()))
        choix = list(rng.choice(len(labels), size=sans, replace=False, p=poids))
        if k > sans:
            choix += list(rng.choice(len(labels), size=k - sans, p=poids))
        for i, c in zip(lignes, choix):
            sortie[i] = labels[c]
    for i in np.where(np.asarray(codes) < 0)[0]:
        sortie[i] = labels[int(rng.choice(len(labels), p=poids))]
    return sortie


def manquants_aleatoires(taux, n, rng, codes):
    if taux <= 0:
        return np.zeros(n, dtype=bool)
    if codes is None:
        return rng.random(n) < taux
    m = int(codes.max()) + 1 if len(codes) and codes.max() >= 0 else 0
    tirage = rng.random(m) < taux
    libres = rng.random(n) < taux
    return np.array([bool(tirage[c]) if c >= 0 else bool(libres[i]) for i, c in enumerate(codes)], dtype=bool)


def appliquer_exceptions(j, a, p, g, valeurs, codes_de, groupes_de, rng):
    exceptions = p.get("exceptions") or {}
    if not exceptions:
        return
    vals = valeurs[j]
    if "constant" in exceptions and a.constant_par is not None:
        groupes = groupes_de(a.constant_par)
        for e in entites_choisies(groupes, exceptions["constant"], rng):
            lignes = groupes[e]
            ligne = int(lignes[-1])
            for _ in range(5):
                nouveau, _ = tirer(g, p, 1, rng, a.stockage)
                v = list(nouveau)[0]
                if cle_valeur(v) != cle_valeur(vals[ligne]):
                    vals[ligne] = v
                    break
    if "unique" in exceptions and a.unique_par is not None:
        groupes = groupes_de(a.unique_par)
        for e in entites_choisies(groupes, exceptions["unique"], rng):
            lignes = groupes[e]
            vals[int(lignes[1])] = vals[int(lignes[0])]
    if "rang" in exceptions and a.rang_par is not None:
        groupes = groupes_de(a.rang_par[0])
        for e in entites_choisies(groupes, exceptions["rang"], rng):
            lignes = groupes[e]
            vals[int(lignes[-1])] = vals[int(lignes[-2])]


def echanger_dans_entites(vals, groupes, taux, rng, premier=0, dernier=-1):
    for e in entites_choisies(groupes, taux, rng):
        lignes = groupes[e]
        x, y = int(lignes[premier]), int(lignes[dernier])
        vals[x], vals[y] = vals[y], vals[x]


def ordonner_sequence(vals, groupes, ordre, positions, obligatoires=(), labels=None, rng=None):
    rang = {s: k for k, s in enumerate(ordre)}
    fin = len(ordre)
    exiges = {c: q for c, q in obligatoires if labels and c in labels}
    for lignes in groupes.values():
        if len(lignes) < 1:
            continue
        presentes = [int(r) for r in lignes if vals[int(r)] is not None]
        if not presentes:
            continue
        etiquettes = [vals[r] for r in presentes]
        if exiges and rng is not None:
            cles = [cle_valeur(v) for v in etiquettes]
            for c, q in exiges.items():
                if c in cles or rng.random() >= q:
                    continue
                remplacables = [k for k, x in enumerate(cles) if x not in exiges]
                if not remplacables:
                    break
                k = remplacables[int(rng.integers(len(remplacables)))]
                etiquettes[k] = labels[c]
                cles[k] = c
        if len(presentes) < 2:
            vals[presentes[0]] = etiquettes[0]
            continue
        etiquettes = sorted(etiquettes, key=lambda v: rang.get(cle_valeur(v), fin))
        if positions is not None:
            presentes = sorted(presentes, key=lambda r: (np.inf if np.isnan(positions[r]) else positions[r], r))
        for r, v in zip(presentes, etiquettes):
            vals[r] = v


def meme_jour(x, codes, reelles):
    if codes is None or reelles is None:
        return x
    m = (codes >= 0) & ~np.isnan(reelles)
    if m.sum() < 2:
        return x
    idx = np.where(m)[0]
    tableau = pd.DataFrame({"e": codes[idx], "s": reelles[idx], "i": idx})
    premiers = tableau.groupby(["e", "s"], sort=False)["i"].transform("first").to_numpy()
    if np.array_equal(premiers, idx):
        return x
    x = np.array(x, dtype=float)
    x[idx] = x[premiers]
    return x


def codes_paires(codes, secondes):
    sortie = np.full(len(codes), -1)
    m = (np.asarray(codes) >= 0) & ~np.isnan(secondes)
    if m.any():
        f, _ = pd.factorize(pd.MultiIndex.from_arrays([np.asarray(codes)[m], secondes[m]]))
        sortie[m] = f
    return sortie


def cles_tuples(analyses, noms):
    par_nom = {a.nom: a for a in analyses}
    from .profil import cle_tuple
    return [cle_tuple(v) for v in zip(*[par_nom[n].cles() for n in noms])]


def copier_depuis_parents(liens, analyses, valeurs, jetons, manquants, caches):
    index = {a.nom: j for j, a in enumerate(analyses)}
    for k, jeu in liens:
        carte = caches["liens"].get((k, tuple(jeu)))
        if not carte:
            continue
        tuples = cles_tuples(analyses, jeu)
        colonnes = [index[n] for n in jeu]
        for r, t in enumerate(tuples):
            if t is None or t not in carte:
                continue
            for j, (v, jet, manque) in zip(colonnes, carte[t]):
                valeurs[j][r] = v
                if jetons[j] is not None:
                    jetons[j][r] = jet
                elif jet is not None:
                    jetons[j] = [None] * len(valeurs[j])
                    jetons[j][r] = jet
                manquants[j][r] = manque


def memoriser_pour_enfants(indice, analyses, valeurs, jetons, manquants, caches):
    index = {a.nom: j for j, a in enumerate(analyses)}
    for jeu in caches["parents_requis"].get(indice, ()):
        tuples = cles_tuples(analyses, jeu)
        colonnes = [index[n] for n in jeu]
        carte = {}
        for r, t in enumerate(tuples):
            if t is None:
                continue
            if t in carte:
                for j, (v, jet, manque) in zip(colonnes, carte[t]):
                    valeurs[j][r] = v
                    if jetons[j] is not None:
                        jetons[j][r] = jet
                    manquants[j][r] = manque
                continue
            carte[t] = [(valeurs[j][r], None if jetons[j] is None else jetons[j][r], bool(manquants[j][r])) for j in colonnes]
        caches["liens"][(indice, tuple(jeu))] = carte


def colonne_de_tri(analyses):
    for j, a in enumerate(analyses):
        if a.genre in ("vide", "constante", "texte_libre", "booleen", "binaire", "nom", "prenom", "email", "adresse") or a.n_valides < 10:
            continue
        if a.genre in GENRES_DATES or a.genre == "heure":
            v = preparer_dates(a)
            v = v[~np.isnan(v)]
        elif a.stockage in ("entier", "decimal") and a.genre not in GENRES_MAPPES:
            v = np.array([float(x) for x in a.valeurs_valides()], dtype=float)
        else:
            cles = [c for c in a.cles() if c is not None]
            if a.stockage in ("entier", "decimal"):
                try:
                    v = np.array([float(c) for c in cles], dtype=float)
                except ValueError:
                    continue
            else:
                v = np.array(cles, dtype=object)
        if len(v) < 10:
            continue
        try:
            croissant = v[1:] >= v[:-1]
            distinct = v[1:] != v[:-1]
        except TypeError:
            continue
        if float(np.mean(croissant)) >= 0.99 and int(np.sum(distinct)) >= 2:
            return j
    return None


def cle_de_tri(valeurs, manquants, numerique):
    n = len(manquants)
    if numerique:
        cle = np.full(n, np.inf)
        for i in range(n):
            v = valeurs[i]
            if not manquants[i] and v is not None:
                try:
                    cle[i] = float(v)
                except (TypeError, ValueError):
                    pass
        return cle
    return np.array(["\U0010ffff" if (manquants[i] or valeurs[i] is None) else str(valeurs[i]) for i in range(n)], dtype=object)


def permutation(n, codes, rng, seuil, tri):
    if codes is None:
        blocs = [np.array([i]) for i in range(n)]
        plafond = None
    else:
        groupes = index_groupes(codes)
        seuls = [np.array([i]) for i in np.where(np.asarray(codes) < 0)[0]]
        tailles = sorted((len(v) for v in groupes.values()), reverse=True)
        plafond = tailles[seuil - 1] if len(tailles) >= seuil and tailles[0] > tailles[seuil - 1] else None
        blocs = [lignes[:plafond] if plafond else lignes for lignes in groupes.values()] + seuls
    if not blocs:
        return np.arange(0), plafond
    ordre = rng.permutation(len(blocs))
    perm = np.concatenate([blocs[k] for k in ordre]).astype(int)
    if tri is not None:
        perm = perm[np.argsort(tri[perm], kind="stable")]
    return perm, plafond


def lignes_du_groupe(codes, i):
    if codes is None or codes[i] < 0:
        return [i]
    return [int(k) for k in np.where(codes == codes[i])[0]]


def garantir_valeurs(valeurs, jetons, manquants, a, p, rng, codes):
    n = len(manquants)
    if n < 2 or a.partage is not None:
        return valeurs, jetons, manquants
    garantis = list(p.get("garantis") or [])
    cles_jetons = {v for v, _ in p.get("jetons") or []}
    presentes = {cle_valeur(v) for v, m in zip(valeurs, manquants) if not m and v is not None}
    if jetons is not None:
        presentes |= {cle_valeur(v) for v in jetons if v is not None}
    pris = set()
    for v in garantis:
        if cle_valeur(v) in presentes:
            continue
        libres = [i for i in range(n) if not manquants[i] and i not in pris]
        if not libres:
            libres = [i for i in range(n) if i not in pris]
            if not libres:
                break
        i = libres[int(rng.integers(len(libres)))]
        lignes = lignes_du_groupe(codes, i)
        if v in cles_jetons and a.genre not in ("categorie", "discret"):
            jetons = list(jetons) if jetons is not None else [None] * n
            for k in lignes:
                jetons[k] = v
        else:
            valeurs = list(valeurs)
            for k in lignes:
                valeurs[k] = v
                if jetons is not None:
                    jetons[k] = None
        manquants = manquants.copy()
        for k in lignes:
            manquants[k] = False
            pris.add(k)
        presentes.add(cle_valeur(v))
    if p.get("singleton") and a.constant_par is None and n >= 3:
        libres = [i for i in range(n) if not manquants[i] and i not in pris]
        if libres:
            valeurs = list(valeurs)
            valeurs[libres[int(rng.integers(len(libres)))]] = p["singleton"]
    if p.get("au_moins_un_manquant") and not manquants.any():
        i = int(rng.integers(n))
        manquants = manquants.copy()
        for k in lignes_du_groupe(codes, i):
            manquants[k] = True
    return valeurs, jetons, manquants


def tirer_manques(col, manquants, rng):
    jetons = col["params"].get("jetons_manquants")
    if not jetons or col["stockage"] not in ("texte", "mixte"):
        return None
    labels = [v for v, _ in jetons]
    poids = np.array([q for _, q in jetons], dtype=float)
    poids = poids / poids.sum()
    sortie = [None] * len(manquants)
    lignes = np.where(manquants)[0]
    if len(lignes) == 0:
        return None
    choix = rng.choice(len(labels), size=len(lignes), p=poids)
    for i, c in zip(lignes, choix):
        sortie[i] = labels[c]
    if len(lignes) >= len(labels):
        vus = {sortie[k] for k in lignes}
        melange = rng.permutation(lignes)
        for i, v in zip(melange, [x for x in labels if x not in vus]):
            sortie[i] = v
    return sortie


def jetons_sensibles(par_table, seuil=11):
    jetons = set()
    for liste in par_table:
        for a in liste:
            if a.genre in ("nom", "prenom", "identifiant", "nir", "email", "adresse"):
                comptes = Counter()
                for c in set(x for x in a.cles() if x is not None):
                    plie = sans_accents(c).casefold()
                    comptes.update(set(m for m in re.findall(r"[a-z0-9]+", plie)
                                       if (len(m) >= 4 and not m.isdigit()) or (m.isdigit() and len(m) >= 5)))
                jetons |= {m for m, n in comptes.items() if n < seuil}
    return frozenset(jetons)


def mots_de(texte):
    return re.findall(r"[a-z0-9]+", sans_accents(str(texte)).casefold())


def jetons_publics(tables, profil):
    publics = set()
    for liste in (NOMS, PRENOMS, VILLES, NOMS_VOIES, TYPES_VOIES, DOMAINES_EMAIL, LOREM):
        for v in liste:
            publics |= set(mots_de(v))
    publics |= set(mots_de(SENTINELLE)) | set(mots_de(SENTINELLE_VALEUR)) | set(mots_de(SENTINELLE_UNIQUE))
    publics |= set(MOTS_COURANTS)
    for t, tp in zip(tables, profil["tables"]):
        publics |= set(mots_de(t.fichier))
        if t.feuille:
            publics |= set(mots_de(t.feuille))
        for col in tp["colonnes"]:
            publics |= set(mots_de(col["nom"]))
            if col["genre"] in ("categorie", "discret", "ville", "code_postal"):
                for v, _ in col["params"].get("modalites") or []:
                    publics |= set(mots_de(v))
    return publics


def suspect(valeur, sensibles):
    if not isinstance(valeur, str) or not sensibles:
        return False
    return any((not m.isdigit()) and m in sensibles for m in mots_de(valeur))


def proteger_table(t, colonnes, sensibles):
    trouvees = []
    if not sensibles:
        return trouvees
    for j, col in enumerate(colonnes):
        if col["genre"] in GENRES_MAPPES | GENRES_PERSONNES:
            continue
        serie = t.donnees[j]
        if isinstance(serie.dtype, pd.CategoricalDtype):
            categories = list(serie.cat.categories)
            if not any(suspect(c, sensibles) for c in categories):
                continue
            nouvelles = list(dict.fromkeys(MASQUE if suspect(c, sensibles) else c for c in categories))
            valeurs = [None if pd.isna(v) else (MASQUE if suspect(v, sensibles) else v) for v in serie.astype(object).tolist()]
            t.donnees[j] = pd.Series(pd.Categorical(valeurs, categories=nouvelles, ordered=serie.cat.ordered))
            trouvees.append(col["nom"])
        elif serie.dtype == object:
            valeurs = serie.tolist()
            suspects = {v for v in set(x for x in valeurs if isinstance(x, str)) if suspect(v, sensibles)}
            if suspects:
                t.donnees[j] = pd.Series([MASQUE if (isinstance(v, str) and v in suspects) else v for v in valeurs], dtype=object)
                trouvees.append(col["nom"])
    return trouvees


def masquer_texte(texte, sensibles):
    if not sensibles:
        return texte

    def remplacer(m):
        return "[masqué]" if suspect(m.group(0), sensibles) else m.group(0)
    return re.sub(r"[\w@.+\-']+", remplacer, texte)


def filtrer_etiquettes(etiquettes, colonnes, sensibles=frozenset()):
    filtrees = {}
    par_nom = {c["nom"]: c for c in colonnes}
    for nom, labels in etiquettes.items():
        col = par_nom.get(nom)
        if col is None or not labels:
            continue
        g = col["genre"]
        if g in GENRES_MAPPES | GENRES_PERSONNES | {"texte_libre", "vide"}:
            continue
        if g == "constante":
            gardees = {cle_valeur(col["params"].get("valeur"))}
        else:
            gardees = {cle_valeur(v) for v, _ in col["params"].get("modalites") or []}
            gardees |= {cle_valeur(v) for v, _ in col["params"].get("speciales") or []}
        propres = {k: v for k, v in labels.items()
                   if (cle_valeur(k) in gardees or (g == "numerique" and est_generique(v))) and not libelle_suspect(v, sensibles)}
        if propres:
            filtrees[nom] = propres
    return filtrees


def generer_table(table, analyses, structure, colonnes, remplaceur, faussaire, rng, caches, sensibles, seuil, indice=None):
    n = table.n_lignes
    memo = {}
    memo_groupes = {}

    def codes_de(a):
        if id(a) not in memo:
            memo[id(a)] = codes_entite(a)
        return memo[id(a)]

    def groupes_de(a):
        if id(a) not in memo_groupes:
            memo_groupes[id(a)] = index_groupes(codes_de(a))
        return memo_groupes[id(a)]

    cle_ind = structure.get("cle_individu")
    cles_ind = cle_ind.cles() if cle_ind is not None else None
    espace = structure.get("espace")
    entite = structure.get("entite")
    remap = None
    if cles_ind is not None and espace is not None and espace in caches["permutations"] and cle_ind in analyses:
        distinctes = {k for k in cles_ind if k is not None}
        if 0 < len(distinctes) < seuil and len(caches["pools"][espace]) >= 2 * seuil:
            remap = caches["permutations"][espace]
            cles_ind = [None if k is None else remap.get(k, k) for k in cles_ind]
    codes_lignes = codes_de(entite) if entite is not None else (codes_de(cle_ind) if cle_ind is not None else None)
    valeurs, jetons, manquants = {}, {}, {}
    ancre = structure.get("ancre")
    ordre = list(range(len(analyses)))
    if ancre is not None:
        ordre.remove(analyses.index(ancre))
        ordre.insert(0, analyses.index(ancre))
    for j in ordre:
        a, col = analyses[j], colonnes[j]
        g = col["genre"]
        p = col["params"]
        if g in GENRES_MAPPES:
            cles = a.cles()
            bruts = a.textes_bruts
            sources = [None if c is None else remap.get(c, c) for c in cles] if (remap is not None and a is cle_ind) else cles
            sortie = []
            for i, c in enumerate(sources):
                if c is None:
                    sortie.append(None)
                    continue
                f = remplaceur(c)
                if bruts is not None and bruts[i] is not None:
                    b = bruts[i]
                    f = b[:len(b) - len(b.lstrip())] + f + b[len(b.rstrip()):]
                sortie.append(f)
            valeurs[j] = sortie
            if g == "telephone":
                manquants[j] = manquants_aleatoires(a.taux_manquants, n, rng, codes_lignes)
                remplis = [v for v in valeurs[j] if v is not None]
                if remplis:
                    valeurs[j] = [v if v is not None else remplis[int(rng.integers(len(remplis)))] for v in valeurs[j]]
            else:
                manquants[j] = a.manquant.copy()
            jetons[j] = None
            continue
        if g in GENRES_PERSONNES:
            cles = a.cles()
            manquants[j] = manquants_aleatoires(a.taux_manquants, n, rng, codes_lignes)
            sortie = []
            for i, c in enumerate(cles):
                if c is None:
                    code = int(codes_lignes[i]) if codes_lignes is not None and codes_lignes[i] >= 0 else -1 - i
                    c = f"\x00{code}"
                sortie.append(faussaire.generer(g, c, p))
            valeurs[j] = sortie
            jetons[j] = None
            continue
        if g == "vide":
            valeurs[j] = [None] * n
            manquants[j] = np.ones(n, dtype=bool)
            jetons[j] = None
            continue
        taux = col["taux_manquants"]
        if a.constant_par is not None:
            manquants[j] = manquants_aleatoires(taux, n, rng, codes_de(a.constant_par))
        else:
            manquants[j] = rng.random(n) < taux
        delai = p.get("delai")
        avec_delai = bool(delai) and g in GENRES_DATES and cles_ind is not None and espace in caches["ancres"]
        if a.partage is not None and cles_ind is not None:
            cache = caches["partages"].setdefault(a.partage, {})
            nouvelles = sorted({k for k in cles_ind if k is not None and k not in cache})
            if nouvelles:
                tires, _ = tirer(g, p, len(nouvelles), rng, a.stockage)
                for k, v in zip(nouvelles, list(tires)):
                    cache[k] = v
            sans_cle = [i for i, k in enumerate(cles_ind) if k is None]
            supplement, _ = tirer(g, p, len(sans_cle), rng, a.stockage)
            liste = [cache.get(k) for k in cles_ind]
            for i, v in zip(sans_cle, list(supplement)):
                liste[i] = v
            valeurs[j] = liste
            jetons[j] = None
        elif a.constant_par is not None:
            codes = codes_de(a.constant_par)
            m = int(codes.max()) + 1 if len(codes) and codes.max() >= 0 else 0
            base, base_jetons = tirer(g, p, m, rng, a.stockage)
            libres, _ = tirer(g, p, n, rng, a.stockage)
            base, libres = list(base), list(libres)
            valeurs[j] = [base[c] if c >= 0 else libres[i] for i, c in enumerate(codes)]
            jetons[j] = None if base_jetons is None else [base_jetons[c] if c >= 0 else None for c in codes]
        elif a.rang_par is not None:
            codes = codes_de(a.rang_par[0])
            rangs = rangs_par_entite(codes, int(p.get("rang", 1)))
            libres, _ = tirer(g, p, n, rng, a.stockage)
            libres = list(libres)
            valeurs[j] = [int(rangs[i]) if codes[i] >= 0 else libres[i] for i in range(n)]
            jetons[j] = None
        elif a.unique_par is not None:
            valeurs[j] = tirer_sans_remise(p, codes_de(a.unique_par), rng, a.stockage, g)
            jetons[j] = None
        elif a.unique_groupe is not None and entite is not None:
            valeurs[j] = tirer_sans_remise(p, codes_paires(codes_de(entite), preparer_dates(a.unique_groupe)), rng, a.stockage, g)
            jetons[j] = None
        elif g == "numerique" and "niveau" in p and entite is not None:
            codes = codes_de(entite)
            m = int(codes.max()) + 1 if len(codes) and codes.max() >= 0 else 0
            niveaux = tirer_continu(p["niveau"], m, rng)
            bruit = rng.normal(0, float(p.get("bruit") or 0), n)
            libres = tirer_continu(p, n, rng)
            x = np.array([niveaux[c] + bruit[i] if c >= 0 else libres[i] for i, c in enumerate(codes)], dtype=float)
            bas, haut = bornes(p)
            x = np.clip(x, bas, haut)
            valeurs[j] = list(superposer_speciales(arrondir(x, p), p, rng))
            jetons[j] = superposer_jetons(p, n, rng)
        else:
            vals, jets = tirer(g, p, n, rng, a.stockage, speciales=not avec_delai)
            valeurs[j] = list(vals) if not isinstance(vals, list) else vals
            jetons[j] = jets
        if avec_delai:
            carte = caches["ancres"][espace]
            ancres = np.array([carte.get(k, np.nan) if k is not None else np.nan for k in cles_ind], dtype=float)
            dispo = ~np.isnan(ancres)
            if dispo.any():
                delais = tirer_continu(delai, n, rng)
                delais = np.where(np.isnan(delais), 0.0, delais)
                delais[rng.random(n) < float(delai.get("p0", 0))] = 0.0
                p0_premier = float(delai.get("p0_premier", 0))
                if p0_premier > 0 and codes_lignes is not None:
                    codes_ind = codes_de(cle_ind)
                    tableau = pd.DataFrame({"e": codes_ind, "d": delais})[dispo & (codes_ind >= 0)]
                    if len(tableau):
                        premiers = tableau.groupby("e")["d"].idxmin().to_numpy()
                        choisis = premiers[rng.random(len(premiers)) < p0_premier]
                        delais[choisis] = 0.0
                x = np.array([np.nan if v is None else v for v in valeurs[j]], dtype=float)
                bas, haut = bornes(p)
                x[dispo] = np.clip(ancres[dispo] + delais[dispo], bas, haut)
                valeurs[j] = list(arrondir_temps(x, p, g))
            valeurs[j] = list(superposer_speciales(np.array(valeurs[j], dtype=float), p, rng))
        if a is ancre and cles_ind is not None and espace is not None:
            carte = caches["ancres"].setdefault(espace, {})
            speciales = {v for v, _ in p.get("speciales") or []}
            for k, v, manque in zip(cles_ind, valeurs[j], manquants[j]):
                if k is not None and not manque and v is not None and not np.isnan(v) and v not in speciales:
                    carte.setdefault(k, float(v))
        appliquer_exceptions(j, a, p, g, valeurs, codes_de, groupes_de, rng)
    for j, a in enumerate(analyses):
        p = colonnes[j]["params"]
        if a.chrono_par is not None and colonnes[j]["genre"] in GENRES_DATES:
            v = np.array([np.nan if (manquants[j][i] or valeurs[j][i] is None) else valeurs[j][i] for i in range(n)], dtype=float)
            v = trier_par_entite(v, codes_de(a.chrono_par))
            taux = (p.get("exceptions") or {}).get("chrono")
            if taux:
                v = list(v)
                echanger_dans_entites(v, groupes_de(a.chrono_par), taux, rng)
            valeurs[j] = list(v)
    noms = {a.nom: k for k, a in enumerate(analyses)}
    for j, a in enumerate(analyses):
        p = colonnes[j]["params"]
        if p.get("sequence") and codes_lignes is not None and entite is not None:
            positions = None
            ref = p.get("sequence_date")
            if ref is not None and ref in noms:
                k = noms[ref]
                positions = np.array([np.nan if (manquants[k][i] or valeurs[k][i] is None) else float(valeurs[k][i]) for i in range(n)], dtype=float)
            vals = list(valeurs[j])
            etiquettes = {cle_valeur(v): v for v, _ in p.get("modalites") or []}
            ordonner_sequence(vals, groupes_de(entite), p["sequence"], positions, p.get("obligatoires") or (), etiquettes, rng)
            taux = (p.get("exceptions") or {}).get("sequence")
            if taux:
                echanger_dans_entites(vals, groupes_de(entite), taux, rng, 0, 1)
            taux_unique = (p.get("exceptions") or {}).get("unique")
            if taux_unique and a.unique_par is not None:
                groupes = groupes_de(a.unique_par)
                for e in entites_choisies(groupes, taux_unique, rng):
                    lignes = groupes[e]
                    vals[int(lignes[1])] = vals[int(lignes[0])]
            valeurs[j] = vals
    if codes_lignes is not None:
        for j, a in enumerate(analyses):
            if colonnes[j]["genre"] in GENRES_DATES and a.constant_par is None and a is not ancre:
                reelles = preparer_dates(a)
                x = np.array([np.nan if v is None else v for v in valeurs[j]], dtype=float)
                valeurs[j] = list(meme_jour(x, codes_lignes, reelles))
    chaine = [analyses.index(a) for a in structure["chaine"]]
    exceptions_chaine = structure.get("chaine_exceptions") or []
    for _ in range(2):
        for x, y in zip(chaine[:-1], chaine[1:]):
            a_ = np.array([np.nan if v is None else v for v in valeurs[x]], dtype=float)
            b_ = np.array([np.nan if v is None else v for v in valeurs[y]], dtype=float)
            m = ~manquants[x] & ~manquants[y] & ~np.isnan(a_) & ~np.isnan(b_) & (b_ < a_)
            if not m.any():
                continue
            x_fixe = analyses[x].constant_par is not None or analyses[x] is ancre or "delai" in colonnes[x]["params"]
            if analyses[y] is ancre or (analyses[y].constant_par is not None and not x_fixe):
                a_[m] = b_[m] - (a_[m] - b_[m])
                valeurs[x] = list(a_)
            else:
                b_[m] = a_[m] + (a_[m] - b_[m])
                valeurs[y] = list(b_)
    for k, (x, y) in enumerate(zip(chaine[:-1], chaine[1:])):
        taux = exceptions_chaine[k] if k < len(exceptions_chaine) else 0
        if not taux:
            continue
        a_ = np.array([np.nan if v is None else v for v in valeurs[x]], dtype=float)
        b_ = np.array([np.nan if v is None else v for v in valeurs[y]], dtype=float)
        lignes = np.where(~manquants[x] & ~manquants[y] & ~np.isnan(a_) & ~np.isnan(b_) & (a_ < b_))[0]
        if len(lignes):
            choisies = rng.choice(lignes, size=min(len(lignes), max(1, int(round(taux * len(lignes))))), replace=False)
            a_[choisies], b_[choisies] = b_[choisies], a_[choisies].copy()
            valeurs[x], valeurs[y] = list(a_), list(b_)
    for j in range(len(analyses)):
        manquants[j] = np.array(manquants[j], dtype=bool)
        valeurs[j] = list(valeurs[j])
        if jetons[j] is not None:
            jetons[j] = list(jetons[j])
    copier_depuis_parents(structure.get("liens") or [], analyses, valeurs, jetons, manquants, caches)
    if indice is not None:
        memoriser_pour_enfants(indice, analyses, valeurs, jetons, manquants, caches)
    j_tri = colonne_de_tri(analyses)
    tri = None
    if j_tri is not None:
        col_tri = colonnes[j_tri]
        numerique = col_tri["genre"] in GENRES_TEMPS or col_tri["stockage"] in ("entier", "decimal")
        tri = cle_de_tri(valeurs[j_tri], manquants[j_tri], numerique)
    perm, plafond = permutation(n, codes_lignes, rng, seuil, tri)
    n_final = len(perm)
    groupes_finaux = {}
    for j in range(len(analyses)):
        valeurs[j] = [valeurs[j][int(i)] for i in perm]
        jetons[j] = None if jetons[j] is None else [jetons[j][int(i)] for i in perm]
        manquants[j] = np.asarray(manquants[j])[perm]
    series = {}
    for j, (a, col) in enumerate(zip(analyses, colonnes)):
        p = col["params"]
        codes_fin = None
        if a.constant_par is not None:
            cle = id(a.constant_par)
            if cle not in groupes_finaux:
                groupes_finaux[cle] = codes_de(a.constant_par)[perm]
            codes_fin = groupes_finaux[cle]
        if col["genre"] not in GENRES_MAPPES | GENRES_PERSONNES | {"vide"}:
            valeurs[j], jetons[j], manquants[j] = garantir_valeurs(valeurs[j], jetons[j], manquants[j], a, p, rng, codes_fin)
        if p.get("numerotation") is not None:
            base = int(p["numerotation"])
            valeurs[j] = [str(base + i) for i in range(n_final)]
            manquants[j] = np.zeros(n_final, dtype=bool)
            jetons[j] = None
        if p.get("bloc_initial"):
            k = min(int(p["bloc_initial"]), n_final - 1)
            if k > 0:
                manquants[j] = manquants[j].copy()
                manquants[j][:k] = True
        manques = tirer_manques(col, manquants[j], rng)
        origine = table.donnees[j]
        series[j] = vers_serie(col, valeurs[j], jetons[j], manquants[j], origine, manques)
    donnees = pd.DataFrame(series) if series else pd.DataFrame(index=range(n_final))
    options = copy.copy(table.options)
    if options.get("etiquettes"):
        options["etiquettes"] = filtrer_etiquettes(options["etiquettes"], colonnes, sensibles)
    if options.get("labels"):
        options["labels"] = {k: v for k, v in options["labels"].items() if not libelle_suspect(v, sensibles)}
    if options.get("noms_vecteur"):
        noms_vecteur = options["noms_vecteur"]
        if len(noms_vecteur) != n or any(libelle_suspect(x, sensibles) or re.search(r"\d{4,}", str(x)) for x in noms_vecteur):
            options["noms_vecteur"] = []
    if options.get("classes_r"):
        par_nom = {c["nom"]: c for c in colonnes}
        propres = {}
        for nom, meta in options["classes_r"].items():
            meta = dict(meta)
            meta["niveaux"] = []
            col = par_nom.get(nom)
            gardees = set()
            if col is not None:
                gardees = {cle_valeur(v) for v, _ in col["params"].get("modalites") or []}
                gardees |= {cle_valeur(v) for v, _ in col["params"].get("speciales") or []}
            meta["etiquettes"] = [[v, l] for v, l in meta.get("etiquettes") or []
                                  if cle_valeur(str(v)) in gardees and not libelle_suspect(l, sensibles)]
            if meta.get("libelle") and libelle_suspect(meta["libelle"], sensibles):
                meta["libelle"] = ""
            propres[nom] = meta
        options["classes_r"] = propres
    numeriques = []
    for j, col in enumerate(colonnes):
        if col["stockage"] != "texte":
            continue
        vus = [v for v in donnees[j].tolist() if v not in (None, "", col.get("jeton_manquant")) and v not in (col.get("jetons_manquants") or [])]
        if vus and all(isinstance(v, str) and RE_NOMBRE.match(v) for v in vus):
            numeriques.append(j)
    options["colonnes_numeriques"] = numeriques
    if plafond:
        options["lignes_plafonnees"] = plafond
    return Table(table.fichier, table.feuille, table.format, list(table.noms), donnees, list(table.stockages), options)


def ordre_generation(structures):
    n = len(structures)
    parents = {i: {k for k, _ in (structures[i].get("liens") or []) if k != i} for i in range(n)}
    restants = set(range(n))
    ordre = []
    while restants:
        prets = [i for i in restants if not (parents[i] & restants)]
        if not prets:
            prets = list(restants)
        prets.sort(key=lambda i: (0 if structures[i].get("ancre") is not None else 1, i))
        i = prets[0]
        ordre.append(i)
        restants.discard(i)
    return ordre


def fabriquer_sosie(tables, seuil=11, graine=None, garder=(), cles_individu=(), controle=None):
    rng = np.random.default_rng(graine)
    utiles = [t for t in tables if not t.options.get("vide")]
    par_table, structures = profiler(utiles, seuil, garder, cles_individu)
    profil = profil_serialisable(utiles, par_table, structures, seuil)
    remplaceur = Remplaceur(rng, seuil)
    for liste in par_table:
        for a in liste:
            if a.genre in GENRES_MAPPES:
                remplaceur.ajouter(a.cles())
    remplaceur.construire()
    faussaire = Faussaire(rng)
    caches = {"ancres": {}, "partages": {}, "pools": {}, "permutations": {}, "liens": {}, "parents_requis": {}}
    for s in structures:
        for k, jeu in s.get("liens") or []:
            caches["parents_requis"].setdefault(k, [])
            if list(jeu) not in caches["parents_requis"][k]:
                caches["parents_requis"][k].append(list(jeu))
    for liste, s in zip(par_table, structures):
        cle = s.get("cle_individu")
        if cle is not None and s.get("espace") is not None and cle in liste and cle.genre in GENRES_MAPPES:
            caches["pools"].setdefault(s["espace"], set()).update(k for k in cle.cles() if k is not None)
    for espace, pool in caches["pools"].items():
        cles = sorted(pool)
        caches["pools"][espace] = cles
        melange = [cles[i] for i in rng.permutation(len(cles))]
        caches["permutations"][espace] = dict(zip(cles, melange))
    sensibles_noms = jetons_sensibles(par_table, seuil)
    publics = jetons_publics(utiles, profil)
    sensibles = frozenset(m for m in sensibles_noms if m not in publics and not m.isdigit())
    ordre = ordre_generation(structures)
    generees = {}
    masques = []
    for i in ordre:
        t = utiles[i]
        sosie = generer_table(t, par_table[i], structures[i], profil["tables"][i]["colonnes"],
                              remplaceur, faussaire, rng, caches, sensibles_noms, seuil, i)
        for nom in proteger_table(sosie, profil["tables"][i]["colonnes"], sensibles):
            masques.append(f"{t.nom_affiche} → {nom}")
        generees[id(t)] = sosie
    sorties = [generees.get(id(t), t) for t in tables]
    if controle is not None:
        controle["sensibles"] = sensibles
        controle["masques"] = masques
    return sorties, profil
