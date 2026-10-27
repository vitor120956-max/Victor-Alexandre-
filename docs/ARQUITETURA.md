# Arquitetura do núcleo

## Visão geral

```text
Texto ou voz
     │
     ▼
Parser local ───────────────► skills do navegador
     │                        tarefas, memória, foco, automações
     │
     ├── comando Python ────► FastAPI ─► allowlist ─► Pydantic ─► skill
     │                            │                         ├─ texto/cálculo
     │                            │                         ├─ arquivos isolados
     │                            │                         ├─ status
     │                            │                         ├─ documentos e PDF
     │                            │                         ├─ produtividade local
     │                            │                         ├─ workflows de engenharia
     │                            │                         └─ legislação
     │                            │                            └─ corpus local
     │                            └─ timeout + rate limit + auditoria
     │
     └── pergunta aberta ───► IA externa opcional
                              (somente se configurada e ativada)
```

Cada resposta registra sua origem. A IA generativa não recebe autoridade para executar ações: ela produz texto; somente as skills validadas executam efeitos. Consultas jurídicas reconhecidas seguem para o corpus e não para o provedor externo.

## API Python

### Rotas

- `GET /api/health` — disponibilidade, versão e quantidade de skills.
- `GET /api/skills` — catálogo e esquemas de entrada.
- `POST /api/skills/{id}/execute` — execução allowlist.
- `POST /api/files/upload` — multipart confinado, com streaming, limite e confirmação.
- `GET /api/files/download` — download de arquivo regular dentro da área autorizada.
- `GET /api/ai/status` — provedor e situação, nunca a chave.
- `POST /api/ai/chat` — conversa externa com histórico limitado.

### Execução de skills

O corpo usa este contrato:

```json
{
  "parameters": { "text": "Conteúdo" },
  "dryRun": false,
  "confirmed": false
}
```

O registro associa cada ID a um modelo Pydantic e a uma função permitida. Não existe endpoint para shell, importação dinâmica ou caminho arbitrário de módulo. Execuções síncronas usam thread separada e timeout de oito segundos.

### Arquivos

As skills e os endpoints de arquivo usam uma raiz dedicada (`storage/user-files` por padrão). O caminho resolvido precisa permanecer dentro dessa raiz. São bloqueados:

- caminhos absolutos, `..` e componentes ocultos;
- formatos fora de TXT, MD, JSON, CSV, LOG, DOCX, XLSX, PPTX e PDF;
- textos simples acima de 200 KB e documentos acima de 25 MB;
- upload ou gravação sem confirmação;
- sobrescrita sem opção explícita;
- fuga por symlink e destinos que não sejam arquivos regulares.

`files.write`, `document.create`, `pdf.merge` e `files.organize` aceitam `dryRun`. Upload e download compartilham `server/workspace.py` com as skills. A escrita de documentos usa arquivo temporário e substituição no destino; a organização não possui operação de exclusão ou sobrescrita.

## Documentos e produtividade

`server/documents.py` contém adaptadores próprios baseados em `python-docx`, `openpyxl`, `python-pptx`, `pypdf` e ReportLab. OOXML passa por limites de entradas e expansão antes da leitura. XLSX criado pelo JARVIS trata entradas como texto, não fórmulas. Nenhuma macro, script ou link é executado.

`server/productivity.py` implementa métricas textuais de reunião, changelog por regras e sorteio com `secrets.SystemRandom`. Essas operações não chamam IA nem serviços externos. No chat, a organização de arquivos é sempre uma simulação; a criação de documentos direciona o usuário à confirmação visual.

As referências de `anthropics/skills` e `ComposioHQ/awesome-claude-skills` são comportamentais. Nenhum código desses catálogos é carregado em runtime. Detalhes e limites estão em [`DOCUMENTOS-E-SKILLS.md`](DOCUMENTOS-E-SKILLS.md).

## Workflows de engenharia

`server/engineering.py` implementa oito operações determinísticas inspiradas em `addyosmani/agent-skills` (MIT). Specs, planos, matrizes, revisões, STRIDE, Web Vitals, ADRs e gates usam somente os dados fornecidos na requisição. Não há acesso implícito ao repositório, execução de código, comandos de Git, coleta de métricas ou deploy.

A revisão estática não inclui os valores de possíveis segredos no relatório. Planos validam o grafo de dependências; gates distinguem checklist bloqueado de pronto para aprovação humana. As oito skills não possuem efeitos colaterais e nunca chamam IA. Detalhes estão em [`ENGENHARIA.md`](ENGENHARIA.md).

## Estúdio de design

`server/studio.py` implementa cinco operações determinísticas inspiradas em `nexu-io/open-design` (Apache-2.0). O contrato lê manifesto, `DESIGN.md` e `tokens.css`; o contraste calcula razão WCAG; a crítica valida as cinco dimensões; o artefato passa por 26 regras lexicais. `server/review.py` concentra achados, contagens, veredito e Markdown compartilhados com o governo de agentes.

Nenhum daemon, CLI, plugin, MCP, runtime de agente ou provedor do upstream é instalado ou executado. O HTML não é renderizado e o CSS não é compilado. Todos os resultados são somente leitura e marcam `executed: false`. Detalhes e limites estão em [`ESTUDIO.md`](ESTUDIO.md).

## Direção de arte

`server/taste.py` e `server/taste_rules.py` implementam sete operações determinísticas inspiradas em `Leonxlnx/taste-skill` (MIT). O sorteio de direções usa SHA-256 do briefing, setor, tom e seções; o argumento exige prova por seção; o deck de copy e o linter aplicam limites e regras lexicais; o registro de tells é datado em três ondas; o júri pondera quatro dimensões e aplica 16 tetos. Os dois módulos reaproveitam `server/review.py` para achados, contagens, veredito e Markdown.

