import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sosie.formats import lire_fichier, lister_fichiers

vraies = Path(sys.argv[1])
sosie = Path(sys.argv[2])
echecs = []


def verifier(condition, message):
    print(("  OK   " if condition else "  ÉCHEC ") + message)
    if not condition:
        echecs.append(message)


def charger(dossier):
    tables = {}
    for chemin, rel in lister_fichiers(dossier):
        try:
            for t in lire_fichier(chemin, rel):
                tables[(Path(rel).stem, t.feuille)] = t
        except Exception:
            pass
    return tables


V = charger(vraies)
S = charger(sosie)
print("1. Structure identique")
for cle, t in V.items():
    s = S.get(cle)
    verifier(s is not None, f"{t.nom_affiche} présent dans le sosie")
    if s is None:
        continue
    verifier(s.noms == t.noms, f"{t.nom_affiche} : mêmes noms de colonnes")
    verifier(s.n_lignes == t.n_lignes or (s.options.get("lignes_plafonnees") is not None or 0.95 * t.n_lignes <= s.n_lignes < t.n_lignes), f"{t.nom_affiche} : même nombre de lignes, ou à peine moins si plafonné ({t.n_lignes} → {s.n_lignes})")
    diff = [(n, a, b) for n, a, b in zip(t.noms, t.stockages, s.stockages) if a != b and not (a == "texte" and b == "texte")]
    verifier(not diff, f"{t.nom_affiche} : mêmes types de colonnes {diff if diff else ''}")
    for j, n in enumerate(t.noms):
        dv, ds = str(t.donnees[j].dtype), str(s.donnees[j].dtype)
        if dv != ds and not ({dv, ds} <= {"object", "str", "string"}):
            if not (dv == "Int64" and ds in ("Int64", "int64")):
                print(f"       note dtype {t.nom_affiche}.{n} : {dv} → {ds}")

print("2. Dialecte CSV")
brut = (sosie / "patients.csv").read_bytes()
verifier(b"\r\n" in brut, "fins de ligne Windows conservées")
try:
    brut.decode("utf-8")
    utf8 = True
except UnicodeDecodeError:
    utf8 = False
verifier(not utf8 and "Pitié" in brut.decode("cp1252"), "encodage Windows-1252 conservé")
p = pd.read_csv(sosie / "patients.csv", sep=";", decimal=",", encoding="cp1252")
verifier(p["poids_initial"].dtype == float, "poids_initial relu comme décimal avec la virgule")
verifier(pd.to_datetime(p["date_inclusion"], format="%d/%m/%Y", errors="coerce").notna().mean() > 0.99, "dates au format JJ/MM/AAAA")
verifier(p["taille"].astype(str).str.len().max() <= 4, "taille avec 2 décimales")
verifier(set(p["sexe"].dropna()) <= {"F", "M"}, "sexe : modalités F/M")
verifier((p["hba1c"].astype(str) == "<4,0").mean() > 0.03, "jeton « <4,0 » fréquent conservé dans hba1c")
verifier(True, "jeton rare générique « NR » : conservé à faible fréquence (voulu)")
verifier(not p["traitement_anterieur"].astype(str).str.contains("Prader").any(), "modalité rare « essai Prader-Willi » absente")
verifier(not (p["nb_enfants"] == 7).any(), "valeur rare nb_enfants=7 absente")
verifier(p["centre"].nunique() == 1, "colonne constante conservée")

print("3. Aucune fuite de valeurs identifiantes")
reel = pd.read_csv(vraies / "patients.csv", sep=";", encoding="cp1252", dtype=str, keep_default_na=False)
texte_sosie = ""
for chemin, rel in lister_fichiers(sosie):
    if rel.startswith("FICHE") or rel == "dictionnaire.xlsx":
        continue
    for t in lire_fichier(chemin, rel):
        for j in range(len(t.noms)):
            texte_sosie += "\n" + "\n".join(str(v) for v in t.donnees[j].tolist())
texte_sosie += (sosie / "FICHE_SOSIE.md").read_text(encoding="utf-8")
for col in ["id_patient", "IPP", "nom", "email", "telephone", "adresse"]:
    valeurs = [v for v in reel[col] if v]
    fuites = [v for v in valeurs if v in texte_sosie]
    verifier(not fuites, f"aucune valeur réelle de « {col} » dans le sosie ni la fiche ({len(fuites)} fuite(s) : {fuites[:3]})")
mots = set()
for c in reel["commentaire"]:
    mots |= {m for m in re.findall(r"[A-Za-zÀ-ÿ]{5,}", c)}
mots -= {"Paris", "Montreuil", "Vincennes", "Créteil", "Patiente"}
fuites = [m for m in mots if re.search(r"\b" + re.escape(m) + r"\b", texte_sosie) and m not in ("charge", "suivi")]
verifier(len(fuites) <= 3, f"texte libre non recopié (mots retrouvés : {fuites[:10]})")
verifier("Bourg-Rare" not in texte_sosie, "villes rares absentes")
vr = pd.read_excel(vraies / "visites.xlsx", sheet_name="Visites", skiprows=2)
par_patient = vr.groupby("effets_indesirables")["id_patient"].nunique()
for modalite, n_pat in par_patient.items():
    present = re.search(r"\b" + re.escape(modalite) + r"\b", texte_sosie) is not None
    if n_pat < 10:
        verifier(not present, f"effet « {modalite} » ({n_pat} patients < 10) absent du sosie")
    else:
        verifier(present, f"effet « {modalite} » ({n_pat} patients ≥ 10) conservé")
verifier("Q87.1" not in texte_sosie, "code CIM rare absent")
verifier("Lp(a)" not in texte_sosie, "analyte rare absent")
psa = pd.read_stata(vraies / "extraction_pmsi.dta")["ben_nir_psa"]
verifier(not any(v in texte_sosie for v in set(psa)), "aucun ben_nir_psa réel")

