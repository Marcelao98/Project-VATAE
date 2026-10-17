# Arquitetura detalhada da Vatty

Detalhe por módulo e por agente. O resumo que vale em toda sessão está no `CLAUDE.md`.

### Legenda primeiro, Whisper se o usuário quiser

Para URL de vídeo (YouTube; no TikTok quase nunca há legenda, então vai direto ao Whisper), a primeira coisa é olhar se o vídeo tem legenda no idioma
pedido (`--lang`). Baixar só a legenda leva segundos; transcrever com Whisper
leva minutos. Então:

1. **Sem legenda** → baixa o áudio e transcreve com Whisper.
2. **Com legenda** → baixa só a legenda (sem áudio), preferindo a manual
   (escrita pelo autor) à automática do YouTube.
3. **O usuário decide a qualidade.** O terminal mostra o tipo da legenda
   (manual ou automática), alguns indicadores calculados e 3 trechos de ~30 s
   (começo, meio e fim), e pergunta: usar a legenda ou transcrever com
   Whisper. Os indicadores são só dica (ex.: proporção de pontuação e
   maiúsculas, marcas como `[Música]`); a decisão é sempre do usuário.
4. Escolheu Whisper → só então baixa o áudio.

A legenda vira os mesmos segmentos `{inicio, fim, texto}` do Motor, então
`texto.py` e os agentes não sabem nem precisam saber de onde veio. A legenda
automática do YouTube repete linhas (texto "rolando"); o parser remove as
repetições.

Flag `--texto perguntar|legenda|whisper` (padrão `perguntar`) para pular a
pergunta. Sem terminal interativo, `perguntar` não é permitido: a CLI pede a
flag explícita em vez de escolher sozinha.

### Visual (opcional, depois do texto)

`--visual nenhum|auto|aula` (padrão `nenhum`: nada de vídeo é baixado). O texto
sai e é gravado **primeiro**; o visual vem depois, então uma falha nele (sem
Tesseract, erro do ffmpeg) não perde o texto: a CLI avisa e sai com código 1.
`aula` faz direto; `auto` mostra um palpite (trocas por minuto, palavras por
tela, formato) e pergunta, como na legenda (Enter aceita o palpite; sem
terminal, a CLI pede `aula` ou `nenhum`). URL baixa só a imagem, até 720p
(480p deixa o texto pequeno demais para o OCR), e o vídeo some depois, como o
áudio; arquivo de vídeo local é usado direto. Os números do perfil (1 s entre
quadros, 0,5% de tela mudada, 10x10 de bloco, teto de 300 slides, 8 palavras
no palpite) foram medidos só em vídeo sintético: ajustar com vídeo real.

Perfil `app` (`--visual app`, padrão da gravação com tela): para quem usa ou
testa um programa. O `aula` descarta justamente o que importa num programa (o
aviso que pisca, a tela em branco, a área que muda), então o `app` compara 5
quadros/s, aceita a tela parada 0,4 s, não usa máscara de movimento e não
descarta tela sem texto. Eventos: `tela`, `transitorio` (estado curto seguido da
volta à tela de antes) e `movimento` (mexendo sem parar por 2 s ou mais, sem
OCR). Economia: OCR só da região que mudou quando ela é pequena (até metade da
tela; o quadro salvo também é o recorte) e tela repetida (pela assinatura, uma
grade 18x32 em 8 tons) não é lida de novo (`repetida`, mesmo `frame`). Números
medidos só em quadro sintético.

Em gravação com tela (`vatty gravar --tela --transcrever`, ou `vatty
gravacoes/<pasta> --visual app` depois), o vídeo é o `tela.mp4` da pasta da
gravação, os horários dos eventos passam por `tela.sincronizar` e o `tela.mp4` é
apagado no fim (`--manter-tela` guarda). Se o visual falhar, nada da gravação é
apagado, para tentar de novo.

