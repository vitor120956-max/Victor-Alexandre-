# JARVIS — Núcleo pessoal

Central local-first com interface React, skills Python reais, consulta a legislação brasileira e camada opcional de IA externa. Conversa por texto ou voz, gerencia tarefas e memórias, controla foco, executa automações e processa arquivos em uma área isolada.

**Versão atual: 0.61.9.**

## O que ele faz sem chave de IA

O chat tem um interpretador local: se a frase casar com um comando conhecido, ele executa em Python ou no próprio navegador, sem chamar modelo nenhum e sem internet. Digite **`ajuda`** na conversa para ver a lista viva.

| Diga isto | O que acontece |
|---|---|
| `calcular (1250 * 0,18) + 40` | resolve a expressão em Python, sem LLM |
| `criar tarefa revisar o projeto` · `mostrar tarefas` | grava e lista tarefas |
| `anotar minha ideia sobre X` · `mostrar notas` | notas locais |
| `iniciar foco de 25 minutos` · `pausar foco` | cronômetro de foco |
| `artigo 49 do CDC` | texto exato, do corpus local de 4.427 artigos |
| `pesquisar na legislação sobre proteção de dados` | busca lexical no corpus |
| `listar documentos` · `ler PDF documentos/relatorio.pdf` | área isolada de arquivos |
| `analisar reunião: Ana: revisar proposta` | métricas da transcrição |
| `analisar texto ...` · `python status` | skills de texto e estado do núcleo |
| `sortear 2 entre Ana, Bruno, Carla` | sorteio com aleatoriedade criptográfica |
| `executar resumo do dia` · `organizar tarefas` | resumo e ordenação |
| `abrir GitHub` · `quero q vc abra uma tela do youtube` | entende o pedido coloquial e abre a aba no navegador |
| `pesquisar e responder X` | busca, lê as páginas e responde citando as fontes |
| `contar as palavras de: …` · `minhas skills locais` | agente local: cria a skill de receita, executa e lista o que já criou |
| `não é essa, é a skill X` · `procure na web sobre isso` | ensina a correlação ou guarda a resposta buscada |
| `abrir estúdio` · `abrir lean` · `abrir agentes` | painéis de análise |
| `baixar o repositório virgiliojr94/book-to-skill` | baixa o `.zip` do GitHub **sem Git**, descreve linguagem, dependências e entradas, e pede o “sim” antes de qualquer execução |
| `limita a banda do drive` · `limita o drive em 500` | grava o limite do app do Drive no registro do Windows (`HKCU`) e confere lendo de volta — vale ao reiniciar o Drive |
| `pausa a sincronização` · `abre o drive` | fecha/abre o app do Google Drive (fechar para a sincronização e derruba a unidade `G:`) |
| `configura o google drive pra mim` · `tira a biblioteca do drive` | leva **só** biblioteca e repositórios para o Drive, confere arquivo por arquivo e grava o `.env` — depois do seu “sim” |
| `importar Downloads/contabilidade.pdf` · `como funciona o rateio de custo` | biblioteca: lê livro, EPUB, DOCX, TXT, imagem e legenda de vídeo, e responde com trecho real + seção + página |
| `importar Downloads/contrato-escaneado.pdf` · `importar Downloads/foto-da-pagina.jpg` | OCR: tira o texto da página digitalizada ou da foto e guarda na biblioteca |
| `baixar a legenda de https://youtu.be/dQw4w9WgXcQ` | pega sozinho a legenda publicada do YouTube (inclusive a automática) e importa como fonte — precisa de `JARVIS_HOST_REDE=1` |

**O que precisa de chave:** qualquer pergunta aberta — “quem foi Machado de Assis”, “explique a diferença entre X e Y”. Sem chave, o JARVIS responde que a IA externa não foi configurada e lembra que os comandos locais continuam valendo.

**Biblioteca, sem modelo:** o JARVIS importa PDF, EPUB, DOCX, TXT/MD, imagem (`png`, `jpg`, `tif`) e legenda de vídeo (VTT/SRT), corta em seções com página e título, e procura por assunto com BM25. **PDF escaneado e foto de página passam pelo OCR** (Tesseract, `winocr` ou RapidOCR — `biblioteca.ocr` diz o que está instalado), e **`biblioteca.video url=…` baixa sozinho a legenda do YouTube**, inclusive a automática, em pt-BR, pt, en ou es. Vídeo sem legenda publicada ele recusa e explica que não transcreve áudio. A resposta é o trecho real com a referência ao lado — nada de resumo inventado — e só sai quando cobre ao menos metade das palavras do pedido; abaixo disso ele cala e vai para a web. Ainda dá para pedir `biblioteca.correlacoes`, que mostra termos presentes em duas ou mais fontes, e `biblioteca.digest`, que monta um `SKILL.md` com sumário, termos, números e citações. Em [`docs/BIBLIOTECA.md`](docs/BIBLIOTECA.md).

**Dados fora do pendrive:** `mover-dados.py --destino C:\JARVIS-DADOS` copia a pasta de dados (biblioteca, repositórios, documentos), **confere arquivo por arquivo**, grava `JARVIS_DADOS` no `.env` e manda reiniciar — sem apagar nada. `armazenamento.status` mostra o tamanho de cada área e o espaço livre.

**Google Drive como espaço de fora:** `usar-drive.bat` (duplo clique) leva **só** `biblioteca/` e `repos/` para uma pasta do Drive e grava `JARVIS_BIBLIOTECA` e `JARVIS_REPOS` no `.env`. O estado do agente (histórico, fila, skills criadas) fica no PC: é regravado a cada resposta e, no Drive, cada gravação viraria uma sincronização. Passo a passo completo, incluindo como pausar, limitar banda e não travar o PC de 4 GB: **[docs/GOOGLE-DRIVE.md](docs/GOOGLE-DRIVE.md)**.

**Repositórios, sem Git:** o JARVIS copia um repositório público do GitHub como `.zip`, extrai em `storage/repos`, mede o que veio (linguagem, dependências, README, árvore) e diz como rodar — `python -m pacote`, `npm run dev`, `make build`. Nada é instalado nem executado sem um “sim, pode” na conversa, e mesmo depois só roda `python`, `node`, `npm`, `npx` ou `make`, sem shell. Em [`docs/REPOSITORIOS.md`](docs/REPOSITORIOS.md).

**Agente local, sem modelo:** quando a frase não é um comando conhecido, o JARVIS procura a skill certa nas 290, preenche os campos a partir da própria frase e executa. Errou? Diga “não é essa, é a skill X” e ele aprende; “procure na web sobre isso” busca, guarda a resposta e o mesmo pedido passa a responder da memória. A página **Agente** mostra a fila do que não foi resolvido, as skills criadas e o histórico. Se não achar, monta uma **skill local** a partir de 20 receitas (contar palavras, somar, converter unidades, datas) e executa na hora; guarda o que criou em `storage/agente-local/skills.json`. Se nem receita servir, busca na web e devolve fontes + trecho, sem resumo. Nada disso chama provedor de IA. Detalhes e limites em [`docs/AGENTE-LOCAL.md`](docs/AGENTE-LOCAL.md).

**Correio sem entrar na conta:** exporte sua caixa (Takeout ou “Baixar mensagem” do Gmail) e ponha em `storage/correio`: `filtra meus e-mails por importância` classifica por regra determinística — **intimação/processo** (100), **fatura/boleto** (85, +10 se vence em até 7 dias), **governo** (75), **segurança** (70), **pessoal** (45), **newsletter** (5) — e ordena; `analisa meus e-mails enviados` mede o seu estilo (saudação, fecho, assinatura, tamanho, listas); `escreve um e-mail para a Ana sobre o relatório: enviar planilha; pedir retorno` monta o rascunho nesse estilo. **Não marca como lido e não envia.** Para o JARVIS ler a caixa *por programa* seria preciso OAuth; mas, com você já logado no navegador do seu PC, ele abre o Gmail pela tela (`mesa.*`, com a sua autorização) e `abre o gmail com as faturas` devolve a busca já filtrada para a sua sessão — sem chave e sem nada sair da máquina. Em [`docs/CORREIO.md`](docs/CORREIO.md).

**Habilidades de fora, sem instalar nada:** `importa a habilidade https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md` puxa o `SKILL.md`, lê o cabeçalho e guarda em `storage/habilidades.json`; “importa estas habilidades: <link 1> <link 2> …” importa até **20 por chamada**, sem um link com erro derrubar os outros; `usa a habilidade frontend-design para revisar a tela de login` devolve o roteiro inteiro com a sua pergunta em cima. Link de catálogo (skills.sh, clawhub) é seguido até o GitHub; link do botão **Raw** passa direto. Guarda **texto**, não instala, não executa e não pede token. **O limite, dito:** sem modelo configurado a habilidade é um roteiro para você seguir — o JARVIS não raciocina com ela, e habilidades que dependem de modelo pago (gerar imagem, Copilot) não funcionam só por serem importadas. Em [`docs/HABILIDADES.md`](docs/HABILIDADES.md).

**Catálogo das 100 skills, linha por linha:** salve a planilha em `storage/catalogo-skills.csv` e diga `carrega o catálogo de skills` — ele lê CSV com vírgula ou ponto e vírgula, com BOM ou `sep=`, tira duplicata e guarda o índice com resumo por categoria e fornecedor. `quais skills de design tem no catálogo` filtra por categoria, fornecedor, palavra ou rank; `importa as 5 primeiras do catálogo` acha o `SKILL.md` pela árvore do repositório e importa **até 10 por chamada** (o GitHub público aceita 60 pedidos por hora), devolvendo o que ficou e o motivo de cada falha. Das 100 linhas, as que não têm `repo_url` (clawhub, skillhub, Feishu) não são importáveis — o índice mostra, a importação diz o porquê. Em [`docs/CATALOGO.md`](docs/CATALOGO.md).

**O tópico `agent-skills` inteiro, em levas:** `pega as skills do tópico agent-skills do github` lê os repositórios mais estrelados do tópico, encontra cada `SKILL.md` pela árvore e soma tudo ao catálogo local (até 15 repositórios por chamada — 1 pedido de busca + 1 de árvore por repositório, dentro dos 60/hora do GitHub público). Depois é o mesmo fluxo do catálogo: filtrar, importar de 10 em 10, adaptar. Repositórios que são lista (`awesome-*`) ou plugin, sem `SKILL.md`, voltam pelo nome — não entram como skill. Em [`docs/CATALOGO.md`](docs/CATALOGO.md).

