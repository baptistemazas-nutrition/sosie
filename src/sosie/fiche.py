import datetime as dt

import pandas as pd

import re

from .formats import NOMS_FORMATS, destination_de, est_manquant
from .profil import GENRES_MAPPES, SENTINELLE, SENTINELLE_VALEUR, cles_liees, vers_float

NA_PANDAS = {"", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan", "1.#IND", "1.#QNAN", "<NA>", "N/A",
             "NA", "NULL", "NaN", "None", "n/a", "nan", "null"}


def chaine_r(texte):
    return '"' + str(texte).replace("\\", "\\\\").replace('"', '\\"') + '"'


def chaine_py(texte):
    return '"' + str(texte).replace("\\", "\\\\").replace('"', '\\"') + '"'


def nom_r(texte):
    t = str(texte)
    if re.fullmatch(r"[A-Za-z.][A-Za-z0-9._]*", t) and not re.match(r"\.\d", t):
        return t
    return "`" + t.replace("`", "\\`") + "`"


def jetons_manquants(table):
    jetons = []
    for c in table.options.get("_colonnes", []):
        for v in c.get("jetons_manquants") or ([c["jeton_manquant"]] if c.get("jeton_manquant") else []):
            if v is not None and v not in jetons:
                jetons.append(v)
    return jetons


def nombre_lisible(v):
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


NATURES = {
    "identifiant": "identifiant / clé (valeurs fictives)",
    "nir": "n° de sécurité sociale (fictif)",
    "code": "code à forte cardinalité (valeurs remplacées)",
    "telephone": "téléphone (fictif)",
    "nom": "nom de personne (fictif)",
    "prenom": "prénom (fictif)",
    "email": "e-mail (fictif)",
    "adresse": "adresse (fictive)",
    "code_postal": "code postal",
    "ville": "ville / commune",
    "numerique": "numérique continu",
    "discret": "numérique discret",
    "categorie": "catégorie",
    "booleen": "logique (vrai/faux)",
    "date": "date",
    "date_naissance": "date de naissance",
    "heure": "heure",
    "texte_libre": "texte libre (remplacé par du faux texte)",
    "constante": "constante",
    "binaire": "binaire (octets fictifs)",
    "vide": "vide",
}

TYPES = {
    "texte": "texte", "mixte": "mixte (nombres + texte)", "entier": "entier", "decimal": "décimal",
    "booleen": "logique", "datetime": "date-heure", "date": "date", "categorie": "facteur / catégorie", "heure": "heure",
    "duree": "durée", "binaire": "binaire",
}

ENCODAGES_R = {"utf-8": "UTF-8", "utf-8-sig": "UTF-8-BOM", "cp1252": "windows-1252", "latin-1": "latin1",
               "utf-16": "UTF-16", "utf-16-le": "UTF-16LE", "utf-16-be": "UTF-16BE", "mac_roman": "macintosh"}
ENCODAGES_PY = {"mac_roman": "mac_roman"}


def echapper(texte):
    return str(texte).replace("|", "\\|").replace("\n", " ")


def court(v, longueur=30):
    s = str(v)
    return s if len(s) <= longueur else s[: longueur - 1] + "…"