### Camada de código (`vatty/`)

- `fonte.py`: URL de vídeo (YouTube, TikTok, o que o `yt-dlp` suportar) → `fonte.json`, legendas
  disponíveis, download da legenda, do áudio ou da imagem. `Sessao` = uma URL, **uma instância do
  yt-dlp, uma leitura da página**: os downloads partem do resultado bruto do extrator
  (`process=False`) e rodam na mesma instância (`process_ie_result`), porque o TikTok recusa a
  segunda leitura ("Unable to extract universal data for rehydration"). Partir do `info` já
  processado não serve: ele guarda o formato escolhido na leitura. TikTok também exige o
  `curl-cffi` (imitar navegador), que é dependência. Arquivo local passa direto.
- `legenda.py`: legenda (.vtt) → segmentos; escolha manual × automática;
  amostras e indicadores para o usuário julgar. Lógica pura, sem perguntar
  nada (quem pergunta é a CLI).
- `gravacao.py`: grava o som do PC (loopback WASAPI, PyAudioWPatch, só
  Windows) e o microfone em `.wav` de 16 kHz mono, um por faixa, em
  `gravacoes/AAAA-MM-DD_HH-MM/`. A linha do tempo vem do relógio, não do dado
  (o loopback não entrega nada em silêncio): cada passo escreve o que o
  relógio pede e completa com silêncio. A captura real é a única parte sem
  teste automático; o resto recebe as entradas por parâmetro. Também junta as
  duas faixas transcritas num resultado só, com `falante` e a lista `faixas`.
  Em gravação o motor liga o horário por palavra (`word_timestamps`): o início
  e o fim do trecho valem da primeira à última palavra. `Gravacao.inicio` é o
  horário real (relógio do sistema) em que o relógio das faixas começou; com
  `--tela` ele vai para o `gravacao.json` da pasta (`salvar_metadados`/`ler_metadados`).
- `tela.py`: grava a tela com o ffmpeg em segundo plano, só Windows, sem áudio,
  taxa variável (`-fps_mode vfr`: quadro igual não é gravado), até 1920 px, x264
  `ultrafast` + `zerolatency` + `crf 25`, mp4 fragmentado para sobreviver a uma
  queda. Tela inteira pelo `ddagrab` (Desktop Duplication, GPU, `dup_frames=0`,
  30/s, ffmpeg 6.1+); janela, ffmpeg sem `ddagrab` (`ffmpeg -filters`) ou
  `ddagrab` que fecha logo caem no `gdigrab` a 10/s com `mpdecimate` (`aviso`).
  O ffmpeg roda num grupo de processo próprio (o Ctrl+C da gravação não o
  derruba) e para com `q` no stdin. O horário real do primeiro quadro vem do
  `-progress` a cada 0,1 s (`-stats_period`): no primeiro relatório com
  `frame >= 1`, horário do relatório menos o `out_time` já escrito; sem
  relatório em 10 s, fica o horário em que abriu (`inicio_aproximado`). A tela abre **antes** do áudio: o áudio aberto antes
  acumularia a espera do ffmpeg. `deslocamento` (início da tela menos o do
  áudio) e `sincronizar` (soma aos eventos do visual, corta no zero) são puros.
  A captura real não tem teste automático (ver `docs/testes-reais.md`).
- `quadros.py`: vídeo → quadros via ffmpeg: um quadro pequeno em cinza a cada
  intervalo (em fluxo, nunca vai ao disco) e a extração de um quadro JPG em
  boa qualidade num horário (inteiro ou só um `recorte`).
- `app.py`: perfil `app` (ver "Visual"). `detectar_eventos`, `regiao_mudada` e
  `assinatura` são puros; `montar` usa as `aula.Ferramentas`.
