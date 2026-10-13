import unittest
from datetime import date
from decimal import Decimal as D

from paie_maroc import Prime, Salarie, VariablesPaie, calculer_bulletin, droits_conges
from paie_maroc.calcul import frais_professionnels, ir_mensuel, taux_anciennete
from paie_maroc.parametres import parametres
from paie_maroc.rendu import journal_csv, page_html
from paie_maroc.web import calcul_depuis_formulaire

P26 = parametres(2026)


def salarie(**kw):
    defaut = dict(nom="Test", salaire_base=D("8000"), date_embauche=date(2026, 1, 1))
    defaut.update(kw)
    return Salarie(**defaut)


class TestBareme(unittest.TestCase):
    def test_exoneration_jusqu_a_40000_par_an(self):
        self.assertEqual(ir_mensuel(D("3333.33"), P26), D("0.00"))

    def test_tranches(self):
        # 60 000 DH/an -> 60 000 x 10 % - 4 000 = 2 000 /an
        self.assertEqual(ir_mensuel(D("5000"), P26), D("166.67"))
        # 120 000 DH/an -> 34 % - 22 000 = 18 800 /an
        self.assertEqual(ir_mensuel(D("10000"), P26), D("1566.67"))
        # 240 000 DH/an -> 37 % - 27 400 = 61 400 /an
        self.assertEqual(ir_mensuel(D("20000"), P26), D("5116.67"))

    def test_frais_professionnels(self):
        self.assertEqual(frais_professionnels(D("6000"), P26), D("2100.00"))      # 35 %
        self.assertEqual(frais_professionnels(D("8000"), P26), D("2000.00"))      # 25 %
        self.assertEqual(frais_professionnels(D("20000"), P26), D("2916.67"))     # plafond 35 000/an

    def test_anciennete(self):
        attendus = {1: "0", 2: "0.05", 4: "0.05", 5: "0.10", 12: "0.15", 20: "0.20", 30: "0.25"}
        for ans, taux in attendus.items():
            self.assertEqual(taux_anciennete(ans, P26), D(taux), ans)


