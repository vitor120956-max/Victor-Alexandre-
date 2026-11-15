# JARVIS 0.91.7 — a chave não é uma chave (era o Ctrl+V)

O `conferir-ia.py` respondeu na primeira linha, e a resposta não era sobre modelo:

```
provedor:  openrouter
modelo:    deepseek/deepseek-chat-v3-0324:free
chaves:    1 configurada(s) ['\x16…\x16']
```

Aquela chave tem **4 caracteres**. Uma chave do OpenRouter começa com
`sk-or-v1-` e tem cerca de 73. O que está gravado ali não é uma chave — e por
isso o provedor responde **400**, que parece problema de modelo e não é.

## O que era o `\x16`

`\x16` é o código de controle do **Ctrl+V**. No console do Windows 10 (o seu é
o 10.0.14393), **Ctrl+V não cola** — ele escreve esse caractere invisível. A
chave então foi gravada com lixo no começo e no fim, e a parte útil se perdeu.

Isso não é culpa sua: é um console de 2016 fazendo o que ele sabe fazer. Mas o
JARVIS podia ter avisado em vez de culpar o modelo.

## O que mudou

**1. A limpeza acontece na leitura.** Caracteres de controle saem da chave
quando ela é lida. Se o arquivo tiver a chave certa com lixo em volta, ela volta
a funcionar **sem você editar nada**. Quebra de linha é preservada — tirar o
`\n` colaria duas chaves e a extração pegaria uma a mais (foi um bug meu,
achado pelo teste que compara as duas cópias da regra).

**2. Chave inválida agora tem nome.** Se o que está gravado não tem cara de
chave de nenhum provedor conhecido, a tela diz isso antes de qualquer chamada
de rede:

```
ATENÇÃO: a chave 1 tinha caractere de controle (é o Ctrl+V…) e tem 4 caractere(s).
Isso é a causa, e não é o modelo: a chave gravada não é uma chave.
```

**3. O `configurar-chave.py` limpa antes de gravar** — e avisa quando removeu
algo, para você saber que a colagem veio torta.

## Como recolar (o jeito que funciona)

No console do Windows 10 antigo, **não use Ctrl+V**. Use o **botão direito do
mouse**: ele cola o conteúdo da área de transferência. Ou copie e cole pela
tela do JARVIS (Configurações → Chaves de IA), onde o Ctrl+V funciona normal.

Depois de recolar, o `conferir-ia.py` deve mostrar a chave começando com
`sk-or-v1…` e terminando com um número de caracteres perto de 73.

## Testes

Seis novos: controle sai da chave; chave boa não gera aviso; chave sem formato
gera aviso com o que fazer; o `estado()` do `.env` com lixo avisa; `.env` limpo
não avisa; e a limpeza não junta linhas.

## O que continua sem prova

Ainda não sei se, **depois de recolar**, o modelo `deepseek/deepseek-chat-v3-0324:free`
existe na sua conta do OpenRouter. O `conferir-ia.py` responde isso na segunda
metade — e agora ele vai conseguir perguntar, porque a chave vai ser uma chave.
