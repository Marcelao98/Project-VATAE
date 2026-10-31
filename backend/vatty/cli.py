"""
CLI fina: traduz argumentos, imprime e pergunta no terminal. `vatty <url-ou-arquivo>`.

O fluxo em si (legenda ou Whisper, visual, pasta do vídeo) mora em
`aplicacao.pipeline`; aqui só ficam o `Decisor` e o `Progresso` do terminal.
"""

import argparse
import sys
import textwrap
import time
from pathlib import Path

from . import gravacao, motor, preprocessar
from .aplicacao import ErroPipeline, Opcoes, PerguntaLegenda, PerguntaVisual, pipeline, relogio

PREPROCESSAR_ESCOLHAS = ("perguntar", "sim", "nao")
TEXTO_ESCOLHAS = ("perguntar", "legenda", "whisper")
VISUAL_ESCOLHAS = ("nenhum", "auto", "aula")

AVISO_CONSENTIMENTO = ("Aviso: gravar uma conversa sem avisar os outros participantes pode ser ilegal "
                       "onde você mora. Avise quem estiver na gravação.")


Erro = ErroPipeline  # nome antigo: erro para mostrar ao usuário e sair com código 1
_relogio = relogio


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


# --- O terminal como Decisor e Progresso -------------------------------------

def _ler(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except EOFError:
        raise Erro("cancelado")


class DecisorTerminal:
    """Pergunta no terminal. Sem terminal (`isatty` falso), o pipeline pede a opção explícita."""

    @property
    def interativo(self) -> bool:
        return sys.stdin.isatty()

    def legenda(self, pergunta: PerguntaLegenda) -> str:
        tipo = "automática do YouTube" if pergunta.automatica else "manual (escrita pelo autor)"
        ind = pergunta.indicadores
        print(f"\nLegenda {tipo}, '{pergunta.chave}':")
        print(f"  {ind['palavras']} palavras, cobre {ind['cobertura_pct']}% do vídeo")
        print(f"  pontuação: {ind['pontuacao_por_100']} sinais a cada 100 palavras")
        print(f"  palavras com maiúscula: {ind['maiusculas_pct']}%")
        print(f"  marcas como [Música]: {ind['marcas']}")
        print("\nTrechos:")
        for inicio, trecho in pergunta.amostras:
            corpo = textwrap.fill(trecho, width=96, initial_indent="    ", subsequent_indent="    ")
            print(f"\n  [{relogio(inicio)}]\n{corpo}")
        print()
        while True:
            resposta = _ler("Usar a [l]egenda ou transcrever com [w]hisper? ")
            if resposta in ("l", "legenda"):
                return "legenda"
            if resposta in ("w", "whisper"):
                return "whisper"

    def preprocessar(self, diagnostico) -> bool:
        """Enter aceita a recomendação (aplicar), como no `--visual auto`."""
        while True:
            resposta = _ler("Aplicar o pré-processamento (tirar ronco e ruído, subir a voz)? [S/n] ")
            if resposta in ("", "s", "sim"):
                return True
            if resposta in ("n", "nao", "não"):
                return False

    def visual(self, pergunta: PerguntaVisual) -> bool:
        ind = pergunta.indicadores
        print("\nO que a tela mostra:")
        print(f"  {ind['trocas']} trocas de tela ({ind['trocas_por_min']} por minuto), "
              f"uma a cada {relogio(ind['tempo_medio_s'])} em média")
        print(f"  {ind['palavras_por_tela']} palavras por tela (lidas em poucas amostras)")
        print(f"  formato: {'vertical' if ind['vertical'] else 'horizontal'}")
        print(f"Palpite: {pergunta.perfil} ({pergunta.motivo})")
        if pergunta.perfil == "corte":
            print("  O perfil 'corte' (vídeo curto, com cortes rápidos) ainda não existe: só aula por enquanto.")
        padrao = pergunta.perfil == "aula"
        resposta = _ler(f"Extrair os slides com OCR? [{'S/n' if padrao else 's/N'}] ")
        return padrao if not resposta else resposta in ("s", "sim", "y", "yes")

    def apagar_audio(self, pasta_audio: Path) -> bool | None:
        if not self.interativo:
            print(f"Áudio guardado em {pasta_audio} (use --apagar-audio para apagar).")
            return None
        try:
            return input("Apagar os áudios gravados? [s/N] ").strip().lower() in ("s", "sim", "y", "yes")
        except EOFError:
            return False


class ProgressoTerminal:
    """Imprime as mensagens; o andamento vira uma linha que se reescreve (`\\r`)."""

    def __init__(self):
        self._ultimo = {}

    def mensagem(self, texto: str) -> None:
        print(texto)

    def aviso(self, texto: str) -> None:
        print(f"Aviso: {texto}")

    def andamento(self, fase: str, atual: float, total: float) -> None:
        porcento = int(atual / total * 100) if total else 100
        if fase == "whisper":
            print(f"\r  {porcento:3d}%  {relogio(atual)} / {relogio(total)}", end="", flush=True)
        elif porcento != self._ultimo.get(fase):  # só quando o número muda: um quadro por segundo seria muito texto
            self._ultimo[fase] = porcento
            print(f"\r  {fase} {porcento:3d}%", end="", flush=True)

    def fim_andamento(self) -> None:
        print()
        self._ultimo.clear()


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
    try:
        saida = pipeline.processar(Opcoes.de_dict(vars(args)), DecisorTerminal(), ProgressoTerminal())
    except Erro as e:
        print(f"\nErro: {e}", file=sys.stderr)
        return 1
    if saida.erro_visual:
        print(f"\nErro no visual: {saida.erro_visual}\nO texto já está salvo em {saida.destino}.", file=sys.stderr)
        return 1
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
