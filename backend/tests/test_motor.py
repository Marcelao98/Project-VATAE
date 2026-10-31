import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from vatty import motor


class ModeloDuble:
    """Faz o papel do WhisperModel: guarda o que recebeu e devolve segmentos prontos."""

    def __init__(self, segmentos=(), idioma="pt"):
        self.segmentos = segmentos
        self.idioma = idioma
        self.audio = None
        self.opcoes = None

    def transcribe(self, audio, **opcoes):
        self.audio, self.opcoes = audio, opcoes
        brutos = (SimpleNamespace(start=a, end=b, text=t) for a, b, t in self.segmentos)
        return brutos, SimpleNamespace(language=self.idioma)


def transcrever(duble, duracao=10.0, **kwargs):
    array = np.zeros(int(duracao * 16000), dtype=np.float32)
    return motor.transcrever(
        "sessao.opus",
        carregar_audio=lambda caminho: (array, duracao),
        obter_modelo=lambda nome: duble,
        **kwargs,
    )


class TestParametros(unittest.TestCase):
    def test_padroes_provados_na_sessao_real(self):
        duble = ModeloDuble()
        transcrever(duble)
        self.assertEqual(duble.opcoes["language"], "pt")
        self.assertIs(duble.opcoes["vad_filter"], True)
        self.assertIs(duble.opcoes["condition_on_previous_text"], False)
        self.assertNotIn("hotwords", duble.opcoes)

    def test_recebe_array_e_nao_caminho(self):
        duble = ModeloDuble()
        transcrever(duble)
        self.assertIsInstance(duble.audio, np.ndarray)

    def test_hotwords_so_quando_passado(self):
        duble = ModeloDuble()
        transcrever(duble, hotwords="Nhalor, Vorric")
        self.assertEqual(duble.opcoes["hotwords"], "Nhalor, Vorric")

    def test_hotwords_vazio_continua_desligado(self):
        duble = ModeloDuble()
        transcrever(duble, hotwords="")
        self.assertNotIn("hotwords", duble.opcoes)

    def test_auto_vira_none(self):
        duble = ModeloDuble(idioma="en")
        resultado = transcrever(duble, idioma="auto")
        self.assertIsNone(duble.opcoes["language"])
        self.assertEqual(resultado.idioma, "en")


class ModeloComPalavras(ModeloDuble):
    """Como o WhisperModel com word_timestamps: cada segmento pode trazer `words`."""

    def transcribe(self, audio, **opcoes):
        self.audio, self.opcoes = audio, opcoes
        brutos = (
            SimpleNamespace(start=a, end=b, text=t,
                            words=[SimpleNamespace(start=ini, end=fim, word=w) for ini, fim, w in palavras] if palavras else None)
            for a, b, t, palavras in self.segmentos
        )
        return brutos, SimpleNamespace(language=self.idioma)


class TestHorarioPorPalavra(unittest.TestCase):
    # Caso real da gravação: "Aham" saiu como {"inicio": 0.02, "fim": 37.86}.
    def test_segmento_com_palavras_vale_da_primeira_a_ultima_palavra(self):
        duble = ModeloComPalavras([(0.02, 37.86, " Aham", [(12.1, 12.6, " Aham")]),
                                   (40.0, 48.0, " Tudo bem?", [(40.5, 41.0, " Tudo"), (41.1, 41.6, " bem?")])])
        r = transcrever(duble, duracao=60.0, palavras=True)
        self.assertEqual([(s.inicio, s.fim, s.texto) for s in r.segmentos],
                         [(12.1, 12.6, "Aham"), (40.5, 41.6, "Tudo bem?")])

    def test_segmento_sem_palavras_fica_como_esta(self):
        duble = ModeloComPalavras([(1.0, 3.0, " Sem palavras", None), (4.0, 6.0, " Lista vazia", [])])
        r = transcrever(duble, palavras=True)
        self.assertEqual([(s.inicio, s.fim) for s in r.segmentos], [(1.0, 3.0), (4.0, 6.0)])

    def test_modelo_sem_atributo_words_funciona(self):
        r = transcrever(ModeloDuble([(0.0, 2.0, "oi")]), palavras=True)
        self.assertEqual((r.segmentos[0].inicio, r.segmentos[0].fim), (0.0, 2.0))

    def test_word_timestamps_so_liga_quando_pedido(self):
        duble = ModeloDuble()
        transcrever(duble)
        self.assertNotIn("word_timestamps", duble.opcoes)
        transcrever(duble, palavras=True)
        self.assertIs(duble.opcoes["word_timestamps"], True)
        # os parâmetros provados continuam intactos
        self.assertEqual(duble.opcoes["language"], "pt")
        self.assertIs(duble.opcoes["vad_filter"], True)
        self.assertIs(duble.opcoes["condition_on_previous_text"], False)
        self.assertIsInstance(duble.audio, np.ndarray)

    def test_o_trecho_refeito_tambem_usa_o_horario_das_palavras(self):
        class Duble(ModeloDuble):
            """Com hotwords entra em loop no 2º segmento; o refeito traz palavras com horário próprio."""

            def transcribe(self, audio, **opcoes):
                self.opcoes = opcoes
                if "hotwords" in opcoes:
                    brutos = [SimpleNamespace(start=0.0, end=4.0, text="A call dá direito de compra.", words=None),
                              SimpleNamespace(start=5.0, end=9.0, text="Call, put, strike, notional, delta.", words=None),
                              SimpleNamespace(start=10.0, end=14.0, text="Fim da aula.", words=None)]
                else:
                    brutos = [SimpleNamespace(start=0.0, end=3.5, text="O notional é quantidade vezes strike.",
                                              words=[SimpleNamespace(start=0.5, end=3.0, word="x")])]
                return iter(brutos), SimpleNamespace(language="pt")

        duble = Duble()
        r = transcrever(duble, duracao=15.0, hotwords="call, put, strike, notional, delta", palavras=True)
        self.assertTrue(r.refeitos)
        self.assertIs(duble.opcoes["word_timestamps"], True)  # o refazer herda as opções
        # janela refeita começa em 4.5 s; as palavras vão de 0.5 a 3.0 dentro dela
        self.assertEqual((r.segmentos[1].inicio, r.segmentos[1].fim), (5.0, 7.5))