Nenhum script Node, navegador, plugin, `npx skills`, `draw.mjs`, `inspect.mjs` ou `scenes.mjs` do upstream é instalado ou executado. Nada é renderizado, compilado ou publicado, e todos os resultados marcam `executed: false`. Detalhes e limites estão em [`DIRECAO.md`](DIRECAO.md).

## Diagramas

`server/diagram.py` implementa sete operações inspiradas em `tt-a1i/archify` (MIT). O módulo lê o IR em PT-BR ou o IR do upstream, valida ids e pontas, posiciona os nós por faixa, raia, estágio, nível, matriz ou relógio, roteia as arestas em ortogonal e mede cruzamento, colisão, folga de rótulo, leque e preenchimento. O desenho sai como SVG inline dentro de um HTML autocontido, ou como SVG puro, Mermaid, texto e DOT. O contrato de entrega roda os gates em ordem e declara o que não foi verificado.

As rotas são `/api/skills/diagram.type`, `diagram.spec`, `diagram.layout`, `diagram.render`, `diagram.legend`, `diagram.delivery` e `diagram.library`. Nenhuma abre navegador, baixa template, executa CLI ou grava arquivo. A página `/diagramas` consome essas respostas e mostra a prévia do HTML em um `iframe` com `sandbox=""`. `docs/DIAGRAMAS.md` documenta o IR, os dez tipos e os limites.

`server/editorial.py` implementa sete operações da camada editorial inspiradas em `cathrynlavery/diagram-design` (MIT). O módulo guarda o catálogo dos **45 tipos** e dos **nove padrões semânticos** com orçamento por tipo, resolve a marca em **11 papéis de cor** medindo contraste WCAG 2.x e propondo o menor ajuste de luminosidade, aplica **12 anti-padrões** lexicais ao HTML/SVG, mede as **seis regras de conector** na geometria declarada, lê Mermaid, draw.io e Excalidraw com parsers próprios e escreve o **recibo de fidelidade** da escada de degradação, e confere o contrato de entrega (SVG acessível, `viewBox` do preset, `min-width`, rolagem local, impressão e rampa). Nada é renderizado, descomprimido ou executado: as contas são feitas em Python sobre o texto da requisição, e tudo volta com `executed: false`.

As rotas são `/api/skills/editorial.tipo`, `editorial.marca`, `editorial.lint`, `editorial.conector`, `editorial.importar`, `editorial.entrega` e `editorial.catalogo`. A página `/diagramas` tem duas camadas — desenho por IR e camada editorial — e mantém a mesma regra: o navegador só envia texto para a API local.

## Curadoria de listas

`server/curadoria.py` implementa seis operações de curadoria inspiradas em `hesreallyhim/awesome-claude-code` (CC BY-NC-ND 4.0). Como a licença do upstream não permite derivados, o módulo não carrega o catálogo, as categorias nem as descrições de lá: o que foi implementado é o mecanismo. Ele normaliza o cabeçalho de 12 colunas (português ou o inglês do schema original), valida a entrada contra a regra de maturidade — 14 dias com desenvolvimento ativo ou 100 estrelas —, recusa URL que quebra Markdown, categoria fechada, subcategoria órfã, acesso pago e descrição com emoji, segunda pessoa ou superlativo, e devolve a linha pronta com ID opaco de oito dígitos hexadecimais. O catálogo é agrupado na ordem da configuração, com órfãs, vazias e nunca checadas visíveis e nada descartado em silêncio; o README é derivado do CSV com âncoras no padrão do GitHub e escape de colchete e barra; o ticker compara dois snapshots `dono/repo,estrelas`, aplica as proteções contra imitação de produto e provável cópia de código-fonte e ordena por variação; a higiene audita dez checagens, de ID repetido a estagnação sem data. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/curadoria.entrada`, `curadoria.catalogo`, `curadoria.readme`, `curadoria.ticker`, `curadoria.higiene` e `curadoria.regras`. Nenhuma chama API de repositório, busca licença na rede ou grava arquivo; todas marcam `executed: false` e `readOnly: true`. A página `/curadoria` só envia o texto colado. Detalhes em [`CURADORIA.md`](CURADORIA.md).

## Marketing mensurável

`server/marketing.py` implementa sete operações determinísticas inspiradas em `coreyhaines31/marketingskills` (MIT). O upstream é uma biblioteca de 52 skills de redação; daqui só entrou a **parte mensurável**, reimplementada em Python — nenhum texto foi copiado e nenhuma skill de copy foi portada. O módulo calcula o funil e a economia unitária a partir das taxas informadas (impressões, cliques, leads, clientes, CAC, ROAS, payback, LTV/CAC), a sensibilidade de cada alavanca até o CAC alvo e o orçamento que a meta de ARR exige; dimensiona teste A/B pela fórmula de duas proporções, com alfa corrigido por Bonferroni para múltiplas variantes e duração que respeita o piso de uma semana (B2C) ou de dois ciclos (B2B); confere a URL de campanha (esquema, três parâmetros obrigatórios, minúsculas, hífen, `medium` do vocabulário, repetição, PII e encurtador) e devolve a URL canônica; revisa assunto, pré-cabeçalho, CTA, descadastro e as marcas de texto gerado do e-mail; audita o HTML entregue sem executar JavaScript (título, description, H1, hierarquia, alt, canonical, idioma, JSON-LD, links e os sinais que um motor de resposta extrai); e conta caractere por peça contra os limites de Google, Meta e LinkedIn, recusando afirmação não verificável. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/marketing.orcamento`, `marketing.teste`, `marketing.utm`, `marketing.email`, `marketing.seo`, `marketing.anuncio` e `marketing.regras`. Nenhuma abre conta de anúncio, lê pixel, chama CRM ou grava arquivo; todas marcam `executed: false` e `readOnly: true`. A página `/marketing` só envia número ou texto colado. Detalhes em [`MARKETING.md`](MARKETING.md).

