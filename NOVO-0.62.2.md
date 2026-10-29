# JARVIS 0.62.2 — "Could not find any USB device" é driver, não cabo

Primeiro: a instrução errada era minha. Eu mandava **puxar a barra de
notificações no celular** — impossível com a tela sem toque. Corrigido: o `.bat`
agora diz explicitamente **"você NÃO precisa mexer na tela do celular"**, e a
barra de notificações só aparece depois, quando o mouse do PC já está mandando.

## O erro que apareceu

```
scrcpy 5.0.1
INFO: Killing adb server (if any)...
ERROR: Could not find any USB device
```

Isso **não** é cabo, **não** é o celular e **não** é a porta: é **driver**. Está na
[FAQ oficial do scrcpy](https://github.com/Genymobile/scrcpy/blob/master/FAQ.md#otg-issues-on-windows)
e na issue [#3654]: no Windows, `--otg` precisa falar com o aparelho pelo
`libusb`, e o driver de MTP do Windows está segurando a interface. O MTP
funcionar (o "Desbloqueie para acessar os dados") prova que os dados passam — o
que falta é o driver certo para o *modo OTG*.

## O conserto (uma vez só), com o celular plugado

**Zadig** — um `.exe` único, não instala nada:

1. baixe em `https://zadig.akeo.ie`;
2. abra o Zadig;
3. menu **Options → List All Devices**;
4. no seletor do meio, escolha o **aparelho Samsung** (`SAMSUNG Mobile USB
   Composite Device`, `MTP`, `SM-G610M` ou parecido — **não** o leitor de cartão,
   **não** o mouse);
5. no campo da direita, escolha **WinUSB** (ou **libusb-1.0**);
6. **Replace Driver**, espere terminar;
7. rode `teclado-pelo-pc.bat` de novo.

Depois disso o aparelho **deixa de aparecer no Explorer** como celular — é
esperado, o driver mudou. O MTP volta quando você desfizer (no fim).

## Plano B, se o Zadig não resolver

Driver oficial do Google, relatado na issue como o que faz **adb, scrcpy e
`scrcpy --otg` funcionarem juntos**:

1. baixe `https://dl.google.com/android/repository/usb_driver_r13-windows.zip`;
2. Gerenciador de Dispositivos → clique direito no aparelho → **Atualizar
   driver** → **Procurar drivers no computador** → **Escolher em uma lista de
   drivers disponíveis** → **Mostrar todos os dispositivos** → **Com disco** →
   aponte para `android_winusb.inf` (dentro do zip extraído) → escolha **Android
   ADB Interface**.

Detalhe interessante da issue: em pelo menos um caso, instalar o **driver
oficial da Samsung** *quebrou* o `--otg` — e sem ele funcionou. Ou seja, se você
instalou o Samsung USB Driver, vale desinstalá-lo antes.

## Depois de usar: voltar ao normal

Gerenciador de Dispositivos → clique direito no aparelho → **Desinstalar
dispositivo** → desconectar e reconectar o cabo. O Windows reinstala o MTP
sozinho.

## O que o `.bat` faz agora

- reconhece o erro exato do Windows e imprime o passo do Zadig e o plano B;
- remove a instrução impossível ("puxe a barra de notificações no celular");
- explica que, com o `--otg` rodando, a barra se abre **arrastando do topo com o
  mouse do PC** (ou pela tecla Windows);
- ensina a desfazer o driver para o MTP voltar.

A skill `celular.otg` devolve os mesmos passos e um campo novo, `desfazer`.

## Testes

- `pytest server/tests` → **2.808 passed** (`test_celular.py`: 152).
- Novos: o `.bat` contém o erro real (`Could not find any USB device`), diz que
  não é cabo nem celular, traz Zadig com `WinUSB`/`Replace Driver`, o plano B com
  `android_winusb.inf` e o passo de desfazer; `celular.otg` devolve o aviso do
  driver e o `desfazer`.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
