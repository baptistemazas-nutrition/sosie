import hashlib
import hmac
import re
import string
import unicodedata
from collections import Counter

from .listes import DOMAINES_EMAIL, NOMS, NOMS_VOIES, PRENOMS, TYPES_VOIES, VILLES

CHIFFRES = string.digits
MAJUSCULES = string.ascii_uppercase
MINUSCULES = string.ascii_lowercase


def classe_caractere(c):
    if c.isdigit():
        return "D"
    if c.isalpha():
        return "U" if c.isupper() else ("L" if c.islower() else "U")
    return None


def motif(valeur):
    return tuple(classe_caractere(c) or ("=" + c) for c in valeur)


RE_PREFIXE_CHIFFRES = re.compile(r"^(\D*?)(\d+)$")


def minuscules(valeur):
    return "".join(c.lower() if len(c.lower()) == 1 else c for c in valeur)


def recaser(faux, modele):
    if len(faux) != len(modele):
        return faux
    return "".join(f.upper() if m.isupper() else f for f, m in zip(faux, modele))


class Remplaceur:
    def __init__(self, rng, seuil=10):
        self.rng = rng
        self.seuil = seuil
        self.valeurs = set()
        self.bruts = set()
        self.prefixes = None
        self.correspondance = {}

    def ajouter(self, cles):
        for c in cles:
            if c is not None:
                self.bruts.add(c)

    def _prefixes_communs(self):
        comptes = Counter()
        for v in self.bruts:
            m = RE_PREFIXE_CHIFFRES.match(v)
            if m:
                comptes[minuscules(m.group(1))] += 1
        return {p for p, c in comptes.items() if p == "" or c >= self.seuil}

    def canonique(self, valeur):
        m = RE_PREFIXE_CHIFFRES.match(valeur)
        if m and self.prefixes is not None and minuscules(m.group(1)) in self.prefixes:
            coeur = m.group(2).lstrip("0") or "0"
            return minuscules(m.group(1)) + "\x1f" + coeur, ("chiffres", m.group(1), len(m.group(2)))
        return minuscules(valeur), ("texte", valeur)

    def construire(self):
        if self.prefixes is None:
            self.prefixes = self._prefixes_communs()
        largeurs = {}
        chiffres = set()
        for v in sorted(self.bruts):
            base, forme = self.canonique(v)
            self.valeurs.add(base)
            if forme[0] == "chiffres":
                chiffres.add(base)
                largeurs[base] = max(largeurs.get(base, 0), forme[2])
        self.chiffres = getattr(self, "chiffres", set()) | chiffres
        groupes = {}
        for c in sorted(self.chiffres):
            if c in self.correspondance:
                continue
            prefixe, coeur = c.split("\x1f")
            w = largeurs.get(c, len(coeur))
            cle = (prefixe, "pad", w) if w > len(coeur) else (prefixe, "len", len(coeur))
            groupes.setdefault(cle, []).append(c)
        for cle in sorted(groupes):
            self._construire_chiffres(cle, groupes[cle])
        classes = {}
        for v in sorted(self.valeurs):
            if v in self.correspondance or v in self.chiffres:
                continue
            classes.setdefault(motif(v), []).append(v)
        for cle_motif, valeurs in classes.items():
            self._construire_classe(cle_motif, sorted(valeurs))

    def _construire_chiffres(self, cle, cles):
        prefixe, genre, w = cle
        valeurs = [c.split("\x1f")[1] for c in cles]
        if genre == "len" and w >= 19:
            reels = {c.split("\x1f")[1] for c in self.chiffres if c.split("\x1f")[0] == prefixe}
            temporaire = Remplaceur(self.rng, self.seuil)
            temporaire._construire_grands_entiers(valeurs, reels)
            for c, v in zip(cles, valeurs):
                self.correspondance[c] = temporaire.correspondance[v]
            return
        n = len(valeurs)
        bas = 0 if (genre == "pad" or w == 1) else 10 ** (w - 1)
        haut = 10 ** (w - 1) - 1 if genre == "pad" else 10 ** w - 1
        if w == 10 and genre == "len" and max(int(v) for v in valeurs) <= 2**31 - 1:
            haut = 2**31 - 1
        tous_interdits = getattr(self, "entiers_interdits", None)
        if tous_interdits is None:
            tous_interdits = {}
            self.entiers_interdits = tous_interdits
        interdits = tous_interdits.setdefault(prefixe, set())
        interdits |= {int(c.split("\x1f")[1]) for c in self.chiffres if c.split("\x1f")[0] == prefixe}
        taille = haut - bas + 1
        faux, reserve = [], []
        if taille <= 2_000_000 and n * 4 > taille:
            deja = getattr(self, "faux_utilises", {}).get(prefixe, set())
            for t in self.rng.permutation(taille):
                f = bas + int(t)
                if f in interdits:
                    if len(reserve) < n and f not in deja:
                        reserve.append(f)
                    continue
                faux.append(f)
                if len(faux) == n:
                    break
            faux += reserve[: n - len(faux)]
        else:
            vus = set()
            essais = 0
            while len(faux) < n and essais < 100 * n + 100_000:
                f = bas + int(self.rng.integers(0, taille))
                essais += 1
                if f in interdits or f in vus:
                    continue
                vus.add(f)
                faux.append(f)
        tous_utilises = getattr(self, "faux_utilises", None)
        if tous_utilises is None:
            tous_utilises = {}
            self.faux_utilises = tous_utilises
        utilises = tous_utilises.setdefault(prefixe, set())
        ordre = list(cles)
        self.rng.shuffle(ordre)
        for c, f in zip(ordre, faux):
            self.correspondance[c] = str(f)
            utilises.add(f)
            interdits.add(f)

    def _construire_grands_entiers(self, valeurs, reels=None):
        reels = self.valeurs if reels is None else reels
        longueur = len(valeurs[0])
        maximum_reel = max(int(v) for v in valeurs)
        plafond = 2**63 - 1 if maximum_reel <= 2**63 - 1 else 2**64 - 1
        bas = 10 ** (longueur - 1)
        haut = min(10**longueur - 1, plafond)
        faux = []
        vus = set()
        while len(faux) < len(valeurs):
            f = str(bas + int(self.rng.integers(0, 2**62)) * 4 % (haut - bas + 1) + int(self.rng.integers(0, 4)))
            if len(f) != longueur or int(f) > haut or f in vus or f in reels:
                continue
            vus.add(f)
            faux.append(f)
        ordre = list(valeurs)
        self.rng.shuffle(ordre)
        for v, f in zip(ordre, faux):
            self.correspondance[v] = f

    def _construire_classe(self, cle_motif, valeurs):
        n = len(valeurs)
        longueur = len(cle_motif)
        if longueur >= 19 and all(m == "D" for m in cle_motif) and not any(v.startswith("0") for v in valeurs):
            self._construire_grands_entiers(valeurs)
            return
        positions = []
        for p in range(longueur):
            m = cle_motif[p]
            if m.startswith("="):
                positions.append(("lit", m[1:]))
                continue
            caracteres = {v[p] for v in valeurs}
            if n >= self.seuil and len(caracteres) == 1:
                positions.append(("lit", next(iter(caracteres))))
                continue
            if m == "D":
                alphabet = CHIFFRES
                if p == 0 and longueur > 1 and "0" not in caracteres:
                    alphabet = CHIFFRES[1:]
            elif m == "U":
                alphabet = MAJUSCULES
            else:
                alphabet = MINUSCULES
            positions.append(("var", alphabet))
        libres = [a for t, a in positions if t == "var"]
        if not libres:
            for v in valeurs:
                self.correspondance[v] = v
            return
        taille = 1
        for a in libres:
            taille *= len(a)
            if taille > 10**15:
                break
        if taille < n:
            raise ValueError("espace de remplacement insuffisant")
        borne = None
        if longueur == 10 and all(m == "D" for m in cle_motif) and max(int(v) for v in valeurs) <= 2**31 - 1:
            borne = 2**31 - 1
        faux = []
        reserve = []
        if taille <= 2_000_000 and n * 4 > taille:
            for t in self.rng.permutation(taille):
                f = self._decoder(int(t), positions)
                if borne is not None and int(f) > borne:
                    continue
                if f in self.valeurs:
                    if len(reserve) < n:
                        reserve.append(f)
                    continue
                faux.append(f)
                if len(faux) == n:
                    break
            faux += reserve[: n - len(faux)]
        else:
            vus = set()
            essais = 0
            limite = 50 * n + 100_000
            while len(faux) < n:
                f = "".join(
                    a[int(self.rng.integers(len(a)))] if t == "var" else a for t, a in positions
                )
                essais += 1
                if borne is not None and int(f) > borne and essais < limite:
                    continue
                if f not in vus and f not in self.valeurs:
                    vus.add(f)
                    faux.append(f)
        ordre = list(valeurs)
        self.rng.shuffle(ordre)
        for i, v in enumerate(ordre):
            if faux[i] == v and n > 1:
                k = (i + 1) % n
                faux[i], faux[k] = faux[k], faux[i]
        for v, f in zip(ordre, faux):
            self.correspondance[v] = f

    @staticmethod
    def _decoder(index, positions):
        caracteres = []
        for t, a in reversed(positions):
            if t == "lit":
                caracteres.append(a)
            else:
                index, r = divmod(index, len(a))
                caracteres.append(a[r])
        return "".join(reversed(caracteres))

    def __call__(self, cle):
        if cle is None:
            return None
        if self.prefixes is None:
            self.construire()
        base, forme = self.canonique(cle)
        if base not in self.correspondance:
            self.bruts.add(cle)
            self.valeurs.add(base)
            self.construire()
        faux = self.correspondance[base]
        if forme[0] == "chiffres":
            return forme[1] + faux.zfill(forme[2])
        return recaser(faux, forme[1])


