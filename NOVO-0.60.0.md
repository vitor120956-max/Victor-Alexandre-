# JARVIS 0.60.0 — o celular entra no PC (e a tela quebrada deixa de ser o fim)

A pergunta que abriu esta versão foi direta: *“e não dá para criar um programa
para o JARVIS fazer essa depuração mesmo sem nunca ter sido ligada?”*

A resposta honesta tem duas metades, e a versão entrega a maior delas:

- **não** existe programa que ligue a Depuração USB e toque em “Permitir depuração
  USB?” — esse consentimento é do Android, na tela, e é assinado por computador.
  Quem promete contornar isso está vendendo outra coisa;
- **existe** muita coisa em volta, e agora ela está dentro do JARVIS.

## 1. Cinco skills novas: `celular.*`

| Skill | O que faz | Confirmação |
|---|---|---|
| `celular.status` | Diz se `adb` e `scrcpy` estão instalados, onde, e se a permissão está ligada. Só olha o disco — não executa nada. | não |
| `celular.plano` | Mede o aparelho com `adb devices` e monta o caminho exato para o estado encontrado — inclusive quando a depuração **nunca** foi ligada. | não (só lê) |
| `celular.preparar` | Baixa platform-tools (Google) e scrcpy (GitHub), confere o SHA-256 e extrai em `ferramentas/`, recusando zip-slip. | **sim** |
| `celular.espelhar` | Abre o `scrcpy`: a tela do celular vira uma janela do Windows. Opcionalmente grava `.mp4`. | **sim** |
| `celular.puxar` | `adb pull` de DCIM, Pictures, Download, Documents, Movies, Music, WhatsApp e Telegram para `storage/celular/<data-hora>`. | **sim** |

Tudo atrás de `JARVIS_HOST_CELULAR=1` (novo no `.env.example`). Baixar as
ferramentas também exige `JARVIS_HOST_REDE=1`, como qualquer download do projeto.

## 2. O plano, que é o coração da coisa

`celular.plano` não devolve conselho genérico: ele mede e responde para o seu
caso. São seis situações reconhecidas — `sem-ferramentas`, `desligado`, `vazio`,
`nao-autorizado`, `autorizado` e `recovery` — e cada uma tem passos com comando.

No caso que motivou o pedido — depuração nunca ligada, tela morta — a resposta é:

1. testar cabo e porta (o culpado nº 1 de `adb devices` vazio);
2. ver se o Windows reconhece o aparelho como MTP (se sim, a placa vive);
3. entrar no modo Download às cegas (**Volume − + Home + Power**, depois
   **Volume +**) — e por que isso sozinho não resolve: o Odin recusa com
   *BLOCKED BY FRP LOCK* enquanto o Desbloqueio OEM não estiver ligado;
4. **tela de teste numa assistência** — 5 minutos para ligar Depuração USB +
   Desbloqueio OEM + “desativar tempo limite de autorização”, e o aparelho fica
   resolvido para sempre, mesmo que o painel vá para o lixo;
5. navegar às cegas com `scrcpy --otg` + **TalkBack** (Volume + e Volume − por 3 s),
   que fala o item focado.

No caso em que a depuração **existe** mas o PC não está autorizado, o plano traz a
sequência que a comunidade usa: `scrcpy --otg` → PIN → fechar → `scrcpy` (o popup
aparece) → `scrcpy --otg` → **Tab, Enter, Tab, Tab, Enter** → `scrcpy`.

## 3. O limite do `adb pull`

`celular.puxar` só copia pasta de mídia do armazenamento compartilhado. Ele
**recusa** `/data`, `system`, `..` e caminho que escape da raiz de dados. Não lê
base de aplicativo, não copia chave, não apaga nada no aparelho.

## 4. O que continua igual

- **288 skills** (283 + 5), todas na allowlist de `server/skill_registry.py`.
- Leitura sem confirmação; execução com `side_effects=True`,
  `requires_confirmation=True` e token de host fora do modo dono.
- Nada de shell livre: o `adb` só é chamado com argumentos montados pelo próprio
  módulo (`devices`, `pull`), e o `scrcpy` só abre a janela.
- Nenhuma chave paga, nenhum modelo obrigatório.

## Como atualizar

```bat
cd /d D:\JARVIS
git pull
```

Confira em `http://127.0.0.1:8000/api/health`:

```json
{"version": "0.60.0", "skills": 288}
```

Para ligar a camada, no `.env`:

```env
JARVIS_HOST_REDE=1
JARVIS_HOST_CELULAR=1
```

## O que testar, em 10 minutos

1. **Estado:** peça `onde está o adb do celular?` → deve dizer que falta e apontar
   `celular.preparar`.
2. **Preparar:** peça `baixa o adb e o scrcpy` → duas confirmações (download é
   efeito), depois um resumo com SHA-256 e o caminho dos executáveis.
3. **Medir:** conecte o celular por USB e peça `meu celular não tem tela, dá para
   usar?` → o plano para o estado real (`vazio`, `nao-autorizado` ou `autorizado`).
4. **Espelhar:** se aparecer `autorizado`, peça `espelha o celular aqui` → janela
   do celular no PC, com mouse e teclado.
5. **Resgatar:** peça `puxa as fotos do celular` → pastas em `storage/celular/…`
   com a contagem por pasta.

## Testes

- `pytest server/tests` → **2.648 passed** (35 novos em `test_celular.py`).
- `npx tsc -b` limpo e `npm run build:embutido` ok.
- `npx vitest run` → **117 passed** (nenhuma tela nova: as skills aparecem no
  formulário gerado a partir do esquema).

### Arquivos

- `server/celular.py` — ferramentas, leitura do `adb devices`, plano por situação,
  espelhamento, `adb pull` com lista fechada de pastas e preparo das ferramentas.
- `server/skill_registry.py` — cinco definições e quatro modelos de entrada.
- `server/tests/test_celular.py` — 35 testes, nenhum toca em aparelho de verdade.
- `docs/CELULAR-LINUX.md` — §3 (`scrcpy` com a tela morta) e §9 (as skills).
- `.env.example` — `JARVIS_HOST_CELULAR=0`.
