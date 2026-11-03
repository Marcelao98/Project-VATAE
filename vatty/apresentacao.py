"""
`vatty apresentacao <pasta>`: transforma o `apresentacao-<tema>.md` que o Apresentador escreveu na apresentação, no
formato que a pessoa escolher: `pptx` (padrão), `pdf` ou `html`. O visual é o "player" de `apresentacao_player.py`
(referência: `exemplos/apresentacao-freddy/`); PDF e PowerPoint são prints da página no navegador
(`apresentacao_render.py`), então os três saem iguais. `pptx-editavel` é o desenho simples de `apresentacao_pptx.py`,
com texto editável (e o que sai se não houver navegador).

O agente decide o que vai em cada slide; aqui só se lê o formato fixo e se desenha.

Formato do .md (o agente segue `.claude/agents/apresentador.md`):

    # Título da apresentação
    subtitulo: uma linha
    marca: Freddy               (opcional: o nome no rodapé de cada slide; sem ela, só o número)
    capa: frames/0003.jpg 30 18 40 38   (opcional: a imagem do assunto na capa e no fim, com recorte opcional;
                                caminho da pasta ou absoluto; `capa: vatty` usa a arte da Vatty; sem ela, sem arte)
    cores: fundo #f5f5f7 texto #1e1e23 destaque #bf4a62   (opcional: as cores do assunto; sem ela, as da Vatty)
    olho: Projeto pessoal · RPG de mesa   (opcional: etiqueta acima do título da capa)
    - **607** faixas            (opcional: linhas "- " antes do primeiro "## " viram etiquetas na capa)
    esconder: Subarashiki Hibi, Subahibi   (opcional: o que a pessoa mandou cortar; o código corta os prints para
                                deixar isso de fora e, se não der, tira o print do slide; ver `esconder.py`)

    ## Título do slide
    tipo: lista | passos | destaque | imagem | citacao | fim
    destaque: frase ou número grande (tipo destaque)
    - item
    print: frames/0006.jpg
    recorte: 20 10 60 80        (opcional: esquerda, topo, largura, altura, em % do print)
    citacao: o que foi dito     (tipo citacao)
    horario: [01:54]
    notas: o que dizer neste slide
    olho: etiqueta curta acima do título (opcional)
    (num slide `fim`, `destaque:` vira o botão de convite)
"""

import json
import re
import subprocess
from pathlib import Path

ARTE = Path(__file__).resolve().parent / "ui" / "static" / "vatty-arte.jpg"
TIPOS = ("lista", "passos", "destaque", "imagem", "citacao", "fim")
CHAVES = ("tipo", "destaque", "print", "recorte", "citacao", "horario", "notas", "subtitulo", "marca", "capa", "cores", "esconder", "olho")
DO_DECK = ("subtitulo", "marca", "capa", "cores", "esconder")   # valem para a apresentação inteira, antes do primeiro "## "
IMAGENS = (".png", ".jpg", ".jpeg", ".webp")
RE_COR = re.compile(r"(fundo|texto|destaque2|destaque)\s*[:=]?\s*#?([0-9a-f]{6})\b", re.I)
RE_CHAVE = re.compile(r"^(%s):\s*(.*)$" % "|".join(CHAVES), re.I)
RE_HORARIO = re.compile(r"\[(\d{1,2}(?::\d{2}){1,2})\]")


class ErroApresentacao(ValueError):
    pass


