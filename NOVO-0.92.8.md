# 0.92.8 — “root temporário sem reiniciar, sem apagar e sem quebrar?”

> e n tem como fazer um root temporario sem precisar reiniciar ou apagar ou
> quebrar nada?

**Essa pergunta é mais precisa que a anterior, e a resposta é: não — mas por um
motivo específico, e existe uma coisa que atende a quase tudo.**

A pergunta anterior era “dá para usar root temporário?”. Esta acrescenta **três
condições**. E elas não são do mesmo tipo:

| condição | o que significa | quem falha |
|---|---|---|
| **sem reiniciar** | sem reiniciar o **aparelho** | ninguém dos três — `adb root` e `su` não reiniciam o aparelho |
| **sem apagar** | sem destravar o bootloader | Magisk e `su` falham: o destravar já apagou |
| **sem quebrar** | sem mexer no `verified boot` | Magisk falha de propósito; `su` falha por tabela |

## A tabela, caminho por caminho

| caminho | dura | sem reiniciar | sem apagar | sem quebrar | **neste aparelho** |
|---|---|---|---|---|---|
| **`adb root`** | até reiniciar | **sim** | **sim** | **sim** | **não** |
| sessão de `su` | N minutos | sim | não | não | não |
| Magisk “sem persistência” | até desinstalar | sim | não | não | não |

**Um** caminho atende às três: o **`adb root`**. Ele reinicia o *daemon do adb*,
não o aparelho; não escreve em partição nenhuma; não toca no `verified boot`; e
some no próximo reinício. É o “root temporário” de verdade, e ele **não quebra
nada**.

O problema é um só: **o `adbd` do seu aparelho recusa**. O SM-A346MU é build
`user` com `ro.debuggable=0`, e a resposta é:

> `adbd cannot run as root in production builds`

Não é o JARVIS dizendo não — é o Samsung travando o `adbd` na fábrica. E sem ele,
os outros dois caminhos só existem **depois** de destravar o bootloader, que é
exatamente o que você não quer: apaga tudo e deixa o `verified boot` em `orange`,
derrubando OTA, banco, carteira e DRM.

## Mas tem uma coisa que atende a “sem quebrar nada”

E é o que o JARVIS **já usa hoje**: o **privilégio de shell do ADB**.

Não é root. Roda como o usuário `shell`, e não como superusuário. Mas é muito mais
que um app comum, e **não apaga, não quebra, não mexe no bootloader**:

**Alcança:**
- ler tudo o que o Android publica (a varredura inteira)
- instalar e remover app do usuário, com confirmação
- conceder e revogar permissão (`pm grant` / `pm revoke`)
- mudar ajustes globais (`settings put`) — inclusive os de animação
- congelar app (`pm disable-user`)
- espelhar a tela e mandar toque/tecla (`scrcpy`)
- copiar as pastas de mídia (`adb pull`)

**Não alcança:**
- `/data/data` — as conversas e os dados de cada app
- `/data/system` — senhas, contas, ajustes protegidos
- partição de boot, recovery e modem
- memória de outro app em execução
- módulo de sistema (Xposed, Magisk, framework)

Essa é a linha que separa **“quase root”** de **root**. E ela é grande: os dados
de app e as senhas ficam do outro lado.

*(O app Shizuku faz exatamente isto: sobe um serviço com a identidade `shell` via
ADB e empresta o privilégio a outros apps. O próprio projeto diz: “ADB privileges
are not full root”.)*

## O que mudou no código

O bloco **“Podemos usar root temporário?”** na aba Anatomia ganhou três coisas:

1. **Uma linha por condição** na tabela — em vez de um “sim/não” que esconde qual
   das três falhou.
2. **A resposta literal** à pergunta, medida no aparelho: começa com “Não.” no seu
   caso, e explica qual caminho atenderia e por que ele não vale aqui.
3. **O que dá para fazer agora sem root**, com as duas colunas — alcança e não
   alcança. Uma lista de “dá para fazer X” sem a de “não dá” é mentira por
   omissão.

E um caso que a regra pegou: **um aparelho que já tem root não responde “Sim”**.
O `root_temporario` dele pode estar `True` por `ro.debuggable`, mas o custo já foi
pago no passado — e dizer “sim” esconderia a conta atrás do resultado.

## Medido

- **pytest 4 275** (0 falhas, 7 pulados) — **6 casos novos**.
- `test_varredura.py` agora tem **48 casos**.
- `vitest` 243, `tsc` limpo, build OK, manifesto **671** arquivos em 0.92.8.
- No aparelho do dono: `atende_as_tres = false`, tabela com `adb root` em “não”
  na coluna “neste aparelho”, e a lista de privilégio de shell com
  `/data/data` e `/data/system` explicitamente fora.

## Resposta curta, para você

**Não.** Neste aparelho não existe root sem reiniciar, sem apagar e sem quebrar —
porque o único caminho que atende às três é o `adb root`, e o `adbd` da Samsung
recusa. O que existe é o **privilégio de shell do ADB**, que o JARVIS já usa:
não apaga, não quebra, não reinicia — e não alcança as conversas nem as senhas de
app, porque isso é root de verdade.

Se um dia você tiver um aparelho `userdebug` (Pixel de desenvolvedor), o cartão
vai dizer **“sim — adb root atende às três”**, e aí a resposta muda de verdade.