`server/ciencia.py` implementa sete operações determinísticas inspiradas em `K-Dense-AI/scientific-agent-skills` (MIT, 177 skills). Nenhum pacote do upstream foi importado e nenhum script é chamado: as contas vêm das fórmulas publicadas e a conferência é lexical e numérica sobre o texto colado. O módulo calcula poder e amostra para duas proporções ou duas médias com alfa ajustado por multiplicidade, perda esperada e efeito de desenho por cluster; lê o relato estatístico (p exato, IC, dispersão, denominador, equivalência sem margem, causa afirmada); audita o desenho em 14 itens ponderados por tipo e aponta pseudorreplicação e confundimento; checa os nove itens de reprodutibilidade; valida método analítico contra os critérios do ICH M10 (cromatográfico e LBA) com recuperação, RSD, R², LOD e LOQ; e confere o manuscrito contra CONSORT 2025, STROBE, STARD, PRISMA 2020 e ARRIVE 2.0, incluindo as afirmações de cura, risco zero e prova. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/ciencia.amostra`, `ciencia.estatistica`, `ciencia.desenho`, `ciencia.reprodutibilidade`, `ciencia.validacao`, `ciencia.manuscrito` e `ciencia.regras`. Nenhuma baixa dado, acessa repositório ou DOI, executa análise, grava arquivo ou consulta modelo; todas marcam `executed: false` e `readOnly: true`. Detalhes em [`CIENCIA.md`](CIENCIA.md).

## Confiança em skill de terceiro

`server/confianca.py` implementa sete operações determinísticas inspiradas em `VoltAgent/awesome-openclaw-skills` (MIT, 5.400+ skills indexadas). Nenhuma skill do índice é baixada, importada ou executada: o que entrou do upstream é o **formato da ficha** e as regras editoriais do próprio repositório, reimplementadas em Python. O módulo lê o frontmatter e o corpo do `SKILL.md` (nome, descrição, licença, versão, autoria, ferramentas e requisitos de ambiente); varre quinze classes de risco — destruição, execução remota, credencial, exfiltração, injeção, ofuscação, proteção desligada, privilégio, persistência, escrita fora do escopo, integridade, segredo em claro, telemetria, permissão ampla e instalação — com nota de 0 a 100 e bloqueio para credencial lida e enviada para fora no mesmo material; compara as oito capacidades declaradas com as usadas; confere a receita de instalação linha por linha (versão fixa ou flutuante, download canalizado, `sudo`, escopo global, script de instalação); audita o índice contra as dez regras do `CONTRIBUTING` de origem; e caça duplicata por nome, link, proximidade e descrição. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/confianca.ficha`, `confianca.risco`, `confianca.permissao`, `confianca.instalacao`, `confianca.indice`, `confianca.duplicata` e `confianca.regras`. Nenhuma abre link, baixa pacote, executa comando ou consulta modelo; todas marcam `executed: false` e `readOnly: true`. A página `/confianca` só envia o texto colado. Detalhes em [`CONFIANCA.md`](CONFIANCA.md).

## Contexto de conversa

`server/contexto.py` implementa sete operações determinísticas inspiradas no subsistema de contexto do `CherryHQ/cherry-studio` (AGPL-3.0). Nenhuma linha do upstream foi copiada e nenhum tokenizador BPE é usado: a regra foi reimplementada em Python e a estimativa é lexical, declarada. O módulo divide a janela entre prompt e resposta pela precedência da reserva (chamada → assistente → teto do modelo só no Anthropic) com piso de 20% para a entrada; mede a conversa e aplica as fórmulas de imagem por dialeto e de áudio/vídeo por segundo; corta o histórico por turno atômico sem partir chamada e resultado; saneia órfão, resultado faltante e abertura fora de ordem; prepara o resumo de retenção com stub progressivo de 4.000 a 0 caracteres; e ancora o contexto em `total − entrada + inicial`, com custo por milhão e por hop. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/contexto.orcamento`, `contexto.tokens`, `contexto.corte`, `contexto.higiene`, `contexto.resumo`, `contexto.uso` e `contexto.regras`. Nenhuma chama provedor, baixa tokenizador, grava arquivo ou lê conversa do banco; todas marcam `executed: false` e `readOnly: true`. A página `/contexto` só envia o texto colado. Detalhes em [`CONTEXTO.md`](CONTEXTO.md).

## Seleção de skills

`server/selecao.py` implementa sete operações determinísticas inspiradas no AAS Core do `sickn33/agentic-awesome-skills` (MIT, 2.743 skills em 114 categorias). O Core entrega a descoberta e a validação do manifesto, mas recusa pontuar; esta camada pontua com a conta à vista. O módulo lê o briefing contra as dez dimensões de capacidade do contrato de cobertura, ranqueia o catálogo com BM25 (k1 1,2 e b 0,75, peso 3 no nome, 2 na categoria e 1 na descrição, plural e singular indexados juntos), valida a stack — id inexistente, repetido, acima de 128, alvo incompatível, lacuna, sobreposição e orçamento de risco de 0 a 3 pontos por classe —, ordena fases com artefato e checagem de saída, mapeia cobertura por dimensão e audita a saúde do índice. Aceita o `skills_index.json`, um objeto com `skills`, listas de ids e as linhas compactas `id | categoria [| risco] | descrição`. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/selecao.brief`, `selecao.buscar`, `selecao.stack`, `selecao.plano`, `selecao.cobertura`, `selecao.catalogo` e `selecao.regras`. Nenhuma baixa catálogo, instala skill, grava manifesto ou consulta modelo; todas marcam `executed: false` e `readOnly: true`. O teto de texto é 1,8 MB e o de entradas é 3.000. A página `/selecao` só envia o que foi colado. Detalhes em [`SELECAO.md`](SELECAO.md).

## Revisão de código

