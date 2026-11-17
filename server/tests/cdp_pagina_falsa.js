// DOM mínimo para exercitar, sem navegador, o JavaScript que o JARVIS injeta.
//
// Por que existe (0.91.27). O caminho novo fala com a página pelo protocolo do
// Chrome: o Python manda `window.__JARVIS("clicar", "New key")` e recebe de
// volta o que a página respondeu. A parte arriscada disso é o JavaScript — não
// dá para descobrir um erro de sintaxe ou de seletor no PC do dono, uma rodada
// por vez. Então o mesmo texto que vai para a página roda aqui, em cima desta
// página falsa, no `node`.
//
// A página falsa imita o que o dono mostrou no print de 16/11: a página real
// das chaves **mais** a moldura da janela (títulos repetidos e o balão
// “Restaurar páginas?”). Se o clique cair na moldura, é aqui que aparece.
//
// Uso (o teste em Python monta a chamada):
//   node cdp_pagina_falsa.js "<javascript injetado>" '<ordem JSON>' ...

const RESULTADOS = [];

function visivelSempre() {
  return { width: 120, height: 30 };
}

let contador = 0;

function elemento(tag, texto, extras = {}) {
  const el = {
    tagName: tag.toUpperCase(),
    innerText: texto,
    _attrs: new Map(Object.entries(extras.attrs || {})),
    _filhos: extras.filhos || [],
    _visivel: extras.visivel !== false,
    _aoClicar: extras.aoClicar || null,
    _valor: extras.valor || "",
    style: {},
    id: extras.id || "",
    name: extras.name || "",
    _ordem: contador++,
  };
  el.getAttribute = (nome) => (el._attrs.has(nome) ? el._attrs.get(nome) : null);
  el.hasAttribute = (nome) => el._attrs.has(nome);
  el.setAttribute = (nome, valor) => el._attrs.set(nome, valor);
  el.getBoundingClientRect = () => (el._visivel ? visivelSempre() : { width: 0, height: 0 });
  el.scrollIntoView = () => {};
  el.focus = () => {};
  el.dispatchEvent = () => true;
  el.querySelectorAll = (seletor) => procurarDentro(el, seletor);
  el.querySelector = (seletor) => procurarDentro(el, seletor)[0] || null;
  el.click = () => {
    if (el._aoClicar) el._aoClicar(el);
  };
  Object.defineProperty(el, "value", {
    get: () => el._valor,
    set: (novo) => {
      el._valor = novo;
    },
  });
  return el;
}

function procurarDentro(raiz, seletor) {
  const alvos = seletor.split(",").map((item) => item.trim()).filter(Boolean);
  const achados = [];
  const visitar = (no) => {
    for (const filho of no._filhos || []) {
      if (casa(filho, alvos)) achados.push(filho);
      visitar(filho);
    }
  };
  visitar(raiz);
  return achados;
}

function casa(no, alvos) {
  return alvos.some((alvo) => {
    if (alvo === "input") return no.tagName === "INPUT";
    if (alvo === "textarea") return no.tagName === "TEXTAREA";
    if (alvo === "select") return no.tagName === "SELECT";
    if (alvo === "button") return no.tagName === "BUTTON";
    if (alvo === "a") return no.tagName === "A";
    const papel = alvo.match(/^\[role="([^"]+)"\]$/);
    if (papel) return no.getAttribute("role") === papel[1];
    const attr = alvo.match(/^\[([a-z-]+)\]$/);
    if (attr) return no.hasAttribute(attr[1]);
    return false;
  });
}

// ---------------------------------------------------------------------------
// A página falsa: OpenRouter + moldura da janela
// ---------------------------------------------------------------------------

