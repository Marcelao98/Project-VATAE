"""
As portas da aplicação: o que o pipeline precisa de quem o usa.

O pipeline nunca chama `print` nem `input`. Quando precisa de uma decisão do
usuário, pergunta ao `Decisor`; quando tem algo a contar, conta ao `Progresso`.
A CLI implementa os dois com o terminal; a API vai implementar com o job
pausado esperando a resposta do front e com eventos (SSE).
"""

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Protocol

from .. import motor


class ErroPipeline(Exception):
    """Erro para mostrar ao usuário: o processamento parou."""


@dataclass
class Opcoes:
    """Tudo o que o pipeline precisa saber. Os nomes são os mesmos da CLI (`--modelo` -> `modelo`)."""
    entrada: str
    saida: Path = Path("transcricoes")
    modelo: str = motor.MODELO_PADRAO
    lang: str = motor.IDIOMA_PADRAO
    termos: list | None = None                  # arquivos .txt com termos (viram hotwords)
    texto: str = "perguntar"                    # perguntar | legenda | whisper
    visual: str = "nenhum"                      # nenhum | auto | aula
    preprocessar: str = "perguntar"             # perguntar | sim | nao
    ruido_modelo: str | None = None
    horario_por_palavra: str = "auto"           # auto | sim | nao
    vad_silencio_ms: int | None = None
    apagar_audio: bool | None = None            # gravação: None = perguntar

    @classmethod
    def de_dict(cls, dados: dict) -> "Opcoes":
        """Pega só os campos conhecidos (ex.: `vars(args)` do argparse)."""
        nomes = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in dados.items() if k in nomes})


@dataclass
class PerguntaLegenda:
    """O que o usuário precisa ver para escolher entre a legenda e o Whisper."""
    chave: str                  # ex.: 'pt-BR'
    automatica: bool
    indicadores: dict           # legenda.indicadores(...)
    amostras: list              # [(inicio_s, texto), ...]


@dataclass
class PerguntaVisual:
    """O palpite do `--visual auto`."""
    indicadores: dict
    perfil: str                 # 'aula' ou 'corte'
    motivo: str


class Decisor(Protocol):
    """Quem decide no lugar do usuário (ou pergunta a ele)."""

    @property
    def interativo(self) -> bool:
        """Dá para perguntar? Sem isso, o pipeline pede a opção explícita em vez de escolher sozinho."""

    def legenda(self, pergunta: PerguntaLegenda) -> str:
        """'legenda' ou 'whisper'."""

    def preprocessar(self, diagnostico) -> bool:
        """Aplicar o pré-processamento recomendado?"""

    def visual(self, pergunta: PerguntaVisual) -> bool:
        """Extrair os slides com OCR?"""

    def apagar_audio(self, pasta: Path) -> bool | None:
        """Apagar os .wav da gravação? None: não deu para perguntar (o decisor já avisou)."""


class Progresso(Protocol):
    """Para onde vão as mensagens e o andamento."""

    def mensagem(self, texto: str) -> None: ...

    def aviso(self, texto: str) -> None: ...

    def andamento(self, fase: str, atual: float, total: float) -> None:
        """fase: 'whisper' (segundos de áudio), 'tela' ou 'slides' (quadros/slides)."""

    def fim_andamento(self) -> None:
        """A barra de andamento terminou."""
