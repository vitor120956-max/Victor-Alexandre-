# JARVIS 0.91.21 — a regra dos testes (e o buraco que ela achou)

Você pediu duas coisas: **teste automatizado do caminho inteiro** e, para
sempre, **todo bug corrigido ganha um teste de regressão**.

## O teste achou um bug antes de eu escrever a regra

Montei um Chrome de mentira que **muda de estado quando é clicado** — a página
só mostra o painel “Create key” depois do clique em **New key**, e os campos só
nascem depois que o painel abre. Rodei o caminho inteiro com o **programa de
verdade** (`main(["--auto", "--autorizar"])`): abrir → New key → nome →
Never → No limit → Create → copiar → gravar `.env`.

Com a página lenta, ele **desistia da criação** — exatamente o que aconteceu
no seu PC na 0.91.20. A causa: o modo automático usava a última leitura que
tinha em mãos, e essa leitura era de uma página ainda carregando.

**Corrigido:** sem o botão na leitura, ele espera a página sossegar e relê
fundo **antes** de desistir. É a mesma espera que o caminho manual já fazia.

## A regra, agora escrita e cobrada por máquina

`docs/TESTES.md` traz a regra e a tabela **versão → teste**. Um teste que
existe mas não está na tabela é teste que ninguém acha daqui a três meses.

E não é só documento: `server/tests/test_regras_do_projeto.py` reprova a suíte
quando

- alguma versão entregue (com `NOVO-*.md`, da 0.91.13 em diante) não tem teste
  de regressão listado;
- algum teste citado na tabela não existe no disco;
- o README não aponta para a regra.

Ele funciona: na primeira rodada reprovou porque eu ainda não tinha posto o
aviso no README.

## O que o teste de ponta a ponta cobre

**19 cenários**, um por print ou por frase sua:

- página lenta (o painel demora a nascer);
- moldura do Chrome aparecendo no meio da leitura;
- janela que mente na ação padrão (diz que fez, não fez);
- primeiro clique engolido pela página;
- nome que ia para o rótulo “Name” em vez da caixa;
- botão **Create** apagado até os três campos;
- chave velha ainda na área de transferência;
- `.env` com provedor, base e modelo que **continuam** intactos — só a chave
  muda;
- `--auto` sem `--autorizar` não cria nada (zero cliques).

Tudo com o `main()` de verdade, a escrita real do `.env` e as leituras
contadas: **menos de 40 leituras e 1 clique em “New key”** no caminho feliz.

## O que continua igual

- sem `--autorizar`, nada é criado nem gravado;
- expiração **“Never”**, limite **“No limit”**, nome `jarvis-AAAA-MM-DD`;
- botão “Create” apagado não é clicado;
- cursor volta para o dono;
- sem chave, o `.env` não é tocado.

Suíte inteira: **3.767 testes passando** (7 pulados: dependem do Windows real).
