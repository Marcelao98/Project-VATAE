# Vatty

*Video Audio To Almost Everything.* Ferramenta que transforma vídeos e áudios
(YouTube, arquivo, gravação do PC) em material útil: transcrição, pontos-chave,
explicações didáticas. O ouvido dela (o Escriba) veio da Natty, bot de mesa de
RPG do Marcelo, mas a Vatty é independente: não importa nada do natty-bot e não
tem Discord. Até a versão 0.9.0 o projeto se chamava Natty-ATA.

## Persona

Na conversa principal, quem fala é a **Vatty**: uma garota robô ouvinte, de
corpo remendado e ouvidos impecáveis. Tom: curiosa, atenta, direta, informal,
com um toque de lore quando cabe (ela odeia música de fundo e desconfia de
legenda automática). A persona é só voz: não muda nenhuma regra técnica,
**não entra nos arquivos que os agentes escrevem** (a saída deles é a parte
mais cara em tokens e precisa ser fiel) e nunca atrapalha a clareza. Ao
gravar, ela avisa que está ouvindo.

## Arquitetura

Duas metades com uma fronteira clara entre elas:

```
CÓDIGO (Python, determinístico)
  URL do YouTube
    ├─ tem legenda e o usuário aprovou os trechos? ─► Legenda ─┐
    └─ senão ─► baixa áudio ─► Motor (Whisper) ────────────────┤
  arquivo local ─► Motor (Whisper) ────────────────────────────┤
                                                               ▼
                                       Texto ─► pasta do vídeo (transcricoes/<slug>/)
─────────────────────────────────────────────────────────────────┼──────────────
AGENTES (LLM, sob demanda)                                       ├─► Escrivão  ─► pontos-chave.md
                                                                 ├─► Preceptor ─► didatico.md
                                                                 └─► (outros no futuro)
```

**Regra central: só vira agente o que exige julgamento.** Baixar, decodificar,
transcrever e formatar é código comum, testável e sem custo de LLM. Os agentes
nunca baixam nem transcrevem; o código nunca resume nem interpreta.

### A pasta do vídeo é o contrato

Cada fonte vira uma pasta em `transcricoes/<slug>/`. É a única coisa que as
duas metades compartilham:

| Arquivo | Quem escreve | Conteúdo |
|---|---|---|
| `fonte.json` | Fonte | `tipo` (`youtube`, `arquivo` ou `gravacao`) e, no YouTube: url, título, canal, duração, data, id, capítulos do autor, descrição |
| `transcricao.json` | Legenda ou Motor | metadados (`origem`, modelo, idioma; em gravação com duas faixas, também `faixas`) + segmentos `{inicio, fim, texto}`, um por linha; em gravação com duas faixas, também `falante` |
| `transcricao.txt` | Texto | parágrafos separados por linha em branco, cada um começando com `[mm:ss]` (`[h:mm:ss]` a partir de 1 h): é o que os agentes leem. Em gravação, `Eu:` / `Outros:` depois do horário; com duas faixas é a **linha do tempo** dos dois |
| `transcricao-eu.txt`, `transcricao-outros.txt` | Texto | só em gravação com duas faixas: um canal só, cada parágrafo começando com `[mm:ss]` (`[h:mm:ss]` a partir de 1 h) |
| `visual.json` | Visual | só com `--visual`: slides da tela (`eventos`: `tipo`, `inicio`, `fim`, `texto` por OCR, `confianca`, `frame`); o cabeçalho traz `ruido_removido` (linhas que se repetiam em muitos slides, como a barra do navegador) e `slides_sem_texto_descartados` |
| `frames/` | Visual | um JPG por slide, citado no `visual.json` |
| `pontos-chave-<foco>.md` | Escrivão | um arquivo por foco pedido |
| `didatico-<tema>.md` | Preceptor | um arquivo por pedido |

`origem` diz de onde veio o texto: `legenda-manual`, `legenda-automatica` ou
`whisper`. Os agentes leem esse campo para saber o quanto confiar em nomes e
termos técnicos.

`falante` só existe em gravação com duas faixas: `eu` (microfone) ou
`outros` (som do PC). É opcional: fonte sem ele (YouTube, arquivo) continua
igual, e os segmentos das duas faixas ficam intercalados por horário no
`transcricao.json` (formato inalterado: os agentes dependem dele).

Os **textos** de uma gravação com duas faixas montam cada canal sozinho, com
as mesmas regras de pausa e duração máxima, e só depois juntam os parágrafos
prontos, ordenados pelo início, na linha do tempo. Assim a fala de um lado
nunca parte a frase do outro. Gravação com uma faixa só, YouTube e arquivo
ficam como sempre: um `transcricao.txt` só, e `Eu:` na frente quando há
`falante`.

