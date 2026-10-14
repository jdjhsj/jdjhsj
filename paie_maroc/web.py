"""Interface web locale (bibliothèque standard uniquement).

Lancement : python -m paie_maroc web   puis ouvrir http://localhost:8000
"""

from __future__ import annotations

import contextvars
import time
from datetime import date
from email.parser import BytesParser
from email.policy import default as politique_email
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from xml.etree.ElementTree import ParseError as ElementTreeError

from . import auth, registre
from .calcul import calculer_bulletin, dec
from .conges import droits_conges
from .donnees import salarie_depuis_dict, variables_depuis_dict
from .importation import analyser, lire_fichier, modele_csv
from .rendu import CSS, MOIS, _qte, bulletin_html, dh, journal_csv, page_html
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
.barre { background:var(--encre); color:#fff; margin:-24px -16px 24px; padding:0 16px; }
.barre-int { max-width:1100px; margin:0 auto; display:flex; align-items:center; gap:20px; flex-wrap:wrap; min-height:56px; }
.marque { font-weight:700; font-size:16px; letter-spacing:.2px; white-space:nowrap; }
.marque span { color:#7fd1b0; }
nav { display:flex; gap:4px; flex-wrap:wrap; flex:1; }
nav a { color:#cfd5e1; text-decoration:none; padding:8px 12px; border-radius:6px; font-size:14px; }
nav a:hover { background:rgba(255,255,255,.08); color:#fff; }
nav a.actif { background:rgba(255,255,255,.14); color:#fff; }
.compte { display:flex; align-items:center; gap:10px; font-size:13px; color:#cfd5e1; }
.compte form { margin:0; padding:0; border:none; background:none; }
.compte button { font:inherit; background:transparent; color:#fff; border:1px solid rgba(255,255,255,.35); border-radius:6px; padding:5px 10px; cursor:pointer; }
.large { max-width:1100px; }
.ok { max-width:900px; margin:0 auto 16px; background:#e8f6ef; border:1px solid #9fd5bb; padding:10px 14px; border-radius:6px; }
.ok ul, .erreur ul { margin:6px 0 0; padding-left:20px; }
.bouton { display:inline-block; font:inherit; font-size:14px; padding:9px 16px; border-radius:6px; border:1px solid var(--trait); background:#fff; color:var(--encre); text-decoration:none; cursor:pointer; }
button[type=submit].bouton { font-weight:400; background:#fff; color:var(--encre); border:1px solid var(--trait); padding:9px 16px; }
button[type=submit].bouton.danger { color:#a12a2a; border-color:#e9a3a3; }
button[type=submit].lien-btn { background:none; border:none; color:#a12a2a; cursor:pointer; font:inherit; font-size:13px; font-weight:400; padding:0; }
.journal th:nth-child(2), .journal td:nth-child(2) { text-align:left; }
@media print { .barre, .no-print, .erreur, .ok { display:none !important; } }
.ligne-actions { display:flex; gap:10px; flex-wrap:wrap; align-items:end; margin-top:12px; }
.ligne-actions form { margin:0; padding:0; border:none; background:none; }
.connexion { max-width:400px; margin:8vh auto 0; }
.connexion h1 { margin-top:0; }
.connexion label { margin-bottom:12px; }
.connexion button[type=submit] { width:100%; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:0 0 16px; }
.stats div { border:1px solid var(--trait); border-radius:6px; padding:10px 12px; font-size:13px; }
.stats b { display:block; font-size:18px; margin-top:2px; }
input[type=file] { padding:6px; background:var(--fond); }
select { font:inherit; padding:7px 9px; border:1px solid var(--trait); border-radius:5px; background:#fff; color:var(--encre); }
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


# Utilisateur connecté pour la requête en cours (affiché dans la barre de navigation).
_utilisateur = contextvars.ContextVar("utilisateur", default=None)
_chemin = contextvars.ContextVar("chemin", default="/")

LIENS = [("/salaries", "Salariés et paie du mois"), ("/", "Bulletin individuel"),
         ("/conges", "Congés payés"), ("/referentiel", "Référentiel"),
         ("/factures", "Factures"), ("/clients", "Clients"), ("/entreprise", "Entreprise")]


def _barre() -> str:
    utilisateur = _utilisateur.get()
    if not utilisateur:
        return ('<header class="barre"><div class="barre-int"><div class="marque">Paie <span>Maroc</span></div>'
                '</div></header>')
    liens = LIENS + ([("/utilisateurs", "Utilisateurs")] if auth.est_admin(utilisateur) else [])
    chemin = _chemin.get()
    nav = "".join(f'<a href="{url}"{" class=actif" if chemin in (url, url + ".csv") or chemin.startswith(url + "/") else ""}>'
                  f'{escape(nom)}</a>' for url, nom in liens)
    return (f'<header class="barre"><div class="barre-int"><div class="marque">Paie <span>Maroc</span></div>'
            f'<nav>{nav}</nav><div class="compte"><a href="/mot-de-passe" style="color:#cfd5e1">{escape(utilisateur)}</a>'
            f'<form method="post" action="/deconnexion"><button type="submit">Déconnexion</button></form>'
            f'</div></div></header>')


def _page(titre, corps):
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(titre)}</title><style>{CSS}{FORM_CSS}</style></head><body>'
            f'{_barre()}{corps}</body></html>')


def _messages(erreur: str = "", succes: str = "", details: list | None = None) -> str:
    liste = "<ul>" + "".join(f"<li>{escape(d)}</li>" for d in details) + "</ul>" if details else ""
    if erreur:
        return f'<div class="erreur">{escape(erreur)}{liste}</div>'
    if succes:
        return f'<div class="ok">{escape(succes)}{liste}</div>'
    return ""


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


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

def page_connexion(erreur: str = "") -> str:
    return _page("Connexion", f"""
<form method="post" action="/connexion" class="connexion">
  <h1>Connexion</h1>
  <p class="sous">Logiciel de paie — droit du travail marocain</p>
  {_messages(erreur)}
  {_champ("identifiant", "Identifiant", extra='required autofocus autocomplete="username"')}
  {_champ("mot_de_passe", "Mot de passe", type_="password", extra='required autocomplete="current-password"')}
  <button type="submit">Se connecter</button>
</form>""")


def page_installation(erreur: str = "") -> str:
    return _page("Premier lancement", f"""
<form method="post" action="/installation" class="connexion">
  <h1>Premier lancement</h1>
  <p class="sous">Créez le compte administrateur. Il pourra ensuite ajouter d'autres utilisateurs.</p>
  {_messages(erreur)}
  {_champ("identifiant", "Identifiant", extra='required autofocus autocomplete="username"')}
  {_champ("mot_de_passe", f"Mot de passe ({auth.LONGUEUR_MIN} caractères minimum)", type_="password",
          extra='required autocomplete="new-password"')}
  {_champ("confirmation", "Confirmer le mot de passe", type_="password", extra='required autocomplete="new-password"')}
  <button type="submit">Créer le compte</button>
</form>""")


def page_utilisateurs(erreur: str = "", succes: str = "") -> str:
    moi = _utilisateur.get()
    lignes = []
    for nom, compte in sorted(auth.utilisateurs().items()):
        bouton = "" if nom == moi else (
            f'<form method="post" action="/utilisateurs/supprimer" onsubmit="return confirm(\'Supprimer {escape(nom)} ?\')">'
            f'<input type="hidden" name="identifiant" value="{escape(nom)}">'
            f'<button class="lien-btn" type="submit">Supprimer</button></form>')
        lignes.append(f"<tr><td>{escape(nom)}{' (vous)' if nom == moi else ''}</td>"
                      f"<td>{'Administrateur' if compte.get('admin') else 'Utilisateur'}</td><td>{bouton}</td></tr>")
    return _page("Utilisateurs", f"""{_messages(erreur, succes)}
<div class="carte">
  <h1>Utilisateurs</h1>
  <div class="wrap"><table class="ref"><thead><tr><th>Identifiant</th><th>Rôle</th><th></th></tr></thead>
  <tbody>{"".join(lignes)}</tbody></table></div>
</div>
<form method="post" action="/utilisateurs/ajouter">
  <h2 style="margin-top:0">Ajouter un utilisateur</h2>
  <div class="grille">
    {_champ("identifiant", "Identifiant", extra="required")}
    {_champ("mot_de_passe", f"Mot de passe ({auth.LONGUEUR_MIN} caractères min.)", type_="password",
            extra='required autocomplete="new-password"')}
    <label>Rôle<select name="role"><option value="utilisateur">Utilisateur</option>
      <option value="admin">Administrateur</option></select></label>
  </div>
  <p><button type="submit">Ajouter</button></p>
</form>""")


def page_mot_de_passe(erreur: str = "", succes: str = "") -> str:
    return _page("Mot de passe", f"""{_messages(erreur, succes)}
<form method="post" action="/mot-de-passe" class="connexion" style="margin-top:0">
  <h1>Changer mon mot de passe</h1>
  {_champ("ancien", "Mot de passe actuel", type_="password", extra='required autocomplete="current-password"')}
  {_champ("nouveau", "Nouveau mot de passe", type_="password", extra='required autocomplete="new-password"')}
  {_champ("confirmation", "Confirmer", type_="password", extra='required autocomplete="new-password"')}
  <button type="submit">Enregistrer</button>
</form>""")


# ---------------------------------------------------------------------------
# Salariés : import en masse et paie du mois
# ---------------------------------------------------------------------------

def _options_mois(choisi: int) -> str:
    return "".join(f'<option value="{i}"{" selected" if i == choisi else ""}>{m.capitalize()}</option>'
                   for i, m in enumerate(MOIS, start=1))


def _nb_elements_variables(variables: dict) -> int:
    """Nombre d'éléments variables non nuls (heures sup., indemnités, absences, retenues)."""
    nombre = 0
    for valeur in variables.values():
        if isinstance(valeur, dict):
            for v in valeur.values():
                montant = v.get("montant") if isinstance(v, dict) else v
                nombre += bool(dec(montant))
        else:
            nombre += bool(dec(valeur))
    return nombre


def page_salaries(erreur: str = "", succes: str = "", details: list | None = None) -> str:
    salaries = registre.charger()
    auj = date.today()
    masse = sum((dec(s.get("salaire_base")) for s in salaries), dec(0))
    lignes = []
    for s in salaries:
        nb_var = _nb_elements_variables(s.get("variables", {}))
        lignes.append(
            f"<tr><td>{escape(s.get('matricule', ''))}</td><td>{escape(s.get('nom', ''))}</td>"
            f"<td>{escape(s.get('fonction', ''))}</td><td>{escape(str(s.get('salaire_base', '')))}</td>"
            f"<td>{escape(s.get('date_embauche', ''))}</td><td>{escape(str(s.get('personnes_a_charge', '') or 0))}</td>"
            f"<td>{nb_var}</td>"
            f'<td><form method="post" action="/salaries/supprimer" style="margin:0;padding:0;border:none">'
            f'<input type="hidden" name="matricule" value="{escape(s.get("matricule", ""))}">'
            f'<button class="lien-btn" type="submit">Retirer</button></form></td></tr>')
    tableau = (
        '<div class="wrap"><table class="ref"><thead><tr><th>Matricule</th><th>Nom</th><th>Fonction</th>'
        '<th>Salaire de base</th><th>Embauche</th><th>Pers. à charge</th><th>Éléments variables</th><th></th>'
        f'</tr></thead><tbody>{"".join(lignes)}</tbody></table></div>'
        if salaries else '<p class="sous">Aucun salarié pour le moment : importez un fichier ci-dessus.</p>')
    paie = f"""
<form method="post" action="/paie" class="large">
  <h2 style="margin-top:0">Calculer la paie du mois</h2>
  <p class="sous">Génère les bulletins de tous les salariés du registre et le journal de paie.</p>
  <div class="ligne-actions">
    <label>Mois<select name="mois">{_options_mois(auj.month)}</select></label>
    {_num("annee", "Année", auj.year)}
    <button type="submit">Calculer {len(salaries)} bulletin(s)</button>
  </div>
</form>""" if salaries else ""
    return _page("Salariés", f"""{_messages(erreur, succes, details)}
<form method="post" action="/salaries/import" enctype="multipart/form-data" class="large">
  <h1>Import des salariés</h1>
  <p class="sous">Fichier Excel (.xlsx) ou CSV : une ligne par salarié. Colonnes obligatoires :
     <b>nom</b>, <b>salaire_base</b>, <b>date_embauche</b>. Les colonnes d'indemnités (ex. <code>transport</code>,
     <code>prime_13e_mois</code>) et d'absences (ex. <code>maladie</code>, <code>conge_annuel</code>)
     reprennent les codes du <a href="/referentiel">référentiel</a>.</p>
  <div class="ligne-actions">
    <label style="flex:1;min-width:240px">Fichier<input type="file" name="fichier" accept=".xlsx,.xlsm,.csv,.txt" required></label>
    <label>Mode<select name="mode"><option value="fusionner">Ajouter / mettre à jour (par matricule)</option>
      <option value="remplacer">Remplacer tout le registre</option></select></label>
    <button type="submit">Importer</button>
    <a class="bouton" href="/modele.csv">Télécharger le modèle</a>
  </div>
</form>
{paie}
<div class="carte large">
  <h2 style="margin-top:0">Registre des salariés</h2>
  <div class="stats"><div>Salariés<b>{len(salaries)}</b></div>
    <div>Masse salariale de base<b>{dh(masse)} DH</b></div></div>
  {tableau}
  {'<div class="ligne-actions"><form method="post" action="/salaries/vider" onsubmit="return confirm(' + "'Vider tout le registre ?'" + ')"><button class="bouton danger" type="submit">Vider le registre</button></form></div>' if salaries else ''}
</div>""")


def calculer_registre(annee: int, mois: int):
    bulletins, erreurs = [], []
    for s in registre.charger():
        try:
            variables = variables_depuis_dict({"annee": annee, "mois": mois, **s.get("variables", {})})
            bulletins.append(calculer_bulletin(salarie_depuis_dict(s), variables))
        except (KeyError, ValueError, ArithmeticError, TypeError) as exc:
            erreurs.append(f"{s.get('matricule')} {s.get('nom')} : {exc}")
    return bulletins, erreurs


def page_paie(annee: int, mois: int) -> str:
    bulletins, erreurs = calculer_registre(annee, mois)
    total = lambda attr: sum((getattr(b, attr) for b in bulletins), 0)
    lignes = "".join(
        f"<tr><td>{escape(b.salarie.matricule)}</td><td>{escape(b.salarie.nom)}</td><td>{dh(b.salaire_brut)}</td>"
        f"<td>{dh(b.cnss + b.amo)}</td><td>{dh(b.ir)}</td><td>{dh(b.net_a_payer)}</td><td>{dh(b.cout_employeur)}</td></tr>"
        for b in bulletins)
    resume = f"""
<div class="carte large no-print">
  <h1>Paie de {MOIS[mois - 1]} {annee}</h1>
  <div class="stats">
    <div>Bulletins<b>{len(bulletins)}</b></div>
    <div>Masse salariale brute<b>{dh(total("salaire_brut"))}</b></div>
    <div>CNSS + AMO salariés<b>{dh(total("cnss") + total("amo"))}</b></div>
    <div>IR retenu<b>{dh(total("ir"))}</b></div>
    <div>Net à payer<b>{dh(total("net_a_payer"))}</b></div>
    <div>Coût employeur<b>{dh(total("cout_employeur"))}</b></div>
  </div>
  <div class="wrap"><table class="journal"><thead><tr><th>Matricule</th><th>Nom</th><th>Brut</th><th>CNSS + AMO</th><th>IR</th>
    <th>Net à payer</th><th>Coût employeur</th></tr></thead><tbody>{lignes}</tbody></table></div>
  <div class="ligne-actions">
    <button class="bouton" onclick="window.print()">Imprimer tous les bulletins / PDF</button>
    <a class="bouton" href="/journal.csv?annee={annee}&mois={mois}">Télécharger le journal (CSV / Excel)</a>
    <a class="bouton" href="/salaries">Retour aux salariés</a>
  </div>
</div>"""
    return _page(f"Paie {mois:02d}/{annee}", _messages(
        "Certains bulletins n'ont pas pu être calculés :" if erreurs else "", details=erreurs)
        + resume + "".join(bulletin_html(b) for b in bulletins))


# ---------------------------------------------------------------------------
# Serveur
# ---------------------------------------------------------------------------

TAILLE_MAX_FICHIER = 10 * 1024 * 1024
PAGES_PUBLIQUES = {"/connexion", "/installation"}


def _multipart(type_contenu: str, corps: bytes) -> dict:
    message = BytesParser(policy=politique_email).parsebytes(
        b"Content-Type: " + type_contenu.encode("latin-1") + b"\r\n\r\n" + corps)
    champs = {}
    for partie in message.iter_parts():
        nom = partie.get_param("name", header="content-disposition")
        if nom:
            champs[nom] = (partie.get_filename(), partie.get_payload(decode=True) or b"")
    return champs


class Gestionnaire(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # pas de journal console à chaque requête
        pass

    # --- Réponses ---
    def _envoyer(self, contenu, code: int = 200, type_contenu="text/html; charset=utf-8",
                 entetes: dict | None = None):
        donnees = contenu.encode("utf-8") if isinstance(contenu, str) else contenu
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(donnees)))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for cle, valeur in (entetes or {}).items():
            self.send_header(cle, valeur)
        self.end_headers()
        self.wfile.write(donnees)

    def _rediriger(self, url: str, cookie: str | None = None):
        self.send_response(303)
        self.send_header("Location", url)
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _fichier(self, nom: str, contenu: str, type_contenu: str):
        self._envoyer(contenu.encode("utf-8-sig"), type_contenu=type_contenu,
                      entetes={"Content-Disposition": f'attachment; filename="{nom}"'})

    # --- Session ---
    def _jeton(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie") or "")
        return cookie["session"].value if "session" in cookie else None

    def _preparer(self) -> bool:
        """Vérifie l'accès ; retourne False si une redirection a été envoyée."""
        url = urlparse(self.path)
        self.chemin, self.requete = url.path, parse_qs(url.query)
        utilisateur = auth.session(self._jeton())
        _utilisateur.set(utilisateur)
        _chemin.set(self.chemin)
        if auth.aucun_utilisateur() and self.chemin != "/installation":
            self._rediriger("/installation")
            return False
        if utilisateur is None and self.chemin not in PAGES_PUBLIQUES:
            self._rediriger("/connexion")
            return False
        if self.chemin == "/utilisateurs" or self.chemin.startswith("/utilisateurs/"):
            if not auth.est_admin(utilisateur):
                self._envoyer(_page("Accès refusé", '<div class="erreur">Réservé aux administrateurs.</div>'), 403)
                return False
        return True

    def _ouvrir_session(self, identifiant: str):
        jeton = auth.ouvrir_session(identifiant)
        self._rediriger("/salaries", f"session={jeton}; HttpOnly; SameSite=Strict; Path=/")

    # --- GET ---
    def do_GET(self):
        if not self._preparer():
            return
        pages = {
            "/": formulaire_paie,
            "/conges": formulaire_conges,
            "/referentiel": page_referentiel,
            "/salaries": page_salaries,
            "/utilisateurs": page_utilisateurs,
            "/mot-de-passe": page_mot_de_passe,
            "/connexion": page_connexion,
            "/installation": page_installation,
        }
        if self.chemin == "/installation" and not auth.aucun_utilisateur():
            return self._rediriger("/connexion")
        if self.chemin in ("/connexion",) and _utilisateur.get():
            return self._rediriger("/salaries")
        if self.chemin in pages:
            return self._envoyer(pages[self.chemin]())
        from . import web_facturation
        if self.chemin.startswith(web_facturation.PREFIXES):
            return web_facturation.get(self)
        if self.chemin == "/modele.csv":
            return self._fichier("modele_salaries.csv", modele_csv(), "text/csv; charset=utf-8")
        if self.chemin == "/journal.csv":
            try:
                annee, mois = int(self.requete["annee"][0]), int(self.requete["mois"][0])
            except (KeyError, ValueError):
                return self._envoyer(_page("Erreur", _messages("Période invalide.")), 400)
            bulletins, _ = calculer_registre(annee, mois)
            return self._fichier(f"journal_paie_{annee}_{mois:02d}.csv", journal_csv(bulletins),
                                 "text/csv; charset=utf-8")
        self._envoyer(_page("Introuvable", _messages("Page introuvable.")), 404)

    # --- POST ---
    def do_POST(self):
        if not self._preparer():
            return
        longueur = int(self.headers.get("Content-Length") or 0)
        if longueur > TAILLE_MAX_FICHIER:
            return self._envoyer(page_salaries("Fichier trop volumineux (10 Mo maximum)."), 413)
        corps = self.rfile.read(longueur)
        type_contenu = self.headers.get("Content-Type") or ""
        if type_contenu.startswith("multipart/form-data"):
            return self._post_import(_multipart(type_contenu, corps))
        from . import web_facturation
        if self.chemin.startswith(web_facturation.PREFIXES):
            return web_facturation.post(self, corps)
        f = _valeurs(corps)
        try:
            self._post(f)
        except (KeyError, ValueError, ArithmeticError) as exc:
            message = f"Données invalides : {exc}"
            page = formulaire_conges(erreur=message) if self.chemin == "/conges" else formulaire_paie(message)
            self._envoyer(page, 400)

    def _post(self, f: dict):
        chemin = self.chemin
        if chemin == "/installation":
            if not auth.aucun_utilisateur():
                return self._rediriger("/connexion")
            if f.get("mot_de_passe") != f.get("confirmation"):
                return self._envoyer(page_installation("Les mots de passe ne correspondent pas."), 400)
            try:
                auth.creer_utilisateur(f.get("identifiant", ""), f.get("mot_de_passe", ""), admin=True)
            except ValueError as exc:
                return self._envoyer(page_installation(str(exc)), 400)
            return self._ouvrir_session(f["identifiant"].strip())
        if chemin == "/connexion":
            identifiant = f.get("identifiant", "").strip()
            if auth.verifier(identifiant, f.get("mot_de_passe", "")):
                return self._ouvrir_session(identifiant)
            time.sleep(1)  # ralentit les tentatives répétées
            return self._envoyer(page_connexion("Identifiant ou mot de passe incorrect."), 401)
        if chemin == "/deconnexion":
            auth.fermer_session(self._jeton())
            return self._rediriger("/connexion", "session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
        if chemin == "/mot-de-passe":
            if f.get("nouveau") != f.get("confirmation"):
                return self._envoyer(page_mot_de_passe("Les mots de passe ne correspondent pas."), 400)
            try:
                auth.changer_mot_de_passe(_utilisateur.get(), f.get("ancien", ""), f.get("nouveau", ""))
            except ValueError as exc:
                return self._envoyer(page_mot_de_passe(str(exc)), 400)
            return self._ouvrir_session(_utilisateur.get())
        if chemin == "/utilisateurs/ajouter":
            try:
                auth.creer_utilisateur(f.get("identifiant", ""), f.get("mot_de_passe", ""), f.get("role") == "admin")
            except ValueError as exc:
                return self._envoyer(page_utilisateurs(str(exc)), 400)
            return self._envoyer(page_utilisateurs(succes=f"Utilisateur « {f['identifiant'].strip()} » ajouté."))
        if chemin == "/utilisateurs/supprimer":
            if f.get("identifiant") == _utilisateur.get():
                return self._envoyer(page_utilisateurs("Vous ne pouvez pas supprimer votre propre compte."), 400)
            try:
                auth.supprimer_utilisateur(f.get("identifiant", ""))
            except ValueError as exc:
                return self._envoyer(page_utilisateurs(str(exc)), 400)
            return self._envoyer(page_utilisateurs(succes="Utilisateur supprimé."))
        if chemin == "/salaries/supprimer":
            registre.supprimer(f.get("matricule", ""))
            return self._rediriger("/salaries")
        if chemin == "/salaries/vider":
            registre.vider()
            return self._rediriger("/salaries")
        if chemin == "/paie":
            annee, mois = int(f.get("annee") or date.today().year), int(f.get("mois") or date.today().month)
            if not 1 <= mois <= 12:
                raise ValueError("mois invalide")
            return self._envoyer(page_paie(annee, mois))
        if chemin == "/bulletin":
            return self._envoyer(page_html([calcul_depuis_formulaire(f)], retour="/"))
        if chemin == "/conges":
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
            return self._envoyer(formulaire_conges(res))
        self._envoyer(_page("Introuvable", _messages("Page introuvable.")), 404)

    def _post_import(self, champs: dict):
        if self.chemin != "/salaries/import":
            return self._envoyer(_page("Introuvable", _messages("Page introuvable.")), 404)
        nom_fichier, contenu = champs.get("fichier", (None, b""))
        if not nom_fichier or not contenu:
            return self._envoyer(page_salaries("Aucun fichier sélectionné."), 400)
        mode = (champs.get("mode", (None, b"fusionner"))[1] or b"").decode()
        try:
            salaries, erreurs, ignorees = analyser(lire_fichier(nom_fichier, contenu))
        except (ValueError, KeyError, IndexError, ElementTreeError) as exc:
            return self._envoyer(page_salaries(f"Import impossible : {exc}"), 400)
        details = list(erreurs)
        if ignorees:
            details.append("Colonnes ignorées (non reconnues) : " + ", ".join(ignorees))
        if not salaries:
            return self._envoyer(page_salaries("Aucun salarié valide dans le fichier.", details=details), 400)
        ajoutes, maj = registre.enregistrer(salaries, remplacer=(mode == "remplacer"))
        message = f"{len(salaries)} salarié(s) importé(s) : {ajoutes} ajouté(s), {maj} mis à jour."
        if erreurs:
            message += f" {len(erreurs)} ligne(s) rejetée(s)."
        self._envoyer(page_salaries(succes=message, details=details))


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
