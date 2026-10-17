import tempfile
import unittest
from pathlib import Path

import numpy as np

from vatty import app, aula
from vatty.ocr import Leitura

A = np.zeros((40, 64), dtype=np.uint8)
B = np.full((40, 64), 200, dtype=np.uint8)
AVISO = A.copy()
AVISO[30:36, 40:60] = 220  # um aviso pequeno no canto de baixo


def _mexendo(n, semente=0):
    gerador = np.random.default_rng(semente)
    return [gerador.integers(0, 255, (40, 64), dtype=np.uint8) for _ in range(n)]


def _resumo(eventos):
    return [(e.tipo, round(e.inicio, 1), round(e.fim, 1), e.repete) for e in eventos]


class TestDetectar(unittest.TestCase):
    def test_troca_de_tela(self):
        eventos, truncado = app.detectar_eventos([A] * 10 + [B] * 10)
        self.assertEqual(_resumo(eventos), [("tela", 0.0, 2.0, None), ("tela", 2.0, 4.0, None)])
        self.assertIsNone(eventos[1].regiao)  # mudou a tela toda: lê inteira
        self.assertFalse(truncado)

    def test_aviso_que_aparece_e_some_vira_transitorio_e_so_a_regiao_e_lida(self):
        eventos, _ = app.detectar_eventos([A] * 10 + [AVISO] * 5 + [A] * 10)
        self.assertEqual(_resumo(eventos), [("tela", 0.0, 2.0, None), ("transitorio", 2.0, 3.0, None),
                                            ("tela", 3.0, 5.0, 0)])
        x0, y0, x1, y1 = eventos[1].regiao
        self.assertTrue(x0 < 40 / 64 < 60 / 64 <= x1 and y0 < 30 / 40 < 36 / 40 <= y1)

    def test_piscada_curta_nao_conta(self):
        eventos, _ = app.detectar_eventos([A] * 5 + [AVISO] + [A] * 5)
        self.assertEqual(_resumo(eventos), [("tela", 0.0, 2.2, None)])

    def test_tela_mexendo_sem_parar_vira_movimento(self):
        eventos, _ = app.detectar_eventos([A] * 5 + _mexendo(15) + [B] * 5)
        self.assertEqual([e[:3] for e in _resumo(eventos)],
                         [("tela", 0.0, 1.0), ("movimento", 1.0, 4.0), ("tela", 4.0, 5.0)])

    def test_tela_que_volta_depois_nao_e_lida_de_novo(self):
        eventos, _ = app.detectar_eventos([A] * 5 + [B] * 25 + [A] * 5)
        self.assertEqual([(e.tipo, e.repete) for e in eventos], [("tela", None), ("tela", None), ("tela", 0)])

    def test_regiao_mudada(self):
        self.assertIsNone(app.regiao_mudada(A, A))  # nada mudou
        self.assertIsNone(app.regiao_mudada(A, B))  # mudou demais: tela nova
        self.assertIsNotNone(app.regiao_mudada(A, AVISO))

    def test_teto_de_eventos(self):
        eventos, truncado = app.detectar_eventos(([A] * 3 + [B] * 25) * 3, max_eventos=2)
        self.assertEqual(len(eventos), 2)
        self.assertTrue(truncado)


class TestMontar(unittest.TestCase):
    def test_le_cada_tela_uma_vez_e_guarda_o_recorte(self):
        quadros = [A] * 10 + [AVISO] * 5 + [A] * 10 + _mexendo(15) + [B] * 10
        extraidos = []

        def extrair(video, segundos, destino, recorte=None):
            extraidos.append(recorte)
            Path(destino).parent.mkdir(parents=True, exist_ok=True)
            Path(destino).write_bytes(b"jpg")
            return Path(destino)

        textos = iter(["Cadastro\nNome", "Erro 500: tente de novo", ""])
        ferramentas = aula.Ferramentas(
            informacoes=lambda v: {"largura": 1920, "altura": 1080, "duracao_s": 10.0},
            amostrar=lambda v, w, h, i: iter(quadros), extrair=extrair,
            ler=lambda imagem, idiomas, exe: Leitura(next(textos), 90.0))
        with tempfile.TemporaryDirectory() as tmp:
            dados = app.montar("tela.mp4", tmp, idiomas="por", exe="tesseract", ferramentas=ferramentas)
        self.assertEqual(dados["perfil"], "app")
        self.assertEqual(dados["telas_lidas"], 3)
        self.assertEqual(len(extraidos), 3)  # a volta à tela A não é lida de novo
        self.assertIsNone(extraidos[0])
        self.assertIsNotNone(extraidos[1])  # o aviso: só o pedaço
        tipos = [e["tipo"] for e in dados["eventos"]]
        self.assertEqual(tipos, ["tela", "transitorio", "tela", "movimento", "tela"])
        aviso, volta, movimento, branca = dados["eventos"][1:]
        self.assertEqual(aviso["texto"], "Erro 500: tente de novo")
        self.assertIn("regiao", aviso)
        self.assertEqual(volta, {"tipo": "tela", "inicio": 3.0, "fim": 5.0, "frame": "frames/0001.jpg", "repetida": True})
        self.assertNotIn("frame", movimento)
        self.assertEqual((branca["texto"], branca["fim"]), ("", 10.0))  # tela sem texto fica


if __name__ == "__main__":
    unittest.main()
