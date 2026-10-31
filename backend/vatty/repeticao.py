"""
Detecta trechos onde o Whisper entrou em loop. Lógica pura.

Por que acontece: o faster-whisper coloca os `hotwords` como se fossem o
"texto anterior" em TODA janela de 30 s. Quando o áudio fica confuso
(música, gente falando junto, silêncio), o Whisper tende a copiar esse texto:
ecoa a lista de termos ou repete a mesma frase. Foi o que a lista de termos
da campanha causou na sessão real da Natty.

O motor usa isto assim: transcreve com os termos, procura os sinais abaixo e
refaz só os trechos suspeitos SEM os termos (ver motor.transcrever).
"""

import re
import zlib

# O próprio Whisper considera alucinação texto com razão de compressão acima
# de 2.4 (texto repetitivo comprime demais). Mesmo critério aqui.
RAZAO_COMPRESSAO_MAX = 2.4
# Texto curto comprime mal de qualquer jeito: abaixo disso a razão não diz nada.
TAMANHO_MIN_COMPRESSAO = 40

# Eco da lista: o segmento é quase só termos da lista, vários diferentes.
ECO_TERMOS_MIN = 4
ECO_PROPORCAO_MIN = 0.6

# Mesma frase em segmentos seguidos: a partir de quantas palavras conta.
REPETIDA_PALAVRAS_MIN = 3


def razao_compressao(texto: str) -> float:
    dados = texto.encode("utf-8")
    return len(dados) / len(zlib.compress(dados)) if dados else 0.0


def _normalizar(texto: str) -> str:
    return " ".join(re.findall(r"\w+", texto.lower()))


def termos_da_lista(hotwords: str | None) -> list:
    """'call, put, strike' -> ['call', 'put', 'strike'] (normalizados)."""
    if not hotwords:
        return []
    return [t for t in (_normalizar(p) for p in hotwords.split(",")) if t]


def _eco_da_lista(texto: str, termos: list) -> bool:
    normal = f" {_normalizar(texto)} "
    palavras = normal.split()
    if not palavras or not termos:
        return False
    achados = [t for t in termos if f" {t} " in normal]
    if len(achados) < ECO_TERMOS_MIN:
        return False
    cobertas = sum(normal.count(f" {t} ") * len(t.split()) for t in achados)
    return cobertas / len(palavras) >= ECO_PROPORCAO_MIN


def motivo(segmento, anterior, termos: list) -> str | None:
    """Por que este segmento parece loop, ou None se parece normal."""
    texto = segmento.texto
    if len(texto) >= TAMANHO_MIN_COMPRESSAO and razao_compressao(texto) > RAZAO_COMPRESSAO_MAX:
        return "texto repetitivo"
    if _eco_da_lista(texto, termos):
        return "eco da lista de termos"
    if anterior is not None:
        atual = _normalizar(texto)
        if len(atual.split()) >= REPETIDA_PALAVRAS_MIN and atual == _normalizar(anterior.texto):
            return "frase repetida"
    return None


def trechos_suspeitos(segmentos, termos: list) -> list:
    """
    [Segmento] -> [(i, j, motivo)]: faixas de índices (j inclusivo) de
    segmentos seguidos com sinal de loop. Numa frase repetida, a faixa inclui
    também a primeira ocorrência: não dá para saber qual delas é a real.
    """
    marcados = {}
    for i, seg in enumerate(segmentos):
        m = motivo(seg, segmentos[i - 1] if i else None, termos)
        if m:
            marcados[i] = m
            if m == "frase repetida":
                marcados.setdefault(i - 1, m)
    faixas = []
    for i in sorted(marcados):
        if faixas and i == faixas[-1][1] + 1:
            faixas[-1] = (faixas[-1][0], i, faixas[-1][2])
        else:
            faixas.append((i, i, marcados[i]))
    return faixas
