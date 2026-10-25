# Agente local — usar as skills sem modelo

A partir da 0.39.0 o chat tenta resolver o pedido **sem chamar provedor de IA**.
Quando nenhuma skill ou receita serve, ele procura na web, lê a página e devolve
o que achou — também sem modelo.

O caminho tem quatro degraus, nesta ordem:

| # | Degrau | O que acontece | Precisa de quê |
|---|---|---|---|
| 1 | **Skill existente** | procura nas 209 skills por palavra (nome, categoria, descrição, campos), preenche os parâmetros a partir da própria frase e executa | API Python ligada |
| 2 | **Receita pronta** | se não achou skill, monta uma **skill local** a partir de 20 receitas e executa na hora | API Python ligada |
| 3 | **Web** | busca no DuckDuckGo, lê a primeira página e devolve fontes + trecho | rede (`JARVIS_HOST_REDE=1`) e token de host |
| 4 | **Explicação** | diz que não achou e mostra o que sabe fazer | — |

Nenhum degrau chama modelo. A pergunta nunca vira custo.

## Como usar no chat

```text
artigo 49 do CDC                     → skill legal.article, executa
analisar texto: a vida é bela        → skill text.analyze, executa
contar as palavras de: um dois três  → cria a skill local e devolve "3 palavras"
minhas skills locais                 → lista o que já foi criado
```

Três jeitos de forçar o agente mesmo com IA configurada:

```text
skill <pedido>
agente <pedido>
modo local <pedido>
```

## O que ele faz quando o pedido é vago

| Situação | Resposta |
|---|---|
| Achou a skill, mas falta um campo | “Encontrei a skill X, mas falta o campo Y” |
| Duas skills parecidas, mesma nota | lista as três mais próximas e pede para você escolher |
| Nenhuma skill, mas uma receita serve | cria a skill local, guarda em `storage/agente-local/skills.json` e executa |
| Nada serve e a web está ligada | fontes numeradas + trecho lido, com aviso de que não criou skill |
| Nada serve e a web está desligada | explica o motivo e sugere “ajuda” |

## As 20 receitas

| Texto | Números | Utilidades |
|---|---|---|
| contar palavras, caracteres, linhas | somar, média, maior e menor | ordenar, remover repetidos, contar repetições |
| extrair links, e-mails, números | porcentagem | maiúsculas, minúsculas, slug, inverter |
| converter unidades (km, kg, litros, °C) | diferença entre datas | hash SHA-256 |

Cada receita é uma função pura. Skill criada aqui é um **registro** dessa receita
com nome próprio — não é código novo.

## Os limites, ditos sem rodeio

- **Não escreve código novo.** Para criar uma skill fora do catálogo de receitas
  seria preciso um modelo. O agente diz isso e devolve o resultado da web.
- **A busca é por palavra, não por significado.** “planilha” encontra “xlsx”
  por sinônimo cadastrado; “aquela coisa de somar” não encontra nada.
- **Termo fraco não executa.** A skill só roda se o pedido casar com o nome, o
  id ou a categoria — descrição sozinha só serve para sugerir.
- **A web precisa de rede e token.** Sem eles, o degrau 3 é pulado e o agente
  avisa.
- **Nada é gravado em disco além da lista de skills locais.** O texto lido da
  web existe só durante a resposta.

## Onde ficam os arquivos

| Peça | Arquivo |
|---|---|
| busca, extração de parâmetros, receitas | `server/agente_local.py` |
| rotas `POST /api/agente/executar` e `GET /api/agente/skills` | `server/app.py` |
| skills locais criadas | `storage/agente-local/skills.json` |
| testes | `server/tests/test_agente_local.py` |

## O que dá para testar sem rede

```bash
.venv/bin/python -m pytest server/tests/test_agente_local.py -q
```

93 testes, nenhum toca a rede: o registro é um dublê e a busca/leitura da web
são funções injetadas.
