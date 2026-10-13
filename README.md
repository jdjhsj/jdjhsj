# Paie Maroc

Logiciel de traitement de la paie conforme au **Code du travail marocain** (loi 65-99)
et au **Code général des impôts** (IR sur salaires). Écrit en Python, **sans aucune
dépendance** : il suffit d'avoir Python 3.10 ou plus récent.

## Ce que le logiciel calcule

| Élément | Règle appliquée |
|---|---|
| **Salaire de base** | taux horaire = base / 191 h, taux journalier = base / 26 j ; contrôle du SMIG (17,92 DH/h en 2026) |
| **Heures supplémentaires** (art. 201) | +25 % jour, +50 % nuit, +50 % jour de repos, +100 % nuit de repos |
| **Prime d'ancienneté** (art. 350) | 5 % (2 ans), 10 % (5 ans), 15 % (12 ans), 20 % (20 ans), 25 % (25 ans), sur base + heures sup. |
| **Primes imposables, avantages en nature** | ajoutés au brut imposable |
| **Indemnités exonérées** | transport 500 DH (750 hors périmètre), panier 2 × SMIG horaire / jour, représentation 10 % du base, caisse 190, lait 150, outillage 100, salissure 210, frais justifiés ; l'excédent est réintégré |
| **Absences** | retenue base / 26 par jour |
| **Congés payés** (art. 231 et s.) | 1,5 j/mois (2 j avant 18 ans), +1,5 j par 5 ans d'ancienneté, plafond 30 j ; indemnité = salaire de référence / 26 par jour ; solde et indemnité compensatrice |
| **CNSS** | salarié 4,48 % plafonné à 6 000 DH ; patronal 8,98 % plafonné + allocations familiales 6,40 % + TFP 1,60 % |
| **AMO** | salarié 2,26 %, patronal 4,11 % (non plafonnés) |
| **CIMR** (facultatif) | taux salarié et patronal au choix, déductible de l'IR |
| **Frais professionnels** (art. 59) | 35 % si brut imposable annuel ≤ 78 000 DH, sinon 25 % plafonné à 35 000 DH/an |
| **IR** (barème LF 2025, inchangé en 2026) | 0 % jusqu'à 40 000 DH/an, 10 %, 20 %, 30 %, 34 %, 37 % au-delà de 180 000 DH |
| **Charges de famille** | 600 DH/an par personne en 2026 (500 DH en 2025), 6 personnes maximum |
| **Intérêts de prêt logement** | déductibles dans la limite de 10 % du brut imposable |
| **Net à payer, coût employeur** | net = brut − cotisations − IR − avances − retenues (avantages en nature non versés) |

## Utilisation

### 1. Interface web (recommandé)

```bash
python3 -m paie_maroc web
```

Ouvrez ensuite <http://localhost:8000> dans votre navigateur :

- **Bulletin de paie** : saisissez le salarié et les éléments variables du mois, puis
  « Calculer le bulletin ». Le bulletin peut être imprimé ou enregistré en PDF.
- **Congés payés** : calcul des droits acquis, du solde et de l'indemnité compensatrice.

### 2. Paie de plusieurs salariés (fichier JSON)

```bash
python3 -m paie_maroc paie exemples/paie_octobre_2026.json --html bulletins.html --csv journal.csv
```

- affiche chaque bulletin dans le terminal ;
- `--html` : tous les bulletins dans une page imprimable ;
- `--csv` : journal de paie (ouvrable dans Excel) avec les totaux CNSS, AMO, IR, net…

Voir `exemples/paie_octobre_2026.json` pour le format. Champs principaux :

```json
{
  "annee": 2026, "mois": 10,
  "salaries": [{
    "nom": "Ahmed Benali", "salaire_base": 8000, "date_embauche": "2019-03-01",
    "personnes_a_charge": 3, "taux_cimr_salarie": 6, "taux_cimr_patronal": 7.8,
    "variables": {
      "heures_sup": {"jour": 10, "nuit": 0, "repos_jour": 4, "repos_nuit": 0},
      "primes": [{"libelle": "Prime de rendement", "montant": 500}],
      "indemnites": {"transport": 600, "panier": 400},
      "avantages_nature": 0,
      "jours_absence": 0, "jours_conges": 3, "salaire_reference_conges": 9000,
      "interets_logement": 0, "avance": 0, "autres_retenues": 0
    }
  }]
}
```

Les taux CIMR sont exprimés en pourcentage (6 = 6 %).

### 3. Depuis Python

```python
from datetime import date
from decimal import Decimal
from paie_maroc import Salarie, VariablesPaie, calculer_bulletin

s = Salarie(nom="Karim", salaire_base=Decimal("8000"), date_embauche=date(2020, 1, 1), personnes_a_charge=2)
b = calculer_bulletin(s, VariablesPaie(2026, 10, heures_sup={"jour": Decimal("8")}))
print(b.salaire_brut, b.cnss, b.amo, b.ir, b.net_a_payer)
```

## Mettre à jour les paramètres légaux

Tous les taux, plafonds et barèmes sont dans `paie_maroc/parametres.py`, par année.
À chaque loi de finances ou revalorisation du SMIG, ajoutez ou modifiez l'année
concernée. Une année inconnue utilise les paramètres de la plus récente.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Limites

- Paie mensuelle uniquement (pas de paie à l'heure ni à la quinzaine).
- L'IR est calculé mois par mois (pas de régularisation annuelle automatique).
- Les plafonds d'exonération CNSS sont supposés identiques à ceux de l'IR.
- Les indemnités de licenciement, le solde de tout compte complet et les
  déclarations CNSS (DAMANCOM) / IR (état 9421) ne sont pas encore générés.

Ce logiciel est un outil d'aide au calcul : faites valider les paramètres par votre
expert-comptable ou votre conseiller social avant une utilisation en production.
