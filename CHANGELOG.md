# Historique des versions

## 1.2.1 — novembre 2026

- **Pour toutes les IA, pas seulement Claude** : textes de l'outil, de l'application, des modes d'emploi et du site reformulés (« l'IA » plutôt que « Claude ») ; nouvelle partie « Avec quelle IA ? » (assistants de code comme Claude Code, Copilot, Cursor ou Codex, IA de discussion comme ChatGPT, Mistral ou Gemini) ; le verrou automatique du coffre, propre à Claude Code, est présenté comme tel.
- **Site et démonstration interactive** : https://baptistemazas-nutrition.github.io/sosie/

## 1.2.0 — novembre 2026

Deuxième vague de vérification (7 agents : parcours utilisateur, fuites dans le sosie, contournement du vérificateur, fidélité R/Quarto, fidélité Python/ML, structure et robustesse, revue du code pour Mac).

- **Moins de fuites possibles dans le sosie** : colonne du patient repérée même sans « IPP » (initiales, MRN, nom + prénom + date de naissance) ; une colonne « centre » n'est plus prise pour le patient ; aucune vraie date de naissance recopiée pour un fichier à un seul patient ; ordre des lignes et appartenance aux petites tables mélangés ; dernier contrôle qui masque tout nom ou identifiant réel restant.
- **Sosie plus fidèle** : ordre des visites et doublons réels, prélèvements du même jour, clés DCT du SNDS, dates conventionnelles (9999-12-31), codes 999, manquants SPSS, valeurs `Inf`, classes R (`data.table`, `haven`, `difftime`, `hms`), catégories entières en Python.
- **Vérificateur plus strict et moins de fausses alertes** : Excel commentés, PowerPoint et Word, HTML interactifs, Parquet à listes, tableaux affichés par R (`table`, `survfit`, tibbles, `kable`), petits effectifs en pourcentage ; plus d'alerte sur les médianes, les cumuls, les lieux publics ou les mots courants.
- **Installation** : versions de bibliothèques et outils de construction figés, messages d'erreur en français, consignes de `CLAUDE.md` des projets mises à jour automatiquement.
- **Application Mac** : application « Sosie » (Applications, Launchpad, Dock) avec un menu en français, installation complète en un double-clic (`Installer Sosie.command`) avec essai de bout en bout, mode d'emploi illustré.
- Nouvelles options : `sosie schema --cle-individu`, `sosie creer --cle-individu LIGNE`.

Limites connues : une même clé écrite différemment selon les fichiers (`P-17` ici, `17` là) ne joint qu'environ la moitié des lignes du sosie ; une table d'actes sans colonne patient voit ses modalités rares jugées par séjour ; les liens entre variables (corrélations, IMC = poids/taille²) ne sont pas reproduits.

## 1.1.0 — novembre 2026

Première vague de vérification (10 agents) : corrections de l'installation, de la fabrication du sosie et de la vérification des résultats ; mode d'emploi complété.

## 1.0.0 — novembre 2026

Première version : coffre protégé, sosie fictif (CSV, Excel, SAS, SPSS, Stata, Parquet, R, SQLite, JSON), exécution des scripts sur les vraies données, vérification des résultats avant de les montrer à Claude, pseudonymisation et dictionnaire des variables.
