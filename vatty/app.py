"""
Perfil "app": o que aconteceu na tela de quem usa ou testa um programa.

O perfil `aula` procura slides: compara um quadro por segundo, só aceita a tela
que ficou parada uns 2 s e ignora a região que mexe muito. Para um programa
isso joga fora justamente o que importa (o aviso que pisca, a tela em branco,
a área que muda). Aqui:

- compara 5 quadros por segundo (`INTERVALO_S`) e aceita a tela que ficou
  parada 0,4 s (`ESTAVEIS`), sem máscara de movimento;
- cada estado da tela vira um evento `tela`; o que apareceu e sumiu rápido,
  voltando à tela de antes, vira `transitorio` (aviso, pop-up, erro que pisca);
  a tela mexendo sem parar por 2 s ou mais vira `movimento` (carregando,
  rolagem, animação), sem OCR;
- o OCR lê só a **região que mudou** quando ela é pequena (o aviso, o campo),
  e não lê de novo uma tela que já apareceu (`repetida`, mesmo quadro);
- tela sem texto não é descartada: tela em branco também é evidência.

Lógica pura em `detectar_eventos`, `regiao_mudada` e `assinatura`; `montar`
junta com o ffmpeg e o Tesseract, que entram por `ferramentas` (dublês nos testes).
"""

import shutil
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from . import aula, visual

INTERVALO_S = 0.2          # 5 comparações por segundo: aviso de 0,5 s já aparece
ESTAVEIS = 2               # quadros seguidos parados para a tela contar como um estado (0,4 s)
LIMIAR = visual.LIMIAR_MUDANCA
TRANSITORIO_MAX_S = 4.0    # estado mais curto que isso, seguido da volta à tela de antes: aviso, pop-up
MOVIMENTO_MIN_S = 2.0      # mexendo sem parar por mais que isso: carregando, rolagem, animação
REGIAO_MAX = 0.5           # região mudada maior que isso (fração da área): lê a tela inteira
MARGEM = 0.02              # folga em volta da região mudada, para o OCR não cortar letra
MAX_EVENTOS = 600          # teto: um teste de horas não pode gerar milhares de quadros
GRADE_ASSINATURA = (18, 32)
PASTA_FRAMES = aula.PASTA_FRAMES


@dataclass
class Evento:
    tipo: str                       # tela | transitorio | movimento
    inicio: float
    fim: float
    quadro_s: float | None = None   # horário do quadro lido (tela parada)
    regiao: tuple | None = None     # (x0, y0, x1, y1) em fração da tela; None = tela inteira
    repete: int | None = None       # índice do evento com a mesma tela (não lê de novo)
    texto: str = ""
    confianca: float | None = None
    frame: str | None = None


# --- Lógica pura ---------------------------------------------------------------

