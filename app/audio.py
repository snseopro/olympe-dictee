"""Capture micro via sounddevice. Enregistre en 16 kHz mono (ideal Whisper)
et ecrit un WAV temporaire a l'arret.
"""
from __future__ import annotations
import logging
import tempfile
import wave

log = logging.getLogger("audio")

ECH = 16000  # 16 kHz


class Enregistreur:
    def __init__(self):
        self._stream = None
        self._frames = []  # morceaux int16
        self.en_cours = False

    def demarrer(self) -> None:
        import sounddevice as sd

        if self.en_cours:
            return
        self._frames = []

        def rappel(indata, frames, time_info, status):
            if status:
                log.warning("Statut flux audio: %s", status)
            # copie defensive (le buffer est reutilise par portaudio)
            self._frames.append(bytes(indata))

        try:
            self._stream = sd.RawInputStream(
                samplerate=ECH, channels=1, dtype="int16", callback=rappel)
            self._stream.start()
            self.en_cours = True
            log.info("Enregistrement demarre")
        except Exception as e:
            log.exception("Impossible de demarrer l'enregistrement: %s", e)
            self._stream = None
            self.en_cours = False
            raise

    def arreter(self) -> str | None:
        """Stoppe et ecrit un WAV temporaire. Renvoie son chemin (ou None si vide)."""
        if not self.en_cours:
            return None
        self.en_cours = False
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception as e:
            log.warning("Fermeture flux: %s", e)
        self._stream = None

        data = b"".join(self._frames)
        self._frames = []
        if len(data) < ECH * 2 // 5:  # < ~0.2 s : trop court, on ignore
            log.info("Audio trop court (%d octets), ignore", len(data))
            return None

        f = tempfile.NamedTemporaryFile(prefix="olympe_dictee_", suffix=".wav", delete=False)
        chemin = f.name
        f.close()
        with wave.open(chemin, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)  # int16
            w.setframerate(ECH)
            w.writeframes(data)
        log.info("WAV ecrit: %s (%d octets PCM)", chemin, len(data))
        return chemin
