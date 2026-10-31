"""CLI fina: traduz argumentos, chama as camadas e pergunta ao usuário. `vatty <url-ou-arquivo>`."""

import argparse
import json
import os
import sys
import tempfile
import textwrap
import time
from pathlib import Path

from . import acervo, app, aula, ata, audio, cartoes as _cartoes, traducao as _traducao, diarizar, fonte, glossario, gravacao, legenda, motor, ocr, pasta, perfis, preprocessar, quadros, slides as _slides, srt, tela, visual, vozes
from .audio import ErroDeDecodificacao, FfmpegAusente

PREPROCESSAR_ESCOLHAS = ("perguntar", "sim", "nao")
TEXTO_ESCOLHAS = ("perguntar", "legenda", "whisper")
VISUAL_ESCOLHAS = ("nenhum", "auto", "aula", "app")

AVISO_CONSENTIMENTO = ("Aviso: gravar uma conversa sem avisar os outros participantes pode ser ilegal "
                       "onde você mora. Avise quem estiver na gravação.")
AVISO_TELA = ("Aviso: a tela também vai ser gravada. Ela pode mostrar senha, notificação e conversa de outras "
              "pessoas; feche o que não deve aparecer. A imagem fica só neste PC.")


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
    p.add_argument("--glossario", type=Path, metavar="ARQUIVO",
                   help="arquivo com correções 'errado = certo', aplicadas ao texto depois de transcrever "
                        f"(sem a flag, usa {glossario.arquivo_padrao()} se existir)")
    p.add_argument("--saida", type=Path, default=Path("transcricoes"), help="pasta de saída (padrão: transcricoes/)")
    p.add_argument("--cookies-navegador", dest="cookies_navegador", choices=fonte.NAVEGADORES, metavar="NAVEGADOR",
                   help="usa o login desse navegador (firefox, edge, chrome...) quando o YouTube pede para provar que "
                        "não é robô. O Firefox é o mais garantido no Windows")
    p.add_argument("--apagar-audio", dest="apagar_audio", action="store_true", default=None,
                   help="gravação: apaga os .wav depois de transcrever, sem perguntar")
    p.add_argument("--manter-audio", dest="apagar_audio", action="store_false", default=None,
                   help="gravação: guarda os .wav depois de transcrever, sem perguntar")
    p.add_argument("--manter-tela", dest="manter_tela", action="store_true",
                   help="gravação com tela: guarda o tela.mp4 depois de tirar os slides (padrão: apagar)")
    p.add_argument("--horario-por-palavra", dest="horario_por_palavra", choices=("auto", "sim", "nao"), default="auto",
                   help="ajusta o início e o fim de cada trecho à primeira e à última palavra (gasta mais tempo). "
                        "'auto' (padrão) liga só em gravação; 'sim' liga sempre; 'nao' desliga")
    p.add_argument("--vad-silencio-ms", dest="vad_silencio_ms", type=int, default=None, metavar="MS",
                   help="experimental: pausa mínima (ms) que corta a fala no filtro de voz do Whisper. "
                        "Sem a opção, fica o padrão do faster-whisper (160)")
    p.add_argument("--preprocessar", choices=PREPROCESSAR_ESCOLHAS, default="perguntar",
                   help="antes do Whisper: corta o ronco grave, tira o ruído e sobe a voz baixa (áudio de WhatsApp, "
                        "celular). 'perguntar' (padrão) mede o áudio e só pergunta se algo estiver ruim; "
                        "'sim' aplica sempre; 'nao' não mede nem mexe. Piora sussurro e áudio com música "
                        "de fundo: nesses casos, 'nao'")
    p.add_argument("--falantes", type=_tipo_falantes, default="nao", metavar="nao|auto|N|perfis",
                   help="separa quem falou (precisa do sherpa-onnx: pip install -e \".[falantes]\"). 'auto' descobre as "
                        "pessoas sozinha; um número (ex.: 5) fixa quantas são e costuma acertar mais; 'perfis' só "
                        "reconhece quem tem perfil cadastrado (vatty perfil --help). Em gravação, só o som do PC. "
                        "Padrão: nao")
    p.add_argument("--perfis", nargs="+", default=None, metavar="NOME",
                   help="com --falantes: usa só esses perfis de voz ('nenhum' não usa nenhum). Sem a opção, usa todos")
    p.add_argument("--ruido-modelo", dest="ruido_modelo", default=None, metavar="NOME_OU_ARQUIVO",
                   help=f"modelo de ruído do arnndn: {', '.join(preprocessar.MODELOS_RUIDO)} (padrão: "
                        f"{preprocessar.MODELO_RUIDO_PADRAO}, baixado na primeira vez) ou o caminho de um .rnnn")


def _tipo_falantes(valor: str) -> str:
    valor = valor.strip().lower()
    if valor in ("nao", "auto", "perfis") or (valor.isdigit() and int(valor) >= 1):
        return valor
    raise argparse.ArgumentTypeError("use nao, auto, perfis ou o número de pessoas (ex.: 5)")