- `visual.py`: lógica pura do perfil "aula". Acha as trocas de tela comparando
  cada quadro com o último slide aceito; só aceita a troca depois que a tela
  estabiliza (espera a animação). Regiões que mexem o tempo todo (câmera do
  professor, ruído) são ignoradas por uma máscara de movimento por blocos.
  Junta slides vizinhos com texto quase igual; dá o palpite do perfil. Também
  limpa o OCR (`limpar_ruido`): linha que aparece em 30% ou mais dos slides com
  texto (barra do navegador, abas) sai do texto, e slide que fica sem texto é
  descartado e contado.
- `ocr.py`: Tesseract chamado pelo terminal (sem pytesseract), com a confiança
  por palavra. Confere programa e idiomas antes de processar o vídeo.
- `aula.py`: junta `quadros`, `visual` e `ocr`: `detectar` (uma passada),
  `palpite` (OCR em até 4 slides) e `montar` (todos os slides → `visual.json`
  e `frames/`).
- `slides.py`: `visual.json` + `frames/` + segmentos → slides (um por quadro; telas seguidas com o mesmo
  quadro viram um; cada segmento vai para a tela aberta quando ele começou). `slides.html` com as imagens em
  base64 (portátil) e `slides.pdf` (reportlab, A4 deitada). A interface serve o HTML com
  `Content-Security-Policy: sandbox allow-scripts`: abre na aba, mas sem acesso à API.
- `fonte.py` lê `VATTY_COOKIES_NAVEGADOR` (a CLI preenche com `--cookies-navegador`) e passa
  `cookiesfrombrowser` ao yt-dlp, para quando o YouTube pede login.
- `audio.py`: arquivo → array float32 mono 16 kHz via ffmpeg (aceita um filtro `-af`).
- `diarizar.py`: separação de falantes, lógica pura (o modelo de voz entra por parâmetro). Janelas de
  2 s → vetores → `agrupar` (average linkage, corte por similaridade ou N fixo) ou `reconhecer` (perfis);
  `montar_turnos`, `atribuir` (o segmento do Whisper vai para quem mais falou nele), `vetor_de_perfil`.
- `vozes.py`: o modelo de voz de verdade (sherpa-onnx: Silero VAD + CAM++), baixado para o cache; sem
  teste automático, como a captura de áudio. Extra opcional `[falantes]`.
- `perfis.py`: perfis de voz de quem consentiu (só o vetor, nunca o áudio; criar sem consentimento é
  recusado; `apagar`). Fora do repositório (`~/.vatty/perfis`).
- `preprocessar.py`: etapa opcional antes do Whisper (`--preprocessar`). Mede o áudio (nível, SNR,
  ronco, estouro), pergunta se recomendado e aplica `highpass` x2 → `speechnorm` → `arnndn` na
  decodificação. Modelo `.rnnn` baixado para o cache (nunca no repositório); sem ele, `afftdn`.
  Registra `preprocessamento` no cabeçalho do `transcricao.json`. O `arnndn` fica por último:
  no ffmpeg 9.0.2, filtro depois dele trava ou dá segfault. **Não usar em sussurro nem com
  música de fundo:** no teste real (12/10/2026, conversa sussurrada com música) o Whisper caiu
  de ~190 para ~70 palavras com ele, e para 2 palavras somado a VAD tolerante. Sem ele e com o
  VAD padrão foi o melhor resultado. Ainda falta testar no caso para o qual foi feito (voz baixa
  de WhatsApp, ronco).
- `motor.py`: array → segmentos (faster-whisper `large-v3-turbo`, CPU, int8).
- `repeticao.py`: sinais de loop do Whisper (com `hotwords`); o motor refaz
  esses trechos sem os termos.
- `ata.py`: o `ata-*.md` do Secretário → `.docx` (python-docx) e `.pdf` (reportlab), extra opcional
  `[ata]`. Lê um subconjunto fixo de Markdown, monta o cabeçalho sem LLM, troca `Pessoa N` por nomes
  (`--nomes "Pessoa 1=Ana"`) e faz a tabela de tarefas. Quem escreve o conteúdo é o agente; quem
  formata é o código (é aí que se economizam tokens).
