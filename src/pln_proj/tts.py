from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    from gtts import gTTS
except ImportError:  # pragma: no cover
    gTTS = None

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None

try:
    import pyttsx3
except ImportError:  # pragma: no cover
    pyttsx3 = None


def _select_portuguese_voice(engine) -> None:
    """Select a Portuguese (preferably pt-BR) voice in pyttsx3."""
    voices = engine.getProperty("voices") or []
    priorities = ("pt-br", "pt_br", "brazil", "portuguese", "pt")
    for priority_term in priorities:
        for voice in voices:
            languages = " ".join(
                lang.decode("utf-8", errors="ignore") if isinstance(lang, bytes) else str(lang)
                for lang in (getattr(voice, "languages", None) or [])
            )
            description = (
                f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')} {languages}".lower()
            )
            if priority_term in description:
                engine.setProperty("voice", voice.id)
                return


class SpeechService:
    """Text-to-speech service using cached gTTS audio played via pygame.mixer."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        cache_dir: Path | None = None,
    ) -> None:
        self.enabled = enabled
        self.muted = not enabled
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "pln_proj_tts_cache"
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._mixer_ready: bool | None = None
        self._pyttsx3_engine = None
        self._play_thread: threading.Thread | None = None

    @property
    def mixer_available(self) -> bool:
        return bool(self._ensure_mixer())

    def toggle_mute(self) -> bool:
        """Toggle mute state and stop active playback when muting."""
        self.muted = not self.muted
        if self.muted:
            self.stop()
        return self.muted

    def stop(self) -> None:
        """Stop any ongoing speech playback immediately."""
        self._stop_event.set()
        if self._mixer_ready and pygame is not None:
            try:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
            except Exception:
                pass

    def _ensure_mixer(self) -> bool:
        if pygame is None:
            self._mixer_ready = False
            return False
        if self._mixer_ready is not None:
            return self._mixer_ready
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._mixer_ready = True
        except Exception:
            self._mixer_ready = False
        return self._mixer_ready

    def prepare_gtts_mp3(self, text: str) -> Path | None:
        """Generate or retrieve a SHA-256 cached gTTS MP3 file."""
        if gTTS is None or not text.strip():
            return None
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            cache_path = self.cache_dir / f"{text_hash}.mp3"
            if not cache_path.exists():
                gTTS(text=text, lang="pt", tld="com.br").save(str(cache_path))
            return cache_path
        except Exception:
            return None

    def _play_with_pygame(self, mp3_path: Path) -> bool:
        if not self._ensure_mixer() or pygame is None:
            return False
        try:
            with self._lock:
                self._stop_event.clear()
                pygame.mixer.music.load(str(mp3_path))
                pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stop_event.is_set():
                    pygame.mixer.music.stop()
                    return True
                time.sleep(0.05)
            return True
        except Exception:
            return False

    def _play_with_ffplay(self, mp3_path: Path) -> bool:
        ffplay_bin = shutil.which("ffplay")
        if not ffplay_bin:
            return False
        result = subprocess.run(
            [
                ffplay_bin,
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                "-af",
                "adelay=250|250",
                str(mp3_path),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0

    def _speak_offline(self, text: str) -> None:
        espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
        if espeak_bin:
            try:
                subprocess.run(
                    [espeak_bin, "-v", "pt-br", "-s", "165", "--", text],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception:
                pass

        if pyttsx3 is None:
            return
        try:
            if self._pyttsx3_engine is None:
                engine = pyttsx3.init()
                engine.setProperty("rate", 180)
                _select_portuguese_voice(engine)
                self._pyttsx3_engine = engine
            self._pyttsx3_engine.say(text)
            self._pyttsx3_engine.runAndWait()
        except Exception:
            self._pyttsx3_engine = None

    def speak_sync(self, text: str) -> None:
        """Synthesize and play speech synchronously."""
        if self.muted or not self.enabled or not text.strip():
            return

        mp3_path = self.prepare_gtts_mp3(text)
        if mp3_path is not None:
            if self._play_with_pygame(mp3_path):
                return
            if self._play_with_ffplay(mp3_path):
                return

        if not self._stop_event.is_set():
            self._speak_offline(text)

    def speak(self, text: str, *, blocking: bool = False) -> None:
        """Speak text (non-blocking by default to keep the terminal responsive)."""
        if self.muted or not self.enabled or not text.strip():
            return
        self.stop()
        if blocking:
            self.speak_sync(text)
            return
        thread = threading.Thread(
            target=self.speak_sync,
            args=(text,),
            daemon=True,
            name="pln-tts",
        )
        self._play_thread = thread
        thread.start()
