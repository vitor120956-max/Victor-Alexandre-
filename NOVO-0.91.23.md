# JARVIS 0.91.23 — o problema não era a janela, era a vista

Seu print das 07:52 mostra o painel **Create API key** aberto na tela e, do
lado, outra vez:

    2. NÃO DEI: a leitura não trouxe o que eu procurava (3 elementos com nome,
    fonte uia; os primeiros: Chrome Legacy Window, Keys | Settings | OpenRouter,
    Notifications).

A 0.91.22 apostou que a janela estava atrás do console. Nesse print ela **fez o
que prometeu** — trouxe a janela do Chrome para a frente, duas vezes — e a
leitura continuou com 3 elementos. Minha teoria estava errada. O que a 0.91.22
acertou foi o diagnóstico: o defeito não é o clique, é **ver**.

## A causa: a vista de acessibilidade

O Windows expõe cada programa em três vistas diferentes. A que o JARVIS usava é
a **de controle** — “o que um teclado alcança”. Quando um painel modal abre, o
site esconde a página da tecnologia assistiva, e a vista de controle passa a
devolver só a moldura: 3 elementos.

A vista **crua** não respeita esse esconderijo. Ela continua vendo o documento
inteiro — inclusive o painel.

## O que mudou

**1. As três vistas.** `uia`, `uia_content` e `uia_raw`. Quando a leitura normal
vem pobre, ele experimenta as outras — uma por vez, girando — e, achada a que
mostra a página, ela passa a ser a primeira de todas.

**2. Orçamento maior na vista crua.** Ela mostra o documento inteiro e o painel
é o **último** nó dele. Com o teto da leitura normal, o painel seria cortado
justamente por estar no fim — de novo “não existe” com ele na tela.

**3. “Leitura boa” deixou de ser só contagem.** O painel aberto tem 6 nomes; a
página logo depois de criar também. Contar sozinho fazia o painel à vista
passar por leitura ruim. Agora “veio da moldura” é o que tem
**“Chrome Legacy Window”** no nome.

**4. O relatório agora responde “qual vista vê?”.** `chave-leitura.txt` mede as
cinco leituras (automática, controle, crua, conteúdo e MSAA) e escreve quantos
elementos cada uma trouxe. Se falhar de novo, a linha com mais nomes é a
resposta.

## Duas coisas menores, do mesmo print

**A espera da área de transferência não fica mais calada.** A cada 20 segundos
uma linha diz que ele continua olhando e quanto falta. Você já apertou Ctrl+C
numa espera de 120 s que não dizia nada.

**Lista de crédito sem “sem limite”:** ele escolhe o maior valor da lista e diz
que escolheu, em vez de parar sem criar chave nenhuma.

## Sobre o que você pediu

> o campo name já tá marcado mas ele precisa digitar um nome e depois clicar na
> expiração e selecionar, como eu fiz agora manual

É exatamente o que o passo faz — e ele já sabe escolher **“No expiration”**
(está na lista de “sem limite” desde a 0.91.15). O que faltava era conseguir
**ver** o painel para fazer isso. É o que muda agora.

## O que foi provado

Um Chrome falso em que a vista de controle devolve **só a moldura** e a vista
crua devolve a página com o painel — o seu print, em teste:

- ele acha o painel pela vista crua, digita o nome `jarvis-AAAA-MM-DD`, escolhe
  **No expiration**, **No limit**, cria, copia e grava no `.env`;
- achada a vista boa, ele não paga as outras a cada passo;
- os dois testes **reprovam** o código da 0.91.22 — conferi rodando contra ele.

## O que eu ainda não sei

Se a vista crua é **mesmo** o que resolve no seu Chrome. O teste prova o
comportamento, não a causa. Se falhar outra vez, me mande o
`chave-leitura.txt`: agora ele traz a contagem das cinco leituras, e isso diz
qual delas enxerga a página.

## O que continua igual

- nada é criado sem `--autorizar`;
- expiração **No expiration**, limite **No limit**, nome `jarvis-AAAA-MM-DD`;
- botão apagado não é clicado;
- cursor volta para o dono;
- sem chave, o `.env` não é tocado.

Suíte inteira: **3.778 testes passando** (7 pulados: dependem do Windows real).
