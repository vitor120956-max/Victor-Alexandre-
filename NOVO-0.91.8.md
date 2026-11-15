# JARVIS 0.91.8 — o script agora diz onde pegar a chave

Você parou no `Provedor [OpenRouter]:` e perguntou "como pego essas coisas?".
Essa pergunta é a prova de que o script estava errado: ele pedia o dado sem
dizer onde encontrá-lo. O endereço já existia no catálogo (`server/provedores.py`,
campo `onde`) — só não era mostrado.

## O que aparece agora

Antes do primeiro prompt:

```
  Provedor: OpenRouter
  Onde pegar a chave:  openrouter.ai/keys
  1. abra esse endereço no navegador e entre (no OpenRouter dá para entrar com o Google)
  2. crie uma chave nova e COPIE pelo botão de copiar (não selecione o texto com o mouse)
  3. volte para esta janela e cole com o BOTÃO DIREITO do mouse
     (no console antigo do Windows o Ctrl+V não cola: ele escreve um símbolo)
  Modelo grátis: 20 pedidos/min e 50/dia nos modelos :free …
  Sugestão de modelo: deepseek/deepseek-chat-v3-0324:free
```

E o endereço aparece **de novo** na hora de digitar a chave, porque nesse ponto
a tela já rolou.

## O que responder em cada prompt

| pergunta | o que fazer |
|---|---|
| `Provedor [OpenRouter]:` | **Enter** — mantém OpenRouter |
| `Base da API [https://openrouter.ai/api/v1]:` | **Enter** |
| `Modelo [deepseek/...:free]:` | **Enter** — mantém o que já está |
| `Chave(s)…` | cole a chave com o **botão direito do mouse** |

Enter mantém o valor entre colchetes. Você só precisa de uma coisa nova: a
chave.

## Por que o modelo pode ficar como está

Se o `conferir-ia.py` depois disser que esse nome não existe mais na sua conta,
ele mesmo mostra os nomes que existem. Não vale a pena adivinhar agora.

## Testes

Três novos: o guia do OpenRouter aponta `openrouter.ai/keys` e a nota do
`:free`; a mensagem avisa que Ctrl+V não cola no console antigo; e provedor
fora do catálogo não quebra o guia (só não mostra endereço).
