import datetime as dt
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path

from .config import DOSSIER_DONNEES, DOSSIER_RESULTATS, DOSSIER_VERIFIES, ErreurSosie, chemin_coffre, cle_nom, proteger_dossier
from .formats import destination_de, ecrire_fichier, fichier_ignore, format_de, lire_fichier, lister_fichiers, r_chaine, trouver_rscript

EXCLUS = {
    DOSSIER_DONNEES, DOSSIER_RESULTATS, DOSSIER_VERIFIES, ".git", ".claude", ".rproj.user", ".quarto", "_freeze",
    "__pycache__", ".ipynb_checkpoints", ".ds_store", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".rhistory",
    ".rdata", ".rapp.history", "_targets", ".jupyter_cache", ".sosie_tmp", "site_libs", "quarantaine",
}
LIENS = {".venv", "venv", "env", "renv", "node_modules"}
SURVEILLANCE_IGNOREE = {".git", ".venv", "venv", "env", "renv", "node_modules", "__pycache__", ".rproj.user",
                        ".ipynb_checkpoints", ".claude", ".quarto", "_freeze"}
EXT_DONNEES = {
    ".csv", ".tsv", ".tab", ".dat", ".xlsx", ".xlsm", ".xls", ".parquet", ".pq", ".feather", ".arrow", ".sav", ".zsav",
    ".dta", ".xpt", ".sas7bdat", ".rds", ".rdata", ".rda", ".sqlite", ".sqlite3", ".db", ".jsonl", ".ndjson", ".pkl",
    ".pickle", ".joblib", ".h5", ".hdf5", ".npy", ".npz", ".fst", ".qs", ".rdb", ".rdx", ".gz", ".bz2", ".xz", ".zst",
    ".zip", ".7z", ".tar", ".duckdb", ".ods",
}
EXT_CODE = {".r", ".py", ".qmd", ".rmd", ".ipynb", ".sh", ".yml", ".yaml", ".toml", ".lock", ".rproj", ".bib", ".csl",
            ".css", ".scss", ".js", ".lua", ".gitignore", ".here", ".cfg", ".ini"}
EXT_COPIEES = EXT_CODE | {".md", ".markdown", ".tex", ".sty", ".cls", ".bst", ".bat", ".ps1", ".sql", ".jl", ".m",
                          ".do", ".sas", ".stan", ".cpp", ".c", ".h", ".hpp", ".editorconfig", ".lintr", ".rprofile",
                          ".renviron", ".rbuildignore", ".gitattributes"}
NOMS_COPIES = {".here", ".rprofile", ".lintr", ".gitignore", "makefile", "dockerfile", "description", "namespace",
               "license", "licence", "readme", "renv.lock", "_quarto.yml", "_brand.yml", "_variables.yml", "_metadata.yml",
               "dictionnaire_donnees.csv"}
DOSSIERS_COPIES = {"references", "_extensions"}
EXT_SORTIES_NOUVELLES = {".txt", ".md", ".html", ".htm", ".json", ".log", ".tex", ".png", ".jpg", ".jpeg", ".svg",
                         ".pdf", ".docx", ".pptx", ".xml", ".out", ".rout"}
DOSSIER_REFERENCES = "references"
EXTENSIONS_SCRIPTS = (".r", ".py", ".qmd", ".rmd", ".ipynb", ".sh")
MANIFESTE_EXECUTION = ".sosie_execution.json"
JOURNAL = "journal.txt"
DOSSIER_QUARANTAINE = "quarantaine"
TAILLE_JSON_DONNEES = 1024 * 1024


def sans_accents_cle(nom):
    s = unicodedata.normalize("NFKD", str(nom))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


def trouver_quarto():
    candidats = [shutil.which("quarto"), "/opt/homebrew/bin/quarto", "/usr/local/bin/quarto",
                 "/Applications/quarto/bin/quarto", str(Path.home() / "Applications/quarto/bin/quarto"),
                 "/Applications/RStudio.app/Contents/Resources/app/quarto/bin/quarto",
                 "/Applications/Positron.app/Contents/Resources/app/quarto/bin/quarto"]
    for c in candidats:
        if c and Path(c).exists():
            return c
    return None


