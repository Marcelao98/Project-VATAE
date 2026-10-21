"""
De onde vem o conteúdo: URL de vídeo (YouTube, TikTok e o que o yt-dlp suportar) ou arquivo local.

`fabrica` é a classe YoutubeDL; os testes trocam por um dublê.
"""

import copy
import os
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
    plataforma: str = "YouTube"   # quem hospeda o vídeo (extrator do yt-dlp): YouTube, TikTok, Instagram...

    def para_json(self) -> dict:
        dados = {
            "tipo": "youtube" if self.plataforma == "YouTube" else "url",
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
        if self.plataforma != "YouTube":  # o contrato do YouTube fica como sempre
            dados["plataforma"] = self.plataforma
        return dados


NAVEGADORES = ("firefox", "edge", "chrome", "brave", "opera", "vivaldi", "chromium", "safari")
VAR_NAVEGADOR = "VATTY_COOKIES_NAVEGADOR"
VAR_IPV4 = "VATTY_IPV4"   # a CLI liga quando o YouTube desconfia do acesso (ver cli._do_youtube)


def eh_bloqueio(texto: str) -> bool:
    """O YouTube pediu para provar que não é robô (ou exigiu login)."""
    return "not a bot" in texto or "Sign in to confirm" in texto or "--cookies" in texto


def diagnostico(procurar=None) -> str:
    """Versão do yt-dlp e runtimes de JavaScript visíveis: explica por que funciona num terminal e não noutro."""
    import shutil
    procurar = procurar or shutil.which
    try:
        from yt_dlp.version import __version__ as versao
    except ImportError:
        versao = "não instalado"
    sim = lambda nome: "sim" if procurar(nome) else "não"
    return f"yt-dlp {versao}; Deno: {sim('deno')}; Node: {sim('node')}"


def _cookies() -> dict:
    """
    Login do navegador (cookies), quando o YouTube pede "prove que não é robô". O navegador vem da
    variável VATTY_COOKIES_NAVEGADOR (a CLI preenche com --cookies-navegador). O yt-dlp lê os cookies
    direto do perfil do navegador; nada é guardado pela Vatty.
    """
    navegador = os.environ.get(VAR_NAVEGADOR, "").strip().lower()
    extras = {"cookiesfrombrowser": (navegador,)} if navegador in NAVEGADORES else {}
    if os.environ.get(VAR_IPV4):
        extras["source_address"] = "0.0.0.0"  # força IPv4: o YouTube desconfia mais de IPv6
    return extras


def _opcoes(**extras) -> dict:
    return {
        **_cookies(),
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


def _plataforma(info: dict) -> str:
    chave = str(info.get("extractor_key") or info.get("extractor") or "")
    if not chave or chave.lower().startswith("youtube"):
        return "YouTube"
    return chave


def _video(info: dict, url: str) -> Video:
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
        plataforma=_plataforma(info),
    )


def _unico(pasta: Path, padrao: str, o_que: str) -> Path:
    achados = sorted(pasta.glob(padrao))
    if not achados:
        raise RuntimeError(f"o yt-dlp não baixou {o_que}")
    return achados[0]


ALTURA_VIDEO_MAX = 720  # texto de slide fica pequeno demais para o OCR em 480p

# Opções que mudam de um download para outro. A mesma instância do YoutubeDL serve a todos, então
# cada chamada parte deste estado e só depois aplica o que é dela.
_POR_CHAMADA = {
    "skip_download": False,
    "writesubtitles": False,
    "writeautomaticsub": False,
    "subtitleslangs": [],
    "subtitlesformat": "best",
}


class Sessao:
    """
    Uma URL, uma instância do yt-dlp. A página do vídeo é lida UMA vez (`inspecionar`) e os downloads
    reaproveitam esse `info` e os cookies da mesma instância (`process_ie_result`), em vez de abrir
    a página de novo. O TikTok entrega um desafio na primeira leitura e recusa a segunda
    ("Unable to extract universal data for rehydration"); com a sessão, a segunda leitura não existe.
    `fabrica` é a classe YoutubeDL; os testes trocam por um dublê.
    """

    def __init__(self, url: str, fabrica=None):
        self.url = url
        fabrica = fabrica or _fabrica_padrao()
        self._ydl = fabrica(_opcoes(skip_download=True, outtmpl={"default": "%(id)s.%(ext)s"}))
        self._bruto = None   # o que o extrator achou, ainda sem escolher formato
        self._info = None    # o mesmo, já processado (formato escolhido): só para os metadados

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        self.fechar()
        return False

    def fechar(self) -> None:
        """Fecha a instância (o yt-dlp salva os cookies, se houver arquivo). Pode chamar mais de uma vez."""
        ydl, self._ydl = self._ydl, None
        if ydl is not None and hasattr(ydl, "__exit__"):
            ydl.__exit__(None, None, None)

    def inspecionar(self) -> Video:
        """Lê os metadados e as legendas disponíveis, sem baixar nada. Só abre a página na primeira vez."""
        if self._info is None:
            # `process=False` devolve o resultado do extrator antes de escolher o formato. Os downloads
            # partem DELE: o `info` já processado traz o formato escolhido na leitura (`requested_formats`)
            # e o yt-dlp o reaproveitaria, ignorando o formato pedido (visto no teste com extrator falso).
            self._bruto = self._ydl.extract_info(self.url, download=False, process=False)
            self._info = self._ydl.process_ie_result(copy.deepcopy(self._bruto), download=False)
        return _video(self._info, self.url)

    def _baixar(self, destino: Path, nome: str, formato: str | None = None, **opcoes) -> None:
        self.inspecionar()
        params = self._ydl.params
        params.update(copy.deepcopy(_POR_CHAMADA))
        params.update(opcoes)
        params["outtmpl"]["default"] = str(Path(destino) / f"{nome}.%(ext)s")
        if formato:
            params["format"] = formato
            # o seletor é montado na criação da instância; para outro formato, monta-se de novo
            self._ydl.format_selector = self._ydl.build_format_selector(formato)
        # copia: o yt-dlp mexe no dicionário, e o próximo download parte do original
        self._ydl.process_ie_result(copy.deepcopy(self._bruto), download=True)

    def baixar_legenda(self, chave: str, automatica: bool, destino: Path) -> Path:
        """Baixa só a legenda `chave` em .vtt para a pasta `destino`. Sem áudio."""
        self._baixar(destino, "legenda", skip_download=True, writesubtitles=not automatica,
                     writeautomaticsub=automatica, subtitleslangs=[chave], subtitlesformat="vtt")
        return _unico(Path(destino), "legenda*.vtt", "a legenda")

    def baixar_audio(self, destino: Path) -> Path:
        """Baixa só a faixa de áudio, no formato que vier (o ffmpeg decodifica)."""
        self._baixar(destino, "audio", formato="bestaudio/best")
        return _unico(Path(destino), "audio.*", "o áudio")

    def baixar_video(self, destino: Path) -> Path:
        """Baixa só a imagem (sem áudio), em até 720p. O vídeo é temporário: quem chama apaga."""
        h = ALTURA_VIDEO_MAX
        self._baixar(destino, "video", formato=f"bestvideo[height<={h}]/best[height<={h}]/bestvideo/best")
        return _unico(Path(destino), "video.*", "o vídeo")


# Funções soltas: cada uma abre a própria sessão (e, portanto, lê a página de novo). Servem para
# quem só precisa de uma coisa; a CLI usa `Sessao` para ler uma vez só.

def listar_playlist(url: str, fabrica=None) -> tuple:
    """
    (título, [urls]) de uma playlist ou canal, sem abrir cada vídeo (`extract_flat`). URL de um vídeo só
    devolve ele mesmo. Entrada sem endereço (só o id) vira o link do YouTube.
    """
    fabrica = fabrica or _fabrica_padrao()
    with fabrica(_opcoes(skip_download=True, extract_flat="in_playlist")) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    entradas = info.get("entries")
    if entradas is None:
        return info.get("title") or "", [url]
    urls = []
    for e in entradas:
        if not e:
            continue  # vídeo indisponível vem como None
        endereco = e.get("url") or e.get("webpage_url")
        if endereco and not eh_url(endereco) and e.get("id"):
            endereco = f"https://www.youtube.com/watch?v={e['id']}"
        elif not endereco and e.get("id"):
            endereco = f"https://www.youtube.com/watch?v={e['id']}"
        if endereco:
            urls.append(endereco)
    return info.get("title") or "", urls


def inspecionar(url: str, fabrica=None) -> Video:
    with Sessao(url, fabrica) as sessao:
        return sessao.inspecionar()


def baixar_legenda(url: str, chave: str, automatica: bool, destino: Path, fabrica=None) -> Path:
    with Sessao(url, fabrica) as sessao:
        return sessao.baixar_legenda(chave, automatica, destino)


def baixar_audio(url: str, destino: Path, fabrica=None) -> Path:
    with Sessao(url, fabrica) as sessao:
        return sessao.baixar_audio(destino)


def baixar_video(url: str, destino: Path, fabrica=None) -> Path:
    with Sessao(url, fabrica) as sessao:
        return sessao.baixar_video(destino)
