# Conectores: Gmail, WhatsApp e sites (0.81.0)

A pergunta: *“mas quero que o modelo tenha acesso à minha caixa ou o JARVIS
acesso ao Gmail, WhatsApp e conectores igual a você.”*

A resposta honesta começa por uma distinção que muda tudo: **existem três níveis
de acesso**, e o que dá para fazer sem burocracia é o segundo.

| nível | o que é | precisa de quê | o que o JARVIS consegue |
|---|---|---|---|
| **1. sessão do navegador** | você já está logado; o JARVIS monta o link certo | nada | abrir a busca pronta do Gmail, abrir a conversa do WhatsApp com o texto no campo |
| **2. IMAP** | o JARVIS lê a caixa pelo protocolo | senha de app (1 minuto, uma vez) | **ler assunto, remetente e data de verdade** e triar por regra determinística |
| **3. OAuth** | o JARVIS recebe um token em seu nome | projeto no Google Cloud + consentimento | ler, marcar como lido, **enviar**, mexer na agenda |

Os conectores que eu uso (Gmail, Agenda, Drive, Notion…) são nível 3 — e o token
fica no servidor de quem hospeda o agente, **não no seu PC**. Para o JARVIS
local, o nível 3 existe, mas exige que **você** crie o projeto no Google Cloud.
Isso é burocracia sua, e por isso o padrão daqui é o nível 2.

---

## Ligar a caixa de e-mail (IMAP, somente leitura)

### Passo 1 — a senha de app (só no Gmail)

1. abra `myaccount.google.com/security`;
2. ligue a **verificação em duas etapas** (se ainda não estiver ligada);
3. abra `myaccount.google.com/apppasswords`;
4. dê um nome (`jarvis`) e clique em **Criar**;
5. o Google mostra **16 letras em 4 grupos**. É essa a senha — **não** a da conta.

A senha normal da conta **não funciona** por IMAP. Quem tenta usá-la recebe
"login recusado", e é exatamente o que a tela diz quando isso acontece.

### Passo 2 — colar no JARVIS

1. **Configurações** → cartão **Conectores**;
2. e-mail: `seuemail@gmail.com`;
3. senha: as 16 letras (os espaços são removidos sozinhos);
4. servidor: deixe vazio — o JARVIS deduz pelo domínio (`gmail.com`,
   `outlook.com`, `hotmail.com`, `yahoo.com`, `bol`, `uol`, `terra`); domínio
   desconhecido pede o endereço à mão;
5. **Ligar a caixa** → depois **Testar**.

Se respondeu, já funciona. E se o provedor recusar, a frase é sobre senha de app
— nunca sobre "erro desconhecido".

### O que ele faz — e o que promete não fazer

| faz | não faz |
|---|---|
| abre a pasta com `EXAMINE` (somente leitura) | não marca nada como lido |
| baixa **só os cabeçalhos** com `BODY.PEEK` | não baixa o corpo dos e-mails |
| lê assunto, remetente, destinatário e data | não apaga, não move, não arquiva |
| aplica as regras do `correio` (intimação 100, fatura 85, governo 75, segurança 70) | não envia e-mail |

O corpo não é baixado por dois motivos: velocidade (30 cabeçalhos em uma chamada)
e discrição (o conteúdo não sai da caixa). A triagem usa assunto, remetente e
data — que é o que define prioridade nas regras.

### Usar no chat

```
filtra meus e-mails por importância
quais e-mails importantes chegaram essa semana
```

Com a caixa ligada, o JARVIS **não** manda mais exportar o Takeout: ele lê a
caixa na hora e responde com prioridade, categoria e motivo, assim:

```
[100] Intimação para audiência — intimacao@tjsc.jus.br (2026-11-03)
      · Intimação / processo · intimação
[ 85] Sua fatura de energia vence em 05/11/2026 — fatura@energiasul.com.br
      · Fatura / boleto · fatura, vence em 1 dia(s)
```

O mesmo conteúdo está disponível como skill: `conectores.email-triar`
(limite e janela de dias ajustáveis) e `conectores.estado`.

---

## WhatsApp

Não existe API grátis do WhatsApp para uso pessoal — e automatizar o WhatsApp Web
viola os termos. O JARVIS faz o que é legítimo e útil:

### Abrir a conversa com o texto pronto

```
manda um oi para a Ana no whatsapp
```

O JARVIS monta `https://web.whatsapp.com/send?phone=5548…&text=…`, que abre no
navegador onde você já pareou o celular, com a mensagem no campo. **Quem aperta
Enter é você** — a skill devolve `enviado: false` e diz isso na resposta.

O 55 do Brasil entra sozinho quando você digita `48 99999-1234`.

### Ler o conteúdo: a conversa exportada

1. no celular, abra a conversa;
2. ⋮ → **Mais** → **Exportar conversa** → **sem mídia**;
3. mande para o PC (Drive, cabo, e-mail) e salve o `.txt` em
   `storage/whatsapp/`;
4. pergunte: `lê a conversa do whatsapp`.

O JARVIS entende os dois formatos que o app usa:

```
12/03/2024 14:05 - Ana: mensagem
[12/03/2024, 14:05:32] Ana: mensagem
```

E devolve quem falou, quando e o quê — sem inventar resumo.

---

## Por que não “conectar tudo com um clique”

Porque seria mentira. Para ler Gmail **pelo protocolo oficial** sem senha de app,
o caminho é OAuth: criar um projeto no Google Cloud, ativar a API do Gmail,
configurar a tela de consentimento, gerar `client_id` e `client_secret` e guardar
o token. É gratuito, mas são ~15 minutos de burocracia **sua** no painel do
Google, e o token precisa ser renovado.

Quando (e se) você quiser esse nível, o caminho já está preparado: o JARVIS fala
OpenAI-compatible com qualquer provedor, as skills são declarativas e o `.env` é
o único lugar de configuração. Mas eu não vou fingir que ele existe antes de
existir.

## O que **não** vai acontecer

- **Ler WhatsApp sem o celular pareado** — não existe.
- **Enviar e-mail pelo JARVIS** nesta versão — o rascunho é montado, o envio é
  seu (SMTP fica para quando houver OAuth ou senha de app com sua autorização
  explícita).
- **Guardar sua senha em texto fora do `.env`** — ela fica só ali, nunca volta
  numa resposta, nunca aparece na tela.

## Estado de cada conector

| conector | nível | grátis | falta |
|---|---|---|---|
| Sua caixa de e-mail | IMAP somente leitura | sim | senha de app (1 minuto) |
| Gmail e sites | sessão do navegador | sim | nada |
| WhatsApp | navegador + conversa exportada | sim | o `.txt` para ler o conteúdo |
