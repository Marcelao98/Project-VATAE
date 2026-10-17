import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from vatty import quadros
from vatty.audio import FfmpegAusente


def achar(nome):
    return f"/usr/bin/{nome}"


class ProcessoFalso:
    """Faz de conta de um ffmpeg que entrega `dados` no stdout (em pedaços pequenos, como o pipe real)."""

    def __init__(self, dados: bytes, codigo=0, erro=b"", pedaco=7):
        self.stdout = _Pedacos(dados, pedaco)
        self.stderr = io.BytesIO(erro)
        self.returncode = codigo

    def wait(self):
        return self.returncode


class _Pedacos(io.BytesIO):
    def __init__(self, dados, pedaco):
        super().__init__(dados)
        self._pedaco = pedaco

    def read(self, n=-1):
        return super().read(min(n, self._pedaco) if n and n > 0 else n)


def quadro_bytes(valor, w, h):
    return np.full((h, w), valor, dtype=np.uint8).tobytes()


class TestTamanho(unittest.TestCase):
    def test_720p(self):
        self.assertEqual(quadros.tamanho_da_amostra(1280, 720), (320, 180))

    def test_altura_sempre_par(self):
        for largura, altura in ((1920, 1080), (1280, 534), (854, 480), (720, 1280)):
            self.assertEqual(quadros.tamanho_da_amostra(largura, altura)[1] % 2, 0)

    def test_vertical(self):
        self.assertEqual(quadros.tamanho_da_amostra(720, 1280), (320, 568))  # 568,9 -> par mais perto


class TestInformacoes(unittest.TestCase):
    def arquivo(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        caminho = Path(tmp.name) / "v.mp4"
        caminho.write_bytes(b"x")
        return caminho

    def test_le_tamanho_e_duracao(self):
        saida = json.dumps({"streams": [{"width": 1280, "height": 720}], "format": {"duration": "61.5"}}).encode()
        info = quadros.informacoes(self.arquivo(), lambda c, **o: SimpleNamespace(returncode=0, stdout=saida, stderr=b""), achar)
        self.assertEqual(info, {"largura": 1280, "altura": 720, "duracao_s": 61.5})

    def test_sem_imagem(self):
        saida = json.dumps({"streams": [], "format": {"duration": "10"}}).encode()
        with self.assertRaises(quadros.ErroDeVideo):
            quadros.informacoes(self.arquivo(), lambda c, **o: SimpleNamespace(returncode=0, stdout=saida, stderr=b""), achar)

    def test_ffprobe_falha(self):
        with self.assertRaises(quadros.ErroDeVideo):
            quadros.informacoes(self.arquivo(), lambda c, **o: SimpleNamespace(returncode=1, stdout=b"", stderr=b"invalid"), achar)

    def test_arquivo_inexistente(self):
        with self.assertRaises(FileNotFoundError):
            quadros.informacoes("/nao/existe.mp4", None, achar)

    def test_sem_ffprobe(self):
        with self.assertRaises(FfmpegAusente):
            quadros.informacoes(self.arquivo(), None, lambda nome: None)


class TestAmostrar(unittest.TestCase):
    def rodar(self, processo, **kw):
        chamadas = []

        def abrir(comando, **opcoes):
            chamadas.append(comando)
            return processo

        lista = list(quadros.amostrar("v.mp4", 1280, 720, kw.pop("intervalo", 1.0), abrir, achar))
        return lista, chamadas[0]

    def test_devolve_um_array_por_quadro_na_ordem(self):
        dados = quadro_bytes(10, 320, 180) + quadro_bytes(200, 320, 180) + quadro_bytes(50, 320, 180)
        lista, _ = self.rodar(ProcessoFalso(dados))
        self.assertEqual([int(q[0, 0]) for q in lista], [10, 200, 50])
        self.assertEqual(lista[0].shape, (180, 320))

    def test_quadro_cortado_no_fim_e_descartado(self):
        dados = quadro_bytes(10, 320, 180) + quadro_bytes(200, 320, 180)[:1000]
        lista, _ = self.rodar(ProcessoFalso(dados))
        self.assertEqual(len(lista), 1)

    def test_comando_pede_cinza_pequeno_e_o_intervalo(self):
        _, comando = self.rodar(ProcessoFalso(b""), intervalo=2.0)
        filtro = comando[comando.index("-vf") + 1]
        self.assertEqual(filtro, "fps=1/2,scale=320:180,format=gray")

    def test_ffmpeg_que_falha_sem_nenhum_quadro_vira_erro(self):
        with self.assertRaises(quadros.ErroDeVideo) as e:
            self.rodar(ProcessoFalso(b"", codigo=1, erro=b"Invalid data"))
        self.assertIn("Invalid data", str(e.exception))

    def test_video_curto_demais_sem_erro_do_ffmpeg_so_nao_gera_nada(self):
        lista, _ = self.rodar(ProcessoFalso(b""))
        self.assertEqual(lista, [])


class TestExtrairQuadro(unittest.TestCase):
    def test_pede_o_horario_e_devolve_o_arquivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "frames" / "0001.jpg"
            chamadas = []

            def executar(comando, **opcoes):
                chamadas.append(comando)
                destino.write_bytes(b"jpg")
                return SimpleNamespace(returncode=0, stderr=b"")

            r = quadros.extrair_quadro("v.mp4", 12.5, destino, executar, achar)
            self.assertEqual(r, destino)
            self.assertEqual(chamadas[0][chamadas[0].index("-ss") + 1], "12.500")
            self.assertNotIn("-vf", chamadas[0])
            quadros.extrair_quadro("v.mp4", 1, destino, executar, achar, recorte=(0.5, 0.75, 1.0, 1.0))
            self.assertEqual(chamadas[1][chamadas[1].index("-vf") + 1],
                             "crop=iw*0.5000:ih*0.2500:iw*0.5000:ih*0.7500")  # só o pedaço que mudou

    def test_ffmpeg_sem_imagem_vira_erro(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(quadros.ErroDeVideo):
                quadros.extrair_quadro("v.mp4", 999, Path(tmp) / "a.jpg",
                                       lambda c, **o: SimpleNamespace(returncode=0, stderr=b""), achar)


if __name__ == "__main__":
    unittest.main()
