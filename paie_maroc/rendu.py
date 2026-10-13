"""Mise en forme du bulletin de paie (HTML imprimable, texte, journal CSV)."""

from __future__ import annotations

import csv
import io
from html import escape

from .calcul import Bulletin, ZERO

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def dh(montant) -> str:
    if montant is None:
        return ""
    texte = f"{montant:,.2f}".replace(",", " ").replace(".", ",")
    return texte


def pct(taux) -> str:
    if taux is None:
        return ""
    return f"{taux * 100:.2f} %".replace(".", ",")


def _qte(valeur) -> str:
    if valeur is None:
        return ""
    return dh(valeur).removesuffix(",00")


def libelle_periode(b: Bulletin) -> str:
    return f"{MOIS[b.variables.mois - 1]} {b.variables.annee}"


CSS = """
:root { --encre:#1d2433; --gris:#5b6475; --trait:#d5dae3; --fond:#f5f7fa; --accent:#0b6e4f; }
* { box-sizing:border-box; }
body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color:var(--encre); background:var(--fond); margin:0; padding:24px 16px; }
.bulletin { max-width:900px; margin:0 auto 32px; background:#fff; border:1px solid var(--trait); border-radius:8px; padding:28px; }
h1 { font-size:20px; margin:0 0 4px; } .sous { color:var(--gris); margin:0 0 20px; }
.entete { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:4px 24px; font-size:14px; margin-bottom:20px; }
.entete b { color:var(--gris); font-weight:500; }
table { width:100%; border-collapse:collapse; font-size:13.5px; margin-bottom:18px; }
th, td { padding:6px 8px; border-bottom:1px solid var(--trait); text-align:right; font-variant-numeric:tabular-nums; }
th:first-child, td:first-child { text-align:left; }
th { background:var(--fond); font-weight:600; font-size:12.5px; color:var(--gris); }
tr.total td { font-weight:600; background:#fafbfc; }
.net { display:flex; justify-content:space-between; align-items:center; background:var(--accent); color:#fff; padding:14px 18px; border-radius:6px; font-size:18px; font-weight:600; }
.resume { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; margin:18px 0; font-size:13px; }
.resume div { border:1px solid var(--trait); border-radius:6px; padding:8px 10px; }
.resume span { display:block; color:var(--gris); font-size:12px; }
.avert { background:#fff6e0; border:1px solid #f0c36d; padding:10px 14px; border-radius:6px; font-size:13px; margin-bottom:16px; }
.wrap { overflow-x:auto; }
.actions { max-width:900px; margin:0 auto 16px; display:flex; gap:8px; }
.actions a, .actions button { font:inherit; padding:8px 14px; border-radius:6px; border:1px solid var(--trait); background:#fff; color:var(--encre); text-decoration:none; cursor:pointer; }
@media print { body { background:#fff; padding:0; } .bulletin { border:none; page-break-after:always; } .actions { display:none; } }
"""


def bulletin_html(b: Bulletin) -> str:
    s = b.salarie
    lignes_g = "".join(
        f"<tr><td>{escape(l.libelle)}</td><td>{_qte(l.base)}</td><td>{pct(l.taux) if l.pourcentage else dh(l.taux)}</td>"
        f"<td>{dh(l.gain)}</td></tr>"
        for l in b.lignes_gains
    )
    lignes_c = "".join(
        f"<tr><td>{escape(l.libelle)}</td><td>{dh(l.base)}</td><td>{pct(l.taux)}</td>"
        f"<td>{dh(l.retenue) if l.retenue else ''}</td><td>{dh(l.patronal) if l.patronal else ''}</td></tr>"
        for l in b.lignes_cotisations
    )
    avert = ""
    if b.avertissements:
        avert = '<div class="avert"><b>Points à vérifier :</b><ul>' + "".join(
            f"<li>{escape(a)}</li>" for a in b.avertissements) + "</ul></div>"
    return f"""
<section class="bulletin">
  <h1>Bulletin de paie</h1>
  <p class="sous">Période : {libelle_periode(b)}</p>
  {avert}
  <div class="entete">
    <div><b>Salarié :</b> {escape(s.nom)}</div>
    <div><b>Matricule :</b> {escape(s.matricule)}</div>
    <div><b>Fonction :</b> {escape(s.fonction)}</div>
    <div><b>CIN :</b> {escape(s.cin)}</div>
    <div><b>N° CNSS :</b> {escape(s.numero_cnss)}</div>
    <div><b>Date d'embauche :</b> {s.date_embauche.strftime('%d/%m/%Y')}</div>
    <div><b>Ancienneté :</b> {b.anciennete_annees} an(s) ({pct(b.taux_anciennete)})</div>
    <div><b>Personnes à charge :</b> {s.personnes_a_charge}</div>
    <div><b>Taux horaire :</b> {dh(b.taux_horaire)} DH</div>
  </div>
  <div class="wrap"><table>
    <thead><tr><th>Rubrique</th><th>Base / Nombre</th><th>Taux</th><th>Gain (DH)</th></tr></thead>
    <tbody>{lignes_g}
      <tr class="total"><td>Salaire brut</td><td></td><td></td><td>{dh(b.salaire_brut)}</td></tr>
      <tr><td>dont éléments exonérés</td><td></td><td></td><td>{dh(b.total_exonere)}</td></tr>
      <tr class="total"><td>Salaire brut imposable</td><td></td><td></td><td>{dh(b.brut_imposable)}</td></tr>
    </tbody>
  </table></div>
  <div class="wrap"><table>
    <thead><tr><th>Cotisations et retenues</th><th>Base</th><th>Taux salarié</th><th>Retenue (DH)</th><th>Part patronale (DH)</th></tr></thead>
    <tbody>{lignes_c}
      <tr class="total"><td>Total</td><td></td><td></td><td>{dh(b.total_retenues)}</td><td>{dh(b.charges_patronales)}</td></tr>
    </tbody>
  </table></div>
  <div class="resume">
    <div><span>Brut imposable</span>{dh(b.brut_imposable)}</div>
    <div><span>Frais professionnels</span>{dh(b.frais_professionnels)}</div>
    <div><span>CNSS + AMO + CIMR</span>{dh(b.cnss + b.amo + b.cimr)}</div>
    <div><span>Intérêts logement déduits</span>{dh(b.interets_logement)}</div>
    <div><span>Net imposable</span>{dh(b.net_imposable)}</div>
    <div><span>IR brut − charges de famille</span>{dh(b.ir_brut)} − {dh(b.deduction_famille)}</div>
    <div><span>Coût total employeur</span>{dh(b.cout_employeur)}</div>
  </div>
  <div class="net"><span>Net à payer</span><span>{dh(b.net_a_payer)} DH</span></div>
</section>"""


