/* Interface da Vatty. Sem biblioteca externa. Todo texto que vem de fora (título, transcrição, erro)
   entra no DOM por textContent, nunca por innerHTML. */
"use strict";

const TOKEN = new URLSearchParams(location.search).get("t") || "";
const $ = (id) => document.getElementById(id);
const estado = { trabalhos: new Map(), logs: new Map(), video: null, logAtivo: null };

function el(tag, attrs = {}, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v === true) n.setAttribute(k, "");
    else if (v !== false && v != null) n.setAttribute(k, v);
  }
  for (const f of filhos.flat()) if (f != null) n.append(f.nodeType ? f : document.createTextNode(String(f)));
  return n;
}

const SEM_CONEXAO = "Perdi a conexão com a Vatty. A janela preta dela ainda está aberta? Se fechou, abra o abrir-vatty.bat de novo. "
  + "Se estiver aberta, feche as outras abas da Vatty e recarregue esta página.";
async function api(caminho, opcoes = {}) {
  let r;
  try {
    r = await fetch("/api/" + caminho, { ...opcoes, headers: { "X-Vatty-Token": TOKEN, ...(opcoes.headers || {}) } });
  } catch (_) {
    throw new Error(SEM_CONEXAO);  // "Failed to fetch": o servidor fechou ou caiu
  }
  const dados = await r.json().catch(() => ({}));
  if (r.status === 401) throw new Error("Esta aba é de uma Vatty antiga. Use a aba que abriu por último (ou o endereço que a janela preta mostra).");
  if (!r.ok) throw new Error(dados.erro || (dados.recusados || []).map((x) => x.erro).join(" ") || "Algo deu errado (" + r.status + ").");
  return dados;
}
const post = (c, corpo) => api(c, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo || {}) });
const comToken = (caminho) => "/api/" + caminho + (caminho.includes("?") ? "&" : "?") + "t=" + encodeURIComponent(TOKEN);

function relogio(s) {
  s = Math.max(0, Math.round(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0");
}

/* ---------- abas ---------- */
function abrirAba(nome) {
  document.querySelectorAll(".abas button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.aba === nome)));
  document.querySelectorAll(".aba").forEach((s) => (s.hidden = s.id !== "aba-" + nome));
  if (nome === "biblioteca") carregarBiblioteca();
}
document.querySelectorAll(".abas button").forEach((b) => b.addEventListener("click", () => abrirAba(b.dataset.aba)));

/* ---------- importar ---------- */
function opcoes() {
  return { texto: $("o-texto").value, falantes: $("o-falantes").value, visual: $("o-visual").value, lang: $("o-lang").value };
}
function aviso(msg, erro = false) {
  const a = $("aviso-importar");
  a.textContent = msg;
  a.className = erro ? "marca" : "";
}
async function enviarEntradas(entradas) {
  const r = await post("trabalhos", { entradas, opcoes: opcoes() }).catch((e) => ({ criados: [], recusados: [{ entrada: "", erro: e.message }] }));
  if (r.recusados && r.recusados.length) aviso(r.recusados.map((x) => x.erro).join(" "), true);
  else aviso(r.criados.length + " na fila.");
  if (r.criados && r.criados.length) abrirAba("fila");
  return r;
}
$("enviar").addEventListener("click", async () => {
  const links = $("links").value.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!links.length) return aviso("Cole pelo menos um link.", true);
  const r = await enviarEntradas(links);
  if (r.criados.length) $("links").value = "";
});

async function enviarArquivos(lista) {
  const caminhos = [];
  for (const arq of lista) {
    aviso("Enviando " + arq.name + "...");
    try {
      const r = await fetch("/api/upload?nome=" + encodeURIComponent(arq.name), { method: "POST", headers: { "X-Vatty-Token": TOKEN }, body: arq });
      const dados = await r.json();
      if (!r.ok) throw new Error(dados.erro);
      caminhos.push(dados.caminho);
    } catch (e) { aviso("Não consegui enviar " + arq.name + ": " + e.message, true); }
  }
  if (caminhos.length) await enviarEntradas(caminhos);
}
const soltar = $("soltar");
soltar.addEventListener("click", () => $("arquivos").click());
soltar.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("arquivos").click(); } });
$("arquivos").addEventListener("change", (e) => { enviarArquivos([...e.target.files]); e.target.value = ""; });
["dragenter", "dragover"].forEach((t) => soltar.addEventListener(t, (e) => { e.preventDefault(); soltar.classList.add("sobre"); }));
["dragleave", "drop"].forEach((t) => soltar.addEventListener(t, (e) => { e.preventDefault(); soltar.classList.remove("sobre"); }));
soltar.addEventListener("drop", (e) => enviarArquivos([...e.dataTransfer.files]));

