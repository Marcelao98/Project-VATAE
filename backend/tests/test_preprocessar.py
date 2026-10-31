import tempfile
import unittest
from pathlib import Path

import numpy as np

from vatty import audio, preprocessar


def _fala(nivel_voz=0.3, ruido=1e-4, ronco=0.0, segundos=8.0, estouro=False):
    """Fala sintética: harmônicos de 120 Hz com sílabas e pausas, mais chiado e ronco (semente fixa)."""
    t = np.arange(int(audio.TAXA * segundos)) / audio.TAXA
    envelope = np.clip(np.sin(2 * np.pi * 1.5 * t), 0, None) ** 2 * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
    voz = sum(np.sin(2 * np.pi * 120 * k * t) / k for k in range(1, 12)) * envelope * nivel_voz
    chiado = np.random.default_rng(0).normal(0, ruido, t.size)
    x = voz + chiado + ronco * np.sin(2 * np.pi * 40 * t)
    if estouro:
        x = np.clip(x * 100, -1, 1)
    return np.clip(x, -1, 1).astype(np.float32)


class TestAnalisar(unittest.TestCase):
    def test_audio_bom_nao_recomenda(self):
        d = preprocessar.analisar(_fala(nivel_voz=0.3, ruido=1e-4))
        self.assertFalse(d.recomendado, d.para_dict())
        self.assertEqual(d.problemas, [])

    def test_voz_baixa(self):
        d = preprocessar.analisar(_fala(nivel_voz=0.004, ruido=1e-5))
        self.assertTrue(d.voz_baixa)
        self.assertFalse(d.ruidoso)
        self.assertTrue(d.recomendado)

    def test_ruido_de_fundo(self):
        d = preprocessar.analisar(_fala(nivel_voz=0.1, ruido=0.04))
        self.assertTrue(d.ruidoso)
        self.assertLess(d.snr_db, preprocessar.LIMITE_SNR_DB)

    def test_ronco_grave(self):
        d = preprocessar.analisar(_fala(nivel_voz=0.3, ruido=1e-4, ronco=0.3))
        self.assertTrue(d.ronco)
        self.assertGreater(d.ronco_fracao, preprocessar.LIMITE_RONCO_FRACAO)

    def test_estouro_avisa_mas_nao_recomenda_sozinho(self):
        d = preprocessar.analisar(_fala(nivel_voz=0.3, ruido=1e-4, estouro=True))
        self.assertTrue(d.estourado)
        self.assertIn("estourado", " ".join(d.problemas))
        self.assertFalse(d.recomendado)  # o filtro não conserta estouro

    def test_silencio_e_audio_curto_nao_medem(self):
        for amostras in (np.zeros(16000 * 5, dtype=np.float32), np.zeros(100, dtype=np.float32),
                         np.array([], dtype=np.float32)):
            d = preprocessar.analisar(amostras)
            self.assertTrue(d.sem_fala)
            self.assertFalse(d.recomendado)
            self.assertIn("sem sinal", preprocessar.formatar_diagnostico(d))

    def test_para_dict_arredonda_e_traz_os_problemas(self):
        d = preprocessar.analisar(_fala(nivel_voz=0.004, ruido=1e-5))
        dados = d.para_dict()
        self.assertIn("voz baixa", dados["problemas"])
        self.assertEqual(dados["fala_dbfs"], round(dados["fala_dbfs"], 1))

    def test_formatar_diagnostico_cita_os_numeros_e_os_problemas(self):
        texto = preprocessar.formatar_diagnostico(preprocessar.analisar(_fala(nivel_voz=0.004, ruido=1e-5)))
        self.assertIn("dBFS", texto)
        self.assertIn("voz baixa", texto)


