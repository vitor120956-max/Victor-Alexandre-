# JARVIS 0.91.35 — o teste disse “OK” para um modelo que não fala

Seu console, logo depois de atualizar:

    TESTE DE VERDADE (8 tokens por chave)...
    OK   chave 1: HTTP 200
         motivo: respondeu com raciocínio em vez de texto
         o provedor disse: “o modelo pode gastar o limite pensando e não sobrar resposta”

    Pronto: provedor, modelo e chave estão coerentes.

Três linhas que se contradizem. A chave está boa — isso o teste acertou. Quem
não fala é o **modelo**: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`
gasta os 8 tokens pensando e devolve a resposta vazia. O teste viu “HTTP 200” e
deu OK, e a última linha comemorou.

E o comando que eu mandei rodar em caso de falha também não consertava: o
`--corrigir` só agia quando o nome do modelo **não existia na lista**. Como o
seu existe, ele não perguntava nada ao modelo e respondia “estão coerentes”.

## O que muda

- **200 sem texto reprova.** Só conta como “respondeu” quando veio texto. O
  modelo de socorro também precisa falar — antes um 200 mudo dele “provava” que
  a chave estava boa.
- **O resumo diz qual dos dois é o problema**: “a chave está válida: o modelo
  respondeu HTTP 200 e não mandou texto…”, com o comando do conserto.
- **`--corrigir` agora testa o modelo que está na lista** — se ele não fala,
  escolhe outro. E vai até **6 candidatos**, não 3 (os seus 3 primeiros eram
  dois `gemma` ocupados e o `nemotron` mudo, e o script parava ali).
- **Ele diz o que houve com cada candidato**: “respondeu, mas sem texto
  (gastou o limite pensando) — pulando” é diferente de “não (HTTP 429)”.
- **Avisa que a API aberta continua com o modelo antigo** até fechar no X e
  rodar o `iniciar-jarvis.bat` de novo.

## Como consertar, na sua máquina

Primeiro pegue a versão:

```bat
cd /d D:\JARVIS
```

```bat
atualizar.bat
```

Depois, com a janela da API **fechada** (no X):

```bat
.venv\Scripts\python conferir-ia.py --corrigir
```

Ele testa o modelo que você tem, vê que ele não fala, e testa os seguintes —
gravando **só** o primeiro que responder com texto. O `.env` ganha uma cópia
antes. Se nenhum falar, nada é gravado e ele diz isso.

No fim, suba o JARVIS de novo:

```bat
iniciar-jarvis.bat
```

E, na conversa, peça a prova:

```text
testar ia
```

## Testado

9 testes novos em `server/tests/test_ia_muda.py`, todos reproduzindo o seu
console: 200 mudo não aprova (nem pelo socorro), o resumo separa chave de
modelo, o `--testar` não diz “coerentes”, o `--corrigir` sozinho testa o modelo
que está na lista, pula o mudo, segue além dos três primeiros, e não grava nada
quando ninguém fala.

Rodei os 9 contra a 0.91.34: **7 falham**. Contra a 0.91.35: 9 passam.

Suíte: **3.893 testes de API** (7 pulados) e **153 testes web**.
