"""
Pré-processamento opcional do áudio, antes do Whisper: corta o ronco grave,
tira o ruído e sobe as partes baixas da fala (áudio de WhatsApp, gravação de
celular com a voz baixa).

Cadeia (no ffmpeg, na decodificação; o áudio continua indo ao Whisper como array):

    aformat (mono, 16 kHz) -> highpass -> arnndn (rede neural) -> speechnorm

A ordem importa: o ruído sai ANTES de subir o volume, senão o chiado sobe junto.

Antes de aplicar, `analisar` mede o áudio (nível da fala, piso de ruído, ronco,
estouro) e `preparar` mostra os números e pergunta. Todos os limites abaixo são
chutes medidos só em sinal sintético: ajustar com áudio real.

Lógica pura: o ffmpeg, o download do modelo e a pergunta entram como parâmetro
(os testes trocam por dublês).
"""

import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import audio

# --- Diagnóstico (chutes, ver o cabeçalho) ---------------------------------
QUADRO_S = 0.03                   # janela do nível por quadro
SILENCIO_DIGITAL_DBFS = -80.0     # quadros abaixo disso não contam (silêncio de verdade)
MIN_QUADROS = 10                  # menos que isso: não dá para medir
LIMITE_FALA_BAIXA_DBFS = -32.0    # percentil 95 do nível por quadro
LIMITE_SNR_DB = 15.0              # (percentil 95 - percentil 10) abaixo disso: ruidoso
RONCO_ATE_HZ = 60.0
LIMITE_RONCO_FRACAO = 0.05        # energia abaixo de RONCO_ATE_HZ sobre a total
LIMITE_ESTOURO_FRACAO = 0.001     # amostras em +-1 (só avisa: o filtro não conserta)
TAMANHO_FFT = 4096

# --- Cadeia de filtros (chutes) --------------------------------------------
CORTE_GRAVE_HZ = 80   # quase não há fala abaixo disso; só ronco de ar-condicionado, vento, manuseio
# e=10: sobe até 10x (+20 dB) onde a fala é baixa; o padrão do ffmpeg (2) pouco ajuda voz baixa.
NORMALIZACAO = "speechnorm=e=10:r=0.0005:l=1"
FORMATO = f"aformat=sample_rates={audio.TAXA}:channel_layouts=mono"

# --- Modelos de ruído do arnndn ---------------------------------------------
# Pesos do projeto GregorR/rnnoise-models (README: "none of this work is creative"; sem licença
# nomeada). Não entram no repositório: baixam uma vez para o cache do usuário.
MODELO_RUIDO_PADRAO = "somnolent-hogwash"  # fala, com ruído de gravação
MODELOS_RUIDO = {
    "somnolent-hogwash": ("somnolent-hogwash-2018-09-01", "sh.rnnn"),  # fala + ruído de gravação
    "beguiling-drafter": ("beguiling-drafter-2018-08-30", "bd.rnnn"),  # voz + ruído de gravação
    "leavened-quisling": ("leavened-quisling-2018-08-31", "lq.rnnn"),  # voz + ruído geral
}
URL_MODELO = "https://raw.githubusercontent.com/GregorR/rnnoise-models/master/{pasta}/{arquivo}"
ASSINATURA_MODELO = b"rnnoise-nu model file"
NOME_SEGURO = re.compile(r"^[\w.\-]+$")  # entra no filtro do ffmpeg: sem vírgula, dois-pontos, aspas


class ModeloIndisponivel(RuntimeError):
    """Não deu para achar nem baixar o modelo de ruído."""


# --- Diagnóstico -------------------------------------------------------------

@dataclass
class Diagnostico:
    fala_dbfs: float | None
    piso_dbfs: float | None
    snr_db: float | None
    ronco_fracao: float | None
    estouro_fracao: float
    sem_fala: bool = False
    voz_baixa: bool = False
    ruidoso: bool = False
    ronco: bool = False
    estourado: bool = False

    @property
    def recomendado(self) -> bool:
        """O pré-processamento ajuda? (Estouro não entra: o filtro não conserta.)"""
        return self.voz_baixa or self.ruidoso or self.ronco

    @property
    def problemas(self) -> list:
        nomes = [("voz baixa", self.voz_baixa), ("ruído de fundo", self.ruidoso),
                 ("ronco grave", self.ronco), ("áudio estourado (não tem conserto)", self.estourado)]
        return [n for n, ativo in nomes if ativo]

    def para_dict(self) -> dict:
        def r(v, casas=1):
            return None if v is None else round(float(v), casas)
        return {"fala_dbfs": r(self.fala_dbfs), "piso_dbfs": r(self.piso_dbfs), "snr_db": r(self.snr_db),
                "ronco_pct": r(None if self.ronco_fracao is None else self.ronco_fracao * 100),
                "estouro_pct": r(self.estouro_fracao * 100, 3), "problemas": self.problemas}


