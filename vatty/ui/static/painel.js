/* Painel "Começar": gravar áudio, gravar tela e áudio ou puxar do YouTube, e depois só guardar ou
   anotar um pedido para os agentes. Usa as funções de app.js (el, api, post, $, relogio, estado,
   abrirVideo). Texto de fora entra só por textContent. */
"use strict";

const painel = {
  raiz: $("aba-comecar"),
  fonte: "audio",
  passo: 1,
  agentes: [],
  trabalhos: [],     // ids dos trabalhos que este painel começou
  pedido: null,      // o que foi pedido (para o "pronto")
  vigia: null,       // timer que acompanha a gravação
};

const FALAS = {
  1: ["Me diz de onde vem o som.", "Eu gravo o seu PC ou puxo um vídeo do YouTube, escuto tudo aqui mesmo e escrevo com o horário de cada fala."],
  2: ["E depois que eu ouvir?", "Posso só guardar o texto no seu PC, ou chamar os agentes pelo Claude Code: pontos-chave, ata, flashcards, achar bugs..."],
  gravando: ["Ouvido ligado.", "Estou gravando. Avise quem está na conversa. Quando quiser, aperte Parar."],
  parando: ["Guardando o que ouvi...", "Fechando os arquivos da gravação."],
  escrevendo: ["Escrevendo o que ouvi...", "Isso roda no seu PC e pode levar alguns minutos (com agentes, mais um pouco). Pode fechar esta aba: eu continuo."],
  pronto: ["Pronto!", "Guardei tudo na pasta do vídeo."],
  erro: ["Não ouvi direito.", "Alguma coisa deu errado. O motivo está abaixo."],
};
const NOMES_FONTE = { audio: "Gravar áudio", tela: "Gravar tela e áudio", youtube: "Puxar do YouTube" };

function falar(chave) {
  const [titulo, texto] = FALAS[chave];
  $("fala-titulo").textContent = titulo;
  $("fala-texto").textContent = texto;
}
function avisoPainel(msg, erro = false) {
  $("p-aviso").textContent = msg;
  $("p-aviso").className = "dica" + (erro ? " marca" : "");
}

/* ---------- modo, passo e fase ---------- */
function mudarModo(modo) {
  painel.raiz.dataset.modo = modo;
  document.querySelectorAll(".modos button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.modo === modo)));
  try { localStorage.setItem("vatty-modo", modo); } catch (_) { /* sem armazenamento: fica no padrão */ }
  desenharDeck();
}
function irPara(passo) {
  painel.passo = passo;
  painel.raiz.dataset.passo = String(passo);
  document.querySelectorAll(".trilha li").forEach((li) => {
    const p = Number(li.dataset.p);
    li.className = p === passo ? "at" : p < passo ? "feito" : "";
    if (p === passo) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
  });
  if (passo <= 2) falar(passo);
}
function mudarFase(fase) {
  painel.raiz.dataset.fase = fase;
  if (fase === "ouvindo") irPara(3);
  if (fase === "pronto") irPara(4);
}

/* ---------- escolhas ---------- */
function escolherFonte(fonte) {
  painel.fonte = fonte;
  document.querySelectorAll(".fonte").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.fonte === fonte)));
  document.querySelectorAll("[data-detalhe]").forEach((d) => (d.hidden = !d.dataset.detalhe.split(" ").includes(fonte)));
  $("p-comecar").textContent = fonte === "youtube" ? "Puxar e transcrever" : "Começar a gravar";
  $("l-so-gravar").hidden = fonte === "youtube";  // do YouTube não tem o que só gravar
  if (fonte === "youtube" && depois() === "gravar") document.querySelector("input[name=depois][value=guardar]").checked = true;
  atualizarResumo();
  desenharDeck();
}
function depois() { return document.querySelector("input[name=depois]:checked").value; }
function agentesMarcados() { return [...document.querySelectorAll("#p-agentes input:checked")].map((i) => i.value); }
function links() { return $("y-links").value.split(/\r?\n/).map((l) => l.trim()).filter(Boolean); }

