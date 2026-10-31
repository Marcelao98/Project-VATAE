"""
`vatty verificar`: confere cada peça de que a Vatty precisa neste computador e monta o plano para instalar
o que falta. Com `--instalar`, instala sozinho o que é do Python (pip no próprio ambiente) e, para o que é do
sistema, mostra o comando (com `sudo` no Linux) e só roda depois de a pessoa confirmar.

Lógica pura: o sistema, a busca de programas e a execução de comandos entram por parâmetro (o teste troca).
"""

import importlib.util
import os
import platform
import shutil
import subprocess
import sys

from .ui import saude

ESSENCIAL = saude.ESSENCIAL
OPCIONAL = saude.OPCIONAL

# Pacotes do sistema por peça. Só o que um gerenciador de pacotes resolve; o resto vai como texto de ajuda.
PACOTES = {
    "dnf": {
        "ffmpeg": ["ffmpeg"],
        "js": ["nodejs"],
        "tesseract": ["tesseract", "tesseract-langpack-por"],
        "tesseract-por": ["tesseract-langpack-por"],
        "gstreamer": ["gstreamer1-plugins-good", "gstreamer1-plugins-bad-free", "pipewire-gstreamer"],
        "codificador": ["gstreamer1-plugin-openh264", "openh264"],
        "pactl": ["pulseaudio-utils"],
    },
    "apt": {
        "ffmpeg": ["ffmpeg"],
        "js": ["nodejs"],
        "tesseract": ["tesseract-ocr", "tesseract-ocr-por"],
        "tesseract-por": ["tesseract-ocr-por"],
        "gstreamer": ["gstreamer1.0-plugins-good", "gstreamer1.0-plugins-bad", "gstreamer1.0-pipewire"],
        "codificador": ["gstreamer1.0-plugins-ugly"],
        "pactl": ["pulseaudio-utils"],
    },
    "winget": {
        "ffmpeg": ["Gyan.FFmpeg"],
        "js": ["DenoLand.Deno"],
        "tesseract": ["UB-Mannheim.TesseractOCR"],
    },
}

# Pacotes do pip por peça (instalados no Python que está rodando a Vatty).
PIP = {
    "yt-dlp": ["yt-dlp[default,curl-cffi]"],
    "falantes": ["sherpa-onnx"],
    "ata": ["python-docx", "reportlab"],
    "portal": ["jeepney"],
    "som-windows": ["pyaudiowpatch"],
}

# O teste do codificador grava um quadro de verdade: o `noopenh264` do Fedora é uma casca, o `openh264enc`
# existe e falha ao gravar.
_TESTE_CODIFICADOR = "videotestsrc num-buffers=1 ! videoconvert ! {} ! h264parse ! fakesink"
CODIFICADORES = ("x264enc", "openh264enc")


def descobrir_sistema(ler=lambda caminho: open(caminho, encoding="utf-8").read(), ambiente=None) -> dict:
    """{so: linux/windows/mac, distro, versao, sessao, gerenciador: dnf/apt/winget/None}."""
    ambiente = os.environ if ambiente is None else ambiente
    so = {"Linux": "linux", "Windows": "windows", "Darwin": "mac"}.get(platform.system(), platform.system().lower())
    info = {"so": so, "distro": "", "versao": "", "sessao": "", "gerenciador": None}
    if so == "windows":
        info["gerenciador"] = "winget"
    elif so == "linux":
        try:
            campos = dict(linha.split("=", 1) for linha in ler("/etc/os-release").splitlines() if "=" in linha)
        except OSError:
            campos = {}
        limpar = lambda v: v.strip().strip('"')
        info["distro"] = limpar(campos.get("ID", ""))
        info["versao"] = limpar(campos.get("VERSION_ID", ""))
        familia = {info["distro"], *limpar(campos.get("ID_LIKE", "")).split()}
        info["gerenciador"] = "dnf" if familia & {"fedora", "rhel"} else "apt" if familia & {"debian", "ubuntu"} else None
        info["sessao"] = ambiente.get("XDG_SESSION_TYPE", "")
    return info