def sans_accents(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def appliquer_casse(texte, casse):
    if casse == "majuscules":
        return texte.upper()
    if casse == "minuscules":
        return texte.lower()
    return texte


class Faussaire:
    def __init__(self, rng):
        self.rng = rng
        self.caches = {}
        self.utilises = {}

    def _choix(self, liste):
        return liste[int(self.rng.integers(len(liste)))]

    def _memo(self, genre, cle, fabrique, composer):
        cache = self.caches.setdefault(genre, {})
        if cle in cache:
            return cache[cle]
        utilises = self.utilises.setdefault(genre, set())
        valeur = fabrique()
        essais = 0
        while valeur in utilises and essais < 20:
            valeur = fabrique()
            essais += 1
        niveau = 2
        while valeur in utilises:
            valeur = composer(niveau)
            essais += 1
            if essais % 50 == 0:
                niveau += 1
        utilises.add(valeur)
        cache[cle] = valeur
        return valeur

    def _noms_composes(self, liste, niveau):
        choisis = []
        while len(choisis) < niveau:
            v = self._choix(liste)
            if v not in choisis:
                choisis.append(v)
        return "-".join(choisis)

    def nom(self, cle, params):
        mots = max(1, int(params.get("mots", 1)))

        def fabrique(niveau=1):
            parties = [self._noms_composes(NOMS, niveau) if niveau > 1 else self._choix(NOMS)]
            if mots >= 2:
                parties.append(self._choix(PRENOMS))
            return appliquer_casse(" ".join(parties), params.get("casse"))
        return self._memo("nom", cle, fabrique, fabrique)

    def prenom(self, cle, params):
        mots = max(1, int(params.get("mots", 1)))

        def fabrique(niveau=1):
            if niveau > 1:
                return appliquer_casse(self._noms_composes(PRENOMS, niveau), params.get("casse"))
            parties = [self._choix(PRENOMS) for _ in range(min(mots, 2))]
            return appliquer_casse(" ".join(parties), params.get("casse"))
        return self._memo("prenom", cle, fabrique, fabrique)

    def email(self, cle, params):
        def fabrique(niveau=1):
            local = sans_accents(f"{self._choix(PRENOMS)}.{self._choix(NOMS)}").lower().replace(" ", "")
            return f"{local}{int(self.rng.integers(10, 10 ** (2 + niveau)))}@{self._choix(DOMAINES_EMAIL)}"
        return self._memo("email", cle, fabrique, fabrique)

    def adresse(self, cle, params):
        def fabrique(niveau=1):
            texte = f"{int(self.rng.integers(1, 120 * niveau))} {self._choix(TYPES_VOIES)} {self._choix(NOMS_VOIES)}"
            if params.get("avec_cp"):
                texte += f", {int(self.rng.integers(10, 95)):02d}{int(self.rng.integers(0, 999)):03d} {self._choix(VILLES)}"
            return texte
        return self._memo("adresse", cle, fabrique, fabrique)

    def generer(self, genre, cle, params):
        return getattr(self, genre)(cle, params)


def pseudonyme(cle_secrete, valeur):
    empreinte = hmac.new(cle_secrete, valeur.encode("utf-8"), hashlib.sha256).hexdigest()
    return "PS-" + empreinte[:16].upper()


def pseudonyme_numerique(cle_secrete, valeur):
    empreinte = hmac.new(cle_secrete, ("numerique:" + valeur).encode("utf-8"), hashlib.sha256).digest()
    return 10**14 + int.from_bytes(empreinte[:8], "big") % (9 * 10**14)


def decalage_jours(cle_secrete, valeur, maximum):
    if maximum <= 0:
        return 0
    empreinte = hmac.new(cle_secrete, ("decalage:" + valeur).encode("utf-8"), hashlib.sha256).digest()
    nombre = int.from_bytes(empreinte[:8], "big")
    return (nombre % (2 * maximum + 1)) - maximum