function atualizarResumo() {
  const comAgentes = depois() === "agentes";
  $("p-agentes").disabled = !comAgentes;
  $("p-objetivo").disabled = !comAgentes;
  const linhas = [["Fonte", NOMES_FONTE[painel.fonte]]];
  if (painel.fonte !== "youtube") linhas.push(["Microfone", $("g-mic").checked ? "sim" : "não"]);
  if (painel.fonte === "tela") {
    linhas.push(["Grava", $("g-alvo").value === "janela" ? "uma janela" : "a tela inteira"]);
    linhas.push(["Para", $("g-perfil").value === "app" ? "testar um programa" : "aula com slides"]);
  }
  if (painel.fonte === "youtube") linhas.push(["Links", String(links().length)]);
  const nomes = agentesMarcados().map((id) => (painel.agentes.find((a) => a.id === id) || {}).nome).filter(Boolean);
  const semTela = painel.fonte === "audio";
  $("p-slides").disabled = semTela;
  $("p-slides-dica").textContent = semTela ? "Só com tela: escolha \"Gravar tela e áudio\" ou \"Puxar do YouTube\"."
    : "Cada tela no momento em que apareceu, com o que foi dito. Sai um slides.html (e PDF).";
  if ($("p-slides").checked && !semTela) linhas.push(["Slides", "sim, com os prints"]);
  linhas.push(["Depois", comAgentes ? (nomes.join(", ") || "escolha os agentes") : depois() === "gravar" ? "só gravar" : "só guardar"]);
  linhas.push(["Onde fica", "transcricoes/"]);
  $("resumo-pedido").replaceChildren(...linhas.map(([k, v]) => el("div", {}, el("dt", {}, k), el("dd", {}, v))));
  const aviso = painel.fonte === "tela" ? "A tela pode mostrar senha e conversa de outras pessoas: feche o que não deve aparecer. Fica só no seu PC."
    : painel.fonte === "audio" ? "Avise quem estiver na conversa que ela está sendo gravada." : "";
  avisoPainel(aviso);
}

function opcoesTranscricao() {
  const o = { falantes: $("p-falantes").value, lang: $("p-lang").value };
  if ($("p-slides").checked && !$("p-slides").disabled) o.slides = true;
  if (depois() === "gravar") o.so_gravar = true;
  if (painel.fonte === "tela" && $("p-manter-tela").checked) o.manter_tela = true;
  if (depois() === "agentes") { o.agentes = agentesMarcados(); o.objetivo = $("p-objetivo").value.trim(); }
  return o;
}
function validar() {
  if (painel.fonte === "youtube" && !links().length) return "Cole pelo menos um link.";
  if (painel.fonte === "tela" && $("g-alvo").value === "janela" && !$("g-janela").value.trim()) return "Escreva o título exato da janela.";
  if (depois() === "agentes" && !agentesMarcados().length) return "Marque pelo menos um agente, ou escolha só guardar.";
  return "";
}

/* ---------- começar ---------- */
async function comecar() {
  const problema = validar();
  if (problema) {
    avisoPainel(problema, true);
    if (painel.raiz.dataset.modo === "passos") irPara(problema.includes("agente") ? 2 : 1);
    return;
  }
  const opcoes = opcoesTranscricao();
  painel.opcoes = opcoes;
  painel.pedido = { fonte: painel.fonte, agentes: opcoes.agentes || [], objetivo: opcoes.objetivo || "", slides: !!opcoes.slides };
  painel.trabalhos = [];
  try {
    if (painel.fonte === "youtube") {
      if ($("y-legenda").checked) opcoes.texto = "legenda";
      if ($("y-cookies").value) opcoes.cookies = $("y-cookies").value;
      if (opcoes.slides) opcoes.visual = "aula";  // os slides precisam do que a tela mostrou
      const r = await post("trabalhos", { entradas: links(), opcoes });
      painel.trabalhos = r.criados.map((t) => t.id);
      if (r.recusados.length) avisoPainel(r.recusados.map((x) => x.erro).join(" "), true);
      $("y-links").value = "";
      mudarFase("ouvindo");
      falar("escrevendo");
      desenharDeck();
    } else {
      const janela = painel.fonte === "tela" && $("g-alvo").value === "janela" ? $("g-janela").value.trim() : "";
      const r = await post("gravacao", { microfone: $("g-mic").checked, tela: painel.fonte === "tela", janela,
        perfil: $("g-perfil").value, opcoes });
      mostrarGravacao(r);
      vigiarGravacao();
    }
  } catch (e) {
    avisoPainel(e.message, true);
  }
}