def python_utilisable(chemin):
    if sys.platform == "darwin" and str(chemin) == "/usr/bin/python3":
        try:
            return subprocess.run(["/usr/bin/xcode-select", "-p"], capture_output=True, timeout=10).returncode == 0
        except Exception:
            return False
    return True


def trouver_python(racine):
    if racine is not None:
        for candidat in [racine / ".venv" / "bin" / "python", racine / "venv" / "bin" / "python"]:
            if candidat.exists():
                return str(candidat)
    for nom in ("python3", "python"):
        c = shutil.which(nom)
        if c and python_utilisable(c):
            return c
    return None


def scripts_du_projet(racine):
    trouves = []
    for chemin in sorted(racine.rglob("*")):
        rel = chemin.relative_to(racine)
        if any(cle_nom(p) in EXCLUS or p.startswith(".") or p in LIENS for p in rel.parts[:-1]):
            continue
        if chemin.is_file() and chemin.suffix.lower() in EXTENSIONS_SCRIPTS:
            trouves.append(rel.as_posix())
    return trouves


def est_script(element):
    chemin = Path(element)
    absolu = chemin if chemin.is_absolute() else Path.cwd() / chemin
    return chemin.suffix.lower() in EXTENSIONS_SCRIPTS and absolu.is_file()


def commande_pour(element, arguments, racine):
    chemin = Path(element)
    absolu = (chemin if chemin.is_absolute() else Path.cwd() / chemin).resolve()
    try:
        rel = absolu.relative_to(racine.resolve()).as_posix()
    except ValueError:
        raise ErreurSosie(f"Le script {element} doit se trouver dans le dossier du projet ({racine}).")
    extension = chemin.suffix.lower()
    if extension == ".r":
        rscript = trouver_rscript()
        if not rscript:
            raise ErreurSosie("R (Rscript) est introuvable sur cet ordinateur : installe R depuis https://cran.r-project.org")
        return [rscript, rel, *arguments], rel
    if extension == ".py":
        python = trouver_python(racine)
        if not python:
            raise ErreurSosie("Python est introuvable pour tes scripts : crée l'environnement du projet (uv venv) ou installe Python.")
        return [python, rel, *arguments], rel
    if extension == ".sh":
        return ["bash", rel, *arguments], rel
    if extension == ".rmd":
        rscript = trouver_rscript()
        if rscript:
            return [rscript, "-e", f"rmarkdown::render({r_chaine(rel)})", *arguments], rel
    quarto = trouver_quarto()
    if quarto:
        commande = [quarto, "render", rel]
        if extension == ".ipynb":
            commande.append("--execute")
        commande.append("--no-cache")
        return [*commande, *arguments], rel
    raise ErreurSosie("Quarto est introuvable : installe-le (https://quarto.org) pour exécuter ce document.")


