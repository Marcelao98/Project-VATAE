import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import numpy as np

from vatty import aula, cli, fonte, gravacao, ocr, quadros, tela, visual
from vatty.motor import Resultado, Segmento

VIDEO = fonte.Video(
    id="abc", url="https://www.youtube.com/watch?v=abc", titulo="Aula", canal="C",
    duracao_s=60.0, data=None, idioma="pt", legendas={"pt-BR": []}, legendas_automaticas={},
)


def _vtt(url, chave, automatica, destino):
    caminho = Path(destino) / "legenda.vtt"
    caminho.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nOlá, turma.\n", encoding="utf-8")
    return caminho


class SessaoFalsa:
    """Faz o papel de `fonte.Sessao`: guarda o que foi pedido e escreve arquivos de mentira."""

    criadas = []

    def __init__(self, url, video=VIDEO, baixou=None, erro_ao_ler=None):
        self.url, self.video, self.baixou, self.erro_ao_ler = url, video, baixou, erro_ao_ler
        self.leituras = 0
        self.audios = 0
        self.fechada = 0
        SessaoFalsa.criadas.append(self)

    def inspecionar(self):
        self.leituras += 1
        if self.erro_ao_ler:
            raise self.erro_ao_ler
        return self.video

    def baixar_legenda(self, chave, automatica, destino):
        return _vtt(self.url, chave, automatica, destino)

    def baixar_audio(self, destino):
        self.audios += 1
        return Path(destino) / "audio.webm"

    def baixar_video(self, destino):
        if self.baixou is not None:
            self.baixou.append(self.url)
        caminho = Path(destino) / "video.mp4"
        caminho.write_bytes(b"v")
        return caminho

    def fechar(self):
        self.fechada += 1


