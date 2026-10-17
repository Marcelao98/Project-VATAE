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
    """
    Faz o papel do YoutubeDL: conta quantas vezes a página foi lida, guarda `params` como o de verdade
    (a Sessao muda as opções entre um download e outro) e 'baixa' criando o arquivo do outtmpl.
    """

    criados = []
    info = INFO

    def __init__(self, opcoes):
        self.params = {**opcoes, "outtmpl": dict(opcoes["outtmpl"])}
        self.leituras = 0
        self.processados = []
        self.format_selector = None
        self.seletores = []
        self.fechado = 0
        YoutubeDLDuble.criados.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        self.fechado += 1
        return False

    def extract_info(self, url, download, process=True):
        assert download is False and process is False  # a Sessao pede o resultado bruto do extrator
        self.leituras += 1
        return dict(self.info)

    def build_format_selector(self, formato):
        self.seletores.append(formato)
        return ("seletor", formato)

    def process_ie_result(self, info, download):
        if not download:
            return {**info, "formato_escolhido_na_leitura": "v+a"}  # o info processado traz isto: não pode ir para o download
        self.processados.append((info, dict(self.params), self.format_selector))
        assert "formato_escolhido_na_leitura" not in info
        modelo = self.params["outtmpl"]["default"]
        if self.params.get("skip_download"):
            Path(modelo.replace("%(ext)s", f"{self.params['subtitleslangs'][0]}.vtt")).write_text("WEBVTT\n")
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
        self.assertTrue(YoutubeDLDuble.criados[0].params["skip_download"])
        self.assertEqual(video.titulo, "Aula 3: Derivadas")
        self.assertEqual(video.duracao_s, 754.0)
        self.assertEqual(video.idioma, "pt-BR")
        self.assertIn("pt-BR", video.legendas)
        self.assertIn("pt-orig", video.legendas_automaticas)
        dados = video.para_json()
        self.assertEqual(dados["url"], "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(dados["capitulos"], [{"inicio": 0, "fim": 53, "titulo": "Introdução"}])
        self.assertEqual(dados["descricao"], "Links e referências")
        self.assertEqual(dados["tipo"], "youtube")
        self.assertNotIn("plataforma", dados)  # o contrato do YouTube fica como sempre
        self.assertEqual(video.plataforma, "YouTube")

    def test_video_sem_capitulos(self):
        class SemCapitulos(YoutubeDLDuble):
            info = {k: v for k, v in INFO.items() if k not in ("chapters", "description")}

        video = fonte.inspecionar("u", fabrica=SemCapitulos)
        self.assertEqual((video.capitulos, video.descricao), ([], ""))

    def test_baixar_legenda_automatica_sem_audio(self):
        vtt = fonte.baixar_legenda("u", "pt-orig", True, self.pasta, fabrica=YoutubeDLDuble)
        opcoes = YoutubeDLDuble.criados[0].processados[0][1]
        self.assertTrue(opcoes["skip_download"])
        self.assertTrue(opcoes["writeautomaticsub"])
        self.assertFalse(opcoes["writesubtitles"])
        self.assertEqual(opcoes["subtitleslangs"], ["pt-orig"])
        self.assertEqual(opcoes["subtitlesformat"], "vtt")
        self.assertEqual(vtt.name, "legenda.pt-orig.vtt")

    def test_baixar_legenda_manual(self):
        fonte.baixar_legenda("u", "pt-BR", False, self.pasta, fabrica=YoutubeDLDuble)
        opcoes = YoutubeDLDuble.criados[0].processados[0][1]
        self.assertTrue(opcoes["writesubtitles"])
        self.assertFalse(opcoes["writeautomaticsub"])

    def test_baixar_audio(self):
        audio = fonte.baixar_audio("u", self.pasta, fabrica=YoutubeDLDuble)
        self.assertEqual(YoutubeDLDuble.criados[0].processados[0][1]["format"], "bestaudio/best")
        self.assertEqual(audio.name, "audio.webm")

    def test_baixar_video_so_imagem_ate_720p(self):
        video = fonte.baixar_video("u", self.pasta, fabrica=YoutubeDLDuble)
        formato = YoutubeDLDuble.criados[-1].processados[0][1]["format"]
        self.assertIn("height<=720", formato)
        self.assertNotIn("audio", formato.replace("bestvideo", ""))  # não pede faixa de áudio
        self.assertEqual(video.name, "video.webm")

    def test_erro_se_nada_foi_baixado(self):
        class NaoBaixa(YoutubeDLDuble):
            def process_ie_result(self, info, download):
                return info

        with self.assertRaises(RuntimeError):
            fonte.baixar_audio("u", self.pasta, fabrica=NaoBaixa)


class TestSessao(unittest.TestCase):
    """O TikTok recusa a segunda leitura da página: a Sessao lê uma vez e reaproveita."""

    def setUp(self):
        YoutubeDLDuble.criados = []
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)

    def test_inspecionar_e_todos_os_downloads_leem_a_pagina_uma_vez_so(self):
        with fonte.Sessao("https://www.tiktok.com/@a/video/1", YoutubeDLDuble) as sessao:
            sessao.inspecionar()
            sessao.inspecionar()
            sessao.baixar_legenda("pt-BR", False, self.pasta)
            sessao.baixar_audio(self.pasta)
            sessao.baixar_video(self.pasta)
        self.assertEqual(len(YoutubeDLDuble.criados), 1)   # uma instância (os cookies do desafio ficam nela)
        self.assertEqual(YoutubeDLDuble.criados[0].leituras, 1)
        self.assertEqual(len(YoutubeDLDuble.criados[0].processados), 3)

    def test_download_parte_do_resultado_bruto_e_nao_do_ja_processado(self):
        with fonte.Sessao("u", YoutubeDLDuble) as sessao:
            sessao.baixar_audio(self.pasta)
            info, _, _ = YoutubeDLDuble.criados[0].processados[0]
        self.assertEqual(info["id"], "abc123")
        self.assertNotIn("formato_escolhido_na_leitura", info)

    def test_cada_download_recomeca_das_opcoes_neutras(self):
        with fonte.Sessao("u", YoutubeDLDuble) as sessao:
            sessao.baixar_legenda("pt-BR", True, self.pasta)
            sessao.baixar_audio(self.pasta)
            _, legenda, _ = YoutubeDLDuble.criados[0].processados[0]
            _, audio, seletor = YoutubeDLDuble.criados[0].processados[1]
        self.assertTrue(legenda["skip_download"] and legenda["writeautomaticsub"])
        # o áudio não herda "só a legenda" nem a lista de idiomas
        self.assertFalse(audio["skip_download"])
        self.assertFalse(audio["writeautomaticsub"])
        self.assertEqual(audio["subtitleslangs"], [])
        self.assertEqual(seletor, ("seletor", "bestaudio/best"))  # o seletor de formato foi refeito
        self.assertTrue(audio["outtmpl"]["default"].endswith("audio.%(ext)s"))

    def test_o_info_guardado_nao_e_alterado_pelo_download(self):
        with fonte.Sessao("u", YoutubeDLDuble) as sessao:
            sessao.baixar_audio(self.pasta)
            YoutubeDLDuble.criados[0].processados[0][0]["id"] = "mexido"
            sessao.baixar_audio(self.pasta)
            self.assertEqual(YoutubeDLDuble.criados[0].processados[1][0]["id"], "abc123")

    def test_plataforma_e_tipo_do_fonte_json(self):
        class TikTok(YoutubeDLDuble):
            info = {"id": "7", "title": "Meu vídeo #fyp", "uploader": "ana", "duration": 31, "extractor_key": "TikTok",
                    "webpage_url": "https://www.tiktok.com/@ana/video/7", "upload_date": "20261012"}

        video = fonte.inspecionar("https://vm.tiktok.com/xyz", fabrica=TikTok)
        self.assertEqual(video.plataforma, "TikTok")
        dados = video.para_json()
        self.assertEqual((dados["tipo"], dados["plataforma"], dados["canal"]), ("url", "TikTok", "ana"))
        self.assertEqual(video.legendas, {})
        self.assertEqual(video.capitulos, [])

    def test_youtube_vira_youtube_com_qualquer_variante_do_extrator(self):
        for chave in ("Youtube", "YoutubeTab", "youtube", None, ""):
            self.assertEqual(fonte._plataforma({"extractor_key": chave}), "YouTube")
        self.assertEqual(fonte._plataforma({"extractor": "tiktok"}), "tiktok")

    def test_fechar_pode_ser_chamado_mais_de_uma_vez(self):
        sessao = fonte.Sessao("u", YoutubeDLDuble)
        sessao.fechar()
        sessao.fechar()
        self.assertEqual(YoutubeDLDuble.criados[0].fechado, 1)

    def test_funcoes_soltas_continuam_funcionando(self):
        self.assertEqual(fonte.baixar_audio("u", self.pasta, fabrica=YoutubeDLDuble).name, "audio.webm")
        self.assertEqual(YoutubeDLDuble.criados[0].fechado, 1)



