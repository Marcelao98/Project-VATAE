"""
Motor de transcrição: arquivo de áudio -> segmentos de texto (faster-whisper).

Extraído do Escriba (modules/echo/service.py da Natty), sem nada de Discord:
uma faixa só, sem horário real, sem fusão de falantes.
"""

import os
from dataclasses import dataclass, field

from . import audio as _audio
from . import repeticao

# "large-v3-turbo": multilíngue, qualidade perto do large-v3, mais rápido até
# que o medium. O "small" errou nomes e palavras soltas num teste real
# (02/10/2026); os distil-whisper são treinados só em inglês.
MODELO_PADRAO = "large-v3-turbo"

# Idioma fixo: a detecção automática gerou alucinações em outros idiomas, e
# com language=None o encoder (a parte pesada) roda uma vez a mais só pra
# detectar. "auto" na CLI vira None aqui.
IDIOMA_PADRAO = "pt"

# 1 hipótese por trecho em vez de 5: em português quase não muda a qualidade
# e fica 2-3x mais rápido (Escriba, 02/10/2026). Uma thread por núcleo físico
# (os.cpu_count() conta os lógicos, o dobro com hyperthreading).
BEAM_SIZE = 1
CPU_THREADS = max(1, (os.cpu_count() or 2) // 2)

# O faster-whisper corta os hotwords em max_length // 2 - 1 = 223 tokens, sem
# avisar. Acima disso a CLI avisa que a lista foi cortada.
LIMITE_TOKENS_TERMOS = 224
# Folga de cada lado ao refazer um trecho suspeito (sem invadir os vizinhos).
FOLGA_REFAZER_S = 0.5

_MODELOS = {}  # nome -> WhisperModel já carregado


@dataclass
class Segmento:
    inicio: float
    fim: float
    texto: str
    # Só em gravação com duas faixas: "eu" (microfone) ou "outros" (som do PC).
    falante: str | None = None


@dataclass
class Resultado:
    fonte: str
    duracao_s: float
    modelo: str | None       # None quando o texto veio de legenda
    idioma: str
    segmentos: list = field(default_factory=list)
    origem: str = "whisper"  # whisper, legenda-manual ou legenda-automatica
    refeitos: list = field(default_factory=list)  # trechos refeitos sem os termos (ver repeticao.py)
    avisos: list = field(default_factory=list)
    faixas: list = field(default_factory=list)  # só em gravação com duas faixas: ["sistema", "microfone"]
    preprocessamento: dict | None = None  # só se o áudio passou pelo pré-processamento (ver preprocessar.py)


def modelo_em_cache(nome: str = MODELO_PADRAO) -> bool:
    """True se o modelo já está no cache do Hugging Face (não precisa baixar)."""
    from faster_whisper import download_model

    try:
        download_model(nome, local_files_only=True)
        return True
    except Exception:
        return False


def carregar_modelo(nome: str = MODELO_PADRAO):
    """Carrega o modelo só na primeira vez que é pedido; depois reaproveita."""
    if nome not in _MODELOS:
        from faster_whisper import WhisperModel

        _MODELOS[nome] = WhisperModel(
            nome, device="cpu", compute_type="int8", cpu_threads=CPU_THREADS
        )
    return _MODELOS[nome]


def _termos_do_texto(texto: str) -> list:
    termos = []
    for linha in texto.splitlines():
        linha = linha.split("#", 1)[0].strip()
        if linha:
            termos.append(linha)
    return termos


def ler_termos(texto: str) -> str:
    """Conteúdo do arquivo de termos (um por linha, # comenta) -> string de hotwords."""
    return ", ".join(_termos_do_texto(texto))


def combinar_termos(textos) -> str:
    """
    Vários arquivos de termos -> uma string de hotwords só, na ordem dos arquivos,
    sem repetir termo (maiúscula e minúscula contam como o mesmo). O limite de
    tokens vale para a soma: `transcrever` avisa se passar.
    """
    vistos, termos = set(), []
    for texto in textos:
        for termo in _termos_do_texto(texto):
            if termo.lower() not in vistos:
                vistos.add(termo.lower())
                termos.append(termo)
    return ", ".join(termos)


def _tokens_dos_termos(whisper, hotwords: str) -> int | None:
    """Quantos tokens a lista ocupa, se o modelo deixar contar (o dublê não deixa)."""
    tokenizador = getattr(whisper, "hf_tokenizer", None)
    if tokenizador is None:
        return None
    return len(tokenizador.encode(" " + hotwords.strip()).ids)


def limites_pelas_palavras(bruto) -> tuple:
    """
    (inicio, fim) do segmento bruto. Com `word_timestamps`, o segmento traz as
    palavras e o horário vale da primeira à última: o Whisper, sozinho, às vezes
    devolve um segmento que cobre silêncio ("Aham" com 37 s de duração). Sem
    palavras, fica o horário do próprio segmento.
    """
    palavras = getattr(bruto, "words", None)
    if palavras:
        return palavras[0].start, palavras[-1].end
    return bruto.start, bruto.end


def _converter(brutos, deslocamento: float = 0.0) -> list:
    segmentos = []
    for s in brutos:
        inicio, fim = limites_pelas_palavras(s)
        segmentos.append(Segmento(inicio=inicio + deslocamento, fim=fim + deslocamento, texto=s.text.strip()))
    return segmentos


def _refazer_suspeitos(whisper, array, duracao, segmentos, termos, opcoes) -> tuple:
    """
    Refaz SEM os termos cada faixa de segmentos com sinal de loop. A janela vai
    do começo do primeiro ao fim do último segmento da faixa, com uma folga
    que não invade os vizinhos. Devolve (segmentos, [trechos refeitos]).
    """
    faixas = repeticao.trechos_suspeitos(segmentos, termos)
    if not faixas:
        return segmentos, []
    sem_termos = {k: v for k, v in opcoes.items() if k != "hotwords"}
    novos, refeitos, inicio_livre = [], [], 0
    for i, j, motivo in faixas:
        ini = max(segmentos[i].inicio - FOLGA_REFAZER_S, segmentos[i - 1].fim if i else 0.0)
        fim = min(segmentos[j].fim + FOLGA_REFAZER_S, segmentos[j + 1].inicio if j + 1 < len(segmentos) else duracao)
        pedaco = array[int(ini * _audio.TAXA):int(fim * _audio.TAXA)]
        brutos, _ = whisper.transcribe(pedaco, **sem_termos)
        novos += segmentos[inicio_livre:i] + _converter(brutos, ini)
        inicio_livre = j + 1
        refeitos.append({
            "inicio": round(ini, 2),
            "fim": round(fim, 2),
            "motivo": motivo,
            "antes": " ".join(s.texto for s in segmentos[i:j + 1]),
        })
    novos += segmentos[inicio_livre:]
    return novos, refeitos


def transcrever(
    caminho,
    modelo: str = MODELO_PADRAO,
    idioma: str | None = IDIOMA_PADRAO,
    hotwords: str | None = None,
    palavras: bool = False,
    vad_silencio_ms: int | None = None,
    progresso=None,
    carregar_audio=_audio.carregar,
    obter_modelo=carregar_modelo,
) -> Resultado:
    """
    Transcreve o arquivo em `caminho`. `idioma` None (ou "auto") deixa o
    Whisper detectar. `progresso(segundo_atual, total)` é chamado a cada
    segmento pronto. `carregar_audio` e `obter_modelo` existem pros testes
    trocarem por dublês.

    `hotwords` só vai pro modelo se vier preenchido, e com proteção contra o
    loop de repetição que a lista de termos da campanha causou na sessão real:
    depois da transcrição, os trechos com sinal de loop (ver repeticao.py) são
    refeitos sem os termos e ficam registrados em `Resultado.refeitos`.

    `palavras` liga o `word_timestamps` do faster-whisper e ajusta o início e o
    fim de cada segmento à primeira e à última palavra (custa um pouco mais de
    tempo; a CLI só liga em gravação). `vad_silencio_ms` muda a pausa mínima que
    o VAD usa para cortar a fala (sem ele, o faster-whisper usa 160 ms); fica
    desligado a não ser que o usuário peça.
    """
    if idioma == "auto":
        idioma = None
    array, duracao = carregar_audio(caminho)
    whisper = obter_modelo(modelo)
    opcoes = dict(
        language=idioma,
        vad_filter=True,  # pula o que não é fala
        # Sem o texto anterior como contexto: com ele, no teste real
        # (02/10/2026) o turbo repetiu uma frase e PULOU o final.
        condition_on_previous_text=False,
        beam_size=BEAM_SIZE,
    )
    if palavras:
        opcoes["word_timestamps"] = True
    if vad_silencio_ms is not None:
        opcoes["vad_parameters"] = {"min_silence_duration_ms": vad_silencio_ms}
    avisos = []
    if hotwords:
        opcoes["hotwords"] = hotwords
        tokens = _tokens_dos_termos(whisper, hotwords)
        if tokens is not None and tokens >= LIMITE_TOKENS_TERMOS:
            avisos.append(f"a lista de termos tem {tokens} tokens; o Whisper só usa os primeiros "
                          f"{LIMITE_TOKENS_TERMOS - 1} e corta o resto. Encurte a lista.")
    brutos, info = whisper.transcribe(array, **opcoes)

    segmentos = []
    for s in brutos:  # gerador: a transcrição acontece aqui, segmento a segmento
        inicio, fim = limites_pelas_palavras(s)
        segmentos.append(Segmento(inicio=inicio, fim=fim, texto=s.text.strip()))
        if progresso:
            progresso(min(fim, duracao), duracao)

    refeitos = []
    if hotwords:
        segmentos, refeitos = _refazer_suspeitos(
            whisper, array, duracao, segmentos, repeticao.termos_da_lista(hotwords), opcoes)
    if progresso:
        progresso(duracao, duracao)

    return Resultado(
        fonte=str(caminho),
        duracao_s=duracao,
        modelo=modelo,
        idioma=getattr(info, "language", None) or idioma or "?",
        segmentos=segmentos,
        refeitos=refeitos,
        avisos=avisos,
    )
