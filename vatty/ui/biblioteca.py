"""
Biblioteca: lê as pastas de `transcricoes/` para a interface (lista, leitor, exportar).

Lógica pura sobre arquivos, sem rede e sem LLM. O nome da pasta (`slug`) que vem da tela nunca é
confiado: tem de ser exatamente uma pasta dentro da raiz.
"""

import csv
import io
import json
import re
from pathlib import Path

from .. import ata, buscar, srt

RE_MARCA = re.compile(r"\s*\[\?\]")
EXPORTAVEIS = {
    "txt": "text/plain; charset=utf-8", "md": "text/markdown; charset=utf-8",
    "srt": "application/x-subrip; charset=utf-8", "vtt": "text/vtt; charset=utf-8",
    "csv": "text/csv; charset=utf-8", "json": "application/json; charset=utf-8",
}
PADROES_GERADOS = ("pontos-chave-*.md", "didatico-*.md", "ata-*.md", "ata-*.docx", "ata-*.pdf",
                   "cartoes-*.md", "cartoes-*.csv", "pericia-*.md", "legenda.srt", "legenda.vtt", "legenda.*.srt",
                   "slides.html", "slides.pdf", "apresentacao-*.html", "apresentacao-*.md")


class NaoAchei(Exception):
    pass


def pasta_de(raiz, slug: str) -> Path:
    """A pasta `slug` dentro de `raiz`, ou NaoAchei (cobre '..', barras e pasta que não existe)."""
    raiz = Path(raiz).resolve()
    if not slug or slug in (".", "..") or "/" in slug or "\\" in slug:
        raise NaoAchei(slug)
    p = (raiz / slug).resolve()
    if p.parent != raiz or not (p / "transcricao.json").is_file():
        raise NaoAchei(slug)
    return p


def _json(arquivo: Path):
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def gerados(pasta: Path) -> list:
    achados = {a.name for padrao in PADROES_GERADOS for a in pasta.glob(padrao)}
    return sorted(achados)


def listar(raiz) -> list:
    """Uma linha por vídeo, a mais recente primeiro."""
    raiz = Path(raiz)
    saida = []
    if not raiz.is_dir():
        return saida
    for pasta in raiz.iterdir():
        dados = _json(pasta / "transcricao.json") if pasta.is_dir() else None
        if dados is None:
            continue
        fonte = _json(pasta / "fonte.json") or {}
        saida.append({
            "slug": pasta.name,
            "titulo": fonte.get("titulo") or pasta.name,
            "tipo": fonte.get("tipo", "arquivo"),
            "duracao_s": dados.get("duracao_s"),
            "origem": dados.get("origem"),
            "duvidosos": dados.get("trechos_duvidosos", 0),
            "glossario": sum((dados.get("glossario") or {}).values()),
            "gerados": gerados(pasta),
            "_mtime": (pasta / "transcricao.json").stat().st_mtime,
        })
    saida.sort(key=lambda v: v["_mtime"], reverse=True)
    for v in saida:
        del v["_mtime"]
    return saida


def _nomes(pasta: Path) -> dict:
    dados = _json(pasta / "nomes.json")
    return {str(k): str(v) for k, v in dados.items()} if isinstance(dados, dict) else {}


def _com_nomes(texto: str, pasta: Path) -> str:
    nomes = _nomes(pasta)
    return ata.aplicar_nomes(texto, nomes) if nomes else texto


def paragrafos(pasta: Path) -> list:
    """O `transcricao.txt` em [{inicio_s, horario, texto, duvidoso}] (o `[?]` sai do texto e vira flag)."""
    arquivo = pasta / "transcricao.txt"
    if not arquivo.is_file():
        return []
    saida = []
    for bloco in arquivo.read_text(encoding="utf-8").split("\n\n"):
        if not bloco.strip():
            continue
        inicio_s, horario, texto = buscar.separar_horario(_com_nomes(bloco, pasta))
        saida.append({"inicio_s": inicio_s, "horario": horario, "texto": RE_MARCA.sub("", texto).strip(),
                      "duvidoso": "[?]" in texto, "trechos": [m.strip() for m in re.findall(r"([^.?!]*?)\s*\[\?\]", texto)]})
    return saida


def ler(raiz, slug: str) -> dict:
    pasta = pasta_de(raiz, slug)
    fonte = _json(pasta / "fonte.json") or {}
    dados = _json(pasta / "transcricao.json") or {}
    return {
        "slug": slug, "fonte": fonte,
        "cabecalho": {k: v for k, v in dados.items() if k != "segmentos"},
        "paragrafos": paragrafos(pasta),
        "falantes": _json(pasta / "falantes.json"),
        "nomes": _nomes(pasta),
        "gerados": gerados(pasta),
        "tem_visual": (pasta / "visual.json").is_file(),  # dá para montar os slides com os prints
    }


def exportar(raiz, slug: str, formato: str):
    """(bytes, tipo MIME, nome do arquivo). Sem converter nada que não esteja na pasta."""
    if formato not in EXPORTAVEIS:
        raise NaoAchei(formato)
    pasta = pasta_de(raiz, slug)
    dados = _json(pasta / "transcricao.json") or {}
    segmentos = dados.get("segmentos", [])
    if formato == "txt":
        texto = (pasta / "transcricao.txt").read_text(encoding="utf-8")
    elif formato == "md":
        fonte = _json(pasta / "fonte.json") or {}
        linhas = [f"# {fonte.get('titulo') or slug}", ""]
        linhas += [f"**{p['horario']}** {p['texto']}\n" for p in paragrafos(pasta)]
        texto = "\n".join(linhas)
    elif formato in ("srt", "vtt"):
        texto = srt.montar(segmentos, formato)
    elif formato == "csv":
        saida = io.StringIO()
        w = csv.writer(saida)
        w.writerow(["inicio_s", "fim_s", "quem", "texto"])
        for s in segmentos:
            w.writerow([s["inicio"], s["fim"], s.get("pessoa") or s.get("falante") or "", s["texto"]])
        texto = saida.getvalue()
    else:
        texto = (pasta / "transcricao.json").read_text(encoding="utf-8")
    if formato != "json":
        texto = _com_nomes(texto, pasta)
    return texto.encode("utf-8"), EXPORTAVEIS[formato], f"{slug}.{formato}"


def texto_para_prompt(raiz, slug: str):
    """(título, transcrição com os nomes dados, origem) para o 'copiar prompt'."""
    pasta = pasta_de(raiz, slug)
    fonte = _json(pasta / "fonte.json") or {}
    dados = _json(pasta / "transcricao.json") or {}
    texto = _com_nomes((pasta / "transcricao.txt").read_text(encoding="utf-8"), pasta)
    return fonte.get("titulo") or slug, texto, dados.get("origem")


def arquivo_gerado(raiz, slug: str, nome: str) -> Path:
    """Um arquivo que a Vatty gerou na pasta (ata, pontos-chave...). Só os nomes conhecidos."""
    pasta = pasta_de(raiz, slug)
    if nome not in gerados(pasta):
        raise NaoAchei(nome)
    return pasta / nome
