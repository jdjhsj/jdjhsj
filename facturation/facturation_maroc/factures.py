"""Facturation : entreprise, clients, séries de numérotation par client et historique des factures.

Chaque client possède sa propre série : ``<PRÉFIXE>-<ANNÉE>-<NNNN>`` (ex. ``ATLAS-2026-0001``).
La numérotation est continue et sans trou pour chaque client et chaque année ; un numéro
attribué n'est jamais réutilisé, même si la facture est annulée.

Les factures émises ne sont jamais modifiées ni supprimées : on y ajoute des paiements,
une annulation et des événements d'historique (date, utilisateur, action).
"""

from __future__ import annotations

import csv
import io
import re
import threading
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal as D

from . import stockage

FICHIER_ENTREPRISE = "entreprise.json"
FICHIER_CLIENTS = "clients.json"
FICHIER_FACTURES = "factures.json"

TAUX_TVA = (20, 14, 10, 7, 0)  # taux de TVA en vigueur au Maroc (%)
MODES_PAIEMENT = ("Virement", "Chèque", "Espèces", "Effet de commerce", "Carte bancaire", "Prélèvement")
CHAMPS_ENTREPRISE = ("raison_sociale", "forme_juridique", "capital", "adresse", "ville", "telephone", "email",
                     "ice", "if_fiscal", "rc", "patente", "cnss", "banque", "rib", "mentions")
CHAMPS_CLIENT = ("nom", "adresse", "ville", "ice", "if_fiscal", "rc", "email", "telephone")

# Une seule écriture à la fois : garantit des numéros uniques et sans trou.
_verrou = threading.RLock()

ZERO = D("0")
CENT = D("0.01")


def dec(valeur) -> D:
    """Convertit une saisie (« 1 250,50 ») en Decimal."""
    if valeur is None or valeur == "":
        return ZERO
    return D(str(valeur).replace(",", ".").replace(" ", "").replace("\u00a0", ""))


def arrondi(valeur) -> D:
    return D(valeur).quantize(CENT, rounding=ROUND_HALF_UP)


def dh(valeur) -> str:
    """Format français : 12 500,50."""
    if valeur is None:
        return ""
    return f"{valeur:,.2f}".replace(",", " ").replace(".", ",")


# ---------------------------------------------------------------------------
# Montants
# ---------------------------------------------------------------------------

def montant(valeur, libelle: str = "montant") -> D:
    try:
        resultat = dec(valeur)
    except ArithmeticError:
        raise ValueError(f"{libelle} invalide : « {valeur} »") from None
    if not resultat.is_finite():
        raise ValueError(f"{libelle} invalide : « {valeur} »")
    return resultat


def _texte(valeur: D) -> str:
    return str(arrondi(valeur))


def calculer_totaux(lignes: list[dict]) -> dict:
    """Total HT, TVA par taux et TTC (montants en chaînes, arrondis au centime)."""
    total_ht, bases = ZERO, {}
    for l in lignes:
        ht = arrondi(montant(l["quantite"]) * montant(l["prix_unitaire"]))
        total_ht += ht
        bases[l["tva"]] = bases.get(l["tva"], ZERO) + ht
    tva = {taux: arrondi(base * D(taux) / 100) for taux, base in sorted(bases.items(), key=lambda x: -int(x[0]))}
    total_tva = sum(tva.values(), ZERO)
    return {
        "total_ht": _texte(total_ht),
        "bases_tva": {t: _texte(b) for t, b in sorted(bases.items(), key=lambda x: -int(x[0]))},
        "tva": {t: _texte(m) for t, m in tva.items()},
        "total_tva": _texte(total_tva),
        "total_ttc": _texte(total_ht + total_tva),
    }


def _quantite(q: D) -> str:
    return str(q.quantize(D(1))) if q == q.to_integral_value() else str(q.normalize())


