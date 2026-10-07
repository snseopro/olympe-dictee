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


def _envoyer_ctrl_v():
    """Simule Ctrl+V en natif (keybd_event) -> envoye au champ au premier plan."""
    import ctypes
    u = ctypes.windll.user32
    VK_CONTROL, VK_V, KEYUP = 0x11, 0x56, 0x0002
    u.keybd_event(VK_CONTROL, 0, 0, 0)
    u.keybd_event(VK_V, 0, 0, 0)
    u.keybd_event(VK_V, 0, KEYUP, 0)
    u.keybd_event(VK_CONTROL, 0, KEYUP, 0)


def taper_texte(texte: str) -> bool:
    """Tape le texte caractere par caractere (SendInput Unicode).

    Marche la ou Ctrl+V est refuse (certaines apps Electron comme Discord).
    """
    import ctypes
    from ctypes import wintypes

    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class _IU(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _IU)]

    u = ctypes.windll.user32

    def _ev(scan, keyup):
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if keyup else 0)
        return INPUT(type=INPUT_KEYBOARD,
                     u=_IU(ki=KEYBDINPUT(0, scan, flags, 0, None)))

    envois = []
    for ch in texte:
        code = ord(ch)
        # les caracteres hors BMP sont rares ici ; on envoie l'unite de code.
        envois.append(_ev(code, False))
        envois.append(_ev(code, True))
    if not envois:
        return False
    arr = (INPUT * len(envois))(*envois)
    n = u.SendInput(len(envois), arr, ctypes.sizeof(INPUT))
    log.info("Texte tape au curseur (%d/%d evenements)", n, len(envois))
    return n > 0


def coller_au_curseur(texte: str, methode: str = "coller", restaurer: bool = True) -> bool:
    """Ecrit `texte` dans le champ actif. methode = 'coller' (Ctrl+V) ou 'taper'."""
    if not texte:
        return False

    # Laisse le focus revenir a l'appli cible (on vient peut-etre du panneau).
    time.sleep(0.18)

    if methode == "taper":
        try:
            return taper_texte(texte)
        except Exception as e:
            log.error("Echec saisie clavier, repli sur Ctrl+V: %s", e)
            # repli sur le collage

    ancien = _lire_presse_papiers() if restaurer else None
    if not _ecrire_presse_papiers(texte):
        return False
    try:
        _envoyer_ctrl_v()
        log.info("Colle au curseur (%d caracteres)", len(texte))
    except Exception as e:
        log.error("Echec Ctrl+V: %s", e)
        return False

    if restaurer and ancien is not None:
        def _restaure():
            time.sleep(0.5)
            _ecrire_presse_papiers(ancien)
        import threading
        threading.Thread(target=_restaure, daemon=True).start()
    return True
