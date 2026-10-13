"""Congés payés annuels (Code du travail, art. 231 à 268)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal as D

from .calcul import ZERO, annees_completes, arrondi, dec
from .parametres import parametres


@dataclass
class DroitsConges:
    mois_travailles: D
    jours_par_mois: D
    jours_base: D
    jours_anciennete: D
    jours_acquis: D          # après plafond de 30 jours ouvrables
    jours_pris: D
    solde: D
    salaire_journalier: D
    valeur_solde: D          # indemnité compensatrice si le contrat prend fin


def droits_conges(
    date_embauche: date,
    date_calcul: date,
    mois_travailles,
    salaire_reference,
    jours_pris=0,
    date_naissance: date | None = None,
) -> DroitsConges:
    """Calcule les droits à congé pour la période de référence.

    - 1,5 jour ouvrable par mois de service effectif (2 jours si moins de 18 ans) ;
    - +1,5 jour par période complète de 5 ans d'ancienneté ;
    - plafond de 30 jours ouvrables par an ;
    - salaire journalier = salaire mensuel de référence / 26.
    """
    p = parametres(date_calcul.year)
    mois = dec(mois_travailles)
    mineur = date_naissance is not None and annees_completes(date_naissance, date_calcul) < 18
    par_mois = p["conges_jours_par_mois_moins_18"] if mineur else p["conges_jours_par_mois"]

    jours_base = par_mois * mois
    periodes_5_ans = annees_completes(date_embauche, date_calcul) // 5
    jours_anc = p["conges_bonus_par_5_ans"] * periodes_5_ans if mois else ZERO
    acquis = min(jours_base + jours_anc, p["conges_plafond_annuel"])

    pris = dec(jours_pris)
    solde = acquis - pris
    journalier = arrondi(dec(salaire_reference) / p["jours_ouvrables_mois"])
    return DroitsConges(
        mois_travailles=mois, jours_par_mois=par_mois,
        jours_base=jours_base, jours_anciennete=jours_anc,
        jours_acquis=acquis, jours_pris=pris, solde=solde,
        salaire_journalier=journalier,
        valeur_solde=arrondi(max(solde, ZERO) * journalier),
    )
