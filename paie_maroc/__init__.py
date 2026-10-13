"""Logiciel de paie conforme au droit du travail et à la fiscalité du Maroc."""

from .calcul import Bulletin, Prime, Salarie, VariablesPaie, calculer_bulletin
from .conges import DroitsConges, droits_conges

__all__ = ["Bulletin", "Prime", "Salarie", "VariablesPaie", "calculer_bulletin",
           "DroitsConges", "droits_conges"]
__version__ = "1.0.0"
