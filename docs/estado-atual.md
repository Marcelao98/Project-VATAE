# Onde estamos (31/10/2026)

Arquivo de passagem de bastão: o que foi feito, o que falta e por onde continuar. Quem pega o projeto
(você ou o Claude Code local) começa por aqui e depois volta ao `CLAUDE.md`.

## 1. Estado do repositório

- **`main` é a verdade de novo.** Até 31/10 o `main` estava parado em 12/10 (0.11.0), e o trabalho
  real estava espalhado em branches. Em 31/10 tudo foi juntado no `main`:
  `linux` (que já continha `ui-*`, `painel`, `captura-tela`, `agente-perito`, `diarizacao`, `lote`,
  `busca`, `glossario`, `srt`, `duvidosos`, `agentes-novos`...) + `perfil-app` + `secretario` +
  `vatty-evolucao` + o commit local "Added a Linux version".
- Versão **0.18.1**. **570 testes, todos verdes** (conferido no Fedora 44 em 31/10, Python 3.14, `.venv`).
- Os branches antigos já estão dentro do `main` e podem ser apagados (ver seção 4).

**Regra daqui pra frente:** cada trabalho num branch curto → PR para o `main` → merge → apaga o
branch. Nunca deixar o trabalho só num branch.

## 2. Roteiro: o que está feito e o que falta confirmar

Itens 1 a 14 do roteiro do `CLAUDE.md` estão **feitos em código e testados com dublês**. O que falta é
**usar de verdade**, com mídia e hardware reais:

| Item | Falta |
|---|---|
| 5, 10, 12 · gravação de som e tela, painel "Começar" (Windows) | confirmar num Windows real |
| 14 · Linux: som pelo PipeWire, tela no Wayland | confirmar no Fedora (você já está gravando: anotar!) |
| 6 · visual `aula` | confirmar com uma aula real; falta o perfil `corte` |
| 7 · separação de falantes | confirmar com vozes reais |
| 8 · Secretário (ata .docx/.pdf) | confirmar numa reunião real |
| 9 · `vatty ui` | usar no PC (só foi conferida na nuvem) |
| 11 · Perito | nunca rodado de verdade |
| 13 · login do navegador no YouTube | não testado |

O roteiro de teste do Fedora já está escrito em `docs/testes-reais.md`, seção
"A fazer: Vatty no Fedora (0.18.0)". **É a prioridade número 1**: sem isso, cada parte nova é construída
em cima de algo que ninguém viu funcionar.

**Andamento no Fedora (31/10):** itens 0 (instalar), 1 (som; microfone precisou baixar para 40%) e 3 (painel
com tela) rodados, anotados em `docs/testes-reais.md`. Novos: `vatty verificar [--instalar]` e `vatty juntar` (um `video.mp4` para enviar).
Também: botão "Gerar slides" na biblioteca e o agente Apresentador (`vatty apresentacao`).
Falta: item 2 inteiro pela CLI (cancelar, Ctrl+C, segunda vez sem perguntar), medir a sincronia, item 4
(YouTube e agentes) e saber por que o `tela.mp4` foi apagado com "Guardar o vídeo da tela".

## 3. Engenharia: como fazer a Vatty crescer (web, desktop, app)

Diagnóstico de 31/10, já sobre a base certa:

- **Back-end:** pacote Python `vatty/`, só com biblioteca padrão + faster-whisper, numpy, yt-dlp
  (extras: gravacao, falantes, ata). Programas externos: ffmpeg, Tesseract, GStreamer.
- **Front-end:** `vatty ui`. Servidor da biblioteca padrão (`vatty/ui/servidor.py`: só 127.0.0.1, token,
  confere o Host) + HTML/CSS/JS puro em `vatty/ui/static/` (arte e `tokens.css` da Vatty).
- **Como os dois conversam:** a fila (`ui/fila.py`) roda a **CLI como subprocesso** (`ui/runner.py`) e
  **lê o texto que ela imprime** com expressões regulares (`RE_PROGRESSO`, `RE_PRONTO`). As perguntas da
  CLI são evitadas mandando a opção pronta (`--texto whisper`...).
- **Agentes:** subagentes do Claude Code (`.claude/agents/`), chamados pela interface via `ui/claude.py`.

