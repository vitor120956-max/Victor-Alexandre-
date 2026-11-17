# JARVIS 0.91.32 — por que o `--corrigir` não existia (e o que fazer)

O erro que você viu:

    conferir-ia.py: error: unrecognized arguments: --corrigi

não é um problema no seu PC nem no comando. É isto: **a sua cópia é a 0.91.29**,
publicada **antes** de o `--corrigir` existir (ele entrou na 0.91.31). O
`atualizar.bat` que você rodou pegou a versão mais nova **daquele momento** — as
0.91.30 e 0.91.31 foram publicadas depois.

Confirma no seu console: `Versão nova: 0.91.29 (a sua é 0.91.28)`.

## O que fazer, nesta ordem

```bat
cd /d D:\JARVIS
```

```bat
atualizar.bat
```

Agora ele vai dizer algo assim:

    Versão nova: 0.91.32 (a sua é 0.91.29), publicada em 17/11 09:12 UTC.
    3x arquivo(s), XXX KB — em vez do zip inteiro.

Repare na **data** — ela passou a aparecer nesta versão, justamente para você não
ficar sem saber se já pegou o que há de mais novo.

Depois:

```bat
.venv\Scripts\python conferir-ia.py --corrigir
```

Isso vai escolher um modelo que exista na sua conta, **testar com 8 tokens de
verdade** e gravar no `.env` (só a linha do modelo, com cópia do `.env` antes).
Pela sua lista, deve cair em `meta-llama/llama-3.3-70b-instruct:free`.

## O que consertei para isso não se repetir

1. **O aviso de atualização mostra a data.** Antes: `Versão nova: 0.91.29 (a sua
   é 0.91.28)`. Número sozinho não diz se a resposta é de hoje. Agora:
   `… publicada em 17/11 09:12 UTC`. E, quando você já está na última, ele diz
   “Já está na última versão publicada: 0.91.32 (publicada em …)”.

2. **Opção desconhecida virou explicação.** Em vez de
   `unrecognized arguments`, o script agora responde:

       Esta cópia do JARVIS não conhece: --corrigir
       Ela é a 0.91.29 — a opção pode ser de uma versão mais nova.
       Rode o atualizar.bat (ele baixa só o que mudou) e tente de novo.

3. **O cabeçalho mostra a versão** — `JARVIS — conferir a IA (0.91.32)` —, para
   você saber com qual cópia está falando.

4. **E o `--corrigir` ficou mais completo:** ele também conserta o caso em que o
   nome do modelo **está** na lista do provedor mas **dá 404** (a lista demora a
   tirar o nome morto). A prova é o teste de 8 tokens, não a listagem.

## Testado

- o aviso diz a data; sem data no manifesto, a frase continua certa; data
  estragada não quebra nada;
- `--opcao-que-nao-existe` sai com a explicação e o `atualizar.bat`, sem
  `usage:`;
- o cabeçalho mostra a versão;
- modelo que está na lista mas dá 404 é trocado, testado e gravado.

Suíte: **3.871 testes**, 7 pulados.
