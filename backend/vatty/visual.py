"""
Perfil "aula": acha as trocas de tela de um vídeo e monta o registro de slides.

Lógica pura. Recebe quadros pequenos em cinza (um por intervalo fixo) e devolve
os slides; quem tira os quadros (ffmpeg) e quem lê o texto (Tesseract) são
outras peças, passadas por parâmetro nos testes.

Os números abaixo são chutes razoáveis, ainda não medidos em vídeo real:
ajustar com a prática.
"""

import re
from collections import Counter
from dataclasses import dataclass, replace
from difflib import SequenceMatcher

import numpy as np

INTERVALO_S = 1.0           # de quanto em quanto tempo um quadro é comparado
# Fração da tela que precisa mudar para contar como troca. Medido num vídeo de
# teste: trocar o texto de um slide de fundo branco muda só 1% a 2% dos pixels,
# então o limiar tem que ser baixo. Câmera do professor e ruído não entram aqui:
# são tirados pela máscara de movimento constante (abaixo).
LIMIAR_MUDANCA = 0.005
# Máscara de movimento constante, por blocos de BLOCO x BLOCO pixels do quadro
# pequeno. Um bloco "mexe" num quadro quando mais de BLOCO_ATIVO dele mudou; a
# média móvel disso passando de LIMITE_MOVIMENTO (mexeu na maioria dos quadros)
# marca o bloco como câmera ou ruído, e ele sai da conta. Texto de slide só muda
# na troca e nunca chega lá. Por bloco, e não por pixel, porque uma câmera
# real muda só parte dos pixels a cada segundo. O peso baixo impede que uma
# animação de poucos quadros mascare o slide novo.
BLOCO = 10
BLOCO_ATIVO = 0.05
PESO_MOVIMENTO = 0.05
LIMITE_MOVIMENTO = 0.4
DIFERENCA_PIXEL = 25        # diferença de cinza (0-255) para um pixel contar como mudado
AMOSTRAS_ESTAVEIS = 2       # quadros seguidos parados antes de aceitar a troca (espera a animação)
MAX_SLIDES = 300            # teto: uma aula de 3 h não pode gerar milhares de quadros
SIMILARIDADE_JUNTAR = 0.9   # textos de slides vizinhos parecidos assim viram um só
MIN_CARACTERES_JUNTAR = 12  # texto curto demais não prova que o slide é o mesmo

# Limpeza do OCR (para o agente gastar menos tokens lendo o visual.json). Numa
# gravação de tela, a barra do navegador e as abas aparecem em quase todo
# quadro (num vídeo real de 27 min, em 167 slides) e dobravam o tamanho do
# arquivo. Linha que se repete em muitos slides é "ruído fixo": sai do texto.
RUIDO_FRACAO_MIN = 0.3        # a linha aparece em pelo menos esta fração dos slides com texto
RUIDO_SLIDES_MIN = 5          # com menos slides com texto não dá para saber o que é fixo
RUIDO_MIN_CARACTERES = 8      # linha curta ("1", "Sim") repete por acaso: nunca é ruído
RUIDO_SIMILARIDADE = 0.9      # o OCR lê a mesma barra com pequenas diferenças a cada quadro
RUIDO_MAX_LISTADAS = 10       # quantas linhas de ruído o cabeçalho do visual.json registra

# Palpite do perfil (indicadores, só uma dica: quem decide é o usuário).
TROCAS_POR_MIN_CORTE = 8.0
PALAVRAS_POR_TELA_AULA = 8


@dataclass
class Slide:
    inicio: float            # quando a tela começou a mudar (s)
    fim: float               # quando a próxima começou (s)
    quadro_s: float          # horário do quadro estável de onde sai a imagem e o texto
    texto: str = ""
    confianca: float | None = None   # média do OCR, 0 a 100
    frame: str | None = None         # caminho do JPG, relativo à pasta do vídeo


def _mudou(a: np.ndarray, b: np.ndarray, diferenca: int = DIFERENCA_PIXEL) -> np.ndarray:
    return np.abs(a.astype(np.int16) - b.astype(np.int16)) > diferenca


