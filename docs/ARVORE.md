# A árvore da janela: ver os elementos sem tocar (0.82.0)

Etapa 1 do que o [`vercel-labs/agent-desktop`](ANALISE-AGENT-DESKTOP.md) propõe.
O `mesa.py` antigo só via **títulos** de janela e clicava por coordenada que você
ditava — sem saber se acertou. Aqui o JARVIS passa a **ler** o que a janela
publica sobre si mesma.

## O maestro: juntar os degraus num objetivo (0.91.0)

As etapas anteriores deram **olhos** (ler a árvore) e **mãos** (abrir, escrever,
conferir). Faltava a cabeça que decide a ordem — e ela chegou com uma escolha
deliberada: **não usar modelo**.

O motivo é o mesmo desta semana inteira. Um passo errado com confiança custa
mais que um passo a menos. Então o plano não é gerado, é **declarado**:

```python
Procedimento(
    id="consertar-erro",
    precisa=("erro",),
    grupos=(("conserta", "arruma", "diagnostic", "corrig"),),
    passos=(
        Passo(skill="conserto.diagnosticar", campos={"erro": "$erro"}),
        Passo(skill="conserto.dossie",       campos={"erro": "$erro"}),
        Passo(skill="conserto.propor",       campos={"erro": "$erro"}),
    ),
)
```

`precisa` são substrings que precisam aparecer todas; `grupos` são grupos em que
**pelo menos uma** de cada grupo precisa aparecer. É assim que "salva" e
"guarda" viram a mesma intenção sem uma lista de sinônimos solta: o
procedimento exige *um* verbo de pesquisa **e** *um* de gravação.

### Por que grupo, e não uma lista só

"procura passagens e salva no arquivo" só casaria com `("guard",)` se eu
tivesse escrito "salva" dentro da lista — e amanhã "anota" quebraria de novo. O
primeiro teste que escrevi falhou exatamente aqui. Grupo é a forma certa: cada
intenção é uma condição, e todas as condições precisam valer.

### O que o maestro **não** faz, e é de propósito

- não abre shell nem interpreta expressão livre (`$1.__class__` devolve vazio —
  e há teste para isso);
- não escolhe skill por modelo;
- não segue depois de um erro;
- não grava arquivo vazio quando a busca voltou sem nada.

### 0.91.1 — a sonda passou a ler o `.env`

Achado antes do primeiro teste no PC: o `arvore_sonda.py` roda solto no
terminal e **não** carregava o `.env` — só o `server/app.py` carregava. Com
`JARVIS_HOST_REDE=1` no arquivo, a fila parava no passo 1 dizendo "Rede
desligada". Medido no sandbox: antes, mensagem de configuração; depois, falha de
rede de verdade. O mesmo valia para `JARVIS_FILES_ROOT`, que decidiria em qual
pasta o maestro grava.


### 0.91.2 — passo que não leu nada não conta como feito

Olhando a execução de verdade (e não só o plano): `conserto.diagnosticar`
devolvia `{"lido": false, "motivo": "Não há erro no diário…"}` e o maestro
seguia para o dossiê e para a proposta, terminando com "todos os 3 passos
rodaram". Dossiê de erro que ninguém leu.

Agora o passo declara `exigir="lido"`, e o maestro confere **antes** de aceitar
o passo: se voltar falso, a fila para com `nao_confirmado` e a saída da skill no
motivo. Declarado, não adivinhado — skill sem campo de confirmação não tem
`exigir` e nada muda.

Junto: cada passo passou a mostrar `voltou: …` (antes só dizia "feito"), o plano
avisa `só vale se voltar lido=true`, e o `$erro` do conserto corta no
`Traceback` quando você cola o erro junto com a frase.


### 0.91.3 — a primeira execução no PC do dono

Medido no `D:\JARVIS`, em 0.91.2. Três defeitos, os três reais:

| o que apareceu | por que era defeito | correção |
|---|---|---|
| `fonte=colado` sem erro colado, `exceção: :` | o pedido inteiro ia como traceback; a skill dizia `lido: true` e o dossiê saía vazio | `erro_do_pedido` só devolve algo que **pareça** erro; senão vazio, e a skill cai no diário |
| `versão: 0.75.0` no dossiê | `conserto.VERSAO` era a versão em que o módulo nasceu | dossiê usa `atualizacao.VERSAO`; teste recusa o `0.75.0` |
| `3. conserto.propor — feito` sem propor | o provedor falhou dentro da skill, sem exceção | passo declara `exigir="proposto"` |

E a parada ganhou **dica declarada no passo**, para a resposta dizer o que fazer
e não só o que faltou:

```
Parei no passo 1 (conserto.diagnosticar): a skill rodou mas não concluiu (lido=false): …
O que fazer: o diário de erros não tinha nada e o pedido não trouxe erro. Cole o traceback junto com o pedido.
```


### 0.91.4 — traceback numa linha só

Achado ao preparar o comando de teste para o PC, antes de mandar. O
`diagnosticar` procurava o tipo da exceção com `^...$` em modo multilinha, então
um traceback colapsado numa linha (terminal estreito, chat, ou o maestro
montando o texto) não tinha `KeyError` no começo de linha: o dossiê saía com
`exceção: :` e causa `desconhecida`.

Agora, se o começo de linha não achar, a busca fica com a **última** ocorrência
em qualquer posição — num traceback, a exceção é a última coisa escrita. Dois
testes fixam: linha única acha e classifica, várias linhas continua igual.


### 0.91.5 — o dossiê inteiro e a falha da IA com causa

Duas coisas que só aparecem quando a máquina funciona: na primeira execução em
que o diagnóstico **achou** o erro (`IndexError`, `server/app.py` linha 318), o
dossiê saiu cortado em 160 caracteres e a falha do passo 3 saiu como
`AIUnavailable` — o nome da exceção, não a explicação.

- `Passo.mostrar_texto`: o terminal imprime o documento inteiro entre
  marcadores; a API continua resumida. Só o passo que produz documento abre.
- `conserto.propor` passou a usar o `str()` do erro: `AIUnavailable` existe para
  poder ser mostrada sem segredo, e diz se a chave foi recusada, se está no
  limite ou se é rede.


### 0.91.6 — o 400 do provedor

No PC: o dossiê saiu inteiro (missão cumprida) e o passo 3 parou com
`O provedor não respondeu (AIUnavailable): o provedor de IA respondeu com HTTP 400.`

400 não é chave (401) nem cota (429): é pedido recusado. E o motivo que o
provedor mandou estava sendo **descartado** — só dois formatos de corpo eram
lidos (`error.message` e `message`). Formato desconhecido virava mensagem vazia.

- `detalhe_do_corpo` passou a aceitar `detail` e `error` como texto, e a mostrar
  o corpo cru (limpo, cortado) quando nada casa.
- A frase do 400 diz o que fazer e aponta `conferir-ia.py`.
- `conferir-ia.py`: script novo que lista os modelos que **a chave vê**
  (`GET /models`, sem gastar geração) e diz se o nome configurado está lá.

Causa mais provável, e é de graça confirmar: nome de modelo de um provedor com
chave de outro — `llama-3.3-70b-versatile` (Groq) × `meta-llama/llama-3.3-70b-instruct`
(OpenRouter). A chave está boa; o nome é que não existe ali.


### 0.91.7 — a chave com Ctrl+V dentro

O `conferir-ia.py` respondeu antes de qualquer chamada de rede:
`chaves: 1 configurada(s) ['\x16…\x16']` — 4 caracteres, dois deles `\x16`.

`\x16` é o código de controle do **Ctrl+V**. No console do Windows 10
(10.0.14393) o Ctrl+V **não cola**: escreve o caractere. A chave foi gravada
com lixo nas pontas, o provedor respondeu 400, e a investigação ia para o
modelo — lugar errado.

- `sem_controle()` em `server/ai.py`, `server/chaves.py` e `configurar-chave.py`:
  caracteres de controle saem na leitura (preservando `\t\n\r` — tirar a
  quebra de linha cola linhas e a extração pega chave a mais).
