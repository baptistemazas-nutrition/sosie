import datetime as dt
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
import pyreadstat

dest = Path(sys.argv[1])
dest.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(2026)
N = 312

NOMS = ["DUPUIS", "LEBLANC", "FAVRE", "KONATE", "NGUYEN", "BENALI", "ROCHE", "VASSEUR", "TESSIER", "MARECHAL",
        "COLIN", "PICARD", "AUBERT", "LACROIX", "RENAUD", "SCHMITT", "BARON", "CARON", "HUET", "COSTE"]
PRENOMS = ["Aurélie", "Bruno", "Cécile", "Didier", "Émilie", "Fabrice", "Ginette", "Hervé", "Isabelle", "Jérôme",
           "Karima", "Laurent", "Mireille", "Noël", "Odile", "Pascal", "Rachida", "Sylvain", "Thérèse", "Yannick"]

ids = [f"SEMA-{i:04d}" for i in range(1, N + 1)]
noms = [NOMS[i % 20] + ("" if i < 20 else f"-{NOMS[(i * 7) % 20]}") for i in range(N)]
prenoms = [PRENOMS[(i * 3) % 20] for i in range(N)]
naiss = [dt.date(1950, 1, 1) + dt.timedelta(days=int(d)) for d in rng.integers(0, 365 * 50, N)]
sexe = rng.choice(["F", "M"], N, p=[0.68, 0.32])
villes_freq = ["Paris", "Créteil", "Saint-Denis", "Montreuil", "Vincennes"]
villes = [villes_freq[i % 5] if rng.random() < 0.8 else f"Bourg-Rare-{i}" for i in range(N)]
cps = [("750" + f"{rng.integers(1, 21):02d}") if v == "Paris" else ("94000" if v == "Créteil" else f"9{rng.integers(1, 5)}{rng.integers(100, 999)}") for v in villes]
tels = [f"06 {rng.integers(10, 99)} {rng.integers(10, 99)} {rng.integers(10, 99)} {rng.integers(10, 99)}" for _ in range(N)]
emails = [f"{p.lower()}.{n.lower()}{i}@example.com".replace("é", "e").replace("è", "e") for i, (p, n) in enumerate(zip(prenoms, noms))]
adresses = [f"{rng.integers(1, 200)} rue {NOMS[(i * 5) % 20].title()}" for i in range(N)]
poids = np.round(rng.normal(118, 18, N), 1)
taille = np.round(rng.normal(1.68, 0.09, N), 2)
imc = np.round(poids / taille ** 2, 1)
hba1c = []
for i in range(N):
    u = rng.random()
    if u < 0.08:
        hba1c.append("<4,0")
    elif u < 0.09:
        hba1c.append("NR")
    elif u < 0.12:
        hba1c.append("")
    else:
        hba1c.append(f"{rng.normal(6.4, 1.1):.1f}".replace(".", ","))
diab = rng.choice(["Oui", "Non"], N, p=[0.35, 0.65])
comment = [f"Patiente adressée par Dr {NOMS[(i * 11) % 20].title()} pour prise en charge obésité, suivi à {villes[i]}." if rng.random() < 0.6 else "" for i in range(N)]
incl = [dt.date(2021, 1, 1) + dt.timedelta(days=int(d)) for d in rng.integers(0, 900, N)]
fin = [d + dt.timedelta(days=int(rng.integers(180, 700))) if rng.random() < 0.85 else None for d in incl]
trait = rng.choice(["aucun", "liraglutide", "orlistat", "metformine", "essai Prader-Willi", "chirurgie antérieure"], N,
                   p=[0.6, 0.15, 0.1, 0.12, 0.006, 0.024])
enfants = rng.choice([0, 1, 2, 3, 4, 7], N, p=[0.3, 0.25, 0.25, 0.12, 0.075, 0.005])
ipp = [str(8010000000 + int(x)) for x in rng.choice(9_000_000, N, replace=False)]

