"""
`vatty juntar <pasta da gravação>`: tela + som do PC + microfone num arquivo só, para mandar a alguém.

A gravação guarda cada faixa separada (é o que a transcrição precisa). Aqui o ffmpeg mistura as faixas de
áudio e põe embaixo da tela, cada uma deslocada pelo horário real em que começou (`inicios` do
gravacao.json), para o som bater com a imagem. Com tela sai `video.mp4` (a imagem é copiada, sem recodificar);
sem tela, `audio.m4a`. Nada na pasta é apagado nem mudado.
"""

import shutil
import subprocess
from pathlib import Path

from . import audio, gravacao, tela

VIDEO = "video.mp4"
SO_AUDIO = "audio.m4a"


class ErroJuntar(RuntimeError):
    pass


def atrasos(inicios: dict, faixas) -> dict:
    """
    {faixa: segundos a atrasar (positivo) ou cortar do começo (negativo)} na linha do tempo da saída, que começa
    com a tela (ou, sem tela, com o primeiro áudio). Sem `inicios`, tudo 0.
    """
    inicios = inicios or {}
    if not all(f in inicios for f in faixas):
        return {f: 0.0 for f in faixas}
    zero = inicios["tela"] if "tela" in inicios else min(inicios[f] for f in faixas)
    return {f: round(inicios[f] - zero, 3) for f in faixas}


def comando(exe: str, pasta: Path, faixas: dict, metadados: dict) -> tuple[list, Path]:
    """(argv do ffmpeg, arquivo de saída). `faixas`: {nome: caminho do .wav}, na ordem de gravação."""
    if not faixas:
        raise ErroJuntar(f"Não achei faixa de áudio em {pasta}.")
    video = pasta / tela.ARQUIVO
    tem_tela = video.is_file()
    nomes = list(faixas)
    desloc = atrasos(metadados.get("inicios"), nomes + (["tela"] if tem_tela else []))

    argv = [exe, "-hide_banner", "-loglevel", "error", "-y"]
    if tem_tela:
        argv += ["-i", str(video)]
    for nome in nomes:
        argv += ["-i", str(faixas[nome])]

    primeiro = 1 if tem_tela else 0
    cadeias, rotulos = [], []
    for i, nome in enumerate(nomes):
        d = desloc[nome]
        ajuste = f"adelay={int(d * 1000)}:all=1" if d > 0 else f"atrim=start={-d},asetpts=PTS-STARTPTS" if d < 0 else "anull"
        cadeias.append(f"[{primeiro + i}:a]{ajuste}[a{i}]")
        rotulos.append(f"[a{i}]")
    if len(nomes) > 1:  # normalize=0: sem isso o amix divide o volume pelo número de faixas
        cadeias.append("".join(rotulos) + f"amix=inputs={len(nomes)}:duration=longest:normalize=0,"
                       "alimiter=limit=0.95[som]")
    else:
        cadeias[-1] = cadeias[-1].replace("[a0]", "[som]")
    argv += ["-filter_complex", ";".join(cadeias)]

    if tem_tela:
        saida = pasta / VIDEO
        argv += ["-map", "0:v", "-map", "[som]", "-c:v", "copy"]
    else:
        saida = pasta / SO_AUDIO
        argv += ["-map", "[som]"]
    argv += ["-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(saida)]
    return argv, saida


def juntar(pasta, achar=shutil.which, executar=subprocess.run) -> Path:
    """Gera o arquivo único da gravação e devolve o caminho dele."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise ErroJuntar(f"Não achei a pasta {pasta}.")
    exe = achar("ffmpeg")
    if not exe:
        raise ErroJuntar(audio.COMO_INSTALAR_FFMPEG)
    argv, saida = comando(exe, pasta, gravacao.faixas_na_pasta(pasta), gravacao.ler_metadados(pasta))
    r = executar(argv, capture_output=True, text=True)
    if r.returncode != 0:
        raise ErroJuntar(f"O ffmpeg não conseguiu juntar: {(r.stderr or '').strip()[-300:]}")
    return saida


def main(argv=None, juntar_=None) -> int:
    import argparse
    import sys
    p = argparse.ArgumentParser(prog="vatty juntar",
                                description="Junta a tela, o som do PC e o microfone de uma gravação num arquivo só "
                                            "(video.mp4, ou audio.m4a sem tela), para enviar.")
    p.add_argument("pasta", type=Path, help="a pasta da gravação (gravacoes/<data>)")
    args = p.parse_args(argv)
    try:
        saida = (juntar_ or juntar)(args.pasta)
    except ErroJuntar as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
    print(f"Pronto para enviar: {saida}")
    return 0
