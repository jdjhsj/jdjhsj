"""Catalogue des congés et absences (Code du travail, loi 65-99 ; régime CNSS).

Pour chaque type :
- ``jours_payes`` : nombre de jours (ouvrables) maintenus par l'employeur par événement.
  ``None`` = tous les jours sont payés, ``0`` = aucun (retenue base / 26 par jour).
- ``duree_legale`` : durée prévue par la loi (contrôle et avertissement), ``None`` si libre.
- ``ij_cnss`` : indemnités journalières versées directement par la CNSS au salarié
  (non intégrées au net, affichées pour information) :
  ``(taux, jours_carence, plafonnee)``.

Le congé annuel payé est traité à part (indemnité calculée sur le salaire de
référence) : voir ``calcul.py`` et ``conges.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal as D


@dataclass(frozen=True)
class TypeConge:
    code: str
    libelle: str
    groupe: str
    jours_payes: D | None
    duree_legale: D | None = None
    article: str = ""
    ij_cnss: tuple | None = None
    note: str = ""

    @property
    def regime(self) -> str:
        if self.jours_payes is None:
            return "Payé par l'employeur"
        if self.jours_payes == 0:
            return "Non payé (retenue)"
        return f"{self.jours_payes:g} jour(s) payé(s), puis retenue"


GROUPES = {
    "annuel": "Congé annuel",
    "familial": "Congés pour événements familiaux (payés)",
    "maternite": "Maternité et naissance",
    "sante": "Maladie et accident du travail",
    "autre_paye": "Autres absences rémunérées",
    "non_paye": "Absences non rémunérées",
}

TYPES_CONGE: dict[str, TypeConge] = {t.code: t for t in [
    TypeConge("conge_annuel", "Congé annuel payé", "annuel", None, None, "art. 231 à 268",
              note="1,5 j/mois (2 j avant 18 ans), +1,5 j par 5 ans, max 30 j ; indemnité = référence / 26"),

    # Événements familiaux (art. 274) : payés pour les salariés mensualisés.
    TypeConge("mariage_salarie", "Mariage du salarié", "familial", D("4"), D("4"), "art. 274"),
    TypeConge("mariage_enfant", "Mariage d'un enfant du salarié", "familial", D("2"), D("2"), "art. 274",
              note="Ou d'un enfant issu d'un précédent mariage du conjoint"),
    TypeConge("deces_proche", "Décès du conjoint, d'un enfant, petit-enfant ou ascendant", "familial",
              D("3"), D("3"), "art. 274"),
    TypeConge("deces_famille", "Décès d'un frère, d'une sœur, d'un frère/sœur ou ascendant du conjoint",
              "familial", D("2"), D("2"), "art. 274"),
    TypeConge("circoncision", "Circoncision d'un enfant", "familial", D("2"), D("2"), "art. 274"),
    TypeConge("intervention_chirurgicale", "Intervention chirurgicale du conjoint ou d'un enfant à charge",
              "familial", D("2"), D("2"), "art. 274"),

    # Maternité / naissance
    TypeConge("naissance", "Congé de naissance (père)", "maternite", D("3"), D("3"), "art. 269",
              note="3 jours payés par l'employeur, à prendre dans le mois de la naissance"),
    TypeConge("maternite", "Congé de maternité", "maternite", D("0"), D("98"), "art. 152 à 165",
              ij_cnss=(D("1"), 0, True),
              note="14 semaines ; indemnité CNSS = 100 % du salaire moyen plafonné à 6 000 DH"),
    TypeConge("conge_education", "Congé non payé pour élever l'enfant", "maternite", D("0"), None, "art. 156",
              note="Suspension de 90 jours après la maternité, ou 1 an en accord avec l'employeur"),

    # Santé
    TypeConge("maladie", "Maladie (arrêt médical)", "sante", D("0"), None, "art. 271 à 273",
              ij_cnss=(D("2") / 3, 3, True),
              note="CNSS : 2/3 du salaire moyen plafonné, à partir du 4e jour (carence de 3 jours)"),
    TypeConge("accident_travail", "Accident du travail / maladie professionnelle", "sante", D("1"), None,
              "loi 18-12",
              note="Jour de l'accident payé par l'employeur ; indemnités versées par l'assureur AT"),

    # Autres absences rémunérées
    TypeConge("jour_ferie", "Jour férié chômé payé", "autre_paye", None, None, "art. 217"),
    TypeConge("delegation", "Heures de délégation (représentants du personnel)", "autre_paye", None, None,
              "art. 456", note="15 heures par mois et par délégué"),
    TypeConge("recherche_emploi", "Absence pour recherche d'emploi pendant le préavis", "autre_paye", None,
              None, "art. 48", note="2 h par jour, max 8 h/semaine et 30 h/mois"),
    TypeConge("formation", "Formation à l'initiative de l'employeur", "autre_paye", None),
    TypeConge("absence_autorisee_payee", "Absence autorisée payée", "autre_paye", None),

    # Non rémunérées
    TypeConge("sans_solde", "Congé sans solde", "non_paye", D("0")),
    TypeConge("absence_non_payee", "Absence autorisée non rémunérée", "non_paye", D("0")),
    TypeConge("absence_injustifiee", "Absence injustifiée", "non_paye", D("0")),
    TypeConge("pelerinage", "Congé pour pèlerinage", "non_paye", D("0"),
              note="Non prévu par le Code du travail : payé seulement si la convention le prévoit"),
    TypeConge("mise_a_pied", "Mise à pied disciplinaire", "non_paye", D("0"), D("8"), "art. 37",
              note="8 jours maximum"),
    TypeConge("greve", "Grève", "non_paye", D("0")),
]}


def type_conge(code: str) -> TypeConge:
    if code not in TYPES_CONGE:
        raise ValueError(f"Type de congé inconnu : {code}")
    return TYPES_CONGE[code]


def par_groupe() -> dict[str, list[TypeConge]]:
    groupes: dict[str, list[TypeConge]] = {g: [] for g in GROUPES}
    for t in TYPES_CONGE.values():
        groupes[t.groupe].append(t)
    return groupes
