import csv
import datetime as dt
import os
import re
import secrets
from pathlib import Path

import pandas as pd

import hashlib
import hmac

from .formats import ecrire_fichier, est_manquant, lire_fichier, lister_fichiers
from .identifiants import decalage_jours, pseudonyme, pseudonyme_numerique
from .profil import DATES_SENTINELLES, GENRES_DATES, cle_valeur, profiler

RE_PSEUDONYME = re.compile(r"PS-[0-9A-F]{16}")
RE_PSEUDONYME_NUMERIQUE = re.compile(r"(?<!\d)\d{12,20}(?!\d)")
RE_PREFIXE_CHIFFRES = re.compile(r"^(\D*?)(\d+)$")


def canonique(valeur):
    m = RE_PREFIXE_CHIFFRES.match(valeur)
    if m:
        return m.group(1).lower() + (m.group(2).lstrip("0") or "0")
    return valeur.lower()


def pseudonyme_valeur(cle, valeur):
    base = canonique(valeur)
    if valeur.isdigit():
        if len(valeur) >= 12 and not valeur.startswith("0"):
            empreinte = hmac.new(cle, ("long:" + base).encode("utf-8"), hashlib.sha256).digest()
            longueur = len(valeur)
            return str(10 ** (longueur - 1) + int.from_bytes(empreinte[:16], "big") % (9 * 10 ** (longueur - 1)))
        return str(pseudonyme_numerique(cle, base))
    return pseudonyme(cle, base)


def date_speciale(moment):
    try:
        iso = moment.date().isoformat() if hasattr(moment, "date") else str(moment)[:10]
    except (ValueError, OverflowError):
        return True
    return iso in DATES_SENTINELLES or iso < "1850" or iso > "2150"
FICHIER_CLE = ".cle_pseudonymisation"
DOSSIER_CORRESPONDANCE = ".correspondance"
FICHIER_CORRESPONDANCE = "table_correspondance.csv"


def charger_cle(coffre_projet):
    chemin = Path(coffre_projet) / FICHIER_CLE
    if not chemin.exists():
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(secrets.token_hex(32), encoding="utf-8")
        try:
            os.chmod(chemin, 0o600)
        except OSError:
            pass
    return bytes.fromhex(chemin.read_text(encoding="utf-8").strip())


def chemin_correspondance(coffre_projet):
    return Path(coffre_projet) / DOSSIER_CORRESPONDANCE / FICHIER_CORRESPONDANCE


def lire_correspondance(coffre_projet):
    chemin = chemin_correspondance(coffre_projet)
    table = {}
    if chemin.exists():
        with open(chemin, encoding="utf-8", newline="") as f:
            for ligne in csv.DictReader(f, delimiter=";"):
                table[ligne["pseudonyme"]] = ligne["valeur_originale"]
    return table


def ecrire_correspondance(coffre_projet, nouvelles):
    table = lire_correspondance(coffre_projet)
    table.update(nouvelles)
    chemin = chemin_correspondance(coffre_projet)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["pseudonyme", "valeur_originale"])
        for p, v in sorted(table.items()):
            w.writerow([p, v])
    try:
        os.chmod(chemin, 0o600)
    except OSError:
        pass
    return chemin


def vide_comme(serie, stockage, jeton):
    n = len(serie)
    if stockage in ("texte", "mixte"):
        return pd.Series([jeton if stockage == "texte" else None] * n, dtype=object)
    if isinstance(serie.dtype, pd.CategoricalDtype):
        return pd.Series(pd.Categorical([None] * n, categories=serie.cat.categories))
    try:
        return pd.Series([None] * n, dtype=serie.dtype)
    except (TypeError, ValueError):
        return pd.Series([None] * n, dtype=object)


def transformer_date(valeur_texte, fmt, jours, naissance):
    try:
        moment = dt.datetime.strptime(valeur_texte, fmt) if fmt else pd.Timestamp(valeur_texte).to_pydatetime()
        if date_speciale(moment):
            return valeur_texte
        moment = moment + dt.timedelta(days=jours)
    except (ValueError, OverflowError, TypeError):
        return valeur_texte
    if naissance == "mois":
        moment = moment.replace(day=1)
    elif naissance == "annee":
        moment = moment.replace(month=1, day=1)
    try:
        return moment.strftime(fmt) if fmt else moment.isoformat()
    except ValueError:
        return valeur_texte


