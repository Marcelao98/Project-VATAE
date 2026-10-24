# Instalar a Vatty

Duas versões deste guia:

- **Com o Claude Code (mais fácil):** abra o Claude Code na pasta do projeto e diga **"instala a Vatty"**. Ele
  segue a skill `.claude/skills/instalar-vatty/SKILL.md`: confere o que já existe, instala o resto e testa. Os
  comandos que pedem senha (`sudo`) ele mostra para você rodar.
- **Na mão:** este arquivo. É mais trabalho, mas dá para fazer tudo sozinho.

## O que a Vatty precisa

| Peça | Para quê | Obrigatória? | Windows | Linux (Fedora) |
|---|---|---|---|---|
| Python 3.14 | rodar a Vatty | sim | ✅ | ✅ (já vem no Fedora 43) |
| Git | baixar e atualizar o projeto | sim | ✅ | ✅ |
| ffmpeg | ler áudio e vídeo, gravar a tela | sim | ✅ | ✅ (do RPM Fusion) |
| Deno (ou Node) | baixar do YouTube sem bloqueio | para YouTube | ✅ | ✅ |
| Tesseract + português | ler o texto da tela (slides, perfil app) | para ler a tela | ✅ | ✅ |
| GStreamer + PipeWire | gravar a tela no Wayland | só Linux, só para gravar a tela | não usa | ✅ |
| Claude Code | os agentes (pontos-chave, ata, bugs...) | para os agentes | ✅ | ✅ |

Pacotes Python (o `pip` instala sozinho): `faster-whisper`, `numpy`, `yt-dlp`. Extras: `gravacao`
(Windows: `pyaudiowpatch`; Linux: `jeepney`), `falantes` (`sherpa-onnx`), `ata` (`python-docx`, `reportlab`).

### O que muda entre Windows e Linux

Só a **gravação** do PC. Todo o resto (transcrição, YouTube, slides, agentes, painel) é igual.

| | Windows | Linux |
|---|---|---|
| Som do PC e microfone | PyAudioWPatch (WASAPI) | ffmpeg lendo o PipeWire (fonte "monitor") |
| Tela inteira | ffmpeg `ddagrab` (placa de vídeo, até 30 quadros/s) | X11: ffmpeg `x11grab`. Wayland (padrão do Fedora): portal do sistema + GStreamer; na primeira vez o sistema pergunta "Compartilhar a tela?" |
| Uma janela só (`--tela-janela`) | ffmpeg `gdigrab` | ainda não |
| Abrir com dois cliques | `abrir-vatty.bat` | `abrir-vatty.sh` |

## Windows

No PowerShell:

```powershell
winget install Python.Python.3.14 Git.Git Gyan.FFmpeg DenoLand.Deno UB-Mannheim.TesseractOCR
```

Feche e abra o PowerShell (para o PATH valer). O Tesseract não entra no PATH sozinho: a Vatty procura em
`C:\Program Files\Tesseract-OCR` mesmo assim. No instalador dele, marque o idioma **Portuguese**.

```powershell
git clone https://github.com/Marcelao98/Project-VATAE.git
cd Project-VATAE
```

Depois é só dar **dois cliques em `abrir-vatty.bat`**: na primeira vez ele cria o ambiente, instala tudo e abre
o painel no navegador.

Claude Code (para os agentes): `irm https://claude.ai/install.ps1 | iex`, depois `claude` uma vez para entrar
na sua conta.

## Linux (Fedora 43)

1. **RPM Fusion**, porque o ffmpeg que vem no Fedora (`ffmpeg-free`) não tem tudo:

   ```bash
   sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm
   sudo dnf swap ffmpeg-free ffmpeg --allowerasing
   ```

2. **O resto:**

   ```bash
   sudo dnf install git python3 nodejs tesseract tesseract-langpack-por \
       gstreamer1-plugins-good gstreamer1-plugins-bad-free pipewire-gstreamer gstreamer1-plugin-openh264
   ```

   O `nodejs` serve para o YouTube (o Deno também serve: `curl -fsSL https://deno.land/install.sh | sh`).
   Os pacotes `gstreamer1-*` e `pipewire-gstreamer` só são usados para gravar a tela.

3. **O projeto:**

   ```bash
   git clone https://github.com/Marcelao98/Project-VATAE.git
   cd Project-VATAE
   ./abrir-vatty.sh
   ```

   Na primeira vez ele cria o ambiente e instala tudo. Ele avisa se faltar alguma peça e abre o painel no
   navegador.

4. **Claude Code**, para os agentes: `curl -fsSL https://claude.ai/install.sh | bash`, depois `claude` uma vez
   para entrar na sua conta.

**Ubuntu/Debian:** os mesmos passos, sem o RPM Fusion. O Python 3.14 não vem no Ubuntu 24.04: use o PPA
`deadsnakes` (`python3.14 python3.14-venv`). O resto: `sudo apt install git ffmpeg nodejs tesseract-ocr
tesseract-ocr-por gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-pipewire gstreamer1.0-plugins-ugly`


## Instalar sem o lançador

Se preferir o terminal:

```bash
python3.14 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[gravacao]"         # opcionais: ".[gravacao,falantes,ata]"
vatty ui                             # o painel
python -m unittest discover -s tests # conferir se está tudo certo
```

## Conferir

- `vatty ui`, aba Começar: se faltar algo essencial, a tela avisa o que e como instalar.
- `vatty gravar --duracao 5` grava 5 s do som do PC (deixe algo tocando). Com `--tela`, grava a tela junto. No
  Fedora, na primeira vez aparece a janela "Compartilhar a tela?" do sistema; depois ela não pergunta mais
  (a permissão fica em `~/.vatty/portal-tela.txt`; apague o arquivo para escolher de novo).
- Algo deu errado? O passo a passo de teste está em `docs/testes-reais.md`.
