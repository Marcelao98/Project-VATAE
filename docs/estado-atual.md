# Onde estamos (03/11/2026)

Arquivo de passagem de bastão: o que foi feito, o que falta e por onde continuar. Quem pega o projeto
(você ou o Claude Code local) começa por aqui e depois volta ao `CLAUDE.md`.

## 1. Estado do repositório

- **`main` = GitHub = 0.20.2** (03/11): Apresentador pelo painel, seguindo as instruções faladas, com `esconder:`
  e o visual "player" em PowerPoint, PDF ou página (exemplo em `exemplos/apresentacao-freddy/`); CI no GitHub
  Actions; roteiro de testes. **610 testes, todos verdes** no Fedora 44 (Python 3.14, `.venv`).
- **Pendente de decisão:** o ramo `ccr-883f2a0c-0pd5sv` (no GitHub) troca a licença MIT pela PolyForm
  Noncommercial 1.0.0 (seria a 0.21.0). Nada foi juntado.
- **Ramos antigos:** 26 ramos do GitHub já estão inteiros dentro do `main` (conferido em 03/11) e podem
  ser apagados com o comando da seção 4. Só o `ccr-…` (licença) tem coisa que o `main` não tem.

**Regra:** cada trabalho num branch curto → PR para o `main` → merge → apaga o branch.

## 2. O que falta: usar de verdade

Os 14 itens do roteiro do `CLAUDE.md` estão **feitos em código e testados com dublês**. O que falta é
**usar com mídia e hardware reais**. A ordem certa (o que depende do quê) está em
**`docs/roteiro-de-testes.md`**; os resultados vão para `docs/testes-reais.md`.

| Item | Situação real (03/11) |
|---|---|
| 0 · instalar no Fedora | **ok** (31/10); `vatty verificar` confere tudo |
| 1 · som no Fedora (PipeWire) | **ok** (31/10); microfone precisou ir para 40% |
| 3 · painel com tela e áudio | **ok** (31/10): Pronto com `visual.json` e laudo do Perito |
| 2 · tela no Wayland pela CLI | falta: permissão lembrada, cancelar, Ctrl+C |
| sincronia tela × fala | falta medir (3 trocas de tela com "agora") |
| `tela.mp4` apagado com "Guardar o vídeo da tela" | **ok** (03/11): ficou guardado |
| 4 · YouTube pelo painel | falta |
| Perito | rodou uma vez (31/10); falta conferir se os bugs têm evidência e nada inventado |
| Apresentador | **ok** (03/11): gravação do Freddy pelo botão novo, seguindo os pedidos falados; falta ver o painel novo (formatos) na tela |
| 6 · visual `aula` | falta aula real; falta o perfil `corte` |
| 7 · falantes | falta vozes reais |
| 8 · Secretário (ata) | falta reunião real |
| 13 · login do navegador no YouTube | falta |
| 5, 10, 12 · Windows | falta um Windows real |

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

1. **CI.** ~~GitHub Actions rodando os testes em cada push e PR.~~ Feito em 03/11 (`.github/workflows/testes.yml`,
   Linux e Windows), no ramo `arrumacao-novembro`.
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
.venv/bin/python -m unittest discover -s tests     # esperado: 593 testes OK
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

- **Testar aos poucos:**
  "Leia `docs/roteiro-de-testes.md`. Vamos fazer o próximo teste que ainda não tem resultado em
  `docs/testes-reais.md`. Me diga o que fazer, espere o resultado e anote numa entrada nova com a data."
- **Eventos estruturados (passo 2 da seção 3):**
  "Leia `docs/estado-atual.md` e `docs/arquitetura.md`. Faça o passo 2 da seção 3 (`--eventos json` na CLI e
  o runner lendo JSON), mantendo o subprocesso. Rode os testes com `.venv/bin/python`. Branch novo e PR."
