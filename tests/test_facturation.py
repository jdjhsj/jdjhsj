import http.cookiejar
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from decimal import Decimal as D
from http.server import ThreadingHTTPServer

_dossier = tempfile.TemporaryDirectory()
os.environ.setdefault("PAIE_DONNEES", _dossier.name)

from paie_maroc import facturation as fa, stockage  # noqa: E402
from paie_maroc.web import Gestionnaire  # noqa: E402


def vider():
    for f in os.listdir(stockage.dossier()):
        os.remove(os.path.join(stockage.dossier(), f))


LIGNE = {"designation": "Maintenance", "quantite": "2", "prix_unitaire": "1500", "tva": "20"}


class TestMontants(unittest.TestCase):
    def test_totaux_par_taux(self):
        t = fa.calculer_totaux(fa.normaliser_lignes([
            LIGNE, {"designation": "Formation", "quantite": "1,5", "prix_unitaire": "1000,10", "tva": "10"},
            {"designation": "", "quantite": "", "prix_unitaire": ""}]))
        self.assertEqual(t["total_ht"], "4500.15")
        self.assertEqual(t["tva"], {"20": "600.00", "10": "150.02"})
        self.assertEqual(t["total_ttc"], "5250.17")

    def test_lignes_invalides(self):
        for ligne in ({"designation": "", "quantite": "1", "prix_unitaire": "10"},
                      {"designation": "X", "quantite": "abc", "prix_unitaire": "10"},
                      {"designation": "X", "quantite": "-1", "prix_unitaire": "10"},
                      {"designation": "X", "quantite": "1", "prix_unitaire": "nan"},
                      {"designation": "X", "quantite": "1", "prix_unitaire": "10", "tva": "19"}):
            with self.assertRaises(ValueError, msg=ligne):
                fa.normaliser_lignes([ligne])
        self.assertEqual(fa.normaliser_lignes([{"designation": "X", "quantite": "10", "prix_unitaire": "1"}])[0]
                         ["quantite"], "10")

    def test_en_lettres(self):
        cas = {
            "0": "zéro dirham", "1": "un dirham", "21": "vingt et un dirhams", "71": "soixante et onze dirhams",
            "80": "quatre-vingts dirhams", "81": "quatre-vingt-un dirhams", "200": "deux cents dirhams",
            "201": "deux cent un dirhams", "1000": "mille dirhams", "80000": "quatre-vingt mille dirhams",
            "200000": "deux cent mille dirhams", "1000000": "un million de dirhams",
            "12500.50": "douze mille cinq cents dirhams et cinquante centimes",
            "1234567.89": "un million deux cent trente-quatre mille cinq cent soixante-sept dirhams "
                          "et quatre-vingt-neuf centimes",
        }
        for valeur, attendu in cas.items():
            self.assertEqual(fa.montant_en_lettres(valeur), attendu)