def normaliser_lignes(lignes: list[dict]) -> list[dict]:
    """Valide les lignes saisies ; ignore les lignes entièrement vides."""
    propres = []
    for i, l in enumerate(lignes, start=1):
        designation = (l.get("designation") or "").strip()
        quantite, prix = (l.get("quantite") or "").strip(), (l.get("prix_unitaire") or "").strip()
        if not (designation or quantite or prix):
            continue
        if not designation:
            raise ValueError(f"ligne {i} : désignation obligatoire")
        q = montant(quantite or "1", f"ligne {i} : quantité")
        p = montant(prix, f"ligne {i} : prix unitaire")
        if q <= 0:
            raise ValueError(f"ligne {i} : la quantité doit être positive")
        if p < 0:
            raise ValueError(f"ligne {i} : le prix unitaire ne peut pas être négatif")
        tva = str(l.get("tva") or "20").strip().removesuffix("%").strip()
        if not tva.isdigit() or int(tva) not in TAUX_TVA:
            raise ValueError(f"ligne {i} : taux de TVA non autorisé ({tva} %)")
        propres.append({"designation": designation, "quantite": _quantite(q),
                        "prix_unitaire": str(p), "tva": str(int(tva))})
    return propres


# ---------------------------------------------------------------------------
# Montant en lettres (« Arrêtée la présente facture à la somme de … »)
# ---------------------------------------------------------------------------

_UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze",
           "douze", "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _moins_de_cent(n: int) -> str:
    if n < 20:
        return _UNITES[n]
    d, u = divmod(n, 10)
    if d in (7, 9):  # soixante-dix, quatre-vingt-dix
        base = "soixante" if d == 7 else "quatre-vingt"
        if d == 7 and u == 1:
            return "soixante et onze"
        return f"{base}-{_UNITES[10 + u]}"
    if d == 8:
        return "quatre-vingts" if u == 0 else f"quatre-vingt-{_UNITES[u]}"
    if u == 0:
        return _DIZAINES[d]
    if u == 1:
        return f"{_DIZAINES[d]} et un"
    return f"{_DIZAINES[d]}-{_UNITES[u]}"


def _moins_de_mille(n: int, final: bool = True) -> str:
    c, r = divmod(n, 100)
    if c == 0:
        return _moins_de_cent(r)
    cent = "cent" if c == 1 else f"{_UNITES[c]} cent"
    if r == 0:
        return cent + ("s" if c > 1 and final else "")
    return f"{cent} {_moins_de_cent(r)}"


def nombre_en_lettres(n: int) -> str:
    if n == 0:
        return "zéro"
    morceaux = []
    for valeur, singulier, pluriel in ((10 ** 9, "milliard", "milliards"), (10 ** 6, "million", "millions")):
        q, n = divmod(n, valeur)
        if q:
            morceaux.append(f"{nombre_en_lettres(q)} {singulier if q == 1 else pluriel}")
    milliers, n = divmod(n, 1000)
    if milliers:
        morceaux.append("mille" if milliers == 1 else f"{_moins_de_mille(milliers, final=False)} mille"
                        .replace("quatre-vingts mille", "quatre-vingt mille"))
    if n:
        morceaux.append(_moins_de_mille(n))
    return " ".join(morceaux)


def montant_en_lettres(valeur) -> str:
    total = arrondi(montant(valeur))
    signe = "moins " if total < 0 else ""
    dirhams, centimes = divmod(int(abs(total) * 100), 100)
    de = "de " if dirhams and dirhams % 10 ** 6 == 0 else ""  # « un million de dirhams »
    texte = f"{signe}{nombre_en_lettres(dirhams)} {de}dirham{'s' if dirhams > 1 else ''}"
    if centimes:
        texte += f" et {nombre_en_lettres(centimes)} centime{'s' if centimes > 1 else ''}"
    return texte


# ---------------------------------------------------------------------------
# Entreprise (émetteur des factures)
# ---------------------------------------------------------------------------

def entreprise() -> dict:
    return stockage.lire(FICHIER_ENTREPRISE, {})


def enregistrer_entreprise(valeurs: dict) -> None:
    donnees = {k: (valeurs.get(k) or "").strip() for k in CHAMPS_ENTREPRISE}
    if not donnees["raison_sociale"]:
        raise ValueError("La raison sociale est obligatoire.")
    stockage.ecrire(FICHIER_ENTREPRISE, donnees)


# ---------------------------------------------------------------------------
# Clients et séries de numérotation
# ---------------------------------------------------------------------------

