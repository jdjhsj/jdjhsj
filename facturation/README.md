# Facturation Maroc

Logiciel de facturation **indépendant** : il génère une **série de factures par client** et
garde **l'historique complet des factures**. Écrit en Python, **sans aucune dépendance** :
il suffit d'avoir Python 3.10 ou plus récent. Les données restent sur votre ordinateur.

## Démarrage rapide

1. Installez Python depuis <https://www.python.org/downloads/>
   (sous Windows, cochez **« Add Python to PATH »** pendant l'installation).
2. Copiez le dossier `facturation` où vous voulez (il fonctionne seul).
3. Double-cliquez sur :
   - **`lancer_windows.bat`** sous Windows ;
   - **`lancer_mac.command`** sous Mac (la première fois : clic droit > Ouvrir).
4. Le navigateur s'ouvre sur <http://localhost:8080>. Laissez la fenêtre noire ouverte
   pendant l'utilisation ; fermez-la pour arrêter le logiciel.
5. **Premier lancement** : créez le compte administrateur (mot de passe de 8 caractères minimum).

En ligne de commande : `python3 -m facturation_maroc --ouvrir` (option `--port` pour changer de port).

## Mise en route

1. **Entreprise** : raison sociale, adresse, ICE, IF, RC, patente, CNSS, banque, RIB et mentions
   de bas de page. Elles figurent sur chaque facture.
2. **Clients** : chaque client reçoit un code (`C0001`…) et sa **propre série de factures**,
   identifiée par un préfixe (proposé automatiquement d'après le nom, ex. `ATLAS`, modifiable).
3. **Nouvelle facture** : choisissez le client, saisissez les lignes (désignation, quantité,
   prix unitaire HT, TVA 20 / 14 / 10 / 7 / 0 %). Les totaux s'affichent pendant la saisie ;
   le numéro est attribué à l'émission.

## Séries de factures par client

| Règle | Détail |
|---|---|
| Numérotation | `PRÉFIXE-ANNÉE-NNNN` (ex. `ATLAS-2026-0001`), continue et sans trou pour chaque client, repart à 0001 chaque année |
| Unicité | deux clients ne peuvent pas avoir le même préfixe ; le préfixe est figé dès la première facture ; deux factures émises en même temps ne reçoivent jamais le même numéro |
| Facturation en série | les **lignes récurrentes** d'un client (abonnement, maintenance, loyer…) permettent d'émettre en un clic une facture par client coché |
| Dupliquer | une facture existante pré-remplit une nouvelle facture avec les mêmes lignes |

## Historique des factures

| Règle | Détail |
|---|---|
| Conservation | une facture émise n'est jamais modifiée ni supprimée ; elle garde les coordonnées du client et de l'entreprise à sa date d'émission |
| Paiements | partiels ou totaux (virement, chèque, espèces, effet, carte, prélèvement), avec date et référence |
| Annulation | avec motif, uniquement si aucun paiement ; le numéro reste dans l'historique et n'est jamais réutilisé |
| Statuts | À payer, Partiellement payée, En retard (échéance dépassée), Payée, Annulée |
| Journal | chaque facture garde ses événements (émission, paiements, annulation) avec l'utilisateur, la date et l'heure |
| Recherche | filtres par client, année, statut et recherche libre ; totaux HT, TTC, encaissé, reste à encaisser |
| Export | CSV ouvrable dans Excel (toutes les factures ou la sélection filtrée) |
| Fiche client | chiffre d'affaires, encaissements, reste dû, historique et séries utilisées par année |

La facture affiche le total de TVA par taux, le montant TTC **en toutes lettres**
(« Arrêtée la présente facture à la somme de… ») et s'imprime ou s'enregistre en PDF
(bouton **Imprimer / PDF**).

## Utilisateurs et données

- L'administrateur ajoute ou supprime des utilisateurs (menu **Utilisateurs**). Chacun change
  son mot de passe en cliquant sur son nom. Mots de passe stockés hachés (PBKDF2-SHA256) ;
  la session expire après 8 heures d'inactivité.
- Les données sont dans le dossier `donnees/` : `entreprise.json`, `clients.json`,
  `factures.json`, `utilisateurs.json`. **Sauvegardez-le régulièrement** (il n'est pas envoyé sur GitHub).
  La variable d'environnement `FACTURATION_DONNEES` permet d'utiliser un autre dossier.
- Mot de passe administrateur perdu : arrêtez le logiciel, supprimez `donnees/utilisateurs.json`
  et recréez le compte au lancement suivant (les factures sont conservées).

## Tests

```bash
cd facturation
python3 -m unittest discover -s tests -v
```

## Limites

- Pas encore d'avoirs (une facture payée ne peut pas être annulée), de devis, de remises
  par ligne ni de droit de timbre sur les paiements en espèces.
- Une seule devise (dirham).

Faites valider les mentions de vos factures par votre expert-comptable avant une utilisation
en production.
