import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from vatty.ui import fila as f
from vatty.ui import servidor, terminal


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name) / "transcricoes"
        self.raiz.mkdir()
        self.fila = f.Fila(lambda t, c: "transcricoes/x")
        self.srv = servidor.Servidor(("127.0.0.1", 0), self.raiz, self.fila, token="segredo", uploads=Path(self.tmp.name) / "up")
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def chamar(self, caminho, corpo=None, token="segredo", metodo=None, host=None, bruto=None):
        dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
        req = urllib.request.Request(self.base + caminho, data=dados, method=metodo or ("POST" if dados is not None else "GET"))
        if token:
            req.add_header("X-Vatty-Token", token)
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()


class TestSeguranca(Base):
    def test_api_sem_token_ou_com_token_errado_e_401(self):
        self.assertEqual(self.chamar("/api/estado", token=None)[0], 401)
        self.assertEqual(self.chamar("/api/estado", token="errado")[0], 401)
        self.assertEqual(self.chamar("/api/estado")[0], 200)

    def test_token_tambem_vale_na_url_para_downloads(self):
        self.assertEqual(self.chamar("/api/biblioteca?t=segredo", token=None)[0], 200)

    def test_host_estranho_e_recusado(self):
        self.assertEqual(self.chamar("/api/estado", host="evil.com")[0], 403)

    def test_saude_lista_as_checagens(self):
        falso = [{"id": "ffmpeg", "nome": "ffmpeg", "ok": False, "nivel": "essencial", "ajuda": "instale"}]
        with mock.patch("vatty.ui.saude.checar", return_value=falso):
            dados = json.loads(self.chamar("/api/saude")[1])
        self.assertEqual(dados, falso)

    def test_pagina_inicial_nao_exige_token(self):
        self.assertEqual(self.chamar("/", token=None)[0], 200)

    def test_estatico_nao_sai_da_pasta(self):
        self.assertEqual(self.chamar("/static/../servidor.py", token=None)[0], 404)
        self.assertEqual(self.chamar("/static/%2e%2e/servidor.py", token=None)[0], 404)


class TestTrabalhos(Base):
    def test_cria_valida_e_recusa(self):
        arq = Path(self.tmp.name) / "a.opus"
        arq.write_bytes(b"x")
        status, corpo = self.chamar("/api/trabalhos", {"entradas": [str(arq), "--evil", "/nao/existe"]})
        dados = json.loads(corpo)
        self.assertEqual((status, len(dados["criados"]), len(dados["recusados"])), (200, 1, 2))
        self.assertEqual(json.loads(self.chamar("/api/estado")[1])["trabalhos"][0]["estado"], "fila")

    def test_corpo_que_a_rota_nao_le_nao_sobra_na_conexao(self):
        import http.client
        con = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=5)
        cab = {"X-Vatty-Token": "segredo", "Content-Type": "application/json"}
        con.request("POST", "/api/trabalhos/nao-existe/cancelar", body="{}", headers=cab)
        con.getresponse().read()
        con.request("GET", "/api/estado", headers=cab)  # mesma conexão: antes chegava como "{}GET" e dava 501
        self.assertEqual(con.getresponse().status, 200)
        con.close()

    def test_lista_vazia_e_400(self):
        self.assertEqual(self.chamar("/api/trabalhos", {"entradas": []})[0], 400)

    def test_cancelar(self):
        arq = Path(self.tmp.name) / "a.opus"
        arq.write_bytes(b"x")
        id_ = json.loads(self.chamar("/api/trabalhos", {"entradas": [str(arq)]})[1])["criados"][0]["id"]
        self.assertTrue(json.loads(self.chamar(f"/api/trabalhos/{id_}/cancelar", {})[1])["ok"])

    def test_upload_guarda_com_nome_seguro(self):
        status, corpo = self.chamar("/api/upload?nome=../../etc/pass%20wd.opus", bruto=b"abc")
        caminho = Path(json.loads(corpo)["caminho"])
        self.assertEqual(status, 200)
        self.assertEqual(caminho.parent, self.srv.uploads)
        self.assertEqual(caminho.read_bytes(), b"abc")
        self.assertEqual(servidor.nome_seguro("../../x/y.opus"), "y.opus")


