#!/bin/bash
DEPOT="$(cd "${1:-$(dirname "$0")/..}" && pwd)"
APP="${SOSIE_APP:-$HOME/Applications/Sosie.app}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$DEPOT/src/sosie/__init__.py")"
marque() { printf 'RESULTAT %s\n' "$*"; }

compiler_app() {
  local args=() ligne
  while IFS= read -r ligne || [ -n "$ligne" ]; do
    args+=(-e "$ligne")
  done < "$DEPOT/macos/Sosie.applescript"
  osacompile -o "$APP" "${args[@]}"
}

rm -rf "$APP"
mkdir -p "$(dirname "$APP")"
if ! compiler_app; then
  marque "application=echec"
  exit 1
fi
if osadecompile "$APP/Contents/Resources/Scripts/main.scpt" 2>/dev/null | grep -q "Déplacer"; then
  marque "accents=ok"
else
  marque "accents=NON"
fi
RES="$APP/Contents/Resources"
PL="$APP/Contents/Info.plist"
cp "$DEPOT/macos/sosie-app.sh" "$RES/sosie-app.sh"
chmod 755 "$RES/sosie-app.sh"
rm -f "$RES/Assets.car"
cp "$DEPOT/macos/applet.icns" "$RES/applet.icns"
cp "$DEPOT/macos/mode-emploi.html" "$DEPOT/macos/lisezmoi.html" "$RES/"
mkdir -p "$RES/sosie"
for f in installer.sh pyproject.toml contraintes.txt construction.txt LISEZMOI.md; do
  cp "$DEPOT/$f" "$RES/sosie/$f"
done
ditto "$DEPOT/src/sosie" "$RES/sosie/src/sosie"
find "$RES/sosie" -name "__pycache__" -type d -prune -exec rm -rf {} +
/usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$PL" >/dev/null 2>&1
for paire in "CFBundleName:Sosie" "CFBundleDisplayName:Sosie" "CFBundleIdentifier:fr.sosie.application" "CFBundleShortVersionString:$VERSION" "CFBundleVersion:$VERSION" "CFBundleIconFile:applet"; do
  cle="${paire%%:*}"
  valeur="${paire#*:}"
  /usr/libexec/PlistBuddy -c "Set :$cle $valeur" "$PL" >/dev/null 2>&1 || /usr/libexec/PlistBuddy -c "Add :$cle string $valeur" "$PL"
done
xattr -cr "$APP"
if codesign --force --deep --sign - "$APP" 2>&1; then marque "signature=ok"; else marque "signature=echec"; fi
touch "$APP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP"
codesign --verify --deep --strict "$APP" 2>&1 && marque "signature_verifiee=ok"
marque "application=ok ($APP, version $VERSION)"

if [ -n "${SOSIE_SANS_DOCK:-}" ]; then
  marque "dock=ignore"
elif defaults read com.apple.dock persistent-apps 2>/dev/null | grep -q "Applications/Sosie.app"; then
  marque "dock=deja"
else
  defaults write com.apple.dock persistent-apps -array-add "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>file://$APP/</string><key>_CFURLStringType</key><integer>15</integer></dict></dict></dict>"
  killall Dock
  marque "dock=ajoute"
fi