**Abrir programa e usar o cmd — sem entregar o shell:** `abre o bloco de notas`, `abre a calculadora`, `abre o arquivo contrato.pdf`, `qual é o meu ip`, `quanto tem de espaço em disco` — `pc.programas`, `pc.abrir-programa`, `pc.abrir-arquivo` e `pc.comando`. O programa sai de uma **lista fechada** (notepad, calc, paint, explorer, cmd, powershell, taskmgr, control, charmap, magnify) e o comando também (ipconfig, system-info, tasklist, ver, query user, disco, data, boot): **não existe campo para digitar linha livre**, então não há por onde injetar `;`, `|` ou `&&`. `.exe`, `.bat` e `.ps1` são recusados na abertura de arquivo, e tudo pede confirmação. Exige `JARVIS_HOST_PC=1`. Em [`docs/PC.md`](docs/PC.md).

**Antes de instalar, ele confere se roda:** `onde você salva o instalador?`, `meu pc aguenta o programa X?`, `o setup.exe roda no meu pc`, `baixa o programa do link …` — `instalador.maquina`, `instalador.destinos`, `instalador.analisar` e `instalador.baixar`. As opções de pasta vêm com espaço livre de verdade; o arquivo é lido pelo cabeçalho (32/64 bits, arquitetura, versão mínima de Windows declarada, .NET, MSIX, assinatura) e comparado com o Windows medido — a resposta é **roda / roda com ressalva / não roda / não dá para saber**, com o motivo. Quem instala continua sendo `sistema.executar`, com token. Em [`docs/INSTALADOR.md`](docs/INSTALADOR.md).

**Agenda, sem calendário na nuvem:** `marca audiência amanhã às 14h`, `o que eu tenho para hoje`, `minha agenda da semana`, `conclui o compromisso audiência` — `agenda.marcar`, `agenda.listar`, `agenda.concluir` e `agenda.remover`. A data é interpretada **sem modelo** e devolvida por extenso (`terça-feira, 27/10/2026 às 14:00`) para você conferir; se a frase não tiver data reconhecível, ele **recusa em vez de adivinhar**. Fica num `agenda.json` na raiz de dados. **Não avisa sozinho** — você pergunta, ele responde. Em [`docs/AGENDA-BACKUP-GIT.md`](docs/AGENDA-BACKUP-GIT.md).

**Lembrete da agenda, enquanto a janela está aberta:** cada compromisso guarda quantos minutos antes avisar (`avisar_antes`, 30 por padrão; `0` desliga). A tela consulta `GET /api/agenda/lembretes` a cada 45 s, mostra o aviso, escreve no chat e dispara a notificação do sistema quando você já deu permissão ao navegador; `o que está vencendo agora` é a mesma coisa pelo chat (`agenda.lembretes`, só leitura). O mesmo compromisso não avisa duas vezes (chave `id|quando|tipo`). **O limite:** sem serviço em segundo plano, com a janela fechada ninguém avisa. Em [`docs/AGENDA-BACKUP-GIT.md`](docs/AGENDA-BACKUP-GIT.md).

**O que ele já instalou, e como remover:** `sistema.instalados` lê o próprio `storage/host-audit.jsonl` e lista as instalações e remoções que terminaram com código 0 — com data, alvo e comando. Cada plano de instalação pendente traz a **remoção sugerida** (`dpkg:nome`, `rpm:nome`) e, no painel de planos, um botão **Desinstalar** que monta o plano de remoção; o plano aparece na mesma lista com **Executar remoção**. Para `.msi`/`.exe` ele **não inventa**: diz que o Windows exige o GUID do produto ou o desinstalador do fabricante. Em [`docs/SISTEMA.md`](docs/SISTEMA.md).

**Backup que abre:** `faz backup dos meus dados em E:/JARVIS-backups`, `quanto vai pesar o backup`, `quais backups eu tenho`, `restaura o backup … para D:/restaurado` — `backup.planejar`, `backup.criar`, `backup.listar` e `backup.restaurar`. Compacta `storage/` sem `.venv`, `node_modules`, `.git` nem a pasta de backups; grava SHA-256 ao lado, confere o `.zip` logo depois de escrever e avisa quando o destino está **no mesmo disco** dos dados (cópia no mesmo HD não protege de HD morto). Restaura só em pasta vazia, recusando caminho que escape dela. Em [`docs/AGENDA-BACKUP-GIT.md`](docs/AGENDA-BACKUP-GIT.md).

**O plano vira botão:** depois de `sistema.instalar`, o cartão **“Plano pronto para executar”** mostra o comando exato, o risco e o SHA-256, com o botão **Executar este plano** — que só funciona depois de você marcar a caixa, e continua exigindo `JARVIS_HOST_INSTALAR=1`. A página **Skills** lista no topo os planos pendentes (`GET /api/host/planos`, renovado a cada 30 s) e diz qual variável ligar quando a trava está desligada. O código de uso único só sai para quem está na própria máquina. Em [`docs/SISTEMA.md`](docs/SISTEMA.md).

**Instalar sem digitar token — só de dentro da máquina:** desde a 0.61.9 o token nem é pedido em `127.0.0.1` — o servidor preenche sozinho. `JARVIS_HOST_CONFIAR_LOCAL=1` deixa isso registrado no banner (e é o que `ligar-celular.bat` grava); `JARVIS_HOST_EXIGIR_TOKEN_LOCAL=1` é a trava de quem quer o token de volta até na própria máquina. A API preenche o token de host sozinha quando a requisição vem da própria máquina (`127.0.0.1`); pedido de outra máquina da rede continua exigindo o token, e `JARVIS_HOST_INSTALAR=1`, o plano com comando e assinatura, o código de uso único e a confirmação da tela continuam valendo. Requisição `POST` com `Origin` de outro site é recusada (`403 ORIGEM_RECUSADA`), sempre. Em [`docs/SISTEMA.md`](docs/SISTEMA.md).

**Git só de leitura:** `como está o git`, `o que mudou no git`, `últimos commits do git`, `qual o remoto do git` — `git.status`, `git.diff`, `git.log` e `git.remoto`. Quatro consultas com argumentos fixos, `shell=False`, `GIT_TERMINAL_PROMPT=0` e teto de 20 s; só aceita repositório dentro do projeto, da raiz de dados ou de `storage/repos`. **Não faz `commit`, `push`, `pull`, `checkout` nem `reset`** — nem como texto livre, porque não existe campo para linha de comando. Em [`docs/AGENDA-BACKUP-GIT.md`](docs/AGENDA-BACKUP-GIT.md).

**A leva do skills.sh em um pedido:** `importa as 8 habilidades do skills.sh` → `habilidades.pack` puxa o `SKILL.md` de frontend-design, web-design-guidelines, react-best-practices, react-components, remotion, grill-me, grill-with-docs e nano-banana-pro pela API pública do GitHub e guarda o texto; `usa a habilidade frontend-design para …` devolve o roteiro junto com o seu pedido. Sem chave e sem instalar nada — e sem fingir que a habilidade “pensa”. Em [`docs/HABILIDADES.md`](docs/HABILIDADES.md).

**Cultura: livro completo, de graça e legal:** `onde acho livros completos de graça` mostra as sete fontes que prestam — **Project Gutenberg** (~79 mil obras em texto puro, API aberta, sem chave), Standard Ebooks, Open Library, Wikisource, Domínio Público (MEC), LibriVox e DOAB. `procura o livro Dom Casmurro` busca no Gutenberg e devolve o `id`; `baixa o livro 59863` puxa o `.txt`, tira o cabeçalho legal e guarda na biblioteca — de onde `biblioteca.buscar` já acha trecho por assunto. `faz uma persona do livro Dom Casmurro` mede o estilo (frase média, diálogo, pontuação, vocabulário) e grava o cartão em `storage/personas.json`, com os limites ditos: é estilo medido, não o autor; não inventa citação. Obra ainda protegida por direito autoral **não** entra. Em [`docs/CULTURA.md`](docs/CULTURA.md).

**Adaptar o que vem de fora:** `adapta a habilidade frontend-design para mim` transforma o guia importado em **skill local de procedimento** (`local.proc-…`), com os passos numerados, e ela passa a responder no chat pelo nome. O que continua verdade: é um roteiro para seguir — não é código executando sozinho.

**GitHub público, sem Git e sem token:** `ficha do repositório vercel-labs/agent-skills`, `lista os arquivos`, `lê o SKILL.md`, `busca repositório de agent skills` — quatro skills (`github.repo`, `github.arquivos`, `github.arquivo`, `github.buscar`) que falam com a API pública do GitHub: estrelas, linguagem, licença, árvore de arquivos e o texto de qualquer arquivo. Sem `clone`, sem `push`, sem repositório privado; 60 pedidos por hora. É o caminho para achar a habilidade e importar. Em [`docs/HABILIDADES.md`](docs/HABILIDADES.md).

**Mouse e teclado, a seu pedido:** você autorizou o JARVIS a usar o mouse e o teclado quando precisar. `clica em 500 300`, `move o mouse para 800 600`, `digita ola mundo`, `aperta ctrl v`, `foca a janela do bloco de notas` — cada uma pede “sim, pode” antes de encostar no cursor, e se **você mexer o mouse** no meio do movimento ele **para na hora** em vez de clicar em outra coisa. Não há captura de tela nem OCR: ele move para onde você mandou e diz a coordenada na confirmação. `onde esta o mouse` só lê. Em [`docs/AGENTE-LOCAL.md`](docs/AGENTE-LOCAL.md).

**Pesquisa com fonte, sem token:** `pesquisar e responder quem foi Machado de Assis` busca no **DuckDuckGo**, na **Wikipédia** ou no **YouTube**, lê as primeiras páginas e devolve as fontes com o trecho lido — marcando de qual plataforma veio cada resultado, e seguindo mesmo quando uma delas cai. Buscar e ler **não pedem token**: basta rede ligada na subida (`JARVIS_HOST_REDE=1`). Se houver um provedor de IA configurado, o texto lido vira material citável para ele resumir; sem provedor ele não falha, entrega fontes + trecho, sem resumo. O token de `storage/host-token.txt` só aparece quando a skill **grava ou executa**. Detalhes em [`docs/PESQUISA.md`](docs/PESQUISA.md).

## Executar em desenvolvimento

Requisitos: **Node.js 22+** e **Python 3.11+**.

```bash
npm install
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm run dev
```

Antes de subir, `npm run checar` mede a máquina e a pasta: versão de Node e Python, bibliotecas, `.env`, chave de IA, espaço livre, sistema de arquivos do drive, `.git` e portas — cada linha que falta vem com o comando que resolve. Detalhes em [`docs/PENDRIVE.md`](docs/PENDRIVE.md).

`npm run dev` inicia os dois processos:

- interface em `0.0.0.0:5173`;
- API Python em `0.0.0.0:8000`.

**Modo sem Node.** A interface compilada também é versionada em `web-dist/` (1,6 MB, 19 arquivos). Com ela, `py iniciar.py` sobe API e tela juntas em <http://127.0.0.1:8000> **sem `npm install`** — útil em pendrive lento ou máquina sem Node. `npm run build:embutido` regenera a pasta a partir do React.

