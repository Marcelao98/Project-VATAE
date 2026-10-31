import io
import unittest

from vatty import tela


class FfmpegFalso:
    """Popen falso: `progresso` são as linhas do -progress; `vivo` diz se ele continua rodando."""

    def __init__(self, progresso=(), vivo=True, erro=b""):
        self.stdout = io.BytesIO(b"".join(linha + b"\n" for linha in progresso))
        self.stderr = io.BytesIO(erro)
        self.stdin = self
        self.escrito = b""
        self.vivo = vivo
        self.comando = None
        self.pediu_q = False

    def __call__(self, comando, **opcoes):
        self.comando = comando
        return self

    def write(self, dados):
        self.escrito += dados

    def flush(self):
        pass

    def close(self):
        pass

    def poll(self):
        return None if self.vivo else 1

    def wait(self, timeout=None):
        self.pediu_q = self.escrito == b"q"
        self.vivo = False

    def kill(self):
        self.vivo = False


class _Saida:
    def __init__(self, stdout):
        self.stdout = stdout


def _filtros(tem_ddagrab):
    return lambda comando, **kw: _Saida(b" ... ddagrab  V->V  Grab Windows Desktop" if tem_ddagrab else b" ... gdigrab")


def _abrir(ffmpeg, **kw):
    opcoes = {"abrir": ffmpeg, "achar": lambda nome: "ffmpeg", "agora": lambda: 1000.0, "executar": _filtros(False),
              "plataforma": "win32", "espera_inicio": 0, **kw}
    return tela.CapturaTela("g/tela.mp4", **opcoes)


class TestComando(unittest.TestCase):
    def test_tela_inteira_pelo_ddagrab_30_por_segundo_so_quando_muda(self):
        c = tela.comando("ffmpeg", "g/tela.mp4")
        self.assertEqual(c[c.index("-f") + 1], "lavfi")
        self.assertIn("ddagrab=output_idx=0:framerate=30:dup_frames=0", c[c.index("-i") + 1])
        self.assertEqual(c[c.index("-fps_mode") + 1], "vfr")  # quadro repetido não é gravado
        self.assertIn("-an", c)
        self.assertEqual(c[-1], "g/tela.mp4")

    def test_janela_pelo_gdigrab_sem_quadros_repetidos(self):
        c = tela.comando("ffmpeg", "g/tela.mp4", motor="gdigrab", janela="Aula - Zoom")
        self.assertEqual(c[c.index("-i") + 1], "title=Aula - Zoom")
        self.assertEqual(c[c.index("-framerate") + 1], "10")
        self.assertTrue(c[c.index("-vf") + 1].startswith("mpdecimate=max=20,"))

    def test_ler_progresso(self):
        self.assertEqual(tela.ler_progresso("out_time_us=1500000\n"), ("out_time_us", 1500000))
        self.assertEqual(tela.ler_progresso("out_time_us=N/A"), ("out_time_us", None))


class TestSincronia(unittest.TestCase):
    def test_deslocamento_e_o_inicio_da_tela_menos_o_do_audio(self):
        inicios = {"sistema": 100.0, "microfone": 100.0, "tela": 98.5}
        self.assertEqual(tela.deslocamento(inicios), -1.5)
        self.assertEqual(tela.deslocamento({"sistema": 100.0}), 0.0)  # sem tela
        self.assertEqual(tela.deslocamento(None), 0.0)

    def test_sincronizar_desloca_corta_no_zero_e_tira_o_que_acabou_antes(self):
        dados = {"perfil": "aula", "eventos": [
            {"tipo": "slide", "inicio": 0.0, "fim": 1.0, "texto": "antes", "frame": "frames/0001.jpg"},
            {"tipo": "slide", "inicio": 1.0, "fim": 10.0, "texto": "capa", "frame": "frames/0002.jpg"},
            {"tipo": "slide", "inicio": 10.0, "fim": 20.0, "texto": "agenda", "frame": "frames/0003.jpg"},
        ]}
        saida = tela.sincronizar(dados, -1.5)
        self.assertEqual([(e["texto"], e["inicio"], e["fim"]) for e in saida["eventos"]],
                         [("capa", 0.0, 8.5), ("agenda", 8.5, 18.5)])
        self.assertEqual(saida["sincronia"], {"deslocamento_s": -1.5})
        self.assertEqual(saida["perfil"], "aula")
        self.assertEqual(tela.sincronizar(dados, 2.0)["eventos"][0]["inicio"], 2.0)
        self.assertEqual(tela.sincronizar(dados, -1.5, duracao=30.0)["eventos"][-1]["fim"], 30.0)  # tela parada no fim