def _niveis_por_quadro(amostras: np.ndarray) -> np.ndarray:
    """Nível RMS (dBFS) de cada quadro de QUADRO_S, sem os quadros em silêncio digital."""
    tamanho = int(audio.TAXA * QUADRO_S)
    n = len(amostras) // tamanho
    if n == 0:
        return np.array([])
    quadros = amostras[: n * tamanho].reshape(n, tamanho).astype(np.float64)
    niveis = 20 * np.log10(np.sqrt((quadros ** 2).mean(axis=1)) + 1e-12)
    return niveis[niveis > SILENCIO_DIGITAL_DBFS]


def _fracao_de_ronco(amostras: np.ndarray) -> float:
    """Energia abaixo de RONCO_ATE_HZ sobre a total (espectro médio, janelas de Hann, em lotes)."""
    n = len(amostras) // TAMANHO_FFT
    if n == 0:
        return 0.0
    quadros = amostras[: n * TAMANHO_FFT].reshape(n, TAMANHO_FFT)
    janela = np.hanning(TAMANHO_FFT)
    freq = np.fft.rfftfreq(TAMANHO_FFT, 1 / audio.TAXA)
    potencia = np.zeros(len(freq))
    for i in range(0, n, 256):  # em lotes: 1 h de áudio não cabe de uma vez
        potencia += (np.abs(np.fft.rfft(quadros[i:i + 256] * janela, axis=1)) ** 2).sum(axis=0)
    total = potencia.sum()
    return float(potencia[freq < RONCO_ATE_HZ].sum() / total) if total > 0 else 0.0


def analisar(amostras: np.ndarray) -> Diagnostico:
    """Array float32 mono 16 kHz -> Diagnóstico (nível da fala, piso de ruído, ronco, estouro)."""
    amostras = np.asarray(amostras, dtype=np.float32)
    niveis = _niveis_por_quadro(amostras)
    estouro = float((np.abs(amostras) >= 0.999).mean()) if len(amostras) else 0.0
    if len(niveis) < MIN_QUADROS:
        return Diagnostico(None, None, None, None, estouro, sem_fala=True)
    fala, piso = float(np.percentile(niveis, 95)), float(np.percentile(niveis, 10))
    snr = fala - piso
    ronco = _fracao_de_ronco(amostras)
    return Diagnostico(
        fala_dbfs=fala, piso_dbfs=piso, snr_db=snr, ronco_fracao=ronco, estouro_fracao=estouro,
        voz_baixa=fala < LIMITE_FALA_BAIXA_DBFS,
        ruidoso=snr < LIMITE_SNR_DB,
        ronco=ronco > LIMITE_RONCO_FRACAO,
        estourado=estouro > LIMITE_ESTOURO_FRACAO,
    )


def formatar_diagnostico(d: Diagnostico) -> str:
    if d.sem_fala:
        return "Áudio: quase sem sinal para medir."
    linha = (f"Áudio: fala em ~{d.fala_dbfs:.0f} dBFS, fundo em ~{d.piso_dbfs:.0f} dBFS "
             f"(diferença ~{d.snr_db:.0f} dB), {d.ronco_fracao * 100:.0f}% da energia abaixo de "
             f"{RONCO_ATE_HZ:.0f} Hz.")
    return linha + (f"\nPossíveis problemas: {', '.join(d.problemas)}." if d.problemas else "")


# --- Cadeia de filtros -------------------------------------------------------

def cadeia_filtros(arquivo_modelo: str | None) -> str:
    """
    Filtro do ffmpeg. `arquivo_modelo` é só o NOME do .rnnn (o ffmpeg roda dentro da pasta dele,
    para não depender de escapar `C:\\...`). Sem modelo, cai no `afftdn` (sem rede neural).
    """
    ruido = f"arnndn=m={arquivo_modelo}" if arquivo_modelo else "afftdn"
    grave = f"highpass=f={CORTE_GRAVE_HZ}"
    # dois estágios em série: 24 dB/oitava. Um só (12 dB/oit) deixava ronco forte passar (medido em sinal sintético).
    return ",".join([FORMATO, grave, grave, ruido, NORMALIZACAO])


# --- Modelo de ruído ---------------------------------------------------------

def pasta_cache() -> Path:
    base = os.environ.get("VATTY_CACHE") or (Path.home() / ".cache" / "vatty")
    return Path(base) / "rnnoise"