function montar() {
  contador = 0;
  const corpo = elemento("body", "");
  const moldura = elemento("div", "Keys | Settings | OpenRouter");
  moldura._filhos = [
    elemento("div", "Keys | Settings | OpenRouter"),
    elemento("div", "Restaurar páginas?"),
    elemento("div", "Restaurar páginas?"),
  ];

  const botao = elemento("button", "New key", {
    aoClicar: () => abrirPainel(),
  });
  const pagina = elemento("div", "API Keys\nNew key\nName\nCreated\nLast used");
  pagina._filhos = [botao];

  const raiz = elemento("div", "", { filhos: [moldura, pagina] });
  corpo._filhos = [raiz];
  // innerText do body: a moldura entra junto, como na leitura de verdade — e
  // o painel entra quando abre, como no navegador.
  Object.defineProperty(corpo, "innerText", {
    get: () =>
      "Keys | Settings | OpenRouter\nRestaurar páginas?\nRestaurar páginas?\n" +
      pagina.innerText +
      (documento.__painel ? "\n" + documento.__painel.innerText : ""),
  });

  const documento = {
    body: corpo,
    documentElement: raiz,
    __painel: null,
    readyState: "complete",
    querySelectorAll: (seletor) => procurarDentro(corpo, seletor),
    querySelector: (seletor) => procurarDentro(corpo, seletor)[0] || null,
  };

  function abrirPainel() {
    const campo = elemento("input", "", { name: "name", valor: "" });
    const expiracao = elemento("button", "Select expiration", {
      aoClicar: () => {
        const painel = documento.__painel;
        painel._filhos = painel._filhos.filter((no) => no.getAttribute("role") !== "option");
        ["1 day", "30 days", "No expiration"].forEach((texto) => {
          painel._filhos.push(elemento("div", texto, { attrs: { role: "option" } }));
        });
      },
    });
    const limite = elemento("button", "Credit limit", {
      aoClicar: () => {
        const painel = documento.__painel;
        painel._filhos = painel._filhos.filter((no) => no.getAttribute("role") !== "option");
        ["No limit", "5", "10"].forEach((texto) => {
          painel._filhos.push(elemento("div", texto, { attrs: { role: "option" } }));
        });
      },
    });
    const campoDoLimite = elemento("input", "", { name: "limit", valor: "No limit" });
    const criar = elemento("button", "Create", {
      aoClicar: () => {
        const chave = "sk-or-v1-" + "a".repeat(64);
        if (process.env.CDP_CHAVE_NO_CAMPO === "1") {
          // Variante do site que mostra a chave dentro de um campo, e não no
          // texto: `innerText` não a veria, `input.value` vê.
          documento.__painel._filhos.push(
            elemento("input", "", { name: "key", valor: chave })
          );
          documento.__chave = "";
        } else {
          documento.__chave = chave;
        }
      },
    });
    const painel = elemento("div", "Create API key", {
      attrs: { role: "dialog" },
      filhos: [
        campo,
        expiracao,
        limite,
        campoDoLimite,
        criar,
      ],
    });
    // O texto do painel é montado na hora: o nome que o JARVIS digitou tem de
    // aparecer nele, e a chave só depois do “Create” — como no site de verdade.
    Object.defineProperty(painel, "innerText", {
      get: () =>
        "Create API key\nName\n" +
        (campo.value || "") +
        (documento.__chave ? "\n" + documento.__chave : "") +
        "\nCreate",
    });
    documento.__painel = painel;
    raiz._filhos.push(painel);
  }

  return documento;
}

// ---------------------------------------------------------------------------
// Bancada: o corpo da página é montado antes do JavaScript do JARVIS
// ---------------------------------------------------------------------------

globalThis.window = globalThis;
globalThis.document = montar();
globalThis.location = { href: "https://openrouter.ai/settings/keys" };
globalThis.getComputedStyle = () => ({ visibility: "visible", display: "block" });
globalThis.HTMLInputElement = function () {};
globalThis.HTMLTextAreaElement = function () {};
Object.defineProperty(HTMLInputElement.prototype, "value", {
  get() {
    return this._valor;
  },
  set(novo) {
    this._valor = novo;
  },
});
Object.defineProperty(HTMLTextAreaElement.prototype, "value", {
  get() {
    return this._valor;
  },
  set(novo) {
    this._valor = novo;
  },
});
globalThis.Event = class {
  constructor(tipo) {
    this.type = tipo;
  }
};
globalThis.inputs = () => procurarDentro(document.body, ["input"]);

module.exports = { documento: () => document };
