# Relatório da evolução da Vatty

Branch `vatty-evolucao`, PR #4 (rascunho). Só arquivos novos, nada ligado na CLI.
Atualizado a cada iteração. Detalhes e fontes em `LOG.md`.

| # | Módulo | O que faz | Como usar | Testes | Verificado em dado real? |
|---|---|---|---|---|---|
| 1 | `buscar` | acha um termo em todas as transcrições, com horário e link | `python -m vatty.buscar "termo" --raiz transcricoes` | 19 | não |

Suíte inteira: 236 testes verdes.

## O que fazer ao acordar

1. Ler este relatório e o PR #4.
2. Testar os módulos no PC com as suas pastas de `transcricoes/`.
3. Decidir o que ligar na CLI (isso exige alterar `cli.py`, então vira outro PR).