`server/revisao.py` implementa sete operações determinísticas inspiradas no `alibaba/open-code-review` (Apache-2.0). O upstream é híbrido — pipeline determinístico mais agente —, e a camada local cobre a parte determinística: parse do diff unificado com hunks (contagem omitida vale 1, `\ No newline` é ignorado, renomeação lida pelo cabeçalho), classificação do caminho em doze classes com peso e decisão de revisar, agrupamento por união-find em lotes que juntam código e teste e as locales do mesmo pacote, normalização de severidade em quatro níveis e de fonte em duas, verificação da âncora de cada comentário contra as linhas do hunk com tolerância de duas linhas e precisão mínima de 80%, comparação lexical entre regra e agente para achar duplicata e conflito de gravidade, cobertura de arquivos revisados contra os revisáveis com piso de 60% e geração do `rule.json` com uma regra em prosa por caminho. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/revisao.escopo`, `revisao.lotes`, `revisao.achados`, `revisao.posicao`, `revisao.duplicatas`, `revisao.cobertura` e `revisao.regras`. Nenhuma executa `git`, aplica patch, lê o repositório ou publica comentário; todas marcam `executed: false` e `readOnly: true`. O teto de texto é 1,8 MB, o de achados é 5.000 e o de arquivos é 2.000. A página `/revisao` só envia o que foi colado. Detalhes em [`REVISAO.md`](REVISAO.md).

## Submissão de artefatos

`server/submissao.py` implementa sete operações determinísticas inspiradas no `github/awesome-copilot` (MIT). O upstream é um catálogo comunitário com esteira de validação em `eng/`, e a camada local cobre a parte determinística: parser próprio de front matter (`chave: valor`, aspas com comentário depois, lista, bloco `- item`, número, booleano, `null`) e conferência dos campos obrigatórios por tipo de artefato — sete tipos, de `skill` a `prompt` —, estrutura do envio com caminho absoluto, saída por `..`, asset acima de 5 MB, vizinho obrigatório, nome repetido pelo nome do artefato, arquivo oculto, caixa alta e pasta profunda, varredura de risco por linha com nove regras (guardrail desligado, shell remoto, `npx -y`, execução de pacote, versão flutuante, segredo, comando destrutivo, caminho absoluto e `sudo`) e trecho mascarado, parser de expressão SPDX com `AND`/`OR`/`WITH`, 45 ids e 10 exceções, conferência de link contra o próprio envio (arquivo, âncora pelo slug do GitHub, caixa, absoluto, `http://`, texto genérico e asset órfão) e o portão que agrega as cinco checagens na decisão do rótulo. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/submissao.ficha`, `submissao.estrutura`, `submissao.risco`, `submissao.licenca`, `submissao.links`, `submissao.gate` e `submissao.regras`. Nenhuma executa `vally lint`, instala plugin, lê repositório ou aplica rótulo; todas marcam `executed: false` e `readOnly: true`. O teto de texto é 1,8 MB, o de arquivos é 300 e o de achados é 1.000. O envio é um bundle com cabeçalho `>>> caminho` por arquivo (`### caminho` só vale quando a linha parece caminho). A página `/submissao` só envia o que foi colado. Detalhes em [`SUBMISSAO.md`](SUBMISSAO.md).

## Memória de agente

`server/memoria.py` implementa sete operações determinísticas inspiradas no `topoteretes/cognee` (Apache-2.0). O upstream é uma plataforma de memória com quatro operações públicas e um portão de skill no `recall()`; a camada local cobre a parte determinística: roteamento da consulta por 29 regras com peso em oito vias (chunks, grafo, híbrido, resumo, temporal, código, procedimento e regras) com limiar de 3,0, margem de 1,0 e janela de negação de 20 caracteres; extração lexical de sete tipos de entidade (nome, sigla, código, arquivo, data, valor e local) e das relações declaradas em `sujeito -> relação -> objeto`; leitura de grafo em `A -> relação -> B` com grau, componente conectado, ciclo dirigido, hub, folha e densidade; destilação da sessão com marcador, verbo de fato, repetição, feedback e os descontos de fala do agente e confirmação curta; recall com BM25 (k1 1,2 e b 0,75), afinidade de termos, decaimento de meia-vida de 180 dias, sinal da via e lastro aberto por resultado; e esquecimento por item, dataset ou total com `somente_memoria` e raio de alcance. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/memoria.roteamento`, `memoria.entidades`, `memoria.grafo`, `memoria.sessao`, `memoria.recall`, `memoria.esquecer` e `memoria.regras`. Nenhuma chama modelo, gera embedding, abre banco de grafo ou grava sessão; todas marcam `executed: false` e `readOnly: true`. O teto de texto é 1,8 MB, o de memórias é 2.000, o de arestas é 5.000 e o de turnos é 500. A página `/memoria-ia` só envia o que foi colado. Detalhes em [`MEMORIA.md`](MEMORIA.md).

## Portabilidade de skills

`server/portabilidade.py` implementa sete operações determinísticas inspiradas no `alirezarezvani/claude-skills` (MIT). O upstream publica centenas de skills para treze ferramentas e mantém `convert.sh`, `install.sh`, `sync-*-skills.py`, `check_dual_publish.py` e `check_plugin_json.py`; a camada local cobre a parte determinística: inventário por cabeçalho `>>> caminho`, JSON com `arquivos` ou lista `caminho | bytes | sha256 | tipo`, com agrupamento de cada arquivo na skill mais próxima acima dele; auditoria de `SKILL.md` com front matter, nome e slug, descrição, script citado no corpo, `allowed-tools`, licença, versão, tamanho de corpo e binário, arquivo solto e campo que o alvo descarta; conversão para treze alvos em quatro estilos (pasta, espelho, regra e convenção) com cinco ações por arquivo (copiar, reescrever, embutir, gerar e descartar), colisão de destino e rebaixamento de `#` na convenção; deriva entre fonte e espelho por conteúdo ou hash com cinco estados, cobertura da comparação e ponteiro quebrado; colisão por nome, por slug gerado e por corpo idêntico, mais caixa trocada no arquivo de entrada; e lote com `plugin.json` de exatamente oito chaves, semver, caminho prefixado por `./`, limite de 25 MB por pacote e o `marketplace.json` derivado. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/portabilidade.auditar`, `portabilidade.converter`, `portabilidade.deriva`, `portabilidade.colisoes`, `portabilidade.lote`, `portabilidade.matriz` e `portabilidade.regras`. Nenhuma clona repositório, executa `convert.sh`, escreve arquivo ou instala skill; todas marcam `executed: false` e `readOnly: true`. Os tetos são 1,8 MB de texto, 2.000 arquivos e 500 skills por bundle, caminho de 200 caracteres e 200 linhas de tabela. A página `/portabilidade` só envia o que foi colado. Detalhes em [`PORTABILIDADE.md`](PORTABILIDADE.md).

