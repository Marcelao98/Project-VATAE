"""O pipeline sem terminal: decisões e mensagens passam por dublês do Decisor e do Progresso."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from vatty import fonte, ocr
from vatty.aplicacao import ErroPipeline, Opcoes, pipeline
from vatty.motor import Resultado, Segmento

VIDEO = fonte.Video(
    id="abc", url="https://www.youtube.com/watch?v=abc", titulo="Aula", canal="C",
    duracao_s=60.0, data=None, idioma="pt", legendas={"pt-BR": []}, legendas_automaticas={},
)


def _vtt(url, chave, automatica, destino):
    caminho = Path(destino) / "legenda.vtt"
    caminho.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nOlá, turma.\n", encoding="utf-8")
    return caminho


def _whisper_falso(caminho, opcoes, idioma, decisor, progresso, em_gravacao=False):
    return Resultado(fonte=str(caminho), duracao_s=2.0, modelo="m", idioma="pt", segmentos=[Segmento(0.0, 2.0, "Oi.")])


class DecisorFalso:
    def __init__(self, interativo=True, legenda="legenda"):
        self.interativo = interativo
        self._legenda = legenda
        self.perguntas = []

    def legenda(self, pergunta):
        self.perguntas.append(pergunta)
        return self._legenda

    def preprocessar(self, diagnostico):
        return False

    def visual(self, pergunta):
        return True

    def apagar_audio(self, pasta):
        return False


class ProgressoFalso:
    def __init__(self):
        self.mensagens, self.avisos = [], []

    def mensagem(self, texto):
        self.mensagens.append(texto)

    def aviso(self, texto):
        self.avisos.append(texto)

    def andamento(self, fase, atual, total):
        pass

    def fim_andamento(self):
        pass


class TestPipeline(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        p = mock.patch.object(pipeline, "_whisper", _whisper_falso)
        p.start()
        self.addCleanup(p.stop)

    def test_arquivo_local_vira_pasta_sem_imprimir_nada(self):
        arquivo = self.raiz / "conversa.opus"
        arquivo.write_bytes(b"x")
        progresso = ProgressoFalso()
        with redirect_stdout(io.StringIO()) as out:
            saida = pipeline.processar(Opcoes(entrada=str(arquivo), saida=self.raiz / "t"), DecisorFalso(), progresso)
        self.assertEqual(out.getvalue(), "")  # tudo foi para o Progresso
        self.assertEqual(saida.txt.read_text(encoding="utf-8"), "[00:00] Oi.\n")
        self.assertEqual(saida.dados_fonte["tipo"], "arquivo")
        self.assertTrue(any(m.startswith("Pronto em") for m in progresso.mensagens))

    def test_youtube_decisor_recebe_os_trechos_e_escolhe_a_legenda(self):
        decisor = DecisorFalso(legenda="legenda")
        with mock.patch.object(fonte, "inspecionar", lambda url: VIDEO), \
                mock.patch.object(fonte, "baixar_legenda", _vtt):
            saida = pipeline.processar(Opcoes(entrada=VIDEO.url, saida=self.raiz), decisor, ProgressoFalso())
        (pergunta,) = decisor.perguntas
        self.assertEqual(pergunta.chave, "pt-BR")
        self.assertIn("Olá, turma.", pergunta.amostras[0][1])
        self.assertEqual(saida.resultado.origem, "legenda-manual")

    def test_sem_interacao_pede_a_opcao_explicita(self):
        with mock.patch.object(fonte, "inspecionar", lambda url: VIDEO), \
                mock.patch.object(fonte, "baixar_legenda", _vtt), self.assertRaises(ErroPipeline):
            pipeline.processar(Opcoes(entrada=VIDEO.url, saida=self.raiz), DecisorFalso(interativo=False),
                               ProgressoFalso())

    def test_falha_no_visual_nao_perde_o_texto(self):
        arquivo = self.raiz / "aula.mp4"
        arquivo.write_bytes(b"x")
        with mock.patch.object(ocr, "verificar", side_effect=ocr.ErroOcr("sem Tesseract")):
            saida = pipeline.processar(Opcoes(entrada=str(arquivo), saida=self.raiz / "t", visual="aula"),
                                       DecisorFalso(), ProgressoFalso())
        self.assertEqual(saida.erro_visual, "sem Tesseract")
        self.assertTrue(saida.txt.is_file())


if __name__ == "__main__":
    unittest.main()
