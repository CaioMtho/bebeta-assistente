from __future__ import annotations

from dataclasses import dataclass
import os
import select
import sys
import threading
import time
from typing import Any, Callable

import numpy as np

try:
    import termios
    import tty
except ImportError:  # pragma: no cover
    termios = None
    tty = None

try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None

try:
    import speech_recognition as sr
except ImportError:  # pragma: no cover
    sr = None


DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_CHANNELS = 1
MIN_AUDIO_SECONDS = 0.2
MIC_COMMANDS = frozenset({"/mic", "/microfone"})


@dataclass(frozen=True)
class AudioCaptureResult:
    """Result of a microphone capture session."""

    pcm_bytes: bytes
    sample_rate: int
    duration_seconds: float
    cancelled: bool = False
    error: str | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    """Result of speech-to-text transcription."""

    text: str | None = None
    error: str | None = None


def compute_rms_level(samples: np.ndarray, *, gain: float = 8.0) -> float:
    """Compute a clamped normalized RMS volume level in [0.0, 1.0]."""
    if samples.size == 0:
        return 0.0
    if np.issubdtype(samples.dtype, np.integer):
        float_samples = samples.astype(np.float32) / 32768.0
    else:
        float_samples = samples.astype(np.float32)
    rms = float(np.sqrt(np.mean(np.square(float_samples))))
    return min(1.0, max(0.0, rms * gain))


def format_volume_bars(level: float, width: int = 20) -> str:
    """Render a fixed-width volume bar meter from a level in [0.0, 1.0]."""
    clamped = min(1.0, max(0.0, level))
    filled = round(clamped * width)
    return ("█" * filled) + ("░" * (width - filled))


