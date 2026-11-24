#!/bin/bash
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/R.framework/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin"
case "${LANG:-}" in
  *UTF-8*|*utf-8*|*UTF8*|*utf8*) ;;
  *) export LANG="fr_FR.UTF-8" ;;
esac
RESSOURCES="$(cd "$(dirname "$0")" && pwd)"
SOSIE="$HOME/.local/bin/sosie"
if [ ! -x "$SOSIE" ]; then
  SOSIE="$(command -v sosie 2>/dev/null || true)"
fi
CONFIG_APP="${XDG_CONFIG_HOME:-$HOME/.config}/sosie/application.txt"
COFFRE_A_FERMER=0

titre() { printf '\n\033[1m%s\033[0m\n\n' "$*"; }
bien() { printf '\033[32m✓\033[0m %s\n' "$*"; }
alerte() { printf '\033[33m⚠\033[0m  %s\n' "$*"; }
erreur() { printf '\033[31m✗\033[0m %s\n' "$*"; }

finir() {
  if [ "$COFFRE_A_FERMER" = 1 ]; then
    "$SOSIE" coffre fermer --silencieux
  fi
  echo
  printf 'Appuie sur Entrée pour fermer cette fenêtre. '
  read -r _
  exit "${1:-0}"
}

exiger_sosie() {
  if [ -z "$SOSIE" ] || [ ! -x "$SOSIE" ]; then
    erreur "sosie n'est pas installé. Ouvre Sosie et choisis « Réparer ou mettre à jour sosie »."
    finir 1
  fi
}

coffre() {
  local f="${XDG_CONFIG_HOME:-$HOME/.config}/sosie/config.toml"
  local c=""
  if [ -f "$f" ]; then
    c="$(sed -n 's/^coffre *= *"\(.*\)" *$/\1/p' "$f" | head -n 1)"
  fi
  if [ -z "$c" ]; then
    c="$HOME/Coffre"
  fi
  case "$c" in
    "~"*) c="$HOME${c#\~}" ;;
  esac
  printf '%s\n' "$c"
}

coffre_projet() {
  local c=""
  if [ -f "$1/sosie.toml" ]; then
    c="$(sed -n 's/^coffre *= *"\(.*\)" *$/\1/p' "$1/sosie.toml" | head -n 1)"
  fi
  if [ -z "$c" ]; then
    c="$(coffre)/$(basename "$1")"
  fi
  printf '%s\n' "$c"
}

lister() {
  if [ -n "$SOSIE" ] && [ -x "$SOSIE" ] && [ -d "$(coffre)" ]; then
    "$SOSIE" coffre projets 2>/dev/null || true
  fi
}

ouvrir_coffre() {
  exiger_sosie
  "$SOSIE" coffre ouvrir --silencieux
}

lire_reglage() {
  if [ -f "$CONFIG_APP" ]; then
    sed -n "s/^$1=//p" "$CONFIG_APP" | head -n 1
  fi
}

ecrire_reglage() {
  mkdir -p "$(dirname "$CONFIG_APP")"
  touch "$CONFIG_APP"
  grep -v "^$1=" "$CONFIG_APP" > "$CONFIG_APP.tmp"
  printf '%s=%s\n' "$1" "$2" >> "$CONFIG_APP.tmp"
  mv "$CONFIG_APP.tmp" "$CONFIG_APP"
}

dossier_projets() {
  local d
  d="$(lire_reglage dossier_projets)"
  if [ -z "$d" ] || [ ! -d "$d" ]; then
    if [ -d "$HOME/Recherche/projets" ]; then
      d="$HOME/Recherche/projets"
    else
      d="$HOME/Documents/Projets sosie"
    fi
  fi
  printf '%s\n' "$d"
}

memoriser_dossier() {
  ecrire_reglage dossier_projets "$1"
}

nettoyer_nom() {
  printf '%s' "$1" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/[[:space:]][[:space:]]*/_/g' -e 's#[/:\\]#-#g' -e 's/^[.~]*//'
}

