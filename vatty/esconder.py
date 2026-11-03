"""
Esconder nos prints o que a pessoa mandou cortar ("não deixa aparecer Subarashiki Hibi").

O Apresentador escreve `esconder: Subarashiki Hibi, Subahibi` no roteiro; aqui o código garante: lê cada print com o
Tesseract (palavra por palavra, com a caixa de cada uma) e **corta** o print para deixar essas palavras de fora (o
maior pedaço do recorte pedido que não as toca). Nada de borrão: borrão chama atenção para o que foi escondido.
O OCR erra letras ("subarasiiki", "Hibr"), então a comparação é aproximada.

Regra de segurança: se não dá para garantir (sem Tesseract, ou o texto da tela no `visual.json` cita o termo e o OCR
não achou onde está), o print **não entra** no slide. Melhor um slide sem imagem que um post com o que foi proibido.
"""

import difflib
import re
import subprocess
import unicodedata
from pathlib import Path

MARGEM = 12         # px de folga em volta de cada palavra proibida
SOBRA_MIN = 0.3     # se o corte deixar menos que isto da área pedida, o print sai do slide
PARECIDO = 0.75     # quanto uma palavra lida pelo OCR precisa parecer com a do termo


def termos(valor: str) -> list:
    """'Subarashiki Hibi, Subahibi' -> ['Subarashiki Hibi', 'Subahibi']."""
    return [t.strip() for t in re.split(r"[,;]", valor or "") if t.strip()]


def _norm(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def _palavras_dos_termos(lista) -> set:
    return {p for t in lista for p in (_norm(x) for x in t.split()) if p}


def bate(palavra: str, lista) -> bool:
    """A palavra lida pelo OCR é (quase) uma das palavras dos termos? Palavra curta só vale igual."""
    p = _norm(palavra)
    if not p:
        return False
    for alvo in _palavras_dos_termos(lista):
        if p == alvo or (len(alvo) >= 4 and len(p) >= 3 and alvo in p):
            return True
        if len(alvo) >= 4 and difflib.SequenceMatcher(None, p, alvo).ratio() >= PARECIDO:
            return True
    return False


def cita(texto: str, lista) -> bool:
    """Algum termo aparece (aproximadamente) num texto corrido, como o OCR do `visual.json`?"""
    return any(bate(p, lista) for p in re.split(r"\s+", texto or ""))


def caixas(tsv: str) -> list:
    """Saída `tsv` do Tesseract -> [(palavra, x, y, w, h)]."""
    saida = []
    for linha in (tsv or "").splitlines()[1:]:
        c = linha.split("\t")
        if len(c) < 12 or not c[11].strip():
            continue
        try:
            x, y, w, h = (int(v) for v in c[6:10])
        except ValueError:
            continue
        saida.append((c[11].strip(), x, y, w, h))
    return saida


def tesseract_tsv(caminho, executar=subprocess.run) -> str | None:
    """O TSV do Tesseract para a imagem, ou None se não houver Tesseract."""
    from . import ocr
    exe = ocr.localizar()
    if not exe:
        return None
    r = executar([exe, str(caminho), "stdout", "-l", "por+eng", "--psm", "11", "tsv"],
                 capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        r = executar([exe, str(caminho), "stdout", "--psm", "11", "tsv"],
                     capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else None


def cortar(area, proibidas):
    """
    O maior retângulo dentro de `area` (x0, y0, x1, y1) que não encosta em nenhuma caixa proibida, cortando um lado
    por vez (o que perde menos). None se sobrar menos que SOBRA_MIN da área.
    """
    x0, y0, x1, y1 = area
    total = max(1, (x1 - x0) * (y1 - y0))
    for bx0, by0, bx1, by1 in sorted(proibidas):
        if bx1 <= x0 or bx0 >= x1 or by1 <= y0 or by0 >= y1:
            continue
        opcoes = [(x0, y0, bx0, y1), (bx1, y0, x1, y1), (x0, y0, x1, by0), (x0, by1, x1, y1)]
        x0, y0, x1, y1 = max(opcoes, key=lambda r: max(0, r[2] - r[0]) * max(0, r[3] - r[1]))
        if x1 <= x0 or y1 <= y0:
            return None
    return (x0, y0, x1, y1) if (x1 - x0) * (y1 - y0) >= SOBRA_MIN * total else None


def limpar(caminho, lista, pista: str = "", recorte=None, ler=tesseract_tsv):
    """
    (imagem PIL já recortada sem os termos, quantas palavras ficaram de fora), ou (None, 0) se não dá para garantir.
    `recorte`: o pedaço pedido, em % (esquerda, topo, largura, altura). `pista`: o texto que o Visual já leu do print.
    """
    from PIL import Image
    img = Image.open(caminho).convert("RGB")
    W, H = img.size
    if recorte:
        x, y, w, h = recorte
        area = (round(x / 100 * W), round(y / 100 * H), round((x + w) / 100 * W), round((y + h) / 100 * H))
    else:
        area = (0, 0, W, H)
    if not lista:
        return img.crop(area), 0
    tsv = ler(Path(caminho))
    if tsv is None:
        return None, 0
    achadas = [c for c in caixas(tsv) if bate(c[0], lista)]
    if not achadas:
        return (None, 0) if cita(pista, lista) else (img.crop(area), 0)
    proibidas = [(x - MARGEM, y - MARGEM, x + w + MARGEM, y + h + MARGEM) for _, x, y, w, h in achadas]
    final = cortar(area, proibidas)
    return (img.crop(final), len(achadas)) if final else (None, 0)