- `texto.py`: segmentos → parágrafos. Em gravação com duas faixas, um canal
  por vez (`por_canal`), `formatar_canal` (`[mm:ss]` por parágrafo) e
  `linha_do_tempo`.
- `cli.py`: casca fina. `vatty <url-arquivo-ou-pasta-de-gravacao>` produz a pasta
  do vídeo; `vatty gravar` grava (e com `--transcrever` já transcreve; com `--tela`
  ou `--tela-janela`, avisa da privacidade e grava a tela também). Depois de
  transcrever uma gravação, pergunta se apaga os `.wav` (padrão: guardar).

### Camada de agentes (`.claude/agents/`)

Subagentes do Claude Code. Cada um lê a pasta do vídeo e escreve um `.md`
nela. São chamados conforme a necessidade, nunca em cadeia automática.

**Quem conversa com o usuário é a conversa principal, nunca o subagente.**
Um subagente roda isolado e só devolve o resultado no fim, então não pode
parar para perguntar. Por isso a conversa principal:

1. descobre a pasta do vídeo (lista `transcricoes/`; se houver mais de uma
   candidata, pergunta);
2. pergunta o que o agente precisa saber, sugerindo opções a partir dos
   capítulos do `fonte.json` (foco para o Escrivão, nível e tema para o
   Preceptor) e a **extensão** (`curto`, `medio` ou `completo`; sem resposta,
   `medio`);
3. chama o subagente com um briefing completo: pasta, foco ou nível,
   extensão, arquivo de saída e a data de hoje;
4. repassa ao usuário o resumo curto que o agente devolveu e o caminho do
   arquivo. O documento em si fica na pasta, não na conversa.

**Custo (tokens).** Os três agentes rodam no **Sonnet** (`model: sonnet` no
arquivo de cada um): extrair e reorganizar texto não pede o modelo mais caro. O
que mais custa é o que eles escrevem, então a **extensão** limita o tamanho
(`curto`: até 15 pontos; `medio`, o padrão: até 5 por capítulo; `completo`: sem
limite), e eles escrevem o arquivo numa chamada só. Leem o `transcricao.txt`
(com `[mm:ss]` por parágrafo, metade dos caracteres do `.json`) e do
`transcricao.json` só o cabeçalho; para um horário mais exato, usam `Grep`. O
código também enxuga o `visual.json` (linhas fixas de OCR e slides sem texto
saem). Tudo isso sem LLM no pacote.

O subagente mantém o contexto isolado: a transcrição de 1 h tem uns 20 mil
tokens e não deve encher a conversa principal. Até uns 3 h de vídeo a
transcrição inteira cabe no contexto de um agente; não há divisão em pedaços.

Nome do arquivo de saída: prefixo do agente + slug do foco (minúsculas, sem
acento, hífens, até ~40 caracteres). Foco "tudo" vira `pontos-chave-geral.md`.
Pedir de novo com o mesmo foco sobrescreve; foco diferente gera outro arquivo.

- **Escrivão** (`escrivao.md`): registro fiel. Extrai pontos-chave,
  definições, números, nomes e referências dentro do foco, cada um com o
  horário (link `&t=` no YouTube), seguindo os capítulos do autor quando há.
  Não acrescenta conhecimento de fora e não explica: se o vídeo não diz, o
  Escrivão não diz. Lista os trechos que a transcrição provavelmente errou.
- **Preceptor** (`preceptor.md`): didática. Pega um conteúdo difícil (ex.: uma aula densa de
  matemática) e reconstrói em ordem de aprendizado: pré-requisitos, intuição
  antes da fórmula, exemplos, analogias, exercícios com resposta. Pode usar
  conhecimento de fora, mas marca o que é acréscimo dele e o que é do vídeo.
  Se já existir um `pontos-chave-*.md` na pasta, usa como mapa; se não,
  lê a transcrição direto. Nunca exige que o Escrivão rode antes.