class TestCaptura(unittest.TestCase):
    def test_so_no_windows_e_com_ffmpeg(self):
        with self.assertRaisesRegex(tela.ErroTela, "Windows"):
            _abrir(FfmpegFalso(), plataforma="linux")
        with self.assertRaisesRegex(tela.ErroTela, "ffmpeg"):
            _abrir(FfmpegFalso(), achar=lambda nome: None)

    def test_inicio_vem_do_progresso_e_parar_pede_q(self):
        ffmpeg = FfmpegFalso([b"frame=0", b"out_time_us=0", b"frame=1", b"out_time_us=N/A",
                              b"out_time_us=500000", b"out_time_us=1000000"])
        captura = _abrir(ffmpeg, espera_inicio=5)
        self.assertEqual(captura.inicio, 999.5)  # relatório às 1000.0 com 0,5 s de vídeo escrito
        self.assertFalse(captura.inicio_aproximado)
        self.assertTrue(captura.parar())
        self.assertTrue(ffmpeg.pediu_q)

    def test_ffmpeg_que_fecha_logo_vira_erro_com_a_mensagem_dele(self):
        ffmpeg = FfmpegFalso(vivo=False, erro=b"Can't find window 'Aula', aborting.")
        with self.assertRaisesRegex(tela.ErroTela, "Can't find window.*está aberta"):
            _abrir(ffmpeg, janela="Aula")

    def test_sem_progresso_fica_o_horario_em_que_abriu(self):
        captura = _abrir(FfmpegFalso())
        self.assertEqual(captura.inicio, 1000.0)
        self.assertTrue(captura.inicio_aproximado)

    def test_parar_diz_se_o_ffmpeg_ja_tinha_parado_sozinho(self):
        ffmpeg = FfmpegFalso([b"frame=1", b"out_time_us=500000"])
        captura = _abrir(ffmpeg, espera_inicio=5)
        ffmpeg.vivo = False  # a janela foi fechada no meio
        self.assertFalse(captura.parar())

    def test_usa_o_ddagrab_e_cai_para_o_gdigrab_se_ele_falhar(self):
        com_ddagrab = FfmpegFalso([b"frame=1", b"out_time_us=0"])
        captura = _abrir(com_ddagrab, executar=_filtros(True), espera_inicio=5)
        self.assertEqual((captura.motor, captura.fps, captura.aviso), ("ddagrab", 30, None))
        self.assertEqual(captura.inicio, 1000.0)  # primeiro quadro com 0 s escritos

        tentativas = [FfmpegFalso(vivo=False, erro=b"Failed to create output duplication"),
                      FfmpegFalso([b"frame=1", b"out_time_us=0"])]
        captura = _abrir(lambda comando, **kw: tentativas.pop(0)(comando), executar=_filtros(True), espera_inicio=5)
        self.assertEqual(captura.motor, "gdigrab")
        self.assertIn("duplication", captura.aviso)

    def test_ffmpeg_sem_ddagrab_avisa_e_usa_o_gdigrab(self):
        captura = _abrir(FfmpegFalso([b"frame=1", b"out_time_us=0"]), espera_inicio=5)
        self.assertEqual((captura.motor, captura.fps), ("gdigrab", 10))
        self.assertIn("6.1", captura.aviso)



class TestLinux(unittest.TestCase):
    def test_x11_grava_pelo_x11grab_e_recusa_janela(self):
        c = tela.comando("ffmpeg", "g/tela.mp4", motor="x11grab", exibicao=":1")
        self.assertEqual((c[c.index("-f") + 1], c[c.index("-i") + 1]), ("x11grab", ":1"))
        captura = _abrir(FfmpegFalso([b"frame=1", b"out_time_us=0"]), plataforma="linux", sessao="x11", espera_inicio=5)
        self.assertEqual(captura.motor, "x11grab")
        with self.assertRaisesRegex(tela.ErroTela, "janela só"):
            _abrir(FfmpegFalso(), plataforma="linux", sessao="x11", janela="Aula")

    def test_wayland_vai_pelo_portal(self):
        from unittest import mock
        from vatty import tela_portal
        with mock.patch.object(tela_portal, "CapturaPortal", side_effect=tela_portal.ErroPortal("cancelado")):
            with self.assertRaisesRegex(tela.ErroTela, "cancelado"):
                tela.abrir("g/tela.mp4", plataforma="linux", sessao="wayland")

    def test_portal_caminho_codificador_e_comando(self):
        from vatty import tela_portal
        self.assertEqual(tela_portal.caminho_pedido(":1.42", "vattyab"),
                         "/org/freedesktop/portal/desktop/request/1_42/vattyab")
        self.assertEqual(tela_portal.escolher_codificador(lambda n: n == "openh264enc"), "openh264enc")
        self.assertIsNone(tela_portal.escolher_codificador(lambda n: False))
        from unittest import mock
        # noopenh264: o elemento existe, mas codificar falha -> não serve
        falha = lambda cmd, **k: type("R", (), {"returncode": 1})()
        with mock.patch("shutil.which", return_value="gst-launch-1.0"):
            self.assertFalse(tela_portal._codificador_funciona("openh264enc", executar=falha))
        c = tela_portal.comando_gst("gst-launch-1.0", 7, 55, "g/tela.mp4", "x264enc")
        self.assertIn("-e", c)  # fim de fluxo no Ctrl+C: o mp4 fecha direito
        self.assertIn("fd=7", c)
        self.assertIn("path=55", c)
        self.assertEqual(c[-1], "location=g/tela.mp4")


if __name__ == "__main__":
    unittest.main()