/* ---------- gravação ---------- */
function vigiarGravacao() {
  clearInterval(painel.vigia);
  let falhas = 0;
  painel.vigia = setInterval(async () => {
    const r = await api("gravacao").catch((e) => { falhas += 1; if (falhas === 3) avisoPainel(e.message, true); return null; });
    if (!r) {
      if (falhas >= 3) $("deck").replaceChildren(el("p", { class: "marca", role: "alert" }, SEM_CONEXAO));
      return;
    }
    falhas = 0;
    mostrarGravacao(r);
  }, 700);
}
function mostrarGravacao(r) {
  painel.gravacao = r;
  if (r.estado === "gravando" || r.estado === "parando") {
    mudarFase("ouvindo");
    falar(r.estado);
  } else if (r.estado === "pronto") {
    clearInterval(painel.vigia);
    if (r.trabalho && !painel.trabalhos.includes(r.trabalho)) painel.trabalhos = [r.trabalho];
    if (r.trabalho) falar("escrevendo");
  } else if (r.estado === "erro") {
    clearInterval(painel.vigia);
    falar("erro");
  }
  desenharDeck();
  aoMudarFila();
}
async function pararGravacao() {
  try { mostrarGravacao(await post("gravacao/parar")); } catch (e) { avisoPainel(e.message, true); }
}

/* ---------- o deck (gravador / progresso) ---------- */
function desenharDeck() {
  const deck = $("deck");
  const g = painel.gravacao;
  const fase = painel.raiz.dataset.fase;
  const sec = painel.raiz.querySelector("[data-bloco=ouvindo]");
  sec.classList.toggle("gravando", !!g && g.estado === "gravando");

  if (g && (g.estado === "gravando" || g.estado === "parando")) {
    const niveis = Object.entries(g.niveis || {});
    const rotulo = { sistema: ["Som do PC", "outros"], microfone: ["Microfone", "eu"] };
    deck.replaceChildren(
      el("div", { class: "rec" },
        el("div", { class: "bola", "aria-hidden": "true" }, "REC"),
        el("div", {}, el("div", { class: "tempo" }, relogio(g.decorrido)),
          el("div", { class: "estado-rec", role: "status" }, g.estado === "parando" ? "Parando e guardando..." : "Gravando" + (g.tela ? " som e tela" : ""))),
        el("button", { class: "btn btn-principal", onclick: pararGravacao, disabled: g.estado === "parando" },
          painel.opcoes && painel.opcoes.so_gravar ? "Parar e guardar" : "Parar e transcrever")),
      el("div", { class: "faixas" }, ...(niveis.length ? niveis : [["sistema", 0]]).map(([nome, n]) => {
        const [titulo, quem] = rotulo[nome] || [nome, ""];
        return el("div", { class: "faixa" }, el("span", {}, titulo),
          el("div", { class: "medidor", role: "meter", "aria-label": "Nível " + titulo, "aria-valuemin": "0", "aria-valuemax": "100",
            "aria-valuenow": String(Math.round(n * 100)) }, el("i", { style: "--n:" + Math.round(n * 100) + "%" })),
          el("span", { class: "dica" }, quem));
      })),
      el("div", { class: "log" }, ...(g.log || []).filter((l) => !l.includes("Ctrl+C")).slice(-3).map((l) => el("div", {}, l))));
    return;
  }
  if (g && g.estado === "erro" && fase === "ouvindo") {
    deck.replaceChildren(el("p", { class: "marca", role: "alert" }, g.erro || "A gravação falhou."),
      el("div", { class: "log" }, ...(g.log || []).slice(-4).map((l) => el("div", {}, l))),
      el("button", { class: "btn btn-calmo", onclick: novoPedido }, "Tentar de novo"));
    return;
  }
  if (g && g.estado === "pronto" && !g.trabalho && fase !== "escolher") {
    deck.replaceChildren(el("h3", {}, "Gravado"), el("p", {}, "Ficou em " + g.pasta + ", sem transcrever."),
      el("button", { class: "btn btn-calmo", onclick: novoPedido }, "Gravar outra"));
    return;
  }
  if (painel.trabalhos.length && fase !== "escolher") {
    deck.replaceChildren(el("h3", {}, "Escrevendo o que ouvi"), ...painel.trabalhos.map((id) => {
      const t = estado.trabalhos.get(id);
      if (!t) return el("p", { class: "dica" }, "Na fila...");
      return el("div", { class: "trab" }, el("b", {}, nomeCurto(t.entrada)),
        el("small", { class: "dica" }, t.estado === "erro" ? t.erro : t.etapa + (t.progresso ? ", " + t.progresso + "%" : "")),
        el("div", { class: "costura", style: "--p:" + t.progresso + "%" }, el("i")));
    }));
    return;
  }
  // parado (aparece no estúdio): o botão grande de começar
  const youtube = painel.fonte === "youtube";
  deck.replaceChildren(el("div", { class: "rec" },
    el("button", { class: "bola", onclick: comecar, "aria-label": youtube ? "Puxar e transcrever" : "Começar a gravar" }, youtube ? "IR" : "REC"),
    el("div", {}, el("div", { class: "tempo" }, "0:00"),
      el("div", { class: "dica" }, youtube ? "Cole o link e aperte IR." : "Pronta para gravar. " + ($("g-mic").checked ? "Som do PC e microfone." : "Só o som do PC.")))),
    el("p", { class: "dica", id: "deck-aviso" }, $("p-aviso").textContent));
}

