# Evolução — o código que prova antes de se alterar

A 0.32.0 entrega a única camada do JARVIS que pode mudar o próprio código-fonte. Ela existe porque o pedido foi explícito: *"sim, pode fazer, e estou ciente dos meus pedidos e responsabilidades"*. Este documento descreve o que a camada faz, o que ela recusa fazer e onde o risco continua sendo seu.

A regra que organiza tudo: **nenhum byte da árvore viva muda antes de o patch provar que aplica, que não abre buraco e que a suíte passa numa cópia.**

## As oito skills

| Skill | Efeito | Trava extra | Para que serve |
|---|---|---|---|
| `evoluir.mapa` | leitura | token | Inventário do projeto: arquivos, linhas, módulos, testes, quem não tem teste |
| `evoluir.proposta` | leitura | token | Prova hunk por hunk se o diff aplica no arquivo como ele está agora |
| `evoluir.risco` | leitura | token | Pontua de 0 a 100: treze padrões de perigo, guarda removida, arquivo central |
| `evoluir.guardas` | leitura | token | Confere as dez leis do projeto contra o diff |
| `evoluir.ensaiar` | executa código na cópia | token + `JARVIS_HOST_EVOLUIR=1` + `confirmed` | Aplica o patch numa cópia e roda o pytest de verdade |
| `evoluir.promover` | **escreve no código vivo** | token + variável + `confirmed` + ensaio aprovado | Backupeia e aplica o patch já ensaiado |
| `evoluir.reverter` | escreve (restaura) | token + variável + `confirmed` | Devolve os arquivos do backup |
| `evoluir.regras` | leitura | nenhuma | Publica o fluxo, as travas, as guardas e as recusas |

As sete primeiras exigem o token de `storage/host-token.txt`, impresso no terminal onde a API subiu. O catálogo é público de propósito: esconder o contrato não protege ninguém.

## O ciclo de sete passos

```
1. mapa       onde a mudança cai          (nunca altera)
2. proposta   o diff aplica?              (nunca altera)
3. risco      o patch abre buraco?        (nunca altera)
4. guardas    as dez leis continuam?      (nunca altera)
5. ensaiar    a suíte passa na cópia?     (executa, mas fora do vivo)
6. promover   árvore limpa + hash igual   (É O ÚNICO QUE ESCREVE)
7. reverter   volta pelo backup           (desfaz o 6)
```

Os passos 2 a 4 são independentes entre si e podem rodar em qualquer ordem; os passos 5 e 6 são uma corrente — o ensaio devolve um token de 8 caracteres que a promoção exige, e o token só vale para aquele diff.

## As seis travas

| # | Trava | Padrão | Vale para |
|---|---|---|---|
| 1 | Token de host | obrigatória | as sete skills com token |
| 2 | `JARVIS_HOST_EVOLUIR=1` | desligada | ensaiar, promover, reverter |
| 3 | Ensaio aprovado | obrigatória | promover |
| 4 | Hash idêntico ao ensaiado | obrigatória | promover |
| 5 | Árvore git limpa no arquivo | obrigatória | promover |
| 6 | Backup antes da escrita | obrigatória | promover |

A trava 2 é a mais importante na prática: **sem a variável de ambiente, a camada inteira fica somente leitura**, mesmo com o token na mão. Quem opera a máquina é quem liga.

A trava 4 fecha o intervalo entre ensaiar e promover. Se você (ou qualquer processo) editar o arquivo depois do ensaio, o SHA-256 não bate e a promoção recusa — o patch foi provado contra um arquivo que não existe mais.

A trava 5 é o que impede a camada de comer trabalho não commitado. Se o arquivo já está modificado no git, promover recusa: o backup guardaria a versão modificada e o diff seria aplicado por cima de algo que você não revisou.

## O ensaio, em detalhe

`evoluir.ensaiar` copia `server/`, `pytest.ini` e os `requirements*.txt` para `storage/evolucao/ensaios/<id>/`, aplica o patch **na cópia** e roda:

```
python -m pytest <alvos> -o addopts= -q --no-header -p no:cacheprovider
```

Três detalhes que custaram correção:

- `-o addopts=` neutraliza o `addopts = -q` do `pytest.ini`. Sem isso, `-q` vira `-qq`, a linha de resumo desaparece e a suíte verde é lida como reprovada.
- Código de saída 4 (erro de uso) e 5 (nada coletado) têm finding próprio. Uma suíte que não coleta nada aprovaria qualquer patch.
- O alvo dos testes passa por allowlist de caracteres e recusa `..`: não é um shell disfarçado.

Aprovação exige `codigo == 0`, `failed == 0` e `passed > 0`. Só então sai o token de confirmação (8 hex, TTL de 900 s, uso único).

## A promoção, em detalhe

1. Revalida o token de confirmação e o consome.
2. Relê o diff do ensaio e confere o SHA-256 de cada arquivo contra o que foi ensaiado.
3. Confere `git status --porcelain` **do arquivo** — só daquele caminho, não do repositório inteiro.
4. Copia cada arquivo para `storage/evolucao/backups/<ensaio>/`.
5. Só então escreve. Registra em `storage/evolucao/audit.jsonl`.
6. Devolve `reinicio_pendente: true` e **não reinicia nada**.

A camada nunca cria branch e nunca commita. A árvore fica modificada de propósito: o `git diff` é a sua revisão, e o commit é uma decisão humana. Se o resultado não servir, `evoluir.reverter <ensaio>` restaura os arquivos do backup.

## O que ela recusa

- **Arquivos fora de `server/`, `src/`, `docs/`, `public/` e `tests/`.**
- **Nome ou sufixo de credencial**: `.env`, `.key`, `.pem`, `.pfx`, `.p12`.
- **Diretórios proibidos**: `.git/`, `storage/`, `node_modules/`, `.venv/`, `dist/`, `cofre/`, `uploads/`.
- **Caminhos com `..` ou absolutos.**
- **Extensões fora da lista** (`.py`, `.ts`, `.tsx`, `.css`, `.md`, `.json`, `.txt`, `.ini`, `.html`, `.toml`, `.example`).
- **Diff acima de 900 KB**, mais de 40 arquivos ou mais de 200 hunks.
- **Gerar o patch**: a camada não escreve código. O diff é entrada sua ou de um modelo externo.
- **Rodar a interface**: só pytest é ensaiado. Vitest e build do front não passam pelo ensaio — mudança em `src/` é promovida com prova apenas textual.
- **Reiniciar o processo.**
- **Desfazer commit.**

## Onde o risco continua

Isso precisa estar escrito sem enfeite:

1. **A suíte pega regressão, não má intenção.** Um patch pode passar em 1.830 testes e ainda abrir uma porta, vazar um arquivo ou apagar um backup. As guardas G1–G10 e o `risco` cobrem os padrões que conhecemos; o que não está no padrão passa.
2. **O ensaio executa código novo.** Um `conftest.py` malicioso roda com o usuário da API antes de qualquer aprovação. Ensaiar já é executar.
3. **"Passou nos testes" ≠ "é boa mudança".** Verde prova que nada quebrado quebrou. Não prova que a mudança é correta, necessária ou segura.
4. **O backup está no mesmo disco.** Reverter protege contra erro de patch, não contra `rm -rf`, disco cheio ou criptografia por ransomware.
5. **A responsabilidade é de quem promove.** O desenho reduz o dano de um patch ruim; não transforma um patch malicioso em seguro.
