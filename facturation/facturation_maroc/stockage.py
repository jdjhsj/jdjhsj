"""Stockage local des données (comptes, entreprise, clients, factures).

Les fichiers JSON sont écrits dans le dossier ``donnees/`` à la racine du projet,
ou dans le dossier indiqué par la variable d'environnement ``FACTURATION_DONNEES``.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_verrou = threading.Lock()


def dossier() -> Path:
    chemin = Path(os.environ.get("FACTURATION_DONNEES") or Path(__file__).resolve().parent.parent / "donnees")
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def lire(nom: str, defaut):
    fichier = dossier() / nom
    if not fichier.exists():
        return defaut
    with _verrou:
        return json.loads(fichier.read_text(encoding="utf-8"))


def ecrire(nom: str, donnees) -> None:
    fichier = dossier() / nom
    temporaire = fichier.with_suffix(".tmp")
    with _verrou:
        temporaire.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporaire, fichier)
