# A página da chave do OpenRouter — o manual, passo a passo

Este é o manual da página, não do JARVIS: **o que existe na tela**, em que
ordem, com que nome, e o que o JARVIS faz em cada ponto. Ele foi escrito a
partir da documentação oficial do OpenRouter e dos prints do dono (15 e 16/11),
porque o dono pediu exatamente isso: *“leia o manual da página de como
configurar, onde é o nome, onde que deve clicar, passo a passo”*.

Quando este documento e o código divergirem, **o documento está errado** — é
ele que tem de ser corrigido, e é para isso que existe o `diagnostico-chave.bat`
(§7).

---

## 1. Onde é a página

    https://openrouter.ai/settings/keys

`openrouter.ai/keys` leva ao mesmo lugar. É preciso estar logado (o JARVIS
reaproveita o login que já existe no Chrome do dono; ele não pede senha).

O título da aba é parecido com **“Keys | Settings | OpenRouter”**. É por isso
que o JARVIS reconhece a página pelo título e pelos textos “API keys” /
“Create and manage your API keys”.

## 2. O botão que abre o painel

No canto da área de chaves: **“New key”** (em algumas contas aparece como
“Create Key” ou “Create New Key” — o rótulo mudou de tempo em tempo). O JARVIS
procura por qualquer um dos três.

O clique é **físico**, com o mouse, na posição medida do botão, porque a ação
de acessibilidade do Chrome mente com frequência (diz que clicou e não clica).
Antes de clicar, a janela é trazida para a frente e o foco é conferido.

## 3. O painel “Create API key”, campo por campo

O painel abre por cima da página. São **três campos obrigatórios** (todos com
asterisco) e um quarto que só vale quando há limite. Nesta ordem, de cima para
baixo:

| # | rótulo na tela | o que é | obrigatório | o que o JARVIS faz |
|---|---|---|---|---|
| 1 | **Name \*** | caixa de texto, com o exemplo `e.g. "ChatbotKey"` | sim | digita `jarvis-AAAA-MM-DD` (ou o `--nome` que você passar) |
| 2 | **Expiration \*** | lista, começa em `Select expiration` | sim | abre a lista e escolhe **`No expiration`** |
| 3 | **Key limit → Credit limit \*** | lista, começa em `Choose a credit limit` | sim | abre a lista e escolhe **`No limit`** |
| 4 | **Reset limit every** | lista, começa em `N/A` | não | **não mexe**: com “No limit” ela fica em `N/A`, que é o certo |
| 5 | **Create** | botão, no rodapé do painel | — | clica **só quando ele acende** |

As opções que a página oferece, medidas na tela do dono:

- **Expiration**: `1 day`, `7 days`, `30 days`, `90 days`, `180 days`,
  `1 year`, `No expiration`.
- **Credit limit**: valores em dólar e `No limit`.

Regra do projeto: **“nunca expira” e “sem limite”**. Chave que expira derruba o
JARVIS meses depois sem ninguém ligar uma coisa à outra; chave com limite para
de funcionar no meio do mês. Se a conta não oferecer `No limit`, o JARVIS
escolhe o maior valor da lista e **diz que escolheu** — parar ali seria não ter
chave nenhuma.

### O detalhe que custou cinco rodadas

O botão **Create fica apagado** enquanto os três campos obrigatórios não estão
preenchidos. Clicar num botão apagado não dá erro e não cria nada: a tela
simplesmente fica parada. Por isso o JARVIS:

1. confere o estado do botão antes de clicar (`desativado` na leitura);
2. se estiver apagado, **para** e diz **qual campo** faltou;
3. depois de clicar, relê o painel: se ele **continua aberto**, a chave não foi
   criada e ele diz isso, em vez de seguir como se tivesse dado certo.

## 4. Depois do Create: a chave aparece uma vez

O site mostra a chave nova **uma única vez**, com um botão **Copy** ao lado.
Ela não pode ser lida de novo depois — a lista passa a mostrar só o prefixo
mascarado (`sk-or-v1-…abc`). Isso é do OpenRouter, não é limitação do JARVIS:
**chave existente não é legível**, e por isso o caminho é sempre criar uma nova.

O JARVIS pega a chave de duas formas, nesta ordem:

1. **pelo texto da página** (`Ctrl+A`, `Ctrl+C` na janela do Chrome) e procura
   o padrão `sk-or-v1-` seguido de 64 caracteres hexadecimais (73 no total);
