# Agente local — usar as skills sem modelo

A partir da 0.40.0 o chat tenta resolver o pedido **sem chamar provedor de IA**.
Quando nenhuma skill ou receita serve, ele procura na web, lê a página e devolve
o que achou — também sem modelo.

O caminho tem seis degraus, nesta ordem:

| # | Degrau | O que acontece | Precisa de quê |
|---|---|---|---|
| 0 | **Correlação ensinada** | se você já corrigiu esse pedido, usa a skill que você escolheu | API Python ligada |
| 0b | **Resposta guardada** | se você já mandou buscar isso na web, devolve o que ficou guardado, com a data | API Python ligada |
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

## Quando ele erra: ensinar em vez de repetir

Errar é esperado — a busca é por palavra. O que não pode acontecer é o pedido
sumir. Por isso:

```text
você: quem inventou o pão
ele:   Não achei skill nem receita… (o pedido entra na fila)
você: não é essa, é a skill legal.article
ele:   Aprendi: quando você pedir "quem inventou o pão", uso legal.article.
```

Três correções e o que cada uma faz:

| Você diz | O que acontece |
|---|---|
| `não é essa, é a skill <id ou nome>` | grava a correlação em `storage/agente-local/apelidos.json`; o mesmo pedido passa a acertar |
| `procure na web sobre isso` | busca, lê a primeira página e **guarda** a resposta; o mesmo pedido passa a responder da memória |
| `esqueça <pedido>` | apaga as duas coisas — volta a perguntar |

A correlação casa pelo começo da frase: se você ensinou "meu relatório do mês",
o pedido "meu relatório do mês com path=documentos/x.pdf" também usa a skill.

Sobre o Google: o JARVIS usa a página HTML do **DuckDuckGo**, que não exige
chave. O Google bloqueia leitura automatizada e não tem busca gratuita com API —
o comando `abrir Google` continua abrindo a aba no navegador para você.

## A página Agente

No menu, **Agente** mostra tudo o que ele fez ou deixou de fazer:

| Seção | Serve para |
|---|---|
| Fila do “não sei fazer” | pedidos que não resolveram, com data e quantas vezes você tentou; dá para ensinar, buscar na web ou remover |
| Skills locais | o que ele criou a partir das receitas, com botão de apagar |
| Correlações ensinadas | os apelidos que você gravou, com botão de esquecer |
| Histórico | as últimas 200 execuções, com ação, skill e confiança |
| Receitas | o catálogo fechado de onde saem as skills novas |

## Cobrir qualquer skill

Nenhum campo precisa ser adivinhado: dá para escrever `campo=valor` no pedido.

```text
skill files.read path=documentos/relatorio.pdf
skill legal.article documentId=cdc, article=49
```

O valor é convertido pelo tipo do campo (inteiro, decimal, sim/não, JSON para
tipo composto). Há um teste que monta essa frase para **todas as 209 skills**,
relê com o mesmo parser e valida no modelo Pydantic de cada uma — sem executar
nada. É a prova de que nenhuma skill fica inalcançável.

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
| correlações ensinadas | `storage/agente-local/apelidos.json` |
| respostas guardadas da web | `storage/agente-local/respostas.json` |
| fila do que não foi resolvido | `storage/agente-local/fila.json` |
| histórico de execuções | `storage/agente-local/historico.json` |
| a tela | `src/pages/AgentePage.tsx` |
| testes | `server/tests/test_agente_local.py` |

## O que dá para testar sem rede

```bash
.venv/bin/python -m pytest server/tests/test_agente_local.py -q
```

112 testes, nenhum toca a rede: o registro é um dublê e a busca/leitura da web
são funções injetadas.