def _baixar(url: str, destino: Path) -> None:
    """Baixa o modelo (uns 300 KB) e confere se é mesmo um modelo, não uma página de erro."""
    with urllib.request.urlopen(url, timeout=30) as resposta:  # noqa: S310 (URL fixa, https)
        dados = resposta.read()
    if not dados.startswith(ASSINATURA_MODELO):
        raise ModeloIndisponivel(f"o arquivo baixado de {url} não parece um modelo do RNNoise.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".parte")
    temporario.write_bytes(dados)
    temporario.replace(destino)


def localizar_modelo(nome_ou_arquivo: str | None = None, baixar=_baixar, cache: Path | None = None,
                     dizer=print) -> Path:
    """
    Nome de um modelo conhecido (baixa na primeira vez) ou caminho de um .rnnn seu.
    Levanta ModeloIndisponivel se não der.
    """
    escolha = nome_ou_arquivo or MODELO_RUIDO_PADRAO
    if escolha.lower().endswith(".rnnn") or os.sep in escolha or "/" in escolha:
        caminho = Path(escolha).expanduser()
        if not caminho.is_file():
            raise ModeloIndisponivel(f"não achei o arquivo de modelo '{escolha}'.")
        if not NOME_SEGURO.match(caminho.name):
            raise ModeloIndisponivel(f"o nome '{caminho.name}' tem caracteres que o ffmpeg não aceita; "
                                     "renomeie o arquivo (só letras, números, ponto, traço e sublinhado).")
        return caminho.resolve()
    if escolha not in MODELOS_RUIDO:
        raise ModeloIndisponivel(f"modelo de ruído desconhecido: '{escolha}'. "
                                 f"Opções: {', '.join(MODELOS_RUIDO)} ou o caminho de um arquivo .rnnn.")
    pasta, arquivo = MODELOS_RUIDO[escolha]
    destino = (cache or pasta_cache()) / arquivo
    if not destino.is_file():
        dizer(f"Baixando o modelo de ruído '{escolha}' (uns 300 KB, só na primeira vez)...")
        try:
            baixar(URL_MODELO.format(pasta=pasta, arquivo=arquivo), destino)
        except ModeloIndisponivel:
            raise
        except Exception as e:  # rede fora, bloqueio, disco cheio...
            raise ModeloIndisponivel(f"não consegui baixar o modelo de ruído ({e}). "
                                     "Baixe o .rnnn à mão e use --ruido-modelo CAMINHO.") from e
    return destino


# --- Orquestração ------------------------------------------------------------

@dataclass
class Preparo:
    """O que a CLI precisa: como carregar o áudio (None = do jeito de sempre) e o que registrar."""
    carregar_audio: object = None   # callable(caminho) -> (array, duracao_s)
    info: dict | None = None        # vai para o cabeçalho do transcricao.json, só se foi aplicado


def preparar(caminho, modo: str, perguntar=None, interativo: bool = False, ruido_modelo: str | None = None,
             carregar=audio.carregar, baixar=_baixar, cache: Path | None = None, dizer=print) -> Preparo:
    """
    modo 'nao': não faz nada (o áudio é carregado como sempre). 'sim': aplica a cadeia.
    'perguntar': mede o áudio e só pergunta se algo estiver ruim; sem terminal, avisa e não aplica.
    `perguntar(diagnostico) -> bool`, `carregar`, `baixar` e `dizer` existem para os testes.
    """
    if modo == "nao":
        return Preparo()
    amostras, duracao = carregar(caminho)
    diagnostico = analisar(amostras)
    dizer(formatar_diagnostico(diagnostico))
    if modo == "sim":
        aplicar = True
    elif not diagnostico.recomendado:
        dizer("Parece bom: sem pré-processamento.")
        aplicar = False
    elif not interativo:
        dizer("Pré-processamento recomendado, mas não há terminal para perguntar: use --preprocessar sim.")
        aplicar = False
    else:
        aplicar = bool(perguntar(diagnostico))
    if not aplicar:
        return Preparo(carregar_audio=lambda _caminho: (amostras, duracao))

    try:
        modelo = localizar_modelo(ruido_modelo, baixar=baixar, cache=cache, dizer=dizer)
        arquivo, pasta, ruido = modelo.name, modelo.parent, f"arnndn:{modelo.name}"
    except ModeloIndisponivel as e:
        dizer(f"Aviso: {e} Usando o afftdn (sem rede neural) no lugar do arnndn.")
        arquivo, pasta, ruido = None, None, "afftdn"
    filtro = cadeia_filtros(arquivo)
    dizer("Pré-processando: tirando o ronco grave e o ruído, subindo a voz...")
    filtrado, duracao_filtrada = carregar(caminho, filtro=filtro, pasta_trabalho=pasta)
    info = {"aplicado": True, "filtro": filtro, "ruido": ruido, "diagnostico": diagnostico.para_dict()}
    return Preparo(carregar_audio=lambda _caminho: (filtrado, duracao_filtrada), info=info)
