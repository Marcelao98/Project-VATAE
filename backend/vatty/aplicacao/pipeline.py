"""
O pipeline: entrada (URL, arquivo ou pasta de gravação) -> pasta do vídeo.

É o que a CLI fazia por dentro, sem `print` nem `input`: as decisões vão ao
`Decisor` e as mensagens ao `Progresso` (ver portas.py). A CLI e a API usam
este mesmo código.
"""

import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path

from .. import aula, fonte, gravacao, legenda, motor, ocr, pasta, preprocessar, quadros, visual
from ..audio import ErroDeDecodificacao, FfmpegAusente
from .portas import Decisor, ErroPipeline, Opcoes, PerguntaLegenda, PerguntaVisual, Progresso


@dataclass
class Saida:
    """O que ficou pronto."""
    destino: Path               # a pasta do vídeo
    txt: Path                   # transcricao.txt
    dados_fonte: dict
    resultado: object           # motor.Resultado
    gasto_s: float              # tempo até o texto ficar pronto
    visual: Path | None = None  # visual.json, se foi feito
    erro_visual: str | None = None  # o texto está salvo, mas o visual falhou


def relogio(segundos: float) -> str:
    m, s = divmod(int(segundos), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _download_error():
    try:
        from yt_dlp.utils import DownloadError
    except ImportError:  # pragma: no cover
        DownloadError = RuntimeError
    return DownloadError


# --- Whisper -----------------------------------------------------------------

def _whisper(caminho, opcoes: Opcoes, idioma, decisor: Decisor, progresso: Progresso, em_gravacao=False):
    hotwords = None
    if opcoes.termos:
        hotwords = motor.combinar_termos(Path(c).read_text(encoding="utf-8") for c in opcoes.termos) or None
    if not motor.modelo_em_cache(opcoes.modelo):
        progresso.mensagem(f"Primeira execução com '{opcoes.modelo}': o modelo (cerca de 1,5 GB) vai ser baixado "
                           "pro cache do Hugging Face. Isso só acontece uma vez.")
    modo = opcoes.horario_por_palavra
    palavras = modo == "sim" or (modo == "auto" and em_gravacao)
    try:
        preparo = preprocessar.preparar(
            caminho, opcoes.preprocessar, perguntar=decisor.preprocessar,
            interativo=decisor.interativo, ruido_modelo=opcoes.ruido_modelo, dizer=progresso.mensagem)
        progresso.mensagem("Transcrevendo com Whisper...")
        extras = {"carregar_audio": preparo.carregar_audio} if preparo.carregar_audio else {}
        resultado = motor.transcrever(caminho, modelo=opcoes.modelo, idioma=idioma, hotwords=hotwords,
                                      palavras=palavras, vad_silencio_ms=opcoes.vad_silencio_ms,
                                      progresso=lambda atual, total: progresso.andamento("whisper", atual, total),
                                      **extras)
    except (FileNotFoundError, FfmpegAusente, ErroDeDecodificacao) as e:
        raise ErroPipeline(str(e)) from e
    resultado.preprocessamento = preparo.info
    progresso.fim_andamento()
    for aviso in resultado.avisos:
        progresso.aviso(aviso)
    if resultado.refeitos:
        linhas = [f"{len(resultado.refeitos)} trecho(s) com sinal de loop refeito(s) sem os termos:"]
        linhas += [f"  [{relogio(r['inicio'])}-{relogio(r['fim'])}] {r['motivo']}" for r in resultado.refeitos]
        progresso.mensagem("\n".join(linhas))
    return resultado


def _idioma(opcoes: Opcoes):
    return None if opcoes.lang == "auto" else opcoes.lang


# --- Fontes ------------------------------------------------------------------

def _do_youtube(opcoes: Opcoes, decisor: Decisor, progresso: Progresso):
    """URL -> (pasta, fonte.json, resultado). Legenda primeiro, Whisper se o usuário quiser."""
    DownloadError = _download_error()
    try:
        progresso.mensagem("Lendo o vídeo no YouTube...")
        video = fonte.inspecionar(opcoes.entrada)
        progresso.mensagem(f"{video.titulo} ({relogio(video.duracao_s)})")
        lang = video.idioma if opcoes.lang == "auto" else opcoes.lang
        escolha = None
        if lang and opcoes.texto != "whisper":
            escolha = legenda.escolher(video.legendas, video.legendas_automaticas, lang)
        if escolha is None and opcoes.texto != "whisper":
            progresso.mensagem(f"Sem legenda confiável em '{lang or '?'}': vai com Whisper.")
        if escolha and opcoes.texto == "perguntar" and not decisor.interativo:
            raise ErroPipeline("o vídeo tem legenda, mas não há terminal para perguntar. "
                               "Use --texto legenda ou --texto whisper.")

        destino = opcoes.saida / pasta.slug(video.titulo, video.id)
        with tempfile.TemporaryDirectory(prefix="vatty-") as tmp:
            if escolha:
                vtt = fonte.baixar_legenda(video.url, escolha.chave, escolha.automatica, Path(tmp))
                segmentos = legenda.ler_vtt(vtt.read_text(encoding="utf-8"))
                decisao = opcoes.texto
                if decisao == "perguntar":
                    decisao = decisor.legenda(PerguntaLegenda(
                        chave=escolha.chave, automatica=escolha.automatica,
                        indicadores=legenda.indicadores(segmentos, video.duracao_s),
                        amostras=list(legenda.amostras(segmentos))))
                if decisao == "legenda":
                    resultado = legenda.para_resultado(segmentos, video.url, video.duracao_s, lang, escolha)
                    return destino, video.para_json(), resultado
            progresso.mensagem("Baixando o áudio...")
            audio = fonte.baixar_audio(video.url, Path(tmp))
            resultado = _whisper(audio, opcoes, _idioma(opcoes), decisor, progresso)
            resultado.fonte = video.url
            # o áudio some junto com a pasta temporária: só o texto fica
            return destino, video.para_json(), resultado
    except DownloadError as e:
        raise ErroPipeline(f"YouTube: {e}") from e


def _do_gravacao(opcoes: Opcoes, pasta_audio: Path, decisor: Decisor, progresso: Progresso):
    """Pasta de gravação (sistema.wav e/ou microfone.wav) -> um texto só, com `falante`."""
    faixas = gravacao.faixas_na_pasta(pasta_audio)
    if not faixas:
        raise ErroPipeline(f"não achei sistema.wav nem microfone.wav em {pasta_audio}")
    resultados = {}
    for nome, caminho in faixas.items():
        progresso.mensagem(f"Faixa '{nome}'...")
        resultados[nome] = _whisper(caminho, opcoes, _idioma(opcoes), decisor, progresso, em_gravacao=True)
    resultado = gravacao.juntar_faixas(resultados)
    dados = {"tipo": "gravacao", "titulo": f"Gravação {pasta_audio.name}", "data": pasta_audio.name,
             "duracao_s": resultado.duracao_s, "faixas": list(faixas), "falantes": gravacao.FALANTES}
    return opcoes.saida / pasta.slug(f"gravacao {pasta_audio.name}"), dados, resultado


def _do_arquivo(opcoes: Opcoes, decisor: Decisor, progresso: Progresso):
    caminho = Path(opcoes.entrada)
    if caminho.is_dir():
        return _do_gravacao(opcoes, caminho, decisor, progresso)
    if not caminho.is_file():
        raise ErroPipeline(f"arquivo não encontrado: {caminho}")
    progresso.mensagem(f"Transcrevendo {caminho.name}...")
    resultado = _whisper(caminho, opcoes, _idioma(opcoes), decisor, progresso)
    dados = {"tipo": "arquivo", "caminho": str(caminho.resolve()), "titulo": caminho.stem,
             "duracao_s": resultado.duracao_s}
    return opcoes.saida / pasta.slug(caminho.stem), dados, resultado


def _apagar_audio(opcoes: Opcoes, pasta_audio: Path, decisor: Decisor, progresso: Progresso) -> None:
    """Depois que o texto foi gravado: apaga os .wav se o usuário quiser (padrão: guardar)."""
    arquivos = list(gravacao.faixas_na_pasta(pasta_audio).values())
    decisao = opcoes.apagar_audio
    if decisao is None:
        decisao = decisor.apagar_audio(pasta_audio)
        if decisao is None:  # não deu para perguntar: o decisor já avisou
            return
    if not decisao:
        progresso.mensagem(f"Áudio guardado em {pasta_audio}.")
        return
    for arquivo in arquivos:
        arquivo.unlink()
    try:
        pasta_audio.rmdir()  # só se ficou vazia: nunca apaga o que não é nosso
    except OSError:
        pass
    progresso.mensagem("Áudio apagado.")


# --- Visual (perfil aula) ----------------------------------------------------

def _lang_visual(opcoes: Opcoes, dados_fonte) -> str | None:
    if opcoes.lang != "auto":
        return opcoes.lang
    return (dados_fonte.get("idioma") or "")[:2] or None


def _fazer_visual(opcoes: Opcoes, destino: Path, dados_fonte: dict, decisor: Decisor,
                  progresso: Progresso) -> Path | None:
    idiomas = ocr.idiomas_para(_lang_visual(opcoes, dados_fonte))
    exe = ocr.verificar(idiomas)  # antes de baixar qualquer coisa
    with tempfile.TemporaryDirectory(prefix="vatty-visual-") as tmp:
        if fonte.eh_url(opcoes.entrada):
            progresso.mensagem("\nBaixando o vídeo (só a imagem, até 720p)...")
            video = fonte.baixar_video(dados_fonte.get("url") or opcoes.entrada, Path(tmp))
        else:
            video = Path(opcoes.entrada)
        progresso.mensagem("Procurando as trocas de tela...")
        deteccao = aula.detectar(video, progresso=lambda a, t: progresso.andamento("tela", a, t))
        progresso.fim_andamento()
        if not deteccao.slides:
            raise ErroPipeline("não achei nenhuma tela no vídeo")
        if deteccao.truncado:
            progresso.aviso(f"passou de {visual.MAX_SLIDES} trocas de tela; só as primeiras ficam.")
        if opcoes.visual == "auto":
            ind, (perfil, motivo) = aula.palpite(video, deteccao, tmp, idiomas=idiomas, exe=exe)
            if not decisor.visual(PerguntaVisual(indicadores=ind, perfil=perfil, motivo=motivo)):
                progresso.mensagem("Visual pulado.")
                return None
        progresso.mensagem(f"Lendo o texto de {len(deteccao.slides)} slide(s) com o Tesseract...")
        dados = aula.montar(video, deteccao, destino, idiomas=idiomas, exe=exe,
                            progresso=lambda a, t: progresso.andamento("slides", a, t),
                            parametros={"intervalo_s": visual.INTERVALO_S, "limiar_mudanca": visual.LIMIAR_MUDANCA,
                                        "max_slides": visual.MAX_SLIDES, "escolha": opcoes.visual})
        progresso.fim_andamento()
    caminho = pasta.gravar_visual(destino, dados)
    progresso.mensagem(f"Visual: {len(dados['eventos'])} slide(s) em {caminho.parent} (visual.json e frames/).")
    return caminho


# --- Entrada principal -------------------------------------------------------

def processar(opcoes: Opcoes, decisor: Decisor, progresso: Progresso) -> Saida:
    """
    Produz a pasta do vídeo para `opcoes.entrada`. Levanta `ErroPipeline` se o
    texto não sair; se só o visual falhar, o texto fica salvo e `Saida.erro_visual` diz o porquê.
    """
    comeco = time.perf_counter()
    if opcoes.visual == "auto" and not decisor.interativo:
        raise ErroPipeline("--visual auto precisa de um terminal para perguntar. "
                           "Use --visual aula ou --visual nenhum.")
    destino, dados_fonte, resultado = (_do_youtube if fonte.eh_url(opcoes.entrada) else _do_arquivo)(
        opcoes, decisor, progresso)
    txt = pasta.gravar(destino, dados_fonte, resultado)
    gasto = time.perf_counter() - comeco
    progresso.mensagem(f"Pronto em {relogio(gasto)} (texto de {resultado.origem}, "
                       f"{resultado.duracao_s:.0f}s de áudio): {txt.parent}")
    saida = Saida(destino=destino, txt=txt, dados_fonte=dados_fonte, resultado=resultado, gasto_s=gasto)

    if dados_fonte.get("tipo") == "gravacao":
        if opcoes.visual != "nenhum":
            progresso.aviso("--visual não se aplica a uma gravação de áudio.")
        _apagar_audio(opcoes, Path(opcoes.entrada), decisor, progresso)
    elif opcoes.visual != "nenhum":
        DownloadError = _download_error()
        try:
            saida = replace(saida, visual=_fazer_visual(opcoes, destino, dados_fonte, decisor, progresso))
        except (ErroPipeline, ocr.ErroOcr, quadros.ErroDeVideo, FfmpegAusente, FileNotFoundError, RuntimeError,
                DownloadError) as e:
            saida = replace(saida, erro_visual=str(e))
    return saida
