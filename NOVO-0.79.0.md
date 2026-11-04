# JARVIS 0.79.0 — a skill vem antes do modelo, e a cota avisa antes de acabar

Duas perguntas suas, duas respostas.

---

## 1. “Agora com o cérebro funcionando ele vai poder usar todas as skills?”

**Antes desta versão: não** — e isso era um defeito, não uma limitação.

O chat tinha dois caminhos separados:

- **sem** chave de IA: a frase desconhecida ia para o agente local, que
  procurava a skill e executava;
- **com** chave de IA: a frase desconhecida ia **direto** para o modelo.

Ou seja: no exato momento em que você configurou o cérebro, as 315 skills
deixaram de ser consultadas para qualquer frase fora dos comandos conhecidos.
O modelo respondia bem, mas **nenhuma ação era executada** — e ele não pode
executar por conta própria (é regra: só skill executa).

### O que muda agora

Toda frase desconhecida faz **duas passadas**, nesta ordem:

```text
1. skill  →  o agente local procura, preenche os campos e executa
2. modelo →  só se nenhuma skill servir, a IA responde em texto
```

A primeira passada é estreita de propósito: **não** busca na web (quem responde
é o modelo, melhor nisso) e **não** cria skill local (a fila do Agente não deve
encher com o que o modelo já respondeu). Ela só executa o que já existe: skill
do catálogo, skill local criada, resposta guardada e os pedidos que têm regra
própria (Drive, PC, mesa, correio, atualização, cota…).

### “Todas” quer dizer todas?

Com honestidade: as **315 estão disponíveis para o roteador** — todas entram no
índice, todas podem ser escolhidas. O que não dá para prometer é que qualquer
frase ache a skill certa: a busca é por palavra (nome, categoria, descrição,
campos), sem modelo decidindo. É por isso que existem os dois limites:

- confiança baixa → o JARVIS **não executa** a skill “quase certa”: mostra as
  mais próximas e pergunta;
- e agora, com o cérebro ligado, se ele não tem certeza, quem responde é o
  modelo — em vez de uma pergunta sobre o formulário errado.

Se errar, os dois caminhos de sempre continuam valendo: *“não é essa, é a skill
X”* (ele aprende o apelido) e *“procure na web sobre isso”*.

---

## 2. “Dá para o JARVIS avisar quando estiver acabando ou quando acabar as APIs?”

Dá — desde que o aviso seja **medido**. Fingir que sabe seria pior que não
avisar. Então o que ele faz é registrar o que o provedor respondeu:

| sinal | o que o JARVIS anota |
|---|---|
| resposta 200 | a chave está boa; e os cabeçalhos `x-ratelimit-*` dizem **quanto resta no minuto** |
| HTTP 429 | aquela chave está **no limite**; o `retry-after`, quando vem, diz em quantos segundos tentar |
| HTTP 401/403 | aquela chave foi **recusada** — só volta com chave nova |
| botão **Testar** | é chamada real: o resultado também entra no diário |

### Onde o aviso aparece

1. **faixa no topo da tela**, acima do aviso de versão:
   - âmbar — **“As chaves de IA estão acabando”**: alguma caiu, ou o que resta
     no minuto já é ≤ 20% do limite;
   - vermelha — **“As chaves de IA acabaram”**: nenhuma responde. O texto diz
     que a conversa com o modelo parou **e que as skills locais continuam**;
   - botões **Conferir agora** (testa as chaves de verdade) e **Chaves de IA**;
   - dá para fechar, mas ela volta sozinha quando a situação piora;
2. **no cartão Chaves de IA**, em Configurações, com o detalhe de cada chave;
3. **no chat**: *“quantas chaves restam?”*, *“as APIs acabaram?”*, *“acabou a
   cota?”* — responde com o diário, sem chamar modelo nenhum;
4. **toast** na tela quando a última chave cai, para quem estiver em outra
   página.

### O que ele não promete

- **não inventa porcentagem**: se o provedor não manda o cabeçalho de cota, o
  aviso fala do que aconteceu (429/401), não de “restam 37%”;
- **não adivinha a cota diária** que o provedor não informa — o que existe é o
  limite por minuto nos cabeçalhos e a recusa real quando ela acontece;
- **não resolve**: avisar não é trocar chave. Trocar ou acrescentar chave
  continua sendo no cartão, em Configurações.

---

## O que NÃO mudou

- **Nada de chave na tela**: o diário guarda posição, código HTTP e horário.
  Nenhuma resposta da API contém a chave — há teste para isso.
- **Nenhuma skill nova**: continuam 315. O que mudou foi a ordem em que o chat
  consulta o que já existia.
- **Skills locais seguem sem chave**: sem cota, sem conta, sem internet.

## Números desta versão

- pytest: **3251 passed, 2 skipped, 0 failed**
- vitest: **134 passed**
- manifesto: **482 arquivos**
- skills: **315** (nenhuma nova)

## Como pegar esta versão

Se você já está na 0.78.0, basta fechar a janela no **X** e abrir de novo: ele
se atualiza sozinho no `[3/4]`. Se ainda estiver numa versão anterior à 0.78.0,
o caminho é o de sempre: fechar no **X** → `atualizar.bat` →
`iniciar-jarvis.bat`.
