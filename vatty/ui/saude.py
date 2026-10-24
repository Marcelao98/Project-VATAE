"""
Primeira execução: confere o que a Vatty precisa e diz, em português, o que falta e como resolver.
Cada checagem entra por parâmetro (o teste troca), então nada aqui roda ffmpeg ou baixa modelo de verdade.
"""

import importlib.util
import shutil

ESSENCIAL = "essencial"
OPCIONAL = "opcional"


def _tem_modulo(nome: str) -> bool:
    try:
        return importlib.util.find_spec(nome) is not None
    except (ImportError, ValueError):
        return False


def _modelo_em_cache() -> bool:
    try:
        from .. import motor
        return motor.modelo_em_cache()
    except Exception:
        return False


def checar(procurar=shutil.which, tem_modulo=_tem_modulo, modelo_em_cache=_modelo_em_cache) -> list:
    """[{id, nome, ok, nivel, ajuda}] na ordem em que importa resolver."""
    itens = [
        ("ffmpeg", "ffmpeg", bool(procurar("ffmpeg")), ESSENCIAL,
         "Instale o ffmpeg e deixe no PATH (Windows: winget install Gyan.FFmpeg; Fedora: sudo dnf install ffmpeg, "
         "com o RPM Fusion). Sem ele nenhum áudio é lido."),
        ("modelo", "Modelo de transcrição (Whisper)", bool(modelo_em_cache()), ESSENCIAL,
         "O modelo (cerca de 1,5 GB) baixa sozinho na primeira transcrição. Precisa de internet só nessa vez."),
        ("yt-dlp", "Baixar de links (yt-dlp)", tem_modulo("yt_dlp"), ESSENCIAL,
         "Rode: pip install -U yt-dlp"),
        ("js", "YouTube: Deno (JavaScript)", bool(procurar("deno") or procurar("node")), OPCIONAL,
         "O YouTube exige um runtime de JavaScript para liberar o vídeo; sem ele, bloqueia mais ('prove que não é "
         "robô'). Windows: winget install DenoLand.Deno; Linux: curl -fsSL https://deno.land/install.sh | sh. "
         "Depois abra a Vatty de novo."),
        ("tesseract", "Ler slides (Tesseract)", bool(procurar("tesseract")), OPCIONAL,
         "Só para a opção 'Ler os slides'. Instale o Tesseract com o idioma português."),
        ("falantes", "Separar quem falou (sherpa-onnx)", tem_modulo("sherpa_onnx"), OPCIONAL,
         "Só para 'Descobrir as pessoas'. Rode: pip install sherpa-onnx"),
        ("claude", "Agentes (Claude Code)", bool(procurar("claude")), OPCIONAL,
         "Só para chamar os agentes (pontos-chave, ata, achar bugs...). Gravar e transcrever funcionam sem ele. "
         "Instale o Claude Code e entre com a sua conta."),
        ("ata", "Ata em .docx e .pdf", tem_modulo("docx") and tem_modulo("reportlab"), OPCIONAL,
         "Só para `vatty ata`. Rode: pip install python-docx reportlab"),
    ]
    return [{"id": i, "nome": n, "ok": ok, "nivel": nv, "ajuda": a} for i, n, ok, nv, a in itens]


def faltando_essencial(itens: list) -> list:
    return [i for i in itens if not i["ok"] and i["nivel"] == ESSENCIAL]