def ajuster_date_typee(v, jours, naissance):
    if est_manquant(v):
        return v
    try:
        if date_speciale(pd.Timestamp(v) if not isinstance(v, (pd.Timestamp, dt.datetime, dt.date)) else v):
            return v
        if isinstance(v, (pd.Timestamp, dt.datetime)):
            m = pd.Timestamp(v) + pd.Timedelta(days=jours)
        else:
            m = (pd.Timestamp(v) + pd.Timedelta(days=jours)).date()
        if naissance == "mois":
            m = m.replace(day=1)
        elif naissance == "annee":
            m = m.replace(month=1, day=1)
        return m
    except (ValueError, OverflowError, TypeError, NotImplementedError):
        return v


def pseudonymiser(source, sortie, coffre_projet, seuil=11, decaler=0, naissance="mois", garder_texte=False,
                  forcer=(), cle_individu=None):
    cle = charger_cle(coffre_projet)
    forcer = set(forcer)
    fichiers = lister_fichiers(source)
    tables = []
    ignores = []
    for chemin, rel in fichiers:
        try:
            tables.extend(lire_fichier(chemin, rel))
        except Exception as e:
            ignores.append((rel, str(e)))
    utiles = [t for t in tables if not t.options.get("vide")]
    demandes = [cle_individu] if isinstance(cle_individu, str) else list(cle_individu or [])
    par_table, structures = profiler(utiles, seuil, (), demandes)
    correspondance = {}
    canoniques = {}
    rapport = []
    avertissements_cles = []
    noms_cles = set()
    for t, liste, s in zip(utiles, par_table, structures):
        individu = s.get("cle_individu") if s.get("cle_individu") is not None else s.get("entite")
        cles_individu = individu.cles() if individu is not None else None
        if individu is not None:
            noms_cles.add(str(individu.nom))
        for a in liste:
            j = a.j
            g = "identifiant" if a.nom in forcer else a.genre
            if g in ("identifiant", "nir"):
                cles = a.cles()
                nouvelles = []
                for c in cles:
                    if c is None:
                        nouvelles.append(None)
                        continue
                    p = pseudonyme_valeur(cle, c)
                    base = canonique(c)
                    if p in canoniques and canoniques[p] != base:
                        raise RuntimeError("collision de pseudonymes : impossible de continuer")
                    canoniques[p] = base
                    correspondance.setdefault(p, c)
                    nouvelles.append(p)
                numerique = all(x is None or x.isdigit() for x in nouvelles)
                if a.stockage in ("entier", "decimal") and numerique:
                    try:
                        t.donnees[j] = pd.Series([None if x is None else int(x) for x in nouvelles],
                                                 dtype="Int64" if a.stockage == "entier" else "float64")
                    except (OverflowError, TypeError, ValueError):
                        t.donnees[j] = pd.Series(nouvelles, dtype=object)
                        t.stockages[j] = "texte"
                else:
                    t.donnees[j] = pd.Series(nouvelles, dtype=object)
                    t.stockages[j] = "texte"
                t.options.get("etiquettes", {}).pop(a.nom, None)
                rapport.append((t.nom_affiche, a.nom, "pseudonymisée (numéros)" if numerique else "pseudonymisée (PS-… pour les valeurs non numériques)"))
            elif g in ("nom", "prenom", "email", "telephone", "adresse", "ville") or (g == "texte_libre" and not garder_texte):
                t.donnees[j] = vide_comme(a.serie, a.stockage, a.jeton_manquant or "")
                rapport.append((t.nom_affiche, a.nom, "vidée (identifiant direct ou texte libre)"))
            elif g == "code_postal":
                if a.stockage in ("entier", "decimal"):
                    t.donnees[j] = pd.Series([None if est_manquant(v) else int(v) // 1000 * 1000 for v in a.serie.tolist()],
                                             dtype="Int64" if a.stockage == "entier" else "float64")
                else:
                    t.donnees[j] = pd.Series([v if c is None else (c[:2] + "0" * (len(c) - 2)) for v, c in zip(a.serie.tolist(), a.cles())],
                                             dtype=object)
                rapport.append((t.nom_affiche, a.nom, "réduite au département"))
            elif g in GENRES_DATES and (decaler or (g == "date_naissance" and naissance != "garder")):
                mode = naissance if g == "date_naissance" else "garder"
                decale = bool(decaler and cles_individu)
                valeurs = []
                for i, v in enumerate(a.serie.tolist()):
                    cle_i = cles_individu[i] if cles_individu else None
                    jours = decalage_jours(cle, canonique(cle_i), decaler) if (decale and cle_i) else 0
                    if a.textes is not None:
                        texte = a.textes[i]
                        valeurs.append(v if texte is None else transformer_date(texte, a.format_date, jours, mode))
                    elif a.stockage in ("entier", "decimal") and a.format_date:
                        valeurs.append(v if est_manquant(v) else nombre_date(v, a.format_date, jours, mode))
                    else:
                        valeurs.append(ajuster_date_typee(v, jours, mode))
                if a.stockage == "datetime":
                    try:
                        t.donnees[j] = pd.to_datetime(pd.Series(valeurs)).astype(a.serie.dtype)
                    except (ValueError, OverflowError, TypeError):
                        t.donnees[j] = pd.Series(valeurs, dtype=object)
                elif a.stockage in ("entier", "decimal"):
                    t.donnees[j] = pd.Series(valeurs, dtype="Int64" if a.stockage == "entier" else "float64")
                else:
                    t.donnees[j] = pd.Series(valeurs, dtype=object)
                actions = []
                if decaler:
                    actions.append(f"décalée de ±{decaler} j par individu (selon « {individu.nom} »), dates conventionnelles intactes" if decale
                                   else "NON décalée (aucun identifiant d'individu dans ce fichier)")
                if mode != "garder":
                    actions.append("réduite au " + ("mois" if mode == "mois" else "1er janvier de l'année"))
                rapport.append((t.nom_affiche, a.nom, " ; ".join(actions)))
            else:
                rapport.append((t.nom_affiche, a.nom, "conservée telle quelle"))
    ecrits = []
    avertissements = list(avertissements_cles)
    if decaler and len(noms_cles) > 1:
        avertissements.append("Décalage des dates calculé selon des clés de noms différents (" + ", ".join(sorted(noms_cles)[:5])
                              + ") : si ce ne sont pas les mêmes valeurs d'un fichier à l'autre, les délais entre fichiers changent. "
                              "Précise la clé commune : sosie pseudonymiser --cle-individu COLONNE")
    par_fichier = {}
    for t in tables:
        par_fichier.setdefault(t.fichier, []).append(t)
    for fichier, groupe in par_fichier.items():
        for t in groupe:
            if "schema" in t.options:
                t.options["schema"] = None
            t.options.pop("meta_pandas", None)
        rel, av = ecrire_fichier(sortie, groupe)
        ecrits.append(rel)
        avertissements += av
    chemin = ecrire_correspondance(coffre_projet, correspondance)
    return rapport, ecrits, ignores, avertissements, chemin, len(correspondance)


def nombre_date(v, fmt, jours, naissance):
    texte = transformer_date(str(int(v)), fmt, jours, naissance)
    try:
        return int(texte)
    except ValueError:
        return v


def reidentifier(fichier, destination, coffre_projet):
    table = lire_correspondance(coffre_projet)
    if not table:
        raise RuntimeError("aucune table de correspondance dans le coffre de ce projet")
    fichier = Path(fichier)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    remplaces = 0
    tables = None
    if fichier.suffix.lower() not in (".txt", ".md", ".qmd", ".rmd", ".html", ".tex", ".log"):
        try:
            tables = lire_fichier(fichier, destination.name)
        except Exception:
            tables = None
    if tables:
        for t in tables:
            for j in range(len(t.noms)):
                valeurs = t.donnees[j].tolist()
                cles = [cle_valeur(v) for v in valeurs]
                if not any(c in table for c in cles if c is not None):
                    continue
                nouvelles = []
                for v, c in zip(valeurs, cles):
                    if c is not None and c in table:
                        nouvelles.append(table[c])
                        remplaces += 1
                    else:
                        nouvelles.append(v)
                entier = t.stockages[j] == "entier" and all(est_manquant(x) or (isinstance(x, str) and x.isdigit() and not (len(x) > 1 and x.startswith("0"))) or isinstance(x, int) for x in nouvelles)
                if entier:
                    try:
                        t.donnees[j] = pd.Series([None if est_manquant(x) else int(x) for x in nouvelles], dtype="Int64")
                        continue
                    except (OverflowError, TypeError, ValueError):
                        pass
                t.donnees[j] = pd.Series(nouvelles, dtype=object)
                if t.stockages[j] not in ("texte", "mixte"):
                    t.stockages[j] = "texte"
            if "schema" in t.options:
                t.options["schema"] = None
            t.options.pop("meta_pandas", None)
            t.fichier = destination.name
        ecrire_fichier(destination.parent, tables)
        return destination, remplaces
    texte = fichier.read_text(encoding="utf-8", errors="replace")

    def remplacer(m):
        nonlocal remplaces
        if m.group(0) in table:
            remplaces += 1
            return table[m.group(0)]
        return m.group(0)

    texte = RE_PSEUDONYME.sub(remplacer, texte)
    texte = RE_PSEUDONYME_NUMERIQUE.sub(remplacer, texte)
    destination.write_text(texte, encoding="utf-8")
    return destination, remplaces