class MicrophoneRecorder:
    """Captures 16-bit PCM audio from the default microphone while tracking volume."""

    def __init__(
        self,
        *,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        stream_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream_factory = stream_factory
        self._lock = threading.Lock()
        self._chunks: list[bytes] = []
        self._level: float = 0.0
        self._started_at: float | None = None
        self._stream: Any | None = None

    @property
    def current_level(self) -> float:
        with self._lock:
            return self._level

    @property
    def elapsed_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        return max(0.0, time.monotonic() - self._started_at)

    def _on_audio(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        arr = np.asarray(indata, dtype=np.int16)
        level = compute_rms_level(arr)
        pcm = arr.tobytes()
        with self._lock:
            self._chunks.append(pcm)
            # Decay smoothly so brief pauses remain visually readable.
            self._level = max(level, self._level * 0.55)

    def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass

    def start(self) -> str | None:
        """Open and start the microphone input stream. Returns an error message on failure."""
        with self._lock:
            self._chunks.clear()
            self._level = 0.0
        self._started_at = time.monotonic()

        factory = self._stream_factory
        if factory is None:
            if sd is None:
                return "Biblioteca 'sounddevice' indisponível para acesso ao microfone."
            factory = sd.InputStream

        try:
            stream = factory(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                callback=self._on_audio,
            )
            self._stream = stream
            stream.start()
            return None
        except Exception as exc:
            self._close_stream()
            return f"Não foi possível acessar o microfone conectado: {exc}"

    def stop(self) -> AudioCaptureResult:
        """Stop capturing and return the recorded PCM audio."""
        self._close_stream()
        with self._lock:
            pcm_bytes = b"".join(self._chunks)
            self._chunks.clear()
            self._level = 0.0
        bytes_per_second = max(1, self.sample_rate * self.channels * 2)
        duration = len(pcm_bytes) / bytes_per_second
        return AudioCaptureResult(
            pcm_bytes=pcm_bytes,
            sample_rate=self.sample_rate,
            duration_seconds=duration,
        )

    def cancel(self) -> AudioCaptureResult:
        """Stop capturing and discard any recorded audio."""
        self._close_stream()
        with self._lock:
            self._chunks.clear()
            self._level = 0.0
        return AudioCaptureResult(
            pcm_bytes=b"",
            sample_rate=self.sample_rate,
            duration_seconds=0.0,
            cancelled=True,
        )


class SpeechToTextService:
    """Speech-to-text service backed by SpeechRecognition (Google Web Speech API)."""

    def __init__(
        self,
        *,
        language: str = "pt-BR",
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        recognizer: Any | None = None,
        recorder_factory: Callable[[], MicrophoneRecorder] | None = None,
    ) -> None:
        self.language = language
        self.sample_rate = sample_rate
        self._recognizer = recognizer
        self._recorder_factory = recorder_factory

    def create_recorder(self) -> MicrophoneRecorder:
        """Build a new microphone recorder configured for this STT service."""
        if self._recorder_factory is not None:
            return self._recorder_factory()
        return MicrophoneRecorder(sample_rate=self.sample_rate)

    def transcribe(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int | None = None,
    ) -> TranscriptionResult:
        """Transcribe 16-bit mono PCM audio bytes into text."""
        rate = sample_rate or self.sample_rate
        min_bytes = int(rate * 2 * MIN_AUDIO_SECONDS)
        if not pcm_bytes or len(pcm_bytes) < min_bytes:
            return TranscriptionResult(
                error="Áudio muito curto ou vazio. Fale um pouco mais antes de pressionar Enter."
            )

        if sr is None:
            return TranscriptionResult(
                error="Biblioteca 'SpeechRecognition' indisponível no ambiente."
            )

        recognizer = self._recognizer if self._recognizer is not None else sr.Recognizer()
        audio_data = sr.AudioData(pcm_bytes, rate, 2)
        try:
            raw_text = recognizer.recognize_google(audio_data, language=self.language)
        except sr.UnknownValueError:
            return TranscriptionResult(
                error="Não consegui entender o que foi dito. Tente falar mais perto do microfone."
            )
        except sr.RequestError as exc:
            return TranscriptionResult(
                error=f"Falha ao acessar o serviço de reconhecimento de fala: {exc}"
            )
        except Exception as exc:
            return TranscriptionResult(
                error=f"Erro inesperado ao transcrever o áudio: {exc}"
            )

        cleaned = str(raw_text).strip()
        if not cleaned:
            return TranscriptionResult(
                error="Não consegui entender o que foi dito. Tente falar mais perto do microfone."
            )
        return TranscriptionResult(text=cleaned)


class TerminalKeyPoller:
    """Non-blocking terminal key reader that detects Enter and Esc/Ctrl+C."""

    def __init__(self) -> None:
        self._fd: int | None = None
        self._old_settings: Any = None

    def __enter__(self) -> TerminalKeyPoller:
        if termios is not None and tty is not None and sys.stdin.isatty():
            try:
                fd = sys.stdin.fileno()
                self._old_settings = termios.tcgetattr(fd)
                tty.setcbreak(fd)
                self._fd = fd
            except Exception:
                self._fd = None
                self._old_settings = None
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._fd is not None and self._old_settings is not None and termios is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)
            except Exception:
                pass
        self._fd = None
        self._old_settings = None

    def poll(self, timeout: float) -> str | None:
        """Poll for a key action: 'enter', 'cancel', or None."""
        if self._fd is None:
            line = sys.stdin.readline()
            return "cancel" if line == "" else "enter"

        ready, _, _ = select.select([self._fd], [], [], timeout)
        if not ready:
            return None
        ch = os.read(self._fd, 1)
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch == b"\x03":
            return "cancel"
        if ch == b"\x1b":
            # Distinguish bare Esc from multi-byte terminal escape sequences (arrows, etc.).
            more, _, _ = select.select([self._fd], [], [], 0.01)
            if more:
                os.read(self._fd, 32)
                return None
            return "cancel"
        return None


def capture_until_key(
    recorder: MicrophoneRecorder,
    poller: Any,
    *,
    on_tick: Callable[[float, float], None] | None = None,
    poll_interval: float = 0.06,
) -> AudioCaptureResult:
    """Start microphone capture and poll until Enter submits or Esc/Ctrl+C cancels."""
    err = recorder.start()
    if err is not None:
        return AudioCaptureResult(
            pcm_bytes=b"",
            sample_rate=recorder.sample_rate,
            duration_seconds=0.0,
            error=err,
        )
    try:
        with poller:
            while True:
                if on_tick is not None:
                    on_tick(recorder.current_level, recorder.elapsed_seconds)
                action = poller.poll(poll_interval)
                if action == "enter":
                    return recorder.stop()
                if action == "cancel":
                    return recorder.cancel()
    except KeyboardInterrupt:
        return recorder.cancel()