class TestFluxoYoutube(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.saida = Path(tmp.name)
        SessaoFalsa.criadas = []
        p = mock.patch.object(fonte, "Sessao", lambda url: SessaoFalsa(url))
        p.start()
        self.addCleanup(p.stop)
        self.whisper = mock.patch.object(cli, "_whisper", return_value=Resultado(
            fonte="x", duracao_s=60.0, modelo="large-v3-turbo", idioma="pt",
            segmentos=[Segmento(0, 1, "do whisper")]))
        self.whisper.start()
        self.addCleanup(self.whisper.stop)

    def rodar(self, *flags, tty=True, respostas=()):
        respostas = iter(respostas)
        with mock.patch.object(cli.sys.stdin, "isatty", return_value=tty), \
             mock.patch("builtins.input", lambda prompt: next(respostas)), \
             redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            codigo = cli.main([VIDEO.url, "--saida", str(self.saida), *flags])
        return codigo, out.getvalue(), err.getvalue()

    def transcricao(self):
        return (self.saida / "aula-abc" / "transcricao.txt").read_text(encoding="utf-8")

    def test_usuario_aprova_a_legenda(self):
        codigo, out, _ = self.rodar(respostas=["l"])
        self.assertEqual(codigo, 0)
        self.assertIn("Olá, turma.", out)  # mostrou o trecho antes de perguntar
        self.assertEqual(self.transcricao(), "[00:01] Olá, turma.\n")
        cli._whisper.assert_not_called()

    def test_usuario_prefere_whisper(self):
        codigo, _, _ = self.rodar(respostas=["x", "w"])
        self.assertEqual(codigo, 0)
        self.assertEqual(self.transcricao(), "[00:00] do whisper\n")

    def test_sem_terminal_exige_flag(self):
        codigo, _, err = self.rodar(tty=False)
        self.assertEqual(codigo, 1)
        self.assertIn("--texto", err)
        self.assertFalse((self.saida / "aula-abc").exists())

    def test_flag_legenda_nao_pergunta(self):
        codigo, _, _ = self.rodar("--texto", "legenda", tty=False)
        self.assertEqual(codigo, 0)
        self.assertEqual(self.transcricao(), "[00:01] Olá, turma.\n")

    def test_sem_legenda_vai_direto_pro_whisper(self):
        sem = fonte.Video(**{**VIDEO.__dict__, "legendas": {}})
        with mock.patch.object(fonte, "Sessao", lambda url: SessaoFalsa(url, sem)):
            codigo, out, _ = self.rodar(tty=False)
        self.assertEqual(codigo, 0)
        self.assertIn("Sem legenda", out)
        self.assertEqual(self.transcricao(), "[00:00] do whisper\n")


class TestOutraPlataforma(unittest.TestCase):
    """TikTok e afins: a página é lida uma vez, e nada diz 'YouTube' à toa."""

    TIKTOK = fonte.Video(
        id="7", url="https://www.tiktok.com/@ana/video/7", titulo="Meu vídeo #fyp", canal="ana",
        duracao_s=31.0, data="20261012", idioma=None, plataforma="TikTok",
    )

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.saida = Path(tmp.name)
        SessaoFalsa.criadas = []
        self.baixou = []
        for objeto, nome, valor in (
            (fonte, "Sessao", lambda url: SessaoFalsa(url, self.TIKTOK, self.baixou)),
            (cli, "_whisper", lambda caminho, args, idioma: Resultado(
                fonte="x", duracao_s=31.0, modelo="m", idioma="pt", segmentos=[Segmento(0, 1, "oi do tiktok")])),
            (ocr, "verificar", lambda idiomas: "tesseract"),
        ):
            p = mock.patch.object(objeto, nome, valor)
            p.start()
            self.addCleanup(p.stop)

    def rodar(self, *flags):
        with mock.patch.object(cli.sys.stdin, "isatty", return_value=False), \
             redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            codigo = cli.main([self.TIKTOK.url, "--saida", str(self.saida), "--preprocessar", "nao", *flags])
        return codigo, out.getvalue(), err.getvalue()

    def test_fonte_json_diz_a_plataforma_e_a_tela_tambem(self):
        codigo, out, _ = self.rodar()
        self.assertEqual(codigo, 0)
        self.assertNotIn("YouTube", out)
        self.assertIn("TikTok: Meu vídeo #fyp", out)
        pasta_video = next(self.saida.iterdir())
        dados = json.loads((pasta_video / "fonte.json").read_text(encoding="utf-8"))
        self.assertEqual((dados["tipo"], dados["plataforma"]), ("url", "TikTok"))
        self.assertEqual(pasta_video.name, "meu-video-fyp-7")

    def test_uma_sessao_so_uma_leitura_e_o_audio_sai_dela(self):
        self.rodar()
        (sessao,) = SessaoFalsa.criadas
        self.assertEqual((sessao.leituras, sessao.audios), (1, 1))
        self.assertEqual(sessao.fechada, 1)

    def test_o_visual_reaproveita_a_mesma_sessao(self):
        with mock.patch.object(cli, "_visual", return_value=0) as visual_:
            self.rodar("--visual", "aula")
        visual_.assert_called_once()
        # o download do vídeo da tela vai usar args.sessao: a página não é aberta de novo
        self.assertEqual(len(SessaoFalsa.criadas), 1)

    def test_visual_baixa_o_video_pela_sessao_da_leitura(self):
        args = cli._argumentos([self.TIKTOK.url, "--visual", "aula"])
        sessao = SessaoFalsa(self.TIKTOK.url, self.TIKTOK, self.baixou)
        args.sessao = sessao
        with mock.patch.object(fonte, "baixar_video", side_effect=AssertionError("não pode abrir a página de novo")), \
             mock.patch.object(aula, "detectar", side_effect=cli.Erro("parou depois de baixar")), \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(cli.Erro):
                cli._fazer_visual(args, self.saida, {"url": self.TIKTOK.url})
        self.assertEqual(self.baixou, [self.TIKTOK.url])

    def test_erro_do_site_vira_mensagem_com_dica(self):
        from yt_dlp.utils import DownloadError
        erro = DownloadError("[TikTok] 7: Unexpected response from webpage request")
        with mock.patch.object(fonte, "Sessao", lambda url: SessaoFalsa(url, self.TIKTOK, erro_ao_ler=erro)):
            codigo, _, err = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertIn("Unexpected response", err)
        self.assertIn("curl-cffi", err)
        self.assertNotIn("YouTube", err)
        self.assertEqual(SessaoFalsa.criadas[-1].fechada, 1)  # fecha mesmo quando dá erro

    def test_outro_erro_nao_ganha_dica(self):
        self.assertNotIn("curl-cffi", cli._erro_download(RuntimeError("HTTP 404")))
        self.assertIn("curl-cffi", cli._erro_download(RuntimeError("Impersonate target unavailable")))


class _Tom:
    """Entrada falsa a 16 kHz mono: a cada leitura entrega 0,25 s de tom."""

    taxa, canais, descricao = 16000, 1, "dispositivo falso"

    def __init__(self, nome):
        self.nome = nome

    def pegar(self):
        t = np.arange(4000) / 16000
        return (0.4 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16).tobytes()

    def fechar(self):
        pass


def _whisper_falso(caminho, args, idioma):
    fala = {"sistema": Segmento(0.0, 2.0, "Bom dia, pessoal."), "microfone": Segmento(3.0, 4.0, "Bom dia!")}
    return Resultado(fonte="x", duracao_s=5.0, modelo="large-v3-turbo", idioma="pt",
                     segmentos=[fala[Path(caminho).stem]])


def _whisper_falso_arquivo(caminho, args, idioma):
    return Resultado(fonte="x", duracao_s=60.0, modelo="large-v3-turbo", idioma="pt",
                     segmentos=[Segmento(0.0, 2.0, "Texto do áudio.")])


class _TelaFalsa:
    """CapturaTela falsa: escreve um tela.mp4 de mentira e começa 1,5 s antes do áudio (ver setUp)."""

    motor, fps, aviso = "ddagrab", 30, None

    def __init__(self, saida, janela=None, fps=None):
        self.janela = janela
        Path(saida).write_bytes(b"video")
        self.inicio, self.inicio_aproximado = 1000.0, False

    def parar(self):
        return True


class TestGravacaoCli(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        self.gravacoes = self.raiz / "gravacoes"
        self.saida = self.raiz / "transcricoes"
        real = gravacao.gravar

        def gravar_sem_esperar(entradas, pasta, **opcoes):
            agora = [0.0]
            return real(entradas, pasta, relogio=lambda: agora[0],
                        dormir=lambda s: agora.__setitem__(0, agora[0] + s), agora=lambda: 1001.5, **opcoes)

        for objeto, nome, valor in (
            (gravacao, "abrir_entradas", lambda microfone=False: [_Tom("sistema")] + ([_Tom("microfone")] if microfone else [])),
            (gravacao, "gravar", gravar_sem_esperar),
            (cli, "_whisper", _whisper_falso),
            (tela, "CapturaTela", _TelaFalsa),
        ):
            p = mock.patch.object(objeto, nome, valor)
            p.start()
            self.addCleanup(p.stop)

    def rodar(self, argv, tty=False, respostas=()):
        respostas = iter(respostas)
        with mock.patch.object(cli.sys.stdin, "isatty", return_value=tty), \
             mock.patch("builtins.input", lambda prompt: next(respostas)), \
             redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            codigo = cli.main(argv)
        return codigo, out.getvalue(), err.getvalue()

    def gravar(self, *flags, **kw):
        return self.rodar(["gravar", "--duracao", "2", "--gravacoes", str(self.gravacoes),
                           "--saida", str(self.saida), *flags], **kw)

    def pastas_de_audio(self):
        return list(self.gravacoes.iterdir()) if self.gravacoes.exists() else []

    def texto(self):
        (pasta_video,) = list(self.saida.iterdir())
        return (pasta_video / "transcricao.txt").read_text(encoding="utf-8")

    def test_so_gravar_guarda_o_audio_e_diz_como_transcrever(self):
        codigo, out, _ = self.gravar()
        self.assertEqual(codigo, 0)
        (pasta_audio,) = self.pastas_de_audio()
        self.assertTrue((pasta_audio / "sistema.wav").is_file())
        self.assertFalse((pasta_audio / "microfone.wav").exists())
        self.assertIn("vatty " + str(pasta_audio), out)
        self.assertIn("avisar", out)  # lembrete de consentimento
        self.assertFalse(self.saida.exists())

    def test_com_mic_grava_duas_faixas(self):
        self.gravar("--mic")
        (pasta_audio,) = self.pastas_de_audio()
        self.assertTrue((pasta_audio / "microfone.wav").is_file())

    def test_transcrever_junta_as_faixas_com_o_falante(self):
        codigo, _, _ = self.gravar("--mic", "--transcrever", "--manter-audio")
        self.assertEqual(codigo, 0)
        # com duas faixas, o .txt é a linha do tempo e cada canal tem o seu arquivo
        self.assertEqual(self.texto(), "[00:00] Outros: Bom dia, pessoal.\n\n[00:03] Eu: Bom dia!\n")
        (pasta_video,) = list(self.saida.iterdir())
        self.assertEqual((pasta_video / "transcricao-outros.txt").read_text(encoding="utf-8"), "[00:00] Bom dia, pessoal.\n")
        self.assertEqual((pasta_video / "transcricao-eu.txt").read_text(encoding="utf-8"), "[00:03] Bom dia!\n")
        fonte_json = json.loads((pasta_video / "fonte.json").read_text(encoding="utf-8"))
        self.assertEqual(fonte_json["tipo"], "gravacao")
        self.assertEqual(fonte_json["faixas"], ["sistema", "microfone"])
        self.assertEqual(len(self.pastas_de_audio()), 1)  # --manter-audio

    def test_apagar_audio_remove_os_wav_e_a_pasta(self):
        self.gravar("--mic", "--transcrever", "--apagar-audio")
        self.assertEqual(self.pastas_de_audio(), [])
        self.assertTrue(self.saida.exists())  # o texto fica

    def test_sem_flag_e_sem_terminal_guarda_o_audio(self):
        _, out, _ = self.gravar("--transcrever", tty=False)
        self.assertEqual(len(self.pastas_de_audio()), 1)
        self.assertIn("--apagar-audio", out)

    def test_sem_flag_pergunta_e_so_apaga_se_disser_sim(self):
        self.gravar("--transcrever", tty=True, respostas=["s"])
        self.assertEqual(self.pastas_de_audio(), [])

    def test_resposta_vazia_guarda(self):
        self.gravar("--transcrever", tty=True, respostas=[""])
        self.assertEqual(len(self.pastas_de_audio()), 1)

    def test_nao_apaga_o_que_nao_e_do_ata(self):
        # um arquivo estranho na pasta impede o rmdir: a pasta e o arquivo ficam
        original = gravacao.pasta_nova
        def com_extra(raiz, nome):
            pasta_audio = original(raiz, nome)
            pasta_audio.mkdir(parents=True)
            (pasta_audio / "notas.txt").write_text("meu", encoding="utf-8")
            return pasta_audio
        with mock.patch.object(gravacao, "pasta_nova", com_extra):
            self.gravar("--transcrever", "--apagar-audio")
        (pasta_audio,) = self.pastas_de_audio()
        self.assertEqual([p.name for p in pasta_audio.iterdir()], ["notas.txt"])

    def test_transcrever_uma_gravacao_ja_existente_pela_pasta(self):
        self.gravar("--mic")
        (pasta_audio,) = self.pastas_de_audio()
        codigo, _, _ = self.rodar([str(pasta_audio), "--saida", str(self.saida), "--manter-audio"])
        self.assertEqual(codigo, 0)
        self.assertIn("Eu: Bom dia!", self.texto())

    def test_pasta_sem_faixas_da_erro(self):
        vazia = self.raiz / "vazia"
        vazia.mkdir()
        codigo, _, err = self.rodar([str(vazia), "--saida", str(self.saida)])
        self.assertEqual(codigo, 1)
        self.assertIn("sistema.wav", err)

    def test_erro_ao_abrir_o_dispositivo(self):
        def falha(microfone=False):
            raise gravacao.ErroGravacao("a gravação só funciona no Windows por enquanto.")
        with mock.patch.object(gravacao, "abrir_entradas", falha):
            codigo, _, err = self.gravar()
        self.assertEqual(codigo, 1)
        self.assertIn("Windows", err)
        self.assertEqual(self.pastas_de_audio(), [])

    def test_faixa_muda_gera_aviso(self):
        class Muda(_Tom):
            def pegar(self):
                return b""
        with mock.patch.object(gravacao, "abrir_entradas", lambda microfone=False: [Muda("sistema")]):
            _, out, _ = self.gravar()
        self.assertIn("quase muda", out)


    def fonte_json(self):
        (pasta_video,) = list(self.saida.iterdir())
        return json.loads((pasta_video / "fonte.json").read_text(encoding="utf-8"))

    def test_tela_avisa_grava_o_video_e_os_inicios(self):
        codigo, out, _ = self.gravar("--tela")
        self.assertEqual(codigo, 0)
        self.assertIn("senha", out)  # aviso de privacidade
        (pasta_audio,) = self.pastas_de_audio()
        self.assertTrue((pasta_audio / "tela.mp4").is_file())
        meta = gravacao.ler_metadados(pasta_audio)
        self.assertEqual(meta["inicios"], {"sistema": 1001.5, "tela": 1000.0})
        self.assertEqual((meta["tela"]["alvo"], meta["tela"]["motor"]), ("tela inteira", "ddagrab"))
        self.assertIn(f"vatty {pasta_audio} --visual app", out)  # o perfil app é o padrão da gravação

    def test_tela_transcrever_tira_os_slides_na_linha_do_audio_e_apaga_a_tela(self):
        with mock.patch.object(cli, "_fazer_visual") as fazer:
            codigo, _, _ = self.gravar("--tela", "--transcrever", "--manter-audio")
        self.assertEqual(codigo, 0)
        (pasta_audio,) = self.pastas_de_audio()
        _, _, _, video, deslocamento = fazer.call_args.args
        self.assertEqual((video, deslocamento), (pasta_audio / "tela.mp4", -1.5))
        self.assertFalse(video.exists())
        self.assertEqual(self.fonte_json()["inicios"]["tela"], 1000.0)

    def test_tela_fps_e_perfil_aula(self):
        with mock.patch.object(tela, "CapturaTela", wraps=_TelaFalsa) as captura, \
                mock.patch.object(cli, "_fazer_visual") as fazer:
            self.gravar("--tela", "--tela-fps", "15", "--visual", "aula", "--transcrever", "--manter-audio")
        self.assertEqual(captura.call_args.kwargs["fps"], 15)
        self.assertEqual(fazer.call_args.args[0].visual, "aula")

    def test_manter_tela(self):
        with mock.patch.object(cli, "_fazer_visual"):
            self.gravar("--tela", "--transcrever", "--apagar-audio", "--manter-tela")
        (pasta_audio,) = self.pastas_de_audio()
        self.assertEqual(sorted(p.name for p in pasta_audio.iterdir()), ["gravacao.json", "tela.mp4"])

    def test_tela_janela_grava_so_a_janela(self):
        with mock.patch.object(tela, "CapturaTela", wraps=_TelaFalsa) as captura:
            self.gravar("--tela-janela", "Aula - Zoom")
        self.assertEqual(captura.call_args.kwargs["janela"], "Aula - Zoom")
        (pasta_audio,) = self.pastas_de_audio()
        self.assertEqual(gravacao.ler_metadados(pasta_audio)["tela"]["alvo"], "Aula - Zoom")

    def test_visual_falhou_sai_com_1_e_guarda_a_gravacao_inteira(self):
        with mock.patch.object(cli, "_fazer_visual", side_effect=quadros.ErroDeVideo("vídeo ilegível")):
            codigo, _, err = self.gravar("--tela", "--transcrever", "--apagar-audio")
        self.assertEqual(codigo, 1)
        self.assertIn("tentar de novo", err)
        (pasta_audio,) = self.pastas_de_audio()
        self.assertTrue((pasta_audio / "tela.mp4").is_file())
        self.assertTrue((pasta_audio / "sistema.wav").is_file())
        self.assertTrue(self.saida.exists())  # o texto ficou

    def test_erro_ao_abrir_a_tela_nao_deixa_pasta(self):
        def falha(saida, janela=None, fps=None):
            raise tela.ErroTela("a gravação da tela só funciona no Windows por enquanto.")
        with mock.patch.object(tela, "CapturaTela", falha):
            codigo, _, err = self.gravar("--tela")
        self.assertEqual(codigo, 1)
        self.assertIn("tela", err)
        self.assertEqual(self.pastas_de_audio(), [])

    def test_sem_tela_a_gravacao_continua_igual(self):
        self.gravar("--mic", "--transcrever", "--manter-audio")
        (pasta_audio,) = self.pastas_de_audio()
        self.assertEqual(sorted(p.name for p in pasta_audio.iterdir()), ["microfone.wav", "sistema.wav"])
        self.assertEqual(sorted(self.fonte_json()), ["data", "duracao_s", "faixas", "falantes", "tipo", "titulo"])


class TestVisualCli(unittest.TestCase):
    INFO = {"largura": 1280, "altura": 720, "duracao_s": 60.0}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        self.saida = self.raiz / "transcricoes"
        self.baixou = []
        self.palpite = ({"vertical": False, "trocas": 3, "trocas_por_min": 3.0, "tempo_medio_s": 20.0,
                         "palavras_por_tela": 25.0}, ("aula", "tela estável com bastante texto"))
        self.slides = [visual.Slide(0, 30, 2), visual.Slide(30, 60, 32)]

        SessaoFalsa.criadas = []
        self.detectar = mock.Mock(side_effect=lambda video, **kw: aula.Deteccao(self.INFO, list(self.slides), False))
        self.montar = mock.Mock(side_effect=lambda video, d, destino, **kw: {
            "perfil": "aula", "eventos": [{"tipo": "slide", "inicio": 0.0, "fim": 30.0, "texto": "Olá", "frame": "frames/0001.jpg"}]})
        for objeto, nome, valor in (
            (fonte, "Sessao", lambda url: SessaoFalsa(url, baixou=self.baixou)),
            (ocr, "verificar", lambda idiomas: "tesseract"),
            (aula, "detectar", self.detectar),
            (aula, "palpite", lambda *a, **kw: self.palpite),
            (aula, "montar", self.montar),
            (cli, "_whisper", _whisper_falso_arquivo),
        ):
            p = mock.patch.object(objeto, nome, valor)
            p.start()
            self.addCleanup(p.stop)

    def rodar(self, entrada, *flags, tty=True, respostas=()):
        respostas = iter(respostas)
        with mock.patch.object(cli.sys.stdin, "isatty", return_value=tty), \
             mock.patch("builtins.input", lambda prompt: next(respostas)), \
             redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            codigo = cli.main([entrada, "--saida", str(self.saida), *flags])
        return codigo, out.getvalue(), err.getvalue()

    def youtube(self, *flags, **kw):
        return self.rodar(VIDEO.url, "--texto", "legenda", *flags, **kw)

    @property
    def pasta_video(self):
        return self.saida / "aula-abc"

    def test_padrao_nao_faz_visual(self):
        codigo, _, _ = self.youtube()
        self.assertEqual(codigo, 0)
        self.detectar.assert_not_called()
        self.assertEqual(self.baixou, [])

    def test_aula_baixa_o_video_e_grava_o_visual_depois_do_texto(self):
        codigo, out, _ = self.youtube("--visual", "aula")
        self.assertEqual(codigo, 0)
        self.assertEqual(self.baixou, [VIDEO.url])
        self.assertTrue((self.pasta_video / "transcricao.txt").is_file())
        lido = json.loads((self.pasta_video / "visual.json").read_text(encoding="utf-8"))
        self.assertEqual(lido["eventos"][0]["texto"], "Olá")
        self.assertIn("1 slide", out)

    def test_aula_passa_o_idioma_do_ocr(self):
        self.youtube("--visual", "aula", "--lang", "en")
        self.assertEqual(self.montar.call_args.kwargs["idiomas"], "eng")
        self.youtube("--visual", "aula")
        self.assertEqual(self.montar.call_args.kwargs["idiomas"], "por+eng")

    def test_auto_sem_terminal_falha_antes_de_fazer_qualquer_coisa(self):
        codigo, _, err = self.youtube("--visual", "auto", tty=False)
        self.assertEqual(codigo, 1)
        self.assertIn("--visual aula", err)
        self.assertFalse(self.saida.exists())
        self.assertEqual(self.baixou, [])

    def test_auto_enter_aceita_o_palpite_aula(self):
        codigo, out, _ = self.youtube("--visual", "auto", respostas=[""])
        self.assertEqual(codigo, 0)
        self.assertIn("Palpite: aula", out)
        self.assertIn("25.0 palavras por tela", out)
        self.assertTrue((self.pasta_video / "visual.json").is_file())

    def test_auto_com_palpite_nenhum_enter_pula(self):
        self.palpite = ({**self.palpite[0], "palavras_por_tela": 2.0}, ("nenhum", "pouco texto na tela"))
        codigo, out, _ = self.youtube("--visual", "auto", respostas=[""])
        self.assertEqual(codigo, 0)
        self.assertIn("Visual pulado", out)
        self.assertFalse((self.pasta_video / "visual.json").exists())
        self.montar.assert_not_called()

    def test_auto_o_usuario_pode_discordar_do_palpite(self):
        self.palpite = ({**self.palpite[0], "palavras_por_tela": 2.0}, ("nenhum", "pouco texto na tela"))
        self.youtube("--visual", "auto", respostas=["s"])
        self.assertTrue((self.pasta_video / "visual.json").is_file())
        self.baixou.clear()
        self.palpite = (self.palpite[0], ("aula", "x"))
        self.youtube("--visual", "auto", respostas=["n"])
        self.assertFalse(self.montar.call_args is None)

    def test_palpite_corte_avisa_que_ainda_nao_existe(self):
        self.palpite = ({**self.palpite[0], "vertical": True}, ("corte", "vídeo vertical"))
        _, out, _ = self.youtube("--visual", "auto", respostas=["n"])
        self.assertIn("ainda não existe", out)

    def test_sem_tesseract_falha_antes_de_baixar_o_video_e_o_texto_fica(self):
        def sem(idiomas):
            raise ocr.ErroOcr("Tesseract não encontrado. Instale o Tesseract")
        with mock.patch.object(ocr, "verificar", sem):
            codigo, _, err = self.youtube("--visual", "aula")
        self.assertEqual(codigo, 1)
        self.assertIn("Tesseract", err)
        self.assertEqual(self.baixou, [])
        self.assertTrue((self.pasta_video / "transcricao.txt").is_file())

    def test_erro_no_video_mantem_o_texto_e_avisa(self):
        self.detectar.side_effect = quadros.ErroDeVideo("ffmpeg não conseguiu ler video.mp4")
        codigo, _, err = self.youtube("--visual", "aula")
        self.assertEqual(codigo, 1)
        self.assertIn("O texto já está salvo", err)
        self.assertTrue((self.pasta_video / "transcricao.txt").is_file())
        self.assertFalse((self.pasta_video / "visual.json").exists())

    def test_video_sem_nenhuma_tela(self):
        self.slides = []
        codigo, _, err = self.youtube("--visual", "aula")
        self.assertEqual(codigo, 1)
        self.assertIn("nenhuma tela", err)

    def test_arquivo_local_nao_baixa_nada_e_usa_o_proprio_arquivo(self):
        arquivo = self.raiz / "aula.mp4"
        arquivo.write_bytes(b"v")
        codigo, _, _ = self.rodar(str(arquivo), "--visual", "aula")
        self.assertEqual(codigo, 0)
        self.assertEqual(self.baixou, [])
        self.assertEqual(Path(self.detectar.call_args.args[0]), arquivo)
        self.assertTrue((self.saida / "aula" / "visual.json").is_file())

    def test_perfil_app_num_video_local(self):
        arquivo = self.raiz / "teste-do-app.mp4"
        arquivo.write_bytes(b"v")
        dados = {"perfil": "app", "eventos": [{"tipo": "transitorio", "inicio": 1.0, "fim": 2.0, "texto": "Erro"}]}
        with mock.patch.object(cli.app, "montar", return_value=dados) as montar:
            codigo, _, _ = self.rodar(str(arquivo), "--visual", "app")
        self.assertEqual(codigo, 0)
        self.assertEqual(Path(montar.call_args.args[0]), arquivo)
        self.detectar.assert_not_called()  # o perfil aula não roda
        self.assertIn('"perfil": "app"', (self.saida / "teste-do-app" / "visual.json").read_text(encoding="utf-8"))

    def test_gravacao_de_audio_ignora_o_visual(self):
        pasta_audio = self.raiz / "gravacoes" / "2026-10-10_14-30"
        pasta_audio.mkdir(parents=True)
        (pasta_audio / "sistema.wav").write_bytes(b"x")
        with mock.patch.object(cli, "_whisper", _whisper_falso):
            codigo, out, _ = self.rodar(str(pasta_audio), "--visual", "aula", "--manter-audio")
        self.assertEqual(codigo, 0)
        self.assertIn("não se aplica", out)
        self.detectar.assert_not_called()


class TestOpcoesDoWhisper(unittest.TestCase):
    """Horário por palavra e VAD chegam ao motor; o resto fica como estava."""

    def chamar(self, *argv, em_gravacao=False):
        # --preprocessar nao: estes testes olham só as opções do Whisper (o arquivo "a.wav" nem existe)
        args = cli._argumentos(["entrada.opus", "--preprocessar", "nao", *argv])
        if em_gravacao:
            args = argparse.Namespace(**{**vars(args), "em_gravacao": True})
        resultado = Resultado(fonte="x", duracao_s=1.0, modelo="m", idioma="pt")
        with mock.patch.object(cli.motor, "modelo_em_cache", return_value=True), \
                mock.patch.object(cli.motor, "transcrever", return_value=resultado) as transcrever, \
                redirect_stdout(io.StringIO()):
            cli._whisper(Path("a.wav"), args, "pt")
        return transcrever.call_args.kwargs

    def test_arquivo_e_youtube_ficam_como_antes(self):
        opcoes = self.chamar()
        self.assertIs(opcoes["palavras"], False)
        self.assertIsNone(opcoes["vad_silencio_ms"])

    def test_gravacao_liga_o_horario_por_palavra_no_automatico(self):
        self.assertIs(self.chamar(em_gravacao=True)["palavras"], True)

    def test_nao_desliga_mesmo_em_gravacao_e_sim_liga_em_qualquer_caso(self):
        self.assertIs(self.chamar("--horario-por-palavra", "nao", em_gravacao=True)["palavras"], False)
        self.assertIs(self.chamar("--horario-por-palavra", "sim")["palavras"], True)

    def test_termos_aceita_varios_arquivos_e_junta_sem_repetir(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.txt", Path(tmp) / "b.txt"
            a.write_text("IA\nClaude\n", encoding="utf-8")
            b.write_text("mano\nia\n", encoding="utf-8")
            self.assertEqual(self.chamar("--termos", str(a), str(b))["hotwords"], "IA, Claude, mano")
            # repetindo a opção também vale
            self.assertEqual(self.chamar("--termos", str(a), "--termos", str(b))["hotwords"], "IA, Claude, mano")
            # a entrada pode vir depois dos arquivos, separada por --
            args = cli._argumentos(["--termos", str(a), str(b), "--", "entrada.opus"])
            self.assertEqual(args.entrada, "entrada.opus")
            self.assertEqual(args.termos, [a, b])

    def test_sem_termos_nao_manda_hotwords(self):
        self.assertIsNone(self.chamar()["hotwords"])

    def test_vad_silencio_ms(self):
        self.assertEqual(self.chamar("--vad-silencio-ms", "500")["vad_silencio_ms"], 500)

    def test_do_gravacao_marca_as_duas_faixas_como_gravacao(self):
        vistos = []

        def whisper(caminho, args, idioma):
            vistos.append(getattr(args, "em_gravacao", False))
            return Resultado(fonte="x", duracao_s=1.0, modelo="m", idioma="pt", segmentos=[Segmento(0.0, 1.0, "oi")])

        args = cli._argumentos(["gravacoes/2026-10-10_09-00"])
        faixas = {"sistema": Path("sistema.wav"), "microfone": Path("microfone.wav")}
        with mock.patch.object(gravacao, "faixas_na_pasta", return_value=faixas), \
                mock.patch.object(cli, "_whisper", whisper), redirect_stdout(io.StringIO()):
            _, dados, resultado = cli._do_gravacao(args, Path("gravacoes/2026-10-10_09-00"))
        self.assertEqual(vistos, [True, True])
        self.assertEqual(resultado.faixas, ["sistema", "microfone"])
        self.assertFalse(getattr(args, "em_gravacao", False))  # os args originais não mudam


class TestPreprocessarNaCli(unittest.TestCase):
    """--preprocessar: o padrão pergunta, e o que o preparo devolve chega ao motor e ao resultado."""

    def test_padrao_e_perguntar_e_aceita_sim_nao(self):
        self.assertEqual(cli._argumentos(["a.opus"]).preprocessar, "perguntar")
        self.assertEqual(cli._argumentos(["a.opus", "--preprocessar", "sim"]).preprocessar, "sim")
        self.assertEqual(cli._argumentos(["a.opus", "--preprocessar", "nao"]).preprocessar, "nao")
        self.assertIsNone(cli._argumentos(["a.opus"]).ruido_modelo)
        self.assertEqual(cli._argumentos(["a.opus", "--ruido-modelo", "beguiling-drafter"]).ruido_modelo,
                         "beguiling-drafter")

    def _rodar(self, preparo, *argv):
        args = cli._argumentos(["entrada.opus", *argv])
        resultado = Resultado(fonte="x", duracao_s=1.0, modelo="m", idioma="pt")
        with mock.patch.object(cli.motor, "modelo_em_cache", return_value=True), \
                mock.patch.object(cli.motor, "transcrever", return_value=resultado) as transcrever, \
                mock.patch.object(cli.preprocessar, "preparar", return_value=preparo) as preparar, \
                redirect_stdout(io.StringIO()):
            devolvido = cli._whisper(Path("a.wav"), args, "pt")
        return devolvido, transcrever.call_args.kwargs, preparar

    def test_o_que_o_preparo_devolve_chega_ao_motor_e_ao_resultado(self):
        carregar = lambda caminho: ([0.0], 1.0)
        info = {"aplicado": True, "filtro": "highpass=f=80"}
        resultado, kwargs, preparar = self._rodar(cli.preprocessar.Preparo(carregar, info), "--preprocessar", "sim",
                                                  "--ruido-modelo", "leavened-quisling")
        self.assertIs(kwargs["carregar_audio"], carregar)
        self.assertEqual(resultado.preprocessamento, info)
        self.assertEqual(preparar.call_args.args[1], "sim")
        self.assertEqual(preparar.call_args.kwargs["ruido_modelo"], "leavened-quisling")

    def test_sem_preprocessamento_o_motor_carrega_como_sempre(self):
        resultado, kwargs, _ = self._rodar(cli.preprocessar.Preparo())
        self.assertNotIn("carregar_audio", kwargs)
        self.assertIsNone(resultado.preprocessamento)

    def test_pergunta_enter_aceita_n_recusa(self):
        for resposta, esperado in (("", True), ("s", True), ("n", False), ("não", False)):
            with mock.patch("builtins.input", return_value=resposta), redirect_stdout(io.StringIO()):
                self.assertIs(cli._perguntar_preprocessar(None), esperado, resposta)

    def test_pergunta_cancelada_sem_entrada(self):
        with mock.patch("builtins.input", side_effect=EOFError), self.assertRaises(cli.Erro):
            cli._perguntar_preprocessar(None)


class TestSepararFalantesNaCli(unittest.TestCase):
    """--falantes: opções, avisos em vez de erro, e o que chega ao resultado."""

    def setUp(self):
        import numpy as np
        self.np = np

    def args(self, *argv):
        return cli._argumentos(["entrada.opus", *argv])

    def voz(self):
        class Voz:
            nome = "falsa"

            def trechos_de_fala(self, amostras):
                return [(0.0, 10.0), (12.0, 22.0)]

            def embutir(self, amostras, janelas):
                base = {0: [1.0, 0.0, 0.0], 1: [0.0, 1.0, 0.0]}
                return self_np.array([base[0 if (i + f) / 2 < 11 else 1] for i, f in janelas])
        self_np = self.np
        return Voz()

    def separar(self, *argv, cadastrados=None):
        resultado = Resultado(fonte="x", duracao_s=22.0, modelo="m", idioma="pt",
                              segmentos=[Segmento(0.0, 9.0, "oi"), Segmento(12.0, 21.0, "tchau")])
        saida = io.StringIO()
        with redirect_stdout(saida), \
                mock.patch.object(cli.perfis, "carregar", return_value=(cadastrados or {}, [])):
            cli._separar_falantes(Path("a.wav"), resultado, self.args(*argv), criar_vozes=self.voz,
                                  carregar=lambda c: (self.np.zeros(16000 * 22, dtype="float32"), 22.0))
        return resultado, saida.getvalue()

    def test_opcoes(self):
        self.assertEqual(self.args().falantes, "nao")
        self.assertEqual(self.args("--falantes", "5").falantes, "5")
        self.assertEqual(self.args("--falantes", "AUTO").falantes, "auto")
        self.assertEqual(self.args("--falantes", "perfis", "--perfis", "Ana", "Beto").perfis, ["Ana", "Beto"])
        for ruim in ("0", "-2", "muitos", ""):
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                self.args("--falantes", ruim)

    def test_padrao_nao_mexe_em_nada(self):
        resultado, saida = self.separar()
        self.assertIsNone(resultado.falantes)
        self.assertEqual([s.pessoa for s in resultado.segmentos], [None, None])
        self.assertEqual(saida, "")

    def test_auto_poe_pessoa_nos_segmentos_e_guarda_os_turnos(self):
        resultado, saida = self.separar("--falantes", "auto")
        self.assertEqual([s.pessoa for s in resultado.segmentos], ["Pessoa 1", "Pessoa 2"])
        self.assertEqual(resultado.falantes["modo"], "agrupar")
        self.assertEqual({t["pessoa"] for t in resultado.falantes["turnos"]}, {"Pessoa 1", "Pessoa 2"})
        self.assertIn("Pessoa 1", saida)

    def test_numero_fixo_chega_ao_agrupamento(self):
        resultado, _ = self.separar("--falantes", "1")
        self.assertEqual({s.pessoa for s in resultado.segmentos}, {"Pessoa 1"})
        self.assertEqual(resultado.falantes["falantes_pedidos"], 1)

    def test_perfis_reconhece_e_marca_desconhecido(self):
        resultado, _ = self.separar("--falantes", "perfis", cadastrados={"Ana": self.np.array([1.0, 0.0, 0.0])})
        self.assertEqual([s.pessoa for s in resultado.segmentos], ["Ana", "Desconhecido"])

    def test_perfis_sem_nenhum_perfil_avisa_e_segue_sem_separar(self):
        resultado, saida = self.separar("--falantes", "perfis")
        self.assertIn("Aviso", saida)
        self.assertIsNone(resultado.falantes)
        self.assertEqual([s.pessoa for s in resultado.segmentos], [None, None])

    def test_perfis_nenhum_nao_usa_perfil(self):
        resultado, _ = self.separar("--falantes", "auto", "--perfis", "nenhum",
                                    cadastrados={"Ana": self.np.array([1.0, 0.0, 0.0])})
        self.assertEqual(resultado.falantes["perfis_usados"], [])

    def test_sem_sherpa_vira_aviso_e_o_texto_fica(self):
        def sem_modelo():
            raise cli.vozes.VozesIndisponiveis("falta o sherpa-onnx")

        resultado = Resultado(fonte="x", duracao_s=1.0, modelo="m", idioma="pt", segmentos=[Segmento(0.0, 1.0, "oi")])
        saida = io.StringIO()
        with redirect_stdout(saida):
            cli._separar_falantes(Path("a.wav"), resultado, self.args("--falantes", "auto"), criar_vozes=sem_modelo)
        self.assertIn("sem separação de falantes", saida.getvalue())
        self.assertEqual(resultado.segmentos[0].texto, "oi")
        self.assertIsNone(resultado.falantes)


class TestPerfilNaCli(unittest.TestCase):
    def setUp(self):
        import os
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pasta = Path(tmp.name) / "perfis"
        antigo = os.environ.get("VATTY_PERFIS")
        os.environ["VATTY_PERFIS"] = str(self.pasta)
        self.addCleanup(lambda: os.environ.__setitem__("VATTY_PERFIS", antigo) if antigo else os.environ.pop("VATTY_PERFIS", None))

    def rodar(self, *argv, voz=None):
        import numpy as np

        class Voz:
            nome = "falsa"

            def trechos_de_fala(self, amostras):
                return [(0.0, 25.0)]

            def embutir(self, amostras, janelas):
                return np.tile([1.0, 0.0], (len(janelas), 1))

        saida, erro = io.StringIO(), io.StringIO()
        with redirect_stdout(saida), redirect_stderr(erro):
            codigo = cli._main_perfil(list(argv), criar_vozes=voz or Voz,
                                      carregar=lambda c: (np.zeros(16000 * 25, dtype="float32"), 25.0))
        return codigo, saida.getvalue(), erro.getvalue()

    def test_sem_consentimento_recusa(self):
        with mock.patch.object(cli, "_confirmar_consentimento", return_value=False):  # a pessoa diz que não
            codigo, _, erro = self.rodar("criar", "Ana", "a.wav")
        self.assertEqual(codigo, 1)
        self.assertIn("consentimento", erro)
        self.assertFalse(self.pasta.exists())

    def test_criar_listar_e_apagar(self):
        codigo, saida, _ = self.rodar("criar", "Ana", "a.wav", "--consentimento")
        self.assertEqual(codigo, 0)
        self.assertIn("não foi guardado", saida)
        self.assertIn("Ana", self.rodar("listar")[1])
        self.assertEqual(self.rodar("apagar", "Ana")[0], 0)
        self.assertIn("Nenhum perfil", self.rodar("listar")[1])

    def test_amostra_curta_demais_vira_erro_claro(self):
        class Curta:
            nome = "falsa"

            def trechos_de_fala(self, amostras):
                return [(0.0, 3.0)]

        codigo, _, erro = self.rodar("criar", "Ana", "a.wav", "--consentimento", voz=Curta)
        self.assertEqual(codigo, 1)
        self.assertIn("pelo menos", erro)

    def test_apagar_o_que_nao_existe(self):
        codigo, _, erro = self.rodar("apagar", "Zé")
        self.assertEqual(codigo, 1)
        self.assertIn("não existe", erro)


class TestGlossarioNaCli(unittest.TestCase):
    def _pasta(self, d):
        (Path(d) / "fonte.json").write_text(json.dumps({"tipo": "arquivo"}))
        (Path(d) / "transcricao.json").write_text(json.dumps({
            "origem": "whisper", "modelo": "m", "idioma": "pt", "duracao_s": 2, "fonte": "a.opus",
            "segmentos": [{"inicio": 0, "fim": 1, "texto": "oi natty"}]}))
        gl = Path(d) / "gl.txt"
        gl.write_text("natty = Nattie\n")
        return gl

    def test_corrigir_refaz_json_e_txt_e_e_idempotente(self):
        with tempfile.TemporaryDirectory() as d:
            gl = self._pasta(d)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["corrigir", d, "--glossario", str(gl)]), 0)
            dados = json.loads((Path(d) / "transcricao.json").read_text(encoding="utf-8"))
            self.assertEqual(dados["glossario"], {"natty": 1})
            self.assertEqual(dados["segmentos"][0]["texto"], "oi Nattie")
            self.assertIn("oi Nattie", (Path(d) / "transcricao.txt").read_text(encoding="utf-8"))
            saida = io.StringIO()
            with redirect_stdout(saida):
                cli.main(["corrigir", d, "--glossario", str(gl)])
            self.assertIn("Nada para corrigir", saida.getvalue())

    def test_glossario_inexistente_e_erro(self):
        with tempfile.TemporaryDirectory() as d:
            self._pasta(d)
            with redirect_stderr(io.StringIO()) as erro:
                self.assertEqual(cli.main(["corrigir", d, "--glossario", str(Path(d) / "nao.txt")]), 1)
            self.assertIn("Não achei o glossário", erro.getvalue())


class TestNovosComandosNaCli(unittest.TestCase):
    def test_cartoes_gera_csv_e_erra_sem_md(self):
        with tempfile.TemporaryDirectory() as d:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["cartoes", d]), 1)
            (Path(d) / "cartoes-a.md").write_text("## T\nP: a?\nR: b\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["cartoes", d]), 0)
            self.assertTrue((Path(d) / "cartoes-a.csv").is_file())

    def test_traduzir_prepara_e_monta(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "transcricao.json").write_text(json.dumps({"segmentos": [{"inicio": 0, "fim": 1, "texto": "oi"}]}))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["traduzir", "preparar", d, "--para", "en"]), 0)
            (Path(d) / "traducao-en.txt").write_text("1|hi\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["traduzir", "montar", d, "--para", "en"]), 0)
            self.assertIn("hi", (Path(d) / "legenda.en.srt").read_text(encoding="utf-8"))

    def test_perguntar_grava_trechos_ou_avisa_que_nao_achou(self):
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "aula"
            v.mkdir()
            (v / "transcricao.txt").write_text("[00:05] a margem sobe\n", encoding="utf-8")
            saida = io.StringIO()
            with redirect_stdout(saida):
                self.assertEqual(cli.main(["perguntar", "margem", "--raiz", d]), 0)
            self.assertTrue((Path(d) / "_consultas" / "margem" / "trechos.md").is_file())
            saida = io.StringIO()
            with redirect_stdout(saida):
                cli.main(["perguntar", "zzzz", "--raiz", d])
            self.assertIn("Não achei trechos", saida.getvalue())


class TestLoteNaCli(unittest.TestCase):
    def test_roda_cada_item_grava_relatorio_e_sai_com_1_se_algum_falhou(self):
        with tempfile.TemporaryDirectory() as d:
            ok, ruim = Path(d) / "a.opus", Path(d) / "b.opus"
            ok.write_bytes(b"x")
            ruim.write_bytes(b"x")
            lista = Path(d) / "lista.txt"
            lista.write_text(f"{ok}\n{ruim}\n")
            chamadas = []

            def falso(argv, **kw):
                chamadas.append(argv)
                falhou = str(ruim) in argv
                return mock.Mock(returncode=1 if falhou else 0, stdout="", stderr="Erro: ffmpeg" if falhou else "")

            saida = io.StringIO()
            with mock.patch("subprocess.run", falso), redirect_stdout(saida):
                codigo = cli.main(["lote", str(lista), "--saida", str(Path(d) / "t")])
            self.assertEqual((codigo, len(chamadas)), (1, 2))
            self.assertIn("1 pronto(s), 1 com erro", saida.getvalue())
            relatorio = json.loads((Path(d) / "t" / "lote-relatorio.json").read_text(encoding="utf-8"))
            self.assertEqual(relatorio["itens"][1]["mensagem"], "Erro: ffmpeg")

    def test_fonte_inexistente_e_erro(self):
        with redirect_stderr(io.StringIO()) as erro:
            self.assertEqual(cli.main(["lote", "/nao/existe.txt"]), 1)
        self.assertIn("Não achei", erro.getvalue())


class TestLegendaNaCli(unittest.TestCase):
    def test_gera_srt_e_erra_sem_transcricao(self):
        with tempfile.TemporaryDirectory() as d:
            erro = io.StringIO()
            with redirect_stderr(erro):
                self.assertEqual(cli.main(["legenda", d]), 1)
            self.assertIn("Transcreva", erro.getvalue())
            (Path(d) / "transcricao.json").write_text(json.dumps({"segmentos": [{"inicio": 0, "fim": 1, "texto": "oi"}]}))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["legenda", d, "--formato", "srt", "vtt"]), 0)
            self.assertTrue((Path(d) / "legenda.vtt").is_file())


class TestBuscarNaCli(unittest.TestCase):
    def test_subcomando_buscar_chama_o_modulo(self):
        import tempfile
        with tempfile.TemporaryDirectory() as raiz:
            saida = io.StringIO()
            with redirect_stdout(saida):
                codigo = cli.main(["buscar", "nada", "--raiz", raiz])
        self.assertEqual(codigo, 0)
        self.assertIn("Nada achado", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
