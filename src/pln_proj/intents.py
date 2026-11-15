from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pln_proj.modules.comandos_respostas import (
    comandos_agradecimento,
    comandos_anotar,
    comandos_atualizar_anotacao,
    comandos_como_funciona,
    comandos_concluir_anotacao,
    comandos_data,
    comandos_emocao,
    comandos_encerrar,
    comandos_excluir_anotacao,
    comandos_funcoes,
    comandos_horas,
    comandos_identidade,
    comandos_ler_anotacoes,
    comandos_pesquisar,
    comandos_saudacao,
)


class IntentId(StrEnum):
    """Identifiers for intents recognized by the assistant."""

    FUNCOES = "funcoes"
    COMO_FUNCIONA = "como_funciona"
    ANOTAR = "anotar"
    LER_ANOTACOES = "ler_anotacoes"
    ATUALIZAR_ANOTACAO = "atualizar_anotacao"
    CONCLUIR_ANOTACAO = "concluir_anotacao"
    EXCLUIR_ANOTACAO = "excluir_anotacao"
    PESQUISAR = "pesquisar"
    HORAS = "horas"
    DATA = "data"
    EMOCAO = "emocao"
    IDENTIDADE = "identidade"
    SAUDACAO = "saudacao"
    AGRADECIMENTO = "agradecimento"
    ENCERRAR = "encerrar"
    DESCONHECIDO = "desconhecido"


@dataclass(frozen=True)
class IntentSpec:
    """Definition of an intent and its embedding anchor phrases."""

    id: IntentId
    description: str
    anchors: tuple[str, ...]


INTENT_SPECS: tuple[IntentSpec, ...] = (
    IntentSpec(
        id=IntentId.FUNCOES,
        description="List assistant capabilities and commands",
        anchors=tuple(comandos_funcoes),
    ),
    IntentSpec(
        id=IntentId.COMO_FUNCIONA,
        description="Explain in plain language how the assistant works",
        anchors=tuple(comandos_como_funciona),
    ),
    IntentSpec(
        id=IntentId.ANOTAR,
        description="Create a new note or reminder",
        anchors=tuple(comandos_anotar),
    ),
    IntentSpec(
        id=IntentId.LER_ANOTACOES,
        description="List and read saved notes",
        anchors=tuple(comandos_ler_anotacoes),
    ),
    IntentSpec(
        id=IntentId.ATUALIZAR_ANOTACAO,
        description="Edit the text of an existing note",
        anchors=tuple(comandos_atualizar_anotacao),
    ),
    IntentSpec(
        id=IntentId.CONCLUIR_ANOTACAO,
        description="Mark a note as completed",
        anchors=tuple(comandos_concluir_anotacao),
    ),
    IntentSpec(
        id=IntentId.EXCLUIR_ANOTACAO,
        description="Delete one or all notes",
        anchors=tuple(comandos_excluir_anotacao),
    ),
    IntentSpec(
        id=IntentId.PESQUISAR,
        description="Search for a term in the browser",
        anchors=tuple(comandos_pesquisar),
    ),
    IntentSpec(
        id=IntentId.HORAS,
        description="Report the current time",
        anchors=tuple(comandos_horas),
    ),
    IntentSpec(
        id=IntentId.DATA,
        description="Report the current date",
        anchors=tuple(comandos_data),
    ),
    IntentSpec(
        id=IntentId.EMOCAO,
        description="Emotion analysis mode (disabled)",
        anchors=tuple(comandos_emocao),
    ),
    IntentSpec(
        id=IntentId.IDENTIDADE,
        description="Report assistant name and identity",
        anchors=tuple(comandos_identidade),
    ),
    IntentSpec(
        id=IntentId.SAUDACAO,
        description="Greet the user",
        anchors=tuple(comandos_saudacao),
    ),
    IntentSpec(
        id=IntentId.AGRADECIMENTO,
        description="Respond to thanks",
        anchors=tuple(comandos_agradecimento),
    ),
    IntentSpec(
        id=IntentId.ENCERRAR,
        description="End the conversation",
        anchors=tuple(comandos_encerrar),
    ),
)
