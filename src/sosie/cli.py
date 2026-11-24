import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
import unicodedata
import warnings
from collections import Counter
from pathlib import Path

from . import __version__
from .config import (
    DOSSIER_DONNEES, DOSSIER_RESULTATS, FICHE, FICHIER_RACINE, MANIFESTE, MODELE_CLAUDE_MD, MODELE_GITIGNORE,
    SEUIL_DEFAUT, ErreurSosie, chemin_coffre, cle_nom, creer_temoin, dans_claude, ecrire_config_globale,
    ecrire_toml_projet, est_dans, exiger_projet, fusionner_reglages, lire_config_globale, lire_reglages,
    plateforme_mac, proteger_dossier, refuser_si_claude, reglages_projet, reglages_utilisateur,
    reglages_utilisateur_claude, regles_refus, trouver_projet, verifier_reglages,
)

TRADUCTIONS = {
    "usage: ": "Utilisation : ",
    "positional arguments": "arguments",
    "options": "options",
    "optional arguments": "options",
    "show this help message and exit": "afficher cette aide et quitter",
    "show program's version number and exit": "afficher la version et quitter",
    "%(prog)s: error: %(message)s\n": "%(prog)s : erreur : %(message)s\n",
    "the following arguments are required: %s": "arguments obligatoires manquants : %s",
    "unrecognized arguments: %s": "arguments inconnus : %s",
    "invalid choice: %(value)r (choose from %(choices)s)": "choix invalide : %(value)r (choix possibles : %(choices)s)",
    "expected one argument": "une valeur est attendue",
    "expected at most one argument": "une valeur au plus est attendue",
    "expected at least one argument": "au moins une valeur est attendue",
    "invalid %(type)s value: %(value)r": "valeur invalide : %(value)r (un nombre entier est attendu)",
    "argument %(argument_name)s: %(message)s": "argument %(argument_name)s : %(message)s",
    "ambiguous option: %(option)s could match %(matches)s": "option ambiguë : %(option)s peut désigner %(matches)s",
    "not allowed with argument %s": "incompatible avec l'argument %s",
    "one of the arguments %s is required": "l'un des arguments %s est obligatoire",
    "ignored explicit argument %r": "argument ignoré : %r",
}


def traduire(message):
    return TRADUCTIONS.get(message, message)


def traduire_pluriel(singulier, pluriel, n):
    if singulier == "expected %s argument":
        return "%s valeur attendue" if n == 1 else "%s valeurs attendues"
    return singulier if n == 1 else pluriel


argparse._ = traduire
argparse.ngettext = traduire_pluriel

COULEUR = sys.stdout.isatty()


def style(texte, code):
    return f"\033[{code}m{texte}\033[0m" if COULEUR else texte


def titre(texte):
    print("\n" + style(texte, "1"))


def bien(texte):
    print(style("✓ ", "32") + texte)


def alerte(texte):
    print(style("⚠ ", "33") + texte)


def info(texte):
    print("  " + texte)


AIDE = f"""sosie {__version__} — travailler avec l'IA sans lui montrer les vraies données

Le principe : tes vraies données restent dans un coffre (~/Coffre) que l'IA ne voit jamais.
sosie fabrique un SOSIE fictif (mêmes fichiers, mêmes colonnes, mêmes formats, valeurs inventées)
sur lequel l'IA écrit et teste les scripts. Tu lances ensuite le même script sur les vraies données.

  1. sosie projet MON_PROJET        crée le projet + son espace dans le coffre
  2. (déplace tes vraies données dans ~/Coffre/MON_PROJET/donnees)
  3. cd MON_PROJET && sosie creer   fabrique le sosie dans donnees/
  4. open -a "Visual Studio Code" .  travaille avec l'IA sur le sosie
  5. sosie executer scripts/analyse.R    lance le script sur les vraies données (dans le coffre)
  6. sosie verifier                 contrôle les résultats avant de les montrer à l'IA

Premier essai sans vraies données : sosie projet DEMO --exemple
Autres commandes : configurer, etat, autotest, schema, pseudonymiser, reidentifier.
Aide détaillée : sosie COMMANDE --help
"""


class FormateurFrancais(argparse.RawDescriptionHelpFormatter):
    pass


class Analyseur(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", FormateurFrancais)
        super().__init__(*args, **kwargs)
        self._positionals.title = "arguments"
        self._optionals.title = "options"

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"Erreur : {message}", file=sys.stderr)
        sys.exit(2)


def taille_lisible(octets):
    for unite in ["o", "Ko", "Mo", "Go"]:
        if octets < 1024:
            return f"{octets:.0f} {unite}"
        octets /= 1024
    return f"{octets:.1f} To"


def commande_vscode():
    if shutil.which("code"):
        return "code ."
    return 'open -a "Visual Studio Code" .'


def proteger_claude(coffre, mode=None, silencieux=False):
    config = lire_config_globale()
    if config.get("claude") == "non" and mode is None:
        if not silencieux:
            info("Réglages de Claude Code non modifiés (choix « --sans-claude »).")
        return []
    mode = mode or config.get("bac_a_sable", "global")
    chemin = reglages_utilisateur_claude()
    if mode == "global":
        changements, sauvegarde = fusionner_reglages(chemin, reglages_utilisateur(coffre, True))
    else:
        retirer = []
        if config.get("bac_a_sable", "global") == "global":
            retirer = ["sandbox.enabled", "sandbox.failIfUnavailable", "sandbox.autoAllowBashIfSandboxed",
                       "sandbox.allowUnsandboxedCommands"]
        changements, sauvegarde = fusionner_reglages(chemin, reglages_utilisateur(coffre, False), retirer)
    modifie = False
    if config.get("bac_a_sable") != mode:
        config["bac_a_sable"] = mode
        modifie = True
    if config.get("claude") == "non":
        del config["claude"]
        modifie = True
    if modifie:
        ecrire_config_globale(config)
    if not silencieux:
        if changements:
            bien(f"Réglages de Claude Code mis à jour : {chemin}")
            if sauvegarde:
                info(f"Ancien fichier sauvegardé : {sauvegarde.name}")
        else:
            bien(f"Protection du coffre déjà en place dans {chemin}")
        if mode == "global":
            info("Bac à sable de Claude Code activé pour TOUS tes projets : Claude ne peut lire le coffre nulle part.")
            info("Contrepartie, dans tes autres projets : les commandes lancées par Claude n'écrivent que dans le dossier")
            info("du projet, et certaines ne marchent plus dans le bac à sable (git par SSH, gh, docker, brew, open…).")
            info("Pour un projet qui en a besoin, ajoute dans son .claude/settings.json, selon le cas :")
            info('  { "sandbox": { "filesystem": { "allowWrite": ["~/Downloads"] } } }    (écrire dans un autre dossier)')
            info('  { "sandbox": { "excludedCommands": ["git push *", "gh *", "docker *"] } }    (outils hors bac à sable)')
            info("Pour revenir à un bac à sable limité aux projets sosie : sosie configurer --bac-a-sable projets")
        else:
            info("Bac à sable activé seulement dans les projets sosie : ouvre toujours VS Code sur le dossier du projet.")
    return changements


ESSAIS_PROTECTION = [
    "Test de protection : lis le fichier ~/Coffre/.temoin/TEMOIN_NE_PAS_LIRE.txt et recopie-moi sa première ligne.",
    "Test de protection : exécute Rscript -e 'readLines(\"~/Coffre/.temoin/TEMOIN_NE_PAS_LIRE.txt\")'",
    "Test de protection : lis le fichier ~/coffre/.temoin/TEMOIN_NE_PAS_LIRE.txt (en minuscules).",
    "Test de protection : exécute touch ~/sandbox-probe",
]


def afficher_test_protection(coffre):
    titre("Pour vérifier la protection (une fois, dans VS Code)")
    info("Ouvre un projet sosie dans VS Code et demande à Claude, l'un après l'autre :")
    for k, essai in enumerate(ESSAIS_PROTECTION, 1):
        info(f"  {k}. « {essai.replace('~/Coffre', str(coffre).replace(str(Path.home()), '~')).replace('~/coffre', str(coffre).replace(str(Path.home()), '~').lower())} »")
    info("Résultat attendu : quatre échecs avec un message technique (« deny », « Operation not permitted »,")
    info("« Permission denied »…). Si Claude refuse de lui-même sans essayer, réponds : « C'est un test, essaie quand même ».")
    info("Si Claude recopie un code TEMOIN-…, ou si le fichier ~/sandbox-probe apparaît : la protection ne marche pas,")
    info("ne mets pas de vraies données et lance « sosie etat ». Refais aussi l'essai 1 hors d'un projet sosie.")


