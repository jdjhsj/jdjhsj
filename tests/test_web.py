import http.cookiejar
import io
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from decimal import Decimal as D
from http.server import ThreadingHTTPServer

_dossier = tempfile.TemporaryDirectory()
os.environ["PAIE_DONNEES"] = _dossier.name

from paie_maroc import auth, registre  # noqa: E402
from paie_maroc.importation import analyser, convertir_date, lire_csv, lire_fichier, lire_xlsx, modele_csv  # noqa: E402
from paie_maroc.web import Gestionnaire, calculer_registre  # noqa: E402


def xlsx(lignes):
    """Construit un classeur .xlsx minimal (chaînes partagées + nombres)."""
    partages, index = [], {}
    feuille = []
    for r, ligne in enumerate(lignes, start=1):
        cellules = []
        for c, valeur in enumerate(ligne):
            ref = f"{chr(65 + c)}{r}"
            if isinstance(valeur, (int, float)):
                cellules.append(f'<c r="{ref}"><v>{valeur}</v></c>')
            else:
                if valeur not in index:
                    index[valeur] = len(partages)
                    partages.append(valeur)
                cellules.append(f'<c r="{ref}" t="s"><v>{index[valeur]}</v></c>')
        feuille.append(f'<row r="{r}">{"".join(cellules)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns} {rel}><sheets><sheet name="Salariés" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml",
                   f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in partages) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData>{"".join(feuille)}</sheetData></worksheet>')
    return tampon.getvalue()


class TestImportation(unittest.TestCase):
    def test_modele_reimportable(self):
        salaries, erreurs, ignorees = analyser(lire_csv(modele_csv().encode("utf-8")))
        self.assertEqual(len(salaries), 3)
        self.assertEqual(erreurs, [])
        self.assertEqual(ignorees, [])
        self.assertEqual(salaries[0]["date_embauche"], "2019-03-01")
        self.assertEqual(salaries[1]["variables"]["indemnites"]["kilometrique"],
                         {"montant": "1200", "quantite": "350"})

    def test_entetes_tolerants_et_virgule(self):
        texte = "Nom et prénom,Salaire de base,Date d'embauche,N° CNSS,Transport,Maladie\n" \
                "Karim,\"8000,50\",01/01/2020,123,600,2\n"
        salaries, erreurs, _ = analyser(lire_csv(texte.encode("cp1252")))
        self.assertEqual(erreurs, [])
        s = salaries[0]
        self.assertEqual((s["nom"], s["numero_cnss"], s["salaire_base"]), ("Karim", "123", "8000,50"))
        self.assertEqual(s["variables"]["absences"], {"maladie": "2"})

    def test_lignes_invalides_signalees(self):
        texte = "nom;salaire_base;date_embauche;bidule\nA;8000;2020-01-01;x\nB;abc;2020-01-01;\nC;8000;32/13/2020;\n"
        salaries, erreurs, ignorees = analyser(lire_csv(texte.encode()))
        self.assertEqual(len(salaries), 1)
        self.assertEqual(len(erreurs), 2)
        self.assertEqual(ignorees, ["bidule"])

    def test_colonnes_obligatoires(self):
        with self.assertRaises(ValueError):
            analyser(lire_csv(b"nom;salaire\nA;1\n"))

    def test_xlsx(self):
        contenu = xlsx([["Matricule", "Nom", "Salaire de base", "Date d'embauche", "prime_13e_mois"],
                        ["010", "Nadia", 9000, 43831, 9000]])          # 43831 = 01/01/2020
        salaries, erreurs, _ = analyser(lire_xlsx(contenu))
        self.assertEqual(erreurs, [])
        self.assertEqual(salaries[0]["date_embauche"], "2020-01-01")
        self.assertEqual(salaries[0]["variables"]["indemnites"]["prime_13e_mois"], {"montant": "9000"})

    def test_formats_refuses(self):
        with self.assertRaises(ValueError):
            lire_fichier("paie.xls", b"...")
        with self.assertRaises(ValueError):
            lire_fichier("paie.xlsx", b"pas un zip")

    def test_dates(self):
        self.assertEqual(convertir_date("15/09/2010"), "2010-09-15")
        self.assertEqual(convertir_date("2010-09-15 00:00:00"), "2010-09-15")


