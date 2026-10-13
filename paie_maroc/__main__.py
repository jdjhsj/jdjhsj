"""Ligne de commande.

  python -m paie_maroc web [--port 8000]
  python -m paie_maroc paie exemples/paie_octobre_2026.json [--html bulletins.html] [--csv journal.csv]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .calcul import calculer_bulletin
from .donnees import salarie_depuis_dict, variables_depuis_dict
from .rendu import bulletin_texte, journal_csv, page_html


def calculer_fichier(chemin: str):
    donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    bulletins = []
    for entree in donnees["salaries"]:
        variables = {"annee": donnees["annee"], "mois": donnees["mois"], **entree.get("variables", {})}
        bulletins.append(calculer_bulletin(salarie_depuis_dict(entree), variables_depuis_dict(variables)))
    return bulletins


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="paie_maroc", description="Paie selon le droit marocain")
    sous = parser.add_subparsers(dest="commande", required=True)

    w = sous.add_parser("web", help="lancer l'interface web locale")
    w.add_argument("--hote", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8000)

    p = sous.add_parser("paie", help="calculer les bulletins d'un fichier JSON")
    p.add_argument("fichier")
    p.add_argument("--html", help="écrire les bulletins dans ce fichier HTML (imprimable)")
    p.add_argument("--csv", help="écrire le journal de paie dans ce fichier CSV")

    args = parser.parse_args(argv)
    if args.commande == "web":
        from .web import lancer
        lancer(args.hote, args.port)
        return 0

    bulletins = calculer_fichier(args.fichier)
    for b in bulletins:
        print(bulletin_texte(b), end="\n\n")
    if args.html:
        Path(args.html).write_text(page_html(bulletins), encoding="utf-8")
        print(f"Bulletins HTML : {args.html}")
    if args.csv:
        Path(args.csv).write_text(journal_csv(bulletins), encoding="utf-8-sig")
        print(f"Journal de paie : {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
