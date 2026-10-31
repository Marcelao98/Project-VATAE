import unittest
from unittest import mock

from vatty import cli, verificar

FEDORA = {"so": "linux", "distro": "fedora", "versao": "44", "sessao": "wayland", "gerenciador": "dnf"}


def checar(sistema=FEDORA, faltam=(), codigos=None, langs="eng\npor"):
    """Tudo instalado, menos `faltam` (programas e módulos pelo nome). `codigos`: {programa: código}."""
    codigos = codigos or {}

    def rodar(cmd, entrada=None):
        if cmd[0] == "tesseract":
            return 0, "List of available languages (2):\n" + langs
        return codigos.get(cmd[0], 0), ""

    return verificar.checar(sistema, procurar=lambda n: None if n in faltam else n,
                            tem_modulo=lambda n: n not in faltam, rodar=rodar, modelo_em_cache=lambda: True)


class TestDescobrirSistema(unittest.TestCase):
    def test_fedora_e_ubuntu_pelo_os_release(self):
        with mock.patch("platform.system", return_value="Linux"):
            f = verificar.descobrir_sistema(ler=lambda _: 'ID=fedora\nVERSION_ID=44\n',
                                            ambiente={"XDG_SESSION_TYPE": "wayland"})
            u = verificar.descobrir_sistema(ler=lambda _: 'ID=linuxmint\nID_LIKE="ubuntu debian"\n', ambiente={})
        self.assertEqual((f["gerenciador"], f["versao"], f["sessao"]), ("dnf", "44", "wayland"))
        self.assertEqual(u["gerenciador"], "apt")

    def test_sem_os_release_nao_quebra(self):
        def ler(_):
            raise OSError
        with mock.patch("platform.system", return_value="Linux"):
            info = verificar.descobrir_sistema(ler=ler, ambiente={})
        self.assertIsNone(info["gerenciador"])


class TestChecar(unittest.TestCase):
    def test_wayland_confere_gstreamer_portal_e_codificador(self):
        ids = {i["id"]: i["ok"] for i in checar(codigos={"gst-launch-1.0": 1})}
        self.assertTrue(ids["gstreamer"] and ids["portal"])
        self.assertFalse(ids["codificador"])   # os dois codificadores falharam ao gravar um quadro

    def test_x11_nao_pede_gstreamer(self):
        ids = {i["id"] for i in checar(sistema={**FEDORA, "sessao": "x11"})}
        self.assertNotIn("gstreamer", ids)
        self.assertIn("pactl", ids)

    def test_tesseract_sem_portugues(self):
        item = next(i for i in checar(langs="eng") if i["id"] == "tesseract-por")
        self.assertFalse(item["ok"])


class TestPlano(unittest.TestCase):
    def test_fedora_rpm_fusion_e_um_dnf_so(self):
        itens = checar(faltam=("ffmpeg", "sherpa_onnx"), codigos={"gst-launch-1.0": 1})
        p = verificar.plano(itens, FEDORA, python="py")
        self.assertEqual(p["pip"], [["py", "-m", "pip", "install", "-U", "sherpa-onnx"]])
        self.assertIn("rpmfusion-free-release-44.noarch.rpm", p["sistema"][0][-1])
        dnf = p["sistema"][1]
        self.assertEqual(dnf[:4], ["sudo", "dnf", "install", "-y"])
        self.assertIn("--enablerepo=fedora-cisco-openh264", dnf)
        self.assertIn("ffmpeg", dnf)
        self.assertIn("openh264", dnf)

    def test_distro_desconhecida_vira_manual(self):
        itens = checar(sistema={**FEDORA, "gerenciador": None}, faltam=("tesseract",))
        p = verificar.plano(itens, {**FEDORA, "gerenciador": None})
        self.assertEqual(p["sistema"], [])
        self.assertEqual([i["id"] for i in p["manual"]], ["tesseract"])

    def test_windows_usa_winget_e_pyaudiowpatch(self):
        win = {"so": "windows", "distro": "", "versao": "", "sessao": "", "gerenciador": "winget"}
        p = verificar.plano(checar(sistema=win, faltam=("deno", "node", "pyaudiowpatch")), win, python="py")
        self.assertEqual(p["sistema"], [["winget", "install", "-e", "--id", "DenoLand.Deno"]])
        self.assertIn("pyaudiowpatch", p["pip"][0])


class TestInstalar(unittest.TestCase):
    def test_sem_confirmacao_so_roda_o_pip(self):
        rodados = []
        p = {"pip": [["py", "-m", "pip", "install", "x"]], "sistema": [["sudo", "dnf", "install", "y"]], "manual": []}
        falhas = verificar.instalar(p, confirmar=lambda _: False,
                                    rodar_visivel=lambda c: rodados.append(c) or 0, saida=lambda *_: None)
        self.assertEqual((falhas, rodados), (0, [p["pip"][0]]))


class TestMain(unittest.TestCase):
    def test_curto_mostra_so_o_que_falta_e_essencial_da_erro(self):
        linhas = []
        r = verificar.main(["--curto"], sistema=FEDORA, checar_=lambda s: checar(s, faltam=("ffmpeg",)),
                           saida=linhas.append)
        self.assertEqual(r, 1)
        self.assertEqual(len(linhas), 2)
        self.assertIn("ffmpeg", linhas[1])

    def test_cli_encaminha_verificar(self):
        with mock.patch("vatty.verificar.main", return_value=0) as m:
            self.assertEqual(cli.main(["verificar", "--instalar"]), 0)
        m.assert_called_once_with(["--instalar"])


if __name__ == "__main__":
    unittest.main()