def clients() -> list[dict]:
    return stockage.lire(FICHIER_CLIENTS, [])


def client(code: str) -> dict | None:
    return next((c for c in clients() if c["code"] == code), None)


def _prefixe_propose(nom: str, existants: set[str]) -> str:
    sans_accents = nom.upper().translate(str.maketrans("ÀÂÄÇÉÈÊËÎÏÔÖÙÛÜ", "AAACEEEEIIOOUUU"))
    mots = [m for m in re.findall(r"[A-Z0-9]+", sans_accents)
            if m not in {"SARL", "SA", "SARLAU", "SNC", "STE", "SOCIETE", "ET", "DE", "DU", "LA", "LE", "LES", "AU"}]
    base = (mots[0] if mots else "CLI")[:6]
    prefixe, i = base, 2
    while prefixe in existants:
        prefixe, i = f"{base[:5]}{i}", i + 1
    return prefixe


def _valider_prefixe(prefixe: str) -> str:
    prefixe = prefixe.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,10}", prefixe):
        raise ValueError("Le préfixe de série doit contenir 1 à 10 lettres (sans accent) ou chiffres.")
    return prefixe


def enregistrer_client(valeurs: dict, code: str | None = None) -> dict:
    """Crée un client (``code`` absent) ou met à jour la fiche d'un client existant."""
    with _verrou:
        liste = clients()
        nom = (valeurs.get("nom") or "").strip()
        if not nom:
            raise ValueError("Le nom du client est obligatoire.")
        try:
            delai = int(valeurs.get("delai_paiement") or 30)
        except ValueError:
            raise ValueError("Délai de paiement invalide.") from None
        if not 0 <= delai <= 365:
            raise ValueError("Le délai de paiement doit être compris entre 0 et 365 jours.")
        autres = [c for c in liste if c["code"] != code]
        prefixes = {c["prefixe"] for c in autres}
        prefixe = valeurs.get("prefixe") or ""
        prefixe = _valider_prefixe(prefixe) if prefixe.strip() else _prefixe_propose(nom, prefixes)
        if prefixe in prefixes:
            raise ValueError(f"Le préfixe « {prefixe} » est déjà utilisé par un autre client.")

        if code is None:
            numeros = [int(c["code"][1:]) for c in liste if re.fullmatch(r"C\d+", c["code"])]
            fiche = {"code": f"C{max(numeros, default=0) + 1:04d}", "compteurs": {}, "actif": True,
                     "lignes_recurrentes": []}
            liste.append(fiche)
        else:
            fiche = next((c for c in liste if c["code"] == code), None)
            if fiche is None:
                raise ValueError("Client inconnu.")
            if fiche["compteurs"] and prefixe != fiche["prefixe"]:
                raise ValueError("Le préfixe de série ne peut plus être modifié : des factures ont déjà été émises.")
        fiche.update({k: (valeurs.get(k) or "").strip() for k in CHAMPS_CLIENT})
        fiche.update(nom=nom, prefixe=prefixe, delai_paiement=delai)
        if "lignes_recurrentes" in valeurs:
            fiche["lignes_recurrentes"] = normaliser_lignes(valeurs["lignes_recurrentes"])
        if "actif" in valeurs:
            fiche["actif"] = bool(valeurs["actif"])
        stockage.ecrire(FICHIER_CLIENTS, liste)
        return fiche


def supprimer_client(code: str) -> None:
    """Supprime un client sans facture ; un client facturé est seulement archivé."""
    with _verrou:
        liste = clients()
        fiche = next((c for c in liste if c["code"] == code), None)
        if fiche is None:
            raise ValueError("Client inconnu.")
        if fiche["compteurs"] or any(f["client_code"] == code for f in factures()):
            fiche["actif"] = False
        else:
            liste.remove(fiche)
        stockage.ecrire(FICHIER_CLIENTS, liste)


def format_numero(prefixe: str, annee: int, sequence: int) -> str:
    return f"{prefixe}-{annee}-{sequence:04d}"


def prochain_numero(fiche: dict, annee: int) -> str:
    return format_numero(fiche["prefixe"], annee, fiche["compteurs"].get(str(annee), 0) + 1)


