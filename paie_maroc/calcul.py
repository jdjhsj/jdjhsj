"""Moteur de calcul du bulletin de paie (droit marocain)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal as D

from .parametres import parametres

ZERO = D("0")
CENT = D("0.01")


def arrondi(montant: D) -> D:
    return D(montant).quantize(CENT, rounding=ROUND_HALF_UP)


def _fr(montant: D) -> str:
    return f"{arrondi(montant):,.2f}".replace(",", " ").replace(".", ",")


def dec(valeur) -> D:
    if valeur is None or valeur == "":
        return ZERO
    return D(str(valeur).replace(",", ".").replace(" ", ""))


# ---------------------------------------------------------------------------
# Données d'entrée
# ---------------------------------------------------------------------------

@dataclass
class Salarie:
    nom: str
    salaire_base: D                      # salaire mensuel de base (temps plein)
    date_embauche: date
    matricule: str = ""
    fonction: str = ""
    cin: str = ""
    numero_cnss: str = ""
    date_naissance: date | None = None
    personnes_a_charge: int = 0          # conjoint + enfants à charge (max 6 retenues)
    taux_cimr_salarie: D = ZERO          # ex. 0.06 pour 6 %
    taux_cimr_patronal: D = ZERO


@dataclass
class Prime:
    libelle: str
    montant: D


@dataclass
class VariablesPaie:
    """Éléments variables du mois."""
    annee: int
    mois: int
    heures_sup: dict = field(default_factory=dict)   # {"jour": h, "nuit": h, "repos_jour": h, "repos_nuit": h}
    primes: list = field(default_factory=list)       # primes imposables (Prime)
    avantages_nature: D = ZERO                       # imposables
    indemnites: dict = field(default_factory=dict)   # indemnités à régime d'exonération (voir parametres)
    jours_absence: D = ZERO                          # absences non rémunérées (jours ouvrables)
    jours_conges: D = ZERO                           # congés payés pris dans le mois (jours ouvrables)
    salaire_reference_conges: D | None = None        # salaire moyen mensuel des 12 derniers mois (facultatif)
    interets_logement: D = ZERO                      # intérêts de prêt logement principal (mensuels)
    avance: D = ZERO                                 # avance / acompte à retenir sur le net
    autres_retenues: D = ZERO                        # prêt, saisie, etc.


# ---------------------------------------------------------------------------
# Résultat
# ---------------------------------------------------------------------------

@dataclass
class Ligne:
    libelle: str
    base: D | None = None
    taux: D | None = None
    gain: D = ZERO
    retenue: D = ZERO
    patronal: D = ZERO
    pourcentage: bool = False   # le taux est un pourcentage (sinon un prix unitaire)


@dataclass
class Bulletin:
    salarie: Salarie
    variables: VariablesPaie
    lignes_gains: list
    lignes_cotisations: list
    salaire_brut: D
    brut_imposable: D
    total_exonere: D
    base_cnss: D
    cnss: D
    amo: D
    cimr: D
    frais_professionnels: D
    interets_logement: D
    net_imposable: D
    ir_brut: D
    deduction_famille: D
    ir: D
    total_retenues: D
    net_a_payer: D
    charges_patronales: D
    cout_employeur: D
    anciennete_annees: int
    taux_anciennete: D
    taux_horaire: D
    avertissements: list

    @property
    def periode(self) -> str:
        return f"{self.variables.mois:02d}/{self.variables.annee}"


# ---------------------------------------------------------------------------
# Fonctions élémentaires
# ---------------------------------------------------------------------------

def annees_completes(debut: date, fin: date) -> int:
    ans = fin.year - debut.year
    if (fin.month, fin.day) < (debut.month, debut.day):
        ans -= 1
    return max(ans, 0)


def fin_de_mois(annee: int, mois: int) -> date:
    if mois == 12:
        return date(annee, 12, 31)
    return date.fromordinal(date(annee, mois + 1, 1).toordinal() - 1)


def taux_anciennete(annees: int, p: dict) -> D:
    for minimum, taux in p["anciennete"]:
        if annees >= minimum:
            return taux
    return ZERO


def frais_professionnels(brut_imposable: D, p: dict) -> D:
    """Art. 59 CGI : 35 % si revenu brut imposable annuel <= 78 000 DH,
    sinon 25 % plafonné à 35 000 DH par an."""
    annuel = brut_imposable * 12
    if annuel <= p["seuil_frais_pro_annuel"]:
        return arrondi(brut_imposable * p["taux_frais_pro_bas"])
    return arrondi(min(annuel * p["taux_frais_pro_haut"], p["plafond_frais_pro_annuel"]) / 12)


def ir_mensuel(net_imposable_mensuel: D, p: dict) -> D:
    """Barème annuel appliqué au net imposable annualisé, ramené au mois."""
    annuel = net_imposable_mensuel * 12
    for borne, taux, deduction in p["bareme_ir"]:
        if borne is None or annuel <= borne:
            return arrondi(max(annuel * taux - deduction, ZERO) / 12)
    raise AssertionError("barème incomplet")


def deduction_charges_famille(personnes: int, p: dict) -> D:
    n = min(max(int(personnes), 0), p["max_personnes_charge"])
    return arrondi(p["charge_famille_annuelle"] * n / 12)


# ---------------------------------------------------------------------------
# Calcul du bulletin
# ---------------------------------------------------------------------------

def calculer_bulletin(s: Salarie, v: VariablesPaie) -> Bulletin:
    p = parametres(v.annee)
    avert: list[str] = []
    gains: list[Ligne] = []

    base = dec(s.salaire_base)
    jours_mois = p["jours_ouvrables_mois"]
    heures_mois = p["heures_mensuelles"]
    taux_h = base / heures_mois
    taux_j = base / jours_mois

    smig_mensuel = arrondi(p["smig_horaire"] * heures_mois)
    if base < smig_mensuel:
        avert.append(
            f"Salaire de base ({_fr(base)} DH) inférieur au SMIG mensuel "
            f"({_fr(smig_mensuel)} DH = {_fr(p['smig_horaire'])} DH x {heures_mois} h)."
        )

    jours_abs = dec(v.jours_absence)
    jours_cp = dec(v.jours_conges)
    if jours_abs + jours_cp > jours_mois:
        avert.append("Absences + congés supérieurs au nombre de jours ouvrables du mois.")

    # 1. Salaire de base, absences, congés payés
    gains.append(Ligne("Salaire de base", heures_mois, arrondi(taux_h), arrondi(base)))

    retenue_abs = arrondi(taux_j * jours_abs)
    if jours_abs:
        gains.append(Ligne("Absences non rémunérées", jours_abs, arrondi(taux_j), -retenue_abs))

    retenue_cp = indemnite_cp = ZERO
    ref_fournie = v.salaire_reference_conges not in (None, "")
    if jours_cp:
        ref = dec(v.salaire_reference_conges) if ref_fournie else base
        retenue_cp = arrondi(taux_j * jours_cp)
        indemnite_cp = arrondi(ref / jours_mois * jours_cp)
        gains.append(Ligne("Retenue jours de congé", jours_cp, arrondi(taux_j), -retenue_cp))
        gains.append(Ligne("Indemnité de congés payés", jours_cp, arrondi(ref / jours_mois), indemnite_cp))

    # 2. Heures supplémentaires
    total_hs = ZERO
    libelles_hs = {
        "jour": "Heures sup. jour (+25 %)",
        "nuit": "Heures sup. nuit (+50 %)",
        "repos_jour": "Heures sup. repos jour (+50 %)",
        "repos_nuit": "Heures sup. repos nuit (+100 %)",
    }
    for cle, majoration in p["majorations_hs"].items():
        heures = dec(v.heures_sup.get(cle))
        if heures:
            taux = taux_h * (1 + majoration)
            montant = arrondi(taux * heures)
            total_hs += montant
            gains.append(Ligne(libelles_hs[cle], heures, arrondi(taux), montant))

    # 3. Prime d'ancienneté (art. 350) : sur salaire de base effectif + HS
    #    (l'indemnité de congé y est incluse si elle est calculée sur le salaire de base,
    #    sinon le salaire de référence est supposé contenir déjà l'ancienneté).
    anciennete = annees_completes(s.date_embauche, fin_de_mois(v.annee, v.mois))
    t_anc = taux_anciennete(anciennete, p)
    base_anc = base - retenue_abs - retenue_cp + total_hs + (ZERO if ref_fournie else indemnite_cp)
    prime_anc = arrondi(base_anc * t_anc)
    if prime_anc:
        gains.append(Ligne(f"Prime d'ancienneté ({anciennete} an{'s' if anciennete > 1 else ''})", arrondi(base_anc), t_anc, prime_anc, pourcentage=True))

    # 4. Primes imposables et avantages en nature
    total_primes = ZERO
    for prime in v.primes:
        m = arrondi(dec(prime.montant))
        if m:
            total_primes += m
            gains.append(Ligne(prime.libelle, gain=m))
    avantages = arrondi(dec(v.avantages_nature))
    if avantages:
        gains.append(Ligne("Avantages en nature", gain=avantages))

    # 5. Indemnités à régime d'exonération
    jours_travailles = max(jours_mois - jours_abs - jours_cp, ZERO)
    plafonds = dict(p["plafonds_exoneres"])
    plafonds["panier"] = arrondi(p["panier_multiple_smig"] * p["smig_horaire"] * jours_travailles)
    plafonds["representation"] = arrondi(base * p["taux_representation"])
    libelles_ind = {
        "transport": "Indemnité de transport",
        "transport_hors_perimetre": "Indemnité de transport (hors périmètre)",
        "panier": "Prime de panier",
        "representation": "Indemnité de représentation",
        "caisse": "Indemnité de caisse",
        "lait": "Indemnité de lait",
        "outillage": "Prime d'outillage",
        "salissure": "Prime de salissure",
        "frais_justifies": "Remboursement de frais",
    }
    total_ind = total_exonere = ZERO
    for cle, montant in v.indemnites.items():
        if cle not in plafonds:
            raise ValueError(f"Indemnité inconnue : {cle}")
        m = arrondi(dec(montant))
        if not m:
            continue
        plafond = plafonds[cle]
        exo = m if plafond is None else min(m, plafond)
        total_ind += m
        total_exonere += exo
        gains.append(Ligne(libelles_ind[cle], gain=m))
        if exo < m:
            avert.append(f"{libelles_ind[cle]} : {_fr(m - exo)} DH au-delà du plafond ({_fr(plafond)} DH), réintégrés dans l'imposable.")

    salaire_brut = (base - retenue_abs - retenue_cp + indemnite_cp + total_hs + prime_anc
                    + total_primes + avantages + total_ind)
    brut_imposable = salaire_brut - total_exonere

    # 6. Cotisations salariales
    cot: list[Ligne] = []
    base_cnss = brut_imposable
    base_plaf = min(base_cnss, p["plafond_cnss"])
    cnss = arrondi(base_plaf * p["taux_cnss_salarie"])
    amo = arrondi(base_cnss * p["taux_amo_salarie"])
    cimr = arrondi(brut_imposable * dec(s.taux_cimr_salarie))

    cnss_pat = arrondi(base_plaf * p["taux_cnss_patronal"])
    af_pat = arrondi(base_cnss * p["taux_af_patronal"])
    tfp_pat = arrondi(base_cnss * p["taux_tfp_patronal"])
    amo_pat = arrondi(base_cnss * p["taux_amo_patronal"])
    cimr_pat = arrondi(brut_imposable * dec(s.taux_cimr_patronal))

    cot.append(Ligne("CNSS prestations sociales", arrondi(base_plaf), p["taux_cnss_salarie"], retenue=cnss, patronal=cnss_pat))
    cot.append(Ligne("AMO", arrondi(base_cnss), p["taux_amo_salarie"], retenue=amo, patronal=amo_pat))
    cot.append(Ligne("Allocations familiales", arrondi(base_cnss), p["taux_af_patronal"], patronal=af_pat))
    cot.append(Ligne("Taxe de formation professionnelle", arrondi(base_cnss), p["taux_tfp_patronal"], patronal=tfp_pat))
    if cimr or cimr_pat:
        cot.append(Ligne("CIMR (retraite complémentaire)", arrondi(brut_imposable), dec(s.taux_cimr_salarie), retenue=cimr, patronal=cimr_pat))

    # 7. Impôt sur le revenu
    avantages_hors_fp = avantages
    fp = frais_professionnels(brut_imposable - avantages_hors_fp, p)
    interets = min(arrondi(dec(v.interets_logement)), arrondi(brut_imposable * p["plafond_interets_logement"]))
    net_imposable = max(brut_imposable - fp - cnss - amo - cimr - interets, ZERO)
    ir_brut = ir_mensuel(net_imposable, p)
    ded_famille = deduction_charges_famille(s.personnes_a_charge, p)
    if s.personnes_a_charge > p["max_personnes_charge"]:
        avert.append(f"Charges de famille limitées à {p['max_personnes_charge']} personnes.")
    ir = max(ir_brut - ded_famille, ZERO)
    cot.append(Ligne("Impôt sur le revenu (IR)", arrondi(net_imposable), None, retenue=ir))

    avance = arrondi(dec(v.avance))
    autres = arrondi(dec(v.autres_retenues))
    if avance:
        cot.append(Ligne("Avance sur salaire", retenue=avance))
    if autres:
        cot.append(Ligne("Autres retenues", retenue=autres))

    total_retenues = cnss + amo + cimr + ir + avance + autres
    # Les avantages en nature ne sont pas versés en espèces.
    net = salaire_brut - total_retenues - avantages
    if net < 0:
        avert.append("Net à payer négatif : vérifiez les retenues.")

    charges_pat = cnss_pat + af_pat + tfp_pat + amo_pat + cimr_pat

    return Bulletin(
        salarie=s, variables=v,
        lignes_gains=gains, lignes_cotisations=cot,
        salaire_brut=arrondi(salaire_brut), brut_imposable=arrondi(brut_imposable),
        total_exonere=arrondi(total_exonere), base_cnss=arrondi(base_cnss),
        cnss=cnss, amo=amo, cimr=cimr, frais_professionnels=fp,
        interets_logement=interets, net_imposable=arrondi(net_imposable),
        ir_brut=ir_brut, deduction_famille=ded_famille, ir=ir,
        total_retenues=arrondi(total_retenues), net_a_payer=arrondi(net),
        charges_patronales=arrondi(charges_pat),
        cout_employeur=arrondi(salaire_brut + charges_pat),
        anciennete_annees=anciennete, taux_anciennete=t_anc,
        taux_horaire=arrondi(taux_h), avertissements=avert,
    )
