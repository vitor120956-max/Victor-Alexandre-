# 0.58.0 — o plano virou botão

Na 0.57.0 o token deixou de ser digitado. Faltava o outro meio do caminho: o
plano de instalação saía com um código de uso único e o passo seguinte era
chamar `sistema.executar` na mão. Agora a tela faz esse passo — mostrando o
comando, exigindo a caixa de confirmação e continuando a exigir a trava.

---

## 1. O cartão “Plano pronto para executar”

Rode `sistema.instalar` (ou `sistema.desinstalar`) e o resultado passa a trazer,
abaixo do texto, um cartão com:

- **alvo**, **tipo**, **risco** e o **SHA-256** do arquivo;
- o **comando exato** em um bloco de código;
- a caixa *“Confirmo que revi o comando acima e quero executá-lo neste PC”*;
- o botão **Executar este plano**.

O botão só liga com a caixa marcada. Ao executar, ele chama `sistema.executar`
com o código do plano e mostra o resultado ali mesmo — inclusive quando a
execução falha, com o código de saída.

## 2. A lista de planos na página Skills

No topo da página **Skills** aparece um painel com os planos pendentes que ainda
valem:

```
┌ Um plano pronto  gerado por sistema.instalar, válido por poucos minutos
│ pacote-teste.deb
│ instalar · deb · expira em 9 min                  [ Executar este plano ]
└
```

Fonte: `GET /api/host/planos`, atualizado a cada 30 segundos e também logo depois
de qualquer skill rodar. O painel mostra o **tempo restante** e, quando a
instalação está desligada, avisa em vermelho:

> A instalação está desligada: suba a API com `JARVIS_HOST_INSTALAR=1` para
> executar.

Os botões ficam **desativados** nesse caso — o painel aparece para você saber
que existe plano, mas ele não sai do lugar sem a trava.

## 3. O que o botão não faz

| Não faz | Por quê |
|---|---|
| escolher o plano por você | com dois planos pendentes, cada um tem o seu botão |
| ignorar `JARVIS_HOST_INSTALAR=1` | a trava é a decisão “quero instalar”; o botão é conveniência |
| esconder o comando | ele aparece em texto **antes** do clique |
| reutilizar o código | cada execução consome o token; o painel mostra “0 planos” depois |
| executar sem confirmação | a caixa é obrigatória, e o servidor também exige `confirmed: true` |

## 4. O código de uso único não vaza

`GET /api/host/planos` devolve `confirmacao` **só** para requisição vinda da
própria máquina (`127.0.0.1` / `::1`). De fora, a resposta continua dizendo que
existe plano e qual é o alvo — mas sem o código, que é o que permite executar.

```json
{
  "ok": true, "local": true, "instalar": true, "total": 1,
  "planos": [{
    "confirmacao": "665422bd", "acao": "instalar", "rotulo": "pacote-teste.deb",
    "tipo": "deb", "comando": "dpkg -i /tmp/host-downloads/pacote-teste.deb",
    "sha256": "48a62627…", "expira_em": 599
  }]
}
```

## 5. Medido

| Verificação | Resultado |
|---|---|
| Skills no registro | **281** (nenhuma nova) |
| Suíte Python | **2.585** testes (5 novos: rota de planos e `planos_pendentes`) |
| Interface | **117** testes (7 novos em `tests/planos.test.ts`) |
| Tipos | `npx tsc -b` sem erro |
| Interface embutida | `npm run build:embutido` refeito |

**Smoke ao vivo, contra a API de verdade:**

```
1) planos antes: 0
2) instalar -> 200 True     confirmação 665422bd
      alvo = pacote-teste.deb · tipo = deb · risco = médio
      comando = dpkg -i /tmp/jarvis058/host-downloads/pacote-teste.deb
3) GET /api/host/planos -> 1 | instalar = True | local = True
4) executar sem digitar token -> 200 True
      comando = dpkg -i …  ·  execução = código 2
5) planos depois: 0
```

O código 2 é o esperado: o sandbox não tem `dpkg` com root. O que o smoke prova
é o caminho inteiro — plano criado, listado, executado sem token digitado (modo
dono) e consumido.

## 6. Como atualizar no seu PC

```bat
cd /d D:\JARVIS
git pull
set JARVIS_HOST_REDE=1
set JARVIS_HOST_INSTALAR=1
set JARVIS_HOST_CONFIAR_LOCAL=1
.venv\Scripts\python iniciar.py
```

Conferir: `http://127.0.0.1:8000/api/health` → `"version": "0.58.0"`,
`"skills": 281`.

Depois: **Skills → sistema.instalar → preencher o arquivo → Executar** → o cartão
aparece com o botão.

## 7. Arquivos

- `server/app.py` — rota `GET /api/host/planos` (código só para requisição local).
- `server/sistema.py` — `planos_pendentes()` passa a devolver `comando` e `sha256`.
- `src/lib/planos.ts` — leitura do plano e montagem dos parâmetros de execução.
- `src/components/PythonSkillRunner.tsx` — cartão “Plano pronto para executar”.
- `src/pages/SkillsPage.tsx` — painel de planos pendentes e modal de execução.
- `src/styles.css` — estilos do cartão e do painel.
- `server/tests/test_modo_dono.py` (+5) e `tests/planos.test.ts` (novo, 7).
- `docs/SISTEMA.md` — seção “O botão Executar este plano”.

## 8. O que continua fora

- **Instalar sem `JARVIS_HOST_INSTALAR=1`**: não.
- **Executar plano de outra máquina**: não — o código não sai para fora do
  `localhost`.
- **Executar vários planos de uma vez**: não existe botão “executar todos”, de
  propósito.
- **Desfazer a instalação**: `sistema.desinstalar` monta o plano de remoção, e ele
  também ganha o botão. Reverter o que o instalador fez no sistema, não.
