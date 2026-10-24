# Contexto de conversa

Medir a conversa, dividir a janela, cortar por turno, consertar o histórico, preparar o resumo e contabilizar o que a chamada custou — antes de o provedor recusar por tamanho.

A camada parte do subsistema de contexto do [`CherryHQ/cherry-studio`](https://github.com/CherryHQ/cherry-studio) — **AGPL-3.0**, 52 mil estrelas — e reimplementa a **regra** em Python: orçamento, estimativa, corte, higiene, retenção e uso. Nenhuma linha do upstream foi copiada e nenhuma skill baixa tokenizador, chama modelo ou envia conversa para fora. O que você cola é lido localmente.

| Camada | O que faz | Toca a rede? |
|---|---|---|
| **Motor** (`server/contexto.py`, 7 skills) | Conta tokens, aplica a fórmula de imagem e mídia, agrupa turnos, saneia o histórico e soma custo | **Não** — só o texto colado |
| **Página** (`/contexto`) | Aba por verbo, campos por análise, métrica, barra de pressão e o parecer para copiar | Não |

O módulo reaproveita `server/review.py`: mesmos grupos (`must`, `should`, `nice`), mesmas contagens, veredito e Markdown. A conta é aritmética explícita e a saída é determinística.

## As sete skills

| Rota | Entrada | O que devolve |
|---|---|---|
| `contexto.orcamento` | janela, reserva, dialeto e conversa opcional | sala de entrada, reserva efetiva por precedência, prompt medido, sobra e pressão contra o limiar de 80% |
| `contexto.tokens` | conversa e dialeto | tokens por mensagem e por papel, anexos contados pela fórmula de cada provedor |
| `contexto.corte` | conversa, janela, reserva, turnos a manter | histórico que cabe, com a decisão por turno e a marca do bloco removido |
| `contexto.higiene` | conversa | órfão removido, resultado injetado, abertura de usuário e o histórico saneado |
| `contexto.resumo` | trecho, limite em tokens, limiar de stub | índice de retenção com decisão, número, caminho, pendência e ferramentas |
| `contexto.uso` | entrada, saída, total, cache, preços, hops | contexto ancorado, custo da chamada e custo repetido em continuação |
| `contexto.regras` | nada | dialetos, fórmulas, precedência, turnos, escalada de stub, marcadores e limites |

Todas aceitam `modo` com `lite`, `full` (padrão) ou `ultra`. `lite` devolve só o que bloqueia, `full` inclui as correções e `ultra` inclui as perguntas que faltam para decidir.

A conversa entra em dois formatos: **linhas** `papel: conteúdo` — com `assistant(tools): c1=buscar_web` para chamada e `tool(c1): resultado` para o retorno — ou **JSON** com `role`, `content`, `tool_calls` e `tool_call_id`. Linhas que não começam por papel continuam a mensagem anterior.

## 1. O orçamento

A reserva de saída não é sugestão: ela sai da janela antes de o histórico entrar. A precedência é a do upstream, com uma diferença deliberada — o teto do modelo só é reservado no dialeto Anthropic, cujo endpoint exige `max_tokens`.

| Ordem | Origem da reserva | Quando vale |
|---|---|---|
| 1 | **Reserva da chamada** | sempre que informada |
| 2 | **Limite do assistente** | quando habilitado e maior que zero |
| 3 | **Teto do modelo** | só no dialeto `anthropic` |
| 4 | **Sem reserva** | nada é descontado da janela |

A **sala de entrada** é `janela − reserva`, com piso de **20% da janela**: um `max_tokens` igual à janela não zera o prompt, apenas o comprime até o piso. A **margem** desconta mais 0% a 20% da sala, e a **pressão** é o prompt medido contra o disponível.

| Achado | Peso | Quando |
|---|---|---|
| `max-saida-maior-que-janela` | must | o teto do modelo é maior ou igual à janela |
| `prompt-acima-da-sala` | must | o prompt medido não cabe no disponível |
| `reserva-acima-da-metade` | should | a reserva passa de 50% da janela |
| `compactar-agora` | should | o prompt passa de 80% da sala |
| `janela-baixa` | should | janela abaixo de 4.096 tokens |
| `sem-teto-declarado` | nice | dialeto Anthropic sem reserva |
| `teto-ignorado` | nice | teto declarado e não reservado fora do Anthropic |
| `margem-grande` | nice | margem acima de 10% |

## 2. A estimativa

Não há BPE. A estimativa é lexical e declarada: **1 token por caractere CJK**, **1 a cada 4 caracteres latinos** e **1 a cada 3 dentro de bloco cercado** por crase tripla, com teto de um token por caractere. É a mesma ordem de grandeza do contador de caracteres do upstream, sem baixar as 2,2 MB de ranks do tokenizador real.

Imagem e mídia não entram por caractere: entram pela fórmula documentada de cada dialeto, quando a dimensão ou a duração aparece no texto — `[imagem 1024x768]`, `[áudio 90s]`, `[vídeo 2min]`, `[documento 12000]`.

| Dialeto | Imagem | Sem dimensão |
|---|---|---|
| Anthropic | `ceil(largura × altura / 750)`, com borda de 1.568 px e 1,15 MP | 1.590 |
| OpenAI | `85 + 170 × ladrilhos` de 512 px, após caber em 2048² e reduzir o menor lado a 768 px | 765 |
| Google | 258 se os dois lados têm até 384 px; senão 258 × recortes de `floor(min/1,5)` | 258 |
| Ollama | constante | 1.000 |

Áudio e vídeo são cobrados **por segundo**, nunca pelo base64: Gemini a 32 e 258 tokens/s, OpenAI a 32 e 170 tokens/s, Anthropic e Ollama na mesma forma. Sem duração, a conta usa 60 s de áudio ou 40 s de vídeo — piso, não adivinhação.

| Achado | Peso | Quando |
|---|---|---|
| `anexo-em-base64` | must | há `data:…;base64,` ou blob de 2.000 caracteres no texto |
| `imagem-sem-dimensao` | should | o marcador não traz largura e altura |
| `midia-sem-duracao` | should | áudio ou vídeo sem duração |
| `mensagem-gigante` | should | uma mensagem acima de 20 mil tokens |
| `sem-system` | nice | nenhuma mensagem de sistema |

## 3. O corte

O corte trabalha em **turnos**, não em mensagens. Um turno é uma mensagem de usuário, uma de sistema ou um assistente simples; um assistente com chamadas forma um turno atômico com **todos** os resultados que vêm depois. Partir esse bloco deixaria um `tool` sem a chamada — e o provedor recusa o histórico inteiro por isso.

1. Mensagens de sistema ficam, sempre.
2. Os últimos `manter_ultimas` turnos ficam.
3. Enquanto o total passar da sala, o turno mais antigo entre os mantidos sai — nunca o último.
4. O primeiro bloco removido vira a marca `[N mensagem(ns) omitida(s) — resuma com contexto.resumo]`.
5. Um `limite_mensagens`, quando informado, corta antes por contagem e arrasta a chamada de volta se o recorte começar num resultado.

| Achado | Peso | Quando |
|---|---|---|
| `ultimo-turno-nao-cabe` | must | sistema + último turno já passam da sala |
| `orfa-no-corte` | must | sobrou resultado de ferramenta sem a chamada |
| `corte-profundo` | should | o corte removeu mais de 60% dos tokens |
| `limite-mensagens-cortou` | should | o limite por contagem removeu o começo |
| `primeiro-nao-usuario` | should | o histórico servido não abre com usuário |
| `sem-resumo` | nice | o bloco saiu sem resumo do que ficou |
| `nada-a-cortar` | nice | já cabia |

## 4. A higiene

O histórico precisa satisfazer três invariantes para ser aceito pela maioria dos provedores — as mesmas que o upstream aplica em silêncio:

1. **Resultado órfão** — mensagem `tool` cujo `tool_call_id` não aparece em nenhum `assistant` anterior é **removida**. Se a limpeza esvaziar tudo, entra `[Conversa continua]`.
2. **Resultado faltante** — chamada sem `tool` correspondente recebe um marcador `[Sem resultado da ferramenta]`, com o nome da ferramenta preservado.
3. **Abertura** — a primeira mensagem depois do sistema precisa ser do usuário; se não for, entra `[Conversa continua]`.

Além disso: `id-duplicado` (should), `tool-sem-id` e `mensagem-vazia` (nice), `chamada-com-texto` (nice) e `historico-valido` quando não há nada a corrigir. A saída mostra cada correção com alvo e efeito, e o histórico saneado vem em bloco separado para copiar.

## 5. O resumo

Compactar sem perder o essencial é escolher o que sobrevive. O resumo daqui não é prosa gerada por modelo: é um **índice de retenção**, extraído por padrão lexical e organizado por tipo.

| Tipo | Como é reconhecido |
|---|---|
| `decisão` | "decidimos", "ficou definido", "vamos usar", "escolhemos", "acordado" |
| `pendência` | "falta", "pendente", "próximo passo", "a fazer", "aguardando" |
| `número` | valor com unidade: `%`, `ms`, `s`, `min`, `h`, `dias`, `R$`, `US$`, `MB`, `GB`, `k`, `mil` |
| `caminho` | `scripts/etl.py`, `docs/x.md`, `app.tsx` |
| `ferramenta` | nome e quantidade de chamadas |

Antes de resumir, as saídas de ferramenta acima do limiar viram `[Ferramenta X devolveu N caracteres; omitida antes do resumo]` — a escalada do upstream, do mais generoso ao mais agressivo: **4.000 → 1.000 → 200 → 0** caracteres. Anexos viram `[imagem]`, `[áudio]`, `[vídeo]` ou `[documento]`.

O texto final entra no orçamento de `limite` tokens; o que não couber é contado e apontado (`itens-cortados`), porque resumo que estoura o próprio limite não serve para nada. Sem nenhum item reconhecido, `sem-retencao` é bloqueio: um resumo que só diz que houve conversa é pior do que cortar.

## 6. O uso

O contexto ancorado é a reconstrução do tamanho da conversa a partir do que o provedor reporta:

```text
contexto = total − entrada + inicial
custo    = entrada/1M × preço_entrada + saída/1M × preço_saída + cache/1M × preço_cache
hops     = hops × (contexto/1M × preço_entrada + saída/1M × preço_saída)
```

`inicial` é o `initialPromptTokenCount` do Gemini/Vertex: em continuação, ele representa o prompt da primeira dobra, não o total acumulado. Sem `total`, o contexto cai para a entrada da chamada e a pressão fica subestimada — por isso `sem-total` é correção.

| Achado | Peso | Quando |
|---|---|---|
| `total-menor-que-entrada` | must | o total informado não comporta a entrada |
| `cache-acima-da-entrada` | must | o cache reportado passa da entrada |
| `janela-ultrapassada` | must | a entrada passa da janela declarada |
| `sem-total` | should | não há total para ancorar |
| `saida-vazia` | should | nenhum token de saída |
| `hops-repetem-prompt` | nice | mais de um hop recobra o contexto |
| `sem-preco` | nice | preços zerados |

## Exemplo

Uma conversa de oito mensagens, com uma imagem de 1024×768 e um par de ferramenta, contra uma janela de 128.000 e reserva de 8.192:

- `contexto.tokens` → **853 tokens**, dos quais 765 são a imagem e 19 o resultado da ferramenta.
- `contexto.orcamento` → sala de **119.808**, prompt de **853**, sobra de **118.955**, pressão de **0,7%** da sala.
- `contexto.uso` com entrada 12.000, saída 800, total 12.800, cache 4.000 e preços 2,50 / 10,00 / 0,25 → contexto de **12.800**, custo de **US$ 0,039** e **US$ 0,08** em dois hops.

Já um corte com janela de 4.000 e reserva de 2.000 numa conversa de 21 mensagens mantém 12 e remove 10, saindo de **386** para **196** tokens; com 61 mensagens e sala de 500, remove 45 por orçamento e aponta `corte-profundo` e `sem-resumo`.

## O que ficou de fora

Não há tokenizador BPE — a estimativa é lexical e erra de 10% a 20% em texto comum. Nenhum modelo é chamado para resumir, nenhuma conversa sai da máquina e nenhum provedor é consultado: janela, preço e `usage` são os que você informa. Compactação automática em segundo plano, cache de prompt, contagem remota de tokens e cobrança real ficam fora — a fonte da verdade é a fatura do provedor.

## Atribuição

Obra original: [`CherryHQ/cherry-studio`](https://github.com/CherryHQ/cherry-studio), licença **GNU AGPL-3.0**. O aviso completo está em [`docs/licenses/cherryhq-cherry-studio.txt`](licenses/cherryhq-cherry-studio.txt): nenhum código, prompt ou arquivo do upstream foi copiado, e `server/contexto.py` é implementação independente.

## Contrato

Toda resposta traz `executed: false`, `readOnly: true` e o `mode` herdado do `review`; o `analysis` é prefixado com `contexto.` e cada `limitations` declara o que a conta não cobre. Nenhuma skill abre arquivo, chama a rede, executa comando ou consulta modelo — inclusive a de regras, que devolve o catálogo estático.