class TestBulletin(unittest.TestCase):
    def test_bulletin_simple(self):
        b = calculer_bulletin(salarie(), VariablesPaie(2026, 10))
        self.assertEqual(b.salaire_brut, D("8000.00"))
        self.assertEqual(b.cnss, D("268.80"))          # 6 000 x 4,48 %
        self.assertEqual(b.amo, D("180.80"))           # 8 000 x 2,26 %
        self.assertEqual(b.frais_professionnels, D("2000.00"))
        self.assertEqual(b.net_imposable, D("5550.40"))
        # 66 604,80 x 20 % - 10 000 = 3 320,96 /an -> 276,75 /mois
        self.assertEqual(b.ir, D("276.75"))
        self.assertEqual(b.net_a_payer, D("7273.65"))
        # patronal : 538,80 + 512 + 128 + 328,80
        self.assertEqual(b.charges_patronales, D("1507.60"))

    def test_charges_de_famille_2026(self):
        b0 = calculer_bulletin(salarie(), VariablesPaie(2026, 10))
        b3 = calculer_bulletin(salarie(personnes_a_charge=3), VariablesPaie(2026, 10))
        self.assertEqual(b0.ir - b3.ir, D("150.00"))      # 3 x 600 / 12
        b9 = calculer_bulletin(salarie(personnes_a_charge=9), VariablesPaie(2026, 10))
        self.assertEqual(b9.deduction_famille, D("300.00"))
        b25 = calculer_bulletin(salarie(personnes_a_charge=3), VariablesPaie(2025, 10))
        self.assertEqual(b25.deduction_famille, D("125.00"))  # 3 x 500 / 12

    def test_ir_jamais_negatif(self):
        b = calculer_bulletin(salarie(salaire_base=D("3422.72"), personnes_a_charge=6), VariablesPaie(2026, 1))
        self.assertEqual(b.ir, D("0"))

    def test_heures_sup_et_anciennete(self):
        s = salarie(salaire_base=D("9550"), date_embauche=date(2020, 1, 1))  # 6 ans -> 10 %
        v = VariablesPaie(2026, 6, heures_sup={"jour": D("10"), "repos_nuit": D("2")})
        b = calculer_bulletin(s, v)
        # taux horaire 9 550 / 191 = 50 DH
        self.assertEqual(b.taux_horaire, D("50.00"))
        hs = [l for l in b.lignes_gains if l.libelle.startswith("Heures")]
        self.assertEqual([l.gain for l in hs], [D("625.00"), D("200.00")])
        anc = [l for l in b.lignes_gains if l.libelle.startswith("Prime d'anc")][0]
        self.assertEqual(anc.gain, D("1037.50"))      # 10 % x (9 550 + 825)

    def test_indemnites_exonerees_et_depassement(self):
        v = VariablesPaie(2026, 10, indemnites={"transport": D("600"), "lait": D("100")})
        b = calculer_bulletin(salarie(), v)
        self.assertEqual(b.salaire_brut, D("8700.00"))
        self.assertEqual(b.total_exonere, D("600.00"))  # 500 + 100
        self.assertEqual(b.brut_imposable, D("8100.00"))
        self.assertTrue(b.avertissements)

    def test_panier_plafonne_selon_jours_travailles(self):
        v = VariablesPaie(2026, 10, indemnites={"panier": D("5000")})
        b = calculer_bulletin(salarie(), v)
        self.assertEqual(b.total_exonere, D("931.84"))  # 2 x 17,92 x 26

    def test_conges_payes_avec_salaire_reference(self):
        v = VariablesPaie(2026, 8, jours_conges=D("13"), salaire_reference_conges=D("10400"))
        b = calculer_bulletin(salarie(salaire_base=D("7800")), v)
        # 7 800 - 7 800/26 x 13 + 10 400/26 x 13 = 3 900 + 5 200
        self.assertEqual(b.salaire_brut, D("9100.00"))

    def test_conges_sans_reference_sont_neutres(self):
        b1 = calculer_bulletin(salarie(), VariablesPaie(2026, 8))
        b2 = calculer_bulletin(salarie(), VariablesPaie(2026, 8, jours_conges=D("5")))
        self.assertEqual(b1.salaire_brut, b2.salaire_brut)

    def test_absence(self):
        b = calculer_bulletin(salarie(salaire_base=D("7800")), VariablesPaie(2026, 8, jours_absence=D("2")))
        self.assertEqual(b.salaire_brut, D("7200.00"))

    def test_cimr_et_interets_logement(self):
        s = salarie(salaire_base=D("20000"), taux_cimr_salarie=D("0.06"), taux_cimr_patronal=D("0.078"))
        b = calculer_bulletin(s, VariablesPaie(2026, 3, interets_logement=D("5000")))
        self.assertEqual(b.cimr, D("1200.00"))
        self.assertEqual(b.interets_logement, D("2000.00"))   # plafond 10 % du SBI

    def test_avantages_nature_non_verses(self):
        b = calculer_bulletin(salarie(), VariablesPaie(2026, 10, avantages_nature=D("1000")))
        self.assertEqual(b.frais_professionnels, D("2000.00"))  # hors avantages en nature
        self.assertEqual(b.net_a_payer, b.salaire_brut - b.total_retenues - D("1000"))

    def test_alerte_smig(self):
        b = calculer_bulletin(salarie(salaire_base=D("3000")), VariablesPaie(2026, 1))
        self.assertTrue(any("SMIG" in a for a in b.avertissements))

    def test_primes(self):
        v = VariablesPaie(2026, 10, primes=[Prime("Prime de bilan", D("1000"))])
        self.assertEqual(calculer_bulletin(salarie(), v).brut_imposable, D("9000.00"))


