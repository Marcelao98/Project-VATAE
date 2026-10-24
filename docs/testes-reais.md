# Testes com mídia real

Diário dos testes da Vatty com áudio e vídeo de verdade: o que foi rodado, o que deu certo, o que
quebrou e o que mudou por causa disso. Os testes automáticos usam dublês; é aqui que fica a prova
com o mundo real. Uma entrada por teste, a mais nova em cima.

---

## A fazer: Vatty no Fedora (0.18.0, ainda não rodado)

Feito com dublês; só a tela X11 foi gravada de verdade (numa tela virtual, na nuvem). Anotar cada passo.

**0. Instalar.** Seguir o `INSTALAR.md` (ou dizer "instala a Vatty" no Claude Code). Anotar o que faltou e se
algum nome de pacote do `dnf` estava errado. `echo $XDG_SESSION_TYPE` (esperado: `wayland`).

**1. Som.** `./abrir-vatty.sh` uma vez (prepara o ambiente) e depois, com algo tocando e falando no microfone:
`.venv/bin/python -m vatty.cli gravar --mic --duracao 10`.
- Os dois `.wav` têm som? Apareceu "faixa quase muda"? Anotar as linhas `sistema:` e `microfone:` (as fontes
  que o `pactl` escolheu).
- Fone Bluetooth ou saída HDMI como padrão: grava o que está tocando nele?

**2. Tela no Wayland.** `.venv/bin/python -m vatty.cli gravar --tela --duracao 15`.
- Apareceu a janela "Compartilhar a tela?" do sistema? Depois de compartilhar, o `tela.mp4` abre e mostra a tela?
- Rodar de novo: desta vez **não** pode perguntar (permissão lembrada em `~/.vatty/portal-tela.txt`).
- Cancelar na janela do sistema: a CLI diz "o compartilhamento da tela foi cancelado" e não deixa pasta vazia?
- Ctrl+C no meio: o `tela.mp4` fica legível? Sobra `gst-launch-1.0` rodando (`pgrep gst-launch`)? Não pode.
- Anotar o codificador usado (x264enc ou openh264enc: aparece no erro se faltar) e a CPU durante a gravação.

**3. Tudo junto pelo painel.** `./abrir-vatty.sh`, aba Começar, "Gravar tela e áudio", 2 minutos, Parar.
- Chega no Pronto com `visual.json`? Os horários batem com a fala (o início da tela no Wayland é aproximado:
  anotar a diferença em 3 trocas de tela)?

**4. YouTube e agentes.** Um link pelo painel (com o Node ou o Deno instalado) e um pedido de agente com o
Claude Code logado. Mesmas perguntas do Windows.

---

## A fazer: gravação da tela, perfil app e Perito (0.16.0, ainda não rodado)

Feito e testado só com dublês. Precisa de Windows, ffmpeg e Tesseract no PATH e o extra `[gravacao]`.
Anotar o resultado de cada passo aqui, numa entrada nova com a data. Parar no primeiro passo que
quebrar e mandar o erro inteiro.

**0. Preparo (2 min).**
- `ffmpeg -version` (anotar a versão) e `ffmpeg -hide_banner -filters | findstr ddagrab`: aparece uma
  linha com `ddagrab`? Sem ela, a tela inteira vai pelo `gdigrab` (mais CPU).
- `tesseract --version` e `tesseract --list-langs` (precisa de `por`).
- `python -m unittest discover -s tests`: tudo verde?

**1. A tela grava e para direito.** `vatty gravar --tela --duracao 20`, com uma janela de texto aberta.
- Aparece o aviso de privacidade e a linha `tela: tela inteira (ddagrab, até 30 quadros por segundo)`?
  Se aparecer "Aviso: o ddagrab falhou" ou "não tem o ddagrab", anotar a mensagem inteira.
- A pasta `gravacoes/<data>/` tem `sistema.wav`, `tela.mp4` e `gravacao.json` (com `motor` e `fps`)?
- O `tela.mp4` abre no player, tem uns 20 s, o texto dá para ler e o cursor aparece?
- Anotar: tamanho do `tela.mp4` e se `inicio_aproximado` é `true` no `gravacao.json`.

