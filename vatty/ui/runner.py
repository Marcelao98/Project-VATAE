"""
Roda a Vatty de verdade para a fila da interface: um subprocesso `python -m vatty.cli ...`.

Usar o próprio comando (em vez de chamar as funções) mantém a tela igual ao terminal: o log que a
pessoa vê é o que a CLI imprime, e o painel de terminal só roda comandos `vatty`. Nada de shell livre.
"""

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

from .. import fonte
from . import claude, pedidos
from .fila import AGENTES, Cancelado

OPCOES_TEXTO = ("legenda", "whisper")
OPCOES_VISUAL = ("nenhum", "aula", "app")
OPCOES_PRE = ("sim", "nao")
RE_PROGRESSO = re.compile(r"^\s*(\d{1,3})%")
RE_PRONTO = re.compile(r"^Pronto em .*?\): (.+)$")
RE_URL = re.compile(r"^https?://\S+$", re.IGNORECASE)

ETAPAS = (  # trecho da saída da CLI -> etapa mostrada na tela
    ("Lendo o vídeo", "Lendo o vídeo"),
    ("Baixando o áudio", "Baixando o áudio"),
    ("Transcrevendo", "Ouvindo"),
    ("Separando os falantes", "Separando os falantes"),
    ("Reconhecendo as vozes", "Reconhecendo as vozes"),
    ("Procurando as trocas de tela", "Olhando a tela"),
    ("Lendo o texto de", "Lendo os slides"),
    ("Baixando o vídeo", "Baixando o vídeo"),
)


def ambiente(base=None) -> dict:
    """
    Ambiente dos subprocessos: acha o pacote `vatty` mesmo sem instalação (PYTHONPATH), escreve em UTF-8
    (no Windows o padrão seria cp1252 e os acentos viravam lixo) e sem buffer (a barra de progresso
    chega na hora).
    """
    env = dict(os.environ if base is None else base)
    raiz_do_pacote = str(Path(__file__).resolve().parent.parent.parent)
    env["PYTHONPATH"] = raiz_do_pacote + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


class EntradaInvalida(ValueError):
    pass


def validar_entrada(entrada: str) -> str:
    """URL http(s) ou caminho de arquivo/pasta. Recusa o que a CLI leria como opção (começa com '-')."""
    entrada = entrada.strip()
    if not entrada or entrada.startswith("-"):
        raise EntradaInvalida("Entrada inválida.")
    if RE_URL.match(entrada) or Path(entrada).exists():
        return entrada
    raise EntradaInvalida(f"Não achei o arquivo nem entendi o link: {entrada}")


def montar_argv(entrada: str, opcoes: dict, saida, python: str = sys.executable) -> list:
    """Só opções conhecidas e com valor válido viram argumentos; o resto é ignorado."""
    argv = [python, "-m", "vatty.cli", validar_entrada(entrada), "--saida", str(saida),
            "--texto", opcoes.get("texto") if opcoes.get("texto") in OPCOES_TEXTO else "whisper",
            "--visual", opcoes.get("visual") if opcoes.get("visual") in OPCOES_VISUAL else "nenhum",
            "--preprocessar", opcoes.get("preprocessar") if opcoes.get("preprocessar") in OPCOES_PRE else "nao"]
    if opcoes.get("manter_tela"):  # o vídeo gravado fica em gravacoes/<data>/tela.mp4
        argv.append("--manter-tela")
    falantes = str(opcoes.get("falantes", "nao")).lower()
    if falantes in ("auto", "perfis") or (falantes.isdigit() and int(falantes) >= 1):
        argv += ["--falantes", falantes]
    lang = str(opcoes.get("lang", "")).strip()
    if re.fullmatch(r"[a-z]{2,3}|auto", lang):
        argv += ["--lang", lang]
    navegador = str(opcoes.get("cookies") or "").lower()
    if navegador in fonte.NAVEGADORES:
        argv += ["--cookies-navegador", navegador]
    glossario = opcoes.get("glossario")
    if glossario and Path(glossario).is_file():
        argv += ["--glossario", str(glossario)]
    return argv


def interpretar(linha: str):
    """Linha da CLI -> (percentual ou None, etapa ou None)."""
    achou = RE_PROGRESSO.match(linha)
    if achou:
        return min(100, int(achou.group(1))), "Ouvindo"
    for trecho, etapa in ETAPAS:
        if trecho in linha:
            return None, etapa
    return None, None


def _linhas(fluxo):
    """Separa a saída por '\\n' e por '\\r' (a barra de progresso da CLI reescreve a linha com '\\r')."""
    resto = ""
    while True:
        bloco = fluxo.read1(1024) if hasattr(fluxo, "read1") else fluxo.read(1024)
        if not bloco:
            break
        resto += bloco.decode("utf-8", errors="replace")
        partes = re.split(r"[\r\n]", resto)
        resto = partes.pop()
        for p in partes:
            if p.strip():
                yield p
    if resto.strip():
        yield resto


