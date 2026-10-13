"""Paramètres légaux de la paie au Maroc, par année.

Toutes les valeurs sont modifiables ici. Vérifiez-les à chaque loi de finances
et à chaque revalorisation du SMIG.

Sources principales :
- Code du travail (loi 65-99) : art. 184 (durée légale), 201 (heures sup.),
  231 et s. (congés payés), 350 (prime d'ancienneté) ;
- Code général des impôts (CGI) : art. 56 et s. (revenus salariaux),
  art. 59 (frais professionnels), art. 73 (barème), art. 74 (charges de famille) ;
- Décrets CNSS / AMO (taux et plafond).
"""

from decimal import Decimal as D

# Barème annuel de l'IR : (borne supérieure du revenu net imposable, taux, somme à déduire)
# LF 2025 (inchangé par la LF 2026).
BAREME_IR_2025 = [
    (D("40000"), D("0.00"), D("0")),
    (D("60000"), D("0.10"), D("4000")),
    (D("80000"), D("0.20"), D("10000")),
    (D("100000"), D("0.30"), D("18000")),
    (D("180000"), D("0.34"), D("22000")),
    (None, D("0.37"), D("27400")),
]

_COMMUN = {
    # --- Temps de travail ---
    "heures_mensuelles": D("191"),        # 44 h x 52 / 12 arrondi (art. 184)
    "jours_ouvrables_mois": D("26"),      # base de calcul du salaire journalier

    # --- CNSS (part salariale) ---
    "plafond_cnss": D("6000"),            # plafond mensuel des prestations sociales
    "taux_cnss_salarie": D("0.0448"),     # court terme + long terme + IPE (plafonné)
    "taux_amo_salarie": D("0.0226"),      # AMO (non plafonné)

    # --- CNSS (part patronale) ---
    "taux_cnss_patronal": D("0.0898"),    # prestations sociales (plafonné)
    "taux_af_patronal": D("0.0640"),      # allocations familiales (non plafonné)
    "taux_tfp_patronal": D("0.0160"),     # taxe de formation professionnelle
    "taux_amo_patronal": D("0.0411"),     # AMO 2,26 % + participation 1,85 %

    # --- Frais professionnels (art. 59 CGI) ---
    "seuil_frais_pro_annuel": D("78000"),
    "taux_frais_pro_bas": D("0.35"),      # revenu brut imposable annuel <= seuil
    "taux_frais_pro_haut": D("0.25"),     # au-delà du seuil
    "plafond_frais_pro_annuel": D("35000"),

    # --- IR ---
    "bareme_ir": BAREME_IR_2025,
    "max_personnes_charge": 6,
    "plafond_interets_logement": D("0.10"),  # 10 % du revenu brut imposable

    # --- Prime d'ancienneté (art. 350) : (années minimum, taux) ---
    "anciennete": [
        (25, D("0.25")),
        (20, D("0.20")),
        (12, D("0.15")),
        (5, D("0.10")),
        (2, D("0.05")),
    ],

    # --- Heures supplémentaires (art. 201) ---
    "majorations_hs": {
        "jour": D("0.25"),            # 6h-21h, jour ouvrable
        "nuit": D("0.50"),            # 21h-6h, jour ouvrable
        "repos_jour": D("0.50"),      # 6h-21h, jour de repos hebdomadaire
        "repos_nuit": D("1.00"),      # 21h-6h, jour de repos hebdomadaire
    },

    # --- Congés payés (art. 231 et s.) ---
    "conges_jours_par_mois": D("1.5"),
    "conges_jours_par_mois_moins_18": D("2"),
    "conges_bonus_par_5_ans": D("1.5"),
    "conges_plafond_annuel": D("30"),
}

PARAMETRES = {
    2025: {
        **_COMMUN,
        "smig_horaire": D("17.10"),
        "charge_famille_annuelle": D("500"),
    },
    2026: {
        **_COMMUN,
        "smig_horaire": D("17.92"),          # décret 2.25.983 du 29/12/2025
        "charge_famille_annuelle": D("600"),  # LF 2026, art. 74-I CGI
    },
}


def parametres(annee: int) -> dict:
    """Retourne les paramètres de l'année (ou de la plus récente connue)."""
    if annee in PARAMETRES:
        return PARAMETRES[annee]
    connues = sorted(PARAMETRES)
    if annee < connues[0]:
        raise ValueError(f"Aucun paramètre de paie pour l'année {annee}")
    return PARAMETRES[connues[-1]]