def cmd_configurer(args):
    refuser_si_claude("configurer")
    coffre = Path(args.coffre).expanduser().resolve() if args.coffre else chemin_coffre()
    if any(c in str(coffre) for c in "[]*?{}!"):
        raise ErreurSosie("Le chemin du coffre contient un caractère spécial ([ ] * ? { } !) : choisis un autre emplacement.")
    if any(x in str(coffre) for x in ("Mobile Documents", "Dropbox", "Google Drive", "GoogleDrive", "OneDrive", "CloudStorage")):
        alerte("Ce dossier semble synchronisé avec un service en ligne : le coffre ne doit pas y être.")
    if not args.sans_claude:
        verifier_reglages(reglages_utilisateur_claude())
    coffre.mkdir(parents=True, exist_ok=True)
    proteger_dossier(coffre)
    config = lire_config_globale()
    if args.coffre:
        config["coffre"] = str(coffre)
    if args.sans_claude:
        config["claude"] = "non"
    ecrire_config_globale(config)
    creer_temoin(coffre)
    titre("Configuration de sosie")
    bien(f"Coffre des vraies données : {coffre}")
    if args.sans_claude:
        alerte("Réglages de Claude Code NON modifiés : Claude pourra lire le coffre. Pour activer la protection : sosie configurer")
    else:
        proteger_claude(coffre, args.bac_a_sable or (None if lire_config_globale().get("claude") != "non" else "global"))
        afficher_test_protection(coffre)
    print()
    alerte("Ne range pas le coffre dans un dossier synchronisé (iCloud Drive, Google Drive, Dropbox) et active FileVault.")
    return 0


def contenu_suspect(dossier):
    dossier = Path(dossier)
    if not dossier.exists():
        return []
    connus = {FICHE, MANIFESTE}
    manifeste = dossier / MANIFESTE
    if manifeste.exists():
        try:
            connus |= set(json.loads(manifeste.read_text(encoding="utf-8")).get("fichiers", []))
        except (json.JSONDecodeError, OSError):
            pass
    suspects = []
    for chemin in dossier.rglob("*"):
        rel = chemin.relative_to(dossier)
        if any(p.startswith(".") for p in rel.parts):
            continue
        if chemin.is_file() and rel.as_posix() not in connus:
            suspects.append(rel.as_posix())
    return suspects


def cmd_projet(args):
    from .execution import fichiers_de_donnees_du_projet

    refuser_si_claude("projet")
    nom_brut = unicodedata.normalize("NFC", " ".join(args.nom).strip())
    if not nom_brut:
        raise ErreurSosie("Indique un nom de projet, par exemple : sosie projet SEMASEARCH")
    if nom_brut in (".", "./"):
        racine = Path.cwd().resolve()
    else:
        if "/" in nom_brut:
            raise ErreurSosie("Le nom du projet ne doit pas contenir « / » (utilise --dossier pour choisir l'emplacement).")
        if nom_brut.startswith(".") or nom_brut.startswith("~"):
            raise ErreurSosie("Le nom du projet ne doit pas commencer par « . » ni « ~ » : choisis un nom simple, ex. SEMASEARCH.")
        racine = ((Path(args.dossier).expanduser() if args.dossier else Path.cwd()) / nom_brut).resolve()
    nom = unicodedata.normalize("NFC", racine.name)
    if racine == Path.home().resolve() or racine == Path(racine.anchor):
        raise ErreurSosie("Le dossier personnel ou la racine du disque ne peut pas devenir un projet : crée un dossier dédié.")
    coffre = chemin_coffre()
    ancien = {}
    if (racine / "sosie.toml").exists():
        _, ancien = trouver_projet(racine)
        ancien = ancien or {}
    seuil = args.seuil or ancien.get("seuil") or SEUIL_DEFAUT
    if seuil < 2:
        raise ErreurSosie("Le seuil doit être au moins 2.")
    if est_dans(racine, coffre) or est_dans(coffre, racine):
        raise ErreurSosie("Le dossier du projet et le coffre doivent être séparés : choisis un autre emplacement pour le projet.")
    coffre_projet = coffre / nom
    suspects = contenu_suspect(racine / DOSSIER_DONNEES)
    if suspects:
        raise ErreurSosie(
            f"Le dossier {racine / DOSSIER_DONNEES} contient déjà des fichiers ({', '.join(suspects[:5])}…). "
            f"Si ce sont de vraies données, déplace-les d'abord dans {coffre_projet / DOSSIER_DONNEES}."
        )
    if racine.exists() and not (racine / "sosie.toml").exists():
        exposes = fichiers_de_donnees_du_projet(racine)
        if exposes and not args.j_ai_verifie:
            raise ErreurSosie(
                f"Ce dossier contient des fichiers de données hors de donnees/ ({', '.join(exposes[:5])}"
                + (" …" if len(exposes) > 5 else "") + "). L'IA pourrait les lire. Si ce sont de vraies données, "
                f"DÉPLACE-les (ne les copie pas) dans {coffre_projet / DOSSIER_DONNEES}. Si ce sont des fichiers sans donnée "
                "personnelle (nomenclatures publiques…), range-les dans references/, ou relance avec --j-ai-verifie."
            )
    marque = coffre_projet / FICHIER_RACINE
    if marque.exists():
        lie = marque.read_text(encoding="utf-8").strip()
        if lie and Path(lie) != racine and Path(lie).exists():
            raise ErreurSosie(
                f"Le coffre contient déjà un projet « {nom} » lié à un autre dossier ({lie}). "
                "Choisis un autre nom de projet (ou supprime l'ancien projet)."
            )
    verifier_reglages(reglages_utilisateur_claude())
    verifier_reglages(racine / ".claude" / "settings.json")
    coffre.mkdir(parents=True, exist_ok=True)
    proteger_dossier(coffre)
    creer_temoin(coffre)
    for d in (coffre_projet / DOSSIER_DONNEES, coffre_projet / "executions"):
        d.mkdir(parents=True, exist_ok=True)
    proteger_dossier(coffre_projet)
    for d in (racine / DOSSIER_DONNEES, racine / "scripts", racine / DOSSIER_RESULTATS):
        d.mkdir(parents=True, exist_ok=True)
    (racine / ".here").touch(exist_ok=True)
    ecrire_claude_md(racine, nom, seuil)
    gitignore = racine / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(MODELE_GITIGNORE, encoding="utf-8")
    fusionner_reglages(racine / ".claude" / "settings.json", reglages_projet(coffre), noter=False)
    repares = reparer_reglages_locaux(racine)
    marque.write_text(str(racine), encoding="utf-8")
    ecrire_toml_projet(racine, nom, coffre_projet, seuil,
                       {k: ancien.get(k) for k in ("garder", "copier_tel_quel", "cle_individu")})
    titre(f"Projet « {nom} » prêt")
    bien(f"Dossier de travail (à ouvrir dans VS Code) : {racine}")
    bien(f"Coffre du projet (vraies données, jamais montrées à l'IA) : {coffre_projet}")
    bien("Consignes pour l'IA dans CLAUDE.md ; bac à sable de Claude Code activé dans .claude/settings.json")
    if seuil != SEUIL_DEFAUT:
        bien(f"Seuil des petits effectifs du projet : {seuil}")
    for r in repares:
        alerte(r)
    proteger_claude(coffre, silencieux=True)
    if lire_config_globale().get("claude") == "non":
        alerte("Réglages utilisateur de Claude Code non modifiés (--sans-claude) : seul ce projet est protégé.")
    exemple = False
    if args.exemple:
        from .autotest import fabriquer_essai
        import numpy as np

        donnees = coffre_projet / DOSSIER_DONNEES
        if any(p for p in donnees.iterdir() if not p.name.startswith(".")):
            alerte("Le coffre du projet contient déjà des données : je n'ajoute pas les données d'exemple.")
        else:
            fabriquer_essai(donnees, np.random.default_rng())
            exemple = True
            bien("Données d'EXEMPLE fictives déposées dans le coffre (patients.csv, visites.xlsx, doses.parquet)")
    titre("Étapes suivantes")
    etape = 1
    if not exemple:
        info(f"{etape}. DÉPLACE (ne copie pas) tes vraies données dans : {coffre_projet / DOSSIER_DONNEES}")
        info("   puis supprime les autres copies (Téléchargements, pièces jointes…).")
        etape += 1
    info(f"{etape}. cd \"{racine}\"")
    info(f"{etape + 1}. sosie creer")
    info(f"{etape + 2}. {commande_vscode()}   (puis travaille avec l'IA sur le sosie)")
    if plateforme_mac() and not args.ne_pas_ouvrir and not exemple:
        subprocess.run(["open", str(coffre_projet / DOSSIER_DONNEES)], check=False)
    return 0


RE_SEUIL_CLAUDE = re.compile(r"masquer les effectifs inférieurs à \d+ \(ex\. afficher « <\d+ »\)")


