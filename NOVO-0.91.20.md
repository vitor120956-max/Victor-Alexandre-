# JARVIS 0.91.20 — ele desistiu com a página na tela

Seu print mostra tudo: a página dos dois lados, o botão **New key** roxo no
canto, e o script dizendo

    1. NÃO DEI: o botão de criar não está na árvore desta janela.

Logo acima, ele mesmo tinha avisado: *“a página ainda está carregando — espero
ela parar antes de clicar”*. Ou seja: **ele sabia que a leitura era de uma
página em construção — e usou essa mesma leitura como veredito.** Uma leitura
vazia virou “o botão não existe”.

## O que mudou

**1. Ele insiste.** O botão agora é procurado relendo por até **18 segundos**,
com leitura funda, antes de dizer que não existe.

**2. Olha as outras janelas.** A cada duas tentativas ele confere as outras
janelas do navegador — a página pode ter aberto na vizinha.

**3. A leitura que decide é a mesma que clica.** Antes, a espera da página
usava leitura rasa e o clique usava leitura funda. Era isso que produzia “o
botão não existe” com o botão na tela.

**4. Desistir agora exige prova.** Quando não acha, ele diz **quantos elementos
a leitura trouxe** e os primeiros nomes, e grava `chave-leitura.txt` com as
três leituras. Se voltar a falhar, essa linha já mostra se é página carregando,
janela errada ou outra coisa.

## O que continua igual

- clique de mouse antes da ação do elemento;
- o nome vai para a caixa de texto, expiração **“Never”**, limite **“No limit”**;
- botão “Create” apagado não é clicado;
- sem chave, nada é gravado; o cursor volta para o lugar.

## O que foi provado

- botão que só aparece na terceira leitura: ele continua e acha;
- botão que nunca aparece: ele diz a contagem, os primeiros nomes e grava o
  relatório;
- a espera da página passou a usar leitura funda;
- página que não para de mudar: ele avisa quantos elementos viu;
- sem botão, nada é clicado e nada é gravado.

Suíte inteira: **3.744 testes passando** (7 pulados: dependem do Windows real).