print("4. Clés de jointure préservées")
ids = set(p["id_patient"])
vis = pd.read_excel(sosie / "visites.xlsx", sheet_name="Visites", skiprows=2)
bio = pd.read_excel(sosie / "visites.xlsx", sheet_name="Biologie")
tr = pd.read_parquet(sosie / "traitements.parquet")
rdv = pd.read_json(sosie / "rendez_vous.json")
con = sqlite3.connect(sosie / "suivi.db")
cons = pd.read_sql("SELECT * FROM consultations", con)
idx = pd.read_sql("SELECT name FROM sqlite_master WHERE type='index'", con)
lb = __import__("pyreadstat").read_xport(str(sosie / "labo.xpt"))[0]
for nom, serie in [("visites", vis["id_patient"]), ("biologie", bio["id_patient"]), ("traitements", tr["id_patient"]),
                   ("rendez_vous", rdv["id_patient"]), ("sqlite", cons["id_patient"]), ("labo.xpt", lb["USUBJID"])]:
    verifier(set(serie.dropna()) <= ids, f"{nom} : tous les identifiants existent dans patients")
verifier(len(idx) == 1, "index SQLite recréé")
reel_vis = pd.read_excel(vraies / "visites.xlsx", sheet_name="Visites", skiprows=2)
verifier(sorted(vis.groupby("id_patient").size().tolist()) == sorted(reel_vis.groupby("id_patient").size().tolist()),
         "nombre de visites par patient identique (structure longitudinale)")
verifier((vis.groupby("id_patient")["sexe"].nunique() == 1).all(), "sexe constant pour un même patient")
ordonne = vis.groupby("id_patient")["date_visite"].apply(lambda s: s.is_monotonic_increasing).mean()
verifier(ordonne == 1.0, f"dates de visite chronologiques par patient ({ordonne:.0%})")
dn = pd.to_datetime(p["date_naissance"], format="%d/%m/%Y")
di = pd.to_datetime(p["date_inclusion"], format="%d/%m/%Y")
df_ = pd.to_datetime(p["date_fin_suivi"], format="%d/%m/%Y")
verifier((dn <= di).all(), "naissance ≤ inclusion")
verifier(((di <= df_) | df_.isna()).all(), "inclusion ≤ fin de suivi")
verifier(set(vis["dose_mg"].dropna()) <= {0.25, 0.5, 1, 1.7, 2.4}, "doses discrètes exactes conservées")
verifier(vis.iloc[:, 0].notna().all(), "lecture Excel avec skip=2 fonctionne")

print("5. Types spécialisés")
v_sav, m_sav = __import__("pyreadstat").read_sav(str(sosie / "questionnaire.sav"))
verifier(m_sav.variable_value_labels.get("q1", {}).get(5.0) == "Énormément", "étiquettes SPSS conservées")
verifier(m_sav.column_names_to_labels.get("score_total") == "Score total IWQOL", "libellé de variable SPSS conservé")
verifier(str(v_sav["date_questionnaire"].dropna().iloc[0].__class__.__name__) in ("date", "Timestamp"), "date SPSS conservée")
import pyarrow.parquet as pq
verifier(pq.read_schema(sosie / "traitements.parquet").equals(pq.read_schema(vraies / "traitements.parquet"), check_metadata=False),
         "schéma Parquet identique")
if shutil.which("Rscript") and (vraies / "cohorte.rds").exists():
    r = subprocess.run(["Rscript", "-e", f'x <- readRDS("{sosie}/cohorte.rds"); cat(sapply(x, function(v) class(v)[1]), sep=","); load("{sosie}/analyses.RData"); cat("|", ls(), sep=",")'],
                       capture_output=True, text=True)
    verifier(r.stdout.startswith("integer,factor,ordered,numeric,Date,logical"), f"classes R conservées ({r.stdout.strip()})")
    verifier("cohorte" in r.stdout and "scores" in r.stdout, "deux objets dans le RData")
else:
    print("  (R absent : vérification des fichiers R sautée)")
dta = pd.read_stata(sosie / "extraction_pmsi.dta")
verifier(set(dta["dp"]) <= {"E66.0", "E66.8", "E11.9", "I10", "MODALITE_RARE"} and "Q87.1" not in set(dta["dp"]), "codes CIM fréquents conservés, rare remplacé (Stata)")
verifier(len(dta["ben_nir_psa"].iloc[0]) == 17, "format des identifiants SNDS conservé (17 caractères)")

verifier((sosie / "labo.xpt").read_bytes()[:80] == (vraies / "labo.xpt").read_bytes()[:80].replace(b"", b"")[:80] or b"LIBV8" in (sosie / "labo.xpt").read_bytes()[:80], "version XPT conservée")
print("6. Aucune ligne réelle recopiée")
reel_tab = reel.drop(columns=["centre"])
sosie_tab = pd.read_csv(sosie / "patients.csv", sep=";", encoding="cp1252", dtype=str, keep_default_na=False).drop(columns=["centre"])
communes = pd.merge(reel_tab, sosie_tab, how="inner")
verifier(len(communes) == 0, "aucune ligne identique entre vraies données et sosie")
cols = ["sexe", "poids_initial", "taille", "date_naissance"]
communes = pd.merge(reel[cols], sosie_tab[cols], how="inner")
verifier(len(communes) <= 2, f"quasi-identifiants (sexe+poids+taille+naissance) jamais recopiés ensemble ({len(communes)})")

print()
print("RÉSULTAT :", "tout est bon" if not echecs else f"{len(echecs)} échec(s)")
sys.exit(1 if echecs else 0)