**Sem compilador no Windows.** O `requirements.txt` pede `uvicorn` **sem** o extra `[standard]`: o extra arrasta o `PyYAML`, que não publica wheel para Python 3.15 no Windows e faz o `pip` parar em *"Microsoft Visual C++ 14.0 or greater is required"*, abortando a instalação inteira. O servidor não usa YAML nem WebSocket. Quem quiser os aceleradores opcionais (`httptools`, `websockets`, `watchfiles`) instala `requirements-rapido.txt`, que é o mesmo conjunto sem o `PyYAML`.

**Editáveis no Bloco de Notas antigo.** `requirements.txt`, `requirements-dev.txt`, `requirements-rapido.txt` e `.env.example` são gravados com quebra de linha **CRLF** (o `.gitattributes` impede o git de converter): o Notepad do Windows 10 anterior ao build 17763 mostra arquivo LF como uma linha única e, se salvar nesse estado, amassa o arquivo.

O navegador usa somente URLs relativas `/api`; não é necessário chamar `localhost` a partir do código da interface.

A chave de IA entra por `py configurar-chave.py`: o script pede a chave sem ecoar, não deixa rastro no histórico e grava o `.env` com quebra de linha do Windows. `--ver` mostra o que está gravado (mascarado) e `--limpar` apaga só a chave.

Para rodar de um pendrive — requisitos por sistema, cópia do projeto, dependências por máquina, limites de formato do drive e a skill que traz os arquivos da pasta Downloads — consulte [`docs/PENDRIVE.md`](docs/PENDRIVE.md).

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

A **0.36.0** acrescenta `files.import` (“Importar do computador”): copia PDFs, documentos Office e textos da pasta de downloads da máquina para a área isolada, com token de host, confirmação, simulação, lista fechada de nove formatos e tetos de 64 MB por arquivo e 512 MB por lote. Ela **copia, não move**, e não apaga nem executa nada. É a skill que leva os arquivos do PC para o pendrive quando o JARVIS roda de lá — o passo a passo está em [`docs/PENDRIVE.md`](docs/PENDRIVE.md).

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