class TestVadSilencio(unittest.TestCase):
    def test_desligado_por_padrao(self):
        duble = ModeloDuble()
        transcrever(duble)
        self.assertNotIn("vad_parameters", duble.opcoes)

    def test_passa_a_pausa_minima_ao_vad(self):
        duble = ModeloDuble()
        transcrever(duble, vad_silencio_ms=500)
        self.assertEqual(duble.opcoes["vad_parameters"], {"min_silence_duration_ms": 500})
        self.assertIs(duble.opcoes["vad_filter"], True)


class TestResultado(unittest.TestCase):
    def test_segmentos_e_metadados(self):
        duble = ModeloDuble([(0.0, 2.5, " Olá, mesa. "), (3.0, 6.0, "Rolem iniciativa.")])
        resultado = transcrever(duble, duracao=8.0, modelo="small")
        self.assertEqual(resultado.fonte, "sessao.opus")
        self.assertEqual(resultado.duracao_s, 8.0)
        self.assertEqual(resultado.modelo, "small")
        self.assertEqual(resultado.idioma, "pt")
        self.assertEqual(
            resultado.segmentos,
            [motor.Segmento(0.0, 2.5, "Olá, mesa."), motor.Segmento(3.0, 6.0, "Rolem iniciativa.")],
        )

    def test_progresso(self):
        chamadas = []
        duble = ModeloDuble([(0.0, 2.0, "a"), (3.0, 5.0, "b")])
        transcrever(duble, duracao=8.0, progresso=lambda atual, total: chamadas.append((atual, total)))
        self.assertEqual(chamadas, [(2.0, 8.0), (5.0, 8.0), (8.0, 8.0)])


class ModeloComLoop(ModeloDuble):
    """Com hotwords entra em loop no 2º segmento; sem hotwords transcreve certo."""

    def __init__(self):
        super().__init__()
        self.chamadas = []

    def transcribe(self, audio, **opcoes):
        self.chamadas.append((len(audio), opcoes))
        if "hotwords" in opcoes:
            self.segmentos = [(0.0, 4.0, "A call dá direito de compra."),
                              (5.0, 9.0, "Call, put, strike, notional, delta."),
                              (10.0, 14.0, "Fim da aula.")]
        else:
            self.segmentos = [(0.3, 3.8, "O notional é quantidade vezes strike.")]
        return super().transcribe(audio, **opcoes)


class TestLoopComTermos(unittest.TestCase):
    def test_refaz_so_o_trecho_suspeito_sem_os_termos(self):
        duble = ModeloComLoop()
        r = transcrever(duble, duracao=15.0, hotwords="call, put, strike, notional, delta")
        self.assertEqual(len(duble.chamadas), 2)
        tamanho, opcoes = duble.chamadas[1]
        self.assertNotIn("hotwords", opcoes)
        self.assertIs(opcoes["vad_filter"], True)
        self.assertEqual(tamanho, int(5.0 * 16000))  # de 4.5 s a 9.5 s: folga sem invadir vizinhos
        self.assertEqual([s.texto for s in r.segmentos],
                         ["A call dá direito de compra.", "O notional é quantidade vezes strike.", "Fim da aula."])
        self.assertAlmostEqual(r.segmentos[1].inicio, 4.8)  # horário deslocado para o vídeo
        self.assertEqual(r.refeitos, [{"inicio": 4.5, "fim": 9.5, "motivo": "eco da lista de termos",
                                       "antes": "Call, put, strike, notional, delta."}])

    def test_sem_termos_nao_procura_loop(self):
        duble = ModeloDuble([(0, 1, "a a a a")])
        r = transcrever(duble)
        self.assertEqual(r.refeitos, [])

    def test_avisa_lista_longa_demais(self):
        class Tokenizador:
            def encode(self, texto):
                return type("E", (), {"ids": texto.split()})()

        duble = ModeloDuble()
        duble.hf_tokenizer = Tokenizador()
        r = transcrever(duble, hotwords=", ".join(["termo"] * 300))
        self.assertTrue(any("tokens" in a for a in r.avisos))