def _argumentos(argv):
    p = argparse.ArgumentParser(prog="vatty", description="Transcreve um vídeo de uma URL (YouTube, TikTok...), um arquivo de áudio/vídeo "
                                "ou uma gravação. Para gravar o áudio do PC: vatty gravar --help.")
    p.add_argument("entrada", help="URL de vídeo (YouTube, TikTok...), arquivo (.opus, .ogg, .mp3, .m4a, .wav, .mp4...) "
                                   "ou pasta de uma gravação (gravacoes/AAAA-MM-DD_HH-MM)")
    _opcoes_comuns(p)
    p.add_argument("--texto", choices=TEXTO_ESCOLHAS, default="perguntar",
                   help="URL com legenda: usar a legenda, o Whisper, ou perguntar depois de mostrar trechos (padrão)")
    p.add_argument("--visual", choices=VISUAL_ESCOLHAS, default="nenhum",
                   help="extrai também o que aparece na tela (OCR com Tesseract). 'aula': os slides que ficam parados; "
                        "'app': cada mudança da tela, aviso rápido e espera (para quem testa um programa); "
                        "'auto' mostra um palpite e pergunta (aula); 'nenhum' (padrão) só o texto. Precisa de vídeo e do Tesseract")
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


def _separar_falantes(caminho, resultado, args, criar_vozes=None, carregar=audio.carregar) -> None:
    """
    Roda a separação de falantes sobre o áudio e põe `pessoa` nos segmentos. Qualquer falha vira aviso:
    o texto já está pronto e não pode se perder por causa disso.
    """
    pedido = getattr(args, "falantes", "nao")
    if pedido == "nao":
        return
    modo, n_falantes = ("perfis", None) if pedido == "perfis" else ("agrupar", None if pedido == "auto" else int(pedido))
    try:
        voz = (criar_vozes or vozes.Vozes)()
        escolhidos = getattr(args, "perfis", None)
        if escolhidos and [e.lower() for e in escolhidos] == ["nenhum"]:
            cadastrados, avisos = {}, []
        else:
            cadastrados, avisos = perfis.carregar(voz.nome, so_nomes=escolhidos)
        for aviso in avisos:
            print(f"Aviso: {aviso}")
        if modo == "perfis" and not cadastrados:
            raise ValueError("--falantes perfis precisa de pelo menos um perfil (vatty perfil criar --help).")
        print("Separando os falantes..." if modo == "agrupar" else "Reconhecendo as vozes cadastradas...")
        amostras, _ = carregar(caminho)
        separacao = diarizar.separar(amostras, voz, modo, n_falantes=n_falantes, perfis=cadastrados)
    except (vozes.VozesIndisponiveis, ValueError, FileNotFoundError, FfmpegAusente, ErroDeDecodificacao) as e:
        print(f"Aviso: sem separação de falantes: {e}")
        return
    resultado.segmentos = diarizar.atribuir(resultado.segmentos, separacao.turnos)
    resultado.falantes = {**separacao.info, "turnos": [
        {"inicio": round(t.inicio, 2), "fim": round(t.fim, 2), "pessoa": t.pessoa} for t in separacao.turnos]}
    for p in separacao.info["pessoas"]:
        print(f"  {p['pessoa']}: {_relogio(p['fala_s'])}{' (perfil)' if p['perfil'] else ''}")
    if not separacao.turnos:
        print("Aviso: não achei fala para separar.")


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

def _mostrar_legenda(escolha, segmentos, duracao, plataforma="YouTube") -> None:
    tipo = f"automática do {plataforma}" if escolha.automatica else "manual (escrita pelo autor)"
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

DICA_IMITAR_NAVEGADOR = ('Dica: este site exige imitar um navegador. Atualize as dependências: '
                         'pip install -e . (ou pip install -U "yt-dlp[default,curl-cffi]")')


DICA_LOGIN = ('Dica: o YouTube pediu para provar que não é robô. Use o login do seu navegador: '
              '--cookies-navegador firefox (ou edge, chrome...; no painel, "Entrar como você"). O Firefox é o mais '
              'garantido: o Chrome no Windows protege os cookies. Atualizar o yt-dlp também ajuda: '
              'pip install -U "yt-dlp[default,curl-cffi]"')


def _erro_download(e) -> str:
    texto = str(e)
    if "mpersonat" in texto or "Unexpected response from webpage request" in texto:
        texto += f"\n{DICA_IMITAR_NAVEGADOR}"
    if fonte.eh_bloqueio(texto):
        texto += f"\n{DICA_LOGIN}\n({fonte.diagnostico()})"
    return f"não consegui ler/baixar o vídeo: {texto}"


class _TentarIPv4(Exception):
    """O YouTube bloqueou: vale uma segunda tentativa forçando IPv4."""


def _do_youtube(args):
    """Lê a URL; se o YouTube pedir "prove que não é robô", tenta uma vez de novo por IPv4."""
    try:
        return _ler_url(args)
    except _TentarIPv4:
        _fechar_sessao(args)
        os.environ[fonte.VAR_IPV4] = "1"
        print("O YouTube desconfiou do acesso. Tentando de novo por IPv4...")
        return _ler_url(args)


