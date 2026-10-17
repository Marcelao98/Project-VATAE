"""`vatty ui`: sobe o servidor local, a fila e abre o navegador."""

import argparse
import functools
import sys
import webbrowser
from pathlib import Path

from . import fila as _fila
from . import runner
from .servidor import Servidor


PORTA_PADRAO = 8765


def criar(raiz, porta: int = 0, token=None, uploads=None, executar=None) -> Servidor:
    """Monta servidor + fila (a fila só começa a rodar em `iniciar`). `executar` entra por parâmetro nos testes."""
    raiz = Path(raiz)
    executar = executar or functools.partial(runner.executar, saida=raiz)
    fila = _fila.Fila(executar)
    return Servidor(("127.0.0.1", porta), raiz, fila, token=token, uploads=uploads)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="vatty ui", description="Abre a interface da Vatty no navegador (só neste computador).")
    p.add_argument("--saida", type=Path, default=Path("transcricoes"), help="pasta das transcrições (padrão: transcricoes/)")
    p.add_argument("--porta", type=int, default=PORTA_PADRAO, help="porta local (padrão: 8765; 0 escolhe uma livre)")
    p.add_argument("--sem-navegador", action="store_true", help="não abre o navegador sozinha")
    args = p.parse_args(argv)
    args.saida.mkdir(parents=True, exist_ok=True)
    try:
        srv = criar(args.saida, args.porta)
    except OSError as e:
        if args.porta == PORTA_PADRAO:  # outra Vatty (ou outro programa) já está nela: abre noutra porta
            print(f"A porta {PORTA_PADRAO} está ocupada (já tem uma Vatty aberta?). Abrindo noutra porta.")
            srv = criar(args.saida, 0)
        else:
            print(f"Erro: não consegui usar a porta {args.porta}: {e}. Tente --porta 0.", file=sys.stderr)
            return 1
    srv.fila.iniciar()
    print(f"Vatty de ouvido ligado. Abra: {srv.url}\nCtrl+C para fechar.")
    if not args.sem_navegador:
        webbrowser.open(srv.url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nAté mais!")
    finally:
        srv.fila.parar()
        srv.server_close()
    return 0