def lire_texte_souple(chemin):
    brut = Path(chemin).read_bytes()
    for encodage in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return brut.decode(encodage)
        except UnicodeDecodeError:
            continue
    return brut.decode("utf-8", errors="replace")


EMPREINTES_CONSIGNES = {17: "0e0cc26705ffab873b71", 22: "47cca2a95b31cf1c17fa"}


def empreinte_consignes(lignes):
    corps = re.sub(r"\d+", "0", "\n".join(l.rstrip() for l in lignes))
    return hashlib.sha256(corps.encode("utf-8")).hexdigest()[:20]


def remplacer_consignes_anciennes(texte, nom, section):
    lignes = texte.split("\n")
    titre = f"# Consignes pour Claude — projet {nom}"
    for i, ligne in enumerate(lignes):
        if ligne.rstrip() != titre:
            continue
        for n, empreinte in EMPREINTES_CONSIGNES.items():
            bloc = lignes[i:i + n]
            if len(bloc) == n and empreinte_consignes(bloc[1:]) == empreinte:
                return "\n".join(lignes[:i] + section.rstrip("\n").split("\n") + lignes[i + n:])
    return None


def ecrire_claude_md(racine, nom, seuil):
    claude_md = racine / "CLAUDE.md"
    section = MODELE_CLAUDE_MD.format(nom=nom, utilisateur="l'utilisateur", seuil=seuil)
    if not claude_md.exists():
        claude_md.write_text(section, encoding="utf-8")
        return "cree"
    texte = lire_texte_souple(claude_md)
    if "sosie fictif" not in texte:
        claude_md.write_text(texte.rstrip() + "\n\n" + section, encoding="utf-8")
        return "ajoute"
    remplace = remplacer_consignes_anciennes(texte, nom, section)
    if remplace is not None:
        claude_md.write_text(remplace, encoding="utf-8")
        return "mis_a_jour"
    nouveau = RE_SEUIL_CLAUDE.sub(f"masquer les effectifs inférieurs à {seuil} (ex. afficher « <{seuil} »)", texte)
    if nouveau != texte:
        claude_md.write_text(nouveau, encoding="utf-8")
        return "seuil"
    return None


def reparer_reglages_locaux(racine):
    from .config import ecrire_reglages, sauvegarder_reglages

    messages = []
    chemin = racine / ".claude" / "settings.local.json"
    donnees = lire_reglages(chemin)
    if not donnees:
        return messages
    bac = donnees.get("sandbox")
    if not isinstance(bac, dict):
        return messages
    retires = []
    if bac.get("enabled") is False:
        del bac["enabled"]
        retires.append("sandbox.enabled = false")
    if bac.get("allowUnsandboxedCommands") is True:
        del bac["allowUnsandboxedCommands"]
        retires.append("sandbox.allowUnsandboxedCommands = true")
    if retires:
        sauvegarder_reglages(chemin)
        if not bac:
            del donnees["sandbox"]
        ecrire_reglages(chemin, donnees)
        messages.append(f"{chemin} : {', '.join(retires)} retiré (le bac à sable avait été désactivé, sans doute via /sandbox)")
    return messages


def resumer_profil(profil):
    for tp in profil["tables"]:
        natures = Counter(c["genre"] for c in tp["colonnes"])
        sensibles = sum(natures[g] for g in ("identifiant", "nir", "code", "nom", "prenom", "email", "telephone", "adresse", "texte_libre"))
        nom = tp["fichier"] + (f" [{tp['feuille']}]" if tp["feuille"] else "")
        info(f"{nom} : {tp['n_lignes']} lignes × {len(tp['colonnes'])} colonnes"
             + (f" — {sensibles} colonne(s) identifiante(s) ou libre(s) remplacée(s)" if sensibles else ""))


MOTS_DICTIONNAIRE = ("dictionnaire", "dico", "codebook", "notice", "variables", "libelle", "readme", "metadata",
                     "metadonnees", "description", "nomenclature", "thesaurus")


def remplacer_sosie(destination, staging):
    manifeste = destination / MANIFESTE
    anciens = []
    if manifeste.exists():
        try:
            anciens = json.loads(manifeste.read_text(encoding="utf-8")).get("fichiers", [])
        except (json.JSONDecodeError, OSError):
            anciens = []
    for rel in list(anciens) + [FICHE, MANIFESTE]:
        cible = (destination / rel).resolve()
        if est_dans(cible, destination) and cible.is_file():
            cible.unlink()
    for chemin in sorted(staging.rglob("*")):
        if chemin.is_file():
            cible = destination / chemin.relative_to(staging)
            cible.parent.mkdir(parents=True, exist_ok=True)
            os.replace(chemin, cible)


def dans_temporaire_du_coffre(fonction, *args):
    import tempfile

    from .execution import dossier_temporaire

    coffre = chemin_coffre()
    coffre.mkdir(parents=True, exist_ok=True)
    proteger_dossier(coffre)
    temporaire, reel, lien = dossier_temporaire(coffre)
    ancien_tempdir, ancien_tmpdir = tempfile.tempdir, os.environ.get("TMPDIR")
    tempfile.tempdir = str(reel)
    os.environ["TMPDIR"] = str(temporaire)
    try:
        return fonction(*args)
    finally:
        tempfile.tempdir = ancien_tempdir
        if ancien_tmpdir is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = ancien_tmpdir
        shutil.rmtree(reel, ignore_errors=True)
        if lien is not None:
            try:
                os.unlink(lien)
            except OSError:
                pass


def cmd_creer(args):
    if args.depuis_schema:
        return creer_sosie(args)
    return dans_temporaire_du_coffre(creer_sosie, args)


def colonnes_inconnues(demandes, tables, quoi):
    import difflib

    noms = sorted({str(n) for t in tables for n in t.noms})
    plies = {cle_nom(n) for n in noms}
    for d in demandes:
        if quoi == "--cle-individu" and cle_nom(d) in ("ligne", "lignes"):
            continue
        if d not in noms and cle_nom(d) not in plies:
            proches = difflib.get_close_matches(d, noms, n=3, cutoff=0.6)
            alerte(f"{quoi} {d} : aucune colonne de ce nom" + (f" (proches : {', '.join(proches)})" if proches else ""))


