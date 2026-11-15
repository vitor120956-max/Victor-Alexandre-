# JARVIS 0.91.11 — o duplo clique

“Não entendi, só atualizei.” — a culpa foi minha: eu deixei o caminho pronto mas
escondido atrás de um comando de duas linhas. Se precisa decorar comando, não
está pronto.

## Agora é um arquivo

Na pasta do JARVIS existe um novo:

```
pegar-chave.bat
```

Duplo clique nele. O que acontece:

1. ele abre `openrouter.ai/keys` no seu navegador;
2. mostra na tela os quatro cliques do site — Create Key, dar um nome, Create,
   **COPIAR** — e espera você;
3. você aperta Enter;
4. ele lê a área de transferência e grava no `.env`;
5. mostra a chave mascarada, com o tamanho, para você ver que veio inteira.

Se você apertar Enter antes de copiar, ele não fecha: pergunta se quer tentar de
novo. É o caso mais comum — copiar depois de já ter apertado.

## Duas coisas que iam atrapalhar

**A gravação fazia perguntas.** Trocar a chave chamava o questionário da primeira
configuração: provedor, base, modelo. Como o seu `.env` já está montado, eram
três perguntas com a resposta na frente. Agora, se o provedor já está gravado,
ele troca **só** a chave e diz o que manteve. Só pergunta tudo na primeira vez,
quando não há o que manter.

**A área de transferência vazia só dizia “não deu”.** Agora diz o que fazer:
copiar no site pelo botão e rodar de novo.

## O que foi provado

- O `.bat` é ASCII puro com CRLF (o console antigo e o Bloco de Notas), e todo
  `goto` tem seu rótulo — sem isso ele fecha sozinho no meio.
- A gravação sem perguntas, com um `.env` de verdade em pasta temporária: a
  chave entrou, o comentário do dono ficou, o modelo ficou, e o arquivo saiu em
  CRLF. Um teste separado confirma que, **sem** provedor gravado, ele ainda
  pergunta — primeira configuração continua sendo primeira configuração.
- Os cinco passos do `--criar` continuam cobertos com Windows falso.

## O que não foi provado

O duplo clique no seu Windows. O que dá para garantir é o que ele chama: os
mesmos comandos que já estavam testados. Se algo falhar, a janela não fecha —
fica aberta com a mensagem, que é justamente para você poder me contar o que
apareceu.
