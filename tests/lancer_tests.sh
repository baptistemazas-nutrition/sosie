#!/bin/bash
set -e
DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${SOSIE_PYTHON:-$HOME/.local/share/uv/tools/sosie/bin/python}"
if [ ! -x "$PY" ]; then
  echo "Python de sosie introuvable : installe sosie (sh installer.sh) ou indique SOSIE_PYTHON."
  exit 1
fi
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export PYTHONPATH="$DEPOT/src"
export SOSIE_SANS_CONTROLE_PARENT=1
echo "== Autotest"
"$PY" -m sosie autotest
echo "== Données fictives de non-régression"
"$PY" "$DEPOT/tests/fabriquer_donnees_essai.py" "$TMP/vraies"
echo "== Fabrication du sosie"
"$PY" -m sosie creer --source "$TMP/vraies" --destination "$TMP/sosie" --graine 3
echo "== Vérification du sosie"
"$PY" "$DEPOT/tests/verifier_sosie.py" "$TMP/vraies" "$TMP/sosie"
echo "== Verrou du coffre, IA détectées, consignes"
"$PY" "$DEPOT/tests/verifier_verrou.py"
echo "== Parcours complet avec le coffre fermé à clé"
ferme() { "$PY" -c 'import sys; from sosie.config import coffre_ferme; sys.exit(0 if coffre_ferme() else 1)'; }
echouer() { echo "ÉCHEC : $*"; exit 1; }
COFFRE="$("$PY" -c 'from sosie.config import chemin_coffre; print(chemin_coffre())')"
NOM="ESSAI_VERROU_$(date +%s)_$$"
ferme || echouer "coffre ouvert avant le parcours"
if [ "$(id -u)" != 0 ] && cat "$COFFRE/.temoin/TEMOIN_NE_PAS_LIRE.txt" >/dev/null 2>&1; then echouer "témoin lisible, coffre fermé"; fi
cd "$TMP"
"$PY" -m sosie projet "$NOM" --exemple --ne-pas-ouvrir >/dev/null
ferme || echouer "coffre ouvert après « sosie projet --exemple »"
cd "$NOM"
for f in CLAUDE.md AGENTS.md GEMINI.md; do grep -q "fermé à clé" "$f" || echouer "consignes absentes de $f"; done
"$PY" -m sosie creer >/dev/null
ferme || echouer "coffre ouvert après « sosie creer »"
cat > scripts/essai.py <<'PEOF'
import csv
import os

with open("donnees/patients.csv", encoding="cp1252", newline="") as f:
    n = sum(1 for _ in csv.DictReader(f, delimiter=";"))
os.makedirs("resultats", exist_ok=True)
with open("resultats/effectif.csv", "w", encoding="utf-8") as f:
    f.write(f"n\n{n}\n")
PEOF
"$PY" -m sosie executer scripts/essai.py
ferme || echouer "coffre ouvert après « sosie executer »"
"$PY" -m sosie verifier
ferme || echouer "coffre ouvert après « sosie verifier »"
find resultats_verifies -name effectif.csv | grep -q . || echouer "résultat vérifié absent"
for marqueur in CODEX_THREAD_ID=essai GEMINI_CLI=1 CURSOR_AGENT=1 AI_AGENT=github-copilot OPENCODE=1; do
  if env "$marqueur" "$PY" -m sosie coffre ouvrir 2>/dev/null; then echouer "$marqueur : coffre ouvert par une IA"; fi
  if env "$marqueur" "$PY" -m sosie executer scripts/essai.py 2>/dev/null; then echouer "$marqueur : exécution acceptée"; fi
  ferme || echouer "coffre ouvert après le refus ($marqueur)"
done
"$PY" -m sosie coffre ouvrir --silencieux
ferme && echouer "« sosie coffre ouvrir » n'ouvre pas"
"$PY" -m sosie etat >/dev/null
ferme && echouer "« sosie etat » a refermé un coffre ouvert à la main"
"$PY" -m sosie coffre fermer --silencieux
ferme || echouer "« sosie coffre fermer » ne ferme pas"
"$PY" -m sosie coffre projets | grep -q "^$NOM$(printf '\t')" || echouer "« sosie coffre projets » ne liste pas le projet"
ferme || echouer "coffre ouvert après « sosie coffre projets »"
cd "$TMP"
"$PY" -m sosie coffre ouvrir --silencieux
rm -rf "${COFFRE:?}/$NOM"
"$PY" -m sosie coffre fermer --silencieux
ferme || echouer "coffre ouvert à la fin"
echo "Parcours complet : tout est bon."
