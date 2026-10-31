import tempfile
import unittest
from pathlib import Path

import numpy as np

from vatty import aula, ocr


def tela(valor):
    return np.full((180, 320), valor, dtype=np.uint8)


INFO = {"largura": 1280, "altura": 720, "duracao_s": 20.0}
TEXTOS = {"Slide um com bastante texto aqui": 90.0, "Outro slide bem diferente do primeiro": 80.0}


class FerramentasFalsas:
    """ffmpeg e Tesseract de mentira: 3 slides (A, B, de novo A com leve diferença) e textos por horário."""

    def __init__(self, textos_por_horario, quadros_=None, info=None):
        self.textos = textos_por_horario
        self.quadros = quadros_ if quadros_ is not None else [tela(10)] * 5 + [tela(200)] * 5 + [tela(100)] * 10
        self.info = info or INFO
        self.extraidos = []

    def ferramentas(self):
        def informacoes(video):
            return self.info

        def amostrar(video, largura, altura, intervalo):
            return iter(self.quadros)

        def extrair(video, segundos, destino):
            Path(destino).parent.mkdir(parents=True, exist_ok=True)
            Path(destino).write_bytes(b"jpg")
            self.extraidos.append(segundos)
            return Path(destino)

        def ler(imagem, idiomas, exe):
            segundos = self.extraidos[-1]
            texto = self.textos(segundos)
            return ocr.Leitura(texto=texto, confianca=TEXTOS.get(texto, 50.0) if texto else None)

        return aula.Ferramentas(informacoes, amostrar, extrair, ler)


def textos(segundos):
    if segundos < 5:
        return "Slide um com bastante texto aqui"
    if segundos < 10:
        return "Outro slide bem diferente do primeiro"
    return "Slide um com bastante texto aqui"


class TestDetectar(unittest.TestCase):
    def test_acha_os_slides_e_estende_o_ultimo_ate_o_fim_do_video(self):
        f = FerramentasFalsas(textos)
        d = aula.detectar("v.mp4", ferramentas=f.ferramentas())
        self.assertEqual(len(d.slides), 3)
        self.assertEqual(d.slides[-1].fim, 20.0)
        self.assertFalse(d.truncado)

    def test_progresso(self):
        vistos = []
        aula.detectar("v.mp4", progresso=lambda s, total: vistos.append((s, total)),
                      ferramentas=FerramentasFalsas(textos).ferramentas())
        self.assertEqual(vistos[0], (0.0, 20.0))
        self.assertEqual(vistos[-1], (19.0, 20.0))


class TestPalpite(unittest.TestCase):
    def test_le_poucos_slides_e_sugere_aula_quando_tem_texto(self):
        f = FerramentasFalsas(textos)
        d = aula.detectar("v.mp4", ferramentas=f.ferramentas())
        f.extraidos.clear()
        with tempfile.TemporaryDirectory() as tmp:
            ind, (perfil, motivo) = aula.palpite("v.mp4", d, tmp, idiomas="por+eng", exe="t",
                                                 ferramentas=f.ferramentas())
        self.assertEqual(len(f.extraidos), 3)       # só tinha 3 slides, leu os 3
        self.assertGreaterEqual(ind["palavras_por_tela"], 5)
        self.assertEqual(ind["trocas"], 3)

    def test_amostras_espalhadas(self):
        self.assertEqual(aula._escolher_amostras(list(range(3)), 4), [0, 1, 2])
        self.assertEqual(aula._escolher_amostras(list(range(100)), 4), [0, 33, 66, 99])

    def test_nao_mexe_nos_slides_originais(self):
        f = FerramentasFalsas(textos)
        d = aula.detectar("v.mp4", ferramentas=f.ferramentas())
        with tempfile.TemporaryDirectory() as tmp:
            aula.palpite("v.mp4", d, tmp, idiomas="eng", exe="t", ferramentas=f.ferramentas())
        self.assertTrue(all(s.texto == "" for s in d.slides))


