# Os modelos de IA — como funcionam e como trocar (0.79.1)

A pergunta foi curta: *“e sobre os modelos, como funcionam?”*. A resposta cabe
em uma frase e o resto é consequência dela:

> **A chave abre a porta; o modelo é quem responde.**

A mesma chave do Groq dá acesso a vários modelos. Trocar de modelo **não** pede
chave nova, não pede reinstalar nada e não muda o preço zero do plano grátis. O
que muda é a troca de sempre:

| | modelo **grande** (70B, 120B) | modelo **pequeno** (8B, 20B) |
|---|---|---|
| entende frase torta | melhor | pior |
| mantém o fio da conversa | melhor | razoável |
| velocidade | mais lento | quase instantâneo |
| cota grátis | menor | muito maior |

Não existe “o melhor”. Existe o melhor para o seu uso — e por isso a escolha
virou uma lista com o custo de cada opção, dentro do JARVIS.

---

## Onde trocar, na tela

**Configurações → Inteligência generativa → cartão `Modelos de IA`**

- a lista mostra cada modelo com uma frase do tipo *“o padrão; cota menor”* ou
  *“resposta quase instantânea; a maior cota grátis”*;
- **Usar este modelo** grava a escolha no `.env` e recarrega o cérebro **na
  hora** — sem fechar a janela;
- **Voltar ao padrão** é o caminho de volta, um clique;
- o campo **“ou o nome exato do modelo”** existe porque a lista é atalho, não
  prisão: qualquer nome que a sua conta tenha vale.

Modelo local é diferente: o “nome” é o arquivo `.gguf` no disco, e quem troca é
`ia.local` (a skill “rodar a IA sem chave”). O cartão avisa isso em vez de
oferecer uma lista de nuvem que não se aplica.

## O que está na lista (e por quê)

Números do plano grátis do Groq, publicados por ele — e que **mudam**:

| modelo | perfil | cota grátis (ordem de grandeza) |
|---|---|---|
| `llama-3.3-70b-versatile` | equilíbrio (padrão) | ~1.000 pedidos/dia |
| `llama-3.1-8b-instant` | rápido e resistente | ~14.400 pedidos/dia |
| `openai/gpt-oss-120b` | qualidade | ~200 mil tokens/dia |
| `openai/gpt-oss-20b` | rápido | ~200 mil tokens/dia |
| `meta-llama/llama-4-scout-17b-16e-instruct` | texto grande | ~500 mil tokens/dia |
| `qwen/qwen3-32b` | raciocínio | ~500 mil tokens/dia |

Três avisos honestos sobre esta tabela:

1. **ela envelhece** — o provedor muda modelo e cota sem pedir licença;
2. **ela não é promessa** — se um nome sair do ar, o botão **Testar** das chaves
   mostra o erro na hora (HTTP 404), em vez de a conversa falhar sem explicação;
3. **cota não é velocidade** — “pedidos por dia” e “tokens por dia” são réguas
   diferentes; o aviso de cota do JARVIS usa o que o provedor devolve nos
   cabeçalhos, não esta tabela.

## A cota é de cada modelo — e é isso que te salva

Um ponto que custou um print de tela ao dono: **no Groq a cota é por conta**
(várias chaves do mesmo login dividem tudo), mas **é separada por modelo**.
Ou seja: com a conta estourada no `llama-3.3-70b-versatile`, o
`llama-3.1-8b-instant` ainda responde, com a mesma chave.

Por isso trocar de modelo é o primeiro socorro — antes de criar conta nova, antes
de esperar o dia virar. O botão **Testar** das chaves já provou isso sozinho: se
a falha for 429/404, ele testa uma vez com `llama-3.1-8b-instant` e, se
responder, mostra o botão **Usar llama-3.1-8b-instant**.

| situação | o que trocar resolve |
|---|---|
| cota diária estourada no 70B | sim: outro modelo tem outra cota |
| chave revogada (401) | não: chave vale para todos os modelos |
| provedor fora do ar | não |

## Como ele escolhe quando você não escolhe

1. o `.env` (`JARVIS_AI_MODEL`) — é o que a tela grava;
2. o que estava em memória;
3. `llama-3.3-70b-versatile`, o padrão do projeto.

Sem chave nenhuma, nada disso importa: **as 315 skills rodam igual**, e o modelo
local (se estiver ligado) responde sem conta e sem internet.

## Três jeitos de trocar

| caminho | quando usar |
|---|---|
| cartão **Modelos de IA** (tela) | o normal; recarrega na hora |
| `.env`: `JARVIS_AI_MODEL=llama-3.1-8b-instant` | quando se quer editar à mão, junto com outras linhas |
| `py configurar-chave.py` | quando a chave **e** o modelo entram juntos, pelo terminal |

Todos escrevem no mesmo `.env`, e o `.env` é do usuário: nada aqui apaga
comentário ou reordena o arquivo.

## Se a resposta vier estranha

Antes de culpar o modelo, confira a ordem de sempre:

1. **a chave responde?** cartão Chaves de IA → **Testar**;
2. **a cota está de pé?** o aviso do topo da tela e o cartão mostram cada chave;
3. **a skill foi executada ou o modelo respondeu?** a bolha do chat diz a fonte
   (`python` = skill, `ai` = modelo).

Trocar de modelo é a última parada, não a primeira.