class TestGravacaoNaApi(Base):
    def test_agentes_e_gravar_parar(self):
        from vatty.ui import gravador
        from test_ui_gravador import ProcFalso
        proc = ProcFalso()
        self.srv.gravador = gravador.Gravador(Path(self.tmp.name) / "gravacoes", self.fila, popen=proc,
                                              pasta_temporaria=self.tmp.name)
        status, corpo = self.chamar("/api/agentes")
        self.assertIn("perito", [a["id"] for a in json.loads(corpo)["lista"]])
        self.assertEqual(json.loads(self.chamar("/api/gravacao")[1])["estado"], "parado")
        self.assertEqual(json.loads(self.chamar("/api/gravacao", {"microfone": True})[1])["estado"], "gravando")
        self.assertEqual(json.loads(self.chamar("/api/gravacao/parar", {})[1])["estado"], "parando")
        self.assertEqual(self.chamar("/api/gravacao/parar", {})[0], 400)  # já está parando
        proc.escrever("Gravado: 0:01 em x\n", fechar=True)
        self.srv.gravador._thread.join(5)


class TestRobustez(Base):
    def test_erro_inesperado_vira_500_e_fica_no_log(self):
        with mock.patch.object(servidor.biblioteca, "listar", side_effect=RuntimeError("quebrou")):
            status, corpo = self.chamar("/api/biblioteca")
        self.assertEqual(status, 500)
        log = (Path(self.tmp.name) / servidor.ARQUIVO_ERROS).read_text(encoding="utf-8")
        self.assertIn("GET /api/biblioteca", log)
        self.assertIn("RuntimeError: quebrou", log)

    def test_link_recusado_explica_o_motivo(self):
        status, corpo = self.chamar("/api/trabalhos", {"entradas": ["não é link"]})
        self.assertEqual(status, 400)
        self.assertIn("Não achei o arquivo nem entendi o link", json.loads(corpo)["recusados"][0]["erro"])

    def test_porta_ocupada_abre_noutra(self):
        from vatty.ui import app
        portas = []

        class SrvFalso:
            url = "http://127.0.0.1:1/?t=x"
            fila = mock.Mock()

            def serve_forever(self):
                raise KeyboardInterrupt

            def server_close(self):
                pass

        def criar(raiz, porta):
            portas.append(porta)
            if porta == app.PORTA_PADRAO:
                raise OSError("porta em uso")
            return SrvFalso()

        with mock.patch.object(app, "criar", criar), mock.patch("sys.stdout"):
            self.assertEqual(app.main(["--saida", str(self.raiz), "--sem-navegador"]), 0)
        self.assertEqual(portas, [app.PORTA_PADRAO, 0])


class TestEventos(Base):
    def test_sse_manda_o_estado_atual_e_depois_as_mudancas(self):
        t = self.fila.adicionar("a.opus")
        req = urllib.request.Request(self.base + "/api/eventos?t=segredo")
        with urllib.request.urlopen(req, timeout=5) as r:
            primeira = r.readline().decode()
            self.assertTrue(primeira.startswith("data: "))
            self.assertEqual(json.loads(primeira[6:])["trabalho"]["id"], t.id)
            r.readline()
            self.fila.cancelar(t.id)
            novo = json.loads(r.readline().decode()[6:])
            self.assertEqual(novo["trabalho"]["estado"], "cancelado")


class TestBiblioteca(Base):
    def _video(self):
        p = self.raiz / "aula"
        p.mkdir()
        (p / "fonte.json").write_text('{"titulo": "Aula"}')
        (p / "transcricao.json").write_text('{"origem":"whisper","segmentos":[{"inicio":1,"fim":2,"texto":"margem"}]}')
        (p / "transcricao.txt").write_text("[00:01] a margem sobe\n")

    def test_lista_le_busca_e_exporta(self):
        self._video()
        self.assertEqual(json.loads(self.chamar("/api/biblioteca")[1])[0]["slug"], "aula")
        self.assertEqual(json.loads(self.chamar("/api/video/aula")[1])["paragrafos"][0]["inicio_s"], 1)
        self.assertEqual(len(json.loads(self.chamar("/api/buscar?q=margem")[1])), 1)
        status, corpo = self.chamar("/api/exportar/aula/srt")
        self.assertIn(b"00:00:01,000", corpo)

    def test_slug_com_fuga_e_404(self):
        self._video()
        self.assertEqual(self.chamar("/api/video/..%2F..")[0], 404)
        self.assertEqual(self.chamar("/api/exportar/aula/exe")[0], 404)


