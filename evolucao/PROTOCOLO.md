# Protocolo do loop de evolução da Vatty

Regras que não mudam (o Marcelo definiu):

1. **Só na nuvem.** Nada no PC dele, nenhuma ferramenta de dispositivo.
2. **Só arquivos novos.** Código existente não é alterado. Cada funcionalidade
   é um módulo novo em `vatty/` mais um teste novo em `tests/`. Nada é ligado
   na `cli.py`: cada módulo roda sozinho com `python -m vatty.<modulo>`.
3. **Sem dano.** Nunca dar merge, nunca mexer na `main`, nunca apagar nada que
   não seja criado neste branch, nunca apagar histórico.
4. **Testes unitários com dublês.** `unittest`, sem rede, sem modelo, sem
   ffmpeg, sem yt-dlp reais. A suíte inteira precisa ficar verde.
5. **Regras do projeto valem:** nenhuma chamada de LLM no pacote; só vira
   agente o que exige julgamento (agente proposto fica em
   `evolucao/agentes-propostos/`, não em `.claude/agents/`); parâmetros do
   Whisper provados não mudam; português, sem travessão.
6. **Honestidade.** O que depende de áudio ou vídeo real fica marcado como
   "não verificado" no LOG. Fonte da pesquisa é registrada.

## Uma iteração

1. Ler `evolucao/BACKLOG.md` e o fim do `evolucao/LOG.md`.
2. Pegar o próximo item `[ ]`. Se o backlog acabou, pesquisar na web (no máximo
   2 buscas) ferramentas parecidas e acrescentar ideias novas, com a fonte.
3. Escrever o módulo novo e o teste novo.
4. Rodar `python -m unittest discover -s tests`. Verde: seguir. Vermelho:
   corrigir no próprio módulo novo; se não resolver, desistir do item e anotar.
5. Commit com a mensagem no padrão do projeto e `git push` neste branch.
6. Marcar o item `[x]` no BACKLOG e registrar no LOG (o que fez, testes, o que
   não foi verificado, fonte).
7. Atualizar `evolucao/RELATORIO.md` (resumo para quem acorda: o que existe,
   como usar, o que não foi verificado) e mandar ao Marcelo **uma mensagem curta**
   com `SendUserMessage`: o que saiu, número de testes, link do PR.
8. Agendar a próxima iteração.

## Quando parar sozinha

- Duas iterações seguidas com a suíte vermelha.
- O Marcelo pedir para parar.
- Backlog vazio e nenhuma ideia nova que passe nas regras acima.
