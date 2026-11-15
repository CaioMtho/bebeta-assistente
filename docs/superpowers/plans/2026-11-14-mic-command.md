# Comando `/mic` e `/microfone` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar os comandos `/mic` e `/microfone` na CLI para capturar áudio do microfone, exibir o estado **ouvindo** com barras de volume em tempo real, enviar ao pressionar `Enter`, exibir o texto transcrito e encaminhá-lo ao `AssistantService`.

**Architecture:** Um novo módulo `src/pln_proj/stt.py` isola a captura de áudio (`sounddevice.InputStream`), o cálculo de volume RMS/barras e o reconhecimento de fala (`SpeechRecognition` com Google Web Speech em `pt-BR`). `TerminalUI` (`src/pln_proj/ui.py`) e `run_plain_cli` (`src/pln_proj/__init__.py`) orquestram o estado ao vivo (`rich.live.Live` + leitura de teclas sem bloqueio), mostram o texto entendido (`Você (mic) > ...`) e repassam ao assistente.

**Tech Stack:** Python 3.14, `sounddevice`, `SpeechRecognition`, `numpy`, `rich`, `unittest`

**Spec:** `docs/superpowers/specs/2026-11-14-mic-command-design.md`

## Global Constraints

- `requires-python = ">=3.14"`
- Dependências de voz: `sounddevice>=0.5.0` e `SpeechRecognition>=3.12.0`
- Idioma padrão de transcrição: `pt-BR` (via `PLN_STT_LANGUAGE`)
- Comandos aceitos: `/mic` e `/microfone`
- Fluxo por comando: gravação única -> `Enter` envia (ou `Esc`/`Ctrl+C` cancela) -> exibe transcrição -> envia ao `AssistantService` -> retorna ao prompt normal

---

### Task 1: Configuração STT em `AppConfig`

**Files:**
- Modify: `src/pln_proj/config.py:16-73`
- Test: `tests/test_config_stt.py`

**Interfaces:**
- Produces: `AppConfig.stt_language: str`, `AppConfig.stt_sample_rate: int`

- [ ] **Step 1: Write the failing test**

```python
import os
import unittest
from unittest.mock import patch

from pln_proj.config import AppConfig


class TestAppConfigSTT(unittest.TestCase):
    def test_stt_defaults_and_env_overrides(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = AppConfig.from_env()
            self.assertEqual(cfg.stt_language, "pt-BR")
            self.assertEqual(cfg.stt_sample_rate, 16_000)

        with patch.dict(
            os.environ,
            {"PLN_STT_LANGUAGE": "en-US", "PLN_STT_SAMPLE_RATE": "22050"},
            clear=True,
        ):
            cfg = AppConfig.from_env()
            self.assertEqual(cfg.stt_language, "en-US")
            self.assertEqual(cfg.stt_sample_rate, 22050)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests/test_config_stt.py -v`
Expected: FAIL with `AttributeError: 'AppConfig' object has no attribute 'stt_language'`

- [ ] **Step 3: Implement STT fields in `AppConfig`**

Add `_env_int`, `stt_language: str = "pt-BR"`, and `stt_sample_rate: int = 16_000` in `src/pln_proj/config.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests/test_config_stt.py -v`
Expected: PASS

---

### Task 2: Cálculo de Volume, `MicrophoneRecorder` e `SpeechToTextService`

**Files:**
- Create: `src/pln_proj/stt.py`
- Test: `tests/test_stt.py`

**Interfaces:**
- Consumes: `numpy`, `sounddevice`, `speech_recognition`
- Produces:
  - `compute_rms_level(samples: np.ndarray, *, gain: float = 8.0) -> float`
  - `format_volume_bars(level: float, width: int = 20) -> str`
  - `AudioCaptureResult(pcm_bytes, sample_rate, duration_seconds, cancelled=False, error=None)`
  - `TranscriptionResult(text=None, error=None)`
  - `MicrophoneRecorder(sample_rate=16_000, channels=1, stream_factory=None)`
  - `SpeechToTextService(language="pt-BR", sample_rate=16_000, recognizer=None, recorder_factory=None)`

- [ ] **Step 1: Write failing tests for RMS, volume bars, recorder, and STT service**

Test `compute_rms_level`, `format_volume_bars`, `MicrophoneRecorder` (chunk accumulation, `stop()`, `cancel()`, stream open error), and `SpeechToTextService` (success, short audio, `UnknownValueError`, `RequestError`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests/test_stt.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pln_proj.stt'`

- [ ] **Step 3: Implement `src/pln_proj/stt.py`**

Implement `compute_rms_level`, `format_volume_bars`, `AudioCaptureResult`, `TranscriptionResult`, `MicrophoneRecorder`, and `SpeechToTextService`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests/test_stt.py -v`
Expected: PASS

---

### Task 3: Integração na `TerminalUI` (Estado "Ouvindo", Barras, Enter/Esc, Transcrição)

**Files:**
- Modify: `src/pln_proj/ui.py`
- Test: `tests/test_ui_mic.py`

**Interfaces:**
- Consumes: `SpeechToTextService`, `MicrophoneRecorder`, `format_volume_bars`, `AudioCaptureResult`, `TranscriptionResult` from `pln_proj.stt`
- Produces: `TerminalUI(..., stt=None, key_poller_factory=None)`, `_build_listening_panel(level, elapsed)`

- [ ] **Step 1: Write failing tests for `/mic` and `/microfone` in `TerminalUI`**

Test:
- `/mic` and `/microfone` stop TTS, render `"Ouvindo"` + volume bars, submit on `enter`, print `Você (mic) > <texto>`, call `assistant.handle_message(<texto>)`, and speak response.
- `escape` cancels without calling `assistant.handle_message`.
- Microphone error and STT error print friendly error and keep loop running.
- `/mic` works during pending assistant prompt (`Resposta >`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests/test_ui_mic.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `/mic` and `/microfone` listening flow in `src/pln_proj/ui.py`**

Add `_TerminalKeyPoller`, `_build_listening_panel`, `_capture_mic_input`, and wire `/mic` / `/microfone` in `TerminalUI.run`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests/test_ui_mic.py -v`
Expected: PASS

---

### Task 4: Integração em `build_services`, `run_plain_cli` e `README.md`

**Files:**
- Modify: `src/pln_proj/__init__.py`
- Modify: `README.md`
- Test: `tests/test_plain_cli_mic.py`

**Interfaces:**
- Consumes: `SpeechToTextService`, `AppConfig.stt_language`, `AppConfig.stt_sample_rate`
- Produces: `build_services` returning `(assistant, tts, stt)` and `run_plain_cli(assistant, tts, stt=None, ...)`

- [ ] **Step 1: Write failing tests for `build_services` and `run_plain_cli` `/mic`**

Test `build_services` returns 3-tuple `(assistant, tts, stt)` with configured language/sample rate, and `run_plain_cli` handles `/mic` + `Enter`, displays `Você (mic): <texto>`, and forwards to `assistant.handle_message`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests/test_plain_cli_mic.py -v`
Expected: FAIL

- [ ] **Step 3: Update `src/pln_proj/__init__.py` and `README.md`**

Wire `SpeechToTextService` in `build_services`, `main`, and `run_plain_cli`; document `/mic`, `/microfone`, and `PLN_STT_LANGUAGE` in `README.md`.

- [ ] **Step 4: Run full test suite and verification**

Run: `uv run python -m unittest discover -s tests -v`
Expected: All tests pass with 0 failures and 0 errors.
