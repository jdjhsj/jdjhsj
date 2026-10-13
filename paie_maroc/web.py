"""Interface web locale (bibliothèque standard uniquement).

Lancement : python -m paie_maroc web   puis ouvrir http://localhost:8000
"""

from __future__ import annotations

from datetime import date
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .calcul import calculer_bulletin
from .conges import droits_conges
from .donnees import salarie_depuis_dict, variables_depuis_dict
from .rendu import CSS, _qte, dh, page_html
from .rubriques import CATEGORIES, RUBRIQUES, par_categorie
from .types_conges import GROUPES, TYPES_CONGE, par_groupe

HS = [("jour", "Jour +25 %"), ("nuit", "Nuit +50 %"),
      ("repos_jour", "Repos jour +50 %"), ("repos_nuit", "Repos nuit +100 %")]

FORM_CSS = """
form, .carte { max-width:900px; margin:0 auto 24px; background:#fff; border:1px solid var(--trait); border-radius:8px; padding:24px; }
fieldset { border:1px solid var(--trait); border-radius:6px; margin:0 0 16px; padding:12px 16px 16px; }
legend { font-weight:600; padding:0 6px; }
.grille { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px 16px; }
label { display:flex; flex-direction:column; font-size:13px; color:var(--gris); gap:4px; }
input { font:inherit; color:var(--encre); padding:7px 9px; border:1px solid var(--trait); border-radius:5px; min-width:0; }
button[type=submit] { font:inherit; font-weight:600; background:var(--accent); color:#fff; border:none; padding:10px 20px; border-radius:6px; cursor:pointer; }
details { border:1px solid var(--trait); border-radius:6px; margin:0 0 12px; padding:10px 16px; }
details[open] { padding-bottom:16px; }
summary { font-weight:600; cursor:pointer; }
.aide { display:block; font-size:11.5px; color:var(--gris); }
.ref td, .ref th { text-align:left; vertical-align:top; }
nav { max-width:900px; margin:0 auto 16px; display:flex; gap:16px; } nav a { color:var(--accent); }
.erreur { max-width:900px; margin:0 auto 16px; background:#fdecec; border:1px solid #e9a3a3; padding:10px 14px; border-radius:6px; }
"""


def _champ(nom, libelle, valeur="", type_="text", extra=""):
    return (f'<label>{escape(libelle)}<input name="{nom}" type="{type_}" '
            f'value="{escape(str(valeur))}" {extra}></label>')


def _num(nom, libelle, valeur="", aide=""):
    aide_html = f'<span class="aide">{escape(aide)}</span>' if aide else ""
    return (f'<label>{escape(libelle)}{aide_html}<input name="{nom}" type="text" inputmode="decimal" '
            f'value="{escape(str(valeur))}"></label>')


def _aide_rubrique(r) -> str:
    if r.categorie in ("imposable", "avantage"):
        return "Imposable IR et CNSS"
    if r.ir == r.cnss:
        return r.ir.description()
    return f"IR : {r.ir.description()} · CNSS : {r.cnss.description()}"


def _champs_rubriques() -> str:
    blocs = []
    for cat, rubriques in par_categorie().items():
        champs = []
        for r in rubriques:
            champs.append(_num("ind_" + r.code, r.libelle, aide=_aide_rubrique(r)))
            if "par_unite" in (r.ir.type, r.cnss.type):
                champs.append(_num("qte_" + r.code, f"{r.libelle} : quantité ({r.unite})"))
            if {"annuel", "global"} & {r.ir.type, r.cnss.type}:
                champs.append(_num("cumul_" + r.code, f"{r.libelle} : déjà versé cette année (DH)"))
        ouvert = " open" if cat == "exoneree" else ""
        blocs.append(f'<details{ouvert}><summary>{escape(CATEGORIES[cat])}</summary>'
                     f'<div class="grille" style="margin-top:12px">{"".join(champs)}</div></details>')
    return "".join(blocs)


def _champs_absences() -> str:
    blocs = []
    for groupe, types in par_groupe().items():
        champs = "".join(_num("abs_" + t.code, t.libelle, aide=t.regime) for t in types)
        ouvert = " open" if groupe == "annuel" else ""
        blocs.append(f'<details{ouvert}><summary>{escape(GROUPES[groupe])}</summary>'
                     f'<div class="grille" style="margin-top:12px">{champs}</div></details>')
    return "".join(blocs)


def _page(titre, corps):
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(titre)}</title><style>{CSS}{FORM_CSS}</style></head><body>'
            f'<nav><a href="/">Bulletin de paie</a><a href="/conges">Congés payés</a><a href="/referentiel">Référentiel indemnités et congés</a></nav>'
            f'{corps}</body></html>')