def interpreter_cibles(elements, racine):
    if not elements:
        raise ErreurSosie("Indique le script à exécuter, par exemple : sosie executer scripts/analyse.R")
    if elements[0] == "--":
        commande = elements[1:]
        if not commande:
            raise ErreurSosie("Après --, indique la commande à lancer.")
        if not shutil.which(commande[0]) and not Path(commande[0]).exists():
            raise ErreurSosie(f"Commande introuvable : {commande[0]}")
        return [(commande, None)]
    scripts = []
    for element in elements:
        if est_script(element):
            scripts.append(element)
        else:
            break
    arguments = elements[len(scripts):]
    if not scripts:
        premier = elements[0]
        if Path(premier).suffix.lower() in EXTENSIONS_SCRIPTS:
            proposes = scripts_du_projet(racine)
            liste = ("\n  Scripts du projet : " + ", ".join(proposes[:15])) if proposes else ""
            raise ErreurSosie(f"Script introuvable : {premier} (vérifie le nom et le dossier courant : {Path.cwd()}).{liste}")
        if Path(premier).is_file():
            raise ErreurSosie(
                f"Je ne sais pas exécuter « {premier} ». Scripts pris en charge : .R, .py, .qmd, .Rmd, .ipynb, .sh "
                "— ou bien : sosie executer -- commande arguments"
            )
        if not shutil.which(premier):
            proposes = scripts_du_projet(racine)
            proches = difflib.get_close_matches(premier, proposes, n=3, cutoff=0.5)
            liste = proches or proposes[:15]
            raise ErreurSosie(f"Script ou commande introuvable : {premier}"
                              + (f"\n  Scripts du projet : {', '.join(liste)}" if liste else ""))
        return [([premier, *arguments], None)]
    commandes = []
    for k, script in enumerate(scripts):
        commandes.append(commande_pour(script, arguments if k == len(scripts) - 1 else [], racine))
    return commandes


def dans_references(rel):
    return bool(rel.parts) and sans_accents_cle(rel.parts[0]) in DOSSIERS_COPIES


