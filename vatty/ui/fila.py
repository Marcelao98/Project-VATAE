"""
Fila de trabalhos da interface: um worker só (a CPU é o gargalo), com eventos para quem assina.

Lógica pura: quem realmente transcreve entra por parâmetro (`executar`), então os testes não rodam
nada de verdade. Sem rede, sem LLM.
"""

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field

LOG_MAX = 500  # linhas guardadas por trabalho (o terminal mostra o fim)

FILA, RODANDO, PRONTO, ERRO, CANCELADO = "fila", "rodando", "pronto", "erro", "cancelado"
# Pistas: cada uma tem o seu trabalhador. Os agentes (Claude Code) andam numa pista própria, então
# gravar e transcrever nunca esperam por eles, nem param se o Claude travar ou não existir.
TRANSCRICAO, AGENTES = "transcricao", "agentes"
PISTAS = (TRANSCRICAO, AGENTES)
ENCERRADOS = (PRONTO, ERRO, CANCELADO)


@dataclass
class Trabalho:
    id: str
    entrada: str
    opcoes: dict
    estado: str = FILA
    progresso: int = 0
    etapa: str = "Esperando a vez"
    pasta: str | None = None
    erro: str | None = None
    criado: float = 0.0
    inicio: float | None = None
    fim: float | None = None
    log: list = field(default_factory=list)
    pista: str = TRANSCRICAO

    def resumo(self) -> dict:
        """O que vai para a tela (sem o log inteiro)."""
        return {"id": self.id, "entrada": self.entrada, "estado": self.estado, "progresso": self.progresso,
                "etapa": self.etapa, "pasta": self.pasta, "erro": self.erro, "criado": self.criado,
                "inicio": self.inicio, "fim": self.fim, "pista": self.pista}


class Cancelado(Exception):
    """O `executar` levanta isto quando viu o pedido de cancelamento e parou."""


