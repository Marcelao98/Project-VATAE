"""
Arquivo de áudio ou vídeo -> array float32 mono 16 kHz, pronto pro Whisper.

Decodifica com o ffmpeg (aceita qualquer coisa que ele abra: .opus, .ogg,
.mp3, .m4a, .wav, .mp4...). O faster-whisper NÃO recebe o caminho: o 1.2.x
abre arquivo pelo PyAV, e o PyAV 19 recusa um parâmetro que ele passa
(TypeError "metadata_errors", visto no Escriba em 02/10/2026). Com array o
decodificador dele nem é chamado.
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np

TAXA = 16000  # o Whisper só trabalha em 16 kHz mono

COMO_INSTALAR_FFMPEG = (
    "ffmpeg não encontrado no PATH. Instale e abra um terminal novo:\n"
    "  Windows: winget install Gyan.FFmpeg\n"
    "  macOS:   brew install ffmpeg\n"
    "  Fedora:  sudo dnf install ffmpeg (ative antes o RPM Fusion: o ffmpeg-free do Fedora vem cortado)\n"
    "  Ubuntu:  sudo apt install ffmpeg"
)


class FfmpegAusente(RuntimeError):
    """O ffmpeg não está no PATH."""


class ErroDeDecodificacao(RuntimeError):
    """O ffmpeg não conseguiu ler o arquivo."""


def comando_ffmpeg(executavel: str, caminho: Path, filtro: str | None = None) -> list:
    """Linha de comando que manda PCM f32le mono 16 kHz pra saída padrão (com `filtro`, passa por ele antes)."""
    comando = [
        executavel, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(caminho),
        "-vn",
    ]
    if filtro:
        comando += ["-af", filtro]
    return comando + ["-f", "f32le", "-acodec", "pcm_f32le", "-ac", "1", "-ar", str(TAXA), "-"]


def carregar(caminho, executar=subprocess.run, achar=shutil.which, filtro: str | None = None,
             pasta_trabalho=None):
    """
    Caminho do arquivo -> (array float32, duração em segundos).
    `filtro` é uma cadeia de filtros do ffmpeg (ver preprocessar.py); `pasta_trabalho` é onde o ffmpeg
    roda, para o filtro achar um arquivo (o modelo do arnndn) só pelo nome, sem escapar caminho.
    `executar` e `achar` existem pros testes trocarem o ffmpeg por um dublê.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(f"arquivo não encontrado: {caminho}")
    executavel = achar("ffmpeg")
    if not executavel:
        raise FfmpegAusente(COMO_INSTALAR_FFMPEG)
    opcoes = {}
    if pasta_trabalho is not None:
        caminho = caminho.resolve()  # o ffmpeg vai rodar em outra pasta
        opcoes["cwd"] = str(pasta_trabalho)
    saida = executar(comando_ffmpeg(executavel, caminho, filtro), capture_output=True, **opcoes)
    if saida.returncode != 0:
        erro = saida.stderr.decode("utf-8", errors="replace").strip()
        raise ErroDeDecodificacao(f"ffmpeg não conseguiu ler {caminho.name}: {erro}")
    audio = np.frombuffer(saida.stdout, dtype=np.float32)
    return audio, len(audio) / TAXA