- `chaves.suspeitas()`: diz, em português, que a chave não tem cara de chave e
  que o Ctrl+V foi o culpado; `estado()` devolve a lista.
- `conferir-ia.py` para **antes** da rede quando há suspeita.
- `configurar-chave.py` limpa ao digitar e avisa quando removeu algo.

Colar no console antigo: **botão direito do mouse**, não Ctrl+V.


### 0.91.8 — o script passa a dizer onde pegar a chave

Medido no PC: `configurar-chave.py` abria com `Provedor [OpenRouter]:` e nenhuma
palavra sobre onde criar a chave. Quem nunca fez isso fica parado no prompt —
foi exatamente a pergunta do dono. O endereço já estava no catálogo
(`provedores.onde`), só não era impresso.

- `guia_do_provedor()` + `mostrar_guia()`: endereço, passo a passo, aviso do
  botão direito (Ctrl+V não cola no console antigo) e o modelo sugerido.
- O endereço reaparece no prompt da chave, quando a tela já rolou.
- Provedor fora do catálogo não quebra: só não mostra endereço.


### 0.91.11 — o duplo clique (nenhum comando para decorar)

Resposta ao “não entendi, só atualizei”: o caminho existia, mas exigia lembrar
um comando de duas linhas e uma opção. Agora é um arquivo na pasta:
`pegar-chave.bat`.

Ele faz, na ordem: abre `openrouter.ai/keys`; mostra no console os quatro
cliques do site (Create Key → nome → Create → COPIAR); espera; lê a área de
transferência; grava. Se a leitura falhar, oferece tentar de novo sem fechar a
janela — o caso comum de copiar a chave depois de já ter apertado Enter.

Duas correções que vieram junto:

| antes | depois |
|---|---|
| gravar chamava o questionário inteiro (provedor, base, modelo) | com provedor já gravado, troca só a chave e diz o que manteve |
| `--pegar` lendo área vazia só dizia “não deu” | diz para copiar no site e rodar de novo |

O `.bat` é ASCII puro com CRLF, como os outros: o console antigo não desenha
acento e o Bloco de Notas não entende LF.


### 0.91.10 — o mouse no botão (medido antes de clicar, e com freio)

A pergunta do dono — “por que não clica no botão de copiar com o mouse?” — tinha
resposta técnica: até a 0.91.9 o executor só sabia pedir a **ação padrão do
elemento**. Quando a página não declara essa ação, ou quando a leitura veio da
UIAutomation (e a janela não publica MSAA), não havia o que fazer.

O que entrou:

| peça | regra |
|---|---|
| `arvore.dentro_da_janela` | o ponto do clique tem de cair dentro do retângulo da janela — conta pura, testada |
| `arvore_windows.clicar_fisico` | traz a janela para a frente, confere a posição, clica e **devolve o cursor** ao dono |
| `executar_ref(..., mouse=True)` | o clique por coordenada é o último degrau; sem `mouse`, continua só a árvore |
| `chave_web.PADROES_CONFIRMAR` | o botão do diálogo é “Create”, não “Create Key” |
| `chave_web.diagnostico` | diz se o botão tem **posição medida** (“o mouse acerta”) ou só nome |

O `--criar --autorizar` usa o mouse por padrão (foi o pedido); `--sem-mouse`
volta ao comportamento antigo. O `--ver` nunca clica.

Também consertou um erro silencioso: o retorno do clique era descartado, e um
passo que falhava fazia o script culpar o seguinte. Agora o primeiro que não dá
para ali, com o motivo do Windows.


### 0.91.9 — a chave pelo navegador (medir antes de clicar)

Pedido do dono: entrar no site, gerar a chave e salvar sozinho. Duas coisas
precisam ser ditas com clareza:

1. **A chave existente não é legível.** O OpenRouter mostra o valor uma vez, na
   criação, e depois só o prefixo mascarado. Não há o que coletar da página.
2. **Criar uma nova é automatizável em princípio** — clicar, nomear, criar,
   copiar, ler a área de transferência — mas depende de o Chrome publicar esses
   botões na árvore de acessibilidade, e isso **não foi medido**.

Por isso o script novo (`chave-no-navegador.py`) chega em três degraus:

| comando | o que faz | risco |
|---|---|---|
| `--pegar` | lê a área de transferência e grava | nenhum — só lê o que você copiou |
| `--ver` | lê a janela e diz quais botões existem | nenhum — não clica |
| `--criar --autorizar` | clica e cria uma chave nova na conta | cria credencial de verdade |

A regra de achar (normalizar, preferir nome curto, ignorar página errada) mora
em `server/chave_web.py` e é testada sem Windows; o driver fica no script.

O `--pegar` é a peça que resolve o problema real das últimas três versões: a
chave **não passa pelo console**, então não há Ctrl+V para virar `\x16` nem
seleção de mouse para cortar caractere.


## Etapa 3 fechada — do zero ao texto conferido (0.90.0)

Na máquina do usuário, com o Bloco de Notas **fechado**, um comando:

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas" --escrever "oi, mundo" --executar
```

```
Abri o Bloco de notas. Feito: digitar 'oi, mundo' em texto em 22,465 (970x69) (conferi: o texto está no campo)

janela:  notepad.exe — Sem título - Bloco de notas
alvo:    @95bc8c3d:e11  texto “”
onde:    22,465 (970x69)
fonte:   msaa   leitura: 95bc8c3d
como:    valor do campo (put_accValue, sem teclado)
abri:    C:\Windows\system32\notepad.exe
conferi: o texto está no campo.
```

A cadeia inteira, medida: **achar o executável → abrir → achar a janela nova →
esperar o campo → escrever → ler de volta e conferir.**

### O que ficou provado, e por qual caminho

| passo | como | confere? |
|---|---|---|
| achar o programa | PATH → System32 → App Paths | caminho impresso |
| abrir | `Popen(caminho)`; sem caminho, ShellExecute | janela do `pid` novo |
| escolher a janela | processo vence título; minimizada por último | sim |
| escrever | `put_accValue` (o 4º degrau) | texto de volta |
| chegar antes | `SetForegroundWindow` | sem mouse |

O caminho vencedor foi o **quarto degrau** — `put_accValue`. Neste Bloco de
Notas o foco não vem (nem no elemento, nem no campo inteiro), então o teclado
nunca seria usado. Foi bom ter os quatro: quem dependesse só de teclado estaria
parado até hoje.

### O que ainda não está provado

- **programas que não publicam o valor do campo.** Se um programa não expõe
  `accValue`, o quarto degrau não existe. Aí resta o `--mouse` (5º degrau) ou
  nada. Cada programa é uma medição, não uma suposição.
- **teclado de verdade.** Neste PC ele nunca chegou a rodar, porque o foco não
  vem. Em outro programa pode ser o caminho natural.
- **escrever no meio de um texto existente.** Ou é acrescentar no fim
  (`--acrescentar`), ou recusa. Editar o meio é outra etapa.

### E o agente escolhe essa skill sozinho

“escreve oi no bloco de notas” empatava em 0,56 com uma skill de memória —
empate é sorteio. As skills passaram a declarar **palavras-chave** (campo
`keywords`), que contam como termo forte na busca do agente local:

| frase | skill escolhida | nota |
|---|---|---|
| escreve oi no bloco de notas | `mesa.ditar` | 1.00 |
| abre o paint e escreve oi | `mesa.ditar` | 0.78 |
| leia a janela do notepad | `mesa.arvore` | 0.67 |
| quais janelas estao abertas | `mesa.status` | 0.75 |

## Depois de abrir, reler — e não trocar a janela nova pela velha (0.89.6)

Com o caminho do executável certo (0.89.5), faltavam dois furos que só
aparecem no momento exato em que o programa nasce:

1. **A lista de janelas ficava velha.** Ela era lida **antes** de abrir o
   programa — quando ele não existia. Depois de abrir, o plano e o retrato do
   erro falavam de uma janela que não era a que acabou de nascer. Agora a lista
   é relida depois da abertura.

2. **A sondagem roubava a janela recém-aberta.** Com mais de uma janela do
   programa, uma leitura em cada decide qual serve. Mas se um Bloco de Notas
   **antigo** também tem campo, ele vencia — e o texto iria para o arquivo
   errado, que pode ser o documento de alguém. A sondagem agora só vale para
   janelas que já existiam: **se eu acabei de abrir, a janela é a que eu abri.**

O teste `test_a_janela_aberta_nao_e_trocada_por_uma_antiga_com_campo` fixa
essa regra: dois Blocos de Notas, um com `relatorio`, outro recém-aberto — o
texto vai para o recém-aberto.

## Nome de gente × nome de arquivo (0.89.5)

O erro seguinte foi:

```
não achei bloco de notas no PATH, em C:\Windows nem no App Paths
([WinError 2] ...: 'bloco de notas')
```

`'bloco de notas'` — com aspas e tudo: **o nome falado usado como nome de
arquivo**. Duas camadas, dois vocabulários:

| camada | recebe | exemplo |
|---|---|---|
| `pc.abrir_programa` (API) | nome de gente | `bloco de notas` |
| `abrir` injetado (sonda) | executável | `notepad.exe` |

A 0.89.4 passou cada um para o lado errado. Não era programa ausente: era
argumento trocado — e a mensagem acusava o PC.

Agora cada camada recebe o que entende, e `abrir_direto` **tolera** o nome
falado (resolve em vez de falhar, porque quem chama nem sempre sabe o que tem
em mãos).

### O diagnóstico passou a responder duas perguntas

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas"
```