def _ler_url(args):
    """
    URL de vídeo (YouTube, TikTok, o que o yt-dlp suportar) -> (pasta, fonte.json, resultado).
    Legenda primeiro, Whisper se o usuário quiser. A página é lida UMA vez (`fonte.Sessao`): o TikTok
    recusa a segunda leitura, então o áudio sai do mesmo `info` e da mesma instância.
    """
    try:
        from yt_dlp.utils import DownloadError
    except ImportError:  # pragma: no cover
        DownloadError = RuntimeError

    sessao = fonte.Sessao(args.entrada)
    args.sessao = sessao  # o --visual reaproveita (ver _fazer_visual)
    try:
        print("Lendo o vídeo...")
        video = sessao.inspecionar()
        print(f"{video.plataforma}: {video.titulo} ({_relogio(video.duracao_s)})")
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
                vtt = sessao.baixar_legenda(escolha.chave, escolha.automatica, Path(tmp))
                segmentos = legenda.ler_vtt(vtt.read_text(encoding="utf-8"))
                decisao = args.texto
                if decisao == "perguntar":
                    _mostrar_legenda(escolha, segmentos, video.duracao_s, video.plataforma)
                    decisao = _perguntar()
                if decisao == "legenda":
                    if getattr(args, "falantes", "nao") != "nao":
                        print("Aviso: com a legenda não há áudio baixado; para separar falantes use --texto whisper.")
                    resultado = legenda.para_resultado(segmentos, video.url, video.duracao_s, lang, escolha)
                    return destino, video.para_json(), resultado
            print("Baixando o áudio...")
            arquivo_audio = sessao.baixar_audio(Path(tmp))
            idioma = None if args.lang == "auto" else args.lang
            resultado = _whisper(arquivo_audio, args, idioma)
            _separar_falantes(arquivo_audio, resultado, args)
            resultado.fonte = video.url
            # o áudio some junto com a pasta temporária: só o texto fica
            return destino, video.para_json(), resultado
    except DownloadError as e:
        if fonte.eh_bloqueio(str(e)) and not os.environ.get(fonte.VAR_IPV4):
            raise _TentarIPv4() from e
        raise Erro(_erro_download(e)) from e


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
        if nome == "sistema":  # o microfone já é uma pessoa só ("eu")
            _separar_falantes(caminho, resultados[nome], args)
    if getattr(args, "falantes", "nao") != "nao" and "sistema" not in faixas:
        print("Aviso: --falantes só se aplica ao som do PC (sistema.wav); esta gravação não tem essa faixa.")
    resultado = gravacao.juntar_faixas(resultados)
    dados = {"tipo": "gravacao", "titulo": f"Gravação {pasta_audio.name}", "data": pasta_audio.name,
             "duracao_s": resultado.duracao_s, "faixas": list(faixas), "falantes": gravacao.FALANTES}
    metadados = gravacao.ler_metadados(pasta_audio)  # só existe em gravação com tela
    dados.update({k: metadados[k] for k in ("inicios", "tela") if k in metadados})
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
    metadados = pasta_audio / gravacao.METADADOS
    if metadados.is_file() and not (pasta_audio / tela.ARQUIVO).exists():
        metadados.unlink()  # sem áudio e sem tela, os horários de início não servem para nada
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
    _separar_falantes(caminho, resultado, args)
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


def _fazer_visual(args, destino: Path, dados_fonte: dict, video=None, deslocamento=None) -> None:
    idiomas = ocr.idiomas_para(_lang_visual(args, dados_fonte))
    exe = ocr.verificar(idiomas)  # antes de baixar qualquer coisa
    with tempfile.TemporaryDirectory(prefix="vatty-visual-") as tmp:
        if video is None and fonte.eh_url(args.entrada):
            print("\nBaixando o vídeo (só a imagem, até 720p)...")
            sessao = getattr(args, "sessao", None)  # a mesma leitura do texto: o TikTok recusa a segunda
            video = (sessao.baixar_video(Path(tmp)) if sessao
                     else fonte.baixar_video(dados_fonte.get("url") or args.entrada, Path(tmp)))
        elif video is None:  # arquivo local; com `video`, é a tela de uma gravação
            video = Path(args.entrada)
        if args.visual == "app":
            print("Procurando as mudanças da tela (perfil app)...")
            dados = app.montar(video, destino, idiomas=idiomas, exe=exe,
                               progresso_tela=_progresso_visual("tela"), progresso_leitura=_progresso_visual("leitura"),
                               parametros={"intervalo_s": app.INTERVALO_S, "limiar_mudanca": app.LIMIAR,
                                           "estaveis": app.ESTAVEIS, "max_eventos": app.MAX_EVENTOS})
            print()
            return _gravar_visual(destino, dados, deslocamento, "evento(s)", dados_fonte.get("duracao_s"))
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
    _gravar_visual(destino, dados, deslocamento, "slide(s)", dados_fonte.get("duracao_s"))


