#!/usr/bin/env bash
# Abre a Vatty no Linux (Fedora, Ubuntu...). Na primeira vez prepara tudo sozinho (leva uns minutos).
# Uso: ./abrir-vatty.sh   (ou dois cliques, se o gerenciador de arquivos deixar executar)
set -u
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "Primeira vez: preparando a Vatty. Isso leva uns minutos..."
  PY=$(command -v python3.14 || command -v python3)
  if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 14))'; then
    echo "Preciso do Python 3.14. Fedora: sudo dnf install python3.14 (o Fedora 43 já vem com ele)."
    exit 1
  fi
  "$PY" -m venv .venv || { echo "Não consegui criar o ambiente (.venv)."; exit 1; }
fi

echo "Conferindo as peças da Vatty..."
.venv/bin/python -m pip install -q --disable-pip-version-check -e ".[gravacao]" || {
  echo "A instalação falhou. Mande um print desta janela."; exit 1; }
# O YouTube muda toda hora: yt-dlp velho é a causa número 1 de bloqueio. Sem internet, segue assim mesmo.
.venv/bin/python -m pip install -q --disable-pip-version-check -U "yt-dlp[default,curl-cffi]" >/dev/null 2>&1

faltam=()
command -v ffmpeg >/dev/null || faltam+=("ffmpeg (Fedora: RPM Fusion + sudo dnf install ffmpeg)")
command -v deno >/dev/null || command -v node >/dev/null || faltam+=("deno, para o YouTube (curl -fsSL https://deno.land/install.sh | sh)")
command -v tesseract >/dev/null || faltam+=("tesseract, só para ler a tela (sudo dnf install tesseract tesseract-langpack-por)")
if [ "${XDG_SESSION_TYPE:-}" != "x11" ]; then
  command -v gst-launch-1.0 >/dev/null || faltam+=("GStreamer, só para gravar a tela no Wayland (sudo dnf install gstreamer1-plugins-good pipewire-gstreamer gstreamer1-plugin-openh264)")
fi
if [ ${#faltam[@]} -gt 0 ]; then
  echo; echo "Aviso, falta instalar:"; printf '  - %s\n' "${faltam[@]}"; echo
fi

exec .venv/bin/python -m vatty.cli ui
