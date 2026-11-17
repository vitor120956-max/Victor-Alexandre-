# JARVIS 0.91.33 — funcionou, e eu já achei o próximo tropeço

Seu console terminou assim:

    testando google/gemma-4-31b-it:free … não (HTTP 429)
    testando google/gemma-4-26b-a4b-it:free … não (HTTP 429)
    testando nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free … respondeu.
    Gravei JARVIS_AI_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free

Isso é a correção funcionando: os dois primeiros estavam **ocupados** (429 é
limite de pedidos da conta gratuita, não defeito do modelo), e o terceiro
respondeu. A chave está boa e o modelo existe.

Só que esse terceiro tem `reasoning` no nome: ele **pensa antes de responder**,
e o pensamento gasta o mesmo limite de tokens da resposta. Com o JARVIS pedindo
800 tokens, é possível que o pensamento coma tudo, o texto venha **vazio**, e
você veja “O provedor retornou uma resposta vazia” — de novo longe da causa.

## O que muda (para não acontecer com você)

- **“Respondeu” agora exige texto.** HTTP 200 com resposta vazia é reprovado —
  o teste passa para o próximo candidato em vez de aprovar um modelo mudo.
- **Resposta cortada por pensamento é pedida de novo**, uma vez, com até 3×
  mais espaço (teto de 4.096 tokens), antes de desistir.
- **Se só veio o raciocínio**, é ele que aparece na tela — melhor que “resposta
  vazia”.
- **A escolha prefere modelos de conversa**; `reasoning`/`thinking` vêm depois
  dos de mesmo tamanho. E o `--corrigir` avisa quando o escolhido é de
  raciocínio.
- **429 agora é contado e explicado**: “ocupados; a conta gratuita tem limite de
  pedidos por minuto — não é defeito do modelo”.

## O que fazer agora

Teste o JARVIS de verdade:

```bat
cd /d D:\JARVIS
```

```bat
iniciar-jarvis.bat
```

Depois abra a tela e mande um “oi”. Duas coisas para observar:

1. **resposta em branco** → rode `.venv\Scripts\python conferir-ia.py --corrigir`
   (na 0.91.33 ele não aceita mais modelo mudo e prefere um de conversa);
2. **demora de 20 s ou mais** → é o modelo pensando. Se incomodar, o
   `--corrigir` agora tende a escolher um mais direto.

Para pegar a 0.91.33: `atualizar.bat` (vai dizer “publicada em …”, com a data).

## Testado

- HTTP 200 com `content` vazio é **reprovado** (antes era aprovado);
- resposta cortada por pensamento é repetida com mais espaço;
- sem texto e sem espaço, a resposta é o raciocínio;
- texto vazio de verdade continua sendo erro claro;
- modelo de raciocínio fica atrás de um de conversa — mas não atrás de um de
  tamanho desconhecido.

Suíte: **3.878 testes**, 7 pulados.