def _gravar_visual(destino: Path, dados: dict, deslocamento, nome: str, duracao=None) -> None:
    if deslocamento is not None:  # gravação: os horários da tela vão para a linha do tempo do áudio
        dados = tela.sincronizar(dados, deslocamento, duracao)
    caminho = pasta.gravar_visual(destino, dados)
    print(f"Visual: {len(dados['eventos'])} {nome} em {caminho.parent} (visual.json e frames/).")


def _visual(args, destino: Path, dados_fonte: dict, video=None, deslocamento=None) -> int:
    """Roda o visual depois do texto. Se falhar, o texto já está salvo: avisa e sai com código 1."""
    try:
        from yt_dlp.utils import DownloadError
    except ImportError:  # pragma: no cover
        DownloadError = RuntimeError
    try:
        _fazer_visual(args, destino, dados_fonte, video, deslocamento)
    except (Erro, ocr.ErroOcr, quadros.ErroDeVideo, FfmpegAusente, FileNotFoundError, RuntimeError, DownloadError) as e:
        print(f"\nErro no visual: {e}\nO texto já está salvo em {destino}.", file=sys.stderr)
        return 1
    return 0


# --- Gravação ----------------------------------------------------------------

def _argumentos_gravar(argv):
    p = argparse.ArgumentParser(
        prog="vatty gravar",
        description="Grava o áudio do PC (Windows ou Linux) até Ctrl+C. Com --mic grava também o microfone, "
                    "em outra faixa. Cada faixa vira um .wav em gravacoes/AAAA-MM-DD_HH-MM/.")
    p.add_argument("--mic", action="store_true", help="grava também o microfone (faixa separada: 'eu')")
    p.add_argument("--transcrever", action="store_true", help="ao parar, já transcreve e cria a pasta do vídeo")
    p.add_argument("--tela", action="store_true",
                   help="grava também a tela inteira (ffmpeg, 2 quadros por segundo, sem som) em tela.mp4. Com "
                        "--transcrever, os slides vão para o visual.json e o tela.mp4 é apagado (salvo --manter-tela)")
    p.add_argument("--tela-janela", dest="tela_janela", metavar="TÍTULO",
                   help="grava só a janela com esse título exato, em vez da tela inteira (já liga --tela)")
    p.add_argument("--tela-fps", dest="tela_fps", type=int, metavar="N",
                   help=f"quadros por segundo da tela (padrão: {tela.FPS_TELA} na tela inteira, {tela.FPS_JANELA} numa janela)")
    p.add_argument("--visual", choices=("app", "aula"), default="app",
                   help="com --tela: 'app' (padrão) registra cada mudança da tela, aviso rápido e espera, para "
                        "testar um programa; 'aula' só os slides que ficam parados")
    p.add_argument("--duracao", type=float, metavar="SEGUNDOS", help="para sozinho depois desse tempo (bom para testar: 5)")
    p.add_argument("--gravacoes", type=Path, default=Path("gravacoes"), help="onde guardar os .wav (padrão: gravacoes/)")
    p.add_argument("--parar-com", dest="parar_com", type=Path, metavar="ARQUIVO",
                   help="para a gravação quando este arquivo aparecer (é como a interface aperta o 'Parar')")
    _opcoes_comuns(p)
    return p.parse_args(argv)


def _barra(pico: float) -> str:
    cheio = min(8, int(pico * 24))
    return "#" * cheio + "." * (8 - cheio)


def _mostrar_gravando(decorrido: float, niveis: dict) -> None:
    faixas = "  ".join(f"{nome} [{_barra(p)}]" for nome, p in niveis.items())
    print(f"\r  {_relogio(decorrido)}  {faixas}  ", end="", flush=True)


def _desfazer_tela(captura, destino: Path) -> None:
    """A gravação não começou: para o ffmpeg (se abriu) e não deixa pasta nem vídeo pela metade."""
    if captura is not None:
        captura.parar()
    (destino / tela.ARQUIVO).unlink(missing_ok=True)
    try:
        destino.rmdir()
    except OSError:
        pass


