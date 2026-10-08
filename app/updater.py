"""Mise a jour integree : telecharge la derniere version depuis un manifeste
JSON (publie par le CI sur GitHub) et remplace l'exe en cours, puis relance.

Fonctionne uniquement quand l'app tourne en .exe (PyInstaller, sys.frozen).
En developpement (python), les fonctions renvoient un message et ne font rien.

Manifeste attendu (latest.json) :
  {"version": "1.0.42",
   "url": "https://github.com/.../releases/download/v1.0.42/OlympeDictee.exe",
   "sha256": "<empreinte hex>",
   "notes": "..."}
"""
from __future__ import annotations
import hashlib
import logging
import os
import subprocess
import sys
import tempfile

import requests

from .version import __version__

log = logging.getLogger("maj")


def _tuple_version(v: str):
    out = []
    for p in str(v).strip().lstrip("vV").split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def est_gelee() -> bool:
    return bool(getattr(sys, "frozen", False))


def verifier(url_manifeste: str) -> dict | None:
    """Renvoie le manifeste si une version plus recente existe, sinon None."""
    try:
        r = requests.get(url_manifeste, timeout=20)
        r.raise_for_status()
        man = r.json()
    except Exception as e:
        log.warning("Verif MAJ impossible: %s", e)
        raise
    distante = str(man.get("version", "")).strip()
    if not distante:
        return None
    if _tuple_version(distante) > _tuple_version(__version__):
        log.info("MAJ dispo: %s > %s", distante, __version__)
        return man
    log.info("Deja a jour (%s)", __version__)
    return None


def telecharger_et_installer(man: dict, progres=None) -> bool:
    """Telecharge le nouvel exe, verifie l'empreinte, installe et relance.

    `progres` : callback optionnel progres(pourcent:int).
    Si tout se passe bien, cette fonction NE REVIENT PAS (l'app se ferme).
    """
    if not est_gelee():
        log.warning("MAJ ignoree : app lancee en mode developpement (pas un .exe).")
        raise RuntimeError("La mise a jour n'est possible que sur la version installee (.exe).")

    url = man.get("url")
    sha = (man.get("sha256") or "").lower().strip()
    if not url:
        raise RuntimeError("Manifeste sans URL de telechargement.")

    tmp = tempfile.NamedTemporaryFile(prefix="olympe_dictee_maj_", suffix=".exe", delete=False)
    chemin_tmp = tmp.name
    tmp.close()

    log.info("Telechargement MAJ: %s", url)
    h = hashlib.sha256()
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        recu = 0
        with open(chemin_tmp, "wb") as f:
            for bloc in r.iter_content(chunk_size=65536):
                if not bloc:
                    continue
                f.write(bloc)
                h.update(bloc)
                recu += len(bloc)
                if progres and total:
                    progres(int(recu * 100 / total))

    if sha:
        calc = h.hexdigest().lower()
        if calc != sha:
            log.error("Empreinte MAJ invalide: attendu %s, obtenu %s", sha, calc)
            try:
                os.remove(chemin_tmp)
            except OSError:
                pass
            raise RuntimeError("Telechargement corrompu (empreinte invalide). Mise a jour annulee.")
    else:
        log.warning("Manifeste sans sha256 : integrite non verifiee.")

    # Cible = l'exe du DOSSIER D'INSTALL STABLE (pas forcement sys.executable) :
    # c'est lui que le raccourci bureau et l'autostart lancent. On remplace donc
    # toujours CE fichier, pour qu'il n'y ait jamais une copie a jour et une
    # copie peri­mee qui se desynchronisent.
    from . import integration
    cible = integration.chemin_install_exe() if integration.est_gelee() else sys.executable
    log_maj = os.path.join(os.path.dirname(cible), "maj.log")
    pid = os.getpid()
    # Script batch : attend la fermeture de l'app, REMPLACE l'exe avec RETRY
    # (un .exe onefile reste verrouille quelques secondes apres la fermeture :
    # sans retry le move echoue en silence et l'ANCIENNE version se relance ->
    # boucle de mise a jour infinie). Tout est journalise dans maj.log.
    bat = tempfile.NamedTemporaryFile(prefix="olympe_dictee_maj_", suffix=".bat",
                                      delete=False, mode="w", encoding="ascii")
    lignes = [
        "@echo off",
        "setlocal",
        f'set "LOG={log_maj}"',
        f'echo [%date% %time%] MAJ: attente fermeture PID {pid} >> "%LOG%"',
        ":wait",
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
        "if not errorlevel 1 (",
        "  timeout /t 1 /nobreak >nul",
        "  goto wait",
        ")",
        'echo [%date% %time%] MAJ: app fermee, pause 2s >> "%LOG%"',
        "timeout /t 2 /nobreak >nul",
        "set /a n=0",
        ":mv",
        f'move /y "{chemin_tmp}" "{cible}" >> "%LOG%" 2>&1',
        "if not errorlevel 1 goto ok",
        "set /a n+=1",
        'echo [%date% %time%] MAJ: move echec, tentative %n% >> "%LOG%"',
        "if %n% geq 40 goto fail",
        "timeout /t 1 /nobreak >nul",
        "goto mv",
        ":ok",
        'echo [%date% %time%] MAJ: remplacement OK, relance >> "%LOG%"',
        "goto run",
        ":fail",
        'echo [%date% %time%] MAJ: ECHEC remplacement apres 40 tentatives >> "%LOG%"',
        ":run",
        f'start "" "{cible}"',
        'del "%~f0"',
    ]
    bat.write("\r\n".join(lignes) + "\r\n")
    bat.close()
    log.info("Lancement de l'updater, fermeture de l'app.")
    subprocess.Popen(["cmd", "/c", bat.name],
                     creationflags=0x00000008 | 0x00000200)  # DETACHED | NEW_GROUP
    # On rend la main a l'appelant qui doit quitter proprement l'app.
    return True
