import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vatty import apresentacao_render as r


class TestNavegador(unittest.TestCase):
    def test_acha_pelo_nome_ou_pelo_caminho_do_windows(self):
        self.assertEqual(r.achar_navegador(lambda n: "/usr/bin/chromium" if n == "chromium" else None), "/usr/bin/chromium")
        edge = r.WINDOWS[2]
        self.assertEqual(r.achar_navegador(lambda n: None, lambda p: p == edge), edge)
        self.assertIsNone(r.achar_navegador(lambda n: None, lambda p: False))

    def test_sem_navegador_explica_como_instalar(self):
        with mock.patch.object(r, "achar_navegador", return_value=None), self.assertRaises(RuntimeError) as e:
            r.renderizar("<html></html>", 1, {"pdf": Path("x.pdf")})
        self.assertIn("Chromium", str(e.exception))


class TestCaptura(unittest.TestCase):
    def test_um_print_por_slide_no_modo_captura_e_pdf(self):
        from PIL import Image
        argvs = []

        def executar(argv, **_):
            argvs.append(argv)
            destino = next(a for a in argv if a.startswith("--screenshot=")).split("=", 1)[1]
            Image.new("RGB", (32, 18), "white").save(destino)
        with tempfile.TemporaryDirectory() as d:
            feitos = r.renderizar("<html>oi</html>", 2, {"pdf": Path(d) / "a.pdf"}, exe="chrome", executar=executar)
            self.assertEqual(feitos, [Path(d) / "a.pdf"])
            self.assertTrue((Path(d) / "a.pdf").stat().st_size > 0)
        self.assertEqual([a[-1].rsplit("#", 1)[1] for a in argvs], ["1c", "2c"])
        self.assertIn("--window-size=1600,900", argvs[0])

    def test_navegador_que_nao_gera_imagem_da_erro_legivel(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(RuntimeError):
            r.renderizar("<html></html>", 1, {"pdf": Path(d) / "a.pdf"}, exe="chrome", executar=lambda argv, **_: None)


if __name__ == "__main__":
    unittest.main()