ouvrir_vscode() {
  if open -b com.microsoft.VSCode "$1" 2>/dev/null; then
    bien "Projet ouvert dans VS Code : $1"
  else
    open "$1"
    alerte "VS Code est introuvable : le projet est ouvert dans le Finder."
  fi
}

transferer() {
  local mode="$1" src="${2%/}" dest="$3" archives="$4" nom
  nom="$(basename "$src")"
  if [ ! -e "$src" ]; then
    erreur "Introuvable : $src"
    return 1
  fi
  if [ -e "$dest/$nom" ]; then
    mkdir -p "$archives" || return 1
    mv "$dest/$nom" "$archives/" || return 1
    alerte "L'ancienne version de « $nom » est rangée dans le coffre : $archives"
  fi
  if [ "$mode" = "copier" ]; then
    ditto "$src" "$dest/$nom" || return 1
    bien "Copié dans le coffre : $nom"
    alerte "L'original est toujours ici : $src (supprime-le quand tu n'en as plus besoin)."
  else
    mv "$src" "$dest/" || return 1
    bien "Déplacé dans le coffre : $nom"
  fi
  return 0
}

importer() {
  local mode="$1" dest="$2" archives echecs=0 src
  shift 2
  archives="$(dirname "$dest")/archives/$(date +%Y-%m-%d_%Hh%M%S)"
  "$SOSIE" coffre ouvrir --silencieux || return 1
  COFFRE_A_FERMER=1
  mkdir -p "$dest" || return 1
  for src in "$@"; do
    transferer "$mode" "$src" "$dest" "$archives" || echecs=$((echecs + 1))
  done
  if [ "$echecs" -gt 0 ]; then
    erreur "$echecs élément(s) n'ont pas pu être mis dans le coffre."
    alerte "Si macOS a refusé l'accès : Réglages Système > Confidentialité et sécurité > Fichiers et dossiers > Terminal."
    return 1
  fi
  return 0
}

fabriquer() {
  cd "$1" || return 1
  "$SOSIE" creer
}

creer_projet() {
  "$SOSIE" projet "$@" 2>&1 | sed '/Étapes suivantes/,$d'
  return "${PIPESTATUS[0]}"
}

conseils_ia() {
  titre "C'est prêt"
  echo "VS Code s'ouvre sur le projet. Ouvre ton assistant d'IA (Claude Code, Copilot…) et demande-lui par exemple :"
  echo "  « Lis donnees/FICHE_SOSIE.md et propose-moi un plan d'analyse. »"
  echo
  echo "Quand un script tourne sur le sosie : ouvre Sosie > « Lancer un script sur les vraies données »."
}

action_nouveau() {
  exiger_sosie
  local nom="$1" parent="$2" mode="$3" racine dest
  shift 3
  titre "Nouveau projet « $nom »"
  mkdir -p "$parent" || { erreur "Impossible de créer le dossier $parent"; finir 1; }
  creer_projet "$nom" --dossier "$parent" --ne-pas-ouvrir || finir 1
  racine="$parent/$nom"
  dest="$(coffre_projet "$racine")/donnees"
  if [ "$#" -eq 0 ]; then
    "$SOSIE" coffre ouvrir --silencieux || finir 1
    open "$dest"
    titre "Dernière étape"
    echo "Dépose tes vraies données dans la fenêtre du Finder qui vient de s'ouvrir (c'est le coffre),"
    echo "puis ouvre Sosie et choisis « Refaire le sosie d'un projet » : le coffre se refermera alors à clé."
    finir 0
  fi
  titre "Rangement des vraies données dans le coffre"
  importer "$mode" "$dest" "$@" || finir 1
  titre "Fabrication du sosie"
  fabriquer "$racine" || finir 1
  ouvrir_vscode "$racine"
  conseils_ia
  finir 0
}

action_ajouter() {
  exiger_sosie
  local racine="$1" mode="$2" dest
  shift 2
  dest="$(coffre_projet "$racine")/donnees"
  titre "Ajout de vraies données au projet « $(basename "$racine") »"
  importer "$mode" "$dest" "$@" || finir 1
  titre "Fabrication du sosie"
  fabriquer "$racine" || finir 1
  bien "Sosie à jour : l'IA voit la nouvelle structure dans donnees/."
  finir 0
}