def formulaire_paie(erreur: str = "") -> str:
    auj = date.today()
    err = f'<div class="erreur">{escape(erreur)}</div>' if erreur else ""
    primes = "".join(
        f'{_champ(f"prime_libelle_{i}", f"Prime imposable {i} (libellé)")}{_num(f"prime_montant_{i}", "Montant (DH)")}'
        for i in (1, 2, 3))
    return _page("Paie Maroc", f"""{err}
<form method="post" action="/bulletin">
  <h1>Calcul du bulletin de paie</h1>
  <p class="sous">CNSS, AMO, IR, ancienneté, heures supplémentaires et congés payés — droit marocain.</p>
  <fieldset><legend>Salarié</legend><div class="grille">
    {_champ("nom", "Nom et prénom", extra="required")}
    {_champ("matricule", "Matricule")}
    {_champ("fonction", "Fonction")}
    {_champ("cin", "CIN")}
    {_champ("numero_cnss", "N° CNSS")}
    {_num("salaire_base", "Salaire de base mensuel (DH)")}
    {_champ("date_embauche", "Date d'embauche", type_="date", extra="required")}
    {_champ("date_naissance", "Date de naissance", type_="date")}
    {_num("personnes_a_charge", "Personnes à charge (max 6)", 0)}
    {_num("taux_cimr_salarie", "CIMR salarié (%)", 0)}
    {_num("taux_cimr_patronal", "CIMR patronal (%)", 0)}
  </div></fieldset>
  <fieldset><legend>Période</legend><div class="grille">
    {_num("mois", "Mois (1-12)", auj.month)}
    {_num("annee", "Année", auj.year)}
  </div></fieldset>
  <fieldset><legend>Heures supplémentaires (nombre d'heures)</legend><div class="grille">
    {"".join(_num("hs_" + k, l) for k, l in HS)}
  </div></fieldset>
  <fieldset><legend>Primes imposables (libellé libre)</legend><div class="grille">
    {primes}
  </div></fieldset>
  <fieldset><legend>Indemnités, primes et avantages (catalogue)</legend>
    {_champs_rubriques()}
  </fieldset>
  <fieldset><legend>Congés et absences du mois (jours ouvrables)</legend>
    {_champs_absences()}
    <div class="grille">
      {_num("salaire_reference_conges", "Salaire moyen 12 mois pour le congé annuel (facultatif)")}
      {_num("salaire_reference_ij", "Salaire moyen pour les indemnités CNSS (facultatif)")}
    </div>
  </fieldset>
  <fieldset><legend>Déductions et retenues</legend><div class="grille">
    {_num("interets_logement", "Intérêts prêt logement (DH/mois)")}
    {_num("avance", "Avance sur salaire (DH)")}
    {_num("autres_retenues", "Autres retenues (DH)")}
  </div></fieldset>
  <button type="submit">Calculer le bulletin</button>
</form>""")


def formulaire_conges(resultat: str = "", erreur: str = "") -> str:
    err = f'<div class="erreur">{escape(erreur)}</div>' if erreur else ""
    return _page("Congés payés", f"""{err}
<form method="post" action="/conges">
  <h1>Droits à congés payés</h1>
  <p class="sous">1,5 jour ouvrable par mois (2 jours avant 18 ans), +1,5 jour par tranche de 5 ans d'ancienneté, plafond 30 jours.</p>
  <div class="grille">
    {_champ("date_embauche", "Date d'embauche", type_="date", extra="required")}
    {_champ("date_naissance", "Date de naissance", type_="date")}
    {_champ("date_calcul", "Date de calcul", date.today().isoformat(), "date")}
    {_num("mois_travailles", "Mois de service effectif (période de référence)", 12)}
    {_num("salaire_reference", "Salaire mensuel de référence (DH)")}
    {_num("jours_pris", "Jours déjà pris", 0)}
  </div>
  <p><button type="submit">Calculer</button></p>
</form>{resultat}""")


def page_referentiel() -> str:
    lignes_r = []
    for cat, rubriques in par_categorie().items():
        lignes_r.append(f'<tr class="total"><td colspan="4">{escape(CATEGORIES[cat])}</td></tr>')
        for r in rubriques:
            lignes_r.append(f"<tr><td>{escape(r.libelle)}<br><code>{r.code}</code></td><td>{escape(r.ir.description())}</td>"
                            f"<td>{escape(r.cnss.description())}</td><td>{escape(r.note)}</td></tr>")
    lignes_c = []
    for groupe, types in par_groupe().items():
        lignes_c.append(f'<tr class="total"><td colspan="5">{escape(GROUPES[groupe])}</td></tr>')
        for t in types:
            duree = f"{t.duree_legale:g} j" if t.duree_legale is not None else ""
            lignes_c.append(f"<tr><td>{escape(t.libelle)}<br><code>{t.code}</code></td><td>{duree}</td>"
                            f"<td>{escape(t.regime)}</td><td>{escape(t.article)}</td><td>{escape(t.note)}</td></tr>")
    return _page("Référentiel", f"""
<div class="carte">
  <h1>Indemnités et primes</h1>
  <p class="sous">Régime fiscal (IR, art. 57 CGI) et social (CNSS/AMO, arrêté n° 1314-25). Les plafonds sont modifiables dans <code>rubriques.py</code>.</p>
  <div class="wrap"><table class="ref"><thead><tr><th>Rubrique</th><th>IR</th><th>CNSS / AMO</th><th>Conditions</th></tr></thead>
  <tbody>{"".join(lignes_r)}</tbody></table></div>
</div>
<div class="carte">
  <h1>Congés et absences</h1>
  <p class="sous">Code du travail (loi 65-99). Modifiables dans <code>types_conges.py</code>.</p>
  <div class="wrap"><table class="ref"><thead><tr><th>Type</th><th>Durée légale</th><th>Rémunération</th><th>Texte</th><th>Remarques</th></tr></thead>
  <tbody>{"".join(lignes_c)}</tbody></table></div>
</div>""")


