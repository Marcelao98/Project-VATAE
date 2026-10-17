import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from vatty.ui import fila as f
from vatty.ui import runner


class ProcFalso:
    def __init__(self, saida: bytes, codigo=0):
        self.stdout, self.codigo, self.terminado = io.BytesIO(saida), codigo, False

    def wait(self):
        return self.codigo

    def terminate(self):
        self.terminado = True


def rodar(saida: bytes, codigo=0, cancelar_antes=False):
    proc = ProcFalso(saida, codigo)
    fila = f.Fila(lambda t, c: runner.executar(t, c, "transcricoes", popen=lambda *a, **k: proc))
    with tempfile.NamedTemporaryFile() as arq:
        t = fila.adicionar(arq.name)
        if cancelar_antes:
            fila._cancelar[t.id].set()
            t.estado = f.FILA  # cancelar() na fila tiraria na hora; aqui simula o pedido durante a execução
        fila.processar_um()
    return t, proc


class TestMontarArgv(unittest.TestCase):
    def test_entrada_que_parece_opcao_e_recusada(self):
        with self.assertRaises(runner.EntradaInvalida):
            runner.montar_argv("--saida=/etc", {}, "t")

    def test_link_e_opcoes_conhecidas(self):
        argv = runner.montar_argv("https://youtu.be/x", {"texto": "legenda", "falantes": "3", "lang": "en"}, "t")
        self.assertEqual(argv[3], "https://youtu.be/x")
        for par in (["--texto", "legenda"], ["--falantes", "3"], ["--lang", "en"], ["--preprocessar", "nao"]):
            i = argv.index(par[0])
            self.assertEqual(argv[i + 1], par[1])

    def test_opcao_invalida_vira_padrao_e_nao_passa(self):
        with tempfile.NamedTemporaryFile() as arq:
            argv = runner.montar_argv(arq.name, {"texto": "rm -rf", "falantes": "x;y", "lang": "pt; ls"}, "t")
        self.assertEqual(argv[argv.index("--texto") + 1], "whisper")
        self.assertNotIn("--falantes", argv)
        self.assertNotIn("--lang", argv)

    def test_login_do_navegador_so_se_for_conhecido(self):
        argv = runner.montar_argv("https://youtu.be/x", {"cookies": "firefox"}, "t")
        self.assertEqual(argv[argv.index("--cookies-navegador") + 1], "firefox")
        self.assertNotIn("--cookies-navegador", runner.montar_argv("https://youtu.be/x", {"cookies": "--x"}, "t"))

    def test_arquivo_inexistente(self):
        with self.assertRaises(runner.EntradaInvalida):
            runner.montar_argv("/nao/existe.opus", {}, "t")


class TestAmbiente(unittest.TestCase):
    def test_acha_o_pacote_e_forca_utf8_sem_buffer(self):
        env = runner.ambiente({"PYTHONPATH": "/x"})
        self.assertTrue((Path(env["PYTHONPATH"].split(":")[0]) / "vatty" / "cli.py").is_file())
        self.assertTrue(env["PYTHONPATH"].endswith("/x"))
        self.assertEqual((env["PYTHONIOENCODING"], env["PYTHONUNBUFFERED"]), ("utf-8", "1"))


class TestInterpretar(unittest.TestCase):
    def test_percentual_e_etapa(self):
        self.assertEqual(runner.interpretar("  62%  14:20 / 23:10"), (62, "Ouvindo"))
        self.assertEqual(runner.interpretar("Baixando o áudio..."), (None, "Baixando o áudio"))
        self.assertEqual(runner.interpretar("qualquer coisa"), (None, None))


