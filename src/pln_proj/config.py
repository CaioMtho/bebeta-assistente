from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "sim", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


@dataclass(frozen=True)
class AppConfig:
    """Centralized application configuration."""

    db_path: Path
    legacy_notes_path: Path
    embedding_model_name: str
    intent_threshold: float
    ambiguity_margin: float
    tts_enabled: bool
    cache_dir: Path
    open_browser: bool = True

    @classmethod
    def from_env(
        cls,
        *,
        db_path: Path | None = None,
        tts_enabled: bool | None = None,
    ) -> AppConfig:
        base_cache = Path(
            os.getenv("PLN_CACHE_DIR")
            or Path(tempfile.gettempdir()) / "pln_proj_cache"
        )
        resolved_db = db_path or Path(
            os.getenv("PLN_DB_PATH") or "data/pln_proj.db"
        )
        resolved_legacy = Path(
            os.getenv("PLN_LEGACY_NOTES_PATH") or "lembretes.txt"
        )
        resolved_tts = (
            tts_enabled
            if tts_enabled is not None
            else _env_bool("PLN_TTS_ENABLED", True)
        )
        return cls(
            db_path=resolved_db,
            legacy_notes_path=resolved_legacy,
            embedding_model_name=(
                os.getenv("PLN_EMBEDDING_MODEL")
                or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            ),
            intent_threshold=_env_float("PLN_INTENT_THRESHOLD", 0.58),
            ambiguity_margin=_env_float("PLN_AMBIGUITY_MARGIN", 0.03),
            tts_enabled=resolved_tts,
            cache_dir=base_cache,
            open_browser=_env_bool("PLN_OPEN_BROWSER", True),
        )