## Continuidade de plano

`server/continuidade.py` implementa sete operações determinísticas inspiradas no `OthmanAdi/planning-with-files` (MIT), já usado como base da 0.6.0. O upstream mantém `inject-plan.py`, `session-catchup.py`, `check-complete.sh`, `plan-doctor.sh`, `ledger-append.sh` e `ledger-summary.sh`; a camada local cobre a parte determinística sem escrever nada: leitura de `### Phase` nos dois formatos de status com a regra de contagem do portão (maior valor por campo entre `**Status:**` e `[status]`), achados para marca duplicada, fase sem status, critério aberto em fase concluída, ordem quebrada e seção vazia; tabela de decisão do portão com cinco guardas — opt-in `gate`, fase em andamento, parada não forçada, teto de bloqueios e avanço do livro — devolvendo `block` ou `allow` com o motivo; retomada que cruza `task_plan.md`, `progress.md` e `findings.md`, aponta divergência de status entre as duas fontes, registro sem data, placeholder não substituído e fase citada no progresso que o plano não tem, e responde as cinco perguntas de reboot; bloco de injeção com seções prioritárias, queda para as primeiras linhas, orçamento de 65.536 bytes para o plano e 32.768 para o progresso, corte em linha inteira, resumo fixo do livro e normalização do relógio; validação do livro JSONL com seis eventos, tick inteiro e crescente, resumo de 200 caracteres, agente sanitizado, lacuna e ordem; e diagnóstico do diretório com arquivo faltando, plano sem livro ou atestação, título duplicado e ambiguidade de plano ativo. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/continuidade.fases`, `continuidade.portao`, `continuidade.retomada`, `continuidade.injecao`, `continuidade.livro`, `continuidade.medico` e `continuidade.regras`. Nenhuma escreve plano, progresso, livro, `.mode` ou atestação, instala hook ou bloqueia sessão; todas marcam `executed: false` e `readOnly: true`. Os tetos são 1,8 MB de texto, 20.000 linhas, 40 fases, 200 planos e 200 linhas de tabela. O diretório de planos chega no bundle `>>> <plano>/<arquivo>`. A página `/continuidade` só envia o que foi colado. Detalhes em [`CONTINUIDADE.md`](CONTINUIDADE.md).

## Acesso ao sistema

`server/sistema.py` é a única camada com efeito colateral real. As anteriores liam texto colado; esta lê o host e, em duas rotas, grava e executa. Três travas separam leitura de efeito: **token de host** em `storage/host-token.txt` (gerado no primeiro uso, impresso no terminal, nunca devolvido por HTTP), **rede** desligada até `JARVIS_HOST_REDE=1` e **instalação** desligada até `JARVIS_HOST_INSTALAR=1`. A comparação do token fica em `server/tokens.py`, não em cada camada: `hmac.compare_digest` com `str` estoura `TypeError` se o texto tem acento, e esse erro subia até a tela como "comparing strings with non-ASCII characters is not supported". O módulo compara em bytes (tempo constante, sem exceção) e explica o motivo da recusa — vazio, não-token ou token errado. O **modo dono** nasceu na 0.57.0 (`JARVIS_HOST_CONFIAR_LOCAL=1`) e virou padrão na 0.60.6: em `127.0.0.1` o servidor preenche o token sozinho, sem variável nenhuma. Não é furo: o token mora em `storage/host-token.txt`, legível por qualquer processo do mesmo usuário, então exigi-lo dali nunca protegeu contra código local — só contra a rede. Requisição de outra máquina não tem IP local e continua exigindo token; página de outro site continua barrada pela checagem de `Origin`. `JARVIS_HOST_EXIGIR_TOKEN_LOCAL=1` é a trava opcional de quem quer o token até localmente.

`ambiente` descreve sistema, arquitetura, núcleos, memória por `/proc/meminfo`, tempo ligado e detecção de contêiner por cinco evidências (`/.dockerenv`, `/run/.containerenv`, runtime no cgroup, `KUBERNETES_SERVICE_HOST` e processo 1 que não é init), avisando em `must` que num contêiner os dados são do contêiner. `disco` mede `shutil.disk_usage` por unidade, descartando pseudo-filesystems (`proc`, `sysfs`, `selinuxfs`, `ramfs`, `rpc_pipefs`, `devtmpfs`), deduplicando bind mount por `st_dev`, marcando `tmpfs`/`overlay` como voláteis e alertando em 15% e 5% livres. `pastas` enumera nome, tipo, tamanho, data e nível até a profundidade pedida, sem ler conteúdo, reconhecendo cofre, chave e token pelo nome e listando-os com tamanho zero, sem seguir symlink, contando pasta negada e declarando truncamento. `drivers` lê `/proc/modules` no Linux com versão de `/sys/module/<nome>/version` e consulta `Win32_PnPSignedDriver` por PowerShell no Windows, apontando item sem versão, driver sem assinatura e fonte indisponível. `bluetooth` lê `/sys/class/bluetooth` e `/var/lib/bluetooth` no Linux e `Get-PnpDevice -Class Bluetooth` no Windows, com achado `must` para ausência de rádio, adaptador desligado e `should` para adaptador sem pareado. `rede` busca no DuckDuckGo HTML e extrai texto de página, recusando esquema diferente de http/https, `localhost`, domínio `.local`/`.internal`, IP privado e host que **resolve** para endereço privado. `baixar` grava em `storage/host-downloads` com teto de 256 MB, nome sanitizado e SHA-256 durante a escrita, registrando cada download em `storage/host-audit.jsonl`. `instalar` monta o comando exato por allowlist fechada — `msiexec`, `dpkg`, `rpm`, `npm`, `python -m pip` e o próprio `.exe` —, declara o risco e devolve token de uso único de 10 minutos. `assinatura` calcula o SHA-256 em fluxo, compara com o hash publicado e verifica a assinatura digital pelo que a plataforma oferece — `Get-AuthenticodeSignature` no Windows com o caminho via `$env:JARVIS_ALVO`, `rpm -K`, `dpkg-sig --verify` e `gpg --verify` para assinatura destacada — declarando `não verificável` em vez de presumir aprovação. `desinstalar` monta o comando de remoção por gerenciador (`dpkg -r`, `rpm -e`, `pip uninstall -y`, `npm uninstall`, `msiexec /x` com GUID ou arquivo) com a mesma allowlist e o mesmo token. `executar` consome o token, exige a trava ligada, recalcula o SHA-256 gravado no plano para recusar arquivo trocado, revalida a assinatura quando o plano exigiu, e roda `subprocess` com `shell=False` e argumentos montados no código.

As rotas são `/api/skills/sistema.ambiente`, `sistema.disco`, `sistema.pastas`, `sistema.drivers`, `sistema.bluetooth`, `sistema.rede`, `sistema.baixar`, `sistema.assinatura`, `sistema.instalar`, `sistema.desinstalar`, `sistema.executar` e `sistema.regras`. `sistema.baixar` e `sistema.executar` declaram `sideEffects`, `dryRunSupported` e `requiresConfirmation` verdadeiros e são as únicas que devolvem `executed: true`. Os tetos são 1,8 MB de texto, 2.000 entradas, profundidade 6, página de 2 MB, download de 256 MB, rede de 20 s e instalador de 300 s. A página `/sistema` só envia o que foi digitado. Detalhes em [`SISTEMA.md`](SISTEMA.md).

## Pessoa

`server/distilar.py` porta a parte determinística de `titanwings/distilly` (MIT). `perfil` reparte o corpus em fontes (`>>> arquivo`) e falas (`Autor: texto`), mede volume, extrai evidências por dimensão com sinais lexicais e classifica cada dimensão em coberta (≥3), parcial (1–2) ou ausente. `dimensoes` publica as quatro famílias e os sinais de cada dimensão. `esboco` gera `SKILL.md` e `manifest.json` propostos, com slug normalizado (NFKD, até 40 caracteres, nomes reservados do Windows recusados), front matter `name: distilly-<slug>`, uma seção por dimensão com o comentário de evidência e SHA-256 do conteúdo. `qualidade` aplica as treze checagens do original em duas réguas — a padrão e a estrita —, incluindo lastro por URL com conteúdo, hierarquia de fonte por `source weight: 1-7`, cadeia de revisão e segurança de direito (bloco de código, citação em bloco e marca de tempo reprovam). `lastro` compara cada bullet com as linhas do material por Jaccard (limiar 0,18), marca o que tem apoio e recusa citação acima de 240 caracteres ou fora do corpus. `correcao` classifica o pedido em fato, voz, julgamento ou limite, indica o efeito na seção e bloqueia correção sem evidência. `hospedeiros` traduz o `hosts.json` do original em caminho calculado, com `DSH_HOME` para o DeepSeek Harness e pasta `distilly-generated` para o Hermes. `catalogo` publica famílias, checagens, hospedeiros, limites e recusas. Nenhuma das oito grava arquivo, instala skill, baixa fonte ou chama modelo. A nona, `server/distilar_ia.py`, é a única exceção: `persona` monta o pedido com as seções da família, envia até 24 mil caracteres pelo campo `material` do `AIRequest` (dado, nunca instrução), recebe até 3 mil tokens, limpa cerca de código, compõe o front matter no código e roda `lastro` e `qualidade` sobre o texto antes de devolver — com os achados das duas no mesmo relatório. Sem chave `JARVIS_AI_API_KEY` recusa; com ela, exporta o material ao provedor e exige confirmação.

## Elevação

`server/elevacao.py` é o único caminho pelo qual o JARVIS pede root, e ele não entrega root ao processo. `privilegio` lê `os.getuid`/`os.geteuid`, procura `sudo` no `PATH`, roda `sudo -n -l` para saber se há `NOPASSWD` e devolve a linha de sudoers restrita aos binários da tabela. `elevar` valida a ação contra `ACOES` — seis entradas fixas, cada uma com binário, argumentos, tipo de alvo, extensões e risco —, resolve o alvo (arquivo dentro de `storage/host-downloads` com SHA-256, nome de pacote por `^[a-z0-9][a-z0-9+.-]{0,63}$`, unidade por `^[A-Za-z0-9][A-Za-z0-9@._:-]{0,63}$` e presença em `JARVIS_HOST_SERVICOS`), monta `sudo -n <binário> <args> -- <alvo>` e devolve token de 8 hex com validade de 600 s. `elevar_executar` exige `JARVIS_HOST_ROOT=1`, consome o token, revalida alvo, hash e argv byte a byte, roda com `shell=False` e grava `elevar:<ação>` em `storage/host-audit.jsonl`. Nenhum campo de comando livre existe em nenhuma das três.

A mesma versão fecha a lacuna da camada de evolução: `sudo`, `pkexec`, `doas`, `runas`, `su -` e `chmod` setuid entram no catálogo de perigos, e a guarda G2 passa a acusar binário de elevação na allowlist. Antes da correção, um patch com `subprocess.run(["sudo", ...])` recebia 10/100 e as dez guardas preservadas; agora soma 60/100, nível alto, com violação de G2.

## Evolução

`server/evolucao.py` é a única camada que pode alterar o código que a executa, e por isso é a única que prova antes de escrever. `mapa` conta arquivos, linhas, classes, funções públicas e módulos, marca quem está sem teste e alerta acima de 2.000 linhas. `proposta` lê diff unificado, valida cabeçalho, caminho dentro de `server/`, `src/`, `docs/`, `public/` ou `tests/`, extensão da lista e ausência de `..`, e aplica cada hunk em memória contra o conteúdo atual, devolvendo `aplica`/`não aplica` com o motivo por arquivo. `risco` pontua de 0 a 100 por treze padrões de perigo (`eval`, `exec`, `os.system`, `shell=True`, `pickle`, `__import__`, YAML sem `SafeLoader`, `chmod 777`, `verify=False`, aviso de TLS silenciado, segredo inline, chave AWS e chave privada), mais peso por arquivo central (`evolucao.py` 20, `sistema.py` 18, `app.py` 16, `skill_registry.py` 15, `review.py` 10, `.env.example` 8), remoção de guarda e tamanho do diff. `guardas` confere G1–G10 nas linhas adicionadas e removidas. `ensaiar` copia `server/`, `pytest.ini` e `requirements*.txt` para `storage/evolucao/ensaios/<id>/`, aplica o patch na cópia, roda `python -m pytest <alvos> -o addopts= -q --no-header -p no:cacheprovider` e aprova só com `codigo == 0`, `failed == 0` e `passed > 0`, devolvendo token de 8 hex com TTL de 900 s e uso único. `promover` revalida o token, refaz o diff do ensaio, compara o SHA-256 de cada arquivo com o que foi ensaiado, confere `git status --porcelain -- <arquivo>`, copia o backup, escreve, registra em `storage/evolucao/audit.jsonl` e devolve `reinicio_pendente: true` sem reiniciar nem commitar. `reverter` restaura do backup e avisa que o processo precisa reiniciar. `catalogo` publica fluxo, travas, guardas, padrões monitorados, raízes permitidas, limites e recusas.

As rotas são `/api/skills/evoluir.mapa`, `evoluir.proposta`, `evoluir.risco`, `evoluir.guardas`, `evoluir.ensaiar`, `evoluir.promover`, `evoluir.reverter` e `evoluir.regras`. Só `evoluir.ensaiar`, `evoluir.promover` e `evoluir.reverter` declaram `sideEffects` e `requiresConfirmation`, e só elas devolvem `executed: true`. Os tetos são 900 KB de diff, 40 arquivos, 200 hunks, 900 s de ensaio e 120 s de promoção. A página `/evolucao` mostra oito abas e só envia o que foi digitado. Detalhes em [`EVOLUCAO.md`](EVOLUCAO.md).

## Carreira

`server/career.py` implementa sete operações determinísticas inspiradas em `career-ops-hq/career-ops` (MIT). O módulo lê a vaga como texto e como dado — nunca como instrução —, extrai requisitos com banda e nível de evidência, classifica empresa e faixa salarial sem adivinhar moeda ou período, e calcula a nota em cinco dimensões com tetos nomeados. A legitimidade do anúncio roda em paralelo, em treze sinais catalogados, e não altera a nota. O ATS tem lints de payload e placar de 100 pontos com pesos fixos; sem HTML, a letra não é emitida. A carta exige vaga, currículo e pesquisa, e só cita número que tenha origem no currículo ou no perfil. O plano de entrevista cruza requisitos com histórias STAR. O funil lê tabela, TSV ou CSV, normaliza dez estados e declara censura e amostra pequena. O módulo reaproveita `server/review.py` para achados, contagens, veredito e Markdown, e não chama IA nem grava arquivo.

## Navegador assistido

`server/navegador.py` implementa sete operações determinísticas inspiradas em `citrolabs/ego-lite` (MIT). O módulo faz o parsing da árvore de acessibilidade em dois espaços por nível, inclusive metadados com colchetes aninhados e frames; indexa papel, nome, `ref`, `loc` e URL; resolve alvos nos formatos `@N`, `ref=`, `text=`, `loc=role:`, `loc=css:`, `loc=href:`, CSS e `nth`, com o documento principal antes dos frames; monta um roteiro de três rodadas com orçamento; aplica quinze padrões de código e dez estados de alvo; normaliza recibos e cobra o fechamento; e classifica ações em bloqueada, confirmar ou liberada. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/navegador.snapshot`, `navegador.alvo`, `navegador.roteiro`, `navegador.checagem`, `navegador.recibos`, `navegador.limites` e `navegador.regras`. Nenhuma abre navegador, executa JavaScript, instala o app do upstream ou grava arquivo; todas marcam `executed: false` e `readOnly: true`. A página `/navegador` só envia o texto colado. Detalhes em [`NAVEGADOR.md`](NAVEGADOR.md).

