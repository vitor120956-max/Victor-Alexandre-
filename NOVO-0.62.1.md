# JARVIS 0.62.1 — o PC vira teclado e mouse do celular

Sem adaptador OTG e sem mouse USB, o caminho curto é este: **o próprio PC manda
teclas e cliques pelo cabo** com `scrcpy --otg`. O Android recebe como se fosse
um teclado e um mouse ligados nele — e você destrava o aparelho **sem encostar
no vidro**.

Não precisa comprar nada. O cabo que já está ligado é o mesmo.

## O que entra nesta versão

- **`teclado-pelo-pc.bat`** — acha o `scrcpy` (inclusive dentro de subpasta com
  versão no nome), explica o passo do MTP e roda `scrcpy --otg`. Se der erro,
  imprime o diagnóstico certo: driver libusb ausente, MTP segurando o aparelho ou
  porta USB fraca.
- **`celular.otg`** (skill nova) — devolve o caminho completo, os atalhos e o
  aviso do driver, sem executar nada. Pergunte no chat: *"dá para usar o PC como
  teclado do celular?"*.
- **O plano mudou** para o caso em que o Windows já vê o celular por MTP: o passo
  1 agora é *"Cabo e porta estão bons — falta destravar"*, com o
  `teclado-pelo-pc.bat` na frente. Não manda mais trocar cabo.

## Os atalhos que o Android entende

| Tecla | O que faz no Android |
|---|---|
| dígitos + **Enter** | digita o PIN e destrava |
| **Tab** / **Shift+Tab** | anda de campo em campo (Configurações vira lista navegável) |
| **Setas** | movem o foco |
| **Enter** | abre / confirma no item focado |
| **Esc** | volta (botão Voltar) |

## O passo a passo

**1. Antes de rodar, no celular**

Puxe a barra de notificações, toque na notificação **"USB"** / **"Conectado
como…"** e escolha **"Carregar este dispositivo"**. Isso solta a interface MTP
que o Windows está segurando — é ela que mostra o "Desbloqueie para acessar todos
os recursos".

Obs.: se o toque também estiver ruim, a notificação também pode ser aberta pelo
teclado depois que o `--otg` estiver rodando.

**2. No PC**

```bat
cd /d D:\JARVIS
```

```bat
teclado-pelo-pc.bat
```

Ele mostra o caminho do scrcpy e abre a janela do `--otg`. **Olhe a tela do
celular**, não a do PC: no modo OTG não há espelhamento, só o controle.

**3. Se aparecer erro de USB / "Could not open device"**

No Windows o `--otg` precisa do driver **libusb**, que o Windows não instala
sozinho. O utilitário é o **Zadig** (gratuito, um `.exe` só):

1. baixe em `zadig.akeo.ie` (ou pergunte `como instalar o zadig` e eu detalho);
2. abra com o celular plugado;
3. em **Options → List All Devices**;
4. escolha o **aparelho Samsung** na lista (aparece como `SAMSUNG Mobile…` ou
   `MTP`/`Android`);
5. confirme que o driver à direita é **libusb** (ou WinUSB) e clique em
   **Replace Driver**.

Isso troca **só a interface daquele aparelho**, não o Windows inteiro. Depois de
usar, dá para devolver o driver padrão: Gerenciador de Dispositivos → clique
direito no aparelho → **Desinstalar dispositivo** → reconectar o cabo (o Windows
reinstala o MTP sozinho).

**4. Destravar e ligar a Depuração USB (olhando a tela do celular)**

1. digite o **PIN** no teclado do PC e aperte **Enter**;
2. **Esc** até a tela inicial (ou **Home**);
3. navegue com **Tab/setas** até **Configurações** e **Enter**;
4. desça até **Sobre o telefone** → **Informações do software**;
5. no item **Número da versão**, aperte **Enter 7 vezes** — aparece "Você agora é
   um desenvolvedor";
6. **Esc**, volte e abra **Opções do desenvolvedor**;
7. com **Tab** até **Depuração USB**, **Enter** para ligar, e confirme **OK**.

**5. No chat**

```
status do celular
```

Com `autorizado`, o `celular.espelhar` abre a tela numa janela do Windows: **a
partir daí o toque fantasma deixa de importar**, porque quem manda é o PC.

## Sobre "o caminho curto" — o que é honesto dizer

O `--otg` é gratuito, mas tem duas arestas:

- **depende do driver libusb no Windows** (o passo do Zadig acima). No Linux e no
  macOS ele funciona direto, sem isso;
- **não espelha a tela**: você opera olhando o celular. Para ver a tela no PC é
  preciso a Depuração USB ligada — que é justamente o que este caminho destrava.

Alternativa que dispensa tudo isso: o **desbloqueio remoto da conta Samsung**
(`findmymobile.samsung.com`), se o aparelho estiver logado numa conta Samsung com
"Controles remotos" ligado. Vale tentar antes: são dois minutos e, se funcionar,
você pula direto para a Depuração USB.

## Testes

- `pytest server/tests` → **2.802 passed** (`test_celular.py`: 146).
- Novos: `otg()` explicando o caminho mesmo sem scrcpy instalado, com scrcpy
  devolvendo comando/atalho/passos, recusa com a camada desligada, os atalhos
  contendo PIN/Tab/Enter/Esc, o `.bat` sem acento e com `--otg`, a busca
  recursiva do `scrcpy.exe` e o aviso de `celular.preparar` — e a skill no
  registro.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Registro: **291 skills**.
