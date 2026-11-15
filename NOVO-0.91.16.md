# JARVIS 0.91.16 — o diálogo estava na tela e ele dizia que não

Você rodou a 0.91.15 e mandou o print: **Create API key aberto na tela** — nome,
expiração, limite — e a saída dizendo

    NÃO DEI: o diálogo de criação não apareceu na leitura.

O script estava certo sobre o que queria fazer e errado sobre o que estava
lendo. Quatro defeitos, todos nesse mesmo print:

**1. A leitura era rasa.** Ele lia 8 níveis da página. O painel de criação é um
bloco no fim de um documento grande — ficava depois do nível 8. Agora, na hora
de achar o diálogo e de preencher os campos, a leitura vai fundo (14 níveis).

**2. Cada passo escolhia a janela pelo nome.** “A janela do chrome” não é uma
só: com duas abertas (a sua e a do site), um passo podia ler — e clicar — na
errada. Agora ele relê **pelo handle**, que é a identidade da janela. O nome é
palpite; o handle não.

**3. Ele olhava uma janela só.** Se o clique abre o painel na outra janela do
Chrome, ninguém estava olhando lá. Agora a espera confere até três janelas do
navegador.

**4. Um falso positivo meu.** Eu tinha posto “Create Key” na lista de títulos do
diálogo. Mas **Create Key é o botão**, que existe na página o tempo todo: a
página passava por “diálogo aberto” e o script ia preencher uma caixa que ainda
não estava na tela. O título agora é só “Create API key”; o botão ficou de fora.

## A mensagem também mudou

“Não apareceu” não ajuda quem está vendo o diálogo na tela. Agora ela diz o que
a leitura viu:

    o diálogo não apareceu na leitura (2 elementos com nome; os primeiros:
    API Keys, Create Key).

Se voltar a acontecer, essa linha já mostra se o problema é profundidade, é
janela errada ou é o site desenhando de outro jeito.

## O último degrau do nome

O diálogo nasce com o cursor **dentro** do “Name”. Se a leitura não der o campo,
ele digita pelo teclado — mas só depois de trazer a janela para a frente e
confirmar que o teclado está nela. Nunca às cegas.

## O que continua igual

- expiração: **“Never”** quando existe; senão, o maior prazo;
- limite: **“No limit”**;
- sem o diálogo, ele **para** — não clica no “New key” de novo;
- sem chave, **nada é gravado**;
- o cursor volta para onde estava.

## O que foi provado

- o painel enterrado em 12 níveis: com a leitura de 8 não aparece, com a funda
  aparece — é o teste que reproduz o seu print;
- o painel que abriu na **outra** janela do Chrome é encontrado;
- “Create Key” na página **não** é confundido com o diálogo aberto;
- o diálogo é reconhecido pelos campos mesmo quando o título não vem na leitura;
- o caminho completo continua criando, copiando e gravando no `.env`.

Suíte inteira: **3.715 testes passando** (7 pulados, porque dependem do Windows
de verdade).

## Para usar

Duplo clique em **`pegar-chave.bat`**, como antes. Nada para digitar.

## Ainda pendente

O acesso às senhas salvas do Chrome — você disse “depois a gente vê”. Fica para
a próxima conversa, depois desta chave estar gravada.
