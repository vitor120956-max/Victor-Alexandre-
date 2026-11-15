# JARVIS 0.91.19 — o nome agora entra no campo

Progresso de verdade: **o painel abriu**. O clique de mouse da 0.91.18 resolveu
aquilo. O que faltou foi o nome.

## Por que o nome não entrou

No painel “Create API key”, o rótulo **Name** e a caixa de texto são **dois
elementos diferentes** na leitura. O script procurava pelo nome, achava o
**rótulo**, clicava nele e mandava as teclas para o nada — e seguia dizendo
“escrevendo…”, como se tivesse dado certo.

## O que mudou

**1. O texto vai para quem aceita escrever.** A caixa é reconhecida pela ação
(“escrever”), não pelo nome que ela publica.

**2. Se o campo não tem nome, a posição decide.** O painel tem uma ordem fixa —
Name, Expiration, Credit limit. A caixa do nome é a que fica logo acima da
expiração, ou logo abaixo do rótulo “Name”. E o que está acima do título do
painel é a página (a busca “Search by name…”), então é descartado.

**3. Digitar agora é conferido.** Três degraus, cada um conferido: clique no
campo + teclado → foco pela árvore → teclado com a janela na frente. Antes ele
dizia “digitei” sem olhar.

**4. O botão apagado é a prova final.** Se o campo não publica o valor, quem
confirma é o “Create” acender. Se ele continua apagado, o script reescreve o
nome do zero — com `Ctrl+A` antes, para não virar “jarvis-testejarvis-teste”.

**5. Botão apagado não se clica.** Clicar num botão desabilitado não dá erro,
não cria nada e deixa você olhando uma tela parada — aconteceu duas vezes. Agora
ele para e diz **qual** campo faltou.

**6. O botão de criar deixou de ser confundido com o título.** “Create API key”
também contém “create” — e, quando o botão está apagado, o título passava na
frente.

## O que continua igual

- expiração **“Never”**, limite **“No limit”**;
- sem chave, nada é gravado; o cursor volta para o lugar;
- duplo clique em `pegar-chave.bat`.

## O que foi provado

Com um painel de mentira que é **igual ao do Chrome**: rótulo separado da
caixa, busca da página atrás do painel, “Create” que só acende com os três
campos.

- o nome vai para a caixa, não para o rótulo nem para a busca;
- caixa sem nome nenhum é achada pela posição;
- campo que recusa o texto (`conferido=False`) leva a outra tentativa;
- botão apagado: não clica, diz o campo que faltou e não grava nada;
- botão apagado + nome sem confirmação: reescreve o nome uma vez;
- “Create” exato não é o título “Create API key”.

Suíte inteira: **3.739 testes passando** (7 pulados: dependem do Windows real).
