import unittest

import numpy as np

from vatty import visual
from vatty.visual import Slide, detectar_trocas, indicadores, juntar_parecidos, sugerir_perfil


def tela(valor, altura=180, largura=320):
    return np.full((altura, largura), valor, dtype=np.uint8)


def com_bolinha(base, fracao=0.01):
    """A mesma tela com um quadradinho diferente (a câmera do professor)."""
    q = base.copy()
    n = max(1, int(q.size * fracao))
    q.reshape(-1)[:n] = 255 - int(base.flat[0])
    return q


class TestDetectarTrocas(unittest.TestCase):
    def test_tela_parada_e_um_slide_so(self):
        slides, truncado = detectar_trocas([tela(10)] * 10)
        self.assertEqual(len(slides), 1)
        self.assertFalse(truncado)
        self.assertEqual((slides[0].inicio, slides[0].fim), (0.0, 10.0))

    def test_troca_clara_gera_dois_slides_com_o_horario_certo(self):
        quadros = [tela(10)] * 5 + [tela(200)] * 5
        slides, _ = detectar_trocas(quadros)
        self.assertEqual(len(slides), 2)
        self.assertEqual((slides[0].inicio, slides[0].fim), (0.0, 5.0))
        self.assertEqual(slides[1].inicio, 5.0)
        self.assertEqual(slides[1].fim, 10.0)
        self.assertGreaterEqual(slides[1].quadro_s, 5.0)   # quadro estável, depois da troca
        self.assertLessEqual(slides[1].quadro_s, 9.0)

    def test_animacao_conta_como_uma_troca_so_e_espera_estabilizar(self):
        # 5 s no slide A, 3 quadros de "animação" diferentes entre si, depois o slide B parado
        quadros = [tela(10)] * 5 + [tela(60), tela(110), tela(160)] + [tela(220)] * 5
        slides, _ = detectar_trocas(quadros)
        self.assertEqual(len(slides), 2)
        self.assertEqual(slides[1].inicio, 5.0)             # começou a mudar aqui
        self.assertGreaterEqual(slides[1].quadro_s, 9.0)    # mas o quadro bom é o parado, depois de 3 animados

    def test_camera_em_movimento_constante_nao_conta(self):
        # a "câmera" (3% da tela) muda a cada quadro durante 60 s; a tela de fundo não muda
        base = tela(10)
        quadros = [com_bolinha(base, 0.03) if i % 2 else base for i in range(60)]
        slides, _ = detectar_trocas(quadros)
        self.assertEqual(len(slides), 1)

    def test_troca_de_slide_com_a_camera_mexendo_ainda_e_detectada(self):
        a, b = tela(10), tela(10)
        b[:, :3] = 240  # o "texto novo": uma faixa de 1% da tela
        quadros = [com_bolinha(a if i < 40 else b, 0.03) if i % 2 else (a if i < 40 else b) for i in range(80)]
        slides, _ = detectar_trocas(quadros)
        self.assertEqual(len(slides), 2)
        self.assertAlmostEqual(slides[1].inicio, 40.0, delta=2.0)

    def test_texto_pequeno_que_muda_pouca_coisa_e_detectado(self):
        # 1,5% da tela mudou (o caso real de slide branco com texto)
        a = tela(255)
        b = a.copy()
        b.reshape(-1)[: int(b.size * 0.015)] = 0
        slides, _ = detectar_trocas([a] * 5 + [b] * 5)
        self.assertEqual(len(slides), 2)

    def test_mudanca_minuscula_como_cursor_nao_conta(self):
        a = tela(255)
        b = a.copy()
        b.reshape(-1)[:20] = 0  # um cursor: 20 de 57.600 pixels
        slides, _ = detectar_trocas([a] * 5 + [b] * 5)
        self.assertEqual(len(slides), 1)

    def test_piscada_que_volta_ao_mesmo_slide_nao_conta(self):
        quadros = [tela(10)] * 4 + [tela(200)] + [tela(10)] * 4
        slides, _ = detectar_trocas(quadros)
        self.assertEqual(len(slides), 1)

    def test_teto_de_slides(self):
        quadros = []
        for v in range(0, 250, 25):
            quadros += [tela(v)] * 3
        slides, truncado = detectar_trocas(quadros, max_slides=4)
        self.assertEqual(len(slides), 4)
        self.assertTrue(truncado)

    def test_video_que_acaba_no_meio_da_troca_ainda_registra(self):
        quadros = [tela(10)] * 4 + [tela(200)]
        slides, _ = detectar_trocas(quadros)
        self.assertEqual(len(slides), 2)
        self.assertEqual(slides[1].quadro_s, 4.0)

    def test_sem_quadros(self):
        self.assertEqual(detectar_trocas([]), ([], False))

    def test_intervalo_muda_a_escala_do_tempo(self):
        slides, _ = detectar_trocas([tela(10)] * 4 + [tela(200)] * 4, intervalo=2.0)
        self.assertEqual(slides[1].inicio, 8.0)


