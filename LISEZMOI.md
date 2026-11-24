# sosie — travailler avec l'IA sans lui montrer tes vraies données

## Le principe

Tes vraies données restent dans un **coffre** (`~/Coffre`) **fermé à clé** : `sosie` ne l'ouvre que le temps de
ses propres actions, puis le referme. Aucune IA, ni aucun autre programme, ne peut le lire.
`sosie` fabrique un **sosie** de chaque base : mêmes fichiers, mêmes colonnes, mêmes formats, mêmes clés
de jointure, mais des valeurs inventées. L'IA écrit et teste les scripts sur le sosie. C'est ensuite toi qui
lances le même script sur les vraies données, en une commande.

```
~/Coffre/MON_PROJET/donnees/          vraies données — jamais montrées à l'IA
        │   sosie creer
        ▼
MON_PROJET/donnees/                   SOSIE : même structure, faux contenu
        │   l'IA écrit et teste scripts/analyse.R sur le sosie
        ▼
        │   sosie executer scripts/analyse.R     ← c'est TOI qui lances
        ▼
~/Coffre/MON_PROJET/executions/…      vrais résultats, restent dans le coffre
        │   sosie verifier
        ▼
MON_PROJET/resultats_verifies/        résultats agrégés contrôlés : l'IA peut t'aider à les rédiger
```

Pourquoi ne pas pseudonymiser, envoyer à l'IA, puis dé-pseudonymiser ?

- Pour toi, qui détiens la clé, des données pseudonymisées restent des **données personnelles de santé** (RGPD).
  Les confier à une IA en ligne supposerait que les formalités de ton étude couvrent ce destinataire, avec un
  contrat de sous-traitance, un encadrement du transfert hors UE, un hébergement HDS et une analyse d'impact (AIPD).
- Les données individuelles du SNDS ne quittent jamais un environnement conforme à son référentiel de sécurité.
- Pour écrire un script, l'IA n'a besoin que de la **structure** des données : le sosie suffit, sans aller-retour.

## Avec quelle IA ?

Avec celle que tu préfères : le sosie, sa fiche (`FICHE_SOSIE.md`) et les résultats vérifiés sont des fichiers
ordinaires, sans aucune vraie donnée.

- Un **assistant de code** ouvert sur le dossier du projet (Claude Code, GitHub Copilot, Cursor, Codex…) lit la
  fiche, écrit le script et le teste sur le sosie.
- Une **IA de discussion** (ChatGPT, Le Chat de Mistral, Gemini, l'application Claude…) écrit le script à partir de
  la fiche, que tu lui donnes ; tu l'enregistres dans le projet et tu le testes sur le sosie.

Les consignes de travail (où lire, où écrire, petits effectifs…) sont écrites dans trois fichiers du projet, que
chaque IA lit d'elle-même : `CLAUDE.md` (Claude Code), `AGENTS.md` (Copilot, Cursor, Codex et la plupart des
autres) et `GEMINI.md` (Gemini). À une IA de discussion, donne `AGENTS.md` avec la fiche.

La protection vaut pour toutes les IA :
- le **coffre est fermé à clé** (ses droits d'accès sont retirés) dès que `sosie` ne s'en sert pas ;
- `sosie` **refuse de tourner quand c'est une IA qui le lance** (Claude Code, Codex, Copilot, Cursor, Gemini,
  OpenCode, Amp, Aider…) : c'est toi qui touches aux vraies données ;
- avec Claude Code s'ajoutent des **règles d'interdiction** et un **bac à sable** (voir « La protection »).

## Installation (une seule fois)