def _blocos_ativos(mudou: np.ndarray) -> np.ndarray:
    """Matriz (blocos de altura x blocos de largura) com 1.0 onde o bloco mexeu neste quadro."""
    altura, largura = mudou.shape
    bh, bw = altura // BLOCO, largura // BLOCO
    if bh == 0 or bw == 0:
        return np.zeros((0, 0), dtype=np.float32)
    fracao = mudou[: bh * BLOCO, : bw * BLOCO].reshape(bh, BLOCO, bw, BLOCO).mean(axis=(1, 3))
    return (fracao > BLOCO_ATIVO).astype(np.float32)


def _mascara(movimento: np.ndarray, forma: tuple) -> np.ndarray:
    """Blocos que mexem demais -> máscara no tamanho do quadro (True = ignorar)."""
    cheia = np.repeat(np.repeat(movimento > LIMITE_MOVIMENTO, BLOCO, axis=0), BLOCO, axis=1)
    mascara = np.zeros(forma, dtype=bool)
    mascara[: cheia.shape[0], : cheia.shape[1]] = cheia
    return mascara


def fracao_mudada(a: np.ndarray, b: np.ndarray, diferenca: int = DIFERENCA_PIXEL, mascara=None) -> float:
    """
    Fração de pixels cuja diferença de cinza passa de `diferenca` (0 a 1). Pixels
    em `mascara` (True = ignorar) não entram na conta, nem no total.
    """
    mudou = _mudou(a, b, diferenca)
    if mascara is None:
        return float(mudou.mean())
    validos = ~mascara
    n = int(validos.sum())
    return float(mudou[validos].sum() / n) if n else 0.0


def detectar_trocas(quadros, *, intervalo: float = INTERVALO_S, limiar: float = LIMIAR_MUDANCA,
                    estaveis: int = AMOSTRAS_ESTAVEIS, max_slides: int = MAX_SLIDES):
    """
    `quadros`: iterável de arrays em cinza, um a cada `intervalo` segundos.
    Devolve (slides, truncado). Uma troca só é aceita quando a tela mudou mais
    que `limiar` em relação ao último slide e depois ficou parada por `estaveis`
    quadros; o `inicio` é o primeiro quadro que mudou, e o `quadro_s` o estável.
    Mudança que volta ao slide anterior (piscada, animação que desfaz) não conta.
    Regiões que mexem o tempo todo (câmera do professor, ruído) são ignoradas.
    """
    slides = []
    referencia = anterior = None
    pendente = None  # índice do primeiro quadro que mudou
    movimento = None  # média móvel, por bloco, de quanto ele mexe; aprende o que é câmera/ruído
    mascara = None
    parados = 0
    total = 0
    truncado = False

    def aceitar(indice_inicio: int, indice_quadro: int, quadro) -> None:
        nonlocal referencia, pendente, truncado
        if len(slides) >= max_slides:
            truncado = True
        else:
            slides.append(Slide(inicio=indice_inicio * intervalo, fim=0.0, quadro_s=indice_quadro * intervalo))
        referencia = quadro
        pendente = None

    ultimo = None
    for i, quadro in enumerate(quadros):
        total = i + 1
        ultimo = quadro
        if anterior is not None:
            ativos = _blocos_ativos(_mudou(quadro, anterior))
            movimento = ativos * PESO_MOVIMENTO if movimento is None else movimento * (1 - PESO_MOVIMENTO) + ativos * PESO_MOVIMENTO
            mascara = _mascara(movimento, quadro.shape)
        if referencia is None and pendente is None:
            pendente, parados = i, 1  # o primeiro quadro conta como mudança em relação a "nada"
        elif pendente is None:
            if fracao_mudada(quadro, referencia, mascara=mascara) > limiar:
                pendente, parados = i, 1
        else:
            parados = parados + 1 if fracao_mudada(quadro, anterior, mascara=mascara) <= limiar else 1
        if pendente is not None and parados >= estaveis:
            if referencia is None or fracao_mudada(quadro, referencia, mascara=mascara) > limiar:
                aceitar(pendente, i, quadro)
            else:
                pendente = None  # voltou ao mesmo slide: era piscada
        anterior = quadro

    if pendente is not None and ultimo is not None and (
            referencia is None or fracao_mudada(ultimo, referencia, mascara=mascara) > limiar):
        aceitar(pendente, total - 1, ultimo)  # o vídeo acabou no meio da troca

    for atual, proximo in zip(slides, slides[1:]):
        atual.fim = proximo.inicio
    if slides:
        slides[-1].fim = total * intervalo
    return slides, truncado


