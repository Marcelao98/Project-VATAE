"""
De onde vem o conteúdo: URL do YouTube (via yt-dlp) ou arquivo local.

`fabrica` é a classe YoutubeDL; os testes trocam por um dublê.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


def eh_url(texto: str) -> bool:
    return bool(re.match(r"^https?://", str(texto).strip(), re.IGNORECASE))


@dataclass
class Video:
    id: str
    url: str
    titulo: str
    canal: str | None
    duracao_s: float
    data: str | None          # AAAAMMDD, como o YouTube devolve
    idioma: str | None        # idioma original do vídeo, se o YouTube souber
    legendas: dict = field(default_factory=dict)              # manuais: chave -> formatos
    legendas_automaticas: dict = field(default_factory=dict)
    # Capítulos que o autor marcou: [{"inicio", "fim", "titulo"}]. Dão aos
    # agentes a estrutura que o próprio autor definiu.
    capitulos: list = field(default_factory=list)
    descricao: str = ""

    def para_json(self) -> dict:
        return {
            "tipo": "youtube",
            "id": self.id,
            "url": self.url,
            "titulo": self.titulo,
            "canal": self.canal,
            "duracao_s": self.duracao_s,
            "data": self.data,
            "idioma": self.idioma,
            "capitulos": self.capitulos,
            "descricao": self.descricao,
        }


def _opcoes(**extras) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        # O YouTube exige um runtime de JavaScript para liberar todos os
        # formatos. O yt-dlp só tenta o deno por padrão; o node (>= 22) também
        # serve. Sem nenhum, ainda funciona, mas com menos formatos.
        "js_runtimes": {"deno": {}, "node": {}},
        **extras,
    }


def _fabrica_padrao():
    from yt_dlp import YoutubeDL

    return YoutubeDL


def inspecionar(url: str, fabrica=None) -> Video:
    """Lê os metadados e as legendas disponíveis, sem baixar nada."""
    fabrica = fabrica or _fabrica_padrao()
    with fabrica(_opcoes(skip_download=True)) as ydl:
        info = ydl.extract_info(url, download=False)
    return Video(
        id=info["id"],
        url=info.get("webpage_url") or url,
        titulo=info.get("title") or info["id"],
        canal=info.get("channel") or info.get("uploader"),
        duracao_s=float(info.get("duration") or 0),
        data=info.get("upload_date"),
        idioma=info.get("language"),
        legendas=info.get("subtitles") or {},
        legendas_automaticas=info.get("automatic_captions") or {},
        capitulos=[
            {"inicio": c.get("start_time"), "fim": c.get("end_time"), "titulo": c.get("title")}
            for c in info.get("chapters") or []
        ],
        descricao=info.get("description") or "",
    )


def _unico(pasta: Path, padrao: str, o_que: str) -> Path:
    achados = sorted(pasta.glob(padrao))
    if not achados:
        raise RuntimeError(f"o yt-dlp não baixou {o_que}")
    return achados[0]


def baixar_legenda(url: str, chave: str, automatica: bool, destino: Path, fabrica=None) -> Path:
    """Baixa só a legenda `chave` em .vtt para a pasta `destino`. Sem áudio."""
    fabrica = fabrica or _fabrica_padrao()
    opcoes = _opcoes(
        skip_download=True,
        writesubtitles=not automatica,
        writeautomaticsub=automatica,
        subtitleslangs=[chave],
        subtitlesformat="vtt",
        outtmpl={"default": str(Path(destino) / "legenda.%(ext)s")},
    )
    with fabrica(opcoes) as ydl:
        ydl.download([url])
    return _unico(Path(destino), "legenda*.vtt", "a legenda")


def baixar_audio(url: str, destino: Path, fabrica=None) -> Path:
    """Baixa só a faixa de áudio, no formato que vier (o ffmpeg decodifica)."""
    fabrica = fabrica or _fabrica_padrao()
    opcoes = _opcoes(
        format="bestaudio/best",
        outtmpl={"default": str(Path(destino) / "audio.%(ext)s")},
    )
    with fabrica(opcoes) as ydl:
        ydl.download([url])
    return _unico(Path(destino), "audio.*", "o áudio")


ALTURA_VIDEO_MAX = 720  # texto de slide fica pequeno demais para o OCR em 480p


def baixar_video(url: str, destino: Path, fabrica=None) -> Path:
    """Baixa só a imagem (sem áudio), em até 720p. O vídeo é temporário: quem chama apaga."""
    fabrica = fabrica or _fabrica_padrao()
    h = ALTURA_VIDEO_MAX
    opcoes = _opcoes(
        format=f"bestvideo[height<={h}]/best[height<={h}]/bestvideo/best",
        outtmpl={"default": str(Path(destino) / "video.%(ext)s")},
    )
    with fabrica(opcoes) as ydl:
        ydl.download([url])
    return _unico(Path(destino), "video.*", "o vídeo")