## Escritório assistido

`server/escritorio.py` implementa sete operações determinísticas inspiradas em `googleworkspace/cli` (Apache-2.0). O módulo monta a invocação de descoberta com `--params`/`--json`, valida parâmetro de caminho obrigatório, classifica risco e liga o ensaio; planeja quinze receitas com passos, verificação, escopos e rollback; lê páginas em JSON, NDJSON ou array, detecta chave de itens, deduplica e monta a próxima chamada; divide lotes nos tetos de Sheets, Docs, Gmail, Drive e Calendar; compara operações com escopos concedidos, inclusive superconjunto; e tria código de saída, status e `reason` em causa, ação e política de repetição. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/escritorio.comando`, `escritorio.receita`, `escritorio.paginas`, `escritorio.lote`, `escritorio.escopos`, `escritorio.erros` e `escritorio.regras`. Nenhuma autentica, chama o Google, lê credencial, instala o CLI ou grava arquivo; todas marcam `executado: false`. A página `/escritorio` só envia o texto colado. Detalhes em [`ESCRITORIO.md`](ESCRITORIO.md).

## Estação do agente

`server/estacao.py` implementa sete operações determinísticas inspiradas em `feder-cr/invisible_dots` (MIT). O módulo planeja a tarefa como um laço observar/agir/verificar/registrar, com ferramenta, permissão e prova por passo, parada e orçamento; audita a matriz `allow`/`ask`/`deny` contra o catálogo de 30 ferramentas e 14 permissões, com risco alto liberado como bloqueio; lê recibos de execução e aponta chamada sem resultado, execução dupla, aprovação reaproveitada e retomada sem conferir o estado; valida cron de cinco campos, sobreposição, presença e acordadas por dia; classifica cada ação pretendida em liberada, confirmar ou bloqueada, recusando evasão de detecção, CAPTCHA e rotação de conta; e audita notas e skills quanto a tamanho, segredo, data, gatilho e verificação. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/estacao.tarefa`, `estacao.permissoes`, `estacao.recibos`, `estacao.agenda`, `estacao.limites`, `estacao.memoria` e `estacao.regras`. Nenhuma abre máquina, navegador, canal ou conexão; todas marcam `executado: false` e `readOnly: true`. A página `/estacao` só envia o texto colado. Detalhes em [`ESTACAO.md`](ESTACAO.md).

