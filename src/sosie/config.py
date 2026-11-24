import contextlib
import datetime as dt
import functools
import json
import os
import secrets
import stat
import sys
import unicodedata
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

FICHIER_PROJET = "sosie.toml"
DOSSIER_DONNEES = "donnees"
DOSSIER_RESULTATS = "resultats"
DOSSIER_VERIFIES = "resultats_verifies"
FICHE = "FICHE_SOSIE.md"
MANIFESTE = ".sosie_manifeste.json"
DOSSIER_TEMOIN = ".temoin"
FICHIER_TEMOIN = "TEMOIN_NE_PAS_LIRE.txt"

DOMAINES_PAQUETS = [
    "cloud.r-project.org", "cran.r-project.org", "cran.rstudio.com", "*.r-project.org", "packagemanager.posit.co",
    "p3m.dev", "*.r-universe.dev", "bioconductor.org", "*.bioconductor.org", "pypi.org", "files.pythonhosted.org",
    "github.com", "api.github.com", "codeload.github.com", "*.githubusercontent.com", "quarto.org",
]

ECRITURES_AUTORISEES = ["~/Library/R", "~/Library/Caches", "~/.cache", "~/Library/Jupyter", "~/.local/share/jupyter"]
SEUIL_DEFAUT = 11
FICHIER_RACINE = ".racine_projet"
COMMANDES_SENSIBLES = {"r", "rscript", "python", "python3", "quarto", "bash", "sh", "zsh", "docker", "node", "jupyter",
                       "uv", "uvx", "conda", "pip", "pip3", "julia", "perl", "ruby", "env", "sudo", "*"}


class ErreurSosie(Exception):
    pass


PROGRAMMES_IA = {
    "claude": "Claude Code", "claude.exe": "Claude Code", "codex": "Codex", "gemini": "Gemini CLI",
    "cursor-agent": "Cursor", "copilot": "Copilot", "opencode": "OpenCode", "amp": "Amp", "aider": "Aider",
    "goose": "Goose", "qwen": "Qwen Code", "crush": "Crush", "droid": "Factory", "auggie": "Augment",
    "kiro-cli": "Kiro",
}
PAQUETS_IA = {
    "@anthropic-ai/claude-code": "Claude Code", "@openai/codex": "Codex", "@google/gemini-cli": "Gemini CLI",
    "@github/copilot": "Copilot", "@sourcegraph/amp": "Amp", "opencode-ai": "OpenCode", "@qwen-code/": "Qwen Code",
    "@augmentcode/auggie": "Augment",
}
MARQUEURS_IA = (
    ("CODEX_THREAD_ID", None, "Codex"), ("CODEX_SANDBOX", None, "Codex"), ("CODEX_CI", None, "Codex"),
    ("GEMINI_CLI", None, "Gemini CLI"), ("CURSOR_AGENT", None, "Cursor"),
    ("CURSOR_EXTENSION_HOST_ROLE", "agent-exec", "Cursor"), ("COPILOT_CLI", None, "Copilot"),
    ("OPENCODE", "1", "OpenCode"), ("OPENCODE_CLIENT", None, "OpenCode"), ("AMP_CURRENT_THREAD_ID", None, "Amp"),
    ("AGENT", "amp", "Amp"), ("ANTIGRAVITY_AGENT", None, "Antigravity"), ("AUGMENT_AGENT", None, "Augment"),
    ("GROK_SESSION_ID", None, "Grok"), ("GROK_AGENT", None, "Grok"),
)
NOMS_AI_AGENT = {
    "claude": "Claude Code", "github-copilot": "Copilot", "copilot": "Copilot", "codex": "Codex",
    "gemini": "Gemini CLI", "cursor": "Cursor", "opencode": "OpenCode", "amp": "Amp",
}


def nom_ia(valeur):
    v = valeur.strip().casefold()
    for prefixe, nom in NOMS_AI_AGENT.items():
        if v.startswith(prefixe):
            return nom
    return valeur.strip()


