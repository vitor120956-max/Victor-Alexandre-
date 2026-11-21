# 0.92.5 — “quero 100% de acesso ao meu celular”: os cinco degraus, e até onde o JARVIS vai

> quero e preciso q o jarvis tenha 100 de acesso ao meu celular

> ta ja conectei o cll no pc como faço o jarvis rodar por todo o meu celular

Duas perguntas, uma resposta só: **quanto do celular um programa pode alcançar, e
o que o JARVIS faz com o que alcança.**

## 100% não existe — e não é o JARVIS se escondendo

O Android foi desenhado para que **ninguém** — nem quem fabricou o aparelho — leia
tudo de dentro dele com ele ligado e bloqueado:

- cada app roda na própria caixa (sandbox), e ler os dados de outro exige root;
- a memória é embaralhada por aparelho (ASLR + verificação de integridade), então
  “espiar” a RAM de fora não dá;
- o **bootloader travado** recusa imagem de sistema que não seja assinada;
- o **verified boot** compara o sistema com o hash assinado — mexer nele **é
  detectado**, e aí o banco, o WhatsApp e o Google Pay param de funcionar.

O caminho real para “tudo” é **desbloquear o bootloader e instalar root** — e o
desbloqueio, na prática, **apaga o aparelho inteiro** (é o preço do fabricante
para provar que a caixa foi aberta). Isso está escrito no cartão da tela, não só
aqui.

## Os cinco degraus

| degrau | o que ganha | o que exige | o que custa | o JARVIS faz? |
|---|---|---|---|---|
| **1** | ler tudo o que o Android publica, espelhar a tela, mandar toque e tecla, instalar/remover app, copiar mídia | cabo USB + **Depuração USB** ligada + “Permitir” no popup | nada — reversível, sem apagar nada | **sim** |
| **2** | o mesmo **sem cabo**, pela rede | `adb tcpip 5555` (uma vez, com cabo) | o aparelho fica escutando na rede local | **sim** |
| **3** | root: ler dados de qualquer app, mudar arquivos de sistema | desbloquear bootloader + Magisk | **apaga o aparelho**; quebra OTA, banco, carteira, alguns apps | **não** |
| **4** | trocar o sistema inteiro (ROM, kernel) | bootloader destravado + imagem assinada por você | risco de tijolo; sem volta fácil | **não** |
| **5** | explorar uma falha para escapar da caixa sem permissão | falha ainda não corrigida | aparelho de outra pessoa, sem consentimento: é crime | **não** |

O cartão mede o **seu** aparelho e mostra em que degrau ele está: cabo ligado →
1; `tcpip` ativo → 2; `ro.build.tags` com `test-keys` ou `su` no PATH do adb →
3+. Hoje o JARVIS **para no 2**, de propósito.

**Por que parar no 2?** Porque 3, 4 e 5 não são “mais acesso ao seu celular”: são
**acesso ao celular de qualquer um que encostar no seu cabo**, e a mesma porta que
lê a sua conversa lê a senha do seu banco. O motivo vai escrito na tela, degrau por
degrau, para você poder discordar do JARVIS com o custo na mão.

## O que mudou no código

**`server/varredura.py` — `CONTROLE` e `controle()`**
Os cinco degraus viram dado, não promessa: `degras[5]{degrau, nome, ganha, falta,
custa, jarvis_faz, recusa, alcancado}` e `o_que_nao_faz_e_por_que[]`, com
`degrau_maximo_jarvis = 2`.

**`server/acoes.py` — as ações do degrau 1**
Abrir, fechar e instalar app: `monkey -p <pacote> -c android.intent.category.LAUNCHER 1`,
`am force-stop <pacote>`, `install -r <apk>` — sempre `adb -s <serial>`, sempre com
`JARVIS_ACOES=1` **e** `confirmed: true`, pacote validado por regex
(`com.whatsapp; rm -rf /` é recusado) e só `.apk` de dentro da área do JARVIS.

**`server/app.py` — `GET /api/anatomia/android/controle`**
Sem aparelho responde 409 `CONTROLE_CELULAR` com o texto do que fazer; com
aparelho devolve o mapa medido.

**Tela — Anatomia → “Até onde o JARVIS chega”**
Badge “degrau N de 5”, o que ganha, o que falta, o que custa, e a lista do que o
JARVIS **não** faz e por quê.

**`ver-tudo-no-celular.bat` — o “rodar por todo o celular”**
Duplo clique: passa por **12 leituras** em 6 seções (pastas, partições, memória,
processos, sistema/apps, identidade) e escreve o relatório em
`storage/diagnosticos/`. É **só leitura** — não instala, não apaga, não muda nada.

## Como usar, na ordem

1. No celular: **Opções do desenvolvedor → Depuração USB**; conecte o cabo e toque
   **Permitir** no popup do aparelho.
2. No PC: `set JARVIS_HOST_CELULAR=1` no `iniciar-jarvis.bat` (uma vez) e reinicie.
3. Duplo clique em **`ver-tudo-no-celular.bat`**. Ou `escanear-celular.bat` se
   quiser o scanner com as perguntas de sintoma.
4. Na tela: **Anatomia** (Ctrl+F5) → o cartão “Até onde o JARVIS chega”.

Windows não reconhece o aparelho? Instale o **driver do fabricante** e, no celular,
**Revogar autorizações USB** → reconecte → Permitir de novo.

## Medido

- **pytest 4 249** (0 falhas, 7 pulados) — **35 casos novos** (24 de varredura e
  controle, 11 das ações do celular).
- **358 skills** no registry — 5 novas nesta versão: `celular.varredura`,
  `celular.controle`, `celular.abrir-app`, `celular.fechar-app` e
  `celular.instalar-apk` (ver `docs/ARVORE.md`).
- API real (8014, adb simulado): `/api/anatomia/android/controle` → **200**,
  degrau 0, máximo 2; `/api/anatomia/android/varredura` → **200**, 12 de 12
  leituras, 6 seções; `/anatomia` → 200.
- `vitest` 243, `tsc` limpo, manifesto 668 arquivos em 0.92.5.

## O que eu preciso de você

Rode o `ver-tudo-no-celular.bat` e me mande o relatório (ou a tela do cartão). Com
o modelo, o `ro.build.tags` e o que apareceu nas 12 leituras eu digo exatamente em
que degrau o seu aparelho está — e o que dá para fazer nele **sem apagar nada**.
