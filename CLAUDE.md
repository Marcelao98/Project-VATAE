# Vatty

*Video Audio To Almost Everything.* Ferramenta que transforma vídeos e áudios
(YouTube, arquivo, gravação do PC) em material útil: transcrição, pontos-chave,
explicações didáticas. O ouvido dela (o Escriba) veio da Natty, bot de mesa de
RPG do Marcelo, mas a Vatty é independente: não importa nada do natty-bot e não
tem Discord. Até a versão 0.9.0 o projeto se chamava Natty-ATA.


## Onde ler o quê

- Persona e voz: `AGENTS.md`. Fluxograma: `docs/fluxo.md`.
- Detalhe por módulo, legenda, visual e agentes: `docs/arquitetura.md` (ler só quando mexer nessa parte).
- Testes feitos no PC real: `docs/testes-reais.md`.

## Persona (resumo)

Na conversa principal fala a **Vatty**. Ela é só voz: não muda regra técnica e **nunca entra nos
arquivos que os agentes escrevem**. Detalhes em `AGENTS.md`.

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
| `fonte.json` | Fonte | `tipo` (`youtube`, `url`, `arquivo` ou `gravacao`) e, em vídeo de URL: url, título, canal, duração, data, id, capítulos do autor, descrição. `tipo: "url"` é vídeo de outra plataforma (TikTok etc.) e traz `plataforma`; sem capítulos nem legenda, em geral. Gravação com tela traz também `inicios` (`{faixa: horário real de início}`, em segundos do relógio do sistema, com `tela`) e `tela` (`arquivo`, `alvo`, `motor`, `fps`, `inicio_aproximado`), vindos do `gravacao.json`; gravação sem tela não tem esses campos |
| `transcricao.json` | Legenda ou Motor | metadados (`origem`, modelo, idioma; em gravação com duas faixas, também `faixas`) + segmentos `{inicio, fim, texto}`, um por linha; em gravação com duas faixas, também `falante` |
| `transcricao.txt` | Texto | parágrafos separados por linha em branco, cada um começando com `[mm:ss]` (`[h:mm:ss]` a partir de 1 h): é o que os agentes leem. Em gravação, `Eu:` / `Outros:` depois do horário; com duas faixas é a **linha do tempo** dos dois |
| `transcricao-eu.txt`, `transcricao-outros.txt` | Texto | só em gravação com duas faixas: um canal só, cada parágrafo começando com `[mm:ss]` (`[h:mm:ss]` a partir de 1 h) |
| `falantes.json` | Falantes | só com `--falantes`: `modo` (`agrupar`/`perfis`), `modelo_voz`, `pessoas` (`pessoa`, `fala_s`, `perfil`) e `turnos` (`inicio`, `fim`, `pessoa`). Os segmentos do `transcricao.json` ganham `pessoa` (`Pessoa N`, nome de perfil ou `Desconhecido`); no `transcricao.txt` a pessoa aparece no lugar de `Outros:`. Em gravação só o som do PC é separado |
| `visual.json` | Visual | só com `--visual`: slides da tela (`eventos`: `tipo`, `inicio`, `fim`, `texto` por OCR, `confianca`, `frame`); o cabeçalho traz `ruido_removido` (linhas que se repetiam em muitos slides, como a barra do navegador) e `slides_sem_texto_descartados`. Em gravação com tela, também `sincronia.deslocamento_s` (já somado aos horários: o `[mm:ss]` do slide é o da fala). Com `perfil: "app"`: eventos `tela`, `transitorio` e `movimento` (este sem texto nem frame), `regiao` quando o texto é só do pedaço que mudou, `repetida` para tela já vista (mesmo `frame`), `telas_lidas` no cabeçalho, e tela sem texto não é descartada |
| (cabeçalho do `transcricao.json`) | Glossário | `glossario`: `{errado: vezes}`, só se o glossário corrigiu algo |
| (cabeçalho e segmentos) | Duvidoso | `trechos_duvidosos` no cabeçalho e `duvidoso` (motivo) no segmento, só se o Whisper não confiou; o `transcricao.txt` marca o trecho com `[?]` |
| `legenda.srt`, `legenda.vtt` | Legenda (código) | `vatty legenda <pasta>`: os segmentos do `transcricao.json` em blocos de até 2 linhas de 42 caracteres |
| `frames/` | Visual | um JPG por slide, citado no `visual.json` |
| `pontos-chave-<foco>.md` | Escrivão | um arquivo por foco pedido |
| `didatico-<tema>.md` | Preceptor | um arquivo por pedido |
| `ata-<assunto>.md` | Secretário | só o conteúdo da ata (seções `## Resumo/Decisões/Tarefas/Pendências/Dúvidas da transcrição`, itens `- ...`; tarefas como `Responsável \| tarefa \| prazo \| [mm:ss]`) |
| `cartoes-<tema>.md`, `.csv` | Cartas (agente) + código | `.md`: `## Tópico`, `P:`, `R:`, `[mm:ss]`; `vatty cartoes <pasta>` gera o `.csv` do Anki |
| `traducao-<lang>-entrada.txt`, `traducao-<lang>.txt`, `legenda.<lang>.srt` | código, Tradutor, código | `N\|texto`; `vatty traduzir preparar/montar`; o código recusa tradução com bloco faltando |
| `_consultas/<pergunta>/trechos.md`, `resposta.md` | código, Consulta | `vatty perguntar` escolhe os trechos; o agente responde só com eles |
| `_comparacoes/comparacao-<a>-<b>.md` | Comparador | só o agente, lendo duas pastas |
| `pericia-<assunto>.md` | Perito | laudo de uma gravação de teste de programa (de preferência com `--tela`): seções `## Resumo/Bugs/Lentidão e espera/Atrito/Comportamento observado/Para reproduzir/Dúvidas`; bug como `[mm:ss] o que \| evidência \| gravidade \| certeza` |
| `slides.html`, `slides.pdf` | Slides (código) | `vatty slides <pasta>` (ou o painel): um slide por tela do `visual.json`, com o print (embutido no HTML) e a fala do `transcricao.json` daquele intervalo; precisa do visual (`--visual aula/app` ou gravação com tela) |
| `pedidos.json` | Painel (código) | só quando o painel pediu agentes: lista de `{agente, objetivo, pedido_em, estado}` (`pendente`/`feito`); ver "Pedidos do painel" |
| `ata-<assunto>.docx`, `.pdf` | Ata (código) | `vatty ata <pasta>`: cabeçalho (data, duração, participantes) vindo de `fonte.json`/`falantes.json`, mais o `.md` do agente, com `Pessoa N` trocada pelos nomes dados |

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

