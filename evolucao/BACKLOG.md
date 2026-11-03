# Backlog (ideias da conversa de 11/10/2026)

Conferido em 03/11/2026: o que já existe está marcado, com o lugar onde ficou.

Todas são lógica pura, testável com dublês, em módulos novos.

- [x] `buscar`: achar um termo em todas as pastas de `transcricoes/`, com horário e link
- [x] `srt`: transcricao.json -> legenda `.srt` (`vatty/srt.py`; o painel exporta .srt e .vtt)
- [ ] `capitulos`: dividir a transcrição pelos capítulos do `fonte.json`
- [ ] `obsidian`: exportar a pasta do vídeo para `.md` com frontmatter
- [ ] `estimativa`: tempo de Whisper e tamanho em tokens antes de rodar
- [x] `fila`: ler um arquivo de URLs e controlar o que já foi feito (retomar) (`vatty/lote.py`)
- [~] `correcoes`: em parte, pela revisão do painel e o `glossario.txt` (correção feita por pessoa, não por agente)
- [x] `painel`: virou o `vatty ui` (biblioteca, leitor com horário clicável e busca), não um `index.html` por pasta
- [ ] `metricas`: normalizar views, likes, hashtags do yt-dlp para o `fonte.json` de short
- [x] `alucinacao`: virou os trechos duvidosos (`vatty/duvidoso.py`), em todos os canais; limites ainda não calibrados com áudio real
- [x] `flashcards`: agente Cartas + `vatty/cartoes.py` (CSV que o Anki importa)