class TestRubriques(unittest.TestCase):
    def bulletin(self, **indemnites):
        return calculer_bulletin(salarie(), VariablesPaie(2026, 10, indemnites=indemnites))

    def test_catalogue_complet(self):
        from paie_maroc.rubriques import RUBRIQUES
        self.assertGreaterEqual(len(RUBRIQUES), 40)
        for r in RUBRIQUES.values():
            self.assertTrue(r.ir.description() and r.cnss.description())

    def test_prime_imposable_du_catalogue(self):
        b = self.bulletin(prime_13e_mois=D("8000"))
        self.assertEqual(b.brut_imposable, D("16000.00"))
        self.assertEqual(b.base_cnss, D("16000.00"))

    def test_tournee_et_kilometrique(self):
        b = self.bulletin(tournee=D("1800"), kilometrique={"montant": D("1000"), "quantite": D("300")})
        self.assertEqual(b.total_exonere, D("2400.00"))   # 1 500 + 3 x 300
        self.assertEqual(b.brut_imposable, D("8400.00"))

    def test_kilometrique_sans_quantite_imposable(self):
        b = self.bulletin(kilometrique=D("500"))
        self.assertEqual(b.total_exonere, D("0.00"))
        self.assertTrue(any("quantité" in a for a in b.avertissements))

    def test_deplacement_forfaitaire_plafonne_5000(self):
        b = calculer_bulletin(salarie(salaire_base=D("20000")),
                              VariablesPaie(2026, 10, indemnites={"deplacement_forfaitaire": D("7000")}))
        self.assertEqual(b.total_exonere, D("5000.00"))

    def test_gratifications_sociales_regimes_differents(self):
        b = self.bulletin(gratifications_sociales={"montant": D("3000"), "cumul_annuel": D("1000")})
        self.assertEqual(b.total_exonere, D("1500.00"))        # IR : 2 500 - 1 000
        self.assertEqual(b.total_exonere_cnss, D("3000.00"))   # CNSS : 5 000 - 1 000
        self.assertEqual(b.base_cnss, D("8000.00"))

    def test_indemnite_licenciement(self):
        b = self.bulletin(indemnite_licenciement=D("120000"), indemnite_preavis=D("8000"))
        self.assertEqual(b.total_exonere, D("120000.00"))
        self.assertEqual(b.brut_imposable, D("16000.00"))
        self.assertEqual(b.base_cnss, D("16000.00"))

    def test_avantages_en_nature_catalogue(self):
        b = self.bulletin(avantage_voiture=D("1500"), avantage_logement=D("2000"))
        self.assertEqual(b.brut_imposable, D("11500.00"))
        self.assertEqual(b.net_a_payer, b.salaire_brut - b.total_retenues - D("3500"))


