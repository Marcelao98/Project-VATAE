"""
Gravação da tela no Linux com Wayland (Fedora, Ubuntu recentes): pelo portal do sistema.

No Wayland nenhum programa pode capturar a tela por conta própria: quem libera é o portal
(xdg-desktop-portal), que mostra a janela "Compartilhar a tela?" do GNOME/KDE. O caminho é:

1. falar com o portal pelo D-Bus (`jeepney`, Python puro): CreateSession, SelectSources, Start;
2. o portal devolve um "nó" do PipeWire com a imagem da tela e um descritor de arquivo para abri-lo;
3. o GStreamer (`gst-launch-1.0`, `pipewiresrc`) grava esse nó em `tela.mp4`.

O portal devolve também um `restore_token`, guardado em ~/.vatty/portal-tela.txt: com ele, nas
próximas vezes o sistema não pergunta de novo. Sem nada de terminal nem de rede.

Como a captura da tela do Windows, a parte real (D-Bus, PipeWire) não tem teste automático: só os
comandos e as escolhas, que são puros. A prova fica em `docs/testes-reais.md`.
"""

import os
import secrets
import shutil
import signal
import subprocess
import time
from pathlib import Path

FPS = 10
TOKEN = Path.home() / ".vatty" / "portal-tela.txt"
ESPERA_PORTAL_S = 120     # a pessoa precisa clicar em "Compartilhar"
ESPERA_FIM_S = 15
CODIFICADORES = ("x264enc", "openh264enc")   # x264: RPM Fusion; openh264: o do Fedora (repositório da Cisco)


class ErroPortal(Exception):
    """Falha ao começar a gravar a tela pelo portal (mensagem para o usuário)."""


def caminho_pedido(nome_unico: str, token: str) -> str:
    """Onde o portal responde a um pedido: /org/freedesktop/portal/desktop/request/<remetente>/<token>."""
    remetente = nome_unico.lstrip(":").replace(".", "_")
    return f"/org/freedesktop/portal/desktop/request/{remetente}/{token}"


def escolher_codificador(funciona) -> str | None:
    """O primeiro codificador H.264 que funciona no GStreamer (`funciona(nome) -> bool`)."""
    return next((c for c in CODIFICADORES if funciona(c)), None)


def comando_gst(exe: str, fd: int, no: int, saida, codificador: str, fps: int = FPS) -> list:
    """gst-launch gravando o nó do PipeWire em mp4 fragmentado (legível mesmo se cair no meio)."""
    cod = {"x264enc": ["x264enc", "tune=zerolatency", "speed-preset=ultrafast", f"key-int-max={fps * 2}"],
           "openh264enc": ["openh264enc", "complexity=low"]}[codificador]
    return [exe, "-e", "-q",
            "pipewiresrc", f"fd={fd}", f"path={no}", "do-timestamp=true", "keepalive-time=1000", "!",
            "videoconvert", "!", "videorate", "!", f"video/x-raw,framerate={fps}/1,format=I420", "!",
            *cod, "!", "h264parse", "!", "mp4mux", "fragment-duration=1000", "!",
            "filesink", f"location={saida}"]


