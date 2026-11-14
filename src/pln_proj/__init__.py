from __future__ import annotations

import argparse
from pathlib import Path
import sys

from pln_proj.assistant import AssistantService
from pln_proj.config import AppConfig
from pln_proj.nlu import SemanticIntentClassifier, SentenceTransformerBackend
from pln_proj.storage import ChatHistoryRepository, Database, NoteRepository
from pln_proj.tts import SpeechService
from pln_proj.ui import TerminalUI


def build_services(
    config: AppConfig,
    *,
    backend=None,
) -> tuple[AssistantService, SpeechService]:
    """Initialize SQLite repositories, semantic classifier, TTS, and assistant service."""
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
    assistant = AssistantService(
        classifier=classifier,
        notes=notes,
        history=history,
        open_browser=config.open_browser,
    )
    return assistant, tts


def run_plain_cli(assistant: AssistantService, tts: SpeechService) -> None:
    """Run a plain text CLI loop without Rich formatting."""
    welcome = assistant.welcome_message()
    print(f"Bebeta: {welcome}")
    tts.speak(welcome, blocking=True)

    while True:
        try:
            user_input = input("Você: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        response = assistant.handle_message(user_input)
        print(f"Bebeta [{response.intent} {response.confidence:.0%}]: {response.text}")
        if response.speak:
            tts.speak(response.text, blocking=response.should_exit)
        if response.should_exit:
            break


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pln-proj",
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
    assistant, tts = build_services(config)

    if args.plain or not sys.stdin.isatty():
        run_plain_cli(assistant, tts)
        return

    model_short = config.embedding_model_name.split("/")[-1]
    ui = TerminalUI(
        assistant=assistant,
        tts=tts,
        model_label=model_short,
    )
    ui.run()


if __name__ == "__main__":
    main()
