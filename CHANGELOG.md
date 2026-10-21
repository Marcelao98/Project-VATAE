# Changelog

## 0.17.0 — 2026-10-17

Painel "Começar" no `vatty ui`.

- **Painel da Vatty**, a primeira aba: gravar áudio, gravar tela e áudio ou puxar do YouTube; depois só
  transcrever e guardar (local) ou pedir aos agentes. Três modos: **Passo a passo** (padrão), **Bancada** e
  **Estúdio** (gravador com tempo e nível de cada faixa). O modo escolhido fica guardado no navegador.
- **Gravar pela interface**: `vatty/ui/gravador.py` roda `vatty gravar` em segundo plano; o "Parar" cria um
  arquivo vigiado (`vatty gravar --parar-com ARQUIVO`, novo) e a transcrição entra na fila sozinha, com o perfil
  de tela escolhido. Fechar e reabrir a página reencontra a gravação.
- **Agentes pelo Claude Code local**: ao fim da transcrição, o pedido vai para `pedidos.json` e o painel roda
  `claude -p` na pasta do projeto (pedido pelo stdin, só ler e escrever arquivo, sem terminal); o andamento
  ("chamando o agente perito...") aparece na fila e os arquivos escritos aparecem na tela de pronto. Sem Claude
  Code, ou se ele falhar, o texto fica salvo e o pedido fica pendente ("faz os pedidos da Vatty" ou "copiar
  prompt"). Gravar e transcrever não precisam dele. **Provado de verdade na nuvem**: o Escrivão escreveu os
  pontos-chave de uma transcrição curta e o pedido foi marcado como feito.
- **Slides com os prints** (`vatty slides <pasta> --formato html pdf`, e a caixa "Montar slides" no painel): um
  slide por tela do visual, com o print e a fala daquele intervalo. `slides.html` é um arquivo só (imagens
  dentro, setas passam, abre isolado na interface); `slides.pdf` com o reportlab. Sem IA.
- **YouTube "prove que não é robô"**: `--cookies-navegador firefox|edge|chrome...` (e "Entrar como você" no
  painel) usa o login do navegador; o erro agora diz o que fazer.
- Corrigido: POST cujo corpo a rota não lia (Parar, Cancelar, Tentar de novo) deixava o corpo na conexão, e a
  requisição seguinte chegava como `{}GET` (erro 501).
- Checagem de saúde lista o Claude Code (opcional). Biblioteca reconhece `pericia-*.md`, `cartoes-*.md` e
  `legenda.<lang>.srt`.
- **Corrigido no Windows ("Failed to fetch")**: o servidor do Python deixava duas Vattys abrirem a mesma porta,
  e o navegador falava ora com uma, ora com outra. Agora a porta é exclusiva; se a 8765 estiver ocupada, abre
  noutra e avisa. Erros do servidor vão para `vatty-ui-erros.log`, a tela diz quando perdeu a conexão, e link
  recusado mostra o motivo (antes: "Algo deu errado (400)").
- **Gravar e transcrever não dependem mais do Claude Code**: os agentes andam numa pista própria da fila, com
  trabalhador próprio. A transcrição fica pronta na hora; os agentes aparecem como outro item ("Agentes ·
  pasta") e, se o Claude falhar, travar (limite de 30 min) ou não existir, só esse item dá erro.
- **YouTube mais resistente**: quando ele pede "prove que não é robô", a Vatty tenta de novo sozinha por IPv4;
  o erro traz a versão do yt-dlp e se há Deno/Node (para entender por que o terminal funciona e a interface
  não); a tela de erro tem "Tentar de novo entrando pelo navegador"; a saúde avisa se falta o Deno; o
  `abrir-vatty.bat` atualiza o yt-dlp a cada abertura.
- 551 testes (eram 524). Conferido no Chromium da nuvem com uma gravação falsa nos três modos, no celular
  (390 px) e no tema claro, sem erro no console. **Não verificado**: gravar de verdade pelo painel no Windows.

## 0.16.0 — 2026-10-13

Gravação da tela junto com o áudio, perfil `app` para quem testa programa e o agente Perito.

- **`vatty gravar --tela`** (ou `--tela-janela "título"`): o ffmpeg grava a tela em segundo plano em `tela.mp4`,
  sem som, com taxa variável (tela parada não grava nada), até 1920 px. Tela inteira pelo **`ddagrab`** (placa de
  vídeo, até 30 quadros/s); janela, ffmpeg antigo ou `ddagrab` que falha caem no `gdigrab` a 10/s. `--tela-fps`
  muda a taxa. O áudio segue pelo `gravacao.py`.
- **Perfil `app`** (`--visual app`, padrão da gravação com tela): 5 comparações por segundo, eventos `tela`,
  `transitorio` (aviso que pisca) e `movimento` (espera, rolagem); OCR só da região que mudou e tela repetida não é
  lida de novo. O perfil `aula` continua igual.
- Aviso de privacidade antes de começar: a tela pode mostrar senha e conversa de terceiros, e fica só no PC.
- **Sincronia**: cada faixa guarda o horário real de início (`gravacao.json` na pasta da gravação,
  `inicios` no `fonte.json`); os slides são deslocados pela diferença (`sincronia.deslocamento_s` no
  `visual.json`), para o `[mm:ss]` do slide bater com o da fala.
- Com `--transcrever`, o `tela.mp4` passa pelo `--visual` (`app` ou `aula`) e é apagado; `--manter-tela` guarda. Se o visual
  falhar, o texto fica salvo, a gravação inteira fica para tentar de novo e a CLI sai com código 1.
- Gravação sem tela continua igual (sem `gravacao.json`, `fonte.json` sem campos novos).
- Agente novo **Perito** (`.claude/agents/perito.md`): laudo de teste de programa a partir da gravação com tela
  (`pericia-<assunto>.md`: bugs com evidência, gravidade e certeza, lentidão, atrito, comportamento observado e
  passos para reproduzir). "Copiar prompt" da interface ganhou o modelo "Achar bugs". Nunca rodado de verdade.
- README reescrito pelo que a pessoa quer fazer, com todos os agentes, ferramentas e opções.
- 524 testes (eram 493).
- **Não verificado em PC real**: a captura da tela com o ffmpeg de verdade e a sincronia com áudio real só
  rodam no Windows; aqui tudo foi provado com dublês. Passo a passo em `docs/testes-reais.md`.

## 0.15.0 — 2026-10-12

Interface local (`vatty ui`) e os recursos que a alimentam. Tudo roda no computador de quem usa.

- **`vatty ui`**: servidor em biblioteca padrão (127.0.0.1, token por sessão, checagem de Host), fila de um
  worker com progresso ao vivo (SSE), importar por arrastar ou colar links em lote, biblioteca com busca,
  leitor, exportação (`.txt .md .srt .vtt .csv .json`) e um terminal que só roda subcomandos `vatty`.
- **Revisão**: trechos `[?]` em destaque, corrigir uma palavra (e guardar como regra do glossário),
  dar nome a cada `Pessoa N` (`nomes.json`, usado também por `vatty ata`) e "copiar prompt" para qualquer IA.
- `vatty buscar`, `vatty legenda` (.srt/.vtt), `vatty corrigir` e `--glossario`; trechos duvidosos
  (`[?]`, `trechos_duvidosos`).
- `vatty lote <lista.txt|playlist>`: transcreve vários, um erro não para os outros, relatório em JSON
  (`fonte.listar_playlist` expande playlist e canal sem abrir cada vídeo).
- Agentes novos: **Cartas** (flashcards, `vatty cartoes` gera o `.csv` do Anki), **Tradutor** (`vatty traduzir
  preparar|montar`, confere que nenhum bloco sumiu), **Consulta** (`vatty perguntar` escolhe os trechos do acervo e
  o agente responde só com eles) e **Comparador**. O Escrivão faz resumo em níveis. Nenhum agente foi
  executado de verdade ainda: só o código ao redor foi testado.
- Padrão visual da Vatty em `vatty/ui/static/` (`docs/visual.md`).
- **Empacotamento corrigido**: `packages = ["vatty"]` deixava de fora subpacotes e os arquivos da tela;
  agora `vatty.ui` e `static/*` vão no wheel (verificado montando o pacote).
- Primeira execução: a tela avisa o que falta (ffmpeg, modelo, yt-dlp) com a ajuda em português.
- **Não verificado em PC real**: a interface foi conferida com screenshots e testes na nuvem, com um
  executor de mentira; a transcrição de verdade só roda no seu computador.

## 0.14.0 — 2026-10-12

TikTok (e outras URLs) direto, sem baixar o vídeo à mão.

- `fonte.Sessao`: uma URL, uma instância do yt-dlp, **uma leitura da página**. Legenda, áudio e vídeo
  saem do mesmo resultado do extrator. Antes, a segunda abertura da página falhava no TikTok
  ("Unable to extract universal data for rehydration").
- `curl-cffi` virou dependência (`yt-dlp[default,curl-cffi]`): sem ele o TikTok responde
  "Unexpected response from webpage request". O erro agora traz a dica de atualizar.
- `fonte.json`: `tipo: "url"` e `plataforma` para o que não é YouTube (YouTube fica como sempre). A CLI
  deixou de dizer "YouTube" para qualquer URL. O `&t=` dos agentes vale só no YouTube.
- `tests/manual_ytdlp_real.py` prova a leitura única com o yt-dlp de verdade (sem rede), fora do `unittest`.
- **Não verificado no TikTok de verdade**: o TikTok está bloqueado no ambiente em que isto foi feito.

## 0.13.0 — 2026-10-12

Ata de reunião, feita para gastar o mínimo de tokens.

- Agente **Secretário** (`.claude/agents/secretario.md`): escreve só decisões, tarefas, pendências e dúvidas,
  em Markdown de formato fixo e curto, com horário. Sem título, data nem participantes.
- `vatty ata <pasta> [--formato docx pdf] [--nomes "Pessoa 1=Ana"]`: o código monta o cabeçalho (data,
  duração, participantes pela voz), a tabela de tarefas e o `.docx`/`.pdf`, sem LLM.
- Extra `[ata]` (python-docx, reportlab; só Python, sem Word, LaTeX nem pandoc).
- Verificado só com uma ata de teste; falta rodar numa reunião real.

## 0.12.0 — 2026-10-12

Separação de falantes, em dois fluxos.

- `--falantes auto|N|perfis|nao` (padrão `nao`): sem consentimento, agrupa as vozes e rotula `Pessoa N`;
  com perfis cadastrados, reconhece e dá o nome (`Desconhecido` se não bater com ninguém).
- `vatty perfil criar|listar|apagar`: perfil de voz só com consentimento; guarda o vetor, nunca o áudio.
- `falantes.json` na pasta do vídeo e `pessoa` nos segmentos. Em gravação, só o som do PC é separado.
- Extra `[falantes]` (sherpa-onnx); modelos (~29 MB) baixam para o cache, nada entra no repositório.
- Falha na separação vira aviso: o texto nunca se perde. O Escrivão sabe que `Pessoa N` não é nome.
- Validado só com voz sintética em português (4 vozes: todas as falas certas, com `auto` e com N fixo).
  Limiares e modelo (treinado em chinês e inglês) precisam de teste com voz real.

## 0.11.0 — 2026-10-12

Pré-processamento opcional do áudio antes do Whisper (feito pensando em áudio de WhatsApp).

- `--preprocessar perguntar|sim|nao` (padrão `perguntar`): a Vatty mede o áudio (nível da fala,
  relação sinal/ruído, ronco grave, estouro) e, se parecer ruim, pergunta se aplica. Sem terminal,
  só avisa; `sim` força, `nao` pula.
- Cadeia no ffmpeg: mono 16 kHz, `highpass` 80 Hz (dois estágios), `arnndn` (rede neural RNNoise),
  `speechnorm` para subir a fala baixa. Sem o modelo, cai no `afftdn`.
- `--ruido-modelo` escolhe o modelo (nome conhecido ou arquivo `.rnnn`). O modelo baixa uma vez para
  `~/.cache/vatty/rnnoise` (`VATTY_CACHE` muda); nenhum peso entra no repositório.
- O que foi feito fica no cabeçalho do `transcricao.json` (`preprocessamento`); sem uso, nada muda.
- Limiares e parâmetros foram validados só em sinal sintético: ajustar com áudio real.

## 0.10.0 — 2026-10-12

Natty-ATA virou **Vatty** (*Video Audio To Almost Everything*). Só nome e
documentação: nenhum comportamento mudou.

- Pacote `natty_ata` -> `vatty`; projeto `natty-ata` -> `vatty`.
- Comando `ata` -> `vatty`. O `ata` continua instalado como apelido, para não
  quebrar o que já estava em uso.
- README e `CLAUDE.md` com a história da Vatty e a persona da conversa
  principal. A persona não entra nos arquivos dos agentes.
- Escrivão e Preceptor citam a Vatty; os nomes deles não mudam.
- O contrato da pasta do vídeo (`transcricoes/<slug>/`) é o mesmo: o que já foi
  transcrito continua valendo.
- Depois de atualizar: `pip install -e .` de novo para o comando `vatty`
  aparecer.

## 0.9.0 — 2026-10-10

Menos tokens nos agentes. Os agentes gastavam muito: um Escrivão de vídeo de
5 h 20 escreveu um documento de ~54 mil tokens (quase o tamanho da legenda,
~70 mil), lendo o JSON, que tem o dobro dos caracteres do texto.

- **`transcricao.txt` com `[mm:ss]` em cada parágrafo**, em todas as fontes
  (antes, só na linha do tempo da gravação com duas faixas). Os agentes leem
  só ele; do `transcricao.json`, só o cabeçalho, e usam `Grep` quando precisam
  de um horário mais exato (o do parágrafo pode ter até 1 minuto de folga).
- **OCR mais enxuto.** `visual.limpar_ruido`: linha que aparece em 30% ou mais
  dos slides com texto (barra do navegador, abas) sai do texto, e slide sem
  texto útil é descartado e contado. O `visual.json` ganha `ruido_removido` e
  `slides_sem_texto_descartados` no cabeçalho. Os números são chutes, ainda
  não medidos em vídeo real.
- **Escrivão e Preceptor no Sonnet** (`model: sonnet`) e com **extensão**
  (`curto`, `medio`, `completo`; padrão `medio`) para limitar o que escrevem.
  Leem em poucas chamadas e escrevem o arquivo numa só. O Preceptor, com um
  `pontos-chave-*.md` na pasta, não relê a transcrição inteira.
- Fora do pacote Python: nenhuma chamada de LLM foi adicionada.

## 0.8.0 — 2026-10-10

Gravação: canais separados até o fim, horário certo, listas de termos.
Achados numa chamada real de 11 min.

- **Frases partidas.** O texto misturava os segmentos dos dois canais antes de
  montar os parágrafos, e qualquer fala de um lado cortava a frase do outro.
  Agora cada canal vira parágrafos sozinho (mesmas regras de pausa e duração).
  Gravação com duas faixas ganha `transcricao-eu.txt` e `transcricao-outros.txt`
  (`[mm:ss]` por parágrafo; `[h:mm:ss]` a partir de 1 h), e o `transcricao.txt`
  vira a linha do tempo dos dois (`[mm:ss] Outros: ...`). O `transcricao.json`
  não muda de formato; ganha só a lista `faixas` no cabeçalho. YouTube, arquivo
  e gravação com uma faixa ficam exatamente como antes.
- **Horário absurdo.** Um "Aham" saiu com 37 s de duração. Em gravação o motor
  liga o `word_timestamps` e o trecho vale da primeira à última palavra
  (`--horario-por-palavra auto|sim|nao`). Nenhum parâmetro provado mudou.
- **Pontuação do microfone** (investigado, não corrigido): `--vad-silencio-ms`
  experimental, desligado. Explicação no PR.
- `termos/tecnologia-ia.txt` e `termos/girias-brasil.txt`; `--termos` aceita
  vários arquivos (a soma é conferida contra o limite de tokens).
- Escrivão e Preceptor sabem dos arquivos por canal.

## 0.7.0 — 2026-10-10

Visual, perfil "aula": slides + OCR.

- `--visual nenhum|auto|aula` (padrão `nenhum`). Depois do texto, acha as
  trocas de tela do vídeo, lê cada slide com o Tesseract e grava `visual.json`
  (um slide por linha: horário, texto, confiança do OCR, quadro) e `frames/`.
- `auto` mostra um palpite (trocas por minuto, palavras por tela, formato) e
  pergunta, como na legenda. Sem terminal, pede `aula` ou `nenhum`.
- `visual.py`: troca de tela por comparação de quadros (um por segundo), com
  espera de estabilização (animação) e **máscara de movimento por blocos**
  para a câmera do professor não virar "troca". `quadros.py`: ffmpeg.
  `ocr.py`: Tesseract pelo terminal. `aula.py`: junta tudo.
- `fonte.baixar_video`: só imagem, até 720p; arquivo de vídeo local é usado
  direto. Falha no visual não perde o texto (já salvo): avisa e sai com 1.
- O Escrivão e o Preceptor leem o `visual.json` quando existe (sem agente
  novo): citam o que o slide mostra, separado do que foi dito, e tratam OCR de
  baixa confiança como duvidoso.
- Achado no teste com ffmpeg e Tesseract reais: trocar o texto de um slide de
  fundo branco muda só 1% a 2% dos pixels, então o limiar ficou em 0,5%, e a
  câmera passou a ser tratada pela máscara (por bloco: por pixel não pegava).
- Os números (1 s, 0,5%, blocos de 10x10, 300 slides, 8 palavras no palpite)
  foram medidos só em vídeo sintético. Confirmar com vídeo real.
- Ainda falta o perfil `corte` (vídeo curto com cortes rápidos).

## 0.6.0 — 2026-10-10

Gravação do áudio do PC (Windows).

- `gravacao.py` e `ata gravar`: grava o som do PC (loopback WASAPI via
  PyAudioWPatch, extra `.[gravacao]`) e, com `--mic`, o microfone em outra
  faixa. Cada faixa é um `.wav` de 16 kHz mono em `gravacoes/AAAA-MM-DD_HH-MM/`.
- A linha do tempo segue o relógio: quando o Windows não entrega áudio
  (silêncio), a faixa é completada com silêncio, e os horários continuam certos.
- `--transcrever` transcreve ao parar; `ata <pasta-da-gravacao>` transcreve
  depois. As duas faixas viram um texto só, intercalado por horário, com
  `falante` (`eu` / `outros`) em cada segmento e `Eu:` / `Outros:` no `.txt`.
- Depois de transcrever, pergunta se apaga os `.wav` (padrão: guardar);
  `--apagar-audio` e `--manter-audio` pulam a pergunta. Só apaga os `.wav`
  que a própria `ata` criou.
- Aviso quando uma faixa fica quase muda e lembrete de consentimento ao começar.
- `Segmento` ganha `falante` (opcional; fora de gravação nada muda nos arquivos).
- Os agentes passam a registrar quem disse cada coisa quando há `falante`.
- A captura real não tem teste automático (precisa de placa de som no
  Windows): confirmar com `ata gravar --duracao 5`.

## 0.5.0 — 2026-10-10

Passo 4: o Preceptor.

- `.claude/agents/preceptor.md`: subagente que reescreve o vídeo em ordem de
  aprendizado para o nível pedido, com exemplos numéricos conferidos,
  analogias, erros comuns, exercícios com resposta e glossário. Tudo que não
  está no vídeo vem marcado como [acréscimo]; o que está leva o horário.
- Primeiro teste real dos dois agentes: vídeo de notional de opções
  (Escrivão com foco "tudo", Preceptor para iniciante).

## 0.4.0 — 2026-10-10

Lista de termos com proteção contra loop.

- `repeticao.py`: detecta loop do Whisper (texto repetitivo pelo critério de
  compressão do próprio Whisper, eco da lista de termos, frase repetida em
  segmentos seguidos).
- Com `--termos`, o motor refaz só os trechos suspeitos sem a lista e guarda
  cada um em `trechos_refeitos` no `transcricao.json`.
- Aviso quando a lista passa do limite de ~223 tokens que o Whisper usa.
- `termos/mercado-financeiro.txt`: 35 termos de derivativos e opções.

## 0.3.0 — 2026-10-10

Passo 3: o Escrivão.

- `.claude/agents/escrivao.md`: subagente que lê a pasta do vídeo e escreve
  `pontos-chave-<foco>.md`, fiel ao vídeo, com horário e link de cada ponto.
- `fonte.json` ganha os capítulos que o autor marcou e a descrição do vídeo.
- `transcricao.json` com um segmento por linha, para os agentes lerem por
  faixas.
- CLAUDE.md: quem pergunta ao usuário é a conversa principal (subagente não
  conversa); um arquivo por foco; limitação do que só aparece na tela.

## 0.2.0 — 2026-10-10

Passo 2: YouTube, com legenda antes do Whisper.

- `fonte.py`: lê metadados e legendas com o yt-dlp, baixa só a legenda ou só
  o áudio (apagado depois).
- `legenda.py`: escolhe a legenda (manual antes da automática; da automática
  só a original, nunca a traduzida), lê o .vtt sem as linhas repetidas da
  legenda automática e calcula indicadores e trechos para o usuário julgar.
- A CLI mostra os trechos e pergunta: legenda ou Whisper. `--texto` pula a
  pergunta.
- `pasta.py`: cada entrada vira `transcricoes/<nome>/` com `fonte.json`,
  `transcricao.json` (com `origem`) e `transcricao.txt`.
- Parágrafo tem no máximo 60 s (`DURACAO_MAX_PARAGRAFO_S`): fala sem pausa
  virava um bloco só.

## 0.1.0 — 2026-10-10

Passo 1: motor de transcrição extraído do Escriba da Natty.

- `audio.py`: decodifica qualquer áudio/vídeo com ffmpeg (PCM f32le, mono,
  16 kHz) para array numpy; erro claro se o ffmpeg não estiver no PATH.
- `motor.py`: carrega o `large-v3-turbo` (CPU, int8) uma vez só e transcreve
  com `language="pt"`, `vad_filter=True`, `condition_on_previous_text=False`;
  `hotwords` só com arquivo de termos. Devolve segmentos e metadados, com
  callback de progresso.
- `texto.py`: junta segmentos em parágrafos quando a pausa é menor que
  `PAUSA_PARAGRAFO_S` (2 s).
- CLI `ata <arquivo>` com `--modelo`, `--lang`, `--termos` e `--saida`.