O ponto frágil para escalar é a leitura do texto impresso: qualquer mudança numa mensagem da CLI pode
quebrar a interface sem nenhum teste avisar. E a interface não consegue mostrar as perguntas boas da CLI
(os 3 trechos da legenda, o palpite do visual), só escolher por fora.

### Passos sugeridos (um PR cada, nesta ordem)

1. **CI.** GitHub Actions rodando `python -m unittest discover -s tests` em cada push e PR. É barato e
   protege o `main`.
2. **Eventos estruturados em vez de texto.** A CLI ganha `--eventos json`: cada mensagem, progresso,
   aviso, pergunta e "pronto" sai como uma linha JSON. O runner lê JSON em vez de regex. **O subprocesso
   continua**, de propósito: cancelar é matar o processo, e a memória do Whisper volta ao sistema no fim.
3. **Camada de aplicação.** Tirar o fluxo de dentro do `cli.py` (949 linhas) para
   `vatty/aplicacao/pipeline.py`, que chama um `Decisor` (as perguntas) e um `Progresso` (as mensagens),
   sem `print` nem `input`. A CLI implementa os dois no terminal; com `--eventos json`, o mesmo pipeline
   pergunta pela interface (a pergunta vai como evento e a resposta volta pela entrada do processo).
   Fazer **aos poucos**, um fluxo por PR (YouTube, arquivo, gravação, visual), com os testes verdes a
   cada passo. Este desenho já foi feito uma vez sobre a base velha (31/10) e deu certo; a ideia vale,
   o código precisa ser refeito sobre o `cli.py` atual.
4. **`"versao"` no contrato.** Campo `versao` no `fonte.json`, `transcricao.json` e `visual.json`, para
   o app saber se uma pasta antiga é compatível.
5. **Front.** Decidir: migrar `vatty/ui/static/` para React + TypeScript (Vite) ou evoluir o JS atual.
   Sugestão: migrar quando a interface crescer mais (hoje são uns 700 linhas de JS); com os eventos do
   passo 2 o contrato entre os dois já fica claro, e a arte e o `tokens.css` são reaproveitados.
6. **Depois:** desktop (Tauri com o Python ao lado), agentes pela API do Claude usando os mesmos
   `.claude/agents/*.md`, e só então nuvem.

## 4. Instruções para o Claude Code local

Na pasta do projeto, com o `main` atualizado:

```bash
cd ~/Programas/Project-VATAE
git checkout main && git pull
./abrir-vatty.sh          # cria/atualiza o .venv e abre o painel (Ctrl+C para fechar)
```

Testes sempre **com o ambiente da Vatty**, nunca com o Python do sistema (o do sistema não tem o
`numpy`, e quase todos os testes falham na importação):

```bash
.venv/bin/python -m unittest discover -s tests     # esperado: 559 testes OK
```

Limpeza dos branches que já estão no `main` (só apaga os que estão dentro dele: `-d` recusa o resto):

```bash
git branch --merged main | grep -v '^\*\| main$' | xargs -r git branch -d
for b in linux painel perfil-app secretario vatty-evolucao ui-servidor ui-tela ui-revisao ui-instalacao \
         ui-visual captura-tela agente-perito diarizacao lote busca glossario srt duvidosos agentes-novos \
         docs-vatty economia-tokens gravacao-audio-pc gravacao-canais visual-aula renomear-vatty; do
  git merge-base --is-ancestor origin/$b main && git push origin --delete $b
done
```

Depois, abra o `claude` na pasta e cole um destes pedidos:

- **Teste real no Fedora (prioridade):**
  "Leia `docs/estado-atual.md` e `docs/testes-reais.md`. Vamos rodar juntos o roteiro 'A fazer: Vatty no
  Fedora (0.18.0)', passo a passo. Em cada passo, me diga o comando, espere o resultado e anote numa
  entrada nova com a data. Pare no primeiro passo que quebrar."
- **CI (passo 1 da seção 3):**
  "Leia `docs/estado-atual.md`. Faça o passo 1 da seção 3 (CI no GitHub Actions) num branch novo e abra um PR
  para o `main`."
- **Eventos estruturados (passo 2 da seção 3):**
  "Leia `docs/estado-atual.md` e `docs/arquitetura.md`. Faça o passo 2 da seção 3 (`--eventos json` na CLI e
  o runner lendo JSON), mantendo o subprocesso. Rode os testes com `.venv/bin/python`. Branch novo e PR."
