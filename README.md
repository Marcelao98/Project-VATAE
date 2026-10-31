# Vatty

*Video Audio To Almost Everything.* Uma garota robô que ouve tudo.

> **A história.** A Natty é uma bot de mesa de RPG: ela narra, rola dados e,
> principalmente, **ouve** a sessão inteira para escrever a ata depois. O
> ouvido dela (o módulo Escriba) é bom demais. Um engenheiro maluco, o
> Marcelo, copiou esse ouvido e montou em volta dele um corpo de peças
> diferentes, remendado, com cobre aparecendo nas juntas. Assim nasceu a Vatty.
> Ela escuta qualquer vídeo, áudio ou gravação, e depois vira quase qualquer
> coisa: transcrição, pontos-chave, aula explicada do zero, ata, flashcards,
> laudo de bugs. O que ela não entende são pessoas (ainda). Aprendeu o mundo
> por áudio, e por isso odeia música de fundo.

A Vatty pega **um vídeo do YouTube (ou TikTok), um arquivo de áudio/vídeo ou uma
gravação do seu PC** e transforma em texto com horário. Depois, os agentes dela
(no Claude Code) transformam esse texto no que você precisa.

Duas metades, sempre separadas:

- **O código ouve e lê**, no seu computador e sem custo de IA: baixa, transcreve
  com o [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  (`large-v3-turbo`, CPU), separa quem falou, lê a tela com OCR, grava o PC.
- **Os agentes julgam**, só quando você pede: resumem, ensinam, fazem a ata,
  acham bugs. Eles nunca transcrevem, e o código nunca resume.

## O que dá para fazer

| Eu quero... | Como |
|---|---|
| Transcrever um vídeo do YouTube | `vatty "https://youtube.com/watch?v=..."` |
| Transcrever TikTok ou outra plataforma | `vatty "https://www.tiktok.com/..." --texto whisper` |
| Transcrever um arquivo (.mp4, .mp3, .opus, áudio de WhatsApp...) | `vatty arquivo.opus` |
| Gravar uma reunião ou aula do PC (Windows ou Linux) | `vatty gravar --mic --transcrever` |
| Gravar a tela junto, com os slides no horário da fala | `vatty gravar --mic --tela --visual aula --transcrever` |
| Testar um programa e achar bugs | `vatty gravar --mic --tela --transcrever` e peça ao **Perito** |
| Ler o que aparece na tela de um vídeo | `vatty video.mp4 --visual aula` (ou `app`, ou `auto`) |
| Saber quem falou o quê | `--falantes auto` (ou o número de pessoas) |
| Limpar áudio ruim de WhatsApp | `--preprocessar sim` |
| Ajudar o Whisper com nomes e siglas | `--termos termos/tecnologia-ia.txt` |
| Corrigir palavras que ele sempre erra | `vatty corrigir <pasta> --glossario glossario.txt` |
| Pontos-chave, resumo em níveis | peça ao **Escrivão** |
| Explicação didática | peça ao **Preceptor** |
| Ata de reunião em .docx/.pdf | **Secretário** + `vatty ata <pasta>` |
| Flashcards para o Anki | **Cartas** + `vatty cartoes <pasta>` |
| Legenda traduzida | `vatty traduzir preparar` + **Tradutor** + `vatty traduzir montar` |
| Perguntar algo a todos os vídeos já transcritos | `vatty perguntar "..."` + **Consulta** |
| Comparar dois vídeos | peça ao **Comparador** |
| Achar um termo em tudo que já foi transcrito | `vatty buscar "termo"` |
| Legenda .srt/.vtt | `vatty legenda <pasta> --formato srt vtt` |
| Slides com os prints de cada tela e o que foi dito | `vatty slides <pasta> --formato html pdf` |
| O YouTube pediu "prove que não é robô" | `--cookies-navegador firefox` |
| Vários vídeos ou uma playlist | `vatty lote lista.txt` |
| Usar tudo pelo navegador (gravar, YouTube, agentes) | `vatty ui` |

## Instalação

Funciona no **Windows** e no **Linux** (testado para Fedora 43; Ubuntu também). O passo a passo completo, com a
lista de tudo que a Vatty usa e o que muda em cada sistema, está em **[INSTALAR.md](INSTALAR.md)**. Resumo:

- **Com o Claude Code:** abra-o na pasta do projeto e diga **"instala a Vatty"** (skill `instalar-vatty`).
- **Na mão:** instale Python 3.14, Git, ffmpeg, Deno (ou Node) e Tesseract, clone o projeto e dê dois cliques
  em `abrir-vatty.bat` (Windows) ou rode `./abrir-vatty.sh` (Linux). Na primeira vez ele prepara tudo sozinho.
- Só a **gravação do PC** muda entre os sistemas; transcrição, YouTube, slides, agentes e painel são iguais.

## Primeiros passos

```bash
vatty "https://www.youtube.com/watch?v=..."     # vira transcricoes/<titulo>/
vatty gravacao.opus                              # qualquer formato que o ffmpeg abra
vatty gravar --duracao 5                         # teste rápido da gravação
```

Tudo vai para uma **pasta do vídeo** em `transcricoes/<nome>/`. O principal é o
`transcricao.txt`: parágrafos com o horário na frente (`[12:34]`), que é o que
você lê e o que os agentes leem.

## De onde vem o texto

### YouTube: legenda primeiro

Se o vídeo tem legenda no idioma pedido (a manual do autor antes da automática),
a Vatty baixa só a legenda, que leva segundos, e mostra uns números e três trechos
(começo, meio e fim). Você decide: usar a legenda ou transcrever com o Whisper,
que leva minutos. O áudio só é baixado se você escolher o Whisper, e é apagado
depois. Legenda automática sem pontuação costuma errar nomes e termos técnicos:
nesse caso, vale o Whisper. Sem terminal para perguntar, passe `--texto legenda`
ou `--texto whisper`.

### TikTok e outras plataformas

A URL vai direto, como no YouTube. O TikTok quase nunca tem legenda, então a Vatty baixa o áudio e usa o Whisper:

```bash
vatty "https://www.tiktok.com/@alguem/video/123" --texto whisper
```

O TikTok exige que o downloader imite um navegador (`curl-cffi`, já nas dependências: rode `pip install -e .` de novo
se atualizou). A página do vídeo é lida uma vez só; o TikTok recusava a segunda leitura. Instagram costuma pedir login
(cookies) e o Kwai não tem suporte no yt-dlp: nesses casos baixe o vídeo e passe o arquivo. Se o site mudar e o
download quebrar, atualize: `pip install -U "yt-dlp[default,curl-cffi]"`. O `fonte.json` registra `tipo: "url"` e a `plataforma`.

### Arquivo do seu computador

`.opus`, `.ogg`, `.mp3`, `.m4a`, `.wav`, `.mp4`... qualquer coisa que o ffmpeg
abra. O arquivo não é alterado nem copiado.

## Gravar o PC (Windows e Linux)

Grava o que sai nas caixas (reunião no Meet/Zoom/Teams, aula, live) e, com `--mic`,
o seu microfone em outra faixa:

```bash
vatty gravar --duracao 5                # teste rápido: grava 5 s, deixe algo tocando
vatty gravar                            # grava o som do PC até Ctrl+C
vatty gravar --mic --transcrever        # PC + microfone; ao parar, já transcreve
vatty gravacoes/2026-10-10_14-30        # transcreve depois uma gravação guardada
```

Cada faixa vira um `.wav` de 16 kHz (uns 115 MB por hora) em
`gravacoes/AAAA-MM-DD_HH-MM/`. Com as duas faixas, a pasta do vídeo ganha:

- `transcricao.txt`: a linha do tempo dos dois (`[mm:ss] Outros: ...` / `[mm:ss] Eu: ...`).
  Cada canal é montado sozinho, então uma fala sua no meio não parte a frase do outro;
- `transcricao-outros.txt` e `transcricao-eu.txt`: um canal cada.

- **Silêncio:** o Windows não entrega áudio enquanto nada toca. A gravação segue o
  relógio e completa com silêncio, então os horários continuam certos. Se uma faixa
  ficar quase muda, a Vatty avisa no fim.
- **Os .wav:** depois de transcrever, a Vatty pergunta se apaga (o padrão é guardar).
  `--apagar-audio` ou `--manter-audio` pulam a pergunta.
- **Dispositivo:** usa o alto-falante e o microfone padrão do sistema. No Linux, o som do PC vem da fonte
  "monitor" do PipeWire (o ffmpeg lê direto; nada a instalar além dele).
- **Consentimento:** gravar uma conversa sem avisar os outros pode ser ilegal onde
  você mora. A Vatty lembra disso ao começar.
- **Pontuação do microfone (experimental):** o canal `Eu:` às vezes sai em
  trechos curtos e sem ponto final. Pela leitura do faster-whisper 1.2.1, o
  filtro de voz corta a fala a cada pausa de 160 ms e cada pedaço curto é
  decodificado com pouco contexto. Não deu para validar sem áudio real, então
  `--vad-silencio-ms` fica desligado. Para testar na sua gravação (guardada
  com `--manter-audio`), compare as duas saídas:

  ```bash
  vatty gravacoes/2026-10-10_14-30 --saida teste/padrao
  vatty gravacoes/2026-10-10_14-30 --saida teste/vad --vad-silencio-ms 600
  ```

  e leia o `transcricao-eu.txt` de cada uma. Se melhorar, o valor vira padrão
  da gravação em outro PR. (`initial_prompt` não resolve: com os parâmetros
  provados, o faster-whisper só o aplica na primeira janela.)

## Gravar a tela junto (Windows e Linux)

```bash
vatty gravar --mic --tela --transcrever                        # testar um programa (perfil app)
vatty gravar --mic --tela --visual aula --transcrever          # aula ou reunião com slides
vatty gravar --mic --tela-janela "Nome da janela" --transcrever # só uma janela (título exato)
vatty gravar --tela --tela-fps 15 --transcrever --manter-tela  # menos quadros; guarda o vídeo
```

**Como a tela é gravada.** O ffmpeg grava em segundo plano, sem som, em `tela.mp4`
na pasta da gravação. O áudio segue pelo caminho de sempre.

| | Tela inteira | Uma janela (`--tela-janela`) |
|---|---|---|
| Motor | `ddagrab` (Desktop Duplication, pela placa de vídeo) | `gdigrab` |
| Quadros por segundo | até 30 | até 10 |
| CPU | baixa | média (copia a tela a cada quadro) |
| Tela parada | não grava nada | quadros repetidos são descartados |

A taxa é variável: quadro igual ao anterior não é gravado, então uma tela parada
quase não ocupa espaço. Largura até 1920 px, para o texto pequeno de programa
continuar legível. Se o seu ffmpeg não tiver o `ddagrab` (mais velho que o 6.1)
ou ele falhar (área de trabalho remota, por exemplo), a Vatty avisa e cai para o
`gdigrab`. `--tela-fps N` muda a taxa.

**No Linux.** Tela inteira só (ainda sem `--tela-janela`). Com **X11**, o ffmpeg grava pelo `x11grab`. Com
**Wayland** (o padrão do Fedora e do Ubuntu novos), nenhum programa pode capturar a tela sozinho: a Vatty pede ao
**portal do sistema**, que mostra a janela "Compartilhar a tela?", e o **GStreamer** grava. Na primeira vez você
escolhe a tela e clica em compartilhar; a permissão fica lembrada em `~/.vatty/portal-tela.txt` (apague para
escolher de novo). No Wayland o horário de início da tela é aproximado (o GStreamer não informa o primeiro
quadro como o ffmpeg), então a sincronia pode errar alguns décimos de segundo a mais.

**Privacidade.** A tela pode mostrar senha, notificação e conversa de outras
pessoas. A Vatty avisa antes de começar; feche o que não deve aparecer. A imagem
fica só no seu PC.

**Sincronia.** Cada faixa guarda o horário real em que começou (`gravacao.json`).
O que a tela mostrou é levado para a linha do tempo da fala, então o `[mm:ss]` do
evento na tela bate com o `[mm:ss]` do que foi dito.

**No fim.** Com `--transcrever`, o `tela.mp4` passa pelo perfil de leitura
(`--visual app`, o padrão, ou `--visual aula`), vira `visual.json` e `frames/` na
pasta do vídeo e é apagado, porque a Vatty não guarda mídia. `--manter-tela`
guarda. Se a leitura da tela falhar, o texto já está salvo, a gravação inteira
fica na pasta para tentar de novo (`vatty gravacoes/<pasta> --visual app`) e a
CLI sai com código 1. Sem `--transcrever`, tudo fica guardado e a Vatty mostra o
comando para depois.

## Ler a tela: `--visual`

Depois do texto, a Vatty olha o vídeo, lê o que aparece com o Tesseract e grava
`visual.json` (um evento por linha, com horário) e `frames/` (as imagens). Os
agentes usam isso quando existe. Dois perfis:

| | `aula` | `app` |
|---|---|---|
| Para | aula, palestra, reunião com slides | alguém usando ou testando um programa |
| Olha | 1 quadro por segundo | 5 quadros por segundo |
| Conta uma tela quando | fica parada uns 2 s | fica parada 0,4 s |
| Câmera e área que mexe | ignoradas | contam (é onde as coisas acontecem) |
| Eventos | `slide` | `tela`, `transitorio` (aviso que pisca e some), `movimento` (carregando, rolagem) |
| OCR | a tela inteira de cada slide | só o pedaço que mudou, quando é pequeno; tela repetida não é lida de novo |
| Tela sem texto | descartada | fica (tela em branco é evidência) |

```bash
vatty "https://www.youtube.com/watch?v=..." --visual auto   # mostra um palpite e pergunta (aula)
vatty aula.mp4 --visual aula
vatty teste-do-app.mp4 --visual app
```

- **O texto sai primeiro.** Se a leitura da tela falhar (Tesseract faltando, erro
  do ffmpeg), o texto já está salvo e a Vatty sai com código 1.
- **URL:** baixa só a imagem, até 720p, e apaga depois.
- **Ruído fixo:** linha que aparece em muitas telas (barra do navegador, menu) sai
  do texto e fica listada no cabeçalho, para gastar menos tokens dos agentes.
- **Limites:** gráfico e imagem não viram texto. No `app`, o que aparece e some em
  menos de 0,4 s (um flash) e mudança muito pequena (um caractere digitado) não
  viram evento. Ainda falta o perfil `corte` (vídeo curto com cortes rápidos).

## Melhorar o texto

### Lista de termos (`--termos`)

Ajuda o Whisper com palavras que ele costuma errar: termos em inglês, siglas,
nomes próprios. Há uma pronta para mercado financeiro:

```bash
vatty "https://www.youtube.com/watch?v=..." --texto whisper --termos termos/mercado-financeiro.txt
```

Listas prontas em `termos/`: `mercado-financeiro.txt`, `tecnologia-ia.txt` (IA,
Claude Code, ChatGPT, GitHub, TikTok...) e `girias-brasil.txt` (mano, sacou, tá
ligado, rolê, paia...). Dá para usar mais de uma, e a Vatty junta sem repetir
termo e avisa se a soma passar do limite. Ponha a entrada **antes** de
`--termos` (ou separe com `--`):

```bash
vatty gravacoes/2026-10-10_14-30 --termos termos/tecnologia-ia.txt termos/girias-brasil.txt
```

O faster-whisper coloca a lista como "texto anterior" em toda janela de 30 s,
e com áudio confuso o Whisper às vezes copia a lista ou repete uma frase (já
aconteceu numa sessão real da Natty). Por isso, com `--termos`:

1. **Lista curta.** O Whisper só usa ~223 tokens da lista; acima disso a
   a Vatty avisa. Coloque só o que ele erra, não palavras comuns.
2. **Detecção.** Depois de transcrever, procura sinais de loop: texto
   repetitivo demais (o mesmo critério de compressão do Whisper), segmento
   que é quase só termos da lista, ou a mesma frase em segmentos seguidos.
3. **Correção.** Refaz só esses trechos **sem** a lista. O terminal mostra
   quantos foram refeitos, e o `transcricao.json` guarda cada um em
   `trechos_refeitos` (horário, motivo e o texto de antes).

### Glossário: corrigir depois (`--glossario`, `vatty corrigir`)

Para palavras que o Whisper erra sempre do mesmo jeito. Um arquivo com
`errado = certo`, uma regra por linha (`#` comenta):

```bash
vatty video.mp4 --glossario glossario.txt          # aplica depois de transcrever
vatty corrigir transcricoes/aula --glossario glossario.txt   # refaz uma pasta pronta
```

Sem a flag, usa `~/.vatty/glossario.txt` se existir. Diferente do `--termos`, que
ajuda o Whisper a ouvir, o glossário troca no texto pronto, por palavra inteira.

### Trechos duvidosos `[?]`

Quando o Whisper não confia num trecho, o `transcricao.txt` marca com ` [?]`. Os
agentes tratam como incerto e listam os mais importantes. Os limites ainda não
foram calibrados com áudio real.

### Áudio ruim (WhatsApp, voz baixa): `--preprocessar`

Antes do Whisper a Vatty pode limpar o áudio: corta o ronco grave (`highpass`), tira o ruído com a
rede neural RNNoise (`arnndn`) e sobe a fala baixa (`speechnorm`). Ela mede o áudio primeiro e só
pergunta se parecer ruim.

```bash
vatty zap.opus                       # mede e pergunta se precisar
vatty zap.opus --preprocessar sim    # aplica sempre
vatty zap.opus --preprocessar nao    # pula
vatty zap.opus --ruido-modelo arquivo.rnnn
```

O modelo de ruído (~300 KB) baixa uma vez para `~/.cache/vatty/rnnoise` (`VATTY_CACHE` muda a
pasta) e não fica no repositório. Sem ele, cai num filtro simples (`afftdn`). O que foi aplicado
fica no `transcricao.json`. Os limiares foram validados só em sinal sintético: compare com e sem.

## Quem falou: `--falantes` e perfis de voz

A Vatty separa as pessoas de um áudio (reunião, ata, conversa). Dois fluxos, que você pode combinar:

```bash
vatty reuniao.opus --falantes auto       # descobre as pessoas sozinha: Pessoa 1, Pessoa 2...
vatty reuniao.opus --falantes 5          # você diz quantas são (costuma acertar mais)
vatty reuniao.opus --falantes perfis     # só reconhece quem tem perfil; o resto é "Desconhecido"
```

**Sem consentimento (por voz):** a fala é cortada em janelas de 2 s, cada uma vira uma "impressão de
voz" (vetor de timbre) e as parecidas são agrupadas. Os grupos saem como `Pessoa N`.

**Com consentimento (perfis):** quem concordou grava 20 a 30 s falando sozinho e a Vatty guarda só o
vetor, nunca o áudio:

```bash
vatty perfil criar "Ana" ana.opus        # pergunta se a pessoa consentiu (ou use --consentimento)
vatty perfil listar
vatty perfil apagar "Ana"
```

Com `--falantes auto` ou um número, quem tiver perfil recebe o nome no lugar de `Pessoa N`. `--perfis Ana Beto`
limita a esses perfis; `--perfis nenhum` não usa nenhum. Em gravação a separação roda só no som do PC (o
microfone já é o "Eu").

Instalação: `pip install -e ".[falantes]"` (sherpa-onnx). Dois modelos pequenos (~29 MB) baixam uma vez para
`~/.cache/vatty/voz`. Os perfis ficam em `~/.vatty/perfis` (`VATTY_PERFIS` muda), nunca no repositório.

Perfil de voz é dado biométrico, sensível pela LGPD: só crie com o consentimento da pessoa, que pode pedir
para apagar quando quiser. (Isto não é parecer jurídico.)

O resultado: `falantes.json` na pasta (turnos e resumo) e `pessoa` em cada segmento do `transcricao.json`.

Limites conhecidos: fala sobreposta erra; um trecho do Whisper vai inteiro para quem mais falou nele; o
modelo de voz foi treinado em chinês e inglês e os limiares foram medidos só em voz sintética em português:
teste com reunião real e me conte.

## Os agentes

Peça pela conversa do Claude Code, em português normal ("faz os pontos-chave
sobre juros", "acha os bugs desse teste"). A Vatty conversa com você, pergunta o
que falta (foco, nível, objetivo) e chama o agente certo. Cada um escreve um
arquivo na pasta do vídeo, em tom neutro, e devolve só um resumo curto.

| Agente | Pedido típico | Arquivo |
|---|---|---|
| **Escrivão** | "pontos-chave sobre X", "resumo em níveis" | `pontos-chave-<foco>.md` |
| **Preceptor** | "me explica isso do zero" | `didatico-<tema>.md` |
| **Secretário** | "faz a ata da reunião" | `ata-<assunto>.md` (e `vatty ata` faz o .docx/.pdf) |
| **Cartas** | "faz flashcards" | `cartoes-<tema>.md` (e `vatty cartoes` faz o .csv do Anki) |
| **Tradutor** | "legenda em inglês" | `traducao-<idioma>.txt` (e `vatty traduzir montar` faz o .srt) |
| **Consulta** | "o que os vídeos dizem sobre X?" | `_consultas/<pergunta>/resposta.md` |
| **Comparador** | "compara esses dois vídeos" | `_comparacoes/comparacao-<a>-<b>.md` |
| **Perito** | "acha os bugs desse teste" | `pericia-<assunto>.md` |

Regras que valem para todos: não inventam (se o vídeo não diz, eles não dizem),
citam o horário de cada ponto, separam o que foi **dito** do que estava **na
tela** e tratam `Pessoa N` como rótulo, nunca como nome. Agente novo só aparece
depois de reiniciar a sessão do Claude Code.

### Ata de reunião (Secretário)

Depois de transcrever a reunião (de preferência com `--falantes`), peça a ata. O
Secretário escreve só decisões, tarefas (responsável, prazo), pendências e
dúvidas. O código monta o documento:

```bash
vatty ata transcricoes/reuniao --nomes "Pessoa 1=Ana" "Pessoa 2=Beto" --formato docx pdf
```

Título, data, duração e participantes saem dos arquivos da pasta, sem gastar
tokens; `--nomes` troca "Pessoa N" pelo nome certo só no documento final.
Confira sempre: decisão e tarefa dependem da transcrição e da separação de
falantes estarem certas.

### Estudar, perguntar e traduzir

```bash
vatty cartoes transcricoes/aula                       # cartoes-*.md (Cartas) -> .csv do Anki
vatty perguntar "o que disseram sobre margem?"        # separa os trechos; a Consulta responde só com eles
vatty traduzir preparar transcricoes/aula --para en   # o Tradutor traduz as linhas
vatty traduzir montar transcricoes/aula --para en     # legenda.en.srt com os horários originais
```

O código escolhe e confere (a montagem recusa tradução com linha faltando); o
agente só escreve o que exige julgamento.

### Testar um programa e achar bugs (Perito)

Para quem testa aplicativo novo, faz QA ou engenharia reversa. Grave você usando
o programa e **fale em voz alta** o que espera e o que estranha ("cliquei em
salvar e nada", "isso demorou"):

```bash
vatty gravar --mic --tela --transcrever          # ou --tela-janela "Nome do app"
```

Depois peça ao Perito, dizendo o que estava testando e o que esperava. Ele cruza
a sua fala com o que a tela mostrou (perfil `app`) e escreve `pericia-<assunto>.md`:

- **Bugs**, do mais grave ao mais leve, com horário, evidência (o texto da tela,
  o quadro, a sua fala) e se foi **visto** na tela, só **dito** ou **suposto**;
- **Lentidão e espera**, com quanto tempo;
- **Atrito**: passos repetidos, idas e voltas, tentativa e erro;
- **Comportamento observado**: cada ação e a resposta do programa (mensagens,
  códigos de erro, rotas e versões que aparecem na tela);
- **Para reproduzir** o bug mais grave, passo a passo.

Senha, token e dado de terceiros que aparecem na tela viram `[oculto]`, e ele não
ensina a burlar licença, login ou proteção. Funciona também só com áudio, mas aí
tudo vem da fala.

## Slides com os prints: `vatty slides`

Transforma um vídeo ou gravação já transcrito numa apresentação: **um slide por tela**, com o print no
momento em que ela apareceu e **o que foi dito** enquanto ela estava aberta (no YouTube, o horário vira
link para aquele ponto do vídeo).

```bash
vatty "https://www.youtube.com/watch?v=..." --visual aula   # primeiro, o texto e as telas
vatty slides transcricoes/<pasta> --formato html pdf
```

O `slides.html` é um arquivo só, com as imagens dentro: abre no navegador, as setas passam os slides e dá
para mandar para alguém. O PDF (uma página por slide) precisa do reportlab (`pip install -e ".[ata]"`).
Precisa do visual: transcreva com `--visual aula` (ou `app`) ou grave com `--tela`. No painel, é a caixa
"Montar slides com os prints".

## YouTube pedindo "prove que não é robô"

Às vezes o YouTube bloqueia o download e pede login. A Vatty pode usar o login do seu navegador (os
cookies, lidos direto do perfil; nada é guardado): `--cookies-navegador firefox` (ou `edge`, `chrome`...).
No painel, "Entrar como você no YouTube". O **Firefox** é o mais garantido: o Chrome no Windows protege os
cookies e o yt-dlp às vezes não consegue ler. Atualizar o yt-dlp também ajuda:
`pip install -U "yt-dlp[default,curl-cffi]"`.

## Mais ferramentas

```bash
vatty buscar "termo"                          # acha em todas as transcrições, com horário (e link no YouTube)
vatty legenda transcricoes/aula --formato srt vtt
vatty lote lista.txt                          # um link ou arquivo por linha; # comenta
vatty lote "https://youtube.com/playlist?list=..." --falantes auto
vatty ui                                      # interface no navegador
```

**Lote:** roda um de cada vez, um erro não para os outros, e no fim grava
`lote-relatorio.json`. Sem terminal para perguntar, usa `--texto whisper` e
`--preprocessar nao` (mude com as flags).

**Interface (`vatty ui`):** abre `http://127.0.0.1:8765` com um token. A primeira aba, **Começar**, é o painel
da Vatty: escolha **gravar áudio**, **gravar tela e áudio** ou **puxar do YouTube**, depois **só transcrever e
guardar** (100% no seu PC) ou **chamar os agentes**: quando a transcrição termina, a Vatty chama o **Claude
Code** instalado no seu PC (com a sua conta), que roda os agentes e escreve os arquivos na pasta; o andamento
aparece na fila. Sem Claude Code, ela só anota o pedido (diga depois "faz os pedidos da Vatty" no Claude Code,
ou use "copiar prompt"). Gravar e transcrever **nunca** precisam do Claude Code. O gravador mostra o tempo e o nível de cada faixa, e o
"Parar" já manda transcrever. Três jeitos de ver, no canto: **Passo a passo** (padrão, guiado), **Bancada**
(tudo numa tela) e **Estúdio** (o gravador no centro, os agentes do lado). Pode fechar a aba durante a
gravação: ao voltar, o painel reencontra o gravador. Nas outras abas: importe
arquivos (arrastar) ou cole links, acompanhe a fila, procure em tudo, leia com
horário, corrija palavras (e guarde como regra do glossário), dê nome às pessoas,
exporte (`.txt .md .srt .vtt .csv .json`) e use "copiar prompt" (pontos-chave,
resumo, ata, flashcards, explicação, achar bugs) para colar em qualquer IA. A
página só responde neste computador. `--porta 0` usa uma porta livre;
`--sem-navegador` não abre sozinha.

## A pasta do vídeo

| Arquivo | O que é |
|---|---|
| `transcricao.txt` | o texto, um parágrafo por trecho com `[mm:ss]` (é o que você e os agentes leem) |
| `transcricao.json` | os mesmos trechos com horário exato, origem do texto e os detalhes técnicos |
| `transcricao-eu.txt`, `-outros.txt` | gravação com microfone: um canal cada |
| `fonte.json` | de onde veio: link, título, canal, duração; em gravação, as faixas e os horários de início |
| `falantes.json` | com `--falantes`: quem é cada `Pessoa N` e quanto falou |
| `visual.json`, `frames/` | com `--visual` ou gravação com tela: o que apareceu na tela, com horário |
| `legenda.srt`, `.vtt` | `vatty legenda` |
| `*.md` | o que os agentes escreveram |

## Privacidade e dados

- Transcrição, separação de falantes, OCR e gravação rodam **no seu computador**.
  Nada vai para a internet, a não ser o download do YouTube/TikTok e, na primeira
  vez, os modelos.
- O texto só vai para uma IA quando você chama um agente ou usa "copiar prompt".
- Mídia não é guardada: o áudio baixado e o `tela.mp4` são apagados depois de
  usados (a gravação do PC pergunta). `transcricoes/` e `gravacoes/` ficam fora
  do git.
- Perfil de voz guarda só o vetor, nunca o áudio, e só com consentimento.

## Referência das opções

| Flag | Padrão | O que faz |
|---|---|---|
| `--modelo` | `large-v3-turbo` | modelo do faster-whisper (`small`, `base`... se a RAM apertar) |
| `--lang` | `pt` | idioma; `auto` usa o do vídeo ou detecta (gerou alucinação em outros idiomas, por isso não é o padrão) |
| `--texto` | `perguntar` | URL com legenda: `legenda`, `whisper` ou `perguntar` |
| `--visual` | `nenhum` (`app` em `gravar --tela`) | `aula`, `app`, `auto` ou `nenhum` |
| `--termos a.txt [b.txt]` | desligado | termos que o Whisper erra (`hotwords`) |
| `--glossario ARQ` | `~/.vatty/glossario.txt` | correções `errado = certo` depois de transcrever |
| `--preprocessar` | `perguntar` | `sim`, `nao` ou `perguntar` (mede e pergunta se o áudio estiver ruim) |
| `--falantes` | `nao` | `auto`, um número de pessoas ou `perfis` |
| `--perfis NOME...` | todos | com `--falantes`: só esses perfis (`nenhum` não usa nenhum) |
| `--horario-por-palavra` | `auto` | ajusta o horário à primeira e à última palavra; `auto` liga só em gravação |
| `--vad-silencio-ms MS` | desligado | experimental: pausa mínima que corta a fala no filtro de voz |
| `--saida pasta` | `transcricoes/` | onde as pastas são criadas |
| `--apagar-audio` / `--manter-audio` | pergunta | gravação: o que fazer com os `.wav` |
| `--manter-tela` | apaga | gravação com tela: guarda o `tela.mp4` |

Só de `vatty gravar`: `--mic`, `--transcrever`, `--duracao S`, `--gravacoes pasta`,
`--tela`, `--tela-janela "título"`, `--tela-fps N`. Tudo tem `--help`.

## Onde fica o modelo

O modelo (cerca de 1,5 GB) é baixado na primeira execução para o cache
padrão do Hugging Face (`~/.cache/huggingface`, no Windows
`C:\Users\<você>\.cache\huggingface`), nunca dentro do repositório. Se a
Natty já baixou o mesmo modelo, ele é reaproveitado.

Para mover o cache para outro drive, defina `HF_HOME` antes de rodar:

```powershell
setx HF_HOME "D:\huggingface"      # Windows, vale para terminais novos
```
```bash
export HF_HOME=/mnt/dados/huggingface
```

## O que já foi provado de verdade

Os testes automáticos usam dublês: sem rede, sem modelo, sem ffmpeg. O que foi
rodado com mídia real está em [`docs/testes-reais.md`](docs/testes-reais.md).
**Ainda não confirmados num PC real:** a gravação do áudio e da tela no Windows e no Linux (no Linux, só a
tela X11 foi gravada de verdade, numa tela virtual), e
a sincronia entre eles, o perfil `app`, a separação de falantes com voz real, a
ata numa reunião real, a interface usada no dia a dia e os agentes rodando de
verdade.

```bash
python -m unittest discover -s tests
```

## Licença

[PolyForm Noncommercial 1.0.0](LICENSE). Em resumo (o texto que vale é o do `LICENSE`):

- **Pode, sem pedir:** usar, estudar, modificar e compartilhar para uso pessoal, estudo, pesquisa, hobby, e
  em escola, ONG, órgão público e instituição de pesquisa.
- **Não pode sem autorização:** uso comercial. Isso inclui usar numa empresa, vender, embutir num produto
  ou oferecer a Vatty como serviço pago.
- **Licença comercial:** fale com o autor ([Marcelao98](https://github.com/Marcelao98)).

Até a versão 0.18.0 o projeto era MIT: quem já tinha uma cópia dessas versões continua com os direitos da
MIT para elas. Da 0.19.0 em diante vale a PolyForm Noncommercial.