def apercu(serie, col):
    g = col["genre"]
    exclus = {col.get("jeton_manquant")} | set(col.get("jetons_manquants") or [])
    valeurs = [v for v in serie.tolist() if not est_manquant(v) and v not in exclus]
    if not valeurs:
        return "toutes les valeurs manquantes"
    if col["params"].get("rang") is not None:
        base = int(col["params"]["rang"])
        return f"{base}, {base + 1}, {base + 2}, … (rang pour un même individu)"
    if col["params"].get("numerotation") is not None:
        base = int(col["params"]["numerotation"])
        return f"{base}, {base + 1}, {base + 2}, … (numéro de ligne)"
    if g == "numerique":
        nombres = [v for v in valeurs if not isinstance(v, str)]
        textes = [v for v in valeurs if isinstance(v, str)]
        if textes and not nombres:
            convertis = []
            for v in textes:
                try:
                    convertis.append((vers_float(v), v))
                except ValueError:
                    pass
            if convertis:
                convertis.sort()
                base = f"de {convertis[0][1]} à {convertis[-1][1]}"
            else:
                base = ""
        else:
            base = f"de {nombre_lisible(min(nombres))} à {nombre_lisible(max(nombres))}" if nombres else ""
        jetons = col["params"].get("jetons") or []
        if jetons:
            base += " ; aussi : " + ", ".join(f"« {v} »" for v, _ in jetons)
        return base
    if g in ("discret", "categorie", "booleen", "code_postal", "ville", "constante"):
        distincts = list(dict.fromkeys(valeurs))
        try:
            distincts = sorted(distincts, key=lambda z: (str(type(z)), z))
        except TypeError:
            pass
        montre = ", ".join(court(v, 25) for v in distincts[:10])
        if len(distincts) > 10:
            montre += f" … (+{len(distincts) - 10})"
        return montre
    if g in ("date", "date_naissance", "heure"):
        jetons = [v for v, _ in col["params"].get("jetons") or []]
        suite = (" ; aussi : " + ", ".join(f"« {v} »" for v in jetons)) if jetons else ""
        valeurs = [v for v in valeurs if v not in jetons]
        if not valeurs:
            return suite.lstrip(" ;")
        try:
            if isinstance(valeurs[0], str) and g != "heure":
                fmt = col["params"].get("format")
                dates = pd.to_datetime(pd.Series(valeurs), format=fmt, errors="coerce", utc=bool(fmt and "%z" in fmt)) if fmt else pd.to_datetime(pd.Series(valeurs), errors="coerce")
                ordre = dates.dropna().sort_values()
                if len(ordre):
                    debut = valeurs[int(ordre.index[0])]
                    fin = valeurs[int(ordre.index[-1])]
                    return f"du {debut} au {fin}{suite}"
            return f"du {min(valeurs)} au {max(valeurs)}{suite}"
        except Exception:
            return f"ex. {court(valeurs[0])}"
    if g in GENRES_MAPPES:
        distincts = len(set(map(str, valeurs)))
        unique = " (une valeur par ligne)" if distincts == len(valeurs) else ""
        seuil = col.get("_seuil") or 11
        nombre = f"moins de {seuil}" if distincts < seuil else str(distincts)
        return f"{nombre} valeurs distinctes{unique}, ex. « {court(valeurs[0])} »"
    if g == "texte_libre":
        return "faux texte (lorem ipsum)"
    return f"ex. « {court(valeurs[0])} »"