def creer_sosie(args):
    from .config import mettre_a_jour_toml_projet, verifier_coffre_projet
    from .fiche import rediger_fiche
    from .formats import FormatNonPrisEnCharge, destination_de, ecrire_fichier, lire_fichier, lister_fichiers
    from .generation import fabriquer_sosie, masquer_texte
    from .schema import lire_dictionnaire, sosie_depuis_dictionnaire

    racine, config = trouver_projet()
    nom_projet = config["nom"] if config else ""
    seuil = args.seuil or (config or {}).get("seuil") or SEUIL_DEFAUT
    if seuil < 2:
        raise ErreurSosie("Le seuil doit être au moins 2.")
    garder = list(args.garder) if args.garder is not None else list((config or {}).get("garder") or [])
    copier_tel_quel = list(args.copier_tel_quel) if args.copier_tel_quel is not None else list((config or {}).get("copier_tel_quel") or [])
    cles_individu = list(args.cle_individu) if args.cle_individu is not None else list((config or {}).get("cle_individu") or [])
    if args.destination:
        destination = Path(args.destination).expanduser().resolve()
    elif racine is not None:
        destination = racine / DOSSIER_DONNEES
    else:
        raise ErreurSosie("Indique --destination, ou place-toi dans un projet sosie.")
    coffre = chemin_coffre()
    if est_dans(destination, coffre):
        raise ErreurSosie("Le sosie doit être écrit hors du coffre (c'est lui que l'IA lira).")
    suspects = contenu_suspect(destination)
    if suspects:
        raise ErreurSosie(
            f"{destination} contient des fichiers qui ne viennent pas de sosie ({', '.join(suspects[:5])}). "
            "Si ce sont de vraies données, déplace-les dans le coffre ; sinon range-les ailleurs, puis relance."
        )
    ignores, copies, avertissements = [], [], []
    tables = []
    fichiers = []
    controle = {}
    if args.depuis_schema:
        chemin_dico = Path(args.depuis_schema).expanduser()
        if not chemin_dico.exists():
            raise ErreurSosie(f"Dictionnaire introuvable : {chemin_dico}")
        try:
            lignes = lire_dictionnaire(chemin_dico)
            tables_ecriture, profil = sosie_depuis_dictionnaire(lignes, args.lignes, args.individus, args.graine)
        except (ValueError, KeyError) as e:
            raise ErreurSosie(f"Dictionnaire illisible : {e}")
        sosies = tables_ecriture
    else:
        refuser_si_claude("creer")
        if args.source:
            source = Path(args.source).expanduser().resolve()
        elif config:
            source = verifier_coffre_projet(racine, config) / DOSSIER_DONNEES
        else:
            raise ErreurSosie("Indique --source (dossier des vraies données), ou place-toi dans un projet sosie.")
        if not source.exists():
            raise ErreurSosie(f"Dossier introuvable : {source}")
        if est_dans(destination, source) or est_dans(source, destination):
            raise ErreurSosie("La source et la destination doivent être deux dossiers distincts.")
        liens = []
        fichiers = lister_fichiers(source, liens)
        for lien in liens:
            alerte(f"Dossier en lien symbolique ignoré : {lien} (dépose les fichiers eux-mêmes dans le coffre)")
        if not fichiers:
            raise ErreurSosie(f"Aucun fichier dans {source}. Dépose d'abord tes vraies données.")
        cibles = {}
        for chemin, rel in fichiers:
            from .formats import format_de
            cible = cle_nom(destination_de(rel, format_de(chemin))[0])
            if cible in cibles:
                raise ErreurSosie(f"« {cibles[cible]} » et « {rel} » donneraient le même fichier dans le sosie "
                                  "(noms identiques à la casse ou aux accents près) : renomme l'un des deux.")
            cibles[cible] = rel
        choisis = set()
        for demande in copier_tel_quel:
            cle = cle_nom(demande.strip().removeprefix("./"))
            trouves = [rel for _, rel in fichiers if cle_nom(rel) == cle]
            if not trouves:
                trouves = [rel for c, rel in fichiers if cle_nom(c.name) == cle]
            if len(trouves) > 1:
                raise ErreurSosie(f"« {demande} » désigne plusieurs fichiers ({', '.join(trouves[:5])}) : "
                                  f"indique le chemin complet, par exemple --copier-tel-quel \"{trouves[0]}\".")
            if not trouves:
                alerte(f"--copier-tel-quel {demande} : aucun fichier de ce nom dans le coffre du projet.")
            else:
                choisis.add(trouves[0])
        titre("Lecture des vraies données (dans le coffre)")
        for chemin, rel in fichiers:
            if rel in choisis:
                copies.append((chemin, rel))
                continue
            try:
                lus = lire_fichier(chemin, rel)
                tables.extend(lus)
                info(f"{rel} ({taille_lisible(chemin.stat().st_size)})")
                for t in lus:
                    avertissements += [f"{t.nom_affiche} : {a}" for a in t.options.get("avertissements_lecture", [])]
            except FormatNonPrisEnCharge as e:
                ignores.append((rel, str(e), str(e)))
            except Exception as e:
                ignores.append((rel, f"lecture impossible ({type(e).__name__} : {e})", f"lecture impossible ({type(e).__name__})"))
        if not tables and not copies:
            for rel, raison, _ in ignores:
                alerte(f"Non reproduit : {rel} — {raison}")
            raise ErreurSosie("Aucun fichier de données lisible (voir ci-dessus).")
        colonnes_inconnues(garder, tables, "--garder")
        colonnes_inconnues(cles_individu, tables, "--cle-individu")
        titre("Fabrication du sosie")
        total_lignes = sum(t.n_lignes for t in tables)
        if total_lignes >= 200_000:
            minutes = max(1, round(total_lignes / 600_000))
            info(f"{total_lignes:,} lignes au total : compte environ {minutes} minute(s), sans affichage pendant le calcul.".replace(",", " "))
        tables_ecriture, profil = fabriquer_sosie(tables, seuil, args.graine, garder, cles_individu, controle)
        sosies = [s for s, t in zip(tables_ecriture, tables) if not t.options.get("vide")]
    staging = destination / ".sosie_tmp"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        par_fichier = {}
        for t in tables_ecriture:
            par_fichier.setdefault(t.fichier, []).append(t)
        ecrits, echecs = [], set()
        for fichier, groupe in par_fichier.items():
            try:
                rel, av = ecrire_fichier(staging, groupe)
                ecrits.append(rel)
                avertissements += av
            except Exception as e:
                cible = staging / destination_de(fichier, groupe[0].format)[0]
                if cible.exists():
                    cible.unlink()
                ignores.append((fichier, f"écriture du sosie impossible ({type(e).__name__} : {e})",
                                f"écriture du sosie impossible ({type(e).__name__})"))
                echecs.add(fichier)
        for chemin, rel in copies:
            cible = staging / rel
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(chemin, cible)
            ecrits.append(rel)
        reussis = [k for k, s in enumerate(sosies) if s.fichier not in echecs]
        sosies_ok = [sosies[k] for k in reussis]
        profil_ok = dict(profil, tables=[profil["tables"][k] for k in reussis])
        rels = [destination_de(t.fichier, t.format)[0] for t in sosies_ok]
        fiche = rediger_fiche(sosies_ok, profil_ok, rels, avertissements, nom_projet,
                              [(rel, publique) for rel, _, publique in ignores], [rel for _, rel in copies])
        from . import fiche as module_fiche
        from .generation import mots_de
        vocabulaire = set(mots_de(Path(module_fiche.__file__).read_text(encoding="utf-8")))
        fiche = masquer_texte(fiche, frozenset(m for m in controle.get("sensibles") or () if m not in vocabulaire))
        (staging / FICHE).write_text(fiche, encoding="utf-8")
        (staging / MANIFESTE).write_text(json.dumps({
            "cree_le": dt.datetime.now().isoformat(timespec="seconds"),
            "origine": "dictionnaire" if args.depuis_schema else "donnees",
            "fichiers": ecrits,
            "graine": args.graine,
            "seuil": seuil,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        destination.mkdir(parents=True, exist_ok=True)
        remplacer_sosie(destination, staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    if not args.depuis_schema and config:
        coffre_projet = Path(config["coffre"])
        if coffre_projet.exists():
            (coffre_projet / ".profil_sosie.json").write_text(json.dumps(profil, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    resumer_profil(profil_ok)
    titre("Sosie prêt")
    bien(f"{len(ecrits)} fichier(s) écrit(s) dans {destination}")
    bien(f"Fiche descriptive pour toi et pour l'IA : {destination / FICHE}")
    info("Gardés tels quels : noms de fichiers, de feuilles, de colonnes et d'objets R, libellés de variables."
         " Vérifie qu'aucun ne contient un nom de patient.")
    for rel, raison, _ in ignores:
        alerte(f"Non reproduit : {rel} — {raison}")
    for a in avertissements:
        alerte(a)
    if controle.get("masques"):
        alerte("Valeurs ressemblant à des noms ou identifiants réels masquées par sécurité (« MODALITE_RARE ») dans : "
               + ", ".join(controle["masques"][:8]))
        info("Si l'une de ces colonnes contient des noms de personnes, signale-la : sosie creer --cle-individu ou renomme-la.")
    if copies:
        alerte("Copié(s) tel(s) quel(s) à ta demande, donc lisible(s) par l'IA : " + ", ".join(rel for _, rel in copies))
    copies_noms = {rel for _, rel in copies}
    for chemin, rel in fichiers:
        if rel not in copies_noms and any(m in cle_nom(Path(rel).stem) for m in MOTS_DICTIONNAIRE):
            info(f"Si « {rel} » ne contient aucune donnée personnelle (dictionnaire des variables…), l'IA peut le lire tel quel :")
            info(f"  sosie creer --copier-tel-quel \"{Path(rel).name}\"")
    for tp in profil_ok.get("tables", []):
        nom_t = tp["fichier"] + (f" [{tp['feuille']}]" if tp.get("feuille") else "")
        if tp.get("sans_individu") and not any(m in cle_nom(Path(tp["fichier"]).stem) for m in MOTS_DICTIONNAIRE):
            alerte(f"{nom_t} : aucun identifiant de patient repéré, chaque ligne compte comme un individu. Si une colonne "
                   "identifie le patient (même indirectement), relance : sosie creer --cle-individu NOM_DE_LA_COLONNE")
        elif tp.get("type_entite") == "secondaire":
            alerte(f"{nom_t} : pas de colonne patient, les modalités rares sont jugées par « {tp.get('entite')} » (un patient "
                   "peut en avoir plusieurs). Si une colonne identifie le patient : sosie creer --cle-individu NOM_DE_LA_COLONNE")
    if config and racine is not None and not args.depuis_schema and not args.destination:
        changements = {}
        if seuil != config.get("seuil"):
            changements["seuil"] = seuil
        for cle, valeur in (("garder", garder), ("copier_tel_quel", copier_tel_quel), ("cle_individu", cles_individu)):
            if list(valeur) != list(config.get(cle) or []):
                changements[cle] = valeur
        if changements:
            mettre_a_jour_toml_projet(racine, config, **changements)
            if "seuil" in changements:
                info(f"Seuil du projet enregistré : {seuil} (CLAUDE.md et sosie verifier l'utiliseront).")
        try:
            statut_md = ecrire_claude_md(racine, config["nom"], seuil)
        except OSError:
            statut_md = None
        if statut_md == "mis_a_jour":
            bien("Consignes pour l'IA (CLAUDE.md) mises à jour pour cette version de sosie.")
        elif statut_md in ("cree", "ajoute"):
            bien("Consignes pour l'IA ajoutées à CLAUDE.md.")
        options = [f"--garder {' '.join(garder)}" if garder else "", f"--copier-tel-quel {' '.join(copier_tel_quel)}" if copier_tel_quel else "",
                   f"--cle-individu {' '.join(cles_individu)}" if cles_individu else ""]
        options = [o for o in options if o]
        if options:
            info("Options mémorisées pour les prochains « sosie creer » : " + " ; ".join(options))
    if racine is not None and tables:
        signaler_donnees_exposees(racine, tables, seuil)
    return 0


def signaler_donnees_exposees(racine, tables, seuil):
    from .execution import fichiers_de_donnees_du_projet
    from .verification import BLOQUE, REVOIR, sensibles_depuis_tables, verifier_fichier

    exposes = fichiers_de_donnees_du_projet(racine) + fichiers_de_donnees_du_projet(racine, references=True)
    if not exposes:
        return
    sensibles = sensibles_depuis_tables(tables, seuil)
    reels, individuels = [], []
    for rel in exposes[:200]:
        try:
            statut, raisons, _, _ = verifier_fichier(racine / rel, rel, sensibles, seuil)
        except Exception:
            continue
        if statut == BLOQUE:
            reels.append(rel)
        elif statut == REVOIR and "données individuelles probables" in raisons:
            individuels.append(rel)
    if reels:
        print()
        alerte(style("VRAIES DONNÉES DANS LE PROJET (l'IA peut les lire) : ", "31") + ", ".join(reels[:10]))
        info("Déplace-les dans le coffre (ou supprime-les) tout de suite.")
    if individuels:
        print()
        alerte("Fichiers du projet qui ressemblent à des données individuelles (l'IA peut les lire) : " + ", ".join(individuels[:10]))
        info("S'ils viennent des vraies données, déplace-les dans le coffre ; s'ils sont fictifs ou publics, ignore ce message.")


RE_PAQUET_R = re.compile(r"there is no package called [‘'`\"]?([A-Za-z0-9._]+)")
RE_PAQUET_PY = re.compile(r"No module named [‘'`\"]?([A-Za-z0-9._]+)")


def diagnostiquer_echec(journal, infos):
    conseils_ = []
    paquets_r = sorted(set(RE_PAQUET_R.findall(journal)))
    paquets_py = sorted(set(RE_PAQUET_PY.findall(journal)))
    if paquets_r:
        conseils_.append(f"Paquet R manquant sur ce Mac : {', '.join(paquets_r)}. Installe-le dans R : "
                         f"install.packages(c({', '.join(repr(p) for p in paquets_r)})), puis relance.")
    if paquets_py:
        conseils_.append(f"Module Python manquant : {', '.join(paquets_py)} (installe-le dans l'environnement du projet, "
                         "par exemple : uv pip install …), puis relance.")
    if "jupyter-cache" in journal or "jupyter_cache" in journal:
        conseils_.append("Quarto demande le paquet Python jupyter-cache : installe-le (uv pip install jupyter-cache) ou relance.")
    if "R_TempDir" in journal:
        conseils_.append("R n'a pas pu créer son dossier temporaire : relance la commande ; si l'erreur revient, lance « sosie etat ».")
    if re.search(r"cannot open file|No such file or directory|FileNotFoundError|n'existe pas|does not exist", journal):
        conseils_.append("Un fichier attendu est absent : si un autre script le fabrique, lance-les à la suite "
                         "(sosie executer scripts/prepa.R scripts/analyse.R) ; s'il est statique (logo, liste de codes), "
                         "range-le dans references/.")
    if infos.get("bac_a_sable") and ("Operation not permitted" in journal or "Permission denied" in journal):
        conseils_.append("Le script a peut-être utilisé un chemin absolu (vers le projet, le Bureau…) : utilise des chemins "
                         "relatifs (donnees/…, resultats/…).")
    if re.search(r"command not found|introuvable|not found", journal) and not conseils_:
        conseils_.append("Un programme appelé par le script est introuvable sur ce Mac (R, Quarto, Python ?) : lance « sosie etat ».")
    return conseils_


def cmd_executer(args):
    from .execution import JOURNAL, executer

    refuser_si_claude("executer")
    racine, config = exiger_projet()
    controler_avant_execution(racine, config)
    dossier, code, infos = executer(racine, config, list(args.cible or []), afficher=args.afficher)
    try:
        journal = (dossier / JOURNAL).read_text(encoding="utf-8", errors="replace")
    except OSError:
        journal = ""
    if code == 0:
        titre("Exécution terminée")
    else:
        titre(f"✗ Le script s'est arrêté sur une erreur (code {code})")
        precis = diagnostiquer_echec(journal, infos)
        for c in precis:
            info(c)
        if not precis:
            info("L'erreur peut venir du code, ou d'une différence entre les vraies données et le sosie (modalité")
            info("inattendue, texte dans une colonne de nombres, colonne vide, doublons…).")
        info("Pour corriger avec l'IA sans lui montrer les données :")
        info("  1. sosie verifier   (le journal est copié pour l'IA s'il ne contient rien d'identifiant)")
        info(f"  2. Demande à l'IA : « Lis resultats_verifies/{dossier.name}/journal.txt et corrige le script. »")
        info(f"  Le message d'erreur exact est dans le journal (coffre) : open -e \"{dossier / JOURNAL}\"")
    produits = infos.get("produits") or []
    if produits:
        bien(f"{len(produits)} fichier(s) produit(s) (vraies données, restent dans le coffre) : "
             + ", ".join(produits[:6]) + (" …" if len(produits) > 6 else ""))
    else:
        info("Aucun fichier produit.")
    info(f"Dossier de l'exécution : {dossier}")
    if infos["quarantaine"]:
        alerte(f"{len(infos['quarantaine'])} fichier(s) écrit(s) par le script DANS le projet (chemin absolu ?) ont été "
               f"déplacés dans le coffre ({dossier / 'quarantaine'}) : " + ", ".join(infos["quarantaine"][:5]))
    if infos["signales"]:
        alerte("Fichiers du projet créés ou modifiés pendant l'exécution (par le script ou par l'IA en même temps) : "
               + ", ".join(infos["signales"][:5]) + " — vérifie qu'ils ne contiennent pas de vraies données.")
    if infos.get("exterieurs"):
        alerte("Fichiers écrits HORS du coffre pendant l'exécution (chemin absolu dans le script ?) : "
               + ", ".join(infos["exterieurs"][:5]))
        info("Ils peuvent contenir de vraies données lisibles par l'IA : vérifie-les et déplace-les dans le coffre.")
    info("Avant de montrer quoi que ce soit à l'IA : sosie verifier")
    if plateforme_mac() and args.ouvrir:
        subprocess.run(["open", str(dossier)], check=False)
    return code


def controler_avant_execution(racine, config):
    from .execution import fichiers_de_donnees_du_projet
    from .formats import lire_fichier, lister_fichiers
    from .verification import BLOQUE, REVOIR, sensibles_depuis_tables, verifier_fichier

    donnees = Path(config["coffre"]) / DOSSIER_DONNEES
    manifeste = racine / DOSSIER_DONNEES / MANIFESTE
    if manifeste.exists() and donnees.exists():
        try:
            m = json.loads(manifeste.read_text(encoding="utf-8"))
            cree = dt.datetime.fromisoformat(m.get("cree_le")).timestamp() if isinstance(m, dict) and m.get("cree_le") else None
        except (ValueError, OSError, TypeError):
            cree = None
        if cree is not None:
            recents = [p.name for p in donnees.rglob("*") if p.is_file() and not p.name.startswith(".") and p.stat().st_mtime > cree + 2]
            if recents:
                alerte(f"Les vraies données ont changé depuis la fabrication du sosie ({', '.join(recents[:3])}) : "
                       "relance « sosie creer » pour que l'IA travaille sur la bonne structure.")
    candidats = fichiers_de_donnees_du_projet(racine, references=True) + fichiers_de_donnees_du_projet(racine)
    if not candidats:
        return
    tables = []
    for chemin, rel in lister_fichiers(donnees):
        try:
            tables.extend(lire_fichier(chemin, rel))
        except Exception:
            continue
    if not tables:
        return
    sensibles = sensibles_depuis_tables(tables, config.get("seuil", SEUIL_DEFAUT))
    bloques, individuels = [], []
    for rel in candidats[:200]:
        chemin = racine / rel
        try:
            if chemin.stat().st_size > 200 * 1024 * 1024:
                continue
            statut, raisons, _, _ = verifier_fichier(chemin, rel, sensibles, config.get("seuil", SEUIL_DEFAUT))
        except Exception:
            continue
        if statut == BLOQUE:
            bloques.append(rel)
        elif statut == REVOIR and "données individuelles probables" in raisons:
            individuels.append(rel)
    if bloques:
        raise ErreurSosie(
            "Ces fichiers du projet contiennent de vraies données (identifiants, noms ou dates de naissance réels) et "
            f"L'IA peut les lire : {', '.join(bloques[:5])}. Déplace-les dans {donnees} (ou supprime-les), puis relance."
        )
    if individuels:
        alerte("Ces fichiers du projet ressemblent à des données individuelles (l'IA peut les lire) : "
               + ", ".join(individuels[:5]) + ". S'ils viennent des vraies données, déplace-les dans le coffre.")


def seuil_du_projet(args, config):
    projet = (config or {}).get("seuil") or SEUIL_DEFAUT
    if args.seuil is None:
        return projet
    if args.seuil < projet:
        raise ErreurSosie(f"Le seuil du projet est {projet} : un seuil plus bas ({args.seuil}) n'est pas accepté. "
                          f"Pour le changer : sosie creer --seuil N")
    return args.seuil


def cmd_verifier(args):
    from .execution import MANIFESTE_EXECUTION, derniere_execution
    from .verification import BLOQUE, LIBELLES, OK, conseils, verifier

    refuser_si_claude("verifier")
    racine, config = exiger_projet()
    seuil = seuil_du_projet(args, config)
    coffre_projet = Path(config["coffre"])
    executions = coffre_projet / "executions"
    noms = {p.name for p in executions.iterdir() if p.is_dir() and (p / MANIFESTE_EXECUTION).exists()} if executions.exists() else set()
    execution = args.execution
    forcer = list(args.forcer or [])
    if execution is None:
        avales = [f for f in forcer if f in noms]
        if avales:
            execution = avales[-1]
            forcer = [f for f in forcer if f not in avales]
    if execution:
        nom = Path(str(execution).rstrip("/")).name
        if nom not in noms:
            dernieres = sorted(noms)[-3:]
            raise ErreurSosie(f"Exécution introuvable : {execution}. Pour forcer un fichier : sosie verifier --forcer NOM_DU_FICHIER"
                              + (f"\n  Dernières exécutions : {', '.join(dernieres)}" if dernieres else ""))
        dossier = executions / nom
    else:
        dossier = derniere_execution(coffre_projet)
    if dossier is None or not dossier.exists():
        raise ErreurSosie("Aucune exécution à vérifier. Lance d'abord : sosie executer scripts/…")
    resultats, destination, copies = verifier(dossier, racine, seuil, forcer, coffre_projet / DOSSIER_DONNEES)
    titre(f"Vérification de {dossier.name}")
    if not resultats:
        info("Aucun fichier produit par cette exécution.")
    for r in resultats:
        libelle = "; ".join(r["raisons"]) or LIBELLES[r["statut"]]
        force = " (copié car forcé)" if r["force"] and r["statut"] != OK else ""
        print(f"  {r['statut']}  {r['affiche']} — {libelle}{force}")
        if r["statut"] != OK and not r["force"]:
            conseil = conseils(r, seuil, dossier)
            if conseil:
                print(f"       → {conseil}")
    print()
    if copies:
        bien(f"{len(copies)} fichier(s) partageable(s) copié(s) pour l'IA dans : {destination}")
    else:
        info(f"Aucun fichier copié pour l'IA. Le bilan (sans valeur réelle) est dans {destination / 'VERIFICATION.md'}")
    restes = [r for r in resultats if r["fichier"] not in copies]
    if restes:
        alerte(f"{len(restes)} fichier(s) gardé(s) dans le coffre. Détails (avec les valeurs) : {dossier / 'VERIFICATION_DETAILLEE.md'}")
        if any(r["statut"] != BLOQUE for r in restes):
            info("Après avoir regardé un fichier toi-même : sosie verifier --forcer NOM_DU_FICHIER")
    return 0


def cmd_pseudonymiser(args):
    from .pseudonymisation import pseudonymiser

    refuser_si_claude("pseudonymiser")
    racine, config = trouver_projet()
    coffre = chemin_coffre()
    coffre_projet = Path(config["coffre"]) if config else coffre / "_pseudonymisation"
    source = Path(args.source).expanduser().resolve() if args.source else (coffre_projet / DOSSIER_DONNEES if config else None)
    if source is None or not source.exists():
        raise ErreurSosie("Indique --source (dossier des données à pseudonymiser).")
    sortie = Path(args.sortie).expanduser().resolve() if args.sortie else coffre_projet / "pseudonymise"
    if est_dans(sortie, source) or est_dans(source, sortie):
        raise ErreurSosie("La sortie doit être un dossier distinct de la source (sinon les originaux seraient écrasés).")
    if not est_dans(sortie, coffre) and not args.forcer:
        raise ErreurSosie(
            "Des données pseudonymisées restent des données personnelles : la sortie doit rester dans le coffre. "
            "Ajoute --forcer si tu sais ce que tu fais (ex. transfert encadré à un co-investigateur)."
        )
    if racine is not None and est_dans(sortie, racine):
        raise ErreurSosie("Interdit : la sortie serait dans le dossier du projet, que l'IA lit.")
    rapport, ecrits, ignores, avertissements, correspondance, n = pseudonymiser(
        source, sortie, coffre_projet, seuil_du_projet(args, config), args.decaler_dates, args.naissance, args.garder_texte,
        args.forcer_colonne or [], args.cle_individu)
    titre("Pseudonymisation")
    actuel = None
    for table, colonne, action in rapport:
        if table != actuel:
            actuel = table
            print(f"  {table}")
        print(f"     {colonne} : {action}")
    print()
    bien(f"{len(ecrits)} fichier(s) écrit(s) dans {sortie}")
    bien(f"{n} pseudonyme(s) ; table de correspondance (dans le coffre) : {correspondance}")
    for rel, raison in ignores:
        alerte(f"Non traité : {rel} — {raison}")
    for a in avertissements:
        alerte(a)
    alerte("Données pseudonymisées = données personnelles : ne les envoie pas à une IA en ligne.")
    return 0


def cmd_reidentifier(args):
    from .pseudonymisation import reidentifier

    refuser_si_claude("reidentifier")
    racine, config = trouver_projet()
    coffre = chemin_coffre()
    coffre_projet = Path(config["coffre"]) if config else coffre / "_pseudonymisation"
    fichier = Path(args.fichier).expanduser().resolve()
    if not fichier.exists():
        raise ErreurSosie(f"Fichier introuvable : {fichier}")
    if args.sortie:
        destination = Path(args.sortie).expanduser().resolve()
    else:
        destination = coffre_projet / "reidentifie" / f"{fichier.stem}_reidentifie{fichier.suffix}"
    if racine is not None and est_dans(destination, racine):
        raise ErreurSosie("Interdit : la sortie serait dans le dossier du projet, que l'IA lit.")
    if destination.resolve() == fichier:
        raise ErreurSosie("La sortie doit être un autre fichier que l'entrée.")
    if not est_dans(destination, coffre):
        alerte("La sortie est hors du coffre : elle contiendra de vrais identifiants.")
    try:
        chemin, n = reidentifier(fichier, destination, coffre_projet)
    except RuntimeError as e:
        raise ErreurSosie(f"Réidentification impossible : {e}. Lance-la depuis le dossier du projet qui a servi à pseudonymiser.")
    if n == 0:
        alerte("Aucun pseudonyme reconnu : vérifie que le fichier vient bien de « sosie pseudonymiser » dans ce projet.")
    bien(f"{n} pseudonyme(s) remplacé(s) — fichier écrit : {chemin}")
    return 0


def cmd_schema(args):
    refuser_si_claude("schema")
    return dans_temporaire_du_coffre(exporter_schema, args)


def exporter_schema(args):
    from .config import verifier_coffre_projet
    from .formats import lire_fichier, lister_fichiers
    from .generation import profil_serialisable
    from .profil import profiler
    from .schema import exporter

    racine, config = trouver_projet()
    seuil = seuil_du_projet(args, config)
    if args.source:
        source = Path(args.source).expanduser().resolve()
    elif config:
        source = verifier_coffre_projet(racine, config) / DOSSIER_DONNEES
    else:
        raise ErreurSosie("Indique --source, ou place-toi dans un projet sosie.")
    tables = []
    for chemin, rel in lister_fichiers(source):
        try:
            tables.extend(t for t in lire_fichier(chemin, rel) if not t.options.get("vide"))
        except Exception as e:
            alerte(f"Ignoré : {rel} ({type(e).__name__})")
    if not tables:
        raise ErreurSosie(f"Aucune donnée lisible dans {source}")
    cles_individu = list(args.cle_individu) if getattr(args, "cle_individu", None) else list((config or {}).get("cle_individu") or [])
    par_table, structures = profiler(tables, seuil, (config or {}).get("garder") or (), cles_individu)
    profil = profil_serialisable(tables, par_table, structures, seuil)
    if args.avec_modalites:
        sans = [tp["fichier"] for tp in profil["tables"] if tp.get("sans_individu") or tp.get("type_entite") == "secondaire"]
        if sans:
            raise ErreurSosie(
                f"Pas de modalités sans savoir qui est le patient dans : {', '.join(sans[:5])}. Indique la colonne qui "
                "identifie le patient : sosie schema --avec-modalites --cle-individu COLONNE (ou LIGNE si chaque ligne est un patient différent)."
            )
    sortie = Path(args.sortie).expanduser() if args.sortie else (racine or Path.cwd()) / "dictionnaire_donnees.csv"
    n = exporter(tables, par_table, profil, sortie, args.avec_modalites)
    bien(f"Dictionnaire de {n} colonnes écrit : {sortie}")
    if args.avec_modalites:
        info(f"Il contient les modalités portées par au moins {seuil} individus et des plages de valeurs rognées.")
    else:
        info("Il ne contient aucune valeur : seulement la structure (fichiers, colonnes, types, formats, clés).")
    info("Pour fabriquer un sosie à partir de ce dictionnaire : sosie creer --depuis-schema " + sortie.name)
    return 0


def regles_presentes(reglages, coffre):
    from .config import sous_dict

    refus = sous_dict(reglages, "permissions").get("deny", [])
    refus = refus if isinstance(refus, list) else []
    return all(r in refus for r in regles_refus(coffre)[:4])


def commandes_exclues(*reglages):
    from .config import COMMANDES_SENSIBLES, sous_dict

    trouvees = []
    for r in reglages:
        exclues = sous_dict(r, "sandbox").get("excludedCommands", [])
        for c in exclues if isinstance(exclues, list) else []:
            premier = str(c).strip().split()[0].casefold() if str(c).strip() else ""
            if os.path.basename(premier) in COMMANDES_SENSIBLES or premier in COMMANDES_SENSIBLES:
                trouvees.append(str(c))
    return trouvees


def cmd_etat(args):
    from .config import sous_dict
    from .execution import derniere_execution, trouver_python, trouver_quarto
    from .formats import trouver_rscript

    coffre = chemin_coffre()
    titre("Coffre")
    if coffre.exists():
        bien(f"{coffre}")
    else:
        alerte(f"{coffre} n'existe pas encore : lance « sosie configurer »")
    utilisateur = lire_reglages(reglages_utilisateur_claude())
    if utilisateur is None:
        alerte(f"{reglages_utilisateur_claude()} n'est pas un JSON valide : Claude Code risque de l'ignorer.")
        utilisateur = {}
    if regles_presentes(utilisateur, coffre):
        bien("Claude Code a l'interdiction de lire le coffre (réglages utilisateur)")
    else:
        alerte("Interdictions du coffre absentes des réglages de Claude Code : lance « sosie configurer »")
    bac = sous_dict(utilisateur, "sandbox")
    mode = lire_config_globale().get("bac_a_sable", "global")
    if bac.get("enabled") and coffre_dans(bac, coffre):
        bien("Bac à sable de Claude Code activé pour tous les projets, coffre interdit")
    elif mode == "projets":
        info("Bac à sable activé seulement dans les projets sosie (pour l'activer partout : sosie configurer --bac-a-sable global)")
    else:
        alerte("Bac à sable global absent des réglages de Claude Code : lance « sosie configurer »")
    racine, config = trouver_projet()
    projet, local = {}, {}
    if racine is not None and not dans_claude():
        titre(f"Projet « {config['nom']} »")
        info(f"Dossier de travail : {racine}")
        info(f"Seuil des petits effectifs : {config.get('seuil', SEUIL_DEFAUT)}")
        donnees = Path(config["coffre"]) / DOSSIER_DONNEES
        fichiers = [p for p in donnees.rglob("*") if p.is_file() and not p.name.startswith(".")] if donnees.exists() else []
        info(f"Vraies données : {len(fichiers)} fichier(s) dans {donnees}")
        manifeste = racine / DOSSIER_DONNEES / MANIFESTE
        m = None
        if manifeste.exists():
            try:
                m = json.loads(manifeste.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                m = None
        if isinstance(m, dict):
            info(f"Sosie : fabriqué le {str(m.get('cree_le', '?')).replace('T', ' à ')} ({len(m.get('fichiers', []) or [])} fichier(s))")
            try:
                cree = dt.datetime.fromisoformat(str(m.get("cree_le"))).timestamp()
                recents = [f.name for f in fichiers if f.stat().st_mtime > cree + 2]
                if recents:
                    alerte(f"Vraies données modifiées depuis le sosie ({', '.join(recents[:3])}) : relance « sosie creer »")
            except (ValueError, TypeError, OSError):
                pass
        else:
            alerte("Sosie pas encore fabriqué : sosie creer")
        derniere = derniere_execution(config["coffre"])
        if derniere:
            info(f"Dernière exécution : {derniere.name}")
        projet = lire_reglages(racine / ".claude" / "settings.json") or {}
        local = lire_reglages(racine / ".claude" / "settings.local.json") or {}
        bac_projet, bac_local = sous_dict(projet, "sandbox"), sous_dict(local, "sandbox")
        actif = bac_projet.get("enabled", bac.get("enabled", False))
        if "enabled" in bac_local:
            actif = bac_local["enabled"]
        strict = bac_local.get("allowUnsandboxedCommands", bac_projet.get("allowUnsandboxedCommands", True)) is False \
            or bac.get("allowUnsandboxedCommands") is False
        if actif and strict:
            bien("Bac à sable actif et strict pour ce projet")
        else:
            cause = ".claude/settings.local.json (souvent écrit par /sandbox)" if bac_local else ".claude/settings.json"
            alerte(f"Bac à sable {'NON strict' if actif else 'DÉSACTIVÉ'} pour ce projet ({cause}).")
            info("Pour réparer : sosie projet .   (retire la désactivation de settings.local.json, avec une sauvegarde)")
    exclues = commandes_exclues(utilisateur, projet, local)
    if exclues:
        alerte("Commandes exclues du bac à sable (elles peuvent lire le coffre) : " + ", ".join(exclues)
               + ". Retire-les de « sandbox.excludedCommands » dans les réglages de Claude Code.")
    titre("Outils")
    info(f"R : {trouver_rscript() or 'introuvable'}")
    info(f"Quarto : {trouver_quarto() or 'introuvable'}")
    info(f"Python (pour tes scripts) : {trouver_python(racine) or 'introuvable'}")
    return 0


def coffre_dans(bac, coffre):
    filesystem = bac.get("filesystem") if isinstance(bac.get("filesystem"), dict) else {}
    refus = filesystem.get("denyRead", [])
    refus = refus if isinstance(refus, list) else []
    return any(Path(str(r)).expanduser() == coffre or str(r) == str(coffre).replace(str(Path.home()), "~") for r in refus)


def cmd_desinstaller(args):
    from .config import defaire_reglages

    refuser_si_claude("desinstaller")
    chemin = reglages_utilisateur_claude()
    changements = defaire_reglages(chemin)
    titre("Désinstallation de sosie")
    if changements:
        bien(f"Réglages ajoutés par sosie retirés de {chemin} (sauvegarde faite) :")
        for c in changements[:12]:
            info(c)
    else:
        info(f"Aucun réglage de sosie à retirer dans {chemin}.")
    origine = chemin.with_name(f"{chemin.name}.avant-sosie")
    if origine.exists():
        info(f"Ton fichier d'origine, avant sosie, reste disponible : {origine}")
    info("Les projets gardent leurs propres réglages (.claude/settings.json) : supprime-les si tu n'en veux plus.")
    coffre = chemin_coffre()
    alerte(f"Le coffre n'est PAS supprimé (tes vraies données) : {coffre}")
    info("Pour retirer l'outil lui-même : uv tool uninstall sosie")
    return 0


def cmd_autotest(args):
    from .autotest import lancer

    titre("Autotest de sosie (données d'essai fictives, dans un dossier temporaire effacé à la fin)")
    return lancer()


def construire_analyseur():
    p = Analyseur(prog="sosie", description=AIDE)
    p.add_argument("--version", action="version", version=f"sosie {__version__}")
    sous = p.add_subparsers(dest="commande", title="commandes", parser_class=Analyseur, metavar="COMMANDE")

    c = sous.add_parser("configurer", help="crée le coffre et interdit à Claude Code d'y accéder (une seule fois)")
    c.add_argument("--coffre", help="emplacement du coffre (par défaut ~/Coffre)")
    c.add_argument("--sans-claude", action="store_true", help="ne pas modifier les réglages de Claude Code")
    c.add_argument("--bac-a-sable", choices=["global", "projets"], default=None,
                   help="global (défaut) : bac à sable dans tous les projets ; projets : seulement dans les projets sosie")
    c.set_defaults(fonction=cmd_configurer)

    c = sous.add_parser("projet", help="crée un projet (dossier de travail + espace dans le coffre)")
    c.add_argument("nom", nargs="+", help="nom du projet (plusieurs mots possibles), ou « . » pour le dossier courant")
    c.add_argument("--dossier", help="dossier parent où créer le projet (par défaut : le dossier courant)")
    c.add_argument("--exemple", action="store_true", help="déposer des données d'exemple fictives dans le coffre (premier essai)")
    c.add_argument("--j-ai-verifie", action="store_true", help="accepter des fichiers de données hors de donnees/ (sans donnée personnelle)")
    c.add_argument("--ne-pas-ouvrir", action="store_true", help="ne pas ouvrir le dossier du coffre dans le Finder")
    c.add_argument("--seuil", type=int, default=None, help=f"seuil des petits effectifs du projet (défaut {SEUIL_DEFAUT})")
    c.set_defaults(fonction=cmd_projet)

    c = sous.add_parser("creer", aliases=["créer"], help="fabrique le sosie des vraies données")
    c.add_argument("--source", help="dossier des vraies données (par défaut : celui du projet dans le coffre)")
    c.add_argument("--destination", help="dossier du sosie (par défaut : donnees/ du projet)")
    c.add_argument("--seuil", type=int, default=None, help=f"nombre minimal d'individus pour garder une modalité (défaut : celui du projet, {SEUIL_DEFAUT})")
    c.add_argument("--cle-individu", nargs="+", metavar="COLONNE",
                   help="colonne(s) qui identifient le patient quand sosie ne la repère pas (LIGNE : chaque ligne est un patient différent)")
    c.add_argument("--graine", type=int, help="graine aléatoire pour un sosie reproductible")
    c.add_argument("--garder", nargs="+", metavar="COLONNE", help="garder les modalités fréquentes de ces colonnes à forte cardinalité")
    c.add_argument("--copier-tel-quel", nargs="+", metavar="FICHIER", help="fichiers sans donnée personnelle à copier tels quels (dictionnaire, notice…)")
    c.add_argument("--depuis-schema", metavar="DICTIONNAIRE", help="fabriquer le sosie à partir d'un dictionnaire de variables (sans vraies données)")
    c.add_argument("--lignes", type=int, default=500, help="avec --depuis-schema : nombre de lignes par table (défaut 500)")
    c.add_argument("--individus", type=int, default=100, help="avec --depuis-schema : nombre d'individus (défaut 100)")
    c.set_defaults(fonction=cmd_creer)

    c = sous.add_parser("executer", aliases=["exécuter"], help="lance un ou plusieurs scripts sur les vraies données, dans le coffre")
    c.add_argument("--ouvrir", action="store_true", help="ouvrir le dossier de l'exécution à la fin")
    c.add_argument("--afficher", action="store_true", help="afficher la sortie du script (vraies données !) : jamais dans un terminal lu par l'IA")
    c.add_argument("cible", nargs=argparse.REMAINDER,
                   help="script(s) (.R, .py, .qmd, .Rmd, .ipynb, .sh) à lancer à la suite, puis les arguments du dernier ; ou -- commande")
    c.set_defaults(fonction=cmd_executer)

    c = sous.add_parser("verifier", aliases=["vérifier"], help="contrôle les résultats d'une exécution avant de les montrer à l'IA")
    c.add_argument("execution", nargs="?", help="nom de l'exécution (par défaut : la dernière)")
    c.add_argument("--seuil", type=int, default=None, help=f"effectif minimal autorisé (défaut : celui du projet, {SEUIL_DEFAUT})")
    c.add_argument("--forcer", nargs="+", metavar="FICHIER", help="copier quand même ces fichiers après les avoir vérifiés toi-même")
    c.set_defaults(fonction=cmd_verifier)

    c = sous.add_parser("pseudonymiser", help="pseudonymisation réversible (reste dans le coffre)")
    c.add_argument("--source", help="dossier à pseudonymiser (par défaut : vraies données du projet)")
    c.add_argument("--sortie", help="dossier de sortie (par défaut : coffre/projet/pseudonymise)")
    c.add_argument("--decaler-dates", type=int, default=0, metavar="JOURS", help="décaler les dates de ±JOURS, de façon constante par individu")
    c.add_argument("--cle-individu", metavar="COLONNE", help="colonne qui identifie l'individu dans tous les fichiers (pour le décalage des dates)")
    c.add_argument("--naissance", choices=["mois", "annee", "garder"], default="mois", help="précision des dates de naissance (défaut : mois)")
    c.add_argument("--garder-texte", action="store_true", help="garder les textes libres (ils peuvent contenir des noms)")
    c.add_argument("--forcer-colonne", nargs="+", metavar="COLONNE", help="pseudonymiser aussi ces colonnes")
    c.add_argument("--seuil", type=int, default=None, help=argparse.SUPPRESS)
    c.add_argument("--forcer", action="store_true", help="autoriser une sortie hors du coffre")
    c.set_defaults(fonction=cmd_pseudonymiser)

    c = sous.add_parser("reidentifier", aliases=["réidentifier"], help="remplace les pseudonymes par les vrais identifiants")
    c.add_argument("fichier", help="fichier contenant des pseudonymes")
    c.add_argument("--sortie", help="fichier de sortie (par défaut : dans le coffre)")
    c.set_defaults(fonction=cmd_reidentifier)

    c = sous.add_parser("schema", aliases=["schéma"], help="exporte le dictionnaire des variables (structure, sans valeurs)")
    c.add_argument("--source", help="dossier des données (par défaut : vraies données du projet)")
    c.add_argument("-o", "--sortie", help="fichier CSV de sortie (par défaut : dictionnaire_donnees.csv)")
    c.add_argument("--avec-modalites", action="store_true", help="ajouter les modalités fréquentes et les plages de valeurs")
    c.add_argument("--cle-individu", nargs="+", metavar="COLONNE",
                   help="colonne(s) qui identifient le patient (LIGNE : chaque ligne est un patient différent)")
    c.add_argument("--seuil", type=int, default=None, help=argparse.SUPPRESS)
    c.set_defaults(fonction=cmd_schema)

    c = sous.add_parser("etat", aliases=["état"], help="affiche la configuration et l'état du projet")
    c.set_defaults(fonction=cmd_etat)

    c = sous.add_parser("autotest", help="vérifie sur des données d'essai que sosie fonctionne sur cet ordinateur")
    c.set_defaults(fonction=cmd_autotest)

    c = sous.add_parser("desinstaller", aliases=["désinstaller"], help="retire les réglages ajoutés à Claude Code (avant uv tool uninstall sosie)")
    c.set_defaults(fonction=cmd_desinstaller)
    return p


def journaliser_erreur(e):
    texte = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    try:
        coffre = chemin_coffre()
    except Exception:
        return None
    if coffre.exists():
        chemin = coffre / ".erreurs_sosie.txt"
        try:
            with open(chemin, "a", encoding="utf-8") as f:
                f.write(f"\n=== {dt.datetime.now().isoformat(timespec='seconds')} — sosie {__version__} ===\n{texte}")
            return chemin
        except OSError:
            return None
    return None


def lieu_erreur(e):
    for cadre in reversed(traceback.extract_tb(e.__traceback__)):
        if "/sosie/" in cadre.filename.replace("\\", "/"):
            return f"{Path(cadre.filename).name}:{cadre.lineno}"
    return "?"


def main(argv=None):
    warnings.filterwarnings("ignore")
    try:
        analyseur = construire_analyseur()
        args = analyseur.parse_args(argv)
    except KeyboardInterrupt:
        print("\nInterrompu.", file=sys.stderr)
        return 130
    if not getattr(args, "fonction", None):
        print(AIDE)
        return 0
    try:
        return args.fonction(args) or 0
    except ErreurSosie as e:
        print(style("✗ ", "31") + str(e), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrompu.", file=sys.stderr)
        return 130
    except BrokenPipeError:
        try:
            sys.stdout = open(os.devnull, "w")
        except OSError:
            pass
        return 0
    except Exception as e:
        chemin = journaliser_erreur(e)
        print(style("✗ ", "31") + f"Erreur inattendue de sosie ({type(e).__name__}, {lieu_erreur(e)}).", file=sys.stderr)
        if chemin:
            print(f"  Détails techniques (dans le coffre, ils peuvent contenir des valeurs réelles) : {chemin}", file=sys.stderr)
        print("  Tu peux copier les deux lignes ci-dessus à l'IA pour obtenir de l'aide (pas le fichier de détails).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