class TestCadeia(unittest.TestCase):
    def test_ordem_formato_grave_ruido_volume(self):
        cadeia = preprocessar.cadeia_filtros("sh.rnnn")
        partes = cadeia.split(",")
        self.assertTrue(partes[0].startswith("aformat="))
        self.assertEqual(partes[1], f"highpass=f={preprocessar.CORTE_GRAVE_HZ}")
        self.assertEqual(partes[2], partes[1])  # dois estágios em série
        self.assertEqual(partes[3], "arnndn=m=sh.rnnn")
        self.assertTrue(partes[4].startswith("speechnorm="))

    def test_sem_modelo_cai_no_afftdn(self):
        self.assertEqual(preprocessar.cadeia_filtros(None).split(",")[3], "afftdn")


class TestModelo(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def baixador(self):
        chamadas = []

        def baixar(url, destino):
            chamadas.append(url)
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(preprocessar.ASSINATURA_MODELO + b" 1\n")

        return baixar, chamadas

    def test_baixa_na_primeira_vez_e_reaproveita_depois(self):
        baixar, chamadas = self.baixador()
        avisos = []
        a = preprocessar.localizar_modelo(None, baixar=baixar, cache=self.tmp, dizer=avisos.append)
        b = preprocessar.localizar_modelo(None, baixar=baixar, cache=self.tmp, dizer=avisos.append)
        self.assertEqual(a, b)
        self.assertEqual(a.name, "sh.rnnn")
        self.assertEqual(len(chamadas), 1)  # a segunda veio do cache
        self.assertIn("somnolent-hogwash-2018-09-01/sh.rnnn", chamadas[0])
        self.assertEqual(len(avisos), 1)

    def test_nome_desconhecido(self):
        with self.assertRaises(preprocessar.ModeloIndisponivel) as ctx:
            preprocessar.localizar_modelo("inventado", cache=self.tmp)
        self.assertIn("somnolent-hogwash", str(ctx.exception))

    def test_falha_de_rede_vira_modelo_indisponivel_com_saida(self):
        def baixar(url, destino):
            raise OSError("sem rede")

        with self.assertRaises(preprocessar.ModeloIndisponivel) as ctx:
            preprocessar.localizar_modelo("beguiling-drafter", baixar=baixar, cache=self.tmp, dizer=lambda m: None)
        self.assertIn("--ruido-modelo", str(ctx.exception))

    def test_arquivo_do_usuario(self):
        arq = self.tmp / "meu-modelo.rnnn"
        arq.write_bytes(b"x")
        self.assertEqual(preprocessar.localizar_modelo(str(arq)), arq.resolve())

    def test_arquivo_do_usuario_inexistente_ou_com_nome_perigoso(self):
        with self.assertRaises(preprocessar.ModeloIndisponivel):
            preprocessar.localizar_modelo(str(self.tmp / "nao-existe.rnnn"))
        ruim = self.tmp / "a,b.rnnn"  # a vírgula quebraria o filtro do ffmpeg
        ruim.write_bytes(b"x")
        with self.assertRaises(preprocessar.ModeloIndisponivel) as ctx:
            preprocessar.localizar_modelo(str(ruim))
        self.assertIn("renomeie", str(ctx.exception))

    def test_download_real_recusa_pagina_de_erro(self):
        class Resposta:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"<html>404: Not Found</html>"

        original = preprocessar.urllib.request.urlopen
        preprocessar.urllib.request.urlopen = lambda url, timeout: Resposta()
        try:
            with self.assertRaises(preprocessar.ModeloIndisponivel):
                preprocessar._baixar("https://exemplo/x.rnnn", self.tmp / "x.rnnn")
        finally:
            preprocessar.urllib.request.urlopen = original
        self.assertFalse((self.tmp / "x.rnnn").exists())


class TestPreparar(unittest.TestCase):
    """`preparar` com o carregamento do áudio, o download e a pergunta trocados por dublês."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = Path(tmp.name)
        self.mensagens = []
        self.chamadas = []

    def carregar_com(self, amostras):
        def carregar(caminho, **kwargs):
            self.chamadas.append(kwargs)
            return (amostras if not kwargs else amostras * 0.5), len(amostras) / audio.TAXA
        return carregar

    def baixar(self, url, destino):
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(preprocessar.ASSINATURA_MODELO)

    def preparar(self, amostras, modo, **extra):
        return preprocessar.preparar(
            "a.opus", modo, carregar=self.carregar_com(amostras), baixar=self.baixar, cache=self.cache,
            dizer=self.mensagens.append, **extra)

    def test_nao_nao_mede_nem_mexe(self):
        preparo = self.preparar(_fala(), "nao")
        self.assertIsNone(preparo.carregar_audio)
        self.assertIsNone(preparo.info)
        self.assertEqual(self.chamadas, [])

    def test_audio_bom_em_perguntar_nao_pergunta_e_reaproveita_o_array(self):
        perguntou = []
        bom = _fala()
        preparo = self.preparar(bom, "perguntar", perguntar=lambda d: perguntou.append(d) or True, interativo=True)
        self.assertEqual(perguntou, [])
        self.assertIsNone(preparo.info)
        array, _ = preparo.carregar_audio("a.opus")
        np.testing.assert_array_equal(array, bom)
        self.assertEqual(len(self.chamadas), 1)  # decodificou uma vez só
        self.assertTrue(any("Parece bom" in m for m in self.mensagens))

    def test_audio_ruim_pergunta_e_aplica_quando_aceita(self):
        baixo = _fala(nivel_voz=0.004, ruido=1e-5)
        preparo = self.preparar(baixo, "perguntar", perguntar=lambda d: True, interativo=True)
        self.assertTrue(preparo.info["aplicado"])
        self.assertEqual(preparo.info["ruido"], "arnndn:sh.rnnn")
        self.assertIn("highpass", preparo.info["filtro"])
        self.assertIn("voz baixa", preparo.info["diagnostico"]["problemas"])
        # a segunda decodificação levou o filtro e a pasta do modelo
        self.assertEqual(self.chamadas[1]["pasta_trabalho"], self.cache)
        self.assertEqual(self.chamadas[1]["filtro"], preparo.info["filtro"])
        array, _ = preparo.carregar_audio("a.opus")
        np.testing.assert_allclose(array, baixo * 0.5)  # o array já filtrado (dublê)

    def test_audio_ruim_recusado_segue_sem_filtro(self):
        preparo = self.preparar(_fala(nivel_voz=0.004, ruido=1e-5), "perguntar",
                                perguntar=lambda d: False, interativo=True)
        self.assertIsNone(preparo.info)
        self.assertEqual(len(self.chamadas), 1)

    def test_sem_terminal_avisa_e_nao_aplica(self):
        preparo = self.preparar(_fala(nivel_voz=0.004, ruido=1e-5), "perguntar", interativo=False)
        self.assertIsNone(preparo.info)
        self.assertTrue(any("--preprocessar sim" in m for m in self.mensagens))

    def test_sim_aplica_mesmo_com_audio_bom_sem_perguntar(self):
        preparo = self.preparar(_fala(), "sim")
        self.assertTrue(preparo.info["aplicado"])

    def test_sem_modelo_cai_no_afftdn_com_aviso(self):
        def sem_rede(url, destino):
            raise OSError("sem rede")

        preparo = preprocessar.preparar("a.opus", "sim", carregar=self.carregar_com(_fala()), baixar=sem_rede,
                                        cache=self.cache, dizer=self.mensagens.append)
        self.assertEqual(preparo.info["ruido"], "afftdn")
        self.assertIn("afftdn", preparo.info["filtro"])
        self.assertNotIn("arnndn", preparo.info["filtro"])
        self.assertIsNone(self.chamadas[1]["pasta_trabalho"])
        self.assertTrue(any(m.startswith("Aviso:") for m in self.mensagens))


if __name__ == "__main__":
    unittest.main()
