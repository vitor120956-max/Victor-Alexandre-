# Ações com efeito real (0.92.0)

Até a 0.91.46, doze itens apareciam em [`NAO-FAZ.md`](NAO-FAZ.md) §2 como “não
faz **por decisão**”: o módulo lia, media ou planejava, e parava ali. O dono leu a
lista e respondeu:

> adicione essas coisas arrume oq tiver q ser arrumado

Esta página é o contrato do que passou a existir, de como cada ação é travada e
do que continua de fora — porque “agora faz” sem limite escrito vira a próxima
frase mentirosa do projeto.

## A regra que vale para todas

1. **Trava de ambiente.** Sem `JARVIS_ACOES=1` nada tem efeito. A resposta diz o
   nome exato da variável e como ligar.
2. **Confirmação em dois tempos.** Sem `confirmed=true` (rota) ou
   `confirmar: true` (skill), a ação devolve o **plano** — o que seria enviado,
   aberto, convertido ou gravado — e não toca em nada.
3. **Nada de shell livre.** Cada ferramenta externa recebe uma lista de
   argumentos montada no código, com caminhos resolvidos dentro da área do
   JARVIS.
4. **Nenhuma credencial volta.** Senha de SMTP e token nunca aparecem no JSON de
   resposta nem em mensagem de erro. O erro diz *qual* variável falta, não o
   valor.
5. **Falta de ferramenta é resposta, não exceção.** Sem `pandoc`, `ffmpeg`,
   `jadx` ou Graphviz, a resposta diz o que instalar — e a ação não finge ter
   feito.

O estado completo, medido na máquina, sai em `GET /api/acoes/estado` (ou na
skill `acoes.estado`): trava, SMTP, token do Google, token do GitHub,
embeddings e cada ferramenta externa presente. É o primeiro lugar a olhar
quando uma ação responde “falta X”.

## As doze

| # | antes | agora | como | continua fora |
|---|---|---|---|---|
| 1 | Escritório não chama o Google | `google.email`, `google.listar`, `google.evento`, `google.planilha` | REST do Google com `JARVIS_GOOGLE_TOKEN` (OAuth); host fechado em `GOOGLE_HOSTS` | instalar o `gws`, autenticar por você, ler credencial de outra pessoa |
| 2 | Correio não envia e-mail | `email.enviar` | `smtplib` + TLS, servidor e remetente do `.env`, anexos da área do JARVIS (25 MB cada) | ler a caixa de entrada, apagar, organizar pasta |
| 3 | Navegador não abre aba | `navegador.abrir`, `POST /api/acoes/abrir` | `webbrowser`, só `http`/`https`, sem usuário e senha na URL | clicar, preencher, pagar, baixar arquivo, resolver captcha |
| 4 | Carreira não envia candidatura | `carreira.candidatar` | monta a carta com `career.draft_letter`, **só envia se a checagem disser `pronto`**, e manda por SMTP com o CV anexo | preencher formulário web/ATS, criar conta no site da vaga |
| 5 | Portabilidade não converte arquivo | `arquivo.converter` | tabela fechada (`md→pdf/docx/html`, `docx→pdf/md`, `html→pdf`, `png↔jpg`, `wav→mp3`, `mp4→mp3`, `mov→mp4`) com pandoc, LibreOffice, ImageMagick e ffmpeg | formato fora da tabela, lote em pasta, OCR dentro da conversão |
| 6 | Estúdio não compila tokens nem renderiza | `estudio.tokens`, `estudio.previa` | compila a tabela no contrato fechado de 56 slots e grava `tokens.css`; monta o HTML de arquivo único com os seus tokens | rasterizar (PNG), capturar tela, publicar |
| 7 | Diagramas não desenham Mermaid | `diagrama.mermaid`, `diagrama.dot` | renderizador próprio de `flowchart`/`graph` (sem Puppeteer) e Graphviz para DOT | sequência, classe, gantt, estado; tema do `mmdc` |
| 8 | Agência não executa agente | `agencia.executar` | `maestro.planejar` + `maestro.executar` com teto de passos; passo com efeito exige `autorizar` e a trava | alterar permissão de agente, rodar sem plano declarado |
| 9 | Memória é só lexical | `memoria.embedding`, `memoria.similaridade` | endpoint de embeddings do provedor quando há chave; sem chave, vetor local de 256 dimensões **declarado como não-modelo** | grafo, paráfrase com recall, reescrever a memória sozinho |
| 10 | Reversa não descompila | `reverse.descompilar` | `jadx` (Java) ou `apktool` (recursos/smali), timeout 600 s, saída dentro da área reversa | executar o artefato, extrair contêiner, recompilar ou assinar |
| 11 | Enxuto não roda teste | `lean.testar` | `pytest`, `pytest-full` ou `npm test` numa pasta dentro da área do JARVIS, com tempo limite e saída cortada | alterar código, corrigir o teste, instalar dependência |
| 12 | Submissão não publica | `submissao.publicar` | API do GitHub (`JARVIS_GITHUB_TOKEN`): blob → tree → commit → ref → PR, ou PATCH quando a branch já existe | revisão humana, merge, deploy, binário (vai pelo `git`) |

Cada uma também existe como skill (`/api/skills/<id>/execute`), com
`sideEffects`, `dryRunSupported` e `requiresConfirmation` declarados — a mesma
trava, duas portas.

## Onde configurar

Tudo no `.env`, ao lado das chaves que já existiam:

```env
JARVIS_ACOES=1

# e-mail (Gmail: senha de app, não a do login)
JARVIS_SMTP_HOST=smtp.gmail.com
JARVIS_SMTP_PORTA=587
JARVIS_SMTP_USUARIO=voce@gmail.com
JARVIS_SMTP_SENHA=xxxx xxxx xxxx xxxx
JARVIS_SMTP_REMETENTE=voce@gmail.com
JARVIS_SMTP_TLS=1

# Google (Drive, Gmail, Agenda, Sheets) — token OAuth com os escopos usados
JARVIS_GOOGLE_TOKEN=

# GitHub (fine-grained: Contents + Pull requests no repositório)
JARVIS_GITHUB_TOKEN=

# embeddings (opcional; sem isto, vetor local declarado)
JARVIS_EMBEDDINGS_MODEL=text-embedding-3-small
```

Sem `JARVIS_ACOES=1`, o teste `test_acoes.py` confirma que **nenhuma** ação toca
em nada: todas devolvem plano e a frase da trava.

## O que este recorte não resolve

- **Não há navegador automatizado.** Abrir aba é `webbrowser`; clicar e
  preencher continua fora, e a decisão da 0.91.x de não olhar a tela por pixels
  segue de pé.
- **Publicar PR não é publicar produto.** Revisão, merge e release continuam
  seus.
- **A conversão não é mágica.** O que não está na tabela fechada é recusado com
  a lista do que existe — em vez de um `ffmpeg -i` genérico que ninguém audita.
- **A carta da carreira não inventa número.** Se a checagem do
  `career.draft_letter` reprovar, a candidatura não sai; a resposta diz o motivo.
