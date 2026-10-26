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

O catálogo completo tem **254 skills Python**: as 36 anteriores (incluindo os oito workflows de engenharia documentados em [`ENGENHARIA.md`](ENGENHARIA.md) e as seis de análise reversa em [`ENGENHARIA-REVERSA.md`](ENGENHARIA-REVERSA.md)), quatro de engenharia enxuta em [`LEAN.md`](LEAN.md), seis de governo de agentes em [`AGENTES.md`](AGENTES.md), cinco de estúdio de design em [`ESTUDIO.md`](ESTUDIO.md), sete de direção de arte em [`DIRECAO.md`](DIRECAO.md) sete de diagramas e sete editoriais em [`DIAGRAMAS.md`](DIAGRAMAS.md) e sete de carreira em [`CARREIRA.md`](CARREIRA.md) e sete de navegação assistida em [`NAVEGADOR.md`](NAVEGADOR.md) sete de escritório assistido em [`ESCRITORIO.md`](ESCRITORIO.md) sete de estação do agente em [`ESTACAO.md`](ESTACAO.md), seis de curadoria em [`CURADORIA.md`](CURADORIA.md), sete de marketing em [`MARKETING.md`](MARKETING.md), sete de ciência em [`CIENCIA.md`](CIENCIA.md), sete de confiança em [`CONFIANCA.md`](CONFIANCA.md), sete de contexto em [`CONTEXTO.md`](CONTEXTO.md), sete de seleção em [`SELECAO.md`](SELECAO.md) sete de revisão em [`REVISAO.md`](REVISAO.md) sete de submissão em [`SUBMISSAO.md`](SUBMISSAO.md) e sete de memória de agente em [`MEMORIA.md`](MEMORIA.md). A 0.17.0 acrescentou também o executor real da Estação (`server/estacao_runtime.py`), fora do registro de skills; a 0.18.0 acrescentou sete skills da camada editorial de diagramas (`server/editorial.py`), que também não desenham — decidem e conferem —, e a 0.19.0 acrescentou seis skills de curadoria (`server/curadoria.py`), que também não tocam a rede: leem o CSV que você cola e devolvem parecer, e a 0.20.0 acrescentou sete skills de marketing (`server/marketing.py`), que fazem conta de funil, amostra de teste, higiene de UTM, revisão de e-mail, auditoria on-page e limite de anúncio sem abrir conta de anúncio nem escrever copy, e a 0.21.0 acrescentou sete skills de ciência (`server/ciencia.py`), que dimensionam estudo, conferem relato estatístico, auditam desenho e reprodutibilidade, validam método analítico e leem o manuscrito contra a diretriz sem baixar dado, executar análise ou usar modelo de linguagem, e a 0.22.0 acrescentou sete skills de confiança (`server/confianca.py`), que leem a ficha da skill, varrem o risco do texto, comparam permissão declarada com a usada, conferem a receita de instalação, auditam o índice e caçam duplicata sem baixar skill nenhuma, e a 0.23.0 acrescentou sete skills de contexto (`server/contexto.py`), que medem a conversa, dividem a janela, cortam por turno, saneiam o histórico, preparam o resumo de retenção e contabilizam o uso sem chamar modelo. A 0.24.0 acrescentou sete skills de seleção (`server/selecao.py`), que leem o briefing, ranqueiam o catálogo com BM25, validam a stack, montam o plano, mapeiam a cobertura e auditam o índice, sem baixar ou instalar skill, a 0.25.0 acrescentou sete skills de revisão (`server/revisao.py`), que leem o diff e os achados colados, classificam o escopo, agrupam lotes, normalizam severidade, conferem a âncora do comentário, comparam regra e agente e montam o `rule.json` sem executar git, aplicar patch ou publicar comentário, a 0.26.0 acrescentou sete skills de submissão (`server/submissao.py`), que leem a ficha do artefato, conferem a estrutura do envio, varrem o risco do texto, validam a licença como expressão SPDX, checam link e âncora e decidem o estado do envio sem rodar lint, instalar plugin ou aplicar rótulo, a 0.27.0 acrescentou sete skills de memória de agente (`server/memoria.py`), que roteiam a consulta pela forma da pergunta, extraem entidade e relação por padrão lexical, medem o grafo, pontuam a lição da sessão, recuperam com BM25 e decaimento e planejam o esquecimento com raio de alcance sem chamar modelo nem gravar nada, e a 0.28.0 acrescentou sete skills de portabilidade (`server/portabilidade.py`), que auditam o bundle antes da conversão, montam o plano para treze ferramentas, medem a deriva entre fonte e espelho, caçam colisão pelo destino, geram o lote de marketplace com `plugin.json` de oito chaves cruzam a matriz skill × alvo sem copiar arquivo, instalar skill ou chamar modelo, a 0.29.0 acrescentou sete skills de continuidade de plano (`server/continuidade.py`), que leem as fases nos dois formatos de status, aplicam os cinco guardas do portão de conclusão, reconstroem o estado depois de `/clear`, montam o bloco reinjetado com orçamento, validam o livro append-only e diagnosticam o diretório de planos sem escrever arquivo nem instalar hook, e a 0.30.0 acrescentou dez skills de sistema (`server/sistema.py`), que medem disco, enumeram pastas sem ler conteúdo, listam drivers e Bluetooth, buscam e leem páginas, baixam para quarentena com hash e executam instalador por allowlist. Das 254, as de escrita declaram efeito colateral e exigem confirmação explícita; as que tocam a máquina — `sistema.baixar`, `sistema.executar`, `sistema.elevar_executar` e `files.import` — exigem também o token de host e, conforme o caso, `JARVIS_HOST_INSTALAR=1` ou `JARVIS_HOST_ROOT=1`, a 0.31.0 acrescentou duas skills de verificação e remoção (`sistema.assinatura` e `sistema.desinstalar`), que calculam SHA-256, validam Authenticode, rpm -K, dpkg-sig ou gpg quando a plataforma permite, declaram quando não permitem e montam o comando de remoção por gerenciador com token de uso único, e a 0.32.0 acrescentou oito skills de evolução (`server/evolucao.py`), que inventariam o código, provam se um diff unificado aplica hunk por hunk, pontuam o risco até 100, conferem as dez guardas do projeto, ensaiam o patch numa cópia isolada rodando a suíte real, promovem só o ensaio aprovado com backup e revertem pelo backup. A 0.36.0 acrescentou `files.import`, que copia PDFs, Office e textos da pasta de downloads do usuário para a área isolada, com token de host, lista fechada de nove formatos e teto de 64 MB por arquivo e 512 MB por lote — sem mover, apagar ou executar nada. Só `evoluir.ensaiar`, `evoluir.promover` e `evoluir.reverter` têm efeito, e as três exigem `JARVIS_HOST_EVOLUIR=1`. A **0.48.0** acrescentou seis skills de repositório (`server/repos.py`): baixar o `.zip` de um repositório público do GitHub sem Git, analisar o que veio, listar, ler arquivo, executar com interpretador de lista fechada e remover — descritas em [`REPOSITORIOS.md`](REPOSITORIOS.md). A **0.49.0** liberou a busca na web sem token — `sistema.rede` deixou de pedir `token` para buscar e ler página, passou a usar três fontes sem chave (`duckduckgo`, `wikipedia`, `youtube`, em `server/busca_web.py`) e devolve de qual fonte veio cada resultado — e acrescentou seis skills de mesa (`server/mesa.py`): status, mover, clicar, digitar, teclar e focar, por `ctypes` no Windows, com confirmação obrigatória e freio de pânico. A **0.50.0** acrescentou oito skills de fora: `habilidades.importar/listar/aplicar/remover` (puxam um `SKILL.md` de link do GitHub ou de catálogo, guardam em `storage/habilidades.json` e devolvem o roteiro com a pergunta do usuário) e `github.repo/arquivos/arquivo/buscar` (API pública do GitHub, sem token, 60 pedidos por hora) — descritas em [`HABILIDADES.md`](HABILIDADES.md). A **0.51.0** acrescentou cinco skills: `habilidades.importar-varias` (importa até 20 links de uma vez, sem um erro derrubar os outros) e as quatro de correio exportado (`correio.arquivos`, `correio.triar`, `correio.padroes`, `correio.rascunho`), que leem `.eml`/`.mbox` de `storage/correio`, classificam por prioridade e escrevem no seu estilo — sem conectar no Gmail e sem enviar, descritas em [`CORREIO.md`](CORREIO.md). A **0.52.0** acrescentou quatro: `catalogo.carregar`, `catalogo.listar` e `catalogo.importar` (leem a planilha CSV de habilidades de terceiros, filtram e trazem o `SKILL.md` de cada linha pela árvore do repositório, até 10 por chamada) e `correio.gmail-busca` (monta o link de uma busca pronta do Gmail — faturas, intimações, governo, segurança ou não lidos — para abrir na sessão já logada, sem ler nada e sem chave), descritas em [`CATALOGO.md`](CATALOGO.md). Todas continuam registradas manualmente na allowlist de `server/skill_registry.py`, com entrada validada por Pydantic. O registro não oferece shell, importação de skill por nome nem código arbitrário; a única porta de execução é o executor da Estação (`server/estacao_runtime.py`), com ferramentas fixas, política `allow`/`ask`/`deny` e recibo por chamada.

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
