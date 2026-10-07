"""Appels Groq : transcription (Whisper) et transformation de texte (LLM).

Pas de SDK, juste requests. Les prompts de transformation renvoient
UNIQUEMENT le texte resultat (pas de blabla autour).
"""
from __future__ import annotations
import logging

import requests

log = logging.getLogger("groq")

URL_STT = "https://api.groq.com/openai/v1/audio/transcriptions"
URL_CHAT = "https://api.groq.com/openai/v1/chat/completions"

# Consignes par action. {contexte} est injecte si l'utilisateur en fournit.
CONSIGNE_BASE = (
    "Tu es un correcteur de francais. On te donne un texte dicte a la voix. "
    "Corrige l'orthographe, la grammaire, les prepositions, les accords, "
    "ajoute la ponctuation et les majuscules. Ne change PAS le sens, "
    "n'ajoute aucune information, ne retire rien d'important. Garde le ton et "
    "le registre d'origine. Reponds UNIQUEMENT par le texte corrige, sans "
    "guillemets, sans commentaire, sans prefixe."
)

CONSIGNES = {
    "nettoyer": CONSIGNE_BASE,
    "reformuler_pro": (
        "Reformule le texte suivant dans un francais professionnel, clair, "
        "fluide et soigne. Garde exactement le sens et les informations. "
        "Reponds UNIQUEMENT par le texte reformule, sans guillemets ni commentaire."
    ),
    "raccourcir": (
        "Raccourcis le texte suivant en gardant l'essentiel et toutes les "
        "informations importantes, en francais correct. Reponds UNIQUEMENT par "
        "le texte raccourci, sans guillemets ni commentaire."
    ),
    "resume": (
        "Resume le texte suivant en quelques phrases claires (ou points si "
        "pertinent), en francais correct. Reponds UNIQUEMENT par le resume, "
        "sans guillemets ni commentaire."
    ),
}


class GroqErreur(Exception):
    pass


# Phrases qu'un modele Whisper "hallucine" sur du silence / audio tres court
# (credits de sous-titrage, incitations vues a l'entrainement).
_HALLUCINATIONS = [
    "sous-titrage", "sous-titres", "soustitreur", "amara.org",
    "merci d'avoir regarde", "merci de votre attention", "abonnez-vous",
    "n'oubliez pas de vous abonner", "radio-canada", "st' 501", "st 501",
    "generique", "merci pour votre ecoute",
]


def _est_hallucination(texte: str) -> bool:
    t = texte.lower().strip()
    if not t:
        return True
    # court ET contient un motif d'hallucination -> on jette
    if len(t) <= 60 and any(m in t for m in _HALLUCINATIONS):
        return True
    # cas ou toute la sortie n'est qu'un de ces credits
    if any(t == m or t.startswith(m) for m in _HALLUCINATIONS):
        return True
    return False


def transcrire(chemin_wav: str, cle: str, modele: str, langue: str = "fr") -> str:
    """Envoie le WAV a Whisper, renvoie le texte brut transcrit."""
    if not cle:
        raise GroqErreur("Cle Groq manquante (Reglages).")
    log.info("Transcription: %s (modele=%s)", chemin_wav, modele)
    with open(chemin_wav, "rb") as f:
        files = {"file": ("audio.wav", f, "audio/wav")}
        data = {"model": modele, "language": langue, "response_format": "text",
                "temperature": "0"}
        r = requests.post(URL_STT, headers={"Authorization": f"Bearer {cle}"},
                          files=files, data=data, timeout=120)
    if r.status_code != 200:
        log.error("STT echec %s: %s", r.status_code, r.text[:300])
        raise GroqErreur(f"Transcription refusee ({r.status_code}).")
    texte = r.text.strip()
    if _est_hallucination(texte):
        log.info("Transcription ignoree (hallucination Whisper): %r", texte[:80])
        return ""
    log.info("Transcription OK (%d caracteres)", len(texte))
    return texte


def transformer(texte: str, action: str, cle: str, modele: str,
                contexte: str = "", consigne_libre: str = "") -> str:
    """Passe le texte dans le LLM selon l'action demandee.

    action: cle de CONSIGNES, ou "libre" pour utiliser consigne_libre.
    """
    if not cle:
        raise GroqErreur("Cle Groq manquante (Reglages).")
    texte = (texte or "").strip()
    if not texte:
        return ""

    if action == "libre" and consigne_libre.strip():
        systeme = (
            consigne_libre.strip()
            + " Reponds UNIQUEMENT par le texte resultat, sans guillemets ni commentaire."
        )
    else:
        systeme = CONSIGNES.get(action, CONSIGNE_BASE)

    if contexte.strip():
        systeme += (
            "\n\nContexte fourni par l'utilisateur (a prendre en compte pour "
            "mieux comprendre, sans le recopier) :\n" + contexte.strip()
        )

    corps = {
        "model": modele,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": systeme},
            {"role": "user", "content": texte},
        ],
    }
    log.info("Transformation action=%s modele=%s (%d car. entree)", action, modele, len(texte))
    r = requests.post(URL_CHAT,
                      headers={"Authorization": f"Bearer {cle}",
                               "Content-Type": "application/json"},
                      json=corps, timeout=120)
    if r.status_code != 200:
        log.error("Chat echec %s: %s", r.status_code, r.text[:300])
        raise GroqErreur(f"Traitement refuse ({r.status_code}).")
    try:
        out = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.error("Reponse chat illisible: %s", e)
        raise GroqErreur("Reponse illisible du modele.")
    # Retire d'eventuels guillemets encadrants.
    if len(out) >= 2 and out[0] in "\"'" and out[-1] == out[0]:
        out = out[1:-1].strip()
    log.info("Transformation OK (%d car. sortie)", len(out))
    return out
