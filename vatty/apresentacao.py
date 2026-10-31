"""
`vatty apresentacao <pasta>`: transforma o `apresentacao-<tema>.md` que o Apresentador escreveu num deck de slides
bonito: `apresentacao-<tema>.pptx` (padrão, ver `apresentacao_pptx.py`) e, se pedido, `.html` num arquivo só
(prints e arte embutidos) que funciona offline.

O agente decide o que vai em cada slide; aqui só se lê o formato fixo e se desenha. Navegação: setas, espaço,
clique, deslizar o dedo; F tela cheia; N notas de quem apresenta. Para PDF: imprimir no navegador (um slide por
página, já no tamanho certo).

Formato do .md (o agente segue `.claude/agents/apresentador.md`):

    # Título da apresentação
    subtitulo: uma linha

    ## Título do slide
    tipo: lista | passos | destaque | imagem | citacao | fim
    destaque: frase ou número grande (tipo destaque)
    - item
    print: frames/0006.jpg
    recorte: 20 10 60 80        (opcional: esquerda, topo, largura, altura, em % do print)
    citacao: o que foi dito     (tipo citacao)
    horario: [01:54]
    notas: o que dizer neste slide
"""

import base64
import html
import json
import re
from pathlib import Path

ARTE = Path(__file__).resolve().parent / "ui" / "static" / "vatty-arte.jpg"
TIPOS = ("lista", "passos", "destaque", "imagem", "citacao", "fim")
CHAVES = ("tipo", "destaque", "print", "recorte", "citacao", "horario", "notas", "subtitulo")
RE_CHAVE = re.compile(r"^(%s):\s*(.*)$" % "|".join(CHAVES), re.I)
RE_HORARIO = re.compile(r"\[(\d{1,2}(?::\d{2}){1,2})\]")
LARGURA, ALTURA = 1600, 900
PRINT_PADRAO = (1920, 1080)


class ErroApresentacao(ValueError):
    pass


def ler(texto: str) -> dict:
    """{titulo, subtitulo, slides: [{titulo, tipo, itens, destaque, print, recorte, citacao, horario, notas}]}."""
    deck = {"titulo": "", "subtitulo": "", "slides": []}
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
                     "recorte": None, "citacao": "", "horario": "", "notas": ""}
            deck["slides"].append(atual)
            continue
        achou = RE_CHAVE.match(crua.strip())
        if achou:
            chave, valor = achou.group(1).lower(), achou.group(2).strip()
            if atual is None:
                if chave == "subtitulo":
                    deck["subtitulo"] = valor
                continue
            if chave == "tipo":
                atual["tipo"] = valor.lower() if valor.lower() in TIPOS else "lista"
            elif chave == "recorte":
                atual["recorte"] = _recorte(valor)
            elif chave != "subtitulo":
                atual[chave] = valor
            continue
        if crua.lstrip().startswith(("- ", "* ")) and atual is not None:
            atual["itens"].append(crua.lstrip()[2:].strip())
    if not deck["titulo"] or not deck["slides"]:
        raise ErroApresentacao("o arquivo precisa de um '# Título' e de pelo menos um '## Slide'.")
    return deck


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


