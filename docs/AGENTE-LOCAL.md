# Agente local — usar as skills sem modelo

Desde a 0.39.0 o chat tenta resolver o pedido **sem chamar provedor de IA**; a
correção por apelido, a memória de respostas e o painel chegaram na 0.40.0.
Quando nenhuma skill ou receita serve, ele procura na web, lê a página e devolve
o que achou — também sem modelo.

O caminho tem seis degraus, nesta ordem:

| # | Degrau | O que acontece | Precisa de quê |
|---|---|---|---|
| 0 | **Correlação ensinada** | se você já corrigiu esse pedido, usa a skill que você escolheu | API Python ligada |
| 0b | **Resposta guardada** | se você já mandou buscar isso na web, devolve o que ficou guardado, com a data | API Python ligada |
| 1 | **Skill existente** | procura nas 230 skills por palavra (nome, categoria, descrição, campos), preenche os parâmetros a partir da própria frase e executa | API Python ligada |
| 2 | **Receita pronta** | se não achou skill, monta uma **skill local** a partir de 26 receitas e executa na hora | API Python ligada |
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

## Pedidos que ganham do ranking

Alguns pedidos não se resolvem por palavra — a palavra certa aparece em dezenas
de skills. Para esses existe regra explícita, antes da busca:

| Pedido | Vai para | Pede confirmação |
| --- | --- | --- |
| `configura o google drive pra mim` · `usa o drive como espaço externo` | `armazenamento.drive-copiar` | **sim** |
| `tira a biblioteca do drive` · `desfaz o drive` | `armazenamento.drive-copiar` com `modo=desfazer` | **sim** |
| `como configuro o drive?` · `o drive tá configurado?` | `armazenamento.drive` (só lê) | não |
| `limita a banda do drive` · `limita o drive em 500` · `devolve a banda toda` | `armazenamento.drive-banda` | **sim** |
| `rodar "python -m pacote --help" no repositório dono--repo` | `repos.executar` | **sim** |
| `ler README.md do repositório dono--repo` | `repos.ler` | não |

Pergunta com `?` nunca dispara a skill de cópia: no máximo ela mostra o estado.
`abre o drive` e `pausa o drive` continuam indo para a busca normal.

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
tipo composto). Há um teste que monta essa frase para **todas as 230 skills**,
relê com o mesmo parser e valida no modelo Pydantic de cada uma — sem executar
nada. É a prova de que nenhuma skill fica inalcançável.

## As skills novas também caem aqui

`biblioteca.ocr`, `biblioteca.video`, `biblioteca.importar` e todo o resto do
catálogo entram na busca por palavra como qualquer outra skill — e como elas
têm efeito, a execução para na confirmação:

```text
importar a foto da página Downloads/contrato.jpg
→ skill biblioteca.importar · parâmetros caminho=Downloads/contrato.jpg
→ “Responda ‘sim, pode’ para eu seguir.”
```

O que o agente **não** faz sozinho: escolher por você que um vídeo do YouTube
deve ser baixado só porque você colou o link — isso exige o pedido explícito.

## O que ele faz quando o pedido é vago

| Situação | Resposta |
|---|---|
| Achou a skill, mas falta um campo | “Encontrei a skill X, mas falta o campo Y” |
| A skill escolhida grava, baixa ou executa | pede o “sim, pode” e mostra os parâmetros antes |
| Duas skills parecidas, mesma nota | lista as três mais próximas e pede para você escolher |
| Nenhuma skill, mas uma receita serve | cria a skill local, guarda em `storage/agente-local/skills.json` e executa |
| Nada serve e a web está ligada | fontes numeradas + trecho lido, com aviso de que não criou skill |
| Nada serve e a web está desligada | explica o motivo e sugere “ajuda” |

## As 26 receitas

| Texto | Números | Utilidades |
|---|---|---|
| contar palavras, caracteres, linhas | somar, média, maior e menor | ordenar, remover repetidos, contar repetições |
| extrair links, e-mails, números, telefones, datas | porcentagem, regra de três, juros simples | maiúsculas, minúsculas, slug, inverter |
| converter unidades (km, kg, litros, °C) | diferença entre datas, somar dias a uma data | hash SHA-256, validar CPF |
| | IMC (peso e altura) | |

Cada receita é uma função pura. Skill criada aqui é um **registro** dessa receita
com nome próprio — não é código novo.

## Os limites, ditos sem rodeio

- **Não escreve código novo.** Para criar uma skill fora do catálogo de receitas
  seria preciso um modelo. O que ele faz no lugar: copia o **passo a passo** que
  leu da página e guarda como skill de procedimento — texto para você seguir,
  não código para rodar.
- **A busca é por palavra, não por significado.** “planilha” encontra “xlsx”
  por sinônimo cadastrado; “aquela coisa de somar” não encontra nada.
- **Termo fraco não executa.** A skill só roda se o pedido casar com o nome, o
  id ou a categoria — descrição sozinha só serve para sugerir.
- **A web precisa de rede e token.** Sem eles, o degrau 3 é pulado e o agente
  avisa.
- **Os passos ficam pendentes até você decidir.** O texto lido da web é guardado
  em `storage/agente-local/pendente.json` (um pedido por vez) para poder virar
  skill; se você não pedir, ele é substituído no próximo pedido.

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

164 testes, nenhum toca a rede: o registro é um dublê e a busca/leitura da web
são funções injetadas.

## Aprender com a página

Quando nenhuma skill nem receita serve e a web responde, o agente **não joga o
resultado fora**. Se o texto lido tem lista numerada, ele recorta os passos
(`1. … 2. …`) e pergunta:

```text
A página traz um passo a passo:
1. Baixe o arquivo do site oficial do emissor
2. Abra o gerenciador de certificados do Windows
3. Importe o arquivo e confirme a senha

Se quiser que eu guarde isso como skill, diga: criar skill com esses passos
```

Diga a frase e nasce uma **skill local de procedimento** — `local.proc-<nome>`,
com os passos e o link da fonte. Depois disso, pedir pelo nome devolve o passo a
passo na hora, sem rede e sem modelo. O que ela **não** faz: executar os passos
sozinha. Procedimento de fora é texto para você seguir, não código para rodar.

---

## Confirmação de efeito

Skill que baixa, grava ou executa não roda só porque a frase parecida apareceu.
O agente devolve `acao: "confirmar"` com os parâmetros já preenchidos e espera um
“sim, pode”. Vale uma vez: cada novo pedido com efeito pergunta de novo.

É o que protege `repos.baixar`, `repos.executar`, `sistema.baixar`, `files.write`
e companhia de serem disparadas por engano. Na API, quem confirma manda
`confirmar: true` no corpo de `POST /api/agente/executar`.

