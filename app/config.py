"""Reglages persistes dans %APPDATA%/OlympeDictee/settings.json.

Rien de sensible n'est embarque dans le binaire : la cle Groq est saisie une
fois dans les reglages et stockee localement sur le PC de l'utilisateur.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

from .version import APP_ID

# Valeurs par defaut
DEFAUTS = {
    "groq_api_key": "",
    # Modele texte (nettoyage / reformulation). gpt-oss-120b = qualite, 20b = rapide.
    "modele_texte": "openai/gpt-oss-120b",
    "modele_stt": "whisper-large-v3-turbo",
    "langue": "fr",
    "peripherique_entree": "",  # "" = micro par defaut ; sinon index sounddevice
    # Raccourcis globaux (syntaxe de la lib "keyboard")
    "raccourci_dictee": "ctrl+alt+space",   # dicter la ou est le curseur
    "raccourci_panneau": "ctrl+alt+o",       # ouvrir / masquer le panneau
    # Comportement
    "inserer_automatiquement": True,          # coller le texte au curseur apres dictee
    "mode_saisie": "coller",                  # "coller" (Ctrl+V) ou "taper" (compatible Discord/Electron)
    "beep": True,                             # petit son au debut/fin d'enregistrement
    "demarrer_avec_windows": True,            # lancer l'app au demarrage de Windows
    "verifier_maj_au_demarrage": True,
    # Mise a jour : manifeste distant (rempli au build CI)
    "url_manifeste_maj": "https://raw.githubusercontent.com/snseopro/olympe-dictee/main/latest.json",
}


def dossier_donnees() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d


def chemin_reglages() -> Path:
    return dossier_donnees() / "settings.json"


def charger() -> dict:
    cfg = dict(DEFAUTS)
    p = chemin_reglages()
    try:
        if p.exists():
            charge = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(charge, dict):
                cfg.update({k: v for k, v in charge.items() if k in DEFAUTS})
    except Exception:
        # Reglages corrompus : on repart des defauts plutot que de planter.
        pass
    return cfg


def enregistrer(cfg: dict) -> None:
    p = chemin_reglages()
    propre = {k: cfg.get(k, DEFAUTS[k]) for k in DEFAUTS}
    p.write_text(json.dumps(propre, ensure_ascii=False, indent=2), encoding="utf-8")
