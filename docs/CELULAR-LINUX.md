# Celular velho como PC/Linux — o caso do Galaxy J7 Prime

Este documento responde a uma pergunta concreta: **dá para transformar um Galaxy
J7 Prime em um PC com Linux?** A resposta curta é *sim, com um porém caro e um
porém barato*: o modelo é um dos melhores candidatos possíveis, mas o aparelho em
questão está com a tela morta — e sem tela não existe caminho por software.

Nada aqui é executado pelo JARVIS. Ele não tem `adb` nem `fastboot`; todo comando
no celular é feito por você, na mão. O que ele faz é o que está na última seção.

---

## 1. O aparelho

| Item | Valor |
|---|---|
| Modelos | SM-G610F, SM-G610F/DS, SM-G610M, SM-G610M/DS, SM-G610Y |
| Codename (o que importa) | **`on7xelte`** |
| SoC | Samsung Exynos 7870 — 8× Cortex-A53 até 1,6 GHz, 14 nm |
| GPU | Mali-T830MP2 |
| RAM | 3 GB |
| Tela | 5,5" IPS, 1920×1080 |
| Armazenamento | 16/32 GB + microSD até 128 GB |
| Bateria | 3300 mAh **não removível** |
| Android de fábrica | 6.0.1 (atualizações até Oreo em boa parte das variantes) |

O codename é o que os projetos de Linux usam. "Galaxy J7 Prime" não serve: existe
o **J7 Prime 2** (`on7xreflte`, SM-G611x), que é outro aparelho e não aceita as
mesmas ROMs nem os mesmos dtb. Confira em **Configurações → Sobre o telefone →
Número de compilação**, ou no adesivo atrás da tampa.

---

## 2. O bloqueio: a tela não funciona

Sem imagem, você não consegue nenhuma destas quatro coisas — e todas são
pré-requisito para "virar PC":

1. ligar **Depuração USB** (Opções do desenvolvedor → precisa do toque 7× em
   "Número da compilação" e de navegar);
2. aceitar o popup **"Permitir depuração USB?"** — o `adb` recusa o aparelho até
   isso ser tocado;
3. navegar no recovery para escolher *install*, *wipe* ou *reboot*;
4. ler qualquer progresso de flash.

E o J7 Prime **não tem saída de vídeo por cabo**: nada de MHL ou HDMI. Não há
"espelhar no monitor" por hardware, e o modo Download/Recovery só aparece na
própria tela. Mouse por OTG também não resolve: o touch pode até responder, mas
sem imagem não há o que clicar.

> **Conclusão:** com a tela morta o projeto está travado. O caminho mais barato
> é trocar o módulo.

### Diagnóstico antes de comprar a peça (5 minutos, custo zero)

1. **Carregue 20 min.** Se o aparelho esquentar na região do conector ou vibrar
   ao ligar, a placa está viva — só falta imagem.
2. **Ligue no PC por USB.** No Gerenciador de Dispositivos, veja se aparece algo
   como *SAMSUNG Mobile USB Composite Device* ou *MTP*. Se aparecer, a placa
   inicializa.
3. **Segure Volume − + Power por 10 s.** Se houver vibração, o bootloader roda.
4. **Ligue na tomada e olhe a tela de perto, com luz forte e de lado.** Se houver
   um brilho cinza fraco, o backlight vive e pode ser só o flex do display.
5. **Teste um carregador com outro cabo.** Antes de condenar o aparelho, elimine
   o óbvio.

Se 1, 2 e 3 falharem, pode ser placa, não tela — aí a peça não resolve.

---

## 3. A peça

| Opção | Faixa de preço (Brasil, 2026) | Observação |
|---|---|---|
| Módulo compatível (LCD+touch) | R$ 70 – 160 | O que se acha no Mercado Livre; qualidade variável |
| Módulo "premium"/nacional | R$ 100 – 160 | Lojas de peça (Brascell, Empório, d7) |
| Original Samsung | R$ 220 – 240 | Vale se o aparelho for ficar de uso diário |

Códigos que servem: **SM-G610F, G610F/DS, G610M, G610M/DS, G610Y/DS**. Peça
sempre "com aro", se possível: sem aro você precisa transferir o chassi e a chance
de quebrar o vidro na hora da colagem sobe muito.

**Cuidado com a bateria.** Aparelho de 2016, bateria colada e 3300 mAh. Se estiver
estufada (tampa traseira abaulada ou tela "saltando"), **não recarregue** — e não
deixe o aparelho como monitor fixo na tomada 24 h. Bateria de celular estufada é
risco real de incêndio.

---

## 4. Caminho A — Linux **dentro** do Android (recomendado)

Sem root, sem desbloquear nada, sem risco de perder o aparelho. Você instala o
Termux e ganha um Debian com `apt`.

**Requisito:** Android 7.0 ou mais novo e o APK do **F-Droid** ou do GitHub — a
versão da Play Store é outro ramo, experimental, e exige Android 11. Para Android
5/6 existem APKs "legacy" (`apt-android-5`) com repositório congelado.

```bash
# Termux (F-Droid)
pkg update && pkg upgrade -y
pkg install proot-distro openssh
proot-distro install debian
proot-distro login debian
```

Dentro do Debian:

```bash
apt update && apt install -y python3 git nano curl
python3 --version
```

Área de trabalho (opcional; em 3 GB prefira algo leve, não XFCE completo):

```bash
# no Termux
pkg install x11-repo && pkg install tigervnc
# dentro do Debian
apt install -y lxqt-core tigervnc-standalone-server
vncserver :1 -geometry 1280x720 -depth 24
```

Depois, um app de VNC no Android (bVNC, por exemplo) apontando para
`127.0.0.1:5901`.

