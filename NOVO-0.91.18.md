# JARVIS 0.91.18 — o clique era de mentira

O print explica tudo numa linha:

    1. clicando em “New key”…
       ação padrão do elemento

“Ação padrão do elemento” é o pedido de clique pela árvore de acessibilidade.
No Chrome, para esse botão, **ela devolve sucesso e não faz nada**. O script
achava que tinha clicado, esperava 35 segundos, tentava de novo, esperava mais
35 — e a página continuava igual, com o painel fechado.

O clique de verdade (o do mouse) existia no código, mas só era tentado quando
você passava `--mouse`. O `pegar-chave.bat` não passa. Resultado: o duplo
clique nunca clicava de verdade.

E a prova estava na sua própria história: na **0.91.15** o clique saiu como
*“clique físico em 68,317”* e **o painel abriu** — quem não viu foi a leitura.
Ação do elemento: nada. Clique de mouse: funciona.

## O que mudou

**1. O clique de mouse vem primeiro.** É o que uma pessoa faz e o que
comprovadamente abre o painel.

**2. A janela é confirmada na frente.** Antes de clicar, o JARVIS traz a janela
para a frente **e confere** pelo próprio Windows que ela está na frente.
`SetForegroundWindow` pode dizer “ok” sem trocar nada — e o primeiro clique
nesse caso só ativa a janela em vez de apertar o botão.

**3. Escada de três degraus, cada um conferido:** clique de mouse → clique de
novo (para o caso do primeiro só ter ativado a janela) → ação do elemento.
Se o painel abrir em qualquer degrau, ele para ali.

**4. Esperas curtas.** 12 s, 12 s e 10 s entre os degraus, em vez de 70
segundos parado depois de um clique que não fez nada. O total é menor e cada
segundo tem uma tentativa de verdade dentro.

**5. Ctrl+C não vira erro.** Antes saía um traceback de oito linhas e o `.bat`
seguia como se tivesse dado certo. Agora: *“Interrompido com Ctrl+C. Nada foi
gravado.”*

**6. O `--pegar` parou de mentir.** Se a chave da área de transferência é a
mesma que já estava no `.env`, ele diz *“é a MESMA chave — nada mudou”* em vez
de anunciar que gravou uma nova. Foi o que aconteceu depois do Ctrl+C: ele
salvou a chave velha e o `.bat` disse “pronto”.

**7. O relatório ficou mais útil.** Se ainda falhar, `chave-leitura.txt` agora
também lista o que cada tentativa de clique fez.

## O que continua igual

- expiração **“Never”**, limite **“No limit”**;
- sem painel, para; sem chave, nada é gravado;
- o cursor volta para onde estava depois de cada clique;
- `--sem-mouse` continua existindo e não mexe no ponteiro;
- duplo clique em `pegar-chave.bat` é tudo o que você faz.

## O que foi provado

- o primeiro clique pedido é o do mouse (e `--sem-mouse` não pede clique físico);
- primeiro clique que só ativa a janela → segundo clique → painel, chave criada;
- clique recusado pelo Windows para a escada e diz o motivo;
- janela que não vem para a frente é avisada, e o clique é tentado mesmo assim;
- Ctrl+C sai com 130 e uma frase, sem traceback;
- `--pegar` com a chave repetida não regrava e avisa.

Suíte inteira: **3.730 testes passando** (7 pulados: dependem do Windows real).