Sobre esse motor entra a **camada editorial**, adaptada de [`cathrynlavery/diagram-design`](https://github.com/cathrynlavery/diagram-design) em outras sete skills. Ela decide **antes** do traço: escolhe entre **45 tipos** e **nove padrões semânticos**, fixa orçamento (`≤9 nós`, `≤12 setas`, `≤2 acentos`, `≤2 chamadas`), converte a marca em **11 papéis de cor** com contrato de contraste WCAG — 4,5:1 para texto, 3:1 para marca essencial — e propõe o menor ajuste de luminosidade que passa, preservando o matiz. Confere também **12 anti-padrões** no arquivo (brilho ciano, sombra, raio grande, mono total, rótulo sem máscara, diagonal) e as **seis regras de conector** medidas na geometria declarada: ortogonal com `r=8`, folga de rótulo de 6–10px, paralelos a ≥12px, leque `L·k/(N+1)`, trânsito tracejado e máscara que nunca sobrepõe um nó desenhado depois.

Importar é redesenhar: Mermaid, draw.io e Excalidraw entram por parser próprio, a **escada de degradação** corta decorativo, duplicata, cluster de folha, sumidouro e infraestrutura transversal — e tudo o que sai aparece no **recibo de fidelidade**. A entrega confere o contrato de SVG acessível (`role="img"`, `<title>` primeiro filho, IDs prefixados, `<desc>` de conteúdo), o `viewBox` do preset, o `min-width` igual à largura, a rolagem local e a liberação na impressão.

Nada dos dois upstreams é instalado ou executado: sem `npx skills add`, `archify.zip`, `bin/archify.mjs`, `finalize`, `visual-check`, plugins DSH, Chrome de inspeção, `verify-geometry.py`, `self_check.py`, `lint-render.py` ou `export_png.py`. Consulte [`docs/DIAGRAMAS.md`](docs/DIAGRAMAS.md), a licença MIT do archify em [`docs/licenses/tt-a1i-archify.txt`](docs/licenses/tt-a1i-archify.txt) e a do diagram-design em [`docs/licenses/cathrynlavery-diagram-design.txt`](docs/licenses/cathrynlavery-diagram-design.txt).

## Carreira

A página **Carreira** (`/carreira`) adapta [`career-ops-hq/career-ops`](https://github.com/career-ops-hq/career-ops) em sete skills locais. O upstream é um agente de busca de emprego que roda no CLI de IA do usuário: avalia vagas antes de candidatar, adapta o currículo para ATS, escreve carta, prepara entrevista e mantém um tracker. Aqui fica o que sobrevive sem portal, navegador ou IA: **triagem com evidência, ATS, bullets, carta, entrevista, funil e catálogo**.

A nota não é média. Cada requisito recebe uma banda de importância (`critical`, `high`, `meaningful`, `preferred`, `low_signal`) e um nível de evidência (`stated`, `structural`, `inferred`) — uma inferência nunca sobe para obrigatório. Cinco dimensões entram com peso declarado (aderência 45%, alvo 20%, remuneração 15%, cultura 10%, risco 10%) e tetos nomeados limitam o resultado: regra dura do perfil → 2,0, dois requisitos centrais ausentes → 3,5, contradição cultural → 3,4, anúncio suspeito → 2,5. A confiança é derivada: alta só com as cinco dimensões sustentadas; baixa quando falta currículo, alvo ou duas dimensões. As faixas seguem o upstream: **≥4,5 aplicar agora; 4,0–4,4 vale aplicar; 3,5–3,9 hesitar; <3,5 não aplicar**. A linha ética de 4,0 é decisão declarada, não probabilidade.

A legitimidade do anúncio é lida por treze sinais catalogados (idade, faixa larga, PJ, cobrança de candidato, jornada, requisito protegido, triagem automática…), devolve um tier — alta confiança, cautela ou suspeito — com nota 0–100 e **não altera a nota 1–5**. Cada sinal é observação sobre o texto, nunca acusação.

O ATS tem duas etapas: lints de payload (empresa no cargo, parêntese no nome da empresa, duas faixas de data na mesma entrada, competências duplicadas) e um placar de **100 pontos com pesos fixos** sobre o HTML — 15 texto, 20 cabeçalhos, 15 e-mail no corpo, 20 coluna única, 10 imagem, 10 fonte, 5 UTF-8, 5 texto oculto — com nota A–F. Sem HTML, o placar é parcial e a letra não é emitida. Nada é reescrito.

A carta só existe com três insumos: vaga, currículo com conquista verificável e pesquisa da empresa. Com eles, monta três ou quatro parágrafos citando só números que existem no currículo ou no perfil, e checa clichê, tamanho, marcador, número sem origem e nome da empresa. A entrevista transforma os seis requisitos principais em perguntas por tipo, cruza com um banco de histórias STAR e separa perguntas para a empresa dos sinais a esclarecer. O funil lê tabela, TSV ou CSV e calcula conversão, coortes e candidaturas paradas, declarando censura e amostra pequena.

Nada do upstream é instalado ou executado: sem `npx @santifer/career-ops init`, plugins de CLI, os ~200 scripts Node, o dashboard Go, o runner de batch ou workflows. Consulte [`docs/CARREIRA.md`](docs/CARREIRA.md) e a licença MIT em [`docs/licenses/career-ops-hq-career-ops.txt`](docs/licenses/career-ops-hq-career-ops.txt).

## Navegador assistido

A página **Navegador** (`/navegador`) adapta [`citrolabs/ego-lite`](https://github.com/citrolabs/ego-lite) em sete skills locais. O upstream é um navegador próprio para agentes: cada tarefa roda numa *space* isolada, o agente escreve JavaScript contra uma API pequena e enxerga a página por um snapshot de acessibilidade com referências e locators estáveis. Aqui fica o que sobrevive sem navegador: **leitura do snapshot, resolução de alvo, roteiro de rodadas, checagem, recibos e limites**.

O snapshot é uma árvore de dois espaços por nível (`root`, depois `papel "nome" [ref=N, loc=...]`). O parser aceita marcador, nome com escape e metadados com colchetes aninhados, distingue `[ref=…]` dentro do nome acessível de metadado real e guarda o caminho de frames. Nove achados cobrem referência repetida, árvore sem alvo acionável, recuo ímpar, locator instável, iframe sem referência e árvore densa. Nada é inferido do DOM: vale o que o snapshot declarou.

O alvo aceita `@N`, `ref=N`, `text=` exato ou livre, `loc=role:`, `loc=css:`, `loc=href:`, CSS e `>> nth=N`; XPath é recusado com alternativa. A regra é a do upstream: **documento principal antes dos frames**, e dois matches no mesmo escopo são ambíguos — a skill devolve candidatos e não escolhe. O comando sai pronto (`await page.click("@21", { label: "entrar na conta" })`), com `label` só nas ações de ponteiro e 3 a 6 palavras.

O roteiro tem três rodadas — abrir e observar, agir, verificar e fechar — com orçamento de 2 a 8, uma space por objetivo, `p1` reaproveitada e nenhum dado inventado: o que falta vira `<valor real>`. Verbo de risco (pagar, excluir, publicar) insere o ponto de confirmação e o `handOff`. A checagem aplica **15 padrões** (espera fixa, space nova, `finish` duplicado, `label` proibido, Playwright, caminho relativo, retry cego…) e classifica os passos por **dez estados** do alvo. Os recibos separam despacho de verificação e cobram popup, diálogo, download salvo e `finish` único. Os limites classificam cada ação como **bloqueada, para confirmar ou liberada**, com o handoff escrito.

Nada do upstream é instalado ou executado: sem app, DMG/EXE, `npx skills add`, launcher, CDP, plugins de CLI ou SDK. Consulte [`docs/NAVEGADOR.md`](docs/NAVEGADOR.md) e a licença MIT em [`docs/licenses/citrolabs-ego-lite.txt`](docs/licenses/citrolabs-ego-lite.txt).

## Escritório assistido

A página **Escritório** (`/escritorio`) adapta [`googleworkspace/cli`](https://github.com/googleworkspace/cli) em sete skills locais. O upstream é um CLI que não carrega lista fixa de comandos: lê o documento de descoberta do Google em tempo de execução e monta a árvore `serviço → recurso → método`, com saída JSON, `--dry-run`, paginação automática e códigos de saída estáveis. Aqui fica o que sobrevive sem binário, credencial ou rede: **comando, receita, páginas, lote, escopos e triagem de erro**.

O montador valida serviço, recurso e método, compacta `--params` e `--json` em objetos JSON com aspas simples (e `'\''` para aspas internas), confere parâmetro de caminho obrigatório por recurso e classifica o risco em leitura, escrita ou destrutivo. Escrita ganha `--dry-run`; leitura nunca. Ajudantes (`+send`, `+append`, `+agenda`) têm lista branca de flags por serviço. `--upload` só vale no Drive; `--sanitize` exige o nome completo do template do Model Armor.

Quinze receitas cobrem agenda, standup, digest, triagem, envio e resposta de e-mail, leitura e append de planilha, upload e organização de pasta, convite de evento, arquivamento por rótulo, tarefa a partir de e-mail, relatório e arquivos grandes. Cada passo declara por que existe, como saber que deu certo e o ensaio equivalente — e a receita diz o que fazer se der errado. A leitura de páginas aceita uma página, NDJSON ou array, detecta a chave dos itens, conta únicos e duplicados e monta a próxima chamada com `pageToken`. O planejador de lote divide itens nos tetos da operação (100 em Sheets/Docs, 1000 no Gmail, uma escrita por item no Drive e no Calendar) e avisa quando o `batchUpdate` é atômico.

Os escopos saem do princípio do menor acesso: cada operação aponta o mínimo, superconjunto conta (`drive` cobre `drive.file`), falta e sobra aparecem separadas e o limite de ~25 escopos de app em teste é checado. A triagem de erro lê código de saída, status e `reason`, devolve causa, ação e comando, e **não repete escrita às cegas**: uma chamada pode ter sido aplicada mesmo com resposta de erro.

Nada do upstream é instalado ou executado: sem release, `cargo install`, Homebrew, Nix, `npm install -g`, `gws auth setup`, service account, extensão do Gemini, `npx skills add` ou chamada ao Google. Consulte [`docs/ESCRITORIO.md`](docs/ESCRITORIO.md) e a licença Apache-2.0 em [`docs/licenses/googleworkspace-cli.txt`](docs/licenses/googleworkspace-cli.txt).

## Estação do agente

A página **Estação** (`/estacao`) adapta [`feder-cr/invisible_dots`](https://github.com/feder-cr/invisible_dots) e é a primeira parte do JARVIS que **executa de verdade**. O upstream é um agente self-hosted em que cada instância é uma VM Linux com navegador por identidade e permissões `allow`/`ask`/`deny`. Aqui a máquina não existe: o agente roda no seu próprio sistema de arquivos, dentro de `storage/user-files`.

O **executor** (`server/estacao_runtime.py`) faz `bash -lc` com timeout, lê e grava arquivos, lista diretórios, busca com regex e cria automações de cron. Toda chamada passa por uma decisão: `allow` roda, `ask` fica pendente com os argumentos completos e `deny` recusa. A política é editável na página e persiste em SQLite (`storage/estacao/estacao.db`, fora do Git). Aprovar uma chamada a executa uma única vez — a linha é reivindicada com `UPDATE ... WHERE estado='pendente'`, então clique duplo não roda duas vezes.

Cada chamada gera **recibos** em ordem (`intent`, `aprovado`, `ok`/`erro`, `recusado`, `negado`). Se o processo cair no meio, a linha fica em `executando` e a recuperação a marca `interrompido`, avisando que o resultado é desconhecido e que o estado deve ser conferido antes de repetir — chamada interrompida nunca roda de novo. A **agenda** usa cron de cinco campos, dispara a cada 30 s pelo agendador da API e passa pelo mesmo gate; três falhas seguidas pausam a automação.

As sete skills de análise continuam só lendo texto: plano de tarefa durável, auditoria da matriz de permissões, leitura de recibos, validação de agenda, classificação de efeito e higiene de notas e skills. A classificação é por **efeito** — `liberado`, `confirmar`, `irreversível` —, não por assunto; quem decide executar é a política do executor.

**Confinamento:** caminhos presos ao diretório da Estação, ambiente do subprocesso reduzido a `PATH`/`HOME`/`LANG`/`TERM`, timeout com `SIGKILL` no grupo. **Não é** jaula de sistema operacional: um `exec` aprovado é shell com os seus privilégios. Isolamento real exigiria VM ou contêiner — componente do upstream que este repositório não tem (sem QEMU, imagem dourada, navegador, MCP, Telegram ou WhatsApp).

Consulte [`docs/ESTACAO.md`](docs/ESTACAO.md) e a licença MIT em [`docs/licenses/feder-cr-invisible-dots.txt`](docs/licenses/feder-cr-invisible-dots.txt).

## Curadoria de listas

A página **Curadoria** (`/curadoria`) adapta [`hesreallyhim/awesome-claude-code`](https://github.com/hesreallyhim/awesome-claude-code) — **CC BY-NC-ND 4.0** — e trata a lista como decisão editorial, não como catálogo. O upstream é um índice de recursos com formulário de recomendação, validação automática, CSV de 12 colunas, README gerado e um ticker de estrelas. Aqui nenhum dos 263 recursos, nenhuma descrição e nenhuma categoria de lá foi copiado: a licença proíbe derivados, então o que o módulo implementa é o **mecanismo**, com dados seus.

`server/curadoria.py` valida a entrada contra a regra que evita lista de projeto imaturo — **14 dias de desenvolvimento ativo ou 100 estrelas** — e devolve a linha CSV pronta, com ID opaco de 8 dígitos hexadecimais. Também recusa `http://`, espaço e metacaractere de Markdown no link, categoria fora da configuração, categoria fechada, subcategoria órfã, cadastro ou pagamento obrigatório, licença não identificável, descrição com emoji, segunda pessoa, superlativo de venda e chamada para clicar. A **descrição** é o campo que separa lista de catálogo publicitário: uma linha, presente do indicativo, sem falar com o leitor.

O **catálogo** agrupa o CSV na ordem da configuração, não na ordem do arquivo, e não descarta o que não reconhece: categoria desconhecida aparece no fim, marcada. O **README** é derivado da base — sumário com âncoras do GitHub, seção vazia fora do arquivo, nome com colchete escapado —, então ninguém edita duas fontes. O **ticker** compara dois snapshots `dono/repo,estrelas`, ordena por variação e aplica proteções contra imitação de produto e provável cópia de código-fonte. A **higiene** audita dez checagens: ID único e no formato, link válido, duplicata por link e por nome, data de inclusão, checagem antiga, estagnação sem justificativa e o estilo de cada descrição.

Nada é buscado na rede: elegibilidade, licença e atividade são o que o formulário declara, e o parecer diz isso. Nada é gravado: a saída é texto para você colar no seu repositório.

Consulte [`docs/CURADORIA.md`](docs/CURADORIA.md) e a atribuição em [`docs/licenses/hesreallyhim-awesome-claude-code.txt`](docs/licenses/hesreallyhim-awesome-claude-code.txt).

## Marketing mensurável

A página **Marketing** (`/marketing`) adapta [`coreyhaines31/marketingskills`](https://github.com/coreyhaines31/marketingskills) — **MIT** — e fica com a parte que se pode medir. O upstream tem 52 skills de redação; nenhuma foi portada, e nenhum texto de lá foi copiado: o JARVIS mede o que existe, não escreve anúncio nem promete resultado.

`server/marketing.py` faz a conta do funil e da economia unitária — impressões, cliques, leads, clientes, CAC, ROAS, payback, LTV/CAC — com as taxas que você informa, e aponta quanto cada alavanca precisa mudar para chegar ao CAC alvo e qual verba a meta de ARR exige. Dimensiona teste A/B pela fórmula de duas proporções, com alfa corrigido para múltiplas variantes e duração que respeita o ciclo de compra. Confere a URL de campanha — minúsculas, hífen, `medium` do vocabulário, sem PII, sem encurtador — e devolve a URL canônica. Revisa o e-mail antes do disparo: assunto, pré-cabeçalho, CTA, descadastro e as marcas de texto gerado. Audita o HTML da página sem executar JavaScript: título, description, H1, hierarquia, alt, canonical, idioma, JSON-LD e os sinais que um motor de resposta extrai. E conta caractere por peça contra o limite de Google, Meta e LinkedIn, recusando afirmação não verificável.

Nada é buscado na rede: nenhuma conta de anúncio, pixel, CRM ou ferramenta de análise é acessada, e o parecer declara isso em `limitations`. As tabelas de tamanho de amostra do upstream se contradizem entre si, então a grade publicada em `marketing.regras` é calculada na hora, não copiada.

Consulte [`docs/MARKETING.md`](docs/MARKETING.md) e a licença MIT em [`docs/licenses/coreyhaines31-marketingskills.txt`](docs/licenses/coreyhaines31-marketingskills.txt).

## Rigor científico

A página **Ciência** (`/ciencia`) adapta [`K-Dense-AI/scientific-agent-skills`](https://github.com/K-Dense-AI/scientific-agent-skills) — **MIT**, 177 skills — e fica com a parte que se pode conferir no texto. Nenhum dos 177 pacotes foi importado e nenhum script do upstream é chamado: as contas vêm das fórmulas publicadas, e a leitura é lexical e numérica sobre o que você cola.

`server/ciencia.py` dimensiona o estudo pelas quatro quantidades do poder — n, efeito, alfa e poder — com alocação desigual, correção de multiplicidade, perda esperada, efeito de desenho por cluster e a recusa explícita do poder observado. Confere o relato estatístico: p exato contra limiar, IC na ordem certa, média com dispersão, percentual com denominador e equivalência só com margem declarada. Audita o desenho em 14 itens ponderados por tipo — ensaio, observacional, diagnóstico e animal — e pega pseudorreplicação, confundimento por dia de execução e atribuição por conveniência. Checa os nove itens de reprodutibilidade, de dado e código a versão, semente, ambiente, registro e identificador. Valida método analítico contra o critério do ICH M10 (cromatográfico ou LBA): recuperação, RSD, R², LOD e LOQ por nível, com a folga do LLOQ. E lê o manuscrito contra CONSORT 2025, STROBE, STARD, PRISMA 2020 ou ARRIVE 2.0, apontando seção ausente e afirmação de cura, risco zero ou prova.

Nada é executado: nenhum repositório, DOI, registro ou dado é baixado, e nenhum teste é reexecutado. O critério de aceitação é o que você declara — fixá-lo depois de ver o resultado é justamente o que a camada aponta.

Consulte [`docs/CIENCIA.md`](docs/CIENCIA.md) e a licença MIT em [`docs/licenses/k-dense-ai-scientific-agent-skills.txt`](docs/licenses/k-dense-ai-scientific-agent-skills.txt).

## Confiança em skill de terceiro

A página **Confiança** (`/confianca`) parte de [`VoltAgent/awesome-openclaw-skills`](https://github.com/VoltAgent/awesome-openclaw-skills) — **MIT**, mais de 5.400 skills indexadas — e fica com a parte que se pode conferir antes de deixar uma skill rodar. Nenhuma das skills do índice foi baixada, importada ou executada: a leitura é lexical sobre o texto que você cola.

`server/confianca.py` lê a ficha e cobra o que a faz utilizável: nome em kebab-case, descrição com gatilho, licença, versão, autoria e lista exata de ferramentas. Varre o risco em 15 classes — comando destrutivo, download executado, credencial, exfiltração, injeção, ofuscação, privilégio, persistência, segredo em claro — e nota de 0 a 100, com bloqueio para a combinação de credencial lida e enviada para fora. Compara a permissão declarada com a usada nas oito capacidades e aponta a ferramenta ociosa e a usada sem declaração. Confere a receita de instalação: versão fixa ou flutuante, download canalizado para o shell, `sudo`, escopo global e script de instalação. Audita o índice contra as dez regras do próprio repositório de origem — link para o registro canônico, descrição curta, nome kebab-case, sem duplicata — e caça variações de teste e descrições iguais.

Nada é aberto, baixado ou instalado, e o parecer não usa modelo de linguagem: o veredito sai da soma dos pesos, e a ausência de padrão não é atestado de segurança — é o que o texto colado não tem.

Consulte [`docs/CONFIANCA.md`](docs/CONFIANCA.md) e a licença MIT em [`docs/licenses/voltagent-awesome-openclaw-skills.txt`](docs/licenses/voltagent-awesome-openclaw-skills.txt).

## Contexto de conversa

A página **Contexto** (`/contexto`) parte do subsistema de contexto do [`CherryHQ/cherry-studio`](https://github.com/CherryHQ/cherry-studio) — **AGPL-3.0**, 52 mil estrelas — e reimplementa a regra em Python. Nenhuma linha do upstream foi copiada e nenhum tokenizador BPE é baixado: a estimativa é lexical e a conta é explícita.

`server/contexto.py` divide a janela entre prompt e resposta com a precedência da reserva — chamada, assistente, teto do modelo só no Anthropic — e piso de 20% para a entrada; mede a conversa com 1 token por caractere CJK, 1 a cada 4 latinos e 1 a cada 3 em código, e aplica as fórmulas de imagem por dialeto (750 px por token no Anthropic, 85 + 170 por ladrilho no OpenAI, 258 por recorte no Google) e de áudio/vídeo por segundo. Corta o histórico por turno atômico, preservando sistema e últimos turnos, sem nunca partir uma chamada do resultado dela. Saneia o que o provedor recusa: resultado órfão, chamada sem retorno e histórico que não abre com o usuário. Prepara o resumo de retenção com decisão, número, caminho e pendência, estubando saída de ferramenta na escalada 4.000 → 1.000 → 200 → 0 caracteres. E ancora o contexto em `total − entrada + inicial`, com custo por milhão e custo repetido em hops.

Nada é enviado a modelo: janela, preço e `usage` são os que você informa, e a fatura do provedor continua sendo a fonte.

Consulte [`docs/CONTEXTO.md`](docs/CONTEXTO.md) e o aviso AGPL-3.0 em [`docs/licenses/cherryhq-cherry-studio.txt`](docs/licenses/cherryhq-cherry-studio.txt).

## Seleção de skills

A página **Seleção** (`/selecao`) parte do **AAS Core** do [`sickn33/agentic-awesome-skills`](https://github.com/sickn33/agentic-awesome-skills) — **MIT**, 48 mil estrelas, 2.743 skills em 114 categorias — e faz o que o Core recusa fazer: pontuar. O `search_skills` de lá devolve ordem estável sem score e o `compose_stack` só valida ids; aqui a conta é explícita.

`server/selecao.py` lê o briefing contra as **dez dimensões de capacidade** do contrato de cobertura do Core, ranqueia o catálogo com **BM25** (k1 1,2 e b 0,75, peso 3 no nome, 2 na categoria e 1 na descrição), valida a stack — id inexistente, repetido, acima de 128, alvo incompatível, lacuna de dimensão, sobreposição e orçamento de risco —, monta um plano com artefato, checagem de saída e portão de aprovação para skill crítica, mapeia a cobertura por dimensão e audita a saúde do índice.

O catálogo é o JSON que você cola — o índice completo tem 2,1 MB e o formato compacto `id | categoria | risco | descrição`, 506 KB. Nada é instalado, composto ou gravado.

Consulte [`docs/SELECAO.md`](docs/SELECAO.md) e a licença MIT em [`docs/licenses/sickn33-agentic-awesome-skills.txt`](docs/licenses/sickn33-agentic-awesome-skills.txt).

## Revisão de código

A página **Revisão** (`/revisao`) parte do [`alibaba/open-code-review`](https://github.com/alibaba/open-code-review) — **Apache-2.0**, 48 mil estrelas — e trata as três falhas conhecidas de revisão feita só por agente: cobertura incompleta em diff grande, comentário na linha errada e qualidade que varia com o prompt.

`server/revisao.py` lê o diff unificado com hunks, classifica cada caminho em **doze classes** com peso e decisão de revisar (lockfile e arquivo gerado ficam fora), agrupa o que se lê junto — código com o seu teste, todas as locales do mesmo pacote — com teto de 12 arquivos e 20 mil tokens, normaliza a severidade dos comentários em quatro níveis e duas fontes, confere se cada comentário cai em linha que existe no hunk (precisão contra o piso de 80 %), compara regra e agente por Jaccard para achar o mesmo problema reportado duas vezes, mede a cobertura contra o que o diff pedia (piso de 60 %) e monta o `rule.json` com uma regra em prosa por caminho.

O diff é o texto que você cola: nada é aplicado, o repositório não é lido e nenhum comentário é publicado.

Consulte [`docs/REVISAO.md`](docs/REVISAO.md) e a atribuição Apache-2.0 em [`docs/licenses/alibaba-open-code-review.txt`](docs/licenses/alibaba-open-code-review.txt).

## Submissão de artefatos

A página **Submissão** (`/submissao`) parte do [`github/awesome-copilot`](https://github.com/github/awesome-copilot) — **MIT**, 40 mil estrelas — e responde, com conta explícita, o que todo catálogo de skill pergunta antes de ler o conteúdo: o arquivo está na pasta certa, o front matter tem `name` e `description`, o texto manda rodar `curl | sh`, a licença é SPDX e o link aponta para arquivo que veio no envio.

`server/submissao.py` lê o front matter por tipo de artefato (skill, agente, instrução, hook, plugin, workflow e prompt) e confere nome, descrição, tags, semver e URL; valida a estrutura do envio — caminho absoluto, saída por `..`, asset acima de 5 MB, vizinho obrigatório, nome repetido, arquivo oculto e caixa alta; varre o texto com **nove regras de risco** (`curl | sh`, `npx -y`, `sudo rm -rf`, versão flutuante, segredo, caminho absoluto…) com trecho mascarado e truncado em 180 caracteres; lê a licença como **expressão SPDX** com `AND`/`OR`/`WITH`, 45 ids e 10 exceções, separando identificador desconhecido de sintaxe quebrada; e confere cada link do envio contra o próprio envio — arquivo, âncora e caixa. O portão junta as cinco checagens e devolve a decisão do rótulo: `requires-submitter-fixes` se houver bloqueio, `awaiting-review` se não houver conteúdo para conferir e `ready-for-review` quando o envio está limpo.

O envio é o texto que você cola, com um cabeçalho `>>> caminho` por arquivo: nada é instalado, nenhum `vally lint` roda e nenhum rótulo é aplicado.

Consulte [`docs/SUBMISSAO.md`](docs/SUBMISSAO.md) e a atribuição MIT em [`docs/licenses/awesome-copilot.txt`](docs/licenses/awesome-copilot.txt).

## Memória de agente

A página **Memória IA** (`/memoria-ia`) parte do [`topoteretes/cognee`](https://github.com/topoteretes/cognee) — **Apache-2.0**, 32 mil estrelas — e trata as quatro perguntas de quem tenta dar memória a um agente: em que via procurar, o que vira nó e aresta, o que promover da sessão e qual é o raio de alcance do esquecimento.

`server/memoria.py` escolhe a via de recuperação pela forma da pergunta — `chunks`, `grafo`, `hibrido`, `resumo`, `temporal`, `codigo`, `procedimento` e `regras` — somando **29 regras com peso**, descartando o que aparece depois de uma negação e declarando limiar e margem; extrai **sete tipos de entidade** (nome, sigla, código, arquivo, data, valor e local) e as relações declaradas em `sujeito -> relação -> objeto`, sem modelo de linguagem; mede o grafo com grau, componente, ciclo, isolado, hub e densidade; pontua cada turno da sessão como lição em potencial — marcador explícito, verbo de fato, repetição e feedback contra fala do agente e confirmação curta — para dizer o que promover; recupera com **BM25 + afinidade + decaimento de meia-vida de 180 dias** e devolve o lastro de cada resultado; e planeja o esquecimento por item, dataset ou total, com `somente_memoria` e o raio de alcance do que ainda cita o alvo.

A memória é o texto que você cola: nenhum modelo é chamado, nenhum embedding é gerado e nada é gravado.

Consulte [`docs/MEMORIA.md`](docs/MEMORIA.md) e a atribuição Apache-2.0 em [`docs/licenses/topoteretes-cognee.txt`](docs/licenses/topoteretes-cognee.txt).

## Portabilidade de skills

A página **Portabilidade** (`/portabilidade`) parte do [`alirezarezvani/claude-skills`](https://github.com/alirezarezvani/claude-skills) — **MIT**, 28 mil estrelas — e responde à pergunta de quem publica o mesmo procedimento em mais de uma ferramenta: o que cada alvo aceita, o que a conversão copia ou descarta, o que divergiu do espelho, onde duas skills colidem e como o lote vira plugin de marketplace.

`server/portabilidade.py` lê o bundle pelo cabeçalho `>>> caminho` (ou por `caminho | bytes | sha256`) e agrupa cada arquivo na skill mais próxima acima dele; audita **front matter, nome, slug, descrição, script citado no corpo, `allowed-tools`, licença, versão, tamanho e arquivo solto**; converte para **treze alvos** — Claude Code, Codex, Gemini, OpenClaw, Hermes, Vibe, Windsurf, OpenCode, Antigravity, Cursor, Kilo Code, Augment e Aider — com quatro estilos de empacotamento (pasta, espelho, regra e convenção) e cinco ações por arquivo (copiar, reescrever, embutir, gerar e descartar); compara fonte e espelho por conteúdo ou hash e classifica cada caminho em igual, alterado, faltando, sobrando ou não comparável; caça duplicata e slug repetido pelo destino, não pelo nome declarado; e monta o lote com `plugin.json` de **exatamente oito chaves** — `name`, `description`, `version`, `author`, `homepage`, `repository`, `license` e `skills`, com caminho prefixado por `./` — mais o `marketplace.json` que agrupa os plugins por domínio.

O bundle é o texto que você cola: nada é copiado, escrito ou instalado, nenhum `convert.sh` roda, nenhuma skill é baixada e nenhum modelo de linguagem é chamado. O plano de conversão é o produto.

Consulte [`docs/PORTABILIDADE.md`](docs/PORTABILIDADE.md) e a atribuição MIT em [`docs/licenses/alirezarezvani-claude-skills.txt`](docs/licenses/alirezarezvani-claude-skills.txt).

## Continuidade de plano

A página **Continuidade** (`/continuidade`) retoma o [`OthmanAdi/planning-with-files`](https://github.com/OthmanAdi/planning-with-files) — **MIT**, 27 mil estrelas — que já era a base da 0.6.0. Agora o eixo é o outro lado do padrão: o plano precisa continuar valendo quando a sessão é limpa, quando o contexto é compactado e quando o agente insiste em parar no meio.

`server/continuidade.py` lê o `### Phase` do `task_plan.md` nos **dois formatos de status** (`**Status:**` e `[status]`) e conta por formato como o portão conta; aplica os **cinco guardas** do bloqueio de parada — opt-in `gate`, fase em andamento, parada não forçada, teto de bloqueios e avanço do livro — devolvendo `block` ou `allow` com o motivo; cruza plano, progresso e achados para apontar **divergência de status entre as duas fontes** e responder as cinco perguntas de reboot; monta o **bloco reinjetado por turno** com as seções prioritárias, orçamento de 65.536 bytes, corte em linha inteira e hora zerada para o prefixo ficar estável; valida o **livro append-only** em JSONL com seis eventos, tick crescente, resumo de 200 caracteres e lacuna; e diagnostica o **diretório de planos** com arquivo faltando, plano sem livro ou atestação, título duplicado e ambiguidade de plano ativo.

O plano é o texto que você cola: nada é escrito, nenhum hook é instalado, nenhum agente é bloqueado e nenhum modelo é chamado.

Consulte [`docs/CONTINUIDADE.md`](docs/CONTINUIDADE.md) e a atribuição MIT em [`docs/licenses/othmanadi-planning-with-files.txt`](docs/licenses/othmanadi-planning-with-files.txt).

## Acesso ao sistema

Esta é a primeira camada que toca a máquina em vez de ler texto colado. Depois de 21 camadas declarando `executed: false`, o eixo mudou: aqui existe leitura real do host, download para quarentena e execução de instalador — cada um atrás de uma trava própria.

`server/sistema.py` mede **espaço em disco** por unidade, ignorando pseudo-filesystems e bind mounts repetidos, com alerta em 15% e 5% livres; enumera **pastas** com nome, tipo, tamanho e data sem ler um byte de conteúdo, reconhecendo cofre, chave e token pelo nome; lista **drivers** — módulos do kernel no Linux, drivers PnP assinados no Windows — apontando item sem versão e driver sem assinatura; lista **adaptadores Bluetooth e dispositivos pareados** e diagnostica o caso do fone: sem rádio, rádio desligado ou nada pareado; **busca na web** e lê o texto de uma página; **baixa** para `storage/host-downloads` com teto de 256 MB e SHA-256; monta o **plano de instalação** com o comando exato, o risco, o SHA-256 e a assinatura; planeja a **desinstalação** por gerenciador; e **executa** o plano confirmado.

A 0.31.0 fechou o ciclo com **verificação de assinatura e integridade** — SHA-256 contra o hash publicado, Authenticode no Windows, `rpm -K`, `dpkg-sig` e `gpg` para assinatura destacada, declarando quando não é verificável — e o **desinstalador simétrico**, que usa o mesmo token de uso único e revalida o hash do arquivo entre o plano e a execução.

Três travas separam leitura de efeito: a **rede desligada** até `JARVIS_HOST_REDE=1`, que basta para **buscar e ler** página (desde a 0.49.0, sem token); o **token de host** em `storage/host-token.txt`, gerado no primeiro uso e impresso no terminal, exigido só de quem **grava** — baixar, importar, instalar e executar; e a **instalação desligada** até `JARVIS_HOST_INSTALAR=1`. Não existe shell livre — o executor só roda uma allowlist fechada (msi, msix, deb, rpm, exe, AppImage, pip, npm) com `shell=False` e nenhum texto do usuário na linha de comando.

O aviso que a interface repete: os dados são da máquina que executa a API. Num contêiner, é o contêiner — e a skill `sistema.ambiente` detecta isso e diz na cara.

Consulte [`docs/SISTEMA.md`](docs/SISTEMA.md).

## Perfil de pessoa com lastro

A 0.34.0 porta a parte determinística de **`titanwings/distilly`** (MIT): quatro famílias de personagem — colega, relação, figura pública e dono do agente —, oito hospedeiros compatíveis, gate de treze checagens de qualidade e a regra que organiza tudo: **cada linha do perfil precisa de linha de origem**.

`server/distilar.py` expõe oito skills de leitura — mais `distilar.persona`, a única que escreve: `distilar.perfil` mede o corpus por dimensão e mostra o que está coberto, parcial ou ausente; `distilar.dimensoes` publica o que cada família exige; `distilar.esboco` monta o `SKILL.md` e o `manifest.json` propostos, com slug portátil e seção marcada como sem evidência; `distilar.qualidade` aplica o gate na régua padrão ou na estrita do original; `distilar.lastro` confronta cada afirmação com o material e recusa citação acima de 240 caracteres; `distilar.correcao` classifica o "ele não faria isso" em fato, voz, julgamento ou limite e exige evidência nova; `distilar.hospedeiros` mostra o caminho nativo em oito agentes; `distilar.regras` publica o contrato.

**O gerador de persona é a nona skill, opcional e explícita.** `distilar.persona` pede o rascunho ao provedor do `.env`, monta o front matter no código e submete o texto ao lastro e ao gate antes de devolver — com até 24 mil caracteres de material e 3 mil tokens de resposta. Sem `JARVIS_AI_API_KEY` ela recusa e as outras oito seguem funcionando. As oito primeiras não chamam modelo, não baixam fonte e não instalam perfil.

Consulte [`docs/DISTILAR.md`](docs/DISTILAR.md).

## Root, sem virar root

A 0.33.0 entrega a elevação controlada: `server/elevacao.py`. A API continua rodando com o seu usuário; quem ganha root é o comando de uma **tabela fechada de seis ações**, por um instante, com token de uso único e linha de auditoria. Nada de processo root e nada de comando livre.

| Skill | Efeito | Travas |
|---|---|---|
| `sistema.privilegio` | leitura | token de host |
| `sistema.elevar` | leitura — monta o argv e o SHA-256 | token de host |
| `sistema.elevar_executar` | **root** | token + `JARVIS_HOST_ROOT=1` + `confirmed` + token de 8 hex |

A tabela é `dpkg -i`, `dpkg -r`, `rpm -Uvh`, `rpm -e`, `systemctl restart` e `systemctl stop`. As quatro primeiras só aceitam arquivo da quarentena ou nome de pacote validado por regex; as duas de serviço só aceitam unidade declarada em `JARVIS_HOST_SERVICOS`. O argv sai com `sudo -n`, `--` antes do alvo e `shell=False`.

Quem autoriza root de verdade é o `/etc/sudoers`: sem uma linha `NOPASSWD` restrita aos três binários, a chamada falha e nada acontece. E o limite precisa ficar dito — `NOPASSWD` em `dpkg` equivale a root, porque um pacote instala o que quiser. O ganho não é impedir processo comprometido de virar root; é impedir bug acidental e texto livre de virar root, além de deixar um registro por execução.

A 0.35.1 corrige o texto que ficou para trás: `sistema.instalar`, `sistema.desinstalar` e `sistema.regras` ainda diziam que elevação \"não é feita\", como se a 0.33.0 não existisse. Agora dizem o que é verdade — **esta camada não eleva** e apontam para `sistema.elevar`, com token próprio, tabela fechada de seis ações e auditoria. Nenhuma linha do caminho de execução mudou; mudou o que a resposta conta.

Consulte [`docs/ROOT.md`](docs/ROOT.md).

## Evolução do próprio código

A 0.32.0 abre o único caminho pelo qual o JARVIS pode mudar o próprio código — e o desenha para que a prova venha antes da escrita. `server/evolucao.py` expõe oito skills: `evoluir.mapa` inventaria arquivos, linhas, módulos e quem está sem teste; `evoluir.proposta` prova hunk por hunk se o diff aplica no arquivo como ele está; `evoluir.risco` pontua de 0 a 100 por treze padrões de perigo — shell, `eval`/`exec`, TLS desligado, segredo embutido, chave privada — mais peso por arquivo central; `evoluir.guardas` confere as dez leis do projeto; `evoluir.ensaiar` aplica o patch numa **cópia isolada** em `storage/evolucao/ensaios/<id>/` e roda o pytest de verdade; `evoluir.promover` só escreve depois de ensaio aprovado, hash idêntico ao ensaiado, `git status` limpo naquele arquivo e backup em `storage/evolucao/backups/<id>/`; `evoluir.reverter` devolve os arquivos do backup; `evoluir.regras` publica o contrato.

A camada **não gera o patch** — o diff é entrada sua ou de um modelo externo —, **não cria branch** e **não commita**: a promoção deixa a árvore modificada para revisão, com `reinicio_pendente: true`. Além do token de host, ensaiar, promover e reverter exigem `JARVIS_HOST_EVOLUIR=1`; sem a variável, a camada inteira é somente leitura.

O aviso que precisa ficar dito: a suíte pega regressão, não má intenção. Um patch pode passar em 1.830 testes e ainda abrir uma porta. O ensaio já executa o código novo — `conftest.py` malicioso roda antes de qualquer aprovação. E o backup mora no mesmo disco, então ele protege contra patch ruim, não contra disco apagado.

Consulte [`docs/EVOLUCAO.md`](docs/EVOLUCAO.md).

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
| `editorial.tipo` | Escolhe entre 45 tipos e 9 padrões, com orçamento e preset |
| `editorial.marca` | Resolve 11 papéis de cor e mede o contraste WCAG |
| `editorial.lint` | Aplica os 12 anti-padrões ao HTML ou SVG |
| `editorial.conector` | Mede as 6 regras de conector na geometria |
| `editorial.importar` | Lê draw.io/Mermaid/Excalidraw e escreve o recibo |
| `editorial.entrega` | Confere SVG acessível, canvas, impressão e rampa |
| `editorial.catalogo` | Publica tipos, padrões, papéis, presets e regras |
| `carreira.triagem` | Nota 1–5 com bandas, evidência, tetos e legitimidade |
| `carreira.ats` | Lints de payload e placar ATS de pesos fixos |
| `carreira.bullets` | Audita abertura, métrica, voz e clichê de cada bullet |
| `carreira.carta` | Rascunha carta só com conquista e número de origem |
| `carreira.entrevista` | Converte requisitos em perguntas e cruza histórias STAR |
| `carreira.funil` | Calcula conversão, coortes e candidaturas paradas |
| `carreira.regras` | Publica bandas, dimensões, estados e pesos |
| `navegador.snapshot` | Indexa a árvore: papéis, refs, locators e frames |
| `navegador.alvo` | Resolve @ref, texto, papel, CSS e href em comando |
| `navegador.roteiro` | Monta três rodadas com orçamento e handoff |
| `navegador.checagem` | Aplica 15 padrões e classifica dez estados do alvo |
| `navegador.recibos` | Separa despacho de verificação e cobra o fechamento |
| `navegador.limites` | Classifica ação em bloqueada, confirmar ou liberada |
| `navegador.regras` | Publica papéis, alvos, ações, estados e limites |
| `escritorio.comando` | Monta o comando `gws` com params, corpo e ensaio |
| `escritorio.receita` | Planeja uma receita com verificação e rollback |
| `escritorio.paginas` | Lê páginas, conta únicos e monta o `pageToken` |
| `escritorio.lote` | Divide itens em chamadas e valida cada item |
| `escritorio.escopos` | Compara operações com escopos concedidos |
| `escritorio.erros` | Triagem de código, status e `reason` |
| `escritorio.regras` | Publica serviços, flags, escopos e receitas |
| `system.status` | Versão e horário do ambiente, sem variáveis ou credenciais |
| `legal.search` | Busca por tema nos textos do recorte jurídico |
| `legal.article` | Consulta exata de artigo, incluindo milhares e sufixos |
| `legal.sources` | Catálogo de documentos, origem e fontes oficiais |

São **290 skills Python**. A página **Skills** gera os formulários a partir dos esquemas Pydantic publicados pela API. As skills jurídicas abrem Legislação; leitura e criação de documentos abrem Documentos; workflows de engenharia abrem Engenharia; planejamento persistente abre Planos; análise reversa abre Reversa; engenharia enxuta abre Enxuto; governo de agentes abre Agentes; estúdio de design abre Estúdio; direção de arte abre Direção; diagramas abrem Diagramas; carreira abre Carreira; navegador abre Navegador; escritório abre Escritório; estação abre Estação; marketing abre Marketing; ciência abre Ciência; confiança abre Confiança; contexto abre Contexto; seleção abre Seleção; revisão abre Revisão; memória abre Memória IA; portabilidade abre Portabilidade; continuidade abre Continuidade; sistema abre Sistema; evolução abre Evolução; agenda abre Agenda; backup abre Backup; leitura do Git abre Git; perfil de pessoa abre Pessoa; mesclagem e organização usam o executor genérico com simulação. Os arquivos ficam em `storage/user-files`; a área reversa usa `storage/user-files/reverse`, separada dos documentos. O confinamento não permite `..`, caminhos absolutos, arquivos ocultos ou fuga por symlink.

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
- página Curadoria com entrada, catálogo, README, ticker, higiene e regras;
- página Marketing com orçamento, teste, campanha, e-mail, SEO, anúncio e regras;
- página Diagramas em duas camadas: desenho por IR (tipo, IR validado, layout medido, desenho portátil, legenda, entrega) e camada editorial (tipo, marca, lint, conectores, importação e entrega);
- página Carreira com triagem 1–5, ATS, bullets, carta, entrevista, funil e catálogo;
- página Navegador com snapshot, alvo, roteiro, checagem, recibos, limites e catálogo;
- página Escritório com comando, receita, páginas, lote, escopos, erros e catálogo;
- página Ciência com amostra, estatística, desenho, reprodutibilidade, validação, manuscrito e regras;
- página Confiança com ficha, risco, permissão, instalação, índice, duplicata e regras;
- página Contexto com orçamento, tokens, corte, higiene, resumo, uso e regras;
- página Seleção com briefing, busca, stack, plano, cobertura, catálogo e regras;
- página Revisão com escopo, lotes, achados, posição, duplicatas, cobertura e regras;
- página Submissão com ficha, estrutura, risco, licença, links, portão e regras;
- página Memória IA com roteamento, entidades, grafo, sessão, recall, esquecimento e regras;
- catálogo unificado de skills locais e Python;
- `dryRun`, confirmação e resultado detalhado das skills;
- paleta global com `Ctrl/Cmd + K`;
- preferências de cor, voz, notificações e redução de movimento;
- layout desktop e móvel.

## Celular velho como PC

A pergunta "dá para transformar um celular velho em um PC com Linux?" tem
resposta técnica e resposta prática, e elas não coincidem. Em
[`docs/CELULAR-LINUX.md`](docs/CELULAR-LINUX.md) está o estudo de caso do **Galaxy
J7 Prime** (`on7xelte`): o aparelho **é** um bom candidato — tem port no Nura
(ex-postmarketOS) em testing, LineageOS 18.1 e /e/OS —, e **a tela morta não é o
fim**: o `scrcpy` espelha e controla o aparelho numa janela do Windows, porque a
GPU continua desenhando mesmo com o painel quebrado. A condição que decide tudo é
se a *Depuração USB* já esteve ligada; se nunca esteve, há o `scrcpy --otg`
(teclado e mouse sem ADB) e, no limite, uma tela de teste de bancada. O documento
traz o diagnóstico de placa antes de comprar a peça (R$ 70–160 o módulo), o
caminho sem risco (Termux + proot-distro, com `apt` e SSH) e o caminho nativo
(Nura) com seus limites e riscos.

**Ligar em um clique:** duplo clique em **`ligar-celular.bat`**. Ele ajusta
`JARVIS_HOST_REDE=1`, `JARVIS_HOST_CELULAR=1` e `JARVIS_HOST_CONFIAR_LOCAL=1` no
`.env` — o último é o **modo dono** registrado no banner (numa outra máquina o
token continua sendo pedido, e desde a 0.61.9 ele já não é pedido nem sem essa
linha). Troca a linha se ela já
existir, sem duplicar chave, em UTF-8 sem BOM e com CRLF. Se o `.env` não
existir, cria a partir do `.env.example`; se achar um `.env.txt` perdido (o Bloco
de Notas adora salvar assim), renomeia. Depois é só reiniciar a API e conferir
`rede=ligada ... celular=ligado` na primeira linha do banner.

**Quando o celular não aparece:** duplo clique em **`vigiar-usb.bat`**. Ele deixa uma janela aberta checando a USB do Windows a cada 2 segundos e apita no instante em que algum dispositivo entra ou sai, dizendo se é a Samsung (`VID_04E8`, com o **modelo**, ex.: `SM-A346B`), se é o `VID_0000` (a porta viu algo e não conseguiu identificar: cabo de carga ou conector) ou se é só o que já estava lá. É o teste conectar/desconectar sem precisar rodar `status do celular` a cada cabo. Só leitura, sem admin, e fecha no X. Se o conector tem mau contato, o aparelho pode aparecer por menos de um segundo: **`vigiar-usb-atento.bat`** assina o evento de PnP do Windows e é avisado no instante em que algo entra ou sai — sem intervalo para passar batido (na consulta por lista, esta máquina leva ~5 s por volta). Ele mostra só o que é aparelho (VID da Samsung, modelo ou o “desconhecido”): leitor de cartão, hub e controladora viram uma linha discreta e ficam completos no log, porque cinco linhas de leitor de cartão escondem justamente a do celular, e toda entrada e saída fica gravada em `storage\celular\vigia-*.log` — dá para colar no chat depois. E `celular.eventos` lê o log do Windows (canal System, sem admin) para dizer o que passou pela USB nos últimos minutos, mesmo o que a janela não alcançou.

Na **0.60.0** isso virou cinco skills: `celular.status` (mede o aparelho: `adb devices`, autorização e, sem aparelho à vista, a USB do Windows — além de onde estão o adb e o scrcpy), `celular.plano` (o caminho exato para o estado medido, inclusive
quando a depuração nunca foi ligada), `celular.preparar` (baixa as duas
ferramentas com SHA-256), `celular.espelhar` (a tela do celular numa janela do
Windows) e `celular.puxar` (fotos e documentos por `adb pull`). Tudo atrás de
`JARVIS_HOST_CELULAR=1`, com confirmação. O que ele **não** faz, e nenhum programa
faz: tocar em “Permitir depuração USB?” — esse consentimento é do Android, na
tela.

## Atualizar

**Duplo clique em `atualizar.bat`.** Ele descobre sozinho como a pasta foi
instalada e faz a coisa certa:

- **se houver `.git`** — confere o ramo, **para se houver arquivo seu alterado**
  (não joga nada por cima), faz `--ff-only`, mostra o que entrou e avisa quando as
  dependências mudaram;
- **se não houver `.git`** (instalação pelo zip) — baixa o zip oficial e copia por
  cima, **preservando `.env`, `storage\`, `.venv\` e `node_modules\`**.

Durante a atualização aparecem **porcentagem, MB, velocidade e tempo que falta**
no download, e `X de Y arquivos` na cópia — mais o título da janela acompanhando.
(Veio na 0.61.9; antes a tela ficava parada num cursor piscando.)

Feche a janela da API **antes** de rodar: arquivo aberto pela API pode não ser
copiado. Nos dois casos ele avisa se existe uma pasta `dist\` de build antigo (a
API prefere `dist\` a `web-dist\`, então uma tela velha continuaria aparecendo) e
lembra de reiniciar a API — e, se ela ainda pedir token, de rodar
`ligar-celular.bat` uma vez para ligar o modo dono.

**Primeira vez, se você ainda não tem o `atualizar.bat`:** baixe
<https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre>,
descompacte **por cima** de `D:\JARVIS` e **preserve** `.env`, `storage\` e
`.venv\`. A interface já vem compilada em `web-dist\`, então não precisa de Node.
Depois disso, o `atualizar.bat` já está na pasta.

**Pelo Git, se preferir na mão:**

```bat
cd /d D:\JARVIS
git fetch origin
git checkout arena/f26cfa7a-victor-alexandre
git pull --ff-only
```

Depois de qualquer atualização, confira em `http://127.0.0.1:8000/api/health`:
`{"version": "0.61.9", "skills": 290}`.

## Verificações

```bash
npm test          # Vitest + Pytest
npm run build     # TypeScript + bundle de produção
npm audit         # dependências JavaScript
```

Os testes cobrem o parser em português, calculadora, catálogo da API, execução real das skills, corpus jurídico, documentos, upload/download, produtividade, normalização numérica, grafos de dependências, matriz de testes, revisão estática sem exposição de segredos, STRIDE, Web Vitals, ADR, gate de release, recuperação persistente, isolamento de planos, hash otimista, evidências e gate determinístico, parsers ELF/PE/Mach-O/ZIP/ASAR/WASM com artefatos sintéticos, entropia, strings, análise JavaScript, bloqueio de symlink na árvore, confirmação de upload reverso, `path traversal`, escada com evidência por degrau, proteção removida e risco novo em diffs, marcadores `shortcut:` sem gatilho, auditoria com limite de arquivos e bloqueio de symlink, raiz humana e ciclos de reporte, quadro com dono/evidência/bloqueios, orçamento com hard stop e projeção, impressão digital e supressão do watchdog, mandato não ampliável, linha de base e exceções de permissões, contrato de design com 56 slots e temas, manifesto inseguro, prosa rasa, contraste AA/AAA, cinco dimensões com evidência e inflação, 26 regras anti-clichê no HTML, determinismo do sorteio de direções, ficha por seção, prova sem fonte, orçamento de título, deck de copy, 29 regras lexicais com isenções e modo app, 25 tells em três ondas, pesos e tetos do júri, notas e tetos da triagem de carreira, confiança da evidência, legitimidade do anúncio, lints e placar ATS, auditoria de bullets, gate da carta, plano de entrevista, leitura de funil, parser de snapshot com nove achados, resolução de alvo ambíguo, roteiro de três rodadas, quinze padrões de checagem, recibos de fechamento, limites de navegação, montagem de comando `gws`, planejamento de receitas, leitura de páginas, lotes, escopos e triagem de erro, plano de tarefa durável, matriz de permissões, recuperação de execução, agenda de automações, classificação de efeito, memória e skills do agente, execução real com gate de permissão, fila de aprovação, recibos duráveis, recuperação de chamada interrompida e automação de cron, e provedor de IA com respostas simuladas, catálogo dos 45 tipos editoriais, seleção por padrão semântico, contraste com proposta de ajuste, os 12 anti-padrões, as 6 regras de conector, os três parsers de importação, a escada de degradação, o recibo de fidelidade, o contrato de entrega, elegibilidade pelos dois caminhos, validação de entrada com linha pronta, agrupamento por configuração, README derivado com âncoras e escape, proteções e movimentos do ticker, as dez checagens de higiene, o front matter por tipo de artefato, o cabeçalho `>>> caminho` do bundle, as nove regras de risco, o parser SPDX com `AND`/`OR`/`WITH`, a âncora e a caixa do link, o portão de três decisões e o catálogo da submissão, as 29 regras de roteamento de via com negação e limiar, os sete tipos de entidade, o grafo com ciclo e componente, a pontuação de lição da sessão, o recall com BM25 e decaimento, o raio de alcance do esquecimento e o catálogo da memória, o inventário por `>>> caminho`, a auditoria de front matter e slug, o plano de conversão para os treze alvos, a deriva entre fonte e espelho, a colisão pelo destino, o `plugin.json` de oito chaves e a matriz skill × alvo, os dois formatos de status de fase, os cinco guardas do portão, a divergência entre plano e progresso, o bloco injetado com orçamento e o livro append-only em JSONL, a medição de disco sem pseudo-filesystem, o inventário sem conteúdo, a classificação de pasta protegida, os drivers por plataforma, o diagnóstico de Bluetooth sem rádio, o bloqueio de URL privada, a quarentena com hash, a allowlist de instaladores, o SHA-256 contra o hash publicado, a assinatura Authenticode/rpm/gpg, a desinstalação por gerenciador, a revalidação do arquivo entre plano e execução, o mapa do projeto, a prova de hunk, o escore de risco, as dez guardas, o ensaio em cópia isolada, a promoção com hash e backup, a reversão, a elevação por tabela fechada com sudo, o mapa de cobertura por dimensão, o gate de qualidade do perfil e o lastro de cada afirmação. O estado desta versão tem **41 testes web e 1.830 testes de API**. Nenhum teste exige uma chave real nem faz cobrança em provedores.

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
├── pages/CareerPage.tsx     # triagem, ATS, bullets, carta, entrevista, funil e catálogo
├── pages/NavegadorPage.tsx  # snapshot, alvo, roteiro, checagem, recibos e limites
├── pages/EscritorioPage.tsx # comando gws, receitas, páginas, lotes, escopos e erros
├── pages/EstacaoPage.tsx    # tarefa, permissões, execução, agenda, limites e memória
├── pages/DiagramPage.tsx    # IR, layout, desenho, legenda e camada editorial
├── pages/CuradoriaPage.tsx  # entrada, catálogo, README, ticker, higiene e regras
├── pages/MarketingPage.tsx  # funil, teste, campanha, e-mail, SEO, anúncio e regras
├── pages/CienciaPage.tsx    # amostra, estatística, desenho, repro, validação e manuscrito
├── pages/ConfiancaPage.tsx  # ficha, risco, permissão, instalação, índice, duplicata e regras
├── pages/ContextoPage.tsx   # orçamento, tokens, corte, higiene, resumo, uso e regras
├── pages/SelecaoPage.tsx    # briefing, busca, stack, plano, cobertura, catálogo e regras
├── pages/RevisaoPage.tsx    # escopo, lotes, achados, posição, duplicatas, cobertura e regras
├── pages/SubmissaoPage.tsx  # ficha, estrutura, risco, licença, links, portão e regras
├── pages/MemoriaPage.tsx    # roteamento, entidades, grafo, sessão, recall e esquecimento
├── pages/PortabilidadePage.tsx # auditar, converter, deriva, colisão, lote, matriz e regras
├── pages/ContinuidadePage.tsx # fases, portão, retomada, injeção, livro, médico e regras
├── pages/SistemaPage.tsx    # ambiente, disco, pastas, drivers, bluetooth, rede, download e instalador
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
├── curadoria.py            # schema, elegibilidade, catálogo, README, ticker e higiene
├── marketing.py            # funil, amostra, UTM, e-mail, SEO, anúncio e regras
├── ciencia.py              # poder, relato, desenho, reprodutibilidade, método e manuscrito
├── confianca.py             # ficha, risco, permissão, instalação, índice e duplicata
├── contexto.py              # janela, tokens, corte por turno, higiene, resumo e uso
├── selecao.py               # briefing, BM25, stack, plano, cobertura e catálogo
├── revisao.py               # diff em hunks, escopo, lotes, âncora, duplicata e cobertura
├── submissao.py             # front matter, estrutura, risco, SPDX, link e portão
├── memoria.py               # roteamento, entidades, grafo, sessão, recall e esquecimento
├── portabilidade.py         # alvos, conversão, deriva, colisão, lote, matriz e catálogo
├── continuidade.py          # fases, portão, retomada, injeção, livro, médico e catálogo
├── sistema.py               # host: disco, pastas, drivers, bluetooth, rede e instalador
├── editorial.py             # 45 tipos, padrões, contraste, conectores e recibo
├── career.py                # triagem com evidência, ATS, bullets, carta, entrevista e funil
├── navegador.py             # snapshot, alvo, roteiro, checagem, recibos e limites
├── escritorio.py            # comando gws, receitas, páginas, lotes, escopos e erros
├── estacao.py               # tarefa, permissões, recibos, agenda, limites e memória
├── estacao_runtime.py       # execução real, gate, aprovação, recibos e cron
├── review.py                # achados, contagens, veredito e Markdown compartilhados
├── legal_corpus.py          # parser, índice e busca lexical
├── legal_data/              # oito normas, índice e atribuição
├── skill_registry.py        # allowlist, Pydantic e 290 skills
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
- Submissão é lexical: o front matter é lido por um parser de subconjunto, o risco não pega frase reescrita e a licença é conferida por identificador SPDX, não pelo texto do arquivo `LICENSE`. Nada é publicado — o rótulo do GitHub continua com a revisão humana.
- Memória de agente é lexical: o roteador não entende paráfrase sem palavra-chave, a extração não faz correferência, o recall mede termo em comum e não verdade, e o esquecimento devolve plano em vez de apagar. Nenhum modelo, embedding ou banco de grafo é usado.
- Acesso ao sistema é a única camada com efeito real: `sistema.baixar` grava e `sistema.executar` roda. Ambas exigem token de host, `confirmed` e, no caso da execução, `JARVIS_HOST_INSTALAR=1`. Rede desligada por padrão, endereço privado e laço local bloqueados inclusive via DNS, nenhuma assinatura digital verificada, nenhum privilégio elevado e nenhum shell livre.
- Continuidade de plano é leitura: a camada sabe se o critério está marcado, não se foi cumprido; a decisão do portão é texto, não bloqueio de sessão; o bloco injetado é corte e contagem, não resumo por modelo; e nenhum hook é instalado.
- Portabilidade é declarada, não testada: os treze formatos vêm do que cada ferramenta publica, a conversão devolve plano em vez de escrever arquivo, a deriva compara hash ou conteúdo colado e o manifesto não é submetido ao marketplace. Nenhum `convert.sh`, `install.sh` ou skill do catálogo upstream é executado.
- Planos são limitados a 100 KB por arquivo; o hash bloqueia escritores obsoletos, mas o lock local não é coordenação distribuída entre servidores.
- Análise reversa é estática e baseada em parsers próprios: não descompila, não executa, não extrai contêineres e não cobre formatos sem parser dedicado. Evidência não substitui laudo pericial ou atestado de malware.
- Engenharia enxuta é estática: a escada avalia só o que foi declarado, a revisão e a auditoria produzem candidatos que exigem confirmação no código real. Execução, carga, testes e chamadores fora da árvore não são verificados; o histórico do Git não é lido.
- Estúdio de design é estático: não compila tokens, não lê o repositório do pacote, não renderiza o HTML nem publica artefato. O esquema de 56 slots é embutido, o parser de CSS cobre blocos simples e o linter é lexical, sujeito a falso positivo.
- Diagramas são gerados a partir do que você declara: sem navegador, o piso de texto e o overflow são estimativas, e Mermaid/DOT são exportados como texto, não renderizados aqui.
- A camada editorial também é estática: o lint e a entrega leem texto, as seis regras de conector valem sobre a geometria declarada, o draw.io comprimido pede o XML do modelo e a escada de degradação é heurística — qual caminho é principal continua sendo julgamento humano.
- Carreira é triagem declarada: não lê portais, LinkedIn, e-mail ou calendário, não envia candidatura e não altera o currículo. A nota vem só do texto colado; legitimidade é sinal, não acusação, e percentual do funil com menos de oito linhas é contagem, não tendência.
- Navegador é leitura declarada: não abre aba, não clica, não preenche, não paga e não baixa. O snapshot é uma foto, XPath/CSS/shadow DOM não são avaliados, o código gerado não é executado e a classificação de limites lê palavras, não intenção.
- Escritório é planejamento declarado: não instala o CLI, não autentica, não lê credencial e não chama o Google. A descoberta não é consultada ao vivo, os parâmetros obrigatórios e os escopos vêm de tabelas curadas, e os tetos de lote são conservadores.
- Direção de arte é estática e declarada: a ficha não é desenhada, o sorteio não vê imagens, a quebra de linha do título é estimada por caracteres e as notas do júri vêm de quem revisa. Toda varredura é lexical e pode ter falso positivo.
- Governo de agentes é declarativo: não executa agentes, não lê runtime, banco, identidade ou fatura e não altera permissões. Orçamento não converte moeda nem incorpora retries; a projeção é linear. A impressão digital cobre a parada e as instruções, não arquivos ou anexos, e a varredura de instruções é lexical.
- Rotinas agendadas dependem do aplicativo aberto; não há worker 24 horas.
- Reconhecimento de voz depende do navegador.
- A migração das rotinas antigas do Lino está fora do escopo atual.
- Nenhuma publicação em rede social ou renovação de sessão foi ativada.

A ampliação do corpus deve ser feita por sincronização controlada, revisão do diff e novos testes.
