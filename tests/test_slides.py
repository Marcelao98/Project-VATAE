import json
import tempfile
import unittest
from pathlib import Path

from vatty import cli, slides


def _seg(inicio, texto, **extra):
    return {"inicio": inicio, "fim": inicio + 2, "texto": texto, **extra}


class TestMontar(unittest.TestCase):
    def test_cada_fala_vai_para_a_tela_que_estava_aberta(self):
        eventos = [{"inicio": 10.0, "fim": 30.0, "frame": "frames/0002.jpg"},
                   {"inicio": 0.0, "fim": 10.0, "frame": "frames/0001.jpg"},
                   {"tipo": "movimento", "inicio": 30.0, "fim": 32.0}]          # sem quadro: não vira slide
        segs = [_seg(-1.0, "antes de tudo"), _seg(3.0, "capa", falante="eu"), _seg(10.0, "agenda", pessoa="Pessoa 1"),
                _seg(25.0, "  ")]
        s = slides.montar(eventos, segs, duracao=40.0)
        self.assertEqual([(x.frame, x.inicio, x.fim) for x in s], [("frames/0001.jpg", 0.0, 10.0), ("frames/0002.jpg", 10.0, 40.0)])
        self.assertEqual([(q, t) for _, q, t in s[0].fala], [(None, "antes de tudo"), ("Eu", "capa")])
        self.assertEqual([(q, t) for _, q, t in s[1].fala], [("Pessoa 1", "agenda")])

    def test_mesma_tela_seguida_vira_um_slide_e_sem_quadro_nada(self):
        eventos = [{"inicio": 0.0, "fim": 5.0, "frame": "frames/0001.jpg"},
                   {"inicio": 5.0, "fim": 9.0, "frame": "frames/0001.jpg", "repetida": True}]
        self.assertEqual(len(slides.montar(eventos, [])), 1)
        self.assertEqual(slides.montar([{"tipo": "movimento", "inicio": 0, "fim": 3}], [_seg(0, "oi")]), [])


class TestPasta(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pasta = Path(tmp.name) / "aula"
        (self.pasta / "frames").mkdir(parents=True)
        (self.pasta / "frames" / "0001.jpg").write_bytes(b"\xff\xd8jpg")
        (self.pasta / "fonte.json").write_text(json.dumps({"tipo": "youtube", "url": "https://youtu.be/abc",
                                                           "titulo": "Aula <de> derivadas"}))
        (self.pasta / "transcricao.json").write_text(json.dumps({"duracao_s": 60, "segmentos": [_seg(5, "x < y & z")]}))

    def test_sem_visual_explica_o_que_fazer(self):
        with self.assertRaisesRegex(slides.ErroSlides, "--visual aula"):
            slides.gerar(self.pasta)

    def test_html_de_um_arquivo_so_com_link_e_texto_escapado(self):
        (self.pasta / "visual.json").write_text(json.dumps({"eventos": [{"inicio": 0, "fim": 60, "frame": "frames/0001.jpg"}]}))
        (arquivo,) = slides.gerar(self.pasta)
        html = arquivo.read_text(encoding="utf-8")
        self.assertIn("data:image/jpeg;base64,", html)          # a imagem vai dentro: dá para mandar o arquivo
        self.assertIn("https://youtu.be/abc?t=0s", html)
        self.assertIn("x &lt; y &amp; z", html)
        self.assertNotIn("<de>", html)

    def test_cli_slides_e_erro(self):
        self.assertEqual(cli.main(["slides", str(self.pasta)]), 1)  # sem visual.json
        (self.pasta / "visual.json").write_text(json.dumps({"eventos": [{"inicio": 0, "fim": 60, "frame": "frames/0001.jpg"}]}))
        self.assertEqual(cli.main(["slides", str(self.pasta)]), 0)
        self.assertTrue((self.pasta / "slides.html").is_file())


if __name__ == "__main__":
    unittest.main()
