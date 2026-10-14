"""Interface web locale de Facturation Maroc (bibliothèque standard uniquement).

Lancement : python -m facturation_maroc   puis ouvrir http://localhost:8080
"""

from __future__ import annotations

import contextvars
import time
from datetime import date
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from . import auth
from . import factures as fa
from .factures import dh

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]

CSS = """
:root { --encre:#1d2433; --gris:#5b6475; --trait:#d5dae3; --fond:#f5f7fa; --accent:#1f4e8c; }
* { box-sizing:border-box; }
body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color:var(--encre); background:var(--fond); margin:0; padding:24px 16px; }
h1 { font-size:20px; margin:0 0 4px; } .sous { color:var(--gris); margin:0 0 20px; }
table { width:100%; border-collapse:collapse; font-size:13.5px; margin-bottom:18px; }
th, td { padding:6px 8px; border-bottom:1px solid var(--trait); text-align:right; font-variant-numeric:tabular-nums; }
th:first-child, td:first-child { text-align:left; }
th { background:var(--fond); font-weight:600; font-size:12.5px; color:var(--gris); }
tr.total td { font-weight:600; background:#fafbfc; }
.wrap { overflow-x:auto; }
form, .carte { max-width:900px; margin:0 auto 24px; background:#fff; border:1px solid var(--trait); border-radius:8px; padding:24px; }
.grille { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px 16px; }
label { display:flex; flex-direction:column; font-size:13px; color:var(--gris); gap:4px; }
input { font:inherit; color:var(--encre); padding:7px 9px; border:1px solid var(--trait); border-radius:5px; min-width:0; }
select { font:inherit; padding:7px 9px; border:1px solid var(--trait); border-radius:5px; background:#fff; color:var(--encre); }
button[type=submit] { font:inherit; font-weight:600; background:var(--accent); color:#fff; border:none; padding:10px 20px; border-radius:6px; cursor:pointer; }
details { border:1px solid var(--trait); border-radius:6px; margin:0 0 12px; padding:10px 16px; }
summary { font-weight:600; cursor:pointer; }
.ref td, .ref th { text-align:left; vertical-align:top; }
.barre { background:var(--encre); color:#fff; margin:-24px -16px 24px; padding:0 16px; }
.barre-int { max-width:1100px; margin:0 auto; display:flex; align-items:center; gap:20px; flex-wrap:wrap; min-height:56px; }
.marque { font-weight:700; font-size:16px; letter-spacing:.2px; white-space:nowrap; }
.marque span { color:#8fb8f0; }
nav { display:flex; gap:4px; flex-wrap:wrap; flex:1; }
nav a { color:#cfd5e1; text-decoration:none; padding:8px 12px; border-radius:6px; font-size:14px; }
nav a:hover { background:rgba(255,255,255,.08); color:#fff; }
nav a.actif { background:rgba(255,255,255,.14); color:#fff; }
.compte { display:flex; align-items:center; gap:10px; font-size:13px; color:#cfd5e1; }
.compte form { margin:0; padding:0; border:none; background:none; }
.compte button { font:inherit; background:transparent; color:#fff; border:1px solid rgba(255,255,255,.35); border-radius:6px; padding:5px 10px; cursor:pointer; }
.large { max-width:1100px; }
.ok { max-width:900px; margin:0 auto 16px; background:#e8f6ef; border:1px solid #9fd5bb; padding:10px 14px; border-radius:6px; }
.erreur { max-width:900px; margin:0 auto 16px; background:#fdecec; border:1px solid #e9a3a3; padding:10px 14px; border-radius:6px; }
.ok ul, .erreur ul { margin:6px 0 0; padding-left:20px; }
.bouton { display:inline-block; font:inherit; font-size:14px; padding:9px 16px; border-radius:6px; border:1px solid var(--trait); background:#fff; color:var(--encre); text-decoration:none; cursor:pointer; }
button[type=submit].bouton { font-weight:400; background:#fff; color:var(--encre); border:1px solid var(--trait); padding:9px 16px; }
button[type=submit].bouton.danger { color:#a12a2a; border-color:#e9a3a3; }
button[type=submit].lien-btn { background:none; border:none; color:#a12a2a; cursor:pointer; font:inherit; font-size:13px; font-weight:400; padding:0; }
.ligne-actions { display:flex; gap:10px; flex-wrap:wrap; align-items:end; margin-top:12px; }
.ligne-actions form { margin:0; padding:0; border:none; background:none; }
.connexion { max-width:400px; margin:8vh auto 0; }
.connexion h1 { margin-top:0; } .connexion label { margin-bottom:12px; } .connexion button[type=submit] { width:100%; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:0 0 16px; }
.stats div { border:1px solid var(--trait); border-radius:6px; padding:10px 12px; font-size:13px; }
.stats b { display:block; font-size:18px; margin-top:2px; }
@page { margin:15mm; }
@media print { body { background:#fff; padding:0; } .barre, .no-print, .erreur, .ok { display:none !important; } }
"""


def _champ(nom, libelle, valeur="", type_="text", extra=""):
    return (f'<label>{escape(libelle)}<input name="{nom}" type="{type_}" '
            f'value="{escape(str(valeur))}" {extra}></label>')


def _num(nom, libelle, valeur="", aide=""):
    aide_html = f'<span class="aide">{escape(aide)}</span>' if aide else ""
    return (f'<label>{escape(libelle)}{aide_html}<input name="{nom}" type="text" inputmode="decimal" '
            f'value="{escape(str(valeur))}"></label>')


# Utilisateur connecté pour la requête en cours (affiché dans la barre de navigation).
_utilisateur = contextvars.ContextVar("utilisateur", default=None)
_chemin = contextvars.ContextVar("chemin", default="/")

LIENS = [("/factures", "Factures"), ("/factures/nouvelle", "Nouvelle facture"),
         ("/factures/generer", "Facturation en série"), ("/clients", "Clients"), ("/entreprise", "Entreprise")]