**2. Peso e tamanho.** `vatty gravar --tela --duracao 120`, mexendo na tela metade do tempo (rolar uma
página, abrir menus) e deixando parada a outra metade.
- No Gerenciador de Tarefas, a CPU do `ffmpeg.exe` mexendo e parado.
- Tamanho do `tela.mp4` (MB por minuto). O áudio picotou?
- Repetir com `--tela-fps 15` e anotar a diferença.

**3. Ctrl+C no meio.** `vatty gravar --tela` e pare com Ctrl+C depois de uns 30 s.
- O `tela.mp4` abre no player? (o ffmpeg não pode morrer junto com o Ctrl+C)
- Sobrou algum `ffmpeg.exe` rodando? Não pode sobrar.

**4. Uma janela só.** `vatty gravar --tela-janela "<título exato>" --duracao 20` (ex.: o Bloco de Notas).
- Linha `tela: <título> (gdigrab, até 10 quadros por segundo)`? Grava só a janela?
- Com um título que não existe: erro claro e nenhuma pasta vazia em `gravacoes/`?
- Feche a janela no meio: aparece "a gravação da tela parou antes do fim"?

**5. Perfil app num teste de verdade (o principal).** Escolha um site ou programa e faça um roteiro
de 3 a 5 minutos, **falando em voz alta** o que faz e o que estranha:
1. abrir uma tela e esperar carregar;
2. provocar um erro com aviso que some sozinho (ex.: login com senha errada, formulário vazio);
3. repetir um passo duas vezes;
4. rolar uma página longa por uns 5 s;
5. dizer em voz alta "agora" no exato momento de 3 trocas de tela.

`vatty gravar --mic --tela --transcrever --manter-tela --manter-audio`
- No `visual.json`: o aviso do passo 2 virou `transitorio` com o texto do erro e `regiao`? A rolagem
  virou `movimento`? A tela do passo 3 aparece como `repetida`?
- Sincronia: para as 3 trocas do passo 5, compare o `inicio` do evento com o `[mm:ss]` do "agora" no
  `transcricao.txt`. Anotar a diferença de cada uma (esperado: menos de 0,5 s). Diferença constante =
  conta do início errada; crescendo com o tempo = deriva do relógio.
- Anotar: quantos eventos, quantas `telas_lidas`, quanto tempo a leitura da tela levou e o tamanho do
  `visual.json`. Algum evento importante faltou? Algum lixo sobrou (muitos eventos iguais)?

**6. O Perito.** No Claude Code (sessão reiniciada), peça: "acha os bugs desse teste", dizendo o que
estava testando e o que esperava.
- O laudo achou o erro do passo 2 com horário e evidência? A espera e o passo repetido?
- Alguma coisa inventada (bug sem evidência)? Alguma senha ou e-mail aparecendo no laudo?

**7. Perfil aula na gravação.** `vatty gravar --mic --tela --visual aula --transcrever` com uns slides
passando (PowerPoint em tela cheia ou vídeo de aula). Os slides saem com o horário certo da fala?

**8. Limpeza e falha.**
- Repetir um teste curto sem `--manter-tela` e com `--apagar-audio`: a pasta da gravação some e a pasta
  do vídeo fica com `visual.json` e `frames/`?
- Tire o Tesseract do PATH só nesse terminal e rode `vatty gravar --tela --transcrever --duracao 20`:
  sai com código 1, o texto fica salvo e a gravação fica inteira? Volte o Tesseract e rode o comando que
  ela sugeriu (`vatty gravacoes/<pasta> --visual app`).

---

## 2026-10-12 — Vídeo curto do TikTok (51 s, vertical, legenda animada na tela)

**Comando:** `vatty <arquivo>.mp4 --visual aula --falantes auto --preprocessar nao --lang pt`
(o vídeo foi baixado à mão com `yt-dlp`; ver "URL do TikTok" abaixo).

**Texto: ótimo.** Whisper em 45 s (texto + falantes), fala clara, sem erro visível em 47 s de
monólogo. A única falha foi no fim, com a música de saída: *"Beauty and Star"*.

**Falantes: certo.** Pessoa 1 (0:47) é o apresentador; a "Pessoa 2" (0:04) é o fim com música.

