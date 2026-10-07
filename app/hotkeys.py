"""Raccourcis clavier GLOBAUX via l'API native Windows (RegisterHotKey).

Plus fiable que la lib 'keyboard' (pas de hook bas niveau, pas besoin d'admin).
WM_HOTKEY arrive dans la boucle de messages du thread principal -> capte via
un QAbstractNativeEventFilter installe sur l'application.
"""
from __future__ import annotations
import ctypes
import logging

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

log = logging.getLogger("hotkeys")

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
_MODS = {
    "ctrl": 0x0002, "control": 0x0002, "ctl": 0x0002,
    "alt": 0x0001, "shift": 0x0004,
    "win": 0x0008, "super": 0x0008, "meta": 0x0008,
}
_VK = {
    "space": 0x20, "espace": 0x20, "enter": 0x0D, "entree": 0x0D, "return": 0x0D,
    "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "backspace": 0x08,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    **{f"f{i}": 0x70 + (i - 1) for i in range(1, 13)},
    **{str(d): 0x30 + d for d in range(10)},
}


def _parse(combo: str):
    """'ctrl+alt+space' -> (modificateurs, code_touche) ou (0, None)."""
    mods = 0
    vk = None
    for part in combo.lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in _MODS:
            mods |= _MODS[part]
        elif part in _VK:
            vk = _VK[part]
        elif len(part) == 1:
            vk = ord(part.upper())
    return mods, vk


class GestionnaireRaccourcis(QAbstractNativeEventFilter, QObject):
    active = Signal(int)  # emet l'id du raccourci declenche

    def __init__(self):
        QObject.__init__(self)
        QAbstractNativeEventFilter.__init__(self)
        self._enregistres = {}   # id -> combo
        self._compteur = 0

    def enregistrer(self, combo: str):
        mods, vk = _parse(combo)
        if vk is None or mods == 0:
            log.error("Raccourci invalide: %r (modif=%s, touche=%s)", combo, mods, vk)
            return None
        self._compteur += 1
        hk = self._compteur
        try:
            ok = ctypes.windll.user32.RegisterHotKey(None, hk, mods | MOD_NOREPEAT, vk)
        except Exception as e:
            log.error("RegisterHotKey indisponible: %s", e)
            return None
        if ok:
            self._enregistres[hk] = combo
            log.info("Raccourci natif enregistre: %s (id=%d, mods=0x%x, vk=0x%x)",
                     combo, hk, mods, vk)
            return hk
        err = ctypes.windll.kernel32.GetLastError()
        log.error("RegisterHotKey a echoue pour %s (GetLastError=%d, souvent 1409 = deja pris)",
                  combo, err)
        return None

    def tout_retirer(self):
        for hk in list(self._enregistres):
            try:
                ctypes.windll.user32.UnregisterHotKey(None, hk)
            except Exception:
                pass
        self._enregistres.clear()

    def nativeEventFilter(self, eventType, message):
        try:
            if eventType == b"windows_generic_MSG":
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    self.active.emit(int(msg.wParam))
        except Exception as e:
            log.debug("nativeEventFilter: %s", e)
        return False, 0
