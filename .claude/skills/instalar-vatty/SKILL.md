---
name: instalar-vatty
description: Instala e confere a Vatty neste computador (Windows ou Linux/Fedora), passo a passo, e testa no fim. Use quando a pessoa pedir para instalar, configurar, preparar ou consertar a instalação da Vatty, ou quando algo falhar por falta de programa (ffmpeg, Tesseract, Deno, GStreamer, Python).
---

# Instalar a Vatty

Você vai deixar a Vatty funcionando neste computador. O guia para humanos é o `INSTALAR.md` (mesmas peças,
mesmos comandos). Fale com a pessoa como a Vatty, curto e claro.

## Regras

- **Confira antes de instalar.** Só instale o que falta, e diga o que vai instalar antes.
- **`sudo` é da pessoa.** Você não digita senha. Mostre o comando e peça para ela rodar no próprio Claude Code
  com `!` na frente (ex.: `! sudo dnf install tesseract`) ou num terminal, e espere ela dizer que rodou.
- No Windows, `winget` pode pedir confirmação na tela: avise.
- Nada fora disso: não mexa em outras pastas, não apague nada, não mude configuração do sistema além dos pacotes.

## Passo 1: descobrir o sistema

- Windows: `$env:OS` ou `ver`. Linux: `cat /etc/os-release` (ID: `fedora`, `ubuntu`...) e `echo $XDG_SESSION_TYPE`
  (`wayland` ou `x11`, importa para gravar a tela).

## Passo 2: conferir cada peça

Rode e anote o que falta:

| Peça | Conferir | Obrigatória |
|---|---|---|
| Python 3.14 | `python3.14 --version` (Windows: `py -3.14 --version`) | sim |
| Git | `git --version` | sim |
| ffmpeg | `ffmpeg -version` (no Fedora, se a primeira linha disser `ffmpeg-free` ou faltar `x11grab`/`pulse` em `ffmpeg -devices`, trocar pelo do RPM Fusion) | sim |
| Deno ou Node | `deno --version` ou `node --version` (Node 20 ou mais) | para YouTube |
| Tesseract + português | `tesseract --list-langs` (precisa de `por`) | para ler a tela |
| GStreamer (só Linux Wayland) | `gst-inspect-1.0 pipewiresrc` e `gst-inspect-1.0 openh264enc` (ou `x264enc`) e `gst-inspect-1.0 h264parse` | para gravar a tela |
| PipeWire (só Linux) | `pactl info` (a linha "Server Name" diz PipeWire) | para gravar o som |
| Claude Code | `claude --version` | para os agentes |

## Passo 3: instalar o que falta

**Fedora** (peça para a pessoa rodar, são `sudo`):

1. RPM Fusion e o ffmpeg completo, se o ffmpeg faltar ou for o `ffmpeg-free`:
   `sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm`
   e depois `sudo dnf swap ffmpeg-free ffmpeg --allowerasing`
2. O resto, só os que faltam: `sudo dnf install git python3 nodejs tesseract tesseract-langpack-por gstreamer1-plugins-good gstreamer1-plugins-bad-free pipewire-gstreamer gstreamer1-plugin-openh264`

**Ubuntu/Debian:** `sudo apt install git ffmpeg nodejs tesseract-ocr tesseract-ocr-por gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-pipewire gstreamer1.0-plugins-ugly`. Python 3.14 pelo PPA `deadsnakes` se faltar.

**Windows:** `winget install Python.Python.3.14 Git.Git Gyan.FFmpeg DenoLand.Deno UB-Mannheim.TesseractOCR` (só os que faltam).
Depois, a pessoa precisa fechar e abrir o terminal (e o Claude Code) para o PATH valer. No instalador do
Tesseract, marcar **Portuguese**.

**Claude Code** (se a pessoa ainda não estiver nele, o que é raro aqui): Linux `curl -fsSL https://claude.ai/install.sh | bash`;
Windows `irm https://claude.ai/install.ps1 | iex`.

## Passo 4: o projeto

Na pasta do projeto (sem sudo, você mesmo roda):

```bash
python3.14 -m venv .venv                       # Windows: py -3.14 -m venv .venv
.venv/bin/python -m pip install -e ".[gravacao]"   # Windows: .venv\Scripts\python.exe -m pip ...
.venv/bin/python -m pip install -U "yt-dlp[default,curl-cffi]"
```

Pergunte se a pessoa quer os extras `falantes` (quem falou) e `ata` (.docx/.pdf): `pip install -e ".[gravacao,falantes,ata]"`.

## Passo 5: testar

1. `.venv/bin/python -m unittest discover -s tests`: tudo verde.
2. Saúde: `.venv/bin/python -c "from vatty.ui import saude; [print(('OK ' if i['ok'] else 'FALTA ') + i['nome']) for i in saude.checar()]"`
3. Peça para a pessoa deixar algo tocando e rode `.venv/bin/python -m vatty.cli gravar --duracao 5`: tem que
   gravar e não avisar "faixa quase muda". No Linux com Wayland, `--tela --duracao 5` abre a janela
   "Compartilhar a tela?" do sistema: a pessoa precisa clicar em compartilhar.

## Passo 6: fechar

Diga o que ficou instalado, o que ficou de fora (e para que serve), e como abrir: dois cliques em
`abrir-vatty.bat` (Windows) ou `./abrir-vatty.sh` (Linux), ou `vatty ui` com o ambiente ativo.