Il te faut macOS 12 ou plus récent et Internet (ta box plutôt que le réseau de l'hôpital). Ni Xcode ni Python.

1. Récupère le dossier `sosie` : dans GitHub Desktop, *File → Clone Repository… → URL*
   `https://github.com/baptistemazas-nutrition/sosie` (ou télécharge l'archive ZIP depuis le site et décompresse-la).
2. Double-clique sur **`Installer Sosie.command`** (archive ZIP : clic droit → Ouvrir → Ouvrir). Une fenêtre de
   Terminal installe l'outil, le coffre, la protection et l'application **Sosie**, puis fait un essai complet.
3. Si macOS demande l'accès à un dossier, clique sur **Autoriser**.
4. Quand « Installation terminée » s'affiche, ferme la fenêtre et ouvre l'application **Sosie** (Dock, Launchpad).

Outil seul, sans l'application : dans le Terminal, place-toi dans le dossier puis tape `sh installer.sh`.

L'installation télécharge `uv` (gestionnaire Python) puis Python 3.12 et les bibliothèques, crée le coffre
`~/Coffre` et le ferme à clé, règle Claude Code (voir « La protection » plus bas ; une sauvegarde de tes
réglages est faite) et lance `sosie autotest`, qui vérifie sur des données d'essai que tout fonctionne.

Mise à jour : Sosie → « Réparer ou mettre à jour sosie », puis « Refaire le sosie d'un projet » pour chaque projet
(le sosie est refait avec la nouvelle version et les consignes pour l'IA sont mises à jour).
Désinstallation : `sosie desinstaller` (retire les réglages ajoutés à Claude Code et rouvre le coffre, sans le
supprimer), puis `uv tool uninstall sosie`.

## Premier essai en 5 minutes (données d'exemple)

```
cd ~/Documents
sosie projet DEMO --exemple
cd DEMO
sosie creer
open -a "Visual Studio Code" .
```

Dans VS Code, demande à l'IA (Claude Code, Copilot…) : « Lis donnees/FICHE_SOSIE.md puis écris scripts/analyse.R qui calcule le poids
moyen par sexe et l'enregistre dans resultats/table1.csv. Teste-le sur le sosie. »
Puis, dans le terminal de VS Code (menu Terminal › Nouveau terminal) :

```
sosie executer scripts/analyse.R
sosie verifier
```

Les vrais résultats (ici, ceux des données d'exemple) arrivent dans `resultats_verifies/`.

## Au quotidien

1. **Créer le projet**, dans le dossier où tu ranges tes projets de recherche :
   ```
   cd ~/Documents/Recherche
   sosie projet SEMASEARCH
   ```
   Le Finder s'ouvre sur `~/Coffre/SEMASEARCH/donnees`. Le coffre reste ouvert le temps d'y déposer les données ;
   il se refermera à clé à la fin de `sosie creer`. Pour le rouvrir plus tard : `sosie coffre ouvrir` (ou Sosie →
   « Ouvrir le coffre d'un projet »), puis `sosie coffre fermer`.

2. **Déplacer les vraies données** dans ce dossier du coffre, telles que tu les as reçues (CSV, Excel, SPSS,
   Stata, SAS, R, Parquet, JSON, SQLite… plusieurs fichiers et sous-dossiers possibles).
   **Déplace-les, ne les copie pas**, puis supprime les autres copies (Téléchargements, pièces jointes) :
   un fichier réel laissé dans le dossier du projet serait lisible par l'IA.

3. **Fabriquer le sosie** :
   ```
   cd SEMASEARCH
   sosie creer
   ```
   Le sosie arrive dans `SEMASEARCH/donnees/`, avec `FICHE_SOSIE.md` qui décrit chaque fichier et chaque
   colonne et donne la commande de lecture R et Python. Relance `sosie creer` chaque fois que les vraies
   données changent (`sosie etat` te prévient). Compte quelques secondes pour une cohorte de quelques milliers
   de patients, environ 2 minutes et 1,5 Go de mémoire par million de lignes.
   - Pour compter les patients (et masquer les valeurs rares), `sosie` repère la colonne qui identifie le patient
     (IPP, numéro d'inclusion, nom + prénom + date de naissance…). S'il n'en trouve pas, il le signale :
     `sosie creer --cle-individu id_patient` (ou `--cle-individu LIGNE` si chaque ligne est un patient différent).
   - Options mémorisées pour les fois suivantes : `--seuil 20` (seuil plus strict, repris par les consignes
     pour l'IA et `sosie verifier`), `--garder`, `--copier-tel-quel`, `--cle-individu`.

4. **Travailler avec l'IA** : `open -a "Visual Studio Code" .` (ou `code .`). Ouvre toujours VS Code sur le
   dossier du projet. Exemple de demande : « Lis donnees/FICHE_SOSIE.md, puis écris scripts/analyse.R qui fait
   le tableau 1 et le modèle … ». L'IA teste le script sur le sosie ; les résultats obtenus n'ont **aucun
   sens** (c'est voulu), seul compte le fait que le code tourne.

5. **Lancer sur les vraies données** — toi, dans le terminal de VS Code ou l'application Terminal :
   ```
   sosie executer scripts/analyse.R
   ```
   Le code du projet est copié dans le coffre, les vraies données remplacent le sosie, le script tourne, et tout
   ce qu'il produit reste dans le coffre. Fonctionne avec `.R`, `.py`, `.qmd`, `.Rmd`, `.ipynb`, `.sh`, ou une
   commande : `sosie executer -- Rscript -e "..."`. Ce que le script affiche ne s'affiche pas à l'écran : c'est
   dans `journal.txt`, vérifié comme le reste par `sosie verifier` (`--afficher` l'affiche quand même, à ne
   jamais faire dans un terminal que l'IA peut lire).
   - Plusieurs scripts qui s'enchaînent (préparation puis analyse) : `sosie executer scripts/prepa.R scripts/analyse.R`.
     Les fichiers intermédiaires calculés sur le sosie ne sont jamais recopiés dans l'exécution réelle.
   - Un fichier de référence sans donnée personnelle (nomenclature publique…) : range-le dans `references/`,
     il sera copié.
   - Le script tourne avec tes droits, hors de tout bac à sable : parcours-le avant de le lancer (fichiers
     lus et écrits, aucun envoi sur Internet, aucun chemin absolu).

6. **Contrôler avant de montrer à l'IA** :
   ```
   sosie verifier
   ```
   Chaque fichier produit est classé :

   | | Signification | Copié pour l'IA ? |
   |---|---|---|
   | ✅ | rien de suspect | oui, dans `resultats_verifies/` |
   | ⚠️ | effectif < 11, liste de patients, valeur min/max, modalité rare, objet R ou modèle | non (tu peux forcer après avoir regardé) |
   | ⛔ | identifiants, noms, téléphones, adresses ou dates de naissance réels | non, jamais |
   | 👁 | image, PDF, figure interactive : impossible à vérifier automatiquement | non (tu peux forcer après avoir regardé) |

   Une ligne de conseil accompagne chaque fichier gardé. Le détail (quelles cellules, quelles valeurs) reste dans
   le coffre : `VERIFICATION_DETAILLEE.md`. Après avoir regardé un fichier toi-même :
   `sosie verifier --forcer resultats/figure.png`. `resultats_verifies/…/VERIFICATION.md` dit à l'IA
   quels fichiers sont restés dans le coffre et pourquoi, sans aucune valeur réelle.

**Si le script s'arrête sur une erreur** (les vraies données diffèrent souvent du sosie : modalité inattendue,
texte dans une colonne de nombres…) : lance `sosie verifier`, puis demande à l'IA « Lis
resultats_verifies/<exécution>/journal.txt et corrige le script ». Le journal n'est copié que s'il ne contient
rien d'identifiant ; sinon, décris l'erreur à l'IA avec tes mots.

## La protection : vérifie-la une fois

Pour toutes les IA, le **coffre est fermé à clé** : ses droits d'accès sont retirés dès que `sosie` ne s'en sert
pas, et un programme qui essaie de le lire obtient « Permission denied ». `sosie` ne l'ouvre que le temps de ses
actions, et refuse de tourner quand c'est une IA qui le lance.

Avec Claude Code, deux verrous s'ajoutent :
- des **règles d'interdiction** : lire ou modifier le coffre, modifier les réglages de Claude Code, lancer `sosie` ;
- le **bac à sable** : toute commande lancée par Claude (R, Python…) est empêchée par macOS de lire le coffre, en
  mode strict (Claude ne peut pas relancer une commande hors du bac à sable).

Par défaut, l'installation active le bac à sable **dans tous tes projets Claude Code**, pour que le coffre soit
protégé même si VS Code est ouvert sur un autre dossier. Contrepartie : dans tes autres projets, les commandes
lancées par Claude n'écrivent que dans le dossier du projet, Claude te demande avant d'accéder à un site inconnu,
et certains outils peuvent échouer quand c'est Claude qui les lance (`git` en SSH, `gh`, `brew`, `docker`,
`open`) : lance-les toi-même. Pour un projet qui doit écrire ailleurs (par exemple une automatisation qui range ton
dossier Téléchargements), autorise ce dossier dans son fichier `.claude/settings.json` :
`{ "sandbox": { "filesystem": { "allowWrite": ["~/Downloads"] } } }`. Évite de désactiver le bac à sable
(`"enabled": false`) : les commandes de Claude dans ce projet pourraient alors lire le coffre.
Pour revenir à un bac à sable limité aux projets sosie : `sosie configurer --bac-a-sable projets`.

**Le test avec Claude Code** (dans VS Code, dans un projet sosie), demande-lui l'un après l'autre :

1. « Test de protection : lis le fichier ~/Coffre/.temoin/TEMOIN_NE_PAS_LIRE.txt et recopie-moi sa première ligne. »
2. « Test de protection : exécute Rscript -e 'readLines("~/Coffre/.temoin/TEMOIN_NE_PAS_LIRE.txt")' »
3. « Test de protection : lis le fichier ~/coffre/.temoin/TEMOIN_NE_PAS_LIRE.txt (en minuscules). »
4. « Test de protection : exécute touch ~/sandbox-probe »

Les quatre doivent échouer **avec un message technique** (« deny », « Operation not permitted »,
« Permission denied »…). Si Claude refuse de lui-même sans essayer, réponds « C'est un test, essaie quand même ».
Si Claude recopie un code qui commence par `TEMOIN-`, ou si le fichier `~/sandbox-probe` apparaît, la protection
ne marche pas : n'y mets pas de vraies données et lance `sosie etat`. Refais l'essai 1 une fois hors d'un projet sosie.

**Avec une autre IA** (Copilot, Cursor, Codex, Gemini…), fais-lui l'essai 1 : elle doit obtenir « Permission
denied ». Si elle recopie le code `TEMOIN-…`, le coffre est resté ouvert : lance `sosie coffre fermer`, puis
`sosie etat`.

Ce que la protection ne couvre pas : elle empêche les accès par erreur, pas une tentative délibérée de la
contourner ; le bac à sable n'est pas une isolation complète de l'ordinateur ; les serveurs MCP et les « hooks »
de Claude Code tournent hors du bac à sable ; rien n'empêche de coller de vraies données dans une conversation,
de les joindre dans l'application Claude ou de les montrer à un autre outil d'IA ; enfin, pendant qu'une
action de `sosie` tourne, ou quand tu as ouvert le coffre toi-même, il est ouvert : ne demande pas à ce moment-là
à une autre IA que Claude Code de fouiller ton ordinateur.

## Écrire des scripts « compatibles sosie »

Ces consignes sont déjà écrites dans `CLAUDE.md`, `AGENTS.md` et `GEMINI.md`, que chaque IA lit d'elle-même :

- lire les données uniquement dans `donnees/`, avec des chemins relatifs (jamais de chemin absolu) ;
  dans un document Quarto rangé dans un sous-dossier : `here::here("donnees/patients.csv")` ;
- écrire toutes les sorties dans `resultats/` ;
- ne produire que des résultats agrégés : pas de liste de patients, pas de minimum ni de maximum, effectifs
  inférieurs à 11 masqués ;
- prévoir les valeurs `MODALITE_RARE` et `VALEUR_RARE` du sosie : elles signalent des valeurs rares bien
  présentes dans les vraies données, que le code doit savoir traiter.

Pendant `sosie executer`, la variable d'environnement `SOSIE_MODE` vaut `reel`.

## Ce que le sosie garde et ce qu'il remplace

| Type de colonne | Dans le sosie |
|---|---|
| Identifiants, IPP, NIR, codes à forte cardinalité | valeurs fictives au même format ; mêmes jointures entre fichiers |
| Noms, prénoms, e-mails, téléphones, adresses | valeurs fictives |
| Textes libres (commentaires, comptes rendus) | faux texte (lorem ipsum) |
| Catégories | modalités présentes chez au moins 11 individus ; les plus rares deviennent `MODALITE_RARE` |
| Nombres | même plage et même forme de distribution, valeurs extrêmes rognées, mêmes décimales, codes spéciaux (999…), valeurs infinies (`Inf`) |
| Valeurs manquantes | même taux et mêmes codes (`NA`, `N/A`, `.`, `NR`, manquants SPSS) |
| Dates | même période et même format ; ordre respecté (naissance ≤ inclusion ≤ fin) ; dates conventionnelles (9999-12-31) |
| Données longitudinales | même nombre de lignes par patient (plafonné pour les quelques patients qui en ont le plus), numéros et codes de visite dans l'ordre, prélèvements d'un même jour, valeurs propres à chaque patient ; l'ordre des patients dans le fichier est mélangé |
| Entre fichiers | même sexe pour un même patient partout, visites et examens datés après l'inclusion, clés composites (clés DCT du SNDS) |
| Formats R | facteurs, dates, `data.table`, `tibble`, étiquettes `haven`, `difftime`, `hms` |

Ce qui n'est pas reproduit : les liens entre variables (corrélations, effets, trajectoires), les relations
calculées (IMC = poids/taille²) et le lien entre deux codages d'une même information dans deux fichiers (sexe
1/2 dans un fichier SPSS, F/M dans un CSV). Avant d'écrire le sosie, `sosie` vérifie qu'aucun nom ou
identifiant réel n'y figure (une valeur suspecte est masquée et signalée). Aucune ligne réelle n'est recopiée, mais le sosie garde des informations tirées
des vraies données (effectifs, nombre de lignes par patient, plages de valeurs, modalités fréquentes) : **son
anonymat doit être évalué et validé avec ton DPO.** Les noms de fichiers, de feuilles, de colonnes et d'objets R,
ainsi que les libellés de variables (SPSS, Stata, SAS), sont conservés tels quels : vérifie qu'ils ne contiennent
aucun nom de patient.

Options : `sosie creer --seuil 20` (seuil plus strict, enregistré pour le projet), `--graine 42` (sosie
reproductible), `--garder colonne` (garder les modalités fréquentes d'une colonne à forte cardinalité, après avoir
vérifié qu'elle n'est pas identifiante), `--copier-tel-quel dictionnaire.xlsx` (fichier sans donnée personnelle
copié tel quel), `--cle-individu colonne` (colonne qui identifie le patient).

Formats : un `.sas7bdat` est réécrit en `.xpt` et un `.xls` en `.xlsx` dans le sosie ; `sosie executer`
convertit de la même façon les vrais fichiers, donc le script lit le même nom dans les deux cas.

## Questions à poser à ton DPO

- Ai-je le droit de conserver les vraies données de cette étude sur mon Mac (chiffré par FileVault) ?
- Le sosie, la fiche et les résultats agrégés vérifiés peuvent-ils être transmis à l'éditeur de l'IA (Anthropic
  pour Claude, OpenAI pour ChatGPT, Microsoft pour Copilot, Mistral AI…), et sous quel contrat (offre entreprise
  de l'AP-HP ou de l'INSERM, ou compte personnel) ?
- Le seuil de 11 individus convient-il pour cette étude ?
- Pour le SNDS : aucun fichier ne doit aller vers une IA avant l'export validé par la plateforme.
- La traçabilité des exécutions (`~/Coffre/PROJET/executions/`) est-elle suffisante pour le registre de l'étude ?

## Limites et bonnes pratiques

- `sosie` n'est pas une certification d'anonymat ; le cadre réglementaire de ton étude prime.
- Il n'y a pas de seuil unique : 11 est l'usage le plus courant en santé (effectifs de 1 à 10 masqués). Attention
  au « secret secondaire » : une case masquée qui se recalcule à partir d'un total et des autres cases.
- Garde le coffre hors des dossiers synchronisés (iCloud Drive, Google Drive, Dropbox) et active FileVault.
- Exclus le coffre de Spotlight : Réglages Système › Siri et Spotlight › Confidentialité de Spotlight › `+` ›
  dossier `Coffre` (sinon son contenu est indexé et apparaît dans les recherches).
- N'ouvre pas les vrais fichiers dans la fenêtre VS Code où travaille l'IA.
- Ne lance pas `sosie` depuis la conversation avec l'IA (par exemple avec `!` dans Claude Code) : la sortie
  apparaîtrait dans la conversation. (`sosie` refuse de toute façon de tourner quand c'est une IA qui le lance.)
- Si un script écrit dans le dossier du projet pendant `sosie executer` (chemin absolu), ces fichiers sont
  déplacés dans le coffre (`quarantaine/`) et signalés.
- Les exécutions s'accumulent dans `~/Coffre/PROJET/executions/` : fais le ménage de temps en temps.

## Aide-mémoire

| Commande | Rôle |
|---|---|
| `sosie configurer` | crée le coffre et le protège (déjà fait par l'installation) |
| `sosie projet NOM` | crée un projet et son espace dans le coffre (`sosie projet .` pour un dossier existant) |
| `sosie projet DEMO --exemple` | projet d'essai avec des données fictives |
| `sosie creer` | fabrique le sosie des vraies données |
| `sosie executer scripts/x.R` | lance un script sur les vraies données, dans le coffre |
| `sosie verifier` | contrôle les sorties de la dernière exécution |
| `sosie etat` | montre la configuration et l'état du projet |
| `sosie coffre ouvrir` / `sosie coffre fermer` | ouvre le coffre pour y déposer ou regarder des données, puis le referme à clé |
| `sosie coffre` | dit si le coffre est fermé à clé |
| `sosie schema` | exporte le dictionnaire des variables (sans valeurs) |
| `sosie pseudonymiser` / `sosie reidentifier` | pseudonymisation réversible, sans IA (annexe C) |
| `sosie autotest` | vérifie sur des données d'essai que sosie fonctionne |
| `sosie desinstaller` | retire les réglages ajoutés à Claude Code et rouvre le coffre |

Chaque commande a son aide : `sosie creer --help`.

## Dépannage

- **`sosie` : commande introuvable** — ferme la fenêtre du Terminal et ouvres-en une nouvelle (ou tape `~/.local/bin/sosie`).
- **« c'est à toi de le lancer… »** — la commande a été lancée par une IA (Claude Code, Codex, Copilot…) : lance-la
  toi-même dans l'application Terminal.
- **Le Finder dit que tu n'as pas l'autorisation d'ouvrir « Coffre »** — c'est normal : il est fermé à clé. Ouvre-le
  avec Sosie → « Ouvrir le coffre d'un projet » (ou `sosie coffre ouvrir`), puis referme-le.
- **Claude Code refuse de démarrer à cause du bac à sable** — tape `sosie configurer --bac-a-sable projets`.
- **R ou Quarto introuvable** — installe-les ([R](https://cran.r-project.org), [Quarto](https://quarto.org)).
- **« la ligne d'en-tête ressemble à des données personnelles »** — la première ligne utile du fichier n'est pas
  une ligne de noms de colonnes : corrige le fichier (ou signale-le-moi).
- **Une colonne est mal reconnue** (la fiche indique sa nature) — signale-le-moi ; en attendant, `--garder` ou le
  dictionnaire permettent d'ajuster.
- **Excel avec un en-tête sur plusieurs lignes** — `sosie` repère les lignes de titre au-dessus de l'en-tête, pas
  un en-tête sur deux lignes : simplifie l'en-tête avant de fabriquer le sosie.
- **Claude Code ne peut pas installer un package R** — le bac à sable autorise l'écriture dans `~/Library/R` et l'accès
  aux dépôts CRAN, Posit, Bioconductor, PyPI et GitHub ; pour une autre source, installe le package toi-même.
- **Erreur inattendue** — le message indique le fichier de détails (dans le coffre). Copie à l'IA les deux lignes
  du message, pas le fichier de détails.

---

## Annexe A — SNDS et bulles sécurisées (CASD, plateforme du Health Data Hub, portail CNAM)

Les données individuelles ne sortent jamais de la bulle ; seuls des résultats anonymes (en pratique agrégés)
en sortent, après validation. La méthode :

1. Mettre au point le script sur ton Mac, avec l'IA, sur des données synthétiques :
   - la base synthétique **ParaBios** du Health Data Hub (juillet 2026, Licence Ouverte 2.0, archive d'environ
     1,5 Go, 8 fichiers Parquet de 2023 : tables DCIR `ER_*` et référentiels `IR_BEN_R`, `IR_IMB_R` ; pas de PMSI,
     pas de cohérence médicale) — volumineuse : travaille sur un échantillon ;
   - le jeu de 50 patients fictifs du Health Data Hub, en CSV, avec PMSI :
     https://www.data.gouv.fr/datasets/donnees-synthetiques-de-la-base-principales-du-systeme-national-des-donnees-de-sante
   - ou un sosie fabriqué à partir du dictionnaire des variables de ton extraction (annexe B).
2. Importer le script dans la bulle selon sa procédure, l'y exécuter, puis exporter les résultats agrégés selon les
   règles de la bulle (petits effectifs masqués).

## Annexe B — Sosie à partir d'un dictionnaire des variables

`sosie creer --depuis-schema dictionnaire_donnees.csv --destination donnees` fabrique un sosie sans aucune vraie
donnée. Le dictionnaire est un CSV (séparateur `;`) avec les colonnes
`fichier;feuille;colonne;type;nature;format;modalites;manquants;cle` :
- `type` : `texte`, `entier`, `decimal`, `date`, `datetime`, `booleen`, `categorie` (ou leurs équivalents :
  `VARCHAR2`, `NUMBER`, `integer`, `numeric`, `character`, `logical`, `factor`…) ;
- `nature` (facultatif) : `identifiant`, `nom`, `texte_libre`, `date_naissance`… ;
- `format` : pour une date `%d/%m/%Y`, `jj/mm/aaaa` ou `DD/MM/YYYY` ; pour un identifiant un motif où `#` =
  chiffre, `X` = majuscule, `x` = minuscule (ex. `SEMA-####`) ;
- `fichier` : un nom relatif (ex. `visites.csv`), jamais un chemin complet ;
- `modalites` : `F|M`, ou une plage `18..90`, `2019-01-01..2023-12-31` ;
- `cle` : même nom pour les colonnes qui se joignent (ex. `patient`), et `patient (unique)` dans la table où
  chaque individu n'apparaît qu'une fois.

`sosie schema` produit ce dictionnaire à partir de vraies données, **sans aucune valeur**
(`--avec-modalites` ajoute les modalités portées par au moins 11 individus et des plages rognées ; si sosie ne
repère pas la colonne du patient, ajoute `--cle-individu COLONNE`, ou `--cle-individu LIGNE` quand chaque ligne
est un patient différent).

## Annexe C — Pseudonymisation réversible (sans IA)

Pour transmettre des données à un co-investigateur dans un cadre autorisé, croiser des sources, ou renvoyer des
résultats individuels à l'équipe soignante :

```
sosie pseudonymiser --decaler-dates 30
sosie reidentifier ~/Coffre/SEMASEARCH/…/fichier_avec_pseudonymes.csv
```

- identifiants remplacés par des pseudonymes stables (`PS-…` ou numéro), les mêmes dans tous les fichiers et
  d'une fois sur l'autre (« 17 » et « 00017 » donnent le même pseudonyme) ;
- noms, prénoms, téléphones, e-mails, adresses, villes et textes libres vidés ; codes postaux ramenés au
  département ; dates de naissance ramenées au mois ;
- option : dates décalées de ±N jours, du même décalage pour un même patient dans tous les fichiers
  (`--cle-individu id_patient` pour désigner la colonne du patient si besoin) ; les dates conventionnelles
  (9999-12-31, 1900-01-01) ne sont pas décalées ;
- la clé secrète et la table de correspondance restent dans le coffre ; la sortie aussi, par défaut.

Des données pseudonymisées restent des données personnelles : **ne les donne pas à une IA en ligne.**