class TestAuth(unittest.TestCase):
    def setUp(self):
        for f in os.listdir(_dossier.name):
            os.remove(os.path.join(_dossier.name, f))

    def test_comptes_et_sessions(self):
        self.assertTrue(auth.aucun_utilisateur())
        auth.creer_utilisateur("admin", "motdepasse1", admin=True)
        self.assertTrue(auth.verifier("admin", "motdepasse1"))
        self.assertFalse(auth.verifier("admin", "mauvais"))
        self.assertFalse(auth.verifier("inconnu", "motdepasse1"))
        with open(os.path.join(_dossier.name, "utilisateurs.json"), encoding="utf-8") as f:
            self.assertNotIn("motdepasse1", f.read())
        jeton = auth.ouvrir_session("admin")
        self.assertEqual(auth.session(jeton), "admin")
        auth.fermer_session(jeton)
        self.assertIsNone(auth.session(jeton))

    def test_regles(self):
        with self.assertRaises(ValueError):
            auth.creer_utilisateur("a", "court")
        auth.creer_utilisateur("admin", "motdepasse1", admin=True)
        with self.assertRaises(ValueError):
            auth.creer_utilisateur("admin", "motdepasse2")
        with self.assertRaises(ValueError):
            auth.supprimer_utilisateur("admin")      # dernier administrateur

    def test_registre(self):
        registre.enregistrer([{"matricule": "1", "nom": "A", "salaire_base": "8000", "date_embauche": "2020-01-01"}])
        ajoutes, maj = registre.enregistrer([
            {"matricule": "1", "nom": "A2", "salaire_base": "9000", "date_embauche": "2020-01-01"},
            {"matricule": "2", "nom": "B", "salaire_base": "7000", "date_embauche": "2021-01-01"}])
        self.assertEqual((ajoutes, maj), (1, 1))
        self.assertEqual([s["nom"] for s in registre.charger()], ["A2", "B"])
        bulletins, erreurs = calculer_registre(2026, 10)
        self.assertEqual((len(bulletins), erreurs), (2, []))
        self.assertEqual(bulletins[0].salaire_brut, D("9900.00"))   # + 10 % ancienneté (6 ans)


class TestServeur(unittest.TestCase):
    """Parcours complet via HTTP : installation, connexion, import, paie, déconnexion."""

    @classmethod
    def setUpClass(cls):
        for f in os.listdir(_dossier.name):
            os.remove(os.path.join(_dossier.name, f))
        cls.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
        cls.url = f"http://127.0.0.1:{cls.serveur.server_address[1]}"
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def requete(self, client, chemin, donnees=None, multipart=None):
        entetes = {}
        if multipart:
            limite = "----limitetest"
            corps = b""
            for nom, (fichier, contenu) in multipart.items():
                dispo = f'form-data; name="{nom}"' + (f'; filename="{fichier}"' if fichier else "")
                corps += f"--{limite}\r\nContent-Disposition: {dispo}\r\n\r\n".encode() + contenu + b"\r\n"
            donnees = corps + f"--{limite}--\r\n".encode()
            entetes["Content-Type"] = f"multipart/form-data; boundary={limite}"
        elif donnees is not None:
            donnees = urllib.parse.urlencode(donnees).encode()
        try:
            reponse = client.open(urllib.request.Request(self.url + chemin, data=donnees, headers=entetes))
        except urllib.error.HTTPError as erreur:
            return erreur.code, erreur.geturl(), erreur.read().decode("utf-8-sig")
        return reponse.status, reponse.geturl(), reponse.read().decode("utf-8-sig")

    def test_parcours(self):
        c = self.client()
        _, url, _ = self.requete(c, "/salaries")
        self.assertTrue(url.endswith("/installation"))
        code, _, page = self.requete(c, "/installation", {"identifiant": "admin", "mot_de_passe": "court",
                                                          "confirmation": "court"})
        self.assertEqual(code, 400)
        _, url, page = self.requete(c, "/installation", {"identifiant": "admin", "mot_de_passe": "motdepasse1",
                                                         "confirmation": "motdepasse1"})
        self.assertTrue(url.endswith("/salaries"))
        self.assertIn("Déconnexion", page)

        code, _, page = self.requete(c, "/salaries/import", multipart={
            "fichier": ("salaries.csv", modele_csv().encode("utf-8")), "mode": (None, b"remplacer")})
        self.assertEqual(code, 200)
        self.assertIn("3 salarié(s) importé(s)", page)

        _, _, page = self.requete(c, "/paie", {"annee": "2026", "mois": "10"})
        self.assertIn("Paie de octobre 2026", page)
        self.assertEqual(page.count("Bulletin de paie</h1>"), 3)
        _, _, journal = self.requete(c, "/journal.csv?annee=2026&mois=10")
        self.assertIn("Salma El Idrissi", journal)

        # Un autre navigateur sans session est renvoyé vers la connexion.
        autre = self.client()
        _, url, _ = self.requete(autre, "/journal.csv?annee=2026&mois=10")
        self.assertTrue(url.endswith("/connexion"))
        code, _, _ = self.requete(autre, "/connexion", {"identifiant": "admin", "mot_de_passe": "faux"})
        self.assertEqual(code, 401)

        # Ajout d'un utilisateur simple : pas d'accès à la gestion des utilisateurs.
        self.requete(c, "/utilisateurs/ajouter", {"identifiant": "compta", "mot_de_passe": "motdepasse2",
                                                  "role": "utilisateur"})
        self.requete(autre, "/connexion", {"identifiant": "compta", "mot_de_passe": "motdepasse2"})
        code, _, _ = self.requete(autre, "/utilisateurs")
        self.assertEqual(code, 403)

        _, url, _ = self.requete(c, "/deconnexion", {})
        self.assertTrue(url.endswith("/connexion"))
        _, url, _ = self.requete(c, "/salaries")
        self.assertTrue(url.endswith("/connexion"))


if __name__ == "__main__":
    unittest.main()