class TestSeries(unittest.TestCase):
    def setUp(self):
        vider()
        fa.enregistrer_entreprise({"raison_sociale": "Ma Société", "ice": "001234567000089"})
        self.a = fa.enregistrer_client({"nom": "Société Atlas SARL", "delai_paiement": "30"})
        self.b = fa.enregistrer_client({"nom": "Atlas Services", "prefixe": "atl"})

    def test_prefixes(self):
        self.assertEqual((self.a["code"], self.a["prefixe"]), ("C0001", "ATLAS"))
        self.assertEqual(self.b["prefixe"], "ATL")
        self.assertEqual(fa.enregistrer_client({"nom": "Atlas"})["prefixe"], "ATLAS2")
        with self.assertRaises(ValueError):
            fa.enregistrer_client({"nom": "Autre", "prefixe": "ATL"})
        with self.assertRaises(ValueError):
            fa.enregistrer_client({"nom": "Autre", "prefixe": "A-B"})

    def test_numerotation_par_client_et_par_annee(self):
        n = lambda code, jour: fa.creer_facture(code, [LIGNE], jour)["numero"]
        self.assertEqual(n("C0001", "2026-01-10"), "ATLAS-2026-0001")
        self.assertEqual(n("C0001", "2026-02-10"), "ATLAS-2026-0002")
        self.assertEqual(n("C0002", "2026-02-10"), "ATL-2026-0001")
        self.assertEqual(n("C0001", "2027-01-02"), "ATLAS-2027-0001")
        self.assertEqual(fa.prochain_numero(fa.client("C0001"), 2026), "ATLAS-2026-0003")
        # Le préfixe est figé dès la première facture.
        with self.assertRaises(ValueError):
            fa.enregistrer_client({"nom": "Atlas", "prefixe": "NEW"}, "C0001")

    def test_numeros_uniques_en_parallele(self):
        fils = [threading.Thread(target=fa.creer_facture, args=("C0001", [LIGNE], "2026-03-01")) for _ in range(20)]
        for t in fils:
            t.start()
        for t in fils:
            t.join()
        numeros = sorted(f["numero"] for f in fa.factures())
        self.assertEqual(numeros, [f"ATLAS-2026-{i:04d}" for i in range(1, 21)])

    def test_historique_paiements_annulation(self):
        f = fa.creer_facture("C0001", [LIGNE], "2026-01-10", utilisateur="admin")
        self.assertEqual((f["echeance"], f["total_ttc"]), ("2026-02-09", "3600.00"))
        self.assertEqual(f["client"]["nom"], "Société Atlas SARL")
        self.assertEqual(f["emetteur"]["ice"], "001234567000089")
        self.assertEqual(fa.statut(f, date(2026, 1, 15)), "À payer")
        self.assertEqual(fa.statut(f, date(2026, 3, 1)), "En retard")
        with self.assertRaises(ValueError):
            fa.enregistrer_paiement(f["numero"], "5000")           # dépasse le reste
        fa.enregistrer_paiement(f["numero"], "1000", "2026-01-20", "Chèque", "CHQ 123", "admin")
        f = fa.facture(f["numero"])
        self.assertEqual(fa.reste_a_payer(f), D("2600.00"))
        self.assertEqual(fa.statut(f, date(2026, 1, 21)), "Partiellement payée")
        with self.assertRaises(ValueError):
            fa.annuler_facture(f["numero"], "erreur", "admin")      # déjà réglée en partie
        fa.enregistrer_paiement(f["numero"], "2600", utilisateur="admin")
        self.assertEqual(fa.statut(fa.facture(f["numero"])), "Payée")
        self.assertEqual(len(fa.facture(f["numero"])["historique"]), 3)

        # Une facture annulée garde son numéro, qui n'est jamais réattribué.
        g = fa.creer_facture("C0001", [LIGNE], "2026-01-11")
        fa.annuler_facture(g["numero"], "Doublon")
        self.assertEqual(fa.statut(fa.facture(g["numero"])), "Annulée")
        self.assertEqual(fa.creer_facture("C0001", [LIGNE], "2026-01-12")["numero"], "ATLAS-2026-0003")
        s = fa.synthese(fa.rechercher(client_code="C0001"))
        self.assertEqual((s["nombre"], s["ttc"], s["encaisse"], s["reste"]),
                         (3, D("7200.00"), D("3600.00"), D("3600.00")))
        self.assertIn("ATLAS-2026-0002;", fa.export_csv(fa.factures()))

    def test_client_facture_archive_et_non_supprime(self):
        fa.creer_facture("C0001", [LIGNE])
        fa.supprimer_client("C0001")
        self.assertFalse(fa.client("C0001")["actif"])
        with self.assertRaises(ValueError):
            fa.creer_facture("C0001", [LIGNE])
        fa.supprimer_client("C0002")
        self.assertIsNone(fa.client("C0002"))

    def test_facturation_en_serie(self):
        fa.enregistrer_client({"nom": "Atlas", "prefixe": "ATLAS", "lignes_recurrentes": [LIGNE]}, "C0001")
        creees, erreurs = fa.generer_series(["C0001", "C0002"], "2026-10-31", "Octobre 2026")
        self.assertEqual([f["numero"] for f in creees], ["ATLAS-2026-0001"])
        self.assertEqual(len(erreurs), 1)                            # C0002 : aucune ligne récurrente


