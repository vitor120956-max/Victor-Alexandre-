# Pesquisar e ler a web

Resposta curta para a pergunta mais comum: **o JARVIS consegue usar a web para responder?**

| O que você quer | Existe hoje? | Onde |
|---|---|---|
| Abrir uma busca no navegador | sim | chat: `pesquisar por X` |
| Buscar na web de dentro do JARVIS | sim, **sem token** desde a 0.49.0 | skill `sistema.rede`, ação `buscar` |
| Escolher a plataforma: DuckDuckGo, Wikipédia ou YouTube | sim | campo `fonte` (ou diga “no youtube”, “na wikipedia”) |
| Ler o texto de uma página | sim | skill `sistema.rede`, ação `olhar` |
| **Redigir a resposta a partir do que leu** | **sim, desde a 0.38.0** | chat: `pesquisar e responder X` |

Desde a 0.38.0 as duas pontas estão ligadas: o comando `pesquisar e responder X` busca, lê as primeiras páginas e manda o texto ao modelo como material citável. Sem provedor configurado ele não falha — devolve as fontes e o trecho lido, sem resumo.

Desde a **0.49.0** buscar e ler **não pede token**: basta a rede ligada. A busca usa três fontes que não cobram chave — **DuckDuckGo**, **Wikipédia** e **YouTube** — e cada resultado vem marcado com a fonte de onde saiu. O token de host continua obrigatório só para o que **grava ou executa** (baixar, importar, instalar, rodar).

## Pesquisa com fonte, no chat

```text
pesquisar e responder quem foi Machado de Assis
```

Se você já tinha o hábito de mandar `token SEU_TOKEN` antes de pesquisar, pode parar: a busca não usa mais o token. (O valor, quando existe, fica **só na memória da aba** — não vai para o `localStorage` nem para o backup exportado.)

O que o JARVIS faz, em ordem:

1. confere se a API subiu com `JARVIS_HOST_REDE=1`;
2. busca os 6 primeiros resultados na fonte pedida — sem pedido explícito, intercala DuckDuckGo, Wikipédia e YouTube;
3. lê o texto das **2 primeiras** páginas (endereço privado é recusado);
4. monta o material com título, URL e conteúdo de cada fonte;
5. pede a resposta ao modelo com esse material, que entra como dado, nunca como instrução;
6. devolve a resposta **e a lista de fontes**, marcando quais foram lidas.

| Situação | O que você recebe |
|---|---|
| IA configurada | resposta redigida + fontes |
| IA não configurada | fontes + trecho da primeira página, sem resumo |
| Página que não abre | aviso citando o endereço, e a pesquisa continua nas outras |
| Busca sem resultado | aviso explícito — ele não inventa link |
| Provedor com erro (401, 429) | aviso com o motivo e as fontes continuam listadas |

Variantes aceitas: `pesquise na web e me explique ...`, `buscar e responder ...`, `responder com fontes ...`.

A fonte também pode vir no próprio pedido — `pesquisa no youtube sobre python`, `procura na wikipedia sobre café`, `busca no duckduckgo sobre impostos`. A regra ganha do ranking de skills, então o pedido não cai em “legenda de vídeo” por causa da palavra “vídeo”. `no google` vira a busca nas três: o Google não entrega resultado parseável sem chave paga, e o JARVIS diz isso em vez de fingir que leu.

## O que o chat faz

```text
pesquisar por Machado de Assis
```

Isso **abre o Google numa aba nova**. O JARVIS não lê os resultados e não responde: é um atalho de navegador. Sem chave de IA, perguntas abertas ("quem foi Machado de Assis") caem na mensagem de IA não configurada.

## O que a skill faz

A skill **Busca e leitura na web** (`sistema.rede`) tem duas ações:

| Ação | O que devolve |
|---|---|
| `buscar` | título, link e **fonte** de até 25 resultados do DuckDuckGo, da Wikipédia ou do YouTube, sem resumo. Campo `fonte`: `auto` (as três), `duckduckgo`, `wikipedia` ou `youtube` |
| `olhar` | o texto extraído da página informada, até **20.000 caracteres**, com status e tipo |

Medido nesta máquina, `olhar` numa página do GitHub devolveu **4 linhas de metadados** (url, status, tipo, caracteres) mais o texto raspado. A busca usa a página HTML do DuckDuckGo (sem chave de API) e depende de ela responder sem captcha — por isso ela pode voltar vazia mesmo com internet boa. É exatamente para isso que existem as outras duas fontes: se uma não responde, a resposta mostra “Fontes que responderam” e “Fontes que não responderam”, e o que veio continua valendo.

## As travas

A skill não liga sozinha, e é de propósito:

1. **Rede desligada por padrão.** A API precisa subir com `JARVIS_HOST_REDE=1`. Para **buscar e ler**, essa é a única trava.
2. **Token de host — só para gravar.** `storage/host-token.txt` e o campo `autorizacao` continuam exigidos por `sistema.baixar`, `sistema.executar`, `sistema.elevar_executar` e `files.import`. Busca e leitura não pedem token desde a 0.49.0.
3. **Endereço privado é recusado.** `localhost`, `192.168.x.x`, `10.x.x.x` e link-local são bloqueados — sem isso, uma skill poderia ler a sua rede interna.

## Passo a passo

1. Suba a API com a rede ligada:

```bat
cd /d D:\JARVIS
set JARVIS_HOST_REDE=1
.venv\Scripts\python iniciar.py
```

2. Na interface, abra **Skills → Busca e leitura na web**.

3. Ação `buscar`, consulta `Machado de Assis`, limite 8, fonte `auto`. Execute — **sem token**. Você recebe uma tabela de títulos, links e a fonte de cada um.

4. Para ler uma das páginas: ação `olhar`, cole o link no campo `url`. Você recebe o texto extraído.

Não há resumo: o que vem é o texto da página, truncado. Quem interpreta é você.

## O que cada modo entrega

| Sem chave | Com chave |
|---|---|
| a skill **encontra** e **lê**; a busca com fonte devolve links + trecho | o comando `pesquisar e responder` **redige** a resposta com o texto lido |
| você interpreta | a IA interpreta **citando as fontes** |
| a pergunta não sai da máquina | pergunta e páginas lidas vão ao provedor |

A diferença técnica está no campo `material` da requisição de IA: ele aceita até 60.000 caracteres de texto e o provedor o trata como **dado citável, nunca como instrução**. É o que impede uma página maliciosa de sequestrar o comportamento do modelo — o texto entra como material, não como ordem.

As páginas lidas também passam pelo timeout do servidor: uma página que demora mais que o limite vira aviso e a pesquisa continua. Nada é gravado em disco: o material existe só durante a resposta.

## Limites que precisam ficar ditos

- **DuckDuckGo, não Google.** O Google bloqueia esse tipo de acesso; o DuckDuckGo aguenta, mas muda a marcação da página de vez em quando e a busca passa a voltar vazia.
- **Sem resumo automático.** Texto bruto, truncado em 20 mil caracteres.
- **Resultado vazio não prova que o assunto não existe.** Pode ser bloqueio, captcha ou marcação nova.
- **Nada é gravado.** A skill não salva arquivo; quem baixa é `sistema.baixar`, e só para a quarentena.