def page_html(bulletins: list[Bulletin], retour: str | None = None) -> str:
    actions = '<div class="actions"><button onclick="window.print()">Imprimer / PDF</button>'
    if retour:
        actions += f'<a href="{escape(retour)}">Nouveau calcul</a>'
    actions += "</div>"
    corps = "".join(bulletin_html(b) for b in bulletins)
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Bulletins de paie</title><style>{CSS}</style></head>'
            f'<body>{actions}{corps}</body></html>')


def bulletin_texte(b: Bulletin) -> str:
    s = b.salarie
    largeur = 72
    out = [
        "=" * largeur,
        f"BULLETIN DE PAIE - {libelle_periode(b).upper()}".center(largeur),
        "=" * largeur,
        f"Salarié : {s.nom}   Matricule : {s.matricule}",
        f"Ancienneté : {b.anciennete_annees} an(s) ({pct(b.taux_anciennete)})   "
        f"Personnes à charge : {s.personnes_a_charge}",
        "-" * largeur,
    ]
    for l in b.lignes_gains:
        out.append(f"{l.libelle:<48}{dh(l.gain):>24}")
    out += [
        "-" * largeur,
        f"{'SALAIRE BRUT':<48}{dh(b.salaire_brut):>24}",
        f"{'Salaire brut imposable':<48}{dh(b.brut_imposable):>24}",
        "-" * largeur,
    ]
    for l in b.lignes_cotisations:
        if l.retenue:
            out.append(f"{l.libelle:<48}{dh(l.retenue):>24}")
    out += [
        "-" * largeur,
        f"{'Frais professionnels':<48}{dh(b.frais_professionnels):>24}",
        f"{'Net imposable':<48}{dh(b.net_imposable):>24}",
        f"{'Total retenues':<48}{dh(b.total_retenues):>24}",
        "=" * largeur,
        f"{'NET À PAYER':<48}{dh(b.net_a_payer):>24}",
        "=" * largeur,
        f"{'Charges patronales':<48}{dh(b.charges_patronales):>24}",
        f"{'Coût total employeur':<48}{dh(b.cout_employeur):>24}",
    ]
    for a in b.avertissements:
        out.append(f"! {a}")
    return "\n".join(out)


COLONNES_JOURNAL = [
    "matricule", "nom", "periode", "salaire_brut", "total_exonere", "brut_imposable",
    "cnss", "amo", "cimr", "frais_professionnels", "net_imposable", "ir",
    "net_a_payer", "charges_patronales", "cout_employeur",
]


def journal_csv(bulletins: list[Bulletin]) -> str:
    """Journal de paie (une ligne par salarié), séparateur « ; » pour Excel."""
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";")
    w.writerow(COLONNES_JOURNAL)
    totaux = {c: ZERO for c in COLONNES_JOURNAL[3:]}
    for b in bulletins:
        valeurs = [getattr(b, c) for c in COLONNES_JOURNAL[3:]]
        for c, v in zip(COLONNES_JOURNAL[3:], valeurs):
            totaux[c] += v
        w.writerow([b.salarie.matricule, b.salarie.nom, b.periode] + [dh(v).replace(" ", "") for v in valeurs])
    w.writerow(["", "TOTAL", ""] + [dh(v).replace(" ", "") for v in totaux.values()])
    return sortie.getvalue()
