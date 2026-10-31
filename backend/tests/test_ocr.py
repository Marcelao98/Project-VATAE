import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from vatty import ocr

# Saída real do Tesseract 5 (`tesseract slide.png stdout -l eng tsv`), encurtada.
TSV = "\n".join([
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
    "1\t1\t0\t0\t0\t0\t0\t0\t1280\t720\t-1\t",
    "2\t1\t1\t0\t0\t0\t82\t86\t475\t34\t-1\t",
    "5\t1\t1\t1\t1\t1\t82\t86\t154\t29\t96.5\tNotional",
    "5\t1\t1\t1\t1\t2\t262\t86\t35\t29\t96.5\tof",
    "5\t1\t1\t1\t1\t3\t322\t94\t17\t21\t90.0\tput",
    "2\t1\t2\t0\t0\t0\t82\t165\t596\t35\t-1\t",
    "5\t1\t2\t1\t1\t1\t82\t166\t156\t34\t80.0\tquantity",
    "5\t1\t2\t1\t1\t2\t264\t166\t93\t29\t80.0\ttimes",
    "5\t1\t2\t1\t2\t1\t82\t210\t93\t29\t70.0\t350000",
    "",
])


def resultado(stdout="", codigo=0, stderr=""):
    return SimpleNamespace(stdout=stdout, returncode=codigo, stderr=stderr)


class TestLerTsv(unittest.TestCase):
    def test_texto_por_linhas_e_blocos(self):
        leitura = ocr.ler_tsv(TSV)
        self.assertEqual(leitura.texto, "Notional of put\n\nquantity times\n350000")

    def test_confianca_e_a_media_das_palavras(self):
        # (96.5 + 96.5 + 90 + 80 + 80 + 70) / 6
        self.assertEqual(ocr.ler_tsv(TSV).confianca, 85.5)

    def test_sem_palavras(self):
        leitura = ocr.ler_tsv("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n")
        self.assertEqual((leitura.texto, leitura.confianca), ("", None))

    def test_ignora_linha_quebrada(self):
        self.assertEqual(ocr.ler_tsv("cabecalho\nlinha sem colunas\n").texto, "")


class TestIdiomas(unittest.TestCase):
    def test_idiomas_para(self):
        self.assertEqual(ocr.idiomas_para("pt"), "por+eng")
        self.assertEqual(ocr.idiomas_para("en"), "eng")
        self.assertEqual(ocr.idiomas_para("es"), "spa+eng")
        self.assertEqual(ocr.idiomas_para("auto"), "por+eng")
        self.assertEqual(ocr.idiomas_para(None), "por+eng")


class TestLerImagem(unittest.TestCase):
    def test_chama_o_tesseract_com_o_idioma_e_le_o_tsv(self):
        chamadas = []

        def executar(comando, **opcoes):
            chamadas.append(comando)
            return resultado(TSV)

        leitura = ocr.ler_imagem("frames/0001.jpg", "por+eng", "/usr/bin/tesseract", executar)
        self.assertEqual(chamadas[0], ["/usr/bin/tesseract", "frames/0001.jpg", "stdout", "-l", "por+eng", "tsv"])
        self.assertIn("Notional", leitura.texto)

    def test_falha_do_tesseract_vira_erro_com_o_nome_da_imagem(self):
        with self.assertRaises(ocr.ErroOcr) as e:
            ocr.ler_imagem("frames/0002.jpg", "eng", "t", lambda c, **o: resultado(codigo=1, stderr="Error opening data file"))
        self.assertIn("0002.jpg", str(e.exception))
        self.assertIn("Error opening", str(e.exception))

    def test_programa_sumiu_no_meio(self):
        def executar(comando, **opcoes):
            raise FileNotFoundError

        with self.assertRaises(ocr.ErroOcr) as e:
            ocr.ler_imagem("a.jpg", "eng", "t", executar)
        self.assertIn("Instale", str(e.exception))

    def test_demora_demais(self):
        def executar(comando, **opcoes):
            raise subprocess.TimeoutExpired(comando, 60)

        with self.assertRaises(ocr.ErroOcr):
            ocr.ler_imagem("a.jpg", "eng", "t", executar)


class TestVerificar(unittest.TestCase):
    LISTA = "List of available languages in \"/x/tessdata/\" (3):\neng\nosd\npor\n"

    def test_ok_devolve_o_executavel(self):
        with mock.patch.object(ocr, "localizar", return_value="/usr/bin/tesseract"):
            exe = ocr.verificar("por+eng", lambda c, **o: resultado(self.LISTA))
        self.assertEqual(exe, "/usr/bin/tesseract")

    def test_sem_o_programa(self):
        with mock.patch.object(ocr, "localizar", return_value=None):
            with self.assertRaises(ocr.ErroOcr) as e:
                ocr.verificar("eng", lambda c, **o: resultado(self.LISTA))
        self.assertIn("Instale o Tesseract", str(e.exception))

    def test_falta_idioma(self):
        with mock.patch.object(ocr, "localizar", return_value="t"):
            with self.assertRaises(ocr.ErroOcr) as e:
                ocr.verificar("spa+eng", lambda c, **o: resultado(self.LISTA))
        self.assertIn("spa", str(e.exception))


class TestLocalizar(unittest.TestCase):
    def test_variavel_de_ambiente_tem_prioridade(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "tesseract.exe"
            exe.write_text("", encoding="utf-8")
            with mock.patch.dict(ocr.os.environ, {"TESSERACT_CMD": str(exe)}), \
                 mock.patch.object(ocr.shutil, "which", return_value="/outro/tesseract"):
                self.assertEqual(ocr.localizar(), str(exe))

    def test_usa_o_path(self):
        with mock.patch.dict(ocr.os.environ, {}, clear=True), \
             mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"):
            self.assertEqual(ocr.localizar(), "/usr/bin/tesseract")

    def test_nao_acha(self):
        with mock.patch.dict(ocr.os.environ, {}, clear=True), \
             mock.patch.object(ocr.shutil, "which", return_value=None), \
             mock.patch.object(ocr, "CAMINHOS_WINDOWS", ()):
            self.assertIsNone(ocr.localizar())


if __name__ == "__main__":
    unittest.main()