2. **pelo botão Copy**, se o texto da página não render.

Só vale o que **mudou** na área de transferência desde o começo do comando: o
que já estava copiado antes (outra chave, um texto qualquer) é ignorado.

## 5. O caminho inteiro, na ordem

    abrir a página
      → achar a janela do Chrome (pelo handle, não pelo nome)
      → atravessar o login, se cair em Sign In / escolha de conta
      → achar “New key” e clicar com o mouse
      → esperar o painel abrir (lendo fundo, por todas as vistas)
      → digitar o nome na caixa (não no rótulo “Name”, que é outro elemento)
      → abrir a lista de expiração e escolher “No expiration”
      → abrir a lista de limite e escolher “No limit”
      → conferir que o Create acendeu e clicar
      → conferir que o painel fechou (senão: não criou)
      → copiar a chave (texto da página ou botão Copy)
      → gravar só a linha JARVIS_AI_API_KEY no .env
      → avisar a API que já está no ar para reler o .env

Cada passo **confere o anterior**. Nenhum passo supõe que o anterior deu certo.

## 6. O que o JARVIS nunca faz

- não cria nada sem `--autorizar`;
- não clica num botão apagado;
- não digita às cegas: se não consegue ver o campo, diz que não vê;
- não escolhe conta no chute quando há mais de uma conta do Google;
- não tira print, não lê pixel, não usa OCR;
- não apaga nem reescreve as outras linhas do `.env`;
- não promete sucesso: quando não deu, diz **o que viu** (quantos elementos,
  quais os primeiros nomes, qual leitura, em que estado estava a janela).

## 7. Se falhar: o diagnóstico (sem criar nada)

Duplo clique em **`diagnostico-chave.bat`** (ou
`.venv\Scripts\python chave-no-navegador.py --diagnostico`).

Ele **não cria chave e não clica em nada**. Ele mede o que cada leitura do
Windows enxerga da janela do Chrome e escreve `chave-leitura.txt` na pasta do
JARVIS, com:

- a linha `estado:` — a janela está minimizada? com o foco? quem tem o foco?;
- uma entrada por leitura: `auto`, `uia`, `uia_raw`, `uia_content`, `msaa`;
- quantos elementos com nome cada uma trouxe;
- **quais campos do painel** cada uma enxerga (nome, expiração, limite, criar,
  copiar);
- os primeiros 40 nomes de cada leitura.

**Melhor ainda:** abra o painel na tela antes de rodar (clique em *New key*) e
rode com ele aberto. Aí o relatório responde a pergunta que importa: *qual
leitura vê o painel que está na minha frente?* — sem gastar uma chave.

### 7.1 O modo leitor de tela — a peça que faltava (0.91.25)

Medido no PC do dono em 16/11, 08:35: com o painel aberto na tela, **as cinco
leituras** devolveram 3 elementos — “Chrome Legacy Window”, o título da aba e
“Notifications”. Não era a janela atrás, nem a vista errada: era o **Chrome com
a acessibilidade desligada**.

O Chrome não publica a página para qualquer programa. Ele publica quando o
Windows diz que existe um **leitor de tela** na máquina — a configuração
`SPI_SETSCREENREADER`, a mesma que o NVDA liga ao abrir. Sem esse sinal, a
janela responde só pela moldura, por todas as vistas.

Então o JARVIS passou a:

1. **dar o sinal** (ligar o modo leitor de tela) quando a leitura vem pobre, e
   pedir a árvore de novo;
2. **devolver a configuração como estava** no fim do programa — é emprestado,
   não tomado;
3. mostrar no diagnóstico se o modo estava ligado, e medir **antes e depois**.

Se mesmo assim continuar em 3 elementos, o diagnóstico lista as **janelas
filhas** do Chrome (a página mora numa filha, `Chrome_RenderWidgetHostHWND`) com
a contagem de cada uma — e aí o problema não é leitura: é o Chrome não publicar
nada, e o caminho é `chrome-acessibilidade.bat` (§7.2).

### 7.1.1 O que o log de 16/11 mostrou (0.91.26)

Duas rodadas do mesmo diagnóstico, na mesma janela, sem nada mudar na tela:

    1a rodada:   msaa 85 elementos — diálogo: SIM
    2a rodada:   auto 3 — uia 3 — uia_raw 3 — uia_content 3 — msaa 2

