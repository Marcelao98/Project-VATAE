import unittest

from vatty import repeticao
from vatty.motor import Segmento

TERMOS = repeticao.termos_da_lista("call, put, strike, notional, delta, gama, hedge, swap")


def seg(texto, inicio=0.0, fim=1.0):
    return Segmento(inicio, fim, texto)


class TestSinais(unittest.TestCase):
    def test_fala_normal_com_termos_nao_e_suspeita(self):
        s = seg("A call dá o direito de comprar no strike, e o delta mede a sensibilidade.")
        self.assertIsNone(repeticao.motivo(s, None, TERMOS))

    def test_eco_da_lista(self):
        s = seg("Call, put, strike, notional, delta, gama.")
        self.assertEqual(repeticao.motivo(s, None, TERMOS), "eco da lista de termos")

    def test_texto_repetitivo(self):
        s = seg("vamos lá vamos lá " * 8)
        self.assertEqual(repeticao.motivo(s, None, TERMOS), "texto repetitivo")

    def test_texto_curto_nao_conta_compressao(self):
        self.assertIsNone(repeticao.motivo(seg("sim sim sim"), None, TERMOS))

    def test_frase_repetida_em_seguida(self):
        a, b = seg("O notional é o valor de referência."), seg("o notional é o valor de referência")
        self.assertEqual(repeticao.motivo(b, a, TERMOS), "frase repetida")

    def test_resposta_curta_repetida_e_normal(self):
        self.assertIsNone(repeticao.motivo(seg("Isso."), seg("Isso."), TERMOS))

    def test_sem_lista_nao_ha_eco(self):
        self.assertIsNone(repeticao.motivo(seg("Call, put, strike, notional, delta."), None, []))


class TestTrechos(unittest.TestCase):
    def test_junta_seguidos_e_inclui_primeira_ocorrencia(self):
        segs = [
            seg("Bom dia, vamos falar de opções."),
            seg("O preço subiu bastante hoje."),
            seg("O preço subiu bastante hoje."),
            seg("O preço subiu bastante hoje."),
            seg("Agora, o strike da call."),
            seg("Call, put, strike, notional, delta, gama."),
        ]
        self.assertEqual(repeticao.trechos_suspeitos(segs, TERMOS),
                         [(1, 3, "frase repetida"), (5, 5, "eco da lista de termos")])

    def test_nada_suspeito(self):
        self.assertEqual(repeticao.trechos_suspeitos([seg("a b c"), seg("d e f")], TERMOS), [])


if __name__ == "__main__":
    unittest.main()