**Visual (`aula`): nada.** 0 slides. O vídeo é um rosto falando com legenda animada palavra por
palavra. O perfil `aula` procura uma tela que muda e depois fica parada, e a máscara de movimento
trata a legenda como "região que mexe o tempo todo". Era o esperado: este é o caso do perfil
`corte`, que ainda não existe. A legenda na tela repete a fala, então não se perdeu conteúdo.
O Tesseract com `--psm 11` (texto esparso) leu `parcele.ele nunca` num quadro; com o modo padrão,
não leu nada. Se o `corte` for feito, ele precisa do `--psm 11`.

**O que quebrou no caminho**

1. **URL do TikTok.** O yt-dlp precisa do `curl_cffi` para se passar por navegador (sem ele:
   `Unexpected response from webpage request`). Com ele instalado, o vatty lê os dados do vídeo,
   mas o TikTok barra a segunda requisição, a do download do áudio (`Unable to extract universal data
   for rehydration`, duas vezes seguidas). Baixar direto com `python -m yt_dlp <url>` funciona.
   A fonte também grava `"tipo": "youtube"` e imprime "Lendo o vídeo no YouTube..." para qualquer URL.
2. **`--preprocessar perguntar` sem terminal.** O diagnóstico recomendou (ruído, ronco), fez a
   pergunta e, sem quem respondesse, saiu com `Erro: cancelado`. O `--texto` recusa `perguntar`
   sem terminal e pede a flag explícita; o `--preprocessar` deveria fazer o mesmo.
3. **Tesseract fora do PATH.** Está instalado (winget, `C:\Program Files\Tesseract-OCR`, com `por` e
   `eng`), mas o instalador não põe no PATH. Funcionou depois de pôr à mão no terminal.

**A fazer:** fonte aceitar TikTok (uma requisição só, ou baixar o vídeo e ler o áudio dele;
`tipo` certo) **[feito na 0.14.0: `fonte.Sessao` lê a página uma vez, `curl-cffi` é dependência, `tipo: "url"` +
`plataforma`; provado só com extrator falso, falta rodar numa URL de TikTok de verdade]**; `--preprocessar` pedir a flag sem terminal; perfil `corte` com `--psm 11`.

---

## 2026-10-12 — Conversa sussurrada com música de fundo (2:51, .ogg)

O pior caso possível: amigos sussurrando, música com letra em inglês ("Time", do Pink Floyd) o tempo
todo, português e inglês misturados.

**Travamento do pré-processamento (corrigido em `54a2356`).** Com `--preprocessar sim`, o ffmpeg
ficava rodando para sempre. Causa: no ffmpeg 9.0.2, qualquer filtro depois do `arnndn`
(`speechnorm`, `dynaudnorm`) às vezes trava ou dá segfault. Com o `arnndn` por último: 10 de 10
rodadas sem falha.

**Comparação** (mesmo modelo e opções; muda só o pré-processamento e o VAD):

| Variante | Palavras | Até onde chega |
|---|---|---|
| pré-processamento + VAD padrão | ~70 | 1:14 de 2:51 |
| **sem pré-processamento + VAD padrão** | **189** | **fim** |
| pré-processamento + VAD tolerante (`threshold=0.3`, `min_speech_duration_ms=100`) | 2 | — |
| sem pré-processamento + VAD tolerante | 182 | fim |

**Conclusões**

- O pré-processamento (`speechnorm` + `arnndn`) piora sussurro e música: o RNNoise trata o sussurro
  como ruído. Ficou registrado no CLAUDE.md e no `--help`. Ainda não foi testado no caso para o qual foi
  feito (voz baixa de WhatsApp).
- O VAD padrão não era o problema; o tolerante empata e pula um pouco mais de música.
- Com `--lang pt`, o Whisper **traduziu a letra da música** para o português ("you missed the
  starting gun" virou "você perdeu o tiro de partida"). Quem lê pensa que alguém disse aquilo. Só a
  separação de voz e música (Demucs) resolveria; não foi testada.
- O diagnóstico não viu problema: a música, num volume constante, foi medida como "fundo".
- Falantes: 4 grupos, com a música provavelmente contada como uma "pessoa".