/* ---------- fila ---------- */
const ROTULO = { fila: "Na fila", rodando: "Rodando", pronto: "Pronto", erro: "Erro", cancelado: "Cancelado" };
const CLASSE = { fila: "estado-fila", rodando: "estado-rodando", pronto: "estado-pronto", erro: "estado-erro", cancelado: "estado-fila" };

function nomeCurto(entrada) {
  const limpo = entrada.replace(/^.*[\\/]/, "").replace(/^[0-9a-f]{8}-/, "");
  return /^https?:/i.test(entrada) ? entrada : limpo;
}
function itemFila(t) {
  const detalhe = t.estado === "erro" ? t.erro : t.etapa + (t.estado === "rodando" && t.progresso ? ", " + t.progresso + "%" : "");
  const costura = el("div", { class: "costura", style: "--p:" + t.progresso + "%" }, el("i"));
  const acoes = el("div", { class: "acoes" });
  if (t.estado === "fila" || t.estado === "rodando") acoes.append(el("button", { class: "btn-mini", onclick: () => post("trabalhos/" + t.id + "/cancelar") }, "Cancelar"));
  if (t.estado === "erro" || t.estado === "cancelado") acoes.append(el("button", { class: "btn-mini", onclick: () => post("trabalhos/" + t.id + "/repetir") }, "Tentar de novo"));
  if (t.estado === "pronto" && t.pasta) acoes.append(el("button", { class: "btn-mini", onclick: () => abrirVideo(t.pasta.split(/[\\/]/).pop()) }, "Abrir"));
  acoes.append(el("button", { class: "btn-mini", onclick: () => verLog(t.id) }, "Log"));
  return el("div", { class: "item", "data-id": t.id },
    el("div", { class: "nome" }, nomeCurto(t.entrada), el("small", {}, detalhe)),
    costura, el("span", { class: "estado " + CLASSE[t.estado] }, ROTULO[t.estado]), acoes);
}
function desenharFila() {
  const lista = [...estado.trabalhos.values()].sort((a, b) => a.criado - b.criado);
  $("lista-fila").replaceChildren(...lista.map(itemFila));
  $("vazio-fila").hidden = lista.length > 0;
  const ativos = lista.filter((t) => t.estado === "fila" || t.estado === "rodando");
  $("c-fila").hidden = !ativos.length;
  $("c-fila").textContent = ativos.length;
  const rodando = lista.find((t) => t.estado === "rodando");
  const barra = $("barra-geral");
  barra.style.setProperty("--p", (rodando ? rodando.progresso : lista.length && !ativos.length ? 100 : 0) + "%");
  $("resumo-fila").textContent = rodando ? nomeCurto(rodando.entrada) + ": " + rodando.etapa : ativos.length ? ativos.length + " esperando." : "Nada na fila.";
  if (window.aoMudarFila) window.aoMudarFila();  // o painel "Começar" acompanha os trabalhos dele
}
async function verLog(id) {
  estado.logAtivo = id;
  const dados = await api("trabalhos/" + id + "/log").catch(() => ({ log: [] }));
  estado.logs.set(id, dados.log);
  abrirGaveta(true);
  desenharTerminal();
}