def ressemble_table_texte(chemin):
    try:
        with open(chemin, "rb") as f:
            debut = f.read(65536)
    except OSError:
        return False
    if b"\x00" in debut[:4096] and not debut[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return False
    for encodage in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            texte = debut.decode(encodage)
            break
        except UnicodeDecodeError:
            continue
    lignes = [l for l in texte.splitlines()[:200] if l.strip()]
    if len(lignes) < 20:
        return False
    for sep in (";", "\t", ",", "|"):
        comptes = [l.count(sep) for l in lignes[1:]]
        if not comptes:
            continue
        mode = max(set(comptes), key=comptes.count)
        if mode >= 1 and comptes.count(mode) >= 0.8 * len(comptes):
            return True
    return False


def ressemble_json_donnees(chemin):
    try:
        taille = chemin.stat().st_size
    except OSError:
        return False
    if taille > TAILLE_JSON_DONNEES:
        return True
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    if isinstance(donnees, list):
        return len(donnees) >= 20 and all(isinstance(x, (dict, list)) for x in donnees[:20])
    if isinstance(donnees, dict):
        listes = [v for v in donnees.values() if isinstance(v, (list, dict))]
        return any(len(v) >= 20 for v in listes)
    return False


def fichier_de_donnees(chemin, rel):
    if dans_references(rel) or cle_nom(chemin.name) == "dictionnaire_donnees.csv":
        return False
    extension = chemin.suffix.lower()
    if extension in EXT_DONNEES:
        return True
    if extension in (".txt", ".tsv", ".prn", ".asc", ""):
        return ressemble_table_texte(chemin)
    if extension == ".json":
        return ressemble_json_donnees(chemin)
    return False


def fichier_copie(chemin, rel):
    if dans_references(rel):
        return True
    nom = chemin.name
    plie = cle_nom(nom)
    if plie in NOMS_COPIES or plie.split(".")[0] in ("readme", "license", "licence") and chemin.suffix.lower() in ("", ".md", ".txt"):
        return True
    return chemin.suffix.lower() in EXT_COPIEES


def nom_exclu(nom):
    plie = cle_nom(nom)
    if plie in (".here", ".rprofile", ".lintr", ".gitignore", ".renviron"):
        return False
    return plie in EXCLUS or plie.startswith(".sosie") or plie.endswith("_cache") or fichier_ignore(nom)


def cache_knitr(dossier):
    try:
        noms = {p.name for p in Path(dossier).iterdir()}
    except OSError:
        return False
    return "__packages" in noms or any(n.endswith(".rdx") for n in noms)


def copier_projet(racine, destination):
    exclus = []
    non_copies = []

    def ignorer(dossier, noms):
        ignores = []
        for nom in noms:
            chemin = Path(dossier) / nom
            rel = chemin.relative_to(racine)
            if nom_exclu(nom):
                ignores.append(nom)
            elif chemin.is_symlink():
                ignores.append(nom)
                non_copies.append(rel.as_posix())
            elif chemin.is_dir():
                if cache_knitr(chemin):
                    ignores.append(nom)
            elif fichier_de_donnees(chemin, rel):
                ignores.append(nom)
                exclus.append(rel.as_posix())
            elif not fichier_copie(chemin, rel):
                ignores.append(nom)
                non_copies.append(rel.as_posix())
        return ignores

    destination.mkdir(parents=True, exist_ok=True)
    for element in sorted(racine.iterdir()):
        rel = element.relative_to(racine)
        if element.name in LIENS and element.is_dir():
            os.symlink(element.resolve(), destination / element.name, target_is_directory=True)
            continue
        if nom_exclu(element.name):
            continue
        if element.is_symlink():
            non_copies.append(rel.as_posix())
            continue
        if element.is_dir():
            if cache_knitr(element):
                continue
            shutil.copytree(element, destination / element.name, symlinks=True, ignore=ignorer)
        elif element.is_file():
            if fichier_de_donnees(element, rel):
                exclus.append(rel.as_posix())
                continue
            if not fichier_copie(element, rel):
                non_copies.append(rel.as_posix())
                continue
            shutil.copy2(element, destination / element.name)
    return exclus, non_copies


def fichiers_de_donnees_du_projet(racine, references=False):
    racine = Path(racine)
    trouves = []
    for dossier, sous, fichiers in os.walk(racine):
        rel_dossier = Path(dossier).relative_to(racine)
        if rel_dossier.parts:
            tete = sans_accents_cle(rel_dossier.parts[0])
            if tete in {DOSSIER_DONNEES, DOSSIER_RESULTATS, DOSSIER_VERIFIES} or (tete in DOSSIERS_COPIES) != references:
                sous[:] = []
                continue
        sous[:] = [d for d in sous if not d.startswith(".") and d not in LIENS and not d.endswith("_cache")
                   and cle_nom(d) not in {"_freeze", "_targets", "__pycache__", "site_libs", "quarantaine"}
                   and (rel_dossier.parts or not references or sans_accents_cle(d) in DOSSIERS_COPIES)]
        for f in fichiers:
            chemin = Path(dossier) / f
            rel = chemin.relative_to(racine)
            if f.startswith(".") or not rel_dossier.parts and references:
                continue
            if references:
                extension = chemin.suffix.lower()
                if extension in EXT_DONNEES or (extension in (".txt", ".tsv", ".prn", ".asc", "") and ressemble_table_texte(chemin)) \
                        or (extension == ".json" and ressemble_json_donnees(chemin)):
                    trouves.append(rel.as_posix())
            elif fichier_de_donnees(chemin, rel):
                trouves.append(rel.as_posix())
    return sorted(trouves)


def preparer_donnees_reelles(source, cible):
    shutil.copytree(source, cible, ignore=shutil.ignore_patterns(".*"))
    conversions = []
    for chemin, rel in lister_fichiers(cible):
        nouveau, _, _ = destination_de(rel, format_de(chemin))
        if nouveau == rel or (cible / nouveau).exists():
            continue
        try:
            tables = lire_fichier(chemin, rel)
            ecrire_fichier(cible, tables)
            conversions.append((rel, nouveau, None))
        except Exception as e:
            conversions.append((rel, nouveau, type(e).__name__))
    return conversions


def empreinte_projet(racine):
    etat = {}
    for dossier, sous, fichiers in os.walk(racine):
        sous[:] = [d for d in sous if cle_nom(d) not in SURVEILLANCE_IGNOREE and not d.endswith("_cache")
                   and not (Path(dossier) / d).is_symlink()]
        for f in fichiers:
            p = Path(dossier) / f
            try:
                st = p.lstat()
            except OSError:
                continue
            etat[p.relative_to(racine).as_posix()] = (st.st_size, st.st_mtime_ns)
    return etat


def mettre_en_quarantaine(racine, avant, apres, dossier, isole):
    deplaces, signales = [], []
    for rel, empreinte in apres.items():
        if avant.get(rel) == empreinte:
            continue
        nouveau = rel not in avant
        chemin = racine / rel
        extension = chemin.suffix.lower()
        if extension in EXT_CODE or chemin.name.startswith("."):
            if nouveau:
                signales.append(rel)
            continue
        if isole:
            signales.append(rel)
            continue
        cible = dossier / DOSSIER_QUARANTAINE / rel
        cible.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(chemin), str(cible))
            deplaces.append(rel)
        except OSError:
            signales.append(rel)
    return deplaces, signales


