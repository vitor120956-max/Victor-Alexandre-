# JARVIS 0.72.0 — o JARVIS pede o administrador para você

A pergunta foi: *“o JARVIS não consegue fazer isso? podemos configurar para o
JARVIS fazer isso?”* — “isso” era rodar como administrador.

## A resposta curta

**Fazer sem perguntar: não existe.** O aviso de permissão do Windows (UAC) é a
barreira feita exatamente para impedir que um programa se torne administrador
sozinho. Não é o JARVIS que está limitado; é o Windows. Qualquer programa que
prometesse “me elevo sozinho” estaria usando uma falha de segurança.

**Pedir em vez de te mandar clicar com o botão direito: agora sim.**

## O que entrou

| onde | antes | agora |
|---|---|---|
| tela `/maquina` → Limpeza | “abra o arrumar-pc.bat como administrador” (você fazia) | botão **Reabrir como administrador** → o Windows pergunta → você clica **Sim** |
| chat | nada | `reinicia como administrador` (skill `maquina.administrador`) |
| `arrumar-pc.bat` | exigia botão direito → Executar como administrador | **se eleva sozinho**: duplo clique basta |
| `desfazer-limpeza.bat` | idem | idem |
| recusa no UAC | — | aparece como recusa (“você clicou Não”), nunca como sucesso |

Continua sendo **um clique** — o “Sim” do Windows. Não tem como ser zero.

## Como funciona

1. O JARVIS escreve `storage/subir-como-admin.bat` (ASCII, CRLF — o console
   antigo embaralha acento e o `cmd` não aceita LF).
2. Chama `ShellExecuteW(..., "runas", ...)`: o Windows mostra o aviso.
3. Aceito: o auxiliar espera **4 segundos** (para a resposta do pedido sair),
   encerra a instância atual com `server.instancia --parar --sim` e sobe
   `iniciar-jarvis.bat` — que já vem com `JARVIS_HOST_ARRUMAR=1`.
4. A tela cai por alguns segundos e volta elevada; o diário e o instantâneo
   continuam em `storage/limpezas/`.

## O que isso **não** muda

Elevação é permissão, não permissividade. Continuam fora, nos dois modos: driver
(NVIDIA Container), essencial (Store, VCLibs, Segurança), WinSxS, Windows.old,
`C:\Windows\Installer` e Prefetch. A trava `JARVIS_HOST_ARRUMAR=1`, a confirmação
e o diário continuam valendo — agora com as tarefas e os serviços **funcionando**
em vez de voltarem “acesso negado”.

## Detalhe honesto sobre testar

O `ShellExecuteW` só existe no Windows; no Linux do desenvolvimento ele não roda.
Os testes cobrem o que dá para cobrir sem a máquina: o `.bat` gerado (ASCII, CRLF,
para a instância antes de subir, espera antes de matar), a recusa do UAC virando
`aceito: false`, o código estranho explicando o plano B, quem já é administrador
não sendo reaberto, e os dois `.bat` do projeto contendo `net session` + `-Verb
RunAs` + rótulos consistentes. **O clique no UAC só é verdade na sua máquina** —
é o primeiro teste que eu não posso fazer por você.

## Testes

- `pytest server/tests` → **3.059 passed, 7 skipped**.
  - `test_arrumar.py`: **48** (+7) — elevação fora do Windows, já elevado, o
    auxiliar ASCII/CRLF com a ordem certa, recusa do UAC, código estranho, a
    skill no registro e os dois `.bat` que se elevam sozinhos.
  - `test_agente_local.py`: **202** (+1) — “reinicia como administrador” indo
    para `maquina.administrador`, e “arruma o pc como administrador” continuando
    na limpeza.
- `vitest` → **128**; `tsc -b` limpo; `build:embutido` ok.
- Skills: **307** (a nova: `maquina.administrador`).