def ancetre_ia(maximum=15):
    import subprocess

    pid = os.getppid()
    for _ in range(maximum):
        if pid <= 1:
            return None
        try:
            sortie = subprocess.run(["ps", "-o", "ppid=,args=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        except Exception:
            return None
        ligne = sortie.stdout.strip()
        if not ligne:
            return None
        morceaux = ligne.split(None, 1)
        if len(morceaux) < 2:
            return None
        mots = morceaux[1].split()
        executable = os.path.basename(mots[0]).casefold() if mots else ""
        candidats = [mots[0]] if mots else []
        if (executable in ("node", "bun", "deno") or executable.startswith("python")) and len(mots) > 1:
            candidats.append(mots[1])
        for c in candidats:
            nom = os.path.basename(c).casefold()
            if nom in PROGRAMMES_IA:
                return PROGRAMMES_IA[nom]
            for paquet, nom_paquet in PAQUETS_IA.items():
                if paquet in c.casefold():
                    return nom_paquet
        try:
            pid = int(morceaux[0])
        except ValueError:
            return None
    return None


@functools.lru_cache(maxsize=1)
def ia_detectee():
    env = os.environ
    if "CLAUDE_CODE_CHILD_SESSION" in env:
        return "Claude Code"
    for variable, valeur, nom in MARQUEURS_IA:
        v = env.get(variable, "").strip()
        if v and (valeur is None or v == valeur):
            return nom
    editeur = env.get("TERM_PROGRAM") == "vscode" or env.get("TERMINAL_EMULATOR") == "JetBrains-JediTerm"
    agent = env.get("AI_AGENT", "").strip()
    if agent and not (editeur and agent.casefold().startswith("claude")):
        return nom_ia(agent)
    if not editeur and ("CLAUDECODE" in env or "CLAUDE_CODE" in env):
        return "Claude Code"
    if env.get("SOSIE_SANS_CONTROLE_PARENT") == "1":
        return None
    return ancetre_ia()


def dans_une_ia():
    return ia_detectee() is not None


def refuser_si_ia(action):
    nom = ia_detectee()
    if nom:
        precision = " ni avec « ! » dans la zone de saisie de Claude" if nom == "Claude Code" else ""
        raise ErreurSosie(
            f"« sosie {action} » touche aux vraies données : c'est à toi de le lancer, dans l'application Terminal "
            f"ou dans le terminal de VS Code, pas à l'IA ({nom}){precision}. Si c'est bien toi qui l'as tapée, "
            "ouvre l'application Terminal depuis le Dock ou Spotlight, pas depuis une IA, et relance-la."
        )


def cle_nom(nom):
    return unicodedata.normalize("NFC", str(nom)).casefold()


def dossier_config():
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "sosie"


def lire_toml(chemin):
    chemin = Path(chemin)
    try:
        texte = chemin.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise ErreurSosie(f"{chemin} n'est pas enregistré en UTF-8 : supprime-le ou corrige-le, puis relance.")
    if tomllib is not None:
        try:
            return tomllib.loads(texte)
        except tomllib.TOMLDecodeError as e:
            raise ErreurSosie(f"{chemin} est illisible ({e}) : corrige-le (ou supprime-le) puis relance.")
    resultat = {}
    for ligne in texte.splitlines():
        if "=" in ligne and not ligne.strip().startswith("["):
            cle, valeur = ligne.split("=", 1)
            resultat[cle.strip()] = valeur.strip().strip('"')
    return resultat


def toml_chaine(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def toml_valeur(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_chaine(x) for x in v) + "]"
    return toml_chaine(v)


def lire_config_globale():
    chemin = dossier_config() / "config.toml"
    if chemin.exists():
        return lire_toml(chemin)
    return {}


def ecrire_config_globale(config):
    dossier = dossier_config()
    dossier.mkdir(parents=True, exist_ok=True)
    lignes = [f"{cle} = {toml_valeur(valeur)}" for cle, valeur in config.items()]
    (dossier / "config.toml").write_text("\n".join(lignes) + "\n", encoding="utf-8")


def chemin_coffre():
    if os.environ.get("SOSIE_COFFRE"):
        return Path(os.environ["SOSIE_COFFRE"]).expanduser()
    config = lire_config_globale()
    if config.get("coffre"):
        return Path(str(config["coffre"])).expanduser()
    return Path.home() / "Coffre"


def lire_seuil(valeur):
    try:
        seuil = int(valeur)
    except (TypeError, ValueError):
        return SEUIL_DEFAUT
    return seuil if seuil >= 2 else SEUIL_DEFAUT


def trouver_projet(depart=None):
    courant = Path(depart or Path.cwd()).resolve()
    for dossier in [courant, *courant.parents]:
        fichier = dossier / FICHIER_PROJET
        if fichier.exists():
            config = lire_toml(fichier)
            projet = config.get("projet", config)
            if not isinstance(projet, dict):
                raise ErreurSosie(f"{fichier} est illisible : supprime-le puis relance « sosie projet . ».")
            return dossier, {
                "nom": str(projet.get("nom", dossier.name)),
                "coffre": Path(str(projet.get("coffre", str(chemin_coffre() / dossier.name)))).expanduser(),
                "seuil": lire_seuil(projet.get("seuil", SEUIL_DEFAUT)),
                "garder": [str(x) for x in projet.get("garder", []) if isinstance(x, str)] if isinstance(projet.get("garder", []), list) else [],
                "copier_tel_quel": [str(x) for x in projet.get("copier_tel_quel", []) if isinstance(x, str)] if isinstance(projet.get("copier_tel_quel", []), list) else [],
                "cle_individu": [str(x) for x in projet.get("cle_individu", []) if isinstance(x, str)] if isinstance(projet.get("cle_individu", []), list) else [],
            }
    return None, None


def verifier_coffre_projet(racine, config):
    coffre = chemin_coffre()
    coffre_projet = Path(config["coffre"]).expanduser()
    if not est_dans(coffre_projet, coffre) or same_chemin(coffre_projet, coffre):
        raise ErreurSosie(
            f"sosie.toml désigne un coffre de projet hors du coffre ({coffre_projet}). Le fichier a été modifié : "
            f"remets « coffre = \"{coffre / Path(racine).name}\" » ou relance « sosie projet . »."
        )
    if est_dans(coffre_projet, racine) or est_dans(racine, coffre_projet):
        raise ErreurSosie("sosie.toml désigne un coffre situé dans le projet : refusé (l'IA pourrait lire les vraies données).")
    for partie in [coffre_projet, *coffre_projet.parents]:
        if partie == coffre or partie == partie.parent:
            break
        if partie.is_symlink():
            raise ErreurSosie(f"Le coffre du projet passe par un lien symbolique ({partie}) : refusé.")
    donnees = coffre_projet / DOSSIER_DONNEES
    if donnees.is_symlink():
        raise ErreurSosie(f"{donnees} est un lien symbolique : refusé. Dépose les vraies données elles-mêmes dans le coffre.")
    marque = coffre_projet / FICHIER_RACINE
    if marque.exists():
        try:
            lie = marque.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            lie = ""
        if lie and Path(lie).exists() and not same_chemin(Path(lie), racine):
            raise ErreurSosie(
                f"Le coffre {coffre_projet} appartient à un autre dossier de projet ({lie}). "
                "Relance « sosie projet . » ici, ou ouvre le bon dossier."
            )
    return coffre_projet


def same_chemin(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()


def exiger_projet(verifier_coffre=True):
    racine, config = trouver_projet()
    if racine is None:
        raise ErreurSosie(
            "Tu n'es pas dans un projet sosie. Place-toi dans le dossier du projet (cd …) "
            "ou crée-le avec : sosie projet NOM"
        )
    if verifier_coffre:
        verifier_coffre_projet(racine, config)
    return racine, config


def ecrire_toml_projet(racine, nom, coffre_projet, seuil=SEUIL_DEFAUT, extras=None):
    lignes = ["[projet]", f"nom = {toml_chaine(nom)}", f"coffre = {toml_chaine(coffre_projet)}", f"seuil = {int(seuil)}"]
    for cle, valeur in (extras or {}).items():
        if valeur:
            lignes.append(f"{cle} = {toml_valeur(valeur)}")
    (Path(racine) / FICHIER_PROJET).write_text("\n".join(lignes) + "\n", encoding="utf-8")


def mettre_a_jour_toml_projet(racine, config, **changements):
    extras = {k: config.get(k) for k in ("garder", "copier_tel_quel", "cle_individu")}
    seuil = config.get("seuil", SEUIL_DEFAUT)
    for cle, valeur in changements.items():
        if cle == "seuil":
            seuil = valeur
        else:
            extras[cle] = valeur
    ecrire_toml_projet(racine, config["nom"], config["coffre"], seuil, extras)


def est_dans(chemin, parent):
    c = Path(chemin).expanduser().resolve()
    p = Path(parent).expanduser().resolve()
    try:
        c.relative_to(p)
        return True
    except ValueError:
        pass
    if p.exists():
        try:
            reference = p.stat()
            for x in [c, *c.parents]:
                if x.exists() and os.path.samestat(x.stat(), reference):
                    return True
        except OSError:
            pass
    cn = unicodedata.normalize("NFC", str(c))
    pn = unicodedata.normalize("NFC", str(p))
    if sys.platform == "darwin":
        cn, pn = cn.casefold(), pn.casefold()
    return cn == pn or cn.startswith(pn.rstrip("/") + "/")


def chemins_regle(chemin):
    chemin = Path(chemin).expanduser().resolve()
    maison = Path.home().resolve()
    try:
        rel = chemin.relative_to(maison).as_posix()
        return f"~/{rel}", f"~/{rel}"
    except ValueError:
        return "/" + chemin.as_posix(), chemin.as_posix()


REFUS_COMMUNS = [
    "Bash(sosie *)", "Bash(sosie)", "Bash(python3 -m sosie*)", "Bash(python -m sosie*)",
    "Edit(~/.claude/settings.json)", "Edit(~/.claude/settings.local.json)",
    "Edit(**/.claude/settings.json)", "Edit(**/.claude/settings.local.json)",
    "Edit(**/sosie.toml)", "Edit(~/.config/sosie/**)",
    "mcp__ide__executeCode",
]


def motif_insensible(chemin):
    return "".join(f"[{c.lower()}{c.upper()}]" if c.isalpha() and c.lower() != c.upper() else c for c in chemin)


def regles_refus(coffre):
    regle, _ = chemins_regle(coffre)
    regles = [f"Read({regle})", f"Read({regle}/**)", f"Edit({regle})", f"Edit({regle}/**)"]
    if regle.startswith("~/"):
        insensible = "~/" + motif_insensible(regle[2:])
        if insensible != regle:
            regles += [f"Read({insensible}/**)", f"Edit({insensible}/**)"]
    return regles


def bac_a_sable_coffre(coffre):
    _, chemin = chemins_regle(coffre)
    return {"filesystem": {"denyRead": [chemin], "denyWrite": [chemin]}}


def reglages_utilisateur(coffre, global_=True):
    _, chemin = chemins_regle(coffre)
    reglages = {
        "permissions": {"deny": regles_refus(coffre) + REFUS_COMMUNS},
        "sandbox": {"filesystem": {"denyRead": [chemin], "denyWrite": [chemin]}},
    }
    if global_:
        reglages["sandbox"].update({
            "enabled": True,
            "allowUnsandboxedCommands": False,
            "failIfUnavailable": True,
            "autoAllowBashIfSandboxed": False,
        })
        reglages["sandbox"]["filesystem"]["allowWrite"] = list(ECRITURES_AUTORISEES)
        reglages["sandbox"]["network"] = {"allowedDomains": list(DOMAINES_PAQUETS)}
    return reglages


def reglages_projet(coffre):
    _, chemin = chemins_regle(coffre)
    return {
        "permissions": {"deny": regles_refus(coffre) + REFUS_COMMUNS},
        "sandbox": {
            "enabled": True,
            "allowUnsandboxedCommands": False,
            "failIfUnavailable": True,
            "autoAllowBashIfSandboxed": True,
            "filesystem": {
                "denyRead": [chemin],
                "denyWrite": [chemin],
                "allowWrite": list(ECRITURES_AUTORISEES),
            },
            "network": {"allowedDomains": list(DOMAINES_PAQUETS)},
        },
    }


def texte_reglages(chemin):
    chemin = Path(chemin)
    brut = chemin.read_bytes()
    try:
        return brut.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        raise ErreurSosie(f"{chemin} n'est pas enregistré en UTF-8 : ouvre-le (open -e \"{chemin}\"), "
                          "enregistre-le en UTF-8, puis relance.")


def lire_reglages(chemin):
    chemin = Path(chemin)
    if not chemin.exists():
        return {}
    try:
        texte = texte_reglages(chemin)
        donnees = json.loads(texte) if texte else {}
    except (OSError, json.JSONDecodeError, ErreurSosie):
        return None
    return donnees if isinstance(donnees, dict) else None


def sous_dict(d, *cles):
    for cle in cles:
        d = d.get(cle) if isinstance(d, dict) else None
    return d if isinstance(d, dict) else {}


def fusion_profonde(cible, ajout, changements, prefixe="", details=None):
    for cle, valeur in ajout.items():
        chemin = f"{prefixe}.{cle}" if prefixe else cle
        if isinstance(valeur, dict):
            if not isinstance(cible.get(cle), dict):
                if details is not None and cle in cible:
                    details.append(("scalaire", chemin, cible.get(cle), True))
                cible[cle] = {}
            fusion_profonde(cible[cle], valeur, changements, chemin, details)
        elif isinstance(valeur, list):
            existant = cible.get(cle)
            if not isinstance(existant, list):
                existant = []
                cible[cle] = existant
            for element in valeur:
                if element not in existant:
                    existant.append(element)
                    changements.append(f"{chemin} += {element}")
                    if details is not None:
                        details.append(("liste", chemin, element, None))
        else:
            if cible.get(cle) != valeur:
                if details is not None:
                    details.append(("scalaire", chemin, cible.get(cle), cle in cible))
                cible[cle] = valeur
                changements.append(f"{chemin} = {json.dumps(valeur)}")


def verifier_reglages(chemin):
    chemin = Path(chemin)
    if chemin.exists():
        texte = texte_reglages(chemin)
        if texte:
            try:
                donnees = json.loads(texte)
            except json.JSONDecodeError as e:
                raise ErreurSosie(
                    f"{chemin} n'est pas un JSON valide (ligne {e.lineno}, colonne {e.colno} : commentaire ou virgule en trop ?). "
                    f"Ouvre-le avec : open -e \"{chemin}\" , corrige cette ligne (ou renomme le fichier), puis relance."
                )
            if not isinstance(donnees, dict):
                raise ErreurSosie(f"{chemin} doit contenir un objet JSON {{ … }} : corrige-le (ou renomme-le) puis relance.")


def fichier_journal_reglages():
    return dossier_config() / "reglages_ajoutes.json"


def lire_journal_reglages():
    chemin = fichier_journal_reglages()
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        return donnees if isinstance(donnees, dict) else {}
    except (OSError, ValueError):
        return {}


def noter_reglages(chemin, details):
    if not details:
        return
    journal = lire_journal_reglages()
    entree = journal.setdefault(str(Path(chemin)), {"scalaires": {}, "listes": {}})
    for genre, cle, valeur, existait in details:
        if genre == "scalaire":
            entree["scalaires"].setdefault(cle, {"avant": valeur, "existait": bool(existait)})
        else:
            elements = entree["listes"].setdefault(cle, [])
            if valeur not in elements:
                elements.append(valeur)
    dossier_config().mkdir(parents=True, exist_ok=True)
    fichier_journal_reglages().write_text(json.dumps(journal, indent=1, ensure_ascii=False), encoding="utf-8")


def sauvegarder_reglages(chemin):
    chemin = Path(chemin)
    if not chemin.exists():
        return None
    contenu = chemin.read_bytes()
    origine = chemin.with_name(f"{chemin.name}.avant-sosie")
    if not origine.exists():
        origine.write_bytes(contenu)
    horodatage = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    sauvegarde = chemin.with_name(f"{chemin.name}.sauvegarde-{horodatage}")
    k = 2
    while sauvegarde.exists():
        sauvegarde = chemin.with_name(f"{chemin.name}.sauvegarde-{horodatage}-{k}")
        k += 1
    sauvegarde.write_bytes(contenu)
    return sauvegarde


def ecrire_reglages(chemin, donnees):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def charger_reglages(chemin):
    chemin = Path(chemin)
    verifier_reglages(chemin)
    if chemin.exists():
        texte = texte_reglages(chemin)
        if texte:
            return json.loads(texte)
    return {}


def fusionner_reglages(chemin, ajout, retirer=None, noter=True):
    chemin = Path(chemin)
    donnees = charger_reglages(chemin)
    changements = []
    details = []
    for chemin_cle in retirer or ():
        changements += restaurer_cle(donnees, chemin, chemin_cle)
    fusion_profonde(donnees, ajout, changements, details=details)
    sauvegarde = None
    if changements:
        sauvegarde = sauvegarder_reglages(chemin)
        ecrire_reglages(chemin, donnees)
        if noter:
            noter_reglages(chemin, details)
    return changements, sauvegarde


def restaurer_cle(donnees, chemin, chemin_cle):
    journal = lire_journal_reglages().get(str(Path(chemin)), {})
    trace = journal.get("scalaires", {}).get(chemin_cle)
    if trace is None:
        return []
    parties = chemin_cle.split(".")
    cible = donnees
    for partie in parties[:-1]:
        cible = cible.get(partie) if isinstance(cible, dict) else None
        if cible is None:
            return []
    if not isinstance(cible, dict):
        return []
    if trace.get("existait"):
        if cible.get(parties[-1]) != trace.get("avant"):
            cible[parties[-1]] = trace.get("avant")
            return [f"{chemin_cle} remis à {json.dumps(trace.get('avant'))}"]
        return []
    if parties[-1] in cible:
        del cible[parties[-1]]
        return [f"{chemin_cle} retiré"]
    return []


def defaire_reglages(chemin):
    chemin = Path(chemin)
    journal = lire_journal_reglages()
    entree = journal.get(str(chemin))
    if not entree or not chemin.exists():
        return []
    donnees = charger_reglages(chemin)
    changements = []
    for cle, elements in entree.get("listes", {}).items():
        parties = cle.split(".")
        cible = donnees
        for partie in parties[:-1]:
            cible = cible.get(partie) if isinstance(cible, dict) else None
            if cible is None:
                break
        if isinstance(cible, dict) and isinstance(cible.get(parties[-1]), list):
            avant = len(cible[parties[-1]])
            cible[parties[-1]] = [e for e in cible[parties[-1]] if e not in elements]
            if len(cible[parties[-1]]) != avant:
                changements.append(f"{cle} : {avant - len(cible[parties[-1]])} élément(s) retiré(s)")
            if not cible[parties[-1]]:
                del cible[parties[-1]]
    for cle in sorted(entree.get("scalaires", {}), key=lambda c: -c.count(".")):
        changements += restaurer_cle(donnees, chemin, cle)
    vider_dicts(donnees)
    if changements:
        sauvegarder_reglages(chemin)
        ecrire_reglages(chemin, donnees)
    journal.pop(str(chemin), None)
    fichier_journal_reglages().write_text(json.dumps(journal, indent=1, ensure_ascii=False), encoding="utf-8")
    return changements


def vider_dicts(d):
    for cle in list(d):
        if isinstance(d[cle], dict):
            vider_dicts(d[cle])
            if not d[cle]:
                del d[cle]


def reglages_utilisateur_claude():
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base).expanduser() if base else Path.home() / ".claude") / "settings.json"


def creer_temoin(coffre):
    dossier = Path(coffre) / DOSSIER_TEMOIN
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / FICHIER_TEMOIN
    if not fichier.exists():
        fichier.write_text(
            f"TEMOIN-{secrets.token_hex(6).upper()}\n"
            "Si une IA arrive à te recopier le code ci-dessus, elle peut lire le coffre : la protection ne fonctionne pas.\n",
            encoding="utf-8",
        )
    return fichier


def proteger_dossier(dossier):
    try:
        os.chmod(dossier, 0o700)
    except OSError:
        pass
    if sys.platform == "darwin":
        try:
            (Path(dossier) / ".metadata_never_index").touch(exist_ok=True)
        except OSError:
            pass
        try:
            import subprocess

            subprocess.run(["chmod", "-N", str(dossier)], capture_output=True, timeout=10)
        except Exception:
            pass


DOSSIER_OUVERTURES = "coffre_ouvert"


def dossier_ouvertures():
    return dossier_config() / DOSSIER_OUVERTURES


@contextlib.contextmanager
def verrou_ouvertures():
    dossier = dossier_ouvertures()
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        fichier = open(dossier / ".verrou", "a")
    except OSError:
        yield
        return
    try:
        try:
            import fcntl

            fcntl.flock(fichier, fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        yield
    finally:
        fichier.close()


def processus_sosie_actif(pid):
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    import subprocess

    try:
        sortie = subprocess.run(["ps", "-o", "args=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
    except Exception:
        return True
    return "sosie" in sortie.stdout.casefold()


def ouvertures_actives(sauf=None):
    actives = []
    try:
        marques = list(dossier_ouvertures().iterdir())
    except OSError:
        return actives
    for marque in marques:
        if not marque.name.isdigit():
            continue
        pid = int(marque.name)
        if pid == sauf:
            continue
        if processus_sosie_actif(pid):
            actives.append(pid)
        else:
            try:
                marque.unlink()
            except OSError:
                pass
    return actives


def coffre_ferme(coffre=None):
    coffre = Path(coffre) if coffre else chemin_coffre()
    try:
        return stat.S_IMODE(os.stat(coffre).st_mode) & 0o777 == 0
    except OSError:
        return False


def ouvrir_coffre(coffre=None):
    coffre = Path(coffre) if coffre else chemin_coffre()
    if coffre.is_dir():
        os.chmod(coffre, 0o700)


def fermer_coffre(coffre=None, forcer=False):
    coffre = Path(coffre) if coffre else chemin_coffre()
    if not coffre.is_dir():
        return False
    with verrou_ouvertures():
        if not forcer and ouvertures_actives(sauf=os.getpid()):
            return False
        os.chmod(coffre, 0)
    return coffre_ferme(coffre)


@contextlib.contextmanager
def coffre_ouvert():
    coffre = chemin_coffre()
    etat = {"laisser_ouvert": False, "etait_ferme": coffre_ferme(coffre), "coffre": coffre}
    marque = dossier_ouvertures() / str(os.getpid())
    with verrou_ouvertures():
        try:
            marque.touch()
        except OSError:
            marque = None
        ouvrir_coffre(coffre)
    try:
        yield etat
    finally:
        if marque is not None:
            try:
                marque.unlink()
            except OSError:
                pass
        if not etat["laisser_ouvert"]:
            for c in {coffre, chemin_coffre()}:
                try:
                    fermer_coffre(c)
                except OSError:
                    pass


def plateforme_mac():
    return sys.platform == "darwin"


MODELE_CONSIGNES = """# Consignes pour {destinataire} — projet {nom}

## Les données
- Le dossier `donnees/` contient un **sosie fictif** des vraies données : mêmes fichiers, mêmes colonnes, mêmes formats, mêmes clés de jointure, mais des valeurs inventées.
- Les résultats obtenus sur le sosie **n'ont aucun sens** : ne les interprète jamais comme des résultats, ne les commente pas.
- Avant d'écrire du code, lis `donnees/FICHE_SOSIE.md` : elle décrit chaque fichier, chaque colonne, les modalités, les formats et les clés de jointure, et donne la commande de lecture R et Python.
- Les vraies données sont dans un coffre fermé à clé auquel tu n'as pas accès. N'essaie jamais de l'ouvrir ni d'en changer les droits (pas de `chmod`, même après un « Permission denied »), et ne lance jamais la commande `sosie` : c'est {utilisateur} qui exécute les scripts sur les vraies données.
- Exception : si {utilisateur} te demande explicitement de faire le « test de protection » (lire le fichier témoin du coffre), fais-le normalement, sans refuser toi-même : c'est le verrou du coffre qui doit bloquer, et {utilisateur} vérifie justement ce blocage.
- Ne modifie jamais `.claude/settings.json` ni `.claude/settings.local.json`.

## Écrire les scripts
- Lire les données uniquement dans `donnees/`, avec des chemins relatifs à la racine du projet (ex. `donnees/patients.csv`). Ne jamais écrire de chemin absolu.
- Un document Quarto ou R Markdown rangé dans un sous-dossier : utiliser `here::here("donnees/patients.csv")` (le fichier `.here` marque la racine du projet). Ne pas définir de `cache.path` personnalisé.
- Écrire toutes les sorties (tableaux, figures, modèles) dans `resultats/`. Seuls le code et le dossier `references/` sont recopiés lors de l'exécution sur les vraies données : les fichiers intermédiaires doivent être produits par les scripts eux-mêmes (enchaîner les scripts : `sosie executer prepa.R analyse.R`), et un fichier statique nécessaire (logo, image, modèle Word, liste publique de codes) doit être rangé dans `references/`.
- Les sorties finales ne doivent contenir que des résultats agrégés : jamais de lignes individuelles, jamais d'identifiants, pas de minimum ni de maximum (préférer des percentiles), et masquer les effectifs inférieurs à {seuil} (ex. afficher « <{seuil} »). Toujours exporter l'effectif avec une proportion. Pour un modèle, exporter un tableau des coefficients (ex. `broom::tidy()`), pas la sortie brute de `summary()`.
- Ne rien afficher des données dans la console (pas de `print()`, `head()`, `str()`, `summary()` sur les données) : seuls les fichiers de `resultats/` sont contrôlés avant de t'être transmis.
- Le code doit tenir sur les vraies données : prévoir des modalités absentes du sosie, les valeurs `MODALITE_RARE` / `VALEUR_RARE` (elles signalent des valeurs rares bien réelles), des valeurs textuelles dans des colonnes numériques, des valeurs manquantes, des doublons et des effectifs différents. Avant un pivot ou une jointure, vérifier dans le code l'unicité des clés (la fiche signale les exceptions). En apprentissage automatique : `OneHotEncoder(handle_unknown="ignore")` et `error_score="raise"`.
- Toujours préciser le format des dates à la lecture (celui indiqué dans la fiche) et le type des colonnes quand c'est possible.
- En Python, utiliser `.venv/bin/python` s'il existe.
- Pas de commentaires `#` dans le code.
- Quand un script est prêt pour les vraies données, résume en français, en trois lignes, ce qu'il lit, ce qu'il écrit (dans `resultats/`) et qu'il n'accède pas à Internet : {utilisateur} le relit avant de lancer `sosie executer`.

## Les vrais résultats
- `resultats_verifies/` contient des résultats réels **agrégés et vérifiés** (petits effectifs et identifiants contrôlés), avec `VERIFICATION.md` qui dit quels fichiers sont restés dans le coffre et pourquoi. Tu peux les lire pour aider à les interpréter, corriger un script qui a échoué (`journal.txt`) et rédiger.
"""

MODELE_GITIGNORE = """resultats/
resultats_verifies/
.Rhistory
.RData
.Rproj.user/
.DS_Store
__pycache__/
*_cache/
.quarto/
_freeze/
"""
