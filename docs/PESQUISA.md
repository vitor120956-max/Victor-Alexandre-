# Pesquisar e ler a web

Resposta curta para a pergunta mais comum: **o JARVIS consegue usar a web para responder?**

| O que você quer | Existe hoje? | Onde |
|---|---|---|
| Abrir uma busca no navegador | sim | chat: `pesquisar por X` |
| Buscar na web de dentro do JARVIS | sim | skill `sistema.rede`, ação `buscar` |
| Ler o texto de uma página | sim | skill `sistema.rede`, ação `olhar` |
| **Redigir a resposta a partir do que leu** | **sim, desde a 0.38.0** | chat: `pesquisar e responder X` |

Desde a 0.38.0 as duas pontas estão ligadas: o comando `pesquisar e responder X` busca, lê as primeiras páginas e manda o texto ao modelo como material citável. Sem provedor configurado ele não falha — devolve as fontes e o trecho lido, sem resumo.

## Pesquisa com fonte, no chat

```text
token SEU_TOKEN
pesquisar e responder quem foi Machado de Assis
```

O `token` guarda o valor **só na memória desta aba**: não vai para o `localStorage` nem para o backup exportado. Some ao recarregar a página — é para isso mesmo.

O que o JARVIS faz, em ordem:

1. verifica o token e se a API subiu com `JARVIS_HOST_REDE=1`;
2. busca os 6 primeiros resultados no DuckDuckGo;
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

## O que o chat faz

```text
pesquisar por Machado de Assis
```

Isso **abre o Google numa aba nova**. O JARVIS não lê os resultados e não responde: é um atalho de navegador. Sem chave de IA, perguntas abertas ("quem foi Machado de Assis") caem na mensagem de IA não configurada.

## O que a skill faz

A skill **Busca e leitura na web** (`sistema.rede`) tem duas ações:

| Ação | O que devolve |
|---|---|
| `buscar` | título e link de até 25 resultados do **DuckDuckGo** (não do Google), sem resumo |
| `olhar` | o texto extraído da página informada, até **20.000 caracteres**, com status e tipo |

Medido nesta máquina, `olhar` numa página do GitHub devolveu **4 linhas de metadados** (url, status, tipo, caracteres) mais o texto raspado. A busca usa a página HTML do DuckDuckGo e depende de ela responder sem captcha — por isso ela pode voltar vazia mesmo com internet boa.

## As três travas

A skill não liga sozinha, e é de propósito:

1. **Rede desligada por padrão.** A API precisa subir com `JARVIS_HOST_REDE=1`.
2. **Token de host.** O valor está em `storage/host-token.txt` e vai no campo `autorizacao`.
3. **Endereço privado é recusado.** `localhost`, `192.168.x.x`, `10.x.x.x` e link-local são bloqueados — sem isso, uma skill poderia ler a sua rede interna.

## Passo a passo

1. Suba a API com a rede ligada:

```bat
cd /d D:\JARVIS
set JARVIS_HOST_REDE=1
.venv\Scripts\python iniciar.py
```

2. Abra `D:\JARVIS\storage\host-token.txt` no Bloco de Notas e copie a linha. O terminal também mostra os 4 primeiros e os 4 últimos caracteres.

3. Na interface, abra **Skills → Busca e leitura na web**.

4. Ação `buscar`, consulta `Machado de Assis`, limite 8. Cole o token e execute. Você recebe uma tabela de títulos e links.

5. Para ler uma das páginas: ação `olhar`, cole o link no campo `url`. Você recebe o texto extraído.

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
