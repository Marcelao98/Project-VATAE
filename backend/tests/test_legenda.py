import unittest

from vatty import legenda
from vatty.motor import Segmento

# Imita a legenda automática do YouTube: linha "rolando", trechos de 10 ms
# repetidos, tempos dentro da linha e marcas como [Música].
VTT_AUTOMATICA = """WEBVTT
Kind: captions
Language: pt

00:00:00.179 --> 00:00:04.960 align:start position:0%

[Música]

00:00:04.960 --> 00:00:04.970 align:start position:0%
[Música]


00:00:04.970 --> 00:00:07.900 align:start position:0%
[Música]
olá<00:00:05.630><c> tudo</c><00:00:06.110><c> bem</c>

00:00:07.900 --> 00:00:07.910 align:start position:0%
olá tudo bem


00:00:07.910 --> 00:00:10.000 align:start position:0%
olá tudo bem
hoje<00:00:08.300><c> vamos</c><00:00:09.000><c> falar</c> de &amp; derivadas
"""

VTT_MANUAL = """WEBVTT

1
00:00:01.000 --> 00:00:03.500
Olá, tudo bem?
Hoje: derivadas.

2
00:01:02.000 --> 01:00:04.250
<i>Fim.</i>
"""


class TestEscolher(unittest.TestCase):
    def test_manual_antes_da_automatica(self):
        e = legenda.escolher({"pt-BR": [], "en": []}, {"pt-orig": []}, "pt")
        self.assertEqual(e, legenda.Escolha("pt-BR", automatica=False))

    def test_automatica_so_a_original(self):
        e = legenda.escolher({}, {"pt": [], "pt-orig": [], "en": []}, "pt")
        self.assertEqual(e, legenda.Escolha("pt-orig", automatica=True))

    def test_automatica_traduzida_nao_vale(self):
        # vídeo em inglês: o "pt" automático é tradução, não serve
        self.assertIsNone(legenda.escolher({}, {"pt": [], "en-orig": []}, "pt"))

    def test_lang_com_regiao_casa_com_base(self):
        e = legenda.escolher({}, {"pt-orig": []}, "pt-BR")
        self.assertEqual(e.chave, "pt-orig")

    def test_sem_legenda(self):
        self.assertIsNone(legenda.escolher({}, {}, "pt"))


class TestLerVtt(unittest.TestCase):
    def test_automatica_sem_repeticao_e_sem_tags(self):
        segs = legenda.ler_vtt(VTT_AUTOMATICA)
        self.assertEqual([s.texto for s in segs], ["[Música]", "olá tudo bem", "hoje vamos falar de & derivadas"])
        self.assertEqual((segs[1].inicio, segs[1].fim), (4.97, 7.9))

    def test_manual_junta_linhas_do_mesmo_trecho(self):
        segs = legenda.ler_vtt(VTT_MANUAL)
        self.assertEqual(segs[0], Segmento(1.0, 3.5, "Olá, tudo bem? Hoje: derivadas."))
        self.assertEqual(segs[1], Segmento(62.0, 3604.25, "Fim."))

    def test_aceita_crlf(self):
        self.assertEqual(len(legenda.ler_vtt(VTT_MANUAL.replace("\n", "\r\n"))), 2)


class TestIndicadores(unittest.TestCase):
    def test_automatica_vs_manual(self):
        auto = legenda.indicadores(legenda.ler_vtt(VTT_AUTOMATICA), 10.0)
        self.assertEqual(auto["marcas"], 1)
        self.assertEqual(auto["pontuacao_por_100"], 0.0)
        self.assertEqual(auto["maiusculas_pct"], 0)
        self.assertEqual(auto["palavras"], 9)

        manual = legenda.indicadores([Segmento(0, 2, "Olá, tudo bem? Hoje: derivadas.")], 4.0)
        self.assertGreater(manual["pontuacao_por_100"], 50)
        self.assertEqual(manual["maiusculas_pct"], 40)
        self.assertEqual(manual["cobertura_pct"], 50)

    def test_cobertura_nao_conta_sobreposicao_duas_vezes(self):
        segs = [Segmento(0, 6, "a"), Segmento(4, 8, "b")]
        self.assertEqual(legenda.indicadores(segs, 10.0)["cobertura_pct"], 80)


class TestAmostras(unittest.TestCase):
    def test_comeco_meio_fim(self):
        segs = [Segmento(t, t + 4, f"fala {t}") for t in range(0, 600, 5)]
        trechos = legenda.amostras(segs, quantas=3, janela=10)
        self.assertEqual([t for t, _ in trechos], [0, 295, 585])
        self.assertEqual(trechos[0][1], "fala 0 fala 5")

    def test_video_curto_vira_um_trecho(self):
        segs = [Segmento(0, 2, "a"), Segmento(3, 5, "b")]
        self.assertEqual(legenda.amostras(segs), [(0, "a b")])

    def test_ignora_marcas(self):
        segs = [Segmento(0, 2, "[Música]"), Segmento(40, 42, "oi")]
        self.assertEqual(legenda.amostras(segs), [(40, "oi")])


class TestParaResultado(unittest.TestCase):
    def test_tira_marcas_e_marca_origem(self):
        segs = legenda.ler_vtt(VTT_AUTOMATICA)
        r = legenda.para_resultado(segs, "https://youtu.be/x", 10.0, "pt", legenda.Escolha("pt-orig", True))
        self.assertEqual(r.origem, "legenda-automatica")
        self.assertIsNone(r.modelo)
        self.assertEqual([s.texto for s in r.segmentos], ["olá tudo bem", "hoje vamos falar de & derivadas"])

        r = legenda.para_resultado(segs, "u", 10.0, "pt", legenda.Escolha("pt-BR", False))
        self.assertEqual(r.origem, "legenda-manual")


if __name__ == "__main__":
    unittest.main()
