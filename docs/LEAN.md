# Engenharia enxuta (lean)

Adaptação própria do comportamento do projeto [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) (MIT) para o JARVIS. O JARVIS **não instala** o plugin, hooks, comandos npm, telemetria `band`/`board` ou qualquer script do upstream, e **não copia** o prompt original. As quatro skills são implementações estáticas em Python: leem somente o que o usuário cola ou envia para a área de código e devolvem candidatos com evidência e limites declarados.

- Upstream: `https://github.com/DietrichGebert/ponytail`, branch `main`, último push em 2026-10-18.
- Licença: MIT, Copyright (c) 2026 DietrichGebert. Texto integral em [`docs/licenses/dietrichgebert-ponytail.txt`](licenses/dietrichgebert-ponytail.txt).
- Nada do repositório é executado. As rotas e skills retornam `executed: false` e `readOnly: true`.

## A escada

A ordem é deliberada: primeiro entender o problema e o código, depois cortar. A escada para no **primeiro degrau que cobre o pedido por completo**.

| # | Degrau | Pergunta |
|---|---|---|
| 1 | Precisa existir? | O pedido justifica este recurso, opção ou flexibilidade? |
| 2 | Já existe no projeto? | Existe helper, componente ou padrão que o resto do código já usa? |
| 3 | Biblioteca padrão ou nativo? | Uma API da plataforma resolve sem dependência nova? |
| 4 | Dependência já instalada? | Um pacote que já está no projeto cobre o caso? |
| 5 | Cabe em uma linha legível? | O leitor entende de primeira? |
| 6 | O mínimo que funciona | Só então escreva o menor código completo, com teste quando necessário. |

Cada degrau recebe uma situação e uma evidência:

- `holds`: cobre por completo e é a decisão.
- `available`: cobre, mas um degrau anterior já resolveu.
- `partial`: cobre em parte; a escada continua.
- `skipped`: não existe, não foi declarado ou não cobre.
- `cut`: item de escopo declarado que ninguém pediu.
- `clear`: degrau sem pendência declarada.
- `fallback`: o degrau do mínimo, quando nada acima resolve.

A skill não lê o repositório: ela avalia **declarações**. Por isso toda evidência é obrigatória nos degraus que cobrem, e a saída sempre lista o que não foi verificado. Alcance da mudança é o que a alteração precisa tocar (callers, testes, fixtures, config, exports) mais o que pode quebrar para usuários; recurso extra não é escopo.

## Preguiçoso com a solução, nunca com a leitura

Nunca cortar, em nenhum nível:

- validação nas fronteiras de confiança;
- tratamento de erro que evita perda de dados;
- segurança;
- acessibilidade;
- calibração exigida por hardware real;
- qualquer coisa que o usuário pediu.

A skill `lean.review` procura proteções removidas no diff e exige substituto visível. `lean.audit` sinaliza padrões de risco (`eval`, shell, HTML injetado, segredo literal, SQL concatenado, desserialização insegura).

## Obrigação de teste

Teste pequeno é obrigatório quando a mudança introduz ramo, laço, parser, dinheiro, segurança ou um script/aplicativo novo. Mudança trivial não recebe teste artificial. A escada declara a obrigação; a revisão acusa ramo, laço, parse, dinheiro ou segurança adicionados sem arquivo de teste no diff; a auditoria acusa arquivos com lógica arriscada sem teste correspondente.

## Atalhos com prazo

Convenção no código:

```
shortcut: <o limite>, <quando revisar>
```

Exemplos:

```js
// shortcut: cache em memória, revisar com 100 usuários
// shortcut: sem paginação, quando a tabela passar de 10k linhas
```

O marcador antigo `ponytail:` também é aceito (`includeLegacy`). Um gatilho vazio ou genérico (`depois`, `futuro`, `TODO`, `someday`, `nunca`) vira `no-trigger`, porque um atalho sem limite e sem data se transforma em decisão permanente por esquecimento.

## Níveis

- `lite`: cita a opção menor e mostra apenas bloqueios (na revisão, só achados obrigatórios; na auditoria, só `must`).
- `full`: padrão. Corrige, enxuga e cobra teste.
- `ultra`: questiona o pedido antes de construir.

## Ordens de revisão

`lean.review` e `lean.audit` ordenam por correto, seguro, aguenta carga, testado, rápido, enxuto. Cada achado tem quatro partes: **o que é**, **problema**, **correção** e **se ignorar**. A auditoria devolve no máximo 20 achados por padrão e declara quantos ficaram de fora.

## Skills

| Skill | Entrada | Saída |
|---|---|---|
| `lean.ladder` | Tarefa, proposta, situação e evidência de cada degrau, linhas estimadas, fora de escopo, alcance | Decisão por degrau, teste obrigatório, perguntas (`ultra`), avisos |
| `lean.review` | Diff unificado ou trecho colado, nível e contexto | Achados agrupados em obrigatório/corrigir/opcional, veredito, linhas economizáveis |
| `lean.debt` | Código colado **ou** pasta de código, marcador, marcador legado | Marcadores por arquivo/linha, teto, gatilho, `no-trigger` |
| `lean.audit` | Pasta de código, nível, máximo de arquivos | Inventário, risco, teste, duplicação, export morto, dívida, cobertura |

Nenhuma skill escreve arquivos, instala dependências, executa código analisado ou chama a IA externa.

## Área de código

A leitura por pasta usa a mesma área da engenharia reversa (`storage/user-files/reverse`). Envie arquivos e subpastas pela página **Reversa**; a página **Enxuto** lista as pastas disponíveis. Extensões lidas: JS/TS/JSX/TSX, Python, HTML, CSS e JSON.

## Limites

- Diff de até 200.000 caracteres; código colado de dívida até 500.000 caracteres. O corpo da API é limitado a 2 MB.
- Auditoria: até 400 arquivos, 3 MB no total e 1 MB por arquivo. Ignora `.git`, `node_modules`, `dist`, `build`, `coverage`, `__pycache__`, `.venv`, `venv`, `target` e `vendor`; não segue symlinks.
- A auditoria é estática: achados são candidatos e precisam de confirmação no código real.
- Execução, carga esperada, chamadores fora da árvore e testes não executados ficam sempre declarados como **não verificados**.
- O histórico do Git não é lido: autoria e data de um atalho não entram no levantamento.

## Pelo chat

- “revisar mudança: <diff>” → `lean.review`
- “auditar código app” → `lean.audit`
- “dívida de atalhos em app” → `lean.debt`
- “abrir lean” → página Enxuto

## Preservação

As 36 skills anteriores (texto, cálculo, arquivos, documentos, legislação, produtividade, planejamento, engenharia e engenharia reversa) continuam com o mesmo contrato e as mesmas rotas. Esta adaptação adiciona quatro skills, a rota `/lean` e a página Enxuto, sem alterar o comportamento das existentes. A versão 0.9.0 acrescentou seis skills de governo de agentes e a página Agentes, a 0.10.0 acrescentou cinco skills de estúdio de design e a página Estúdio, a 0.11.0 acrescentou sete skills de direção de arte e a página Direção, a 0.12.0 acrescentou sete skills de diagramas e a página Diagramas, a 0.13.0 acrescentou sete skills de carreira e a página Carreira, a 0.14.0 acrescentou sete skills de navegação assistida e a página Navegador, e a 0.15.0 acrescentou sete skills de escritório assistido e a página Escritório, sem alterar o contrato das skills de engenharia enxuta.
