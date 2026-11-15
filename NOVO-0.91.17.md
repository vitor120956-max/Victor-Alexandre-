# JARVIS 0.91.17 — esperar a página, e não confiar numa leitura ruim

Você acertou a causa do print 1: **a página ainda estava carregando e ele tentou
antes.** E o print 2 mostra um problema diferente, que também é de leitura.

## O que cada print mostrou

**Print 1** — a leitura veio boa (43 elementos, a página inteira), o clique em
“New key” saiu, mas o painel não abriu. A página ainda estava se montando: o
clique caiu num botão que ia ser trocado, e o efeito se perdeu.

**Print 2** — o painel estava aberto na tela e a leitura trouxe **3 elementos**:

    Chrome Legacy Window · Keys | Settings | OpenRouter · Notifications

Isso é a **moldura** do Chrome, não a página. O Chrome moderno publica o
conteúdo do site só pela UIAutomation; a outra leitura (MSAA) devolve a casca da
janela. Quando a escolha automática caía nessa casca, a página inteira sumia — e
o script dizia “o painel não apareceu” com toda a certeza do mundo.

## O que mudou

**1. Leitura pobre não é resposta.** Abaixo de 8 nomes, a leitura é repetida
pedindo cada fonte na mão (UIAutomation e MSAA) e fica com a que mostrou a
página. Aqueles 3 nomes do print 2 deixam de ser um veredito.

**2. Espera de verdade: 35 segundos** (eram 12), com aviso na tela a cada poucos
segundos — esperar calado parecia travamento.

**3. A página tem de estar pronta antes do clique.** Ele lê, espera uma segunda
leitura com os mesmos elementos e só então clica. Era isso que faltava no
print 1.

**4. Uma segunda tentativa, só com prova.** Se o painel não abrir **e** a página
estiver legível (o painel comprovadamente não está lá), ele clica em “New key”
mais uma vez. Se a leitura estiver ruim, **não** repete: sem saber o que está na
tela, repetir poderia abrir um painel em cima do outro.

**5. Se falhar, fica um arquivo.** `chave-leitura.txt`, na pasta do JARVIS, com
o que cada fonte leu naquele momento: quantos elementos, de que fonte, os
primeiros nomes e os avisos. É o que permite descobrir a causa em vez de
adivinhar — e você só precisa dizer “falhou”.

**6. Uma leitura que despenca não vira veredito.** Antes vinham 43 elementos e
depois do Create vêm 3? Quem falhou foi a leitura, não o clique. Nesse caso ele
não diz “não criou”: vai pela cópia, que é o que prova a chave.

## O que continua igual

- expiração **“Never”** (ou o maior prazo), limite **“No limit”**;
- sem painel, para; sem chave, nada é gravado;
- o cursor volta para onde estava;
- o duplo clique em `pegar-chave.bat` continua sendo tudo o que você faz.

## O que foi provado

Com um Chrome de mentira que **muda de tela quando é clicado**:

- com a moldura na leitura automática e a página na UIAutomation, ele acha a
  página — é o print 2;
- duas leituras ruins seguidas não fazem o script desistir;
- a página que ainda está carregando é esperada antes do clique — é o print 1;
- o clique em “New key” se repete **uma** vez quando a página está legível;
- quando o painel está ilegível, ele não repete o clique;
- o relatório com as três leituras é gravado;
- uma leitura que despenca depois do Create não faz ele dizer “não criou”.

Suíte inteira: **3.722 testes passando** (7 pulados: dependem do Windows real).
