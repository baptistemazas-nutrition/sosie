import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEPOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPOT / "src"))
TMP = Path(tempfile.mkdtemp(prefix="sosie-verrou-"))
os.environ["XDG_CONFIG_HOME"] = str(TMP / "config")
os.environ["SOSIE_COFFRE"] = str(TMP / "Coffre")

from sosie.cli import FICHIERS_CONSIGNES, ecrire_consignes
from sosie.config import MODELE_CONSIGNES, coffre_ferme, coffre_ouvert, fermer_coffre, ouvrir_coffre

echecs = []


def verifier(condition, message):
    print(("  OK   " if condition else "  ÉCHEC ") + message)
    if not condition:
        echecs.append(message)


ADMIN = os.geteuid() == 0
COFFRE = Path(os.environ["SOSIE_COFFRE"])
(COFFRE / "PROJET").mkdir(parents=True)
VRAIES = COFFRE / "PROJET" / "vraies.csv"
VRAIES.write_text("id;nom\n1;NOMREEL\n", encoding="utf-8")


def lisible():
    try:
        VRAIES.read_text(encoding="utf-8")
        return True
    except PermissionError:
        return False


print("1. Coffre fermé à clé")
fermer_coffre()
verifier(coffre_ferme(), "fermé : droits 000")
verifier(ADMIN or not lisible(), "fermé : vraies données illisibles pour tout programme")
with coffre_ouvert():
    verifier(not coffre_ferme() and lisible(), "pendant une commande sosie : ouvert")
verifier(coffre_ferme(), "après la commande : refermé à clé")
with coffre_ouvert() as etat:
    etat["laisser_ouvert"] = True
verifier(not coffre_ferme(), "« sosie coffre ouvrir » : reste ouvert")
fermer_coffre()
verifier(coffre_ferme(), "« sosie coffre fermer » : refermé")

print("2. Une commande sosie en cours garde le coffre ouvert")
code = (f"import sys, time\nsys.path.insert(0, {str(DEPOT / 'src')!r})\n"
        "from sosie.config import coffre_ouvert\nwith coffre_ouvert():\n    time.sleep(4)\n")
autre = subprocess.Popen([sys.executable, "-c", code])
time.sleep(1.5)
verifier(not coffre_ferme(), "ouvert par l'autre commande")
fermer_coffre()
verifier(not coffre_ferme(), "« sosie coffre fermer » attend la fin de l'autre commande")
autre.wait()
verifier(coffre_ferme(), "refermé à clé quand l'autre commande a fini")

print("3. IA détectées")
LANCEUR = TMP / "lanceur.sh"
LANCEUR.write_text('#!/bin/bash\nnom="$1"\nshift\nexec -a "$nom" bash -c \'"$@"; exit $?\' bash "$@"\n', encoding="utf-8")
LANCEUR.chmod(0o755)
BASE = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(TMP), "PYTHONPATH": str(DEPOT / "src")}
CODE = "from sosie.config import ia_detectee; print(ia_detectee() or '')"


def detecte(variables, ancetre=None):
    env = dict(BASE, **variables)
    commande = [sys.executable, "-c", CODE]
    if ancetre:
        commande = [str(LANCEUR), ancetre, *commande]
    else:
        env["SOSIE_SANS_CONTROLE_PARENT"] = "1"
    return subprocess.run(commande, env=env, capture_output=True, text=True).stdout.strip()