class TestExecutar(unittest.TestCase):
    def test_acompanha_progresso_e_acha_a_pasta(self):
        saida = ("Transcrevendo a.opus...\n\r   5%  0:10 / 3:00\r  62%  1:50 / 3:00\r 100%  3:00 / 3:00\n"
                 "Pronto em 0:42 (texto de whisper, 180s de áudio): transcricoes/a\n").encode()
        t, _ = rodar(saida)
        self.assertEqual((t.estado, t.pasta, t.progresso), (f.PRONTO, "transcricoes/a", 100))
        self.assertTrue(any("Transcrevendo" in l for l in t.log))
        self.assertFalse(any("62%" in l for l in t.log))  # a barra de progresso não polui o log

    def test_codigo_de_saida_ruim_vira_erro_com_a_mensagem(self):
        t, _ = rodar("Erro: ffmpeg não encontrado\n".encode(), codigo=1)
        self.assertEqual((t.estado, t.erro), (f.ERRO, "Erro: ffmpeg não encontrado"))

    def test_sem_pasta_na_saida_e_erro(self):
        t, _ = rodar(b"Transcrevendo...\n")
        self.assertEqual(t.estado, f.ERRO)

    def test_pedido_de_agente_fica_anotado_na_pasta(self):
        with tempfile.TemporaryDirectory() as pasta:
            proc = ProcFalso(f"Pronto em 0:42 (texto de whisper, 180s de áudio): {pasta}\n".encode())
            fila = f.Fila(lambda t, c: runner.executar(t, c, "transcricoes", popen=lambda *a, **k: proc,
                                                       achar_claude=lambda: None))
            with tempfile.NamedTemporaryFile() as arq:
                t = fila.adicionar(arq.name, {"agentes": ["escrivao"], "objetivo": "juros"})
                fila.processar_um()
            self.assertEqual(t.estado, f.PRONTO)
            self.assertTrue((Path(pasta) / "pedidos.json").is_file())
            self.assertTrue(any("Claude Code não está instalado" in l for l in t.log))  # sem ele, só anota

    def test_com_claude_code_chama_os_agentes_e_falha_dele_nao_derruba_a_transcricao(self):
        with tempfile.TemporaryDirectory() as pasta:
            transcricao = ProcFalso(f"Pronto em 0:42 (texto de whisper, 180s de áudio): {pasta}\n".encode())
            agentes = ProcFalso(b'{"type":"result","is_error":true,"result":"Not logged in"}\n', codigo=1)
            agentes.stdin = io.BytesIO()
            chamadas = []

            def popen(argv, **k):
                chamadas.append(argv)
                return transcricao if len(chamadas) == 1 else agentes

            fila = f.Fila(lambda t, c: runner.executar(t, c, "transcricoes", popen=popen, achar_claude=lambda: "claude"))
            with tempfile.NamedTemporaryFile() as arq:
                t = fila.adicionar(arq.name, {"agentes": ["perito"]})
                fila.processar_um()
            self.assertEqual(t.estado, f.PRONTO)  # o texto está salvo mesmo com o erro dos agentes
            self.assertEqual(chamadas[1][:2], ["claude", "-p"])
            self.assertIn("Erro dos agentes: Not logged in", t.log)
            self.assertTrue(any(l.startswith("Aviso: os agentes não terminaram") for l in t.log))

    def test_slides_pedidos_sem_visual_viram_aviso_e_nao_erro(self):
        with tempfile.TemporaryDirectory() as pasta:
            proc = ProcFalso(f"Pronto em 0:42 (texto de whisper, 180s de áudio): {pasta}\n".encode())
            fila = f.Fila(lambda t, c: runner.executar(t, c, "transcricoes", popen=lambda *a, **k: proc))
            with tempfile.NamedTemporaryFile() as arq:
                t = fila.adicionar(arq.name, {"slides": True})
                fila.processar_um()
            self.assertEqual(t.estado, f.PRONTO)
            self.assertTrue(any(l.startswith("Aviso: sem slides") for l in t.log))

    def test_cancelar_derruba_o_processo(self):
        t, proc = rodar(b"Transcrevendo...\nmais uma\n", cancelar_antes=True)
        self.assertEqual(t.estado, f.CANCELADO)
        self.assertTrue(proc.terminado)


if __name__ == "__main__":
    unittest.main()
