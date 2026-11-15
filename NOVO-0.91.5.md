# JARVIS 0.91.5 — o dossiê inteiro na tela, e a falha da IA com nome e causa

Sua execução no `D:\JARVIS` funcionou:

```
2. conserto.dossie — feito
   voltou: … - exceção: IndexError: list index out of range - arquivo: `server/app.py` lin…
```

O diagnóstico achou o tipo, o arquivo e a linha. A 0.91.4 fez o que devia. Mas
a saída mostrou dois defeitos que só aparecem quando a máquina funciona de
verdade.

## 1. O dossiê saía cortado

O produto do passo 2 é o texto do dossiê. Na tela ele aparecia até 160
caracteres e depois `…`. Ou seja: o maestro fazia o trabalho e entregava um
resumo do trabalho, não o trabalho. Se você quisesse colar aquilo num modelo
para pedir o patch — que é o uso real —, não tinha o que colar.

Agora o terminal imprime o documento inteiro, entre marcadores:

```
2. conserto.dossie — feito
   voltou: # Dossiê de conserto — JARVIS - versão: 0.91.5 …

   --- conserto.dossie (documento completo) ---
   # Dossiê de conserto — JARVIS
   - versão: 0.91.5
   - exceção: IndexError: list index out of range
   - arquivo: `server/app.py` linha 318 (função `_autorizacao_do_dono`)
   - causa classificada: **indice** — a lista acabou antes do índice esperado
   ## Código em volta da linha
       314 |             preencheu = True
   >>  318 |             dados["confirmacao"] = pendentes[0]["confirmacao"]
   --- fim de conserto.dossie ---
```

O passo declara `mostrar_texto=True`, então é só o passo que produz documento
que abre inteiro. Diagnóstico e busca continuam resumidos: mostrar tudo de
tudo viraria parede de texto.

No chat (a API) o texto continua resumido — quem precisa do inteiro é quem está
no terminal, com a mão no teclado.

## 2. "O provedor não respondeu: AIUnavailable"

Essa era a resposta toda. `AIUnavailable` é o **nome da exceção**, não uma
explicação. E o pior: a exceção já trazia a frase certa e ela foi jogada fora.

O `AIUnavailable` do JARVIS foi escrito justamente para poder ser mostrado sem
segredo, e diz coisas como:

- "a chave foi recusada pelo provedor (HTTP 401). Gere uma nova em … "
- "as 2 chaves estão no limite agora (HTTP 429). Espere alguns minutos …"
- "não foi possível conectar ao provedor de IA."

Agora o maestro mostra isso:

```
Parei no passo 3 (conserto.propor): a skill rodou mas não concluiu (proposto=false):
O provedor não respondeu (AIUnavailable): as 2 chaves estão no limite agora (HTTP 429).
Espere alguns minutos ou acrescente outra chave ao .env.
```

É a diferença entre "deu erro" e "a cota acabou, espere ou ponha outra chave".

## O que muda para você na prática

Você já tinha chave configurada — por isso a mensagem mudou de "sem chave" para
"AIUnavailable". Depois desta versão, a mesma execução vai dizer **qual** é o
problema da chave: recusada, no limite, ou sem conexão.

## Testes

Quatro novos: dois no conserto (falha do provedor mostra a causa; falha sem
mensagem ainda mostra o tipo) e dois no maestro (o documento aparece inteiro no
terminal; só o passo que declara é aberto).