def _main_gravar(argv) -> int:
    args = _argumentos_gravar(argv)
    com_tela = args.tela or args.tela_janela is not None
    print(AVISO_CONSENTIMENTO)
    if com_tela:
        print(AVISO_TELA)
    destino = gravacao.pasta_nova(args.gravacoes, time.strftime("%Y-%m-%d_%H-%M"))
    captura = None
    try:
        if com_tela:
            # A tela abre antes do áudio: o ffmpeg demora um pouco para gravar o primeiro quadro,
            # e o áudio aberto antes ficaria acumulando essa espera.
            destino.mkdir(parents=True)
            captura = tela.abrir(destino / tela.ARQUIVO, janela=args.tela_janela, fps=args.tela_fps)
            print(f"  tela: {args.tela_janela or 'tela inteira'} ({captura.motor}, até {captura.fps} quadros por segundo)")
            if captura.aviso:
                print(f"Aviso: {captura.aviso}")
        entradas = gravacao.abrir_entradas(microfone=args.mic)
        for e in entradas:
            print(f"  {e.nome}: {getattr(e, 'descricao', '')}")
        print("Gravando. Ctrl+C para parar." if args.duracao is None else f"Gravando por {args.duracao:g}s.")
        parar = (lambda: args.parar_com.exists()) if args.parar_com else None
        resultado = gravacao.gravar(entradas, destino, duracao_max=args.duracao, progresso=_mostrar_gravando, parar=parar)
    except (gravacao.ErroGravacao, tela.ErroTela) as e:
        if com_tela:
            _desfazer_tela(captura, destino)
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    except BaseException:
        if captura is not None:
            captura.parar()  # nunca deixa o ffmpeg gravando sozinho
        raise
    print(f"\nGravado: {_relogio(resultado.duracao_s)} em {resultado.pasta}")
    for nome in resultado.faixas_mudas():
        print(f"Aviso: a faixa '{nome}' ficou quase muda. Era pra ter som nela?")
    if captura is not None:
        _fechar_tela(captura, resultado, args.tela_janela)
    if not args.transcrever:
        print(f"Para transcrever depois: vatty {resultado.pasta}" + (f" --visual {args.visual}" if com_tela else ""))
        return 0
    args.entrada = str(resultado.pasta)
    if not com_tela:
        args.visual = "nenhum"
    return _executar(args)


def _fechar_tela(captura, resultado, janela) -> None:
    """Para o ffmpeg e registra no gravacao.json o horário real de início de cada faixa."""
    if not captura.parar():
        print("Aviso: a gravação da tela parou antes do fim (a janela foi fechada?). O que foi gravado fica.")
    if captura.inicio_aproximado:
        print("Aviso: o ffmpeg não disse quando gravou o primeiro quadro; os horários dos slides podem errar uns segundos.")
    inicios = {nome: resultado.inicio for nome in resultado.faixas}
    inicios["tela"] = captura.inicio
    gravacao.salvar_metadados(resultado.pasta, {
        "inicios": inicios,
        "tela": {"arquivo": tela.ARQUIVO, "alvo": janela or "tela inteira", "motor": captura.motor, "fps": captura.fps,
                 "inicio_aproximado": captura.inicio_aproximado},
    })


# --- Entrada principal -------------------------------------------------------

def _executar(args) -> int:
    """Produz a pasta do vídeo para `args.entrada` (URL, arquivo ou pasta de gravação)."""
    if getattr(args, "cookies_navegador", None):
        os.environ[fonte.VAR_NAVEGADOR] = args.cookies_navegador  # a fonte lê daqui
    comeco = time.perf_counter()
    visual_pedido = getattr(args, "visual", "nenhum")
    if visual_pedido == "auto" and not sys.stdin.isatty():
        print("\nErro: --visual auto precisa de um terminal para perguntar. Use --visual aula ou --visual nenhum.",
              file=sys.stderr)
        return 1
    try:
        destino, dados_fonte, resultado = (_do_youtube if fonte.eh_url(args.entrada) else _do_arquivo)(args)
    except Erro as e:
        _fechar_sessao(args)
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    try:
        return _concluir(args, comeco, visual_pedido, destino, dados_fonte, resultado)
    finally:
        _fechar_sessao(args)


def _fechar_sessao(args) -> None:
    sessao = getattr(args, "sessao", None)
    if sessao is not None:
        sessao.fechar()


def _aplicar_glossario(resultado, arquivo) -> dict:
    """Corrige o texto do resultado e registra o que foi trocado (nada, se nada casou)."""
    if arquivo is not None and not Path(arquivo).is_file():
        raise glossario.GlossarioErro(f"Não achei o glossário {arquivo}.")
    arquivo = arquivo or glossario.arquivo_padrao()
    if not Path(arquivo).is_file():
        return {}  # o glossário padrão é opcional
    regras = glossario.ler(Path(arquivo).read_text(encoding="utf-8"))
    resultado.segmentos, feitas = glossario.aplicar(resultado.segmentos, regras)
    if feitas:
        acumulado = dict(resultado.glossario or {})  # `vatty corrigir` de novo soma ao que já foi feito
        for k, v in feitas.items():
            acumulado[k] = acumulado.get(k, 0) + v
        resultado.glossario = acumulado
        print(f"Glossário: {sum(feitas.values())} correção(ões) em {len(feitas)} termo(s).")
    return feitas


def _concluir(args, comeco, visual_pedido, destino, dados_fonte, resultado) -> int:
    try:
        _aplicar_glossario(resultado, getattr(args, "glossario", None))
    except glossario.GlossarioErro as e:
        print(f"Aviso: {e} O texto sai sem correções.", file=sys.stderr)
    txt = pasta.gravar(destino, dados_fonte, resultado)
    gasto = time.perf_counter() - comeco
    print(f"Pronto em {_relogio(gasto)} (texto de {resultado.origem}, {resultado.duracao_s:.0f}s de áudio): {txt.parent}")
    if dados_fonte.get("tipo") == "gravacao":
        pasta_audio = Path(args.entrada)
        if _tela_da_gravacao(args, visual_pedido, destino, dados_fonte, pasta_audio):
            return 1  # a gravação fica inteira, para tentar o visual de novo
        _apagar_audio(args, pasta_audio)
    elif visual_pedido != "nenhum":
        return _visual(args, destino, dados_fonte)
    return 0


