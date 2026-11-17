# JARVIS 0.91.28 — ele espera, em vez de desistir

O seu print mostrou o caminho novo chegando até o fim do primeiro trecho: o
`chrome-cdp.bat` achou a porta, abriu o Chrome do JARVIS. E aí a aba ficou
**branca**, no endereço `openrouter.ai/sign-in?redirect_url=…`.

Duas coisas ao mesmo tempo, e nenhuma delas é defeito seu:

1. **a página estava demorando** para carregar;
2. **a janela é nova** — ela não tem a sua conta ainda (é a regra do Chrome 136
   que eu expliquei: a porta de controle não abre no perfil do dia a dia).

A 0.91.27 tratava as duas como “não deu”: 25 segundos e desistia; e ao ver
“Sign In” mandava você rodar tudo de novo. Era pressa minha, não problema seu.

## O que muda

| antes | agora |
|---|---|
| 25 s e desiste | até **90 s** carregando, com o tempo aparecendo a cada 10 s |
| “Sign In” = pare e recomece | **espera você entrar** nessa janela (até 5 min) e **segue sozinho** quando a página das chaves aparece |
| conexão que cai = erro | **refaz** a conexão na mesma aba e continua |
| aba vazia = “não deu” | diz que a página **não terminou de carregar**, manda apertar F5 e lembra que a janela já está logada |

Traduzindo: na primeira vez, você clica em **Sign In** dentro da janela do
JARVIS, entra com a sua conta, e **não precisa fazer mais nada** — ele percebe
sozinho que a página das chaves apareceu e continua: “New key”, nome, “No
expiration”, “No limit”, “Create”, chave no `.env`.

Do segundo dia em diante nem isso: o login fica guardado na pasta `perfil-cdp`.

## O que fazer agora

1. Atualize (`atualizar.bat`).
2. Duplo clique em **`chrome-cdp.bat`**.
3. Se a janela abrir pedindo login, clique em **Sign In** ali dentro e entre.
   Deixe a janela preta aberta: ela vai mostrando o tempo e segue sozinha.

Se a página simplesmente não abrir, ele agora diz isso com clareza — e o
caminho é apertar **F5** naquela janela e rodar o `chrome-cdp.bat` de novo (ele
aproveita a janela que já está aberta; não pede login outra vez).

## Como isso foi testado

Quatro testes novos, e todos **reprovam** contra o código da 0.91.27:

- a página que responde “ainda carregando” seis vezes e depois vira a página
  das chaves — o trabalho tem de terminar com a chave no `.env`;
- a tela de entrada que aparece cinco vezes e depois a página das chaves — o
  programa espera e **continua sozinho**;
- ninguém entra na janela — uma frase clara, e **nenhum clique** na página;
- a aba que nunca carrega — a mensagem culpa o carregamento (e manda F5), não o
  clique.

Suíte: **3.816 testes**, 7 pulados.
