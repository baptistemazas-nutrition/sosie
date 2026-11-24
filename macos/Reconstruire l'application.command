#!/bin/bash
DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$DEPOT/journaux"
bash "$DEPOT/macos/construire_app.sh" "$DEPOT" 2>&1 | tee "$DEPOT/journaux/application.txt"
