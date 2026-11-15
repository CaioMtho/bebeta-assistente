# Especificação: Comando `/mic` / `/microfone` para Entrada por Voz

## Objetivo

Adicionar suporte ao comando `/mic` (e alias `/microfone`) na interface CLI da Bebeta para capturar áudio do microfone conectado, exibir o estado **ouvindo** com barras de volume em tempo real, enviar ao pressionar `Enter`, exibir o texto entendido pelo sistema na interface e encaminhá-lo ao `AssistantService`.

## Escopo

- **Comandos aceitos:** `/mic` e `/microfone` (case-insensitive, com espaços aparados), tanto no prompt principal (`Você >`) quanto em prompts de continuação (`Resposta >`), na interface Rich (`TerminalUI`) e no modo texto simples (`--plain`).
- **Fluxo por comando:** cada execução de `/mic` ou `/microfone` realiza uma gravação única, envia para transcrição e retorna ao prompt normal após a resposta da Bebeta.
- **Motor STT:** `SpeechRecognition` usando `Recognizer.recognize_google(..., language="pt-BR")` (configurável via `PLN_STT_LANGUAGE`), recebendo áudio PCM capturado via `sounddevice` (16 kHz, mono, `int16`).

## Arquitetura e Componentes

### 1. Subsistema de Áudio e Transcrição (`src/pln_proj/stt.py`)

Responsável exclusivamente por captura de microfone, cálculo de nível de volume e transcrição de fala, isolado da UI e do `AssistantService`.

- **Constantes e tipos:**
  - `DEFAULT_SAMPLE_RATE = 16_000`
  - `DEFAULT_CHANNELS = 1`
  - `AudioCaptureResult`: `pcm_bytes: bytes`, `sample_rate: int`, `duration_seconds: float`, `cancelled: bool = False`, `error: str | None = None`
  - `TranscriptionResult`: `text: str | None = None`, `error: str | None = None`
- **Cálculo de volume e renderização de barras:**
  - `compute_rms_level(samples: np.ndarray, *, gain: float = 8.0) -> float`: calcula o RMS normalizado em `[0.0, 1.0]` a partir de amostras `int16` ou `float32`, aplicando ganho e clamp para tornar fala normal visível nas barras.
  - `format_volume_bars(level: float, width: int = 20) -> str`: formata a barra de volume em blocos (`█` preenchido / `░` vazio) proporcional ao nível `[0.0, 1.0]`.
- **`MicrophoneRecorder`:**
  - Abre um `sounddevice.InputStream` (ou factory injetável para testes) com callback que acumula os chunks PCM (`int16`) e atualiza o nível RMS atual (com suavização simples para evitar flicker).
  - Expõe `start()`, `stop() -> AudioCaptureResult`, `cancel() -> AudioCaptureResult` e propriedade `current_level: float` + `elapsed_seconds: float`.
  - Converte falhas de dispositivo/PortAudio/importação em mensagens amigáveis em português (`error`), sem lançar exceções não tratadas para o loop principal.
- **`SpeechToTextService`:**
  - `transcribe(pcm_bytes: bytes, sample_rate: int) -> TranscriptionResult`
  - Valida se há áudio útil (duração mínima e bytes não vazios).
  - Cria `speech_recognition.AudioData(pcm_bytes, sample_rate, sample_width=2)` e invoca `recognizer.recognize_google(audio_data, language=self.language)`.
  - Trata `UnknownValueError` ("Não consegui entender o que foi dito. Tente falar mais perto do microfone.") e `RequestError` / falhas de conexão ("Falha ao acessar o serviço de reconhecimento de fala...").

### 2. Configuração (`src/pln_proj/config.py`)

- Adiciona `stt_language: str = "pt-BR"` e `stt_sample_rate: int = 16_000` em `AppConfig`, lidos de `PLN_STT_LANGUAGE` e `PLN_STT_SAMPLE_RATE` (com fallback seguro).

### 3. Interface Terminal Rich (`src/pln_proj/ui.py`)