class TestTypesConges(unittest.TestCase):
    def bulletin(self, base="7800", **absences):
        return calculer_bulletin(salarie(salaire_base=D(base)), VariablesPaie(2026, 10, absences=absences))

    def test_evenements_familiaux_payes(self):
        b = self.bulletin(mariage_salarie=D("4"), naissance=D("3"), deces_proche=D("3"))
        self.assertEqual(b.salaire_brut, D("7800.00"))
        self.assertEqual(b.jours_travailles, D("16"))

    def test_depassement_duree_legale(self):
        b = self.bulletin(mariage_salarie=D("6"))
        self.assertEqual(b.salaire_brut, D("7200.00"))   # 2 jours au-delà non payés
        self.assertTrue(any("durée légale" in a for a in b.avertissements))

    def test_maladie_retenue_et_ij_cnss(self):
        b = self.bulletin(maladie=D("5"))
        self.assertEqual(b.salaire_brut, D("6300.00"))   # 7 800 - 5 x 300
        ij = b.indemnites_cnss[0]
        self.assertEqual(ij.jours, D("2"))               # carence de 3 jours
        self.assertEqual(ij.taux_journalier, D("153.85"))  # 6 000 / 26 x 2/3
        self.assertEqual(ij.montant, D("307.70"))

    def test_maternite(self):
        b = self.bulletin(maternite=D("26"))
        self.assertEqual(b.salaire_brut, D("0.00"))
        self.assertEqual(b.indemnites_cnss[0].montant, D("6000.02"))   # 230,77 x 26

    def test_accident_travail_premier_jour_paye(self):
        b = self.bulletin(accident_travail=D("4"))
        self.assertEqual(b.salaire_brut, D("6900.00"))   # 3 jours retenus

    def test_sans_solde_et_jour_ferie(self):
        b = self.bulletin(sans_solde=D("2"), jour_ferie=D("1"))
        self.assertEqual(b.salaire_brut, D("7200.00"))

    def test_panier_tient_compte_des_absences(self):
        v = VariablesPaie(2026, 10, indemnites={"panier": D("5000")}, absences={"maladie": D("6")})
        b = calculer_bulletin(salarie(), v)
        self.assertEqual(b.total_exonere, D("716.80"))   # 2 x 17,92 x 20 jours

    def test_type_inconnu(self):
        with self.assertRaises(ValueError):
            self.bulletin(vacances=D("1"))


class TestConges(unittest.TestCase):
    def test_droits_standard(self):
        d = droits_conges(date(2024, 1, 1), date(2026, 12, 31), 12, 7800)
        self.assertEqual(d.jours_acquis, D("18"))
        self.assertEqual(d.salaire_journalier, D("300.00"))
        self.assertEqual(d.valeur_solde, D("5400.00"))

    def test_bonus_anciennete_et_plafond(self):
        d = droits_conges(date(2010, 1, 1), date(2026, 12, 31), 12, 7800, jours_pris=10)
        self.assertEqual(d.jours_acquis, D("22.5"))     # 18 + 3 x 1,5
        self.assertEqual(d.solde, D("12.5"))
        d = droits_conges(date(1980, 1, 1), date(2026, 12, 31), 12, 7800)
        self.assertEqual(d.jours_acquis, D("30"))

    def test_mineur(self):
        d = droits_conges(date(2025, 1, 1), date(2026, 6, 30), 6, 3422.72, date_naissance=date(2009, 1, 1))
        self.assertEqual(d.jours_acquis, D("12"))


class TestRenduEtWeb(unittest.TestCase):
    def test_formulaire_web(self):
        f = {"nom": "Karim", "salaire_base": "8000", "date_embauche": "2026-01-01", "mois": "10",
             "annee": "2026", "personnes_a_charge": "0", "hs_jour": "", "ind_transport": "300",
             "prime_libelle_1": "Bonus", "prime_montant_1": "200", "jours_conges": ""}
        b = calcul_depuis_formulaire(f)
        self.assertEqual(b.salaire_brut, D("8500.00"))
        html = page_html([b])
        self.assertIn("Net à payer", html)
        self.assertIn("Karim", journal_csv([b]))

    def test_formulaire_web_catalogue(self):
        f = {"nom": "Nadia", "salaire_base": "7800", "date_embauche": "2026-01-01", "mois": "10",
             "annee": "2026", "ind_kilometrique": "600", "qte_kilometrique": "200",
             "ind_prime_13e_mois": "7800", "abs_maladie": "4", "abs_naissance": "3"}
        b = calcul_depuis_formulaire(f)
        self.assertEqual(b.total_exonere, D("600.00"))
        self.assertEqual(b.salaire_brut, D("15600.00") - D("1200.00") + D("600.00"))
        self.assertIn("Indemnités journalières CNSS", page_html([b]))

    def test_pages_web(self):
        from paie_maroc.web import formulaire_paie, page_referentiel
        self.assertIn("abs_maternite", formulaire_paie())
        self.assertIn("Prime de tournée", page_referentiel())


if __name__ == "__main__":
    unittest.main()