class TestJuntarParecidos(unittest.TestCase):
    def test_texto_quase_igual_vira_um_slide_e_estende_o_fim(self):
        a = Slide(0, 10, 2, "Notional da put vendida", 80.0, "a.jpg")
        b = Slide(10, 20, 12, "Notional da put vendida.", 90.0, "b.jpg")
        (unico,) = juntar_parecidos([a, b])
        self.assertEqual((unico.inicio, unico.fim), (0, 20))
        self.assertEqual(unico.frame, "b.jpg")  # ficou a leitura mais confiável

    def test_texto_diferente_continua_separado(self):
        a = Slide(0, 10, 2, "Notional da put vendida")
        b = Slide(10, 20, 12, "Notional da call vendida mais longa")
        self.assertEqual(len(juntar_parecidos([a, b])), 2)

    def test_sem_texto_nunca_junta(self):
        self.assertEqual(len(juntar_parecidos([Slide(0, 5, 1), Slide(5, 9, 6)])), 2)

    def test_texto_curto_nunca_junta(self):
        self.assertEqual(len(juntar_parecidos([Slide(0, 5, 1, "Fim"), Slide(5, 9, 6, "Fim")])), 2)


class TestPalpite(unittest.TestCase):
    def slides(self, n, palavras):
        return [Slide(i * 60, (i + 1) * 60, i * 60 + 2, " ".join(["palavra"] * palavras)) for i in range(n)]

    def test_indicadores(self):
        ind = indicadores(self.slides(10, 20), duracao_s=600, largura=1280, altura=720)
        self.assertEqual(ind["trocas"], 10)
        self.assertEqual(ind["trocas_por_min"], 1.0)
        self.assertEqual(ind["tempo_medio_s"], 60.0)
        self.assertEqual(ind["palavras_por_tela"], 20.0)
        self.assertFalse(ind["vertical"])

    def test_aula(self):
        perfil, _ = sugerir_perfil(indicadores(self.slides(10, 20), 600, 1280, 720))
        self.assertEqual(perfil, "aula")

    def test_vertical_e_corte(self):
        perfil, motivo = sugerir_perfil(indicadores(self.slides(2, 20), 600, 720, 1280))
        self.assertEqual(perfil, "corte")
        self.assertIn("vertical", motivo)

    def test_muita_troca_e_corte(self):
        perfil, _ = sugerir_perfil(indicadores(self.slides(100, 20), 600, 1280, 720))
        self.assertEqual(perfil, "corte")

    def test_pouco_texto_e_nenhum(self):
        perfil, _ = sugerir_perfil(indicadores(self.slides(10, 2), 600, 1280, 720))
        self.assertEqual(perfil, "nenhum")

    def test_sem_slides_nao_quebra(self):
        ind = indicadores([], 0, 1280, 720)
        self.assertEqual(ind["trocas_por_min"], 0.0)
        self.assertEqual(sugerir_perfil(ind)[0], "nenhum")


