"""
O deck do Apresentador em HTML, no visual "player" (o do exemplo do Freddy, `exemplos/apresentacao-freddy/`).

Cada slide é uma faixa; a barra de baixo mostra o que está tocando, a faixa e o horário do vídeo de onde aquilo
saiu. As cores vêm do roteiro (`cores:`) e funcionam claras ou escuras; sem `cores:`, as da Vatty. A capa e o fim
usam a imagem do assunto (`capa:`). Um arquivo só, com as imagens embutidas: abre offline em qualquer navegador.

O mesmo HTML é a fonte do PDF e do PowerPoint (`apresentacao_render.py` tira um print de cada slide no navegador),
então os três formatos saem iguais. Com `#3c` no fim do endereço, o deck abre no slide 3 em "modo captura"
(sem moldura, no tamanho exato de 1600 x 900).
"""

import base64
import html
import io
import re
from pathlib import Path

VATTY = {"fundo": "0b0e16", "texto": "e9f1f7", "destaque": "2fd4f2", "destaque2": "ff9a3d"}
RE_HORARIO = re.compile(r"\[(\d{1,2}(?::\d{2}){1,2})\]")


# --- cores ------------------------------------------------------------------------------------------------------

def _rgb(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a: str, b: str, t: float) -> str:
    """Cor entre a e b (t=0 é a, t=1 é b), em #hex."""
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(_rgb(a), _rgb(b)))


