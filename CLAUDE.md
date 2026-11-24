# Consignes pour Claude — développement de sosie

Ce dépôt contient le code de sosie lui-même, pas un projet d'analyse.

- Réponds en français. Messages, textes et noms de variables en français.
- Aucun commentaire dans le code : ni `#` en Python et en shell, ni `--` en AppleScript.
- Jamais de vraies données de patients dans ce dépôt, ni dans les tests, ni dans les messages de commit : uniquement les données fictives de `tests/fabriquer_donnees_essai.py` ou de `sosie autotest`.
- Ne lance jamais `sosie` sur un vrai projet ni dans `~/Coffre`. sosie refuse de tourner sous Claude Code : c'est voulu, ne contourne jamais ce contrôle.
- Après une modification : `uv tool run pyflakes src tests outils`, `shellcheck` sur les scripts modifiés, puis `sosie autotest`. La non-régression complète (`tests/lancer_tests.sh`) tourne dans GitHub Actions ou dans le Terminal de l'utilisateur.
- `macos/Sosie.applescript` ne se compile que sur Mac : après l'avoir modifié, lance le workflow *Tests* à la main avec l'option macOS.
- Nouvelle version : `src/sosie/__init__.py`, `pyproject.toml` et `CHANGELOG.md` ensemble.
- Si `LISEZMOI.md` ou `macos/mode-emploi.html` change : `python3 outils/convertir_lisezmoi.py LISEZMOI.md macos/mode-emploi.html macos/lisezmoi.html`.