def chaine_sbpl(chemin):
    return '"' + str(chemin).replace("\\", "\\\\").replace('"', '\\"') + '"'


def chemin_disque(chemin):
    chemin = Path(os.path.realpath(chemin))
    parties = chemin.parts
    courant = Path(parties[0])
    for partie in parties[1:]:
        cible = unicodedata.normalize("NFC", partie).casefold()
        try:
            noms = os.listdir(courant)
        except OSError:
            return chemin
        exact = [n for n in noms if n == partie]
        if not exact:
            exact = [n for n in noms if unicodedata.normalize("NFC", n).casefold() == cible]
        courant = courant / (exact[0] if exact else partie)
    return courant


def profil_sbpl(racine, dossier, temporaire, strict):
    projet = chaine_sbpl(chemin_disque(racine))
    donnees = chaine_sbpl(chemin_disque(Path(racine) / DOSSIER_DONNEES))
    autorises = " ".join(f"(subpath {chaine_sbpl(chemin_disque(p))})" for p in (dossier, temporaire) if p)
    regles = ["(version 1)", "(allow default)"]
    if strict:
        maison = chemin_disque(Path.home())
        zones = [maison / n for n in ("Desktop", "Documents", "Downloads", "Movies", "Music", "Pictures", "Public")]
        zones += [maison / "Library" / "Mobile Documents", maison / "Library" / "CloudStorage", Path("/Volumes")]
        regles.append("(deny file-write* " + " ".join(f"(subpath {chaine_sbpl(z)})" for z in zones) + ")")
        regles.append(f"(allow file-write* {autorises})")
    regles.append(f"(deny file-write* (subpath {projet}))")
    regles.append(f"(deny file-read* (subpath {donnees}))")
    return "".join(regles)


def essai_bac_a_sable(profil, racine, dossier):
    def lance(*args):
        try:
            return subprocess.run(["/usr/bin/sandbox-exec", "-p", profil, *args], capture_output=True, timeout=20).returncode
        except Exception:
            return None

    sonde_projet = Path(racine) / ".sosie_sonde"
    sonde_execution = Path(dossier) / ".sosie_sonde"
    ecrit_projet = lance("/bin/sh", "-c", ': > "$1"', "sh", str(sonde_projet))
    if sonde_projet.exists():
        sonde_projet.unlink(missing_ok=True)
        return "inefficace"
    if ecrit_projet is None:
        return "erreur"
    fiche = Path(racine) / DOSSIER_DONNEES / "FICHE_SOSIE.md"
    if fiche.exists() and lance("/bin/cat", str(fiche)) == 0:
        return "inefficace"
    ecrit_execution = lance("/bin/sh", "-c", ': > "$1"', "sh", str(sonde_execution))
    present = sonde_execution.exists()
    sonde_execution.unlink(missing_ok=True)
    if ecrit_execution != 0 or not present:
        return "bloquant"
    return "ok"


def bac_a_sable_mac(racine, dossier, temporaire):
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").exists():
        return None, "indisponible"
    projet = os.path.realpath(racine)
    if os.path.realpath(dossier).startswith(projet + os.sep):
        return None, "indisponible"
    dernier = "erreur"
    for strict in (True, False):
        profil = profil_sbpl(racine, dossier, temporaire, strict)
        dernier = essai_bac_a_sable(profil, racine, dossier)
        if dernier == "ok":
            return ["/usr/bin/sandbox-exec", "-p", profil], "strict" if strict else "projet"
        if dernier == "inefficace":
            return None, "inefficace"
    return None, dernier


