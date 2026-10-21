import io
import json
import unittest
from types import SimpleNamespace

from vatty.ui import claude


class ProcFalso:
    def __init__(self, saida: bytes):
        self.stdout, self.stdin, self.terminado = io.BytesIO(saida), io.BytesIO(), False
        self.stdin.close = lambda: None  # o teste lê o que foi escrito depois

    def wait(self):
        return 0

    def terminate(self):
        self.terminado = True


def _evento(**kw):
    return json.dumps(kw)


class TestClaude(unittest.TestCase):
    def test_argv_so_le_e_escreve_e_o_pedido_vai_pelo_stdin(self):
        argv = claude.montar_argv("claude", "/t/aula")
        self.assertEqual(argv[:2], ["claude", "-p"])
        ferramentas = argv[argv.index("--allowedTools") + 1]
        self.assertNotIn("Bash", ferramentas)
        self.assertIn("Write", ferramentas)
        self.assertNotIn("pedidos.json", " ".join(argv))  # o pedido não vai como argumento
        self.assertIn("pedidos.json", claude.pedido("/t/aula"))

    def test_resumir_o_stream(self):
        chamar = _evento(type="assistant", message={"content": [
            {"type": "tool_use", "name": "Task", "input": {"subagent_type": "perito"}}]})
        escrever = _evento(type="assistant", message={"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": "/t/aula/pericia-login.md"}}]})
        self.assertEqual(claude.resumir(chamar), "Chamando o agente perito...")
        self.assertEqual(claude.resumir(escrever), "Escrevendo pericia-login.md")
        self.assertEqual(claude.resumir(_evento(type="result", result="perito: pericia-login.md")), "Agentes: perito: pericia-login.md")
        self.assertIsNone(claude.resumir(_evento(type="system", subtype="init")))
        self.assertIsNone(claude.resumir("não é json"))

    def test_rodar_manda_o_pedido_e_mostra_o_andamento(self):
        saida = (_evento(type="assistant", message={"content": [{"type": "tool_use", "name": "Agent", "input": {"subagent_type": "escrivao"}}]})
                 + "\nInvalid API key\n").encode()
        proc, log, etapas = ProcFalso(saida), [], []
        ctx = SimpleNamespace(cancelado=False, log=log.append, progresso=lambda p, e: etapas.append(e))
        codigo = claude.rodar("/t/aula", ctx, "claude", popen=lambda argv, **kw: proc, cwd="/projeto")
        self.assertEqual(codigo, 0)
        self.assertEqual(log, ["Chamando o agente escrivao...", "Invalid API key"])
        self.assertEqual(etapas, ["Agentes trabalhando"])
        self.assertIn(b"pedidos.json", proc.stdin.getvalue())

    def test_claude_que_trava_e_encerrado_no_limite(self):
        import os
        r, w = os.pipe()
        escrita = os.fdopen(w, "wb")

        class Travado(ProcFalso):
            def __init__(self):
                super().__init__(b"")
                self.stdout = os.fdopen(r, "rb")

            def kill(self):
                escrita.close()  # o cano fecha: a leitura termina, como num processo morto

            def wait(self):
                return -9

        log = []
        ctx = SimpleNamespace(cancelado=False, log=log.append, progresso=lambda p, e: None)
        codigo = claude.rodar("/t/aula", ctx, "claude", popen=lambda argv, **kw: Travado(), cwd="/p", limite_s=0.05)
        self.assertEqual(codigo, -9)
        self.assertTrue(any("foi encerrado" in l for l in log))


if __name__ == "__main__":
    unittest.main()