- **Secretário** (`secretario.md`): ata de reunião. Escreve só decisões, tarefas (responsável,
  prazo), pendências e dúvidas, cada uma com horário, em Markdown de formato fixo e o mais curto
  possível: título, data, duração, participantes e o arquivo `.docx`/`.pdf` são do código
  (`vatty ata`). Nunca presume o nome de uma `Pessoa N`; não decide o que a reunião não decidiu.
  A conversa principal pergunta a extensão e quem é cada `Pessoa N` (mostrando quanto cada uma
  falou), chama o agente e depois roda `vatty ata <pasta> --nomes ... --formato docx`.

Os papéis são separados de propósito: um é fiel ao vídeo, o outro é
livre para ensinar. Misturar os dois num agente só faz o resumo inventar e a
explicação ficar presa ao texto.

**O que está só na tela.** Aulas mostram fórmulas e listas que o professor
não fala ("isso aqui vezes isso"), e a transcrição perde isso. Com
`--visual`, o código extrai os slides e lê o texto por OCR (`visual.json`);
os agentes citam o que o slide mostra, sempre separado do que foi dito, e
tratam OCR de baixa confiança como duvidoso. **Sem agente novo:** o Escrivão e
o Preceptor leem o `visual.json` quando existe; sem ele, nada muda. Gráfico
e imagem não viram texto: continua valendo "estava na tela".

Perfis de visual: `aula` (feito: slides + OCR). Falta o `corte` (vídeo curto,
com cortes rápidos: poucos quadros para um agente olhar). O palpite do
`--visual auto` já reconhece esse caso e avisa que ainda não existe.

Agente novo em `.claude/agents/` só aparece depois de reiniciar a sessão do
Claude Code. Na mesma sessão em que foi criado, chame um agente genérico
instruído a ler e seguir o arquivo do agente.

Novos agentes entram como novos arquivos em `.claude/agents/` e novos `.md`
na pasta do vídeo, sem mexer no código (ex.: um que gera flashcards, um que
compara dois vídeos). Não criar agente novo sem necessidade real.


- `buscar.py`: acha um termo (sem acento nem maiúscula) no `transcricao.txt` de todas as pastas de
  `transcricoes/`, com horário e, no YouTube, link `&t=`. `vatty buscar "termo" [--raiz] [--limite]`.
- `srt.py`: `transcricao.json` → `legenda.srt`/`legenda.vtt`; quebra segmento longo e divide a duração
  pelo tamanho do texto; `pessoa`/`falante` viram prefixo. `vatty legenda <pasta> --formato srt vtt`.
- `glossario.py`: correções do usuário (`errado = certo`, uma por linha, `#` comenta) aplicadas ao texto
  **depois** da transcrição, por palavra inteira e sem diferenciar maiúscula; a regra maior vence. Diferente
  de `--termos`, que só ajuda o Whisper a ouvir. `--glossario ARQ` (ou `~/.vatty/glossario.txt`, se existir)
  na transcrição; `vatty corrigir <pasta>` refaz uma pasta pronta (`pasta.carregar`). Registra o que trocou
  em `glossario` no cabeçalho do `transcricao.json`; `corrigir` repetido soma.
- `duvidoso.py`: usa `avg_logprob`, `no_speech_prob` e `compression_ratio` que o faster-whisper já devolve
  (limites -1,0 / 0,6 / 2,4, os padrões do Whisper, **não calibrados** com áudio real). O `motor` grava o
  motivo em `Segmento.duvidoso`; `texto.py` põe ` [?]` depois do trecho. Legenda do YouTube não tem esses
  números, então não marca. Escrivão e Secretário listam esses trechos em "trechos que a transcrição errou".
