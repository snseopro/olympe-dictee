"""Journalisation vers fichier (pour debugger a distance) + console.

Le fichier de log est le premier reflexe de diagnostic quand l'app tourne sur
le PC de l'utilisateur et pas ici : on lui demande de l'envoyer.
"""
from __future__ import annotations
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from .config import dossier_donnees
from .version import __version__


def init_logs() -> Path:
    dossier = dossier_donnees() / "logs"
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / "app.log"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    # Evite les doublons si init appele deux fois.
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    fh = RotatingFileHandler(fichier, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    try:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    except Exception:
        pass

    logging.info("=== Demarrage Olympe Dictee v%s ===", __version__)
    return fichier
