import datetime as dt
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from .config import coffre_ferme, fermer_coffre, ouvrir_coffre
from .fiche import rediger_fiche
from .formats import destination_de, ecrire_fichier, environnement_r, lire_fichier, lister_fichiers, trouver_rscript
from .generation import fabriquer_sosie


def fabriquer_essai(dossier, rng):
    dossier = Path(dossier)
    n = 120
    ids = [f"ESSAI-{i:04d}" for i in range(1, n + 1)]
    noms = [f"NOMREEL{i}" for i in range(n)]
    sexes = [str(rng.choice(["F", "M"])) for _ in range(n)]
    inclusions = [dt.date(2022, 1, 3) + dt.timedelta(days=int(rng.integers(0, 300))) for _ in range(n)]
    lignes = ["id_patient;nom;date_naissance;sexe;poids;traitement;date_inclusion;commentaire"]
    for i in range(n):
        naissance = (dt.date(1950, 1, 1) + dt.timedelta(days=int(rng.integers(0, 18000)))).strftime("%d/%m/%Y")
        traitement = "essai rare" if i == 5 else str(rng.choice(["aucun", "metformine"]))
        lignes.append(f"{ids[i]};{noms[i]};{naissance};{sexes[i]};{rng.normal(110, 15):.1f}".replace(".", ",")
                      + f";{traitement};{inclusions[i].strftime('%d/%m/%Y')};Vu par le Dr SECRETDOC{i} à domicile")
    (dossier / "patients.csv").write_bytes(("\r\n".join(lignes) + "\r\n").encode("cp1252"))
    visites = []
    for i in range(n):
        niveau = rng.normal(110, 15)
        for k in range(int(rng.integers(2, 5))):
            visites.append({"id_patient": ids[i], "num_visite": k + 1, "sexe": sexes[i],
                            "poids": round(float(niveau - 2 * k + rng.normal(0, 1.5)), 1),
                            "date": dt.datetime.combine(inclusions[i], dt.time()) + dt.timedelta(days=90 * k + int(rng.integers(0, 20)))})
    with pd.ExcelWriter(dossier / "visites.xlsx") as w:
        pd.DataFrame(visites).to_excel(w, sheet_name="Visites", index=False)
        pd.DataFrame({"id_patient": ids, "groupe": rng.choice(["A", "B"], n)}).to_excel(w, sheet_name="Groupes", index=False)
    pd.DataFrame({"id_patient": ids, "dose": rng.choice([0.25, 0.5, 1.0, 2.4], n)}).to_parquet(dossier / "doses.parquet", index=False)
    return set(ids), set(noms)


