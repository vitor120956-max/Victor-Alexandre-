# 0.57.0 — “não tem como instalar sem token?”

Tem. O token de host nunca foi chave de ninguém: é uma string que o próprio
JARVIS sorteia e guarda em `storage/host-token.txt`. O que incomodava era copiar
e colar. A 0.57.0 tira o copiar-colar **sem** apagar as travas — e diz na cara o
que cada uma continua fazendo.

---

## 1. Modo dono — uma linha no `.bat`

```bat
set JARVIS_HOST_CONFIAR_LOCAL=1
```

Com essa variável, a API preenche o token sozinha **quando a requisição vem da
própria máquina** (`127.0.0.1` / `::1`). A resposta marca
`"autorizadoPor": "modo-dono-local"`, para você saber que foi automático.

O terminal passa a mostrar o estado:

```text
JARVIS modo host: token em storage/host-token.txt -> 8I99…NvFY (rede=desligada, instalar=desligado, root=desligado, pc=desligado, dono=LIGADO (sem digitar token nesta máquina))
```

## 2. O que **não** mudou

O modo dono não é um “desliga tudo”. Continuam valendo:

| Trava | No modo dono |
|---|---|
| `JARVIS_HOST_INSTALAR=1` | **continua obrigatória** para instalar |
| plano com comando, risco e assinatura | **continua** — `sistema.instalar` mostra antes |
| código de uso único do plano | usado **só quando há um plano pendente**; com dois, ele pede o código e não escolhe por você |
| confirmação da tela (`confirmed: true`) | **continua** — o servidor exige |
| requisição de **outra máquina** | **continua pedindo token**, mesmo com o modo ligado |

## 3. Bloqueio de origem — novo, e vale sempre

Requisição `POST` para `/api/` com `Origin` de outro site é recusada:

```json
{"ok": false, "error": {"code": "ORIGEM_RECUSADA", "message": "Requisição de outra origem. O JARVIS só aceita pedidos da própria tela."}}
```

Isso fecha o buraco clássico: uma página aberta no navegador (de outro site)
tentando chamar a API local. Passa `127.0.0.1`, `localhost`, o próprio host da
API e requisição sem `Origin` (como `curl`). Origem `null` e site de fora: 403.

## 4. Na tela

- Com o modo dono ligado, o campo **Token de host** some do formulário de cada
  skill e aparece uma nota explicando por quê.
- O token que você digitou no chat (`token abc…`) passa a preencher o campo
  automaticamente nas skills que o pedem — digita uma vez por aba, não por skill.

## 5. O preço, sem enfeite

Com o modo dono ligado, **qualquer programa que rode como você, nesta máquina**,
pode disparar instalação pela API sem saber o token. Antes, ele precisaria abrir
`storage/host-token.txt` — que já está legível para o seu usuário. Então o modo
dono não abre a porta para a rede nem para página de outro site; o que ele reduz
é a exigência de quem **já está dentro** da máquina.

Se o computador é compartilhado, deixe desligado. É uma linha no `.bat` para
ligar e uma para desligar:

```bat
set JARVIS_HOST_CONFIAR_LOCAL=0
```

## 6. Medido

| Verificação | Resultado |
|---|---|
| Skills no registro | **281** (nenhuma nova) |
| Suíte Python | **2.580** testes (17 novos em `test_modo_dono.py`) |
| Interface | **110** testes (vitest) |
| Tipos | `npx tsc -b` sem erro |
| Interface embutida | `npm run build:embutido` refeito |

Os 17 testes provam, sem HTTP e com HTTP: modo desligado continua exigindo token;
modo ligado preenche; modo ligado **não** preenche para `192.168.x.x`; modo ligado
respeita token digitado à mão; plano pendente único é usado e **dois planos não
são escolhidos no chute**; página de outro site toma 403; `Origin` local e
`Origin` ausente passam.

## 7. Como atualizar no seu PC

```bat
cd /d D:\JARVIS
git pull
set JARVIS_HOST_REDE=1
set JARVIS_HOST_INSTALAR=1
set JARVIS_HOST_CONFIAR_LOCAL=1
.venv\Scripts\python iniciar.py
```

Conferir: `http://127.0.0.1:8000/api/health` → `"version": "0.57.0"`,
`"skills": 281`, `"confiarLocal": true`.

## 8. Arquivos

- `server/sistema.py` — `confiar_local()`, `planos_pendentes()` e os campos novos
  em `capacidades()`.
- `server/app.py` — preenchimento do token e do plano para requisição local,
  bloqueio de origem, `confiarLocal` no `/api/health`, modo dono no chat do agente
  e no banner do terminal.
- `server/tests/test_modo_dono.py` — 17 testes.
- `src/lib/api.ts`, `src/context/AppContext.tsx`, `src/components/PythonSkillRunner.tsx`
  — `modoDono` na tela, campo de token escondido e token do chat reaproveitado.
- `docs/SISTEMA.md` — seção “Modo dono”.

## 9. O que continua fora

- **Instalar sem nenhuma trava** (sem `JARVIS_HOST_INSTALAR=1`): não. Essa
  variável é a decisão de “quero que ele possa instalar”; o modo dono é só
  “não quero digitar”.
- **Instalar sem mostrar o plano**: não. O plano com comando, risco e assinatura
  continua vindo antes.
- **Confiar em máquina da rede**: não. O modo dono vale só para `127.0.0.1`.
