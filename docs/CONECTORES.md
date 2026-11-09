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

---

# Conectores por token: Notion, Linear, Dropbox, Vercel e Supabase (0.82.0)

*“Não tem como criar conectores igual ao do Arena?”* — Tem, e a diferença é
menor do que parece.

## OAuth e token pessoal são a mesma porta

| | OAuth (o que o Arena usa) | token pessoal (o que o JARVIS usa) |
|---|---|---|
| quem cria a credencial | o time do Arena registrou o aplicativo no serviço | **você** cria a chave no painel do serviço |
| o que o serviço devolve | um token | um token |
| onde ele fica | no servidor de quem hospeda o agente | **no `.env` desta máquina** |
| tempo para começar | zero (já está pronto) | ~1 minuto por serviço |

O resultado é o mesmo: o JARVIS fala com o serviço em seu nome. O que muda é
**quem registra o aplicativo**. Para OAuth no seu PC, esse aplicativo teria de
ser registrado por você em cada serviço — mais trabalho, não menos.

## Como ligar (exemplo: Notion)

1. abra `notion.so/my-integrations`;
2. **New integration** → nome `jarvis` → escolha o workspace → **Save**;
3. copie o **Internal Integration Secret** (começa com `secret_` ou `ntn_`);
4. no JARVIS: **Configurações → Conectores → Serviços com token pessoal**;
5. **Colar token** → cole → **Guardar token** → **Testar**.

O Teste faz uma leitura de verdade (`GET /v1/users/me`) e responde com o nome do
workspace. Se der 401, a frase diz que o token foi recusado e onde gerar outro.

> **Notion:** a integração só vê as páginas que você **compartilhar com ela**
> (na página: ⋯ → Connections → jarvis). Sem isso, a API responde vazio — não é
> erro do JARVIS.

## Os cinco, e onde pegar a chave

| serviço | onde a chave nasce | o que o teste lê |
|---|---|---|
| **Notion** | `notion.so/my-integrations` | workspace dono do token |
| **Linear** | `linear.app/settings/api` | seu nome e e-mail |
| **Dropbox** | `dropbox.com/developers/apps` → Generated access token | nome da conta e espaço |
| **Vercel** | `vercel.com/account/tokens` | usuário e times |
| **Supabase** | painel do projeto → Settings → API → `service_role` | tabelas do projeto (pede o endereço `https://xxx.supabase.co`) |

**Linear** autentica o token **cru** no cabeçalho `Authorization` (sem
“Bearer”); **Supabase** usa `apikey` + `Bearer`. Cada serviço tem o seu jeito, e
o módulo sabe qual é — você não precisa saber.

## O que o módulo garante

- o token **nunca** volta numa resposta: o estado mostra `secr…cdef (54 caracteres)`;
- **não** grava token curto nem com espaço (erro de cópia acontece muito);
- `Esquecer` apaga **só aquela** variável do `.env`;
- o Teste é **leitura**, nunca escrita: nada é criado, alterado ou apagado no
  serviço durante o teste.

## O que ainda falta (e o que eu preciso de você)

O que existe hoje é a **porta**: ligar, testar, saber o que está ligado. As
**ações** de cada serviço — listar páginas do Notion, criar tarefa no Linear,
mandar arquivo para o Dropbox, disparar deploy na Vercel, consultar tabela no
Supabase — dependem de qual você usa primeiro.

Diga **um** para começar e eu construo as três ações mais úteis dele na próxima
versão, com a mesma regra de sempre: leitura primeiro, escrita com confirmação.

## O que fica de fora, e por quê

- **Google (Gmail, Agenda, Drive, Docs, Sheets, Slides) por OAuth**: dá, mas exige
  que **você** crie um projeto no Google Cloud (~15 min, grátis). O Gmail já
  resolve por IMAP (`docs/CONECTORES.md` §1); os outros ficam para quando você
  quiser pagar esse pedágio.
- **WhatsApp**: não existe API para uso pessoal — ver §2 deste documento.
- **Slack, Discord, GitHub**: mesmo esquema de token pessoal; entram quando
  fizerem falta.
