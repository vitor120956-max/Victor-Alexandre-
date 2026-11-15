# JARVIS 0.91.10 — o mouse no botão de copiar

Sua pergunta foi direta: por que não clicar no botão de copiar com o mouse?
Resposta curta: agora clica. E a versão anterior tinha três defeitos que só
apareceram quando fui ligar isso.

## O que mudou

**1. O clique de verdade.**

O JARVIS lia o botão na página e pedia ao Windows “execute a ação padrão deste
elemento”. Quando o botão não declara essa ação — ou quando a leitura veio pela
UIAutomation, que não fala com a MSAA —, não havia mais nada: o script desistia.
Agora, com a posição medida na leitura, ele move o cursor até o centro do
botão, clica uma vez e **devolve o cursor para onde estava**.

**2. Três travas antes de tocar no ponteiro.**

- a janela do Chrome precisa estar **na frente** — clique às cegas acerta o que
  estiver por cima, e por cima pode estar qualquer coisa sua;
- o ponto precisa cair **dentro do retângulo da janela** — se a página rolou
  depois da leitura, a conta não vale mais e ele recusa em vez de clicar torto;
- se você mexer o mouse no meio do caminho, ele **para na hora** (o freio que já
  existia no `mesa`).

**3. O clique que falhava em silêncio.**

O resultado do clique era descartado. Se o passo 1 não dava, o script seguia
para o passo 2 e culpava o passo errado. Agora quem não executou vira erro com
o motivo que o Windows deu, e a sequência **para ali**.

## Uma quarta coisa, achada pelos testes

O botão que fecha o diálogo de criação não se chama “Create Key”: chama-se
**“Create”**. A 0.91.9 procurava o rótulo longo, não achava e concluía que a
página tinha mudado. Isso apareceu num teste com páginas falsas, antes de você
gastar uma chave descobrindo. Agora existe uma lista própria para o botão do
diálogo.

## Como ficou o comando

```
.venv\Scripts\python chave-no-navegador.py --ver
.venv\Scripts\python chave-no-navegador.py --criar --autorizar
```

O `--ver` continua só lendo, e agora diz também **se o mouse tem onde acertar**:
“botão de copiar: SIM — “Copy” (em 980,500 — o mouse acerta)”.

O `--criar --autorizar` clica com o mouse por padrão. Quem não quiser o ponteiro
mexido usa `--sem-mouse` — e aí vale só a ação do elemento. `--mouse` força o
clique físico desde o primeiro passo, sem tentar a árvore.

Sem `--autorizar`, nada é clicado: ele mostra a sequência e espera.

## O que foi provado, e o que não foi

Provado, com páginas falsas e Windows falso: a ordem dos cinco passos, o nome
digitado, o mouse chegando em cada clique, o `--sem-mouse` desligando o mouse, a
falha parando no passo certo, e a chave que veio da área de transferência sendo
gravada (73 caracteres exatos, sem lixo).

**Não provado:** o clique em pixel na sua tela. Depende de a posição medida
estar certa no seu monitor — se o Windows estiver com escala diferente de 100%,
a conta pode sair deslocada. Por isso o `--ver` mede primeiro: ele mostra a
posição que encontrou, e você vê se o número combina com o botão na tela antes
de deixar o `--criar` agir.