/* ---------- pronto ---------- */
function trabalhoDosAgentes(pasta) {  // o mais recente da pista dos agentes para esta pasta
  return [...estado.trabalhos.values()].filter((x) => x.pista === "agentes" && x.entrada === pasta)
    .sort((a, b) => b.criado - a.criado)[0];
}
window.aoMudarFila = function aoMudarFila() {
  if (!painel.trabalhos.length || painel.raiz.dataset.fase === "escolher") return;
  const lista = painel.trabalhos.map((id) => estado.trabalhos.get(id));
  if (lista.every((t) => t && ["pronto", "erro", "cancelado"].includes(t.estado))) {
    // os agentes andam na pista deles: o pronto se redesenha quando eles mudam, sem prender a transcrição
    const marca = lista.map((t) => { const a = t.pasta && trabalhoDosAgentes(t.pasta); return t.estado + (a ? a.estado + a.etapa : ""); }).join("|");
    if (painel.raiz.dataset.fase !== "pronto" || marca !== painel.marcaPronto) {
      painel.marcaPronto = marca;
      mudarFase("pronto");
      falar(lista.some((t) => t.estado === "pronto") ? "pronto" : "erro");
      desenharPronto(lista);
    }
  }
  desenharDeck();
};
function ehBloqueioYoutube(erro) { return /não é robô|not a bot|Sign in to confirm/i.test(erro || ""); }
async function tentarComLogin(entrada, navegador) {
  try {
    const r = await post("trabalhos", { entradas: [entrada], opcoes: { ...(painel.opcoes || {}), cookies: navegador } });
    painel.trabalhos = r.criados.map((t) => t.id);
    mudarFase("ouvindo");
    falar("escrevendo");
    desenharDeck();
  } catch (e) { avisoPainel(e.message, true); }
}

