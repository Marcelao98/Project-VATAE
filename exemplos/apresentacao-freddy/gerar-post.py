"""Gera a versão do post: HTML estático, estilos inline, sem script, sem fonte externa, imagem só por https."""
from pathlib import Path

ARTE = ("https://raw.githubusercontent.com/Marcelao98/Projeto-Frederico/"
        "5353813f5a46ab4eb1f9e12aa32bb3bf4ea64224/frontend/public/aves/frederico.png")
FUNDO, PAPEL, NEVOA, TINTA, TINTA2, TINTA3 = "#f5f5f7", "#ffffff", "#e6e6ec", "#1e1e23", "#52525c", "#70707b"
BICO, BICO_ESC, BICO_CL, CRISTA, CRISTA_CL, ASA = "#bf4a62", "#a43b52", "#f6dde2", "#f2b48c", "#fbe6d6", "#c5c7d1"
DISPLAY = "'Fraunces','Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif"
TEXTO = "system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"
MONO = "ui-monospace,'SF Mono','Cascadia Mono',Consolas,'Liberation Mono',monospace"


def st(**k):
    return ";".join(f"{a.replace('_', '-')}:{v}" for a, v in k.items())


def olho(t):
    return f'<p style="{st(margin="0 0 10px", font=f"700 12px/1.2 {MONO}", letter_spacing=".16em", text_transform="uppercase", color=BICO)}">{t}</p>'


def titulo(t, tam=34):
    return f'<h2 style="{st(margin="0 0 18px", font=f"700 {tam}px/1.08 {DISPLAY}", letter_spacing="-.01em", color=TINTA)}">{t}</h2>'


def em(t):
    return f'<em style="{st(font_style="italic", color=BICO, font_weight="600")}">{t}</em>'


def faixa(n, nome, hora):
    """Cabeçalho de cada cartão: a faixa do player."""
    return (f'<div style="{st(display="flex", align_items="center", justify_content="space-between", gap="12px", padding="12px 22px", border_bottom=f"1px solid {NEVOA}", font=f"600 12px/1 {MONO}", color=TINTA3)}">'
            f'<span>FAIXA {n:02d} DE 09 · {nome}</span><span style="{st(color=BICO_ESC, background=BICO_CL, padding="5px 8px", border_radius="6px")}">{hora}</span></div>')


def cartao(n, nome, hora, corpo, fundo=PAPEL):
    return (f'<section style="{st(background=fundo, border=f"1px solid {NEVOA}", border_radius="22px", overflow="hidden", margin="0 0 18px", box_shadow="0 10px 30px rgba(30,30,35,.07)")}">'
            f'{faixa(n, nome, hora)}<div style="{st(padding="26px 24px 28px")}">{corpo}</div></section>')


def lista(itens):
    lis = "".join(
        f'<li style="{st(display="flex", gap="12px", align_items="flex-start", margin="0 0 10px", font=f"500 17px/1.45 {TEXTO}", color=TINTA)}">'
        f'<span style="{st(flex="none", width="11px", height="11px", margin_top="7px", border_radius="4px", background=BICO, box_shadow=f"4px 4px 0 {CRISTA}")}"></span><span>{i}</span></li>'
        for i in itens)
    return f'<ul style="{st(list_style="none", margin="0", padding="0")}">{lis}</ul>'


def chip(t, on=False):
    cor = st(background=BICO, color="#fff", border=f"1px solid {BICO}") if on else st(background=PAPEL, color=TINTA2, border=f"1px solid {NEVOA}")
    return f'<span style="{st(display="inline-block", margin="0 8px 8px 0", padding="8px 14px", border_radius="999px", font=f"600 15px/1 {TEXTO}")};{cor}">{t}</span>'


def bolha(t, eu=True, mono=False):
    fonte = MONO if mono else TEXTO
    if eu:
        return (f'<div style="{st(text_align="right", margin="0 0 10px")}"><span style="{st(display="inline-block", background=BICO, color="#fff", padding="11px 16px", border_radius="18px 18px 6px 18px", font=f"600 16px/1.35 {fonte}")}">{t}</span></div>')
    return (f'<div style="{st(margin="0 0 10px")}"><span style="{st(display="inline-flex", align_items="center", gap="10px", background=FUNDO, color=TINTA, padding="8px 16px 8px 8px", border_radius="18px 18px 18px 6px", border=f"1px solid {NEVOA}", font=f"500 16px/1.35 {TEXTO}")}">'
            f'<img src="{ARTE}" alt="" width="34" height="34" style="{st(width="34px", height="34px", border_radius="50%", background=CRISTA_CL)}"><span>{t}</span></span></div>')


