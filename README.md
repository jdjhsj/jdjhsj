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
| **Absences et congés** | 22 types (voir ci-dessous) : jours maintenus, retenue base / 26, indemnités journalières CNSS estimées |
| **Congé annuel payé** (art. 231 et s.) | 1,5 j/mois (2 j avant 18 ans), +1,5 j par 5 ans d'ancienneté, plafond 30 j ; indemnité = salaire de référence / 26 par jour ; solde et indemnité compensatrice |
| **Indemnités et primes** | catalogue de 47 rubriques avec régime IR et CNSS distincts (voir ci-dessous) |
| **CNSS** | salarié 4,48 % plafonné à 6 000 DH ; patronal 8,98 % plafonné + allocations familiales 6,40 % + TFP 1,60 % |
| **AMO** | salarié 2,26 %, patronal 4,11 % (non plafonnés) |
| **CIMR** (facultatif) | taux salarié et patronal au choix, déductible de l'IR |
| **Frais professionnels** (art. 59) | 35 % si brut imposable annuel ≤ 78 000 DH, sinon 25 % plafonné à 35 000 DH/an |
| **IR** (barème LF 2025, inchangé en 2026) | 0 % jusqu'à 40 000 DH/an, 10 %, 20 %, 30 %, 34 %, 37 % au-delà de 180 000 DH |
| **Charges de famille** | 600 DH/an par personne en 2026 (500 DH en 2025), 6 personnes maximum |
| **Intérêts de prêt logement** | déductibles dans la limite de 10 % du brut imposable |
| **Net à payer, coût employeur** | net = brut − cotisations − IR − avances − retenues (avantages en nature non versés) |

## Référentiel des indemnités

Le catalogue complet est dans `paie_maroc/rubriques.py` et consultable dans
l'interface web (page **Référentiel**). Chaque rubrique a un régime IR (art. 57 CGI)
et un régime CNSS/AMO (arrêté n° 1314-25, en vigueur depuis le 1er octobre 2025).

**Imposables (IR + CNSS)** : rendement, productivité, objectif/bonus, commissions,
13e mois, fin d'année/bilan, assiduité, responsabilité/fonction, technicité,
astreinte, pénibilité/risque, sujétion, travail de nuit, chantier/éloignement,
logement, résidence, langue, gratification exceptionnelle, intéressement,
rappel de salaire, préavis, indemnité compensatrice de congés, départ à la retraite.

**Non imposables, dans la limite des plafonds** :

| Rubrique (code) | Plafond d'exonération |
|---|---|
| Transport urbain (`transport`) | 500 DH/mois |
| Transport hors périmètre (`transport_hors_perimetre`) | 750 DH/mois |
| Indemnité kilométrique (`kilometrique`) | 3 DH/km (quantité à saisir) |
| Prime de tournée (`tournee`) | 1 500 DH/mois |
| Déplacement régulier forfaitaire (`deplacement_forfaitaire`) | 100 % du salaire de base, max 5 000 DH/mois (à vérifier) |
| Frais de mission, frais justifiés (`frais_mission`, `frais_justifies`) | sans plafond, sur justificatifs |
| Représentation (`representation`) | 10 % du salaire de base |
| Panier (`panier`) | 2 × SMIG horaire par jour travaillé |
| Caisse, lait, outillage, salissure | 190, 150, 100, 210 DH/mois |
| Gratifications sociales (`gratifications_sociales`) | IR 2 500 DH/an (à vérifier), CNSS 5 000 DH/an |
| Indemnité de stage (`indemnite_stage`) | 6 000 DH/mois |
| Licenciement, départ volontaire, dommages-intérêts | IR : 1 000 000 DH au total ; exclus de la CNSS |

**Avantages en nature** (imposables, non versés en espèces) : logement, voiture,
nourriture, téléphone, autres.

Le dépassement d'un plafond est automatiquement réintégré dans la base imposable
ou cotisable, avec un avertissement sur le bulletin.

## Référentiel des congés et absences

Le catalogue est dans `paie_maroc/types_conges.py`.

| Type (code) | Durée | Rémunération |
|---|---|---|
| Congé annuel (`conge_annuel`) | 18 j/an + ancienneté | indemnité de congé |
| Mariage du salarié (`mariage_salarie`) | 4 j | payé (art. 274) |
| Mariage d'un enfant (`mariage_enfant`) | 2 j | payé |
| Décès conjoint, enfant, petit-enfant, ascendant (`deces_proche`) | 3 j | payé |
| Décès frère, sœur, ascendant du conjoint (`deces_famille`) | 2 j | payé |
| Circoncision (`circoncision`) | 2 j | payé |
| Intervention chirurgicale conjoint/enfant (`intervention_chirurgicale`) | 2 j | payé |
| Naissance (`naissance`) | 3 j | payé (art. 269) |
| Maternité (`maternite`) | 14 semaines | retenue ; CNSS 100 % du salaire plafonné à 6 000 DH |
| Congé pour élever l'enfant (`conge_education`) | 90 j à 1 an | non payé (art. 156) |
| Maladie (`maladie`) | — | retenue ; CNSS 2/3 du salaire plafonné après 3 jours de carence |
| Accident du travail (`accident_travail`) | — | 1er jour payé, puis assureur AT |
| Jour férié chômé, délégation, recherche d'emploi, formation, absence autorisée payée | — | payé |
| Sans solde, absence non rémunérée, absence injustifiée, pèlerinage, mise à pied (8 j max), grève | — | retenue |

Au-delà de la durée légale, les jours sont retenus et un avertissement s'affiche.
Les indemnités journalières CNSS sont versées directement par la CNSS : elles
apparaissent sur le bulletin à titre d'information, sans entrer dans le net.

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
      "primes": [{"libelle": "Prime libre", "montant": 500}],
      "indemnites": {
        "transport": 600, "prime_13e_mois": 8000, "avantage_voiture": 1200,
        "kilometrique": {"montant": 900, "quantite": 300},
        "gratifications_sociales": {"montant": 2000, "cumul_annuel": 1000}
      },
      "absences": {"conge_annuel": 3, "mariage_salarie": 4, "maladie": 5},
      "salaire_reference_conges": 9000,
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
- L'IR est calculé mois par mois (pas de régularisation annuelle automatique) :
  une prime annuelle (13e mois, bilan) versée en une fois est donc taxée au taux du mois.
- Les plafonds annuels (gratifications sociales) demandent de saisir le cumul déjà versé.
- La carence maladie de 3 jours est appliquée par saisie mensuelle (un arrêt sur deux mois
  doit être ajusté à la main).
- Les indemnités de licenciement, le solde de tout compte complet et les
  déclarations CNSS (DAMANCOM) / IR (état 9421) ne sont pas encore générés.

Ce logiciel est un outil d'aide au calcul : faites valider les paramètres par votre
expert-comptable ou votre conseiller social avant une utilisation en production.
