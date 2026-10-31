# Arquitetura da Vatty

## Camadas

```
┌──────────────────────── frontend/ (React + TS + Vite) ────────────────────────┐
│  Nova fonte · Job em andamento · Decisão · Pasta do vídeo · Agentes           │
│  cliente gerado do OpenAPI (tipos iguais aos do Python) · SSE de progresso    │
└──────────────────────────────────┬─────────────────────────────────────────────┘
                                   │ HTTP (JSON) + SSE
┌──────────────────────────────────▼──────────────── backend/ (Python) ─────────┐
│ CASCAS          cli.py (feito) · api/ (FastAPI, a fazer)                       │
│                 implementam o Decisor e o Progresso; não decidem o fluxo       │
├────────────────────────────────────────────────────────────────────────────────┤
│ APLICAÇÃO       aplicacao/pipeline.py  processar(opcoes, decisor, progresso)   │
│                 aplicacao/portas.py    Opcoes · Decisor · Progresso · Erro     │
├──────────────────────────────────────┬─────────────────────────────────────────┤
│ NÚCLEO (lógica pura)                 │ ADAPTADORES (mundo externo)             │
│ legenda · texto · visual · repeticao │ fonte (yt-dlp) · audio/quadros (ffmpeg) │
│ preprocessar (diagnóstico)           │ motor (faster-whisper) · ocr (Tesseract)│
│                                      │ gravacao (WASAPI) · pasta (disco)       │
└──────────────────────────────────────┴─────────────────────────────────────────┘
                                   │ escreve
                     transcricoes/<slug>/   (contrato, com "versao")
                                   │ lê
                     .claude/agents/*.md    (Escrivão, Preceptor)
```

As dependências só apontam para baixo: casca → aplicação → núcleo/adaptadores.
O núcleo não conhece ninguém; o front só conhece a API.

## Plano

| Passo | O quê | Estado |
|---|---|---|
| 1 | Monorepo: `backend/`, `frontend/` | feito |
| 2 | CI (ruff + unittest no 3.12/3.13), `versao` no contrato, Python ≥ 3.12 | feito |
| 3 | `aplicacao/`: pipeline fora da CLI, `Decisor` e `Progresso` | feito |
| 4 | API FastAPI (extra `[api]`): jobs numa thread, decisão por `POST /jobs/{id}/decisao`, progresso por SSE | a fazer |
| 5 | Front React + TS (Vite, TanStack Query, tipos do OpenAPI) | a fazer |
| 6 | Agentes no backend (extra `[agentes]`): API do Claude com os mesmos `.claude/agents/*.md` | a fazer |
| 7 | Desktop: Tauri com o backend como sidecar | a fazer |
| 8 | Nuvem (S3, fila, GPU, login), só se houver demanda | — |

### Decisões

- **Decisão no meio do job (passo 4).** O job roda numa thread; quando o
  pipeline chama o `Decisor`, a API publica a pergunta (trechos da legenda,
  indicadores) e a thread espera a resposta. Simples e suficiente para desktop
  e um servidor pequeno. Com vários workers (passo 8), vira máquina de estados;
  a interface `Decisor` não muda.
- **`vatty gravar`** continua na CLI: a captura depende do dispositivo e do
  Ctrl+C. No desktop vira um adaptador próprio.
- **LLM:** a regra passa a ser "nenhum LLM no núcleo"; o pacote de agentes do
  passo 6 fica separado e opcional.