def _clara(c: str) -> bool:
    r, g, b = (v / 255 for v in _rgb(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5


def tokens(cores: dict | None) -> dict:
    """As variáveis CSS do deck, derivadas de fundo, texto, destaque e destaque2 (claro ou escuro)."""
    c = dict(VATTY, **{k: v for k, v in (cores or {}).items() if v})
    if cores and "destaque2" not in cores:
        c["destaque2"] = _mix(c["destaque"], c["fundo"], 0.45).lstrip("#")
    fundo, texto, d1, d2 = (f"#{c[k]}" for k in ("fundo", "texto", "destaque", "destaque2"))
    clara = _clara(fundo)
    return {
        "--fundo": fundo, "--tinta": texto,
        "--papel": _mix(fundo, "#ffffff", 0.75) if clara else _mix(fundo, texto, 0.05),
        "--nevoa": _mix(fundo, texto, 0.09), "--asa": _mix(fundo, texto, 0.25),
        "--tinta-2": _mix(texto, fundo, 0.3), "--tinta-3": _mix(texto, fundo, 0.45),
        "--acento": d1, "--acento-escuro": _mix(d1, texto, 0.2) if clara else _mix(d1, "#ffffff", 0.25),
        "--acento-claro": _mix(fundo, d1, 0.16), "--acento2": d2, "--acento2-claro": _mix(fundo, d2, 0.25),
        "--sobre-acento": "#ffffff" if not _clara(d1) else "#111111",
        "--sombra": "rgba(30,30,35,.16)" if clara else "rgba(0,0,0,.45)",
        "--moldura": "#dcdde3" if clara else _mix(fundo, "#000000", 0.4),
    }


# --- pedaços ------------------------------------------------------------------------------------------------------

def _inline(texto: str) -> str:
    """Escapa e transforma **x** no destaque em itálico."""
    return re.sub(r"\*\*(.+?)\*\*", r"<em>\1</em>", html.escape(texto or ""))


def _segundos(h: str) -> int:
    partes = [int(p) for p in h.split(":")]
    return sum(v * 60 ** i for i, v in enumerate(reversed(partes)))


def _relogio(s: float) -> str:
    s = int(s or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def _data(img) -> str:
    buf = io.BytesIO()
    if img.mode in ("RGBA", "LA", "P"):
        img.save(buf, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    img.convert("RGB").save(buf, "JPEG", quality=86)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _imagem_print(slide, pasta: Path, deck: dict, largura=1600):
    """data: URI do print (recortado e sem o que foi mandado esconder), ampliado com nitidez se ficou pequeno."""
    from . import apresentacao as ap
    if not slide["print"]:
        return None
    alvo = (pasta / slide["print"]).resolve()
    if pasta.resolve() not in alvo.parents or not alvo.is_file():
        return None
    img, recorte = ap.abrir_imagem(alvo, deck, slide["recorte"])
    if img is None:
        return None
    if recorte:
        W, H = img.size
        x, y, w, h = recorte
        img = img.crop((round(x / 100 * W), round(y / 100 * H), round((x + w) / 100 * W), round((y + h) / 100 * H)))
    return _data(_nitida(img, largura))


def _nitida(img, largura):
    from PIL import Image, ImageFilter
    if img.size[0] >= largura:
        return img
    k = largura / img.size[0]
    return img.resize((largura, round(img.size[1] * k)), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 60, 2))


def _imagem_capa(arte, deck: dict):
    """data: URI da imagem do assunto. PNG recortado (fundo transparente) continua transparente."""
    from PIL import Image
    from . import apresentacao as ap
    if not arte:
        return None
    caminho, recorte = arte if isinstance(arte, tuple) else (Path(arte), None)
    dentro = Path(caminho).name in (deck.get("_pistas") or {})   # é um print da gravação: passa pelo esconder
    if deck.get("esconder") and dentro:
        img, _ = ap.abrir_imagem(Path(caminho), deck, recorte)
        if img is None:
            return None
    else:
        img = Image.open(caminho)
        img = img.convert("RGBA") if "A" in img.getbands() or img.mode == "P" else img.convert("RGB")
        if recorte:
            W, H = img.size
            x, y, w, h = recorte
            img = img.crop((round(x / 100 * W), round(y / 100 * H), round((x + w) / 100 * W), round((y + h) / 100 * H)))
    img.thumbnail((900, 900))
    return _data(img)


def _janela(dados: str, alt: str, classe="") -> str:
    return (f'<figure class="janela {classe}"><div class="barra"><i></i><i></i><i></i></div>'
            f'<img src="{dados}" alt="{html.escape(alt)}"></figure>')


def _lista(itens) -> str:
    return '<ul class="lista">' + "".join(f"<li>{_inline(i)}</li>" for i in itens) + "</ul>" if itens else ""


def _chips_horario(horario: str, url: str) -> str:
    chips = []
    for h in RE_HORARIO.findall(horario or ""):
        if url:
            link = url + ("&" if "?" in url else "?") + f"t={_segundos(h)}s"
            chips.append(f'<a class="horario" href="{html.escape(link)}" target="_blank" rel="noopener">{h}</a>')
        else:
            chips.append(f'<span class="horario">{h}</span>')
    return f'<div class="horarios">{"".join(chips)}</div>' if chips else ""


def _olho(texto: str) -> str:
    return f'<p class="olho">{_inline(texto)}</p>' if texto else ""


EQ = '<div class="eq" aria-hidden="true">' + "<i></i>" * 12 + "</div>"


# --- slides -------------------------------------------------------------------------------------------------------

def _capa(deck: dict, fonte: dict, arte: str | None) -> str:
    data = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(fonte.get("data") or ""))
    detalhe = " · ".join(x for x in (fonte.get("canal"), data and f"{data[3]}/{data[2]}/{data[1]}") if x)
    olho = deck.get("olho") or detalhe or "Apresentação"
    chips = "".join(f'<span class="chip">{_inline(i)}</span>' for i in deck.get("itens") or [])
    lado = (f'<div class="ave"><div class="ondas"></div><img src="{arte}" alt="{html.escape(deck.get("marca") or "Capa")}"></div>'
            if arte else '<div class="ave sem-arte"><div class="ondas"></div>' + EQ + "</div>")
    return (f'<div class="texto">{_olho(olho)}<h1>{_inline(deck["titulo"])}</h1>'
            + (f'<p class="sub">{_inline(deck["subtitulo"])}</p>' if deck["subtitulo"] else "")
            + EQ + (f'<div class="chips">{chips}</div>' if chips else "") + f"</div>{lado}")


def _corpo(s: dict, pasta: Path, deck: dict, url: str, arte: str | None) -> tuple:
    """(classe extra da seção, HTML de dentro)."""
    tipo, itens = s["tipo"], s["itens"]
    titulo = f'<h2>{_inline(s["titulo"])}</h2>'
    olho, horarios = _olho(s.get("olho", "")), _chips_horario(s["horario"], url)
    figura = _imagem_print(s, pasta, deck)
    if tipo == "passos":
        passos = "".join(f'<div class="passo"><b>{i + 1:02d}</b><span>{_inline(t)}</span></div>' for i, t in enumerate(itens))
        return "", f'{olho}{titulo}<div class="passos" style="--n:{max(1, len(itens))}">{passos}</div>{horarios}'
    if tipo == "destaque":
        chips = "".join(f'<span class="chip">{_inline(i)}</span>' for i in itens)
        onda = ('<svg class="onda" viewBox="0 0 1400 90" aria-hidden="true"><path d="M0 45 Q 35 5 70 45'
                + "".join(f" T {70 * k} 45" for k in range(2, 21))
                + '" class="o1"/><path d="M0 45 Q 70 80 140 45' + "".join(f" T {140 * k} 45" for k in range(2, 11))
                + '" class="o2"/></svg>')
        return "centro", (_olho(s["titulo"]) + f'<p class="enorme">{_inline(s["destaque"] or s["titulo"])}</p>{onda}'
                          + (f'<div class="chips">{chips}</div>' if chips else "") + horarios)
    if tipo == "citacao":
        return "centro", (_olho(s["titulo"]) + '<span class="aspas" aria-hidden="true">“</span>'
                          + f'<blockquote>{_inline(s["citacao"] or " ".join(itens))}</blockquote>{horarios}')
    if tipo == "fim":
        convite = f'<span class="convite"><i></i>{_inline(s["destaque"])}</span>' if s["destaque"] else ""
        lado = (f'<div class="ave fim-ave"><div class="ondas"></div><img src="{arte}" alt=""></div>' if arte
                else (_janela(figura, s["titulo"]) if figura else ""))
        return "lado-a-lado", f'<div class="texto">{olho}{titulo}{_lista(itens)}{convite}{horarios}</div>{lado}'
    if tipo == "imagem" and figura:
        legenda = _lista(itens[:3]).replace('class="lista"', 'class="lista legenda"')
        return "", f'{olho}{titulo}<div class="palco-img">{_janela(figura, s["titulo"])}</div>{legenda}{horarios}'
    if figura:
        return "", (f'<div class="duas"><div class="texto">{olho}{titulo}{_lista(itens)}{horarios}</div>'
                    f'{_janela(figura, s["titulo"], "inclinada")}</div>')
    cartoes = "".join(f'<div class="cartao"><span class="n">{i + 1:02d}</span><span>{_inline(t)}</span></div>'
                      for i, t in enumerate(itens))
    return "", f'{olho}{titulo}<div class="cartoes" style="--cols:{2 if len(itens) in (2, 4) else 3}">{cartoes}</div>{horarios}'


def para_html(deck: dict, pasta, fonte: dict | None = None, arte=None) -> str:
    """O deck inteiro, num arquivo só. `arte`: None usa a `capa:` do roteiro."""
    from . import apresentacao as ap
    pasta, fonte = Path(pasta), fonte or {}
    url = fonte.get("url", "") if fonte.get("tipo") == "youtube" else ""
    dados_arte = _imagem_capa(arte or ap.arte_do_deck(deck, pasta), deck)
    total = len(deck["slides"]) + 1
    duracao = fonte.get("duracao") or fonte.get("duracao_s") or deck.get("_duracao") or 0
    secoes = [(f'<section class="slide capa ativo" data-titulo="{html.escape(deck["titulo"])}" data-hora="00:00">'
               f'{_capa(deck, fonte, dados_arte)}</section>')]
    for s in deck["slides"]:
        classe, corpo = _corpo(s, pasta, deck, url, dados_arte)
        h = RE_HORARIO.findall(s["horario"] or "")
        notas = f'<aside class="notas">{_inline(s["notas"])}</aside>' if s["notas"] else ""
        secoes.append(f'<section class="slide {classe}" data-titulo="{html.escape(re.sub(r"[*]", "", s["titulo"]))}" '
                      f'data-hora="{h[0] if h else ""}">{corpo}{notas}</section>')
    css_vars = ";".join(f"{k}:{v}" for k, v in tokens(deck.get("cores")).items())
    esquema = "light" if _clara("#" + dict(VATTY, **(deck.get("cores") or {}))["fundo"].lstrip("#")) else "dark"
    avatar = (f'<img src="{dados_arte}" alt="">' if dados_arte else '<span class="avatar-eq">' + EQ + "</span>")
    marca = html.escape(deck.get("marca") or "")
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(re.sub(r"[*]", "", deck["titulo"]))}</title>'
            f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link rel="stylesheet" href="{FONTES}">'
            f'<style>:root{{{css_vars};color-scheme:{esquema}}}{CSS}</style></head><body>'
            f'<div id="palco" aria-roledescription="apresentação">{"".join(secoes)}'
            f'<nav id="player" aria-label="Controles da apresentação">'
            f'<div class="agora">{avatar}<div class="agora-txt"><b id="faixa-titulo"></b><small id="faixa-num"></small></div></div>'
            f'<div class="meio"><div class="botoes">'
            f'<button id="voltar" aria-label="Slide anterior"><svg viewBox="0 0 24 24"><path d="M6 5h2v14H6zM20 5v14L9 12z"/></svg></button>'
            f'<button id="tocar" aria-label="Passar sozinho"><svg viewBox="0 0 24 24" id="icone"><path d="M8 5v14l11-7z"/></svg></button>'
            f'<button id="seguir" aria-label="Próximo slide"><svg viewBox="0 0 24 24"><path d="M16 5h2v14h-2zM4 5l11 7L4 19z"/></svg></button>'
            f'</div><div class="progresso"><span id="hora">00:00</span><div class="trilho" id="barra"><i id="feito"></i></div>'
            f'<span>{_relogio(duracao) if duracao else ""}</span></div></div>'
            f'<div class="direita">{marca + "<br>" if marca else ""}<span>setas · N notas</span></div>'
            f'</nav></div><script>{JS.replace("__TOTAL__", str(total))}</script></body></html>')


