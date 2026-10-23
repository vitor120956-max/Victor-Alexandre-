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

## Carreira

`server/career.py` implementa sete operações determinísticas inspiradas em `career-ops-hq/career-ops` (MIT). O módulo lê a vaga como texto e como dado — nunca como instrução —, extrai requisitos com banda e nível de evidência, classifica empresa e faixa salarial sem adivinhar moeda ou período, e calcula a nota em cinco dimensões com tetos nomeados. A legitimidade do anúncio roda em paralelo, em treze sinais catalogados, e não altera a nota. O ATS tem lints de payload e placar de 100 pontos com pesos fixos; sem HTML, a letra não é emitida. A carta exige vaga, currículo e pesquisa, e só cita número que tenha origem no currículo ou no perfil. O plano de entrevista cruza requisitos com histórias STAR. O funil lê tabela, TSV ou CSV, normaliza dez estados e declara censura e amostra pequena. O módulo reaproveita `server/review.py` para achados, contagens, veredito e Markdown, e não chama IA nem grava arquivo.

## Navegador assistido

`server/navegador.py` implementa sete operações determinísticas inspiradas em `citrolabs/ego-lite` (MIT). O módulo faz o parsing da árvore de acessibilidade em dois espaços por nível, inclusive metadados com colchetes aninhados e frames; indexa papel, nome, `ref`, `loc` e URL; resolve alvos nos formatos `@N`, `ref=`, `text=`, `loc=role:`, `loc=css:`, `loc=href:`, CSS e `nth`, com o documento principal antes dos frames; monta um roteiro de três rodadas com orçamento; aplica quinze padrões de código e dez estados de alvo; normaliza recibos e cobra o fechamento; e classifica ações em bloqueada, confirmar ou liberada. Reaproveita `server/review.py` para achados, contagens, veredito e Markdown.

As rotas são `/api/skills/navegador.snapshot`, `navegador.alvo`, `navegador.roteiro`, `navegador.checagem`, `navegador.recibos`, `navegador.limites` e `navegador.regras`. Nenhuma abre navegador, executa JavaScript, instala o app do upstream ou grava arquivo; todas marcam `executed: false` e `readOnly: true`. A página `/navegador` só envia o texto colado. Detalhes em [`NAVEGADOR.md`](NAVEGADOR.md).

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
