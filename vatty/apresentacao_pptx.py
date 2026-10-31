"""
O deck do Apresentador em PowerPoint (.pptx), com o mesmo visual do .html: fundo escuro com brilho ciano e rosa,
moldura tracejada (a costura), prints recortados numa janela e a arte da Vatty na capa e no fim.

Precisa do extra `apresentacao` (`pip install -e ".[apresentacao]"`: python-pptx, que já traz o Pillow).
Tudo é desenhado numa grade de 1600 x 900 "pontos de tela" (a mesma do .html) e convertido para a página 16:9.
As fontes são as que vêm com o Office (Calibri e Consolas), para abrir igual em qualquer PowerPoint.
"""

import io
import math
import re
from pathlib import Path

from . import apresentacao as ap

FONTE, MONO = "Calibri", "Consolas"
COR = {"fundo": "07090F", "papel": "EEF4FA", "papel2": "9FB0C4", "item": "D9E4EF", "ouvido": "2FD4F2",
       "costura": "FF9A3D", "fone": "FF7EB6", "cartao": "161D2D", "borda": "2C3650", "costura_fraca": "4A3423",
       "chip": "0D2630", "chip_borda": "1B5868"}
MARCADORES = ("ouvido", "costura", "fone")
ESQ, LARG = 110, 1380            # margem e largura útil
EMU_POR_PX = 914400 // 120       # 1600 px = 13,333 pol


class SemPptx(ap.ErroApresentacao):
    pass


def _carregar():
    try:
        import pptx  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        raise SemPptx('para salvar em .pptx falta o python-pptx: pip install -e ".[apresentacao]"') from None


def _px(v) -> int:
    return int(round(v * EMU_POR_PX))


def _rgb(nome):
    from pptx.dml.color import RGBColor
    return RGBColor.from_string(COR.get(nome, nome))


def _linhas(texto: str, largura_px: float, tam_pt: float) -> int:
    """Quantas linhas o texto ocupa (estimativa pela largura média de um caractere da Calibri)."""
    por_linha = max(1, int(largura_px / (tam_pt / 0.6 * 0.47)))
    total = 0
    for paragrafo in texto.split("\n"):
        palavras, atual, n = paragrafo.split(), 0, 1
        for p in palavras:
            if atual and atual + 1 + len(p) > por_linha:
                n, atual = n + 1, len(p)
            else:
                atual += len(p) + (1 if atual else 0)
        total += n
    return total


def _altura(texto, largura_px, tam_pt, entrelinha=1.25) -> float:
    """Altura em px. Entrelinha "simples" do PowerPoint já é ~1,2 vez o corpo da letra."""
    return _linhas(texto, largura_px, tam_pt) * tam_pt / 0.6 * max(entrelinha, 1.22)


def _largura(texto: str, tam_pt: float) -> float:
    """Largura aproximada em px de uma linha de texto na Calibri."""
    return len(texto) * tam_pt / 0.6 * 0.47


# --- imagens desenhadas com o Pillow ---------------------------------------------------------------------------

def _png(img) -> io.BytesIO:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    buf.seek(0)
    return buf


def _fundo():
    """1600 x 900: o escuro da oficina com o brilho ciano em cima à direita e o rosa embaixo à esquerda."""
    import numpy as np
    from PIL import Image
    y, x = np.mgrid[0:900, 0:1600].astype(np.float32)
    base = np.array([7, 9, 15], np.float32)
    ciano = np.clip(1 - np.hypot((x - 1410) / 1100, (y + 90) / 620), 0, 1)[..., None] ** 1.6 * 0.20
    rosa = np.clip(1 - np.hypot((x + 80) / 900, (y - 990) / 600), 0, 1)[..., None] ** 1.6 * 0.17
    img = base + ciano * (np.array([47, 212, 242]) - base) + rosa * (np.array([255, 126, 182]) - base)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGB")


def _cantos(img, raio):
    from PIL import Image, ImageDraw
    mascara = Image.new("L", img.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], raio, fill=255)
    img = img.convert("RGBA")
    img.putalpha(mascara)
    return img


