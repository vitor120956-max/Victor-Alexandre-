# JARVIS 0.73.0 — o erro que ele mesmo vê, e o dossiê que faz a correção acertar

A pergunta: *“tem como ele se auto programar? deu erro numa função, ele vai
procurar para que serve e como funciona, aí ele pesquisa, entende, testa, roda e,
se funcionar, entrega — quase como você”*.

Resposta em três partes: **metade já existia**, **a outra metade entrou agora**, e
**uma parte não vai existir** — e é bom que não.

## 1. O que já existia (e é a parte difícil)

`server/evolucao.py` já fazia o fim do laço, desde antes desta versão:

| skill | o que ela prova |
|---|---|
| `evoluir.proposta` | o diff **aplica** no arquivo atual, hunk por hunk |
| `evoluir.risco` | pontua 0–100 (`eval`, `shell=True`, segredo, guarda removida) |
| `evoluir.guardas` | confere as **dez leis** do projeto no patch |
| `evoluir.ensaiar` | copia o projeto, aplica o patch **na cópia** e roda a **suíte real** |
| `evoluir.promover` | só com hash idêntico, árvore limpa, backup e token de uso único |
| `evoluir.reverter` | restaura do backup |

“Testa, roda e, se funcionar, entrega” **já era verdade**. O que não existia era o
começo: ninguém ligava o erro real a uma proposta. O diff era escrito à mão, e o
erro tinha que ser copiado do terminal.

## 2. O que entrou agora — `server/conserto.py` + 3 skills

**Diário de erros.** Toda falha interna de skill vira uma linha em
`storage/erros.jsonl` (quando, versão, skill, tipo, mensagem, traceback; últimas
200). O HTTP continua respondendo o mesmo texto genérico — **não é vazamento
novo**: é o rastro guardado do lado de dentro, onde só você lê.

**`conserto.diagnosticar`** — lê o diário (ou um traceback colado) e diz:

- o **arquivo, a linha e a função** — escolhendo o último quadro *deste* projeto
  (o último quadro de um traceback costuma ser `json/decoder.py`, que não tem
  conserto);
- o **trecho real** do arquivo, 9 linhas, com a linha do erro marcada;
- a **causa por regra escrita**: `permissao`, `arquivo_ausente`, `chave_ausente`,
  `tipo_none`, `tipo_errado`, `indice`, `valor_invalido`, `unicode`, `json`,
  `timeout`, `rede`, `subprocesso` — e `desconhecida`, dita com todas as letras,
  quando nada casa;
- se aquele módulo **tem teste** (e avisa quando não tem, porque aí o ensaio pode
  passar sem cobrir o caminho que quebrou).

**`conserto.dossie`** — junta erro + trecho + **a docstring do próprio módulo**
(é o “procurar para que serve” que você citou) + o teste + as guardas. É o que faz
a correção sair em uma tentativa em vez de dez. Serve para mim, para você ou para
qualquer modelo.

**`conserto.propor`** — só com chave de IA: manda o dossiê ao provedor, recebe o
diff e passa pela **mesma régua** do `evolucao` (aplica? risco? guardas?). Não
escreve nada. Sem chave, **recusa** com o motivo: *inventar correção é pior que
não corrigir*.

No chat: `por que deu erro` → diagnóstico; `me dá o dossiê do erro` → dossiê;
`conserta o erro` → proposta (com confirmação). E “deu erro no site que abri”
continua indo para a busca normal — ali não há traceback.

## 3. O que não vai existir, e por quê

**Corrigir sem inteligência.** Não há regra determinística que escreva o patch
certo de um `KeyError` qualquer: escolher o padrão exige entender o domínio. É por
isso que o passo da proposta depende de um modelo — e que ele **recusa** em vez de
chutar.

**Patch se aplicando sozinho com a API rodando.** `evoluir.promover` exige token,
hash e árvore limpa; o processo precisa reiniciar depois. Isso é de propósito: um
patch que derruba o processo derrubaria junto o que sabe reverter.

## 4. O laço completo

```
erro real → storage/erros.jsonl (automático)
          → conserto.diagnosticar (onde, o quê, por quê)
          → conserto.dossie (código + docstring + teste + guardas)
          → conserto.propor (diff, só com chave, já validado)
          → evoluir.ensaiar (suíte real numa cópia; verde libera token)
          → evoluir.promover (backup + token de uso único)
          → reiniciar a API → evoluir.reverter se não prestar
```

Cada seta é uma decisão sua. Nada pula etapa.

## 5. Detalhe honesto

Eu não consigo testar o `conserto.propor` de verdade: no ambiente de
desenvolvimento não há chave de IA, e chamar provedor em teste seria usar a sua
cota. O que está testado é o contrato — provedor falso respondendo diff, diff
sendo lido pela régua do `evolucao`, recusa sem chave, “SEM PATCH” e diff mal
formado. Com chave, o primeiro uso real é seu.

## Testes

- `pytest server/tests` → **3.090 passed, 7 skipped**.
  - `test_conserto.py`: **31 novos** — diário gravando/listando/podando,
    quadro certo entre stdlib e projeto, 12 causas parametrizadas, trecho lido do
    arquivo real, dossiê < 12 KB com docstring e guardas, proposta sem chave
    recusada, diff validado pela régua (com o arquivo vivo byte a byte igual) e o
    app registrando a falha **sem** vazar detalhe no HTTP.
  - `test_agente_local.py`: +1 — as frases de conserto no chat, e o que **não**
    deve virar conserto.
- `vitest` → 128; `tsc -b` limpo; `build:embutido` ok.
- Skills: **310** (+3).
