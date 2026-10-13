"""Conversion dictionnaire / JSON -> objets de paie."""

from __future__ import annotations

from datetime import date

from .calcul import Prime, Salarie, VariablesPaie, dec


def _date(valeur) -> date | None:
    if not valeur:
        return None
    if isinstance(valeur, date):
        return valeur
    return date.fromisoformat(str(valeur))


def salarie_depuis_dict(d: dict) -> Salarie:
    return Salarie(
        nom=d["nom"],
        salaire_base=dec(d["salaire_base"]),
        date_embauche=_date(d["date_embauche"]),
        matricule=str(d.get("matricule", "")),
        fonction=d.get("fonction", ""),
        cin=d.get("cin", ""),
        numero_cnss=str(d.get("numero_cnss", "")),
        date_naissance=_date(d.get("date_naissance")),
        personnes_a_charge=int(d.get("personnes_a_charge") or 0),
        taux_cimr_salarie=dec(d.get("taux_cimr_salarie")) / 100,
        taux_cimr_patronal=dec(d.get("taux_cimr_patronal")) / 100,
    )


def variables_depuis_dict(d: dict) -> VariablesPaie:
    ref = d.get("salaire_reference_conges")
    return VariablesPaie(
        annee=int(d["annee"]),
        mois=int(d["mois"]),
        heures_sup={k: dec(v) for k, v in (d.get("heures_sup") or {}).items() if dec(v)},
        primes=[Prime(p["libelle"], dec(p["montant"])) for p in d.get("primes") or [] if dec(p.get("montant"))],
        avantages_nature=dec(d.get("avantages_nature")),
        indemnites={k: dec(v) for k, v in (d.get("indemnites") or {}).items() if dec(v)},
        jours_absence=dec(d.get("jours_absence")),
        jours_conges=dec(d.get("jours_conges")),
        salaire_reference_conges=dec(ref) if ref not in (None, "") else None,
        interets_logement=dec(d.get("interets_logement")),
        avance=dec(d.get("avance")),
        autres_retenues=dec(d.get("autres_retenues")),
    )
