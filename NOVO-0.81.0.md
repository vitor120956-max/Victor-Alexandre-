# JARVIS 0.81.0 — Gmail, WhatsApp e conectores: o que é real e o que é conversa

Sua pergunta: *“quero que o modelo tenha acesso à minha caixa, ou o JARVIS acesso
ao Gmail, WhatsApp e conectores igual a você.”*

Antes da resposta, uma confissão útil: **conector não é mágica, é credencial**.
Os que eu uso funcionam porque existe um servidor no meio guardando um token que
você autorizou uma vez. No seu PC, o JARVIS precisa da mesma coisa — e é aí que
a maioria dos programas mente. Este não mente: ele declara o **nível**.

| nível | o que é | precisa | o que consegue |
|---|---|---|---|
| 1. sessão do navegador | você já está logado | nada | abrir a busca pronta do Gmail, abrir a conversa do WhatsApp |
| **2. IMAP** | lê a caixa pelo protocolo | **senha de app (1 minuto)** | **ler assunto, remetente e data de verdade e triar** |
| 3. OAuth | token em seu nome | projeto no Google Cloud | ler, marcar como lido, **enviar**, agenda |

O nível 2 está pronto nesta versão. O nível 3 está descrito com honestidade: é
burocracia **sua** no painel do Google, e eu não vou fingir que existe.

## Ligar sua caixa agora (3 minutos)

**Passo 1 — a senha de app.** No Gmail a senha normal **não funciona** por IMAP.

1. abra `myaccount.google.com/security`
2. ligue a **verificação em duas etapas** (se ainda não estiver)
3. abra `myaccount.google.com/apppasswords`
4. nome `jarvis` → **Criar**
5. copie as **16 letras** que aparecem em 4 grupos

**Passo 2 — colar no JARVIS.**

1. **Configurações** → cartão **Conectores**
2. e-mail: `seuemail@gmail.com`
3. senha: as 16 letras (os espaços saem sozinhos)
4. servidor: deixe vazio — ele deduz pelo domínio
5. **Ligar a caixa** → **Testar**

Se o provedor recusar, a frase é sobre **senha de app** — não um "erro
desconhecido".

**Passo 3 — usar.**

```
filtra meus e-mails por importância
quais e-mails importantes chegaram essa semana
```

E ele responde com prioridade, categoria e motivo:

```
[100] Intimação para audiência — intimacao@tjsc.jus.br (2026-11-03)
      · Intimação / processo · intimação
[ 85] Sua fatura de energia vence em 05/11/2026 — fatura@energiasul.com.br
      · Fatura / boleto · fatura, vence em 1 dia(s)
```

## O que ele faz — e o que promete não fazer

| faz | não faz |
|---|---|
| abre a pasta com `EXAMINE` (somente leitura) | **não marca nada como lido** |
| baixa só os **cabeçalhos** com `BODY.PEEK` | não baixa o corpo dos e-mails |
| lê assunto, remetente, destinatário e data | não apaga, não move, não arquiva |
| aplica as regras do `correio` (intimação 100, fatura 85, governo 75…) | **não envia e-mail** |

Essas três colunas não são frase de efeito: há teste que falha se o conector
chamar `STORE` ou deixar de pedir `PEEK`. A promessa está presa por código.

## WhatsApp

Não existe API grátis para uso pessoal — e automatizar o WhatsApp Web viola os
termos. O que existe:

**Abrir a conversa com o texto pronto**
```
manda um oi para a Ana no whatsapp
```
Monta `web.whatsapp.com/send?phone=5548…&text=…` com a mensagem no campo. **Quem
aperta Enter é você** — a resposta diz `enviado: false`, sem fingir.

**Ler o conteúdo: a conversa exportada**
1. no celular: conversa → ⋮ → **Mais** → **Exportar conversa** → **sem mídia**
2. mande o `.txt` para o PC e salve em `storage/whatsapp/`
3. pergunte: `lê a conversa do whatsapp`

Ele entende os dois formatos que o app usa e devolve quem falou, quando e o quê.

## Sobre “o modelo ter acesso”

Detalhe importante: **o modelo não acessa nada** — ele recebe texto. Quem acessa é
o JARVIS. A caixa é lida pelo conector (determinístico), triada por regra fixa, e
só então o resultado vira texto para o modelo, se houver um. Isso é melhor do que
dar ao modelo uma chave da sua caixa:

- o que sai da máquina é **assunto, remetente e data** — não o corpo dos e-mails;
- a classificação não depende do humor do modelo: as regras são as mesmas todas as vezes;
- sem modelo configurado, `filtra meus e-mails` **continua funcionando**.

## As quatro skills novas (315 → 319)

| skill | o que faz |
|---|---|
| `conectores.estado` | o que está ligado, em que nível, o que falta |
| `conectores.email-triar` | lê a caixa ao vivo e tria (limite e janela de dias) |
| `conectores.whatsapp-link` | monta o link com o texto pronto, sem enviar |
| `conectores.whatsapp-ler` | lê o `.txt` exportado do WhatsApp |

## O que eu recusei fazer

- **Guardar sua senha fora do `.env`** — fica só ali, nunca volta numa resposta.
- **Ler o WhatsApp pela força** (automação do Web) — viola os termos e quebra a
  cada atualização deles.
- **Prometer “conectar tudo com um clique”** — seria mentira, e este projeto já
  pagou caro por prometer o que não entregava (a tela velha, as quatro chaves).

## Números medidos

- pytest: **3.388 passed, 2 skipped, 0 failed** (25 testes novos do conector)
- vitest: **134 passed**
- manifesto: **508 arquivos**
- skills: **319**
