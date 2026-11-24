<p align="center"><img src="macos/icone.png" width="128" alt=""></p>

<h1 align="center">Sosie</h1>

<p align="center">Travailler avec l'IA sur des bases de données de santé <b>sans jamais lui montrer les vraies</b>.</p>

<p align="center"><a href="https://baptistemazas-nutrition.github.io/sosie/"><b>Site et démonstration interactive</b></a> · <a href="LISEZMOI.md">Mode d'emploi complet</a> · <a href="CHANGELOG.md">Nouveautés</a></p>

Sosie range les vraies données dans un **coffre** que l'IA ne voit jamais, fabrique un **sosie** fictif de la base (mêmes fichiers, mêmes colonnes, mêmes formats et mêmes pièges, aucune vraie personne), lance sur les vraies données les scripts que l'IA a écrits sur le sosie, puis **vérifie** ce qu'ils produisent avant de le lui montrer. Claude, ChatGPT, Copilot, Mistral, Gemini… : l'IA de ton choix.

```
 L'IA écrit le script sur le sosie  →  tu le lances sur les vraies données  →  Sosie vérifie  →  l'IA lit les résultats vérifiés
```

## Installer sur un Mac

1. Dans **GitHub Desktop** : *File → Clone Repository…* → `sosie`.
2. Dans le dossier cloné, double-clique sur **`Installer Sosie.command`**.
   En quelques minutes (connexion Internet nécessaire), l'installation :
   - installe l'outil `sosie` (Python 3.12 et ses bibliothèques, dans un environnement isolé) ;
   - crée le coffre `~/Coffre`, l'exclut de Spotlight et en interdit l'accès à Claude Code ;
   - installe l'application **Sosie** dans `~/Applications` et l'ajoute au Dock ;
   - fait un essai complet sur des données fictives, puis l'efface.

   Le compte rendu est dans `journaux/installation.txt` (non suivi par git).
3. Ouvre **Sosie** → **Nouveau projet**, donne un nom, choisis ta base : elle part dans le coffre, le sosie est fabriqué et le projet s'ouvre dans VS Code.

**Mettre à jour** : Sosie → *Réparer ou mettre à jour sosie* (ou, dans GitHub Desktop, *Fetch origin* puis *Pull*, et de nouveau `Installer Sosie.command`). Dans chaque projet, refais ensuite le sosie (*Refaire le sosie d'un projet*) pour profiter des corrections.

Sans Mac ou sans l'application : `sh installer.sh` installe seulement l'outil en ligne de commande.

## Au quotidien

| Dans l'application Sosie | Équivalent dans le terminal de VS Code |
|---|---|
| Refaire le sosie d'un projet | `sosie creer` |
| Lancer un script sur les vraies données | `sosie executer scripts/analyse.R` puis `sosie verifier` |
| Vérifier les derniers résultats | `sosie verifier` |
| État et protection d'un projet | `sosie etat` |

L'IA ne lance jamais ces commandes : c'est toi qui touches aux vraies données. Elle ne lit que `donnees/` (le sosie) et `resultats_verifies/`.

## Documentation

- Mode d'emploi rapide : [`macos/mode-emploi.html`](macos/mode-emploi.html) (aussi dans l'application, *Mode d'emploi*).
- Mode d'emploi complet : [`LISEZMOI.md`](LISEZMOI.md) — formats, options, vérification, pseudonymisation, limites connues.
- Historique des versions : [`CHANGELOG.md`](CHANGELOG.md).

## Organisation du dépôt

| Dossier ou fichier | Contenu |
|---|---|
| `src/sosie/` | l'outil (profil des données, génération du sosie, exécution, vérification, formats) |
| `installer.sh` | installation de l'outil seul, avec des versions de bibliothèques figées (`contraintes.txt`, `construction.txt`) |
| `Installer Sosie.command` | installation complète sur Mac : outil, application, vérifications, essai |
| `macos/` | l'application : menu AppleScript, script d'actions, icône, mode d'emploi |
| `tests/` | cohorte fictive de non-régression et ses contrôles |
| `outils/` | régénérer l'icône et le mode d'emploi HTML |

## Sécurité

- Ce dépôt ne contient **aucune donnée réelle**, et le `.gitignore` refuse les fichiers de données. Les tests fabriquent leurs propres données fictives.
- Sosie marche avec n'importe quelle IA, mais le verrou automatique du coffre (règles d'interdiction, bac à sable) est réglé pour Claude Code. N'ajoute jamais le dossier `Coffre` à un outil d'IA (application Claude, ChatGPT, Copilot, Cursor, Codex…) et, avec un autre assistant que Claude Code, refuse toute commande qui vise `~/Coffre`.
- Par défaut, `sosie configurer` active le bac à sable de Claude Code dans tous les projets, pour qu'aucun ne puisse lire le coffre. Pour le limiter aux projets Sosie : `sosie configurer --bac-a-sable projets`.

## Développement

- `sosie autotest` : contrôle rapide de bout en bout.
- `tests/lancer_tests.sh` : non-régression complète sur une cohorte fictive de 312 patients (une dizaine de formats). À lancer dans le Terminal : sosie refuse volontairement de tourner sous Claude Code.
- GitHub Actions : à chaque envoi, installation, analyse statique et non-régression sous Linux ; l'installation complète sur Mac (application comprise) se lance à la main depuis l'onglet *Actions*.
- Conventions : textes et code en français, pas de commentaires dans le code, version dans `src/sosie/__init__.py` et `pyproject.toml`.
