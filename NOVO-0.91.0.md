# JARVIS 0.91.0 — o maestro: um pedido, vários passos

Até ontem, cada pedido valia por **uma** skill. "Pesquisa o clima e guarda num
arquivo" tem duas coisas dentro, e a resposta honesta era: peça uma, depois a
outra, e leve o resultado da primeira na mão.

Agora existe quem encadeie. E o jeito como ele faz isso é a parte importante.

## O que ele faz

Você diz o objetivo em português:

```
pesquisa o clima de Palhoça e guarda em clima.txt
```

E ele responde com a fila, antes de fazer qualquer coisa:

```
Plano para: pesquisa o clima de Palhoça e guarda em clima.txt
Procedimento: Pesquisar na web e guardar num arquivo (pesquisar-guardar)

1. sistema.rede
   por quê: buscar e ler as fontes antes de escrever qualquer coisa
2. files.write [tem efeito: só com autorização]
   por quê: gravar o que foi encontrado, com as fontes junto
   recebe do passo anterior: content (do passo 1)

Um dos passos tem efeito colateral. Nada foi executado: sem autorização, a fila para antes dele.
```

E, autorizando, ele roda na ordem — e diz onde parou:

```
1. sistema.rede — feito
2. files.write — feito
Todos os 2 passos rodaram.
```

Se o passo 1 falha, o passo 2 **não roda**. A resposta é:

```
Parei no passo 1 (sistema.rede): SkillError: Rede desligada. ...
```

## As quatro decisões que fazem isso não virar bagunça

**1. Nada de modelo no planejamento.** O plano não é "gerado": é **declarado**.
Cada procedimento é uma lista fixa de passos, escrita à mão, com a skill
nomeada. Pedido igual dá plano igual — 20 vezes, sempre o mesmo. Quem inventa
passo é o modelo, e modelo inventa passo errado com muita confiança.

**2. Só skill do catálogo.** Um teste percorre os 4 procedimentos e confere que
toda skill citada existe no registro. Se alguém renomear `files.write`, o teste
quebra antes de o usuário ver o erro.

**3. Plano primeiro, sempre.** `maestro.planejar` **não executa nada** — nem a
leitura de rede, que é inofensiva. Não é economia: é a diferença entre ver o que
vai acontecer e descobrir depois.

**4. Passo com efeito pausa a fila.** Abrir, baixar, gravar, digitar: nada roda
sem `autorizar=true`. Sem autorização, os passos de leitura rodam e a fila para
**antes** do efeito — e diz qual passo é.

## Como um passo recebe o resultado do anterior

Três formas, e só três. Nada de expressão, nada de `eval`:

| forma | o que faz | exemplo |
|---|---|---|
| `$pedido` | o pedido inteiro | `consulta: "$pedido"` |
| `$slot` | um dado tirado do pedido | `path: "$arquivo"` → `clima.txt` |
| `$1.campo` | o campo `campo` da saída do passo 1 | `repo: "$1.slug"` |
| `{{1.campo}}` | o mesmo, dentro de um texto | `"# {{1.resumo}}"` |

Uma referência que não existe vira **vazio** — e o passo é **barrado** antes de
rodar, se aquele campo era obrigatório. Ir com campo vazio seria pior: gravaria
um arquivo com o nome certo e o conteúdo errado.

Existe um teste que tenta `$1.__class__` e `$1.slug()` justamente para provar
que isso não é um interpretador disfarçado.

## Os quatro procedimentos de estreia

| id | objetivo | passos |
|---|---|---|
| `pesquisar-guardar` | pesquisa e guarda num arquivo | `sistema.rede` → `files.write` |
| `baixar-repositorio` | baixa do GitHub e analisa | `repos.baixar` → `repos.analisar` |
| `consertar-erro` | diagnostica o erro e monta o dossiê | `conserto.diagnosticar` → `conserto.dossie` → `conserto.propor` |
| `escrever-no-programa` | abre o programa e escreve | `mesa.ditar` |

São poucos de propósito. Um catálogo de cinquenta procedimentos mal testados é
pior que quatro que funcionam — e o usuário descobre a diferença do jeito caro.

## Como usar

No PC, pelo arquivo que já existe:

```
py arvore_sonda.py --catalogo
py arvore_sonda.py --orquestrar "conserta o erro do meu programa"
py arvore_sonda.py --orquestrar "conserta o erro do meu programa" --autorizar
```

Pela API, como skill:

```
maestro.catalogo    — o que ele sabe encadear
maestro.planejar    — o plano, sem executar
maestro.executar    — roda com autorizar=true
```

E no chat: um objetivo de **dois ou mais passos** devolve o plano na hora. Um
pedido de um passo só continua indo para o ranking normal — "escreve oi no
bloco de notas" segue indo para o `mesa.ditar`, que já foi provado no PC. O
maestro não rouba o que já funciona.

## O que ele não faz (e não é esquecimento)

- **Não inventa procedimento.** Objetivo fora do catálogo recebe "não tenho
  procedimento para esse pedido" e a lista do que existe.
- **Não aplica patch.** `conserto.propor` propõe; aplicar é outra decisão.
- **Não recupera de erro.** Um passo que falha para a fila, sempre.
- **Não aprende sozinho.** Procedimento novo entra por código, com teste — não
  por conversa.

## O que ainda não foi medido

- **Nenhum procedimento rodou no PC dele ainda.** O que está provado é o
  planejamento, a parada por autorização e a parada por erro — em teste, com
  registro de mentira e com registro real (o `files.write` + `files.read`
  gravam e releem de verdade na suíte).
- **`conserto.*` sem erro no texto** usa o último erro do diário. Se o diário
  estiver vazio, o passo 1 pode devolver um diagnóstico vazio — e o maestro vai
  seguir para o passo 2 com isso. É o primeiro lugar a medir no PC.
- **Tempo total.** Cada passo tem o próprio limite, mas a fila inteira não tem
  um teto próprio. Um procedimento de 3 passos pode levar 3× o limite de um.

## Números

- **325 skills** (322 + `maestro.catalogo`, `maestro.planejar`, `maestro.executar`)
- **4 procedimentos** declarados
- **47 testes** no `test_maestro.py`
- Versão **0.91.1** em 17 arquivos, manifesto regerado
