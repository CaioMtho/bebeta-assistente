from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Protocol
import unicodedata

import numpy as np

from pln_proj.intents import INTENT_SPECS, IntentId, IntentSpec


class EmbeddingBackend(Protocol):
    """Protocol for backends that generate L2-normalized text embeddings."""

    model_name: str

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return an (N, D) float32 matrix of L2-normalized vectors."""


class SentenceTransformerBackend:
    """Local embedding backend powered by sentence-transformers."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def warm_up(self) -> None:
        if self._model is not None:
            return

        from sentence_transformers import SentenceTransformer

        try:
            from transformers.utils import logging as hf_logging

            hf_logging.disable_progress_bar()
        except Exception:
            pass

        try:
            # Prefer cached local files to avoid unnecessary HF Hub checks/warnings.
            self._model = SentenceTransformer(self.model_name, local_files_only=True)
        except Exception:
            self._model = SentenceTransformer(self.model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        self.warm_up()
        assert self._model is not None
        vectors = self._model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        return _l2_normalize(arr)


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    if vectors.size == 0:
        return vectors.astype(np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return (vectors / norms).astype(np.float32)


@dataclass(frozen=True)
class IntentCandidate:
    """Score for a single candidate intent."""

    intent: IntentId
    score: float
    best_anchor: str


@dataclass(frozen=True)
class IntentMatch:
    """Result of semantic intent classification for a user message."""

    intent: IntentId
    confidence: float
    best_anchor: str
    candidates: tuple[IntentCandidate, ...] = field(default_factory=tuple)
    is_ambiguous: bool = False


@dataclass(frozen=True)
class ExtractedSlots:
    """Parameters extracted from a natural-language command."""

    content: str | None = None
    query: str | None = None
    note_id: int | None = None
    new_content: str | None = None
    clear_all: bool = False


def _strip_accents(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )


class SemanticIntentClassifier:
    """Classify user intent by cosine similarity against anchor phrases."""

    def __init__(
        self,
        backend: EmbeddingBackend,
        *,
        specs: tuple[IntentSpec, ...] = INTENT_SPECS,
        threshold: float = 0.58,
        ambiguity_margin: float = 0.03,
        cache_dir: Path | None = None,
    ) -> None:
        self.backend = backend
        self.specs = specs
        self.threshold = threshold
        self.ambiguity_margin = ambiguity_margin
        self.cache_dir = cache_dir

        self._anchor_intents: list[IntentId] = []
        self._anchor_texts: list[str] = []
        for spec in specs:
            for anchor in spec.anchors:
                self._anchor_intents.append(spec.id)
                self._anchor_texts.append(anchor)

        self._anchor_matrix: np.ndarray | None = None

    def _cache_paths(self) -> tuple[Path, Path] | None:
        if self.cache_dir is None:
            return None
        payload = json.dumps(
            {
                "model": self.backend.model_name,
                "anchors": [
                    (intent.value, text)
                    for intent, text in zip(self._anchor_intents, self._anchor_texts)
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return (
            self.cache_dir / f"anchors_{digest}.npy",
            self.cache_dir / f"anchors_{digest}.json",
        )

    def ensure_ready(self) -> None:
        """Load cached anchor embeddings (or compute them) and warm up the backend."""
        if self._anchor_matrix is None:
            cache = self._cache_paths()
            if cache is not None:
                npy_path, meta_path = cache
                if npy_path.exists() and meta_path.exists():
                    try:
                        loaded = np.load(npy_path)
                        if loaded.shape[0] == len(self._anchor_texts):
                            self._anchor_matrix = _l2_normalize(loaded)
                    except Exception:
                        pass

            if self._anchor_matrix is None:
                matrix = _l2_normalize(self.backend.encode(self._anchor_texts))
                self._anchor_matrix = matrix

                if cache is not None and matrix.size > 0:
                    npy_path, meta_path = cache
                    try:
                        self.cache_dir.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
                        np.save(npy_path, matrix)
                        meta_path.write_text(
                            json.dumps(
                                {
                                    "model": self.backend.model_name,
                                    "count": len(self._anchor_texts),
                                }
                            ),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass

        warm_up = getattr(self.backend, "warm_up", None)
        if callable(warm_up):
            warm_up()

    def classify(self, text: str) -> IntentMatch:
        """Classify text by cosine similarity against anchor phrases."""
        cleaned = text.strip()
        if not cleaned:
            return IntentMatch(
                intent=IntentId.DESCONHECIDO,
                confidence=0.0,
                best_anchor="",
            )

        self.ensure_ready()
        assert self._anchor_matrix is not None

        words = cleaned.split()
        variants: list[tuple[str, float]] = [(cleaned, 1.0)]
        # Initial word windows prevent semantic dilution when commands carry long payloads.
        if len(words) > 4:
            variants.append((" ".join(words[:4]), 0.95))
            variants.append((" ".join(words[:3]), 0.92))

        variant_vectors = _l2_normalize(
            self.backend.encode([variant_text for variant_text, _ in variants])
        )
        weights = np.array([weight for _, weight in variants], dtype=np.float32)[:, None]
        similarity_matrix = (variant_vectors @ self._anchor_matrix.T) * weights
        similarities = np.max(similarity_matrix, axis=0)

        best_by_intent: dict[IntentId, tuple[float, str]] = {}
        for index, raw_score in enumerate(similarities):
            score = float(raw_score)
            intent = self._anchor_intents[index]
            anchor = self._anchor_texts[index]
            previous = best_by_intent.get(intent)
            if previous is None or score > previous[0]:
                best_by_intent[intent] = (score, anchor)

        ranked = sorted(
            (
                IntentCandidate(intent=intent, score=score, best_anchor=anchor)
                for intent, (score, anchor) in best_by_intent.items()
            ),
            key=lambda candidate: candidate.score,
            reverse=True,
        )

        if not ranked:
            return IntentMatch(IntentId.DESCONHECIDO, 0.0, "")

        top_candidate = ranked[0]
        if top_candidate.score < self.threshold:
            return IntentMatch(
                intent=IntentId.DESCONHECIDO,
                confidence=top_candidate.score,
                best_anchor=top_candidate.best_anchor,
                candidates=tuple(ranked[:3]),
            )

        # Reject ambiguous matches only when confidence is near the threshold.
        if (
            len(ranked) > 1
            and top_candidate.score < self.threshold + 0.10
            and (top_candidate.score - ranked[1].score) < self.ambiguity_margin
        ):
            return IntentMatch(
                intent=IntentId.DESCONHECIDO,
                confidence=top_candidate.score,
                best_anchor=top_candidate.best_anchor,
                candidates=tuple(ranked[:3]),
                is_ambiguous=True,
            )

        return IntentMatch(
            intent=top_candidate.intent,
            confidence=top_candidate.score,
            best_anchor=top_candidate.best_anchor,
            candidates=tuple(ranked[:3]),
        )

    def rank_texts(self, query: str, candidates: list[str]) -> list[tuple[int, float]]:
        """Rank candidate texts by semantic similarity to the query."""
        if not query.strip() or not candidates:
            return []
        query_vector = _l2_normalize(self.backend.encode([query.strip()]))[0]
        candidate_matrix = _l2_normalize(self.backend.encode(candidates))
        similarities = candidate_matrix @ query_vector
        ranked = [(index, float(score)) for index, score in enumerate(similarities)]
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked


_ID_PATTERN = re.compile(r"(?:#|n[úu]mero\s+|num\s+|id\s+)?\b(\d+)\b", re.IGNORECASE)

_ANOTAR_PREFIXES = (
    r"^(?:por favor\s+)?(?:não me deixe esquecer(?:\s+de)?|"
    r"preciso (?:anotar|lembrar)(?:\s+de)?|"
    r"quero (?:anotar|criar|fazer|adicionar|salvar|registrar|escrever)(?:\s+(?:um|uma))?(?:\s+(?:novo|nova))?(?:\s+(?:lembrete|anotação|nota))?(?:\s+(?:de|sobre|que|para|pra))?|"
    r"(?:me\s+)?lembr[ae](?:r)?(?:\s+de)?|"
    r"(?:anot[ae]|anotar|adicion(?:e|ar)|cri(?:e|ar)|salv(?:e|ar)|guard(?:e|ar)|registr(?:e|ar)|escrev(?:a|er))(?:\s+isso)?(?:\s+(?:um|uma))?(?:\s+(?:novo|nova))?(?:\s+(?:lembrete|anotação|nota))?(?:\s+(?:de|sobre|que|para|pra))?|"
    r"(?:novo|nova)\s+(?:lembrete|anotação|nota)(?:\s+(?:de|sobre|para|pra))?)\s*[:\-–]?\s*"
)

_PESQUISAR_PREFIXES = (
    r"^(?:por favor\s+)?(?:me\s+ajud[ae]\s+a\s+pesquisar(?:\s+(?:sobre|por))?|"
    r"(?:quero|preciso|pode|fazer\s+(?:uma)?)\s+pesquis(?:ar|a)(?:\s+no\s+google)?(?:\s+(?:sobre|por))?|"
    r"(?:pesquis[ae]r?|busc(?:a|ar)|procur(?:a|ar)|google)(?:\s+na\s+internet)?(?:\s+no\s+google)?(?:\s+(?:sobre|por|de))?)\s*[:\-–]?\s*"
)

_CLEAR_ALL_RE = re.compile(
    r"\b(todas?\s+(?:as\s+)?(?:notas|anotações)|todos?\s+(?:os\s+)?lembretes|tudo|limpar\s+(?:tudo|lembretes|notas|anotações))\b",
    re.IGNORECASE,
)

_UPDATE_SPLIT_RE = re.compile(
    r"\s+(?:para|pra|por)\s+|(?:\s*[:=]\s*)",
    re.IGNORECASE,
)

_CRUD_STOP_PREFIX = re.compile(
    r"^(?:por favor\s+)?(?:pode\s+)?(?:editar|alterar|atualizar|mudar|corrigir|modificar|substituir|trocar(?:\s+o\s+texto)?|renomear|"
    r"concluir|marcar|finalizar|completar|riscar|dar\s+baixa(?:\s+em|\s+na|\s+no)?|"
    r"apagar|excluir|remover|deletar|tirar|descartar)"
    r"(?:\s+(?:o|a|os|as))?"
    r"(?:\s+(?:lembrete|anotação|anotacao|nota|tarefa))?"
    r"(?:\s+(?:com\s+o\s+texto|sobre|dos|das|do|da|de|número|numero|id|#)(?=\s|$))?\s*",
    re.IGNORECASE,
)

_TRAILING_STATUS_RE = re.compile(
    r"\s+(?:como\s+(?:feita|feito|conclu[ií]da|conclu[ií]do)|da\s+lista)\s*$",
    re.IGNORECASE,
)


def has_anotar_cue(text: str) -> bool:
    """Return True if text begins with an explicit note-creation verb or prefix."""
    return bool(re.match(_ANOTAR_PREFIXES, text.strip(), flags=re.IGNORECASE))


def extract_slots(intent: IntentId, text: str) -> ExtractedSlots:
    """Extract command arguments (content, query, note ID) from Portuguese text."""
    raw = text.strip()
    if not raw:
        return ExtractedSlots()

    if intent == IntentId.ANOTAR:
        content = re.sub(_ANOTAR_PREFIXES, "", raw, count=1, flags=re.IGNORECASE).strip(" .:-")
        if content and _strip_accents(content) not in {"lembrete", "anotacao", "nota", "isso"}:
            return ExtractedSlots(content=content)
        return ExtractedSlots()

    if intent == IntentId.PESQUISAR:
        query = re.sub(_PESQUISAR_PREFIXES, "", raw, count=1, flags=re.IGNORECASE).strip(" ?.!")
        if query and _strip_accents(query) not in {"google", "pesquisa", "duvida", "ajuda"}:
            return ExtractedSlots(query=query)
        return ExtractedSlots()

    if intent in {IntentId.EXCLUIR_ANOTACAO, IntentId.CONCLUIR_ANOTACAO}:
        if intent == IntentId.EXCLUIR_ANOTACAO and _CLEAR_ALL_RE.search(_strip_accents(raw)):
            return ExtractedSlots(clear_all=True)

        id_match = _ID_PATTERN.search(raw)
        if id_match:
            return ExtractedSlots(note_id=int(id_match.group(1)))

        cleaned = _CRUD_STOP_PREFIX.sub("", raw, count=1)
        cleaned = _TRAILING_STATUS_RE.sub("", cleaned).strip(" .:-?!")
        if cleaned and _strip_accents(cleaned) not in {"lembrete", "anotacao", "nota", "tarefa"}:
            return ExtractedSlots(query=cleaned)
        return ExtractedSlots()

    if intent == IntentId.ATUALIZAR_ANOTACAO:
        after_prefix = _CRUD_STOP_PREFIX.sub("", raw, count=1).strip()
        parts = _UPDATE_SPLIT_RE.split(after_prefix, maxsplit=1)
        if len(parts) == 2:
            target_part, new_part = parts[0].strip(" .:-"), parts[1].strip(" .:-")
            target_id_match = _ID_PATTERN.search(target_part)
            resolved_id = int(target_id_match.group(1)) if target_id_match else None
            query = None
            if resolved_id is None:
                target_query = _CRUD_STOP_PREFIX.sub("", target_part, count=1).strip(" .:-")
                if target_query:
                    query = target_query
            return ExtractedSlots(
                note_id=resolved_id,
                query=query,
                new_content=new_part or None,
            )

        id_match = _ID_PATTERN.search(after_prefix) or _ID_PATTERN.search(raw)
        if id_match is not None:
            return ExtractedSlots(note_id=int(id_match.group(1)))
        if after_prefix:
            return ExtractedSlots(query=after_prefix.strip(" .:-"))
        return ExtractedSlots()

    return ExtractedSlots()
