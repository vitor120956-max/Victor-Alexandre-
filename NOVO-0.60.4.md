# JARVIS 0.60.4 — o token que não era token

Dois erros apareceram na tela no primeiro teste real do celular. Nenhum dos dois
era "o adb falhou": os dois eram o programa tratando **texto comum** como se
fosse token. Esta versão fecha os dois.

## O que você viu

1. `A skill "Baixar adb e scrcpy" recusou o pedido: comparing strings with non-ASCII characters is not supported`
2. Depois do `sim, pode`: `Token de host inválido. Confira em storage/host-token.txt.`

## Por que aconteceu

**Erro 1 — acento derrubava a comparação.** O token é comparado com
`hmac.compare_digest`, que **levanta `TypeError`** se qualquer lado tiver
caractere fora de ASCII:

```python
>>> hmac.compare_digest("abc", "não")
TypeError: comparing strings with non-ASCII characters is not supported
```

O `TypeError` não estava previsto em lugar nenhum, então ele subiu cru até a
interface, traduzido do inglês do fornecedor. A mensagem não dizia o que fazer —
pior, parecia defeito de biblioteca.

**Erro 2 — o chat mandou "sim, pode" no lugar do token.** Quando você confirma
uma skill, a interface reenvia o pedido junto com `confirmar: true`. Nesse reenvio
ela colocava **o texto que você digitou** (`sim, pode`) no campo `autorizacao`.
Numa skill que toca a máquina, esse campo é o token: o servidor comparava
`"sim, pode"` com o token de verdade, não batia, e respondia "token inválido" —
mesmo com a instalação correta.

O agente local tinha um segundo caminho para o mesmo defeito: ele pescava
qualquer campo de texto do formulário na frase do usuário. Se a skill tinha um
campo `autorizacao`, a frase inteira caía ali.

## O que mudou

**Um lugar só compara token — `server/tokens.py`.**

- `iguais()` converte para bytes antes de comparar. Bytes nunca dão `TypeError`, e
  a comparação continua em tempo constante (que é o motivo de existir
  `compare_digest`). Ainda por cima, um `except` devolve `False` em vez de
  derrubar a requisição.
- `explicar()` diz **por que** recusou, em português:
  - vazio e sem modo dono → "rode `ligar-celular.bat` (ou ponha
    `JARVIS_HOST_CONFIAR_LOCAL=1` no `.env`) e reinicie a API";
  - com acento → "isso não é um token: o valor tem acento ou símbolo";
  - curtíssimo ou com espaço → "não parece um token de host";
  - formato certo mas conteúdo errado → "token inválido, confira
    `storage/host-token.txt`".
- `server/sistema.py`, `server/elevacao.py` e `server/evolucao.py` passaram a usar
  o módulo. Não sobrou nenhum `compare_digest` solto com `str`.

**A confirmação manda token, não conversa.** `src/lib/confirmacao.ts` decide o
valor: no modo dono vai vazio (o servidor preenche na própria máquina); fora dele
vai o token da tela. O `sendMessage` usa essa função.

**Modo dono conserta token torto na própria máquina.** Se
`JARVIS_HOST_CONFIAR_LOCAL=1` e a requisição vem de `127.0.0.1`, um valor
inválido é trocado pelo token de verdade em vez de virar erro. Pedido vindo de
outra máquina da rede continua exigindo o token digitado, e token válido
continua sendo respeitado como veio.

**O agente não pesca mais segredo na frase.** `autorizacao`, `token` e `senha`
saíram da extração por texto livre e do `campo=valor`. O `confirmacao` (código
curto do plano) ficou de propósito: não é segredo e colar à mão é caminho válido.

## O que você faz agora

```bat
cd /d D:\JARVIS
```

Depois, uma vez só:

```bat
ligar-celular.bat
```

Ele liga `JARVIS_HOST_CONFIAR_LOCAL=1`. Feche a janela da API, suba de novo:

```bat
cd /d D:\JARVIS
.venv\Scripts\python iniciar.py
```

O banner deve mostrar `dono=LIGADO (sem digitar token nesta máquina)`. A partir
daí a interface não pede token para operar o próprio PC, e o "sim, pode" executa
a skill.

## Testes

- `pytest server/tests` → **2.673 passed**.
- `test_celular.py` → **54**: token com acento vira explicação, token vazio
  explica o modo dono, agente não tira token da frase, `atualizar.bat` avisa
  antes de copiar e nenhum atalho manda digitar `Ctrl+C`.
- `test_modo_dono.py` → **28** (3 novos + 1 reescrito: token certo é respeitado,
  token torto é corrigido na própria máquina, e **não** é corrigido vindo de
  outra máquina).
- `vitest` → **120** (3 novos em `confirmacao.test.ts`).
- `tsc -b` limpo, `npm run build:embutido` ok.

## Limite que continua valendo

Nada aqui liga a Depuração USB do celular sozinha. O Android exige o toque em
"Permitir depuração USB?" na tela do aparelho. O que o JARVIS faz é baixar `adb`
e `scrcpy` com hash, medir o estado, espelhar quando a depuração já estiver
ligada e guiar o resto — inclusive o caminho `scrcpy --otg`, que funciona **sem**
depuração para teclado e mouse.