class TestMontar(unittest.TestCase):
    def montar(self, f, destino):
        d = aula.detectar("v.mp4", ferramentas=f.ferramentas())
        return aula.montar("v.mp4", d, destino, idiomas="por+eng", exe="t", parametros={"intervalo_s": 1.0},
                           ferramentas=f.ferramentas())

    def test_monta_o_visual_com_os_eventos_e_os_quadros(self):
        f = FerramentasFalsas(textos)
        with tempfile.TemporaryDirectory() as tmp:
            dados = self.montar(f, tmp)
            frames = sorted(p.name for p in (Path(tmp) / "frames").iterdir())
        self.assertEqual(dados["perfil"], "aula")
        self.assertEqual(dados["ocr"], "tesseract")
        self.assertEqual(dados["resolucao"], [1280, 720])
        self.assertEqual(dados["parametros"], {"intervalo_s": 1.0})
        self.assertEqual([e["tipo"] for e in dados["eventos"]], ["slide"] * 3)
        self.assertEqual(dados["eventos"][0]["texto"], "Slide um com bastante texto aqui")
        self.assertEqual(dados["eventos"][0]["frame"], "frames/0001.jpg")
        self.assertEqual(frames, ["0001.jpg", "0002.jpg", "0003.jpg"])

    def test_slides_vizinhos_com_o_mesmo_texto_sao_juntados_e_o_quadro_sobrante_apagado(self):
        # B e C têm o mesmo texto: viram um slide só, de 5 s até o fim
        f = FerramentasFalsas(lambda s: "Slide um com bastante texto aqui" if s < 5 else "Outro slide bem diferente do primeiro")
        with tempfile.TemporaryDirectory() as tmp:
            dados = self.montar(f, tmp)
            frames = sorted(p.name for p in (Path(tmp) / "frames").iterdir())
        self.assertEqual(len(dados["eventos"]), 2)
        self.assertEqual((dados["eventos"][1]["inicio"], dados["eventos"][1]["fim"]), (5.0, 20.0))
        self.assertEqual(len(frames), 2)  # o quadro do slide juntado foi apagado
        self.assertEqual({e["frame"].split("/")[1] for e in dados["eventos"]}, set(frames))

    def test_refazer_nao_deixa_quadro_de_execucao_antiga(self):
        f = FerramentasFalsas(textos)
        with tempfile.TemporaryDirectory() as tmp:
            antigo = Path(tmp) / "frames" / "0099.jpg"
            antigo.parent.mkdir()
            antigo.write_bytes(b"velho")
            self.montar(f, tmp)
            self.assertFalse(antigo.exists())

    def test_slide_sem_texto_e_descartado_e_contado_e_o_quadro_apagado(self):
        f = FerramentasFalsas(lambda s: "")
        with tempfile.TemporaryDirectory() as tmp:
            dados = self.montar(f, tmp)
            frames = list((Path(tmp) / "frames").iterdir())
        self.assertEqual(dados["eventos"], [])
        self.assertEqual(dados["slides_sem_texto_descartados"], 3)
        self.assertEqual(frames, [])

    def test_barra_fixa_sai_do_texto_e_aparece_no_cabecalho(self):
        barra = "Arquivo Editar Visualização Histórico Favoritos"
        # 6 telas diferentes, todas com a mesma barra do navegador em cima
        quadros_ = [tela(v) for v in (10, 60, 110, 160, 210, 250) for _ in range(3)]
        assunto = ["derivadas", "integrais", "matrizes", "limites", "vetores", "séries"]
        f = FerramentasFalsas(lambda s: f"{barra}\nConteúdo sobre {assunto[int(s // 3)]} começa aqui", quadros_=quadros_,
                              info={"largura": 1280, "altura": 720, "duracao_s": 18.0})
        with tempfile.TemporaryDirectory() as tmp:
            dados = self.montar(f, tmp)
        self.assertEqual(len(dados["eventos"]), 6)
        self.assertTrue(all(barra not in e["texto"] for e in dados["eventos"]))
        self.assertTrue(all(e["texto"].startswith("Conteúdo sobre") for e in dados["eventos"]))
        self.assertEqual(dados["ruido_removido"], [barra])
        self.assertEqual(dados["slides_sem_texto_descartados"], 0)

    def test_progresso(self):
        vistos = []
        f = FerramentasFalsas(textos)
        d = aula.detectar("v.mp4", ferramentas=f.ferramentas())
        with tempfile.TemporaryDirectory() as tmp:
            aula.montar("v.mp4", d, tmp, idiomas="eng", exe="t", progresso=lambda n, t: vistos.append((n, t)),
                        ferramentas=f.ferramentas())
        self.assertEqual(vistos, [(1, 3), (2, 3), (3, 3)])


if __name__ == "__main__":
    unittest.main()