class TestPagesFacturation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vider()
        cls.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
        cls.url = f"http://127.0.0.1:{cls.serveur.server_address[1]}"
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def requete(self, client, chemin, donnees=None):
        corps = urllib.parse.urlencode(donnees, doseq=True).encode() if donnees is not None else None
        try:
            r = client.open(urllib.request.Request(self.url + chemin, data=corps))
        except urllib.error.HTTPError as erreur:
            return erreur.code, erreur.geturl(), erreur.read().decode("utf-8-sig")
        return r.status, r.geturl(), r.read().decode("utf-8-sig")

    def test_parcours(self):
        c = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        _, url, _ = self.requete(c, "/factures")
        self.assertTrue(url.endswith("/installation"))
        self.requete(c, "/installation", {"identifiant": "admin", "mot_de_passe": "motdepasse1",
                                          "confirmation": "motdepasse1"})
        _, _, page = self.requete(c, "/entreprise", {"raison_sociale": "Ma <Société>", "ice": "0011"})
        self.assertIn("Informations enregistrées", page)
        self.assertIn("Ma &lt;Société&gt;", page)

        _, url, page = self.requete(c, "/clients/ajouter", {"nom": "Client Rabat", "prefixe": "RBT", "ice": "999"})
        self.assertIn("/clients/fiche?code=C0001", url)
        self.requete(c, "/clients/modifier", {
            "code": "C0001", "nom": "Client Rabat", "prefixe": "RBT", "actif": "1", "delai_paiement": "15",
            "rec_designation_1": "Abonnement", "rec_quantite_1": "1", "rec_prix_1": "1000", "rec_tva_1": "20"})
        self.assertEqual(fa.client("C0001")["lignes_recurrentes"][0]["designation"], "Abonnement")

        code, _, page = self.requete(c, "/factures/nouvelle", {"client": "C0001", "date": "2026-10-01",
                                                               "designation_1": "", "quantite_1": "", "prix_1": ""})
        self.assertEqual(code, 400)
        self.assertIn("au moins une ligne", page)
        _, url, page = self.requete(c, "/factures/nouvelle", {
            "client": "C0001", "date": "2026-10-01", "objet": "Octobre",
            "designation_1": "Audit", "quantite_1": "1", "prix_1": "12500,50", "tva_1": "20"})
        self.assertTrue(url.endswith("/factures/voir?numero=RBT-2026-0001"))
        self.assertIn("quinze mille", page)
        self.assertIn("15 000,60", page)

        _, _, page = self.requete(c, "/factures/paiement", {"numero": "RBT-2026-0001", "montant": "15000.60",
                                                            "date": "2026-10-05", "mode": "Virement"})
        self.assertIn("Paiement enregistré", page)
        _, _, page = self.requete(c, "/factures/generer", {"date": "2026-10-31", "objet": "Abonnement",
                                                           "clients": ["C0001"]})
        self.assertIn("RBT-2026-0002", page)

        _, _, page = self.requete(c, "/factures?client=C0001")
        self.assertIn("RBT-2026-0001", page)
        self.assertIn("Payée", page)
        _, _, csv_ = self.requete(c, "/factures.csv?statut=" + urllib.parse.quote("Payée"))
        self.assertIn("RBT-2026-0001", csv_)
        self.assertNotIn("RBT-2026-0002", csv_)
        _, _, page = self.requete(c, "/clients/fiche?code=C0001")
        self.assertIn("RBT-2026-0003", page)                         # prochain numéro de la série
        code, _, _ = self.requete(c, "/factures/voir?numero=INCONNU")
        self.assertEqual(code, 404)


if __name__ == "__main__":
    unittest.main()
