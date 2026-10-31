import json
import tempfile
import unittest
from pathlib import Path

from vatty import pasta
from vatty.motor import Resultado, Segmento


class TestPasta(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(pasta.slug("Aula 3: Derivadas & Integrais!"), "aula-3-derivadas-integrais")
        self.assertEqual(pasta.slug("Cálculo 📚", "abc123"), "calculo-abc123")
        self.assertEqual(pasta.slug("📚"), "video")
        self.assertLessEqual(len(pasta.slug("a" * 200)), pasta.TAMANHO_MAX_SLUG)

    def test_gravar(self):
        resultado = Resultado(
            fonte="https://youtu.be/x", duracao_s=20.0, modelo=None, idioma="pt",
            segmentos=[Segmento(0.0, 2.0, "Olá."), Segmento(2.5, 4.0, "Tudo bem?"), Segmento(10.0, 12.0, "Tchau.")],
            origem="legenda-manual",
        )
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "aula-x"
            txt = pasta.gravar(destino, {"tipo": "youtube", "titulo": "Aula"}, resultado)

            # `[mm:ss]` em cada parágrafo, em todas as fontes
            self.assertEqual(txt.read_text(encoding="utf-8"), "[00:00] Olá. Tudo bem?\n\n[00:10] Tchau.\n")
            self.assertEqual(json.loads((destino / "fonte.json").read_text(encoding="utf-8"))["titulo"], "Aula")
            transcricao = json.loads((destino / "transcricao.json").read_text(encoding="utf-8"))
            self.assertEqual(transcricao["origem"], "legenda-manual")
            self.assertIsNone(transcricao["modelo"])
            self.assertEqual(transcricao["segmentos"][1], {"inicio": 2.5, "fim": 4.0, "texto": "Tudo bem?"})
            # um segmento por linha, para os agentes lerem por faixas
            linhas = (destino / "transcricao.json").read_text(encoding="utf-8").splitlines()
            self.assertIn('    {"inicio": 2.5, "fim": 4.0, "texto": "Tudo bem?"},', linhas)

    def test_falante_so_aparece_quando_existe(self):
        resultado = Resultado(fonte="g", duracao_s=5.0, modelo="m", idioma="pt",
                              segmentos=[Segmento(0.0, 1.0, "oi", "eu"), Segmento(2.0, 3.0, "olá")])
        with tempfile.TemporaryDirectory() as tmp:
            pasta.gravar(Path(tmp), {"tipo": "gravacao"}, resultado)
            segs = json.loads((Path(tmp) / "transcricao.json").read_text(encoding="utf-8"))["segmentos"]
        self.assertEqual(segs[0], {"inicio": 0.0, "fim": 1.0, "texto": "oi", "falante": "eu"})
        self.assertEqual(segs[1], {"inicio": 2.0, "fim": 3.0, "texto": "olá"})

    def _duas_faixas(self, **extra):
        return Resultado(
            fonte="gravacao", duracao_s=8.0, modelo="m", idioma="pt", origem="whisper",
            segmentos=[Segmento(0.0, 3.0, "Eu já fiz um vídeo antes, mas", "outros"), Segmento(3.2, 4.0, "Vamos ver", "eu"),
                       Segmento(3.5, 6.0, "eu quero que esse seja o tutorial", "outros")],
            **extra)

    def test_gravacao_com_duas_faixas_gera_um_arquivo_por_canal_e_a_linha_do_tempo(self):
        fonte = {"tipo": "gravacao", "faixas": ["sistema", "microfone"]}
        with tempfile.TemporaryDirectory() as tmp:
            txt = pasta.gravar(Path(tmp), fonte, self._duas_faixas(faixas=["sistema", "microfone"]))
            ler = lambda nome: (Path(tmp) / nome).read_text(encoding="utf-8")
            self.assertEqual(txt.name, "transcricao.txt")
            self.assertEqual(ler("transcricao.txt"),
                             "[00:00] Outros: Eu já fiz um vídeo antes, mas eu quero que esse seja o tutorial\n\n"
                             "[00:03] Eu: Vamos ver\n")
            self.assertEqual(ler("transcricao-outros.txt"),
                             "[00:00] Eu já fiz um vídeo antes, mas eu quero que esse seja o tutorial\n")
            self.assertEqual(ler("transcricao-eu.txt"), "[00:03] Vamos ver\n")
            cabecalho = json.loads(ler("transcricao.json"))
            self.assertEqual(cabecalho["faixas"], ["sistema", "microfone"])
            self.assertEqual(len(cabecalho["segmentos"]), 3)  # o json segue com um segmento por linha, com `falante`
            self.assertEqual(cabecalho["segmentos"][1]["falante"], "eu")

    def test_canal_mudo_gera_arquivo_vazio_mas_a_gravacao_continua_de_duas_faixas(self):
        fonte = {"tipo": "gravacao", "faixas": ["sistema", "microfone"]}
        resultado = Resultado(fonte="g", duracao_s=5.0, modelo="m", idioma="pt",
                              segmentos=[Segmento(0.0, 1.0, "oi", "outros")], faixas=["sistema", "microfone"])
        with tempfile.TemporaryDirectory() as tmp:
            pasta.gravar(Path(tmp), fonte, resultado)
            self.assertEqual((Path(tmp) / "transcricao-eu.txt").read_text(encoding="utf-8"), "")
            self.assertEqual((Path(tmp) / "transcricao.txt").read_text(encoding="utf-8"), "[00:00] Outros: oi\n")

    def test_gravacao_com_uma_faixa_fica_como_antes(self):
        fonte = {"tipo": "gravacao", "faixas": ["microfone"]}
        resultado = Resultado(fonte="g", duracao_s=5.0, modelo="m", idioma="pt",
                              segmentos=[Segmento(0.0, 1.0, "oi", "eu"), Segmento(1.5, 2.0, "tudo bem?", "eu")])
        with tempfile.TemporaryDirectory() as tmp:
            txt = pasta.gravar(Path(tmp), fonte, resultado)
            self.assertEqual(txt.read_text(encoding="utf-8"), "[00:00] Eu: oi tudo bem?\n")
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()),
                             ["fonte.json", "transcricao.json", "transcricao.txt"])
            self.assertNotIn("faixas", json.loads((Path(tmp) / "transcricao.json").read_text(encoding="utf-8")))

    def test_youtube_e_arquivo_nao_ganham_arquivos_por_canal(self):
        resultado = Resultado(fonte="x", duracao_s=5.0, modelo="m", idioma="pt", segmentos=[Segmento(0.0, 1.0, "oi")])
        for fonte in ({"tipo": "youtube"}, {"tipo": "arquivo"}):
            with tempfile.TemporaryDirectory() as tmp:
                pasta.gravar(Path(tmp), fonte, resultado)
                self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()),
                                 ["fonte.json", "transcricao.json", "transcricao.txt"])

    def test_gravar_visual_um_evento_por_linha(self):
        dados = {"perfil": "aula", "ocr": "tesseract", "eventos": [
            {"tipo": "slide", "inicio": 0.0, "fim": 4.0, "texto": "Linha 1\nLinha 2", "confianca": 96.2, "frame": "frames/0001.jpg"},
            {"tipo": "slide", "inicio": 4.0, "fim": 9.0, "texto": "", "confianca": None, "frame": "frames/0002.jpg"},
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            destino = pasta.gravar_visual(Path(tmp) / "v", dados)
            lido = json.loads(destino.read_text(encoding="utf-8"))
            linhas = destino.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lido, {"versao": pasta.VERSAO_CONTRATO, **dados})
        self.assertEqual(sum(1 for l in linhas if '"tipo": "slide"' in l), 2)  # um por linha, texto com \\n escapado

    def test_gravar_visual_sem_eventos_continua_json_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = pasta.gravar_visual(Path(tmp), {"perfil": "aula", "eventos": []})
            self.assertEqual(json.loads(destino.read_text(encoding="utf-8"))["eventos"], [])

    def test_versao_do_contrato_nos_tres_json(self):
        resultado = Resultado(fonte="f", duracao_s=0.0, modelo=None, idioma="pt")
        with tempfile.TemporaryDirectory() as tmp:
            pasta.gravar(Path(tmp), {"tipo": "arquivo"}, resultado)
            pasta.gravar_visual(Path(tmp), {"perfil": "aula", "eventos": []})
            for nome in ("fonte.json", "transcricao.json", "visual.json"):
                dados = json.loads((Path(tmp) / nome).read_text(encoding="utf-8"))
                self.assertEqual(dados["versao"], pasta.VERSAO_CONTRATO, nome)

    def test_gravar_sem_segmentos_continua_json_valido(self):
        resultado = Resultado(fonte="f", duracao_s=0.0, modelo=None, idioma="pt")
        with tempfile.TemporaryDirectory() as tmp:
            pasta.gravar(Path(tmp), {}, resultado)
            dados = json.loads((Path(tmp) / "transcricao.json").read_text(encoding="utf-8"))
            self.assertEqual(dados["segmentos"], [])


class TestCabecalhoPreprocessamento(unittest.TestCase):
    def _cabecalho(self, **extra):
        with tempfile.TemporaryDirectory() as tmp:
            pasta.gravar(Path(tmp), {"tipo": "arquivo"},
                         Resultado(fonte="x", duracao_s=1.0, modelo="m", idioma="pt",
                                   segmentos=[Segmento(0.0, 1.0, "oi")], **extra))
            return json.loads((Path(tmp) / "transcricao.json").read_text(encoding="utf-8"))

    def test_sem_preprocessamento_o_cabecalho_fica_como_antes(self):
        self.assertNotIn("preprocessamento", self._cabecalho())

    def test_com_preprocessamento_o_cabecalho_registra_o_que_foi_feito(self):
        info = {"aplicado": True, "filtro": "highpass=f=80", "ruido": "arnndn:sh.rnnn"}
        self.assertEqual(self._cabecalho(preprocessamento=info)["preprocessamento"], info)


if __name__ == "__main__":
    unittest.main()