def ler(texto: str) -> dict:
    """{titulo, subtitulo, marca, capa, cores, slides: [{titulo, tipo, itens, destaque, print, recorte, citacao,
    horario, notas}]}."""
    deck = {"titulo": "", "subtitulo": "", "marca": "", "capa": None, "cores": None, "esconder": [], "olho": "",
            "itens": [], "slides": []}
    atual = None
    for linha in texto.splitlines():
        crua = linha.rstrip()
        if not crua.strip():
            continue
        if crua.startswith("# ") and not deck["titulo"]:
            deck["titulo"] = crua[2:].strip()
            continue
        if crua.startswith("## "):
            atual = {"titulo": crua[3:].strip(), "tipo": "lista", "itens": [], "destaque": "", "print": "",
                     "recorte": None, "citacao": "", "horario": "", "notas": "", "olho": ""}
            deck["slides"].append(atual)
            continue
        achou = RE_CHAVE.match(crua.strip())
        if achou:
            chave, valor = achou.group(1).lower(), achou.group(2).strip()
            if atual is None:
                if chave in ("subtitulo", "marca", "olho"):
                    deck[chave] = valor
                elif chave == "capa":
                    deck["capa"] = _capa_de(valor)
                elif chave == "esconder":
                    from . import esconder
                    deck["esconder"] += esconder.termos(valor)
                elif chave == "cores":
                    deck["cores"] = {k.lower(): v.lower() for k, v in RE_COR.findall(valor)} or None
                continue
            if chave == "tipo":
                atual["tipo"] = valor.lower() if valor.lower() in TIPOS else "lista"
            elif chave == "recorte":
                atual["recorte"] = _recorte(valor)
            elif chave not in DO_DECK:
                atual[chave] = valor
            continue
        if crua.lstrip().startswith(("- ", "* ")):
            (atual["itens"] if atual is not None else deck["itens"]).append(crua.lstrip()[2:].strip())
    if not deck["titulo"] or not deck["slides"]:
        raise ErroApresentacao("o arquivo precisa de um '# Título' e de pelo menos um '## Slide'.")
    return deck


def _capa_de(valor: str):
    """'frames/0003.jpg 30 18 40 38' -> {caminho, recorte}; 'vatty' -> a arte da Vatty; vazio/'nenhuma' -> None."""
    partes = valor.split()
    if not partes or partes[0].lower() in ("nenhuma", "nenhum", "sem"):
        return None
    if partes[0].lower() == "vatty":
        return {"caminho": str(ARTE), "recorte": None}
    recorte = _recorte(" ".join(partes[-4:])) if len(partes) >= 5 else None
    caminho = " ".join(partes[:-4]) if recorte else valor.strip()
    return {"caminho": caminho, "recorte": recorte}


def arte_do_deck(deck: dict, pasta):
    """(Path, recorte) da capa, se o arquivo existe e é imagem. Caminho relativo só vale dentro da pasta."""
    capa = deck.get("capa")
    if not capa:
        return None
    pasta = Path(pasta).resolve()
    alvo = Path(capa["caminho"]).expanduser()
    if not alvo.is_absolute():
        alvo = (pasta / alvo).resolve()
        if pasta not in alvo.parents:
            return None
    if alvo.suffix.lower() not in IMAGENS or not alvo.is_file():
        return None
    return alvo, capa["recorte"]


def abrir_imagem(caminho, deck: dict, recorte=None):
    """
    (imagem PIL, recorte que falta aplicar). Com `esconder:`, a imagem já vem recortada sem os termos (e o recorte
    que falta é None); (None, None) se não dá para garantir o corte.
    """
    from PIL import Image
    termos = deck.get("esconder") or []
    if not termos:
        return Image.open(caminho).convert("RGB"), recorte
    from . import esconder
    cache = deck.setdefault("_limpas", {})
    chave = (str(Path(caminho).resolve()), recorte)
    if chave not in cache:
        pista = (deck.get("_pistas") or {}).get(Path(caminho).name, "")
        cache[chave] = esconder.limpar(caminho, termos, pista, recorte)[0]
    return cache[chave], None


def _recorte(valor: str):
    """'20 10 60 80' -> (20, 10, 60, 80) em %, ou None se não fizer sentido."""
    try:
        x, y, w, h = (float(v) for v in valor.replace(",", " ").split())
    except ValueError:
        return None
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > 100.01 or y + h > 100.01:
        return None
    return (x, y, w, h)


def _segundos(horario: str) -> int:
    partes = [int(p) for p in horario.split(":")]
    return sum(v * 60 ** i for i, v in enumerate(reversed(partes)))


def para_html(deck: dict, pasta, fonte: dict | None = None, resolucao=None, arte=None) -> str:
    """O deck em HTML, no visual "player" (`apresentacao_player.py`). `arte`: None usa a `capa:` do roteiro."""
    from . import apresentacao_player
    return apresentacao_player.para_html(deck, pasta, fonte, arte)


FORMATOS = ("pptx", "pdf", "html", "pptx-editavel")