## Estação do agente

`server/estacao.py` implementa sete operações de análise inspiradas em `feder-cr/invisible_dots` (MIT): plano de tarefa com laço observar/agir/verificar/registrar, auditoria da matriz `allow`/`ask`/`deny`, leitura de recibos, validação de agenda, classificação de efeito, higiene de notas e skills, e catálogo.

`server/estacao_runtime.py` é o **executor real**: fila durável em SQLite com gate de permissão, seis ferramentas (`exec`, `read_file`, `write_file`, `list_dir`, `grep`, `cron`), aprovação que vale uma chamada e roda no máximo uma vez (reivindicação por `UPDATE ... WHERE estado='pendente'`), recibos por evento, recuperação que marca `executando` como `interrompido` e encerra o grupo de processos no timeout. Os caminhos ficam presos ao diretório de trabalho por `safe_path`; o subprocesso recebe ambiente mínimo, sem `JARVIS_*`. Não é isolamento de sistema operacional: a VM do upstream não existe aqui.

As rotas operacionais são `/api/estacao/estado`, `executar`, `aprovacoes`, `aprovacoes/{id}/decidir`, `politica`, `chamadas`, `recibos`, `agenda` (GET/POST/DELETE), `agenda/tick` e `recuperar`. As de análise são `/api/skills/estacao.{tarefa,permissoes,recibos,agenda,limites,memoria,regras}`. A página `/estacao` tem uma aba Executor e sete de análise. Detalhes em [`ESTACAO.md`](ESTACAO.md).

