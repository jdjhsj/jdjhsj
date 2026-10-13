"""Registre des salariés importés (fichier donnees/salaries.json)."""

from __future__ import annotations

from . import stockage

FICHIER = "salaries.json"


def charger() -> list[dict]:
    return stockage.lire(FICHIER, [])


def enregistrer(nouveaux: list[dict], remplacer: bool = False) -> tuple[int, int]:
    """Ajoute ou met à jour les salariés (clé : matricule).

    Retourne ``(ajoutes, mis_a_jour)``.
    """
    existants = [] if remplacer else charger()
    index = {s["matricule"]: i for i, s in enumerate(existants)}
    ajoutes = mis_a_jour = 0
    for salarie in nouveaux:
        if salarie["matricule"] in index:
            existants[index[salarie["matricule"]]] = salarie
            mis_a_jour += 1
        else:
            index[salarie["matricule"]] = len(existants)
            existants.append(salarie)
            ajoutes += 1
    stockage.ecrire(FICHIER, existants)
    return ajoutes, mis_a_jour


def supprimer(matricule: str) -> None:
    stockage.ecrire(FICHIER, [s for s in charger() if s["matricule"] != matricule])


def vider() -> None:
    stockage.ecrire(FICHIER, [])