Se o programa não estiver aberto, ele diz **e** diz se está instalado:

```
  O Bloco de notas (notepad.exe) não está aberto.
  Instalado em: C:\Windows\System32\notepad.exe
```

ou

```
  E não achei notepad.exe no PATH, em %SystemRoot% nem no App Paths —
  o programa pode não estar instalado neste PC.
```

Uma rodada, as duas respostas. Sem precisar adivinhar qual metade falhou.

## “O Windows recusou abrir notepad.exe” — mentira minha (0.89.4)

Depois da 0.89.3 o terminal parou de ser confundido com o Bloco de Notas, e o
erro seguinte foi:

```
NÃO DEU: o Windows recusou abrir notepad.exe: [WinError 2] O sistema não pode
encontrar o arquivo especificado
```

Duas coisas erradas nessa frase:

1. **“o Windows recusou”** — ele não recusou nada. `FileNotFoundError` é
   subclasse de `OSError`, e o `except OSError` genérico veio antes: qualquer
   “não achei o arquivo” era reportado como recusa.
2. **“notepad.exe” sozinho não basta** — `subprocess.Popen(["notepad.exe"])`
   depende do PATH do processo. Neste Windows (10.0.14393) voltou WinError 2.

A correção é `caminho_do_programa`, que procura em três degraus:

| degrau | onde | por quê |
|---|---|---|
| 1 | `shutil.which` | respeita o PATH quando ele está certo |
| 2 | `%SystemRoot%\System32`, `SysWOW64`, raiz | onde o Windows guarda os próprios programas |
| 3 | registro `App Paths` | onde os instaladores registram o que não vai no PATH |

E se nada for achado, `abrir_sem_shell` cai para `os.startfile` — o mesmo
mecanismo do duplo clique (`ShellExecute`), que acha pelo App Paths. Nenhum
shell de verdade é usado: não existe linha digitada nesse caminho.

O plano também passou a mostrar **qual caminho** foi aberto:

```
  abri:    C:\Windows\System32\notepad.exe
```

## O terminal não é o programa (0.89.3)

O diagnóstico da 0.89.2 entregou o culpado na primeira linha:

```
Bloco de notas (notepad.exe) — 1 janela(s):
  C:\Windows\system32\cmd.exe - .venv\Scripts\python arvore_sonda.py
  --programa "bloco de notas"  —  12 elemento(s), sem campo
```

A “janela do Bloco de notas” era **o próprio terminal**. O título do `cmd` é a
linha de comando, e a linha de comando dizia `"bloco de notas"`. O casamento
por título achava o mensageiro e chamava de alvo.

Corrigido em três regras:

1. **processo vence título, sempre** — e o título só é usado quando o processo
   não veio;
2. **terminal nunca casa por título** (`cmd.exe`, `powershell.exe`,
   `conhost.exe`, `wt.exe`… o título deles é o comando);
3. **título só casa inteiro** — igual, começando ou terminando com o rótulo.
   “Como abrir o Bloco de notas” é um artigo, não o programa.

## A pergunta do mouse: três degraus, e o mouse é o último

“Por que ele não usa o mouse para ir na janela e clicar no Bloco de Notas?”

**Para chegar na janela, mouse não é necessário.** `trazer_para_frente` usa
`SetForegroundWindow` + `BringWindowToTop` — com o truque de
`AttachThreadInput` que o Alt+Tab usa por dentro. A janela vem para a frente
sem mover o ponteiro, e isso agora acontece sozinho antes de escrever.

**Para apertar algo, o mouse é o último degrau**, nesta ordem:

| grau | o que faz | precisa de mouse? | confere? |
|---|---|---|---|
| 1 | ação padrão do elemento (`accDoDefaultAction`) | não | não |
| 2 | foco no elemento e teclado (`accSelect`) | não | sim, lê de volta |
| 3 | foco no campo inteiro e teclado | não | sim |
| 4 | `put_accValue` no valor do campo | não | sim |
| 5 | **clique físico no centro medido** (`--mouse`) | **sim** | sim |

O degrau 5 existe desde a 0.89.3, com o nome certo: `clicar_fisico`. Ele só
entra quando pedido (`--mouse`), porque:

- mover o ponteiro mexe na máquina de quem está usando;
- a tela deste PC dá **toque fantasma** — o ponteiro pode ser levado embora
  entre o `mover` e o `clicar`;
- clique errado numa tela que a pessoa está usando pode apagar trabalho.

E a coordenada nunca é inventada: é o **centro da caixa que a leitura mediu**
(`caixa[0] + caixa[2] // 2`). Sem caixa medida, ele não clica — diz que não tem
posição.

## A janela minimizada publica 12 elementos (0.89.2)

Depois da 0.89.1, o usuário viu:

```
NÃO DEU: a janela do Bloco de notas está aberta, mas em 15s ela não publicou
nenhum lugar de escrever. ... 12 de 12 elemento(s) vieram com coordenada
```

Doze elementos, todos de moldura. Esse número tem nome: **janela minimizada**.
Na barra de tarefas o Windows só descreve a moldura — o campo não existe para a
leitura enquanto a janela está recolhida. Some-se a isso um Bloco de Notas
antigo, aberto desde as tentativas anteriores, e o JARVIS tinha duas janelas
do mesmo programa: uma recolhida, uma servindo, e nenhuma informação para
saber qual era qual.

Quatro correções:

1. **`pid` na lista de janelas.** Cada janela passa a dizer de que processo
   veio. Quando o JARVIS abre o programa, ele guarda o `pid` do processo que
   acabou de nascer e só aceita janela daquele `pid` — é a janela que ele
   abriu, não a antiga.
2. **`minimizada` na lista.** `IsIconic` é perguntado direto ao Windows. A
   escolha põe as abertas antes das recolhidas, em vez de pegar a primeira.
3. **Restaurar em vez de pedir clique.** Janela recolhida é restaurada com
   `ShowWindow(SW_RESTORE)` — sem mouse, sem coordenada, sem pedir nada a
   ninguém. Depois disso a leitura acha o campo.
4. **O erro mostra o retrato.** Em vez de “não achei lugar para escrever”, ele
   lista cada janela do programa: título, se está minimizada, quantos elementos
   e se tem campo.

E a sonda ganhou um diagnóstico direto:

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas"
```

```
  Bloco de notas (notepad.exe) — 2 janela(s):
    Sem título - Bloco de notas  —  49 elemento(s), tem campo @f14b5235:e11
    velho - Bloco de notas  —  minimizada, 12 elemento(s), sem campo

  1 aceita(m) escrita. Uma delas é a que o JARVIS usa.
