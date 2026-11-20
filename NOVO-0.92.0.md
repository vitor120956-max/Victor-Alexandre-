# JARVIS 0.92.0 — as doze ações e o guia de conversa

Seu pedido, em 19/11:

> adicione essas coisas arrume oq tiver q ser arrumado e adicione filosofia,
> psicólogo, psicologia, como responder uma mulher por msg/presencialmente como
> se comportar dicas e ideias como comecar uma conversa como ir levando a garota
> para q ela queira ou de vontade de ela sair cmg ou q se apaixone por quem eu sou

## 1. As doze que estavam em “não faz por decisão” agora fazem

| antes | agora | o que você precisa |
|---|---|---|
| escritório não chamava o Google | Gmail, Drive, Agenda e Sheets | `JARVIS_GOOGLE_TOKEN` |
| correio não enviava e-mail | envio real por SMTP, com anexo | `JARVIS_SMTP_*` (Gmail: **senha de app**) |
| navegador não abria aba | abre no navegador padrão | nada além de `JARVIS_ACOES=1` |
| carreira não enviava candidatura | carta + CV por e-mail, **só se a carta passar na checagem** | SMTP |
| portabilidade não convertia | md→pdf/docx/html, docx→pdf/md, html→pdf, png↔jpg, wav/mp4→mp3, mov→mp4 | pandoc / LibreOffice / ImageMagick / ffmpeg |
| estúdio não compilava nem renderizava | `tokens.css` do contrato de 56 slots + prévia HTML | nada |
| diagramas não desenhavam Mermaid | SVG de `flowchart`/`graph` (renderizador próprio) e DOT | Graphviz, para DOT |
| agência não executava agente | plano do maestro rodando com teto de passos | `JARVIS_ACOES=1` |
| memória era só lexical | embedding por provedor **ou** vetor local declarado | opcional |
| Reversa não descompilava | `jadx` / `apktool` | a ferramenta instalada |
| enxuto não rodava teste | `pytest` / `npm test` de verdade | a suíte na pasta |
| submissão não publicava | PR no GitHub (blob → tree → commit → ref → PR) | `JARVIS_GITHUB_TOKEN` |

**A trava é a mesma para todas:** `JARVIS_ACOES=1` no `.env` **e** confirmação
em dois tempos. Sem confirmação, a resposta é o **plano** — o que seria enviado,
aberto ou gravado — e nada acontece. Sem a variável, a resposta diz o nome dela.

Para saber o que falta na sua máquina, abra a aba **Skills** e rode
`acoes.estado` (ou `GET /api/acoes/estado`): ele lista SMTP, tokens, embeddings e
cada ferramenta externa, com o que instalar onde.

> **Como conferir:** rode `conferir-versao.bat` (deve dizer 0.92.0). Se a aba
> nova não aparecer, **Ctrl+F5**.

## 2. O guia de conversa (`/guia`)

- **Começar** — aberturas por contexto (app, festa, academia, trabalho, rua,
  curso) e o que evitar em cada um;
- **Manter** — princípios, exemplo ruim × bom e a análise da sua mensagem;
- **Convidar** — estrutura do convite, exemplos, saída fácil, como receber um
  não;
- **Sinais** — interesse, desconforto, consentimento, o que fazer quando ela
  some;
- **Revisar** — tamanho, número de perguntas, cobrança, pressão, maiúsculas;
- **Filosofia** — estoicismo, existencialismo, virtude, pragmatismo,
  fenomenologia, Camus, taoísmo, ética do cuidado (ideia, pergunta, prática,
  limite);
- **Psicologia** — escuta ativa, comunicação não violenta, apego, rejeição,
  ansiedade social, reciprocidade, atração (com “o que a pesquisa sustenta” e o
  exagero popular ao lado);
- **Limites** — o que ele recusa escrever e por quê.

### A parte que eu não faço — e por que

Você pediu “que ela se apaixone por quem eu sou”. **Ninguém faz alguém se
apaixonar**, e quem promete isso está vendendo manipulação. O que existe aqui é
o caminho honesto: chegar bem, conversar de verdade, ser claro sobre o que quer,
receber “não” sem virar campanha, e ser alguém com quem vale a pena conversar.
As seis técnicas que aparecem em curso de sedução — neg, insistir depois do não,
chantagem emocional, personagem falso, confundir, vigiar — estão **recusadas em
código**, com o motivo escrito e teste prendendo a lista.

**Não é terapia.** Em crise, o JARVIS para e aponta o **CVV 188** (24 h,
gratuito). Violência: **180** (Central de Atendimento à Mulher) e **190**.

## 3. Defeitos achados no caminho (e teste para cada)

- `revisar()` mandava **texto vazio** ao detector de crise/violência: um rascunho
  com ameaça passava sem aviso. Corrigido; o teste manda o texto e cobra 180/190.
- O parser do Mermaid **apagava o rótulo** de um nó quando ele reaparecia solto
  (`B[Pedido] --> C` e depois `B --> D`): o desenho saía com “B” no lugar de
  “Pedido”. Corrigido; `A --> B --> C` também passou a valer duas arestas.
- `perguntas` contava cada `?` de `??` como pergunta separada. Agora conta grupos.
- `converter` reclamava do arquivo ausente antes de dizer que o **par de
  formatos** não existe — a mensagem útil vinha depois da inútil. Invertido.
- `enviar_email` estourava “falta SMTP” antes de mostrar o plano. Agora o plano
  sai com o campo `falta` dentro.

## 4. O que continua fora (e é decisão)

Clicar e preencher em página, preencher formulário/ATS, rasterizar página em
PNG, publicar o pacote de design, sequência/classe/gantt do Mermaid, grafo de
memória, executar o APK descompilado, corrigir o código para o teste passar,
merge/release do PR, instalar APK por ADB, descompilar/recompilar/assinar o jogo.
Cada linha está em [`docs/NAO-FAZ.md`](docs/NAO-FAZ.md) §2 **com teste que
impede o documento de voltar atrás**.

## 5. Números desta versão

- **352 skills** (eram 325) — 24 novas de ação/conversa + 3 de estúdio/carreira;
- **33 testes novos** (`test_acoes.py` 19, `test_conversa.py` 12) + `test_nao_faz.py` de 11 para 13;
- suíte inteira: **4 134 casos, 0 falhas, 7 pulados**; vitest **243**; `tsc` limpo;
- rotas novas: `/api/acoes/*` (4) e `/api/conversa/*` (9);
- uma aba nova no menu: **Guia de conversa**.
