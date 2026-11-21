# 0.92.7 — “podemos usar root temporário?”

> podemos usar root temporario

Antes de responder “sim” ou “não”, três coisas com o mesmo nome precisam ser
separadas — porque só **uma** delas é temporária de verdade.

## Os três “root temporário”

| # | o que é | dura quanto | exige destravar? | apaga o aparelho? |
|---|---|---|---|---|
| **1** | **`adb root`** — reinicia o `adbd` como root | até reiniciar | **não** | **não** |
| 2 | Magisk “sem persistência” | até desinstalar o Magisk | **sim** | **sim** |
| 3 | `su` emprestado por N minutos a um app | N minutos para o app | **sim** (root já instalado) | **sim** (foi apagado antes) |

**O item 1 é o único “temporário” pela porta da frente**: não toca no bootloader,
não apaga nada, e o aparelho volta ao normal no próximo reinício. **Ele depende de
uma coisa só: o `adbd` deste aparelho aceitar rodar como root.**

**No seu aparelho, ele não aceita.** O SM-A346MU é build `user` com
`ro.debuggable=0` — o `adb root` responde, literalmente:

> `adbd cannot run as root in production builds`

Não é o JARVIS se recusando: é o **próprio aparelho** se recusando. Samsung travou
o `adbd` na fábrica. E sem `adb root`, o único root que sobra é o **instalado**
(Magisk), que exige **destravar o bootloader** — e destravar, na Samsung,
**apaga o aparelho inteiro** e quebra OTA, banco, carteira e DRM de vídeo.

**Resposta curta:** *neste* aparelho, não existe root temporário. O temporário que
existe em outros aparelhos (Pixel com `userdebug`, por exemplo) seria reversível —
mas o JARVIS continua não rodando `adb root`, porque root é a linha que o projeto
não cruza em **nenhuma** forma. A diferença é o passivo: num aparelho `userdebug`
seria reversível; no seu, seria apagar tudo.

## O que a sua pergunta consertou no código

O mapa de degraus tinha três defeitos, e a pergunta os expôs todos:

### 1. O degrau 2 estava errado

O mapa dizia que o degrau 2 (“ADB sem cabo”) era decidido por
`ro.debuggable == "1"` — que é **build de fábrica/teste**, não rede. O certo é a
porta do `adbd` (`service.adb.tcp.port`), que é o que `adb tcpip 5555` abre.
**Corrigido.** Um teste antigo cobrava a heurística errada e foi reescrito com o
motivo no comentário.

### 2. O estado do bootloader chegava vazio

A rota montava as propriedades pelos **rótulos da tela** e nunca lia
`ro.boot.verifiedbootstate`. Resultado: o cartão dizia “não destravado” em
**todo** aparelho, inclusive num com root. **Corrigido:** a anatomia agora devolve
`relatorio["propriedades"]` cru, e o mapa lê `verifiedbootstate` + `flash.locked`
(com fallback quando a propriedade não existe).

### 3. O `verifiedbootstate` nem era lido

Faltava na lista de `PROPS`. Junto com ele entraram `ro.boot.flash.locked` e
`service.adb.tcp.port` — as três propriedades que decidem degrau de verdade.

E um bônus: o handler da skill `celular.controle` usava `anatomia_mod` sem
importar. **Era um `NameError` esperando acontecer** — nunca disparou porque o
caminho não tinha sido exercitado com aparelho conectado. Agora está importado e
o handler usa a leitura crua.

## O que você vê na tela agora

Na aba **Anatomia**, abaixo dos cinco degraus, nasceu o bloco
**“Podemos usar root temporário?”** com três linhas: situação neste aparelho,
se precisa destravar o bootloader, e se apaga o aparelho. Elas vêm do `getprop`
do seu celular — não de uma tabela fixa.

## Medido

- **pytest 4 269** (0 falhas, 7 pulados) — **8 casos novos**, um deles reescrevendo
  o teste que cobrava a heurística errada do degrau 2.
- `vitest` 243, `tsc` limpo, build OK, manifesto **670** arquivos em 0.92.7.
- API real (8017, `adb` imitando o SM-A346MU): `/api/anatomia/android/controle` →
  **200**, degrau 1, e `root_temporario.qual = "nenhum sem destravar o
  bootloader"`, `apaga_o_aparelho = true`.
- `verified_boot` saiu **vazio** nesse teste — e isso é o certo: o `adb` de teste
  não devolve a propriedade, e o código não inventa. “Sem medida” não vira “green”.

## Se você quiser mesmo root neste aparelho

Dá para fazer — e o custo é este, sem enfeite:

1. **Destravar o bootloader** apaga o aparelho inteiro (contas, fotos, WhatsApp).
2. Instalar Magisk (`OdIn`/`Heimdall`, patch do `boot.img`).
3. **Sem OTA**: você atualiza na mão, a cada patch de segurança.
4. **Banco e carteira**: muitos recusam aparelho com root; o Google Pay quase
   sempre.
5. **DRM de vídeo**: Netflix em HD cai para SD.

O JARVIS não faz os passos 1 e 2, e continua sendo só leitura no degrau 1. Se
você fizer por conta própria, o JARVIS **vai detectar** (`test-keys`, `su` no
PATH) e o cartão passa a dizer “este aparelho já está com root” — mas ele não vai
usar esse root.

## O que eu preciso de você

Não precisa fazer nada. Rode o **`atualizar.bat`** se quiser ver o bloco novo na
tela. Se um dia você tiver um aparelho `userdebug` (Pixel de desenvolvedor, por
exemplo), o cartão vai dizer que o `adb root` **seria** possível ali — e a
resposta continua sendo a mesma, com o motivo escrito.