/* ---------- terminal ---------- */
function abrirGaveta(abrir) {
  const corpo = document.querySelector(".gaveta-corpo");
  corpo.hidden = !abrir;
  $("gaveta-botao").setAttribute("aria-expanded", String(abrir));
}
$("gaveta-botao").addEventListener("click", () => abrirGaveta(document.querySelector(".gaveta-corpo").hidden));
function linhaTerminal(texto, classe) { return el("div", { class: classe || "" }, texto); }
function classeDaLinha(l) { return /^Erro/.test(l) ? "erro" : /^Aviso/.test(l) ? "aviso" : /^Pronto/.test(l) ? "ok" : ""; }
function desenharTerminal() {
  const t = $("terminal");
  const linhas = (estado.logs.get(estado.logAtivo) || []).map((l) => linhaTerminal(l, classeDaLinha(l)));
  t.replaceChildren(...linhas);
  t.scrollTop = t.scrollHeight;
}
$("form-comando").addEventListener("submit", async (e) => {
  e.preventDefault();
  const linha = $("comando").value.trim();
  if (!linha) return;
  $("comando").value = "";
  const t = $("terminal");
  t.append(linhaTerminal("$ vatty " + linha, "ok"));
  try {
    const r = await post("comando", { linha });
    r.saida.split("\n").forEach((l) => t.append(linhaTerminal(l, r.codigo ? "erro" : "")));
  } catch (err) { t.append(linhaTerminal(err.message, "erro")); }
  t.scrollTop = t.scrollHeight;
});

/* ---------- eventos em tempo real ---------- */
function ouvirEventos() {
  const fonte = new EventSource("/api/eventos?t=" + encodeURIComponent(TOKEN));
  fonte.onmessage = (m) => {
    const e = JSON.parse(m.data);
    if (e.tipo === "trabalho") {
      const antes = estado.trabalhos.get(e.trabalho.id);
      estado.trabalhos.set(e.trabalho.id, e.trabalho);
      desenharFila();
      if (e.trabalho.estado === "pronto" && (!antes || antes.estado !== "pronto")) carregarBiblioteca();
    } else if (e.tipo === "log") {
      const l = estado.logs.get(e.id) || [];
      l.push(e.linha);
      estado.logs.set(e.id, l);
      if (!estado.logAtivo) estado.logAtivo = e.id;
      if (estado.logAtivo === e.id) {
        $("terminal").append(linhaTerminal(e.linha, classeDaLinha(e.linha)));
        $("terminal").scrollTop = $("terminal").scrollHeight;
      }
    }
  };
}

/* ---------- biblioteca ---------- */
async function carregarBiblioteca() {
  const lista = await api("biblioteca").catch(() => []);
  $("lista-biblioteca").replaceChildren(...lista.map((v) => el("div", { class: "video" },
    el("div", {}, el("b", {}, v.titulo),
      el("small", {}, [v.tipo, v.duracao_s ? relogio(v.duracao_s) : null, v.origem].filter(Boolean).join(", "),
        v.duvidosos ? el("span", { class: "marca" }, " · " + v.duvidosos + " para revisar") : null)),
    el("button", { class: "btn btn-calmo", onclick: () => abrirVideo(v.slug) }, "Abrir"))));
  $("vazio-biblioteca").hidden = lista.length > 0;
  $("n-videos").textContent = lista.length;
  $("n-horas").textContent = (lista.reduce((s, v) => s + (v.duracao_s || 0), 0) / 3600).toFixed(1);
  $("n-duvidosos").textContent = lista.reduce((s, v) => s + (v.duvidosos || 0), 0);
}
$("form-busca").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("busca").value.trim();
  if (!q) return $("achados").replaceChildren();
  const achados = await api("buscar?q=" + encodeURIComponent(q)).catch(() => []);
  $("achados").replaceChildren(...(achados.length ? achados.map((a) => el("div", { class: "holo achado" },
    el("span", { class: "onde" }, a.titulo + (a.horario ? " " + a.horario : "")),
    a.trecho, a.link ? el("div", {}, el("a", { href: a.link, target: "_blank", rel: "noopener" }, "Abrir no vídeo")) : null,
    el("div", {}, el("button", { class: "btn-mini", onclick: () => abrirVideo(a.pasta) }, "Abrir transcrição"))))
    : [el("p", { class: "vazio" }, "Nada achado para “" + q + "”.")]));
});