def lecture(table, rel):
    fmt = destination_de(table.fichier, table.format)[1]
    chemin = f"donnees/{rel}"
    o = table.options
    if fmt == "csv":
        sep = o.get("separateur", ",")
        sep_r = "\\t" if sep == "\t" else sep
        enc = o.get("encodage", "utf-8")
        decimales = {c["params"].get("decimale") for c in o.get("_colonnes", []) if c["genre"] == "numerique"}
        dec = "," if "," in decimales else "."
        saut = len(o.get("preambule", [])) + (1 if o.get("ligne_sep") else 0)
        manques = [""] + [v for v in ["NA"] + jetons_manquants(table) if v != ""]
        manques = list(dict.fromkeys(manques))
        na_r = ", ".join(chaine_r(v) for v in manques)
        r = f'read.csv({chaine_r(chemin)}, sep = "{sep_r}", dec = "{dec}", fileEncoding = "{ENCODAGES_R.get(enc, enc)}", check.names = FALSE, na.strings = c({na_r})'
        py = f'pd.read_csv({chaine_py(chemin)}, sep="{sep_r}", decimal="{dec}", encoding="{ENCODAGES_PY.get(enc, enc)}"'
        extra = [v for v in manques if v not in NA_PANDAS]
        if extra:
            py += ", na_values=[" + ", ".join(chaine_py(v) for v in extra) + "]"
        if saut:
            r += f", skip = {saut}"
            py += f", skiprows={saut}"
        if o.get("sans_entete"):
            r += ", header = FALSE"
            py += ", header=None"
        if o.get("noms_lignes"):
            py += ", index_col=0"
        return r + ")", py + ")"
    if fmt == "xlsx":
        saut = o.get("lignes_titre", 0)
        manques = [v for v in jetons_manquants(table) if v != ""]
        r = f'readxl::read_excel({chaine_r(chemin)}, sheet = {chaine_r(table.feuille)}, guess_max = 100000'
        py = f'pd.read_excel({chaine_py(chemin)}, sheet_name={chaine_py(table.feuille)}'
        if manques:
            r += ", na = c(" + ", ".join(chaine_r(v) for v in [""] + manques) + ")"
            extra = [v for v in manques if v not in NA_PANDAS]
            if extra:
                py += ", na_values=[" + ", ".join(chaine_py(v) for v in extra) + "]"
        if saut:
            r += f", skip = {saut}"
            py += f", skiprows={saut}"
        if o.get("sans_entete"):
            r += ", col_names = FALSE"
            py += ", header=None"
        return r + ")", py + ")"
    c_r, c_py = chaine_r(chemin), chaine_py(chemin)
    if fmt == "parquet":
        return f'arrow::read_parquet({c_r})', f'pd.read_parquet({c_py})'
    if fmt == "feather":
        return f'arrow::read_feather({c_r})', f'pd.read_feather({c_py})'
    if fmt == "sav":
        return f'haven::read_sav({c_r}, user_na = TRUE)', f'pyreadstat.read_sav({c_py}, user_missing=True)[0]'
    if fmt == "dta":
        return f'haven::read_dta({c_r})', f'pyreadstat.read_dta({c_py})[0]'
    if fmt == "xpt":
        return f'haven::read_xpt({c_r})', f'pyreadstat.read_xport({c_py})[0]'
    if fmt == "rds":
        return f'readRDS({c_r})', f'pyreadr.read_r({c_py})[None]'
    if fmt == "rdata":
        objet = nom_r(table.feuille)
        return (f'{objet} <- local({{load({c_r}); {objet}}})',
                f'pyreadr.read_r({c_py})[{chaine_py(table.feuille)}]')
    if fmt == "json":
        return f'jsonlite::fromJSON({c_r})', f'pd.read_json({c_py})'
    if fmt == "jsonl":
        return f'jsonlite::stream_in(file({c_r}))', f'pd.read_json({c_py}, lines=True)'
    if fmt == "sqlite":
        table_sql = '"' + str(table.feuille).replace('"', '""') + '"'
        return (f'DBI::dbReadTable(DBI::dbConnect(RSQLite::SQLite(), {c_r}), {chaine_r(table.feuille)})',
                f'pd.read_sql({chaine_py("SELECT * FROM " + table_sql)}, sqlite3.connect({c_py}))')
    return "", ""


def relations(tables, profil):
    colonnes = []
    for t, tp in zip(tables, profil["tables"]):
        for j, col in enumerate(tp["colonnes"]):
            if col["genre"] in ("identifiant", "nir", "code"):
                valeurs = set(str(v) for v in t.donnees[j].tolist() if not est_manquant(v))
                if valeurs:
                    colonnes.append((f"{t.nom_affiche} → {col['nom']}", valeurs, col["nom"]))
    parent = list(range(len(colonnes)))

    def racine(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(colonnes)):
        for k in range(i + 1, len(colonnes)):
            if cles_liees(colonnes[i][2], colonnes[i][1], colonnes[k][2], colonnes[k][1]):
                parent[racine(i)] = racine(k)
    groupes = {}
    for i in range(len(colonnes)):
        groupes.setdefault(racine(i), []).append(colonnes[i][0])
    return [g for g in groupes.values() if len(g) > 1]


