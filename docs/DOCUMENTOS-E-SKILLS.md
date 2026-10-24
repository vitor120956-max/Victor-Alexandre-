# Documentos e skills de produtividade

## Escopo da versão 0.4.0

Este incremento adapta capacidades observadas em dois catálogos públicos:

- [`anthropics/skills`](https://github.com/anthropics/skills): referência comportamental para leitura e criação de DOCX, XLSX, PPTX e PDF;
- [`ComposioHQ/awesome-claude-skills`](https://github.com/ComposioHQ/awesome-claude-skills): referência para organização de arquivos, análise de reuniões, geração de changelog e sorteio.

Os repositórios não são dependências do JARVIS. Nenhum de seus scripts é instalado, importado ou executado. As quatro skills de documentos da Anthropic possuem licença específica/source-available; o JARVIS usa **implementações próprias**, não cópias desse código. As adaptações de produtividade também foram escritas para este núcleo.

Não foram habilitados Composio, SaaS, downloads de vídeo, credenciais de terceiros, automações externas ou chamadas de IA nestas skills.

## Skills adicionadas

| ID | Operação | Efeitos |
|---|---|---|
| `document.read` | Extrai texto de DOCX, XLSX, PPTX e PDF | Somente leitura |
| `document.create` | Cria DOCX, XLSX, PPTX ou PDF a partir de conteúdo estruturado | `dryRun` + confirmação |
| `pdf.merge` | Mescla de 2 a 10 PDFs | `dryRun` + confirmação |
| `files.organize` | Move arquivos para subpastas por extensão | `dryRun` + confirmação; nunca exclui nem sobrescreve |
| `meeting.analyze` | Métricas de falas, perguntas, hedges e possíveis ações/decisões | Somente texto local |
| `changelog.generate` | Agrupa mensagens por prefixos e regras determinísticas | Sem gravar; sem acessar o Git |
| `random.pick` | Sorteia participantes com `secrets.SystemRandom` | Sem gravar; sem IA |

O catálogo completo tem **106 skills Python**: as 36 anteriores (incluindo os oito workflows de engenharia documentados em [`ENGENHARIA.md`](ENGENHARIA.md) e as seis de análise reversa em [`ENGENHARIA-REVERSA.md`](ENGENHARIA-REVERSA.md)), quatro de engenharia enxuta em [`LEAN.md`](LEAN.md), seis de governo de agentes em [`AGENTES.md`](AGENTES.md), cinco de estúdio de design em [`ESTUDIO.md`](ESTUDIO.md), sete de direção de arte em [`DIRECAO.md`](DIRECAO.md) sete de diagramas e sete editoriais em [`DIAGRAMAS.md`](DIAGRAMAS.md) e sete de carreira em [`CARREIRA.md`](CARREIRA.md) e sete de navegação assistida em [`NAVEGADOR.md`](NAVEGADOR.md) sete de escritório assistido em [`ESCRITORIO.md`](ESCRITORIO.md) sete de estação do agente em [`ESTACAO.md`](ESTACAO.md) e seis de curadoria em [`CURADORIA.md`](CURADORIA.md). A 0.17.0 acrescentou também o executor real da Estação (`server/estacao_runtime.py`), fora do registro de skills; a 0.18.0 acrescentou sete skills da camada editorial de diagramas (`server/editorial.py`), que também não desenham — decidem e conferem —, e a 0.19.0 acrescentou seis skills de curadoria (`server/curadoria.py`), que também não tocam a rede: leem o CSV que você cola e devolvem parecer. Todas continuam registradas manualmente na allowlist de `server/skill_registry.py`, com entrada validada por Pydantic. O registro não oferece shell, importação de skill por nome nem código arbitrário; a única porta de execução é o executor da Estação (`server/estacao_runtime.py`), com ferramentas fixas, política `allow`/`ask`/`deny` e recibo por chamada.

## Página Documentos

A rota `/documentos` reúne:

- biblioteca dos arquivos visíveis da área isolada;
- upload de TXT, MD, JSON, CSV, LOG, DOCX, XLSX, PPTX e PDF;
- download pelo nome e caminho validados no servidor;
- leitura de documentos e textos sem enviá-los à IA;
- criação de DOCX, XLSX, PPTX e PDF;
- simulação obrigatória na interface antes de criar um documento;
- confirmação separada para upload e para gravação;
- opção de sobrescrita desmarcada por padrão.

Mesclagem de PDF e organização de arquivos ficam no executor da página **Skills**, pois usam planos e parâmetros próprios. Resultados que geram arquivos oferecem um link de download.

### Formatos de entrada para criação

- **DOCX/PDF:** `#`, `##` e `###` criam títulos; `- ` cria itens de lista; as demais linhas viram parágrafos. A sintaxe não é HTML e não executa markup.
- **XLSX:** CSV, ponto e vírgula ou tabulação. Cada célula é armazenada como texto; valores começados por `=`, `+`, `-` ou `@` não viram fórmulas.
- **PPTX:** a primeira linha de cada seção é o título do slide; as linhas seguintes são tópicos; uma linha `---` separa slides.

A criação é determinística e não chama IA. O PDF usa fontes padrão do ReportLab; a extração de PDF depende de texto presente no arquivo e **não faz OCR**.

## Upload e download

### Upload

`POST /api/files/upload`, multipart:

- `upload`: arquivo;
- `directory`: subpasta relativa opcional;
- `overwrite`: booleano, `false` por padrão;
- `confirmed`: precisa ser `true`.

O corpo é recebido em streaming para um arquivo temporário dentro da área de destino. O servidor limita o arquivo a **25 MB**, valida extensão e nome, rejeita caminhos no nome do arquivo e só move o temporário para o destino depois das validações. Upload sem confirmação é recusado.

### Download

`GET /api/files/download?path=<caminho-relativo>`

O download usa a mesma confinação das skills. Caminhos absolutos, `..`, arquivos ocultos, formatos fora da allowlist, itens que não sejam arquivos regulares e arquivos acima de 25 MB são recusados. A resposta usa `Content-Disposition: attachment`.

## Limites defensivos

| Recurso | Limite atual |
|---|---|
| Upload/documento | 25 MB |
| Texto extraído | 100.000 caracteres, com indicação de truncamento |
| OOXML expandido | 100 MB somados e 2.048 entradas |
| DOCX | 50 tabelas e 500 linhas por tabela na extração |
| XLSX — leitura | 20 planilhas, 500 linhas por planilha e 10.000 linhas úteis no total |
| XLSX — criação | 1.000 linhas e 100 colunas |
| PPTX — leitura | 100 slides |
| PPTX — criação | 25 slides e 20 tópicos por slide |
| PDF — leitura | 200 páginas |
| PDF — mesclagem | 10 entradas e 500 páginas somadas |
| Biblioteca | 200 arquivos por resposta |
| Texto simples — leitura | 200 KB |

OOXML criptografado, PDF criptografado, arquivos corrompidos e destinos fora da área isolada são recusados. Documentos são tratados como dados: macros, fórmulas, links e scripts não são executados pelas skills.

## Organização sem exclusão

`files.organize` examina somente os arquivos do diretório informado, sem recursão. O plano usa estas categorias:

- `documentos`: PDF, DOCX, TXT e MD;
- `planilhas`: XLSX e CSV;
- `apresentacoes`: PPTX;
- `dados`: JSON e LOG.

Se qualquer destino já existir, a operação é recusada. A skill não possui rotina de exclusão nem opção de sobrescrita. No chat, `organizar arquivos` executa **somente `dryRun`**; a gravação exige abrir Skills, revisar e confirmar.

## Reuniões, changelogs e sorteios

### Reuniões

A análise usa regras locais sobre a transcrição fornecida. Linhas no formato `Nome: fala` permitem métricas por participante. O resultado inclui palavras, turnos, perguntas, vícios de linguagem, hedges e heurísticas de ação/decisão.

Essas listas são **candidatas para revisão**, não fatos inferidos por IA. A ferramenta não mede sentimento, não faz diagnóstico psicológico e não transcreve áudio.

### Changelogs

A skill recebe mensagens de commit explicitamente; não lê o histórico do repositório. Prefixos como `feat`, `fix`, `perf`, `security` e `docs` são agrupados. Entradas internas como `test`, `ci`, `chore` e `refactor` ficam fora do Markdown por padrão e são contabilizadas separadamente. Revise o resultado antes de publicar.

### Sorteios

A seleção usa o gerador criptográfico do sistema operacional por `secrets.SystemRandom`, remove duplicidades sem diferenciar maiúsculas e aplica exclusões. Não há integração com auditoria externa ou mecanismo de sorteio público verificável.

## Comandos da conversa

```text
listar documentos
ler PDF documentos/relatorio.pdf
ler planilha dados/resumo.xlsx
analisar reunião:
Ana: Podemos revisar a proposta?
Bruno: Eu fico responsável pela revisão.
gerar changelog versão 0.4.0:
feat: adiciona documentos
fix: corrige leitura de slides
sortear 2 entre Ana, Bruno, Carla
organizar arquivos
```

`criar documento`, `criar planilha`, `criar apresentação` e `criar PDF` apenas orientam o uso da página Documentos; o chat não afirma ter criado algo e não contorna a confirmação visual.

## Implementação

- `server/workspace.py`: confinamento, extensões, limites e URLs de download;
- `server/documents.py`: adaptadores próprios com `python-docx`, `openpyxl`, `python-pptx`, `pypdf` e ReportLab;
- `server/productivity.py`: reuniões, changelogs e sorteio;
- `server/skill_registry.py`: allowlist, schemas e efeitos;
- `server/app.py`: upload/download e limites de corpo;
- `src/pages/DocumentsPage.tsx`: experiência de arquivos;
- `src/lib/skillResults.ts`: apresentação dos resultados no chat.

Nenhuma dessas rotas envia conteúdo de arquivo, transcrição, commits ou participantes ao provedor de IA.