def nom_execution(etiquette):
    propre = "".join(c if c.isalnum() or c in "-_" else "_" for c in etiquette)[:40] or "execution"
    return f"{dt.datetime.now().strftime('%Y-%m-%d_%Hh%M-%S')}_{propre}"


def creer_dossier_execution(base, etiquette):
    base.mkdir(parents=True, exist_ok=True)
    nom = nom_execution(etiquette)
    for k in range(1, 100):
        candidat = base / (nom if k == 1 else f"{nom}-{k}")
        try:
            candidat.mkdir(exist_ok=False)
            return candidat
        except FileExistsError:
            continue
    raise ErreurSosie("Impossible de créer le dossier de l'exécution (trop d'exécutions simultanées ?).")


def dossier_temporaire(coffre):
    base = Path(coffre) / ".tmp"
    base.mkdir(parents=True, exist_ok=True)
    proteger_dossier(base)
    reel = Path(tempfile.mkdtemp(prefix="x", dir=base))
    if not any(c.isspace() for c in str(reel)):
        return reel, reel, None
    systeme = Path(tempfile.gettempdir())
    lien = systeme / f"sosie_{reel.name}"
    try:
        os.symlink(reel, lien)
    except OSError:
        return reel, reel, None
    if any(c.isspace() for c in str(lien)):
        return reel, reel, lien
    return lien, reel, lien


def etat_fichiers(dossier):
    etat = {}
    for chemin in Path(dossier).rglob("*"):
        if chemin.is_symlink() or not chemin.is_file():
            continue
        rel = chemin.relative_to(dossier).as_posix()
        if rel.startswith(DOSSIER_DONNEES + "/"):
            continue
        stat = chemin.stat()
        etat[rel] = [stat.st_size, stat.st_mtime_ns]
    return etat


def ecritures_exterieures(debut, exclure, larges=False):
    maison = Path.home()
    zones = [(maison, 0, False, ()), (Path("/tmp"), 1, True, ("claude",))]
    if larges:
        zones += [(maison / n, 2, False, ()) for n in ("Desktop", "Bureau", "Documents", "Downloads")]
    exclure = [os.path.realpath(e) for e in exclure if e]
    extensions = EXT_DONNEES | EXT_SORTIES_NOUVELLES | {".csv", ".xlsx"}
    trouves, vus = [], set()
    limite = time.time() + 3

    def exclu(p):
        r = os.path.realpath(p)
        return any(r == e or r.startswith(e + os.sep) for e in exclure)

    def parcourir(dossier, profondeur, filtrer, ignorer):
        if time.time() > limite or len(trouves) >= 20:
            return
        try:
            entrees = list(os.scandir(dossier))
        except OSError:
            return
        for e in entrees:
            if e.name.startswith(".") or e.name.startswith("sosie_") or e.name == "Library":
                continue
            if ignorer and e.name.lower().startswith(ignorer):
                continue
            try:
                if e.is_symlink():
                    continue
                if e.is_file():
                    if filtrer and Path(e.name).suffix.lower() not in extensions:
                        continue
                    if e.stat().st_mtime >= debut and not exclu(e.path):
                        r = os.path.realpath(e.path)
                        if r not in vus:
                            vus.add(r)
                            trouves.append(e.path)
                elif e.is_dir() and profondeur > 0 and not exclu(e.path):
                    parcourir(e.path, profondeur - 1, filtrer, ignorer)
            except OSError:
                continue

    for base, profondeur, filtrer, ignorer in zones:
        if base.exists():
            parcourir(base, profondeur, filtrer, ignorer)
    return trouves