# ---------------------------------------------------------------------------
# Factures
# ---------------------------------------------------------------------------

def factures() -> list[dict]:
    return stockage.lire(FICHIER_FACTURES, [])


def facture(numero: str) -> dict | None:
    return next((f for f in factures() if f["numero"] == numero), None)


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _date(valeur, libelle: str) -> date:
    try:
        return date.fromisoformat(str(valeur))
    except ValueError:
        raise ValueError(f"{libelle} invalide : « {valeur} »") from None


def creer_facture(code_client: str, lignes: list[dict], date_facture=None, echeance=None,
                  objet: str = "", notes: str = "", utilisateur: str = "") -> dict:
    """Émet une facture : attribue le prochain numéro de la série du client et l'archive."""
    lignes = normaliser_lignes(lignes)
    if not lignes:
        raise ValueError("La facture doit comporter au moins une ligne.")
    jour = _date(date_facture, "Date de facture") if date_facture else date.today()
    with _verrou:
        liste_clients = clients()
        fiche = next((c for c in liste_clients if c["code"] == code_client), None)
        if fiche is None:
            raise ValueError("Client inconnu.")
        if not fiche.get("actif", True):
            raise ValueError(f"Le client « {fiche['nom']} » est archivé.")
        echeance_ = _date(echeance, "Échéance") if echeance else jour + timedelta(days=fiche["delai_paiement"])
        if echeance_ < jour:
            raise ValueError("L'échéance ne peut pas précéder la date de facture.")
        historique = factures()
        annee = str(jour.year)
        sequence = fiche["compteurs"].get(annee, 0) + 1
        existants = {f["numero"] for f in historique}
        while format_numero(fiche["prefixe"], jour.year, sequence) in existants:  # sécurité
            sequence += 1
        numero = format_numero(fiche["prefixe"], jour.year, sequence)
        nouvelle = {
            "numero": numero,
            "client_code": fiche["code"],
            "client": {k: fiche.get(k, "") for k in CHAMPS_CLIENT},
            "emetteur": entreprise(),
            "date": jour.isoformat(),
            "echeance": echeance_.isoformat(),
            "objet": objet.strip(),
            "notes": notes.strip(),
            "lignes": lignes,
            **calculer_totaux(lignes),
            "paiements": [],
            "annulee": False,
            "motif_annulation": "",
            "historique": [{"date": _maintenant(), "utilisateur": utilisateur,
                            "action": f"Facture émise ({numero})"}],
        }
        fiche["compteurs"][annee] = sequence
        historique.append(nouvelle)
        stockage.ecrire(FICHIER_FACTURES, historique)
        stockage.ecrire(FICHIER_CLIENTS, liste_clients)
        return nouvelle


def _modifier(numero: str, action) -> dict:
    with _verrou:
        liste = factures()
        f = next((x for x in liste if x["numero"] == numero), None)
        if f is None:
            raise ValueError("Facture introuvable.")
        action(f)
        stockage.ecrire(FICHIER_FACTURES, liste)
        return f


def enregistrer_paiement(numero: str, valeur, jour=None, mode: str = "Virement", reference: str = "",
                         utilisateur: str = "") -> dict:
    somme = arrondi(montant(valeur, "Montant du paiement"))
    jour_ = _date(jour, "Date de paiement") if jour else date.today()
    if somme <= 0:
        raise ValueError("Le montant du paiement doit être positif.")
    if mode not in MODES_PAIEMENT:
        raise ValueError("Mode de paiement inconnu.")

    def action(f):
        if f["annulee"]:
            raise ValueError("Facture annulée : aucun paiement possible.")
        reste = reste_a_payer(f)
        if somme > reste:
            raise ValueError(f"Le paiement ({somme}) dépasse le reste à payer ({reste}).")
        f["paiements"].append({"date": jour_.isoformat(), "montant": str(somme), "mode": mode,
                               "reference": reference.strip()})
        f["historique"].append({"date": _maintenant(), "utilisateur": utilisateur,
                                "action": f"Paiement de {somme} DH ({mode}{', ' + reference.strip() if reference.strip() else ''})"
                                          f" du {jour_.strftime('%d/%m/%Y')}"})
    return _modifier(numero, action)