function desenharPronto(lista) {
  const p = painel.pedido || { agentes: [] };
  const partes = lista.map((t) => {
    if (t.estado !== "pronto") {
      const erro = el("p", { class: "marca" }, nomeCurto(t.entrada) + ": " + (t.erro || "não terminou."));
      if (!ehBloqueioYoutube(t.erro)) return erro;
      const nav = el("select", { "aria-label": "Navegador" }, ...[["firefox", "Firefox (o mais garantido)"], ["edge", "Edge"], ["chrome", "Chrome"], ["brave", "Brave"]]
        .map(([v, n]) => el("option", { value: v }, n)));
      return el("div", { class: "trab" }, erro,
        el("p", {}, "O YouTube desconfiou do acesso. Dá para tentar de novo usando o login do seu navegador (é só ler os cookies dele, nada é guardado):"),
        el("div", { class: "linha-btn" }, nav, el("button", { class: "btn btn-principal", onclick: () => tentarComLogin(t.entrada, nav.value) }, "Tentar de novo entrando por ele")));
    }
    const slug = t.pasta.split(/[\\/]/).pop();
    const bloco = el("div", { class: "trab" }, el("b", {}, slug), el("small", { class: "dica" }, "Guardado em " + t.pasta),
      el("div", { class: "linha-btn" }, el("button", { class: "btn btn-principal", onclick: () => abrirVideo(slug) }, "Abrir o texto")));
    if (p.slides) {
      const caixa = el("div", { class: "pedido" }, el("span", { class: "dica" }, "Procurando os slides..."));
      bloco.append(el("h3", { style: "margin-top:14px" }, "Slides com os prints"), caixa);
      api("video/" + encodeURIComponent(slug)).then((v) => {
        const url = (g) => comToken("arquivo/" + encodeURIComponent(slug) + "/" + encodeURIComponent(g));
        const achados = [];
        if (v.gerados.includes("slides.html")) achados.push(el("a", { class: "btn btn-principal", href: url("slides.html"), target: "_blank", rel: "noopener" }, "Abrir os slides"));
        if (v.gerados.includes("slides.pdf")) achados.push(el("a", { class: "btn-mini", href: url("slides.pdf") }, "Baixar em PDF"));
        caixa.replaceChildren(...(achados.length ? achados
          : [el("span", { class: "dica" }, "Não saíram slides: a tela não teve trocas que eu conseguisse ler. Veja o log no Terminal (embaixo).")]));
      }).catch(() => {});
    }
    if (p.agentes.length) {
      const status = el("span", { class: "dica", role: "status" });
      const botoes = p.agentes.map((id) => painel.agentes.find((a) => a.id === id)).filter((a) => a && a.prompt).map((a) =>
        el("button", { class: "btn-mini", onclick: () => copiarPrompt(slug, a, p.objetivo, status) }, "Copiar prompt: " + a.faz));
      const arquivos = el("div", { class: "pedido" });
      const aj = trabalhoDosAgentes(t.pasta);
      const andamento = !aj ? null
        : ["fila", "rodando"].includes(aj.estado) ? el("p", { class: "dica", role: "status" }, "Os agentes estão trabalhando no Claude Code (" + aj.etapa + "). O texto já está salvo: pode gravar ou puxar outra coisa enquanto isso.")
        : aj.estado === "erro" ? el("p", { class: "marca" }, aj.erro) : null;
      bloco.append(el("h3", { style: "margin-top:14px" }, "O que os agentes escreveram"), andamento, arquivos,
        el("p", { class: "dica" }, "Faltou algum? No Claude Code, diga ", el("span", { class: "comando-claude" }, "faz os pedidos da Vatty"),
          ", ou copie o prompt para outra IA:"),
        el("div", { class: "pedido" }, ...botoes, status));
      api("video/" + encodeURIComponent(slug)).then((v) => {
        const mds = v.gerados.filter((g) => g.endsWith(".md"));
        arquivos.replaceChildren(...(mds.length ? mds.map((g) => el("a", { class: "btn-mini", href: comToken("arquivo/" + encodeURIComponent(slug) + "/" + encodeURIComponent(g)) }, g))
          : aj && ["fila", "rodando"].includes(aj.estado) ? []
          : [el("span", { class: "dica" }, painel.claude ? "Nenhum arquivo ainda: veja o log no Terminal (embaixo)." : "Nada ainda: o Claude Code não está neste PC.")]));
      }).catch(() => {});
    }
    return bloco;
  });
  $("pronto").replaceChildren(...partes, el("div", { class: "linha-btn", style: "margin-top:14px" },
    el("button", { class: "btn btn-calmo", onclick: novoPedido }, "Começar outro")));
}
async function copiarPrompt(slug, agente, objetivo, status) {
  try {
    const r = await api("video/" + encodeURIComponent(slug) + "/prompt?tipo=" + encodeURIComponent(agente.prompt) + "&foco=" + encodeURIComponent(objetivo || ""));
    await navigator.clipboard.writeText(r.prompt);
    status.textContent = "Copiado. " + r.aviso;
  } catch (e) {
    status.textContent = "Não consegui copiar daqui: use a revisão do texto (Abrir o texto). " + (e.message || "");
  }
}

