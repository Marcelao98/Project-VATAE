"""Segmentos do Whisper -> parágrafos de texto."""

# Segmentos seguidos com pausa menor que isso viram um parágrafo só (o Whisper
# corta em pedaços de ~7-10s, e frases saíam partidas).
PAUSA_PARAGRAFO_S = 2.0

# Parágrafo não passa disso (do começo do 1º segmento ao fim do último): quem
# fala sem pausa viraria um bloco enorme. A legenda automática do YouTube não
# tem pausa nenhuma; num vídeo de 15 min saiu um parágrafo de 2.877 palavras.
DURACAO_MAX_PARAGRAFO_S = 60.0

# Como o `falante` do segmento aparece no começo do parágrafo (gravação com duas faixas).
ROTULOS = {"eu": "Eu", "outros": "Outros"}


def juntar_com_inicio(
    segmentos,
    pausa_max: float = PAUSA_PARAGRAFO_S,
    duracao_max: float = DURACAO_MAX_PARAGRAFO_S,
) -> list:
    """
    [Segmento(inicio, fim, texto)] -> [(inicio_s, texto do parágrafo)], juntando
    segmentos consecutivos quando a pausa entre o fim de um e o começo do outro
    é menor que `pausa_max`. Pausa maior, ou o parágrafo passar de `duracao_max`
    segundos, abre parágrafo novo. Texto vazio é ignorado. Quando há `falante`,
    cada troca abre parágrafo novo, com "Eu:" ou "Outros:" na frente.
    """
    paragrafos = []
    comeco = ultimo_fim = falante_atual = None
    for seg in sorted(segmentos, key=lambda s: s.inicio):
        texto = seg.texto.strip()
        if not texto:
            continue
        falante = getattr(seg, "falante", None)
        mesmo_falante = falante == falante_atual
        if paragrafos and mesmo_falante and seg.inicio - ultimo_fim < pausa_max and seg.fim - comeco <= duracao_max:
            paragrafos[-1] = (paragrafos[-1][0], f"{paragrafos[-1][1]} {texto}")
        else:
            # Quem fala só aparece quando há mais de uma faixa; sem falante, nada muda.
            rotulo = f"{ROTULOS.get(falante, falante)}: " if falante else ""
            paragrafos.append((seg.inicio, f"{rotulo}{texto}"))
            comeco = seg.inicio
        falante_atual = falante
        ultimo_fim = seg.fim
    return paragrafos


def juntar_em_paragrafos(
    segmentos,
    pausa_max: float = PAUSA_PARAGRAFO_S,
    duracao_max: float = DURACAO_MAX_PARAGRAFO_S,
) -> list:
    """Como `juntar_com_inicio`, só com o texto de cada parágrafo."""
    return [texto for _, texto in juntar_com_inicio(segmentos, pausa_max, duracao_max)]


def formatar(paragrafos: list) -> str:
    """Parágrafos separados por linha em branco."""
    return "\n\n".join(paragrafos) + "\n" if paragrafos else ""


# --- Gravação com duas faixas: um canal por vez ------------------------------
# Misturar os segmentos dos dois canais antes de montar os parágrafos fazia a
# fala de um lado cortar a frase do outro. Aqui cada canal vira parágrafos
# sozinho (com as mesmas regras de pausa e duração) e só depois entram na
# linha do tempo, já prontos.

def duas_faixas(segmentos) -> bool:
    """True se os segmentos têm mais de um `falante` (gravação com duas faixas)."""
    return len({getattr(s, "falante", None) for s in segmentos} - {None}) >= 2


def horario(segundos: float) -> str:
    """72.4 -> '[01:12]'; a partir de 1 h, '[1:02:03]'."""
    total = int(segundos)
    horas, resto = divmod(total, 3600)
    minutos, seg = divmod(resto, 60)
    return f"[{horas}:{minutos:02d}:{seg:02d}]" if horas else f"[{minutos:02d}:{seg:02d}]"


def paragrafos_com_horario(
    segmentos,
    pausa_max: float = PAUSA_PARAGRAFO_S,
    duracao_max: float = DURACAO_MAX_PARAGRAFO_S,
) -> list:
    """
    Como `juntar_em_paragrafos`, mas devolve [(inicio_s, texto)] e trata todos
    os segmentos como de um canal só (ignora o `falante`).
    """
    paragrafos = []
    comeco = ultimo_fim = None
    for seg in sorted(segmentos, key=lambda s: s.inicio):
        texto = seg.texto.strip()
        if not texto:
            continue
        if paragrafos and seg.inicio - ultimo_fim < pausa_max and seg.fim - comeco <= duracao_max:
            paragrafos[-1] = (paragrafos[-1][0], f"{paragrafos[-1][1]} {texto}")
        else:
            paragrafos.append((seg.inicio, texto))
            comeco = seg.inicio
        ultimo_fim = seg.fim
    return paragrafos


def por_canal(segmentos, **regras) -> dict:
    """{falante: [(inicio_s, texto)]}, um canal montado sozinho, na ordem em que aparecem."""
    canais = {}
    for seg in segmentos:
        canais.setdefault(seg.falante, []).append(seg)
    return {falante: paragrafos_com_horario(segs, **regras) for falante, segs in canais.items()}


def formatar_canal(paragrafos: list) -> str:
    """[(inicio_s, texto)] -> '[mm:ss] texto', parágrafos separados por linha em branco."""
    return formatar([f"{horario(inicio)} {texto}" for inicio, texto in paragrafos])


def linha_do_tempo(canais: dict) -> str:
    """
    Os parágrafos já montados dos canais, ordenados pelo horário de início:
    '[mm:ss] Outros: ...' / '[mm:ss] Eu: ...'. Empate fica na ordem dos canais.
    """
    itens = [(inicio, ordem, falante, texto)
             for ordem, (falante, paragrafos) in enumerate(canais.items())
             for inicio, texto in paragrafos]
    itens.sort(key=lambda i: (i[0], i[1]))
    return formatar([f"{horario(inicio)} {ROTULOS.get(falante, falante)}: {texto}"
                     for inicio, _, falante, texto in itens])
