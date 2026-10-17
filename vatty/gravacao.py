"""
Gravação do áudio do PC (e do microfone) em arquivos .wav, uma faixa por fonte.

Só Windows por enquanto: o som do sistema vem do loopback do WASAPI, via
PyAudioWPatch (extra opcional: `pip install -e ".[gravacao]"`).

Cada faixa vai para um .wav de 16 kHz mono (o que o Whisper usa) numa pasta
`gravacoes/AAAA-MM-DD_HH-MM/`: `sistema.wav` e, com microfone, `microfone.wav`.
Duas faixas dão a separação de quem falou: o sistema é "outros", o microfone
é "eu".

O loopback do Windows não entrega dado nenhum enquanto nada toca. Por isso a
linha do tempo vem do relógio, não do dado: a cada passo cada faixa escreve
exatamente o que o relógio pede e completa com silêncio o que não chegou. O
horário do arquivo é sempre o horário real.

A captura real (`abrir_entradas`) é a única parte que toca a placa de som; o
resto recebe as entradas por parâmetro, e os testes passam dublês.
"""

import json
import queue
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import motor

TAXA = 16000          # Hz: o que o Whisper usa
PASSO_S = 0.25        # de quanto em quanto tempo as faixas são esvaziadas
QUADROS_POR_BLOCO = 1024

# faixa -> quem fala nela
FALANTES = {"sistema": "outros", "microfone": "eu"}
FAIXAS = tuple(FALANTES)  # ordem fixa: sistema primeiro

# Pico (0 a 1) abaixo disso: a faixa ficou praticamente muda.
PICO_MUDO = 0.005

# Metadados da gravação (só com --tela): o horário real de início de cada faixa, para a sincronia.
METADADOS = "gravacao.json"


class ErroGravacao(Exception):
    """Falha ao preparar ou fazer a gravação (mensagem para o usuário)."""


@dataclass
class Gravacao:
    pasta: Path
    duracao_s: float
    faixas: dict = field(default_factory=dict)  # nome -> caminho do .wav
    picos: dict = field(default_factory=dict)   # nome -> maior amplitude (0 a 1)
    inicio: float | None = None                 # horário real (relógio do sistema) do começo das faixas

    def faixas_mudas(self) -> list:
        return [nome for nome, pico in self.picos.items() if pico < PICO_MUDO]


# --- Conversões (puras) ------------------------------------------------------