cas = [
    ({}, "", "terminal ordinaire"),
    ({"CODEX_THREAD_ID": "t1"}, "Codex", "Codex (CODEX_THREAD_ID)"),
    ({"CODEX_SANDBOX": "seatbelt"}, "Codex", "Codex (bac à sable)"),
    ({"GEMINI_CLI": "1"}, "Gemini CLI", "Gemini CLI"),
    ({"CURSOR_AGENT": "1", "TERM_PROGRAM": "vscode"}, "Cursor", "agent de Cursor"),
    ({"CURSOR_EXTENSION_HOST_ROLE": "agent-exec"}, "Cursor", "agent de Cursor (extension)"),
    ({"AI_AGENT": "github-copilot"}, "Copilot", "Copilot (AI_AGENT)"),
    ({"OPENCODE": "1"}, "OpenCode", "OpenCode"),
    ({"AGENT": "amp"}, "Amp", "Amp"),
    ({"CLAUDECODE": "1"}, "Claude Code", "Claude Code"),
    ({"CLAUDECODE": "1", "TERM_PROGRAM": "vscode"}, "", "terminal de VS Code ouvert depuis Claude Code (humain)"),
    ({"AI_AGENT": "claude-code/2", "TERM_PROGRAM": "vscode"}, "", "terminal de VS Code avec AI_AGENT hérité (humain)"),
    ({"CURSOR_TRACE_ID": "abc", "TERM_PROGRAM": "vscode"}, "", "terminal de Cursor tapé par un humain"),
]
for variables, attendu, quoi in cas:
    obtenu = detecte(variables)
    verifier(obtenu == attendu, f"{quoi} : « {obtenu or 'aucune IA'} »")
for programme, attendu in (("codex", "Codex"), ("gemini", "Gemini CLI"), ("cursor-agent", "Cursor"), ("aider", "Aider")):
    obtenu = detecte({}, programme)
    verifier(obtenu == attendu, f"lancé depuis le programme « {programme} » : « {obtenu or 'aucune IA'} »")

print("4. Consignes pour toutes les IA")
projet = TMP / "projet"
projet.mkdir()
statuts = ecrire_consignes(projet, "ESSAI", 11)
for fichier, destinataire in FICHIERS_CONSIGNES:
    texte = (projet / fichier).read_text(encoding="utf-8")
    verifier(statuts.get(fichier) == "cree" and texte.startswith(f"# Consignes pour {destinataire} — projet ESSAI")
             and "fermé à clé" in texte, f"{fichier} créé")
ancien = MODELE_CONSIGNES.format(destinataire="Claude", nom="ESSAI", utilisateur="l'utilisateur", seuil=11)
ancien = ancien.replace(
    "un coffre fermé à clé auquel tu n'as pas accès. N'essaie jamais de l'ouvrir ni d'en changer les droits "
    "(pas de `chmod`, même après un « Permission denied »), et ne lance jamais",
    "un coffre auquel tu n'as pas accès. N'essaie jamais d'y accéder et ne lance jamais",
).replace("c'est le verrou du coffre qui doit bloquer", "c'est Claude Code et macOS qui doivent bloquer")
verifier("fermé à clé" not in ancien and "Claude Code et macOS" in ancien, "consignes de la version 1.2 reconstituées")
(projet / "CLAUDE.md").write_text("Mes notes\n\n" + ancien + "\nNote finale\n", encoding="utf-8")
statuts = ecrire_consignes(projet, "ESSAI", 11)
texte = (projet / "CLAUDE.md").read_text(encoding="utf-8")
verifier(statuts.get("CLAUDE.md") == "mis_a_jour" and "fermé à clé" in texte and "Claude Code et macOS" not in texte
         and texte.startswith("Mes notes") and texte.rstrip().endswith("Note finale"), "ancien CLAUDE.md mis à jour, notes gardées")
ecrire_consignes(projet, "ESSAI", 20)
verifier(all("inférieurs à 20" in (projet / f).read_text(encoding="utf-8") for f, _ in FICHIERS_CONSIGNES),
         "nouveau seuil reporté dans les trois fichiers")

ouvrir_coffre()
shutil.rmtree(TMP, ignore_errors=True)
print()
print("Verrou, détection et consignes : " + ("tout est bon." if not echecs else f"{len(echecs)} échec(s)."))
sys.exit(1 if echecs else 0)
