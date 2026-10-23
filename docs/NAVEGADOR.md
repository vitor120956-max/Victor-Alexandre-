# Navegador assistido

Leitura de **snapshot**, resolução de **alvo**, **roteiro de rodadas**, checagem de plano, leitura de **recibos** e classificação de **limites**. A adaptação parte de [`citrolabs/ego-lite`](https://github.com/citrolabs/ego-lite) (MIT, 2026), mas o código é local: nenhum app, binário, SDK, navegador ou skill de marketplace do upstream é instalado ou executado.

O upstream é um navegador próprio para agentes de IA: cada tarefa roda numa *space* isolada, o agente escreve JavaScript contra uma API pequena (`taskSpace`, `page`, `mouse`, `keyboard`) e enxerga a página por um **snapshot** de acessibilidade com referências (`@21`) e locators estáveis (`loc=...`). O valor que sobrevive sem navegador é o **contrato de leitura e de decisão**: como transformar a árvore em alvo, quando um alvo é ambíguo, o que conta como verificação, quando parar e devolver o controle. É isso que a versão 0.14.0 traz, em português.

---

## O que foi adaptado

| Do upstream | Aqui |
|---|---|
| Snapshot de acessibilidade com `ref=` e `loc=` por nó | Parser da árvore com nome entre aspas, metadados aninhados, frames e nove achados |
| Locators `@N`, `text=`, `loc=role:`, `loc=css:`, `loc=href:` | Mesmos formatos, com a regra do documento principal antes dos frames |
| Alvo ambíguo recusado no mesmo documento ou frame | Ambiguidade detectada no snapshot, com candidatos e sugestão de refinamento |
| `label` só em ações de ponteiro, 3 a 6 palavras | Mesma restrição, validada antes de montar o comando |
| Uma space por objetivo, `p1`, `goto` antes de `newPage` | Roteiro fixo de três rodadas com orçamento de 2 a 8 |
| `waitForSelector`/`waitForURL` em vez de espera fixa | Catálogo de 15 padrões que quebram a rodada, com correção |
| Recibo de ação, popup, diálogo e download | Log normalizado em recibos, com despacho separado de verificação |
| `handOff`, `takeOverTaskSpace`, `finish({ keep })` | Ponto de confirmação humana e regras de fechamento |
| Catálogo público de 66 entradas da API | Catálogo local de papéis, alvos, ações, estados, limites e orçamento |

### O que ficou de fora, de propósito

- **Nada de navegador.** O JARVIS não abre aba, não clica, não preenche e não baixa. Ele lê o texto que você cola e devolve plano, achados e comandos.
- **Nada de app, binário ou SDK.** Sem download do ego lite, sem `npx skills add`, sem launcher, sem CDP, sem plugins de Claude/Codex.
- **Nada de IA no laço.** A resolução e a checagem são determinísticas: mesmo snapshot, mesma saída.
- **Nada de execução do plano.** O código gerado é uma proposta para o seu agente; os valores reais e os caminhos absolutos ficam como `<...>`.
- **Nada de conta, credencial ou pagamento.** As regras de limite existem para parar, não para contornar.

---

## O snapshot

O formato esperado é a árvore de acessibilidade que o ego-browser imprime, com **dois espaços por nível**:

```text
root
  heading "Entrar na conta" [level=1]
  textbox "E-mail" [ref=5, loc=css:#email]
  textbox "Senha" [ref=6, loc=unstable]
  button "Entrar" [ref=21, loc=role:button[name="Entrar"]]
  link "Esqueci minha senha" [ref=22, url=https://app.exemplo.com/recuperar]
  iframe [ref=12]
    textbox "Busca" [ref=901, loc=css:#busca]
    button "Pesquisar" [ref=902]
  text "Acesso restrito a clientes."
```

O parser aceita marcador `- `, nome entre aspas com escape, metadados com **colchetes aninhados** (`loc=css:[data-ref="[ref=1]"]`) e distingue `[ref=…]` dentro do nome acessível de metadado real — a mesma distinção que o upstream faz. Metadados reconhecidos: `ref`, `loc`, `url`, `href`, `level`, `checked`, `disabled`, `expanded`, `pressed`, `selected`, `valuetext`, `placeholder`.

Cada linha vira um nó com índice, linha, profundidade, papel, nome, referência, locator, URL, frame e se é acionável. A árvore guarda o caminho de frames (`iframe [ref=12]` → `quadro: ["12"]`) e reporta a profundidade.

### Nove achados da leitura

| Achado | Grupo | O que significa |
|---|---|---|
| `ref-duplicado` | obrigatório | duas linhas com a mesma referência; a ação atinge só uma |
| `sem-acionaveis` | obrigatório | a árvore só tem texto e contêiner; não há alvo semântico |
| `sem-raiz` | corrigir | o recorte começa sem `root`; a hierarquia pode estar incompleta |
| `indentacao` | corrigir | recuo ímpar quebra a leitura de pai e de frame |
| `acionavel-sem-ref` | corrigir | controle sem `ref=`; só resolve por papel + nome ou CSS |
| `loc-instavel` | corrigir | `loc=unstable` ou `loc=ambiguous` não identificam o nó |
| `iframe-sem-ref` | corrigir | sem a referência não há `scope: "subtree"` |
| `sem-nome` | opcional | controle sem nome acessível; sobra o CSS |
| `denso` | opcional | acima de 300 nós, peça um subtree em vez da página inteira |

---

## Resolução de alvo

| Formato | Exemplo | Como resolve |
|---|---|---|
| Referência | `@21`, `ref=21` | procura o nó pelo valor de `ref` |
| Texto exato | `text="Entrar"` | igualdade sensível a maiúsculas, como no upstream |
| Texto livre | `Entrar` | substring sem caixa e sem acento |
| Papel + nome | `loc=role:button[name="Entrar"]` | papel e nome exato |
| Papel + trecho | `loc=role:button[name*="Entrar"]` | papel e trecho do nome |
| CSS | `loc=css:#email`, `css=…`, `#email` | casa com o `loc=css:` que o snapshot trouxe |
| URL do link | `loc=href:recuperar` | trecho da URL do nó |
| Índice | `… >> nth=1` | escolhe a posição depois do escopo |
| XPath | `xpath=//button` | **recusado**: não é avaliável a partir do texto |

A ordem é a do upstream: primeiro o **documento principal**; só quando não há correspondência acionável a busca desce para os frames. Dois matches no mesmo escopo são **ambíguos** e a skill não escolhe por conta própria — devolve os candidatos e pede `@ref`, nome exato ou `nth`.

Se o alvo existe mas o papel não recebe ação (`text`, `heading`, `iframe`), o resultado é `não acionável` e o comando não é montado. `esperar` é a exceção: espera por qualquer nó, inclusive título.

O comando sai pronto para o seu agente:

```js
await page.click("@21", { label: "entrar na conta" });
await page.fill("@5", "<valor real>", { clearFirst: true });
await page.waitForSelector("@902", { state: "visible" });
```

`label` só é aceito em `click`, `dblclick`, `hover`, `dragAndDrop` e `mouse.*`; nas demais ações a skill recusa e explica. Acima de seis palavras, vira observação: o texto aparece ao lado do cursor e precisa ser curto.

---

## Roteiro de rodadas

O roteiro tem três rodadas fixas e um orçamento declarado (2 a 8):

1. **Abrir e observar** — cria a space com nome único, abre a URL em `p1` e termina no snapshot.
2. **Agir** — preenche o primeiro campo quando a intenção é preencher, clica no botão que combina com o objetivo, ou monta `evaluate`, download com `waitForEvent`/`saveAs`, ou um passo de localização.
3. **Verificar e fechar** — espera uma condição observável, lê o título e chama `finish({ keep: [] })` uma única vez, por último.

Regras que o roteiro carrega:

- **Uma space por objetivo.** O nome inclui a data; reabrir com o mesmo nome retoma em vez de criar outra. Cada rodada é um processo novo: variáveis somem, space e rótulos ficam.
- **Uma página.** `p1` navega com `goto`; `newPage` só quando duas telas precisam ficar abertas.
- **Uma observação por rodada**, e o snapshot fecha a rodada: ele é a vista da rodada seguinte.
- **Nenhum dado inventado.** Valores ficam como `<valor real>`, `<seletor do estado final>` e `<caminho absoluto>`.
- **Verbo de risco para o roteiro.** Pagar, comprar, excluir, publicar ou enviar insere o ponto de confirmação e o `handOff`.

Orçamento menor que as três rodadas é bloqueio: sem a última, a space fica aberta e o resultado não é conferido.

---

## Checagem antes de agir

### Quinze padrões de código

| Regra | Grupo | Correção |
|---|---|---|
| `espera-fixa` | corrigir | use `waitForURL`, `waitForSelector` ou `waitForFunction` |
| `duas-superficies` | opcional | escolha snapshot **ou** screenshot na mesma rodada |
| `space-nova` | obrigatório | retome a space; não crie outra para escapar de página travada |
| `pagina-por-url` | corrigir | reuse `p1` com `goto` |
| `finish-ausente` | corrigir | feche com `finish({ keep: [] })` |
| `finish-duplo` | obrigatório | chame uma vez, por último |
| `finish-cedo` | obrigatório | nada de página depois do fechamento |
| `rotulo-proibido` | obrigatório | `label` só em ação de ponteiro |
| `rotulo-longo` | opcional | 3 a 6 palavras |
| `playwright` | obrigatório | a API é própria; não importe nem lance navegador |
| `env` | corrigir | o processo não herda o ambiente do shell |
| `caminho-relativo` | obrigatório | caminho absoluto para screenshot e download |
| `coordenada-primeiro` | corrigir | snapshot antes de clicar por coordenada |
| `retry-cego` | corrigir | observe antes de repetir |
| `claim-sem-pedido` | corrigir | assumir space alheia só com autorização |

### Dez estados de alvo

`oculto`, `desabilitado`, `somente-leitura`, `coberto`, `fora-da-viewport`, `animando`, `destacado`, `ambíguo`, `sem-ref` e `sem-nome`. Cada um traz causa, correção e o que se perde ao ignorar. A lista de passos é `ação | alvo | estado`, uma por linha.

---

## Recibos e fechamento

O log é lido linha a linha e vira recibo com ação, alvo, resultado, efeito, popup, diálogo, download, tempo e a linha original. Sobre esses recibos rodam dez cobranças:

- `sem-finish`, `finish-repetido` e `acao-pos-finish`;
- `popup` aberto sem tratamento e `dialogo` pendente;
- `download` sem `saveAs` para caminho absoluto;
- `keep-demais` (manter páginas é exceção);
- `sem-observacao` (agiu e não olhou);
- `recibo-nao-e-prova` (despacho não é verificação);
- `falha` declarada no log.

**Recibo é despacho.** Quem prova que a tarefa terminou é uma condição observável: URL, seletor visível, título ou um snapshot novo.

---

## Limites e consentimento

Onze regras, três níveis, e a pessoa no centro:

| Nível | Regras | Quem decide |
|---|---|---|
| bloqueado | credencial, pagamento, CAPTCHA, contornar o controle do usuário | você |
| confirmar | exclusão, publicação, termos, alteração de conta, upload, dados de terceiros, conta corporativa | você, com o efeito descrito |
| liberado | abrir, ler, rolar, buscar, preencher formulário comum, baixar relatório próprio | o agente |

A classificação é **léxica e conservadora**: o que não é reconhecido como leitura vira `confirmar`. Ela lê palavras, não intenção — e não substitui política da empresa, termos do site ou julgamento humano.

Quando há bloqueio ou confirmação pendente, a saída inclui o handoff: pare, explique o que falta e devolva o controle com `await task.handOff()`; depois do aval, retome a **mesma** space com `takeOverTaskSpace`.

---

## As sete skills

| Skill | Entrada | Devolve |
|---|---|---|
| `navegador.snapshot` | snapshot, modo | índice de nós, papéis, refs, locators, frames, profundidade e nove achados |
| `navegador.alvo` | snapshot, alvo, ação, valor, rótulo | resolução, escopo, candidatos, ambiguidade, sugestões e comando |
| `navegador.roteiro` | objetivo, URL, snapshot, orçamento | três rodadas com código, ações, risco, handoff e achados |
| `navegador.checagem` | plano em JavaScript, passos | quinze padrões, tabela de passos por estado e veredito |
| `navegador.recibos` | log | recibos normalizados, dez cobranças e veredito de fechamento |
| `navegador.limites` | ações pretendidas | veredito por ação, motivo, o que fazer e handoff |
| `navegador.regras` | — | papéis, alvos, ações, estados, limites, padrões e orçamento |

Todas devolvem `executed: false` e `readOnly: true`. Nenhuma abre navegador, lê portal ou grava arquivo.

---

## Página `/navegador`

Sete abas, cada uma com exemplo próprio e nível `lite`, `full` ou `ultra`:

- **Snapshot** — métricas, chips por papel, tabela de nós e achados;
- **Alvo** — veredito de resolução, comando pronto, candidatos e sugestões;
- **Roteiro** — rodadas com código, ações e aviso de confirmação;
- **Checagem** — métricas, padrões, tabela de passos e achados;
- **Recibos** — tabela de recibos, efeitos e cobranças;
- **Limites** — veredito por ação, cores por nível e bloco de handoff;
- **Regras** — catálogo completo lido da API.

O relatório em markdown é copiável em todas as abas.

---

## Determinismo e limites

- O snapshot é uma foto: se a página mudou depois dele, a referência pode não existir mais.
- CSS, XPath e shadow DOM não são avaliados aqui: a skill só usa o que o snapshot declarou. XPath é recusado com alternativa.
- A checagem de código é léxica; um padrão pode ser intencional e ainda aparecer.
- A classificação de limites lê palavras e nunca substitui política, termos ou julgamento humano.
- Nada é executado, aberto, clicado, preenchido, baixado ou enviado por estas skills.

---

## Como rodar e testar

```bash
.venv/bin/python -m pytest server/tests -q     # 381 testes, 69 deles em test_navegador.py
npx vitest run                                 # 41 testes web
npx tsc --noEmit && npm run build
```

As skills ficam em `server/navegador.py` e o registro em `server/skill_registry.py`. A página está em `src/pages/NavegadorPage.tsx`, com o CSS em `src/navegador.css`.

---

## Licença e atribuição

O upstream está sob **MIT** (`Copyright (c) 2026 CitroLabs`). A licença completa está em [`docs/licenses/citrolabs-ego-lite.txt`](licenses/citrolabs-ego-lite.txt).

Este projeto não copia código do upstream: o parser, a resolução, o roteiro, a checagem e o catálogo foram escritos aqui, a partir do contrato documentado. Nada do ego lite é baixado, instalado ou executado.