partes = []

# 1 capa
partes.append(
    f'<section style="{st(background=f"radial-gradient(circle at 78% 42%,{CRISTA_CL} 0,{CRISTA_CL} 22%,transparent 22.5%),{PAPEL}", border=f"1px solid {NEVOA}", border_radius="26px", overflow="hidden", margin="0 0 18px", box_shadow="0 14px 40px rgba(30,30,35,.09)")}">'
    f'<div style="{st(display="flex", flex_wrap="wrap", align_items="center", gap="10px", padding="34px 28px 10px")}">'
    f'<div style="{st(flex="1 1 300px", min_width="0")}">{olho("Projeto pessoal · RPG de mesa")}'
    f'<h1 style="{st(margin="0 0 16px", font=f"700 52px/1 {DISPLAY}", letter_spacing="-.02em", color=TINTA)}">Freddy,<br>o {em("som")} da mesa</h1>'
    f'<p style="{st(margin="0 0 18px", font=f"400 18px/1.5 {TEXTO}", color=TINTA2)}">Uma calopsita virtual que toca a música certa para a cena, pelo chat ou pelo Discord.</p>'
    f'<div>{chip("<b style=\"color:" + BICO + "\">607</b> faixas")}{chip("<b style=\"color:" + BICO + "\">9</b> franquias")}{chip("pedido em português")}</div></div>'
    f'<div style="{st(flex="0 1 300px", text_align="center", min_width="0")}"><img src="{ARTE}" alt="Frederico, a calopsita de fone de ouvido que dá cara ao Freddy" width="300" style="{st(width="100%", max_width="300px", height="auto")}"></div></div>'
    f'<div style="{st(display="flex", align_items="center", gap="12px", padding="14px 22px", border_top=f"1px solid {NEVOA}", background=FUNDO, font=f"600 12px/1 {MONO}", color=TINTA3)}">'
    f'<span style="{st(width="30px", height="30px", border_radius="50%", background=TINTA, color="#fff", display="inline-flex", align_items="center", justify_content="center", font_size="11px")}">▶</span>'
    f'<span style="{st(flex="1", height="5px", border_radius="3px", background=f"linear-gradient(90deg,{BICO} 0 6%,{NEVOA} 6%)")}"></span><span>00:00 / 07:27</span></div></section>')

# 2 secretário
no = lambda pequeno, nome, txt, destaque=False: (
    f'<div style="{st(flex="1 1 220px", background=PAPEL, border=f"1.5px solid {BICO if destaque else NEVOA}", border_radius="18px", padding="18px 20px", min_width="0")}">'
    f'<p style="{st(margin="0 0 6px", font=f"700 11px/1 {MONO}", letter_spacing=".14em", text_transform="uppercase", color=TINTA3)}">{pequeno}</p>'
    f'<p style="{st(margin="0 0 6px", font=f"700 24px/1.1 {DISPLAY}", color=BICO if destaque else TINTA)}">{nome}</p>'
    f'<p style="{st(margin="0", font=f"400 15px/1.45 {TEXTO}", color=TINTA2)}">{txt}</p></div>')
partes.append(cartao(2, "DE ONDE ELE VEM", "00:02",
    titulo(f"Um projeto maior: o {em('secretário')} virtual")
    + f'<div style="{st(display="flex", flex_wrap="wrap", align_items="center", gap="12px")}">'
    + no("O projeto", "Secretário virtual", "Meu projeto principal: um agente que é meu secretário.")
    + f'<span style="{st(font=f"700 22px/1 {MONO}", color=ASA)}">→</span>'
    + no("Nasceu dele", "Freddy", "O agente que cuida do som da mesa de RPG.", True) + "</div>"))

# 3 peça do seu jeito
passo = lambda n, t: (f'<div style="{st(flex="1 1 150px", background=FUNDO, border_radius="14px", padding="14px 16px", min_width="0")}">'
                      f'<p style="{st(margin="0 0 6px", font=f"700 20px/1 {MONO}", color=BICO)}">{n:02d}</p>'
                      f'<p style="{st(margin="0", font=f"500 15px/1.4 {TEXTO}", color=TINTA2)}">{t}</p></div>')
