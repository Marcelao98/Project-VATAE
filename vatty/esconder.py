"""
Esconder nos prints o que a pessoa mandou cortar ("não deixa aparecer Subarashiki Hibi").

O Apresentador escreve `esconder: Subarashiki Hibi, Subahibi` no roteiro; aqui o código garante: lê cada print com o
Tesseract (palavra por palavra, com a caixa de cada uma), borra as palavras que batem com os termos e devolve a
imagem limpa. O OCR erra letras ("subarasiiki", "Hibr"), então a comparação é aproximada.

Regra de segurança: se não dá para garantir (sem Tesseract, ou o texto da tela no `visual.json` cita o termo e o OCR
não achou onde está), o print **não entra** no slide. Melhor um slide sem imagem que um post com o que foi proibido.
"""

import difflib
import re
import subprocess
import unicodedata
from pathlib import Path

MARGEM = 6          # px a mais em volta de cada palavra borrada
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


def limpar(caminho, lista, pista: str = "", ler=tesseract_tsv):
    """
    (imagem PIL limpa, quantas palavras borradas), ou (None, 0) se não dá para garantir que o termo sumiu.
    `pista`: o texto que o Visual já leu desse print (no `visual.json`).
    """
    from PIL import Image, ImageFilter
    img = Image.open(caminho).convert("RGB")
    if not lista:
        return img, 0
    tsv = ler(Path(caminho))
    if tsv is None:
        return None, 0
    achadas = [c for c in caixas(tsv) if bate(c[0], lista)]
    if not achadas:
        return (None, 0) if cita(pista, lista) else (img, 0)
    W, H = img.size
    for _, x, y, w, h in achadas:
        caixa = (max(0, x - MARGEM), max(0, y - MARGEM), min(W, x + w + MARGEM), min(H, y + h + MARGEM))
        pedaco = img.crop(caixa)
        pequeno = pedaco.resize((max(1, pedaco.size[0] // 12), max(1, pedaco.size[1] // 12)))
        img.paste(pequeno.resize(pedaco.size, Image.NEAREST).filter(ImageFilter.GaussianBlur(4)), caixa[:2])
    return img, len(achadas)