**Pedidos do painel.** Quando a pessoa escolhe "chamar os agentes" no painel (`vatty ui`, aba Começar),
o código anota em `pedidos.json` na pasta do vídeo e, se houver Claude Code no PC, roda `claude -p` na
pasta do projeto (`vatty/ui/claude.py`, pedido pelo stdin, só ferramentas de ler e escrever arquivo) para
fazer os pedidos daquela pasta, sem perguntar nada. Sem Claude Code, ou se ele falhar, o pedido fica
pendente. Quando a pessoa disser "faz os pedidos da Vatty" (ou o painel mandar), a conversa principal procura `transcricoes/*/pedidos.json` com `estado: pendente`,
monta o briefing de cada um (pasta, `objetivo` como foco/nível/o que foi testado, extensão `medio`,
arquivo de saída, data; o Tradutor ainda precisa do idioma, então pergunte), chama o agente e, no fim,
troca o `estado` para `feito` e acrescenta `arquivo` com o que foi escrito.

O áudio baixado é temporário e apagado depois da transcrição (não guardar
mídia). Os agentes citam trechos pelo horário (`[12:34]`), que vem do
`transcricao.json`; num vídeo do YouTube o horário vira link `&t=754s`.


Detalhes de legenda-primeiro, visual, módulos e agentes: `docs/arquitetura.md`. Interface: `vatty/ui/` e `docs/visual.md`.

## Princípios

- **Lógica pura separada da casca.** `cli.py` só traduz argumentos e imprime.
- **Testes com dublês.** `unittest`, sem rede, sem modelo, sem ffmpeg, sem
  Tesseract, sem yt-dlp reais. Dependências externas entram como parâmetro para o teste trocar.
- **Nenhum modelo nem mídia no repositório.** Pesos ficam no cache do Hugging
  Face (`HF_HOME` move o cache); `transcricoes/` é ignorada pelo git.
