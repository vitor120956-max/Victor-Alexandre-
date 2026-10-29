# JARVIS 0.62.0 — o celular está na porta. O que falta é o toque, não o cabo.

A foto resolveu o mistério em duas linhas:

1. **a tela funciona** — está acesa, desenhando vídeo, com o vidro quebrado no canto;
2. **o Android mostra “Desbloqueie para acessar todos os recursos/dados”** — e essa
   frase é do próprio aparelho quando o MTP está ativo.

**Isso significa que a linha de dados está funcionando.** Não é cabo de carga, não
é conector morto, não é placa. O Windows e o Android estão conversando agora.

Também explica por que a vigia ficou muda: o Windows mostra um Android bloqueado
por MTP como **`Dispositivo MTP USB`** / **`Dispositivo portátil`**, com
`InstanceId` começando em `SWD\WPDBUSENUM\...` — **sem VID nenhum**. A sonda
procurava `VID_04E8` e nomes em inglês, e o Windows desta máquina fala português.
O celular estava lá o tempo todo, invisível para o JARVIS.

## O que mudou

- **`e_aparelho` reconhece WPD**: `InstanceId` começando com `SWD` é aparelho, é o
  barramento de dispositivos portáteis do Windows — é por ali que o MTP aparece.
- **Nomes em português**: “Dispositivo portátil”, “Telefone”, “Dispositivo MTP
  USB” agora contam como aparelho (antes só inglês).
- **A vigia** (`vigiar-usb.ps1`) também escuta `SWD`/WPD e, quando o que entra é
  MTP, diz o que isso significa:

  ```
  ENTROU  Dispositivo MTP USB [sem VID]
          E o celular por MTP: o Windows ja o ve, a linha de dados funciona.
          Se a tela pedir para desbloquear, desbloqueie: ai os arquivos abrem.
          A Depuracao USB (adb) e outro passo, separado deste.
  ```

- **Aviso de porta oscilando**: se um dispositivo entra 3 vezes na mesma sessão, a
  vigia para e avisa que o problema é a porta/cabo, não o aparelho testado. (O
  leitor de cartão entrou cinco vezes na sua sessão de 09:55 — isso é a porta, e
  enquanto ela oscila um aparelho novo pode nem ser enumerado.)
- **O diagnóstico do chat** mudou: quando o Windows vê o aparelho **sem VID**, a
  resposta não manda mais trocar cabo. Ela diz: *cabo, conector e porta estão
  bons; falta destravar e ligar a Depuração USB* — com os caminhos para quem não
  tem toque.

## O problema real: o toque morreu, a tela não

Toque fantasma (ghost touch) é o digitalizador quebrado agindo sozinho. A tela
continua desenhando porque são peças diferentes. Isso tem uma consequência boa:
**o mouse USB não passa pelo digitalizador** — ele entra pelo controlador USB do
aparelho, que está funcionando (o MTP provou isso).

## O caminho, em ordem

**1. Adaptador OTG + mouse USB** (o mais direto, R$ 15–30)

- plugue o adaptador OTG no celular e o mouse nele;
- aparece um **cursor** na tela; mova, clique e destrave o aparelho;
- com o cursor, vá em **Configurações → Sobre o telefone → Informações do
  software** e toque 7 vezes em **Número da versão**;
- volte, entre em **Opções do desenvolvedor** → ligue **Depuração USB**;
- plugue o cabo no PC e rode `status do celular`.

A partir daí o `scrcpy` espelha a tela numa janela do Windows, com mouse e
teclado do PC — e o toque fantasma deixa de importar, porque quem manda é o PC.

**2. Desbloqueio remoto da conta Samsung** (grátis, se o aparelho estiver logado)

Como o J7 está no Wi-Fi, o **Find My Mobile** da Samsung
(`findmymobile.samsung.com`) tem a opção **Desbloquear** em alguns aparelhos e
versões. Se aparecer, o aparelho destrava sem toque nenhum.

**3. `scrcpy --otg`** (sem depuração nenhuma)

O PC se passa por mouse e teclado USB. No Windows exige instalar um driver
(libusb/WinUSB) — mais chato que o mouse OTG, e o resultado é o mesmo: um cursor
controlado pelo PC.

**4. Toque na sorte, com o vidro**

Não recomendo: com toque fantasma você não sabe se o toque é seu ou do vidro, e
o risco é apagar algo ou travar a conta. O mouse elimina a variável.

## Depois de destravar

O resto já está pronto e testado:

- `status do celular` vai mostrar `autorizado`;
- `celular.espelhar` abre a tela do aparelho na janela do Windows;
- `celular.puxar` copia fotos e documentos (DCIM, WhatsApp, Download);
- e, com depuração ligada, o caminho do LineageOS/Nura (que exige desbloqueio
  OEM) deixa de ser teoria.

## Testes

- `pytest server/tests` → **2.795 passed**.
- Novos: `SWD\WPDBUSENUM` reconhecido como aparelho mesmo sem VID, nomes em
  português (`Dispositivo portátil`, `Telefone`), a sonda aceitando a classe
  `WPD`, o diagnóstico de MTP visível mandando destravar (em vez de trocar cabo),
  o plano com mouse OTG, e o aviso de oscilação da porta.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
