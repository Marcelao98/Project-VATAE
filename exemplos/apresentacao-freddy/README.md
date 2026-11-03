# Exemplo: apresentação do Freddy (03/11/2026)

A gravação de 03/11 (o Marcelo mostrando o Freddy, o som da mesa de RPG) virou estas versões. É a referência de
nível para as apresentações da Vatty: o visual "player" (cada slide é uma faixa, a barra de baixo mostra onde no
vídeo aquilo foi dito), nas cores do assunto, seguindo o que a pessoa falou na gravação.

| Arquivo | O que é | No git? |
|---|---|---|
| `roteiro-apresentador.md` | o roteiro que o Apresentador escreveu (`marca:`, `capa:`, `cores:`, `esconder:`, `> pedido`) | sim |
| `modelo-player.html` | o HTML feito à mão, com `{{imagem}}` no lugar das imagens: a base do visual novo | sim |
| `Freddy-post.html` + `gerar-post.py` | versão para rede social que só aceita HTML estático (sem script, estilo inline, imagem por https) | sim |
| `Freddy-apresentacao.html` / `.md` | o deck com as imagens embutidas (e o mesmo dentro de um `.md`, para copiar) | não (prints) |
| `Freddy-apresentacao.pdf` / `.pptx` | o deck em PDF e PowerPoint, feitos de prints do HTML no Chrome | não (grandes) |
| `vatty-pptx-editavel.pptx` | o .pptx que a Vatty montava antes (python-pptx), para comparar | não |

O que a pessoa pediu na gravação e como foi cumprido está nas linhas `> pedido` do roteiro. Ponto de atenção que
gerou o `esconder:`: a fala "não deixa aparecer sobre o ringue" era o Subahibi (Subarashiki Hibi), não o Elden Ring.

## Gerado pela própria Vatty (0.20.2)

`vatty-gerado.html`, `.pdf` e `.pptx` saíram de `vatty apresentacao <pasta> --formato html pdf pptx` com o `roteiro-apresentador.md`: é o visual novo, sem nada feito à mão. Fora do git (têm os prints).