def juntar_parecidos(slides, similaridade: float = SIMILARIDADE_JUNTAR):
    """
    Slides vizinhos com texto quase igual viram um só (o fim se estende). Texto
    curto ou vazio nunca junta: duas imagens sem texto não são o mesmo slide.
    """
    juntos = []
    for slide in slides:
        anterior = juntos[-1] if juntos else None
        if (anterior and len(slide.texto) >= MIN_CARACTERES_JUNTAR and len(anterior.texto) >= MIN_CARACTERES_JUNTAR
                and SequenceMatcher(None, anterior.texto, slide.texto).ratio() >= similaridade):
            anterior.fim = slide.fim
            if (slide.confianca or 0) > (anterior.confianca or 0):  # fica a leitura mais confiável
                anterior.texto, anterior.confianca, anterior.frame = slide.texto, slide.confianca, slide.frame
                anterior.quadro_s = slide.quadro_s
        else:
            juntos.append(slide)
    return juntos


def _chave(linha: str) -> str:
    return " ".join(re.findall(r"\w+", linha.lower()))


def limpar_ruido(slides) -> tuple:
    """
    Tira do texto dos slides as linhas que se repetem em muitos slides (barra do
    navegador, abas, cabeçalho fixo) e descarta os slides que ficam sem texto,
    incluindo os que nunca tiveram (rosto, transição). Devolve
    (slides_limpos, linhas_de_ruido, quantos_descartados). As linhas de ruído
    (até RUIDO_MAX_LISTADAS, as mais frequentes) vão para o cabeçalho do
    visual.json, para o agente saber o que foi tirado. A confiança do OCR de cada
    slide continua a da leitura inteira.
    """
    com_texto = [s for s in slides if s.texto.strip()]
    fixas = {}  # chave -> (quantos slides, linha original)
    if len(com_texto) >= RUIDO_SLIDES_MIN:
        contagem, original = Counter(), {}
        for slide in com_texto:
            for chave in {_chave(l) for l in slide.texto.splitlines()}:
                if len(chave) >= RUIDO_MIN_CARACTERES:
                    contagem[chave] += 1
            for linha in slide.texto.splitlines():
                original.setdefault(_chave(linha), linha.strip())
        fixas = {c: (n, original[c]) for c, n in contagem.items() if n / len(com_texto) >= RUIDO_FRACAO_MIN}

    def eh_ruido(linha: str) -> bool:
        chave = _chave(linha)
        if len(chave) < RUIDO_MIN_CARACTERES or not fixas:
            return False
        return chave in fixas or any(SequenceMatcher(None, chave, f).ratio() >= RUIDO_SIMILARIDADE for f in fixas)

    limpos, descartados = [], 0
    for slide in slides:
        linhas = [l for l in slide.texto.splitlines() if l.strip() and not eh_ruido(l)]
        if linhas:
            limpos.append(replace(slide, texto="\n".join(linhas)))
        else:
            descartados += 1
    mais_frequentes = sorted(fixas.values(), key=lambda v: -v[0])[:RUIDO_MAX_LISTADAS]
    return limpos, [linha for _, linha in mais_frequentes], descartados


def indicadores(slides, duracao_s: float, largura: int, altura: int) -> dict:
    """Números para o usuário julgar o tipo do vídeo. `palavras_por_tela` vem do OCR (slides com texto)."""
    minutos = duracao_s / 60 if duracao_s else 0
    palavras = [len(s.texto.split()) for s in slides if s.texto]
    return {
        "vertical": altura > largura,
        "trocas": len(slides),
        "trocas_por_min": round(len(slides) / minutos, 1) if minutos else 0.0,
        "tempo_medio_s": round(duracao_s / len(slides), 1) if slides else 0.0,
        "palavras_por_tela": round(sum(palavras) / len(palavras), 1) if palavras else 0.0,
    }


def sugerir_perfil(ind: dict) -> tuple:
    """(perfil, motivo): 'aula', 'corte' ou 'nenhum'. É só um palpite; a decisão é do usuário."""
    if ind["vertical"]:
        return "corte", "vídeo vertical"
    if ind["trocas_por_min"] > TROCAS_POR_MIN_CORTE:
        return "corte", f"{ind['trocas_por_min']} trocas de tela por minuto"
    if ind["palavras_por_tela"] >= PALAVRAS_POR_TELA_AULA:
        return "aula", f"tela estável com bastante texto ({ind['palavras_por_tela']} palavras por tela)"
    return "nenhum", "pouco texto na tela"
