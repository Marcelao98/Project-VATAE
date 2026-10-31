"""
Perfil "aula" de ponta a ponta: vídeo -> slides com texto (visual.json + frames/).

Junta as peças: `quadros` (ffmpeg), `visual` (acha as trocas) e `ocr`
(Tesseract). Em duas etapas, para a CLI poder mostrar um palpite antes do
trabalho pesado: `detectar` (uma passada pelo vídeo), `palpite` (OCR em
poucos slides) e `montar` (extrai e lê todos os slides).

As ferramentas entram como parâmetro (`ferramentas`) para os testes trocarem
ffmpeg e Tesseract por dublês.
"""

import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from . import ocr, quadros, visual

AMOSTRAS_PALPITE = 4   # slides lidos para estimar a densidade de texto
PASTA_FRAMES = "frames"


@dataclass
class Ferramentas:
    """O que fala com programas externos. Os padrões são os reais."""
    informacoes: object = quadros.informacoes
    amostrar: object = quadros.amostrar
    extrair: object = quadros.extrair_quadro
    ler: object = ocr.ler_imagem


@dataclass
class Deteccao:
    info: dict          # largura, altura, duracao_s
    slides: list
    truncado: bool


def detectar(video, *, intervalo=visual.INTERVALO_S, max_slides=visual.MAX_SLIDES, progresso=None,
             ferramentas: Ferramentas | None = None) -> Deteccao:
    """Uma passada pelo vídeo: onde a tela troca. `progresso(segundos_vistos, duracao_s)`."""
    f = ferramentas or Ferramentas()
    info = f.informacoes(video)

    def com_progresso(quadros_):
        for i, q in enumerate(quadros_):
            if progresso:
                progresso(i * intervalo, info["duracao_s"])
            yield q

    slides, truncado = visual.detectar_trocas(
        com_progresso(f.amostrar(video, info["largura"], info["altura"], intervalo)),
        intervalo=intervalo, max_slides=max_slides)
    if slides and info["duracao_s"]:
        slides[-1].fim = max(slides[-1].fim, info["duracao_s"])
    return Deteccao(info=info, slides=slides, truncado=truncado)


def _escolher_amostras(slides, n):
    """Índices espalhados pelo vídeo (começo, meio, fim...), sem repetir."""
    if len(slides) <= n:
        return list(range(len(slides)))
    return sorted({round(i * (len(slides) - 1) / (n - 1)) for i in range(n)})


def palpite(video, deteccao: Deteccao, pasta_temporaria, *, idiomas: str, exe: str,
            ferramentas: Ferramentas | None = None) -> tuple:
    """
    Lê poucos slides para estimar a densidade de texto e sugere o perfil.
    Devolve (indicadores, (perfil, motivo)). Só uma dica: quem decide é o usuário.
    """
    f = ferramentas or Ferramentas()
    pasta_temporaria = Path(pasta_temporaria)
    lidos = [replace(s) for s in deteccao.slides]
    for i in _escolher_amostras(lidos, AMOSTRAS_PALPITE):
        imagem = f.extrair(video, lidos[i].quadro_s, pasta_temporaria / f"amostra-{i:04d}.jpg")
        lidos[i].texto = f.ler(imagem, idiomas, exe).texto
    ind = visual.indicadores(lidos, deteccao.info["duracao_s"], deteccao.info["largura"], deteccao.info["altura"])
    return ind, visual.sugerir_perfil(ind)


def montar(video, deteccao: Deteccao, destino, *, idiomas: str, exe: str, parametros: dict | None = None,
           progresso=None, ferramentas: Ferramentas | None = None) -> dict:
    """
    Extrai o quadro de cada slide para `destino/frames/`, lê o texto, junta slides
    vizinhos com texto quase igual e devolve o conteúdo do visual.json. Linhas que
    se repetem em muitos slides (barra do navegador) saem do texto, e os slides sem
    texto útil são descartados e contados. Os quadros dos slides que foram
    juntados ou descartados são apagados.
    """
    f = ferramentas or Ferramentas()
    destino = Path(destino)
    pasta_frames = destino / PASTA_FRAMES
    if pasta_frames.exists():
        shutil.rmtree(pasta_frames)  # refazer o visual não deixa quadro de uma execução antiga
    slides = [replace(s) for s in deteccao.slides]
    for n, slide in enumerate(slides, start=1):
        if progresso:
            progresso(n, len(slides))
        imagem = f.extrair(video, slide.quadro_s, pasta_frames / f"{n:04d}.jpg")
        leitura = f.ler(imagem, idiomas, exe)
        slide.texto, slide.confianca = leitura.texto, leitura.confianca
        slide.frame = f"{PASTA_FRAMES}/{imagem.name}"

    # Primeiro tira o ruído fixo (barra do navegador...) e os slides sem texto; só
    # depois junta os vizinhos parecidos, que sem o ruído ficam mais fáceis de achar.
    slides, ruido, descartados = visual.limpar_ruido(slides)
    slides = visual.juntar_parecidos(slides)
    mantidos = {s.frame for s in slides}
    for arquivo in pasta_frames.glob("*.jpg") if pasta_frames.exists() else []:
        if f"{PASTA_FRAMES}/{arquivo.name}" not in mantidos:
            arquivo.unlink()

    return {
        "perfil": "aula",
        "ocr": "tesseract",
        "idiomas": idiomas,
        "duracao_s": deteccao.info["duracao_s"],
        "resolucao": [deteccao.info["largura"], deteccao.info["altura"]],
        "truncado": deteccao.truncado,
        "ruido_removido": ruido,                  # linhas fixas tiradas do texto (barra do navegador...)
        "slides_sem_texto_descartados": descartados,  # telas sem texto útil (rosto, transição, só barra)
        "parametros": parametros or {},
        "eventos": [
            {"tipo": "slide", "inicio": round(s.inicio, 1), "fim": round(s.fim, 1), "texto": s.texto,
             "confianca": s.confianca, "frame": s.frame}
            for s in slides
        ],
    }
