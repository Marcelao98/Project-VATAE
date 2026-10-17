"""
Gravação da tela junto com o áudio (`vatty gravar --tela`).

O ffmpeg roda em segundo plano e grava `tela.mp4` na pasta da gravação, sem
áudio, com taxa de quadros variável: quadro igual ao anterior não é gravado,
então a tela parada quase não ocupa espaço. Dois motores:

- `ddagrab` (tela inteira, padrão): Desktop Duplication do Windows, pela placa
  de vídeo; só entrega quadro quando a tela muda. Até 30 por segundo com pouca
  CPU. Precisa do ffmpeg 6.1 ou mais novo.
- `gdigrab` (uma janela, ou se o ddagrab faltar ou falhar): copia a tela a cada
  quadro, o que gasta CPU; por isso 10 por segundo, e o `mpdecimate` tira os repetidos.

O áudio continua pelo caminho de sempre (`gravacao.py`).

Sincronia: cada faixa guarda o seu horário real de início (relógio do
sistema, em segundos). O áudio começa quando `gravacao.gravar` liga o relógio;
a tela começa quando o ffmpeg grava o primeiro quadro, calculado pelo
relatório de progresso dele (`-progress`, a cada 0,1 s): horário do relatório
menos o tempo de vídeo já escrito. `deslocamento` e `sincronizar` levam os
horários do visual para a linha do tempo do áudio, para o `[mm:ss]` da fala
bater com o da tela.

A captura real (`CapturaTela`) recebe o ffmpeg por parâmetro (`abrir`,
`achar`, `executar`), e os testes passam dublês. A prova com a tela de verdade
fica em `docs/testes-reais.md`.
"""

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ARQUIVO = "tela.mp4"
FPS_TELA = 30            # ddagrab: só grava quando a tela muda, então 30 por segundo custa pouco
FPS_JANELA = 10          # gdigrab: copia a tela a cada quadro; mais que isso pesa na CPU
LARGURA_MAX = 1920       # texto de programa é pequeno: reduzir mais estraga o OCR
ESPERA_INICIO_S = 10.0   # quanto esperar o primeiro quadro antes de usar o horário aproximado
ESPERA_FIM_S = 15.0      # quanto esperar o ffmpeg fechar o arquivo depois do "q"
MOTORES = ("ddagrab", "gdigrab")


class ErroTela(Exception):
    """Falha ao começar a gravar a tela (mensagem para o usuário)."""


def comando(exe: str, saida, *, motor: str = "ddagrab", janela: str | None = None, fps: int | None = None) -> list:
    """Linha de comando do ffmpeg. `janela` (título exato) só existe no gdigrab."""
    escala = f"scale='trunc(min({LARGURA_MAX},iw)/2)*2':-2"  # largura par (o yuv420p exige)
    if motor == "ddagrab":
        fps = fps or FPS_TELA
        # dup_frames=0: sem mudança na tela, sem quadro novo
        entrada = ["-f", "lavfi", "-i", f"ddagrab=output_idx=0:framerate={fps}:dup_frames=0,hwdownload,format=bgra"]
        filtro = escala
    else:
        fps = fps or FPS_JANELA
        entrada = ["-f", "gdigrab", "-framerate", str(fps), "-i", f"title={janela}" if janela else "desktop"]
        filtro = "mpdecimate," + escala  # tira os quadros repetidos
    return [
        exe, "-hide_banner", "-loglevel", "error", "-nostats", "-stats_period", "0.1",
        *entrada, "-an", "-vf", filtro, "-fps_mode", "vfr",
        # zerolatency: o x264 não segura quadros, então o progresso mostra o horário real da captura
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-crf", "25",
        "-pix_fmt", "yuv420p", "-g", str(fps * 2),
        # mp4 fragmentado: se o ffmpeg morrer no meio, o que já foi gravado continua legível
        "-movflags", "+frag_keyframe+empty_moov",
        "-progress", "pipe:1", "-y", str(saida),
    ]


def tem_ddagrab(exe: str, executar=subprocess.run) -> bool:
    """O ffmpeg instalado tem o ddagrab (6.1 ou mais novo, no Windows)?"""
    try:
        saida = executar([exe, "-hide_banner", "-filters"], capture_output=True)
    except OSError:
        return False
    return b"ddagrab" in (saida.stdout or b"")


def ler_progresso(linha: str) -> tuple:
    """`out_time_us=1500000` -> ('out_time_us', 1500000). Valor que não é número (`N/A`) -> None."""
    chave, _, valor = linha.strip().partition("=")
    try:
        return chave, int(valor)
    except ValueError:
        return chave, None


def deslocamento(inicios: dict) -> float:
    """
    Quanto somar a um horário da tela para cair na linha do tempo do áudio:
    início da tela menos o início do áudio (a primeira faixa de áudio). 0 se faltar algum.
    """
    audios = [v for nome, v in (inicios or {}).items() if nome != "tela"]
    if "tela" not in (inicios or {}) or not audios:
        return 0.0
    return inicios["tela"] - min(audios)


