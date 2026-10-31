import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from vatty import cli, gravacao, juntar


class TestAtrasos(unittest.TestCase):
    def test_audio_depois_da_tela_atrasa(self):
        a = juntar.atrasos({"tela": 100.0, "sistema": 102.3, "microfone": 102.3}, ["sistema", "microfone", "tela"])
        self.assertEqual(a, {"sistema": 2.3, "microfone": 2.3, "tela": 0.0})

    def test_sem_inicios_nada_desloca(self):
        self.assertEqual(juntar.atrasos({}, ["sistema"]), {"sistema": 0.0})


class TestComando(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pasta = Path(tmp.name)
        for nome in ("sistema", "microfone"):
            (self.pasta / f"{nome}.wav").write_bytes(b"")

    def faixas(self):
        return gravacao.faixas_na_pasta(self.pasta)

    def test_tela_e_duas_faixas_mistura_sem_baixar_o_volume_e_copia_a_imagem(self):
        (self.pasta / "tela.mp4").write_bytes(b"")
        meta = {"inicios": {"tela": 10.0, "sistema": 12.5, "microfone": 9.0}}
        argv, saida = juntar.comando("ffmpeg", self.pasta, self.faixas(), meta)
        filtro = argv[argv.index("-filter_complex") + 1]
        self.assertIn("[1:a]adelay=2500:all=1[a0]", filtro)
        self.assertIn("[2:a]atrim=start=1.0", filtro)        # o microfone começou antes da tela
        self.assertIn("amix=inputs=2:duration=longest:normalize=0", filtro)
        self.assertEqual(argv[argv.index("-c:v") + 1], "copy")
        self.assertEqual(saida, self.pasta / juntar.VIDEO)

    def test_sem_tela_e_uma_faixa_sai_audio_sem_mistura(self):
        (self.pasta / "microfone.wav").unlink()
        argv, saida = juntar.comando("ffmpeg", self.pasta, self.faixas(), {})
        self.assertEqual(argv[argv.index("-filter_complex") + 1], "[0:a]anull[som]")
        self.assertNotIn("-c:v", argv)
        self.assertEqual(saida, self.pasta / juntar.SO_AUDIO)

    def test_sem_faixa_da_erro(self):
        with self.assertRaisesRegex(juntar.ErroJuntar, "Não achei faixa"):
            juntar.comando("ffmpeg", self.pasta, {}, {})

    def test_falha_do_ffmpeg_vira_erro_legivel(self):
        rodar = lambda argv, **kw: SimpleNamespace(returncode=1, stderr="Invalid data found")
        with self.assertRaisesRegex(juntar.ErroJuntar, "Invalid data"):
            juntar.juntar(self.pasta, achar=lambda n: "ffmpeg", executar=rodar)


class TestCli(unittest.TestCase):
    def test_cli_juntar_mostra_o_arquivo(self):
        with mock.patch("vatty.juntar.juntar", return_value=Path("g/video.mp4")) as m, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(["juntar", "g"]), 0)
        m.assert_called_once_with(Path("g"))
        self.assertIn("Pronto para enviar: g/video.mp4", out.getvalue())

    def test_cli_juntar_erro(self):
        with mock.patch("vatty.juntar.juntar", side_effect=juntar.ErroJuntar("Não achei a pasta g.")), \
                redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cli.main(["juntar", "g"]), 1)
        self.assertIn("Não achei a pasta", err.getvalue())


if __name__ == "__main__":
    unittest.main()