def _inline(texto: str) -> str:
    """Escapa e aceita só **negrito**."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(texto))


def _imagem(caminho: Path) -> str | None:
    if not caminho.is_file():
        return None
    tipo = "image/png" if caminho.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{tipo};base64," + base64.b64encode(caminho.read_bytes()).decode()


def _chips(horario: str, url: str) -> str:
    chips = []
    for h in RE_HORARIO.findall(horario or ""):
        if url:
            link = url + ("&" if "?" in url else "?") + f"t={_segundos(h)}s"
            chips.append(f'<a class="chip" href="{html.escape(link)}" target="_blank" rel="noopener">{h}</a>')
        else:
            chips.append(f'<span class="chip">{h}</span>')
    return f'<div class="chips">{"".join(chips)}</div>' if chips else ""


def _print(slide: dict, pasta: Path, resolucao) -> str:
    """O print numa moldura de janela; com recorte, só o pedaço pedido (fundo posicionado em %)."""
    if not slide["print"]:
        return ""
    alvo = (pasta / slide["print"]).resolve()
    if pasta.resolve() not in alvo.parents:
        return ""
    dados = _imagem(alvo)
    if not dados:
        return ""
    w_img, h_img = resolucao
    x, y, w, h = slide["recorte"] or (0, 0, 100, 100)
    proporcao = (w * w_img) / (h * h_img)
    pos_x = 0 if w >= 100 else x / (100 - w) * 100
    pos_y = 0 if h >= 100 else y / (100 - h) * 100
    estilo = (f"aspect-ratio:{proporcao:.4f};background-image:url('{dados}');"
              f"background-size:{100 * 100 / w:.3f}% auto;background-position:{pos_x:.3f}% {pos_y:.3f}%")
    return (f'<figure class="janela"><div class="barra"><i></i><i></i><i></i></div>'
            f'<div class="print" role="img" aria-label="Print da tela" style="{estilo}"></div></figure>')


def _itens(itens, classe="itens") -> str:
    if not itens:
        return ""
    colunas = 2 if len(itens) in (2, 4) else 3   # 4 cartões em 2x2, nunca 3+1
    return f'<ul class="{classe}" style="--cols:{colunas}">' + "".join(f"<li>{_inline(i)}</li>" for i in itens) + "</ul>"


def _slide(slide: dict, n: int, total: int, pasta: Path, url: str, resolucao) -> str:
    tipo, titulo = slide["tipo"], _inline(slide["titulo"])
    chips, figura = _chips(slide["horario"], url), _print(slide, pasta, resolucao)
    if tipo == "passos":
        passos = "".join(f'<li><b>{i + 1:02d}</b><span>{_inline(t)}</span></li>' for i, t in enumerate(slide["itens"]))
        corpo = f'<h2>{titulo}</h2><ol class="passos" style="--n:{max(1, len(slide["itens"]))}">{passos}</ol>{chips}'
    elif tipo == "destaque":
        corpo = (f'<p class="rotulo">{titulo}</p><p class="grande">{_inline(slide["destaque"] or slide["titulo"])}</p>'
                 f'{_itens(slide["itens"], "itens soltos")}{chips}')
    elif tipo == "imagem" and figura:
        legenda = _itens(slide["itens"][:3], "itens legenda")
        corpo = f'<h2>{titulo}</h2><div class="palco">{figura}</div>{legenda}{chips}'
    elif tipo == "citacao":
        corpo = (f'<p class="rotulo">{titulo}</p><blockquote>{_inline(slide["citacao"] or " ".join(slide["itens"]))}'
                 f'</blockquote>{chips}')
    elif tipo == "fim":
        corpo = (f'<div class="texto"><h2 class="fim-titulo">{titulo}</h2>{_itens(slide["itens"], "itens cta")}'
                 f'{chips}</div><div class="arte-fim" aria-hidden="true"></div>')
    elif figura:
        corpo = (f'<div class="texto"><h2>{titulo}</h2>{_itens(slide["itens"])}{chips}</div>'
                 f'<div class="lado">{figura}</div>')
    else:
        corpo = f'<h2>{titulo}</h2>{_itens(slide["itens"], "itens cartoes")}{chips}'
    classe = "dividido" if tipo in ("lista", "fim") and (figura or tipo == "fim") else ""
    notas = f'<aside class="notas">{_inline(slide["notas"])}</aside>' if slide["notas"] else ""
    return (f'<section class="slide t-{tipo} {classe}" data-n="{n}" aria-label="Slide {n} de {total}">'
            f'<div class="conteudo">{corpo}</div><footer><span class="marca">Vatty</span>'
            f'<span class="num">{n:02d} / {total:02d}</span></footer>{notas}</section>')


def _capa(deck: dict, fonte: dict, total: int, arte: str | None) -> str:
    data = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(fonte.get("data") or ""))
    detalhe = " · ".join(x for x in (fonte.get("canal"), data and f"{data[3]}/{data[2]}/{data[1]}") if x)
    return (f'<section class="slide t-capa" data-n="1" aria-label="Capa">'
            f'<div class="conteudo"><div class="texto"><p class="selo">Apresentação</p>'
            f'<h1>{_inline(deck["titulo"])}</h1>'
            + (f'<p class="sub">{_inline(deck["subtitulo"])}</p>' if deck["subtitulo"] else "")
            + (f'<p class="detalhe">{html.escape(detalhe)}</p>' if detalhe else "")
            + '<div class="costura-capa" aria-hidden="true"></div></div>'
            + ('<div class="arte" aria-hidden="true"></div>' if arte else "")
            + f'</div><footer><span class="marca">Vatty</span><span class="num">01 / {total:02d}</span></footer></section>')


def para_html(deck: dict, pasta, fonte: dict | None = None, resolucao=PRINT_PADRAO, arte=ARTE) -> str:
    pasta, fonte = Path(pasta), fonte or {}
    url = fonte.get("url", "") if fonte.get("tipo") == "youtube" else ""
    total = len(deck["slides"]) + 1
    dados_arte = _imagem(Path(arte)) if arte else None
    slides = [_capa(deck, fonte, total, dados_arte)]
    slides += [_slide(s, i + 2, total, pasta, url, resolucao) for i, s in enumerate(deck["slides"])]
    css_arte = f":root{{--arte:url('{dados_arte}')}}" if dados_arte else ""
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(deck["titulo"])}</title><style>{css_arte}{CSS}</style></head>'
            f'<body><main id="deck">{"".join(slides)}</main>'
            f'<div class="progresso" aria-hidden="true"><i></i></div><script>{JS}</script></body></html>')


def montar(pasta, arquivo=None, formatos=("pptx",), ler_json=lambda p: json.loads(p.read_text(encoding="utf-8"))) -> list:
    """Gera o .pptx (e/ou .html) de cada apresentacao-*.md da pasta (ou só do `arquivo`). Devolve os caminhos."""
    pasta = Path(pasta)
    fontes = [pasta / arquivo] if arquivo else sorted(pasta.glob("apresentacao-*.md"))
    if not fontes or not all(f.is_file() for f in fontes):
        raise ErroApresentacao(f"não achei apresentacao-*.md em {pasta} (o agente Apresentador escreve esse arquivo).")
    fonte, resolucao = {}, PRINT_PADRAO
    try:
        fonte = ler_json(pasta / "fonte.json")
    except (OSError, ValueError):
        pass
    try:
        resolucao = tuple(ler_json(pasta / "visual.json").get("resolucao") or PRINT_PADRAO)
    except (OSError, ValueError):
        pass
    feitos = []
    for md in fontes:
        deck = ler(md.read_text(encoding="utf-8"))
        if "pptx" in formatos:
            from . import apresentacao_pptx
            feitos.append(apresentacao_pptx.para_pptx(deck, pasta, md.with_suffix(".pptx"), fonte))
        if "html" in formatos:
            destino = md.with_suffix(".html")
            destino.write_text(para_html(deck, pasta, fonte, resolucao), encoding="utf-8")
            feitos.append(destino)
    return feitos


def main(argv=None) -> int:
    import argparse
    import sys
    p = argparse.ArgumentParser(prog="vatty apresentacao",
                                description="Monta o deck de slides (.pptx ou .html) a partir do apresentacao-*.md do Apresentador.")
    p.add_argument("pasta", type=Path, help="a pasta do vídeo (transcricoes/<nome>)")
    p.add_argument("--arquivo", help="só este .md (padrão: todos os apresentacao-*.md da pasta)")
    p.add_argument("--formato", nargs="+", choices=("pptx", "html"), default=["pptx"],
                   help="pptx (PowerPoint, padrão) e/ou html (abre no navegador, offline)")
    args = p.parse_args(argv)
    try:
        feitos = montar(args.pasta, args.arquivo, tuple(args.formato))
    except ErroApresentacao as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
    for f in feitos:
        print(f"Apresentação pronta: {f}")
    return 0


CSS = """
:root{--oficina:#07090f;--bancada:#111624;--remendo:#1a2133;--papel:#eef4fa;--papel-2:#9fb0c4;--ouvido:#2fd4f2;
--costura:#ff9a3d;--fone:#ff7eb6;--fio:#2c3650;--fonte:"Avenir Next","Segoe UI Variable","Segoe UI",Inter,system-ui,sans-serif;
--mono:ui-monospace,"Cascadia Mono",Consolas,monospace;--escala:1}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:#000;overflow:hidden}
body{font-family:var(--fonte);color:var(--papel)}
#deck{position:fixed;inset:0;display:grid;place-items:center}
.slide{position:absolute;left:50%;top:50%;width:1600px;height:900px;margin:-450px 0 0 -800px;transform:scale(var(--escala));
opacity:0;visibility:hidden;transition:opacity .45s ease;overflow:hidden;padding:88px 110px 96px;
background:radial-gradient(1100px 620px at 88% -10%,rgba(47,212,242,.16),transparent 60%),
radial-gradient(900px 600px at -5% 110%,rgba(255,126,182,.13),transparent 60%),var(--oficina)}
.slide::before{content:"";position:absolute;inset:26px;border:2px dashed rgba(255,154,61,.28);border-radius:22px;pointer-events:none}
.slide.ativo{opacity:1;visibility:visible}
.conteudo{position:relative;height:100%;display:flex;flex-direction:column;justify-content:center;gap:34px}
h1,h2{margin:0;letter-spacing:-.025em;line-height:1.04}
h1{font-size:104px;font-weight:850;background:linear-gradient(100deg,#fff 10%,var(--ouvido) 55%,var(--fone));
-webkit-background-clip:text;background-clip:text;color:transparent;max-width:900px}
h2{font-size:66px;font-weight:800;max-width:1250px}
h2 strong,.grande strong,li strong{color:var(--ouvido);font-weight:inherit}
.selo,.rotulo{margin:0;font:700 22px/1 var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--costura)}
.sub{margin:0;font-size:36px;line-height:1.35;color:var(--papel-2);max-width:820px}
.detalhe{margin:0;font:500 22px/1 var(--mono);color:var(--papel-2)}
.costura-capa{width:340px;height:6px;border-radius:3px;background:repeating-linear-gradient(90deg,var(--costura) 0 22px,transparent 22px 34px)}
footer{position:absolute;left:110px;right:110px;bottom:46px;display:flex;justify-content:space-between;
font:600 18px/1 var(--mono);color:var(--papel-2);letter-spacing:.08em}
.marca::before{content:"";display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--fone);margin-right:12px;
box-shadow:0 0 14px var(--fone);vertical-align:1px}
/* capa e fim: arte à direita */
.t-capa .conteudo{flex-direction:row;align-items:center;justify-content:space-between}
.t-capa .texto{display:flex;flex-direction:column;gap:30px}
.arte,.arte-fim{flex:none;width:470px;height:705px;border-radius:26px;background:var(--arte) center/cover;
box-shadow:0 30px 90px rgba(0,0,0,.6),0 0 0 2px rgba(47,212,242,.35),0 0 60px rgba(47,212,242,.18);transform:rotate(2deg)}
.arte-fim{width:380px;height:570px;transform:rotate(-2deg)}
.dividido .conteudo{flex-direction:row;align-items:center;gap:70px}
.dividido .texto{flex:1;display:flex;flex-direction:column;gap:34px}
.dividido .lado{flex:1.25;min-width:0}
/* listas */
.itens{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:22px}
.itens li{position:relative;padding-left:46px;font-size:34px;line-height:1.3;color:#d9e4ef}
.itens li::before{content:"";position:absolute;left:0;top:.42em;width:20px;height:20px;border-radius:6px;
background:var(--ouvido);box-shadow:0 0 18px rgba(47,212,242,.6)}
.itens li:nth-child(3n+2)::before{background:var(--costura);box-shadow:0 0 18px rgba(255,154,61,.55)}
.itens li:nth-child(3n)::before{background:var(--fone);box-shadow:0 0 18px rgba(255,126,182,.55)}
.cartoes{display:grid;grid-template-columns:repeat(var(--cols),1fr);gap:24px;max-width:1380px}
.cartoes li{background:linear-gradient(160deg,var(--remendo),var(--bancada));border:1px solid var(--fio);border-radius:20px;
padding:30px 30px 30px 74px;font-size:30px}
.cartoes li::before{left:30px;top:38px}
.cta li{font-size:32px}
/* passos: a linha de montagem */
.passos{list-style:none;margin:10px 0 0;padding:0;display:grid;grid-template-columns:repeat(var(--n),1fr);gap:22px;counter-reset:p}
.passos li{position:relative;background:linear-gradient(170deg,var(--remendo),var(--bancada));border:1px solid var(--fio);
border-radius:22px;padding:34px 26px 30px;min-height:250px;display:flex;flex-direction:column;gap:18px}
.passos li:not(:last-child)::after{content:"";position:absolute;right:-22px;top:62px;width:22px;height:4px;
background:repeating-linear-gradient(90deg,var(--costura) 0 6px,transparent 6px 10px)}
.passos b{font:800 52px/1 var(--mono);color:var(--ouvido);text-shadow:0 0 22px rgba(47,212,242,.45)}
.passos li:nth-child(even) b{color:var(--costura);text-shadow:0 0 22px rgba(255,154,61,.4)}
.passos span{font-size:28px;line-height:1.3;color:#d9e4ef}
/* destaque */
.t-destaque .conteudo{align-items:flex-start}
.grande{margin:0;font-size:150px;font-weight:880;line-height:.98;letter-spacing:-.04em;max-width:1350px;
background:linear-gradient(95deg,var(--ouvido),#9ff3ff 45%,var(--fone));-webkit-background-clip:text;background-clip:text;color:transparent}
.soltos{flex-direction:row;flex-wrap:wrap;gap:16px 44px}.soltos li{font-size:30px}
/* citação */
blockquote{margin:0;position:relative;font-size:76px;line-height:1.16;font-weight:800;letter-spacing:-.02em;max-width:1300px;padding:70px 0 0 0}
blockquote::before{content:"“";position:absolute;left:-8px;top:-60px;font:900 230px/1 Georgia,serif;color:var(--fone);opacity:.9}
/* print numa janela */
.janela{margin:0;border-radius:18px;overflow:hidden;background:#0b0f19;border:1px solid #2a3550;
box-shadow:0 30px 80px rgba(0,0,0,.55),0 0 0 1px rgba(47,212,242,.14),0 0 70px rgba(47,212,242,.12)}
.barra{height:34px;display:flex;align-items:center;gap:9px;padding:0 16px;background:#141a29;border-bottom:1px solid #222c43}
.barra i{width:12px;height:12px;border-radius:50%;background:#ff5f57}.barra i:nth-child(2){background:#febc2e}.barra i:nth-child(3){background:#28c840}
.print{width:100%;background-repeat:no-repeat}
.t-imagem .conteudo{gap:26px}.palco{flex:1;min-height:0;display:flex;justify-content:center}
.palco .janela{height:100%;max-width:100%;display:flex;flex-direction:column}.palco .print{flex:1;width:auto;height:100%}
.legenda{flex-direction:row;gap:14px 40px;flex-wrap:wrap}.legenda li{font-size:26px}
.chips{display:flex;gap:12px;flex-wrap:wrap}
.chip{font:600 20px/1 var(--mono);color:var(--ouvido);background:rgba(47,212,242,.1);border:1px solid rgba(47,212,242,.35);
padding:9px 14px;border-radius:999px;text-decoration:none}
.notas{display:none;position:absolute;left:110px;right:110px;bottom:84px;background:rgba(9,11,18,.94);border:1px solid var(--costura);
border-radius:14px;padding:18px 22px;font-size:22px;line-height:1.45;color:var(--papel)}
body.com-notas .notas{display:block}
.progresso{position:fixed;left:0;right:0;bottom:0;height:5px;background:rgba(44,54,80,.6)}
.progresso i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--ouvido),var(--fone));transition:width .35s ease}
@media (prefers-reduced-motion:reduce){.slide,.progresso i{transition:none}}
@media print{@page{size:1600px 900px;margin:0}html,body{overflow:visible;background:var(--oficina);height:auto}
#deck{position:static;display:block}.slide{position:relative;left:0;top:0;margin:0;transform:none;opacity:1;visibility:visible;
break-after:page;-webkit-print-color-adjust:exact;print-color-adjust:exact}.progresso,.notas{display:none!important}}
"""

JS = """
(()=>{const s=[...document.querySelectorAll('.slide')];let i=0;
const ajustar=()=>document.documentElement.style.setProperty('--escala',Math.min(innerWidth/1600,innerHeight/900));
const ir=n=>{i=Math.max(0,Math.min(s.length-1,n));s.forEach((x,k)=>x.classList.toggle('ativo',k===i));
document.querySelector('.progresso i').style.width=(s.length>1?i/(s.length-1)*100:100)+'%';try{history.replaceState(null,'','#'+(i+1))}catch(_){}};
addEventListener('resize',ajustar);ajustar();
addEventListener('keydown',e=>{const k=e.key;
if(['ArrowRight','ArrowDown','PageDown',' ','Enter'].includes(k)){e.preventDefault();ir(i+1)}
else if(['ArrowLeft','ArrowUp','PageUp','Backspace'].includes(k)){e.preventDefault();ir(i-1)}
else if(k==='Home')ir(0);else if(k==='End')ir(s.length-1);
else if(k==='f'||k==='F'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()}
else if(k==='n'||k==='N')document.body.classList.toggle('com-notas')});
addEventListener('click',e=>{if(e.target.closest('a'))return;ir(e.clientX>innerWidth/3?i+1:i-1)});
let x0=null;addEventListener('touchstart',e=>{x0=e.touches[0].clientX},{passive:true});
addEventListener('touchend',e=>{if(x0===null)return;const d=e.changedTouches[0].clientX-x0;if(Math.abs(d)>40)ir(d<0?i+1:i-1);x0=null});
ir((parseInt(location.hash.slice(1))||1)-1)})();
"""
