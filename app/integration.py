"""Intégration Windows : raccourci bureau + démarrage automatique.

Résout le "je n'ai plus aucun moyen de la relancer" : un .exe autonome n'a ni
entrée menu Démarrer ni raccourci. On en crée un sur le bureau, et on démarre
avec Windows (clé Run) pour qu'elle soit toujours disponible dans la barre.
"""
from __future__ import annotations
import logging
import os
import subprocess
import sys

from .version import APP_NOM, APP_ID

log = logging.getLogger("integration")

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _exe() -> str:
    return sys.executable


def est_gelee() -> bool:
    return bool(getattr(sys, "frozen", False))


# --- Auto-installation dans un dossier STABLE -------------------------------
# Sinon l'exe tourne depuis Downloads (ou ailleurs), la MAJ remplace un fichier
# et le raccourci/autostart pointent vers une autre copie -> desynchronisation.
def dossier_install() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_ID)


def chemin_install_exe() -> str:
    return os.path.join(dossier_install(), "OlympeDictee.exe")


def est_installe() -> bool:
    try:
        return (os.path.normcase(os.path.abspath(_exe()))
                == os.path.normcase(os.path.abspath(chemin_install_exe())))
    except Exception:
        return False


def installer_et_relancer() -> bool:
    """Copie l'exe dans le dossier d'install stable, lance la copie et
    demande a l'instance courante de quitter. Renvoie True si on a relance."""
    if not est_gelee() or est_installe():
        return False
    import shutil
    dst = chemin_install_exe()
    try:
        os.makedirs(dossier_install(), exist_ok=True)
        shutil.copy2(_exe(), dst)
    except Exception as e:
        log.error("Installation dans %s impossible: %s", dossier_install(), e)
        return False
    try:
        subprocess.Popen([dst], creationflags=0x00000008)  # DETACHED_PROCESS
    except Exception as e:
        log.error("Lancement de la copie installee impossible: %s", e)
        return False
    log.info("Installe dans %s, l'instance courante va quitter.", dst)
    return True


def chemin_raccourci_bureau() -> str:
    bureau = os.path.join(os.path.expanduser("~"), "Desktop")
    # OneDrive déplace parfois le Bureau
    od = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
    if os.path.isdir(od):
        bureau = od
    return os.path.join(bureau, APP_NOM + ".lnk")


def creer_raccourci_bureau() -> bool:
    """Crée (ou recrée) le raccourci bureau pointant vers l'exe courant."""
    if not est_gelee():
        return False
    lnk = chemin_raccourci_bureau()
    # Toujours pointer vers l'exe du dossier d'install STABLE (c'est lui que la
    # MAJ remplace), jamais sys.executable : sinon un lancement depuis une autre
    # copie recreerait un raccourci vers une version qui ne sera pas mise a jour.
    exe = chemin_install_exe() if os.path.isfile(chemin_install_exe()) else _exe()
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{lnk}'); "
        f"$s.TargetPath = '{exe}'; "
        f"$s.WorkingDirectory = '{os.path.dirname(exe)}'; "
        f"$s.IconLocation = '{exe},0'; "
        f"$s.Description = '{APP_NOM}'; "
        "$s.Save()"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, timeout=20,
                       creationflags=0x08000000)  # CREATE_NO_WINDOW
        log.info("Raccourci bureau cree: %s", lnk)
        return True
    except Exception as e:
        log.error("Creation raccourci bureau impossible: %s", e)
        return False


def autostart_actif() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            v, _ = winreg.QueryValueEx(k, APP_ID)
            return bool(v)
    except Exception:
        return False


def activer_autostart() -> bool:
    if not est_gelee():
        return False
    try:
        import winreg
        exe = chemin_install_exe() if os.path.isfile(chemin_install_exe()) else _exe()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, APP_ID, 0, winreg.REG_SZ, f'"{exe}"')
        log.info("Demarrage automatique active")
        return True
    except Exception as e:
        log.error("Activation autostart impossible: %s", e)
        return False


def desactiver_autostart() -> None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP_ID)
        log.info("Demarrage automatique desactive")
    except FileNotFoundError:
        pass
    except Exception as e:
        log.error("Desactivation autostart impossible: %s", e)
