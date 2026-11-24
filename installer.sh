#!/bin/sh
set -e
DOSSIER="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
cd "$DOSSIER"
echo "Installation de sosie depuis $DOSSIER"
if [ -n "$SUDO_USER" ]; then
  echo "✗ Ne lance pas l'installation avec sudo. Tape simplement : sh installer.sh"
  exit 1
fi
if [ "$(uname)" = "Darwin" ] && [ "$(sw_vers -productVersion | cut -d. -f1)" -lt 12 ]; then
  echo "✗ sosie demande macOS 12 (Monterey) ou plus récent (menu Pomme > À propos de ce Mac)."
  exit 1
fi
trouver_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return
  fi
  for c in "$BIN/uv" "${XDG_BIN_HOME:-$BIN}/uv" "$HOME/.cargo/bin/uv"; do
    if [ -x "$c" ]; then
      echo "$c"
      return
    fi
  done
}
UV="$(trouver_uv)"
if [ -z "$UV" ]; then
  echo "Téléchargement de uv (gestionnaire Python d'Astral)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh || true
  UV="$(trouver_uv)"
fi
if [ -z "$UV" ] || [ ! -x "$UV" ]; then
  echo ""
  echo "✗ Le téléchargement de uv a échoué. Vérifie ta connexion Internet ; le réseau de l'hôpital peut"
  echo "  bloquer ce téléchargement : essaie depuis ta box ou un partage de connexion, puis relance :"
  echo "  sh installer.sh"
  exit 1
fi
echo "Téléchargement de Python 3.12 et des bibliothèques (environ 150 Mo, quelques minutes)…"
if ! PATH="$BIN:$PATH" UV_NATIVE_TLS=1 UV_PYTHON_PREFERENCE=only-managed UV_CONSTRAINT=contraintes.txt UV_BUILD_CONSTRAINT=construction.txt \
  UV_NO_BUILD_PACKAGE="numpy pandas pyarrow pyreadstat pyreadr" \
  "$UV" tool install -q --force --python 3.12 "$DOSSIER"; then
  echo ""
  echo "✗ Le téléchargement de Python ou des bibliothèques a échoué. Vérifie ta connexion Internet ; le réseau de"
  echo "  l'hôpital peut le bloquer : essaie depuis ta box ou un partage de connexion, puis relance : sh installer.sh"
  echo "  Si uv était déjà installé sur ce Mac, mets-le d'abord à jour : $UV self update"
  exit 1
fi
"$UV" tool update-shell >/dev/null 2>&1 || true
SOSIE="$("$UV" tool dir --bin 2>/dev/null || true)/sosie"
if [ ! -x "$SOSIE" ]; then
  SOSIE="$BIN/sosie"
fi
echo ""
"$SOSIE" configurer
echo ""
"$SOSIE" autotest
echo ""
echo "Installation terminée. Ferme la fenêtre du Terminal, ouvre-en une nouvelle, puis tape : sosie"