- `ui/` (`vatty ui`), painel "Começar": `gravador.py` roda `vatty gravar --parar-com ARQUIVO` em segundo plano
  (uma gravação por vez), lê o medidor da CLI (tempo e nível por faixa) e, ao parar, põe a pasta na fila com
  `visual` app/aula se teve tela; o "Parar" só cria o arquivo vigiado, sem sinal, igual em qualquer sistema.
  `pedidos.py` anota os agentes pedidos em `pedidos.json` quando o trabalho termina (o `runner` chama).
  `claude.py` roda o Claude Code local (`claude -p --output-format stream-json --permission-mode acceptEdits`,
  `--allowedTools Read,Write,Edit,Glob,Grep,Task,Agent`, `--add-dir` da pasta) na pasta do projeto, com o
  pedido pelo stdin, e resume o stream no log ("Chamando o agente X...", "Escrevendo Y.md"). Falha dele vira
  aviso: o trabalho termina pronto, porque o texto já está salvo.
  Front: `painel.js`/`painel.css`, as mesmas peças (fonte, depois, ouvindo, pronto, resumo) em três arranjos
  por `data-modo` (passos, bancada, estudio); o modo fica no `localStorage`. O servidor descarta o corpo de
  um POST que a rota não leu (sobrava na conexão e a próxima requisição chegava como `{}GET`).
- `ui/` (`vatty ui`): `servidor.py` (HTTP local, token, Host, SSE), `fila.py` (fila pura de um worker),
  `runner.py` (roda `python -m vatty.cli` por subprocesso, só opções conhecidas; UTF-8 e sem buffer),
  `terminal.py` (só subcomandos `vatty`, caminhos dentro da raiz), `biblioteca.py` (lista, leitor, exportar;
  nunca sai da raiz), `revisao.py` (corrigir palavra, regra do glossário em `<raiz>/glossario.txt`,
  `nomes.json`), `prompts.py` ("copiar prompt"), `saude.py` (o que falta instalar), `static/` (tela).
  A interface não chama API de LLM: gera o texto do prompt ou dispara o Claude Code local (`claude.py`).
- `lote.py`: `vatty lote`. Lê a lista (ou expande a playlist), roda cada item como subprocesso `vatty`, não para no
  erro e devolve o relatório. `fonte.listar_playlist` usa `extract_flat`.
- **Cartas** (`cartas.md`): flashcards em formato fixo; `cartoes.py` converte em `.csv` do Anki.
  **Tradutor** (`tradutor.md`): traduz só as linhas `N|texto`; `traducao.py` prepara a entrada e monta o `.srt`
  com os horários originais, recusando tradução incompleta. **Consulta** (`consulta.md`): responde só com os
  trechos que `acervo.py` escolheu (pontuação por termos, sem embeddings). **Comparador** (`comparador.md`):
  compara duas pastas. O **Escrivão** também faz resumo em níveis quando o briefing pedir.
  **Perito** (`perito.md`): laudo de quem testou um programa gravando a tela e a voz (`vatty gravar --mic --tela
  --transcrever`). Cruza a fala (`transcricao.txt`) com as telas paradas (`visual.json`, já na linha do tempo da
  fala) e escreve `pericia-<assunto>.md`: bugs (evidência, gravidade, certeza `visto`/`dito`/`suposto`), lentidão,
  atrito, comportamento observado (ação -> resposta, útil para engenharia reversa) e passos para reproduzir o
  bug mais grave. Abre no máximo 6 quadros de `frames/`, esconde senha e token (`[oculto]`) e não ensina a burlar
  proteção. Lê os eventos do perfil `app` (`transitorio` é o aviso que pisca; `movimento`, a espera).
  Limite conhecido: o que some em menos de 0,4 s e mudança mínima (um caractere) não viram evento.
  Sem código novo: o Perito só lê o que a gravação já produz.
  Agente novo só aparece depois de reiniciar a sessão do Claude Code.
