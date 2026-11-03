# Roteiro de testes por dependência (03/11/2026)

O que testar de verdade, **na ordem em que uma coisa depende da outra**: se um teste de baixo falha, os de
cima dele nem valem ainda. Cada teste é curto e dá pra fazer num dia diferente. O resultado de cada um vai
para `docs/testes-reais.md`, numa entrada nova com a data.

Legenda: **ok** já conferido de verdade · **falta** ainda não.

```
0 instalar ─┬─ 1 transcrever um arquivo ─┬─ 4 agentes pelo painel ─┬─ 4a Apresentador (botão novo)
            │                            │                         ├─ 4b Perito (qualidade do laudo)
            │                            │                         └─ 4c Cartas, Tradutor, Consulta, Comparador
            │                            ├─ 5 falantes ─── 5a Secretário (ata)
            │                            └─ 6 YouTube ─── 6a login do navegador
            └─ 2 som ─┬─ 3 painel com tela ─┬─ 3a sincronia tela × fala
                      │                      ├─ 3b tela.mp4 guardado
                      │                      ├─ 3c visual aula (slides)
                      │                      └─ 3d juntar (video.mp4)
                      └─ 2b tela pela CLI (Wayland): permissão, cancelar, Ctrl+C
7 Windows (outro PC): repete 2, 3 e 4 lá
```

---

## Nível 0 e 1: a base

| # | Teste | Situação |
|---|---|---|
| 0 | Instalar e `vatty verificar` | **ok** (31/10) |
| 1 | Transcrever um arquivo local com o Whisper | **ok** (vários, desde 12/10) |
| 2 | Som do PC e microfone no Fedora | **ok** (31/10), microfone em 40% |
| 3 | Painel: "Gravar tela e áudio" até o Pronto | **ok** (31/10) |

## Já dá pra fazer junto com a próxima gravação (cobre 3a, 3b, 4a e 4b de uma vez)

Ao gravar um programa pelo painel ("Gravar tela e áudio"):

1. Deixe **"Guardar o vídeo da tela" marcado** e **fale em voz alta** o que faz e o que estranha.
2. Em 3 trocas de tela, diga **"agora"** no exato momento da troca.
3. No fim, peça o **Perito** ("achar bugs") e diga no objetivo o que estava testando.
4. Depois que tudo terminar, abra o vídeo na **Biblioteca** e clique em **"Chamar o Apresentador"**.

O que anotar:

- **3b · tela.mp4:** o `tela.mp4` continua na pasta da gravação? (antes ele sumia; foi consertado na 0.19.x)
- **3a · sincronia:** para as 3 trocas, compare o horário do evento no `visual.json` com o `[mm:ss]` do
  "agora" no `transcricao.txt`. Esperado: menos de 0,5 s de diferença. Diferença sempre igual = início da
  tela errado; diferença crescendo = relógio derivando.
- **4b · Perito:** o laudo acha os problemas que você falou em voz alta, com horário e evidência? Inventou
  algum bug? Apareceu senha ou e-mail no laudo? (não pode)
- **4a · Apresentador:** o botão aceitou o pedido? A aba Fila mostrou "Agentes · …" e chegou em Pronto? O
  `apresentacao-*.pptx` apareceu nos arquivos do vídeo? Abre no LibreOffice/PowerPoint e conta a história certa?

## Nível 2: tela pela linha de comando (2b)

Só depende do som (já ok). Uns 10 minutos.

- `.venv/bin/python -m vatty.cli gravar --tela --duracao 15`: apareceu a janela "Compartilhar a tela?" e
  o `tela.mp4` abre?
- Rodar de novo: **não** pode perguntar outra vez (permissão em `~/.vatty/portal-tela.txt`).
- Cancelar na janela do sistema: a CLI diz "o compartilhamento da tela foi cancelado" e não deixa pasta vazia?
- Ctrl+C no meio: o `tela.mp4` fica legível? Sobrou `gst-launch-1.0` rodando (`pgrep gst-launch`)? Não pode.

## Nível 3: visual de aula (3c)

Depende do painel com tela (ok). Precisa de uma aula ou um PowerPoint passando em tela cheia.

- Painel → "Gravar tela e áudio" → tipo "Aula ou reunião com slides". Os slides saem com o horário certo
  da fala? O "Gerar slides" da biblioteca monta um slide por tela?

## Nível 5: falantes e Secretário

Depende de transcrever (ok). Precisa de uma conversa real com 2 ou mais pessoas.

- **5 · falantes:** transcrever com a opção de falantes ligada. Acertou quem falou o quê? Dar os nomes em "Quem é
  quem" troca "Pessoa 1" pelo nome em todo o texto?
- **5a · Secretário:** pedir a ata. O `.docx` e o `.pdf` abrem? Decisões e prazos estão certos e atribuídos
  à pessoa certa?

## Nível 6: YouTube

Depende de transcrever (ok) e do Deno ou do Node (o `vatty verificar` avisa).

- **6:** colar um link no painel. Usou a legenda do YouTube quando havia? Sem legenda, foi para o Whisper?
- **6a:** um vídeo que pede login (idade ou membros): quando o YouTube pede login, o painel oferece tentar com o login do navegador. Passou?

## Nível 4c: os outros agentes

Depende dos agentes pelo painel (já ok com o Perito em 31/10). Um de cada vez, em qualquer vídeo já transcrito.

- **Cartas** (flashcards): o `.csv` importa no Anki?
- **Tradutor:** a legenda traduzida abre no player junto com o vídeo?
- **Consulta** e **Comparador** (pelo Claude Code): a resposta cita o horário certo?

## Nível 7: Windows

Outro PC. Repetir 2, 3 e 4 seguindo a seção "A fazer: gravação da tela, perfil app e Perito (0.16.0)" de
`docs/testes-reais.md`.
