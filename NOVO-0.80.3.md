# JARVIS 0.80.3 — “HTTP 400” não é resposta. Agora ele diz o que houve

O print: você pediu *“veja e faça um filtro do q é importante”* e o JARVIS
respondeu:

> Não consegui concluir pela IA externa: **O provedor de IA respondeu com HTTP 400.**

Verdade e inútil. O Google usa **400** para três problemas completamente
diferentes, e o corpo da resposta diz qual. O JARVIS lia o número e jogava fora a
frase.

## As três caras do 400 do Google

| o que o Google escreve | o que o JARVIS dizia | o que passa a dizer |
|---|---|---|
| `API key not valid. Please pass a valid API key.` | HTTP 400 | **chave inválida ou expirada** — gere outra no painel (e o JARVIS já te diz qual painel) |
| `User location is not supported for the API use.` | HTTP 400 | **o provedor não atende a sua região** — troque para o Groq ou o OpenRouter |
| `...multiturn requests alternate between user and model` | HTTP 400 | **o histórico precisa alternar** — comece uma conversa nova |

A primeira é a armadilha: o Google responde **400**, e não 401, para chave
inválida. Quem lê “400” procura erro de formato e nunca encontra.

## A causa mais provável do seu caso: histórico

O terceiro item explica o seu print. Repare na sequência:

1. você: `abre o gmail` → o JARVIS responde com a **skill local** (“Gmail aberto em uma nova aba”) — e isso **não entra no histórico da conversa**;
2. você: `veja e faça um filtro do q é importante` → o JARVIS manda as duas falas **suas**, em sequência, para o modelo;
3. o Gemini recebe duas mensagens seguidas de “user” e recusa com 400.

A correção está no envio: **falas seguidas do mesmo lado são juntadas** antes de
irem para o provedor. Para o Groq e para o OpenRouter isso é indiferente — eles
aceitavam —, e para o Google resolve. (Uma conversa nova também resolve, mas não
é trabalho seu descobrir isso.)

## A segunda tentativa

Se o 400 não for de chave, região nem histórico, o JARVIS repete **uma vez** com
o corpo mínimo (`model` + `messages`, sem `temperature` e sem `max_tokens`).
Parâmetro extra é a causa mais comum, e perder a resposta por causa de uma
`temperature` seria burrice. Só uma vez: não vira laço.

## O botão Testar conta a mesma história

O `Testar` das chaves passou a traduzir os mesmos três casos. Se você colar uma
chave do Google e ela estiver revogada, a lista agora diz **“chave inválida ou
expirada — gere outra no painel”**, não “HTTP 400”.

## O que fazer agora, no seu PC

1. **Feche e abra o JARVIS** (`iniciar-jarvis.bat`) — ele se atualiza sozinho para a 0.80.3;
2. **Ctrl+F5** na tela, para não ficar com a interface velha;
3. mande a mesma pergunta outra vez: `veja e faça um filtro do que é importante`;
4. se voltar erro, agora ele **diz qual é** — e a frase termina com o que fazer.

## Uma coisa que o 400 não consertou

O filtro de e-mails depende do skill local `correio.filtrar`, que lê os e-mails
exportados em `storage/correio`. Sem arquivo exportado lá, a tarefa cai no
modelo — e o modelo **não tem acesso à sua caixa**. Para o filtro ser
determinístico (intimação 100, fatura 85, governo 75…), exporte a caixa (Takeout
ou “Baixar mensagem”) e ponha em `storage/correio`. Está em
[`docs/CORREIO.md`](docs/CORREIO.md).

## Números medidos

- pytest: **3.363 passed, 2 skipped, 0 failed** (24 testes novos)
- vitest: **134 passed**
- manifesto: **504 arquivos**
- skills: **315** (nenhuma nova)