O Chrome **liga** a árvore da página quando alguém a pede e **desliga** quando
para de pedir. Ligar o sinal uma vez, no meio do caminho, não segura nada: a
página aparece, é lida, e segundos depois já não está mais lá.

Por isso, desde a 0.91.26:

1. o sinal é dado **antes da primeira leitura**;
2. **toda** leitura (a que preenche o painel, a que confere o botão, a que
   copia) repete o pedido de árvore quando vem pobre;
3. a **MSAA** é tentada primeiro: foi a única que viu o painel aberto
   (85 elementos, contra 43–58 das vistas da UIAutomation).

### 7.2 `chrome-acessibilidade.bat`

Fecha o Chrome e abre de novo com `--force-renderer-accessibility`. É a opção
que o próprio Chrome oferece para publicar a árvore sempre, sem depender do
sinal do Windows. **Fecha o Chrome** — as abas voltam, mas salve o que estiver
escrevendo.

Desde a 0.91.26 ele **espera o Chrome fechar de verdade** (até 15 s, conferindo
a lista de processos) antes de abrir: reabrir cedo faz o Windows entregar a
chamada ao processo antigo, e aí a opção é ignorada — foi por isso que, no log
de 16/11, o Chrome voltou com 43 elementos uma vez e com 3 na seguinte.

### 7.3 O caminho que não lê a tela (0.91.27)

O log de 16/11 mostrou que o sinal de leitor de tela **não segura** a página
por mais que alguns segundos, e que o balão “Restaurar páginas?” (o Chrome
pergunta isso depois de ser morto com `taskkill /F`) entrava na leitura como se
fosse o site. Doze versões gastas em cima da pergunta errada.

O Chrome tem uma porta de controle própria — a mesma que o F12 usa, o
**DevTools Protocol**. Por ela o programa não lê tela: ele pergunta à página
quais são os botões e recebe a resposta em texto. A página pode despublicar a
árvore de acessibilidade quando quiser; a porta continua lá.

    chrome-cdp.bat        (um duplo clique)

O que ele faz, na ordem:

1. abre um Chrome **próprio do JARVIS**, com o perfil na pasta `perfil-cdp`
   (o Chrome do dia a dia **não é fechado**; nada de `taskkill`);
2. espera a porta 9222 responder (até 20 s);
3. chama `chave-no-navegador.py --cdp --autorizar`, que faz o serviço inteiro
   dentro da página: “New key” → nome → expiração “No expiration” → limite
   “No limit” → “Create” → lê a chave → grava no `.env`.

Duas condições do Chrome, e nenhuma é escolha nossa:

- a porta **só abre** num Chrome iniciado com `--remote-debugging-port=9222`;
- **desde o Chrome 136** essa opção é **ignorada no perfil padrão** (proteção
  contra roubo de cookie por porta de depuração). Por isso o perfil separado.

A consequência prática, e ela é uma vez só: na **primeira** execução, entre na
sua conta do OpenRouter **na janela do JARVIS**. É uma janela separada da sua;
o login fica guardado em `perfil-cdp`, e nas próximas vezes não é pedido de
novo (o `perfil-cdp` também sobrevive a atualização do JARVIS — ele está na
pasta do programa, não no zip).

Se a janela abrir sem login, o programa diz exatamente isso e não clica em
nada. Se a porta não abrir, o `chrome-cdp.bat` diz para rodar de novo (o Chrome
às vezes leva mais que 20 s na primeira abertura de um perfil novo).

O `pegar-chave.bat` continua existindo: se a porta 9222 estiver aberta, ele vai
por ela; se não, faz o caminho antigo (ler a tela, esperar a cópia do dono).

## 8. De onde veio este manual

- `openrouter.ai/docs` — *Creating an API key*: “dê um nome e, opcionalmente,
  um limite de crédito; a chave é mostrada uma vez na criação”.
- `openrouter.ai/docs/api_reference/authentication` — formato da chave
  (`sk-or-v1-` + 64 hex, 73 caracteres), e que limite por chave é recomendado.
- Guias de terceiros (2025–2026) confirmando o painel: **Credit limit**,
  **Reset limit every** (diário/semanal/mensal, meia-noite UTC; `N/A` = limite
  fixo que não reseta) e **Expiration** com a opção **No expiration**.
- Prints do dono: `image-32/33/34` (15–16/11) — o painel aberto, os três campos
  e a lista de expiração aberta com `No expiration` marcado.