def _rodar(cmd, entrada=None) -> tuple:
    """(código, saída). Programa que não existe dá código 127, nunca exceção."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, input=entrada)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def _tem_modulo(nome: str) -> bool:
    try:
        return importlib.util.find_spec(nome) is not None
    except (ImportError, ValueError):
        return False


def checar(sistema: dict, procurar=shutil.which, tem_modulo=_tem_modulo, rodar=_rodar,
           modelo_em_cache=saude._modelo_em_cache) -> list:
    """As peças de `ui/saude.py` mais as que dependem do sistema: [{id, nome, ok, nivel, ajuda}]."""
    itens = saude.checar(procurar=procurar, tem_modulo=tem_modulo, modelo_em_cache=modelo_em_cache)
    tess = next(i for i in itens if i["id"] == "tesseract")
    if tess["ok"]:
        _, langs = rodar(["tesseract", "--list-langs"])
        if "por" not in langs.split():
            itens.insert(itens.index(tess) + 1, {
                "id": "tesseract-por", "nome": "Tesseract em português", "ok": False, "nivel": OPCIONAL,
                "ajuda": "O Tesseract está instalado, mas sem o idioma português (por)."})

    novos = []
    if sistema["so"] == "windows":
        novos.append(("som-windows", "Gravar o som do PC (PyAudioWPatch)", tem_modulo("pyaudiowpatch"), OPCIONAL,
                      "Só para `vatty gravar`. Rode: pip install pyaudiowpatch"))
    elif sistema["so"] == "linux":
        novos.append(("pactl", "Escolher o som do PC (pactl)", bool(procurar("pactl")), OPCIONAL,
                      "Sem ele a gravação usa as fontes padrão do PipeWire, que em geral funcionam."))
        if sistema["sessao"] != "x11":
            tem_gst = bool(procurar("gst-launch-1.0")) and rodar(["gst-inspect-1.0", "pipewiresrc"])[0] == 0
            novos.append(("gstreamer", "Gravar a tela no Wayland (GStreamer + PipeWire)", tem_gst, OPCIONAL,
                          "Só para gravar a tela no Wayland."))
            novos.append(("portal", "Pedir a tela ao sistema (jeepney)", tem_modulo("jeepney"), OPCIONAL,
                          'Só para gravar a tela no Wayland. Rode: pip install -e ".[gravacao]"'))
            if tem_gst:
                ok = any(rodar(["gst-launch-1.0", "-q", *_TESTE_CODIFICADOR.format(c).split()])[0] == 0
                         for c in CODIFICADORES)
                novos.append(("codificador", "Codificador de vídeo (x264enc ou openh264enc)", ok, OPCIONAL,
                              "Só para gravar a tela no Wayland. No Fedora, a OpenH264 que vem é uma casca: "
                              "troque pela da Cisco."))
    itens += [{"id": i, "nome": n, "ok": ok, "nivel": nv, "ajuda": a} for i, n, ok, nv, a in novos]
    return itens


def plano(itens: list, sistema: dict, python: str = sys.executable) -> dict:
    """O que fazer para o que falta: {pip: [cmd], sistema: [cmd], manual: [item]}. Cada cmd é uma lista."""
    faltam = [i for i in itens if not i["ok"]]
    ger = sistema.get("gerenciador")
    tabela = PACOTES.get(ger, {})

    pip = [p for i in faltam for p in PIP.get(i["id"], [])]
    pacotes, manual = [], []
    for i in faltam:
        if i["id"] in PIP:
            continue
        if i["id"] in tabela:
            pacotes += [p for p in tabela[i["id"]] if p not in pacotes]
        else:
            manual.append(i)

    cmds_sistema = []
    ids = {i["id"] for i in faltam}
    if ger == "dnf":
        # O ffmpeg do Fedora (ffmpeg-free) não tem tudo: o completo vem do RPM Fusion.
        if "ffmpeg" in ids and sistema.get("distro") == "fedora" and sistema.get("versao"):
            cmds_sistema.append(["sudo", "dnf", "install", "-y",
                                 "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-"
                                 f"{sistema['versao']}.noarch.rpm"])
        if pacotes:
            extra = ["--allowerasing"] if {"ffmpeg", "codificador"} & ids else []
            repo = ["--enablerepo=fedora-cisco-openh264"] if "codificador" in ids else []
            cmds_sistema.append(["sudo", "dnf", "install", "-y", *extra, *repo, *pacotes])
    elif ger == "apt" and pacotes:
        cmds_sistema.append(["sudo", "apt", "install", "-y", *pacotes])
    elif ger == "winget":
        cmds_sistema += [["winget", "install", "-e", "--id", p] for p in pacotes]
    elif pacotes:
        manual += [i for i in faltam if i["id"] in tabela]

    return {"pip": [[python, "-m", "pip", "install", "-U", *pip]] if pip else [],
            "sistema": cmds_sistema, "manual": manual}


def mostrar(itens: list, saida=print) -> None:
    for i in itens:
        marca = "ok   " if i["ok"] else ("FALTA" if i["nivel"] == ESSENCIAL else "falta")
        saida(f"  {marca}  {i['nome']}")


def instalar(p: dict, confirmar, rodar_visivel=subprocess.call, saida=print) -> int:
    """Roda o plano: pip direto, sistema só com confirmação. Devolve quantos comandos falharam."""
    falhas = 0
    for cmd in p["pip"]:
        saida("\n$ " + " ".join(cmd))
        falhas += rodar_visivel(cmd) != 0
    if p["sistema"]:
        saida("\nPara o resto preciso do gerenciador de pacotes do sistema:")
        for cmd in p["sistema"]:
            saida("  " + " ".join(cmd))
        if confirmar("Rodar agora? (o sudo pede a sua senha) [s/N] "):
            for cmd in p["sistema"]:
                saida("\n$ " + " ".join(cmd))
                falhas += rodar_visivel(cmd) != 0
        else:
            saida("Tudo bem: rode os comandos acima quando quiser e depois `vatty verificar` de novo.")
    return falhas


def main(argv=None, sistema=None, checar_=checar, confirmar=None, rodar_visivel=subprocess.call, saida=print) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="vatty verificar",
                                description="Confere o que a Vatty precisa neste computador e instala o que falta.")
    p.add_argument("--instalar", action="store_true",
                   help="instala o que falta (o do Python direto; o do sistema depois de você confirmar)")
    p.add_argument("--curto", action="store_true", help="só mostra o que falta (é o que o abrir-vatty.sh usa)")
    args = p.parse_args(argv)
    sistema = descobrir_sistema() if sistema is None else sistema

    itens = checar_(sistema)
    faltam = [i for i in itens if not i["ok"]]
    if args.curto:
        if faltam:
            saida("Aviso, falta instalar (`vatty verificar --instalar` resolve):")
            mostrar(faltam, saida)
        return 1 if saude.faltando_essencial(itens) else 0

    descricao = " ".join(x for x in (sistema.get("distro") or sistema["so"], sistema.get("versao"),
                                     sistema.get("sessao")) if x)
    saida(f"Conferindo a Vatty ({descricao}):")
    mostrar(itens, saida)
    if not faltam:
        saida("\nTudo certo.")
        return 0

    pl = plano(itens, sistema)
    if not args.instalar:
        saida("\nPara instalar o que falta:")
        for cmd in pl["pip"] + pl["sistema"]:
            saida("  " + " ".join(cmd))
        for i in pl["manual"]:
            saida(f"  {i['nome']}: {i['ajuda']}")
        saida("\nOu rode `vatty verificar --instalar` e eu instalo.")
        return 1 if saude.faltando_essencial(itens) else 0

    if confirmar is None:
        def confirmar(pergunta):
            if not sys.stdin.isatty():
                return False
            try:
                return input(pergunta).strip().lower() in ("s", "sim", "y", "yes")
            except EOFError:
                return False
    falhas = instalar(pl, confirmar, rodar_visivel, saida)
    for i in pl["manual"]:
        saida(f"\nFica com você: {i['nome']}. {i['ajuda']}")

    itens = checar_(sistema)
    saida("\nDepois de instalar:")
    mostrar(itens, saida)
    return 1 if falhas or saude.faltando_essencial(itens) else 0