```

## A janela que não era a janela (0.89.1)

A primeira tentativa real de `--programa` morreu assim:

```
NÃO DEU: não achei lugar para escrever nesta janela. a janela publicou só
moldura (barra de título, rolagem, botões de janela)... 12 de 12 elemento(s)
vieram com coordenada
```

Não era o Bloco de Notas. Havia **duas janelas `notepad.exe`** vivas — uma que
publica o campo e outra que publica só moldura — e o código pegava a
**primeira da lista**. Depois, para agir, **escolhia de novo** pela regra de
peso, podendo cair na outra. Escolher duas vezes é escolher errado uma vez.

Três correções:

1. **Quem acha, decide.** `ditar` passa o `handle` da janela que achou; a ação
   não escolhe outra. Janela que sumiu no meio vira erro claro, não sorteio.
2. **Várias janelas, uma serve.** Com mais de uma candidata, uma leitura em
   cada uma descobre qual publica campo antes de esperar 15 s na errada. E
   `escrever_na_janela` sem `handle` também tenta as outras janelas do mesmo
   processo antes de desistir.
3. **Esperar o campo, não a janela.** A janela do programa aparece antes de o
   campo existir. Reler até o campo nascer (até 15 s) evita dizer “esta janela
   não aceita escrita” meio segundo antes de ela aceitar.

O erro final agora repete o que a janela respondeu, em vez de só dizer “não
deu”.

## Do zero: abrir, esperar, escrever e conferir (0.89.0)

Até aqui o JARVIS escrevia numa janela **que já estava aberta**. Quem abria o
Bloco de Notas era você — e pedir isso é pedir trabalho a quem pediu que ele
fizesse o trabalho.

A 0.89.0 junta as duas peças que já existiam:

1. `pc.abrir_programa` — lista fechada (bloco de notas, paint, calculadora,
   cmd, powershell…), sem caminho livre;
2. `mesa_agir.escrever_na_janela` — acha o campo, escreve, confere.

E acrescenta o que faltava: **esperar a janela aparecer**. Abrir um programa e
ler a tela no mesmo instante é ler o vazio.

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas" --escrever "oi, mundo" --executar
```

```
  Abri o Bloco de notas. Feito: digitar 'oi, mundo' em texto em 476,472 (970x69) (conferi: o texto está no campo)

  janela:  notepad.exe — Sem título - Bloco de notas
  alvo:    @da9f5b32:e11  texto “”
  onde:    476,472 (970x69)
  fonte:   msaa   leitura: da9f5b32
  como:    valor do campo (put_accValue, sem teclado)
  conferi: o texto está no campo.
```

Se o programa já estiver aberto, ele usa a janela que existe e **não abre uma
segunda**. Se a janela não aparecer em 12 segundos, ele diz isso e para — não
fica esperando para sempre diante de uma tela parada.

### O que continua valendo

- **sem `--executar`, nada é aberto e nada é escrito** — abrir programa já é
  agir, e o plano diz o que faria;
- a lista de programas é fechada; o executável vem dela, nunca de um caminho
  digitado;
- **pela API**, `mesa.ditar` exige `JARVIS_HOST_PC=1` (quem chama é o modelo).
  Na sonda, quem autoriza é a linha que a pessoa digitou;
- nada de mouse, nada de foto da tela, e a leitura de volta sempre.

## Escreveu de verdade — pelo terceiro degrau (0.88.0)

Na máquina do usuário, a 0.87.1 escreveu:

```
  Feito: digitar 'oi, mundo' em texto em 378,542 (970x69) (conferi: o texto está no campo)
  como:    valor do campo (put_accValue, sem teclado)
  conferi: o texto está no campo.
```

O `oi, mundo` estava no Bloco de Notas. Mas o caminho vencedor foi o
**terceiro**: `put_accValue`. Nem `accSelect` no elemento, nem no campo inteiro,
deram foco neste Bloco de Notas — e o JARVIS não digitou às cegas: escreveu
direto no valor e **conferiu lendo de volta**.

Isso também explica por que a 0.86.0 falhava: não era o programa recusando
foco, era o índice trocado; mas mesmo com o índice certo o foco não vem neste
controle. Quem depende de teclado teria ficado sem escrever.

### O problema que aparece na segunda vez

`put_accValue` **substitui** o conteúdo. Na primeira vez o campo estava vazio.
Na segunda, ele já tem `oi, mundo` — e escrever por cima apagaria o que já
estava lá.

Antes, o JARVIS recusava: *"o campo já tem texto e eu não sobrescrevo o que não
escrevi"*. Recusar está certo, mas não resolve — a pessoa quer continuar
escrevendo.

Agora ele lê o que existe e escreve `o que existe + o novo`, e diz o que fez:

```
  Feito: digitar ' de novo' em texto em ... (conferi: o texto está no campo)
  como:    valor do campo, acrescentado ao que já havia
```

Isso só acontece com `--acrescentar`. Sem a opção, continua recusando — porque
**acrescentar por conta própria mudaria o significado do que está escrito**, e
isso é decisão de quem escreveu, não minha.

## O foco que nunca foi pedido (0.87.1)

Na primeira tentativa de verdade, a tela do usuário disse:

```
Não foi feito: digitar 'oi, mundo' em texto em 339,298 (970x69) — o elemento
recusou o foco (accSelect). Sem foco, digitar iria para outra janela — parei.
```

O Bloco de Notas não recusou nada. **O índice da vtable estava errado.**
`IAccessible` tem, depois dos métodos de `IDispatch`:

| índice | método |
|---|---|
| 20 | `get_accDefaultAction` |
| **21** | **`accSelect`** |
| 22 | `accLocation` |
| 23 | `accNavigate` |
| **25** | **`accDoDefaultAction`** |
| 27 | `put_accValue` |

A 0.86.0 usava **21** para `accDoDefaultAction` e **23** para `accSelect` — um
a mais, outro a menos. Ou seja: o "pedido de foco" chamava `accNavigate`, que
devolve `S_FALSE`, e o JARVIS contava isso como recusa do programa. Um erro de
diagnóstico apresentado como se fosse do Bloco de Notas.

### E a escrita agora tem três degraus

1. **foco no elemento exato** (`accSelect`) + teclado;
2. **foco no dono** — o campo inteiro, quando o texto é filho simples;
3. **`put_accValue`** — escreve no valor do campo, sem teclado e sem foco.

O teclado só é usado quando o Windows confirma que o foco está **dentro da
janela alvo** (`GetGUIThreadInfo` → `hwndFocus` → sobe pelos pais). Se não
está, ele não digita às cegas: dizer "digitei" e ter digitado noutro programa
seria pior do que não fazer nada.

E depois de digitar, ele **lê o campo de volta** e diz o que viu:

```
  Feito: digitar 'oi, mundo' em texto em 445,577 (970x140) (conferi: o texto está no campo)
```

`put_accValue` substitui o conteúdo, então só é usado quando o campo está
vazio — sobrescrever o que a pessoa escreveu para "dar certo" é destruir
trabalho.

## Escrever sem copiar ref nenhum (0.87.0)

A etapa 2 pediu um `ref`, e o usuário colou o marcador que eu tinha escrito:

```
--ref @SEU_REF_AQUI
```

A recusa funcionou (o ref não existia) — mas o erro era do comando: pedir para
copiar um código de uma saída para a linha seguinte é trabalho que não devia
existir. O JARVIS já sabe apontar onde se escreve.

Agora:

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --escrever "oi, mundo"
```

```
  Ação pronta (nada foi feito): digitar 'oi, mundo' em texto em 445,577 (970x140)

  janela:  notepad.exe — Sem título - Bloco de notas
  alvo:    @c7aa400c:e11  texto “”
  onde:    445,577 (970x140)

  repita o comando com --executar para fazer de verdade.
```

E com `--executar`, escreve. O `--ref` continua existindo para quem quer
apontar um elemento específico (clicar num botão, por exemplo) — mas para
escrever, ninguém precisa mais dele.

`mesa.agir` no chat ficou igual: `ref` em branco na ação digitar, e ele acha o
campo.

### O erro agora fala português

O erro do ref saía como `{"erro": "..."}` numa linha só. Quem lê no terminal
não merece JSON sem ter pedido:

```
  NÃO DEU: não achei lugar para escrever nesta janela. a janela publicou só
  moldura... Rode `--provados` para ver quais janelas aceitam escrita.
