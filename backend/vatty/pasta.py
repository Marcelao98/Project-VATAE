"""A pasta do vídeo: o contrato entre o código e os agentes (ver CLAUDE.md)."""

import json
import re
import unicodedata
from dataclasses import asdict
from pathlib import Path

from . import texto

TAMANHO_MAX_SLUG = 60
# Versão do formato da pasta (fonte.json, transcricao.json, visual.json). Sobe quando
# um campo muda de sentido ou sai; campo novo e opcional não muda a versão.
VERSAO_CONTRATO = 1


def slug(nome: str, sufixo: str | None = None) -> str:
    """'Aula 3: Derivadas!' -> 'aula-3-derivadas'. `sufixo` (id do vídeo) evita colisão."""
    sem_acento = unicodedata.normalize("NFD", nome)
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    base = re.sub(r"[^a-zA-Z0-9]+", "-", sem_acento).strip("-").lower()
    base = base[:TAMANHO_MAX_SLUG].rstrip("-") or "video"
    return f"{base}-{sufixo}" if sufixo else base


def _transcricao_json(resultado) -> str:
    """
    JSON com um segmento por linha: os agentes leem o arquivo por faixas de
    linhas, e com indentação normal cada segmento ocupava cinco.
    """
    cabecalho = {
        "versao": VERSAO_CONTRATO,
        "origem": resultado.origem,
        "modelo": resultado.modelo,
        "idioma": resultado.idioma,
        "duracao_s": resultado.duracao_s,
        "fonte": resultado.fonte,
        # trechos que entraram em loop com a lista de termos e foram refeitos sem ela
        "trechos_refeitos": resultado.refeitos,
    }
    if resultado.faixas:  # só gravação com duas faixas; os outros casos saem como antes
        cabecalho["faixas"] = resultado.faixas
    if getattr(resultado, "preprocessamento", None):  # só se o áudio foi pré-processado
        cabecalho["preprocessamento"] = resultado.preprocessamento
    linhas = [f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}," for k, v in cabecalho.items()]
    # `falante` só aparece quando existe (gravação com duas faixas).
    dados = [{k: v for k, v in asdict(s).items() if k != "falante" or v is not None} for s in resultado.segmentos]
    segmentos = [f"    {json.dumps(d, ensure_ascii=False)}" for d in dados]
    linhas.append('  "segmentos": [')
    if segmentos:
        linhas.append(",\n".join(segmentos))
    return "{\n" + "\n".join(linhas) + "\n  ]\n}\n"


def gravar(pasta: Path, fonte: dict, resultado) -> Path:
    """Escreve fonte.json, transcricao.json e transcricao.txt. Devolve o .txt."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)

    def escrever_json(nome, dados):
        (pasta / nome).write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    escrever_json("fonte.json", {"versao": VERSAO_CONTRATO, **fonte})
    (pasta / "transcricao.json").write_text(_transcricao_json(resultado), encoding="utf-8")
    destino = pasta / "transcricao.txt"
    if _duas_faixas(fonte, resultado.segmentos):
        # Cada canal vira parágrafos sozinho; o .txt principal é a linha do tempo deles.
        canais = texto.por_canal(resultado.segmentos)
        destino.write_text(texto.linha_do_tempo(canais), encoding="utf-8")
        for falante in texto.ROTULOS:
            (pasta / f"transcricao-{falante}.txt").write_text(
                texto.formatar_canal(canais.get(falante, [])), encoding="utf-8")
    else:
        # `[mm:ss]` em cada parágrafo: os agentes leem só este arquivo (metade do custo do
        # JSON) e ainda citam o horário.
        destino.write_text(texto.formatar_canal(texto.juntar_com_inicio(resultado.segmentos)), encoding="utf-8")
    return destino


def _duas_faixas(fonte: dict, segmentos) -> bool:
    """Gravação com as duas faixas. Uma faixa muda ainda conta: o arquivo do canal sai vazio."""
    faixas = fonte.get("faixas")
    if fonte.get("tipo") == "gravacao" and faixas is not None:
        return len(faixas) >= 2
    return texto.duas_faixas(segmentos)


def gravar_visual(pasta: Path, dados: dict) -> Path:
    """
    Escreve visual.json: o cabeçalho e depois um evento por linha (os agentes leem
    por faixas de linhas, como na transcrição). `dados["eventos"]` é a lista de eventos.
    """
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    cabecalho = {"versao": VERSAO_CONTRATO, **{k: v for k, v in dados.items() if k != "eventos"}}
    linhas = [f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}," for k, v in cabecalho.items()]
    eventos = [f"    {json.dumps(e, ensure_ascii=False)}" for e in dados.get("eventos", [])]
    linhas.append('  "eventos": [')
    if eventos:
        linhas.append(",\n".join(eventos))
    destino = pasta / "visual.json"
    destino.write_text("{\n" + "\n".join(linhas) + "\n  ]\n}\n", encoding="utf-8")
    return destino
