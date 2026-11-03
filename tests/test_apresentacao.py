import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from vatty import apresentacao as a
from vatty import cli

ROTEIRO = """# Vatty: ouve e transforma
subtitulo: Tudo no seu PC.

## Como funciona
tipo: passos
- Grava
- Transcreve
horario: [00:55]

## O painel
tipo: imagem
- Gravando
print: frames/0001.jpg
recorte: 20 10 60 80
notas: mostrar o REC

## Estranho
tipo: bolo
recorte: 90 0 20 50
- <script>alert(1)</script> e **forte**
"""


class TestLer(unittest.TestCase):
    def test_roteiro_vira_capa_e_slides(self):
        deck = a.ler(ROTEIRO)
        self.assertEqual((deck["titulo"], deck["subtitulo"]), ("Vatty: ouve e transforma", "Tudo no seu PC."))
        self.assertEqual([s["tipo"] for s in deck["slides"]], ["passos", "imagem", "lista"])  # tipo desconhecido vira lista
        self.assertEqual(deck["slides"][1]["recorte"], (20, 10, 60, 80))
        self.assertEqual(deck["slides"][1]["notas"], "mostrar o REC")

    def test_recorte_fora_da_imagem_e_ignorado(self):
        self.assertIsNone(a.ler(ROTEIRO)["slides"][2]["recorte"])

    def test_sem_titulo_ou_sem_slide_da_erro(self):
        with self.assertRaises(a.ErroApresentacao):
            a.ler("## Só um slide\n- item")
        with self.assertRaises(a.ErroApresentacao):
            a.ler("# Só o título")