def _tela_da_gravacao(args, visual_pedido, destino: Path, dados_fonte: dict, pasta_audio: Path) -> int:
    """Gravação com tela.mp4: slides na linha do tempo do áudio, depois apaga a tela (salvo --manter-tela)."""
    video = pasta_audio / tela.ARQUIVO
    if not video.is_file():
        if visual_pedido != "nenhum":
            print("Aviso: --visual não se aplica a uma gravação só de áudio (sem tela.mp4).")
        return 0
    if visual_pedido == "nenhum":
        print(f"A tela ficou em {video} (para tirar os slides: vatty {pasta_audio} --visual aula).")
        return 0
    if _visual(args, destino, dados_fonte, video, tela.deslocamento(dados_fonte.get("inicios"))):
        print(f"A gravação (áudio e tela) ficou em {pasta_audio}. Para tentar de novo: "
              f"vatty {pasta_audio} --visual aula", file=sys.stderr)
        return 1
    if getattr(args, "manter_tela", False):
        print(f"Tela guardada em {video}.")
    else:
        video.unlink()
        print("Tela apagada (os slides ficaram no visual.json e em frames/).")
    return 0


# --- Perfis de voz -----------------------------------------------------------

def _argumentos_perfil(argv):
    p = argparse.ArgumentParser(
        prog="vatty perfil",
        description="Perfis de voz: a impressão de voz de quem consentiu em ser reconhecido. Guarda só o vetor, "
                    f"nunca o áudio, em {perfis.pasta_perfis()} (VATTY_PERFIS muda).")
    sub = p.add_subparsers(dest="comando", required=True)
    c = sub.add_parser("criar", help="cria o perfil de uma pessoa a partir de um áudio só dela falando (20 a 30 s)")
    c.add_argument("nome")
    c.add_argument("amostra", type=Path, help="áudio com SÓ essa pessoa falando, num lugar quieto")
    c.add_argument("--consentimento", action="store_true",
                   help="confirma que a pessoa foi avisada e concordou (sem isso, a Vatty pergunta)")
    c.add_argument("--substituir", action="store_true", help="refaz um perfil que já existe")
    sub.add_parser("listar", help="mostra os perfis cadastrados")
    a = sub.add_parser("apagar", help="apaga o perfil de uma pessoa")
    a.add_argument("nome")
    return p.parse_args(argv)


def _confirmar_consentimento() -> bool:
    if not sys.stdin.isatty():
        return False
    print(perfis.TEXTO_CONSENTIMENTO)
    try:
        return input("Confirma? [s/N] ").strip().lower() in ("s", "sim", "y", "yes")
    except EOFError:
        return False


def _main_perfil(argv, criar_vozes=None, carregar=audio.carregar) -> int:
    args = _argumentos_perfil(argv)
    try:
        if args.comando == "listar":
            lista = perfis.listar()
            if not lista:
                print("Nenhum perfil cadastrado.")
            for d in lista:
                print(f"{d['nome']}  (modelo {d['modelo_voz']}, consentimento em {d['consentimento']})")
        elif args.comando == "apagar":
            perfis.apagar(args.nome)
            print(f"Perfil '{args.nome}' apagado.")
        else:
            if not (args.consentimento or _confirmar_consentimento()):
                raise Erro("sem o consentimento da pessoa não se cria perfil de voz "
                           "(confirme com --consentimento ou respondendo 's' quando eu perguntar).")
            voz = (criar_vozes or vozes.Vozes)()
            amostras, _ = carregar(args.amostra)
            vetor, info = diarizar.vetor_de_perfil(amostras, voz)
            perfis.criar(args.nome, vetor, voz.nome, consentimento=True, info=info, substituir=args.substituir)
            print(f"Perfil '{args.nome}' criado ({info['fala_s']:.0f} s de fala, coerência {info['coerencia']}). "
                  "O áudio da amostra não foi guardado.")
    except (Erro, perfis.PerfilErro, ValueError, vozes.VozesIndisponiveis, FileNotFoundError, FfmpegAusente,
            ErroDeDecodificacao) as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    return 0


# --- Ata de reunião ----------------------------------------------------------

