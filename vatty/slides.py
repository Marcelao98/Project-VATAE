"""
Vídeo ou gravação -> apresentação: um slide por tela, com o print na hora certa e o que foi dito
enquanto aquela tela estava aberta. `vatty slides <pasta>`.

Código puro, sem IA: junta o `visual.json` + `frames/` (o que a tela mostrou, de `--visual aula` ou
`app`, ou da gravação com tela) com os segmentos do `transcricao.json` (o que foi dito). Sai
`slides.html`, um arquivo só com as imagens dentro (dá para mandar para alguém e abrir offline, as
setas passam os slides) e, com reportlab, `slides.pdf` (uma página por slide).
"""

import base64
import bisect
import html
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import texto as _texto

FALA_MAX_PDF = 1400          # caracteres de fala por página do PDF (o resto vira "...")
QUEM = {"eu": "Eu", "outros": "Outros"}
COMO_INSTALAR_PDF = 'O PDF precisa do reportlab: pip install -e ".[ata]"'


class ErroSlides(Exception):
    """Pasta sem o que os slides precisam (mensagem para o usuário)."""


@dataclass
class Slide:
    inicio: float
    fim: float
    frame: str
    fala: list = field(default_factory=list)   # [(inicio, quem ou None, texto)]


def montar(eventos: list, segmentos: list, duracao: float | None = None) -> list:
    """
    Eventos do visual (só os que têm quadro) -> slides em ordem. Telas seguidas com o mesmo quadro
    viram um slide só. Cada segmento da fala vai para o slide que estava na tela quando ele começou;
    a fala de antes do primeiro slide vai para o primeiro.
    """
    slides = []
    for e in sorted((e for e in eventos if e.get("frame")), key=lambda e: e["inicio"]):
        if slides and slides[-1].frame == e["frame"]:
            continue
        slides.append(Slide(inicio=float(e["inicio"]), fim=float(e.get("fim") or e["inicio"]), frame=e["frame"]))
    if not slides:
        return []
    for atual, seguinte in zip(slides, slides[1:]):
        atual.fim = seguinte.inicio
    slides[-1].fim = max(slides[-1].fim, float(duracao or 0))
    inicios = [s.inicio for s in slides]
    for seg in sorted(segmentos, key=lambda s: s["inicio"]):
        texto = " ".join(str(seg.get("texto", "")).split())
        if not texto:
            continue
        i = max(0, bisect.bisect_right(inicios, seg["inicio"]) - 1)
        quem = seg.get("pessoa") or QUEM.get(seg.get("falante"))
        slides[i].fala.append((float(seg["inicio"]), quem, texto))
    return slides


