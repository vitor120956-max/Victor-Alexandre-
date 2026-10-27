# JARVIS 0.60.5 — chega de token na própria máquina

A 0.60.4 consertou o erro em inglês e o "sim, pode" virando token. Faltava a
raiz: **por que raio o JARVIS pedia token para operar o seu próprio PC?**

Ele não pede mais. Se a requisição vem de `127.0.0.1`, o servidor preenche o
token sozinho. Sem variável, sem script, sem copiar nada de
`storage/host-token.txt`.

## O que você viu

```
A skill "Baixar adb e scrcpy" recusou o pedido: Isso não parece um token de
host (curto demais ou com espaço). Copie o conteúdo de storage/host-token.txt...
```

A 0.60.4 já dizia o motivo direito — mas o motivo era "você não configurou o
modo dono". Isso é fricção minha, não sua.

## Por que a trava local não protegia nada

O token mora em `storage/host-token.txt`, na sua pasta. **Qualquer programa
rodando como você lê esse arquivo** — e o JARVIS roda como você. Ou seja, exigir
o token de `127.0.0.1` não impedia código local nenhum: só fazia você copiar e
colar. O que o token realmente protege é a **porta aberta para a rede**: outra
máquina não tem o arquivo.

Então a regra ficou honesta: local não digita, remoto digita.

## O que mudou

**`sistema.confiar_no_pedido(da_propria_maquina)`** — uma função só, usada por
todas as rotas de host:

- veio de `127.0.0.1` / `::1` → token preenchido, sempre;
- veio de outra máquina → token exigido, sempre;
- `JARVIS_HOST_CONFIAR_LOCAL=1` → deixa o modo dono explícito no banner (é o que
  o `ligar-celular.bat` grava; continua funcionando igual);
- `JARVIS_HOST_EXIGIR_TOKEN_LOCAL=1` → **trava opcional**: pede token até
  localmente, para quem deixa a API exposta na rede.

**Valor torto não vira erro.** Se o campo chega vazio ou com algo que nem parece
token (`"sim, pode"`, texto do chat, token velho da tela), o servidor troca pelo
token de verdade. Token com formato válido é respeitado como veio — cada camada
(sistema, elevação, evolução) tem o seu arquivo, e quem valida é ela.

**A rota do agente tinha o buraco.** `/api/agente/executar` só preenchia quando o
valor chegava **vazio**; valor torto passava direto para a skill. Agora usa a
mesma regra da execução de skill.

**`/api/health` responde por origem.** `confiarLocal` é `true` quando quem
pergunta está na própria máquina — é o que o front lê para esconder o campo de
token. Também informa `confiarLocalPorVariavel` e `exigirTokenLocal`.

**Banner sem mentira:**

```
dono=automático na própria máquina (127.0.0.1 não digita token)
dono=LIGADO (sem digitar token nesta máquina)        # com =1
dono=token exigido até nesta máquina (=1 na trava)   # com a trava
```

## O que continua de pé

- `JARVIS_HOST_REDE=1` para baixar e pesquisar;
- `JARVIS_HOST_INSTALAR=1` para executar instalador;
- plano mostrado antes, com comando e SHA-256;
- token de uso único do plano (10 minutos);
- confirmação na tela;
- `Origin` de outro site recusado com `403 ORIGEM_RECUSADA`;
- pedido de outra máquina exige token digitado.

## Testes

- `pytest server/tests` → **2.679 passed**.
- `test_modo_dono.py` → **31** (novos: própria máquina não digita por padrão,
  trava explícita devolve o token, pedido de outra máquina nunca é preenchido,
  API local passa do token, health responde por origem).
- `test_sistema.py` → os testes "exige token" agora provam **os dois lados**:
  com a trava, recusa; sem ela, a skill responde de verdade.
- `vitest` → 120, `tsc -b` limpo.