def _barre() -> str:
    marque = '<div class="marque">Facturation <span>Maroc</span></div>'
    utilisateur = _utilisateur.get()
    if not utilisateur:
        return f'<header class="barre"><div class="barre-int">{marque}</div></header>'
    liens = LIENS + ([("/utilisateurs", "Utilisateurs")] if auth.est_admin(utilisateur) else [])
    chemin = _chemin.get()
    nav = "".join(f'<a href="{url}"{" class=actif" if chemin == url else ""}>{escape(nom)}</a>'
                  for url, nom in liens)
    return (f'<header class="barre"><div class="barre-int">{marque}'
            f'<nav>{nav}</nav><div class="compte"><a href="/mot-de-passe" style="color:#cfd5e1">{escape(utilisateur)}</a>'
            f'<form method="post" action="/deconnexion"><button type="submit">Déconnexion</button></form>'
            f'</div></div></header>')


def _page(titre, corps):
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(titre)}</title><style>{CSS}{FACT_CSS}</style></head><body>'
            f'{_barre()}{corps}</body></html>')


def _messages(erreur: str = "", succes: str = "", details: list | None = None) -> str:
    liste = "<ul>" + "".join(f"<li>{escape(d)}</li>" for d in details) + "</ul>" if details else ""
    if erreur:
        return f'<div class="erreur">{escape(erreur)}{liste}</div>'
    if succes:
        return f'<div class="ok">{escape(succes)}{liste}</div>'
    return ""


NB_LIGNES = 10  # lignes de saisie sur une facture
NB_LIGNES_RECURRENTES = 6

FACT_CSS = """
.facture { max-width:900px; margin:0 auto 32px; background:#fff; border:1px solid var(--trait); border-radius:8px; padding:32px; position:relative; font-size:14px; }
.f-haut { display:flex; justify-content:space-between; gap:24px; flex-wrap:wrap; margin-bottom:24px; }
.f-emetteur b { font-size:18px; display:block; margin-bottom:4px; }
.f-titre { text-align:right; } .f-titre h1 { font-size:26px; letter-spacing:1px; margin:0 0 6px; color:var(--accent); }
.f-client { border:1px solid var(--trait); border-radius:6px; padding:12px 16px; margin:0 0 20px auto; max-width:380px; }
.f-client span, .f-emetteur span { color:var(--gris); }
.f-totaux { margin-left:auto; max-width:360px; }
.f-totaux td:first-child { color:var(--gris); }
.f-lettres { font-style:italic; margin:8px 0 18px; }
.f-pied { border-top:1px solid var(--trait); margin-top:28px; padding-top:10px; font-size:11.5px; color:var(--gris); text-align:center; }
.f-annulee { position:absolute; top:40%; left:0; right:0; text-align:center; font-size:72px; font-weight:800; color:rgba(161,42,42,.18); transform:rotate(-18deg); pointer-events:none; }
.etiquette { display:inline-block; padding:2px 8px; border-radius:10px; font-size:12px; white-space:nowrap; background:#eef1f5; }
.etiquette.payee { background:#e8f6ef; color:#0b6e4f; } .etiquette.retard { background:#fdecec; color:#a12a2a; }
.etiquette.partielle { background:#fff6e0; color:#8a5a00; } .etiquette.annulee { background:#eee; color:#777; text-decoration:line-through; }
.lignes-saisie td { padding:3px 4px; } .lignes-saisie input, .lignes-saisie select { width:100%; }
.lignes-saisie td:first-child { width:46%; } .lignes-saisie select { min-width:78px; }
.lignes-saisie .total-ligne { min-width:90px; white-space:nowrap; }
.liste-f th, .liste-f td { white-space:nowrap; } .liste-f .txt { text-align:left; white-space:normal; }
textarea { font:inherit; color:var(--encre); padding:7px 9px; border:1px solid var(--trait); border-radius:5px; min-height:60px; resize:vertical; }
.historique-f { font-size:13px; } .historique-f td, .historique-f th { text-align:left; }
a.num { font-weight:600; color:var(--accent); text-decoration:none; }
@media print { .facture { border:none; padding:0; } }
"""

CLASSES_STATUT = {"Payée": "payee", "En retard": "retard", "Partiellement payée": "partielle", "Annulée": "annulee"}


def _etiquette(f: dict) -> str:
    s = fa.statut(f)
    return f'<span class="etiquette {CLASSES_STATUT.get(s, "")}">{escape(s)}</span>'


