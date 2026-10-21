"""
Os agentes pelo Claude Code instalado neste PC (`claude -p`).

Gravar e transcrever nunca precisam disto. Quando o painel pede agentes, a transcrição termina, o
`pedidos.json` é anotado e, se o Claude Code existir aqui, ele é chamado na pasta do projeto (onde
estão o CLAUDE.md e `.claude/agents/`) para fazer os pedidos pendentes daquela pasta. O pacote Python
não fala com API nenhuma: quem usa a IA é o Claude Code, com a conta de quem está no PC.

O pedido vai pelo stdin (no Windows o `claude` costuma ser um .cmd, e argumento com aspas num .cmd é
frágil). O Claude Code só pode ler e escrever arquivos: nada de terminal.
"""

import json
import shutil
import subprocess
import threading
from pathlib import Path

from . import runner
from .fila import Cancelado

PROJETO = Path(__file__).resolve().parent.parent.parent   # onde estão o CLAUDE.md e .claude/agents/
FERRAMENTAS = "Read,Write,Edit,Glob,Grep,Task,Agent"         # Task/Agent: o nome muda entre versões
TEXTO_MAX = 300
LIMITE_S = 30 * 60   # passou disso, o Claude Code é encerrado (travou esperando login, por exemplo)


def achar(procurar=shutil.which) -> str | None:
    return procurar("claude")


def pedido(pasta) -> str:
    return (f"Faz os pedidos da Vatty da pasta {Path(pasta).resolve()}: leia o pedidos.json dela e siga a "
            "seção \"Pedidos do painel\" do CLAUDE.md. Chame o agente de cada pedido pendente e marque como "
            "feito. Não pergunte nada a ninguém: se faltar alguma informação (por exemplo, o idioma do "
            "Tradutor, quando o objetivo não diz), pule esse pedido e diga por quê. No fim, responda com uma "
            "linha por pedido: o agente e o arquivo escrito.")


def montar_argv(exe: str, pasta) -> list:
    return [exe, "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
            "--allowedTools", FERRAMENTAS, "--add-dir", str(Path(pasta).resolve())]


def resumir(linha: str) -> str | None:
    """Uma linha do stream-json do Claude Code -> o que mostrar no log (ou None)."""
    try:
        evento = json.loads(linha)
    except ValueError:
        return None
    if evento.get("type") == "assistant":
        for parte in (evento.get("message") or {}).get("content") or []:
            if parte.get("type") != "tool_use":
                continue
            entrada = parte.get("input") or {}
            if parte.get("name") in ("Task", "Agent"):
                return f"Chamando o agente {entrada.get('subagent_type') or entrada.get('description') or ''}...".replace(" ...", "...")
            if parte.get("name") == "Write" and entrada.get("file_path"):
                return f"Escrevendo {Path(entrada['file_path']).name}"
    if evento.get("type") == "result":
        texto = " ".join(str(evento.get("result") or "").split())[:TEXTO_MAX]
        return ("Erro dos agentes: " if evento.get("is_error") else "Agentes: ") + (texto or "terminaram.")
    return None


def rodar(pasta, ctx, exe: str, popen=subprocess.Popen, cwd=PROJETO, limite_s: float = LIMITE_S) -> int:
    """Roda o Claude Code para a pasta, mostrando o andamento no log do trabalho. Devolve o código de saída."""
    ctx.progresso(None, "Agentes trabalhando")
    proc = popen(montar_argv(exe, pasta), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                 cwd=str(cwd), env=runner.ambiente())
    try:
        proc.stdin.write(pedido(pasta).encode("utf-8"))
        proc.stdin.close()
    except OSError:
        pass
    estourou = threading.Event()

    def encerrar():
        estourou.set()
        proc.kill()

    relogio = threading.Timer(limite_s, encerrar)
    relogio.daemon = True
    relogio.start()
    try:
        for linha in runner._linhas(proc.stdout):
            if ctx.cancelado:
                proc.terminate()
                raise Cancelado()
            resumo = resumir(linha)
            if resumo:
                ctx.log(resumo)
            elif not linha.lstrip().startswith("{"):
                ctx.log(linha)  # mensagem solta do Claude Code (ex.: não está logado)
        codigo = proc.wait()
        if estourou.is_set():
            ctx.log(f"Aviso: o Claude Code passou de {int(limite_s // 60)} minutos e foi encerrado.")
        return codigo
    except Cancelado:
        proc.wait()
        raise
    finally:
        relogio.cancel()