```

`--json` continua entregando o formato de máquina para quem é máquina.

## Etapa 2: agir por `ref` (0.86.0)

A leitura do Bloco de Notas entregou o alvo:

```
texto  @4ab283d9:e11  em 227,559 (970x140)  (escreve aqui)
Onde escrever: @4ab283d9:e11 em 227,559 (970x140)
```

Com um alvo que tem nome, posição e `ref`, o braço pode existir:

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe" --ref @4ab283d9:e11 --acao digitar --texto "oi"
```

```
  Ação pronta (nada foi feito): digitar 'oi' em texto em 227,559 (970x140)

  janela:  notepad.exe — Sem título - Bloco de notas
  alvo:    @4ab283d9:e11  texto “”
  onde:    227,559 (970x140)
  fonte:   msaa   leitura: 4ab283d9

  repita o comando com --executar para fazer de verdade.
```

Sem `--executar`, **nada é tocado**. Com ele:

```
  Feito: digitar 'oi' em texto em 227,559 (970x140)
  como:    foco + teclado
```

### A regra que manda em tudo: `ref` não sobrevive à leitura

`ref` não é o nome do elemento — é o número dele naquela leitura. A tela muda.
Por isso **todo `agir` relê a janela antes** e procura o ref na leitura nova:

```
o ref @antigo:e12 não existe nesta leitura — ele deve ser de uma leitura
anterior, e a tela já mudou. Refs válidos agora: @4ab283d9:e11, ...
```

Um `ref` velho nunca vira alvo por acaso. É a diferença entre um braço e um
chute.

### Sem mover o mouse

A ação vem do próprio elemento:

| ação | como |
|---|---|
| clicar | `accDoDefaultAction` — a ação que o programa declara |
| sem ação padrão | `accSelect(TAKEFOCUS)` — o mesmo que um clique faria |
| digitar | foco no elemento, depois teclado (Unicode) |
| recusa de foco | **para** e diz; digitar sem foco iria para outra janela |

Isso não é preferência estética: no seu PC a tela não responde a toque e não há
mouse USB. Clicar por coordenada seria o único caminho que não funciona ali.

### O que é recusado, e por quê

| pedido | resposta |
|---|---|
| `ref` de leitura anterior | recusa e lista os refs válidos agora |
| moldura (Fechar, Minimizar, rolagem) | recusa — não é trabalhar no programa |
| digitar em botão | recusa com a ação que o elemento aceita |
| digitar sem texto | recusa |
| agir sem `--executar` | mostra o plano e para |

### No chat

`mesa.agir` faz o mesmo pelo JARVIS, com `executar` explícito e confirmação.
A etapa 2 deixou de ser promessa: é a skill `mesa.agir`.

## Os 26 acionáveis eram moldura (0.85.0)

A leitura do Bloco de Notas, no PC do usuário:

```
notepad.exe — Sem título - Bloco de notas: 49 elemento(s), 26 acionável(is) — fonte: msaa.
  SERVE para agir: 49 elemento(s) de árvore, 26 acionável(is) e 26 com nome ou escrita.
```

26 acionáveis. E olhando a árvore, quais eram: **IME, Minimizar, Maximizar,
Fechar**, os botões das duas barras de rolagem e uma alça. Moldura inteira.

O campo onde se escreve aparecia assim:

```
texto  em 227,559 (970x140)
```

Sem `ref`. A MSAA não dá ação padrão a um campo de texto, e a minha tabela de
papéis acionáveis não incluía `texto`. Ou seja: **o JARVIS não tinha como
digitar no Bloco de Notas**, e a prontidão dizia “dá para agir”.

### Duas contas erradas, uma causa

1. **A prontidão contava botão de janela como ação.** 26 botões de moldura
   passavam no critério “existe acionável com nome”. Agora moldura é
   reconhecida — por papel (barra de título, rolagem, alça, status, indicador)
   e por nome (IME, Minimizar, Maximizar, Fechar, “uma linha acima”…) — e
   **contamina os filhos**: os botões dentro da barra de título são moldura
   mesmo que o papel deles seja “botão”.

2. **O lugar de escrever não era acionável.** Papel `texto` (42) e `documento`
   (15) com caixa na tela passam a receber a ação **digitar** — e portanto um
   `ref`. Só quando a janela deixa: `get_accState` é consultado e
   `STATE_SYSTEM_READONLY` recusa. Um painel de log também é “texto”, e
   prometer escrita ali seria mentira.

A leitura do Bloco de Notas agora sai assim:

```
notepad.exe — Sem título - Bloco de notas: 49 elemento(s), 26 acionável(is) — fonte: msaa.
Todos os acionáveis são moldura (fechar/minimizar/rolagem); o lugar de escrever é @7625b028:e10.

  SERVE para agir: 49 elemento(s) de árvore, 1 onde se escreve — dá para agir por `ref`.
  Onde escrever: @7625b028:e10 em 227,559 (970x140)

  texto  @7625b028:e10  em 227,559 (970x140)  (escreve aqui)
```

E `--provados` diz onde cada janela aceita escrita:

```
  - notepad.exe — Sem título - Bloco de notas — escreve em 227,559
```

## O Chrome acordou (0.84.0)

A medição que virou o quadro, no PC do usuário, dois comandos seguidos sem
tocar em nada:

```
1ª rodada:  chrome.exe   Arena | Benchmar     3     3  nao   nao   uia  1.0
2ª rodada:  chrome.exe   Arena | Benchmar   104   104  sim   SIM   uia  0.9
```

A mesma janela. **3 elementos sem conteúdo** e, no comando seguinte, **104 com
conteúdo**. A diferença não foi código: foi o **Chrome ligando a
acessibilidade** ao perceber que alguém estava lendo.

É o comportamento conhecido dos navegadores: a árvore da página é construída
sob demanda, quando um programa de acessibilidade aparece. A primeira leitura
é o que acende a luz; ela chega antes de a luz acender.

### O erro que isso revelou — e que era meu

Eu li **uma vez** e concluí “não publica”. Era o primeiro estado, não o único.
Foi por isso que encerrei o Chrome na 0.83.0, com toda a convicção e errado.
Uma leitura não é uma medição quando o objeto muda de estado ao ser tocado.

### O que mudou

- `ler_janela` relê **uma vez**, 0,4 s depois, quando a primeira leitura vem
  sem conteúdo. Se a segunda trouxer conteúdo (ou mais elementos), ela vence e
  o resultado diz por quê:

  ```
  A janela só publicou o conteúdo na segunda leitura — é o caso do navegador,
  que liga a acessibilidade quando percebe alguém lendo.
  ```

- Janela que já vem com conteúdo **não paga** a segunda passada.
- `--provados` avisa quais acordaram, para ninguém achar que precisa rodar
  duas vezes:

  ```
  Acordaram na segunda leitura (o navegador liga a acessibilidade quando
  percebe alguém lendo — já vem lido, não precisa repetir):
    - chrome.exe — Arena | Benchmark & Compare the Best AI Mode
  ```

## Onde ele enxerga, e onde para (0.83.1)

Pergunta justa depois do veredito: **“mas ele não está reconhecendo onde fica
cada coisa?”** — sim, para a moldura. E a resposta nunca esteve na tela, o que
é um defeito meu: a posição era medida (`caixa`: x, y, largura, altura) e o
desenho não a mostrava.

Agora mostra:

```
janela “Chrome”  em 0,0 (1200x800)
  botão “Fechar”  @568600ab:e2  em 1180,5 (30x20)
  botão “Minimizar”  @568600ab:e3  em 1140,5 (30x20)
```

E a diferença fica escrita, não deduzida:

| o que | ele sabe? |
|---|---|
| a janela existe, e onde ela está na tela | **sim** — coordenada |
| barra de título, minimizar, fechar, rolagem | **sim** — nome, ação e coordenada |
| o que está **dentro** da página | **não** — o Chrome não publica |

`--provados` ganhou a coluna `posicoes`:

```
  janela aberta                    elementos  posicoes  conteudo  serve?  fonte  seg
  --------------------------------------------------------------------------------------
  chrome.exe     Arena | Benchmar         4         4  nao       nao     uia    1.2
  explorer.exe   Downloads               88        88  sim       SIM     msaa   0.9
```

`posicoes` alto com `conteudo` baixo quer dizer exatamente isto: **ele vê as
peças e onde estão; não vê o que elas são.** Moldura tem posição e não serve
para trabalhar; conteúdo é o que serve.

Isso também corrige uma coisa que eu disse rápido demais. “O Chrome não
publica” é impreciso. O mais provável é que o Chrome só ligue a árvore da
página quando percebe um programa de acessibilidade, e aqui ela tenha ficado
desligada. É ajuste do Chrome, não do JARVIS — e não é algo que eu vá pedir
para você fazer à mão.

## O veredito do Chrome (0.83.0)

A 0.82.6 mediu a janela certa. A resposta:

```
  medindo: chrome.exe — Arena | Benchmark & Compare the Best AI Models - Google Chro
  classe:  Chrome_WidgetWin_1

  janela                            msaa   uia   conteudo  processo
  ------------------------------------------------------------------------
  Chrome_WidgetWin_1                   4     4   nenhum   chrome.exe
    Chrome_RenderWidgetHostHWND        1     1   nenhum   chrome.exe
    Chrome_RenderWidgetHostHWND        1     1   nenhum   chrome.exe

  VEREDITO: 4 elemento(s), nenhum de conteudo (fonte uia).
```

Duas janelas filhas `Chrome_RenderWidgetHostHWND`, **1 elemento cada**, sem
conteúdo. A página não é publicada — nem pela MSAA, nem pela UIAutomation.

**Está encerrado o Chrome neste PC.** Era a promessa, e ela vale: não peço
outra rodada, não mudo a pergunta, não há uma sétima tentativa.

> **Correção (0.84.0):** estava errado. O Chrome publica a página sim — ele
> liga a acessibilidade quando percebe alguém lendo, e a primeira leitura
> pegou o estado antes disso. Ver “O Chrome acordou”, acima. A promessa de não
> insistir continua; o que mudou é que agora não há por que insistir: funciona.

O que isso significa na prática: neste `Windows 10.0.14393`, este Chrome não
expõe o conteúdo da página para um leitor de acessibilidade. O JARVIS não vai
adivinhar o que está na tela — sem foto, sem OCR, sem clique às cegas. Ler o
Chrome **aqui** não é um problema de código meu que mais uma versão resolve.

### O que ficou de aprendizado, e virou código

**1. Número não é resposta.** “47 elementos” manteve a etapa 2 parada por seis
versões, porque os 47 eram moldura. Agora toda leitura termina com a pergunta
que importa:

```
  NAO SERVE para agir: a janela publicou só moldura (barra de título,
  rolagem, botões de janela). Esta é a mesma parede que o Chrome deu neste PC.
```

**2. Não perguntar uma janela por vez.** Seis mensagens suas foram gastas
medindo um programa por vez. Agora existe um comando que mede **todas as
janelas abertas** de uma vez e responde onde dá para trabalhar:

```
.venv\Scripts\python arvore_sonda.py --provados
```

```
  janela aberta                        elementos  conteudo  serve?  fonte  seg
  ------------------------------------------------------------------------------
  notepad.exe        Sem título - B...       31  sim        SIM     uia   0.4
  explorer.exe       Downloads               88  sim        SIM     msaa  0.9
  chrome.exe         Arena | Benchmar...      4  nao        nao     uia   1.2

  2 de 3 janela(s) servem para o JARVIS agir:
    - notepad.exe — Sem título - Bloco de notas
    - explorer.exe — Downloads
```

**3. A ordem da medição importa.** Na 0.82.6 a coluna da MSAA do Chrome saiu
com 4, quando a leitura da 0.82.4 tinha achado 47 na mesma janela — a diferença
era a UIA já ter aberto a janela antes da medição. O diagnóstico agora mede a
MSAA **primeiro**, e o veredito é a leitura de verdade (`ler_janela`), não uma
segunda implementação dela.

**4. A conta da prontidão é explícita.** `arvore.prontidao()` responde com
números: total, acionáveis, com nome, editáveis, e um motivo em português. Ela
recusa moldura mesmo com 600 botões, e aceita o campo do Bloco de Notas, que
não tem nome nenhum — porque é onde se escreve.

## A sexta medição: a tabela mediu o terminal (0.82.6)

A 0.82.5 pediu uma tabela e ela veio assim:

```
  [FALHA] varredura de janelas (1)
  janela                                  msaa  uia   conteudo
  ConsoleWindowClass                         1    12   nenhum
```

`ConsoleWindowClass` é o **terminal**. O comando pedia o Chrome.

**O defeito era meu, não do Chrome.** `diagnostico()` não recebia o handle:
ignorava o `--alvo` e media sempre a janela em foco. A 0.82.3 tinha corrigido
exatamente isso na leitura normal e deixou o diagnóstico de fora — o mesmo erro,
no outro caminho. A tabela que devia decidir a etapa 2 estava olhando para a
janela errada.

### O que mudou

1. **O diagnóstico escolhe como a leitura escolhe.** A sonda usa o mesmo
   `_escolher`/`arvore.escolher_janela` e passa o **handle** para
   `diagnostico(alvo, handle=…)`. Não há segunda escolha para divergir.
2. **A tabela diz qual janela está medindo**, com processo e classe, antes de
   qualquer número:

   ```
   medindo: chrome.exe — Arena | Benchmark...
   classe:  Chrome_WidgetWin_1
   ```

3. **A MSAA também desce as filhas.** A 0.82.5 varria as filhas só na UIA. O
   Chrome publica a página pela MSAA da filha em várias versões; agora
   `varrer_msaa` percorre até 24 filhas, conteúdo primeiro, com a mesma regra
   de `escolher_fonte`.
4. **Há um veredito, e ele é medido como a leitura mede.** A tabela mostra cada
   janela isolada; a leitura agrega. No fim:

   ```
   VEREDITO: a leitura vai funcionar — 812 elemento(s) de conteudo, fonte uia.
   lido de dentro de: Chrome_RenderWidgetHostHWND
   ```
   ou `VEREDITO: 12 elemento(s), nenhum de conteudo (fonte uia).` — sem deixar a
   interpretação para você.
5. **A coluna `processo`** existe para o engano não se repetir: se a linha não
   diz `chrome.exe`, a janela não é o Chrome.

### O critério continua o mesmo

Se, **medindo a janela certa**, a tabela do Chrome disser `nenhum` em todas as
linhas e o veredito não tiver conteúdo, eu encerro a leitura do Chrome neste PC.
Sem nova rodada, sem nova tentativa: sigo com Explorer, Bloco de Notas e
instaladores, que publicam árvore clássica — e a etapa 2 (clique por `ref`) é
medida neles.

## A quinta medição: moldura não é conteúdo (0.82.5)

A 0.82.4 matou a repetição — **600 para 47 elementos**. Mas o número novo
denunciou outra coisa:

```
chrome.exe — Arena | Benchmark...: 47 elemento(s), 26 acionável(is) — fonte: msaa.
a UIAutomation mostrou 4; a MSAA mostrou mais (47).
```

Os 47 eram **todos moldura**: barra de título, barra de rolagem, “alça”.
Nenhum item da página. E a regra “ganha quem mostrou mais” premiava exatamente
a leitura sem conteúdo — 47 pedaços de moldura venciam 4 elementos de página.

Três correções:

### 1. Conteúdo vence moldura

A escolha entre fontes parou de contar elementos e passou a perguntar **o que**
eles são. Papéis de conteúdo — link, texto, item de lista, célula, documento —
valem mais do que qualquer quantidade de botão de janela.

| situação | quem ganha |
|---|---|
| uma tem conteúdo, a outra só moldura | a que tem conteúdo |
| navegador (Chrome, Edge, Firefox…) | UIAutomation, mesmo com menos nós |
| nenhuma tem conteúdo | quem mostrou mais (regra antiga) |

### 2. A página mora numa janela **filha**

