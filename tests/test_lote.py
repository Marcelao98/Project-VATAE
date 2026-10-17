import json
import tempfile
import unittest
from pathlib import Path

from vatty import lote


class TestLerLista(unittest.TestCase):
    def test_ignora_vazias_comentarios_e_repetidas(self):
        self.assertEqual(lote.ler_lista("# meus\n\nhttps://a\n  https://b  \nhttps://a\n"), ["https://a", "https://b"])


class TestEntradas(unittest.TestCase):
    def test_link_usa_o_listador_e_arquivo_le_as_linhas(self):
        self.assertEqual(lote.entradas_da_fonte("https://x/playlist", listar=lambda u: ("T", ["v1", "v2"])), ["v1", "v2"])
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("a.opus\n#c\nb.opus\n")
        try:
            self.assertEqual(lote.entradas_da_fonte(f.name), ["a.opus", "b.opus"])
        finally:
            Path(f.name).unlink()

    def test_lista_vazia_ou_inexistente_e_erro(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("# só comentário\n")
        try:
            with self.assertRaises(lote.LoteErro):
                lote.entradas_da_fonte(f.name)
        finally:
            Path(f.name).unlink()
        with self.assertRaises(lote.LoteErro):
            lote.entradas_da_fonte("/nao/existe.txt")


class TestExecutar(unittest.TestCase):
    def test_um_erro_nao_para_os_outros_e_o_relatorio_conta(self):
        def rodar(e):
            if e == "ruim":
                raise RuntimeError("quebrou")
            return (1, "Erro: x") if e == "falha" else (0, "")

        r = lote.executar(["a", "ruim", "falha", "b"], rodar, avisar=lambda *_: None)
        self.assertEqual((r["ok"], r["falhas"]), (2, 2))
        self.assertEqual(r["itens"][1]["mensagem"], "quebrou")
        texto = lote.resumo(r)
        self.assertIn("2 pronto(s), 2 com erro", texto)
        self.assertIn("Falhou: falha (Erro: x)", texto)

    def test_relatorio_vai_para_json(self):
        with tempfile.TemporaryDirectory() as d:
            destino = lote.gravar_relatorio({"ok": 1, "falhas": 0, "itens": []}, Path(d) / "r.json")
            self.assertEqual(json.loads(destino.read_text())["ok"], 1)


if __name__ == "__main__":
    unittest.main()
