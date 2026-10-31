import tempfile
import unittest
from pathlib import Path

from vatty import fonte

INFO = {
    "id": "abc123",
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
    "title": "Aula 3: Derivadas",
    "channel": "Canal",
    "duration": 754,
    "upload_date": "20260101",
    "language": "pt-BR",
    "subtitles": {"pt-BR": [{"ext": "vtt"}]},
    "automatic_captions": {"pt-orig": [{"ext": "vtt"}]},
    "chapters": [{"start_time": 0, "end_time": 53, "title": "Introdução"}],
    "description": "Links e referências",
}


class YoutubeDLDuble:
    """Faz o papel do YoutubeDL: guarda as opções e 'baixa' criando o arquivo do outtmpl."""

    criados = []

    def __init__(self, opcoes):
        self.opcoes = opcoes
        YoutubeDLDuble.criados.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        return False

    def extract_info(self, url, download):
        assert download is False
        return INFO

    def download(self, urls):
        modelo = self.opcoes["outtmpl"]["default"]
        if self.opcoes.get("skip_download"):
            Path(modelo.replace("%(ext)s", f"{self.opcoes['subtitleslangs'][0]}.vtt")).write_text("WEBVTT\n")
        else:
            Path(modelo.replace("%(ext)s", "webm")).write_bytes(b"audio")


class TestFonte(unittest.TestCase):
    def setUp(self):
        YoutubeDLDuble.criados = []
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)

    def test_eh_url(self):
        self.assertTrue(fonte.eh_url("https://youtu.be/abc"))
        self.assertTrue(fonte.eh_url("HTTP://youtube.com/watch?v=x"))
        self.assertFalse(fonte.eh_url("C:/videos/aula.mp4"))
        self.assertFalse(fonte.eh_url("aula.opus"))

    def test_inspecionar_nao_baixa(self):
        video = fonte.inspecionar("https://youtu.be/abc123", fabrica=YoutubeDLDuble)
        self.assertTrue(YoutubeDLDuble.criados[0].opcoes["skip_download"])
        self.assertEqual(video.titulo, "Aula 3: Derivadas")
        self.assertEqual(video.duracao_s, 754.0)
        self.assertEqual(video.idioma, "pt-BR")
        self.assertIn("pt-BR", video.legendas)
        self.assertIn("pt-orig", video.legendas_automaticas)
        dados = video.para_json()
        self.assertEqual(dados["url"], "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(dados["capitulos"], [{"inicio": 0, "fim": 53, "titulo": "Introdução"}])
        self.assertEqual(dados["descricao"], "Links e referências")

    def test_video_sem_capitulos(self):
        class SemCapitulos(YoutubeDLDuble):
            def extract_info(self, url, download):
                return {k: v for k, v in INFO.items() if k not in ("chapters", "description")}

        video = fonte.inspecionar("u", fabrica=SemCapitulos)
        self.assertEqual((video.capitulos, video.descricao), ([], ""))

    def test_baixar_legenda_automatica_sem_audio(self):
        vtt = fonte.baixar_legenda("u", "pt-orig", True, self.pasta, fabrica=YoutubeDLDuble)
        opcoes = YoutubeDLDuble.criados[0].opcoes
        self.assertTrue(opcoes["skip_download"])
        self.assertTrue(opcoes["writeautomaticsub"])
        self.assertFalse(opcoes["writesubtitles"])
        self.assertEqual(opcoes["subtitleslangs"], ["pt-orig"])
        self.assertEqual(opcoes["subtitlesformat"], "vtt")
        self.assertEqual(vtt.name, "legenda.pt-orig.vtt")

    def test_baixar_legenda_manual(self):
        fonte.baixar_legenda("u", "pt-BR", False, self.pasta, fabrica=YoutubeDLDuble)
        opcoes = YoutubeDLDuble.criados[0].opcoes
        self.assertTrue(opcoes["writesubtitles"])
        self.assertFalse(opcoes["writeautomaticsub"])

    def test_baixar_audio(self):
        audio = fonte.baixar_audio("u", self.pasta, fabrica=YoutubeDLDuble)
        self.assertEqual(YoutubeDLDuble.criados[0].opcoes["format"], "bestaudio/best")
        self.assertEqual(audio.name, "audio.webm")

    def test_baixar_video_so_imagem_ate_720p(self):
        video = fonte.baixar_video("u", self.pasta, fabrica=YoutubeDLDuble)
        formato = YoutubeDLDuble.criados[-1].opcoes["format"]
        self.assertIn("height<=720", formato)
        self.assertNotIn("audio", formato.replace("bestvideo", ""))  # não pede faixa de áudio
        self.assertEqual(video.name, "video.webm")

    def test_erro_se_nada_foi_baixado(self):
        class NaoBaixa(YoutubeDLDuble):
            def download(self, urls):
                pass

        with self.assertRaises(RuntimeError):
            fonte.baixar_audio("u", self.pasta, fabrica=NaoBaixa)


if __name__ == "__main__":
    unittest.main()