class TestListarPlaylist(unittest.TestCase):
    def _duble(self, info):
        class D:
            def __init__(self, opcoes):
                self.opcoes = opcoes
                D.ultimo = self

            def __enter__(self):
                return self

            def __exit__(self, *e):
                return False

            def extract_info(self, url, download):
                assert download is False
                return info
        return D

    def test_playlist_vira_lista_de_links_e_pula_indisponivel(self):
        info = {"title": "Aulas", "entries": [{"url": "https://www.youtube.com/watch?v=a"}, None, {"id": "b"},
                                               {"url": "b2", "id": "c"}]}
        titulo, urls = fonte.listar_playlist("https://youtube.com/playlist?list=x", self._duble(info))
        self.assertEqual(titulo, "Aulas")
        self.assertEqual(urls, ["https://www.youtube.com/watch?v=a", "https://www.youtube.com/watch?v=b",
                                "https://www.youtube.com/watch?v=c"])

    def test_video_unico_devolve_ele_mesmo_e_pede_flat(self):
        duble = self._duble({"title": "Um"})
        self.assertEqual(fonte.listar_playlist("https://youtu.be/x", duble), ("Um", ["https://youtu.be/x"]))
        self.assertEqual(duble.ultimo.opcoes["extract_flat"], "in_playlist")



class TestCookiesDoNavegador(unittest.TestCase):
    def test_so_com_a_variavel_e_navegador_conhecido(self):
        from unittest import mock
        with mock.patch.dict("os.environ", {fonte.VAR_NAVEGADOR: "Firefox"}):
            self.assertEqual(fonte._opcoes()["cookiesfrombrowser"], ("firefox",))
        with mock.patch.dict("os.environ", {fonte.VAR_NAVEGADOR: "netscape; rm"}):
            self.assertNotIn("cookiesfrombrowser", fonte._opcoes())
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertNotIn("cookiesfrombrowser", fonte._opcoes())


if __name__ == "__main__":
    unittest.main()
