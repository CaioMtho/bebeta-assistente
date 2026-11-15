from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Callable

from pln_proj.assistant import AssistantService
from pln_proj.config import AppConfig
from pln_proj.nlu import SemanticIntentClassifier, SentenceTransformerBackend
from pln_proj.storage import ChatHistoryRepository, Database, NoteRepository
from pln_proj.stt import (
    MIC_COMMANDS,
    SpeechToTextService,
    TerminalKeyPoller,
    capture_until_key,
    format_volume_bars,
)
from pln_proj.tts import SpeechService
from pln_proj.ui import TerminalUI


def build_services(
    config: AppConfig,
    *,
    backend=None,
) -> tuple[AssistantService, SpeechService, SpeechToTextService]:
    """Initialize SQLite repositories, semantic classifier, TTS, STT, and assistant service."""
    database = Database(config.db_path)
    database.migrate_legacy_txt(config.legacy_notes_path)

    notes = NoteRepository(database)
    history = ChatHistoryRepository(database)

    embedding_backend = backend or SentenceTransformerBackend(config.embedding_model_name)
    classifier = SemanticIntentClassifier(
        embedding_backend,
        threshold=config.intent_threshold,
        ambiguity_margin=config.ambiguity_margin,
        cache_dir=config.cache_dir,
    )
    tts = SpeechService(enabled=config.tts_enabled, cache_dir=config.cache_dir / "tts")
    stt = SpeechToTextService(
        language=config.stt_language,
        sample_rate=config.stt_sample_rate,
    )
    assistant = AssistantService(
        classifier=classifier,
        notes=notes,
        history=history,
        open_browser=config.open_browser,
    )
    return assistant, tts, stt


def _capture_plain_mic_input(
    tts: SpeechService,
    stt: SpeechToTextService,
    key_poller_factory: Callable[[], Any],
) -> str | None:
    tts.stop()
    recorder = stt.create_recorder()
    poller = key_poller_factory()

    def _on_tick(level: float, elapsed: float) -> None:
        bars = format_volume_bars(level, width=16)
        sys.stdout.write(
            f"\rOuvindo [{bars}] {elapsed:.1f}s (Enter envia, Esc/Ctrl+C cancela)"
        )
        sys.stdout.flush()

    capture = capture_until_key(recorder, poller, on_tick=_on_tick)
    sys.stdout.write("\n")
    sys.stdout.flush()

    if capture.error:
        print(f"Bebeta: {capture.error}")
        return None
    if capture.cancelled:
        print("Gravação cancelada.")
        return None

    print("Transcrevendo áudio...")
    result = stt.transcribe(capture.pcm_bytes, sample_rate=capture.sample_rate)
    if result.error or not result.text:
        print(f"Bebeta: {result.error or 'Não foi possível entender o que foi dito.'}")
        return None
    print(f"Você (mic): {result.text}")
    return result.text


def run_plain_cli(
    assistant: AssistantService,
    tts: SpeechService,
    stt: SpeechToTextService | None = None,
    *,
    input_fn: Callable[[str], str] | None = None,
    key_poller_factory: Callable[[], Any] | None = None,
) -> None:
    """Run a plain text CLI loop without Rich formatting."""
    active_stt = stt or SpeechToTextService()
    read_input = input_fn or input
    poller_factory = key_poller_factory or TerminalKeyPoller

    welcome = assistant.welcome_message()
    print(f"Bebeta: {welcome}")
    tts.speak(welcome, blocking=True)

    while True:
        try:
            user_input = read_input("Você: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.strip().lower() in MIC_COMMANDS:
            spoken_text = _capture_plain_mic_input(tts, active_stt, poller_factory)
            if not spoken_text:
                continue
            user_input = spoken_text
        response = assistant.handle_message(user_input)
        print(f"Bebeta [{response.intent} {response.confidence:.0%}]: {response.text}")
        if response.speak:
            tts.speak(response.text, blocking=response.should_exit)
        if response.should_exit:
            break


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bebeta-assistente",
        description="Personal assistant with semantic embeddings, SQLite CRUD, and Rich CLI.",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Run in plain text mode without Rich formatting.",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Disable speech synthesis and audio playback.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Alternative path for the SQLite database file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = AppConfig.from_env(
        db_path=args.db,
        tts_enabled=False if args.no_tts else None,
    )
    assistant, tts, stt = build_services(config)

    if args.plain or not sys.stdin.isatty():
        run_plain_cli(assistant, tts, stt)
        return

    model_short = config.embedding_model_name.split("/")[-1]
    ui = TerminalUI(
        assistant=assistant,
        tts=tts,
        model_label=model_short,
        stt=stt,
    )
    ui.run()


if __name__ == "__main__":
    main()
