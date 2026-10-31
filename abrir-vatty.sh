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

# O que falta (ffmpeg, Deno, Tesseract, GStreamer...): só avisa. `vatty verificar --instalar` instala.
.venv/bin/python -m vatty.cli verificar --curto && echo

exec .venv/bin/python -m vatty.cli ui
