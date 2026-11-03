"""
PDF e PowerPoint a partir do deck HTML: o navegador (Chrome, Chromium ou Edge, sem janela) tira um print de cada
slide em 3200 x 1800, e os prints viram as páginas do PDF e os slides do .pptx (com as notas de quem apresenta).
Assim os três formatos saem iguais ao HTML. O .pptx assim é feito de imagens: apresenta normal, mas o texto não
se edita (para isso, `--formato pptx-editavel`, o desenho antigo do `apresentacao_pptx.py`).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

NOMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "msedge", "chrome")
WINDOWS = (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
           r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
COMO_INSTALAR = ("para PDF e PowerPoint no visual novo a Vatty usa o Chrome, o Chromium ou o Edge (sem abrir janela). "
                 "Fedora: sudo dnf install chromium; Windows: o Edge já vem instalado.")


def achar_navegador(procurar=shutil.which, existe=lambda p: Path(p).is_file()) -> str | None:
    for nome in NOMES:
        if achado := procurar(nome):
            return achado
    return next((p for p in WINDOWS if existe(p)), None)


def capturar(arquivo_html, total: int, pasta_saida, exe: str, executar=subprocess.run) -> list:
    """Um PNG por slide (01.png, 02.png...). Erro legível se o navegador não gerar a imagem."""
    pasta_saida = Path(pasta_saida)
    uri = Path(arquivo_html).resolve().as_uri()
    prints = []
    for n in range(1, total + 1):
        destino = pasta_saida / f"{n:02d}.png"
        executar([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                  "--virtual-time-budget=5000", "--window-size=1600,900", f"--screenshot={destino}", f"{uri}#{n}c"],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        if not destino.is_file():
            raise RuntimeError(f"o navegador não gerou o slide {n} ({Path(exe).name}).")
        prints.append(destino)
    return prints


def para_pdf(prints, destino) -> Path:
    from PIL import Image
    paginas = [Image.open(p).convert("RGB") for p in prints]
    paginas[0].save(destino, save_all=True, append_images=paginas[1:], resolution=240)
    return Path(destino)


def para_pptx(prints, destino, notas=(), titulo="") -> Path:
    from pptx import Presentation
    from pptx.util import Emu
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
    prs.core_properties.title = titulo
    for i, p in enumerate(prints):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_picture(str(p), 0, 0, prs.slide_width, prs.slide_height)
        if i < len(notas) and notas[i]:
            slide.notes_slide.notes_text_frame.text = notas[i]
    prs.save(destino)
    return Path(destino)


def renderizar(html: str, total: int, destinos: dict, notas=(), titulo="", exe=None, executar=subprocess.run) -> list:
    """`destinos`: {"pdf": Path, "pptx": Path} (um ou os dois). Devolve os arquivos feitos."""
    exe = exe or achar_navegador()
    if not exe:
        raise RuntimeError(COMO_INSTALAR)
    with tempfile.TemporaryDirectory(prefix="vatty-deck-") as tmp:
        arquivo = Path(tmp) / "deck.html"
        arquivo.write_text(html, encoding="utf-8")
        prints = capturar(arquivo, total, tmp, exe, executar)
        feitos = []
        if "pdf" in destinos:
            feitos.append(para_pdf(prints, destinos["pdf"]))
        if "pptx" in destinos:
            feitos.append(para_pptx(prints, destinos["pptx"], notas, titulo))
        return feitos
