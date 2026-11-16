# JARVIS 0.91.27 — parei de adivinhar: agora ele pergunta à página

O seu console de 16/11 respondeu a pergunta que vinha desde a 0.91.21, e a
resposta foi dura: **ler a tela não dá certo nesta máquina**.

Duas provas, no mesmo dia:

- o diagnóstico da 0.91.26 ligou o modo leitor de tela **antes** de ler, pediu a
  árvore **três vezes** e nas três rodadas “DEPOIS do pedido” continuou em
  3/3/3/3/2 elementos;
- o `pegar-chave.bat` leu **quatro nomes**: “Keys | Settings | OpenRouter” duas
  vezes e “Restaurar páginas?” duas vezes. Isso não é a página — é a moldura de
  uma janela que o Chrome abriu perguntando se quer restaurar as abas.

E aí ele fez pior: chamou essa leitura de “a página foi lida inteira e o botão
estava nela”. Não estava.

## O que muda

**O JARVIS deixa de ler a tela.** O Chrome tem uma porta de controle própria —
a mesma que o F12 usa. Por ela o programa não olha pixels nem árvore de
acessibilidade: ele **pergunta à página** onde estão os botões e recebe a
resposta em texto. Mesma pergunta, mesma resposta. Não tem “às vezes funciona”.

O atalho novo é este:

    chrome-cdp.bat

Um duplo clique. Ele abre um Chrome **próprio do JARVIS** e faz o serviço
inteiro: acha o “New key”, abre o painel, digita o nome, escolhe “No
expiration”, escolhe “No limit”, clica em “Create”, pega a chave e grava no
`.env`.

O seu Chrome do dia a dia **não é fechado** — nem `taskkill`, nem balão de
restaurar páginas, nem aba perdida.

**Uma coisa vai ser pedida uma vez só:** na primeira execução, entre na sua
conta do OpenRouter **na janela que o JARVIS abrir**. Ela é separada da sua por
uma regra do próprio Chrome: desde a versão 136 o Chrome **recusa** abrir a
porta de controle no perfil normal (é proteção contra roubo de cookie). O login
fica guardado na pasta `perfil-cdp`, dentro do JARVIS, e não é pedido de novo —
nem quando você atualizar o programa.

## E o caminho antigo?

Continua lá, inteiro. O `pegar-chave.bat` passou a fazer assim: se o Chrome do
JARVIS estiver aberto (porta 9222 respondendo), ele vai por dentro dele; se
não, faz o caminho de sempre, esperando você copiar a chave.

## A mensagem errada também foi corrigida

Quando a leitura traz **títulos repetidos** (o mesmo nome duas vezes) ou o
balão “Restaurar páginas?”, o JARVIS agora sabe que **aquilo não é a página**.
Antes ele contava 4 nomes, achava que estava tudo bem e culpava o clique. Agora
ele diz que a leitura não chegou na página — que é a verdade.

## O que foi testado, e como

Não testei no seu PC — não consigo. O que fiz foi tirar o risco de onde dava:

- o transporte do protocolo do Chrome é testado contra um Chrome falso numa
  thread (aperto de mão, quadros, resposta casada, erro do Chrome traduzido);
- **o JavaScript que vai para a página roda de verdade no `node`**, sobre uma
  página falsa que tem o OpenRouter **e** a moldura do seu print de 16/11. Se o
  clique cair no lugar errado com os títulos repetidos na frente, o teste falha
  aqui — não no seu PC;
- o fluxo inteiro é testado com uma página que só entrega a chave depois do
  “Create”, e que **para** quando o painel não abre, quando a janela está sem
  conta e quando falta o `--autorizar`.

Total: **3.812 testes**, 7 pulados.

## O que fazer agora

1. Atualize o JARVIS (`atualizar.bat`).
2. Duplo clique em **`chrome-cdp.bat`**.
3. Na primeira vez, entre na sua conta do OpenRouter na janela que abrir.
4. Rode o `chrome-cdp.bat` de novo (ou o `pegar-chave.bat`, que agora aproveita
   a mesma janela).

Se algo falhar, a mensagem vai começar com “NÃO DEI” e dizer o motivo em uma
frase. Me manda essa frase — com ela eu sei onde olhar sem você ficar testando
às cegas.