class TestLimparRuido(unittest.TestCase):
    BARRA = "Arquivo Editar Visualização Histórico Favoritos Perfis"

    def slides(self, textos):
        return [visual.Slide(inicio=float(i), fim=float(i + 1), quadro_s=float(i), texto=t, confianca=80.0,
                             frame=f"frames/{i + 1:04d}.jpg") for i, t in enumerate(textos)]

    def test_linha_que_se_repete_em_muitos_slides_sai_do_texto(self):
        slides = self.slides([f"{self.BARRA}\nConteúdo número {i} da aula" for i in range(6)])
        limpos, ruido, descartados = visual.limpar_ruido(slides)
        self.assertEqual([s.texto for s in limpos], [f"Conteúdo número {i} da aula" for i in range(6)])
        self.assertEqual(ruido, [self.BARRA])
        self.assertEqual(descartados, 0)

    def test_pequenas_diferencas_do_ocr_na_mesma_barra_tambem_saem(self):
        variacoes = [self.BARRA, self.BARRA.replace("Histórico", "Historico"), self.BARRA, self.BARRA + " |",
                     self.BARRA, self.BARRA.replace("Perfis", "Perfls")]
        slides = self.slides([f"{b}\nConteúdo número {i} da aula" for i, b in enumerate(variacoes)])
        limpos, _, _ = visual.limpar_ruido(slides)
        self.assertTrue(all(s.texto.startswith("Conteúdo número") and "\n" not in s.texto for s in limpos))

    def test_slide_que_so_tinha_a_barra_ou_nunca_teve_texto_e_descartado_e_contado(self):
        textos = [f"{self.BARRA}\nConteúdo {i} da aula toda" for i in range(5)] + [self.BARRA, ""]
        limpos, _, descartados = visual.limpar_ruido(self.slides(textos))
        self.assertEqual(len(limpos), 5)
        self.assertEqual(descartados, 2)

    def test_poucos_slides_nao_provam_o_que_e_fixo(self):
        slides = self.slides([f"{self.BARRA}\nConteúdo {i}" for i in range(visual.RUIDO_SLIDES_MIN - 1)])
        limpos, ruido, _ = visual.limpar_ruido(slides)
        self.assertEqual([s.texto for s in limpos], [s.texto for s in slides])
        self.assertEqual(ruido, [])

    def test_linha_curta_repetida_nunca_e_ruido(self):
        slides = self.slides([f"Sim\nConteúdo número {i} da aula" for i in range(8)])
        limpos, ruido, _ = visual.limpar_ruido(slides)
        self.assertTrue(all(s.texto.startswith("Sim\n") for s in limpos))
        self.assertEqual(ruido, [])

    def test_titulo_que_aparece_em_poucos_slides_fica(self):
        textos = ["Título importante da seção 1"] + [f"Conteúdo número {i} da aula" for i in range(9)]
        limpos, ruido, _ = visual.limpar_ruido(self.slides(textos))
        self.assertEqual(limpos[0].texto, "Título importante da seção 1")
        self.assertEqual(ruido, [])

    def test_so_registra_as_mais_frequentes_e_nao_mexe_nos_originais(self):
        fixas = [f"Linha fixa número {i} do navegador" for i in range(visual.RUIDO_MAX_LISTADAS + 3)]
        slides = self.slides(["\n".join(fixas) + f"\nConteúdo {i} da aula" for i in range(6)])
        original = slides[0].texto
        _, ruido, _ = visual.limpar_ruido(slides)
        self.assertEqual(len(ruido), visual.RUIDO_MAX_LISTADAS)
        self.assertEqual(slides[0].texto, original)

    def test_a_confianca_e_o_quadro_ficam(self):
        slides = self.slides([f"{self.BARRA}\nConteúdo {i} da aula" for i in range(6)])
        limpos, _, _ = visual.limpar_ruido(slides)
        self.assertEqual((limpos[2].confianca, limpos[2].frame), (80.0, "frames/0003.jpg"))


if __name__ == "__main__":
    unittest.main()