class Fila:
    def __init__(self, executar, agora=time.time):
        """`executar(trabalho, contexto)` faz o trabalho e devolve a pasta; ver `Contexto`."""
        self._executar = executar
        self._agora = agora
        self._trabalhos: dict = {}
        self._ordem: list = []
        self._trava = threading.RLock()
        self._acorda = threading.Condition(self._trava)
        self._ouvintes: list = []
        self._parar = threading.Event()
        self._cancelar: dict = {}
        self._thread = None

    # --- consulta ---
    def trabalhos(self) -> list:
        with self._trava:
            return [self._trabalhos[i].resumo() for i in self._ordem]

    def trabalho(self, id_: str):
        with self._trava:
            return self._trabalhos.get(id_)

    # --- ações ---
    def adicionar(self, entrada: str, opcoes: dict | None = None, pista: str = TRANSCRICAO) -> Trabalho:
        entrada = (entrada or "").strip()
        if not entrada:
            raise ValueError("Entrada vazia.")
        with self._trava:
            t = Trabalho(id=uuid.uuid4().hex[:8], entrada=entrada, opcoes=dict(opcoes or {}), criado=self._agora(),
                         pista=pista if pista in PISTAS else TRANSCRICAO)
            self._trabalhos[t.id] = t
            self._ordem.append(t.id)
            self._cancelar[t.id] = threading.Event()
            self._publicar({"tipo": "trabalho", "trabalho": t.resumo()})
            self._acorda.notify_all()
            return t

    def cancelar(self, id_: str) -> bool:
        """Na fila: sai na hora. Rodando: pede para parar. Já encerrado: não faz nada."""
        with self._trava:
            t = self._trabalhos.get(id_)
            if not t or t.estado in ENCERRADOS:
                return False
            self._cancelar[id_].set()
            if t.estado == FILA:
                self._encerrar(t, CANCELADO, etapa="Cancelado")
            return True

    def repetir(self, id_: str):
        """Põe de novo na fila um trabalho com erro ou cancelado."""
        with self._trava:
            t = self._trabalhos.get(id_)
            if not t or t.estado not in (ERRO, CANCELADO):
                return None
            return self.adicionar(t.entrada, t.opcoes, t.pista)

    # --- eventos ---
    def assinar(self):
        q = queue.Queue()
        with self._trava:
            self._ouvintes.append(q)
        return q

    def desassinar(self, q) -> None:
        with self._trava:
            if q in self._ouvintes:
                self._ouvintes.remove(q)

    def _publicar(self, evento: dict) -> None:
        for q in list(self._ouvintes):
            q.put(evento)

    def _encerrar(self, t: Trabalho, estado: str, etapa: str, erro: str | None = None) -> None:
        t.estado, t.etapa, t.erro, t.fim = estado, etapa, erro, self._agora()
        if estado == PRONTO:
            t.progresso = 100
        self._publicar({"tipo": "trabalho", "trabalho": t.resumo()})

    # --- execução ---
    def _proximo(self, pista: str = TRANSCRICAO):
        for i in self._ordem:
            if self._trabalhos[i].estado == FILA and self._trabalhos[i].pista == pista:
                return self._trabalhos[i]
        return None

    def processar_um(self, pista: str = TRANSCRICAO) -> bool:
        """Roda o próximo da pista (se houver). Devolve se rodou algo. Os testes chamam isto direto."""
        with self._trava:
            t = self._proximo(pista)
            if not t:
                return False
            t.estado, t.inicio, t.etapa = RODANDO, self._agora(), "Começando"
            self._publicar({"tipo": "trabalho", "trabalho": t.resumo()})
        ctx = Contexto(self, t, self._cancelar[t.id])
        try:
            pasta = self._executar(t, ctx)
        except Cancelado:
            with self._trava:
                self._encerrar(t, CANCELADO, etapa="Cancelado")
        except Exception as e:  # um erro num item não pode derrubar a fila
            with self._trava:
                ctx.log(f"Erro: {e}")
                self._encerrar(t, ERRO, etapa="Erro", erro=str(e))
        else:
            with self._trava:
                t.pasta = pasta
                self._encerrar(t, PRONTO, etapa="Pronto")
        return True

    def iniciar(self) -> None:
        if self._thread:
            return
        self._thread = [threading.Thread(target=self._laco, args=(p,), name=f"fila-vatty-{p}", daemon=True) for p in PISTAS]
        for t in self._thread:
            t.start()

    def parar(self) -> None:
        self._parar.set()
        with self._trava:
            for e in self._cancelar.values():
                e.set()
            self._acorda.notify_all()

    def _laco(self, pista: str = TRANSCRICAO) -> None:
        while not self._parar.is_set():
            if not self.processar_um(pista):
                with self._acorda:
                    if not self._parar.is_set() and not self._proximo(pista):
                        self._acorda.wait(timeout=1.0)


class Contexto:
    """O que o `executar` usa para falar com a fila: log, progresso e pedido de cancelamento."""

    def __init__(self, fila: Fila, trabalho: Trabalho, evento_cancelar):
        self._fila, self._t, self._cancelar = fila, trabalho, evento_cancelar

    @property
    def cancelado(self) -> bool:
        return self._cancelar.is_set()

    def enfileirar(self, entrada: str, opcoes: dict, pista: str):
        """Cria outro trabalho (ex.: os agentes de uma pasta pronta), sem prender este."""
        return self._fila.adicionar(entrada, opcoes, pista)

    def log(self, linha: str) -> None:
        with self._fila._trava:
            self._t.log.append(linha)
            del self._t.log[:-LOG_MAX]
            self._fila._publicar({"tipo": "log", "id": self._t.id, "linha": linha})

    def progresso(self, percentual: int | None = None, etapa: str | None = None) -> None:
        with self._fila._trava:
            if percentual is not None:
                self._t.progresso = max(0, min(100, int(percentual)))
            if etapa:
                self._t.etapa = etapa
            self._fila._publicar({"tipo": "trabalho", "trabalho": self._t.resumo()})