def _valeurs(corps: bytes) -> dict:
    return {k: v[0].strip() for k, v in parse_qs(corps.decode("utf-8"), keep_blank_values=True).items()}


def calcul_depuis_formulaire(f: dict):
    salarie = salarie_depuis_dict(f)
    variables = variables_depuis_dict({
        **f,
        "heures_sup": {k: f.get("hs_" + k) for k, _ in HS},
        "indemnites": {code: {"montant": f.get("ind_" + code), "quantite": f.get("qte_" + code),
                              "cumul_annuel": f.get("cumul_" + code)} for code in RUBRIQUES},
        "absences": {code: f.get("abs_" + code) for code in TYPES_CONGE},
        "primes": [{"libelle": f.get(f"prime_libelle_{i}") or f"Prime {i}", "montant": f.get(f"prime_montant_{i}")}
                   for i in (1, 2, 3)],
    })
    return calculer_bulletin(salarie, variables)


class Gestionnaire(BaseHTTPRequestHandler):
    def _envoyer(self, html: str, code: int = 200):
        donnees = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    def do_GET(self):
        if self.path == "/":
            self._envoyer(formulaire_paie())
        elif self.path == "/conges":
            self._envoyer(formulaire_conges())
        elif self.path == "/referentiel":
            self._envoyer(page_referentiel())
        else:
            self._envoyer(_page("Introuvable", "<p>Page introuvable.</p>"), 404)

    def do_POST(self):
        longueur = int(self.headers.get("Content-Length") or 0)
        f = _valeurs(self.rfile.read(longueur))
        try:
            if self.path == "/bulletin":
                self._envoyer(page_html([calcul_depuis_formulaire(f)], retour="/"))
            elif self.path == "/conges":
                d = droits_conges(
                    date.fromisoformat(f["date_embauche"]),
                    date.fromisoformat(f.get("date_calcul") or date.today().isoformat()),
                    f.get("mois_travailles") or 0,
                    f.get("salaire_reference") or 0,
                    f.get("jours_pris") or 0,
                    date.fromisoformat(f["date_naissance"]) if f.get("date_naissance") else None,
                )
                res = f"""<div class="carte"><table><tbody>
<tr><td>Jours acquis ({_qte(d.mois_travailles)} mois × {_qte(d.jours_par_mois)})</td><td>{_qte(d.jours_base)}</td></tr>
<tr><td>Bonus ancienneté</td><td>{_qte(d.jours_anciennete)}</td></tr>
<tr class="total"><td>Total acquis (plafond 30)</td><td>{_qte(d.jours_acquis)}</td></tr>
<tr><td>Jours pris</td><td>{_qte(d.jours_pris)}</td></tr>
<tr class="total"><td>Solde</td><td>{_qte(d.solde)}</td></tr>
<tr><td>Salaire journalier (référence / 26)</td><td>{dh(d.salaire_journalier)} DH</td></tr>
<tr class="total"><td>Valeur du solde (indemnité compensatrice)</td><td>{dh(d.valeur_solde)} DH</td></tr>
</tbody></table></div>"""
                self._envoyer(formulaire_conges(res))
            else:
                self._envoyer(_page("Introuvable", "<p>Page introuvable.</p>"), 404)
        except (KeyError, ValueError, ArithmeticError) as exc:
            message = f"Données invalides : {exc}"
            page = formulaire_conges(erreur=message) if self.path == "/conges" else formulaire_paie(message)
            self._envoyer(page, 400)


def lancer(hote: str = "127.0.0.1", port: int = 8000, ouvrir_navigateur: bool = False):
    serveur = ThreadingHTTPServer((hote, port), Gestionnaire)
    adresse = f"http://{'localhost' if hote == '127.0.0.1' else hote}:{port}"
    print(f"Logiciel de paie disponible sur {adresse}")
    print("Laissez cette fenêtre ouverte. Pour arrêter : fermez-la ou appuyez sur Ctrl+C.")
    if ouvrir_navigateur:
        import webbrowser
        webbrowser.open(adresse)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()
