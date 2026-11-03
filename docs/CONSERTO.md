# Conserto: do erro real à proposta ensaiada (0.75.0)

O pedido: *“tem como ele se auto programar? deu erro numa função, ele vai procurar
para que serve e como funciona, aí ele pesquisa, entende, testa, roda e, se
funcionar, entrega”*.

A resposta tem três partes: o que **já existia**, o que **faltava** e o que
**não vai existir**.

## 1. O que já existia — e é a metade cara

`server/evolucao.py` já fazia o fim do laço, desde antes desta versão:

| skill | o que prova |
|---|---|
| `evoluir.proposta` | o diff **aplica** no arquivo atual, hunk por hunk |
| `evoluir.risco` | pontua 0–100 (`eval`, `shell=True`, segredo embutido, guarda removida) |
| `evoluir.guardas` | confere as dez leis do projeto contra as linhas adicionadas |
| `evoluir.ensaiar` | copia o projeto, aplica o patch **na cópia** e roda a **suíte real** |
| `evoluir.promover` | aplica no código vivo só com hash idêntico, árvore limpa, backup e token |
| `evoluir.reverter` | restaura do backup |

Ou seja: “testa, roda e, se funcionar, entrega” já era verdade — numa cópia, com
a suíte inteira. O que não existia era **o começo**: ninguém ligava um erro real a
uma proposta. O diff era escrito à mão, e o erro tinha que ser copiado do
terminal.

## 2. O que faltava — e entrou agora (`server/conserto.py`)

### 2.1 O diário de erros

Toda falha **interna** de skill passa a ser anotada em `storage/erros.jsonl`:
quando, versão, skill, tipo, mensagem e traceback. Ficam só as últimas 200 linhas.
O pedido HTTP continua respondendo exatamente o mesmo texto genérico — “Nenhum
detalhe interno foi exposto” —, então isso **não** é vazamento novo: é o rastro
guardado do lado de dentro, onde só o dono da máquina lê.

### 2.2 Diagnóstico (`conserto.diagnosticar`)

Lê o último erro do diário (ou um traceback que você cole) e diz:

- **onde** — arquivo, linha e função, escolhendo o último quadro **deste** projeto
  no traceback (o último quadro costuma ser `json/decoder.py`, que não tem conserto);
- **o trecho** — 9 linhas do arquivo **de verdade**, com a linha do erro marcada;
- **a causa**, por regra escrita: `permissao`, `arquivo_ausente`, `chave_ausente`,
  `tipo_none`, `tipo_errado`, `indice`, `valor_invalido`, `unicode`, `json`,
  `timeout`, `rede`, `subprocesso` — e `desconhecida`, dita com todas as letras,
  quando nada casa;
- **o teste** — existe `server/tests/test_<módulo>.py`? quantos testes? Se não
  existe, avisa que o ensaio pode passar sem cobrir o caminho do erro.

Puro: não escreve, não chama rede, não chama modelo.

### 2.3 Dossiê (`conserto.dossie`)

Junta tudo num texto único — erro, trecho numerado, **a docstring do próprio
módulo** (é o “procurar para que serve” do pedido), o teste existente e as seis
guardas que o patch não pode quebrar. É o que faz uma correção sair em uma
tentativa em vez de dez. Serve para mim, para você ou para qualquer modelo.

### 2.4 Proposta (`conserto.propor`)

Com chave de IA configurada (`JARVIS_AI_API_KEY`), manda o dossiê ao provedor e
pede um diff unificado. A resposta passa pela **mesma régua** do `evoluir.*`
(aplica? risco? guardas?) antes de ser oferecida. **Não escreve nada** — o próximo
passo é `evoluir.ensaiar`.

Sem chave, recusa com o motivo: *“inventar correção é pior que não corrigir”*. O
dossiê vai junto, que é o que falta para alguém corrigir.

### 2.5 No chat

| você digita | ele faz |
|---|---|
| `por que deu erro` | `conserto.diagnosticar` |
| `me dá o dossiê do erro` | `conserto.dossie` |
| `conserta o erro` | `conserto.propor` (pede confirmação) |

“Deu erro no site que abri” continua indo para a busca normal: ali não há
traceback, e o atalho exige palavra de erro **mais** assunto deste programa.

## 3. O que não vai existir

**Corrigir sem inteligência.** Não há regra determinística que escreva um patch
correto para um `KeyError` arbitrário: saber *qual* padrão usar exige entender o
domínio. Por isso o passo 2.4 depende de um modelo (o seu) ou de você — e o
módulo **recusa** em vez de chutar.

**Patch que se aplica sozinho enquanto a API roda.** `evoluir.promover` exige
token, hash e árvore limpa, e o processo precisa reiniciar depois. Isso é de
propósito: um patch que derruba o processo derrubaria junto o que sabe reverter.

**Editar o arquivo e recarregar em memória.** Não existe recarga segura de código
Python num processo com estado (FastAPI, registro de skills, conexões). Quem
reinicia é o `iniciar-jarvis.bat`, com o código já promovido.

## 4. O laço completo, do jeito que ficou

```
erro real
   → storage/erros.jsonl            (anotar, automático)
   → conserto.diagnosticar          (onde, o quê, por quê — regra, sem palpite)
   → conserto.dossie                (código + docstring + teste + guardas)
   → conserto.propor                (diff, só com chave; validado pela régua)
   → evoluir.ensaiar                (suíte real numa cópia; verde libera token)
   → evoluir.promover               (backup + token de uso único)
   → reiniciar a API                (iniciar-jarvis.bat)
   → evoluir.reverter               (se o resultado não prestar)
```

Cada seta é uma decisão sua. Nada pula etapa.

## 5. Testes

`server/tests/test_conserto.py` — **31 testes**:

- diário: grava, lista do mais novo, poda em 200 linhas, aguenta linha corrompida;
- diagnóstico: acha o quadro do projeto e **ignora** stdlib/`site-packages`; o
  trecho é lido do arquivo real; 12 causas parametrizadas + `desconhecida`;
  contagem de testes do módulo, e o aviso quando não há teste;
- dossiê: tem arquivo, causa, guardas, docstring e “evoluir.ensaiar” — e menos de
  12 KB; sem erro, não inventa texto;
- proposta: sem chave recusa e entrega o dossiê; com provedor falso, o diff é
  lido e passa por `risco`/`guardas` (monkeypatchados), e o arquivo vivo continua
  byte a byte igual; “SEM PATCH” e diff sem formato são recusados;
- integração: uma skill que estoura gera `INTERNAL_ERROR` no HTTP **sem** o texto
  do erro, e a linha do diário tem o traceback completo com a skill e o tipo.
