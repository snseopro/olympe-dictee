"""Ecrire du texte la ou est le curseur (n'importe quelle appli Windows).

Methode : on place le texte dans le presse-papiers puis on simule Ctrl+V.
Plus fiable que taper caractere par caractere (accents, longueur, apps).
On sauvegarde et restaure le presse-papiers de l'utilisateur.
"""
from __future__ import annotations
import logging
import time

log = logging.getLogger("inject")


def _lire_presse_papiers():
    try:
        import win32clipboard as cb
        cb.OpenClipboard()
        try:
            if cb.IsClipboardFormatAvailable(cb.CF_UNICODETEXT):
                return cb.GetClipboardData(cb.CF_UNICODETEXT)
        finally:
            cb.CloseClipboard()
    except Exception as e:
        log.debug("Lecture presse-papiers impossible: %s", e)
    return None


def _ecrire_presse_papiers(texte: str) -> bool:
    try:
        import win32clipboard as cb
        cb.OpenClipboard()
        try:
            cb.EmptyClipboard()
            cb.SetClipboardData(cb.CF_UNICODETEXT, texte)
        finally:
            cb.CloseClipboard()
        return True
    except Exception as e:
        log.error("Ecriture presse-papiers impossible: %s", e)
        return False


def coller_au_curseur(texte: str, restaurer: bool = True) -> bool:
    """Colle `texte` dans le champ actif. Renvoie True si l'envoi a eu lieu."""
    if not texte:
        return False
    import keyboard

    ancien = _lire_presse_papiers() if restaurer else None
    if not _ecrire_presse_papiers(texte):
        return False
    # Laisse le focus revenir a l'appli cible (on vient peut-etre du panneau).
    time.sleep(0.12)
    try:
        keyboard.send("ctrl+v")
        log.info("Colle au curseur (%d caracteres)", len(texte))
    except Exception as e:
        log.error("Echec Ctrl+V: %s", e)
        return False

    if restaurer and ancien is not None:
        # Restaure apres un court delai (le collage doit avoir eu lieu).
        def _restaure():
            time.sleep(0.4)
            _ecrire_presse_papiers(ancien)
        import threading
        threading.Thread(target=_restaure, daemon=True).start()
    return True