- **Descoberta do comando:**
  - Banner e tabela `/ajuda` atualizados para incluir `/mic` / `/microfone`.
- **Execução de `/mic` e `/microfone`:**
  1. Interrompe qualquer fala TTS ativa (`self.tts.stop()`) antes de abrir o microfone.
  2. Entra em estado **ouvindo** usando `rich.live.Live` (atualização contínua ~15 Hz) exibindo:
     - Estado explícito: `● Ouvindo...`
     - Barras de volume em tempo real (coloridas conforme intensidade: verde/amarelo/vermelho) e tempo decorrido
     - Instrução de controle: `Enter para enviar · Esc ou Ctrl+C para cancelar`
  3. Lê teclas sem bloquear o loop de atualização (via `termios`/`tty` + `select` em Unix, com injeção de leitor de tecla para testes).
     - `Enter` (`\r` ou `\n`): encerra a gravação para envio.
     - `Esc` (`\x1b`, ignorando sequências ANSI extras se necessário) ou `Ctrl+C` (`\x03`): cancela a gravação e exibe `[dim]Gravação cancelada.[/]` sem chamar o assistente.
  4. Após `Enter`, exibe feedback de processamento (`Transcrevendo...`), chama `stt.transcribe(...)`.
  5. Em caso de erro (microfone indisponível, áudio vazio, fala não reconhecida ou erro de rede), mostra a mensagem de erro no console e retorna ao prompt.
  6. Em caso de sucesso, exibe claramente na interface o que o sistema entendeu:
     `Você (mic) > <texto transcrito>`
  7. Encaminha `<texto transcrito>` para `self.assistant.handle_message(...)`, renderiza a resposta e tabela de notas (se alteradas) e dispara `self.tts.speak(...)` exatamente como uma mensagem digitada.

### 4. Modo Texto Simples (`src/pln_proj/__init__.py`)

- `build_services` passa a construir e retornar `(assistant, tts, stt)` (ou manter assinatura compatível com `stt` opcional/novo helper) para uso tanto na `TerminalUI` quanto em `run_plain_cli`.
- Em `run_plain_cli`: quando o usuário digita `/mic` ou `/microfone`, usa o mesmo gravador/transcritor com barra textual simples em `\r` + `Enter` para enviar, exibe `Você (mic): <texto>` e encaminha para `assistant.handle_message`.

### 5. Dependências e Documentação (`pyproject.toml`, `README.md`)

- `pyproject.toml`: adicionar `sounddevice>=0.5.0` e `SpeechRecognition>=3.12.0`.
- `README.md`: documentar `/mic`, `/microfone` e `PLN_STT_LANGUAGE`.

## Estratégia de Testes

Todos os testes usarão `unittest` (stdlib) com injeção de dependências/mocks para dispositivo de áudio, teclado e reconhecedor:
1. `tests/test_stt.py`:
   - Cálculo de RMS e clamping (`compute_rms_level`) para silêncio, sinal médio e saturação.
   - Formatação da barra de volume (`format_volume_bars`).
   - Fluxo de `MicrophoneRecorder` (captura de chunks, `stop()`, `cancel()`, tratamento de falha de abertura do stream).
   - Fluxo de `SpeechToTextService` (sucesso em `pt-BR`, áudio vazio/curto, `UnknownValueError`, `RequestError`).
2. `tests/test_ui_mic.py`:
   - `/mic` e `/microfone` chamam `tts.stop()`, exibem estado `Ouvindo` e barras de volume, enviam com `Enter`, imprimem o texto entendido (`Você (mic)`), chamam `assistant.handle_message` e reproduzem resposta.
   - Cancelamento por `Esc` ou `Ctrl+C` não envia texto ao assistente.
   - Falhas de microfone ou transcrição exibem erro sem quebrar o loop da CLI.
   - `/mic` funciona em prompt pendente (`Resposta >`).
   - Modo `--plain` também aceita `/mic` / `/microfone`.