FONTES = ("https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT@0,9..144,500..800,100;"
          "1,9..144,500..800,100&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&display=swap")

CSS = """
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{background:var(--moldura);color:var(--tinta);font-family:"Manrope","Segoe UI",system-ui,sans-serif;overflow:hidden;
display:grid;place-items:center;-webkit-font-smoothing:antialiased}
#palco{width:1600px;height:900px;position:relative;transform-origin:center;flex:none;background:var(--fundo);border-radius:28px;
overflow:hidden;box-shadow:0 30px 80px var(--sombra)}
html.captura body{display:block;background:var(--fundo)}html.captura #palco{transform:none!important;border-radius:0;box-shadow:none}
html.captura .slide{transition:none}
.slide{position:absolute;inset:0 0 96px 0;padding:70px 96px 40px;display:flex;flex-direction:column;justify-content:center;opacity:0;visibility:hidden;
transform:translateY(14px);transition:opacity .45s ease,transform .45s ease,visibility 0s .45s}
.slide.ativo{opacity:1;visibility:visible;transform:none;transition:opacity .45s ease,transform .45s ease}
@media (prefers-reduced-motion:reduce){.slide,.slide.ativo{transition:none;transform:none}}
.olho{margin:0 0 14px;font:700 15px/1.2 "JetBrains Mono",ui-monospace,Consolas,monospace;letter-spacing:.16em;text-transform:uppercase;color:var(--acento)}
h1,h2,.enorme,blockquote{font-family:"Fraunces",Georgia,"Times New Roman",serif;font-variation-settings:"SOFT" 100;font-weight:700;
letter-spacing:-.02em;margin:0;text-wrap:balance;color:var(--tinta)}
h1{font-size:104px;line-height:.98}h2{font-size:62px;line-height:1.04;margin-bottom:34px}
em{font-style:italic;color:var(--acento);font-weight:600}
p{margin:0}.sub{font-size:26px;line-height:1.45;color:var(--tinta-2);max-width:36ch}
.chips{display:flex;flex-wrap:wrap;gap:12px}
.chip{font:600 19px/1 "Manrope",system-ui,sans-serif;padding:12px 18px;border-radius:999px;background:var(--papel);border:1.5px solid var(--nevoa);color:var(--tinta-2)}
.lista{list-style:none;margin:0;padding:0;display:grid;gap:18px}
.lista li{display:grid;grid-template-columns:30px 1fr;gap:14px;font-size:27px;line-height:1.35}
.lista li::before{content:"";width:14px;height:14px;margin-top:11px;border-radius:5px;background:var(--acento);box-shadow:5px 5px 0 var(--acento2)}
.horarios{display:flex;gap:10px;margin-top:26px}
.horario{font:700 16px/1 "JetBrains Mono",ui-monospace,Consolas,monospace;color:var(--acento-escuro);background:var(--acento-claro);padding:9px 12px;border-radius:8px;text-decoration:none}
.janela{margin:0;background:#16181d;border-radius:18px;overflow:hidden;box-shadow:0 24px 60px var(--sombra),0 0 0 1px rgba(127,127,127,.12)}
.janela .barra{height:34px;display:flex;align-items:center;gap:8px;padding:0 16px;background:#1f2228}
.janela .barra i{width:12px;height:12px;border-radius:50%;background:#ff5f57}.janela .barra i:nth-child(2){background:#febc2e}.janela .barra i:nth-child(3){background:#28c840}
.janela img{display:block;width:100%;height:auto;max-height:600px;object-fit:contain;background:#16181d}
.inclinada{transform:rotate(1.2deg)}
.duas{display:grid;grid-template-columns:1fr 1.4fr;gap:64px;align-items:center;flex:1;min-height:0}
.duas .texto{display:flex;flex-direction:column;min-width:0}.duas h2{font-size:58px}
.palco-img{flex:1;min-height:0;display:flex;justify-content:center;align-items:flex-start}
.palco-img .janela{max-width:100%}.palco-img .janela img{max-height:400px;width:auto;max-width:100%}
.legenda{grid-auto-flow:column;justify-content:start;gap:40px;margin-top:22px}.legenda li{font-size:22px}
.capa{flex-direction:row;align-items:center;gap:40px}
.capa .texto{flex:1;display:grid;gap:30px;min-width:0}
.ave{width:600px;height:600px;position:relative;flex:none;display:grid;place-items:center}
.ondas{position:absolute;inset:0;border-radius:50%;background:radial-gradient(circle at 50% 55%,var(--acento2-claro) 0 34%,transparent 34.5%),
repeating-radial-gradient(circle at 50% 55%,transparent 0 46px,var(--acento-claro) 47px 49px,transparent 50px 62px)}
.ave img{position:relative;max-width:520px;max-height:520px;object-fit:contain;border-radius:22px;filter:drop-shadow(0 22px 26px var(--sombra))}
.sem-arte .eq{height:200px;gap:16px;position:relative}.sem-arte .eq i{width:22px;border-radius:10px}
.eq{display:flex;align-items:flex-end;gap:7px;height:46px}
.eq i{width:9px;border-radius:4px;background:var(--acento);height:30%;animation:eq 1.1s ease-in-out infinite alternate}
.eq i:nth-child(2n){background:var(--acento2);animation-duration:.8s}.eq i:nth-child(3n){animation-duration:1.4s}.eq i:nth-child(5n){animation-duration:.95s}
@keyframes eq{to{height:100%}}#palco:not(.tocando) .eq i{animation-play-state:paused}
.eq i:nth-child(1){height:40%}.eq i:nth-child(2){height:75%}.eq i:nth-child(3){height:55%}.eq i:nth-child(4){height:90%}.eq i:nth-child(6){height:65%}.eq i:nth-child(7){height:85%}.eq i:nth-child(9){height:70%}.eq i:nth-child(11){height:50%}
@media (prefers-reduced-motion:reduce){.eq i{animation:none}}
.passos{display:grid;grid-template-columns:repeat(var(--n),1fr);gap:26px;margin-top:20px}
.passo{background:var(--papel);border:1.5px solid var(--nevoa);border-radius:22px;padding:28px;display:grid;gap:14px;align-content:start;position:relative}
.passo:not(:last-child)::after{content:"";position:absolute;right:-24px;top:52px;width:22px;height:4px;background:repeating-linear-gradient(90deg,var(--asa) 0 6px,transparent 6px 10px)}
.passo b{font:700 34px/1 "JetBrains Mono",ui-monospace,monospace;color:var(--acento)}.passo:nth-child(2n) b{color:var(--acento2)}
.passo span{font-size:23px;line-height:1.38;color:var(--tinta-2)}
.cartoes{display:grid;grid-template-columns:repeat(var(--cols),1fr);gap:22px;margin-top:10px}
.cartao{background:var(--papel);border:1.5px solid var(--nevoa);border-radius:22px;padding:28px 30px;display:grid;gap:12px;align-content:start;font-size:26px;line-height:1.35}
.cartao .n{font:700 18px/1 "JetBrains Mono",ui-monospace,monospace;color:var(--asa)}
.centro{justify-content:center;align-items:flex-start}
.enorme{font-size:140px;line-height:.96;letter-spacing:-.03em;max-width:13ch;margin-bottom:30px}
.onda{width:100%;height:90px;margin-bottom:24px}.onda path{fill:none;stroke-linecap:round}.onda .o1{stroke:var(--acento);stroke-width:5}.onda .o2{stroke:var(--acento2);stroke-width:4;opacity:.9}
.aspas{font:700 220px/.6 Georgia,serif;color:var(--acento);height:110px}
blockquote{font-size:64px;line-height:1.12;max-width:24ch;margin:0}
.lado-a-lado{flex-direction:row;align-items:center;gap:40px}.lado-a-lado .texto{flex:1;display:flex;flex-direction:column;gap:6px;min-width:0}
.lado-a-lado .janela{flex:0 1 640px}
.fim-ave{width:500px;height:500px}.fim-ave img{max-width:420px;max-height:420px;transform:scaleX(-1)}
.convite{display:inline-flex;align-self:flex-start;align-items:center;gap:14px;font:700 26px "Manrope",system-ui,sans-serif;color:var(--fundo);background:var(--tinta);padding:20px 30px;border-radius:999px;margin-top:30px}
.convite i{width:12px;height:12px;border-radius:50%;background:var(--acento2)}
.notas{display:none}body.com-notas .slide.ativo .notas{display:block;position:absolute;left:96px;right:96px;bottom:10px;padding:14px 18px;border-radius:14px;
background:var(--tinta);color:var(--fundo);font-size:19px;line-height:1.4}
#player{position:absolute;left:0;right:0;bottom:0;height:96px;background:var(--papel);border-top:1.5px solid var(--nevoa);
display:grid;grid-template-columns:340px 1fr 260px;align-items:center;gap:30px;padding:0 34px}
.agora{display:flex;align-items:center;gap:16px;min-width:0}
.agora img,.avatar-eq{width:54px;height:54px;border-radius:14px;background:var(--acento2-claro);object-fit:contain;padding:3px;flex:none}
.avatar-eq{display:grid;place-items:center}.avatar-eq .eq{height:28px;gap:3px}.avatar-eq .eq i{width:3px}.avatar-eq .eq i:nth-child(n+6){display:none}
.agora-txt{min-width:0}.agora b{display:block;font-size:18px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.agora small{font:600 14px "JetBrains Mono",ui-monospace,monospace;color:var(--tinta-3)}
.meio{display:grid;gap:10px}.botoes{display:flex;justify-content:center;gap:18px}
.botoes button{border:0;background:none;cursor:pointer;width:42px;height:42px;border-radius:50%;display:grid;place-items:center;color:var(--tinta)}
.botoes button:hover{background:var(--nevoa)}.botoes button:focus-visible{outline:3px solid var(--acento);outline-offset:2px}
.botoes #tocar{background:var(--tinta);color:var(--fundo);width:46px;height:46px}.botoes svg{width:20px;height:20px;fill:currentColor}
.progresso{display:grid;grid-template-columns:70px 1fr 70px;gap:14px;align-items:center;font:600 14px "JetBrains Mono",ui-monospace,monospace;color:var(--tinta-3)}
.progresso span:last-child{text-align:right}
.trilho{height:6px;border-radius:3px;background:var(--nevoa);position:relative;cursor:pointer}
.trilho i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:var(--acento);transition:width .45s ease}
.trilho i::after{content:"";position:absolute;right:-7px;top:-4px;width:14px;height:14px;border-radius:50%;background:var(--acento);box-shadow:0 0 0 4px var(--acento-claro)}
.direita{justify-self:end;font:600 14px "JetBrains Mono",ui-monospace,monospace;color:var(--tinta-3);text-align:right;line-height:1.6}
.direita{color:var(--acento)}.direita span{color:var(--tinta-3)}
@media print{body{display:block;background:none}#palco{transform:none!important;box-shadow:none;border-radius:0;page-break-after:always}}
"""