def lancer():
    rng = np.random.default_rng(0)
    resultats = []

    def controle(condition, message):
        resultats.append((bool(condition), message))
        print(("  ✓ " if condition else "  ✗ ") + message)

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "vraies"
        cible = Path(tmp) / "sosie"
        source.mkdir()
        vrais_ids, vrais_noms = fabriquer_essai(source, rng)
        tables = []
        for chemin, rel in lister_fichiers(source):
            tables.extend(lire_fichier(chemin, rel))
        sosies, profil = fabriquer_sosie(tables, 11, 1)
        par_fichier = {}
        for t in sosies:
            par_fichier.setdefault(t.fichier, []).append(t)
        for groupe in par_fichier.values():
            ecrire_fichier(cible, groupe)
        fiche = rediger_fiche(sosies, profil, [destination_de(t.fichier, t.format)[0] for t in sosies], [], "autotest", [], [])
        relus = {}
        for chemin, rel in lister_fichiers(cible):
            for t in lire_fichier(chemin, rel):
                relus[(rel, t.feuille)] = t
        controle(len(relus) == len(tables), "mêmes fichiers et feuilles")
        for t in tables:
            s = relus.get((t.fichier, t.feuille))
            controle(s is not None and s.noms == t.noms and s.n_lignes == t.n_lignes, f"{t.nom_affiche} : mêmes colonnes et même nombre de lignes")
        brut = (cible / "patients.csv").read_bytes()
        controle(b"\r\n" in brut and b";" in brut.split(b"\r\n")[0], "CSV : séparateur et fins de ligne conservés")
        texte = brut.decode("cp1252")
        controle(not any(i in texte for i in vrais_ids), "aucun vrai identifiant dans le sosie")
        controle(not any(nm in texte for nm in vrais_noms), "aucun vrai nom dans le sosie")
        controle("SECRETDOC" not in texte, "texte libre remplacé")
        controle("essai rare" not in texte and "MODALITE_RARE" in texte, "modalité rare remplacée par MODALITE_RARE")
        controle(not any(i in fiche for i in vrais_ids) and "SECRETDOC" not in fiche, "la fiche ne contient aucune vraie valeur")
        patients = pd.read_csv(cible / "patients.csv", sep=";", decimal=",", encoding="cp1252")
        visites = pd.read_excel(cible / "visites.xlsx", sheet_name="Visites")
        doses = pd.read_parquet(cible / "doses.parquet")
        controle(set(visites["id_patient"]) <= set(patients["id_patient"]), "jointure visites → patients conservée")
        controle(set(doses["id_patient"]) == set(patients["id_patient"]), "jointure doses → patients conservée")
        controle(patients["poids"].dtype == float, "nombres à virgule relus correctement")
        ordre = visites.groupby("id_patient")["date"].apply(lambda s: s.is_monotonic_increasing).all()
        controle(ordre, "visites chronologiques par patient")
        rangs = visites.groupby("id_patient")["num_visite"].apply(lambda s: list(s) == list(range(1, len(s) + 1))).all()
        controle(rangs, "numéros de visite 1, 2, 3… par patient")
        fusion = visites.merge(patients, on="id_patient", suffixes=("", "_p"))
        inclusion = pd.to_datetime(fusion["date_inclusion"], format="%d/%m/%Y")
        controle((fusion["date"] >= inclusion).mean() >= 0.95, "visites postérieures à l'inclusion du même patient")
        controle((fusion["sexe"] == fusion["sexe_p"]).all(), "même sexe pour un même patient dans les deux fichiers")
        formats = Path(tmp) / "formats"
        formats.mkdir()
        df = pd.DataFrame({"id_patient": [f"F-{i:04d}" for i in range(60)], "age": rng.integers(18, 90, 60).astype("float64"),
                           "sexe": rng.choice(["F", "M"], 60)})
        import pyreadr
        import pyreadstat

        pyreadstat.write_sav(df, str(formats / "q.sav"))
        pyreadstat.write_dta(df, str(formats / "q.dta"))
        pyreadstat.write_xport(df, str(formats / "q.xpt"))
        pyreadr.write_rds(str(formats / "q.rds"), df)
        df.to_json(formats / "q.json", orient="records")
        with sqlite3.connect(formats / "q.sqlite") as cx:
            df.to_sql("q", cx, index=False)
        sortie = Path(tmp) / "formats_sosie"
        for chemin, rel in lister_fichiers(formats):
            try:
                lues = lire_fichier(chemin, rel)
                sos, _ = fabriquer_sosie(lues, 11, 1)
                ecrire_fichier(sortie, sos)
                relu = lire_fichier(sortie / destination_de(rel, lues[0].format)[0], rel)
                ok = relu[0].noms == lues[0].noms and relu[0].n_lignes == 60
            except Exception as e:
                ok = False
                print(f"    ({type(e).__name__} : {e})")
            controle(ok, f"format {Path(rel).suffix} : lu, reproduit et relu")
        rscript = trouver_rscript()
        if rscript:
            df = pd.DataFrame({"id": range(1, 41), "groupe": pd.Categorical(rng.choice(["a", "b"], 40)),
                               "date": [dt.date(2023, 1, 1) + dt.timedelta(days=int(d)) for d in rng.integers(0, 300, 40)]})
            pyreadr.write_rds(str(source / "r.rds"), df)
            t = lire_fichier(source / "r.rds", "r.rds")
            sos, _ = fabriquer_sosie(t, 11, 1)
            ecrire_fichier(cible, sos)
            r = subprocess.run([rscript, "--vanilla", "-e", f'x <- readRDS("{cible / "r.rds"}"); cat(class(x$groupe)[1])'],
                               capture_output=True, text=True, env=environnement_r())
            controle(r.stdout.strip() == "factor", "fichier R écrit avec R (facteurs conservés)")
        else:
            print("  · R n'est pas installé : test des fichiers R ignoré (installe R si tu l'utilises)")
        faux = Path(tmp) / "coffre_essai"
        (faux / "projet").mkdir(parents=True)
        (faux / "projet" / "vraies.csv").write_text("id;nom\n1;NOMREEL\n", encoding="utf-8")
        fermer_coffre(faux, forcer=True)
        ferme = coffre_ferme(faux)
        lisible = True
        if ferme and os.geteuid() != 0:
            try:
                (faux / "projet" / "vraies.csv").read_text(encoding="utf-8")
            except PermissionError:
                lisible = False
        ouvrir_coffre(faux)
        controle(ferme and (not lisible or os.geteuid() == 0), "coffre fermé à clé : illisible pour les autres programmes")
    echecs = [m for ok, m in resultats if not ok]
    print()
    print("Tout fonctionne." if not echecs else f"{len(echecs)} problème(s) : copie ce message à l'IA.")
    return 0 if not echecs else 1
