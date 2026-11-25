# 0.95.5 — Lindows, TempleOS, Whonix: onde o JARVIS roda e onde não existe caminho

Você pediu oito sistemas. Eu podia ter escrito oito nomes numa lista e dizer
"pronto". Não fiz isso, porque metade deles **não roda** e uma lista bonita não
mudaria nada no seu PC. O que existe agora é uma skill que responde de verdade.

## A lista

| sistema | veredito | o que acontece |
|---|---|---|
| **Parrot OS** | roda | Debian vivo; `apt` tem tudo |
| **Astra Linux** | roda | Debian por baixo; cuidado com a versão do Python |
| **NeoKylin** | roda, com ressalva | família RPM (`dnf`); o `adb` não vem no repositório |
| **Whonix** | roda, com ressalva | instala, mas **toda** rede passa pelo Tor — updater e driver degradam |
| **Lindows** | **não roda** | empresa fechou em 2008; não há repositório para instalar |
| **Red Star OS** | **não roda** | Fedora fechado, sem repositório alcançável, e marca arquivos |
| **TempleOS** | **não roda** | não tem Python, nem `pip`, nem TLS |
| **"Windows Gaming Edition"** | **não recomendado** | não é produto da Microsoft |

## TempleOS: o detalhe que você pediu

Cinco motivos, e cada um sozinho já basta:

1. **Não existe Python para TempleOS** — nem interpretador, nem porta. O JARVIS é
   Python de ponta a ponta: a API, as 360 skills e os 4.350 testes.
2. **Não existe `pip`** — então nem FastAPI, nem httpx, nem as outras bibliotecas
   teriam onde ser instaladas.
3. **A pilha de rede é mínima e sem TLS** — nada de HTTPS. Nem baixar o `adb`,
   nem falar com o GitHub.
4. **Sem TLS 1.2+, o updater morre** — é exatamente o mesmo bloqueio que o
   `raw.githubusercontent.com` causou aqui, mas permanente.
5. **Não há subprocesso** — o sistema roda num único processo cooperativo, em
   memória de endereço fixo. O JARVIS chama `adb` e `ffmpeg` como processos; isso
   não existe ali.

O que seria preciso: reescrever o JARVIS inteiro em **HolyC** e escrever um
cliente TLS do zero. Não é questão de esforço — é outro projeto.

## "Windows Gaming Edition"

Não é edição da Microsoft. São ISOs de terceiros com nome que não existe
oficialmente. Os problemas são concretos:

- sem assinatura da Microsoft na imagem, ninguém sabe o que foi alterado;
- edições "gaming" costumam desligar **Windows Update** e **Defender** — os dois
  que o JARVIS consulta para diagnosticar;
- o driver da Samsung exige assinatura válida, e num sistema alterado a
  instalação pode ser recusada;
- sem Update, o JARVIS fica sem as correções que ele mesmo recomenda.

**Em vez disso:** Windows 10/11 **Home ou Pro** oficiais, com os ajustes de jogo
feitos à mão (modo de jogo, plano de energia, driver de vídeo). Mesmo efeito,
com procedência.

## A parte que mede, em vez de supor

Para os sistemas que rodam, a skill **mede a máquina** antes de responder:

```
/etc/os-release · python3 · pip · adb · git · ffmpeg
```

E diz o que falta. No meu ambiente aqui, por exemplo: Debian 12, Python 3.11,
mas **sem `adb` e sem `ffmpeg`** — então o diagnóstico de celular não funcionaria.

Se a máquina já tem tudo, o passo a passo encolhe: só o `.venv`, o
`pip install` e o `iniciar.py`. Não mando instalar o que já está lá.

## Como pedir

No chat: **"roda no TempleOS?"**, **"e no Whonix?"**, **"como instalo no NeoKylin?"**

Ou, pelo terminal:

```bash
.venv\Scripts\python escanear-celular.py --sistemas
```

## O que esta skill NÃO faz

Não instala nada. Devolve o **plano** — quem executa é `sistema.instalar`, atrás
das travas de sempre (`JARVIS_HOST_REDE`, `JARVIS_HOST_INSTALAR`, token do plano).

## Testes

16 novos, e o mais importante é o que cobra a **recusa**:

- os oito sistemas pedidos estão na lista (nenhum esquecido);
- TempleOS, Lindows, Red Star e Gaming Edition **não recebem comando** — resposta
  `pode_instalar: false` com `comandos: []`, e sempre um "em vez disso";
- TempleOS explica os cinco motivos, não uma frase só;
- família Debian recebe `apt`, família RPM recebe `dnf` — **nunca trocados**;
- Whonix avisa do Tor;
- Python 3.8 é recusado com o motivo da versão;
- a medição não pode dizer "pode rodar" com problema listado.