A página do Chrome não é um elemento da janela principal: é a janela filha
`Chrome_RenderWidgetHostHWND` — outro processo. Ler só a janela de topo dá a
moldura; é por isso que a UIA “mostrava 4”.

Agora a leitura varre as janelas filhas (até 24), começando pelas classes que
carregam conteúdo, e fica com a que tiver mais nós. O resumo diz de onde veio:

```
(lido de dentro: Chrome_RenderWidgetHostHWND)
```

### 3. O diagnóstico passou a medir isso

`--diagnostico` agora mostra uma tabela por janela e por fonte:

```
  janela                                  msaa  uia   conteudo
  --------------------------------------------------------------
  Chrome_WidgetWin_1                        47     4   nenhum
    Chrome_RenderWidgetHostHWND              0   812   uia
```

Essa tabela é a resposta definitiva. Se a linha indentada mostrar `uia` com
conteúdo, a leitura funciona. Se mostrar `nenhum` em tudo, o Windows 10 do seu
PC não expõe a página — e aí eu paro, em vez de te fazer rodar de novo.

## A quarta medição: a causa raiz (0.82.4)

`--alvo chrome` passou a achar o Chrome. Mas a árvore continuou repetindo — e
agora dava para ver **o quê** repetia:

```
barra de rolagem “Vertical”
  botão “Uma linha acima”
    botão “Uma linha acima”
      botão “Uma página acima”
        botão “Uma linha acima” ...
```

Não era a moldura da janela. Era a **barra de rolagem**. E a causa não era o
Chrome — era uma linha minha:

```python
usar = ponteiro_filho or ponteiro      # <- o defeito
```

A MSAA tem dois tipos de filho:

| tipo | o que é | tem filhos? |
|---|---|---|
| **objeto** (VT_DISPATCH) | um objeto COM de verdade, com ponteiro próprio | sim |
| **simples** (VT_I4) | só um número de identificação dentro do pai | **não** |

Para um filho simples, `get_accChildCount` **no pai** devolve os filhos *do
pai*. Ao reusar o ponteiro do pai, eu pedia ao pai que listasse os próprios
filhos — de novo, e de novo, até acabar o limite. Cada “botão Uma linha acima”
era o mesmo botão, lido repetidamente.

O certo: **elemento simples entra na árvore (nome e papel são lidos dele), mas
não se desce nele.** Uma linha.

Junto com isso, a montagem ganhou a mesma guarda em segundo lugar: mesmo que a
sonda devolva árvore repetida (versão antiga, programa estranho), o `montar`
corta antes de chegar ao chat. E a distinção passou a ser explícita:

- **moldura** (Minimizar, Fechar, IME): o nó é real, entra e para ali;
- **repetição** (o mesmo nó dentro de si mesmo): não é nó novo, **não entra**.

Por fim: navegador (Chrome, Edge, Firefox, VS Code, Slack, Discord…) agora
**sempre** tenta a UIAutomation, mesmo que a MSAA venha grande. No seu PC a
MSAA do Chrome devolveu 600 elementos de barra de rolagem e **zero** da página.

## A terceira medição no seu PC (0.82.3)

A 0.82.2 consertou os índices da UIAutomation — e isso **funcionou**:

```
D:\JARVIS>.venv\Scripts\python arvore_sonda.py --alvo chrome --diagnostico
  [ok  ] CoInitializeEx(MTA)                0x00000000
  [ok  ] CoCreateInstance(IUIAutomation)    0x00000000  objeto criado
  [ok  ] get_ControlViewWalker (índice 14)  0x00000000
  [ok  ] ElementFromHandle (índice 6)       0x00000000
  [ok  ] get_CurrentControlType             0x00000000  tipo=50032
```

E a leitura pela UIA trouxe conteúdo de verdade onde a MSAA trazia a moldura:

```
--alvo chrome: 12 elemento(s), 7 acionável(is) — fonte: uia
  barra de rolagem “Vertical”
    botão “Uma linha acima”  @93d11915:e3
    botão “Uma página acima”  @93d11915:e4
    elevador “Posição”
```

**Mas `--alvo chrome` leu o terminal, não o Chrome.** O motivo está no título
daquela janela:

```
cmd.exe — C:\Windows\system32\cmd.exe - .venv\Scripts\python arvore_sonda.py --alvo chrome
```

A busca procurava **primeiro no título**, e o título do `cmd` é a linha de
comando — que contém a palavra “chrome”. A janela que roda a sonda é a **única**
que sempre carrega o pedido escrito nela. Era o pior lugar possível para
começar a busca.

Agora:

1. a janela que roda a sonda **nunca** é candidata;
2. **processo vence título**: `chrome` casa com `chrome.exe` (nota 0) antes de
   casar com qualquer título que mencione a palavra (nota 3);
3. quando nada casa, a mensagem lista só janelas de programas de verdade.

## A segunda medição no seu PC (0.82.2)

Depois da 0.82.1 você rodou de novo, agora com o Chrome aberto:

```
chrome.exe — Arena | Benchmark...: 600 elemento(s), 596 acionável(is) — fonte: msaa.
botão “IME” → botão “IME” → botão “IME” → ...
botão “Minimizar” → botão “Minimizar” → ...
```

```
D:\JARVIS>.venv\Scripts\python arvore_sonda.py --fonte uia
o foco estava neste terminal; li “Iniciar” (explorer.exe) em vez dele.
a UIAutomation não devolveu árvore para esta janela.
```

Eram **três defeitos meus**, e nenhum do seu PC:

1. **A árvore se repetia dentro de si mesma.** O Chrome expõe a moldura da
   janela *dentro* da janela: cada botão de moldura devolve os cinco botões de
   novo. Sem guarda, os 600 elementos acabaram antes de chegar ao conteúdo da
   página — 596 “botões” que não existem. Agora **moldura é folha** (não se desce
   em Minimizar/Maximizar/Fechar/IME) e **quem repete um ancestral para**.
2. **Os índices da UIAutomation estavam todos +3.** A vtable começa em
   `CompareElements`, mas QueryInterface/AddRef/Release ocupam as posições 0, 1
   e 2 — eu tinha esquecido. Na prática, `ElementFromHandle` chamava
   `GetRootElementBuildCache`. Corrigido e **preso por teste**.
3. **A troca de janela pegou o menu Iniciar.** “Iniciar” é do Windows, não é um
   programa seu. Agora a lista de janelas de sistema (menu Iniciar, barra,
   área de trabalho) fica de fora da escolha.

E o que faltava para não errar de novo em silêncio: `--diagnostico`, que mostra o
retorno de **cada** passo do COM, em hexadecimal.

```
.venv\Scripts\python arvore_sonda.py --diagnostico
```

## A primeira medição no seu PC (0.82.1)

Você rodou isto no `cmd` e recebeu, três vezes:

```
D:\JARVIS>.venv\Scripts\python arvore_sonda.py
cmd.exe — C:\Windows\system32\cmd.exe - ...: 1 elemento(s), 0 acionável(is) — fonte: msaa.
área do cliente “C:\Windows\system32\cmd.exe - ...”
```

**Duas coisas estavam erradas, e nenhuma era o seu PC:**

1. **A sonda leu a si mesma.** O comando roda *dentro* de um `cmd.exe`, e a
   janela em foco era esse `cmd`. Você queria ver o programa aberto **atrás**.
   Agora, quando o foco é o terminal que roda a sonda, ela pega a janela anterior
   e **diz que trocou** (`o foco estava neste terminal; li “...” em vez dele`).
2. **O console não publica botões pela MSAA.** A MSAA é de 1996 e o `cmd` só
   expõe a moldura. O Windows tem uma **segunda** árvore, a **UIAutomation**, que
   é a mesma que o Narrador usa — e é nela que os programas de hoje publicam
   (Bloco de Notas do Windows 11, apps WinUI, boa parte do Chrome).

Por isso a leitura agora **tenta as duas** e fica com a que mostrou mais
elementos. Numa janela rica ela não paga a segunda leitura: o tempo de espera
seria seu.

E quando a árvore vem quase vazia, aparece a **dica** em vez de silêncio — o
resumo diz *por que* e *o que fazer* (trocar de janela, usar `--alvo`).