def ler(pasta) -> tuple:
    """(fonte, slides) de uma pasta do vídeo. Levanta ErroSlides se faltar o visual."""
    pasta = Path(pasta)
    visual = pasta / "visual.json"
    if not visual.is_file():
        raise ErroSlides(f"{pasta.name} não tem visual.json. Os slides precisam do que a tela mostrou: transcreva "
                         f"com --visual aula (ou app), ou grave com --tela.")
    try:
        dados_visual = json.loads(visual.read_text(encoding="utf-8"))
        fonte = json.loads((pasta / "fonte.json").read_text(encoding="utf-8"))
        transcricao = json.loads((pasta / "transcricao.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ErroSlides(f"pasta do vídeo incompleta ({pasta}): {e}") from e
    slides = montar(dados_visual.get("eventos", []), transcricao.get("segmentos", []),
                    transcricao.get("duracao_s") or dados_visual.get("duracao_s"))
    slides = [s for s in slides if (pasta / s.frame).is_file()]
    if not slides:
        raise ErroSlides(f"{pasta.name} não tem nenhum quadro em frames/ para virar slide.")
    return fonte, slides


def _link(fonte: dict, segundos: float) -> str | None:
    if fonte.get("tipo") != "youtube" or not fonte.get("url"):
        return None
    return fonte["url"] + ("&" if "?" in fonte["url"] else "?") + f"t={int(segundos)}s"


def _faixa(s: Slide) -> str:
    return f"{_texto.horario(s.inicio)[1:-1]} a {_texto.horario(s.fim)[1:-1]}"


def _fala_html(s: Slide) -> str:
    if not s.fala:
        return '<p class="nada">Ninguém falou enquanto esta tela estava aberta.</p>'
    return "".join(f'<p><span class="h">{_texto.horario(t)}</span> '
                   + (f"<b>{html.escape(quem)}:</b> " if quem else "") + f"{html.escape(txt)}</p>"
                   for t, quem, txt in s.fala)


def para_html(pasta, fonte: dict, slides: list) -> str:
    """Um arquivo só: CSS, as imagens (em base64) e as setas do teclado."""
    pasta = Path(pasta)
    titulo = html.escape(fonte.get("titulo") or pasta.name)
    partes = []
    for n, s in enumerate(slides, start=1):
        img = base64.b64encode((pasta / s.frame).read_bytes()).decode("ascii")
        link = _link(fonte, s.inicio)
        quando = html.escape(_faixa(s))
        quando = f'<a href="{html.escape(link)}" target="_blank" rel="noopener">{quando}</a>' if link else quando
        partes.append(f'<section class="slide" id="s{n}"><header><span>{n} / {len(slides)}</span>'
                      f'<span>{quando}</span></header><img src="data:image/jpeg;base64,{img}" alt="Tela {n}">'
                      f'<div class="fala">{_fala_html(s)}</div></section>')
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titulo}: slides</title>
<style>
:root{{--fundo:#090b12;--painel:#121723;--texto:#e9f1f7;--fraco:#9fb0c4;--ciano:#2fd4f2;--ambar:#ff9a3d}}
@media (prefers-color-scheme:light){{:root{{--fundo:#f1f5f9;--painel:#fff;--texto:#0f1a2b;--fraco:#506078;--ciano:#0a7f99;--ambar:#b85c00}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--fundo);color:var(--texto);font:16px/1.55 "Segoe UI",system-ui,sans-serif}}
h1{{font-size:1.4rem;margin:24px auto 8px;max-width:1100px;padding:0 16px}}
.dica{{color:var(--fraco);max-width:1100px;margin:0 auto 16px;padding:0 16px;font-size:.9rem}}
.slide{{max-width:1100px;margin:0 auto 28px;background:var(--painel);border:2px dashed var(--fraco);border-radius:14px;padding:16px;scroll-margin-top:12px}}
.slide:target,.slide.atual{{border-color:var(--ambar)}}
header{{display:flex;justify-content:space-between;color:var(--fraco);font:600 .9rem ui-monospace,Consolas,monospace;margin-bottom:10px}}
header a{{color:var(--ciano)}}
img{{display:block;width:100%;height:auto;border-radius:8px;background:#000}}
.fala{{margin-top:12px}}.fala p{{margin:6px 0}}.h{{font:500 .85rem ui-monospace,Consolas,monospace;color:var(--ciano)}}
.nada{{color:var(--fraco);font-style:italic}}
@media print{{.dica{{display:none}}.slide{{page-break-after:always;border:0}}}}
</style></head><body>
<h1>{titulo}</h1>
<p class="dica">{len(slides)} slides feitos pela Vatty: cada tela no momento em que apareceu, com o que foi dito. Setas ← → passam.</p>
{"".join(partes)}
<script>
const s=[...document.querySelectorAll(".slide")];let i=0;
function ir(n){{i=Math.max(0,Math.min(s.length-1,n));s.forEach((x,k)=>x.classList.toggle("atual",k===i));s[i].scrollIntoView({{behavior:"smooth"}})}}
document.addEventListener("keydown",e=>{{if(e.key==="ArrowRight"||e.key==="PageDown"){{e.preventDefault();ir(i+1)}}if(e.key==="ArrowLeft"||e.key==="PageUp"){{e.preventDefault();ir(i-1)}}}});
</script></body></html>
"""


def para_pdf(pasta, fonte: dict, slides: list, destino) -> Path:
    """Uma página (A4 deitada) por slide: o print em cima, a fala embaixo."""
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate
        from reportlab.lib.utils import ImageReader
    except ImportError as e:
        raise ErroSlides(COMO_INSTALAR_PDF) from e
    pasta, destino = Path(pasta), Path(destino)
    from reportlab.lib.styles import ParagraphStyle
    estilos = getSampleStyleSheet()
    fala_estilo = ParagraphStyle("fala", parent=estilos["Normal"], fontSize=12, leading=16, spaceBefore=8)
    largura, altura = landscape(A4)
    util_l, util_a = largura - 3 * cm, (altura - 3 * cm) * 0.62

    def xml(t: str) -> str:
        return html.escape(t, quote=False)

    historia = []
    for n, s in enumerate(slides, start=1):
        caminho = pasta / s.frame
        w, h = ImageReader(str(caminho)).getSize()
        escala = min(util_l / w, util_a / h)
        historia.append(Paragraph(f"<b>{n} / {len(slides)}</b> · {xml(_faixa(s))}", estilos["Normal"]))
        historia.append(Image(str(caminho), width=w * escala, height=h * escala))
        fala = " ".join(f"{_texto.horario(t)} " + (f"{quem}: " if quem else "") + txt for t, quem, txt in s.fala)
        if len(fala) > FALA_MAX_PDF:
            fala = fala[:FALA_MAX_PDF].rsplit(" ", 1)[0] + "..."
        historia.append(Paragraph(xml(fala) if fala else "<i>Ninguém falou enquanto esta tela estava aberta.</i>",
                                  fala_estilo))
        if n < len(slides):
            historia.append(PageBreak())
    SimpleDocTemplate(str(destino), pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                      topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                      title=f"{fonte.get('titulo') or pasta.name}: slides").build(historia)
    return destino


def gerar(pasta, formatos=("html",)) -> list:
    """Escreve `slides.html` e/ou `slides.pdf` na pasta. Devolve os caminhos."""
    pasta = Path(pasta)
    fonte, slides = ler(pasta)
    feitos = []
    if "html" in formatos:
        destino = pasta / "slides.html"
        destino.write_text(para_html(pasta, fonte, slides), encoding="utf-8")
        feitos.append(destino)
    if "pdf" in formatos:
        feitos.append(para_pdf(pasta, fonte, slides, pasta / "slides.pdf"))
    return feitos
