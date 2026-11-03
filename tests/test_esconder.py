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
        Image.new("RGB", (300, 200), "white").save(self.img)

    def tearDown(self):
        self.tmp.cleanup()

    def test_corta_o_print_para_deixar_o_termo_de_fora(self):
        img, n = e.limpar(self.img, ["Subarashiki Hibi"], ler=lambda p: TSV)
        self.assertEqual(n, 2)
        self.assertEqual(img.size, (300, 200 - 30 - e.MARGEM))   # corta a faixa de cima, onde está o nome

    def test_cortar_escolhe_o_lado_que_perde_menos_e_desiste_se_sobra_pouco(self):
        self.assertEqual(e.cortar((0, 0, 100, 100), [(90, 0, 100, 10)]), (0, 0, 90, 100))
        self.assertEqual(e.cortar((0, 0, 100, 100), [(200, 0, 210, 10)]), (0, 0, 100, 100))   # fora da área
        self.assertIsNone(e.cortar((0, 0, 100, 100), [(10, 10, 90, 90)]))                      # no meio de tudo

    def test_sem_garantia_o_print_sai(self):
        self.assertEqual(e.limpar(self.img, ["Subahibi"], ler=lambda p: None), (None, 0))           # sem Tesseract
        self.assertEqual(e.limpar(self.img, ["Subahibi"], "aba Subahibi", ler=lambda p: "")[0], None)  # OCR não achou
        img, n = e.limpar(self.img, ["Subahibi"], "nada aqui", ler=lambda p: "")
        self.assertEqual((img is not None, n), (True, 0))                                             # não está lá


if __name__ == "__main__":
    unittest.main()