def montar(pasta, arquivo=None, formatos=("pptx",), ler_json=lambda p: json.loads(p.read_text(encoding="utf-8")),
           avisar=lambda msg: None, renderizar=None) -> list:
    """
    Gera, para cada apresentacao-*.md da pasta (ou só o `arquivo`), os formatos pedidos: `html` (o deck "player"),
    `pdf` e `pptx` (prints do HTML no navegador, iguais a ele) e `pptx-editavel` (o desenho antigo, texto editável).
    Sem navegador, o `pptx` sai editável (com aviso) e o `pdf` dá erro legível. Devolve os caminhos feitos.
    """
    pasta = Path(pasta)
    fontes = [pasta / arquivo] if arquivo else sorted(pasta.glob("apresentacao-*.md"))
    if not fontes or not all(f.is_file() for f in fontes):
        raise ErroApresentacao(f"não achei apresentacao-*.md em {pasta} (o agente Apresentador escreve esse arquivo).")
    desconhecidos = [f for f in formatos if f not in FORMATOS]
    if desconhecidos or not formatos:
        raise ErroApresentacao(f"formato desconhecido: {', '.join(desconhecidos) or 'nenhum'} (use {', '.join(FORMATOS)}).")
    fonte, pistas, duracao = {}, {}, 0
    try:
        fonte = ler_json(pasta / "fonte.json")
    except (OSError, ValueError):
        pass
    try:
        duracao = (ler_json(pasta / "transcricao.json") or {}).get("duracao_s") or 0
    except (OSError, ValueError, AttributeError):
        pass
    try:
        for e in ler_json(pasta / "visual.json").get("eventos") or []:   # o que o Visual já leu: a pista do esconder
            if e.get("frame"):
                nome = Path(e["frame"]).name
                pistas[nome] = (pistas.get(nome, "") + " " + (e.get("texto") or "")).strip()
    except (OSError, ValueError, AttributeError):
        pass
    if renderizar is None:
        from . import apresentacao_render
        renderizar = apresentacao_render.renderizar
    feitos = []
    for md in fontes:
        deck = ler(md.read_text(encoding="utf-8"))
        deck["_pistas"], deck["_duracao"] = pistas, duracao
        if "pptx-editavel" in formatos:
            feitos.append(_pptx_editavel(deck, pasta, md, fonte, "-editavel" if "pptx" in formatos else ""))
        pagina = para_html(deck, pasta, fonte) if {"html", "pdf", "pptx"} & set(formatos) else ""
        if "html" in formatos:
            destino = md.with_suffix(".html")
            destino.write_text(pagina, encoding="utf-8")
            feitos.append(destino)
        destinos = {f: md.with_suffix("." + f) for f in ("pdf", "pptx") if f in formatos}
        if destinos:
            notas = [""] + [s["notas"] for s in deck["slides"]]
            try:
                feitos += renderizar(pagina, len(deck["slides"]) + 1, destinos, notas, deck["titulo"])
            except (RuntimeError, OSError, subprocess.SubprocessError) as e:
                if "pdf" in destinos:
                    raise ErroApresentacao(f"sem PDF: {e}") from None
                avisar(f"Aviso: {e} O .pptx sai no desenho antigo (editável).")
                feitos.append(_pptx_editavel(deck, pasta, md, fonte))
    return feitos


def _pptx_editavel(deck, pasta, md, fonte, sufixo=""):
    from . import apresentacao_pptx
    return apresentacao_pptx.para_pptx(deck, pasta, md.with_name(md.stem + sufixo + ".pptx"), fonte)


def main(argv=None) -> int:
    import argparse
    import sys
    p = argparse.ArgumentParser(prog="vatty apresentacao",
                                description="Monta a apresentação (PowerPoint, PDF ou página HTML) a partir do apresentacao-*.md do Apresentador.")
    p.add_argument("pasta", type=Path, help="a pasta do vídeo (transcricoes/<nome>)")
    p.add_argument("--arquivo", help="só este .md (padrão: todos os apresentacao-*.md da pasta)")
    p.add_argument("--formato", nargs="+", choices=FORMATOS, default=["pptx"],
                   help="pptx (PowerPoint, padrão), pdf, html (abre no navegador) e/ou pptx-editavel (texto editável, "
                        "desenho simples). pptx e pdf usam o Chrome, o Chromium ou o Edge")
    args = p.parse_args(argv)
    try:
        feitos = montar(args.pasta, args.arquivo, tuple(args.formato), avisar=lambda m: print(m, file=sys.stderr))
    except ErroApresentacao as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
    for f in feitos:
        print(f"Apresentação pronta: {f}")
    return 0


