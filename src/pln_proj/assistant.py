from __future__ import annotations

from dataclasses import dataclass
import datetime
import random
import re
import urllib.parse
import webbrowser

from pln_proj.intents import IntentId
from pln_proj.modules.comandos_respostas import (
    respostas_agradecimento,
    respostas_ambiguo,
    respostas_boas_vindas,
    respostas_conclusao,
    respostas_despedida,
    respostas_identidade,
    respostas_nao_entendi,
    respostas_saudacao,
    texto_funcionalidades,
)
from pln_proj.nlu import (
    ExtractedSlots,
    SemanticIntentClassifier,
    extract_slots,
    has_anotar_cue,
)
from pln_proj.storage import ChatHistoryRepository, Note, NoteRepository

WEEKDAYS_PT = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]

MONTHS_PT = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]

_CANCEL_WORDS = {"cancelar", "cancela", "deixa pra la", "deixa pra lá", "nada", "esquece"}
_CONFIRM_WORDS = {"sim", "s", "confirmo", "confirmar", "pode", "pode apagar", "ok", "claro"}


def format_long_date(reference_date: datetime.date | None = None) -> str:
    """Return the current date formatted in Portuguese."""
    today = reference_date or datetime.date.today()
    weekday_name = WEEKDAYS_PT[today.weekday()]
    month_name = MONTHS_PT[today.month - 1]
    return f"{weekday_name}, {today.day} de {month_name} de {today.year}"


def format_current_time(reference_time: datetime.datetime | None = None) -> str:
    """Return the current time formatted for Portuguese speech."""
    current_time = reference_time or datetime.datetime.now()
    hour_label = "hora" if current_time.hour == 1 else "horas"
    minute_label = "minuto" if current_time.minute == 1 else "minutos"
    return f"Agora são {current_time.hour} {hour_label} e {current_time.minute} {minute_label}."


@dataclass(frozen=True)
class PendingAction:
    """Multi-turn dialog state when a required parameter is missing."""

    kind: str
    note_id: int | None = None


@dataclass(frozen=True)
class AssistantResponse:
    """Structured result from processing a user message."""

    text: str
    intent: str
    confidence: float
    notes_changed: bool = False
    should_exit: bool = False
    speak: bool = True