function novoPedido() {
  clearInterval(painel.vigia);
  painel.trabalhos = [];
  painel.gravacao = null;
  painel.pedido = null;
  mudarFase("escolher");
  irPara(1);
  atualizarResumo();
  desenharDeck();
}

/* ---------- ligações ---------- */
document.querySelectorAll(".modos button").forEach((b) => b.addEventListener("click", () => mudarModo(b.dataset.modo)));
document.querySelectorAll(".fonte").forEach((b) => {
  b.addEventListener("click", () => escolherFonte(b.dataset.fonte));
  b.addEventListener("keydown", (e) => {  // setas trocam a fonte, como num grupo de rádio
    const todas = [...document.querySelectorAll(".fonte")], i = todas.indexOf(b);
    const passo = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!passo) return;
    e.preventDefault();
    const alvo = todas[(i + passo + todas.length) % todas.length];
    alvo.focus();
    escolherFonte(alvo.dataset.fonte);
  });
});
$("g-alvo").addEventListener("change", () => { $("l-janela").hidden = $("g-alvo").value !== "janela"; atualizarResumo(); });
["g-mic", "g-perfil", "y-links", "p-objetivo", "p-slides"].forEach((id) => $(id).addEventListener("input", atualizarResumo));
document.querySelectorAll("input[name=depois]").forEach((r) => r.addEventListener("change", atualizarResumo));
$("p-proximo").addEventListener("click", () => {
  const problema = painel.passo === 1 ? validar().replace(/.*agente.*/, "") : "";
  if (problema) return avisoPainel(problema, true);
  irPara(2);
  atualizarResumo();
});
$("p-voltar").addEventListener("click", () => irPara(1));
$("p-comecar").addEventListener("click", comecar);

/* ---------- começo ---------- */
(async function iniciarPainel() {
  let modo = "passos";
  try { modo = localStorage.getItem("vatty-modo") || modo; } catch (_) { /* sem armazenamento */ }
  const ag = await api("agentes").catch(() => ({ claude: false, lista: [] }));
  painel.agentes = ag.lista;
  painel.claude = ag.claude;
  if (!ag.claude) $("p-agentes-dica").textContent = "O Claude Code não está neste PC: eu só anoto o pedido na pasta e você usa \"copiar prompt\". Gravar e transcrever funcionam sem ele.";
  $("p-agentes").replaceChildren(el("legend", { class: "so-leitor" }, "Agentes"), ...painel.agentes.map((a) =>
    el("label", { class: "agente" }, el("input", { type: "checkbox", value: a.id, onchange: atualizarResumo }),
      a.nome, el("small", {}, a.faz))));
  irPara(1);
  escolherFonte("audio");
  mudarModo(["passos", "bancada", "estudio"].includes(modo) ? modo : "passos");
  const g = await api("gravacao").catch(() => null);  // voltou para a página com uma gravação rodando?
  if (g && (g.estado === "gravando" || g.estado === "parando")) {
    mostrarGravacao(g);
    vigiarGravacao();
  }
})();