def rediger_fiche(tables, profil, rels_sortie, avertissements, nom_projet, ignores, copies):
    lignes = [
        f"# Fiche du sosie{' — ' + nom_projet if nom_projet else ''}",
        "",
        f"> **Données FICTIVES** générées par `sosie` le {dt.date.today().strftime('%d/%m/%Y')}. "
        "Mêmes fichiers, mêmes colonnes, mêmes formats et mêmes clés de jointure que les vraies données, "
        "mais **aucune ligne réelle** : les valeurs sont tirées au hasard. "
        "Les résultats calculés sur ce sosie n'ont **aucune valeur scientifique**.",
        "",
        f"Seuil des petits effectifs : {profil['seuil']} individus. Les modalités portées par moins de "
        f"{profil['seuil']} individus sont remplacées par « {SENTINELLE} » (catégories) ou « {SENTINELLE_VALEUR} » "
        "(valeurs textuelles dans une colonne de nombres ou de dates) ; les valeurs extrêmes sont rognées.",
        "",
    ]
    rels = relations(tables, profil)
    if rels:
        lignes += ["## Clés de jointure détectées", ""]
        for g in rels:
            lignes.append("- " + " ↔ ".join(f"`{x}`" for x in g))
        lignes.append("")
    actuel = None
    for t, tp, rel in zip(tables, profil["tables"], rels_sortie):
        if rel != actuel:
            actuel = rel
            fmt = destination_de(t.fichier, t.format)[1]
            lignes += [f"## `{rel}`", "", f"Format : {NOMS_FORMATS.get(fmt, fmt)}"]
            if rel != t.fichier:
                lignes.append(f"- Le vrai fichier s'appelle `{t.fichier}` : `sosie executer` le convertit en `{rel}` avant de lancer le script. Lis toujours `{rel}`.")
            if fmt == "csv":
                o = t.options
                sep = {"\t": "tabulation", ";": "point-virgule", ",": "virgule", "|": "barre verticale"}.get(o.get("separateur"), o.get("separateur"))
                fin = {"\r\n": "Windows", "\r": "Mac ancien", "\n": "Unix"}.get(o.get("fin_ligne"), "Unix")
                lignes.append(f"- séparateur : {sep} ; encodage : {o.get('encodage')} ; fins de ligne : {fin}")
                if o.get("preambule"):
                    lignes.append(f"- {len(o['preambule'])} ligne(s) de titre au-dessus de l'en-tête (masquées dans le sosie)")
                if o.get("sans_entete"):
                    lignes.append("- pas de ligne d'en-tête : les colonnes s'appellent V1, V2…")
                if o.get("noms_lignes"):
                    lignes.append("- la première colonne contient des noms de lignes (export `write.table` de R)")
            lignes.append("")
        titre = f"### Feuille / objet « {t.feuille} »" if t.feuille is not None else "### Contenu"
        lignes += [titre, ""]
        t.options["_colonnes"] = tp["colonnes"]
        r, py = lecture(t, rel)
        t.options.pop("_colonnes", None)
        lignes += [f"- {t.n_lignes} lignes × {len(t.noms)} colonnes"]
        if r:
            lignes += [f"- Lecture R : `{r}`", f"- Lecture Python : `{py}`"]
        if tp.get("entite") and tp.get("type_entite") == "secondaire":
            lignes.append(f"- Plusieurs lignes par `{tp['entite']}` ; aucune colonne patient repérée : un même patient peut avoir "
                          "plusieurs valeurs de cette clé (les modalités rares sont jugées par cette clé)")
        elif tp.get("entite") and tp.get("type_entite") == "unique":
            lignes.append("- Un seul individu dans ce fichier : toutes ses valeurs sont remplacées par des valeurs génériques")
        elif tp.get("entite"):
            lignes.append(f"- Plusieurs lignes par `{tp['entite']}` (données longitudinales)")
        if tp.get("sans_individu"):
            lignes.append("- Aucune colonne identifiant le patient repérée : chaque ligne compte comme un individu différent")
        if t.options.get("lignes_plafonnees"):
            lignes.append(f"- Nombre de lignes par individu plafonné à {t.options['lignes_plafonnees']} dans le sosie "
                          "(les individus qui en ont le plus sont tronqués) ; l'ordre des individus est mélangé")
        if tp.get("ordre_dates"):
            nuance = " (à quelques exceptions près, comme dans les vraies données)" if any(tp.get("exceptions_dates") or []) else ""
            lignes.append("- Ordre des dates respecté : " + " ≤ ".join(f"`{n}`" for n in tp["ordre_dates"]) + nuance)
        if t.format == "xlsx" or t.format == "xls":
            if t.options.get("lignes_titre"):
                lignes.append(f"- {t.options['lignes_titre']} ligne(s) au-dessus de l'en-tête (titre masqué dans le sosie)")
        lignes += ["", "| Colonne | Nature | Type | Manquants | Contenu du sosie | Remarques |", "|---|---|---|---|---|---|"]
        etiquettes = t.options.get("etiquettes") or {}
        for j, col in enumerate(tp["colonnes"]):
            col["_seuil"] = profil["seuil"]
            remarques = list(col.get("notes", []))
            exceptions = col["params"].get("exceptions") or {}
            if exceptions.get("rang"):
                remarques = [r + " (quelques trous ou doublons, comme dans les vraies données)" if r.startswith("rang de") else r for r in remarques]
            if col.get("constant_par"):
                remarques.append(f"constante pour un même `{col['constant_par']}`" + (" (à quelques exceptions près)" if exceptions.get("constant") else ""))
            if col.get("chrono_par"):
                remarques.append(f"chronologique pour un même `{col['chrono_par']}`" + (" (à quelques exceptions près)" if exceptions.get("chrono") else ""))
            if col.get("unique_par"):
                remarques.append(f"jamais répétée pour un même `{col['unique_par']}`" + (" (à de rares exceptions près)" if exceptions.get("unique") else ""))
            labels = etiquettes.get(col["nom"]) or {}
            if labels:
                texte = " ; ".join(f"{nombre_lisible(k)} = {v}" for k, v in list(labels.items())[:8])
                remarques.append("étiquettes : " + texte + (" …" if len(labels) > 8 else ""))
            if col["jetons_manquants"] if "jetons_manquants" in col else False:
                remarques.append("manquants écrits " + ", ".join(f"« {v} »" for v in col["jetons_manquants"] if v != ""))
            if col["params"].get("niveau"):
                remarques.append("valeurs propres à chaque individu (niveau + variation)")
            fmt_date = col["params"].get("format")
            if fmt_date:
                remarques.append(f"format `{fmt_date}`")
            if col["params"].get("decimale") == ",":
                remarques.append("virgule décimale")
            taux = col["taux_manquants"]
            manq = "0 %" if taux == 0 else ("< 1 %" if taux < 0.01 else f"≈ {round(taux * 100)} %")
            type_affiche = TYPES.get(col["stockage"], col["stockage"])
            if col["stockage"] == "texte" and col["genre"] in ("numerique", "discret"):
                type_affiche = "texte (nombres)"
            elif col["stockage"] == "texte" and col["genre"] in ("date", "date_naissance"):
                type_affiche = "texte (dates)"
            lignes.append(
                f"| `{echapper(col['nom'])}` | {NATURES.get(col['genre'], col['genre'])} | {type_affiche} "
                f"| {manq} | {echapper(apercu(t.donnees[j], col))} | {echapper('; '.join(remarques))} |"
            )
            col.pop("_seuil", None)
        lignes.append("")
    lignes += [
        "## Ce que le sosie reproduit",
        "",
        "- Les fichiers, colonnes, types, formats, encodages, modalités fréquentes, taux et codes de valeurs manquantes.",
        "- Les clés de jointure entre fichiers (y compris les clés composites), le nombre de lignes par individu "
        "(plafonné pour les individus extrêmes), les rangs et l'ordre des visites.",
        "- Les attributs constants d'un individu (même valeur dans toutes les tables), l'ordre des dates, les délais "
        "par rapport à la date d'inclusion, les prélèvements d'un même jour et les dates ou codes conventionnels (9999-12-31, 999…).",
        "- Les exceptions aux règles (doublons, trous, ordre non respecté) quand elles existent dans les vraies données.",
        "- L'ordre des lignes est mélangé (par individu) : ne t'appuie pas sur la position d'une ligne.",
        "",
        "## Ce que le sosie ne reproduit pas",
        "",
        "- Les liens entre variables (corrélations, effets, trajectoires) : les colonnes sont tirées indépendamment.",
        "- Les relations calculées (ex. IMC = poids / taille²) : ne t'appuie pas dessus pour valider le code.",
        "- Les modalités rares, les valeurs extrêmes, les vrais identifiants, noms, adresses et textes libres.",
        f"- Le code doit donc prévoir des modalités absentes du sosie et les valeurs « {SENTINELLE} » / « {SENTINELLE_VALEUR} », "
        "qui signalent des valeurs rares bien présentes dans les vraies données.",
        "",
    ]
    if copies:
        lignes += ["## Fichiers copiés tels quels (à ta demande)", ""] + [f"- `{c}`" for c in copies] + [""]
    if ignores:
        lignes += ["## Fichiers non reproduits", ""] + [f"- `{f}` : {raison}" for f, raison in ignores] + [""]
    if avertissements:
        lignes += ["## Avertissements", ""] + [f"- {a}" for a in avertissements] + [""]
    return "\n".join(lignes)
