# Correio — triar por importância e escrever no seu estilo

O pedido que originou esta camada: *“se eu pedir para ele entrar no meu Gmail e
filtrar por importância — faturas a pagar, intimações, e-mails do governo — ou
ver os padrões de e-mail que eu mando e copiar para ele enviar um e-mail”*.

Antes de qualquer promessa, o limite: **o JARVIS não entra na sua conta.** Ler a
caixa em tempo real exige OAuth do Google — isto é, uma credencial — e o projeto
foi feito sem chave. O que existe aqui é o caminho que funciona **sem credencial**:
você exporta a sua caixa (ou as mensagens que interessam) e o JARVIS lê o arquivo.

## O que dá para fazer hoje

| Você pede | Ele faz |
|---|---|
| `filtra meus e-mails por importância` | lê os `.eml`/`.mbox`, classifica e ordena por prioridade |
| `quais e-mails são importantes` | mesma triagem, mostrando só o topo |
| `analisa meus e-mails enviados` | mede o seu jeito: saudação, fecho, assinatura, tamanho, uso de lista |
| `escreve um e-mail para a Ana sobre o relatório: enviar planilha; pedir retorno` | monta o texto no seu padrão, com os pontos ditados |

Nada é aberto, marcado como lido, apagado ou enviado.

## Como exportar do Gmail

**Uma mensagem só** (o jeito mais rápido):

1. abra a mensagem no Gmail;
2. menu **⋮ → Baixar mensagem** (gera um `.eml`);
3. ponha o arquivo em `D:\JARVIS\storage\correio`.

**A caixa inteira** (para a triagem fazer sentido):

1. acesse [takeout.google.com](https://takeout.google.com);
2. desmarque tudo e marque só **Mail**, com **“Incluir todos os rótulos”**;
3. exporte e baixe o `.zip`; dentro dele há um `.mbox`;
4. copie o `.mbox` para `D:\JARVIS\storage\correio`.

O `X-Gmail-Labels` que vem no arquivo é o que permite separar **Enviados** de
**Caixa de entrada** — é assim que o padrão de escrita olha só o que **você**
escreveu.

## A triagem, regra por regra

Não há modelo nem “palpite”: são listas fechadas de termos em português,
aplicadas ao assunto e ao corpo.

| Categoria | Prioridade | O que dispara |
|---|---|---|
| Intimação / processo | **100** | intimação, citação, prazo, audiência, processo, tribunal, vara, DJE, PJe, mandado |
| Fatura / boleto | **85** (+10 se vence em até 7 dias) | fatura, boleto, vencimento, cobrança, débito automático, mensalidade, pagamento, PIX |
| Governo | **75** | gov.br, Receita Federal, SEFAZ, prefeitura, Detran, INSS, IPVA, imposto de renda, e-CAC, FGTS |
| Segurança / acesso | **70** | código de verificação, senha, acesso suspeito, novo login, 2FA |
| Pessoal | **45** | remetente humano sem termo de outra categoria |
| Newsletter / promoção | **5** | descadastrar, unsubscribe, promoção, oferta, cupom, “não responda” |

O **vencimento** só é aceito quando a data aparece perto de “vencimento”,
“vence”, “prazo” ou “até” — data solta no meio de uma nota fiscal não vira
boleto. Vencendo em até 7 dias, a prioridade sobe 10.

## O padrão de escrita

Só as mensagens **enviadas** entram na conta. O relatório traz:

- saudação mais comum (`olá`, `bom dia`, `prezados`…);
- fecho mais comum (`abraços`, `atenciosamente`, `att`…);
- assinatura — a última linha curta sem ponto final;
- média e mediana de palavras;
- porcentagem de mensagens com lista de marcadores.

Com isso, o rascunho já sai com a sua abertura, o seu fecho e a sua assinatura.
Sem nenhuma mensagem enviada, ele usa `Olá,` e `Atenciosamente,` e **avisa** que
foi genérico.

## O que ele não faz (e por quê)

1. **Não conecta no Gmail.** Sem OAuth, não há leitura em tempo real. Existe a
   camada `escritorio.*`, que monta os comandos do `gws` — mas ela também só
   monta: quem autentica é você.
2. **Não envia e-mail.** O rascunho é texto; enviar é decisão sua no Gmail (ou
   pelo `gws`, com a sua credencial).
3. **Não apaga, não arquiva, não marca como lido.**
4. **Não inventa categoria.** Se nenhum termo casar, a mensagem fica em
   “Pessoal” ou “Outro”, com prioridade baixa — e o motivo é mostrado.

## Onde ficam os arquivos

| Peça | Caminho |
|---|---|
| leitura, triagem, padrões, rascunho | `server/correio.py` |
| seus e-mails exportados | `storage/correio` (ou `JARVIS_DADOS/correio`) |
| skills | `correio.arquivos`, `correio.triar`, `correio.padroes`, `correio.rascunho` |
| testes | `server/tests/test_correio.py` (24, com `.eml` e `.mbox` montados no teste) |

A pasta aceita também caminho absoluto **dentro de `storage/`** ou da pasta
**Downloads** — o mesmo confinamento de `files.import`. Qualquer outro caminho é
recusado.
