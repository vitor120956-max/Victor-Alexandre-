# JARVIS 0.91.22 — o painel estava aberto e ele disse que não abriu

Seu print tem as três coisas ao mesmo tempo: o painel **Create API key** aberto
e vazio, o console com o log, e o veredito

    2. NÃO DEI: a leitura não trouxe o que eu procurava (3 elementos com nome,
    fonte uia; os primeiros: Chrome Legacy Window, Keys | Settings | OpenRouter,
    Notifications).

**O clique funcionou.** O botão “New key” foi apertado e o painel abriu. O que
falhou foi **ver**: a leitura trouxe 3 elementos — a moldura do Chrome, não a
página.

Não é coincidência que isso aconteceu justo quando você foi ler o console. A
janela do Chrome foi para trás, e uma janela do Chrome atrás (ou minimizada)
pode parar de publicar a página — sobra a moldura.

## O que mudou

**1. Leitura pobre não é resposta.** Quando vêm menos de 8 nomes, ele traz a
janela do Chrome para a frente, confirma que ela está com o foco e lê de novo.
Isso vale na espera do painel, na espera da página e depois de cada clique.

**2. Se a janela não subir, ele diz.** O Windows às vezes recusa (`SetForegroundWindow`
falha quando outro programa tem o foco). Aí ele fala, em vez de continuar
calado:

    a leitura caiu (só a moldura do Chrome) e o Windows não deixou eu pôr a
    janela na frente — clique uma vez no Chrome para ela subir.

**3. A desculpa agora é a verdadeira.** Antes, com 3 elementos, ele escrevia
“a página foi lida inteira e o botão estava nela” — falso. Agora são duas
mensagens diferentes: ou não conseguiu **ver** a página, ou leu a página
inteira e o clique não abriu o painel. São problemas diferentes e a solução é
diferente.

**4. O relatório responde a pergunta.** `chave-leitura.txt` ganhou uma linha:

    estado: minimizada; SEM o foco (o foco está em 'Prompt de Comando')

Se voltar a falhar, essa linha já diz se era a janela.

**5. Mais paciência.** 20 segundos por degrau de clique (era 12).

## O que foi provado

Um Chrome falso que **dorme depois do clique** — só publica a moldura até
alguém trazê-lo para a frente, exatamente como no seu print:

- ele acorda a janela, lê o painel e cria a chave;
- com o Windows recusando o foco, nada é gravado e a mensagem diz “NÃO consegui
  ver a página”, não “o painel não abriu”;
- o `.env` só muda quando a chave é mesmo criada.

Os dois testes **reprovam** o código da 0.91.21 — conferi rodando contra ele.

## O que eu não sei

Se a janela atrás é **mesmo** a causa no seu Chrome. O teste prova o
comportamento (janela que para de publicar é acordada e o painel é lido), não a
causa. Se voltar a falhar, mande o `chave-leitura.txt` — agora ele tem a linha
`estado:` e as três leituras.

## O que continua igual

- nada é criado sem `--autorizar`;
- expiração **Never**, limite **No limit**, nome `jarvis-AAAA-MM-DD`;
- botão apagado não é clicado;
- cursor volta para o dono;
- sem chave, o `.env` não é tocado.

Suíte inteira: **3.771 testes passando** (7 pulados: dependem do Windows real).
