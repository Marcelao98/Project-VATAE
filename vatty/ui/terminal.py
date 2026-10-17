"""
Terminal da interface: roda só subcomandos `vatty` conhecidos (nada de shell livre).

Quem alcançasse a página não pode executar comandos quaisquer no computador: a linha é separada com
`shlex`, o primeiro termo tem de estar na lista e os caminhos têm de ficar dentro da raiz de trabalho.
"""

import shlex
import subprocess
import sys
from pathlib import Path

from .runner import ambiente

PERMITIDOS = ("buscar", "legenda", "slides", "corrigir", "ata", "cartoes", "traduzir", "perguntar")
TEMPO_MAX_S = 180
SAIDA_MAX = 20000


class ComandoInvalido(ValueError):
    pass


def montar(linha: str, raiz, python: str = sys.executable) -> list:
    """'buscar margem' -> [python, -m, vatty.cli, buscar, margem, --raiz, <raiz>]. Erro se não for permitido."""
    try:
        partes = shlex.split(linha)
    except ValueError as e:
        raise ComandoInvalido(f"Não entendi a linha: {e}")
    if partes and partes[0] == "vatty":
        partes = partes[1:]
    if not partes:
        raise ComandoInvalido("Digite um comando, por exemplo: buscar margem")
    if partes[0] not in PERMITIDOS:
        raise ComandoInvalido(f"Aqui só roda: {', '.join(PERMITIDOS)}. Para transcrever, use Importar.")
    raiz = Path(raiz).resolve()
    for p in partes[1:]:
        if p.startswith("-") or not (Path(p).is_absolute() or ".." in Path(p).parts or "/" in p or "\\" in p):
            continue
        alvo = (raiz / p).resolve() if not Path(p).is_absolute() else Path(p).resolve()
        if alvo != raiz and raiz not in alvo.parents:
            raise ComandoInvalido(f"O caminho {p} está fora da pasta de trabalho.")
    argv = [python, "-m", "vatty.cli", *partes]
    if partes[0] in ("buscar", "perguntar") and "--raiz" not in partes:
        argv += ["--raiz", str(raiz)]
    return argv


def rodar(linha: str, raiz, executar=subprocess.run) -> dict:
    """Roda o comando e devolve {codigo, saida}. A saída é cortada para não encher a tela."""
    argv = montar(linha, raiz)
    try:
        r = executar(argv, capture_output=True, text=True, timeout=TEMPO_MAX_S, cwd=str(Path(raiz).parent),
                     stdin=subprocess.DEVNULL, errors="replace", encoding="utf-8", env=ambiente())
    except subprocess.TimeoutExpired:
        return {"codigo": 124, "saida": f"Passou de {TEMPO_MAX_S}s e foi interrompido."}
    saida = (r.stdout or "") + (r.stderr or "")
    return {"codigo": r.returncode, "saida": saida[-SAIDA_MAX:]}
