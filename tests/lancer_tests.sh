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