JS = """
(function(){
var palco=document.getElementById("palco"),slides=[].slice.call(document.querySelectorAll(".slide")),total=__TOTAL__,atual=0,timer=null;
var PLAY='<path d="M8 5v14l11-7z"/>',PAUSA='<path d="M7 5h4v14H7zM13 5h4v14h-4z"/>';
var captura=/c$/.test(location.hash);if(captura)document.documentElement.classList.add("captura");
function encaixar(){if(captura)return;var k=Math.min(innerWidth/1640,innerHeight/940);palco.style.transform="scale("+k+")";}
function ir(n){atual=(n+total)%total;slides.forEach(function(s,i){s.classList.toggle("ativo",i===atual);s.setAttribute("aria-hidden",i!==atual);});
var s=slides[atual];document.getElementById("faixa-titulo").textContent=s.dataset.titulo;
document.getElementById("faixa-num").textContent="Faixa "+String(atual+1).padStart(2,"0")+" de "+String(total).padStart(2,"0");
document.getElementById("hora").textContent=s.dataset.hora||"";document.getElementById("feito").style.width=(total>1?atual/(total-1)*100:100)+"%";
if(!captura){try{history.replaceState(null,"","#"+(atual+1));}catch(e){}}}
function tocar(liga){clearInterval(timer);timer=null;if(liga)timer=setInterval(function(){ir(atual+1);},6000);palco.classList.toggle("tocando",!!liga);
document.getElementById("icone").innerHTML=liga?PAUSA:PLAY;document.getElementById("tocar").setAttribute("aria-label",liga?"Pausar":"Passar sozinho");}
document.getElementById("voltar").onclick=function(e){e.stopPropagation();ir(atual-1);};
document.getElementById("seguir").onclick=function(e){e.stopPropagation();ir(atual+1);};
document.getElementById("tocar").onclick=function(e){e.stopPropagation();tocar(!timer);};
document.getElementById("barra").onclick=function(e){e.stopPropagation();var r=this.getBoundingClientRect();ir(Math.round((e.clientX-r.left)/r.width*(total-1)));};
addEventListener("keydown",function(e){var k=e.key;
if(["ArrowRight","PageDown"," ","Enter"].indexOf(k)>=0){e.preventDefault();ir(atual+1);}
else if(["ArrowLeft","PageUp","Backspace"].indexOf(k)>=0){e.preventDefault();ir(atual-1);}
else if(k==="Home")ir(0);else if(k==="End")ir(total-1);
else if(k==="f"||k==="F"){if(document.fullscreenElement)document.exitFullscreen();else if(document.documentElement.requestFullscreen)document.documentElement.requestFullscreen().catch(function(){});}
else if(k==="n"||k==="N")document.body.classList.toggle("com-notas");else if(k==="p"||k==="P")tocar(!timer);});
slides.forEach(function(s){s.addEventListener("click",function(e){if(e.target.closest("a"))return;var r=palco.getBoundingClientRect();ir(e.clientX<r.left+r.width/3?atual-1:atual+1);});});
var x0=null;palco.addEventListener("touchstart",function(e){x0=e.touches[0].clientX;},{passive:true});
palco.addEventListener("touchend",function(e){if(x0===null)return;var d=e.changedTouches[0].clientX-x0;x0=null;if(Math.abs(d)>40)ir(d<0?atual+1:atual-1);});
addEventListener("resize",encaixar);encaixar();var n=parseInt(location.hash.slice(1),10);ir(n>=1&&n<=total?n-1:0);
})();
"""
