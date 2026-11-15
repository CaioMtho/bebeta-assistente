from __future__ import annotations

from typing import Any, Callable

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pln_proj.assistant import AssistantResponse, AssistantService
from pln_proj.intents import IntentId
from pln_proj.stt import (
    MIC_COMMANDS,
    SpeechToTextService,
    TerminalKeyPoller,
    capture_until_key,
    format_volume_bars,
)
from pln_proj.tts import SpeechService


class TerminalUI:
    """Styled terminal user interface built with Rich."""

    def __init__(
        self,
        *,
        assistant: AssistantService,
        tts: SpeechService,
        model_label: str,
        console: Console | None = None,
        input_fn: Callable[[str], str] | None = None,
        stt: SpeechToTextService | None = None,
        key_poller_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.assistant = assistant
        self.tts = tts
        self.model_label = model_label
        self.console = console or Console()
        self._input_fn = input_fn
        self.stt = stt or SpeechToTextService()
        self._key_poller_factory = key_poller_factory or TerminalKeyPoller

    def _read_input(self, prompt_label: str) -> str:
        if self._input_fn is not None:
            return self._input_fn(prompt_label)
        return self.console.input(prompt_label)

    def render_banner(self) -> None:
        self.console.print("[bold cyan]Bebeta[/]")
        self.console.print(
            "[dim]Comandos:[/] [bold]/ajuda[/]  [bold]/notas[/]  [bold]/mic[/]  "
            "[bold]/microfone[/]  [bold]/mudo[/]  [bold]/parar[/]  [bold]/limpar[/]  [bold]/sair[/]\n"
        )

    def render_help(self) -> None:
        table = Table(
            title="Menu de Comandos e Exemplos",
            border_style="cyan",
            show_lines=False,
        )
        table.add_column("Ação", style="bold cyan", no_wrap=True)
        table.add_column("Exemplos em linguagem natural", style="white")

        rows = [
            ("Criar anotação", "\"me lembre de comprar café\", \"anotar pagar luz\""),
            ("Listar anotações", "\"quais são meus lembretes?\", \"/notas\""),
            ("Editar anotação", "\"editar lembrete 1 para comprar 12 ovos\""),
            ("Concluir anotação", "\"concluir lembrete 1\", \"já fiz a nota dos ovos\""),
            ("Excluir anotação", "\"apagar lembrete 1\", \"remover nota dos ovos\", \"limpar lembretes\""),
            ("Pesquisar", "\"pesquisar sobre python\", \"buscar receita no google\""),
            ("Hora e Data", "\"que horas são?\", \"qual a data de hoje?\""),
            ("Controles do menu", "/ajuda  |  /notas  |  /mic  |  /microfone  |  /mudo  |  /parar  |  /limpar  |  /sair"),
        ]
        for action_label, example_text in rows:
            table.add_row(action_label, example_text)
        self.console.print(table)

    def render_notes_table(self) -> None:
        notes = self.assistant.notes.list_all()
        if not notes:
            self.console.print(
                Panel("Nenhuma anotação salva no momento.", title="Anotações", border_style="dim")
            )
            return

        table = Table(title="Suas Anotações", border_style="blue")
        table.add_column("#", style="bold cyan", justify="right", width=4)
        table.add_column("St", justify="center", width=4)
        table.add_column("Conteúdo", style="white")

        for note in notes:
            status = "[green]✓[/]" if note.completed else "[yellow]•[/]"
            content = f"[strike dim]{note.content}[/]" if note.completed else note.content
            table.add_row(str(note.id), status, content)

        self.console.print(table)

    def render_response(self, response: AssistantResponse) -> None:
        badge = f"{response.intent} · {response.confidence:.0%}"
        if response.intent == IntentId.LER_ANOTACOES.value and self.assistant.notes.list_all():
            self.console.print(f"[bold green]Bebeta[/] [dim]({badge})[/]:")
            self.render_notes_table()
            return

        text = Text()
        text.append("Bebeta ", style="bold green")
        text.append(f"({badge})", style="dim")
        text.append(": ")
        text.append(response.text, style="white")
        self.console.print(text)

    def _handle_slash_command(self, raw_input: str) -> tuple[bool, bool]:
        """Handle a slash command and return `(handled, should_exit)`."""
        command = raw_input.strip().lower()
        if command in {"/ajuda", "/help", "/menu"}:
            self.render_help()
            return True, False
        if command == "/notas":
            self.render_notes_table()
            return True, False
        if command == "/mudo":
            muted = self.tts.toggle_mute()
            audio_state = "[yellow]silenciado[/]" if muted else "[green]reativado[/]"
            self.console.print(f"[dim]Áudio {audio_state}.[/]")
            return True, False
        if command == "/parar":
            self.tts.stop()
            self.console.print("[dim]Reprodução de áudio interrompida.[/]")
            return True, False
        if command == "/limpar":
            self.console.clear()
            self.render_banner()
            return True, False
        if command in {"/sair", "/exit", "/quit"}:
            self.console.print("[bold green]Bebeta:[/] Até mais!")
            return True, True
        return False, False

    def _build_listening_panel(self, level: float, elapsed: float) -> Panel:
        if level < 0.55:
            bar_color = "green"
        elif level < 0.85:
            bar_color = "yellow"
        else:
            bar_color = "red"

        bars = format_volume_bars(level, width=24)
        percent = int(round(min(1.0, max(0.0, level)) * 100))
        content = Text.from_markup(
            f"[bold red]●[/] [bold cyan]Ouvindo...[/] [dim]({elapsed:.1f}s)[/]\n"
            f"Volume: [{bar_color}]{bars}[/] [dim]{percent:3d}%[/]\n"
            "[dim]Pressione Enter para enviar · Esc ou Ctrl+C para cancelar[/]"
        )
        return Panel(content, title="Microfone", border_style="cyan")

    def _capture_mic_input(self) -> str | None:
        """Record audio with a live volume meter and return transcribed text or None."""
        self.tts.stop()
        recorder = self.stt.create_recorder()
        poller = self._key_poller_factory()

        if self.console.is_interactive and not self.console.is_dumb_terminal:
            with Live(
                self._build_listening_panel(0.0, 0.0),
                console=self.console,
                auto_refresh=False,
                transient=True,
            ) as live:
                capture = capture_until_key(
                    recorder,
                    poller,
                    on_tick=lambda lvl, sec: live.update(
                        self._build_listening_panel(lvl, sec),
                        refresh=True,
                    ),
                )
        else:
            rendered_fallback = False

            def _fallback_tick(lvl: float, sec: float) -> None:
                nonlocal rendered_fallback
                if not rendered_fallback:
                    rendered_fallback = True
                    self.console.print(self._build_listening_panel(lvl, sec))

            capture = capture_until_key(recorder, poller, on_tick=_fallback_tick)

        if capture.error:
            self.console.print(f"[yellow]{capture.error}[/]")
            return None
        if capture.cancelled:
            self.console.print("[dim]Gravação cancelada.[/]")
            return None

        with self.console.status("[cyan]Transcrevendo áudio...[/]", spinner="dots"):
            result = self.stt.transcribe(capture.pcm_bytes, sample_rate=capture.sample_rate)

        if result.error or not result.text:
            message = result.error or "Não foi possível entender o que foi dito."
            self.console.print(f"[yellow]{message}[/]")
            return None

        self.console.print(f"[bold blue]Você (mic) >[/] {result.text}")
        return result.text

    def run(self, *, warm_up: bool = True) -> None:
        self.render_banner()
        if warm_up:
            with self.console.status(
                "[cyan]Carregando modelo de embeddings local...[/]",
                spinner="dots",
            ):
                self.assistant.classifier.ensure_ready()

        welcome = self.assistant.welcome_message()
        self.console.print(f"[bold green]Bebeta:[/] {welcome}")
        self.tts.speak(welcome)

        while True:
            prompt_label = (
                "[bold yellow]Resposta > [/]"
                if self.assistant.pending is not None
                else "[bold blue]Você > [/]"
            )
            try:
                raw_input = self._read_input(prompt_label)
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]Encerrando...[/]")
                break

            cleaned = raw_input.strip()
            if not cleaned:
                continue

            if cleaned.lower() in MIC_COMMANDS:
                spoken_text = self._capture_mic_input()
                if not spoken_text:
                    continue
                cleaned = spoken_text
            elif cleaned.startswith("/"):
                handled, should_exit = self._handle_slash_command(cleaned)
                if should_exit:
                    break
                if handled:
                    continue

            self.tts.stop()
            response = self.assistant.handle_message(cleaned)
            self.render_response(response)
            if response.notes_changed and response.intent != IntentId.LER_ANOTACOES.value:
                self.render_notes_table()
            if response.speak:
                self.tts.speak(response.text, blocking=response.should_exit)
            if response.should_exit:
                break
