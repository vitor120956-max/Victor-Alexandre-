# JARVIS 0.91.12 — ele abre, ele copia, ele grava

Você está certo, e eu tinha feito meio caminho: o `pegar-chave.bat` abria a
página e **esperava você**. Abrir e esperar não é autonomia — é uma janela
aberta com alguém do lado de fora.

Agora ele faz a coisa inteira num duplo clique.

## O que o duplo clique faz

1. **descobre o site pelo provedor que está no seu `.env`** — OpenRouter abre
   `openrouter.ai/keys`, Groq abre `console.groq.com/keys`, Google abre
   `aistudio.google.com/apikey`, e o mesmo vale para os outros do catálogo.
   Não é um site só no código: é o site do provedor que você escolheu;
2. abre a página no seu navegador, que já está logado;
3. acha **a janela certa** — se o Chrome está aberto com o e-mail numa janela e
   as chaves em outra, ele lê a das chaves. Antes, todas as janelas do Chrome
   empatavam e ele podia ler a errada;
4. clica em Create Key, escreve o nome, clica em Create (com o mouse, como você
   pediu, e devolvendo o cursor para onde estava);
5. copia: **primeiro pelo texto da página** (Ctrl+A, Ctrl+C). Isso não depende
   de achar botão nenhum — depois de criar, a chave está escrita na tela, e a
   mesma régua que lê chave de arquivo acha ela ali. Se não der, ele tenta o
   botão Copy;
6. grava no `.env` — só a chave, sem perguntar nada.

## Quando ele não consegue clicar

Isso pode acontecer: o Chrome nem sempre conta a quem pergunta quais são os
botões da página. Nesse caso o comando **não termina em erro**. Ele:

- deixa a página aberta no site;
- escreve na tela os quatro cliques (Create Key → nome → Create → COPIAR);
- fica olhando a área de transferência por dois minutos;
- quando você copia, ele lê, grava e fecha dizendo o que gravou.

Ou seja: no pior caso, o trabalho é um clique em COPIAR. No melhor, nenhum.

## Um defeito que os testes pegaram antes de você

A primeira versão do `--auto` tirava a “foto” da área de transferência **no
passo 4**. Só que o clique em Create já tinha colocado a chave nova lá — então
o programa comparava a chave nova com ela mesma, concluía “nada mudou” e
recusava a chave que ele mesmo tinha acabado de criar.

A foto agora é tirada **antes do primeiro clique**, e ela serve para uma coisa
só: não confundir com uma chave que você tenha copiado antes. Um teste com uma
chave velha na área confirma: a que é gravada é a nova.

## O que foi provado

Com navegador, Windows e área de transferência falsos: o caminho inteiro
(abrir → criar → copiar → gravar), a escolha da janela certa entre duas do
Chrome, o provedor vindo do `.env`, o `--provedor groq` abrindo o site da Groq,
o “sem autorizar não abre nem cria”, o plano B esperando a sua cópia, o
`Ctrl+C` recusado quando o teclado não está na janela, e a chave velha da área
sendo ignorada.

## O que não foi provado

Os cliques no seu Chrome. Continuam dependendo de o navegador publicar os
botões — é o que o `--ver` mede em dois segundos. A diferença desta versão é
que, se não publicar, **o duplo clique ainda resolve**, só com uma cópia sua.
