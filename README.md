# JARVIS — Núcleo pessoal

Central local-first com interface React, skills Python reais, consulta a legislação brasileira e camada opcional de IA externa. Conversa por texto ou voz, gerencia tarefas e memórias, controla foco, executa automações e processa arquivos em uma área isolada.

**Versão atual: 0.12.0.**

## Executar em desenvolvimento

Requisitos: **Node.js 22+** e **Python 3.11+**.

```bash
npm install
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm run dev
```

`npm run dev` inicia os dois processos:

- interface em `0.0.0.0:5173`;
- API Python em `0.0.0.0:8000`.

O navegador usa somente URLs relativas `/api`; o Vite encaminha essas chamadas ao backend. Não é necessário chamar `localhost` a partir do código da interface.

## Legislação brasileira

A página **Legislação** (`/leis`) e os comandos da conversa consultam um recorte local inspirado em [`ctresb/leis`](https://github.com/ctresb/leis), sem clonar o acervo inteiro. A versão inicial contém **oito normas e 4.427 artigos indexados**:

- Constituição Federal;
- Código Civil;
- Código Penal;
- CLT;
- Estatuto da Criança e do Adolescente;
- Código de Defesa do Consumidor;
- LGPD;
- Marco Civil da Internet.

Exemplos:

```text
artigo 49 do CDC
consultar art. 1.046 do Código Civil
pesquisar no CDC sobre direito de arrependimento
pesquisar na legislação sobre proteção de dados
fontes da legislação
```

A busca é lexical, sem acentos, com ranking por cobertura e proximidade. O texto e as referências vêm dos arquivos locais, **não de uma resposta gerada por IA**. Cada consulta oferece a fonte oficial e um aviso para confirmar texto e vigência. O conteúdo é informativo e não substitui o Diário Oficial nem orientação jurídica profissional.

Atribuição, commit de origem e caminhos estão em `server/legal_data/`. O guia de sincronização controlada está em [`docs/LEGISLACAO.md`](docs/LEGISLACAO.md).

## Documentos e produtividade

A página **Documentos** (`/documentos`) cria, lê, envia e baixa DOCX, XLSX, PPTX, PDF e arquivos de texto em uma área confinada. Criação e upload exigem confirmação; a criação pela interface também exige uma simulação prévia. Nenhum conteúdo de documento é enviado à IA pelas skills locais.

A versão 0.4.0 também adiciona mesclagem de PDF, organização de arquivos sem exclusão ou sobrescrita, análise textual de reuniões, changelog por regras e sorteio com aleatoriedade criptográfica. As capacidades foram inspiradas por [`anthropics/skills`](https://github.com/anthropics/skills) e [`ComposioHQ/awesome-claude-skills`](https://github.com/ComposioHQ/awesome-claude-skills), mas são **implementações próprias**: nenhum script desses repositórios é instalado ou executado, e nenhum conector SaaS foi habilitado.

Limites, formatos, comandos e decisões de segurança estão em [`docs/DOCUMENTOS-E-SKILLS.md`](docs/DOCUMENTOS-E-SKILLS.md).

## Workflows de engenharia

A página **Engenharia** (`/engenharia`) reúne oito adaptações locais inspiradas em [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills): especificação, plano vertical, matriz de testes, revisão estática, STRIDE, Core Web Vitals, ADR e gate de release.

Esses workflows não executam código, testes, Git ou deploy. Eles produzem rascunhos, avaliações e bloqueadores com limites explícitos. O repositório upstream é MIT, mas não é instalado; plugins, hooks, scripts e agentes ficam fora do núcleo. Consulte [`docs/ENGENHARIA.md`](docs/ENGENHARIA.md) para contratos e exemplos.

## Planos persistentes

A página **Planos** (`/planejamento`) adapta [`OthmanAdi/planning-with-files`](https://github.com/OthmanAdi/planning-with-files) em cinco skills locais. Cada plano tem `task_plan.md`, `findings.md` e `progress.md` em um diretório isolado. A recuperação exige um ID explícito e lê somente esse bundle, sem histórico de outros agentes ou da sessão do host.

Criação e atualização exigem simulação e confirmação. Atualizações usam um hash otimista dos três arquivos para bloquear escritores obsoletos; concluir fases exige evidência. O gate verifica status e critérios, sem executar comandos encontrados em Markdown. Contratos, exemplos e limites estão em [`docs/PLANEJAMENTO.md`](docs/PLANEJAMENTO.md).

## Engenharia reversa estática

A página **Reversa** (`/reversa`) adapta o modelo de evidências de [`morluto/rea`](https://github.com/morluto/rea) em seis skills locais: inspeção, layout binário, strings, entropia por blocos, análise JavaScript/Electron e comparação de artefatos.

O recorte é deliberadamente **estático**. Parsers próprios leem ELF, PE, Mach-O, ZIP/APK/AAR/JAR, ASAR, WASM, PDF, safetensors, GGUF, PYC e BEAM sem extrair, importar ou executar o alvo. Cada resultado traz SHA-256, fatos observados, achados, cobertura e limitações; `executed` permanece `false`. O REA completo, seu MCP, CLI, hooks e provedores Hopper/Ghidra/IDA/JADX não são instalados. Consulte [`docs/ENGENHARIA-REVERSA.md`](docs/ENGENHARIA-REVERSA.md).

## Engenharia enxuta

A página **Enxuto** (`/lean`) adapta o comportamento de [`DietrichGebert/ponytail`](https://github.com/DietrichGebert/ponytail) em quatro skills locais: a escada do menor caminho, revisão de diff, levantamento de dívida e auditoria de código.

O recorte é **estático e somente leitura**. A escada avalia o que foi declarado e cobra evidência por degrau; a revisão aponta proteção removida, risco novo, teste ausente, duplicação e reimplementação de plataforma; a dívida coleta `shortcut: <limite>, <quando revisar>` e marca `no-trigger`; a auditoria varre até 400 arquivos sem seguir symlinks. Nada é executado, instalado ou enviado à IA. Regra central: preguiçoso com a solução, nunca com a leitura — validação, tratamento de erro, segurança, acessibilidade e o que o usuário pediu não são cortados. O plugin, hooks, comandos npm e telemetria `band`/`board` do upstream não são instalados. Consulte [`docs/LEAN.md`](docs/LEAN.md).

## Governo de agentes

A página **Agentes** (`/agencia`) adapta o modelo de governança de [`paperclipai/paperclip`](https://github.com/paperclipai/paperclip) em seis skills locais. O upstream é um *control plane* para uma empresa de agentes — organograma, tarefas com dono único, heartbeats, orçamentos, rotinas e aprovações. Aqui fica a parte que não exige executar agentes: revisar o que você declara sobre equipe, quadro, dinheiro, parada de trabalho e permissões.

O recorte cobre quatro leis: **recebe heartbeat, foi contratado** (identidade, estado e teto); **todo trabalho tem um dono**; **toda parada tem revisão**; **todo limite tem parada**. A revisão de equipe encontra ciclo de reporte, raiz humana ausente, supervisor inativo, amplitude alta e permissão curinga. A do quadro encontra tarefa sem dono, conclusão sem evidência, bloqueio sem causa, ciclo de dependências e WIP acima do limite. A de orçamento compara limite, gasto e alerta, cobra a parada automática e projeta o mês. A de permissões compara a declaração com a linha de base de 18 grants e 6 negações, incluindo exceções para baixa confiança e agentes gerenciados, cota de criação e override de runtime.

A verificação de parada é o recorte mais fiel: observa uma **subárvore**, calcula uma impressão digital SHA-256 das folhas paradas e das instruções, suprime a revisão quando o hash não mudou e prepara uma única tarefa `watchdog-<slug>-<hash>`. Cada folha é tratada como alegação verificável; instruções customizadas só podem estreitar o mandato, nunca aprovar, gastar, contratar, criar outro watchdog ou acordar a si mesmo. Nada é executado, agendado, conectado ou alterado. O runtime, os adapters, os heartbeats, os plugins e os comandos `pnpm`/Docker do upstream não são instalados. Consulte [`docs/AGENTES.md`](docs/AGENTES.md).

## Estúdio de design

A página **Estúdio** (`/estudio`) adapta o contrato de design de [`nexu-io/open-design`](https://github.com/nexu-io/open-design) em cinco skills locais. O upstream é um workspace colaborativo com daemon, Electron, 26 CLIs, MCP, 277 plugins e geração de artefatos; aqui fica a parte editorial e verificável: o pacote declarado, a acessibilidade medida, a crítica disciplinada e o linter anti-clichê.

O contrato exige `manifest.json` com `schemaVersion` `od-design-system-project/v1`, `DESIGN.md` com pelo menos sete seções substantivas e `tokens.css` com os **56 slots em 14 grupos**. Cor bruta fora de `:root`, tema sem paridade, movimento sem `prefers-reduced-motion` e `scale(0)` são achados. O contraste mede AA 4,5:1 e AAA 7:1 para texto normal (3:1 e 4,5:1 para grande). A crítica valida cinco dimensões fixas com nota inteira 0–10, banda, evidência com referência e as listas manter/corrigir/ganhos rápidos; média acima de 8 vira alerta de inflação. O artefato passa por 26 regras lexicais que reconhecem gradiente roxo, emoji como ícone, métrica inventada, dependência externa e falhas de acessibilidade.

Nada é compilado, renderizado, publicado ou enviado a um provedor. O daemon, o CLI `od`, os plugins, o MCP, o Electron, o Docker e o Sealos do upstream não são instalados. Consulte [`docs/ESTUDIO.md`](docs/ESTUDIO.md) e a licença Apache-2.0 em [`docs/licenses/nexu-io-open-design.txt`](docs/licenses/nexu-io-open-design.txt).

## Direção de arte

A página **Direção** (`/direcao`) adapta a disciplina anti-slop de [`Leonxlnx/taste-skill`](https://github.com/Leonxlnx/taste-skill) em sete skills locais. O upstream sorteia uma entre 20 direções, monta o argumento antes do desenho, mede o deck de copy, roda um linter de ~22 regras, mantém um registro datado de tells e fecha a nota em 14 passes com pesos e tetos. Aqui fica a parte editorial e verificável do mesmo método.

O sorteio é determinístico: semente SHA-256 do briefing, setor, tom e seções, três opções entre **12 direções próprias em português** e uma ficha com herói, tipografia, paleta, imagens, movimento, blueprint por papel de seção, armadilhas e redesenhos registrados — redesenhar exige motivo com 20 caracteres ou mais. O argumento exige **uma afirmação e uma prova por seção**, bloqueia número sem fonte e cobra a cota do título (32 caracteres confortáveis, 42 no limite). O deck de copy mede título, apoio, corpo, ações e navegação, e reconhece formas proibidas e micro-tipografia. O linter aplica **29 regras lexicais** em página ou app, com isenções para código, tabelas, formulários, `data-ui` e `taste-skill-ignore`. O registro de tells tem **25 motivos em três ondas** (2023, 2024–2025, 2026) e devolve a onda dominante. O júri pondera design 40, usabilidade 30, criatividade 20 e conteúdo 10, aplica **16 tetos** e devolve a banda, a perda e a ordem de correção.

Nada é renderizado, compilado ou publicado. `npx skills add`, plugins de Claude/Codex, `install.sh`, `draw.mjs`, `inspect.mjs`, `assets.mjs` e `scenes.mjs` não são instalados nem executados. Consulte [`docs/DIRECAO.md`](docs/DIRECAO.md) e a licença MIT em [`docs/licenses/leonxlnx-taste-skill.txt`](docs/licenses/leonxlnx-taste-skill.txt).

## Diagramas

A página **Diagramas** (`/diagramas`) adapta [`tt-a1i/archify`](https://github.com/tt-a1i/archify) em sete skills locais. O upstream transforma uma ideia em um diagrama interativo de página única, com dez tipos, IR JSON validado, geometria medida e um contrato de entrega em gates. Aqui fica o recorte que sobrevive sem navegador: **tipo, IR, layout, desenho, legenda e entrega**.

Os dez tipos são arquitetura, fluxo de trabalho, sequência, fluxo de dados, ciclo de vida, entidades, árvore, classes, linha do tempo e cascata. O IR é escrito em português (`tipo`, `titulo`, `componentes`, `conexoes`), mas também aceita o formato do upstream (`diagram_type`, `meta`, `components`, `connections`) e avisa quando converte. O layout é determinístico e mede **cruzamento, colisão, folga de rótulo, leque e preenchimento**; a folga de uma aresta horizontal é `6,5 px × caracteres + 21 px`, e um canvas acima de 1240 px — ou 1790 px se for 1,55× mais largo que alto — perde o piso de leitura.

O desenho sai em **HTML autocontido com SVG inline**, sem script, fonte remota ou imagem externa, além de SVG puro, Mermaid, texto e DOT. Quatro presets (Clássico, Sinal, Planta e Editorial) mudam papel, tinta e acento sem mudar a topologia, e a legenda automática lista só as variantes que o desenho usa. O contrato de entrega roda **validar → entregar → checar → navegador → revisão visual**, para no primeiro gate falho e nunca marca como feito o que não foi: navegador, captura e revisão visual aparecem como não executados quando não aconteceram.

Nada do upstream é instalado ou executado: sem `npx skills add`, `archify.zip`, `bin/archify.mjs`, `finalize`, `visual-check`, plugins DSH ou Chrome de inspeção. Consulte [`docs/DIAGRAMAS.md`](docs/DIAGRAMAS.md) e a licença MIT em [`docs/licenses/tt-a1i-archify.txt`](docs/licenses/tt-a1i-archify.txt).

## Ativar a IA externa

A integração usa o formato **OpenAI Chat Completions**, aceito por diferentes provedores. Copie o exemplo e preencha os valores no servidor:

```bash
cp .env.example .env
```

```dotenv
JARVIS_AI_PROVIDER=Seu provedor
JARVIS_AI_BASE_URL=https://endereco-do-provedor/v1
JARVIS_AI_MODEL=nome-do-modelo
JARVIS_AI_API_KEY=chave-configurada-somente-no-servidor
```

Reinicie `npm run dev` depois de editar `.env`. A chave nunca é enviada ao navegador, ao Git ou ao conteúdo das respostas. Sem essa configuração, a interface informa **“IA não configurada”** e mantém os comandos locais.

Mais detalhes em [`docs/CONFIGURAR-IA.md`](docs/CONFIGURAR-IA.md).

## Skills Python disponíveis

| Skill | Função |
|---|---|
| `text.analyze` | Palavras, caracteres, frases, leitura estimada e termos frequentes |
| `text.transform` | Maiúsculas, minúsculas, título e slug |
| `data.calculate` | Matemática por AST, sem executar código |
| `files.list` | Lista arquivos da área isolada com URLs de download |
| `files.read` | Lê TXT, MD, JSON, CSV ou LOG permitidos |
| `files.write` | Grava textos com simulação e confirmação |
| `files.organize` | Planeja e move arquivos por tipo, sem excluir ou sobrescrever |
| `document.read` | Extrai texto de DOCX, XLSX, PPTX e PDF |
| `document.create` | Cria DOCX, XLSX, PPTX e PDF com simulação e confirmação |
| `pdf.merge` | Mescla PDFs com validação e confirmação |
| `meeting.analyze` | Métricas determinísticas de transcrições de reunião |
| `changelog.generate` | Agrupa mensagens de commit por regras locais |
| `random.pick` | Sorteia participantes com `secrets.SystemRandom` |
| `engineering.spec` | Produz rascunho de especificação com alertas de qualidade |
| `engineering.plan` | Ordena fatias e dependências, com detecção de ciclos |
| `engineering.tests` | Desenha matriz de testes sem fingir execução |
| `engineering.review` | Revisa padrões estáticos sem executar o código |
| `engineering.threat-model` | Gera perguntas STRIDE por fronteira de confiança |
| `engineering.webvitals` | Classifica LCP, INP e CLS informados |
| `engineering.adr` | Produz ADR com alternativas e consequências |
| `engineering.release` | Avalia bloqueadores de release sem executar deploy |
| `planning.create` | Cria plano persistente em três arquivos, com confirmação |
| `planning.list` | Lista planos sem seleção automática |
| `planning.resume` | Recupera objetivo, fase, próximo passo e arquivos por ID |
| `planning.update` | Atualiza fases e anotações com hash otimista e confirmação |
| `planning.gate` | Verifica fases e critérios sem executar comandos |
| `reverse.inspect` | Identifica formato, SHA-256, entropia e contagens do artefato |
| `reverse.layout` | Lista seções, segmentos, entradas e imports sem executar o arquivo |
| `reverse.strings` | Extrai strings ASCII/UTF-16LE com offsets e filtro |
| `reverse.entropy` | Mede entropia por blocos sem descompactar ou decifrar |
| `reverse.javascript` | Mapeia módulos, imports, IPC e fronteiras Electron por regex estática |
| `reverse.compare` | Compara identidade, estruturas e strings sem alegar equivalência |
| `lean.ladder` | Classifica o menor caminho declarado e exige evidência por degrau |
| `lean.review` | Revisa diff ou trecho com quatro partes por achado e veredito |
| `lean.debt` | Coleta `shortcut:`/`ponytail:` e sinaliza atalhos sem gatilho |
| `lean.audit` | Audita árvore de código, cobertura e superfície morta sem executar |
| `agency.roster` | Revisa raiz humana, ciclos, supervisão e permissões da equipe declarada |
| `agency.board` | Revisa dono, evidência, bloqueios, dependências e WIP do quadro |
| `agency.budget` | Compara limite, gasto, alerta, parada automática e projeção |
| `agency.watchdog` | Calcula impressão digital da subárvore parada e prepara uma revisão |
| `agency.permissions` | Confere grants, negações, exceções, cota e override de runtime |
| `agency.defaults` | Publica a linha de base de permissões e as exceções |
| `studio.contract` | Confere manifesto, prosa e os 56 slots de tokens, com temas e movimento |
| `studio.contrast` | Mede contraste WCAG AA/AAA de pares declarados, inclusive texto grande |
| `studio.critique` | Valida cinco notas com evidência, bandas e manter/corrigir/ganhos rápidos |
| `studio.artifact` | Aplica 26 regras anti-clichê a um HTML de arquivo único, sem renderizar |
| `studio.defaults` | Publica o esquema de tokens, bandas, dimensões, movimento e limites |
| `taste.direction` | Sorteia três direções determinísticas e entrega a ficha da escolhida |
| `taste.argument` | Confere afirmação e prova por seção, título, apoio e ação |
| `taste.copy` | Mede o deck de copy e aponta formas proibidas e micro-tipografia |
| `taste.lint` | Aplica 29 regras lexicais a HTML/CSS, em página ou app |
| `taste.tells` | Confronta o material com 25 tells datados em três ondas |
| `taste.judge` | Pondera quatro dimensões, aplica tetos e devolve a ordem de correção |
| `taste.library` | Publica direções, vocabulário, tetos e ondas |
| `diagram.type` | Escolhe entre dez tipos e devolve esqueleto JSON |
| `diagram.spec` | Valida o IR e devolve o IR normalizado |
| `diagram.layout` | Mede cruzamentos, colisões, folga e canvas |
| `diagram.render` | Gera HTML, SVG, Mermaid, texto ou DOT |
| `diagram.legend` | Compõe legenda e presets com contraste |
| `diagram.delivery` | Roda os gates e para no primeiro erro |
| `diagram.library` | Publica tipos, vocabulários e limites |
| `system.status` | Versão e horário do ambiente, sem variáveis ou credenciais |
| `legal.search` | Busca por tema nos textos do recorte jurídico |
| `legal.article` | Consulta exata de artigo, incluindo milhares e sufixos |
| `legal.sources` | Catálogo de documentos, origem e fontes oficiais |

São **65 skills Python**. A página **Skills** gera os formulários a partir dos esquemas Pydantic publicados pela API. As skills jurídicas abrem Legislação; leitura e criação de documentos abrem Documentos; workflows de engenharia abrem Engenharia; planejamento persistente abre Planos; análise reversa abre Reversa; engenharia enxuta abre Enxuto; governo de agentes abre Agentes; estúdio de design abre Estúdio; direção de arte abre Direção; diagramas abrem Diagramas; mesclagem e organização usam o executor genérico com simulação. Os arquivos ficam em `storage/user-files`; a área reversa usa `storage/user-files/reverse`, separada dos documentos. O confinamento não permite `..`, caminhos absolutos, arquivos ocultos ou fuga por symlink.

## Como a conversa escolhe a origem

1. O parser local verifica comandos determinísticos: tarefas, memória, foco, cálculo, legislação, documentos, engenharia, planos, análise reversa, engenharia enxuta, governo de agentes, estúdio de design, direção de arte, diagramas, produtividade, pesquisa e automações.
2. Comandos como `analisar texto ...`, `artigo 49 do CDC`, `ler PDF ...`, `revisar código python: ...`, `avaliar web vitals ...`, `retomar plano ID`, `inspecionar artefato ...`, `revisar mudança: <diff>` e `auditar código app` são enviados à skill Python correspondente; `abrir agentes` leva à página de governo e `abrir estúdio` à página de design.
3. Consultas jurídicas, leituras de arquivos, análises de artefatos, revisões de design, reuniões, revisões de código ou de mudança, auditorias, Web Vitals e recuperação de planos reconhecidos não são enviados à IA externa.
4. `organizar arquivos` executa somente simulação no chat. Criação de documentos e gravação de planos orientam o uso das páginas dedicadas; nenhum comando contorna a confirmação visual.
5. Pedidos desconhecidos usam a IA externa **somente se ela estiver configurada e ativada**.
6. Se não houver IA disponível, o JARVIS informa a limitação em vez de inventar uma resposta.

As mensagens identificam `SKILL PYTHON` ou `IA EXTERNA` quando essas origens são usadas. Tarefas e notas só são incluídas como contexto da IA se a opção correspondente for ativada nas configurações; ela vem desativada por padrão.

## Recursos da interface

- conversa por texto e voz, com resposta falada opcional;
- tarefas com prioridade, prazo, filtros e persistência;
- memórias com categorias, busca e backup JSON;
- ciclos de foco com pausa e total diário;
- automações manuais ou agendadas enquanto o app está aberto;
- página de Legislação com busca, leitura de artigos e fontes;
- página de Documentos com upload, download, leitura e criação confirmada;
- produtividade local para reuniões, changelogs, sorteios, PDFs e organização;
- página de Engenharia com oito workflows locais e evidências explícitas;
- página de Planos com recuperação por ID, três arquivos, hash otimista e gate;
- página de Reversa com upload confinado, inspeção, layout, strings, entropia, análise JavaScript/Electron e comparação;
- página Enxuto com escada, revisão de diff, dívida de atalhos e auditoria estática;
- página Agentes com equipe, quadro, orçamento, verificação de parada e permissões;
- página Estúdio com contrato de design, contraste WCAG, crítica em cinco dimensões e linter anti-clichê;
- página Direção com sorteio de direções, argumento, deck de copy, linter, tells datados e júri ponderado;
- página Diagramas com tipo, IR validado, layout medido, desenho portátil, legenda e contrato de entrega;
- catálogo unificado de skills locais e Python;
- `dryRun`, confirmação e resultado detalhado das skills;
- paleta global com `Ctrl/Cmd + K`;
- preferências de cor, voz, notificações e redução de movimento;
- layout desktop e móvel.

## Verificações

```bash
npm test          # Vitest + Pytest
npm run build     # TypeScript + bundle de produção
npm audit         # dependências JavaScript
```

Os testes cobrem o parser em português, calculadora, catálogo da API, execução real das skills, corpus jurídico, documentos, upload/download, produtividade, normalização numérica, grafos de dependências, matriz de testes, revisão estática sem exposição de segredos, STRIDE, Web Vitals, ADR, gate de release, recuperação persistente, isolamento de planos, hash otimista, evidências e gate determinístico, parsers ELF/PE/Mach-O/ZIP/ASAR/WASM com artefatos sintéticos, entropia, strings, análise JavaScript, bloqueio de symlink na árvore, confirmação de upload reverso, `path traversal`, escada com evidência por degrau, proteção removida e risco novo em diffs, marcadores `shortcut:` sem gatilho, auditoria com limite de arquivos e bloqueio de symlink, raiz humana e ciclos de reporte, quadro com dono/evidência/bloqueios, orçamento com hard stop e projeção, impressão digital e supressão do watchdog, mandato não ampliável, linha de base e exceções de permissões, contrato de design com 56 slots e temas, manifesto inseguro, prosa rasa, contraste AA/AAA, cinco dimensões com evidência e inflação, 26 regras anti-clichê no HTML, determinismo do sorteio de direções, ficha por seção, prova sem fonte, orçamento de título, deck de copy, 29 regras lexicais com isenções e modo app, 25 tells em três ondas, pesos e tetos do júri, e provedor de IA com respostas simuladas. O estado desta versão tem **40 testes web e 261 testes de API**. Nenhum teste exige uma chave real nem faz cobrança em provedores.

## Produção

```bash
npm run build
npm start
```

A API em `0.0.0.0:8000` serve a pasta `dist` e as rotas `/api`, incluindo fallback da SPA.

## Estrutura

```text
src/                         # interface React e estado local
├── pages/LegalPage.tsx      # pesquisa, artigos e fontes
├── pages/DocumentsPage.tsx  # biblioteca, upload e criação confirmada
├── pages/EngineeringPage.tsx # oito workflows de engenharia
├── pages/PlanningPage.tsx   # planos persistentes e gate
├── pages/ReversePage.tsx    # inspeção, layout, strings, entropia e JavaScript
├── pages/LeanPage.tsx       # escada, revisão, dívida e auditoria estática
├── pages/AgencyPage.tsx     # equipe, quadro, orçamento, parada e permissões
├── pages/EstudioPage.tsx    # contrato, contraste, crítica e anti-clichê
├── pages/TastePage.tsx      # direção, argumento, copy, regras, tells e júri
└── lib/skillResults.ts      # resultados Python apresentados no chat
server/
├── app.py                   # rotas, upload/download, rate limit e SPA
├── ai.py                    # provedor OpenAI-compatible
├── workspace.py             # confinamento e limites de arquivos
├── documents.py             # adaptadores próprios de OOXML e PDF
├── productivity.py          # reuniões, changelogs e sorteio
├── engineering.py           # workflows determinísticos de engenharia
├── planning.py              # bundles persistentes, recuperação, hash e gate
├── reverse.py               # parsers estáticos, evidências, strings e entropia
├── lean.py                  # escada, revisão de diff, dívida e auditoria
├── agency.py                # equipe, quadro, orçamento, watchdog e permissões
├── studio.py                # contrato, contraste, crítica e linter de artefato
├── taste.py                 # direções, argumento, júri e biblioteca
├── taste_rules.py           # copy, 29 regras lexicais e registro de tells
├── diagram.py               # IR, layout medido, SVG e contrato de entrega
├── review.py                # achados, contagens, veredito e Markdown compartilhados
├── legal_corpus.py          # parser, índice e busca lexical
├── legal_data/              # oito normas, índice e atribuição
├── skill_registry.py        # allowlist, Pydantic e 58 skills
└── tests/                   # API, documentos, corpus e provedor
scripts/
├── python.mjs           # detecta .venv e executa o Python correto
└── sync_legal.py        # sincronização manual do recorte declarado
tests/                   # testes do núcleo TypeScript
docs/                    # arquitetura, legislação, IA e inventário legado
```

## Limites desta etapa

- A IA externa só funciona depois da configuração do provedor no `.env`.
- O acervo jurídico é um recorte, não uma base completa nem um serviço de atualização automática.
- A busca jurídica é lexical e não interpreta casos concretos; texto e vigência precisam ser conferidos na fonte oficial.
- Documentos são limitados a 25 MB; PDF não tem OCR e análise de reunião não transcreve áudio nem faz diagnóstico.
- Changelog usa somente mensagens fornecidas, não o histórico do Git; o sorteio não possui auditoria pública externa.
- Revisão de código é heurística; Web Vitals e gates usam valores declarados, sem coleta, teste ou deploy automático.
- Planos são limitados a 100 KB por arquivo; o hash bloqueia escritores obsoletos, mas o lock local não é coordenação distribuída entre servidores.
- Análise reversa é estática e baseada em parsers próprios: não descompila, não executa, não extrai contêineres e não cobre formatos sem parser dedicado. Evidência não substitui laudo pericial ou atestado de malware.
- Engenharia enxuta é estática: a escada avalia só o que foi declarado, a revisão e a auditoria produzem candidatos que exigem confirmação no código real. Execução, carga, testes e chamadores fora da árvore não são verificados; o histórico do Git não é lido.
- Estúdio de design é estático: não compila tokens, não lê o repositório do pacote, não renderiza o HTML nem publica artefato. O esquema de 56 slots é embutido, o parser de CSS cobre blocos simples e o linter é lexical, sujeito a falso positivo.
- Diagramas são gerados a partir do que você declara: sem navegador, o piso de texto e o overflow são estimativas, e Mermaid/DOT são exportados como texto, não renderizados aqui.
- Direção de arte é estática e declarada: a ficha não é desenhada, o sorteio não vê imagens, a quebra de linha do título é estimada por caracteres e as notas do júri vêm de quem revisa. Toda varredura é lexical e pode ter falso positivo.
- Governo de agentes é declarativo: não executa agentes, não lê runtime, banco, identidade ou fatura e não altera permissões. Orçamento não converte moeda nem incorpora retries; a projeção é linear. A impressão digital cobre a parada e as instruções, não arquivos ou anexos, e a varredura de instruções é lexical.
- Rotinas agendadas dependem do aplicativo aberto; não há worker 24 horas.
- Reconhecimento de voz depende do navegador.
- A migração das rotinas antigas do Lino está fora do escopo atual.
- Nenhuma publicação em rede social ou renovação de sessão foi ativada.

A ampliação do corpus deve ser feita por sincronização controlada, revisão do diff e novos testes.