class TestRevisaoNaApi(Base):
    def _video(self):
        p = self.raiz / "aula"
        p.mkdir()
        (p / "fonte.json").write_text('{"titulo": "Aula", "tipo": "arquivo"}')
        (p / "transcricao.json").write_text(json.dumps({"origem": "whisper", "segmentos": [
            {"inicio": 0, "fim": 1, "texto": "oi natty", "pessoa": "Pessoa 1"}]}))
        (p / "transcricao.txt").write_text("[00:00] Pessoa 1: oi natty\n")

    def test_corrigir_nomes_e_prompt(self):
        self._video()
        r = json.loads(self.chamar("/api/video/aula/corrigir", {"errado": "natty", "certo": "Nattie", "guardar": True})[1])
        self.assertEqual(r["vezes"], 1)
        self.assertEqual(self.chamar("/api/video/aula/corrigir", {"errado": "", "certo": "x"})[0], 400)
        self.assertEqual(json.loads(self.chamar("/api/video/aula/nomes", {"nomes": {"Pessoa 1": "Ana"}})[1])["nomes"], {"Pessoa 1": "Ana"})
        corpo = json.loads(self.chamar("/api/video/aula/prompt?tipo=ata&foco=prazos")[1])
        self.assertIn("Ana: oi Nattie", corpo["prompt"])
        self.assertIn("aviso", corpo)
        self.assertEqual(self.chamar("/api/video/aula/prompt?tipo=zzz")[0], 400)
        self.assertEqual(len(json.loads(self.chamar("/api/prompts")[1])), 6)


class TestSlidesNaApi(Base):
    _video = TestRevisaoNaApi._video

    def test_gera_slides_so_com_visual(self):
        self._video()
        self.assertFalse(json.loads(self.chamar("/api/video/aula")[1])["tem_visual"])
        self.assertEqual(self.chamar("/api/video/aula/slides", {})[0], 400)   # sem visual.json: erro legível
        (self.raiz / "aula" / "visual.json").write_text("{}")
        with mock.patch("vatty.slides.gerar", return_value=[self.raiz / "aula" / "slides.html"]) as gerar:
            codigo, corpo = self.chamar("/api/video/aula/slides", {})
        self.assertEqual((codigo, json.loads(corpo)), (200, {"gerados": ["slides.html"]}))
        self.assertEqual(gerar.call_args[0][0], (self.raiz / "aula").resolve())
        self.assertEqual(self.chamar("/api/video/nada/slides", {})[0], 404)


class TestTerminal(unittest.TestCase):
    def test_so_subcomandos_permitidos(self):
        with tempfile.TemporaryDirectory() as d:
            for ruim in ("rm -rf /", "ls", "python -c 1", "ata ../../etc", "buscar 'aberto"):
                with self.assertRaises(terminal.ComandoInvalido):
                    terminal.montar(ruim, d)
            argv = terminal.montar("vatty buscar margem", d)
            self.assertEqual(argv[3:5], ["buscar", "margem"])
            self.assertIn("--raiz", argv)

    def test_caminho_dentro_da_raiz_passa(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(terminal.montar("legenda aula", d)[3:5], ["legenda", "aula"])

    def test_rodar_corta_a_saida_e_devolve_codigo(self):
        from types import SimpleNamespace
        r = terminal.rodar("buscar x", ".", executar=lambda *a, **k: SimpleNamespace(returncode=0, stdout="o" * 30000, stderr=""))
        self.assertEqual((r["codigo"], len(r["saida"])), (0, terminal.SAIDA_MAX))


if __name__ == "__main__":
    unittest.main()
