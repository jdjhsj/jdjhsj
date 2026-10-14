"""Authentification : comptes utilisateurs et sessions."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

from . import stockage

FICHIER = "utilisateurs.json"
ITERATIONS = 200_000
LONGUEUR_MIN = 8
DUREE_SESSION = 8 * 3600  # secondes

_sessions: dict[str, tuple[str, float]] = {}
_verrou = threading.Lock()


def _hacher(mot_de_passe: str, sel: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), sel, ITERATIONS).hex()


def utilisateurs() -> dict:
    return stockage.lire(FICHIER, {})


def aucun_utilisateur() -> bool:
    return not utilisateurs()


def creer_utilisateur(identifiant: str, mot_de_passe: str, admin: bool = False) -> None:
    identifiant = identifiant.strip()
    if not identifiant:
        raise ValueError("Identifiant obligatoire.")
    if len(mot_de_passe) < LONGUEUR_MIN:
        raise ValueError(f"Le mot de passe doit contenir au moins {LONGUEUR_MIN} caractères.")
    comptes = utilisateurs()
    if identifiant in comptes:
        raise ValueError(f"L'utilisateur « {identifiant} » existe déjà.")
    sel = secrets.token_bytes(16)
    comptes[identifiant] = {"sel": sel.hex(), "hash": _hacher(mot_de_passe, sel), "admin": admin}
    stockage.ecrire(FICHIER, comptes)


def changer_mot_de_passe(identifiant: str, ancien: str, nouveau: str) -> None:
    if not verifier(identifiant, ancien):
        raise ValueError("Mot de passe actuel incorrect.")
    if len(nouveau) < LONGUEUR_MIN:
        raise ValueError(f"Le mot de passe doit contenir au moins {LONGUEUR_MIN} caractères.")
    comptes = utilisateurs()
    sel = secrets.token_bytes(16)
    comptes[identifiant].update(sel=sel.hex(), hash=_hacher(nouveau, sel))
    stockage.ecrire(FICHIER, comptes)
    fermer_sessions(identifiant)


def supprimer_utilisateur(identifiant: str) -> None:
    comptes = utilisateurs()
    if identifiant not in comptes:
        raise ValueError("Utilisateur inconnu.")
    if comptes[identifiant].get("admin") and sum(1 for c in comptes.values() if c.get("admin")) == 1:
        raise ValueError("Impossible de supprimer le dernier administrateur.")
    del comptes[identifiant]
    stockage.ecrire(FICHIER, comptes)
    fermer_sessions(identifiant)


def est_admin(identifiant: str) -> bool:
    return bool(utilisateurs().get(identifiant, {}).get("admin"))


def verifier(identifiant: str, mot_de_passe: str) -> bool:
    compte = utilisateurs().get(identifiant)
    if not compte:
        _hacher(mot_de_passe, b"0" * 16)  # temps constant même si l'utilisateur n'existe pas
        return False
    attendu = compte["hash"]
    return hmac.compare_digest(attendu, _hacher(mot_de_passe, bytes.fromhex(compte["sel"])))


# --- Sessions (en mémoire : une reconnexion est nécessaire après redémarrage) ---

def ouvrir_session(identifiant: str) -> str:
    jeton = secrets.token_urlsafe(32)
    with _verrou:
        _sessions[jeton] = (identifiant, time.time() + DUREE_SESSION)
    return jeton


def session(jeton: str | None) -> str | None:
    if not jeton:
        return None
    with _verrou:
        entree = _sessions.get(jeton)
        if not entree:
            return None
        identifiant, expiration = entree
        if expiration < time.time() or identifiant not in utilisateurs():
            _sessions.pop(jeton, None)
            return None
        _sessions[jeton] = (identifiant, time.time() + DUREE_SESSION)
        return identifiant


def fermer_session(jeton: str | None) -> None:
    with _verrou:
        _sessions.pop(jeton or "", None)


def fermer_sessions(identifiant: str) -> None:
    with _verrou:
        for jeton in [j for j, (u, _) in _sessions.items() if u == identifiant]:
            del _sessions[jeton]
