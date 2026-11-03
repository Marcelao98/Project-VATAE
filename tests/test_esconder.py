import tempfile
import unittest
from pathlib import Path

from vatty import esconder as e

TSV = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
       "5\t1\t1\t1\t1\t1\t10\t10\t80\t20\t90\tHollow\n"
       "5\t1\t1\t1\t1\t2\t100\t10\t90\t20\t90\tsubarasiiki\n"
       "5\t1\t1\t1\t1\t3\t200\t10\t40\t20\t90\tHibr\n")


class TestTermos(unittest.TestCase):
    def test_lista_e_comparacao_aproximada(self):
        termos = e.termos("Subarashiki Hibi, Subahibi;")
        self.assertEqual(termos, ["Subarashiki Hibi", "Subahibi"])
        self.assertTrue(e.bate("subarasiiki", termos))     # erro de OCR
        self.assertTrue(e.bate("Subahibi!", termos))
        self.assertFalse(e.bate("Hollow", termos))
        self.assertFalse(e.bate("", termos))

    def test_caixas_le_o_tsv(self):
        self.assertEqual(e.caixas(TSV)[1], ("subarasiiki", 100, 10, 90, 20))
        self.assertEqual(e.caixas(""), [])


class TestLimpar(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.tmp = tempfile.TemporaryDirectory()
        self.img = Path(self.tmp.name) / "p.png"
        Image.new("RGB", (300, 60), "white").save(self.img)

    def tearDown(self):
        self.tmp.cleanup()

    def test_borra_as_palavras_do_termo(self):
        img, n = e.limpar(self.img, ["Subarashiki Hibi"], ler=lambda p: TSV)
        self.assertEqual(n, 2)
        self.assertIsNotNone(img)

    def test_sem_garantia_o_print_sai(self):
        self.assertEqual(e.limpar(self.img, ["Subahibi"], ler=lambda p: None), (None, 0))           # sem Tesseract
        self.assertEqual(e.limpar(self.img, ["Subahibi"], "aba Subahibi", ler=lambda p: "")[0], None)  # OCR não achou
        img, n = e.limpar(self.img, ["Subahibi"], "nada aqui", ler=lambda p: "")
        self.assertEqual((img is not None, n), (True, 0))                                             # não está lá


if __name__ == "__main__":
    unittest.main()
