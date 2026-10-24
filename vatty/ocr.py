"""
OCR do texto que aparece na tela: Tesseract chamado pelo terminal.

Sem `pytesseract`: o Tesseract é um programa externo (como o ffmpeg), e chamar
direto evita mais uma dependência de Python. A execução entra como parâmetro
(`executar`) para os testes trocarem por um dublê.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

TIMEOUT_S = 60

# Idioma da Vatty (--lang) -> código do Tesseract. O inglês entra sempre: slide
# em português vive citando termo em inglês.
IDIOMAS = {"pt": "por", "en": "eng", "es": "spa", "fr": "fra", "de": "deu", "it": "ita"}

# Onde o instalador do Windows costuma deixar o programa (ele não entra no PATH sozinho).
CAMINHOS_WINDOWS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

COMO_INSTALAR = ("Instale o Tesseract (Windows: instalador do UB Mannheim, marcando o idioma Portuguese; "
                 "Fedora: sudo dnf install tesseract tesseract-langpack-por; Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-por; macOS: brew install tesseract tesseract-lang). "
                 "Se ele não estiver no PATH, defina a variável TESSERACT_CMD com o caminho do programa.")


class ErroOcr(Exception):
    """Falha do OCR, com mensagem para o usuário."""


@dataclass
class Leitura:
    texto: str
    confianca: float | None  # média por palavra, 0 a 100; None se não leu nada


def idiomas_para(lang: str | None) -> str:
    """'pt' -> 'por+eng'; 'en' -> 'eng'; 'auto' ou desconhecido -> 'por+eng'."""
    codigo = IDIOMAS.get((lang or "").lower())
    if codigo == "eng":
        return "eng"
    return f"{codigo}+eng" if codigo else "por+eng"


def localizar() -> str | None:
    """Caminho do Tesseract: TESSERACT_CMD, depois o PATH, depois os lugares do instalador do Windows."""
    do_ambiente = os.environ.get("TESSERACT_CMD")
    if do_ambiente and Path(do_ambiente).is_file():
        return do_ambiente
    achado = shutil.which("tesseract")
    if achado:
        return achado
    return next((c for c in CAMINHOS_WINDOWS if Path(c).is_file()), None)


def _rodar(comando, executar):
    try:
        return executar(comando, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_S)
    except FileNotFoundError:
        raise ErroOcr(f"Tesseract não encontrado. {COMO_INSTALAR}") from None
    except subprocess.TimeoutExpired:
        raise ErroOcr(f"o Tesseract passou de {TIMEOUT_S}s numa imagem") from None


def idiomas_instalados(exe: str, executar=subprocess.run) -> set:
    """Idiomas que o Tesseract tem (`tesseract --list-langs`)."""
    r = _rodar([exe, "--list-langs"], executar)
    if r.returncode != 0:
        raise ErroOcr(f"o Tesseract falhou ao listar idiomas: {r.stderr.strip()}")
    linhas = (r.stdout or "").splitlines()
    return {l.strip() for l in linhas[1:] if l.strip()}  # a 1ª linha é o cabeçalho


def verificar(idiomas: str, executar=subprocess.run) -> str:
    """Confere que o Tesseract e os idiomas existem antes de processar o vídeo todo. Devolve o executável."""
    exe = localizar()
    if not exe:
        raise ErroOcr(f"Tesseract não encontrado. {COMO_INSTALAR}")
    faltam = [i for i in idiomas.split("+") if i not in idiomas_instalados(exe, executar)]
    if faltam:
        raise ErroOcr(f"falta o idioma {', '.join(faltam)} no Tesseract. {COMO_INSTALAR}")
    return exe


def ler_tsv(tsv: str) -> Leitura:
    """
    Saída `tsv` do Tesseract -> texto (linhas na ordem, blocos separados por linha
    em branco) e confiança média por palavra. Linhas sem palavra (conf -1) são ignoradas.
    """
    linhas = {}   # (bloco, parágrafo, linha) -> palavras, na ordem
    confs = []
    for linha in tsv.splitlines()[1:]:
        campos = linha.split("\t")
        if len(campos) < 12:
            continue
        try:
            conf = float(campos[10])
        except ValueError:
            continue
        palavra = campos[11].strip()
        if conf < 0 or not palavra:
            continue
        confs.append(conf)
        linhas.setdefault((campos[2], campos[3], campos[4]), []).append(palavra)

    blocos, atual, bloco_atual = [], [], None
    for (bloco, _par, _lin), palavras in linhas.items():
        if bloco != bloco_atual and atual:
            blocos.append("\n".join(atual))
            atual = []
        bloco_atual = bloco
        atual.append(" ".join(palavras))
    if atual:
        blocos.append("\n".join(atual))
    texto = "\n\n".join(blocos)
    return Leitura(texto=texto, confianca=round(sum(confs) / len(confs), 1) if confs else None)


def ler_imagem(caminho, idiomas: str, exe: str, executar=subprocess.run) -> Leitura:
    """Lê o texto de uma imagem com o Tesseract (`exe` vem de `verificar`)."""
    r = _rodar([exe, str(caminho), "stdout", "-l", idiomas, "tsv"], executar)
    if r.returncode != 0:
        raise ErroOcr(f"o Tesseract falhou em {Path(caminho).name}: {r.stderr.strip()}")
    return ler_tsv(r.stdout or "")