def lancer(commande, dossier, environnement, journal, prefixe, afficher):
    try:
        processus = subprocess.Popen([*prefixe, *commande], cwd=dossier, env=environnement, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
    except FileNotFoundError:
        raise ErreurSosie(f"Commande introuvable : {commande[0]}")
    except OSError as e:
        raise ErreurSosie(f"Impossible de lancer « {commande[0]} » : {e.strerror}")
    compte = [0]

    def lire():
        for ligne in processus.stdout:
            compte[0] += 1
            if afficher:
                sys.stdout.write(ligne)
                sys.stdout.flush()
            journal.write(ligne)

    lecteur = threading.Thread(target=lire, daemon=True)
    lecteur.start()
    debut = time.time()
    prochain = 30
    try:
        while True:
            try:
                code = processus.wait(timeout=1)
                break
            except subprocess.TimeoutExpired:
                ecoule = time.time() - debut
                if not afficher and ecoule >= prochain:
                    minutes, secondes = divmod(int(ecoule), 60)
                    print(f"  … en cours ({minutes} min {secondes:02d} s, {compte[0]} ligne(s) dans le journal)", flush=True)
                    prochain += 30 if ecoule < 300 else 120
        lecteur.join(timeout=10)
        return code
    except KeyboardInterrupt:
        processus.terminate()
        try:
            code = processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()
            code = processus.wait()
        lecteur.join(timeout=5)
        journal.write("\n[interrompu]\n")
        return code if code else 130


def environnement_execution(racine, dossier, temporaire):
    environnement = dict(os.environ)
    environnement.update({
        "SOSIE_MODE": "reel",
        "SOSIE_DONNEES": str(dossier / DOSSIER_DONNEES),
        "SOSIE_RESULTATS": str(dossier / DOSSIER_RESULTATS),
        "TMPDIR": str(temporaire),
        "TMP": str(temporaire),
        "TEMP": str(temporaire),
    })
    for nom in (".venv", "venv"):
        bin_ = Path(racine) / nom / "bin"
        if (bin_ / "python").exists():
            environnement["PATH"] = str(bin_) + os.pathsep + environnement.get("PATH", "")
            environnement["VIRTUAL_ENV"] = str((Path(racine) / nom).resolve())
            environnement.setdefault("QUARTO_PYTHON", str(bin_ / "python"))
            break
    return environnement


def executer(racine, config, elements, afficher=False):
    from .config import verifier_coffre_projet

    coffre_projet = verifier_coffre_projet(racine, config)
    donnees_reelles = coffre_projet / DOSSIER_DONNEES
    if not donnees_reelles.exists() or not any(p for p in donnees_reelles.iterdir() if not p.name.startswith(".")):
        raise ErreurSosie(f"Aucune vraie donnée dans {donnees_reelles}.")
    commandes = interpreter_cibles(elements, racine)
    etiquette = "+".join(Path(rel).stem for _, rel in commandes if rel) or Path(commandes[0][0][0]).name
    dossier = creer_dossier_execution(coffre_projet / "executions", etiquette)
    exclus, non_copies = copier_projet(racine, dossier)
    conversions = preparer_donnees_reelles(donnees_reelles, dossier / DOSSIER_DONNEES)
    (dossier / DOSSIER_RESULTATS).mkdir(exist_ok=True)
    avant = etat_fichiers(dossier)
    temporaire, temporaire_reel, lien = dossier_temporaire(chemin_coffre())
    try:
        prefixe, mode = bac_a_sable_mac(racine, dossier, temporaire_reel)
        prefixe = prefixe or []
        (dossier / MANIFESTE_EXECUTION).write_text(json.dumps({
            "commandes": [c for c, _ in commandes],
            "scripts": [rel for _, rel in commandes if rel],
            "debut": dt.datetime.now().isoformat(timespec="seconds"),
            "projet": str(racine),
            "fichiers_avant": avant,
            "donnees_non_copiees": exclus,
            "non_copies": non_copies,
            "conversions": conversions,
            "bac_a_sable": bool(prefixe),
            "isolement": mode,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        environnement = environnement_execution(racine, dossier, temporaire)
        print(f"▶ Exécution sur les VRAIES données, dans le coffre :\n  {dossier}")
        if exclus:
            print(f"⚠ {len(exclus)} fichier(s) de données hors de donnees/ non copié(s) : {', '.join(exclus[:5])}"
                  + (" …" if len(exclus) > 5 else ""))
            print("  S'ils sont produits par un de tes scripts, lance les scripts à la suite : sosie executer prepa.R analyse.R")
            print("  S'ils viennent des vraies données, l'IA peut les lire : déplace-les dans le coffre.")
        if non_copies:
            print(f"  Non copiés (ni code ni references/) : {', '.join(non_copies[:6])}" + (" …" if len(non_copies) > 6 else ""))
            print("  Un fichier statique utile au script (logo, image, modèle) se range dans references/.")
        for rel, nouveau, erreur in conversions:
            if erreur:
                print(f"⚠ {rel} n'a pas pu être converti en {nouveau} ({erreur}) : le script ne le trouvera pas.")
            else:
                print(f"  {rel} converti en {nouveau} (comme dans le sosie)")
        if sys.platform == "darwin" and not prefixe:
            if mode == "inefficace":
                print("⚠ L'isolement macOS ne bloque pas l'accès au projet sur ce Mac : je surveille le projet pendant l'exécution.")
            else:
                print("⚠ Isolement macOS indisponible : je surveille le dossier du projet pendant l'exécution.")
        if not afficher:
            print("  La sortie du script va dans le journal du coffre (elle peut contenir de vraies données).")
        empreinte = empreinte_projet(racine)
        debut = time.time() - 1
        code = 0
        with open(dossier / JOURNAL, "w", encoding="utf-8") as journal:
            for commande, rel in commandes:
                print(f"\n▶ {' '.join(commande)}")
                journal.write(f"▶ {' '.join(commande)}\n")
                code = lancer(commande, dossier, environnement, journal, prefixe, afficher)
                if code != 0:
                    break
        deplaces, signales = mettre_en_quarantaine(racine, empreinte, empreinte_projet(racine), dossier, bool(prefixe))
        exterieurs = ecritures_exterieures(debut, [coffre_projet, chemin_coffre(), racine, temporaire_reel],
                                           larges=mode != "strict" and sys.platform == "darwin")
    finally:
        shutil.rmtree(temporaire_reel, ignore_errors=True)
        if lien is not None:
            try:
                os.unlink(lien)
            except OSError:
                pass
    apres = etat_fichiers(dossier)
    produits = sorted(rel for rel, e in apres.items()
                      if avant.get(rel) != e and rel not in (MANIFESTE_EXECUTION, JOURNAL) and not rel.startswith(DOSSIER_QUARANTAINE + "/"))
    manifeste = json.loads((dossier / MANIFESTE_EXECUTION).read_text(encoding="utf-8"))
    manifeste["fin"] = dt.datetime.now().isoformat(timespec="seconds")
    manifeste["code_retour"] = code
    manifeste["quarantaine"] = deplaces
    manifeste["modifies_pendant"] = signales
    manifeste["ecritures_exterieures"] = exterieurs
    (dossier / MANIFESTE_EXECUTION).write_text(json.dumps(manifeste, ensure_ascii=False, indent=1), encoding="utf-8")
    return dossier, code, {"exclus": exclus, "non_copies": non_copies, "conversions": conversions, "quarantaine": deplaces,
                           "signales": signales, "bac_a_sable": bool(prefixe), "isolement": mode, "produits": produits,
                           "exterieurs": exterieurs}


def derniere_execution(coffre_projet):
    dossier = Path(coffre_projet) / "executions"
    if not dossier.exists():
        return None
    executions = sorted(p for p in dossier.iterdir() if p.is_dir() and (p / MANIFESTE_EXECUTION).exists())
    return executions[-1] if executions else None