/* ---------- leitor ---------- */
const FORMATOS = ["txt", "md", "srt", "vtt", "csv", "json"];
function linkDoHorario(fonte, s) {
  if (fonte.tipo !== "youtube" || !fonte.url || s == null) return null;
  return fonte.url + (fonte.url.includes("?") ? "&" : "?") + "t=" + s + "s";
}
async function abrirVideo(slug) {
  let v;
  try { v = await api("video/" + encodeURIComponent(slug)); } catch (e) { return aviso(e.message, true); }
  estado.video = v;
  $("aba-leitor").hidden = false;
  desenharLeitor();
  abrirAba("leitor");
}
function desenharLeitor() {
  const v = estado.video;
  const topo = el("div", { class: "leitor-topo" },
    el("div", {}, el("h2", {}, v.fonte.titulo || v.slug),
      el("small", { class: "dica" }, [v.fonte.canal, v.cabecalho.origem, v.cabecalho.duracao_s ? relogio(v.cabecalho.duracao_s) : null].filter(Boolean).join(", "))),
    el("div", { class: "exportar" }, ...FORMATOS.map((f) => el("a", { class: "btn-mini", href: comToken("exportar/" + encodeURIComponent(v.slug) + "/" + f) }, "." + f)),
      ...v.gerados.map((g) => el("a", { class: "btn-mini", href: comToken("arquivo/" + encodeURIComponent(v.slug) + "/" + encodeURIComponent(g)) }, g))));
  const duvidosos = v.paragrafos.filter((p) => p.duvidoso).length;
  const filtro = el("label", { class: "filtro" }, el("input", { type: "checkbox", id: "so-duvidosos", onchange: () => desenharParagrafos() }),
    " Só os " + duvidosos + " trechos para revisar");
  $("leitor").replaceChildren(topo, ferramentas(v), duvidosos ? filtro : el("span"), el("div", { class: "paragrafos", id: "paragrafos" }));
  desenharParagrafos();
}
function desenharParagrafos() {
  const v = estado.video, so = $("so-duvidosos") && $("so-duvidosos").checked;
  const lista = v.paragrafos.filter((p) => !so || p.duvidoso);
  $("paragrafos").replaceChildren(...(lista.length ? lista.map((p) => {
    const url = linkDoHorario(v.fonte, p.inicio_s);
    const hora = url ? el("a", { class: "horario", href: url, target: "_blank", rel: "noopener" }, p.horario) : el("span", { class: "horario" }, p.horario);
    return el("div", { class: "para" }, hora, el("span", { class: p.duvidoso ? "duvida" : "" }, p.texto));
  }) : [el("p", { class: "vazio" }, v.paragrafos.length ? "Nada para revisar aqui." : "Esta transcrição está vazia.")]));
}

