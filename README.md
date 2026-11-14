# bebeta-assistente

Assistente pessoal de linha de comando em português para gerenciar anotações/lembretes, fazer pesquisas no navegador e consultar hora e data.

## O que é

A Bebeta é uma assistente que roda no terminal. Ela entende comandos em linguagem natural (por exemplo, `"me lembre de comprar café"` ou `"editar lembrete 1 para comprar chá"`), mantém suas anotações salvas em um banco SQLite local e pode responder por texto e por voz.

## Como funciona

1. **Reconhecimento de intenção (`src/pln_proj/nlu.py`, `src/pln_proj/intents.py`)**
   - Cada intenção (criar anotação, listar, editar, concluir, excluir, pesquisar, horas, data, etc.) possui uma lista de frases-âncora em `src/pln_proj/modules/comandos_respostas.py`.
   - O modelo local `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` gera embeddings normalizados das âncoras (com cache em disco) e da mensagem digitada.
   - A intenção é escolhida pela maior similaridade de cosseno. Se a pontuação ficar abaixo do limiar (`0.58` por padrão) ou se houver empate próximo entre as duas melhores intenções (ambiguidade), nenhuma ação é executada e a assistente pede para o usuário ser mais específico, listando o que sabe fazer.
   - Para evitar anotações acidentais em perguntas genéricas, a criação direta de nota sem verbo/prefixo explícito de anotação exige confiança mais alta e não aceita frases terminadas em `?`.

2. **Extração de parâmetros e diálogo (`src/pln_proj/nlu.py`, `src/pln_proj/assistant.py`)**
   - Expressões regulares extraem o conteúdo da anotação, o termo de busca ou o ID da nota.
   - Quando falta alguma informação (por exemplo, `"quero anotar"` sem dizer o quê), a assistente guarda o estado pendente e pergunta o restante na mensagem seguinte.

3. **Armazenamento (`src/pln_proj/storage.py`)**
   - As anotações e o histórico de conversa são gravados em SQLite (`data/pln_proj.db` por padrão).
   - A busca de notas aceita ID numérico, trecho do texto (sem diferenciar maiúsculas ou acentos) ou ranqueamento semântico.

4. **Síntese de voz (`src/pln_proj/tts.py`)**
   - Gera áudio com `gTTS` (com cache local por hash SHA-256) e reproduz via `pygame.mixer` (ou `ffplay`, se necessário).
   - Se estiver sem internet ou sem dispositivo de áudio, tenta fallback offline (`espeak-ng`, `espeak` ou `pyttsx3`) sem interromper o programa.

5. **Interface no terminal (`src/pln_proj/ui.py`)**
   - Usa `Rich` para exibir respostas, menu de ajuda e tabela de anotações.
   - Também possui modo texto simples (`--plain`).

## Como usar

### Instalação e execução

```bash
uv sync
uv run bebeta-assistente
```

Opções de linha de comando:

```bash
uv run bebeta-assistente --plain          # modo texto simples, sem Rich
uv run bebeta-assistente --no-tts         # desativa a voz
uv run bebeta-assistente --db outro.db    # usa outro arquivo SQLite
```

### Comandos no chat

Em linguagem natural:
- `"me lembre de comprar café"` / `"anotar pagar luz"`
- `"quais são meus lembretes?"` / `"listar anotações"`
- `"editar lembrete 1 para comprar 12 ovos"`
- `"concluir lembrete 1"` / `"já fiz a nota dos ovos"`
- `"apagar lembrete 1"` / `"apagar todos os lembretes"`
- `"pesquisar sobre python"`
- `"que horas são?"` / `"qual a data de hoje?"`

Atalhos com barra na interface Rich:
- `/ajuda`: mostra a tabela de comandos e exemplos
- `/notas`: exibe a tabela de anotações salvas
- `/mudo`: silencia ou reativa o áudio
- `/parar`: interrompe a fala atual
- `/limpar`: limpa a tela do terminal
- `/sair`: encerra a assistente

### Variáveis de ambiente opcionais

- `PLN_DB_PATH`: caminho do banco SQLite (padrão: `data/pln_proj.db`)
- `PLN_LEGACY_NOTES_PATH`: caminho de arquivo `.txt` legado para importação única (padrão: `lembretes.txt`)
- `PLN_EMBEDDING_MODEL`: modelo do `sentence-transformers` (padrão: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`)
- `PLN_INTENT_THRESHOLD`: limiar mínimo de similaridade de cosseno (padrão: `0.58`)
- `PLN_AMBIGUITY_MARGIN`: diferença mínima entre as duas melhores intenções perto do limiar (padrão: `0.03`)
- `PLN_TTS_ENABLED`: `true` ou `false` para ativar/desativar voz por padrão
- `PLN_OPEN_BROWSER`: `true` ou `false` para abrir pesquisas no navegador
