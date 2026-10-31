"""
Pedidos para os agentes, feitos pelo painel: "quando terminar, quero a ata e os pontos-chave".

O pacote Python nunca chama IA. O painel só **anota** o pedido em `pedidos.json`, na pasta do vídeo;
quem faz é a conversa do Claude Code ("faz os pedidos da Vatty"), que lê os pendentes, chama o agente
certo e marca como feito. Para quem não usa o Claude Code, cada agente tem um "copiar prompt".
"""

import json
import time
from pathlib import Path

ARQUIVO = "pedidos.json"
PENDENTE, FEITO = "pendente", "feito"
OBJETIVO_MAX = 300

# id -> (nome, o que faz, tipo do "copiar prompt" em prompts.py)
AGENTES = {
    "escrivao": ("Escrivão", "pontos-chave", "pontos_chave"),
    "preceptor": ("Preceptor", "explicar do zero", "explicar"),
    "secretario": ("Secretário", "ata da reunião", "ata"),
    "cartas": ("Cartas", "flashcards", "cartoes"),
    "tradutor": ("Tradutor", "legenda traduzida", None),
    "perito": ("Perito", "achar bugs", "pericia"),
    "apresentador": ("Apresentador", "apresentação de slides", None),
}


def lista() -> list:
    """Os agentes que o painel oferece."""
    return [{"id": k, "nome": n, "faz": f, "prompt": t} for k, (n, f, t) in AGENTES.items()]


def registrar(pasta, agentes, objetivo: str = "", agora=time.time) -> list:
    """Acrescenta um pedido pendente por agente válido. Devolve os ids anotados (vazio se nenhum)."""
    validos = [a for a in dict.fromkeys(agentes or []) if a in AGENTES]
    if not validos:
        return []
    arquivo = Path(pasta) / ARQUIVO
    pedidos = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.is_file() else []
    quando = time.strftime("%Y-%m-%d %H:%M", time.localtime(agora()))
    objetivo = " ".join(str(objetivo or "").split())[:OBJETIVO_MAX]
    pedidos += [{"agente": a, "objetivo": objetivo, "pedido_em": quando, "estado": PENDENTE} for a in validos]
    arquivo.write_text(json.dumps(pedidos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return validos