/* ---------- revisão, falantes e prompt ---------- */
function ferramentas(v) {
  const status = el("span", { role: "status", class: "dica" });
  const errado = el("input", { id: "f-errado", placeholder: "Como saiu (selecione no texto)", "aria-label": "Como saiu" });
  const certo = el("input", { id: "f-certo", placeholder: "Como deveria ser", "aria-label": "Como deveria ser" });
  const guardar = el("input", { type: "checkbox", id: "f-guardar" });
  const corrigir = el("div", { class: "ferramenta" },
    el("h3", {}, "Corrigir uma palavra"),
    el("div", { class: "duas" }, errado, certo),
    el("label", { class: "marcar" }, guardar, " Guardar como regra para as próximas transcrições"),
    el("div", { class: "linha-btn" }, el("button", { class: "btn btn-principal", onclick: async () => {
      try {
        const r = await post("video/" + encodeURIComponent(v.slug) + "/corrigir", { errado: errado.value, certo: certo.value, guardar: guardar.checked });
        status.textContent = r.vezes ? r.vezes + " troca(s) feita(s)." + (r.regra_guardada ? " Regra guardada." : "") : "Não achei essa palavra.";
        if (r.vezes) await abrirVideo(v.slug);
      } catch (e) { status.textContent = e.message; }
    } }, "Corrigir"), status));
  const partes = [corrigir];

  const pessoas = ((v.falantes && v.falantes.pessoas) || []).map((p) => p.pessoa).filter((n) => /^Pessoa \d+$/.test(n));
  if (pessoas.length) {
    const campos = pessoas.map((n) => el("label", {}, n + (v.falantes.pessoas.find((p) => p.pessoa === n).fala_s ? " (" + relogio(v.falantes.pessoas.find((p) => p.pessoa === n).fala_s) + " de fala)" : ""),
      el("input", { "data-pessoa": n, value: v.nomes[n] || "", placeholder: "Nome" })));
    partes.push(el("div", { class: "ferramenta" }, el("h3", {}, "Quem é quem"), el("div", { class: "duas" }, ...campos),
      el("div", { class: "linha-btn" }, el("button", { class: "btn btn-calmo", onclick: async () => {
        const nomes = {};
        document.querySelectorAll("[data-pessoa]").forEach((i) => (nomes[i.dataset.pessoa] = i.value));
        await post("video/" + encodeURIComponent(v.slug) + "/nomes", { nomes }).catch(() => null);
        await abrirVideo(v.slug);
      } }, "Salvar nomes"))));
  }

  const tipo = el("select", { id: "p-tipo", "aria-label": "Tipo de prompt" });
  api("prompts").then((l) => l.forEach((t) => tipo.append(el("option", { value: t.tipo }, t.nome)))).catch(() => {});
  const foco = el("input", { id: "p-foco", placeholder: "Foco (opcional)", "aria-label": "Foco" });
  const aviso = el("p", { class: "dica", id: "p-aviso" });
  const area = el("textarea", { id: "p-area", rows: "5", hidden: true, readonly: true, "aria-label": "Prompt" });
  partes.push(el("div", { class: "ferramenta" }, el("h3", {}, "Copiar prompt para uma IA"),
    el("div", { class: "duas" }, tipo, foco),
    el("div", { class: "linha-btn" }, el("button", { class: "btn btn-calmo", onclick: async () => {
      try {
        const r = await api("video/" + encodeURIComponent(v.slug) + "/prompt?tipo=" + encodeURIComponent(tipo.value) + "&foco=" + encodeURIComponent(foco.value));
        aviso.textContent = r.aviso;
        try { await navigator.clipboard.writeText(r.prompt); aviso.textContent = "Copiado. " + r.aviso; }
        catch (_) { area.hidden = false; area.value = r.prompt; area.select(); aviso.textContent = "Selecione e copie o texto abaixo. " + r.aviso; }
      } catch (e) { aviso.textContent = e.message; }
    } }, "Copiar prompt")), aviso, area));
  return el("details", { class: "opcoes" }, el("summary", {}, "Revisar, nomear e usar com uma IA"), ...partes);
}
document.addEventListener("mouseup", () => {
  const sel = String(window.getSelection() || "").trim();
  const campo = $("f-errado");
  if (campo && sel && sel.length <= 80 && !sel.includes("\n") && $("leitor").contains(window.getSelection().anchorNode)) campo.value = sel;
});

/* ---------- começo ---------- */
fetch("/api/estado", { headers: { "X-Vatty-Token": TOKEN } }).then((r) => {
  if (r.status === 401) document.body.prepend(el("p", { class: "remendo" }, "Token inválido. Abra o endereço que a Vatty mostrou no terminal."));
});
api("saude").then((itens) => {
  const faltam = itens.filter((i) => !i.ok);
  const essenciais = faltam.filter((i) => i.nivel === "essencial");
  if (!essenciais.length) return;
  $("falta").hidden = false;
  $("falta").replaceChildren(el("h3", {}, "Falta pouco para a primeira transcrição"),
    ...essenciais.map((i) => el("p", {}, el("b", {}, i.nome + ": "), i.ajuda)),
    el("p", { class: "dica" }, "Opções como ler slides ou separar falantes pedem programas extras e avisam quando for a hora."));
}).catch(() => {});
carregarBiblioteca();
ouvirEventos();
