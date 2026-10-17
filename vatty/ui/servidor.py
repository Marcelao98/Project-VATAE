"""
Servidor local da interface (biblioteca padrão, sem dependência extra).

Segurança: escuta só em 127.0.0.1, exige um token por sessão (cabeçalho ou `?t=`) em toda rota da API,
confere o cabeçalho Host (contra DNS rebinding) e nunca devolve arquivo fora da raiz de trabalho.
"""

import json
import mimetypes
import queue
import re
import secrets
import shutil
import socket
import sys
import tempfile
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .. import buscar as _buscar
from . import biblioteca, claude, gravador as _gravador, pedidos, prompts, revisao, runner, saude, terminal

ESTATICOS = Path(__file__).parent / "static"
UPLOAD_MAX = 8 * 1024 ** 3
CORPO_JSON_MAX = 1024 * 1024
RE_NOME = re.compile(r"[^\w.\- ]+")


def nome_seguro(nome: str) -> str:
    """Nome de arquivo de upload sem pasta e sem caracteres estranhos."""
    base = RE_NOME.sub("_", Path(nome or "").name).strip(" .") or "arquivo"
    return base[:120]


ARQUIVO_ERROS = "vatty-ui-erros.log"


class Servidor(ThreadingHTTPServer):
    daemon_threads = True
    # No Windows, SO_REUSEADDR deixa DUAS Vattys abrirem a mesma porta: o navegador falava ora com uma,
    # ora com outra (token inválido, "Failed to fetch"). Lá a porta é exclusiva; no Linux/Mac fica como era.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def registrar_erro(self, onde: str) -> None:
        """Erro inesperado de um pedido: vai para vatty-ui-erros.log (ao lado de transcricoes/) para diagnóstico."""
        try:
            with open(self.raiz.resolve().parent / ARQUIVO_ERROS, "a", encoding="utf-8") as f:
                f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} {onde}\n{traceback.format_exc()}\n")
        except OSError:
            pass

    def __init__(self, endereco, raiz, fila, token=None, uploads=None, handler=None, gravador=None):
        super().__init__(endereco, handler or Handler)
        self.raiz = Path(raiz)
        self.fila = fila
        # as gravações ficam ao lado das transcrições (gravacoes/ e transcricoes/), como na CLI
        self.gravador = gravador or _gravador.Gravador(self.raiz.resolve().parent / "gravacoes", fila)
        self.token = token or secrets.token_urlsafe(18)
        self.uploads = Path(uploads) if uploads else Path(tempfile.gettempdir()) / "vatty-uploads"
        self.uploads.mkdir(parents=True, exist_ok=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/?t={self.token}"


class Handler(BaseHTTPRequestHandler):
    server: Servidor
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # silencioso: o terminal é da Vatty, não do servidor
        pass

    # --- utilidades ---
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _consulta(self) -> dict:
        return parse_qs(urlparse(self.path).query)

    def _token_ok(self) -> bool:
        dado = self.headers.get("X-Vatty-Token") or (self._consulta().get("t") or [""])[0]
        return secrets.compare_digest(dado, self.server.token)

    def _json(self, dados, status=200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _erro(self, status: int, msg: str) -> None:
        self._json({"erro": msg}, status)

    def _corpo_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > CORPO_JSON_MAX:
            raise ValueError("Corpo grande demais.")
        bruto = self.rfile.read(n)
        self._corpo_lido = True
        try:
            dados = json.loads(bruto or b"{}")
        except ValueError:
            raise ValueError("JSON inválido.")
        if not isinstance(dados, dict):
            raise ValueError("Esperava um objeto JSON.")
        return dados

    def _arquivo(self, caminho: Path, nome: str | None = None, tipo: str | None = None) -> None:
        tam = caminho.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", tipo or mimetypes.guess_type(caminho.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(tam))
        if nome and nome.endswith(".html"):
            # abre na aba (os slides), mas isolado: sandbox = origem própria, sem acesso à API da Vatty
            self.send_header("Content-Security-Policy", "sandbox allow-scripts")
        elif nome:
            self.send_header("Content-Disposition", f'attachment; filename="{nome}"')
        self.end_headers()
        with open(caminho, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    # --- roteamento ---
    def do_GET(self):
        try:
            self._rotear("GET")
        except Exception:
            self.server.registrar_erro(f"GET {self.path.split('?')[0]}")
            raise

    def do_POST(self):
        self._corpo_lido = False
        try:
            self._rotear("POST")
        except Exception:
            self.server.registrar_erro(f"POST {self.path.split('?')[0]}")
            raise
        if not self._corpo_lido:  # rota que não usa o corpo: ele não pode sobrar na conexão (viraria "{}GET")
            n = int(self.headers.get("Content-Length") or 0)
            if 0 < n <= CORPO_JSON_MAX:
                self.rfile.read(n)
            elif n:
                self.close_connection = True

    def _rotear(self, metodo: str) -> None:
        if not self._host_ok():
            return self._erro(403, "Host não permitido.")
        caminho = unquote(urlparse(self.path).path)
        try:
            if metodo == "GET" and (caminho == "/" or caminho.startswith("/static/")):
                return self._estatico(caminho)
            if not caminho.startswith("/api/"):
                return self._erro(404, "Não achei.")
            if not self._token_ok():
                return self._erro(401, "Token inválido. Abra o endereço que a Vatty mostrou no terminal.")
            partes = caminho[5:].strip("/").split("/")
            self._api(metodo, partes)
        except biblioteca.NaoAchei:
            self._erro(404, "Não achei.")
        except (ValueError, runner.EntradaInvalida, terminal.ComandoInvalido, revisao.Invalido) as e:
            self._erro(400, str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # nunca derruba o servidor por causa de um pedido
            self.server.registrar_erro(f"{metodo} {caminho}")
            self._erro(500, f"Erro interno: {e}")

    def _estatico(self, caminho: str) -> None:
        nome = "index.html" if caminho == "/" else caminho[len("/static/"):]
        alvo = (ESTATICOS / nome).resolve()
        if ESTATICOS.resolve() not in alvo.parents or not alvo.is_file():
            return self._erro(404, "Não achei.")
        self._arquivo(alvo)

    def _api(self, metodo: str, p: list) -> None:
        s = self.server
        if metodo == "GET" and p == ["estado"]:
            return self._json({"raiz": str(s.raiz), "trabalhos": s.fila.trabalhos()})
        if metodo == "GET" and p == ["saude"]:
            return self._json(saude.checar())
        if metodo == "GET" and p == ["biblioteca"]:
            return self._json(biblioteca.listar(s.raiz))
        if metodo == "GET" and p[0] == "video" and len(p) == 2:
            return self._json(biblioteca.ler(s.raiz, p[1]))
        if metodo == "GET" and p == ["buscar"]:
            q = (self._consulta().get("q") or [""])[0]
            return self._json([a.__dict__ for a in _buscar.buscar(q, s.raiz)])
        if metodo == "GET" and p[0] == "exportar" and len(p) == 3:
            dados, tipo, nome = biblioteca.exportar(s.raiz, p[1], p[2])
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Content-Disposition", f'attachment; filename="{nome}"')
            self.end_headers()
            self.wfile.write(dados)
            return
        if metodo == "GET" and p[0] == "arquivo" and len(p) == 3:
            return self._arquivo(biblioteca.arquivo_gerado(s.raiz, p[1], p[2]), nome=p[2])
        if metodo == "GET" and p == ["agentes"]:
            return self._json({"claude": bool(claude.achar()), "lista": pedidos.lista()})
        if metodo == "GET" and p == ["gravacao"]:
            return self._json(s.gravador.resumo())
        if metodo == "POST" and p == ["gravacao"]:
            return self._json(s.gravador.iniciar(self._corpo_json()))
        if metodo == "POST" and p == ["gravacao", "parar"]:
            return self._json(s.gravador.parar())
        if metodo == "GET" and p == ["prompts"]:
            return self._json(prompts.tipos())
        if metodo == "GET" and p[0] == "video" and len(p) == 3 and p[2] == "prompt":
            tipo = (self._consulta().get("tipo") or [""])[0]
            foco = (self._consulta().get("foco") or [""])[0]
            titulo, texto, origem = biblioteca.texto_para_prompt(s.raiz, p[1])
            try:
                return self._json({"prompt": prompts.montar(tipo, titulo, texto, origem, foco), "aviso": prompts.AVISO})
            except KeyError:
                raise ValueError("Tipo de prompt desconhecido.")
        if metodo == "POST" and p[0] == "video" and len(p) == 3 and p[2] == "corrigir":
            c = self._corpo_json()
            return self._json(revisao.corrigir(s.raiz, p[1], c.get("errado"), c.get("certo"), bool(c.get("guardar"))))
        if metodo == "POST" and p[0] == "video" and len(p) == 3 and p[2] == "nomes":
            nomes = self._corpo_json().get("nomes")
            if not isinstance(nomes, dict):
                raise ValueError("Mande 'nomes' como objeto: {\"Pessoa 1\": \"Ana\"}.")
            return self._json({"nomes": revisao.dar_nomes(s.raiz, p[1], nomes)})
        if metodo == "GET" and p == ["eventos"]:
            return self._eventos()
        if metodo == "GET" and p[0] == "trabalhos" and len(p) == 3 and p[2] == "log":
            t = s.fila.trabalho(p[1])
            if not t:
                raise biblioteca.NaoAchei(p[1])
            return self._json({"log": t.log})
        if metodo == "POST" and p == ["trabalhos"]:
            return self._novos_trabalhos(self._corpo_json())
        if metodo == "POST" and p[0] == "trabalhos" and len(p) == 3 and p[2] == "cancelar":
            return self._json({"ok": s.fila.cancelar(p[1])})
        if metodo == "POST" and p[0] == "trabalhos" and len(p) == 3 and p[2] == "repetir":
            novo = s.fila.repetir(p[1])
            return self._json({"ok": bool(novo), "id": novo.id if novo else None})
        if metodo == "POST" and p == ["upload"]:
            return self._upload()
        if metodo == "POST" and p == ["comando"]:
            return self._json(terminal.rodar(str(self._corpo_json().get("linha", "")), s.raiz))
        self._erro(404, "Não achei.")

    def _novos_trabalhos(self, corpo: dict) -> None:
        entradas = corpo.get("entradas")
        if not isinstance(entradas, list) or not entradas:
            raise ValueError("Mande a lista 'entradas' com pelo menos um link ou arquivo.")
        opcoes = corpo.get("opcoes") if isinstance(corpo.get("opcoes"), dict) else {}
        criados, recusados = [], []
        for e in entradas[:500]:
            try:
                runner.validar_entrada(str(e))
                criados.append(self.server.fila.adicionar(str(e), opcoes).resumo())
            except (ValueError, runner.EntradaInvalida) as erro:
                recusados.append({"entrada": str(e), "erro": str(erro)})
        self._json({"criados": criados, "recusados": recusados}, 200 if criados else 400)

    def _upload(self) -> None:
        nome = nome_seguro((self._consulta().get("nome") or [""])[0])
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > UPLOAD_MAX:
            raise ValueError("Tamanho do arquivo inválido.")
        destino = self.server.uploads / f"{secrets.token_hex(4)}-{nome}"
        restante = n
        with open(destino, "wb") as f:
            while restante:
                bloco = self.rfile.read(min(1024 * 1024, restante))
                if not bloco:
                    break
                f.write(bloco)
                restante -= len(bloco)
        self._corpo_lido = True
        if restante:
            destino.unlink(missing_ok=True)
            raise ValueError("Envio interrompido.")
        self._json({"caminho": str(destino), "nome": nome})

    def _eventos(self) -> None:
        q = self.server.fila.assinar()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for t in self.server.fila.trabalhos():
                self._sse({"tipo": "trabalho", "trabalho": t})
            while True:
                try:
                    self._sse(q.get(timeout=15))
                except queue.Empty:
                    self.wfile.write(b": batimento\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.server.fila.desassinar(q)

    def _sse(self, evento: dict) -> None:
        self.wfile.write(f"data: {json.dumps(evento, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.flush()