def _janela(caminho: Path, recorte):
    """O print (recortado) com a barra de janela e cantos arredondados."""
    from PIL import Image, ImageDraw
    img = Image.open(caminho).convert("RGB")
    if recorte:
        x, y, w, h = recorte
        W, H = img.size
        img = img.crop((round(x / 100 * W), round(y / 100 * H), round((x + w) / 100 * W), round((y + h) / 100 * H)))
    escala = max(1, img.size[0] / 900)
    barra = int(34 * escala)
    tela = Image.new("RGB", (img.size[0], img.size[1] + barra), "#141a29")
    tela.paste(img, (0, barra))
    d = ImageDraw.Draw(tela)
    for i, cor in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        cx, r = int((22 + i * 21) * escala), int(6 * escala)
        d.ellipse([cx - r, barra // 2 - r, cx + r, barra // 2 + r], fill=cor)
    d.line([0, barra - 1, tela.size[0], barra - 1], fill="#222c43", width=max(1, int(escala)))
    d.rounded_rectangle([0, 0, tela.size[0] - 1, tela.size[1] - 1], int(16 * escala), outline="#2a3550",
                        width=max(1, int(escala)))
    return _cantos(tela, int(16 * escala))


def _arte(caminho: Path, giro: float):
    """A arte da Vatty com cantos redondos, contorno ciano e levemente girada."""
    from PIL import Image, ImageDraw
    img = _cantos(Image.open(caminho).convert("RGB"), 36)
    ImageDraw.Draw(img).rounded_rectangle([1, 1, img.size[0] - 2, img.size[1] - 2], 36, outline=(47, 212, 242, 150),
                                          width=3)
    return img.rotate(giro, resample=Image.BICUBIC, expand=True)


# --- formas e texto ----------------------------------------------------------------------------------------------

def _caixa(slide, x, y, w, h, texto, tam, cor="papel", negrito=False, fonte=FONTE, alinhar="esq", meio=False,
           destaque="ouvido", espacamento=None, link=None):
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Pt
    caixa = slide.shapes.add_textbox(_px(x), _px(y), _px(w), _px(h))
    tf = caixa.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE if meio else MSO_ANCHOR.TOP
    p = tf.paragraphs[0]
    p.alignment = {"esq": PP_ALIGN.LEFT, "dir": PP_ALIGN.RIGHT, "centro": PP_ALIGN.CENTER}[alinhar]
    p.line_spacing = 1.0 if tam >= 40 else 1.08
    for i, trecho in enumerate(re.split(r"\*\*(.+?)\*\*", texto)):
        if not trecho:
            continue
        run = p.add_run()
        run.text = trecho
        f = run.font
        f.name, f.size, f.bold = fonte, Pt(tam), negrito
        f.color.rgb = _rgb(destaque if i % 2 else cor)
        if espacamento:
            run._r.get_or_add_rPr().set("spc", str(espacamento))
        if link:
            run.hyperlink.address = link
    return caixa


def _forma(slide, tipo, x, y, w, h, preenchimento=None, borda=None, tracejado=False, raio=None, largura_borda=1.0):
    from pptx.enum.dml import MSO_LINE_DASH_STYLE
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Pt
    forma = slide.shapes.add_shape(getattr(MSO_SHAPE, tipo), _px(x), _px(y), _px(w), _px(h))
    if preenchimento:
        forma.fill.solid()
        forma.fill.fore_color.rgb = _rgb(preenchimento)
    else:
        forma.fill.background()
    if borda:
        forma.line.color.rgb = _rgb(borda)
        forma.line.width = Pt(largura_borda)
        if tracejado:
            forma.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    else:
        forma.line.fill.background()
    if raio is not None and tipo == "ROUNDED_RECTANGLE":
        forma.adjustments[0] = min(0.5, raio / max(1, min(w, h)))
    forma.shadow.inherit = False
    return forma


def _figura(slide, img, x, y, w_max, h_max, centralizar=True):
    """Põe a imagem no maior tamanho que cabe em w_max x h_max. Devolve (x, y, w, h)."""
    proporcao = img.size[0] / img.size[1]
    w = min(w_max, h_max * proporcao)
    h = w / proporcao
    if centralizar:
        x, y = x + (w_max - w) / 2, y + (h_max - h) / 2
    slide.shapes.add_picture(_png(img), _px(x), _px(y), _px(w), _px(h))
    return x, y, w, h


def _chips(slide, horario, url, x, y):
    for h in ap.RE_HORARIO.findall(horario or ""):
        w = len(h) * 13 + 30
        _forma(slide, "ROUNDED_RECTANGLE", x, y, w, 38, "chip", "chip_borda", raio=19)
        link = (url + ("&" if "?" in url else "?") + f"t={ap._segundos(h)}s") if url else None
        _caixa(slide, x, y, w, 38, h, 12, "ouvido", True, MONO, "centro", meio=True, link=link)
        x += w + 12


def _marcador(slide, x, y, i, lado=17):
    _forma(slide, "ROUNDED_RECTANGLE", x, y, lado, lado, MARCADORES[i % 3], raio=5)


def _base(prs, fundo_png, n, total):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(_png(fundo_png), 0, 0, prs.slide_width, prs.slide_height)
    _forma(slide, "ROUNDED_RECTANGLE", 26, 26, 1548, 848, borda="costura_fraca", tracejado=True, raio=22,
           largura_borda=1.5)
    _forma(slide, "OVAL", ESQ, 836, 10, 10, "fone")
    _caixa(slide, ESQ + 22, 828, 200, 26, "Vatty", 11, "papel2", True, MONO, espacamento=100)
    _caixa(slide, 1290, 828, 200, 26, f"{n:02d} / {total:02d}", 11, "papel2", True, MONO, "dir", espacamento=100)
    return slide


def _titulo(slide, texto, y=118, w=LARG):
    _caixa(slide, ESQ, y, w, _altura(texto, w, 40, 1.05) + 10, texto, 40, "papel", True)
    return y + _altura(texto, w, 40, 1.05)


def _lista(slide, itens, x, y, w, tam=20):
    for i, item in enumerate(itens):
        h = _altura(item, w - 44, tam)
        _marcador(slide, x, y + tam / 0.6 * 0.3, i)
        _caixa(slide, x + 44, y, w - 44, h + 6, item, tam, "item")
        y += h + 22
    return y


def _cartoes(slide, itens, y):
    colunas = 2 if len(itens) in (2, 4) else (1 if len(itens) == 1 else 3)
    gap = 24
    w = (LARG - gap * (colunas - 1)) / colunas
    linhas = math.ceil(len(itens) / colunas)
    h = max(_altura(t, w - 104, 18) for t in itens) + 60
    for i, item in enumerate(itens):
        cx, cy = ESQ + (i % colunas) * (w + gap), y + (i // colunas) * (h + gap)
        _forma(slide, "ROUNDED_RECTANGLE", cx, cy, w, h, "cartao", "borda", raio=20)
        _marcador(slide, cx + 30, cy + 34, i)
        _caixa(slide, cx + 70, cy + 28, w - 100, h - 50, item, 18, "item")
    return y + linhas * h + (linhas - 1) * gap


def _rotulo(slide, texto, y):
    _caixa(slide, ESQ, y, LARG, 30, texto.upper(), 13, "costura", True, MONO, espacamento=300)


# --- tipos de slide -----------------------------------------------------------------------------------------------

def _capa(prs, fundo, deck, fonte, total, arte):
    slide = _base(prs, fundo, 1, total)
    w = 860
    h_tit = _altura(deck["titulo"], w, 62, 1.0)
    h_sub = _altura(deck["subtitulo"], 800, 22) if deck["subtitulo"] else 0
    y = 450 - (40 + h_tit + 30 + h_sub + 70) / 2
    _rotulo(slide, "Apresentação", y)
    y += 46
    _caixa(slide, ESQ, y, w, h_tit + 10, deck["titulo"], 62, "papel", True, destaque="ouvido")
    y += h_tit + 26
    if deck["subtitulo"]:
        _caixa(slide, ESQ, y, 800, h_sub + 8, deck["subtitulo"], 22, "papel2")
        y += h_sub + 24
    data = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(fonte.get("data") or ""))
    detalhe = " · ".join(v for v in (fonte.get("canal"), data and f"{data[3]}/{data[2]}/{data[1]}") if v)
    if detalhe:
        _caixa(slide, ESQ, y, 800, 30, detalhe, 13, "papel2", fonte=MONO)
    if arte:
        _figura(slide, arte[0], 1000, 80, 520, 730)
    return slide


def _slide(prs, fundo, s, n, total, pasta, url, arte):
    slide = _base(prs, fundo, n, total)
    tipo, itens = s["tipo"], s["itens"]
    janela = None
    if s["print"]:
        alvo = (pasta / s["print"]).resolve()
        if pasta.resolve() in alvo.parents and alvo.is_file():
            janela = _janela(alvo, s["recorte"])

    if tipo == "passos":
        y = _titulo(slide, s["titulo"]) + 70
        k, gap = max(1, len(itens)), 26
        w = (LARG - gap * (k - 1)) / k
        h = max([_altura(t, w - 52, 17) for t in itens] + [80]) + 120
        for i, t in enumerate(itens):
            x = ESQ + i * (w + gap)
            _forma(slide, "ROUNDED_RECTANGLE", x, y, w, h, "cartao", "borda", raio=22)
            _caixa(slide, x + 26, y + 30, w - 52, 60, f"{i + 1:02d}", 31, "ouvido" if i % 2 == 0 else "costura",
                   True, MONO)
            _caixa(slide, x + 26, y + 104, w - 52, h - 120, t, 17, "item")
            if i < k - 1:
                _forma(slide, "RECTANGLE", x + w + 3, y + 62, gap - 6, 4, "costura")
        y += h + 34
    elif tipo == "destaque":
        _rotulo(slide, s["titulo"], 190)
        grande = s["destaque"] or s["titulo"]
        h = _altura(grande, LARG - 100, 80, 0.98)
        _caixa(slide, ESQ, 236, LARG - 100, h + 20, grande, 80, "ouvido", True, destaque="fone")
        y, x = 236 + h + 48, ESQ
        for i, item in enumerate(itens):
            w = min(LARG, _largura(item, 18) + 60)
            if x + w > ESQ + LARG:
                x, y = ESQ, y + 52
            _marcador(slide, x, y + 10, i)
            _caixa(slide, x + 36, y, w - 36, 40, item, 18, "item")
            x += w + 30
        y += 70
    elif tipo == "imagem" and janela is not None:
        y = _titulo(slide, s["titulo"], 100) + 30
        legenda = itens[:3]
        h_max = 790 - y - (150 if legenda else 60)
        _, fy, _, fh = _figura(slide, janela, ESQ, y, LARG, h_max)
        y, x = fy + fh + 30, ESQ
        for i, item in enumerate(legenda):
            w = min(LARG, _largura(item, 16) + 50)
            if x + w > ESQ + LARG:
                x, y = ESQ, y + 44
            _marcador(slide, x, y + 8, i, 15)
            _caixa(slide, x + 30, y, w - 30, 36, item, 16, "item")
            x += w + 30
        y += 56
    elif tipo == "citacao":
        _rotulo(slide, s["titulo"], 220)
        _caixa(slide, ESQ - 8, 236, 200, 160, "“", 140, "fone", True, "Georgia")
        citacao = s["citacao"] or " ".join(itens)
        h = _altura(citacao, 1300, 46, 1.05)
        _caixa(slide, ESQ, 380, 1300, h + 20, citacao, 46, "papel", True)
        y = 380 + h + 40
    elif tipo == "fim" or janela is not None:
        w_texto = 560 if janela is not None else 860
        h_lista = sum(_altura(t, w_texto - 44, 20) + 22 for t in itens)
        h_tit = _altura(s["titulo"], w_texto, 40, 1.05)
        y = max(110, 450 - (h_tit + 40 + h_lista + 60) / 2)
        _caixa(slide, ESQ, y, w_texto, h_tit + 10, s["titulo"], 40, "papel", True)
        y = _lista(slide, itens, ESQ, y + h_tit + 40, w_texto) + 10
        if tipo == "fim" and arte:
            _figura(slide, arte[1], 1060, 120, 440, 660)
        elif janela is not None:
            _figura(slide, janela, 740, 100, 750, 700)
    else:
        y = _titulo(slide, s["titulo"]) + 50
        y = _cartoes(slide, itens, y) + 34 if itens else y
    _chips(slide, s["horario"], url, ESQ, min(y, 770))
    if s["notas"]:
        slide.notes_slide.notes_text_frame.text = s["notas"]
    return slide


def para_pptx(deck: dict, pasta, destino, fonte: dict | None = None, arte=ap.ARTE) -> Path:
    """Escreve o deck em `destino` (.pptx) e devolve o caminho."""
    _carregar()
    from pptx import Presentation
    pasta, fonte, destino = Path(pasta), fonte or {}, Path(destino)
    prs = Presentation()
    prs.slide_width, prs.slide_height = _px(1600), _px(900)
    prs.core_properties.title = deck["titulo"]
    url = fonte.get("url", "") if fonte.get("tipo") == "youtube" else ""
    total = len(deck["slides"]) + 1
    fundo = _fundo()
    imagens_arte = (_arte(Path(arte), -2), _arte(Path(arte), 2)) if arte and Path(arte).is_file() else None
    _capa(prs, fundo, deck, fonte, total, imagens_arte)
    for i, s in enumerate(deck["slides"]):
        _slide(prs, fundo, s, i + 2, total, pasta, url, imagens_arte)
    prs.save(destino)
    return destino
