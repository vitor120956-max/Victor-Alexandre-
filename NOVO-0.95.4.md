# 0.95.4 — o celular apareceu (e era só o cabo)

Antes de qualquer desculpa, a notícia: **o JARVIS leu o seu A34 inteiro.**

```
SM-A346M · Android 16 · 84,4 GB usados · 7,3 GB de RAM · 35,6 °C
patch de segurança de 2026-07-05 (141 dias atrás)
1 achado: com.dti.telefonica travando
```

E o `adb` funcionou **sem o driver**. A primeira varredura achou o aparelho e
leu tudo. Depois, a segunda disse "nenhum Android apareceu".

## 1. O que a sua tela me ensinou sobre o driver

Eu disse "o driver resolve". **Errado**, e a sua própria máquina provou. O driver
da Samsung serve para o MTP aparecer com nome certo; o `adb` funcionou sem ele.

E pior: eu escrevi que o instalador roda "com o celular desconectado". É o
contrário — o instalador da Samsung é da época do Kies e **quer o aparelho
plugado**. Agora o plano diz:

> Deixe o celular conectado por USB e desbloqueado.

## 2. O erro que travou tudo: token num `.bat` da própria máquina

```
Não consegui instalar o driver:
  Sem token e este pedido não veio da própria máquina.
```

Vindo de um `.bat` **na sua máquina**. O token existe para impedir que uma
página de site dispare instalação no seu PC — e um processo rodando com o seu
usuário já lê `storage/host-token.txt` de qualquer jeito. Exigir ali era teatro,
e o teatro custou o seu tempo.

Agora o **script local** passa sem token — e só ele. A isenção é um parâmetro
explícito (`script_local=True`) que apenas o caminho do `.bat` usa. A API
continua cobrando o token em tudo, porque uma chamada de lá pode vir de uma
página aberta no navegador. **O que continua valendo:**

- `JARVIS_HOST_REDE=1` e `JARVIS_HOST_INSTALAR=1` no `.env`;
- o token de uso único do plano de instalação;
- `JARVIS_HOST_EXIGIR_TOKEN_LOCAL=1` para quem quiser a trava de volta, mesmo aqui;
- a API pedindo token normalmente (`disco`, `baixar`, `instalar`, `executar`).

> O primeiro jeito que eu escrevi foi abrir `_exigir()` para todo mundo, e **8
> testes caíram** — exatamente os que prendem que a API exige token. Eles
> estavam certos e eu estava errado. Está registrado em `test_a_api_continua_exigindo_token`.

## 3. A segunda varredura mentiu

Ela disse "confira o cabo, ligue a Depuração USB" — a mesma frase de sempre,
sem olhar nada. O código **pergunta** ao Windows o que está na USB, mas o
PowerShell do seu Windows 1607 pode não responder, e quando ele não responde a
frase antiga fingia saber.

Agora ela diz o que sabe:

> Nenhum Android apareceu e eu **não consegui perguntar ao Windows** o que está
> na USB (…). Então não vou afirmar que é driver.

E, antes de baixar 33 MB, o JARVIS **pergunta ao Windows se o driver já está lá**.
Você rodou o `.bat` três vezes; seriam 99 MB por nada.

## 4. As mensagens que te fizeram digitar comando no prompt

`JARVIS_HOST_REDE=1` no `cmd` não é comando. A mensagem de erro agora diz isso:

> Rede desligada. Acrescente `JARVIS_HOST_REDE=1` no `.env` (na pasta do JARVIS,
> não no prompt do Windows).

## Sobre o "Pressione qualquer tecla"

Isso é do próprio Windows (`pause`), não do JARVIS. Ele espera a tecla justamente
para você poder ler; **Enter resolve**.

## O que fazer agora

Nada de driver. O que importa é a **segunda varredura vazia**:

1. Rode `atualizar.bat` (0.95.4) e `escanear-celular.bat` de novo.
2. Se aparecer de novo, a **primeira linha** da frase vai dizer se o JARVIS
   conseguiu perguntar ao Windows ou não. Essa distinção é a informação que eu
   preciso — antes eu não tinha como saber.

## Testes

6 novos, com prova por `git stash` nos que importam:

- script local não pede token (falha sem o conserto);
- `JARVIS_HOST_EXIGIR_TOKEN_LOCAL=1` mantém a trava;
- a mensagem de rede desligada fala de `.env`, não de comando;
- o plano avisa que o cabo tem de estar conectado;
- driver já instalado **não** baixa de novo;
- fora do Windows, "já instalado" nunca é verdade.