def sincronizar(dados: dict, desloc: float) -> dict:
    """
    Leva os eventos do visual para a linha do tempo do áudio. O que fica antes
    do zero do áudio é cortado (o slide que já estava na tela começa em 0) e o
    que acaba antes dele sai. O cabeçalho registra o deslocamento usado.
    """
    eventos = []
    for e in dados.get("eventos", []):
        inicio, fim = round(e["inicio"] + desloc, 1), round(e["fim"] + desloc, 1)
        if fim <= 0:
            continue
        eventos.append({**e, "inicio": max(0.0, inicio), "fim": fim})
    return {**dados, "sincronia": {"deslocamento_s": round(desloc, 3)}, "eventos": eventos}


class CapturaTela:
    """
    O ffmpeg gravando a tela em segundo plano. Abre já gravando; `parar()` fecha
    o arquivo. `inicio` é o horário real (relógio do sistema) do primeiro quadro;
    `inicio_aproximado` diz se o ffmpeg não informou e ficou o horário em que foi aberto.
    `motor` e `fps` dizem como gravou; `aviso` explica uma troca de motor.
    """

    def __init__(self, saida, *, janela: str | None = None, fps: int | None = None, abrir=subprocess.Popen,
                 achar=shutil.which, executar=subprocess.run, agora=time.time, plataforma=sys.platform,
                 espera_inicio=ESPERA_INICIO_S):
        if plataforma != "win32":
            raise ErroTela("a gravação da tela só funciona no Windows por enquanto.")
        exe = achar("ffmpeg")
        if not exe:
            raise ErroTela("ffmpeg não encontrado no PATH (precisa dele para gravar a tela).")
        self.saida = Path(saida)
        self.janela = janela
        self.aviso = None
        self._agora = agora
        # grupo próprio: o Ctrl+C que para a gravação não derruba o ffmpeg antes de fechar o arquivo
        self._abrir = lambda c: abrir(c, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        if janela:
            motores = ["gdigrab"]  # o ddagrab não grava uma janela só
        elif tem_ddagrab(exe, executar):
            motores = ["ddagrab", "gdigrab"]
        else:
            motores = ["gdigrab"]
            self.aviso = (f"este ffmpeg não tem o ddagrab (precisa do 6.1 ou mais novo): gravando com o gdigrab, "
                          f"que gasta mais CPU, a {fps or FPS_JANELA} quadros por segundo.")
        for motor in motores:
            erro = self._iniciar(exe, motor, fps, espera_inicio)
            if erro is None:
                return
            if motor == "ddagrab":
                self.aviso = f"o ddagrab falhou ({erro}); gravando com o gdigrab, que gasta mais CPU."
                self.saida.unlink(missing_ok=True)
        raise ErroTela(f"a gravação da tela não começou: {erro}"
                       + (f' (a janela "{janela}" está aberta?)' if janela else ""))

    def _iniciar(self, exe, motor, fps, espera_inicio) -> str | None:
        """Abre o ffmpeg e espera o primeiro quadro. Devolve o erro se ele fechou logo, ou None."""
        self.motor = motor
        self.fps = fps or (FPS_TELA if motor == "ddagrab" else FPS_JANELA)
        self.inicio = None
        self.inicio_aproximado = False
        self._primeiro_quadro = threading.Event()
        aberto_em = self._agora()
        self._proc = self._abrir(comando(exe, self.saida, motor=motor, janela=self.janela, fps=self.fps))
        # o progresso precisa ser lido até o fim: com o cano cheio, o ffmpeg trava
        self._leitor = threading.Thread(target=self._ler, daemon=True)
        self._leitor.start()
        try:
            self._primeiro_quadro.wait(espera_inicio)
        except BaseException:  # Ctrl+C na espera: o ffmpeg tem grupo próprio e ficaria gravando sozinho
            self._proc.kill()
            raise
        if self.inicio is None:
            if self._proc.poll() is not None:
                return self._erro() or "o ffmpeg fechou sem dizer por quê"
            self.inicio, self.inicio_aproximado = aberto_em, True
        return None

    def _ler(self) -> None:
        quadros = 0
        for linha in self._proc.stdout:
            chave, valor = ler_progresso(linha.decode("utf-8", errors="replace"))
            if chave == "frame" and valor:
                quadros = valor
            elif chave == "out_time_us" and valor is not None and valor >= 0 and quadros and self.inicio is None:
                self.inicio = self._agora() - valor / 1e6
                self._primeiro_quadro.set()
        self._primeiro_quadro.set()  # o ffmpeg fechou: ninguém fica esperando à toa

    def _erro(self) -> str:
        try:
            return self._proc.stderr.read().decode("utf-8", errors="replace").strip()
        except (OSError, ValueError):
            return ""

    def parar(self) -> bool:
        """Pede ao ffmpeg para fechar o arquivo. Devolve False se ele já tinha parado sozinho (janela fechada?)."""
        ate_o_fim = self._proc.poll() is None
        if ate_o_fim:
            try:
                self._proc.stdin.write(b"q")
                self._proc.stdin.flush()
                self._proc.stdin.close()
            except OSError:
                pass
            try:
                self._proc.wait(timeout=ESPERA_FIM_S)
            except subprocess.TimeoutExpired:
                self._proc.terminate()
                self._proc.wait(timeout=5)
        self._leitor.join(timeout=5)
        return ate_o_fim