class TestHtml(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pasta = Path(tmp.name)
        (self.pasta / "frames").mkdir()
        (self.pasta / "frames" / "0001.jpg").write_bytes(b"\xff\xd8jpg")

    def test_escapa_texto_embute_o_print_e_conta_os_slides(self):
        doc = a.para_html(a.ler(ROTEIRO), self.pasta, arte=None)
        self.assertNotIn("<script>alert", doc)
        self.assertIn("&lt;script&gt;", doc)
        self.assertIn("<strong>forte</strong>", doc)
        self.assertIn("data:image/jpeg;base64,", doc)
        self.assertEqual(doc.count('<section class="slide'), 4)   # capa + 3

    def test_print_fora_da_pasta_nao_entra(self):
        deck = a.ler(ROTEIRO.replace("frames/0001.jpg", "../../etc/passwd"))
        self.assertNotIn("data:image", a.para_html(deck, self.pasta, arte=None))

    def test_youtube_vira_link_no_horario(self):
        fonte = {"tipo": "youtube", "url": "https://www.youtube.com/watch?v=abc"}
        self.assertIn("watch?v=abc&amp;t=55s", a.para_html(a.ler(ROTEIRO), self.pasta, fonte, arte=None))


class TestMontar(unittest.TestCase):
    def test_cada_roteiro_vira_html_ao_lado(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            (pasta / "fonte.json").write_text(json.dumps({"tipo": "gravacao", "data": "2026-10-31_13-43"}))
            (pasta / "apresentacao-pitch.md").write_text(ROTEIRO, encoding="utf-8")
            feitos = a.montar(pasta, formatos=("html",))
            self.assertEqual(feitos, [pasta / "apresentacao-pitch.html"])
            self.assertIn("31/10/2026", feitos[0].read_text(encoding="utf-8"))

    @unittest.skipUnless(importlib.util.find_spec("pptx"), "python-pptx não instalado")
    def test_pptx_tem_capa_slides_e_notas(self):
        from pptx import Presentation
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            (pasta / "apresentacao-pitch.md").write_text(ROTEIRO, encoding="utf-8")
            feitos = a.montar(pasta)   # padrão: .pptx
            self.assertEqual(feitos, [pasta / "apresentacao-pitch.pptx"])
            prs = Presentation(feitos[0])
            self.assertEqual(len(prs.slides), 4)
            self.assertEqual(prs.slides[2].notes_slide.notes_text_frame.text, "mostrar o REC")
            textos = " ".join(f.text_frame.text for f in prs.slides[1].shapes if f.has_text_frame)
            self.assertIn("Como funciona", textos)

    @unittest.skipUnless(importlib.util.find_spec("pptx"), "python-pptx não instalado")
    def test_pptx_usa_marca_capa_e_cores_do_assunto(self):
        from PIL import Image
        from pptx import Presentation
        from vatty import apresentacao_pptx as ap
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            (pasta / "frames").mkdir()
            Image.new("RGB", (40, 30), "white").save(pasta / "frames" / "0003.jpg")
            roteiro = ROTEIRO.replace("subtitulo: Tudo no seu PC.\n", "subtitulo: Tudo no seu PC.\nmarca: Freddy\n"
                                      "capa: frames/0003.jpg 10 10 50 50\ncores: fundo #f5f5f7 texto #1e1e23 destaque #bf4a62\n")
            (pasta / "apresentacao-freddy.md").write_text(roteiro, encoding="utf-8")
            prs = Presentation(a.montar(pasta)[0])
            capa = prs.slides[0].shapes
            textos = " ".join(f.text_frame.text for f in capa if f.has_text_frame)
            self.assertIn("Freddy", textos)
            self.assertNotIn("Vatty ", textos + " ")
            self.assertEqual(sum(1 for f in capa if f.shape_type == 13), 2)   # fundo + capa
            self.assertEqual(ap.COR, ap.VATTY)                                # a paleta volta ao padrão depois


class TestAssunto(unittest.TestCase):
    def test_marca_capa_e_cores_sao_do_deck_e_nao_viram_slide(self):
        deck = a.ler(ROTEIRO.replace("subtitulo: Tudo no seu PC.\n", "subtitulo: Tudo no seu PC.\nmarca: Freddy\n"
                                     "capa: frames/0003.jpg 30 18 40 38\ncores: fundo #F5F5F7, texto=#1e1e23 destaque #bf4a62\n"))
        self.assertEqual(deck["marca"], "Freddy")
        self.assertEqual(deck["capa"], {"caminho": "frames/0003.jpg", "recorte": (30, 18, 40, 38)})
        self.assertEqual(deck["cores"], {"fundo": "f5f5f7", "texto": "1e1e23", "destaque": "bf4a62"})
        self.assertEqual(len(deck["slides"]), 3)

    def test_sem_capa_nao_tem_arte_da_vatty_e_capa_vatty_tem(self):
        self.assertIsNone(a.ler(ROTEIRO)["capa"])
        self.assertEqual(a.ler("# T\ncapa: vatty\n## S\n- x")["capa"]["caminho"], str(a.ARTE))
        self.assertIsNone(a.ler("# T\ncapa: nenhuma\n## S\n- x")["capa"])

    def test_capa_relativa_nao_sai_da_pasta_e_precisa_ser_imagem(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d) / "video"
            pasta.mkdir()
            (Path(d) / "fora.png").write_bytes(b"x")
            (pasta / "nota.txt").write_text("x")
            (pasta / "capa.png").write_bytes(b"x")
            arte = lambda v: a.arte_do_deck(a.ler(f"# T\ncapa: {v}\n## S\n- x"), pasta)
            self.assertIsNone(arte("../fora.png"))
            self.assertIsNone(arte("nota.txt"))
            self.assertIsNone(arte("sumiu.png"))
            self.assertEqual(arte("capa.png"), ((pasta / "capa.png").resolve(), None))
            self.assertEqual(arte(str(Path(d) / "fora.png")), (Path(d) / "fora.png", None))   # absoluto vale

    def test_html_usa_a_marca_e_as_cores(self):
        doc = a.para_html(a.ler("# T\nmarca: Freddy\ncores: fundo #f5f5f7 texto #1e1e23 destaque #bf4a62\n## S\n- x"), ".")
        self.assertIn('<span class="marca">Freddy</span>', doc)
        self.assertNotIn(">Vatty<", doc)
        self.assertIn("--oficina:#f5f5f7", doc)


class TestCli(unittest.TestCase):
    def test_cli_sem_roteiro_da_erro(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cli.main(["apresentacao", d]), 1)


if __name__ == "__main__":
    unittest.main()