- **Nenhuma chamada de API de LLM no pacote Python.** O LLM vive só nos agentes, que rodam no Claude Code.
  A única ponte é o painel disparar o Claude Code local (`claude -p`) para os pedidos; gravar e
  transcrever nunca dependem dele. Conectar a uma API de terceiros (versão comercial) fica para depois.
- **Parâmetros provados na sessão real não mudam sem motivo:** `language="pt"`,
  `vad_filter=True`, `condition_on_previous_text=False`, `hotwords` desligado
  por padrão, áudio passado como array (nunca o caminho).
- **Com `hotwords`, sempre a proteção contra loop** (`repeticao.py`): detecta
  e refaz sem os termos só os trechos suspeitos. Não usar `repetition_penalty`
  nem `no_repeat_ngram_size` para isso: penalizam tokens já vistos, o que
  inclui os próprios termos, e bloqueiam repetições legítimas da fala.
- Código, comentários, mensagens e agentes em português.


## Testes unitários (quantidade certa)

Regra: **testar comportamento, não linhas.** Pouco teste bom vale mais que muito teste repetido.

- **Por função pública de lógica pura:** 1 caso normal + 1 borda (vazio, um só item, limite exato) + 1 erro
  esperado, se a função falha de propósito. Mais que isso só se houver um bug real a travar.
- **Bug corrigido = 1 teste novo** que falharia sem o conserto.
- **Módulo novo:** em geral 6 a 12 testes. Passou de 20, provavelmente testa a implementação.
- **CLI:** 1 teste por flag nova e 1 para o erro mais provável. A conta fica no módulo, não na CLI.
- **Contrato (`transcricao.json`, `fonte.json` etc.):** 1 teste que confere os campos novos e 1 que
  confere que fonte sem eles continua igual (compatibilidade).
- **Dublês:** dependência externa entra por parâmetro; nada de rede, modelo, ffmpeg, Tesseract ou yt-dlp reais.
- **Não testar:** captura de áudio real e modelos reais (ficam em `docs/testes-reais.md`), nem cópia de
  código de terceiros.
- Antes de abrir PR: `python -m unittest discover -s tests` tudo verde. Contagem atual no `CHANGELOG.md`.

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
7. Separação de falantes (`--falantes`, perfis de voz). **(feito, falta confirmar com voz real)**
8. Secretário (ata em `.docx`/`.pdf`). **(feito, falta confirmar numa reunião real)**
9. Interface local `vatty ui` (importar, fila, biblioteca, revisão). **(feita; conferida só na nuvem, falta usar no PC)**
10. Gravação da tela junto com o áudio (`vatty gravar --tela`, Windows; `ddagrab`, `gdigrab` na janela) e perfil
    `app` do visual → eventos da tela na linha do tempo da fala.
    **(feito, falta confirmar a captura e a sincronia num Windows real)** Fora por enquanto: pausar,
    Mac/Linux, print "no momento da fala" (o botão na interface veio no item 12).
11. Perito: laudo de teste de programa (bugs, lentidão, atrito, comportamento) a partir da gravação
    com tela. **(feito; nunca rodado de verdade)**
12. Painel "Começar" no `vatty ui`: gravar áudio, gravar tela e áudio ou puxar do YouTube, e só guardar ou
    anotar pedido para os agentes; modos Passo a passo (padrão), Bancada e Estúdio. **(feito; conferido na
    nuvem com gravação falsa, falta gravar de verdade pelo painel no Windows)**
13. Slides com os prints (`vatty slides`, opção no painel) e login do navegador para o YouTube
    (`--cookies-navegador`). **(feito; slides conferidos com imagens sintéticas, login não testado no YouTube)**

## Comandos

```bash
python -m unittest discover -s tests
vatty arquivo.opus
vatty gravar --mic --transcrever
vatty gravar --mic --tela --transcrever
vatty "url" --visual auto
vatty ui
vatty perguntar "o que disseram sobre margem?"
vatty cartoes transcricoes/aula
vatty traduzir preparar transcricoes/aula --para en
vatty lote lista.txt
vatty buscar "termo"
vatty corrigir transcricoes/aula --glossario glossario.txt
vatty legenda transcricoes/aula --formato srt vtt
vatty slides transcricoes/aula --formato html pdf
vatty ata transcricoes/reuniao --nomes "Pessoa 1=Ana" --formato docx pdf
```
