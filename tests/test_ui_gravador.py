import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from vatty.ui import gravador as g
from vatty.ui import pedidos

MEDIDOR = "\r  1:05  sistema [####....]  microfone [##......]  "


class ProcFalso:
    """stdout é um cano: o teste escreve as linhas quando quer e fecha para o processo "acabar"."""

    def __init__(self, codigo=0):
        r, w = os.pipe()
        self.stdout, self._w, self.codigo, self.argv = os.fdopen(r, "rb"), os.fdopen(w, "wb"), codigo, None

    def __call__(self, argv, **kw):
        self.argv = argv
        return self

    def escrever(self, texto: str, fechar=False):
        self._w.write(texto.encode())
        self._w.flush()
        if fechar:
            self._w.close()

    def wait(self):
        return self.codigo


class FilaFalsa:
    def __init__(self):
        self.adicionados = []

    def adicionar(self, entrada, opcoes):
        self.adicionados.append((entrada, opcoes))
        return SimpleNamespace(id="t1")


class TestMontarELer(unittest.TestCase):
    def test_argv_so_com_o_que_foi_pedido(self):
        audio = g.montar_argv({"microfone": True}, "gr", "parar", python="py")
        self.assertEqual(audio, ["py", "-m", "vatty.cli", "gravar", "--gravacoes", "gr", "--parar-com", "parar", "--mic"])
        janela = g.montar_argv({"tela": True, "janela": "  Bloco   de notas "}, "gr", "parar", python="py")
        self.assertEqual(janela[-2:], ["--tela-janela", "Bloco de notas"])
        self.assertNotIn("--tela", janela)
        self.assertEqual(g.montar_argv({"tela": True}, "gr", "parar")[-1], "--tela")

    def test_ler_linha_do_medidor(self):
        self.assertEqual(g.ler_linha(MEDIDOR), {"decorrido": 65, "niveis": {"sistema": 0.5, "microfone": 0.25}})
        self.assertEqual(g.ler_linha("  1:02:03  sistema [########]")["decorrido"], 3723)
        self.assertIsNone(g.ler_linha("Gravando. Ctrl+C para parar."))


class TestGravador(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.proc, self.fila = ProcFalso(), FilaFalsa()
        self.grav = g.Gravador(self.tmp / "gravacoes", self.fila, popen=self.proc, pasta_temporaria=self.tmp)

    def test_grava_para_pelo_arquivo_e_poe_a_transcricao_na_fila(self):
        pedido = {"microfone": True, "tela": True, "perfil": "aula", "opcoes": {"agentes": ["secretario"]}}
        self.assertEqual(self.grav.iniciar(pedido)["estado"], g.GRAVANDO)
        with self.assertRaisesRegex(ValueError, "Já tem"):
            self.grav.iniciar(pedido)
        self.proc.escrever("Aviso: a tela também vai ser gravada.\n" + MEDIDOR)
        parar_com = Path(self.proc.argv[self.proc.argv.index("--parar-com") + 1])
        self.assertEqual(self.grav.parar()["estado"], g.PARANDO)
        self.assertTrue(parar_com.exists())  # é assim que a CLI fica sabendo
        self.proc.escrever("\nGravado: 1:05 em gravacoes/2026-10-17_10-00\n", fechar=True)
        self.grav._thread.join(5)
        r = self.grav.resumo()
        self.assertEqual((r["estado"], r["trabalho"], r["decorrido"]), (g.PRONTO, "t1", 65))
        self.assertIn("Aviso: a tela também vai ser gravada.", r["log"])
        self.assertEqual(self.fila.adicionados, [("gravacoes/2026-10-17_10-00", {"agentes": ["secretario"], "visual": "aula"})])
        self.assertFalse(parar_com.exists())

    def test_erro_da_cli_aparece_e_nada_vai_para_a_fila(self):
        self.proc.codigo = 1
        self.grav.iniciar({})
        self.proc.escrever("\nErro: a gravação só funciona no Windows por enquanto.\n", fechar=True)
        self.grav._thread.join(5)
        self.assertEqual(self.grav.resumo()["erro"], "Erro: a gravação só funciona no Windows por enquanto.")
        self.assertEqual(self.fila.adicionados, [])
        with self.assertRaisesRegex(ValueError, "Não tem"):
            self.grav.parar()


class TestPedidos(unittest.TestCase):
    def test_anota_so_agentes_conhecidos_sem_repetir_e_acumula(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(pedidos.registrar(tmp, ["nada"]), [])
            self.assertFalse((Path(tmp) / "pedidos.json").exists())
            self.assertEqual(pedidos.registrar(tmp, ["perito", "perito", "x"], "  testar   o login ", agora=lambda: 0), ["perito"])
            pedidos.registrar(tmp, ["secretario"])
            lista = json.loads((Path(tmp) / "pedidos.json").read_text(encoding="utf-8"))
            self.assertEqual([(p["agente"], p["estado"]) for p in lista], [("perito", "pendente"), ("secretario", "pendente")])
            self.assertEqual(lista[0]["objetivo"], "testar o login")


if __name__ == "__main__":
    unittest.main()
