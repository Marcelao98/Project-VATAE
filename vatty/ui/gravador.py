"""
Gravação pelo painel: roda `vatty gravar` em segundo plano, mostra o tempo e o nível de cada faixa e,
ao parar, põe a transcrição na fila de sempre.

Para parar, o painel cria um arquivo que a CLI vigia (`--parar-com`): funciona igual em qualquer
sistema, sem mandar sinal para o processo. Uma gravação por vez. O subprocesso entra por parâmetro
(`popen`) para os testes.
"""

import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from .. import juntar as _juntar
from . import runner

PARADO, GRAVANDO, PARANDO, PRONTO, ERRO = "parado", "gravando", "parando", "pronto", "erro"
LOG_MAX = 40
PERFIS = ("app", "aula")
RE_NIVEL = re.compile(r"(\w+) \[([#.]{8})\]")
RE_TEMPO = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s")
RE_GRAVADO = re.compile(r"^Gravado: .*? em (.+)$")
JANELA_MAX = 200


def montar_argv(pedido: dict, gravacoes, parar_com, python: str = sys.executable) -> list:
    """Só opções conhecidas viram argumento. A transcrição vem depois, pela fila."""
    argv = [python, "-m", "vatty.cli", "gravar", "--gravacoes", str(gravacoes), "--parar-com", str(parar_com)]
    if pedido.get("microfone"):
        argv.append("--mic")
    janela = " ".join(str(pedido.get("janela") or "").split())[:JANELA_MAX]
    if janela:
        argv += ["--tela-janela", janela]
    elif pedido.get("tela"):
        argv.append("--tela")
    return argv


def ler_linha(linha: str) -> dict | None:
    """Linha do medidor da CLI (`  1:05  sistema [####....]  microfone [##......]`) -> tempo e níveis."""
    tempo, niveis = RE_TEMPO.match(linha), RE_NIVEL.findall(linha)
    if not tempo or not niveis:
        return None
    h, m, s = (int(x or 0) for x in tempo.groups())
    return {"decorrido": h * 3600 + m * 60 + s, "niveis": {nome: barra.count("#") / 8 for nome, barra in niveis}}


class Gravador:
    def __init__(self, gravacoes, fila, popen=subprocess.Popen, pasta_temporaria=None, juntar=_juntar.juntar):
        self.gravacoes = Path(gravacoes)
        self.fila = fila
        self._popen = popen
        self._juntar = juntar
        self._tmp = Path(pasta_temporaria or tempfile.gettempdir())
        self._trava = threading.Lock()
        self._estado = {"estado": PARADO}
        self._parar_com = None

    def resumo(self) -> dict:
        with self._trava:
            return dict(self._estado)

    def iniciar(self, pedido: dict) -> dict:
        with self._trava:
            if self._estado["estado"] in (GRAVANDO, PARANDO):
                raise ValueError("Já tem uma gravação rodando. Pare essa antes de começar outra.")
            tela = bool(pedido.get("tela") or pedido.get("janela"))
            opcoes = dict(pedido.get("opcoes") or {})
            opcoes["visual"] = pedido.get("perfil") if tela and pedido.get("perfil") in PERFIS else ("app" if tela else "nenhum")
            if tela:  # o vídeo da tela só é apagado se a pessoa desmarcou de propósito (manter_tela: false)
                opcoes["manter_tela"] = opcoes.get("manter_tela") is not False
            self._parar_com = self._tmp / f"vatty-parar-{id(self)}-{threading.get_ident()}"
            self._parar_com.unlink(missing_ok=True)
            argv = montar_argv(pedido, self.gravacoes, self._parar_com)
            self._estado = {"estado": GRAVANDO, "tela": tela, "decorrido": 0, "niveis": {}, "log": [],
                            "pasta": None, "erro": None, "trabalho": None, "juntado": None}
            proc = self._popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               env=runner.ambiente())
        self._thread = threading.Thread(target=self._acompanhar, args=(proc, opcoes), daemon=True)
        self._thread.start()
        return self.resumo()

    def parar(self) -> dict:
        with self._trava:
            if self._estado["estado"] != GRAVANDO:
                raise ValueError("Não tem gravação rodando.")
            self._parar_com.touch()
            self._estado["estado"] = PARANDO
        return self.resumo()

    def _acompanhar(self, proc, opcoes: dict) -> None:
        pasta, ultimo_erro = None, ""
        for linha in runner._linhas(proc.stdout):
            medida = ler_linha(linha)
            with self._trava:
                if medida:
                    self._estado.update(medida)
                    continue
                self._estado["log"] = (self._estado["log"] + [linha.strip()])[-LOG_MAX:]
            achou = RE_GRAVADO.match(linha.strip())
            if achou:
                pasta = achou.group(1).strip()
            if linha.lstrip().startswith("Erro"):
                ultimo_erro = linha.strip()
        codigo = proc.wait()
        if self._parar_com:
            self._parar_com.unlink(missing_ok=True)
        with self._trava:
            if codigo != 0 or not pasta:
                self._estado.update(estado=ERRO, erro=ultimo_erro or f"A gravação terminou com código {codigo}.")
                return
            self._estado.update(pasta=pasta)
        if opcoes.get("juntar"):  # antes da transcrição: ela pode apagar o tela.mp4
            self._juntar_tudo(pasta)
        with self._trava:
            if opcoes.get("so_gravar"):  # a pessoa transcreve depois, pela biblioteca ou pela CLI
                self._estado.update(estado=PRONTO, trabalho=None)
                return
        trabalho = self.fila.adicionar(pasta, opcoes)  # fora da trava: a fila avisa quem escuta
        with self._trava:
            self._estado.update(estado=PRONTO, trabalho=trabalho.id)

    def _juntar_tudo(self, pasta: str) -> None:
        """Tela, som do PC e microfone num arquivo só. Se falhar, só avisa: a gravação continua inteira."""
        try:
            arquivo = str(self._juntar(pasta))
            linha = f"Pronto para enviar: {arquivo}"
        except Exception as e:
            arquivo, linha = None, f"Aviso: não consegui juntar num arquivo só ({e})."
        with self._trava:
            self._estado.update(juntado=arquivo, log=(self._estado["log"] + [linha])[-LOG_MAX:])
