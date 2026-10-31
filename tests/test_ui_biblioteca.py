import json
import os
import tempfile
import unittest
from pathlib import Path

from vatty.ui import biblioteca as b


def criar(raiz, slug, texto="[00:05] oi mundo [?] tchau\n\n[01:10] fim\n", **extra):
    p = Path(raiz) / slug
    p.mkdir()
    (p / "fonte.json").write_text(json.dumps({"titulo": f"T {slug}", "tipo": "arquivo"}))
    (p / "transcricao.json").write_text(json.dumps({
        "origem": "whisper", "duracao_s": 90, "trechos_duvidosos": 1, "glossario": {"x": 2},
        "segmentos": [{"inicio": 5.0, "fim": 7.0, "texto": "oi mundo", "pessoa": "Ana"}], **extra}))
    (p / "transcricao.txt").write_text(texto, encoding="utf-8")
    return p


class TestPastaDe(unittest.TestCase):
    def test_recusa_fuga_de_pasta_e_inexistente(self):
        with tempfile.TemporaryDirectory() as d:
            criar(d, "aula")
            for ruim in ("..", "../x", "a/b", "", "nao-existe", "a\\b"):
                with self.assertRaises(b.NaoAchei):
                    b.pasta_de(d, ruim)
            self.assertEqual(b.pasta_de(d, "aula").name, "aula")


class TestListarELer(unittest.TestCase):
    def test_lista_mais_recente_primeiro_e_resume(self):
        with tempfile.TemporaryDirectory() as d:
            criar(d, "velha")
            criar(d, "nova")
            # mexe no horário: a "velha" agora é a mais nova (horário explícito, o do Windows pode empatar)
            depois = (Path(d) / "nova" / "transcricao.json").stat().st_mtime + 10
            os.utime(Path(d) / "velha" / "transcricao.json", (depois, depois))
            (Path(d) / "lixo").mkdir()  # pasta sem transcrição não aparece
            lista = b.listar(d)
            self.assertEqual([v["slug"] for v in lista], ["velha", "nova"])
            self.assertEqual((lista[0]["duvidosos"], lista[0]["glossario"]), (1, 2))

    def test_raiz_inexistente_e_lista_vazia(self):
        self.assertEqual(b.listar("/nao/existe"), [])

    def test_leitor_separa_o_marcador_duvidoso(self):
        with tempfile.TemporaryDirectory() as d:
            criar(d, "aula")
            ps = b.ler(d, "aula")["paragrafos"]
            self.assertEqual((ps[0]["inicio_s"], ps[0]["texto"], ps[0]["duvidoso"]), (5, "oi mundo tchau", True))
            self.assertFalse(ps[1]["duvidoso"])


class TestExportar(unittest.TestCase):
    def test_formatos(self):
        with tempfile.TemporaryDirectory() as d:
            criar(d, "aula")
            self.assertIn("oi mundo", b.exportar(d, "aula", "txt")[0].decode())
            self.assertTrue(b.exportar(d, "aula", "vtt")[0].decode().startswith("WEBVTT"))
            self.assertIn("1\n00:00:05,000 --> 00:00:07,000", b.exportar(d, "aula", "srt")[0].decode())
            self.assertIn("Ana", b.exportar(d, "aula", "csv")[0].decode())
            dados, mime, nome = b.exportar(d, "aula", "md")
            self.assertEqual(nome, "aula.md")
            self.assertIn("**[00:05]**", dados.decode())

    def test_formato_desconhecido(self):
        with tempfile.TemporaryDirectory() as d:
            criar(d, "aula")
            with self.assertRaises(b.NaoAchei):
                b.exportar(d, "aula", "exe")


class TestGerados(unittest.TestCase):
    def test_so_serve_arquivo_conhecido_da_pasta(self):
        with tempfile.TemporaryDirectory() as d:
            p = criar(d, "aula")
            (p / "ata-x.md").write_text("# a")
            (p / "segredo.txt").write_text("x")
            self.assertEqual(b.arquivo_gerado(d, "aula", "ata-x.md").name, "ata-x.md")
            with self.assertRaises(b.NaoAchei):
                b.arquivo_gerado(d, "aula", "segredo.txt")


if __name__ == "__main__":
    unittest.main()