partes.append(cartao(3, "OI, EU SOU O FREDDY", "00:12",
    titulo(f"Peça do {em('seu jeito')}")
    + f'<div style="{st(background=FUNDO, border_radius="18px", padding="16px", margin="0 0 16px")}">'
    + bolha("toca triste e bloodborne") + bolha("Tocando: <b>Gehrman, The First Hunter</b>", eu=False)
    + bolha("pula", mono=True) + bolha("volume 30", mono=True) + "</div>"
    + f'<div style="{st(display="flex", flex_wrap="wrap", gap="10px")}">'
    + passo(1, "Escreva em português, do jeito que fala") + passo(2, "Peça um clima: “toca triste”")
    + passo(3, "Ele pula, repete ou para quando você manda") + passo(4, "607 faixas de 9 franquias") + "</div>"))

# 4 clima
partes.append(cartao(4, "CADA FAIXA TEM UM CLIMA", "02:19",
    titulo(f"Filtre por {em('clima')}")
    + "<div>" + "".join(chip(c, c in ("combate", "triste")) for c in
                         ["combate", "triste", "sombrio", "épico", "dramático", "terror", "calmo", "mistério", "tenso", "exploração", "nostálgico", "vilão"]) + "</div>"
    + f'<p style="{st(margin="8px 0 0", font=f"400 16px/1.5 {TEXTO}", color=TINTA2)}">Combine climas e busque pelo nome até achar a faixa da cena.</p>'))

# 5 busca
partes.append(cartao(5, "A GALERA CONHECE", "03:26",
    titulo(f"Busca por {em('franquia')}")
    + f'<div style="{st(background=FUNDO, border_radius="18px", padding="16px")}">'
    + f'<div style="{st(background=PAPEL, border=f"1px solid {NEVOA}", border_radius="12px", padding="12px 14px", font=f"600 17px/1 {MONO}", color=TINTA, margin="0 0 14px")}">⌕ blood<span style="{st(color=BICO)}">|</span></div>'
    + f'<p style="{st(margin="0 0 10px", font=f"700 11px/1 {MONO}", letter_spacing=".14em", color=BICO)}">TOCANDO AGORA</p>'
    + f'<div style="{st(display="flex", align_items="center", gap="14px")}">'
    + f'<span style="{st(flex="none", width="64px", height="64px", border_radius="14px", background="linear-gradient(135deg,#2a2d36,#4a4e5c)", display="inline-flex", align_items="center", justify_content="center")}"><span style="{st(width="20px", height="20px", border_radius="50%", background=BICO)}"></span></span>'
    + f'<div style="{st(min_width="0")}"><p style="{st(margin="0 0 4px", font=f"700 21px/1.15 {DISPLAY}", color=TINTA)}">Gehrman, The First Hunter</p>'
    + f'<p style="{st(margin="0", font=f"400 15px/1 {TEXTO}", color=TINTA3)}">Bloodborne</p></div></div>'
    + f'<div style="{st(height="6px", border_radius="3px", margin_top="14px", background=f"linear-gradient(90deg,{BICO} 0 8%,{NEVOA} 8%)")}"></div></div>'
    + f'<div style="{st(margin_top="16px")}">{lista(["Digitou “blood”, achou Bloodborne", "A música começa na hora, sem sair da mesa"])}</div>'))

