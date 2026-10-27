# JARVIS 0.59.0 — instalar e desinstalar pelo mesmo caminho, e a agenda que avisa sozinha

Duas coisas que faltavam para o ciclo ficar fechado: depois de instalar, poder
tirar; e não precisar lembrar de olhar a agenda.

## 1. Desinstalar a partir do plano que instalou

O plano de instalação já existia (0.58.0): ele mostra o comando, o hash, o risco
e espera o seu clique. O que faltava era o caminho de volta.

- **`sistema.instalados`** (novo, só leitura) lê `storage/host-audit.jsonl` — o
  registro que o JARVIS já escrevia — e lista **o que foi instalado ou removido
  com código 0**: data, alvo, tipo, comando exato. Tentativa que falhou continua
  no arquivo, mas não entra na lista. Sem registro nenhum, a resposta é honesta:
  “Ele ainda não executou nenhuma instalação nesta máquina.”
- Cada plano de instalação pendente passa a trazer **`remocao`**, com a sugestão
  dedutível do próprio nome do arquivo:

| Arquivo | Remoção sugerida | O que a nota diz |
|---|---|---|
| `app_2.0_amd64.deb` | `dpkg:app` | confira o nome do pacote |
| `nano-7.2-1.fc38.x86_64.rpm` | `rpm:nano` | confira o nome do pacote |
| `.msi` / `.msix` | — | o Windows exige o GUID do produto (`msiexec /x {GUID}`), que não está no nome do arquivo |
| `.exe` | — | o desinstalador é definido pelo fabricante |
| `.AppImage` | — | não se instala: apagar o arquivo é a remoção |

- No painel de planos da página **Skills**, o plano de instalação ganha o botão
  **Desinstalar (dpkg:nome)**. Ele **monta** o plano de remoção via
  `sistema.desinstalar`; o plano aparece na mesma lista, com **Executar remoção**,
  e só roda depois do seu clique — e do checkbox, quando o cartão pede.
  Quando não há remoção automática, o lugar do botão mostra **por que**.

São dois passos de propósito: **montar não é executar**. Nada sai daqui sem o
comando visível, a confirmação e — fora do modo dono — o token.

## 2. A agenda avisa enquanto a janela está aberta

- Cada compromisso guarda por quantos minutos antes avisar (`avisar_antes`, 30
  por padrão; `0` desliga o aviso daquele item).
- **`agenda.lembretes`** (novo) responde “o que está vencendo agora”: o que já
  passou (marcado como atrasado, com quanto tempo) e o que entra na janela.
  A rota equivalente é `GET /api/agenda/lembretes`.
- A tela consulta essa rota **a cada 45 segundos** (só quando o backend está
  online). Quando aparece algo novo: aviso na tela, mensagem no chat e — se você
  já autorizou notificação no navegador — a notificação do sistema.
- O que já foi mostrado fica em memória pela chave `id|quando|tipo`: o mesmo
  compromisso **não avisa duas vezes**, e reiniciar a API não duplica.
- **O limite, sem enfeite:** o JARVIS não tem serviço em segundo plano. Com a
  janela fechada, ninguém avisa. Aviso com o JARVIS fechado exigiria um serviço
  do Windows rodando — não é o que existe aqui.

## O que continua igual

- **283 skills** (281 + `agenda.lembretes` + `sistema.instalados`), todas na
  allowlist de `server/skill_registry.py`, com entrada validada por Pydantic.
- Leitura sem confirmação; gravação, envio e execução com
  `side_effects=True, requires_confirmation=True`.
- Instalar e desinstalar seguem exigindo `JARVIS_HOST_INSTALAR=1`, plano na tela
  e confirmação. No **modo dono** (`JARVIS_HOST_CONFIAR_LOCAL=1`) você não digita
  token na própria máquina; para outra máquina, o token continua obrigatório.
- Nenhuma chave paga, nenhum modelo obrigatório.

## Como atualizar

```bat
cd /d D:\JARVIS
git pull
```

Confira em `http://127.0.0.1:8000/api/health`:

```json
{"version": "0.59.0", "skills": 283}
```

## O que testar, em 5 minutos

1. **Instalados:** peça `o que você já instalou nesta máquina` → lista vazia ou o
   que já rodou, com data e comando.
2. **Remoção sugerida:** peça para analisar um `.deb` ou `.rpm` que você tenha;
   no painel de planos deve aparecer **Desinstalar (dpkg:…)**. Clique: ele monta
   o plano de remoção e **não executa**. O plano fica listado para você decidir.
3. **Sem remoção automática:** faça o mesmo com um `.msi` ou `.exe` — em vez do
   botão, deve aparecer o motivo (GUID do produto / desinstalador do fabricante).
4. **Lembrete:** `marca reunião daqui a 20 minutos` e deixe a janela aberta.
   Em até 45 s deve aparecer o aviso do compromisso, no chat e na tela.
5. **Sem aviso duplicado:** espere mais um ciclo — o mesmo compromisso não deve
   avisar de novo.
6. **Desligar o aviso:** `marca consulta amanhã às 9h, sem aviso` → o item não
   entra nos lembretes; os outros continuam.

## Testes

- `pytest server/tests` → **2.613 passed** (32 na agenda, incluindo a rota).
- `npx vitest run` → **117 passed** (8 arquivos).
- `npx tsc -b` limpo e `npm run build:embutido` ok.

### Arquivos

- `server/agenda.py` — `avisar_antes`, `devidos()`, `chave_do_lembrete()`,
  `texto_lembretes()`.
- `server/sistema.py` — `remocao_sugerida()`, `instalados()`, `remocao` nos planos.
- `server/skill_registry.py` — `agenda.lembretes`, `sistema.instalados`.
- `server/app.py` — `GET /api/agenda/lembretes` (só leitura).
- `src/context/AppContext.tsx` — consulta de 45 s, sem aviso repetido.
- `src/pages/SkillsPage.tsx` — botão Desinstalar e nota de “sem remoção”.
- `docs/SISTEMA.md`, `docs/AGENDA-BACKUP-GIT.md`, `docs/AGENTE-LOCAL.md`, `README.md`.
