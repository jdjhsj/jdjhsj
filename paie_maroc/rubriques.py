"""Catalogue des rubriques de paie : primes et indemnités imposables, indemnités
exonérées (IR et/ou CNSS) et avantages en nature.

Chaque rubrique porte deux régimes indépendants :
- ``ir``   : traitement pour l'impôt sur le revenu (art. 56 et 57 CGI, note de service DGI 2017) ;
- ``cnss`` : traitement pour l'assiette CNSS / AMO (décret 2-25-266 et arrêté n° 1314-25,
  en vigueur depuis le 1er octobre 2025).

Types de régime :
- ``soumis``    : entièrement imposable / cotisable ;
- ``exonere``   : exonéré sans plafond (sur justificatifs) ;
- ``fixe``      : exonéré dans la limite de ``valeur`` DH par mois ;
- ``pct_base``  : exonéré dans la limite de ``valeur`` x salaire de base (et de ``maximum`` DH) ;
- ``smig_jour`` : exonéré dans la limite de ``valeur`` x SMIG horaire x jours travaillés ;
- ``par_unite`` : exonéré dans la limite de ``valeur`` DH x quantité (ex. km parcourus) ;
- ``annuel``    : exonéré dans la limite de ``valeur`` DH par an (cumul de l'année à fournir) ;
- ``global``    : exonéré dans la limite de ``valeur`` DH au total (indemnités de rupture).

Les plafonds sont modifiables ici. Les montants marqués « à vérifier » divergent
selon les sources : faites-les confirmer par votre conseiller.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal as D


@dataclass(frozen=True)
class Regime:
    type: str
    valeur: D | None = None
    maximum: D | None = None

    def description(self) -> str:
        v = self.valeur
        if self.type == "soumis":
            return "Soumis"
        if self.type == "exonere":
            return "Exonéré (justificatifs)"
        if self.type == "fixe":
            return f"Exonéré ≤ {v:,.0f} DH/mois".replace(",", " ")
        if self.type == "pct_base":
            texte = f"Exonéré ≤ {v * 100:.0f} % du salaire de base"
            if self.maximum:
                texte += f" (max {self.maximum:,.0f} DH)".replace(",", " ")
            return texte
        if self.type == "smig_jour":
            return f"Exonéré ≤ {v:g} × SMIG horaire / jour travaillé"
        if self.type == "par_unite":
            return f"Exonéré ≤ {v:g} DH par unité (km)"
        if self.type == "annuel":
            return f"Exonéré ≤ {v:,.0f} DH/an".replace(",", " ")
        if self.type == "global":
            return f"Exonéré ≤ {v:,.0f} DH au total".replace(",", " ")
        return self.type


SOUMIS = Regime("soumis")
EXONERE = Regime("exonere")


@dataclass(frozen=True)
class Rubrique:
    code: str
    libelle: str
    categorie: str            # "imposable", "exoneree", "avantage", "rupture"
    ir: Regime = SOUMIS
    cnss: Regime = SOUMIS
    note: str = ""
    unite: str = ""           # libellé de la quantité pour le régime "par_unite"

    @property
    def en_especes(self) -> bool:
        return self.categorie != "avantage"


def _r(code, libelle, categorie, ir=SOUMIS, cnss=None, note="", unite=""):
    return Rubrique(code, libelle, categorie, ir, ir if cnss is None else cnss, note, unite)


CATEGORIES = {
    "imposable": "Primes et indemnités imposables",
    "exoneree": "Indemnités non imposables (dans la limite des plafonds)",
    "rupture": "Indemnités de fin de contrat",
    "avantage": "Avantages en nature (imposables, non versés en espèces)",
}

RUBRIQUES: dict[str, Rubrique] = {r.code: r for r in [
    # ------------------------------------------------------------------
    # Primes et indemnités imposables (IR + CNSS)
    # ------------------------------------------------------------------
    _r("prime_rendement", "Prime de rendement", "imposable"),
    _r("prime_productivite", "Prime de productivité", "imposable"),
    _r("prime_objectif", "Prime d'objectif / bonus", "imposable"),
    _r("commission", "Commissions sur ventes", "imposable"),
    _r("prime_13e_mois", "Prime de 13e mois", "imposable"),
    _r("prime_fin_annee", "Prime de fin d'année / de bilan", "imposable"),
    _r("prime_assiduite", "Prime d'assiduité", "imposable"),
    _r("prime_responsabilite", "Indemnité de responsabilité / de fonction", "imposable"),
    _r("prime_technicite", "Prime de technicité / de qualification", "imposable"),
    _r("prime_astreinte", "Indemnité d'astreinte", "imposable"),
    _r("prime_penibilite", "Prime de pénibilité / de risque", "imposable"),
    _r("prime_sujetion", "Indemnité de sujétion", "imposable"),
    _r("prime_nuit", "Prime de travail de nuit (forfaitaire)", "imposable"),
    _r("prime_chantier", "Prime de chantier / d'éloignement", "imposable"),
    _r("indemnite_logement", "Indemnité de logement", "imposable"),
    _r("indemnite_residence", "Indemnité de résidence", "imposable"),
    _r("prime_langue", "Prime de langue", "imposable"),
    _r("prime_exceptionnelle", "Gratification exceptionnelle", "imposable"),
    _r("prime_interessement", "Prime d'intéressement / participation", "imposable"),
    _r("rappel_salaire", "Rappel de salaire", "imposable"),
    _r("indemnite_preavis", "Indemnité compensatrice de préavis", "imposable"),
    _r("indemnite_conges_compensatrice", "Indemnité compensatrice de congés payés", "imposable"),
    _r("indemnite_depart_retraite", "Indemnité de départ à la retraite", "imposable",
       note="Imposable sauf disposition conventionnelle contraire"),

    # ------------------------------------------------------------------
    # Indemnités non imposables (frais professionnels et sociaux)
    # ------------------------------------------------------------------
    _r("transport", "Indemnité de transport (périmètre urbain)", "exoneree", Regime("fixe", D("500")),
       note="Trajet domicile-travail"),
    _r("transport_hors_perimetre", "Indemnité de transport (hors périmètre urbain)", "exoneree",
       Regime("fixe", D("750"))),
    _r("kilometrique", "Indemnité kilométrique", "exoneree", Regime("par_unite", D("3")),
       note="Véhicule personnel, sur état (date, trajet, km, objet)", unite="km"),
    _r("tournee", "Prime de tournée", "exoneree", Regime("fixe", D("1500")),
       note="Agents commerciaux et itinérants"),
    _r("deplacement_forfaitaire", "Indemnité forfaitaire de déplacement régulier", "exoneree",
       Regime("pct_base", D("1"), D("5000")),
       note="Fonctions à déplacements continus — à vérifier"),
    _r("frais_mission", "Frais de mission / grand déplacement", "exoneree", EXONERE,
       note="Dépenses réelles, ordre de mission et justificatifs"),
    _r("frais_justifies", "Remboursement de frais professionnels justifiés", "exoneree", EXONERE),
    _r("representation", "Indemnité de représentation", "exoneree", Regime("pct_base", D("0.10")),
       note="Cadres dirigeants"),
    _r("panier", "Prime de panier", "exoneree", Regime("smig_jour", D("2")),
       note="Par jour de travail effectif"),
    _r("caisse", "Indemnité de caisse", "exoneree", Regime("fixe", D("190")),
       note="Salariés manipulant des fonds"),
    _r("lait", "Indemnité de lait", "exoneree", Regime("fixe", D("150")),
       note="Exposition à des produits toxiques"),
    _r("outillage", "Prime d'outillage", "exoneree", Regime("fixe", D("100")),
       note="Ouvriers propriétaires de leurs outils"),
    _r("salissure", "Prime de salissure", "exoneree", Regime("fixe", D("210")),
       note="Travaux salissants"),
    _r("gratifications_sociales", "Gratifications sociales (Aïd, mariage, naissance, scolarité, décès)",
       "exoneree", ir=Regime("annuel", D("2500")), cnss=Regime("annuel", D("5000")),
       note="Plafond IR à vérifier ; CNSS 5 000 DH/an (arrêté 1314-25)"),
    _r("indemnite_stage", "Indemnité de stage", "exoneree", Regime("fixe", D("6000")),
       note="Stagiaires (contrat formation-insertion)"),

    # ------------------------------------------------------------------
    # Indemnités de rupture (art. 57-7° CGI ; exclues de l'assiette CNSS)
    # ------------------------------------------------------------------
    _r("indemnite_licenciement", "Indemnité de licenciement", "rupture",
       ir=Regime("global", D("1000000")), cnss=EXONERE,
       note="Exonérée IR dans la limite de l'indemnité légale (art. 52 et s.)"),
    _r("indemnite_depart_volontaire", "Indemnité de départ volontaire", "rupture",
       ir=Regime("global", D("1000000")), cnss=EXONERE),
    _r("dommages_interets", "Dommages et intérêts (licenciement abusif)", "rupture",
       ir=Regime("global", D("1000000")), cnss=EXONERE,
       note="Accord devant l'inspection du travail ou décision judiciaire"),

    # ------------------------------------------------------------------
    # Avantages en nature (imposables et cotisables, non versés en espèces)
    # ------------------------------------------------------------------
    _r("avantage_logement", "Avantage logement", "avantage"),
    _r("avantage_voiture", "Avantage voiture de fonction (usage privé)", "avantage"),
    _r("avantage_nourriture", "Avantage nourriture", "avantage"),
    _r("avantage_telephone", "Avantage téléphone / internet (usage privé)", "avantage"),
    _r("avantage_autre", "Autres avantages en nature", "avantage"),
]}

# Ancien code conservé pour compatibilité des fichiers JSON.
ALIAS = {"avantages_nature": "avantage_autre"}


def rubrique(code: str) -> Rubrique:
    code = ALIAS.get(code, code)
    if code not in RUBRIQUES:
        raise ValueError(f"Rubrique inconnue : {code}")
    return RUBRIQUES[code]


def par_categorie() -> dict[str, list[Rubrique]]:
    groupes: dict[str, list[Rubrique]] = {c: [] for c in CATEGORIES}
    for r in RUBRIQUES.values():
        groupes[r.categorie].append(r)
    return groupes