def _argumentos_ata(argv):
    p = argparse.ArgumentParser(
        prog="vatty ata",
        description="Monta o .docx/.pdf da ata que o Secretário escreveu (ata-*.md na pasta do vídeo). "
                    "Sem custo de tokens: o título, a data, a duração e os participantes vêm dos arquivos da pasta.")
    p.add_argument("pasta", type=Path, help="pasta do vídeo (transcricoes/<nome>)")
    p.add_argument("--arquivo", help="qual ata-*.md usar (padrão: a mais recente)")
    p.add_argument("--formato", nargs="+", choices=tuple(ata.FORMATOS), default=["docx"],
                   help="docx, pdf ou os dois (padrão: docx)")
    p.add_argument("--nomes", nargs="+", metavar="'Pessoa 1=Ana'",
                   help="troca os rótulos 'Pessoa N' pelos nomes (só no documento final)")
    p.add_argument("--titulo", help="título da ata (padrão: 'Ata: <título da fonte>')")
    return p.parse_args(argv)


def _nomes_guardados(pasta) -> dict:
    """Os nomes dados na interface (`nomes.json` na pasta do vídeo), se houver."""
    try:
        dados = json.loads((Path(pasta) / "nomes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in dados.items()} if isinstance(dados, dict) else {}


def _main_ata(argv) -> int:
    args = _argumentos_ata(argv)
    try:
        nomes = _nomes_guardados(args.pasta)
        nomes.update(ata.ler_nomes(args.nomes))  # o que vier na linha de comando manda sobre o guardado na interface
        arquivos = ata.gerar(args.pasta, args.arquivo, args.formato, nomes, args.titulo)
    except ata.AtaErro as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    for arquivo in arquivos:
        print(f"Ata pronta: {arquivo}")
    return 0


def _main_corrigir(argv) -> int:
    p = argparse.ArgumentParser(prog="vatty corrigir", description="Aplica o glossário numa pasta já transcrita "
                                "(refaz transcricao.json e transcricao.txt, sem transcrever de novo).")
    p.add_argument("pasta", type=Path)
    p.add_argument("--glossario", type=Path, metavar="ARQUIVO")
    args = p.parse_args(argv)
    try:
        dados_fonte, resultado = pasta.carregar(args.pasta)
        feitas = _aplicar_glossario(resultado, args.glossario)
    except (FileNotFoundError, glossario.GlossarioErro) as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    if not feitas:
        print("Nada para corrigir.")
        return 0
    pasta.gravar(args.pasta, dados_fonte, resultado)
    return 0


def _main_lote(argv) -> int:
    import subprocess
    from . import lote
    from .ui import runner
    p = argparse.ArgumentParser(prog="vatty lote", description="Transcreve vários links ou arquivos, um de cada vez. "
                                "A fonte é um arquivo .txt (uma entrada por linha; # comenta) ou o link de uma playlist ou canal.")
    p.add_argument("fonte")
    p.add_argument("--saida", type=Path, default=Path("transcricoes"))
    p.add_argument("--texto", choices=("legenda", "whisper"), default="whisper")
    p.add_argument("--visual", choices=("nenhum", "aula", "app"), default="nenhum")
    p.add_argument("--preprocessar", choices=("sim", "nao"), default="nao")
    p.add_argument("--falantes", type=_tipo_falantes, default="nao")
    p.add_argument("--lang", default=None)
    p.add_argument("--glossario", type=Path, default=None)
    p.add_argument("--relatorio", type=Path, default=None, help="onde guardar o relatório em JSON (padrão: <saida>/lote-relatorio.json)")
    args = p.parse_args(argv)
    opcoes = {"texto": args.texto, "visual": args.visual, "preprocessar": args.preprocessar,
              "falantes": args.falantes, "lang": args.lang or "", "glossario": str(args.glossario) if args.glossario else ""}
    try:
        entradas = lote.entradas_da_fonte(args.fonte)
    except Exception as e:  # LoteErro, ou o yt-dlp recusando a playlist
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    print(f"{len(entradas)} entrada(s). Uma de cada vez; um erro não para as outras.")

    def rodar_um(entrada):
        try:
            argv_item = runner.montar_argv(entrada, opcoes, args.saida)
        except runner.EntradaInvalida as e:
            return 1, str(e)
        r = subprocess.run(argv_item, env=runner.ambiente(), stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        saida = (r.stdout or "") + (r.stderr or "")
        erro = next((l for l in reversed(saida.splitlines()) if l.startswith("Erro")), "")
        return r.returncode, erro

    relatorio = lote.executar(entradas, rodar_um)
    args.saida.mkdir(parents=True, exist_ok=True)
    destino = lote.gravar_relatorio(relatorio, args.relatorio or args.saida / "lote-relatorio.json")
    print(lote.resumo(relatorio) + f"\nRelatório: {destino}")
    return 0 if not relatorio["falhas"] else 1


def _main_cartoes(argv) -> int:
    p = argparse.ArgumentParser(prog="vatty cartoes", description="Converte o cartoes-*.md do agente em .csv para o Anki.")
    p.add_argument("pasta", type=Path)
    p.add_argument("--arquivo", default=None, help="qual cartoes-*.md (se houver mais de um)")
    args = p.parse_args(argv)
    try:
        destino = _cartoes.gerar(args.pasta, args.arquivo)
    except _cartoes.CartoesErro as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    print(f"Cartões prontos: {destino}")
    return 0


def _main_traduzir(argv) -> int:
    p = argparse.ArgumentParser(prog="vatty traduzir", description="Tradução de legenda em duas etapas: 'preparar' escreve a "
                                "entrada do agente tradutor; 'montar' junta a tradução dele aos horários.")
    p.add_argument("etapa", choices=("preparar", "montar"))
    p.add_argument("pasta", type=Path)
    p.add_argument("--para", required=True, metavar="IDIOMA", help="código do idioma de destino (en, es, fr, pt-BR...)")
    p.add_argument("--formato", nargs="+", choices=srt.FORMATOS, default=["srt"], help="só em 'montar'")
    args = p.parse_args(argv)
    try:
        if args.etapa == "preparar":
            destino, n = _traducao.preparar(args.pasta, args.para)
            print(f"{n} bloco(s) em {destino}. Agora peça ao agente tradutor para traduzir.")
        else:
            for arquivo in _traducao.montar(args.pasta, args.para, args.formato):
                print(f"Legenda pronta: {arquivo}")
    except _traducao.TraducaoErro as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    return 0


def _main_perguntar(argv) -> int:
    p = argparse.ArgumentParser(prog="vatty perguntar", description="Escolhe, em todas as transcrições, os trechos mais ligados "
                                "a uma pergunta e grava o arquivo que o agente 'consulta' lê para responder.")
    p.add_argument("pergunta")
    p.add_argument("--raiz", type=Path, default=Path("transcricoes"))
    p.add_argument("--n", type=int, default=8, help="quantos trechos (padrão: 8)")
    args = p.parse_args(argv)
    trechos = acervo.selecionar(args.pergunta, args.raiz, args.n)
    if not trechos:
        print("Não achei trechos ligados a essa pergunta. Tente outras palavras.")
        return 0
    destino = acervo.gravar(args.raiz, args.pergunta, trechos)
    print(f"{len(trechos)} trecho(s) em {destino}. Agora peça ao agente consulta para responder.")
    return 0


def _main_legenda(argv) -> int:
    p = argparse.ArgumentParser(prog="vatty legenda", description="Gera legenda .srt/.vtt de uma pasta já transcrita.")
    p.add_argument("pasta")
    p.add_argument("--formato", nargs="+", choices=srt.FORMATOS, default=["srt"])
    args = p.parse_args(argv)
    try:
        arquivos = srt.gerar(args.pasta, args.formato)
    except srt.LegendaErro as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    for arquivo in arquivos:
        print(f"Legenda pronta: {arquivo}")
    return 0


def _main_slides(argv) -> int:
    p = argparse.ArgumentParser(prog="vatty slides", description="Transforma um vídeo ou gravação já transcrito em "
                                "slides: o print de cada tela na hora certa, com o que foi dito. Precisa do visual "
                                "(--visual aula/app, ou gravação com --tela).")
    p.add_argument("pasta")
    p.add_argument("--formato", nargs="+", choices=("html", "pdf"), default=["html"],
                   help="html (padrão: um arquivo só, abre no navegador) e/ou pdf (precisa do reportlab)")
    args = p.parse_args(argv)
    try:
        arquivos = _slides.gerar(args.pasta, args.formato)
    except _slides.ErroSlides as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    for arquivo in arquivos:
        print(f"Slides prontos: {arquivo}")
    return 0


def main(argv=None) -> int:
    # Título com emoji num terminal cp1252 não pode derrubar o programa. `line_buffering`: com a saída
    # redirecionada (arquivo, outro programa) o Python guarda o texto num buffer e parece travado.
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(errors="replace", line_buffering=True)
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "gravar":
        return _main_gravar(argv[1:])
    if argv and argv[0] == "ata":
        return _main_ata(argv[1:])
    if argv and argv[0] == "perfil":
        return _main_perfil(argv[1:])
    if argv and argv[0] == "cartoes":
        return _main_cartoes(argv[1:])
    if argv and argv[0] == "traduzir":
        return _main_traduzir(argv[1:])
    if argv and argv[0] == "perguntar":
        return _main_perguntar(argv[1:])
    if argv and argv[0] == "lote":
        return _main_lote(argv[1:])
    if argv and argv[0] == "ui":
        from .ui import app
        return app.main(argv[1:])
    if argv and argv[0] == "corrigir":
        return _main_corrigir(argv[1:])
    if argv and argv[0] == "slides":
        return _main_slides(argv[1:])
    if argv and argv[0] == "legenda":
        return _main_legenda(argv[1:])
    if argv and argv[0] == "verificar":
        from . import verificar
        return verificar.main(argv[1:])
    if argv and argv[0] == "apresentacao":
        from . import apresentacao
        return apresentacao.main(argv[1:])
    if argv and argv[0] == "juntar":
        from . import juntar
        return juntar.main(argv[1:])
    if argv and argv[0] == "buscar":
        from . import buscar
        return buscar.main(argv[1:])
    return _executar(_argumentos(argv))


if __name__ == "__main__":
    sys.exit(main())