def annuler_facture(numero: str, motif: str, utilisateur: str = "") -> dict:
    motif = motif.strip()
    if not motif:
        raise ValueError("Indiquez le motif de l'annulation.")

    def action(f):
        if f["annulee"]:
            raise ValueError("Facture déjà annulée.")
        if f["paiements"]:
            raise ValueError("Facture déjà (partiellement) payée : établissez plutôt un avoir.")
        f["annulee"] = True
        f["motif_annulation"] = motif
        f["historique"].append({"date": _maintenant(), "utilisateur": utilisateur, "action": f"Annulée : {motif}"})
    return _modifier(numero, action)


def total_paye(f: dict) -> D:
    return sum((montant(p["montant"]) for p in f["paiements"]), ZERO)


def reste_a_payer(f: dict) -> D:
    return ZERO if f["annulee"] else montant(f["total_ttc"]) - total_paye(f)


def statut(f: dict, aujourdhui: date | None = None) -> str:
    if f["annulee"]:
        return "Annulée"
    reste = reste_a_payer(f)
    if reste <= 0:
        return "Payée"
    if (aujourdhui or date.today()).isoformat() > f["echeance"]:
        return "En retard"
    return "Partiellement payée" if f["paiements"] else "À payer"


STATUTS = ("À payer", "Partiellement payée", "En retard", "Payée", "Annulée")


def rechercher(client_code: str = "", annee: str = "", etat: str = "", texte: str = "") -> list[dict]:
    """Historique filtré, du plus récent au plus ancien."""
    texte = texte.strip().lower()
    resultat = []
    for f in factures():
        if client_code and f["client_code"] != client_code:
            continue
        if annee and not f["date"].startswith(str(annee)):
            continue
        if etat and statut(f) != etat:
            continue
        if texte and texte not in " ".join((f["numero"], f["client"]["nom"], f["objet"],
                                            *(l["designation"] for l in f["lignes"]))).lower():
            continue
        resultat.append(f)
    return sorted(resultat, key=lambda f: (f["date"], f["numero"]), reverse=True)


def synthese(liste: list[dict]) -> dict:
    valides = [f for f in liste if not f["annulee"]]
    return {
        "nombre": len(liste),
        "ht": sum((montant(f["total_ht"]) for f in valides), ZERO),
        "ttc": sum((montant(f["total_ttc"]) for f in valides), ZERO),
        "encaisse": sum((total_paye(f) for f in valides), ZERO),
        "reste": sum((reste_a_payer(f) for f in valides), ZERO),
        "en_retard": sum(1 for f in valides if statut(f) == "En retard"),
    }


def generer_series(codes: list[str], date_facture=None, objet: str = "", utilisateur: str = ""):
    """Facturation en masse : une facture par client à partir de ses lignes récurrentes.

    Retourne ``(factures_creees, erreurs)``.
    """
    creees, erreurs = [], []
    for code in codes:
        fiche = client(code)
        if fiche is None:
            erreurs.append(f"{code} : client inconnu")
            continue
        if not fiche.get("lignes_recurrentes"):
            erreurs.append(f"{fiche['nom']} : aucune ligne récurrente définie")
            continue
        try:
            creees.append(creer_facture(code, fiche["lignes_recurrentes"], date_facture, objet=objet,
                                        utilisateur=utilisateur))
        except ValueError as exc:
            erreurs.append(f"{fiche['nom']} : {exc}")
    return creees, erreurs


def export_csv(liste: list[dict]) -> str:
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";")
    w.writerow(["Numéro", "Date", "Échéance", "Code client", "Client", "ICE client", "Objet",
                "Total HT", "TVA", "Total TTC", "Payé", "Reste à payer", "Statut"])
    virgule = lambda v: str(v).replace(".", ",")
    for f in liste:
        w.writerow([f["numero"], f["date"], f["echeance"], f["client_code"], f["client"]["nom"],
                    f["client"].get("ice", ""), f["objet"], virgule(f["total_ht"]), virgule(f["total_tva"]),
                    virgule(f["total_ttc"]), virgule(arrondi(total_paye(f))), virgule(arrondi(reste_a_payer(f))),
                    statut(f)])
    return sortie.getvalue()
