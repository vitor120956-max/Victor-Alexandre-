# Memória de agente

Agente sem memória recomeça toda conversa. Quem já tentou resolver isso com “só guarda a conversa num arquivo” esbarra em quatro problemas: a busca devolve o arquivo errado, o fato vira texto solto sem relação, a lição da sessão se perde e apagar um dado deixa o resto falando dele. A camada de memória responde essas quatro perguntas com conta explícita: **em que via procurar**, **o que vira nó e aresta**, **o que promover da sessão** e **qual é o raio de alcance do esquecimento**.

O insumo é o [`topoteretes/cognee`](https://github.com/topoteretes/cognee) — **Apache-2.0**, 32 mil estrelas, Python. Ele é uma plataforma de memória para agentes: transforma documento, código e conversa em grafo de conhecimento pesquisável, com quatro operações públicas (`remember`, `recall`, `improve`, `forget`). Daqui não veio código Python do upstream: veio o desenho — o portão determinístico de skill do `recall()`, o vocabulário de vias de busca, o conjunto de nós por sessão e o escopo de esquecimento com `memory_only` — reimplementado com fixtures próprias.

| Camada | O que faz | Toca a rede? |
|---|---|---|
| **Motor** (`server/memoria.py`, 7 skills) | Roteia a consulta, extrai entidade, mede o grafo, destila a sessão, recupera com lastro e planeja o esquecimento | **Não** — só o que foi colado |
| **Página** (`/memoria-ia`) | Aba por operação, amostra de memórias com data, grafo com ciclo e sessão com lição | Não |

Nada é executado: nenhum modelo é chamado, nenhum embedding é gerado, nenhum banco de grafo é aberto e nenhuma sessão é gravada. Toda resposta marca `executed: false` e `readOnly: true`.

## As sete skills

| Rota | Entrada | O que devolve |
|---|---|---|
| `memoria.roteamento` | consulta | a via de recuperação com a pontuação de cada regra, o limiar, a margem e a negação |
| `memoria.entidades` | texto | nome, sigla, código, arquivo, data, valor e local por padrão lexical, mais as triplas declaradas |
| `memoria.grafo` | arestas | grau, componente conectado, ciclo, nó isolado, hub, folha e densidade |
| `memoria.sessao` | conversa, limiar | cada turno pontuado como lição em potencial e o que promover para a memória permanente |
| `memoria.recall` | consulta, memórias, via, dataset, limite, hoje | resultado por BM25 + afinidade + recência + sinal da via, com o lastro de cada item |
| `memoria.esquecer` | memórias, ids, dataset, escopo | o plano de remoção com o raio de alcance e os dependentes que continuam citando o alvo |
| `memoria.regras` | — | vias, pesos, tipos, limites e a fórmula inteira |

Todas aceitam `modo` com `lite`, `full` (padrão) ou `ultra`; `lite` devolve só o que bloqueia e `ultra` acrescenta as perguntas antes de liberar.

## 1. Roteamento: a via sai da pergunta

O cognee escolhe a via com um LLM (`select_search_type`) e o prompt de seleção lista em que cada tipo é bom. Aqui a escolha é lexical e mostra a conta: **29 regras** com peso, agrupadas em oito vias.

| Via | Quando a pergunta pede | Peso típico |
|---|---|---|
| `chunks` | um fato pontual: quem, quando, onde, qual valor | 3,0 a 3,0 |
| `grafo` | relação, caminho de dois saltos, dependência | 3,0 a 4,0 |
| `hibrido` | passagem com a fonte, pergunta ampla (**padrão**) | 2,0 a 3,0 |
| `resumo` | síntese, visão geral, muitos documentos | 2,0 a 4,0 |
| `temporal` | linha do tempo, antes/depois, mais recente | 3,0 a 4,0 |
| `codigo` | símbolo, arquivo, assinatura, stack trace | 2,5 a 4,0 |
| `procedimento` | como fazer, passo a passo, instalar | 2,0 a 4,0 |
| `regras` | política, decisão registrada, permissão, lição | 3,0 a 4,0 |

A decisão segue três passos:

1. **Soma** os pesos das regras que casaram — 4,0 é sinal forte (decide sozinho), 3,0 é frase procedural (decide sozinha), 2,0 é sinal fraco (só soma).
2. **Descarta** o sinal que aparece até 20 caracteres depois de uma negação: “não quero resumo” não pede resumo.
3. **Compara** com o limiar de **3,0** e a margem de **1,0**. Abaixo do limiar, cai em `hibrido` e o parecer diz que foi fallback. Empate técnico entre duas vias acima do limiar levanta `ambiguidade-de-via` — pergunta que pede duas coisas ao mesmo tempo.

Achados: `sem-sinal` (nenhuma via passou), `ambiguidade-de-via`, `consulta-curta` (menos de três termos) e `sinal-negado` (nice — a negação funcionou).

## 2. Entidades: o que vira nó

Sete tipos, todos por padrão lexical — nenhum modelo:

| Tipo | Reconhece | Exemplo |
|---|---|---|
| `nome` | duas a quatro palavras capitalizadas | `Marie Curie` |
| `sigla` | 2 a 8 caracteres em maiúscula | `ESPCI`, `LGPD` |
| `codigo` | prefixo-hífen-número e `#issue` | `SDM-2041`, `#481` |
| `arquivo` | caminho com extensão conhecida | `server/memoria.py` |
| `data` | ISO, `dd/mm/aaaa` e `12 de março de 2024` | `1867-11-07` |
| `valor` | moeda, milhar e percentual | `R$ 45.000`, `90%` |
| `local` | preposição + nome próprio, com `of`/`de` no meio | `University of Paris` |

Sigla que já entrou como código não entra duas vezes, e local que já entrou como sigla também não. O que não é reconhecido é declarado, não adivinhado: `sem-entidades` (must) quando o texto não tem nenhum dos sete tipos, `nome-solto` quando todo nome aparece uma vez e sem relação, `sigla-longa` (nice) para sequência de maiúsculas que é ênfase, não sigla.

**Relação declarada** entra por três formas: `sujeito -> relação -> objeto` em português (foi, é, era, trabalha, nasceu, usa, depende de, substitui, criou, escreveu…), a mesma em inglês (was, works at, born in, uses, depends on…) e papel (`foi professor na`, `é diretor do`). Nada é inferido de prosa solta.

## 3. Grafo: medir antes de confiar

O formato é uma aresta por linha:

```text
Marie Curie -> trabalhou em -> University of Paris
Marie Curie -> descobriu -> polônio
Pierre Curie -> casado com -> Marie Curie
Nanismo
```

Linha sozinha declara nó isolado; `#` inicia comentário; o JSON `{"arestas": [{"de": "...", "relacao": "...", "para": "..."}]}` faz o mesmo.

O que é medido: **grau** de entrada e saída, **componente conectado**, **ciclo simples** na direção das arestas, **densidade** (arestas por nó) e a cobertura do maior componente.

| Achado | Nível | Quando |
|---|---|---|
| `grafo-vazio` | must | há nó e nenhuma aresta |
| `no-isolado` | should | nó fora de toda relação |
| `grafo-fragmentado` | should | mais de um componente entre os nós ligados |
| `ciclo` | should | caminho que volta ao nó de origem |
| `hub` | nice | nó com grau 12 ou mais |
| `grafo-estrela` | nice | todos os nós são folha |

Ciclo é o achado que mais importa: em grafo não dirigido, `A -> B` e `B -> A` parecem vaivém; aqui a travessia segue a seta, então só conta volta real. “É” e “substitui” que voltam ao mesmo nó são identidade, não relação — o parecer pede para trocar por `relaciona`.

## 4. Sessão: o que promover

O cognee chama isso de destilar a sessão em memória permanente (`improve`). Aqui cada turno vira candidato com nota aberta:

| Sinal | Peso |
|---|---|
| marcador explícito (`decisão:`, `regra:`, `aprendizado:`, `nunca`, `sempre`, `armadilha`) | +3,0 |
| verbo de fato dito pela pessoa | +1,0 |
| texto com corpo (40 caracteres ou mais) | +1,0 |
| repetido na conversa | +1,5 |
| `feedback: 2` ou mais | +2,0 |
| `feedback: -1` | −3,0 |
| confirmação curta (`ok`, `certo`, `valeu`) | −2,0 |
| fala do agente sem marcador | −0,5 |

O limiar padrão é **4,0**. Regra declarada pelo agente com marcador conta como sinal — e por isso levanta `regra-do-agente` (should): regra que o agente escreve sobre si mesmo não é decisão do time. Também saem `sessao-sem-licao` (nada passou), `quase-promovido` (a menos de um ponto do limiar), `licao-sem-tipo` (nice) e `sessao-grande` (acima de dez promoções — sessão que promove tudo não destilou nada).

## 5. Recall: lastro, não palpite

A pontuação de cada item é aberta:

```text
pontuacao = BM25 + 0,6 × afinidade + 0,4 × recência + sinal_da_via
```

- **BM25** com `k1 = 1,2` e `b = 0,75` sobre os termos da consulta, sem palavra vazia — em corpus pequeno, um “do” cria casamento falso.
- **Afinidade** é a fração dos termos da consulta presentes no item.
- **Recência** é decaimento exponencial com meia-vida de **180 dias**; sem data, vale 0,5 para todos.
- **Sinal da via** soma 0,5 quando o item combina com a via escolhida: data para `temporal`, arquivo ou código para `codigo`, tipo regra ou decisão para `regras`, tripla para `grafo`, texto longo para `resumo`.
- Item com mais de **365 dias** perde 0,3 e levanta `memoria-vencida`.

Item que não casa **nenhum** termo da consulta sai do resultado: devolver por recência é ruído com carimbo de memória. Quando nada casa, o parecer devolve o recorte mesmo assim e levanta `resultado-fraco` — melhor admitir que avisar por omissão. A tabela de lastro mostra, por resultado, BM25, afinidade, recência e pontuação.

## 6. Esquecer: raio de alcance

Três escopos, como no `forget()` do upstream:

| Escopo | Exige | Apaga |
|---|---|---|
| `item` | `ids` | o item, e o parecer mostra o que ainda cita a entidade dele |
| `dataset` | nome do dataset | todos os itens do conjunto |
| `tudo` | confirmação explícita | a memória inteira (**must**) |

`somente_memoria` reproduz o `memory_only` do cognee: remove grafo e vetor e preserva o arquivo bruto, para reprocessar depois com outro modelo.

O **raio de alcance** é a conta que evita o esquecimento pela metade: para cada alvo, a camada extrai as entidades do texto e conta quantos itens do conjunto as citam. Se o alvo é `Marie Curie nasceu em Warsaw` e outro item fala de Warsaw, apagar só o primeiro deixa o segundo afirmando algo sobre um nó que saiu da memória. O parecer cobra `raio-de-alcance` (should) e lista os `dependentes`.

## Execução real

Rodando as skills contra uma amostra de cinco memórias datadas, um grafo de seis nós e uma conversa de oito turnos:

| Skill | Resultado |
|---|---|
| `memoria.roteamento` | “Onde fica o índice vetorial do Atlas?” → **`chunks`**, 3,0 pontos, margem de 3,0 |
| `memoria.roteamento` | “Como faço para instalar o plugin?” → **`procedimento`**, 7,0 pontos |
| `memoria.roteamento` | “Xyzzy plugh” → **fallback `hibrido`**, 0,0 pontos, achado `sem-sinal` |
| `memoria.entidades` | 13 entidades em 5 linhas, 2 triplas, os sete tipos presentes |
| `memoria.grafo` | 6 nós, 5 arestas, 1 componente, **1 ciclo**, 1 isolado, cobertura 100 % |
| `memoria.sessao` | 8 turnos → 5 candidatos → **3 promovidos** (1 vindo do agente, com aviso) |
| `memoria.recall` | 5 memórias, 2 devolvidas com lastro, 3 descartadas por lastro zero |
| `memoria.recall` | “qual a cor do céu?” → nenhum lastro, achado `resultado-fraco` |
| `memoria.esquecer` | apagar `m2` alcança **2 memórias** e tem **1 dependente** |

Os números são do texto colado, não de um banco: a camada não abre grafo, não lê arquivo e não chama modelo.

## Limites declarados

- O roteador é lexical: paráfrase sem as palavras-chave cai no `hibrido` por fallback.
- A extração não faz desambiguação nem correferência — “Curie” e “Marie Curie” são dois nós.
- Relação só entra na forma declarada; prosa corrida não vira aresta.
- O recall mede termo em comum, não verdade: memória errada continua errada e bem pontuada.
- Recência depende da data declarada; sem data, todo item vale metade.
- O esquecimento devolve plano, não execução: nada é apagado de verdade.
- Português e inglês apenas; outro idioma não casa regra de via nem de relação.

## Licença e atribuição

O desenho vem de [`topoteretes/cognee`](https://github.com/topoteretes/cognee), **Apache-2.0**. Nenhum arquivo Python do upstream foi copiado e nenhuma dependência foi adicionada: o roteador, a extração, o grafo, a destilação, o recall e o esquecimento foram reimplementados com fixtures próprias. A atribuição e o aviso da licença estão em [`licenses/topoteretes-cognee.txt`](licenses/topoteretes-cognee.txt).
