"""
Vídeo -> quadros, via ffmpeg.

Duas coisas: uma sequência de quadros pequenos em cinza, um por intervalo, só
para comparar (nunca vão para o disco), e a extração de um quadro em boa
qualidade num horário, para o OCR e para o agente olhar.

`executar` (ffprobe, extração) e `abrir` (ffmpeg em fluxo) entram como
parâmetro para os testes trocarem por dublês.
"""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from .audio import COMO_INSTALAR_FFMPEG, FfmpegAusente

LARGURA_AMOSTRA = 320   # px: para comparar telas não precisa de mais
QUALIDADE_JPG = 3       # escala do ffmpeg (2 = ótima, 31 = pior)


class ErroDeVideo(RuntimeError):
    """O ffmpeg não conseguiu ler ou extrair do vídeo."""


def _achar(nome: str, achar) -> str:
    exe = achar(nome)
    if not exe:
        raise FfmpegAusente(COMO_INSTALAR_FFMPEG)
    return exe


def informacoes(caminho, executar=subprocess.run, achar=shutil.which) -> dict:
    """{'largura', 'altura', 'duracao_s'} do vídeo (ffprobe)."""
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(f"arquivo não encontrado: {caminho}")
    comando = [_achar("ffprobe", achar), "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height:format=duration", "-of", "json", str(caminho)]
    saida = executar(comando, capture_output=True)
    if saida.returncode != 0:
        raise ErroDeVideo(f"ffprobe não conseguiu ler {caminho.name}: {saida.stderr.decode('utf-8', errors='replace').strip()}")
    dados = json.loads(saida.stdout.decode("utf-8"))
    if not dados.get("streams"):
        raise ErroDeVideo(f"{caminho.name} não tem imagem (só áudio?)")
    fluxo = dados["streams"][0]
    return {"largura": int(fluxo["width"]), "altura": int(fluxo["height"]),
            "duracao_s": float(dados.get("format", {}).get("duration") or 0)}


def tamanho_da_amostra(largura: int, altura: int) -> tuple:
    """(largura, altura) do quadro pequeno: 320 de largura, altura par e proporcional."""
    return LARGURA_AMOSTRA, max(2, int(round(altura * LARGURA_AMOSTRA / largura / 2)) * 2)


def amostrar(caminho, largura: int, altura: int, intervalo: float, abrir=subprocess.Popen, achar=shutil.which):
    """
    Gera um array uint8 (altura x largura) em cinza a cada `intervalo` segundos,
    na ordem. `largura` e `altura` são as do vídeo (de `informacoes`); os quadros
    saem em `tamanho_da_amostra`. O primeiro quadro é o do segundo 0.
    """
    caminho = Path(caminho)
    w, h = tamanho_da_amostra(largura, altura)
    comando = [_achar("ffmpeg", achar), "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(caminho),
               "-an", "-vf", f"fps=1/{intervalo:g},scale={w}:{h},format=gray", "-f", "rawvideo", "-"]
    processo = abrir(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tamanho = w * h
    gerou = False
    try:
        while True:
            bloco = bytearray()
            while len(bloco) < tamanho:
                parte = processo.stdout.read(tamanho - len(bloco))
                if not parte:
                    break
                bloco += parte
            if len(bloco) < tamanho:   # fim (ou quadro cortado no final: descarta)
                break
            gerou = True
            yield np.frombuffer(bytes(bloco), dtype=np.uint8).reshape(h, w)
    finally:
        processo.stdout.close()
        erro = processo.stderr.read().decode("utf-8", errors="replace").strip()
        processo.stderr.close()
        processo.wait()
    if not gerou and processo.returncode != 0:
        raise ErroDeVideo(f"ffmpeg não conseguiu ler {caminho.name}: {erro}")


def extrair_quadro(caminho, segundos: float, destino, executar=subprocess.run, achar=shutil.which,
                   recorte=None) -> Path:
    """
    Salva em `destino` (.jpg) o quadro do vídeo em `segundos`, no tamanho original.
    `recorte` (x0, y0, x1, y1, em fração da tela) salva só esse pedaço.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    filtro = []
    if recorte:
        x0, y0, x1, y1 = recorte
        filtro = ["-vf", f"crop=iw*{x1 - x0:.4f}:ih*{y1 - y0:.4f}:iw*{x0:.4f}:ih*{y0:.4f}"]
    comando = [_achar("ffmpeg", achar), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-ss", f"{max(0.0, segundos):.3f}", "-i", str(caminho), *filtro,
               "-frames:v", "1", "-q:v", str(QUALIDADE_JPG), str(destino)]
    saida = executar(comando, capture_output=True)
    if saida.returncode != 0 or not destino.is_file():
        erro = saida.stderr.decode("utf-8", errors="replace").strip()
        raise ErroDeVideo(f"ffmpeg não extraiu o quadro de {segundos:.1f}s: {erro or 'sem imagem nesse horário'}")
    return destino
