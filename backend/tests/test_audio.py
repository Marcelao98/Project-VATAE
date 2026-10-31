import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from vatty import audio


class TestAudio(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.arquivo = Path(pasta.name) / "zap.opus"
        self.arquivo.write_bytes(b"nao importa, o ffmpeg e dublado")

    def test_decodifica_com_ffmpeg_dublado(self):
        amostras = np.linspace(-1, 1, 32000, dtype=np.float32)  # 2 s a 16 kHz
        chamadas = []

        def executar(cmd, capture_output):
            chamadas.append(cmd)
            return SimpleNamespace(returncode=0, stdout=amostras.tobytes(), stderr=b"")

        array, duracao = audio.carregar(self.arquivo, executar=executar, achar=lambda nome: "/bin/ffmpeg")

        np.testing.assert_array_equal(array, amostras)
        self.assertEqual(array.dtype, np.float32)
        self.assertEqual(duracao, 2.0)
        cmd = chamadas[0]
        self.assertEqual(cmd[0], "/bin/ffmpeg")
        self.assertIn(str(self.arquivo), cmd)
        for par in (["-f", "f32le"], ["-ac", "1"], ["-ar", "16000"]):
            i = cmd.index(par[0])
            self.assertEqual(cmd[i : i + 2], par)
        self.assertEqual(cmd[-1], "-")  # saída padrão

    def test_erro_claro_sem_ffmpeg(self):
        with self.assertRaises(audio.FfmpegAusente) as ctx:
            audio.carregar(self.arquivo, achar=lambda nome: None)
        self.assertIn("winget install", str(ctx.exception))

    def test_erro_quando_ffmpeg_falha(self):
        def executar(cmd, capture_output):
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"Invalid data found")

        with self.assertRaises(audio.ErroDeDecodificacao) as ctx:
            audio.carregar(self.arquivo, executar=executar, achar=lambda nome: "ffmpeg")
        self.assertIn("Invalid data found", str(ctx.exception))

    def test_arquivo_inexistente(self):
        with self.assertRaises(FileNotFoundError):
            audio.carregar(self.arquivo.with_name("nao-existe.opus"), achar=lambda nome: "ffmpeg")

    def test_sem_filtro_o_comando_e_o_de_sempre(self):
        cmd = audio.comando_ffmpeg("ffmpeg", Path("a.opus"))
        self.assertNotIn("-af", cmd)
        self.assertEqual(cmd[-1], "-")

    def test_filtro_entra_antes_do_formato_de_saida(self):
        cmd = audio.comando_ffmpeg("ffmpeg", Path("a.opus"), filtro="highpass=f=80")
        i = cmd.index("-af")
        self.assertEqual(cmd[i + 1], "highpass=f=80")
        self.assertLess(i, cmd.index("-f"))  # o filtro vem antes da conversão final para PCM
        self.assertEqual(cmd[-1], "-")

    def test_pasta_de_trabalho_vira_cwd_e_o_arquivo_vira_caminho_absoluto(self):
        chamadas = []

        def executar(cmd, capture_output, cwd=None):
            chamadas.append((cmd, cwd))
            return SimpleNamespace(returncode=0, stdout=np.zeros(160, dtype=np.float32).tobytes(), stderr=b"")

        audio.carregar(self.arquivo, executar=executar, achar=lambda nome: "ffmpeg",
                       filtro="arnndn=m=sh.rnnn", pasta_trabalho=self.arquivo.parent)
        cmd, cwd = chamadas[0]
        self.assertEqual(cwd, str(self.arquivo.parent))
        self.assertIn(str(self.arquivo.resolve()), cmd)
        self.assertIn("arnndn=m=sh.rnnn", cmd)

    def test_sem_pasta_de_trabalho_nao_manda_cwd(self):
        # o dublê antigo não aceita `cwd`: sem pasta de trabalho, ele não pode ser passado
        def executar(cmd, capture_output):
            return SimpleNamespace(returncode=0, stdout=np.zeros(160, dtype=np.float32).tobytes(), stderr=b"")

        audio.carregar(self.arquivo, executar=executar, achar=lambda nome: "ffmpeg", filtro="anull")


if __name__ == "__main__":
    unittest.main()
