import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import numpy as np

from vatty import aula, cli, fonte, gravacao, ocr, quadros, visual
from vatty.aplicacao import Opcoes, pipeline
from vatty.motor import Resultado, Segmento

VIDEO = fonte.Video(
    id="abc", url="https://www.youtube.com/watch?v=abc", titulo="Aula", canal="C",
    duracao_s=60.0, data=None, idioma="pt", legendas={"pt-BR": []}, legendas_automaticas={},
)


def _vtt(url, chave, automatica, destino):
    caminho = Path(destino) / "legenda.vtt"
    caminho.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nOlá, turma.\n", encoding="utf-8")
    return caminho


class TestFluxoYoutube(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.saida = Path(tmp.name)
        for alvo, valor in (("inspecionar", lambda url: VIDEO), ("baixar_legenda", _vtt)):
            p = mock.patch.object(fonte, alvo, valor)
            p.start()
            self.addCleanup(p.stop)
        self.whisper = mock.patch.object(pipeline, "_whisper", return_value=Resultado(
            fonte="x", duracao_s=60.0, modelo="large-v3-turbo", idioma="pt",
            segmentos=[Segmento(0, 1, "do whisper")]))
        self.whisper.start()
        self.addCleanup(self.whisper.stop)
        p = mock.patch.object(fonte, "baixar_audio", lambda url, destino: Path(destino) / "audio.webm")
        p.start()
        self.addCleanup(p.stop)

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
        pipeline._whisper.assert_not_called()

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
        with mock.patch.object(fonte, "inspecionar", lambda url: sem):
            codigo, out, _ = self.rodar(tty=False)
        self.assertEqual(codigo, 0)
        self.assertIn("Sem legenda", out)
        self.assertEqual(self.transcricao(), "[00:00] do whisper\n")


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


def _whisper_falso(caminho, opcoes, idioma, *_, **__):
    fala = {"sistema": Segmento(0.0, 2.0, "Bom dia, pessoal."), "microfone": Segmento(3.0, 4.0, "Bom dia!")}
    return Resultado(fonte="x", duracao_s=5.0, modelo="large-v3-turbo", idioma="pt",
                     segmentos=[fala[Path(caminho).stem]])


def _whisper_falso_arquivo(caminho, opcoes, idioma, *_, **__):
    return Resultado(fonte="x", duracao_s=60.0, modelo="large-v3-turbo", idioma="pt",
                     segmentos=[Segmento(0.0, 2.0, "Texto do áudio.")])


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
                        dormir=lambda s: agora.__setitem__(0, agora[0] + s), **opcoes)

        for objeto, nome, valor in (
            (gravacao, "abrir_entradas", lambda microfone=False: [_Tom("sistema")] + ([_Tom("microfone")] if microfone else [])),
            (gravacao, "gravar", gravar_sem_esperar),
            (pipeline, "_whisper", _whisper_falso),
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

        def baixar_video(url, destino):
            self.baixou.append(url)
            caminho = Path(destino) / "video.mp4"
            caminho.write_bytes(b"v")
            return caminho

        self.detectar = mock.Mock(side_effect=lambda video, **kw: aula.Deteccao(self.INFO, list(self.slides), False))
        self.montar = mock.Mock(side_effect=lambda video, d, destino, **kw: {
            "perfil": "aula", "eventos": [{"tipo": "slide", "inicio": 0.0, "fim": 30.0, "texto": "Olá", "frame": "frames/0001.jpg"}]})
        for objeto, nome, valor in (
            (fonte, "inspecionar", lambda url: VIDEO),
            (fonte, "baixar_legenda", _vtt),
            (fonte, "baixar_video", baixar_video),
            (fonte, "baixar_audio", lambda url, destino: Path(destino) / "audio.webm"),
            (ocr, "verificar", lambda idiomas: "tesseract"),
            (aula, "detectar", self.detectar),
            (aula, "palpite", lambda *a, **kw: self.palpite),
            (aula, "montar", self.montar),
            (pipeline, "_whisper", _whisper_falso_arquivo),
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

    def test_gravacao_de_audio_ignora_o_visual(self):
        pasta_audio = self.raiz / "gravacoes" / "2026-10-10_14-30"
        pasta_audio.mkdir(parents=True)
        (pasta_audio / "sistema.wav").write_bytes(b"x")
        with mock.patch.object(pipeline, "_whisper", _whisper_falso):
            codigo, out, _ = self.rodar(str(pasta_audio), "--visual", "aula", "--manter-audio")
        self.assertEqual(codigo, 0)
        self.assertIn("não se aplica", out)
        self.detectar.assert_not_called()


class TestOpcoesDoWhisper(unittest.TestCase):
    """Horário por palavra e VAD chegam ao motor; o resto fica como estava."""

    def chamar(self, *argv, em_gravacao=False):
        # --preprocessar nao: estes testes olham só as opções do Whisper (o arquivo "a.wav" nem existe)
        opcoes = Opcoes.de_dict(vars(cli._argumentos(["entrada.opus", "--preprocessar", "nao", *argv])))
        resultado = Resultado(fonte="x", duracao_s=1.0, modelo="m", idioma="pt")
        with mock.patch.object(cli.motor, "modelo_em_cache", return_value=True), \
                mock.patch.object(cli.motor, "transcrever", return_value=resultado) as transcrever, \
                redirect_stdout(io.StringIO()):
            pipeline._whisper(Path("a.wav"), opcoes, "pt", cli.DecisorTerminal(), cli.ProgressoTerminal(),
                              em_gravacao=em_gravacao)
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

        def whisper(caminho, opcoes, idioma, decisor, progresso, em_gravacao=False):
            vistos.append(em_gravacao)
            return Resultado(fonte="x", duracao_s=1.0, modelo="m", idioma="pt", segmentos=[Segmento(0.0, 1.0, "oi")])

        opcoes = Opcoes.de_dict(vars(cli._argumentos(["gravacoes/2026-10-10_09-00"])))
        faixas = {"sistema": Path("sistema.wav"), "microfone": Path("microfone.wav")}
        with mock.patch.object(gravacao, "faixas_na_pasta", return_value=faixas), \
                mock.patch.object(pipeline, "_whisper", whisper), redirect_stdout(io.StringIO()):
            _, dados, resultado = pipeline._do_gravacao(opcoes, Path("gravacoes/2026-10-10_09-00"),
                                                         cli.DecisorTerminal(), cli.ProgressoTerminal())
        self.assertEqual(vistos, [True, True])
        self.assertEqual(resultado.faixas, ["sistema", "microfone"])


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
        opcoes = Opcoes.de_dict(vars(cli._argumentos(["entrada.opus", *argv])))
        resultado = Resultado(fonte="x", duracao_s=1.0, modelo="m", idioma="pt")
        with mock.patch.object(cli.motor, "modelo_em_cache", return_value=True), \
                mock.patch.object(cli.motor, "transcrever", return_value=resultado) as transcrever, \
                mock.patch.object(cli.preprocessar, "preparar", return_value=preparo) as preparar, \
                redirect_stdout(io.StringIO()):
            devolvido = pipeline._whisper(Path("a.wav"), opcoes, "pt", cli.DecisorTerminal(), cli.ProgressoTerminal())
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
                self.assertIs(cli.DecisorTerminal().preprocessar(None), esperado, resposta)

    def test_pergunta_cancelada_sem_entrada(self):
        with mock.patch("builtins.input", side_effect=EOFError), self.assertRaises(cli.Erro):
            cli.DecisorTerminal().preprocessar(None)


if __name__ == "__main__":
    unittest.main()