## Corpus de legislação

`LegalCorpus` carrega somente os oito documentos declarados em `server/legal_data/index.json`. Na inicialização do registry, o parser:

1. separa front matter e corpo Markdown;
2. identifica cabeçalhos de artigos, incluindo milhares e sufixos;
3. limpa marcação sem interpretar o conteúdo como HTML;
4. guarda texto original e forma normalizada sem acentos;
5. monta o catálogo de documentos e artigos.

As três operações são `legal.search`, `legal.article` e `legal.sources`. Elas não gravam arquivos, não chamam a IA e não executam código do repositório de origem.

A busca percorre o índice local e usa cobertura, proximidade e variantes lexicais pequenas para ranking. IDs de documentos são enums allowlisted pelo Pydantic. O usuário não pode informar um caminho de arquivo.

Os resultados incluem texto, fonte e aviso informativo. A interface React renderiza o conteúdo como texto, não como HTML, e abre links oficiais com isolamento de `opener`. A sincronização é um script manual separado, fixado por commit e sem rota pública.

Mais detalhes em [`LEGISLACAO.md`](LEGISLACAO.md).

## IA externa

O provedor é configurado no processo Python por variáveis de ambiente. A chave existe apenas na memória do backend e no cabeçalho da chamada ao provedor.

A requisição externa contém:

- instruções para responder em português e não fingir execuções;
- até 12 mensagens recentes;
- a pergunta atual;
- tarefas e notas somente quando o usuário ativa o compartilhamento de contexto.

O backend limita o tamanho das mensagens, aplica timeout e limita chamadas por minuto. Erros retornam status e mensagem segura, sem corpo sensível do provedor ou stack trace.

## Persistência e privacidade

- Interface: chaves `jarvis:*` no `localStorage`.
- Arquivos das skills: pasta isolada ignorada pelo Git.
- Corpus jurídico: textos estáticos versionados, consultados localmente.
- Credenciais: `.env`, também ignorado.
- Backup da interface: JSON gerado localmente.
- Contexto pessoal para IA: opt-in e separado da ativação da IA.

## Adicionar uma nova skill

1. Escolher uma rotina pequena e declarar seu modelo Pydantic.
2. Restringir arquivos e integrações a recursos explicitamente autorizados.
3. Implementar `dryRun` quando houver efeito colateral.
4. Registrar o ID no `SkillRegistry`; nunca aceitar um caminho de módulo do usuário.
5. Exigir confirmação para gravação ou ação externa.
6. Testar execução, timeout, entradas inválidas e resultado.
7. Usar o formulário genérico da página Skills ou criar uma experiência dedicada sobre o mesmo contrato.