def _jour(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else ""


def _zone(nom: str, libelle: str, valeur: str = "") -> str:
    return f'<label>{escape(libelle)}<textarea name="{nom}">{escape(valeur)}</textarea></label>'


def _select(nom: str, libelle: str, options: list[tuple[str, str]], choisi: str = "", extra: str = "") -> str:
    opts = "".join(f'<option value="{escape(v)}"{" selected" if v == choisi else ""}>{escape(t)}</option>'
                   for v, t in options)
    return f'<label>{escape(libelle)}<select name="{nom}" {extra}>{opts}</select></label>'


def _lien_facture(numero: str) -> str:
    return f'<a class="num" href="/factures/voir?numero={quote(numero)}">{escape(numero)}</a>'


def _options_tva(choisi: str = "20") -> str:
    return "".join(f'<option value="{t}"{" selected" if str(t) == str(choisi) else ""}>{t} %</option>'
                   for t in fa.TAUX_TVA)


def _lignes_saisie(lignes: list[dict], nombre: int, prefixe: str = "") -> str:
    lignes = list(lignes) + [{}] * max(0, nombre - len(lignes))
    rangs = []
    for i, l in enumerate(lignes, start=1):
        rangs.append(
            f'<tr><td><input name="{prefixe}designation_{i}" value="{escape(l.get("designation", ""))}"></td>'
            f'<td><input name="{prefixe}quantite_{i}" inputmode="decimal" value="{escape(str(l.get("quantite", "")))}"></td>'
            f'<td><input name="{prefixe}prix_{i}" inputmode="decimal" value="{escape(str(l.get("prix_unitaire", "")))}"></td>'
            f'<td><select name="{prefixe}tva_{i}">{_options_tva(l.get("tva", "20"))}</select></td>'
            f'<td class="total-ligne"></td></tr>')
    return ('<div class="wrap"><table class="lignes-saisie"><thead><tr><th>Désignation</th><th>Quantité</th>'
            '<th>Prix unitaire HT</th><th>TVA</th><th>Total HT</th></tr></thead>'
            f'<tbody>{"".join(rangs)}</tbody></table></div>')


def lignes_du_formulaire(f: dict, prefixe: str = "") -> list[dict]:
    i, lignes = 1, []
    while f"{prefixe}designation_{i}" in f:
        lignes.append({"designation": f.get(f"{prefixe}designation_{i}", ""),
                       "quantite": f.get(f"{prefixe}quantite_{i}", ""),
                       "prix_unitaire": f.get(f"{prefixe}prix_{i}", ""),
                       "tva": f.get(f"{prefixe}tva_{i}", "20")})
        i += 1
    return lignes


# Calcul des totaux en direct pendant la saisie (indicatif ; le serveur recalcule).
SCRIPT_TOTAUX = """<script>
(function(){
  var t = document.querySelector('.lignes-saisie'); if (!t) return;
  var n = function(v){ v = (v||'').replace(/\\s/g,'').replace(',','.'); return isFinite(v) && v !== '' ? parseFloat(v) : 0; };
  var f = function(x){ return x.toLocaleString('fr-FR',{minimumFractionDigits:2, maximumFractionDigits:2}); };
  function maj(){
    var ht = 0, tva = 0;
    t.querySelectorAll('tbody tr').forEach(function(r){
      var c = r.querySelectorAll('input,select');
      var q = c[1].value.trim() === '' && c[2].value.trim() !== '' ? 1 : n(c[1].value);
      var l = Math.round(q * n(c[2].value) * 100) / 100;
      r.querySelector('.total-ligne').textContent = l ? f(l) : '';
      ht += l; tva += l * n(c[3].value) / 100;
    });
    var s = document.getElementById('totaux-direct');
    if (s) s.textContent = 'Total HT ' + f(ht) + ' · TVA ' + f(tva) + ' · TTC ' + f(ht + tva) + ' DH';
  }
  t.addEventListener('input', maj); t.addEventListener('change', maj); maj();
})();
</script>"""


# ---------------------------------------------------------------------------
# Entreprise
# ---------------------------------------------------------------------------

LIBELLES_ENTREPRISE = {
    "raison_sociale": "Raison sociale *", "forme_juridique": "Forme juridique (SARL, SA…)",
    "capital": "Capital social (DH)", "adresse": "Adresse", "ville": "Ville", "telephone": "Téléphone",
    "email": "E-mail", "ice": "ICE", "if_fiscal": "Identifiant fiscal (IF)", "rc": "Registre du commerce (RC)",
    "patente": "Taxe professionnelle (patente)", "cnss": "N° CNSS", "banque": "Banque", "rib": "RIB (24 chiffres)",
}


def page_entreprise(erreur: str = "", succes: str = "", valeurs: dict | None = None) -> str:
    e = valeurs if valeurs is not None else fa.entreprise()
    champs = "".join(_champ(k, l, e.get(k, ""), extra="required" if k == "raison_sociale" else "")
                     for k, l in LIBELLES_ENTREPRISE.items())
    return _page("Entreprise", f"""{_messages(erreur, succes)}
<form method="post" action="/entreprise">
  <h1>Informations de l'entreprise</h1>
  <p class="sous">Elles figurent sur chaque facture (mentions obligatoires : raison sociale, adresse, ICE, IF, RC,
     patente). Une facture déjà émise conserve les informations en vigueur à sa date d'émission.</p>
  <div class="grille">{champs}</div>
  <div class="grille" style="margin-top:10px">{_zone("mentions", "Mentions en bas de facture (conditions, pénalités de retard…)", e.get("mentions", ""))}</div>
  <p><button type="submit">Enregistrer</button></p>
</form>""")


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

LIBELLES_CLIENT = {"nom": "Nom / raison sociale *", "ice": "ICE", "if_fiscal": "IF", "rc": "RC",
                   "adresse": "Adresse", "ville": "Ville", "telephone": "Téléphone", "email": "E-mail"}


def _champs_client(c: dict) -> str:
    champs = "".join(_champ(k, l, c.get(k, ""), extra="required" if k == "nom" else "")
                     for k, l in LIBELLES_CLIENT.items())
    verrou = "readonly title=\"Non modifiable : des factures ont été émises\"" if c.get("compteurs") else ""
    return (champs
            + _champ("prefixe", "Préfixe de la série (vide = automatique)", c.get("prefixe", ""),
                     extra=f'maxlength="10" pattern="[A-Za-z0-9]{{1,10}}" {verrou}')
            + _num("delai_paiement", "Délai de paiement (jours)", c.get("delai_paiement", 30)))


def page_clients(erreur: str = "", succes: str = "", valeurs: dict | None = None) -> str:
    annee = date.today().year
    toutes = fa.factures()
    lignes = []
    for c in sorted(fa.clients(), key=lambda c: (not c.get("actif", True), c["nom"].lower())):
        siennes = [f for f in toutes if f["client_code"] == c["code"]]
        s = fa.synthese(siennes)
        archive = "" if c.get("actif", True) else ' <span class="etiquette annulee">archivé</span>'
        lignes.append(
            f'<tr><td>{escape(c["code"])}</td><td class="txt"><a class="num" href="/clients/fiche?code={quote(c["code"])}">'
            f'{escape(c["nom"])}</a>{archive}</td><td class="txt">{escape(c.get("ice", ""))}</td>'
            f'<td>{escape(c["prefixe"])}</td><td>{escape(fa.prochain_numero(c, annee))}</td>'
            f'<td>{s["nombre"]}</td><td>{dh(s["ttc"])}</td><td>{dh(s["reste"])}</td>'
            f'<td><a class="bouton" style="padding:4px 10px" href="/factures/nouvelle?client={quote(c["code"])}">'
            f'Facturer</a></td></tr>')
    tableau = ('<div class="wrap"><table class="liste-f"><thead><tr><th>Code</th><th class="txt">Client</th><th class="txt">ICE</th>'
               f'<th>Série</th><th>Prochain n° ({annee})</th><th>Factures</th><th>Facturé TTC</th><th>Reste dû</th>'
               f'<th></th></tr></thead><tbody>{"".join(lignes)}</tbody></table></div>'
               if lignes else '<p class="sous">Aucun client : ajoutez votre premier client ci-dessous.</p>')
    return _page("Clients", f"""{_messages(erreur, succes)}
<div class="carte large">
  <h1>Clients</h1>
  <p class="sous">Chaque client a sa propre série de factures : <code>PRÉFIXE-ANNÉE-NUMÉRO</code>, numérotation
     continue qui repart à 0001 chaque année.</p>
  {tableau}
</div>
<form method="post" action="/clients/ajouter" class="large">
  <h2 style="margin-top:0">Nouveau client</h2>
  <div class="grille">{_champs_client(valeurs or {})}</div>
  <p><button type="submit">Ajouter le client</button></p>
</form>""")


def page_fiche_client(code: str, erreur: str = "", succes: str = "", valeurs: dict | None = None) -> str:
    c = fa.client(code)
    if c is None:
        return _page("Client", _messages("Client introuvable."))
    affiche = {**c, **(valeurs or {})}
    recurrentes = valeurs.get("lignes_recurrentes", c["lignes_recurrentes"]) if valeurs else c["lignes_recurrentes"]
    siennes = fa.rechercher(client_code=code)
    s = fa.synthese(siennes)
    series = "".join(f"<tr><td>{a}</td><td>{escape(fa.format_numero(c['prefixe'], int(a), 1))} → "
                     f"{escape(fa.format_numero(c['prefixe'], int(a), n))}</td><td>{n}</td></tr>"
                     for a, n in sorted(c["compteurs"].items(), reverse=True))
    historique = "".join(
        f"<tr><td>{_lien_facture(f['numero'])}</td><td>{_jour(f['date'])}</td><td class=\"txt\">{escape(f['objet'])}</td>"
        f"<td>{dh(fa.montant(f['total_ttc']))}</td><td>{dh(fa.reste_a_payer(f))}</td><td>{_etiquette(f)}</td></tr>"
        for f in siennes)
    coche = " checked" if affiche.get("actif", True) else ""
    return _page(c["nom"], f"""{_messages(erreur, succes)}
<div class="carte large">
  <h1>{escape(c["nom"])} <span class="sous" style="font-size:14px">({escape(c["code"])})</span></h1>
  <div class="stats">
    <div>Série<b>{escape(c["prefixe"])}</b></div>
    <div>Prochain numéro<b>{escape(fa.prochain_numero(c, date.today().year))}</b></div>
    <div>Factures<b>{s["nombre"]}</b></div>
    <div>Facturé TTC<b>{dh(s["ttc"])}</b></div>
    <div>Encaissé<b>{dh(s["encaisse"])}</b></div>
    <div>Reste dû<b>{dh(s["reste"])}</b></div>
  </div>
  <div class="ligne-actions" style="margin-bottom:16px">
    <a class="bouton" href="/factures/nouvelle?client={quote(code)}">Nouvelle facture</a>
    <a class="bouton" href="/factures.csv?client={quote(code)}">Exporter l'historique (CSV)</a>
  </div>
  <h2>Historique des factures</h2>
  {'<div class="wrap"><table class="liste-f"><thead><tr><th>Numéro</th><th>Date</th><th class="txt">Objet</th><th>TTC</th><th>Reste</th><th>Statut</th></tr></thead><tbody>' + historique + '</tbody></table></div>' if historique else '<p class="sous">Aucune facture émise pour ce client.</p>'}
  {'<h2>Séries utilisées</h2><div class="wrap"><table class="ref"><thead><tr><th>Année</th><th>Numéros</th><th>Nombre</th></tr></thead><tbody>' + series + '</tbody></table></div>' if series else ''}
</div>
<form method="post" action="/clients/modifier" class="large">
  <h2 style="margin-top:0">Fiche client</h2>
  <input type="hidden" name="code" value="{escape(code)}">
  <div class="grille">{_champs_client(affiche)}</div>
  <p><label style="flex-direction:row;align-items:center;gap:8px"><input type="checkbox" name="actif" value="1"{coche}>
     Client actif (décocher pour l'archiver : plus de nouvelles factures)</label></p>
  <h3>Lignes récurrentes</h3>
  <p class="sous">Prestations facturées régulièrement (abonnement, maintenance, loyer…). Elles pré-remplissent
     les nouvelles factures et servent à la <a href="/factures/generer">facturation en série</a>.</p>
  {_lignes_saisie(recurrentes, NB_LIGNES_RECURRENTES, "rec_")}
  <p><button type="submit">Enregistrer la fiche</button></p>
</form>
{'' if c["compteurs"] else f'''<div class="ligne-actions large" style="margin:0 auto 24px"><form method="post" action="/clients/supprimer" onsubmit="return confirm('Supprimer ce client ?')">
  <input type="hidden" name="code" value="{escape(code)}"><button class="bouton danger" type="submit">Supprimer le client</button></form></div>'''}
{SCRIPT_TOTAUX}""")


# ---------------------------------------------------------------------------
# Factures
# ---------------------------------------------------------------------------

def _options_clients(choisi: str = "", actifs: bool = True) -> list[tuple[str, str]]:
    annee = date.today().year
    return [(c["code"], f'{c["nom"]} — prochain n° {fa.prochain_numero(c, annee)}')
            for c in sorted(fa.clients(), key=lambda c: c["nom"].lower())
            if c.get("actif", True) or not actifs or c["code"] == choisi]


def page_nouvelle(valeurs: dict | None = None, erreur: str = "", client: str = "", depuis: str = "") -> str:
    v = dict(valeurs or {})
    lignes = lignes_du_formulaire(v) if valeurs else []
    if not valeurs:
        modele = fa.facture(depuis) if depuis else None
        fiche = fa.client(client) if client else None
        if modele:
            v.update(client=modele["client_code"], objet=modele["objet"], notes=modele["notes"])
            lignes = modele["lignes"]
        elif fiche:
            v["client"] = fiche["code"]
            lignes = fiche["lignes_recurrentes"]
    options = _options_clients(v.get("client", ""))
    if not options:
        return _page("Nouvelle facture", _messages("Ajoutez d'abord un client.")
                       + '<p style="text-align:center"><a class="bouton" href="/clients">Ajouter un client</a></p>')
    avert = "" if fa.entreprise().get("ice") else (
        '<div class="erreur">Les informations de votre entreprise (ICE, IF, RC…) ne sont pas complètes : '
        '<a href="/entreprise">compléter</a> avant d\'émettre des factures.</div>')
    return _page("Nouvelle facture", f"""{_messages(erreur)}{avert}
<form method="post" action="/factures/nouvelle" class="large">
  <h1>Nouvelle facture</h1>
  <p class="sous">Le numéro est attribué automatiquement dans la série du client au moment de l'émission.
     Une facture émise ne peut plus être modifiée (seulement payée ou annulée).</p>
  <div class="grille">
    {_select("client", "Client", [("", "— Choisir —")] + options, v.get("client", ""), "required")}
    {_champ("date", "Date de facture", v.get("date") or date.today().isoformat(), "date", "required")}
    {_champ("echeance", "Échéance (vide = selon délai du client)", v.get("echeance", ""), "date")}
    {_champ("objet", "Objet / référence (bon de commande…)", v.get("objet", ""))}
  </div>
  <h3>Lignes</h3>
  {_lignes_saisie(lignes, NB_LIGNES)}
  <p id="totaux-direct" class="sous" style="text-align:right;font-weight:600"></p>
  <div class="grille">{_zone("notes", "Notes (affichées sur la facture)", v.get("notes", ""))}</div>
  <p><button type="submit">Émettre la facture</button></p>
</form>
{SCRIPT_TOTAUX}""")


def facture_html(f: dict) -> str:
    e, c = f.get("emetteur") or {}, f["client"]
    lignes = "".join(
        f"<tr><td>{escape(l['designation'])}</td><td>{escape(str(l['quantite']).replace('.', ','))}</td>"
        f"<td>{dh(fa.montant(l['prix_unitaire']))}</td><td>{l['tva']} %</td>"
        f"<td>{dh(fa.arrondi(fa.montant(l['quantite']) * fa.montant(l['prix_unitaire'])))}</td></tr>"
        for l in f["lignes"])
    tva = "".join(f"<tr><td>TVA {t} % (base {dh(fa.montant(f['bases_tva'][t]))})</td><td>{dh(fa.montant(m))}</td></tr>"
                  for t, m in f["tva"].items())
    def ligne(libelle, valeur):
        return f"{libelle} : {escape(valeur)}" if valeur else ""
    identifiants = " · ".join(x for x in (ligne("ICE", e.get("ice")), ligne("IF", e.get("if_fiscal")),
                                          ligne("RC", e.get("rc")), ligne("Patente", e.get("patente")),
                                          ligne("CNSS", e.get("cnss"))) if x)
    societe = " ".join(x for x in (e.get("raison_sociale", ""), e.get("forme_juridique", ""),
                                   f"au capital de {e['capital']} DH" if e.get("capital") else "") if x)
    banque = (f"<p><b>Règlement :</b> {escape(e.get('banque', ''))} — RIB {escape(e['rib'])}</p>"
              if e.get("rib") else "")
    client_ids = "<br>".join(x for x in (ligne("ICE", c.get("ice")), ligne("IF", c.get("if_fiscal")),
                                         ligne("RC", c.get("rc"))) if x)
    paye = fa.total_paye(f)
    return f"""
<section class="facture">
  {'<div class="f-annulee">ANNULÉE</div>' if f["annulee"] else ''}
  <div class="f-haut">
    <div class="f-emetteur"><b>{escape(e.get("raison_sociale", "Votre entreprise"))}</b>
      {escape(e.get("adresse", ""))}<br>{escape(e.get("ville", ""))}<br>
      {'<span>Tél. </span>' + escape(e["telephone"]) + '<br>' if e.get("telephone") else ''}
      {escape(e.get("email", ""))}</div>
    <div class="f-titre"><h1>FACTURE</h1>
      <div><b>N° {escape(f["numero"])}</b></div>
      <div>Date : {_jour(f["date"])}</div>
      <div>Échéance : {_jour(f["echeance"])}</div></div>
  </div>
  <div class="f-client"><span>Facturé à</span><br><b>{escape(c["nom"])}</b><br>
    {escape(c.get("adresse", ""))}{'<br>' + escape(c["ville"]) if c.get("ville") else ''}
    {'<br>' + client_ids if client_ids else ''}</div>
  {f'<p><b>Objet :</b> {escape(f["objet"])}</p>' if f["objet"] else ''}
  <div class="wrap"><table>
    <thead><tr><th>Désignation</th><th>Qté</th><th>Prix unitaire HT</th><th>TVA</th><th>Total HT</th></tr></thead>
    <tbody>{lignes}</tbody></table></div>
  <table class="f-totaux"><tbody>
    <tr><td>Total HT</td><td>{dh(fa.montant(f["total_ht"]))}</td></tr>
    {tva}
    <tr class="total"><td>Total TTC (DH)</td><td>{dh(fa.montant(f["total_ttc"]))}</td></tr>
    {f'<tr><td>Déjà réglé</td><td>{dh(paye)}</td></tr><tr class="total"><td>Reste à payer</td><td>{dh(fa.reste_a_payer(f))}</td></tr>' if paye else ''}
  </tbody></table>
  <p class="f-lettres">Arrêtée la présente facture à la somme de : <b>{escape(fa.montant_en_lettres(f["total_ttc"]))}</b> TTC.</p>
  {banque}
  {f'<p>{escape(f["notes"])}</p>' if f["notes"] else ''}
  {f'<p class="sous">{escape(e["mentions"])}</p>' if e.get("mentions") else ''}
  <div class="f-pied">{escape(societe)}<br>{identifiants}</div>
</section>"""


def page_facture(numero: str, erreur: str = "", succes: str = "") -> str:
    f = fa.facture(numero)
    if f is None:
        return _page("Facture", _messages("Facture introuvable."))
    paiements = "".join(f"<tr><td>{_jour(p['date'])}</td><td>{escape(p['mode'])}</td><td>{escape(p['reference'])}</td>"
                        f"<td>{dh(fa.montant(p['montant']))}</td></tr>" for p in f["paiements"])
    evenements = "".join(f"<tr><td>{escape(h['date'].replace('T', ' '))}</td><td>{escape(h['utilisateur'])}</td>"
                         f"<td>{escape(h['action'])}</td></tr>" for h in reversed(f["historique"]))
    reste = fa.reste_a_payer(f)
    actions_paiement = "" if f["annulee"] or reste <= 0 else f"""
  <form method="post" action="/factures/paiement" style="padding:16px;margin:12px 0 0">
    <input type="hidden" name="numero" value="{escape(numero)}">
    <h3 style="margin-top:0">Enregistrer un paiement</h3>
    <div class="grille">
      {_num("montant", "Montant (DH)", str(reste))}
      {_champ("date", "Date", date.today().isoformat(), "date")}
      {_select("mode", "Mode", [(m, m) for m in fa.MODES_PAIEMENT])}
      {_champ("reference", "Référence (n° chèque, virement…)")}
    </div>
    <p><button type="submit">Enregistrer le paiement</button></p>
  </form>"""
    annulation = "" if f["annulee"] or f["paiements"] else f"""
  <details style="margin-top:12px"><summary>Annuler la facture</summary>
    <form method="post" action="/factures/annuler" style="border:none;padding:12px 0 0;margin:0"
          onsubmit="return confirm('Annuler définitivement cette facture ? Le numéro ne sera pas réutilisé.')">
      <input type="hidden" name="numero" value="{escape(numero)}">
      {_champ("motif", "Motif de l'annulation", extra="required")}
      <p><button class="bouton danger" type="submit">Annuler la facture</button></p>
    </form></details>"""
    panneau = f"""
<div class="carte no-print">
  <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
    <h2 style="margin:0">Facture {escape(numero)} {_etiquette(f)}</h2>
    <div class="ligne-actions" style="margin:0">
      <button class="bouton" onclick="window.print()">Imprimer / PDF</button>
      <a class="bouton" href="/factures/nouvelle?depuis={quote(numero)}">Dupliquer</a>
      <a class="bouton" href="/clients/fiche?code={quote(f['client_code'])}">Fiche client</a>
      <a class="bouton" href="/factures">Historique</a>
    </div>
  </div>
  {f'<p class="sous" style="margin-top:12px">Motif d’annulation : {escape(f["motif_annulation"])}</p>' if f["annulee"] else ''}
  {'<h3>Paiements reçus</h3><div class="wrap"><table class="ref"><thead><tr><th>Date</th><th>Mode</th><th>Référence</th><th>Montant</th></tr></thead><tbody>' + paiements + '</tbody></table></div>' if paiements else ''}
  {actions_paiement}{annulation}
  <h3>Historique</h3>
  <div class="wrap"><table class="historique-f"><thead><tr><th>Date</th><th>Utilisateur</th><th>Action</th></tr></thead>
  <tbody>{evenements}</tbody></table></div>
</div>"""
    return _page(f"Facture {numero}", _messages(erreur, succes) + panneau + facture_html(f))


def page_factures(requete: dict) -> str:
    filtre = {k: (requete.get(k) or [""])[0] for k in ("client", "annee", "statut", "q")}
    liste = fa.rechercher(filtre["client"], filtre["annee"], filtre["statut"], filtre["q"])
    s = fa.synthese(liste)
    annees = sorted({f["date"][:4] for f in fa.factures()}, reverse=True)
    lignes = "".join(
        f"<tr><td>{_lien_facture(f['numero'])}</td><td>{_jour(f['date'])}</td><td>{_jour(f['echeance'])}</td>"
        f"<td class=\"txt\">{escape(f['client']['nom'])}</td><td class=\"txt\">{escape(f['objet'])}</td><td>{dh(fa.montant(f['total_ht']))}</td>"
        f"<td>{dh(fa.montant(f['total_ttc']))}</td><td>{dh(fa.reste_a_payer(f))}</td><td>{_etiquette(f)}</td></tr>"
        for f in liste)
    requete_csv = "&".join(f"{k}={quote(v)}" for k, v in filtre.items() if v)
    tableau = ('<div class="wrap"><table class="liste-f"><thead><tr><th>Numéro</th><th>Date</th><th>Échéance</th>'
               '<th class="txt">Client</th><th class="txt">Objet</th><th>HT</th><th>TTC</th><th>Reste</th><th>Statut</th></tr></thead>'
               f'<tbody>{lignes}</tbody></table></div>' if lignes else
               '<p class="sous">Aucune facture ne correspond.</p>')
    return _page("Factures", f"""
<div class="carte large">
  <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
    <h1 style="margin:0">Historique des factures</h1>
    <div class="ligne-actions" style="margin:0">
      <a class="bouton" href="/factures/nouvelle" style="background:var(--accent);color:#fff;border-color:var(--accent)">Nouvelle facture</a>
      <a class="bouton" href="/factures/generer">Facturation en série</a>
      <a class="bouton" href="/factures.csv{'?' + requete_csv if requete_csv else ''}">Exporter (CSV / Excel)</a>
    </div>
  </div>
  <form method="get" action="/factures" style="border:none;padding:16px 0 0;margin:0;max-width:none">
    <div class="ligne-actions" style="margin:0 0 16px">
      {_select("client", "Client", [("", "Tous")] + [(c["code"], c["nom"]) for c in sorted(fa.clients(), key=lambda c: c["nom"].lower())], filtre["client"])}
      {_select("annee", "Année", [("", "Toutes")] + [(a, a) for a in annees], filtre["annee"])}
      {_select("statut", "Statut", [("", "Tous")] + [(x, x) for x in fa.STATUTS], filtre["statut"])}
      {_champ("q", "Recherche (n°, client, désignation)", filtre["q"])}
      <button type="submit">Filtrer</button>
    </div>
  </form>
  <div class="stats">
    <div>Factures<b>{s["nombre"]}</b></div>
    <div>Chiffre d'affaires HT<b>{dh(s["ht"])}</b></div>
    <div>Total TTC<b>{dh(s["ttc"])}</b></div>
    <div>Encaissé<b>{dh(s["encaisse"])}</b></div>
    <div>Reste à encaisser<b>{dh(s["reste"])}</b></div>
    <div>En retard<b>{s["en_retard"]}</b></div>
  </div>
  {tableau}
</div>""")


def page_generer(erreur: str = "", resultat: str = "") -> str:
    annee = date.today().year
    dernieres = {}
    for f in fa.factures():
        if not f["annulee"] and f["date"] > dernieres.get(f["client_code"], ""):
            dernieres[f["client_code"]] = f["date"]
    lignes = []
    for c in sorted(fa.clients(), key=lambda c: c["nom"].lower()):
        if not c.get("actif", True):
            continue
        rec = c["lignes_recurrentes"]
        if rec:
            ttc = fa.montant(fa.calculer_totaux(rec)["total_ttc"])
            case = f'<input type="checkbox" name="clients" value="{escape(c["code"])}" checked>'
        else:
            ttc, case = None, ""
        detail = escape(", ".join(l["designation"] for l in rec)) or "<i>aucune ligne récurrente</i>"
        lignes.append(f'<tr><td>{case}</td><td><a class="num" href="/clients/fiche?code={quote(c["code"])}">'
                      f'{escape(c["nom"])}</a></td><td>{escape(fa.prochain_numero(c, annee))}</td>'
                      f'<td>{detail}</td><td>{dh(ttc)}</td>'
                      f'<td>{_jour(dernieres.get(c["code"], ""))}</td></tr>')
    objet = f"Prestations {MOIS[date.today().month - 1]} {annee}"
    return _page("Facturation en série", f"""{_messages(erreur)}{resultat}
<form method="post" action="/factures/generer" class="large">
  <h1>Facturation en série</h1>
  <p class="sous">Émet en une fois une facture par client coché, à partir de ses lignes récurrentes
     (définies dans la fiche client). Chaque facture prend le numéro suivant de la série du client.</p>
  <div class="grille">
    {_champ("date", "Date des factures", date.today().isoformat(), "date", "required")}
    {_champ("objet", "Objet", objet)}
  </div>
  <div class="wrap" style="margin-top:16px"><table class="ref"><thead><tr><th></th><th>Client</th><th>Prochain n°</th>
    <th>Lignes récurrentes</th><th>TTC</th><th>Dernière facture</th></tr></thead><tbody>{"".join(lignes)}</tbody></table></div>
  <p><button type="submit" onclick="return confirm('Émettre les factures des clients cochés ?')">Générer les factures</button></p>
</form>""")


# ---------------------------------------------------------------------------
# Comptes utilisateurs
# ---------------------------------------------------------------------------

def page_connexion(erreur: str = "") -> str:
    return _page("Connexion", f"""
<form method="post" action="/connexion" class="connexion">
  <h1>Connexion</h1>
  <p class="sous">Facturation — séries de factures par client</p>
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


def page_mot_de_passe(erreur: str = "") -> str:
    return _page("Mot de passe", f"""{_messages(erreur)}
<form method="post" action="/mot-de-passe" class="connexion" style="margin-top:0">
  <h1>Changer mon mot de passe</h1>
  {_champ("ancien", "Mot de passe actuel", type_="password", extra='required autocomplete="current-password"')}
  {_champ("nouveau", "Nouveau mot de passe", type_="password", extra='required autocomplete="new-password"')}
  {_champ("confirmation", "Confirmer", type_="password", extra='required autocomplete="new-password"')}
  <button type="submit">Enregistrer</button>
</form>""")


# ---------------------------------------------------------------------------
# Serveur
# ---------------------------------------------------------------------------

TAILLE_MAX = 2 * 1024 * 1024
PAGES_PUBLIQUES = {"/connexion", "/installation"}
ACCUEIL = "/factures"


class Gestionnaire(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # pas de journal console à chaque requête
        pass

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

    def _introuvable(self):
        self._envoyer(_page("Introuvable", _messages("Page introuvable.")), 404)

    def _jeton(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie") or "")
        return cookie["session"].value if "session" in cookie else None

    def _preparer(self) -> bool:
        """Vérifie l'accès ; retourne False si une réponse a déjà été envoyée."""
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
        if self.chemin.startswith("/utilisateurs") and not auth.est_admin(utilisateur):
            self._envoyer(_page("Accès refusé", _messages("Réservé aux administrateurs.")), 403)
            return False
        return True

    def _ouvrir_session(self, identifiant: str):
        jeton = auth.ouvrir_session(identifiant)
        self._rediriger(ACCUEIL, f"session={jeton}; HttpOnly; SameSite=Strict; Path=/")

    # --- GET ---
    def do_GET(self):
        if not self._preparer():
            return
        q = lambda nom: (self.requete.get(nom) or [""])[0]
        chemin = self.chemin
        if chemin == "/installation" and not auth.aucun_utilisateur():
            return self._rediriger("/connexion")
        if chemin == "/connexion" and _utilisateur.get():
            return self._rediriger(ACCUEIL)
        pages = {
            "/connexion": page_connexion, "/installation": page_installation,
            "/utilisateurs": page_utilisateurs, "/mot-de-passe": page_mot_de_passe,
            "/factures/generer": page_generer, "/clients": page_clients, "/entreprise": page_entreprise,
        }
        if chemin == "/":
            return self._rediriger(ACCUEIL)
        if chemin in pages:
            return self._envoyer(pages[chemin]())
        if chemin == "/factures":
            return self._envoyer(page_factures(self.requete))
        if chemin == "/factures/nouvelle":
            return self._envoyer(page_nouvelle(client=q("client"), depuis=q("depuis")))
        if chemin == "/factures/voir":
            return self._envoyer(page_facture(q("numero")), 200 if fa.facture(q("numero")) else 404)
        if chemin == "/clients/fiche":
            return self._envoyer(page_fiche_client(q("code")), 200 if fa.client(q("code")) else 404)
        if chemin == "/factures.csv":
            liste = fa.rechercher(q("client"), q("annee"), q("statut"), q("q"))
            return self._fichier("factures.csv", fa.export_csv(liste), "text/csv; charset=utf-8")
        self._introuvable()

    # --- POST ---
    def do_POST(self):
        if not self._preparer():
            return
        longueur = int(self.headers.get("Content-Length") or 0)
        if longueur > TAILLE_MAX:
            return self._envoyer(_page("Erreur", _messages("Requête trop volumineuse.")), 413)
        valeurs = parse_qs(self.rfile.read(longueur).decode("utf-8"), keep_blank_values=True)
        f = {k: v[0].strip() for k, v in valeurs.items()}
        f["clients"] = valeurs.get("clients", [])  # cases à cocher multiples
        if self.chemin in ("/installation", "/connexion", "/deconnexion", "/mot-de-passe") \
                or self.chemin.startswith("/utilisateurs/"):
            return self._post_comptes(f)
        self._post_facturation(f)

    def _post_comptes(self, f: dict):
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
        self._introuvable()

    def _post_facturation(self, f: dict):
        chemin, moi = self.chemin, _utilisateur.get() or ""
        if chemin == "/entreprise":
            try:
                fa.enregistrer_entreprise(f)
            except ValueError as exc:
                return self._envoyer(page_entreprise(str(exc), valeurs=f), 400)
            return self._envoyer(page_entreprise(succes="Informations enregistrées."))
        if chemin == "/clients/ajouter":
            try:
                c = fa.enregistrer_client(f)
            except ValueError as exc:
                return self._envoyer(page_clients(str(exc), valeurs=f), 400)
            return self._rediriger(f"/clients/fiche?code={quote(c['code'])}")
        if chemin == "/clients/modifier":
            code = f.get("code", "")
            valeurs = {**f, "actif": f.get("actif") == "1", "lignes_recurrentes": lignes_du_formulaire(f, "rec_")}
            try:
                fa.enregistrer_client(valeurs, code)
            except ValueError as exc:
                return self._envoyer(page_fiche_client(code, str(exc), valeurs=valeurs), 400)
            return self._envoyer(page_fiche_client(code, succes="Fiche client enregistrée."))
        if chemin == "/clients/supprimer":
            try:
                fa.supprimer_client(f.get("code", ""))
            except ValueError as exc:
                return self._envoyer(page_clients(str(exc)), 400)
            return self._rediriger("/clients")
        if chemin == "/factures/nouvelle":
            try:
                nouvelle = fa.creer_facture(f.get("client", ""), lignes_du_formulaire(f), f.get("date"),
                                            f.get("echeance"), f.get("objet", ""), f.get("notes", ""), moi)
            except ValueError as exc:
                return self._envoyer(page_nouvelle(f, str(exc)), 400)
            return self._rediriger(f"/factures/voir?numero={quote(nouvelle['numero'])}")
        if chemin == "/factures/paiement":
            numero = f.get("numero", "")
            try:
                fa.enregistrer_paiement(numero, f.get("montant"), f.get("date"), f.get("mode", ""),
                                        f.get("reference", ""), moi)
            except ValueError as exc:
                return self._envoyer(page_facture(numero, str(exc)), 400)
            return self._envoyer(page_facture(numero, succes="Paiement enregistré."))
        if chemin == "/factures/annuler":
            numero = f.get("numero", "")
            try:
                fa.annuler_facture(numero, f.get("motif", ""), moi)
            except ValueError as exc:
                return self._envoyer(page_facture(numero, str(exc)), 400)
            return self._envoyer(page_facture(numero, succes="Facture annulée."))
        if chemin == "/factures/generer":
            codes = f.get("clients") or []
            if not codes:
                return self._envoyer(page_generer("Cochez au moins un client."), 400)
            try:
                creees, erreurs = fa.generer_series(codes, f.get("date"), f.get("objet", ""), moi)
            except ValueError as exc:
                return self._envoyer(page_generer(str(exc)), 400)
            liste = "".join(f"<li>{_lien_facture(x['numero'])} — {escape(x['client']['nom'])} — "
                            f"{dh(fa.montant(x['total_ttc']))} DH TTC</li>" for x in creees)
            resultat = f'<div class="ok">{len(creees)} facture(s) émise(s) :<ul>{liste}</ul></div>' if creees else ""
            if erreurs:
                resultat += _messages("Certaines factures n'ont pas été émises :", details=erreurs)
            return self._envoyer(page_generer(resultat=resultat), 200 if creees else 400)
        self._introuvable()


def lancer(hote: str = "127.0.0.1", port: int = 8080, ouvrir_navigateur: bool = False):
    serveur = ThreadingHTTPServer((hote, port), Gestionnaire)
    adresse = f"http://{'localhost' if hote == '127.0.0.1' else hote}:{port}"
    print(f"Facturation disponible sur {adresse}")
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