# 6 discord
linha_canal = lambda t, on=False: (f'<p style="{st(margin="0", padding="7px 10px", border_radius="8px", font=f"500 14px/1.2 {TEXTO}", color="#e8e8ec" if on else "#8d90a0", background="rgba(242,180,140,.14)" if on else "transparent")}">🔊 {t}</p>')
partes.append(cartao(6, "NO SERVIDOR DE RPG", "05:08",
    titulo(f"Funciona dentro do {em('Discord')}")
    + f'<div style="{st(background="#1b1d23", border_radius="16px", padding="16px", margin="0 0 16px")}">'
    + f'<div style="{st(display="flex", align_items="center", gap="10px", margin="0 0 12px")}"><img src="{ARTE}" alt="" width="36" height="36" style="{st(width="36px", height="36px", border_radius="50%", background="#2a2d36")}">'
    + f'<div><p style="{st(margin="0", font=f"700 15px/1.2 {TEXTO}", color="#fff")}">Freddy</p><p style="{st(margin="0", font=f"500 13px/1.2 {TEXTO}", color="#5fd68a")}">conectado</p></div></div>'
    + f'<p style="{st(margin="0 0 12px", padding="10px 12px", border_radius="10px", background="#24272f", font=f"600 14px/1.3 {TEXTO}", color="#e8e8ec")}"><span style="color:#5fd68a">●</span> Tocando em #Taverna (The crossroads)</p>'
    + linha_canal("Sala-de-voz") + linha_canal("Taverna", True) + linha_canal("Ecos-do-Mundo") + "</div>"
    + lista(["O Freddy entra na call do servidor", "A música sai direto na chamada", "Tem modo de teste para conferir"])))

# 7 destaque
partes.append(cartao(7, "PARA QUEM JOGA RPG DE MESA", "05:08",
    f'<p style="{st(margin="6px 0 18px", font=f"700 50px/1 {DISPLAY}", letter_spacing="-.02em", color=TINTA)}">A música certa para a {em("cena.")}</p>'
    + f'<div style="{st(height="10px", border_radius="5px", background=f"repeating-linear-gradient(90deg,{BICO} 0 22px,{CRISTA} 22px 34px,transparent 34px 44px)")}"></div>'))

# 8 próximas faixas
linha = lambda n, t: (f'<div style="{st(display="flex", align_items="center", gap="14px", padding="14px 4px", border_top=f"1px solid {NEVOA}")}">'
                      f'<span style="{st(font=f"700 15px/1 {MONO}", color=ASA, width="26px")}">{n:02d}</span>'
                      f'<span style="{st(flex="1", font=f"500 17px/1.3 {TEXTO}", color=TINTA)}">{t}</span>'
                      f'<span style="{st(font=f"700 11px/1 {MONO}", letter_spacing=".1em", color=BICO_ESC, background=BICO_CL, padding="6px 10px", border_radius="999px")}">EM BREVE</span></div>')
partes.append(cartao(8, "PRÓXIMAS FAIXAS", "03:26",
    titulo(f"O que vem {em('a seguir')}")
    + linha(1, "Mixer e soundboard") + linha(2, "Botão de pausa") + linha(3, "Editar e baixar plugins") + linha(4, "Refinar os temas das músicas")))

# 9 fim
partes.append(
    f'<section style="{st(background=f"radial-gradient(circle at 82% 50%,{CRISTA_CL} 0,{CRISTA_CL} 20%,transparent 20.5%),{PAPEL}", border=f"1px solid {NEVOA}", border_radius="26px", overflow="hidden", margin="0 0 6px", box_shadow="0 14px 40px rgba(30,30,35,.09)")}">'
    + faixa(9, "ÚLTIMA FAIXA", "05:08")
    + f'<div style="{st(display="flex", flex_wrap="wrap", align_items="center", gap="10px", padding="26px 24px 28px")}">'
    + f'<div style="{st(flex="1 1 300px", min_width="0")}">{titulo("Procuro " + em("emprego"), 42)}'
    + lista(["Sou engenheiro eletricista e manjo de dados", "Estou buscando uma oportunidade"])
    + f'<p style="{st(margin="18px 0 0")}"><span style="{st(display="inline-block", background=TINTA, color="#fff", padding="13px 22px", border_radius="999px", font=f"700 17px/1 {TEXTO}")}"><span style="color:{CRISTA}">●</span>&nbsp; Vamos conversar?</span></p></div>'
    + f'<div style="{st(flex="0 1 220px", text_align="center", min_width="0")}"><img src="{ARTE}" alt="Frederico, a calopsita" width="220" style="{st(width="100%", max_width="220px", height="auto", transform="scaleX(-1)")}"></div></div></section>')

html = (f'<div style="{st(max_width="760px", margin="0 auto", padding="18px 14px", background=FUNDO, border_radius="28px", font_family=TEXTO, color=TINTA)}">'
        + "\n".join(partes) + "</div>\n")
Path(__file__).with_name("freddy-post.html").write_text(html, encoding="utf-8")
print(len(html), "caracteres,", html.count("\n") + 1, "linhas")
