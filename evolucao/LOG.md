# Log do loop

(Cada iteração registra aqui: o que fez, testes, o que não foi verificado, fonte.)

## Iteração 1 (2026-10-12): `buscar`

- Novo: `vatty/buscar.py`, `tests/test_buscar.py` (19 testes). Nada existente foi alterado.
- Uso: `python -m vatty.buscar "termo" --raiz transcricoes` (não está ligado na `cli.py`).
- Acha o termo sem diferenciar maiúscula e acento; um achado por parágrafo; no YouTube, link `&t=`.
- Suíte inteira: 236 testes verdes.
- Não verificado: nunca rodou em `transcricoes/` de verdade (só em pastas de teste).