**O melhor uso na prática:** com `openssh`, o celular vira terminal do seu PC.

```bash
ssh seuusuario@192.168.1.15     # IP do PC na rede local
```

Limites honestos do caminho A: sem root, **sem `systemd`** (`systemctl` não
existe), sem Docker, gráfico por software (lento), 200 MB a 2 GB por distro, e no
Android 12+ o "matador de processos fantasma" pode derrubar o shell.

---

## 5. Caminho B — Linux **no lugar** do Android (Nura)

O projeto que se chamava **postmarketOS** virou **Nura** em 27/09/2026
(`nura.eco`; `postmarketos.org` redireciona).

**Estado do `on7xelte`:** existe device package desde 2023, na categoria
**testing**, com **rede por USB**, touchscreen, Wi-Fi e bateria funcionando. Há
trabalho de mainline em andamento para o Exynos 7870 (dtb `exynos7870-on7xelte`,
kernel `linux-postmarketos-exynos7870`). "Testing" quer dizer: **liga e faz o
básico** — não quer dizer telefone confiável.

| O que costuma funcionar | O que costuma não funcionar |
|---|---|
| Tela, touch, Wi-Fi | Câmera |
| Rede por USB (ótimo: dá SSH sem tela!) | Chamadas por VoLTE |
| Bateria/energia | Sensores finos, GNSS |
| Terminal, SSH, Python | Aceleração gráfica completa |

**Riscos, sem enfeite:**

- desbloquear e flashar **aciona o Knox** de forma permanente;
- no Exynos 7870 o **Heimdall é notoriamente problemático** — a comunidade usa
  **Odin** ou TWRP;
- errar o passo do recovery pode **bricar** o aparelho;
- e, no seu caso específico: **tudo isso exige tela funcionando primeiro.**

Se um dia chegar lá, a ordem é: firmware estoque → TWRP/Boot → image do Nura →
`ssh` pela rede USB. O guia por aparelho fica na wiki do projeto.

---

## 6. Caminho C — só reviver o Android

Se o objetivo é "ter um celular usável de novo" e não "ter Linux", o melhor custo-
benefício é ROM Android leve:

- **LineageOS 18.1** (Android 11) para `on7xelte`;
- builds não oficiais de **/e/OS** (Android 12) para `on7xelte`;
- kernels alternativos do projeto Exynos7870.

Com 3 GB de RAM e Android 11/12 enxuto, o aparelho volta a ser utilizável — e aí
o Termux do caminho A roda melhor do que rodaria no Android 8 de fábrica.

---

## 7. O celular como tela/terminal do PC (funciona hoje, sem instalar nada)

Independente da tela do celular, o contrário também vale: o PC expõe o JARVIS na
rede e o celular abre no navegador.

```bat
cd /d D:\JARVIS
.venv\Scripts\python iniciar.py --host 0.0.0.0
ipconfig
```

No celular, na mesma rede Wi-Fi: `http://<IPv4-do-PC>:8000`. A interface tem
breakpoints para 480–760 px, então se adapta à tela do celular. O bloqueio de
origem (`403 ORIGEM_RECUSADA`) só barra página de **outro site**; e o modo dono
**não vale** para o celular — ele só preenche o token para requisição vinda de
`127.0.0.1`. Do celular, o token continua sendo pedido para o que grava ou executa.

---

## 8. O que o JARVIS faz e não faz aqui

**Faz** (e você pode pedir pelo chat):

| Pedido | Skill usada |
|---|---|
| "pesquisa o port do on7xelte no Nura" | `sistema.rede` (busca sem chave) |
| "baixa o Termux do F-Droid" | `sistema.baixar` (quarentena + SHA-256) |
| "confere o hash desse APK" | `sistema.assinatura` |
| "esse .msi roda nesta máquina?" | `instalador.analisar` |
| "abre o Gerenciador de Dispositivos" | `pc.abrir-programa` |

**Não faz:** não tem `adb`, não tem `fastboot`, não instala nada no celular e
`sistema.executar` só aceita `msiexec`, `dpkg`, `rpm`, `npm` e Python. Ele não
flasha, não desbloqueia bootloader e não "entra" no aparelho por USB.

---

## 9. Resumo em uma tabela

| Pergunta | Resposta |
|---|---|
| O J7 Prime serve? | Sim: `on7xelte` tem port no Nura (testing), LineageOS e /e/OS |
| Com a tela morta, dá? | **Não.** Nem adb, nem recovery, nem flash |
| Quanto custa destravar? | R$ 70–160 (compatível) ou R$ 220–240 (original) |
| Melhor caminho depois da tela? | Termux + proot-distro (risco zero) |
| Vale o Nura? | Só como experimento: sem câmera e sem VoLTE confiável |
| Vale como PC? | Como **terminal** do PC, sim. Como PC autônomo, não |
| Cuidado maior | Bateria de 2016 — nunca deixe estufada na tomada |

---

## 10. Fontes

- Nura / postmarketOS — device `on7xelte` em testing:
  <https://gitlab.com/postmarketOS/pmaports/-/merge_requests/4220>
- Trabalho de mainline para Exynos 7870 / `on7xelte`:
  <https://github.com/Praxis1071/on7xelte-mainline>
- Renomeação postmarketOS → Nura (27/09/2026): <https://nura.eco/blog/2026/09/27/nura-rename/>
- Termux — requisitos e canais de instalação:
  <https://github.com/termux/termux-app>
- proot-distro: <https://github.com/termux/proot-distro>
- /e/OS não oficial para `on7xelte`:
  <https://community.e.foundation/t/unofficial-build-samsung-galaxy-j7-prime-j7-on-nxt-on7xelte-for-e-os-s-4-x/84419>
- Peças (preços de referência): Mercado Livre, Brascell, d7 Eletrônicos.