fr = lambda d: "" if d is None else d.strftime("%d/%m/%Y")
lignes = ["id_patient;IPP;nom;prenom;date_naissance;sexe;ville;code_postal;telephone;email;adresse;poids_initial;taille;imc;hba1c;diabete_t2;centre;commentaire;date_inclusion;date_fin_suivi;traitement_anterieur;nb_enfants"]
for i in range(N):
    champs = [ids[i], ipp[i], noms[i], prenoms[i], fr(naiss[i]), sexe[i], villes[i], cps[i], tels[i], emails[i], adresses[i],
              f"{poids[i]:.1f}".replace(".", ","), f"{taille[i]:.2f}".replace(".", ","), f"{imc[i]:.1f}".replace(".", ","),
              hba1c[i], diab[i], "Pitié-Salpêtrière", comment[i], fr(incl[i]), fr(fin[i]), trait[i], str(enfants[i])]
    lignes.append(";".join(champs))
(dest / "patients.csv").write_bytes(("\r\n".join(lignes) + "\r\n").encode("cp1252"))

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Visites"
ws.append(["Suivi SEMASEARCH — service du Pr Exemple"])
ws.append([])
ws.append(["id_patient", "num_visite", "date_visite", "poids", "dose_mg", "effets_indesirables", "sexe", "tour_taille", "statut"])
doses = [0.25, 0.5, 1, 1.7, 2.4]
for i in range(N):
    nv = int(rng.integers(3, 7))
    d = dt.datetime.combine(incl[i], dt.time())
    p = poids[i]
    for v in range(1, nv + 1):
        effet = rng.choice(["aucun", "nausées", "diarrhée", "constipation", "pancréatite"], p=[0.6, 0.2, 0.1, 0.095, 0.005])
        tt = None if rng.random() < 0.1 else int(rng.normal(120, 12))
        ws.append([ids[i], v, d, round(float(p), 1), doses[min(v - 1, 4)], str(effet), str(sexe[i]), tt, "en cours" if v < nv else "terminé"])
        d = d + dt.timedelta(days=int(rng.integers(60, 100)))
        p = p * (1 - rng.uniform(0.0, 0.05))
ws2 = wb.create_sheet("Biologie")
ws2.append(["id_patient", "date_prelevement", "analyte", "valeur", "unite", "commentaire_labo"])
for i in range(N):
    for analyte, unite, m, s in [("HbA1c", "%", 6.4, 1), ("LDL", "g/L", 1.2, 0.3), ("CRP", "mg/L", 5, 3)]:
        ws2.append([ids[i], dt.datetime.combine(incl[i], dt.time(8, int(rng.integers(0, 59)))), analyte, round(float(rng.normal(m, s)), 2), unite,
                    f"Prélèvement réalisé par {PRENOMS[i % 20]} {NOMS[(i + 3) % 20]}" if rng.random() < 0.3 else None])
    if i < 3:
        ws2.append([ids[i], dt.datetime.combine(incl[i], dt.time(9, 0)), "Lp(a)", 1.8, "g/L", None])
wb.save(dest / "visites.xlsx")

molecules = rng.choice(["semaglutide", "liraglutide", "tirzepatide", "dulaglutide"], N, p=[0.7, 0.15, 0.12, 0.03])
atc = {"semaglutide": "A10BJ06", "liraglutide": "A10BJ02", "tirzepatide": "A10BX16", "dulaglutide": "A10BJ05"}
tr = pd.DataFrame({
    "id_patient": ids,
    "molecule": pd.Categorical(molecules, categories=["semaglutide", "liraglutide", "tirzepatide", "dulaglutide"]),
    "code_atc": [atc[m] for m in molecules],
    "date_debut": pd.to_datetime(incl),
    "date_fin": [None if f is None else f for f in fin],
    "posologie_mg": rng.choice([0.25, 0.5, 1.0, 1.7, 2.4], N),
    "observance": rng.integers(40, 101, N).astype("int32"),
    "arret": rng.random(N) < 0.2,
})
tr.to_parquet(dest / "traitements.parquet", index=False)

q = pd.DataFrame({
    "num_inclusion": np.arange(1001, 1001 + N, dtype=float),
    **{f"q{k}": rng.integers(1, 6, N).astype(float) for k in range(1, 6)},
    "score_total": np.round(rng.normal(55, 12, N), 1),
    "date_questionnaire": [d + dt.timedelta(days=7) for d in incl],
})
etiq = {f"q{k}": {1.0: "Pas du tout", 2.0: "Un peu", 3.0: "Moyennement", 4.0: "Beaucoup", 5.0: "Énormément"} for k in range(1, 6)}
pyreadstat.write_sav(q, str(dest / "questionnaire.sav"), column_labels={"score_total": "Score total IWQOL", "q1": "Fonction physique"},
                     variable_value_labels=etiq)