action_creer() {
  exiger_sosie
  titre "Fabrication du sosie de « $(basename "$1") »"
  fabriquer "$1"
  finir $?
}

action_executer() {
  exiger_sosie
  local racine="$1" script="$2" cible code
  cd "$racine" || finir 1
  cible="$script"
  case "$script" in
    "$racine"/*) cible="${script#"$racine"/}" ;;
  esac
  titre "Exécution de $cible sur les VRAIES données"
  "$SOSIE" executer "$cible"
  code=$?
  titre "Vérification avant de montrer quoi que ce soit à l'IA"
  "$SOSIE" verifier
  finir "$code"
}

action_verifier() {
  exiger_sosie
  cd "$1" || finir 1
  titre "Vérification des derniers résultats de « $(basename "$1") »"
  "$SOSIE" verifier
  finir $?
}

action_etat() {
  exiger_sosie
  cd "$1" || finir 1
  "$SOSIE" etat
  finir $?
}

action_exemple() {
  exiger_sosie
  local parent="$1" nom="EXEMPLE_SOSIE"
  mkdir -p "$parent" || finir 1
  titre "Projet d'exemple (données entièrement fictives)"
  creer_projet "$nom" --dossier "$parent" --exemple --ne-pas-ouvrir || finir 1
  titre "Fabrication du sosie"
  fabriquer "$parent/$nom" || finir 1
  ouvrir_vscode "$parent/$nom"
  conseils_ia
  finir 0
}

action_reparer() {
  local tmp depot
  depot="$(lire_reglage depot)"
  if [ -n "$depot" ] && [ -f "$depot/Installer Sosie.command" ]; then
    titre "Mise à jour de sosie depuis $depot"
    if [ -d "$depot/.git" ]; then
      if GIT_TERMINAL_PROMPT=0 git -C "$depot" pull --ff-only; then
        bien "Dépôt à jour."
      else
        alerte "Mise à jour automatique impossible : dans GitHub Desktop, fais « Fetch origin » puis « Pull », puis relance."
      fi
    fi
    exec bash "$depot/Installer Sosie.command"
  fi
  titre "Installation ou réparation de sosie"
  if [ ! -f "$RESSOURCES/sosie/installer.sh" ]; then
    erreur "Installateur introuvable dans l'application Sosie."
    finir 1
  fi
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/sosie-installation.XXXXXX")" || finir 1
  ditto "$RESSOURCES/sosie" "$tmp/sosie" || finir 1
  cd "$tmp/sosie" && sh installer.sh
  finir $?
}

action_version() {
  if [ -n "$SOSIE" ] && [ -x "$SOSIE" ]; then
    "$SOSIE" --version 2>/dev/null | head -n 1
  else
    echo "absent"
  fi
}

action="${1:-}"
shift || true
case "$action" in
  lister) lister ;;
  version) action_version ;;
  dossier-projets) dossier_projets ;;
  memoriser-dossier) memoriser_dossier "$1" ;;
  nettoyer-nom) nettoyer_nom "$1" ;;
  ouvrir-vscode) ouvrir_vscode "$1" > /dev/null ;;
  ouvrir-coffre) ouvrir_coffre && open "$(coffre_projet "$1")" ;;
  ouvrir-donnees) ouvrir_coffre && mkdir -p "$(coffre_projet "$1")/donnees" && open "$(coffre_projet "$1")/donnees" ;;
  fermer-coffre) { [ -n "$SOSIE" ] && [ -x "$SOSIE" ] && "$SOSIE" coffre fermer --silencieux; } || true ;;
  nouveau) action_nouveau "$@" ;;
  ajouter) action_ajouter "$@" ;;
  creer) action_creer "$1" ;;
  executer) action_executer "$1" "$2" ;;
  verifier) action_verifier "$1" ;;
  etat) action_etat "$1" ;;
  exemple) action_exemple "$1" ;;
  reparer) action_reparer ;;
  *) echo "Action inconnue : $action" >&2; exit 2 ;;
esac