def para_mono(brutos: bytes, canais: int) -> np.ndarray:
    """Bytes int16 intercalados -> float32 mono em [-1, 1]. Sobra de quadro é descartada."""
    brutos = brutos[: len(brutos) // 2 * 2]
    dados = np.frombuffer(brutos, dtype=np.int16)
    if canais > 1:
        dados = dados[: len(dados) // canais * canais].reshape(-1, canais).mean(axis=1)
    return (dados / 32768.0).astype(np.float32)


def reamostrar(sinal: np.ndarray, taxa_origem: int, taxa_destino: int = TAXA) -> np.ndarray:
    """
    Muda a taxa de amostragem. Quando a origem é múltipla do destino (48 kHz ->
    16 kHz) tira a média de cada grupo, que já filtra o grosso do aliasing;
    senão, interpolação linear (suficiente para fala).
    """
    if taxa_origem == taxa_destino or len(sinal) == 0:
        return sinal
    if taxa_origem % taxa_destino == 0:
        fator = taxa_origem // taxa_destino
        n = len(sinal) // fator
        return sinal[: n * fator].reshape(n, fator).mean(axis=1).astype(np.float32)
    n = round(len(sinal) * taxa_destino / taxa_origem)
    if n == 0:
        return sinal[:0]
    posicoes = np.linspace(0, len(sinal) - 1, n)
    return np.interp(posicoes, np.arange(len(sinal)), sinal).astype(np.float32)


def _para_int16(sinal: np.ndarray) -> bytes:
    return np.clip(sinal * 32767.0, -32768, 32767).astype(np.int16).tobytes()


# --- A gravação em si --------------------------------------------------------

class _Faixa:
    """Uma entrada, o .wav dela e o que já chegou mas ainda não foi escrito."""

    def __init__(self, entrada, caminho: Path):
        self.entrada = entrada
        self.caminho = caminho
        self.pendente = np.zeros(0, dtype=np.float32)
        self.pico = 0.0
        self.escritor = wave.open(str(caminho), "wb")
        self.escritor.setnchannels(1)
        self.escritor.setsampwidth(2)
        self.escritor.setframerate(TAXA)

    def puxar(self) -> None:
        """Traz do dispositivo o que chegou desde o último passo, já em 16 kHz mono."""
        bruto = self.entrada.pegar()
        if bruto:
            mono = para_mono(bruto, self.entrada.canais)
            self.pendente = np.concatenate([self.pendente, reamostrar(mono, self.entrada.taxa)])

    def escrever(self, n: int) -> float:
        """Escreve exatamente `n` amostras (completa com silêncio). Devolve o pico do bloco."""
        bloco, self.pendente = self.pendente[:n], self.pendente[n:]
        if len(bloco) < n:
            bloco = np.concatenate([bloco, np.zeros(n - len(bloco), dtype=np.float32)])
        self.escritor.writeframes(_para_int16(bloco))
        pico = float(np.abs(bloco).max()) if n else 0.0
        self.pico = max(self.pico, pico)
        return pico

    def fechar(self) -> None:
        self.escritor.close()
        self.entrada.fechar()


def gravar(entradas, pasta, *, duracao_max=None, relogio=time.monotonic, dormir=time.sleep,
           progresso=None, agora=time.time, parar=None) -> Gravacao:
    """
    Grava até `duracao_max` segundos ou até Ctrl+C (KeyboardInterrupt), o que vier
    primeiro. `entradas` é uma lista de objetos com `nome`, `taxa`, `canais`,
    `pegar()` (bytes int16 que chegaram, sem bloquear) e `fechar()`. Os .wav
    ficam em `pasta`, um por entrada. `progresso(decorrido_s, {nome: pico})`
    é chamado a cada passo. `parar()` devolvendo True encerra como o Ctrl+C (a
    interface usa isso). `inicio` do resultado é o horário real (`agora()`) em
    que o relógio das faixas começou: todas as faixas de áudio partem dele juntas.
    """
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    faixas = {e.nome: _Faixa(e, pasta / f"{e.nome}.wav") for e in entradas}
    escritas = 0

    def passo(decorrido: float) -> None:
        nonlocal escritas
        n = int(decorrido * TAXA) - escritas
        if n <= 0:
            return
        niveis = {}
        for nome, faixa in faixas.items():
            faixa.puxar()
            niveis[nome] = faixa.escrever(n)
        escritas += n
        if progresso:
            progresso(decorrido, niveis)

    inicio_real, inicio = agora(), relogio()
    try:
        while True:
            dormir(PASSO_S)
            decorrido = relogio() - inicio
            ultimo = duracao_max is not None and decorrido >= duracao_max
            passo(duracao_max if ultimo else decorrido)
            if ultimo or (parar is not None and parar()):
                break
    except KeyboardInterrupt:
        passo(relogio() - inicio)
    finally:
        for faixa in faixas.values():
            faixa.fechar()

    return Gravacao(
        pasta=pasta,
        duracao_s=escritas / TAXA,
        faixas={nome: f.caminho for nome, f in faixas.items()},
        picos={nome: f.pico for nome, f in faixas.items()},
        inicio=inicio_real,
    )


def pasta_nova(raiz, nome: str) -> Path:
    """`raiz/nome`, ou `raiz/nome-2`, `-3`... se já existir: duas gravações no mesmo minuto não se sobrescrevem."""
    raiz = Path(raiz)
    candidata, n = raiz / nome, 1
    while candidata.exists():
        n += 1
        candidata = raiz / f"{nome}-{n}"
    return candidata


def salvar_metadados(pasta, dados: dict) -> Path:
    """Escreve o gravacao.json da pasta da gravação."""
    destino = Path(pasta) / METADADOS
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destino


def ler_metadados(pasta) -> dict:
    """O gravacao.json da pasta, ou {} se não houver (gravação só de áudio, ou de antes da 0.16.0)."""
    arquivo = Path(pasta) / METADADOS
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.is_file() else {}


def faixas_na_pasta(pasta) -> dict:
    """{nome: caminho} das faixas .wav que existem na pasta de uma gravação."""
    pasta = Path(pasta)
    return {nome: pasta / f"{nome}.wav" for nome in FAIXAS if (pasta / f"{nome}.wav").is_file()}


def juntar_faixas(resultados: dict):
    """
    {faixa: Resultado do motor} -> um Resultado só, com os segmentos de todas as
    faixas intercalados por horário e cada um marcado com o `falante`.
    """
    from dataclasses import replace

    segmentos = []
    refeitos = []
    avisos = []
    for nome, r in resultados.items():
        falante = FALANTES[nome]
        segmentos += [replace(s, falante=falante) for s in r.segmentos]
        refeitos += [{**t, "falante": falante} for t in r.refeitos]
        avisos += [f"{nome}: {a}" for a in r.avisos]
    primeiro = next(iter(resultados.values()))
    return motor.Resultado(
        fonte="gravacao",
        duracao_s=max(r.duracao_s for r in resultados.values()),
        modelo=primeiro.modelo,
        idioma=primeiro.idioma,
        segmentos=sorted(segmentos, key=lambda s: (s.inicio, s.fim)),
        origem="whisper",
        refeitos=refeitos,
        avisos=avisos,
        faixas=list(resultados) if len(resultados) >= 2 else [],
        # por faixa: o microfone pode ter sido pré-processado e o som do PC não
        falantes=next((r.falantes for r in resultados.values() if r.falantes), None),
        preprocessamento={n: r.preprocessamento for n, r in resultados.items() if r.preprocessamento} or None,
    )


# --- Captura real (Windows) --------------------------------------------------
# Única parte que fala com a placa de som. Não tem teste automático: é
# verificada rodando `vatty gravar --duracao 5` num Windows.

class _EntradaWasapi:
    """Um dispositivo WASAPI lido por callback; o PortAudio cria a própria thread."""

    def __init__(self, nome: str, escolher):
        import pyaudiowpatch as pyaudio

        self.nome = nome
        # PyAudio é criado aqui, na thread principal, junto com o stream: criar
        # em outro lugar causa "Unanticipated host error" (issue #4 do projeto).
        self._pa = pyaudio.PyAudio()
        try:
            info = escolher(self._pa, pyaudio)
            self.taxa = int(info["defaultSampleRate"])
            self.canais = int(info["maxInputChannels"])
            self.descricao = info["name"]
            self._fila = queue.Queue()

            def callback(dados, quadros, tempo, estado):
                self._fila.put(dados)
                return (None, pyaudio.paContinue)

            self._stream = self._pa.open(
                format=pyaudio.paInt16, channels=self.canais, rate=self.taxa, input=True,
                input_device_index=info["index"], frames_per_buffer=QUADROS_POR_BLOCO,
                stream_callback=callback,
            )
        except BaseException:
            self._pa.terminate()  # não deixa o PortAudio aberto se a abertura falhou
            raise

    def pegar(self) -> bytes:
        blocos = []
        while True:
            try:
                blocos.append(self._fila.get_nowait())
            except queue.Empty:
                return b"".join(blocos)

    def fechar(self) -> None:
        try:
            self._stream.stop_stream()
            self._stream.close()
        finally:
            self._pa.terminate()


def _alto_falante_padrao(pa, pyaudio):
    try:
        return pa.get_default_wasapi_loopback()
    except Exception as e:
        raise ErroGravacao(f"não achei o loopback do alto-falante padrão: {e}") from e


def _microfone_padrao(pa, pyaudio):
    try:
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        return pa.get_device_info_by_index(wasapi["defaultInputDevice"])
    except Exception as e:
        raise ErroGravacao(f"não achei o microfone padrão: {e}") from e


def abrir_entradas(microfone: bool = False) -> list:
    """Abre o som do PC (e o microfone, se pedido). Levanta ErroGravacao com o que fazer."""
    if sys.platform != "win32":
        raise ErroGravacao("a gravação só funciona no Windows por enquanto.")
    try:
        import pyaudiowpatch  # noqa: F401
    except ImportError:
        raise ErroGravacao('falta a biblioteca de captura: pip install -e ".[gravacao]"') from None

    entradas = []
    try:
        entradas.append(_EntradaWasapi("sistema", _alto_falante_padrao))
        if microfone:
            entradas.append(_EntradaWasapi("microfone", _microfone_padrao))
    except ErroGravacao:
        for e in entradas:
            e.fechar()
        raise
    except Exception as e:
        for e_aberta in entradas:
            e_aberta.fechar()
        raise ErroGravacao(f"não consegui abrir o áudio: {e}") from e
    return entradas