class AssistantService:
    """Orchestrate semantic NLU, multi-turn dialog state, and note CRUD."""

    def __init__(
        self,
        *,
        classifier: SemanticIntentClassifier,
        notes: NoteRepository,
        history: ChatHistoryRepository | None = None,
        open_browser: bool = True,
    ) -> None:
        self.classifier = classifier
        self.notes = notes
        self.history = history
        self.open_browser = open_browser
        self.pending: PendingAction | None = None

    def welcome_message(self) -> str:
        return random.choice(respostas_boas_vindas)

    def handle_message(self, raw_text: str) -> AssistantResponse:
        """Process a user message and return a structured assistant response."""
        text = raw_text.strip()
        if not text:
            return AssistantResponse(
                text="Digite um comando ou mensagem para continuar.",
                intent=IntentId.DESCONHECIDO.value,
                confidence=0.0,
                speak=False,
            )

        if self.pending is not None:
            response = self._handle_pending(text)
            self._record_turn(text, response)
            return response

        match = self.classifier.classify(text)
        if match.is_ambiguous:
            response = self._ambiguous_response(match.confidence)
        else:
            slots = extract_slots(match.intent, text)
            response = self._dispatch_intent(
                match.intent,
                match.confidence,
                slots,
                raw_text=text,
            )
        self._record_turn(text, response)
        return response

    def _ambiguous_response(self, confidence: float) -> AssistantResponse:
        return AssistantResponse(
            text=random.choice(respostas_ambiguo),
            intent=IntentId.DESCONHECIDO.value,
            confidence=confidence,
        )

    def _record_turn(self, user_text: str, response: AssistantResponse) -> None:
        if self.history is None:
            return
        self.history.add("user", user_text, intent=response.intent, confidence=response.confidence)
        self.history.add("assistant", response.text, intent=response.intent, confidence=response.confidence)

    def _resolve_note(self, slots: ExtractedSlots) -> tuple[Note | None, str | None]:
        """Resolve a note by ID or by textual/semantic search."""
        if slots.note_id is not None:
            note = self.notes.get_by_id(slots.note_id)
            if note is None:
                return None, f"Não encontrei nenhuma anotação com o ID #{slots.note_id}."
            return note, None

        if not slots.query:
            return None, None

        text_matches = self.notes.find_matches(slots.query)
        if text_matches:
            return text_matches[0], None

        all_notes = self.notes.list_all()
        if not all_notes:
            return None, "Sua lista de anotações está vazia."

        ranked = self.classifier.rank_texts(
            slots.query, [n.content for n in all_notes]
        )
        if ranked and ranked[0][1] >= 0.45:
            return all_notes[ranked[0][0]], None

        return None, f"Não encontrei nenhuma anotação parecida com '{slots.query}'."

    def _handle_pending(self, text: str) -> AssistantResponse:
        pending = self.pending
        assert pending is not None

        if text.lower() in _CANCEL_WORDS:
            self.pending = None
            return AssistantResponse(
                text="Tudo bem, ação cancelada.",
                intent="cancelado",
                confidence=1.0,
            )

        if pending.kind == "create_note":
            self.pending = None
            note = self.notes.create(text)
            return AssistantResponse(
                text=f"{random.choice(respostas_conclusao)} Lembrete #{note.id} anotado: {note.content}",
                intent=IntentId.ANOTAR.value,
                confidence=1.0,
                notes_changed=True,
            )

        if pending.kind == "search_query":
            self.pending = None
            return self._perform_search(text, confidence=1.0)

        if pending.kind == "update_target":
            note_id_match = re.search(r"\b(\d+)\b", text)
            slots = ExtractedSlots(
                note_id=int(note_id_match.group(1)) if note_id_match else None,
                query=None if note_id_match else text,
            )
            note, err = self._resolve_note(slots)
            if err or note is None:
                return AssistantResponse(
                    text=err or "Informe o ID ou trecho da anotação que deseja editar.",
                    intent=IntentId.ATUALIZAR_ANOTACAO.value,
                    confidence=1.0,
                )
            self.pending = PendingAction(kind="update_content", note_id=note.id)
            return AssistantResponse(
                text=f"Qual deve ser o novo texto da anotação #{note.id} ('{note.content}')?",
                intent=IntentId.ATUALIZAR_ANOTACAO.value,
                confidence=1.0,
            )

        if pending.kind == "update_content":
            note_id = pending.note_id
            self.pending = None
            assert note_id is not None
            updated = self.notes.update(note_id, content=text)
            if updated is None:
                return AssistantResponse(
                    text=f"A anotação #{note_id} não existe mais.",
                    intent=IntentId.ATUALIZAR_ANOTACAO.value,
                    confidence=1.0,
                )
            return AssistantResponse(
                text=f"Anotação #{updated.id} atualizada para: {updated.content}",
                intent=IntentId.ATUALIZAR_ANOTACAO.value,
                confidence=1.0,
                notes_changed=True,
            )

        if pending.kind == "complete_target":
            self.pending = None
            note_id_match = re.search(r"\b(\d+)\b", text)
            slots = ExtractedSlots(
                note_id=int(note_id_match.group(1)) if note_id_match else None,
                query=None if note_id_match else text,
            )
            return self._complete_note(slots, confidence=1.0)

        if pending.kind == "delete_target":
            self.pending = None
            if text.lower() in {"todos", "todas", "tudo"}:
                self.pending = PendingAction(kind="confirm_clear_all")
                return AssistantResponse(
                    text="Tem certeza que deseja apagar TODAS as anotações? Responda 'sim' para confirmar.",
                    intent=IntentId.EXCLUIR_ANOTACAO.value,
                    confidence=1.0,
                )
            note_id_match = re.search(r"\b(\d+)\b", text)
            slots = ExtractedSlots(
                note_id=int(note_id_match.group(1)) if note_id_match else None,
                query=None if note_id_match else text,
            )
            return self._delete_note(slots, confidence=1.0)

        if pending.kind == "confirm_clear_all":
            self.pending = None
            if text.lower() in _CONFIRM_WORDS:
                removed = self.notes.clear_all()
                return AssistantResponse(
                    text=f"Pronto! {removed} anotação(ões) removida(s).",
                    intent=IntentId.EXCLUIR_ANOTACAO.value,
                    confidence=1.0,
                    notes_changed=removed > 0,
                )
            return AssistantResponse(
                text="Limpeza cancelada. Suas anotações foram mantidas.",
                intent=IntentId.EXCLUIR_ANOTACAO.value,
                confidence=1.0,
            )

        self.pending = None
        return AssistantResponse(
            text=random.choice(respostas_nao_entendi),
            intent=IntentId.DESCONHECIDO.value,
            confidence=0.0,
        )

    def _perform_search(self, query: str, *, confidence: float) -> AssistantResponse:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        if self.open_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        return AssistantResponse(
            text=f"Pesquisando por '{query}' no Google.",
            intent=IntentId.PESQUISAR.value,
            confidence=confidence,
        )

    def _complete_note(self, slots: ExtractedSlots, *, confidence: float) -> AssistantResponse:
        note, err = self._resolve_note(slots)
        if err:
            return AssistantResponse(
                text=err,
                intent=IntentId.CONCLUIR_ANOTACAO.value,
                confidence=confidence,
            )
        if note is None:
            all_notes = self.notes.list_all(include_completed=False)
            if not all_notes:
                return AssistantResponse(
                    text="Não há anotações pendentes para concluir.",
                    intent=IntentId.CONCLUIR_ANOTACAO.value,
                    confidence=confidence,
                )
            self.pending = PendingAction(kind="complete_target")
            return AssistantResponse(
                text="Qual anotação você deseja concluir? Informe o ID ou parte do texto.",
                intent=IntentId.CONCLUIR_ANOTACAO.value,
                confidence=confidence,
            )

        updated = self.notes.update(note.id, completed=not note.completed)
        assert updated is not None
        status_txt = "concluída" if updated.completed else "reaberta"
        return AssistantResponse(
            text=f"Anotação #{updated.id} marcada como {status_txt}: {updated.content}",
            intent=IntentId.CONCLUIR_ANOTACAO.value,
            confidence=confidence,
            notes_changed=True,
        )

    def _delete_note(self, slots: ExtractedSlots, *, confidence: float) -> AssistantResponse:
        if slots.clear_all:
            if not self.notes.list_all():
                return AssistantResponse(
                    text="Sua lista de anotações já está vazia.",
                    intent=IntentId.EXCLUIR_ANOTACAO.value,
                    confidence=confidence,
                )
            self.pending = PendingAction(kind="confirm_clear_all")
            return AssistantResponse(
                text="Tem certeza que deseja apagar TODAS as anotações? Responda 'sim' para confirmar.",
                intent=IntentId.EXCLUIR_ANOTACAO.value,
                confidence=confidence,
            )

        note, err = self._resolve_note(slots)
        if err:
            return AssistantResponse(
                text=err,
                intent=IntentId.EXCLUIR_ANOTACAO.value,
                confidence=confidence,
            )
        if note is None:
            if not self.notes.list_all():
                return AssistantResponse(
                    text="Sua lista de anotações está vazia.",
                    intent=IntentId.EXCLUIR_ANOTACAO.value,
                    confidence=confidence,
                )
            self.pending = PendingAction(kind="delete_target")
            return AssistantResponse(
                text="Qual anotação deseja apagar? Informe o ID ou parte do texto.",
                intent=IntentId.EXCLUIR_ANOTACAO.value,
                confidence=confidence,
            )

        self.notes.delete(note.id)
        return AssistantResponse(
            text=f"Anotação #{note.id} removida: {note.content}",
            intent=IntentId.EXCLUIR_ANOTACAO.value,
            confidence=confidence,
            notes_changed=True,
        )

    def _dispatch_intent(
        self,
        intent: IntentId,
        confidence: float,
        slots: ExtractedSlots,
        *,
        raw_text: str = "",
    ) -> AssistantResponse:
        if intent == IntentId.ENCERRAR:
            return AssistantResponse(
                text=random.choice(respostas_despedida),
                intent=intent.value,
                confidence=confidence,
                should_exit=True,
            )

        if intent == IntentId.FUNCOES:
            return AssistantResponse(
                text=texto_funcionalidades,
                intent=intent.value,
                confidence=confidence,
            )

        if intent == IntentId.ANOTAR:
            if slots.content:
                if not has_anotar_cue(raw_text) and (
                    raw_text.rstrip().endswith("?") or confidence < 0.70
                ):
                    return self._ambiguous_response(confidence)
                note = self.notes.create(slots.content)
                return AssistantResponse(
                    text=f"{random.choice(respostas_conclusao)} Lembrete #{note.id} anotado: {note.content}",
                    intent=intent.value,
                    confidence=confidence,
                    notes_changed=True,
                )
            self.pending = PendingAction(kind="create_note")
            return AssistantResponse(
                text="O que você gostaria de anotar?",
                intent=intent.value,
                confidence=confidence,
            )

        if intent == IntentId.LER_ANOTACOES:
            all_notes = self.notes.list_all()
            if not all_notes:
                return AssistantResponse(
                    text="Você ainda não tem nenhuma anotação salva.",
                    intent=intent.value,
                    confidence=confidence,
                )
            lines = [
                f"#{note.id} [{'✓' if note.completed else ' '}] {note.content}"
                for note in all_notes
            ]
            summary = (
                f"Você tem {len(all_notes)} anotação(ões):\n"
                + "\n".join(lines)
            )
            return AssistantResponse(
                text=summary,
                intent=intent.value,
                confidence=confidence,
            )

        if intent == IntentId.ATUALIZAR_ANOTACAO:
            all_notes = self.notes.list_all()
            if not all_notes:
                return AssistantResponse(
                    text="Você não tem anotações para editar.",
                    intent=intent.value,
                    confidence=confidence,
                )
            note, err = self._resolve_note(slots)
            if err:
                return AssistantResponse(
                    text=err,
                    intent=intent.value,
                    confidence=confidence,
                )
            if note is None:
                self.pending = PendingAction(kind="update_target")
                return AssistantResponse(
                    text="Qual anotação você quer editar? Informe o ID ou parte do texto.",
                    intent=intent.value,
                    confidence=confidence,
                )
            if slots.new_content:
                updated = self.notes.update(note.id, content=slots.new_content)
                assert updated is not None
                return AssistantResponse(
                    text=f"Anotação #{updated.id} atualizada para: {updated.content}",
                    intent=intent.value,
                    confidence=confidence,
                    notes_changed=True,
                )
            self.pending = PendingAction(kind="update_content", note_id=note.id)
            return AssistantResponse(
                text=f"Qual deve ser o novo texto da anotação #{note.id} ('{note.content}')?",
                intent=intent.value,
                confidence=confidence,
            )

        if intent == IntentId.CONCLUIR_ANOTACAO:
            return self._complete_note(slots, confidence=confidence)

        if intent == IntentId.EXCLUIR_ANOTACAO:
            return self._delete_note(slots, confidence=confidence)

        if intent == IntentId.PESQUISAR:
            if slots.query:
                return self._perform_search(slots.query, confidence=confidence)
            self.pending = PendingAction(kind="search_query")
            return AssistantResponse(
                text="O que você gostaria de pesquisar?",
                intent=intent.value,
                confidence=confidence,
            )

        if intent == IntentId.HORAS:
            return AssistantResponse(
                text=format_current_time(),
                intent=intent.value,
                confidence=confidence,
            )

        if intent == IntentId.DATA:
            return AssistantResponse(
                text=f"Hoje é {format_long_date()}.",
                intent=intent.value,
                confidence=confidence,
            )

        if intent == IntentId.EMOCAO:
            return AssistantResponse(
                text="O modo de reconhecimento de emoções está desativado no momento.",
                intent=intent.value,
                confidence=confidence,
            )

        if intent == IntentId.IDENTIDADE:
            return AssistantResponse(
                text=random.choice(respostas_identidade),
                intent=intent.value,
                confidence=confidence,
            )

        if intent == IntentId.SAUDACAO:
            return AssistantResponse(
                text=random.choice(respostas_saudacao),
                intent=intent.value,
                confidence=confidence,
            )

        if intent == IntentId.AGRADECIMENTO:
            return AssistantResponse(
                text=random.choice(respostas_agradecimento),
                intent=intent.value,
                confidence=confidence,
            )

        return AssistantResponse(
            text=random.choice(respostas_nao_entendi),
            intent=IntentId.DESCONHECIDO.value,
            confidence=confidence,
        )