class TestTermos(unittest.TestCase):
    def test_um_por_linha_ignorando_vazios_e_comentarios(self):
        conteudo = "# nomes da campanha\nNhalor\n\n  Vorric  \nElijah Vorren # NPC\n"
        self.assertEqual(motor.ler_termos(conteudo), "Nhalor, Vorric, Elijah Vorren")


class TestCombinarTermos(unittest.TestCase):
    def test_junta_na_ordem_e_sem_repetir_termo(self):
        a = "# tech\nIA\nClaude\n"
        b = "mano\nclaude  # repetido, minúscula\nIA\ntá ligado\n"
        self.assertEqual(motor.combinar_termos([a, b]), "IA, Claude, mano, tá ligado")

    def test_um_arquivo_so_e_igual_a_ler_termos(self):
        conteudo = "# nomes\nNhalor\nVorric\n"
        self.assertEqual(motor.combinar_termos([conteudo]), motor.ler_termos(conteudo))

    def test_nada_vira_string_vazia(self):
        self.assertEqual(motor.combinar_termos([]), "")
        self.assertEqual(motor.combinar_termos(["# só comentário\n"]), "")

    def test_a_soma_das_listas_e_avisada_quando_passa_do_limite(self):
        class Tokenizador:
            def encode(self, texto):
                return type("E", (), {"ids": texto.split()})()

        a = "\n".join(f"alfa{i}" for i in range(120))
        b = "\n".join(f"beta{i}" for i in range(120))
        for lista in (a, b):  # cada uma sozinha cabe
            duble = ModeloDuble()
            duble.hf_tokenizer = Tokenizador()
            self.assertEqual(transcrever(duble, hotwords=motor.combinar_termos([lista])).avisos, [])
        duble = ModeloDuble()
        duble.hf_tokenizer = Tokenizador()
        r = transcrever(duble, hotwords=motor.combinar_termos([a, b]))  # juntas passam de 223
        self.assertTrue(any("tokens" in aviso for aviso in r.avisos))


class TestListasDeTermos(unittest.TestCase):
    PASTA = Path(__file__).resolve().parents[2] / "termos"  # termos/ fica na raiz do repositório
    # Sem o tokenizador do Whisper aqui, o teste usa uma estimativa pessimista
    # (2 caracteres por token; em português costuma dar 2,5 a 3,5): a lista
    # sozinha tem que caber nos ~223 tokens que o Whisper usa.
    MAX_CARACTERES = 223 * 2

    def listas(self):
        return sorted(self.PASTA.glob("*.txt"))

    def test_as_listas_novas_existem_e_carregam(self):
        for nome in ("tecnologia-ia", "girias-brasil", "mercado-financeiro"):
            termos = motor.ler_termos((self.PASTA / f"{nome}.txt").read_text(encoding="utf-8"))
            self.assertTrue(termos, nome)

    def test_termos_pedidos_estao_nas_listas(self):
        tecnologia = motor.ler_termos((self.PASTA / "tecnologia-ia.txt").read_text(encoding="utf-8")).split(", ")
        for termo in ("IA", "Claude", "Claude Code", "ChatGPT", "LLM", "prompt", "API", "GitHub", "Python",
                      "TikTok", "TCC", "Libras", "capacitação"):
            self.assertIn(termo, tecnologia)
        girias = motor.ler_termos((self.PASTA / "girias-brasil.txt").read_text(encoding="utf-8")).split(", ")
        for termo in ("mano", "tipo", "sacou", "tá ligado", "de boa", "grana", "rolê", "paia"):
            self.assertIn(termo, girias)

    def test_cada_lista_cabe_no_limite_do_whisper_pela_estimativa_pessimista(self):
        for arquivo in self.listas():
            termos = motor.ler_termos(arquivo.read_text(encoding="utf-8"))
            self.assertLessEqual(len(termos), self.MAX_CARACTERES, arquivo.name)

    def test_sem_termo_repetido_dentro_da_lista(self):
        for arquivo in self.listas():
            termos = [t.lower() for t in motor.ler_termos(arquivo.read_text(encoding="utf-8")).split(", ")]
            self.assertEqual(len(termos), len(set(termos)), arquivo.name)


class TestCarregamentoPreguicoso(unittest.TestCase):
    def test_reaproveita_modelo_ja_carregado(self):
        sentinela = object()
        motor._MODELOS["dublê"] = sentinela
        try:
            self.assertIs(motor.carregar_modelo("dublê"), sentinela)
        finally:
            del motor._MODELOS["dublê"]


if __name__ == "__main__":
    unittest.main()
