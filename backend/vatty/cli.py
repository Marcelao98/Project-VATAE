"""CLI fina: traduz argumentos, chama as camadas e pergunta ao usuário. `vatty <url-ou-arquivo>`."""

import argparse
import sys
import tempfile
import textwrap
import time
from pathlib import Path

from . import aula, fonte, gravacao, legenda, motor, ocr, pasta, preprocessar, quadros, visual
from .audio import ErroDeDecodificacao, FfmpegAusente

PREPROCESSAR_ESCOLHAS = ("perguntar", "sim", "nao")
TEXTO_ESCOLHAS = ("perguntar", "legenda", "whisper")
VISUAL_ESCOLHAS = ("nenhum", "auto", "aula")

AVISO_CONSENTIMENTO = ("Aviso: gravar uma conversa sem avisar os outros participantes pode ser ilegal "
                       "onde você mora. Avise quem estiver na gravação.")


class Erro(Exception):
    """Erro para mostrar ao usuário e sair com código 1."""


def _relogio(segundos: float) -> str:
    m, s = divmod(int(segundos), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _mostrar_progresso(atual: float, total: float) -> None:
    porcento = int(atual / total * 100) if total else 100
    print(f"\r  {porcento:3d}%  {_relogio(atual)} / {_relogio(total)}", end="", flush=True)


def _opcoes_comuns(p) -> None:
    """Opções que `vatty` e `vatty gravar` compartilham (o que o Whisper e a pasta de saída precisam)."""
    p.add_argument("--modelo", default=motor.MODELO_PADRAO, help=f"modelo do faster-whisper (padrão: {motor.MODELO_PADRAO})")
    p.add_argument("--lang", default=motor.IDIOMA_PADRAO, help="idioma (padrão: pt; 'auto' usa o do vídeo ou detecta)")
    p.add_argument("--termos", type=Path, nargs="+", action="extend", metavar="ARQUIVO",
                   help="um ou mais arquivos .txt com termos, um por linha (viram hotwords do Whisper; o limite de "
                        "~223 tokens vale para a soma). Ex.: --termos termos/tecnologia-ia.txt termos/girias-brasil.txt")
    p.add_argument("--saida", type=Path, default=Path("transcricoes"), help="pasta de saída (padrão: transcricoes/)")
    p.add_argument("--apagar-audio", dest="apagar_audio", action="store_true", default=None,
                   help="gravação: apaga os .wav depois de transcrever, sem perguntar")
    p.add_argument("--manter-audio", dest="apagar_audio", action="store_false", default=None,
                   help="gravação: guarda os .wav depois de transcrever, sem perguntar")
    p.add_argument("--horario-por-palavra", dest="horario_por_palavra", choices=("auto", "sim", "nao"), default="auto",
                   help="ajusta o início e o fim de cada trecho à primeira e à última palavra (gasta mais tempo). "
                        "'auto' (padrão) liga só em gravação; 'sim' liga sempre; 'nao' desliga")
    p.add_argument("--vad-silencio-ms", dest="vad_silencio_ms", type=int, default=None, metavar="MS",
                   help="experimental: pausa mínima (ms) que corta a fala no filtro de voz do Whisper. "
                        "Sem a opção, fica o padrão do faster-whisper (160)")
    p.add_argument("--preprocessar", choices=PREPROCESSAR_ESCOLHAS, default="perguntar",
                   help="antes do Whisper: corta o ronco grave, tira o ruído e sobe a voz baixa (áudio de WhatsApp, "
                        "celular). 'perguntar' (padrão) mede o áudio e só pergunta se algo estiver ruim; "
                        "'sim' aplica sempre; 'nao' não mede nem mexe")
    p.add_argument("--ruido-modelo", dest="ruido_modelo", default=None, metavar="NOME_OU_ARQUIVO",
                   help=f"modelo de ruído do arnndn: {', '.join(preprocessar.MODELOS_RUIDO)} (padrão: "
                        f"{preprocessar.MODELO_RUIDO_PADRAO}, baixado na primeira vez) ou o caminho de um .rnnn")


def _argumentos(argv):
    p = argparse.ArgumentParser(prog="vatty", description="Transcreve um vídeo do YouTube, um arquivo de áudio/vídeo "
                                "ou uma gravação. Para gravar o áudio do PC: vatty gravar --help.")
    p.add_argument("entrada", help="URL do YouTube, arquivo (.opus, .ogg, .mp3, .m4a, .wav, .mp4...) "
                                   "ou pasta de uma gravação (gravacoes/AAAA-MM-DD_HH-MM)")
    _opcoes_comuns(p)
    p.add_argument("--texto", choices=TEXTO_ESCOLHAS, default="perguntar",
                   help="YouTube: usar a legenda, o Whisper, ou perguntar depois de mostrar trechos (padrão)")
    p.add_argument("--visual", choices=VISUAL_ESCOLHAS, default="nenhum",
                   help="extrai também o que aparece na tela (slides + OCR com Tesseract). 'aula' faz direto; "
                        "'auto' mostra um palpite e pergunta; 'nenhum' (padrão) só o texto. Precisa de vídeo e do Tesseract")
    return p.parse_args(argv)


# --- Whisper -----------------------------------------------------------------

def _whisper(caminho, args, idioma):
    hotwords = None
    if args.termos:
        hotwords = motor.combinar_termos(c.read_text(encoding="utf-8") for c in args.termos) or None
    if not motor.modelo_em_cache(args.modelo):
        print(f"Primeira execução com '{args.modelo}': o modelo (cerca de 1,5 GB) vai ser baixado "
              "pro cache do Hugging Face. Isso só acontece uma vez.")
    modo = getattr(args, "horario_por_palavra", "auto")
    palavras = modo == "sim" or (modo == "auto" and getattr(args, "em_gravacao", False))
    try:
        preparo = preprocessar.preparar(
            caminho, getattr(args, "preprocessar", "nao"), perguntar=_perguntar_preprocessar,
            interativo=sys.stdin.isatty(), ruido_modelo=getattr(args, "ruido_modelo", None))
        print("Transcrevendo com Whisper...")
        extras = {"carregar_audio": preparo.carregar_audio} if preparo.carregar_audio else {}
        resultado = motor.transcrever(caminho, modelo=args.modelo, idioma=idioma, hotwords=hotwords,
                                      palavras=palavras, vad_silencio_ms=getattr(args, "vad_silencio_ms", None),
                                      progresso=_mostrar_progresso, **extras)
    except (FileNotFoundError, FfmpegAusente, ErroDeDecodificacao) as e:
        raise Erro(str(e)) from e
    resultado.preprocessamento = preparo.info
    print()
    for aviso in resultado.avisos:
        print(f"Aviso: {aviso}")
    if resultado.refeitos:
        print(f"{len(resultado.refeitos)} trecho(s) com sinal de loop refeito(s) sem os termos:")
        for r in resultado.refeitos:
            print(f"  [{_relogio(r['inicio'])}-{_relogio(r['fim'])}] {r['motivo']}")
    return resultado


def _perguntar_preprocessar(diagnostico) -> bool:
    """Enter aceita a recomendação (aplicar), como no `--visual auto`."""
    while True:
        try:
            resposta = input("Aplicar o pré-processamento (tirar ronco e ruído, subir a voz)? [S/n] ").strip().lower()
        except EOFError:
            raise Erro("cancelado")
        if resposta in ("", "s", "sim"):
            return True
        if resposta in ("n", "nao", "não"):
            return False


# --- Legenda -----------------------------------------------------------------

def _mostrar_legenda(escolha, segmentos, duracao) -> None:
    tipo = "automática do YouTube" if escolha.automatica else "manual (escrita pelo autor)"
    ind = legenda.indicadores(segmentos, duracao)
    print(f"\nLegenda {tipo}, '{escolha.chave}':")
    print(f"  {ind['palavras']} palavras, cobre {ind['cobertura_pct']}% do vídeo")
    print(f"  pontuação: {ind['pontuacao_por_100']} sinais a cada 100 palavras")
    print(f"  palavras com maiúscula: {ind['maiusculas_pct']}%")
    print(f"  marcas como [Música]: {ind['marcas']}")
    print("\nTrechos:")
    for inicio, trecho in legenda.amostras(segmentos):
        corpo = textwrap.fill(trecho, width=96, initial_indent="    ", subsequent_indent="    ")
        print(f"\n  [{_relogio(inicio)}]\n{corpo}")
    print()


def _perguntar() -> str:
    while True:
        try:
            resposta = input("Usar a [l]egenda ou transcrever com [w]hisper? ").strip().lower()
        except EOFError:
            raise Erro("cancelado")
        if resposta in ("l", "legenda"):
            return "legenda"
        if resposta in ("w", "whisper"):
            return "whisper"


# --- Fluxos ------------------------------------------------------------------

def _do_youtube(args):
    """URL -> (pasta, fonte.json, resultado). Legenda primeiro, Whisper se o usuário quiser."""
    try:
        from yt_dlp.utils import DownloadError
    except ImportError:  # pragma: no cover
        DownloadError = RuntimeError

    try:
        print("Lendo o vídeo no YouTube...")
        video = fonte.inspecionar(args.entrada)
        print(f"{video.titulo} ({_relogio(video.duracao_s)})")
        lang = video.idioma if args.lang == "auto" else args.lang
        escolha = None
        if lang and args.texto != "whisper":
            escolha = legenda.escolher(video.legendas, video.legendas_automaticas, lang)
        if escolha is None and args.texto != "whisper":
            print(f"Sem legenda confiável em '{lang or '?'}': vai com Whisper.")
        if escolha and args.texto == "perguntar" and not sys.stdin.isatty():
            raise Erro("o vídeo tem legenda, mas não há terminal para perguntar. "
                       "Use --texto legenda ou --texto whisper.")

        destino = args.saida / pasta.slug(video.titulo, video.id)
        with tempfile.TemporaryDirectory(prefix="vatty-") as tmp:
            if escolha:
                vtt = fonte.baixar_legenda(video.url, escolha.chave, escolha.automatica, Path(tmp))
                segmentos = legenda.ler_vtt(vtt.read_text(encoding="utf-8"))
                decisao = args.texto
                if decisao == "perguntar":
                    _mostrar_legenda(escolha, segmentos, video.duracao_s)
                    decisao = _perguntar()
                if decisao == "legenda":
                    resultado = legenda.para_resultado(segmentos, video.url, video.duracao_s, lang, escolha)
                    return destino, video.para_json(), resultado
            print("Baixando o áudio...")
            audio = fonte.baixar_audio(video.url, Path(tmp))
            idioma = None if args.lang == "auto" else args.lang
            resultado = _whisper(audio, args, idioma)
            resultado.fonte = video.url
            # o áudio some junto com a pasta temporária: só o texto fica
            return destino, video.para_json(), resultado
    except DownloadError as e:
        raise Erro(f"YouTube: {e}") from e


def _do_gravacao(args, pasta_audio: Path):
    """Pasta de gravação (sistema.wav e/ou microfone.wav) -> um texto só, com `falante`."""
    faixas = gravacao.faixas_na_pasta(pasta_audio)
    if not faixas:
        raise Erro(f"não achei sistema.wav nem microfone.wav em {pasta_audio}")
    idioma = None if args.lang == "auto" else args.lang
    args_faixa = argparse.Namespace(**{**vars(args), "em_gravacao": True})
    resultados = {}
    for nome, caminho in faixas.items():
        print(f"Faixa '{nome}'...")
        resultados[nome] = _whisper(caminho, args_faixa, idioma)
    resultado = gravacao.juntar_faixas(resultados)
    dados = {"tipo": "gravacao", "titulo": f"Gravação {pasta_audio.name}", "data": pasta_audio.name,
             "duracao_s": resultado.duracao_s, "faixas": list(faixas), "falantes": gravacao.FALANTES}
    return args.saida / pasta.slug(f"gravacao {pasta_audio.name}"), dados, resultado


def _apagar_audio(args, pasta_audio: Path) -> None:
    """Depois que o texto foi gravado: pergunta se apaga os .wav (padrão: guardar)."""
    arquivos = list(gravacao.faixas_na_pasta(pasta_audio).values())
    decisao = args.apagar_audio
    if decisao is None:
        if not sys.stdin.isatty():
            print(f"Áudio guardado em {pasta_audio} (use --apagar-audio para apagar).")
            return
        try:
            decisao = input("Apagar os áudios gravados? [s/N] ").strip().lower() in ("s", "sim", "y", "yes")
        except EOFError:
            decisao = False
    if not decisao:
        print(f"Áudio guardado em {pasta_audio}.")
        return
    for arquivo in arquivos:
        arquivo.unlink()
    try:
        pasta_audio.rmdir()  # só se ficou vazia: nunca apaga o que não é nosso
    except OSError:
        pass
    print("Áudio apagado.")


def _do_arquivo(args):
    caminho = Path(args.entrada)
    if caminho.is_dir():
        return _do_gravacao(args, caminho)
    if not caminho.is_file():
        raise Erro(f"arquivo não encontrado: {caminho}")
    print(f"Transcrevendo {caminho.name}...")
    resultado = _whisper(caminho, args, None if args.lang == "auto" else args.lang)
    dados = {"tipo": "arquivo", "caminho": str(caminho.resolve()), "titulo": caminho.stem,
             "duracao_s": resultado.duracao_s}
    return args.saida / pasta.slug(caminho.stem), dados, resultado


# --- Visual (perfil aula) ----------------------------------------------------

def _progresso_visual(fase):
    ultimo = [-1]

    def mostrar(atual, total):
        porcento = int(atual / total * 100) if total else 100
        if porcento != ultimo[0]:  # só quando o número muda: um quadro por segundo seria muito texto
            ultimo[0] = porcento
            print(f"\r  {fase} {porcento:3d}%", end="", flush=True)
    return mostrar


def _mostrar_palpite(ind: dict, perfil: str, motivo: str) -> None:
    print("\nO que a tela mostra:")
    print(f"  {ind['trocas']} trocas de tela ({ind['trocas_por_min']} por minuto), "
          f"uma a cada {_relogio(ind['tempo_medio_s'])} em média")
    print(f"  {ind['palavras_por_tela']} palavras por tela (lidas em poucas amostras)")
    print(f"  formato: {'vertical' if ind['vertical'] else 'horizontal'}")
    print(f"Palpite: {perfil} ({motivo})")
    if perfil == "corte":
        print("  O perfil 'corte' (vídeo curto, com cortes rápidos) ainda não existe: só aula por enquanto.")


def _confirmar_aula(perfil: str) -> bool:
    padrao = perfil == "aula"
    try:
        resposta = input(f"Extrair os slides com OCR? [{'S/n' if padrao else 's/N'}] ").strip().lower()
    except EOFError:
        raise Erro("cancelado")
    return padrao if not resposta else resposta in ("s", "sim", "y", "yes")


def _lang_visual(args, dados_fonte) -> str | None:
    if args.lang != "auto":
        return args.lang
    return (dados_fonte.get("idioma") or "")[:2] or None


def _fazer_visual(args, destino: Path, dados_fonte: dict) -> None:
    idiomas = ocr.idiomas_para(_lang_visual(args, dados_fonte))
    exe = ocr.verificar(idiomas)  # antes de baixar qualquer coisa
    with tempfile.TemporaryDirectory(prefix="vatty-visual-") as tmp:
        if fonte.eh_url(args.entrada):
            print("\nBaixando o vídeo (só a imagem, até 720p)...")
            video = fonte.baixar_video(dados_fonte.get("url") or args.entrada, Path(tmp))
        else:
            video = Path(args.entrada)
        print("Procurando as trocas de tela...")
        deteccao = aula.detectar(video, progresso=_progresso_visual("tela"))
        print()
        if not deteccao.slides:
            raise Erro("não achei nenhuma tela no vídeo")
        if deteccao.truncado:
            print(f"Aviso: passou de {visual.MAX_SLIDES} trocas de tela; só as primeiras ficam.")
        if args.visual == "auto":
            ind, (perfil, motivo) = aula.palpite(video, deteccao, tmp, idiomas=idiomas, exe=exe)
            _mostrar_palpite(ind, perfil, motivo)
            if not _confirmar_aula(perfil):
                print("Visual pulado.")
                return
        print(f"Lendo o texto de {len(deteccao.slides)} slide(s) com o Tesseract...")
        dados = aula.montar(video, deteccao, destino, idiomas=idiomas, exe=exe, progresso=_progresso_visual("slides"),
                            parametros={"intervalo_s": visual.INTERVALO_S, "limiar_mudanca": visual.LIMIAR_MUDANCA,
                                        "max_slides": visual.MAX_SLIDES, "escolha": args.visual})
        print()
    caminho = pasta.gravar_visual(destino, dados)
    print(f"Visual: {len(dados['eventos'])} slide(s) em {caminho.parent} (visual.json e frames/).")


def _visual(args, destino: Path, dados_fonte: dict) -> int:
    """Roda o visual depois do texto. Se falhar, o texto já está salvo: avisa e sai com código 1."""
    try:
        from yt_dlp.utils import DownloadError
    except ImportError:  # pragma: no cover
        DownloadError = RuntimeError
    try:
        _fazer_visual(args, destino, dados_fonte)
    except (Erro, ocr.ErroOcr, quadros.ErroDeVideo, FfmpegAusente, FileNotFoundError, RuntimeError, DownloadError) as e:
        print(f"\nErro no visual: {e}\nO texto já está salvo em {destino}.", file=sys.stderr)
        return 1
    return 0


# --- Gravação ----------------------------------------------------------------

def _argumentos_gravar(argv):
    p = argparse.ArgumentParser(
        prog="vatty gravar",
        description="Grava o áudio do PC (Windows) até Ctrl+C. Com --mic grava também o microfone, "
                    "em outra faixa. Cada faixa vira um .wav em gravacoes/AAAA-MM-DD_HH-MM/.")
    p.add_argument("--mic", action="store_true", help="grava também o microfone (faixa separada: 'eu')")
    p.add_argument("--transcrever", action="store_true", help="ao parar, já transcreve e cria a pasta do vídeo")
    p.add_argument("--duracao", type=float, metavar="SEGUNDOS", help="para sozinho depois desse tempo (bom para testar: 5)")
    p.add_argument("--gravacoes", type=Path, default=Path("gravacoes"), help="onde guardar os .wav (padrão: gravacoes/)")
    _opcoes_comuns(p)
    return p.parse_args(argv)


def _barra(pico: float) -> str:
    cheio = min(8, int(pico * 24))
    return "#" * cheio + "." * (8 - cheio)


def _mostrar_gravando(decorrido: float, niveis: dict) -> None:
    faixas = "  ".join(f"{nome} [{_barra(p)}]" for nome, p in niveis.items())
    print(f"\r  {_relogio(decorrido)}  {faixas}  ", end="", flush=True)


def _main_gravar(argv) -> int:
    args = _argumentos_gravar(argv)
    print(AVISO_CONSENTIMENTO)
    try:
        entradas = gravacao.abrir_entradas(microfone=args.mic)
        for e in entradas:
            print(f"  {e.nome}: {getattr(e, 'descricao', '')}")
        destino = gravacao.pasta_nova(args.gravacoes, time.strftime("%Y-%m-%d_%H-%M"))
        print("Gravando. Ctrl+C para parar." if args.duracao is None else f"Gravando por {args.duracao:g}s.")
        resultado = gravacao.gravar(entradas, destino, duracao_max=args.duracao, progresso=_mostrar_gravando)
    except gravacao.ErroGravacao as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    print(f"\nGravado: {_relogio(resultado.duracao_s)} em {resultado.pasta}")
    for nome in resultado.faixas_mudas():
        print(f"Aviso: a faixa '{nome}' ficou quase muda. Era pra ter som nela?")
    if not args.transcrever:
        print(f"Para transcrever depois: vatty {resultado.pasta}")
        return 0
    args.entrada = str(resultado.pasta)
    return _executar(args)


# --- Entrada principal -------------------------------------------------------

def _executar(args) -> int:
    """Produz a pasta do vídeo para `args.entrada` (URL, arquivo ou pasta de gravação)."""
    comeco = time.perf_counter()
    visual_pedido = getattr(args, "visual", "nenhum")
    if visual_pedido == "auto" and not sys.stdin.isatty():
        print("\nErro: --visual auto precisa de um terminal para perguntar. Use --visual aula ou --visual nenhum.",
              file=sys.stderr)
        return 1
    try:
        destino, dados_fonte, resultado = (_do_youtube if fonte.eh_url(args.entrada) else _do_arquivo)(args)
    except Erro as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    txt = pasta.gravar(destino, dados_fonte, resultado)
    gasto = time.perf_counter() - comeco
    print(f"Pronto em {_relogio(gasto)} (texto de {resultado.origem}, {resultado.duracao_s:.0f}s de áudio): {txt.parent}")
    if dados_fonte.get("tipo") == "gravacao":
        if visual_pedido != "nenhum":
            print("Aviso: --visual não se aplica a uma gravação de áudio.")
        _apagar_audio(args, Path(args.entrada))
    elif visual_pedido != "nenhum":
        return _visual(args, destino, dados_fonte)
    return 0


def main(argv=None) -> int:
    # Título com emoji num terminal cp1252 não pode derrubar o programa.
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "gravar":
        return _main_gravar(argv[1:])
    return _executar(_argumentos(argv))


if __name__ == "__main__":
    sys.exit(main())
