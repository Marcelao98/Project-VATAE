"""
Legenda do YouTube -> segmentos. Lógica pura: escolhe qual legenda usar, lê o
.vtt e prepara amostras e indicadores para o usuário julgar a qualidade.
Quem pergunta ao usuário é a CLI.
"""

import html
import re
from dataclasses import dataclass

from .motor import Resultado, Segmento

# Trechos mostrados ao usuário: quantos e de quantos segundos cada.
AMOSTRAS = 3
JANELA_AMOSTRA_S = 30.0

_TEMPO = r"(?:\d+:)?\d{2}:\d{2}\.\d{3}"
_LINHA_TEMPO = re.compile(rf"^({_TEMPO})\s+-->\s+({_TEMPO})")
_TAG = re.compile(r"<[^>]*>")
_MARCA = re.compile(r"\[[^\]]*\]")  # [Música], [Aplausos], [Risos]


@dataclass
class Escolha:
    chave: str        # como o yt-dlp chama a legenda (ex.: "pt-BR", "pt-orig")
    automatica: bool


def _mesmo_idioma(chave: str, lang: str) -> bool:
    chave = chave.lower()
    return chave == lang or chave.startswith(lang + "-")


def escolher(manuais, automaticas, lang: str) -> Escolha | None:
    """
    Qual legenda usar, ou None se não há nenhuma confiável no idioma `lang`.
    Manual (escrita pelo autor) vem antes da automática. Da automática só
    vale a original (`<idioma>-orig`): as outras são tradução automática da
    legenda automática, erro em cima de erro. "pt-BR" casa com "pt", "pt-PT"...
    """
    lang = lang.split("-")[0].lower()
    for chave in sorted(manuais):
        if _mesmo_idioma(chave, lang) and not chave.endswith("-orig"):
            return Escolha(chave, automatica=False)
    for chave in sorted(automaticas):
        if chave.endswith("-orig") and _mesmo_idioma(chave, lang):
            return Escolha(chave, automatica=True)
    return None


def _segundos(tempo: str) -> float:
    partes = [float(p) for p in tempo.split(":")]
    while len(partes) < 3:
        partes.insert(0, 0.0)
    h, m, s = partes
    return h * 3600 + m * 60 + s


def ler_vtt(conteudo: str) -> list:
    """
    Conteúdo de um .vtt -> [Segmento]. A legenda automática do YouTube "rola":
    cada trecho repete a linha anterior e traz a nova, e entre eles há trechos
    de 10 ms só com a linha repetida. Por isso cada linha só entra se for
    diferente da última que entrou.
    """
    segmentos = []
    ultima = None
    for bloco in re.split(r"\n\s*\n", conteudo.replace("\r\n", "\n")):
        linhas = bloco.strip("\n").split("\n")
        for i, linha in enumerate(linhas):
            tempo = _LINHA_TEMPO.match(linha.strip())
            if tempo:
                break
        else:
            continue  # cabeçalho, NOTE, STYLE
        novas = []
        for linha in linhas[i + 1:]:
            texto = html.unescape(_TAG.sub("", linha)).strip()
            texto = re.sub(r"\s+", " ", texto)
            if texto and texto != ultima:
                novas.append(texto)
                ultima = texto
        if novas:
            inicio, fim = _segundos(tempo.group(1)), _segundos(tempo.group(2))
            segmentos.append(Segmento(inicio, fim, " ".join(novas)))
    return segmentos


def _cobertura(segmentos, duracao: float) -> float:
    """Fração do vídeo coberta por algum segmento (união dos intervalos)."""
    if not duracao:
        return 0.0
    coberto, ate = 0.0, 0.0
    for s in sorted(segmentos, key=lambda s: s.inicio):
        ini, fim = max(s.inicio, ate), min(s.fim, duracao)
        if fim > ini:
            coberto += fim - ini
            ate = fim
    return min(coberto / duracao, 1.0)


def indicadores(segmentos, duracao: float) -> dict:
    """
    Números que ajudam o usuário a julgar a legenda. São só dica. A legenda
    automática costuma vir sem pontuação e quase sem maiúsculas.
    """
    texto = " ".join(s.texto for s in segmentos)
    marcas = len(_MARCA.findall(texto))
    palavras = _MARCA.sub(" ", texto).split()
    n = len(palavras) or 1
    return {
        "palavras": len(palavras),
        "pontuacao_por_100": round(len(re.findall(r"[.!?,;:]", texto)) * 100 / n, 1),
        "maiusculas_pct": round(sum(p[0].isupper() for p in palavras) * 100 / n),
        "marcas": marcas,
        "cobertura_pct": round(_cobertura(segmentos, duracao) * 100),
    }


def amostras(segmentos, quantas: int = AMOSTRAS, janela: float = JANELA_AMOSTRA_S) -> list:
    """
    Trechos espalhados pelo vídeo (começo, meio, fim): [(inicio, texto)].
    Cada trecho junta os segmentos que começam dentro de `janela` segundos.
    """
    falados = [s for s in segmentos if _MARCA.sub("", s.texto).strip()]
    if not falados:
        return []
    primeiro, ultimo = falados[0].inicio, falados[-1].inicio
    if quantas == 1 or ultimo - primeiro <= janela:
        pontos = [primeiro]
    else:
        passo = (ultimo - janela - primeiro) / (quantas - 1)
        pontos = [primeiro + passo * i for i in range(quantas)]
    trechos = []
    for ponto in pontos:
        dentro = [s for s in falados if ponto <= s.inicio < ponto + janela]
        if dentro:
            trechos.append((dentro[0].inicio, " ".join(s.texto for s in dentro)))
    return trechos


def para_resultado(segmentos, fonte: str, duracao: float, idioma: str, escolha: Escolha) -> Resultado:
    """Segmentos da legenda -> o mesmo Resultado do Motor, sem as marcas como [Música]."""
    limpos = []
    for s in segmentos:
        texto = re.sub(r"\s+", " ", _MARCA.sub(" ", s.texto)).strip()
        if texto:
            limpos.append(Segmento(s.inicio, s.fim, texto))
    return Resultado(
        fonte=fonte,
        duracao_s=duracao,
        modelo=None,
        idioma=idioma,
        segmentos=limpos,
        origem="legenda-automatica" if escolha.automatica else "legenda-manual",
    )
