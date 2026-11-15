# JARVIS 0.91.15 — a chave sai daqui preenchida e salva na pasta

Sua tela mostrou exatamente o travamento. O diálogo **Create API key** não é só
o nome:

```
Name *            (você digita)
Expiration *      “Select expiration”   ← obrigatório
Credit limit *    “Choose a credit limit”
                              [ Create ]   ← fica apagado sem a expiração
```

O JARVIS escrevia o nome e ia direto no Create. O botão estava apagado, o
clique “aconteceu” e nada foi criado — e o relatório dizia que tinha dado certo.
Foi por isso que a chave nunca chegava na pasta.

## O que ele faz agora

**1. Preenche o diálogo inteiro.** Nome (o `jarvis-2026-10-15`), depois abre a
lista de expiração, depois a do limite.

**2. Escolhe o maior prazo, não o mais curto.** Se existir “Never”, é ele. Se
não, o mais longo (“1 year” ganha de “30 days”). Isso é de propósito: uma chave
que expira em 90 dias derruba o JARVIS três meses depois, e ninguém liga uma
coisa à outra.

**3. No crédito, “No limit”.** Escolher um teto faria a chave parar sozinha no
meio do mês.

**4. Confere se criou.** Depois de clicar em Create, ele relê a janela. Se o
diálogo continua aberto, **não criou** — e ele diz isso, com o nome do campo que
faltou preencher. Antes ele seguia em frente como se tivesse dado certo.

**5. Copia e salva na pasta.** Depois de criada, copia o texto da página
(Ctrl+A, Ctrl+C — não depende de botão) ou clica em Copy, lê a área de
transferência e grava no `.env` que está na pasta do JARVIS. O `.env` é o
“próprio sistema”: é dele que o JARVIS lê a chave ao abrir.

## Se algum campo não der

A lista de expiração pode não abrir na leitura. Nesse caso ele avisa
*“sem a expiração o botão Create costuma ficar apagado”*, tenta mesmo assim,
confere, e se não criou diz: complete no navegador e rode `--pegar` — sem
refazer nada, sem perder o que já foi feito.

**Nada é gravado sem chave.** Se o diálogo não abriu, ele para ali em vez de
clicar no “New key” de novo e fingir sucesso.

## O que foi provado

Com um OpenRouter falso que **só cria quando os três campos estão preenchidos**
(igual ao de verdade, com as listas abrindo ao clicar):

- o caminho completo: New key → nome → “Never” → “No limit” → Create → Copy →
  gravação no `.env`;
- sem “Never”, o prazo escolhido é “90 days”;
- com as listas que não abrem, o Create não cria, o script detecta o diálogo
  ainda aberto e diz qual campo faltou — sem gravar nada;
- diálogo que não abre: para no primeiro clique, não insiste;
- `--sem-mouse` não move o ponteiro em passo nenhum.

## Ainda pendente, e eu não esqueci

Você pediu antes o acesso às senhas salvas do Chrome para ele entrar sozinho.
Vou fazer isso depois deste — e já adianto o que vou encontrar: o Chrome não
entrega senha para outro programa, e o caminho que funciona é a conta que ele
já lembrou (`JARVIS_CONTA_GOOGLE`) mais uma senha que **você** informa uma vez.
Voltamos nisso quando esta chave estiver gravada.