def _codificador_funciona(nome: str, executar=subprocess.run) -> bool:
    """Codifica um quadro de teste: só existir não basta (o `noopenh264` do Fedora tem o elemento e falha)."""
    exe = shutil.which("gst-launch-1.0")
    if not exe:
        return False
    try:
        cmd = [exe, "-q", "videotestsrc", "num-buffers=1", "!", nome, "!", "fakesink"]
        return executar(cmd, capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class _Portal:
    """A conversa com o portal ScreenCast pelo D-Bus da sessão."""

    def __init__(self):
        try:
            from jeepney import DBusAddress, MatchRule, message_bus, new_method_call  # noqa: F401
            from jeepney.io.blocking import Proxy, open_dbus_connection
        except ImportError:
            raise ErroPortal('falta a biblioteca do portal: pip install -e ".[gravacao]" (instala o jeepney).') from None
        self._j = __import__("jeepney")
        self._Proxy = Proxy
        try:
            self.conexao = open_dbus_connection(bus="SESSION", enable_fds=True)
        except Exception as e:
            raise ErroPortal(f"não achei o D-Bus da sessão (está numa sessão gráfica?): {e}") from e
        self._portal = DBusAddress("/org/freedesktop/portal/desktop", bus_name="org.freedesktop.portal.Desktop",
                                   interface="org.freedesktop.portal.ScreenCast")

    def _pedir(self, metodo: str, assinatura: str, corpo: tuple, opcoes: dict) -> dict:
        """Chama um método que responde pelo sinal Response e devolve os resultados (variantes já abertas)."""
        token = "vatty" + secrets.token_hex(6)
        regra = self._j.MatchRule(type="signal", interface="org.freedesktop.portal.Request", member="Response",
                                  path=caminho_pedido(self.conexao.unique_name, token))
        self._Proxy(self._j.message_bus, self.conexao).AddMatch(regra)
        with self.conexao.filter(regra) as fila:
            opcoes = {**opcoes, "handle_token": ("s", token)}
            self.conexao.send_and_get_reply(self._j.new_method_call(self._portal, metodo, assinatura, (*corpo, opcoes)))
            resposta = self.conexao.recv_until_filtered(fila, timeout=ESPERA_PORTAL_S)
        codigo, resultados = resposta.body
        if codigo == 1:
            raise ErroPortal("o compartilhamento da tela foi cancelado na janela do sistema.")
        if codigo != 0:
            raise ErroPortal(f"o portal recusou {metodo} (código {codigo}).")
        return {k: v[1] for k, v in resultados.items()}

    def abrir(self, token_salvo: str | None) -> tuple:
        """Pede a tela inteira. Devolve (descritor do PipeWire, nó, novo restore_token)."""
        sessao = self._pedir("CreateSession", "a{sv}", (), {"session_handle_token": ("s", "vatty" + secrets.token_hex(4))})
        caminho = sessao["session_handle"]
        fontes = {"types": ("u", 1), "multiple": ("b", False), "cursor_mode": ("u", 2), "persist_mode": ("u", 2)}
        if token_salvo:
            fontes["restore_token"] = ("s", token_salvo)
        self._pedir("SelectSources", "oa{sv}", (caminho,), fontes)
        inicio = self._pedir("Start", "osa{sv}", (caminho, ""), {})
        fluxos = inicio.get("streams") or []
        if not fluxos:
            raise ErroPortal("o portal não devolveu nenhuma tela.")
        resposta = self.conexao.send_and_get_reply(
            self._j.new_method_call(self._portal, "OpenPipeWireRemote", "oa{sv}", (caminho, {})))
        fd = resposta.body[0].to_raw_fd()
        return fd, fluxos[0][0], inicio.get("restore_token")

    def fechar(self) -> None:
        try:
            self.conexao.close()  # fechar a conexão encerra a sessão do portal
        except Exception:
            pass


class CapturaPortal:
    """Mesma cara do `tela.CapturaTela`: abre já gravando; `parar()` fecha o arquivo."""

    def __init__(self, saida, *, fps: int | None = None, agora=time.time, portal=None):
        self.saida = Path(saida)
        self.fps = fps or FPS
        self.motor = "portal"
        self.aviso = None
        exe = shutil.which("gst-launch-1.0")
        if not exe:
            raise ErroPortal("falta o GStreamer (Fedora: sudo dnf install gstreamer1-plugins-good pipewire-gstreamer).")
        codificador = escolher_codificador(_codificador_funciona)
        if not codificador:
            raise ErroPortal("o GStreamer não tem codificador H.264 que funcione (Fedora: sudo dnf install "
                             "gstreamer1-plugin-openh264 e sudo dnf swap noopenh264 openh264 "
                             "--enablerepo=fedora-cisco-openh264, ou o gstreamer1-plugins-ugly do RPM Fusion).")
        self._portal = portal or _Portal()
        token = TOKEN.read_text(encoding="utf-8").strip() if TOKEN.is_file() else None
        fd, no, novo_token = self._portal.abrir(token)
        if novo_token:
            TOKEN.parent.mkdir(parents=True, exist_ok=True)
            TOKEN.write_text(novo_token, encoding="utf-8")
        aberto_em = agora()
        self._proc = subprocess.Popen(comando_gst(exe, fd, no, self.saida, codificador, self.fps), pass_fds=(fd,),
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                      start_new_session=True)  # o Ctrl+C da gravação não derruba antes de fechar o arquivo
        os.close(fd)
        time.sleep(1.0)
        if self._proc.poll() is not None:
            erro = self._proc.stderr.read().decode("utf-8", errors="replace").strip()
            self._portal.fechar()
            raise ErroPortal(f"o GStreamer não começou a gravar: {erro or 'fechou sem dizer por quê'}")
        # o GStreamer não informa o primeiro quadro como o ffmpeg: o horário é o de quando abriu
        self.inicio, self.inicio_aproximado = aberto_em, True

    def parar(self) -> bool:
        """SIGINT com -e: o GStreamer manda fim de fluxo e fecha o mp4 direito."""
        ate_o_fim = self._proc.poll() is None
        if ate_o_fim:
            self._proc.send_signal(signal.SIGINT)
            try:
                self._proc.wait(timeout=ESPERA_FIM_S)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
        self._portal.fechar()
        return ate_o_fim
