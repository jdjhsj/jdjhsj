"""Ligne de commande.

  python -m facturation_maroc [--port 8080] [--ouvrir]
"""

from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="facturation_maroc", description="Facturation par séries de clients")
    parser.add_argument("--hote", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--ouvrir", action="store_true", help="ouvrir le navigateur automatiquement")
    args = parser.parse_args(argv)
    from .web import lancer
    lancer(args.hote, args.port, args.ouvrir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
