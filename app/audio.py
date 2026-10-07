"""Capture micro via sounddevice. Enregistre en 16 kHz mono (ideal Whisper),
expose un niveau en direct (pour l'indicateur de voix) et ecrit un WAV a l'arret.
"""
from __future__ import annotations
import audioop
import logging
import tempfile
import wave

log = logging.getLogger("audio")

ECH = 16000  # 16 kHz
# RMS (0..32768) qui correspond a "barre pleine". Voix normale ~ 800-4000.
_ECHELLE = 3500.0


def lister_entrees():
    """Renvoie [(index, nom)] des peripheriques d'entree disponibles."""
    try:
        import sounddevice as sd
        out = []
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                out.append((i, d.get("name", "Entree %d" % i)))
        return out
    except Exception as e:
        log.warning("Liste des micros impossible: %s", e)
        return []


class Enregistreur:
    def __init__(self):
        self._stream = None
        self._frames = []
        self._niveau = 0.0
        self.en_cours = False

    def demarrer(self, peripherique=None) -> None:
        import sounddevice as sd

        if self.en_cours:
            return
        self._frames = []
        self._niveau = 0.0

        def rappel(indata, frames, time_info, status):
            if status:
                log.warning("Statut flux audio: %s", status)
            b = bytes(indata)
            self._frames.append(b)
            try:
                self._niveau = min(1.0, audioop.rms(b, 2) / _ECHELLE)
            except Exception:
                pass

        try:
            dev = peripherique if peripherique not in (None, "", "defaut") else None
            if isinstance(dev, str) and dev.isdigit():
                dev = int(dev)
            self._stream = sd.RawInputStream(
                samplerate=ECH, channels=1, dtype="int16", device=dev, callback=rappel)
            self._stream.start()
            self.en_cours = True
            try:
                nom = sd.query_devices(dev)["name"] if dev is not None else "defaut"
            except Exception:
                nom = str(dev)
            log.info("Enregistrement demarre (micro=%s)", nom)
        except Exception as e:
            log.exception("Impossible de demarrer l'enregistrement: %s", e)
            self._stream = None
            self.en_cours = False
            raise

    def niveau(self) -> float:
        """Niveau courant 0.0..1.0 (pour l'indicateur de voix)."""
        return self._niveau if self.en_cours else 0.0

    def arreter(self) -> str | None:
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
        # Diagnostic : niveau global de l'enregistrement.
        try:
            rms_global = audioop.rms(data, 2) if data else 0
        except Exception:
            rms_global = -1
        duree = len(data) / 2 / ECH
        log.info("Enregistrement arrete: duree=%.2fs, rms=%s", duree, rms_global)

        if len(data) < ECH * 2 // 5:  # < ~0.2 s
            log.info("Audio trop court (%d octets), ignore", len(data))
            return None
        if rms_global != -1 and rms_global < 60:
            log.warning("Audio quasi silencieux (rms=%s) : micro mal capte ?", rms_global)

        f = tempfile.NamedTemporaryFile(prefix="olympe_dictee_", suffix=".wav", delete=False)
        chemin = f.name
        f.close()
        with wave.open(chemin, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(ECH)
            w.writeframes(data)
        log.info("WAV ecrit: %s (%d octets PCM)", chemin, len(data))
        return chemin