## O que é a árvore de acessibilidade

Todo programa no Windows é obrigado (por acessibilidade) a dizer quais elementos
tem: “aqui há um botão chamado Salvar, nesta posição, e clicar nele faz X”. É o
mesmo canal que o **Narrador** e o **NVDA** usam.

São **duas** portas para a mesma ideia, e o JARVIS usa as duas:

| fonte | biblioteca | quem publica |
|---|---|---|
| **MSAA** | `oleacc.dll` | programas clássicos (Win32, MFC, VB6, muito do Chrome) |
| **UIAutomation** | `uiautomationcore.dll` | programas atuais (WinUI, WPF, Bloco de Notas novo, Explorer) |

As duas via `ctypes` puro — **sem instalar nada**. E as duas só leem: `get_*`,
`accessLocation`, `GetFirstChildElement`, `GetCurrentPattern` (este último só
para **perguntar** se o elemento aceita ação).

```
janela “Cadastro de cliente”
  painel
    botão “Salvar”              @a1b2c3d4:e3
    botão “Cancelar”            @a1b2c3d4:e4
    texto “Nome completo”
    caixa de seleção “Aceito os termos”  @a1b2c3d4:e6
  barra de ferramentas
    item de menu “Arquivo”      @a1b2c3d4:e8
```

O `ref` (`@a1b2c3d4:e3`) só vai para o que **dá para acionar**, e carrega o id da
leitura: se a tela mudar, o `ref` antigo deixa de valer — é assim que se evita
clicar no botão errado depois de uma atualização da janela.

## Como usar

No chat:

```
vê os elementos da janela
lê a janela do chrome
o que dá para clicar no bloco de notas
```

Ou direto no terminal do PC (não precisa do JARVIS aberto):

```
.venv\Scripts\python arvore_sonda.py
.venv\Scripts\python arvore_sonda.py --janelas
.venv\Scripts\python arvore_sonda.py --alvo chrome --profundidade 8
.venv\Scripts\python arvore_sonda.py --json --limite 200
```

## O que ele garante

| garantia | como |
|---|---|
| **só leitura** | o módulo não tem função de clicar, digitar ou mover — há teste que falha se alguém acrescentar |
| **sem foto da tela** | não usa `screenshot`, não lê pixel, não faz OCR |
| **não derruba a API** | a leitura roda em `arvore_sonda.py`, processo separado, com tempo limite |
| **não trava** | profundidade (máx. 14), total de elementos (máx. 3.000) e tempo (25 s) limitados |
| **não finge** | corte vira `completo: false` com o motivo; papel desconhecido vira `elemento 999`; janela sem árvore vem com aviso |
| **fora do Windows** | recusa com frase clara, em vez de devolver vazio |
| **duas fontes** | MSAA e UIAutomation; quem decide é a que mostrou mais elementos |
| **não lê a si mesma** | se o foco é o terminal que roda a sonda, ela pega a janela de trás e avisa |
| **não entra em laço** | moldura é folha e nó que repete um ancestral para — o Chrome já provou que sem isso a leitura vira 600 botões falsos |
| **não escolhe o Windows** | menu Iniciar, barra de tarefas e área de trabalho ficam fora da lista de janelas |
| **não escolhe a si mesma nem por engano** | a janela que roda a sonda é excluída, e processo vence título — `--alvo chrome` acha o Chrome |
| **não repete o mesmo elemento** | filho “simples” da MSAA não desce (era a causa de 600 botões falsos), e a montagem corta repetição de qualquer origem |
| **navegador vai direto na UIA** | Chrome/Edge/Firefox/VS Code publicam a página pela UIAutomation, não pela MSAA |
| **conteúdo vence moldura** | 47 botões de janela não valem mais do que 3 elementos de página |
| **lê as janelas filhas** | a página do navegador é uma janela filha (`Chrome_RenderWidgetHostHWND`), não um elemento da janela de topo |
| **falha com endereço** | `--diagnostico` mostra o retorno de cada passo do COM, não só “não devolveu” |
| **mede a janela certa** | o diagnóstico recebe o handle já escolhido — `--alvo chrome` não mede mais o terminal |
| **diz se serve para agir** | toda leitura termina com serve/não serve e o motivo; `mesa.arvore` devolve `pronto` |
| **mostra onde fica** | cada elemento sai com `em x,y (largura x altura)`; `--provados` tem a coluna `posicoes` |
| **não desiste na primeira** | janela que responde só moldura é relida uma vez, 0,4 s depois — navegador acorda ao ser lido |
| **não confunde moldura com trabalho** | botão de janela, rolagem e alça ficam de fora da conta de “dá para agir” |
| **sabe onde se escreve** | papel `texto`/`documento` com caixa ganha ação `digitar` e `ref`, salvo se for somente leitura |
| **age por `ref`, com freio** | relê antes de agir; ref antigo, moldura e digitar sem texto são recusados; `--executar` é obrigatório |
| **acha o campo sozinho** | `--escrever "texto"` — sem copiar ref de uma saída para outra |
| **acrescenta sem apagar** | `--acrescentar`: campo com texto ganha o novo no fim, não por cima |
| **abre o programa sozinho** | `--programa "bloco de notas"`: abre se não estiver aberto, espera a janela e escreve |
| **chega na janela sem mouse** | `SetForegroundWindow` antes de agir |
| **mouse como último recurso** | `--mouse`: clique físico no centro medido, só se a ação e o foco falharem |
| **não move o mouse** | a ação vem do elemento (ação padrão / foco), que é o único caminho que funciona na sua tela |
| **mede todas as janelas de uma vez** | `--provados` varre o que está aberto, com teto de 60 s, e diz onde dá para trabalhar |
| **mede na ordem da leitura** | MSAA antes de a UIA tocar na mesma janela; o veredito é a própria `ler_janela` |
| **diz o que mediu** | a tabela abre com processo e classe da janela, e fecha com veredito medido como a leitura mede |
| **varre as filhas nas duas fontes** | MSAA e UIA descem até 24 janelas filhas, conteúdo primeiro |

## O que **não** faz (ainda) e por quê

- **Clicar por `ref`** é a **etapa 2**. Ela só entra depois que você rodar isto no
  seu PC e me disser o que apareceu — porque o que decide é **quais programas
  publicam árvore**. Chrome, WhatsApp Desktop e Explorer se comportam de formas
  diferentes, e prometer clique sem essa medição seria repetir o erro das
  versões anteriores.
- **Ver a tela por imagem.** Se um programa não publica árvore (jogo, instalador
  antigo), o JARVIS não vê. Isso é limite do programa, não do JARVIS — e está
  dito em vez de escondido.

## O teste que você mesmo pode fazer

1. abra **o Bloco de Notas** e clique nele;
2. no terminal do PC:

```
cd /d D:\JARVIS
.venv\Scripts\python arvore_sonda.py
```

3. me diga o que apareceu (ou mande o `--json`).

Para saber **em quais programas** dá para trabalhar, sem tentativa e erro:

```
.venv\Scripts\python arvore_sonda.py --provados
```

Se alguma coisa vier estranha, o primeiro comando é sempre:

```
.venv\Scripts\python arvore_sonda.py --diagnostico
```

Quer comparar as duas fontes na mesma janela? Rode uma vez com `--fonte msaa` e
outra com `--fonte uia`. O número de elementos de cada uma é a resposta crua —
e é ela que eu uso para decidir a etapa 2, não um palpite meu.

Se o Bloco de Notas publicar árvore (deve publicar), a etapa 2 fica viável para
programas clássicos. Depois repetimos com o **Chrome** e com o **WhatsApp** —
esses são os que decidem se vale a pena.

## Detalhe técnico: por que a sonda é um processo separado

A leitura conversa por COM com **código de outra pessoa** (o programa que você
tem aberto). Um aplicativo malcomportado pode travar a chamada ou derrubar o
processo inteiro. Derrubar uma sonda descartável é aceitável; derrubar o JARVIS
no meio de uma conversa não é. É o mesmo princípio do `conferir-versao.bat`: o
diagnóstico não pode ser perigoso.