def executar(trabalho, ctx, saida, popen=subprocess.Popen, achar_claude=None) -> str:
    """Roda a CLI para o trabalho. Devolve a pasta do vídeo. `popen` entra por parâmetro para os testes."""
    if trabalho.pista == AGENTES:
        return executar_agentes(trabalho, ctx, popen, achar_claude or claude.achar)
    opcoes = dict(trabalho.opcoes)
    padrao = Path(saida) / "glossario.txt"  # as correções que a pessoa guardou na revisão valem para os próximos
    if "glossario" not in opcoes and padrao.is_file():
        opcoes["glossario"] = str(padrao)
    argv = montar_argv(trabalho.entrada, opcoes, saida)
    proc = popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                 env=ambiente())
    pasta, ultima_erro = None, ""
    try:
        for linha in _linhas(proc.stdout):
            if ctx.cancelado:
                proc.terminate()
                raise Cancelado()
            percentual, etapa = interpretar(linha)
            if percentual is None:
                ctx.log(linha)
            if percentual is not None or etapa:
                ctx.progresso(percentual, etapa)
            achou = RE_PRONTO.match(linha)
            if achou:
                pasta = achou.group(1).strip()
            if linha.startswith("Erro"):
                ultima_erro = linha
        codigo = proc.wait()
    except Cancelado:
        proc.wait()
        raise
    if codigo != 0:
        raise RuntimeError(ultima_erro or f"A Vatty terminou com código {codigo}.")
    if not pasta:
        raise RuntimeError("A Vatty terminou sem dizer onde guardou o resultado.")
    if opcoes.get("slides"):
        _fazer_slides(pasta, ctx)
    anotados = pedidos.registrar(pasta, opcoes.get("agentes"), opcoes.get("objetivo", ""))
    if anotados:  # os agentes vão para a pista deles: a transcrição termina agora, com ou sem Claude
        ctx.enfileirar(pasta, {"agentes": anotados}, AGENTES)
        ctx.log("Pedido anotado para: " + ", ".join(pedidos.AGENTES[a][0] for a in anotados) + ". Os agentes vêm em seguida.")
    return pasta


def formatos_slides() -> tuple:
    """HTML sempre; PDF também, se o reportlab estiver instalado."""
    return ("html", "pdf") if importlib.util.find_spec("reportlab") else ("html",)


def _fazer_slides(pasta, ctx) -> None:
    """Slides com os prints. Falha vira aviso."""
    from .. import slides
    try:
        for arquivo in slides.gerar(pasta, formatos_slides()):
            ctx.log(f"Slides prontos: {arquivo}")
    except slides.ErroSlides as e:
        ctx.log(f"Aviso: sem slides: {e}")


def executar_agentes(trabalho, ctx, popen, achar_claude) -> str:
    """Pista dos agentes: roda o Claude Code local na pasta. Falha aqui nunca mexe no texto, que já está salvo."""
    pasta = trabalho.entrada
    exe = achar_claude()
    if not exe:
        raise RuntimeError("O Claude Code não está instalado neste PC. O texto está salvo e o pedido ficou anotado: "
                           "instale o Claude Code e diga \"faz os pedidos da Vatty\", ou use \"copiar prompt\".")
    nomes = ", ".join(pedidos.AGENTES[a][0] for a in trabalho.opcoes.get("agentes", []) if a in pedidos.AGENTES)
    ctx.log(f"Chamando o Claude Code para: {nomes or 'os pedidos pendentes'}.")
    if claude.rodar(pasta, ctx, exe, popen=popen) != 0:
        raise RuntimeError("Os agentes não terminaram (veja o log). O texto está salvo e o pedido continua anotado: "
                           "no Claude Code, diga \"faz os pedidos da Vatty\".")
    _montar_apresentacoes(pasta, ctx)
    return pasta


def _montar_apresentacoes(pasta, ctx) -> None:
    """O Apresentador escreve o roteiro (.md); o deck (.html) sai daqui. Sem roteiro, nada a fazer."""
    from .. import apresentacao
    if not any(Path(pasta).glob("apresentacao-*.md")):
        return
    formatos = ("pptx",) if importlib.util.find_spec("pptx") else ("html",)
    if formatos == ("html",):
        ctx.log('Aviso: sem o python-pptx a apresentação sai em .html (pip install -e ".[apresentacao]" para .pptx).')
    try:
        for arquivo in apresentacao.montar(pasta, formatos=formatos):
            ctx.log(f"Apresentação pronta: {arquivo}")
    except (apresentacao.ErroApresentacao, OSError) as e:
        ctx.log(f"Aviso: sem apresentação: {e}")
