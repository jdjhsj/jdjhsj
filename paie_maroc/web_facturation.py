"""Pages web de la facturation : clients, séries de factures par client, historique."""

from __future__ import annotations

from datetime import date
from html import escape
from urllib.parse import parse_qs, quote

from . import facturation as fa
from .rendu import MOIS, dh
from .web import _champ, _messages, _num, _page, _utilisateur

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


def _page_f(titre: str, corps: str) -> str:
    return _page(titre, f"<style>{FACT_CSS}</style>{corps}")


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
    return _page_f("Entreprise", f"""{_messages(erreur, succes)}
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
    return _page_f("Clients", f"""{_messages(erreur, succes)}
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
        return _page_f("Client", _messages("Client introuvable."))
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
    return _page_f(c["nom"], f"""{_messages(erreur, succes)}
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
        return _page_f("Nouvelle facture", _messages("Ajoutez d'abord un client.")
                       + '<p style="text-align:center"><a class="bouton" href="/clients">Ajouter un client</a></p>')
    avert = "" if fa.entreprise().get("ice") else (
        '<div class="erreur">Les informations de votre entreprise (ICE, IF, RC…) ne sont pas complètes : '
        '<a href="/entreprise">compléter</a> avant d\'émettre des factures.</div>')
    return _page_f("Nouvelle facture", f"""{_messages(erreur)}{avert}
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
        return _page_f("Facture", _messages("Facture introuvable."))
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
    return _page_f(f"Facture {numero}", _messages(erreur, succes) + panneau + facture_html(f))


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
    return _page_f("Factures", f"""
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
    return _page_f("Facturation en série", f"""{_messages(erreur)}{resultat}
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
# Routage (appelé par web.Gestionnaire)
# ---------------------------------------------------------------------------

PREFIXES = ("/factures", "/clients", "/entreprise")


def get(h) -> None:
    q = lambda nom: (h.requete.get(nom) or [""])[0]
    chemin = h.chemin
    if chemin == "/factures":
        return h._envoyer(page_factures(h.requete))
    if chemin == "/factures/nouvelle":
        return h._envoyer(page_nouvelle(client=q("client"), depuis=q("depuis")))
    if chemin == "/factures/voir":
        f = fa.facture(q("numero"))
        return h._envoyer(page_facture(q("numero")), 200 if f else 404)
    if chemin == "/factures/generer":
        return h._envoyer(page_generer())
    if chemin == "/factures.csv":
        liste = fa.rechercher(q("client"), q("annee"), q("statut"), q("q"))
        return h._fichier("factures.csv", fa.export_csv(liste), "text/csv; charset=utf-8")
    if chemin == "/clients":
        return h._envoyer(page_clients())
    if chemin == "/clients/fiche":
        return h._envoyer(page_fiche_client(q("code")), 200 if fa.client(q("code")) else 404)
    if chemin == "/entreprise":
        return h._envoyer(page_entreprise())
    h._envoyer(_page("Introuvable", _messages("Page introuvable.")), 404)


def post(h, corps: bytes) -> None:
    valeurs = parse_qs(corps.decode("utf-8"), keep_blank_values=True)
    f = {k: v[0].strip() for k, v in valeurs.items()}
    f["clients"] = valeurs.get("clients", [])  # cases à cocher multiples
    chemin, moi = h.chemin, _utilisateur.get() or ""
    if chemin == "/entreprise":
        try:
            fa.enregistrer_entreprise(f)
        except ValueError as exc:
            return h._envoyer(page_entreprise(str(exc), valeurs=f), 400)
        return h._envoyer(page_entreprise(succes="Informations enregistrées."))
    if chemin == "/clients/ajouter":
        try:
            c = fa.enregistrer_client(f)
        except ValueError as exc:
            return h._envoyer(page_clients(str(exc), valeurs=f), 400)
        return h._rediriger(f"/clients/fiche?code={quote(c['code'])}")
    if chemin == "/clients/modifier":
        code = f.get("code", "")
        valeurs = {**f, "actif": f.get("actif") == "1", "lignes_recurrentes": lignes_du_formulaire(f, "rec_")}
        try:
            fa.enregistrer_client(valeurs, code)
        except ValueError as exc:
            return h._envoyer(page_fiche_client(code, str(exc), valeurs=valeurs), 400)
        return h._envoyer(page_fiche_client(code, succes="Fiche client enregistrée."))
    if chemin == "/clients/supprimer":
        try:
            fa.supprimer_client(f.get("code", ""))
        except ValueError as exc:
            return h._envoyer(page_clients(str(exc)), 400)
        return h._rediriger("/clients")
    if chemin == "/factures/nouvelle":
        try:
            nouvelle = fa.creer_facture(f.get("client", ""), lignes_du_formulaire(f), f.get("date"),
                                        f.get("echeance"), f.get("objet", ""), f.get("notes", ""), moi)
        except ValueError as exc:
            return h._envoyer(page_nouvelle(f, str(exc)), 400)
        return h._rediriger(f"/factures/voir?numero={quote(nouvelle['numero'])}")
    if chemin == "/factures/paiement":
        numero = f.get("numero", "")
        try:
            fa.enregistrer_paiement(numero, f.get("montant"), f.get("date"), f.get("mode", ""),
                                    f.get("reference", ""), moi)
        except ValueError as exc:
            return h._envoyer(page_facture(numero, str(exc)), 400)
        return h._envoyer(page_facture(numero, succes="Paiement enregistré."))
    if chemin == "/factures/annuler":
        numero = f.get("numero", "")
        try:
            fa.annuler_facture(numero, f.get("motif", ""), moi)
        except ValueError as exc:
            return h._envoyer(page_facture(numero, str(exc)), 400)
        return h._envoyer(page_facture(numero, succes="Facture annulée."))
    if chemin == "/factures/generer":
        codes = f.get("clients") or []
        if not codes:
            return h._envoyer(page_generer("Cochez au moins un client."), 400)
        try:
            creees, erreurs = fa.generer_series(codes, f.get("date"), f.get("objet", ""), moi)
        except ValueError as exc:
            return h._envoyer(page_generer(str(exc)), 400)
        liste = "".join(f"<li>{_lien_facture(x['numero'])} — {escape(x['client']['nom'])} — "
                        f"{dh(fa.montant(x['total_ttc']))} DH TTC</li>" for x in creees)
        resultat = f'<div class="ok">{len(creees)} facture(s) émise(s) :<ul>{liste}</ul></div>' if creees else ""
        if erreurs:
            resultat += _messages("Certaines factures n'ont pas été émises :", details=erreurs)
        return h._envoyer(page_generer(resultat=resultat), 200 if creees else 400)
    h._envoyer(_page("Introuvable", _messages("Page introuvable.")), 404)