dp = rng.choice(["E66.0", "E66.8", "E11.9", "I10", "Q87.1"], 700, p=[0.5, 0.2, 0.18, 0.115, 0.005])
psa = {i: "".join(rng.choice(list("0123456789ABCDEF"), 17)) for i in ids}
idx = rng.integers(0, N, 700)
pmsi = pd.DataFrame({
    "ben_nir_psa": [psa[ids[i]] for i in idx],
    "dp": dp,
    "date_entree": (pd.to_datetime([incl[i] for i in idx]) + pd.to_timedelta(rng.integers(0, 300, 700), unit="D")).astype("datetime64[us]"),
    "duree_sejour": rng.integers(0, 15, 700).astype(float),
    "ghm": rng.choice(["10M02T", "10M021", "23M20T", "05M092"], 700),
})
pyreadstat.write_dta(pmsi, str(dest / "extraction_pmsi.dta"))

lb = pd.DataFrame({
    "USUBJID": [ids[i] for i in rng.integers(0, N, 400)],
    "LBTESTCD": rng.choice(["GLUC", "INS", "TG"], 400),
    "LBORRES": np.round(rng.normal(1.1, 0.3, 400), 2),
    "LBDTC": (pd.to_datetime("2022-01-01") + pd.to_timedelta(rng.integers(0, 700, 400), unit="D")).astype("datetime64[us]"),
})
pyreadstat.write_xport(lb, str(dest / "labo.xpt"), table_name="LB")

rdv = []
for i in range(N):
    for k in range(int(rng.integers(1, 4))):
        rdv.append({"id_patient": ids[i], "date_rdv": (incl[i] + dt.timedelta(days=30 * (k + 1))).isoformat(),
                    "type_rdv": str(rng.choice(["médecin", "diététicien", "APA"])), "presence": bool(rng.random() < 0.85)})
(dest / "rendez_vous.json").write_text(json.dumps(rdv, ensure_ascii=False, indent=2), encoding="utf-8")

con = sqlite3.connect(dest / "suivi.db")
con.execute("CREATE TABLE consultations (id INTEGER PRIMARY KEY, id_patient TEXT NOT NULL, date_consult TEXT, motif TEXT, duree_min INTEGER)")
con.execute("CREATE INDEX idx_patient ON consultations(id_patient)")
for k in range(900):
    i = int(rng.integers(0, N))
    con.execute("INSERT INTO consultations (id_patient, date_consult, motif, duree_min) VALUES (?,?,?,?)",
                (ids[i], (incl[i] + dt.timedelta(days=int(rng.integers(0, 500)))).isoformat(),
                 str(rng.choice(["suivi", "bilan", "urgence", "téléconsultation"], p=[0.6, 0.25, 0.05, 0.1])), int(rng.integers(10, 60))))
con.commit()
con.close()

pd.DataFrame({"variable": ["id_patient", "poids_initial"], "description": ["Identifiant étude", "Poids à l'inclusion (kg)"]}).to_excel(dest / "dictionnaire.xlsx", index=False)
(dest / "notice.pdf").write_bytes(b"%PDF-1.4 faux")

code_r = f"""
set.seed(1)
n <- {N}
cohorte <- data.frame(
  id = 1:n,
  groupe = factor(sample(c("controle","intervention"), n, TRUE), levels = c("controle","intervention")),
  severite = factor(sample(c("legere","moderee","severe"), n, TRUE), levels = c("legere","moderee","severe"), ordered = TRUE),
  imc = round(rnorm(n, 38, 5), 1),
  date_incl = as.Date("2021-01-01") + sample(0:900, n, TRUE),
  actif = sample(c(TRUE, FALSE, NA), n, TRUE),
  stringsAsFactors = FALSE)
scores <- data.frame(id = 1:n, score = rnorm(n), stringsAsFactors = FALSE)
saveRDS(cohorte, "{dest}/cohorte.rds")
save(cohorte, scores, file = "{dest}/analyses.RData")
"""
if shutil.which("Rscript"):
    subprocess.run(["Rscript", "-e", code_r], check=True)
else:
    print("Rscript absent : cohorte.rds et analyses.RData ne sont pas créés")
print("cohorte fictive écrite dans", dest)
