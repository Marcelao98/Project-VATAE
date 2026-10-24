import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from vatty import gravacao
from vatty.motor import Resultado, Segmento


class Relogio:
    """Relógio falso: `dormir` só avança o tempo, sem esperar."""

    def __init__(self):
        self.agora = 0.0

    def __call__(self):
        return self.agora

    def dormir(self, segundos):
        self.agora += segundos


class EntradaFalsa:
    """
    Gera um tom de 440 Hz proporcional ao tempo que passou desde a última leitura
    (como o dispositivo real), exceto nas janelas de silêncio, onde não entrega nada
    (como o loopback do Windows quando nada toca).
    """

    def __init__(self, relogio, nome="sistema", taxa=48000, canais=2, amplitude=0.5, silencio=()):
        self.relogio, self.nome, self.taxa, self.canais = relogio, nome, taxa, canais
        self.amplitude, self.silencio = amplitude, silencio
        self.ultimo = 0.0
        self.fechada = False

    def pegar(self):
        de, ate = self.ultimo, self.relogio()
        self.ultimo = ate
        if any(a <= de and ate <= b for a, b in self.silencio):
            return b""
        n = int((ate - de) * self.taxa)
        t = (np.arange(n) + de * self.taxa) / self.taxa
        mono = (self.amplitude * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
        return np.repeat(mono, self.canais).tobytes()

    def fechar(self):
        self.fechada = True


def _ler_wav(caminho):
    with wave.open(str(caminho), "rb") as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


class TestConversoes(unittest.TestCase):
    def test_para_mono_tira_a_media_dos_canais(self):
        estereo = np.array([1000, 3000, -2000, 2000], dtype=np.int16).tobytes()
        mono = gravacao.para_mono(estereo, canais=2)
        np.testing.assert_allclose(mono * 32768, [2000, 0], atol=1)

    def test_para_mono_ignora_byte_e_quadro_incompletos(self):
        brutos = np.array([100, 200, 300], dtype=np.int16).tobytes() + b"\x01"
        self.assertEqual(len(gravacao.para_mono(brutos, canais=2)), 1)

    def test_reamostrar_48k_para_16k_divide_por_tres(self):
        sinal = np.ones(4800, dtype=np.float32)
        self.assertEqual(len(gravacao.reamostrar(sinal, 48000)), 1600)

    def test_reamostrar_44100_para_16k_mantem_a_duracao(self):
        sinal = np.zeros(44100, dtype=np.float32)
        self.assertEqual(len(gravacao.reamostrar(sinal, 44100)), 16000)

    def test_reamostrar_mesma_taxa_nao_mexe(self):
        sinal = np.arange(10, dtype=np.float32)
        np.testing.assert_array_equal(gravacao.reamostrar(sinal, 16000), sinal)

    def test_reamostrar_vazio(self):
        self.assertEqual(len(gravacao.reamostrar(np.zeros(0, dtype=np.float32), 44100)), 0)


class TestGravar(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pasta = Path(tmp.name) / "g"
        self.relogio = Relogio()

    def gravar(self, entradas, **opcoes):
        return gravacao.gravar(entradas, self.pasta, relogio=self.relogio, dormir=self.relogio.dormir, **opcoes)

    def test_parar_encerra_e_guarda_o_que_gravou(self):
        g = self.gravar([EntradaFalsa(self.relogio)], parar=lambda: self.relogio.agora >= 1.0)
        self.assertAlmostEqual(g.duracao_s, 1.0)

    def test_guarda_o_horario_real_do_comeco(self):
        g = self.gravar([EntradaFalsa(self.relogio)], duracao_max=1.0, agora=lambda: 1760000000.5)
        self.assertEqual(g.inicio, 1760000000.5)

    def test_para_na_duracao_pedida_e_escreve_wav_16k_mono(self):
        e = EntradaFalsa(self.relogio)
        g = self.gravar([e], duracao_max=3.0)
        canais, largura, taxa, amostras = _ler_wav(g.faixas["sistema"])
        self.assertEqual((canais, largura, taxa), (1, 2, 16000))
        self.assertEqual(len(amostras), 3 * 16000)
        self.assertAlmostEqual(g.duracao_s, 3.0)
        self.assertGreater(g.picos["sistema"], 0.4)
        self.assertTrue(e.fechada)

    def test_silencio_do_dispositivo_vira_silencio_na_linha_do_tempo(self):
        # nada chega entre 1 s e 3 s: o arquivo continua com 4 s e o som volta no lugar certo
        e = EntradaFalsa(self.relogio, silencio=[(1.0, 3.0)])
        g = self.gravar([e], duracao_max=4.0)
        amostras = _ler_wav(g.faixas["sistema"])[3]
        self.assertEqual(len(amostras), 4 * 16000)
        buraco = amostras[int(1.25 * 16000):int(2.75 * 16000)]
        self.assertEqual(int(np.abs(buraco).max()), 0)
        self.assertGreater(np.abs(amostras[: 16000 // 2]).max(), 1000)
        self.assertGreater(np.abs(amostras[int(3.5 * 16000):]).max(), 1000)

    def test_duas_faixas_viram_dois_arquivos(self):
        sistema = EntradaFalsa(self.relogio, "sistema", amplitude=0.5)
        mic = EntradaFalsa(self.relogio, "microfone", taxa=44100, canais=1, amplitude=0.1)
        g = self.gravar([sistema, mic], duracao_max=2.0)
        self.assertEqual(set(g.faixas), {"sistema", "microfone"})
        for caminho in g.faixas.values():
            self.assertEqual(len(_ler_wav(caminho)[3]), 2 * 16000)  # as duas com o mesmo tamanho
        self.assertGreater(g.picos["sistema"], g.picos["microfone"])

    def test_ctrl_c_fecha_os_arquivos_e_guarda_o_que_gravou(self):
        e = EntradaFalsa(self.relogio)

        def dormir(s):
            if self.relogio.agora >= 2.0:
                raise KeyboardInterrupt
            self.relogio.dormir(s)

        g = gravacao.gravar([e], self.pasta, relogio=self.relogio, dormir=dormir)
        self.assertAlmostEqual(g.duracao_s, 2.0, delta=0.01)
        self.assertEqual(len(_ler_wav(g.faixas["sistema"])[3]), int(g.duracao_s * 16000))  # wav fechado e válido
        self.assertTrue(e.fechada)

    def test_faixa_muda_e_avisada(self):
        e = EntradaFalsa(self.relogio, silencio=[(0.0, 10.0)])
        g = self.gravar([e], duracao_max=1.0)
        self.assertEqual(g.faixas_mudas(), ["sistema"])

    def test_faixa_com_som_nao_e_muda(self):
        g = self.gravar([EntradaFalsa(self.relogio)], duracao_max=1.0)
        self.assertEqual(g.faixas_mudas(), [])

    def test_progresso_recebe_tempo_e_nivel_de_cada_faixa(self):
        chamadas = []
        self.gravar([EntradaFalsa(self.relogio)], duracao_max=1.0, progresso=lambda t, n: chamadas.append((t, n)))
        self.assertTrue(chamadas)
        self.assertIn("sistema", chamadas[-1][1])
        self.assertAlmostEqual(chamadas[-1][0], 1.0)


class TestPastas(unittest.TestCase):
    def test_pasta_nova_nao_sobrescreve(self):
        with tempfile.TemporaryDirectory() as tmp:
            primeira = gravacao.pasta_nova(tmp, "2026-10-10_14-30")
            primeira.mkdir()
            self.assertEqual(gravacao.pasta_nova(tmp, "2026-10-10_14-30").name, "2026-10-10_14-30-2")

    def test_faixas_na_pasta(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "microfone.wav").write_bytes(b"")
            self.assertEqual(list(gravacao.faixas_na_pasta(tmp)), ["microfone"])

    def test_metadados_ida_e_volta_e_pasta_sem_eles(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(gravacao.ler_metadados(tmp), {})  # gravação só de áudio
            dados = {"inicios": {"sistema": 100.0, "tela": 98.5}}
            gravacao.salvar_metadados(tmp, dados)
            self.assertEqual(gravacao.ler_metadados(tmp), dados)


class TestJuntarFaixas(unittest.TestCase):
    def test_intercala_por_horario_e_marca_o_falante(self):
        sistema = Resultado(fonte="a", duracao_s=10.0, modelo="m", idioma="pt",
                            segmentos=[Segmento(0.0, 2.0, "Bom dia, pessoal."), Segmento(6.0, 8.0, "Fechado então.")],
                            avisos=["x"])
        mic = Resultado(fonte="b", duracao_s=9.0, modelo="m", idioma="pt",
                        segmentos=[Segmento(3.0, 5.0, "Bom dia!")],
                        refeitos=[{"inicio": 3.0, "fim": 5.0, "motivo": "loop"}])
        r = gravacao.juntar_faixas({"sistema": sistema, "microfone": mic})
        self.assertEqual([(s.texto, s.falante) for s in r.segmentos],
                         [("Bom dia, pessoal.", "outros"), ("Bom dia!", "eu"), ("Fechado então.", "outros")])
        self.assertEqual(r.duracao_s, 10.0)
        self.assertEqual(r.origem, "whisper")
        self.assertEqual(r.refeitos[0]["falante"], "eu")
        self.assertEqual(r.avisos, ["sistema: x"])
        self.assertEqual(r.faixas, ["sistema", "microfone"])

    def test_uma_faixa_so_nao_lista_faixas(self):
        r = gravacao.juntar_faixas({"microfone": Resultado(fonte="a", duracao_s=1.0, modelo="m", idioma="pt",
                                                           segmentos=[Segmento(0.0, 1.0, "oi")])})
        self.assertEqual(r.faixas, [])

    def test_nao_mexe_nos_segmentos_originais(self):
        original = Segmento(0.0, 1.0, "oi")
        gravacao.juntar_faixas({"sistema": Resultado(fonte="a", duracao_s=1.0, modelo="m", idioma="pt", segmentos=[original])})
        self.assertIsNone(original.falante)


class TestPreprocessamentoPorFaixa(unittest.TestCase):
    def _resultado(self, pre=None):
        return Resultado(fonte="a", duracao_s=1.0, modelo="m", idioma="pt",
                         segmentos=[Segmento(0.0, 1.0, "oi")], preprocessamento=pre)

    def test_so_a_faixa_pre_processada_aparece(self):
        info = {"aplicado": True}
        r = gravacao.juntar_faixas({"sistema": self._resultado(), "microfone": self._resultado(info)})
        self.assertEqual(r.preprocessamento, {"microfone": info})

    def test_nenhuma_faixa_pre_processada_fica_sem_o_campo(self):
        r = gravacao.juntar_faixas({"sistema": self._resultado(), "microfone": self._resultado()})
        self.assertIsNone(r.preprocessamento)


if __name__ == "__main__":
    unittest.main()


class TestLinux(unittest.TestCase):
    def test_comando_do_ffmpeg_le_do_pulse_em_16k_mono(self):
        c = gravacao.comando_pulse("ffmpeg", "alsa_output.pci.analog-stereo.monitor")
        self.assertEqual(c[c.index("-f") + 1], "pulse")
        self.assertEqual(c[c.index("-i") + 1], "alsa_output.pci.analog-stereo.monitor")
        self.assertEqual((c[c.index("-ac") + 1], c[c.index("-ar") + 1], c[-2], c[-1]), ("1", "16000", "s16le", "-"))

    def test_fontes_pelo_pactl_ou_os_nomes_especiais(self):
        from types import SimpleNamespace

        def pactl(argv, **kw):
            return SimpleNamespace(returncode=0, stdout={"get-default-sink": "fone\n", "get-default-source": "mic\n"}[argv[1]])
        self.assertEqual(gravacao.fontes_pulse(pactl), {"sistema": "fone.monitor", "microfone": "mic"})

        def sem_pactl(argv, **kw):
            raise FileNotFoundError("pactl")
        self.assertEqual(gravacao.fontes_pulse(sem_pactl), {"sistema": "@DEFAULT_MONITOR@", "microfone": "@DEFAULT_SOURCE@"})

    def test_ffmpeg_que_nao_abre_a_fonte_vira_erro_claro(self):
        import io

        class Fechou:
            stdout, stderr = io.BytesIO(b""), io.BytesIO(b"No such entity")

            def poll(self):
                return 1

        with self.assertRaisesRegex(gravacao.ErroGravacao, "No such entity"):
            gravacao._EntradaFfmpeg("sistema", "x.monitor", "ffmpeg", abrir=lambda c, **kw: Fechou(), dormir=lambda s: None)

    def test_sistema_sem_suporte(self):
        with self.assertRaisesRegex(gravacao.ErroGravacao, "Windows e no Linux"):
            gravacao.abrir_entradas(plataforma="darwin")