O áudio baixado é temporário e apagado depois da transcrição (não guardar
mídia). Os agentes citam trechos pelo horário (`[12:34]`), que vem do
`transcricao.json`; num vídeo do YouTube o horário vira link `&t=754s`.

### Legenda primeiro, Whisper se o usuário quiser

Para URL do YouTube, a primeira coisa é olhar se o vídeo tem legenda no idioma
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

### Camada de código (`vatty/`)

- `fonte.py`: URL do YouTube → `fonte.json`, legendas disponíveis, download
  da legenda ou do áudio via `yt-dlp`. Arquivo local passa direto.
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
  e o fim do trecho valem da primeira à última palavra.
- `quadros.py`: vídeo → quadros via ffmpeg: um quadro pequeno em cinza a cada
  intervalo (em fluxo, nunca vai ao disco) e a extração de um quadro JPG em
  boa qualidade num horário.
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
- `audio.py`: arquivo → array float32 mono 16 kHz via ffmpeg (aceita um filtro `-af`).
- `preprocessar.py`: etapa opcional antes do Whisper (`--preprocessar`). Mede o áudio (nível, SNR,
  ronco, estouro), pergunta se recomendado e aplica `highpass` x2 → `arnndn` → `speechnorm` na
  decodificação. Modelo `.rnnn` baixado para o cache (nunca no repositório); sem ele, `afftdn`.
  Registra `preprocessamento` no cabeçalho do `transcricao.json`.
- `motor.py`: array → segmentos (faster-whisper `large-v3-turbo`, CPU, int8).
- `repeticao.py`: sinais de loop do Whisper (com `hotwords`); o motor refaz
  esses trechos sem os termos.
- `texto.py`: segmentos → parágrafos. Em gravação com duas faixas, um canal
  por vez (`por_canal`), `formatar_canal` (`[mm:ss]` por parágrafo) e
  `linha_do_tempo`.
- `cli.py`: casca fina. `vatty <url-arquivo-ou-pasta-de-gravacao>` produz a pasta
  do vídeo; `vatty gravar` grava (e com `--transcrever` já transcreve). Depois de
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

**Custo (tokens).** Os dois agentes rodam no **Sonnet** (`model: sonnet` no
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

Os dois papéis são separados de propósito: um é fiel ao vídeo, o outro é
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

## Princípios

- **Lógica pura separada da casca.** `cli.py` só traduz argumentos e imprime.
- **Testes com dublês.** `unittest`, sem rede, sem modelo, sem ffmpeg, sem
  Tesseract, sem yt-dlp reais. Dependências externas entram como parâmetro para o teste trocar.
- **Nenhum modelo nem mídia no repositório.** Pesos ficam no cache do Hugging
  Face (`HF_HOME` move o cache); `transcricoes/` é ignorada pelo git.
- **Nenhuma chamada de LLM no pacote Python.** O LLM vive só nos agentes.
- **Parâmetros provados na sessão real não mudam sem motivo:** `language="pt"`,
  `vad_filter=True`, `condition_on_previous_text=False`, `hotwords` desligado
  por padrão, áudio passado como array (nunca o caminho).
- **Com `hotwords`, sempre a proteção contra loop** (`repeticao.py`): detecta
  e refaz sem os termos só os trechos suspeitos. Não usar `repetition_penalty`
  nem `no_repeat_ngram_size` para isso: penalizam tokens já vistos, o que
  inclui os próprios termos, e bloqueiam repetições legítimas da fala.
- Código, comentários, mensagens e agentes em português.

## Roteiro

1. Motor de transcrição de arquivo local. **(feito)**
2. Fonte YouTube (`yt-dlp`): legenda primeiro com aprovação do usuário, **(feito)**
   Whisper como alternativa; pasta do vídeo, `transcricao.json`.
3. Escrivão; capítulos e descrição no `fonte.json`. **(feito)**
4. Preceptor. **(feito)**
5. Gravação do áudio do PC (Windows) com duas faixas. **(feito, falta
   confirmar a captura num Windows real)**
6. Visual, perfil `aula`: slides + OCR (Tesseract) → `visual.json`.
   **(feito, falta confirmar com vídeo real)** Falta o perfil `corte`.

## Comandos

```bash
python -m unittest discover -s backend/tests
vatty arquivo.opus
vatty gravar --mic --transcrever
vatty "url" --visual auto
```
