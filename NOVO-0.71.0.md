# JARVIS 0.71.0 — dá para ver que ele está trabalhando (e por que 13 falharam)

Duas queixas reais, do uso de verdade:

1. *“o JARVIS só aparece com três pontinhos — não aparece tempo, nem o que ele
   está fazendo, nem se deu erro ou travou”*;
2. o primeiro `arruma o pc` terminou em **3 feitas, 13 falhas**, com o resumo
   *“normalmente falta de administrador; o diário diz qual”*.

Nenhuma das duas era mentira. As duas empurravam trabalho para você.

## 1. Por que 13 falharam

A conta fecha: o plano tinha 1 processo + 9 tarefas + 4 serviços + 2 caches = 16.
Fechar processo e apagar cache o Windows deixa o próprio usuário fazer — foram as
**3** que passaram. Desativar tarefa (`schtasks /Change`) e serviço (`sc config`)
exige **administrador**, e a janela da API não estava elevada: as **13** bateram
em “acesso negado”, todas pelo mesmo motivo.

Agora isso vem dito, não sugerido:

- cada ação falha carrega `causa` (`admin`, `sumiu`, `tempo`, `pulado`, `parado`,
  `outro`) e `motivo` em português;
- o resultado traz `falhas_por_causa`, `nao_feitas` (nome, comando, motivo) e
  `como_resolver`;
- o **plano** já avisa antes (`elevado`, `precisam_admin`, `aviso_admin`): sem
  elevação, “13 de 16 vão falhar com acesso negado. Abra o arrumar-pc.bat com o
  botão direito → Executar como administrador”. A aba **Limpeza** mostra isso
  antes do clique.

E o resumo deixa de mandar você abrir o JSON: ele diz *“13 falharam: 13 por falta
de administrador”* e o que fazer.

## 2. Saber se está trabalhando

A bolha do chat deixou de ser só `...`:

```
Arrumando a máquina (limpeza)
00:42 de 300s
Limite desta skill: 300 s.                              [Cancelar]
```

- **o que** — o nome da skill (ou o rótulo deduzido do pedido, antes de a API
  responder qual é);
- **há quanto tempo** — relógio real, atualizado a cada segundo;
- **o limite** — o `timeout_seconds` que o servidor já usava em `wait_for`
  (300 s na limpeza, 180 s no desfazer). Agora ele aparece também na lista de
  skills da API;
- **âmbar aos 40%** do limite (“Ainda rodando — pode cancelar sem estragar nada”)
  e **vermelho no limite** (“Passou do limite: confira se a janela da API ainda
  está aberta”);
- **Cancelar** aborta de verdade (`AbortController` no pedido), e a resposta diz
  que o que já rodou está no diário.

## O que **não** entrou, e por quê

**Barra de porcentagem da limpeza.** Seria mentira: o braço executa uma fila de
comandos do Windows, e cada comando só conta o resultado no fim. Uma barra
enchendo ali seria animação, não medição — exatamente o que os três pontinhos já
faziam de errado. O que dá para medir é tempo decorrido e limite, e é isso que
aparece.

**Cancelar a ação no meio do comando do Windows.** O cancelamento para de
esperar a resposta; o `sc config` que já começou termina no servidor. Por isso a
mensagem diz “o que já rodou está no diário”, e não “desfiz tudo”.

## Onde ficou

| arquivo | o quê |
|---|---|
| `server/arrumar.py` | `elevado()`, `_causa_da_falha`, `_acao`, `_contar_causas`, `_como_resolver`, `TIPOS_QUE_PEDEM_ADMIN`, aviso no plano |
| `server/skill_registry.py` | `timeoutSeconds` no `public()` de toda skill |
| `server/agente_local.py` | `_formatar_braco`: relatório dos braços em texto de gente |
| `src/lib/progresso.ts` | `rotuloDoPedido`, `formatarDecorrido`, `situacao`, `avisoDaSituacao` |
| `src/context/AppContext.tsx` | `etapa`, `iniciarPedido`, `cancelarProcessamento`, `AbortController` |
| `src/components/ChatPanel.tsx` | a bolha com rótulo, tempo, aviso e Cancelar |
| `src/pages/MaquinaPage.tsx` | aviso de admin antes do clique, motivo da falha na lista |
| `docs/LIMPEZA.md` §11 | a tabela de causas e o que é medido |

## Testes

- `pytest server/tests` → **3.051 passed, 7 skipped**.
  - `test_arrumar.py`: **41** (+7) — causa traduzida, falha de admin nomeada,
    diário com a causa, tudo-falhou explicado, aviso de admin no plano,
    plano vazio sem aviso inventado.
  - `test_agente_local.py`: **204** (+3) — relatório dos braços sem dicionário
    cru, próximo passo quando o resumo não traz, plano continuando genérico.
- `vitest` → **128** (+4, `progresso.test.ts`), `tsc -b` limpo, build embutido ok.
- Skills: **306** (nenhuma nova).