def assinatura(quadro: np.ndarray) -> bytes:
    """Resumo da tela (grade de médias, 8 tons): telas iguais dão a mesma assinatura."""
    gh, gw = GRADE_ASSINATURA
    h, w = quadro.shape
    if h < gh or w < gw:
        return (quadro // 32).astype(np.uint8).tobytes()
    grade = quadro[: h // gh * gh, : w // gw * gw].reshape(gh, h // gh, gw, w // gw).mean(axis=(1, 3))
    return (grade // 32).astype(np.uint8).tobytes()


def regiao_mudada(antes: np.ndarray, depois: np.ndarray, margem: float = MARGEM,
                  maximo: float = REGIAO_MAX) -> tuple | None:
    """Retângulo (frações da tela) do que mudou. None se nada mudou ou se mudou demais (tela nova)."""
    mudou = visual._mudou(antes, depois)
    ys, xs = np.nonzero(mudou)
    if len(xs) == 0:
        return None
    h, w = mudou.shape
    x0, x1 = max(0.0, xs.min() / w - margem), min(1.0, (xs.max() + 1) / w + margem)
    y0, y1 = max(0.0, ys.min() / h - margem), min(1.0, (ys.max() + 1) / h + margem)
    if (x1 - x0) * (y1 - y0) > maximo:
        return None
    return tuple(round(v, 3) for v in (x0, y0, x1, y1))


def detectar_eventos(quadros, *, intervalo: float = INTERVALO_S, limiar: float = LIMIAR, estaveis: int = ESTAVEIS,
                     max_eventos: int = MAX_EVENTOS) -> tuple:
    """
    `quadros`: iterável de arrays em cinza, um a cada `intervalo` segundos.
    Devolve (eventos, truncado) em ordem de tempo, sem sobreposição.
    """
    eventos = []
    assinaturas = {}            # assinatura -> índice do primeiro evento com essa tela
    ref = ref_antes = None      # quadro da tela atual e da anterior
    atual = antes = None        # índices dos eventos dessas duas telas
    anterior = None
    mexendo_desde = None        # primeiro quadro que mexeu desde a última tela parada
    parados = total = 0
    truncado = False

    def original(indice):
        return eventos[indice].repete if eventos[indice].repete is not None else indice

    for i, quadro in enumerate(quadros):
        total = i + 1
        if anterior is None or visual.fracao_mudada(quadro, anterior) > limiar:
            mexendo_desde = i if mexendo_desde is None else mexendo_desde
            parados = 1
        else:
            parados += 1
        anterior = quadro
        if mexendo_desde is None or parados != estaveis:
            continue

        parou = i - estaveis + 1
        movimento_s = (parou - mexendo_desde) * intervalo
        nova = ref is None or visual.fracao_mudada(quadro, ref) > limiar
        if not nova and movimento_s < MOVIMENTO_MIN_S:
            mexendo_desde = None  # mexeu e voltou ao mesmo: cursor, piscada
            continue
        if len(eventos) >= max_eventos:
            truncado = True
            break

        t_mexeu = mexendo_desde * intervalo
        if atual is not None:
            eventos[atual].fim = t_mexeu
        inicio = t_mexeu
        if movimento_s >= MOVIMENTO_MIN_S:
            eventos.append(Evento("movimento", t_mexeu, parou * intervalo))
            inicio = parou * intervalo

        repete, regiao = None, None
        if not nova:
            repete = original(atual)                      # parou de mexer e voltou à mesma tela
        elif (ref_antes is not None and movimento_s < MOVIMENTO_MIN_S
              and eventos[atual].fim - eventos[atual].inicio < TRANSITORIO_MAX_S
              and visual.fracao_mudada(quadro, ref_antes) <= limiar):
            eventos[atual].tipo = "transitorio"           # apareceu e sumiu: volta à tela de antes
            repete = original(antes)
        else:
            repete = assinaturas.get(assinatura(quadro))  # uma tela que já apareceu antes
            if repete is None and ref is not None:
                regiao = regiao_mudada(ref, quadro)

        eventos.append(Evento("tela", inicio, inicio, quadro_s=i * intervalo, regiao=regiao, repete=repete))
        if repete is None:
            assinaturas.setdefault(assinatura(quadro), len(eventos) - 1)
        if nova:
            ref_antes, antes = ref, atual
            ref = quadro
        atual = len(eventos) - 1
        mexendo_desde = None

    if not truncado:
        fim = total * intervalo
        if mexendo_desde is not None and (total - mexendo_desde) * intervalo >= MOVIMENTO_MIN_S:
            if atual is not None:
                eventos[atual].fim = mexendo_desde * intervalo
            eventos.append(Evento("movimento", mexendo_desde * intervalo, fim))
        elif atual is not None:
            eventos[atual].fim = fim
    return eventos, truncado


def _limpar_ruido(lidos: list) -> list:
    """Tira as linhas fixas (barra do navegador, menu) do texto lido; tela sem texto continua."""
    com_texto = [e for e in lidos if e.texto.strip()]
    limpos, ruido, _ = visual.limpar_ruido(com_texto)
    por_inicio = {e.inicio: e.texto for e in limpos}
    for e in com_texto:
        e.texto = por_inicio.get(e.inicio, "")
    return ruido


def _para_json(e: Evento) -> dict:
    saida = {"tipo": e.tipo, "inicio": round(e.inicio, 1), "fim": round(e.fim, 1)}
    if e.tipo == "movimento":
        return saida
    if e.repete is not None:
        return {**saida, "frame": e.frame, "repetida": True}
    saida.update(texto=e.texto, confianca=e.confianca, frame=e.frame)
    if e.regiao:
        saida["regiao"] = list(e.regiao)
    return saida


# --- Com o ffmpeg e o Tesseract -----------------------------------------------

def montar(video, destino, *, idiomas: str, exe: str, parametros: dict | None = None, progresso_tela=None,
           progresso_leitura=None, ferramentas: aula.Ferramentas | None = None) -> dict:
    """Vídeo -> conteúdo do visual.json do perfil app, com os quadros em `destino/frames/`."""
    f = ferramentas or aula.Ferramentas()
    destino = Path(destino)
    info = f.informacoes(video)

    def com_progresso(quadros_):
        for i, q in enumerate(quadros_):
            if progresso_tela:
                progresso_tela(i * INTERVALO_S, info["duracao_s"])
            yield q

    eventos, truncado = detectar_eventos(com_progresso(f.amostrar(video, info["largura"], info["altura"], INTERVALO_S)))
    if eventos and info["duracao_s"]:
        eventos[-1].fim = max(eventos[-1].fim, info["duracao_s"])

    pasta_frames = destino / PASTA_FRAMES
    if pasta_frames.exists():
        shutil.rmtree(pasta_frames)  # refazer o visual não deixa quadro de uma execução antiga
    lidos = [e for e in eventos if e.tipo != "movimento" and e.repete is None]
    for n, e in enumerate(lidos, start=1):
        if progresso_leitura:
            progresso_leitura(n, len(lidos))
        alvo = pasta_frames / f"{n:04d}.jpg"
        imagem = f.extrair(video, e.quadro_s, alvo, recorte=e.regiao) if e.regiao else f.extrair(video, e.quadro_s, alvo)
        leitura = f.ler(imagem, idiomas, exe)
        e.texto, e.confianca, e.frame = leitura.texto, leitura.confianca, f"{PASTA_FRAMES}/{imagem.name}"
    for e in eventos:
        if e.repete is not None:
            e.frame = eventos[e.repete].frame
    ruido = _limpar_ruido(lidos)

    return {
        "perfil": "app",
        "ocr": "tesseract",
        "idiomas": idiomas,
        "duracao_s": info["duracao_s"],
        "resolucao": [info["largura"], info["altura"]],
        "truncado": truncado,
        "ruido_removido": ruido,
        "telas_lidas": len(lidos),
        "parametros": parametros or {},
        "eventos": [_para_json(e) for e in eventos],
    }
