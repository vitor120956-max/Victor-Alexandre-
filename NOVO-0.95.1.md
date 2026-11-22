# 0.95.1 — “vai chover amanhã?” não é pedido para fechar app

Você perguntou do tempo e recebeu:

> A skill “Fechar um app no celular” recusou o pedido: Nome de pacote inválido.

Três defeitos atrás de uma frase. Nenhum deles era “o JARVIS não sabe o tempo”.

## 1. O motor local não errou — o modelo sim

Antes de acusar o casamento de skills, medi:

```
pontuar("vai chover amanha", celular.fechar-app)  →  0.00
melhor casamento de toda a frase                   →  0.11   (limiar: 0.50)
```

O motor local **jamais** escolheria essa skill. Quem escolheu foi o modelo, e
mandou a frase inteira no campo `pacote`. O defeito é que **nada barrava** isso.

## 2. O campo `pacote` agora recusa frase

Uma frase com espaço não é nome de pacote. E a recusa mudou de tom:

> Isso não é o nome de um app Android — parece uma frase inteira. **Se o pedido
> não é fechar um app no celular, ele não é para esta skill.**

Antes ela dizia “use o nome do app como o Android conhece” — como se quem
perguntou sobre chuva tivesse errado o nome de um pacote.

## 3. O chat não manda mais a frase inteira

`agente_local` tratava `pacote` como campo de texto livre. “fecha o
com.dti.telefonica no celular” virava o nome do pacote. Agora:

| você digita | o que vai como pacote |
|---|---|
| `fecha o com.dti.telefonica no celular` | `com.dti.telefonica` |
| `fecha o com.dti.telefonica. onde pego o zip?` | `com.dti.telefonica` |
| `fecha o whatsapp` | *(falta o campo — eu pergunto, em vez de mandar lixo)* |

## 4. “Está conectado” mas o adb não vê

A foto que você mandou mostra a pasta **A34** aberta no Explorer e a varredura
dizendo que nenhum Android apareceu. As duas coisas são verdade ao mesmo tempo:
o Windows está falando **MTP** (arquivos) e o `adb` precisa de outra interface
USB — a que só existe com o driver da Samsung instalado.

O código já sabia separar isso desde a 0.92.x (`sem_driver_samsung`), mas a
mensagem do scanner nunca perguntava. Agora ela separa quatro casos:

| o que o Windows vê | a mensagem |
|---|---|
| Samsung com nome genérico (MTP/Composite) | **falta o driver** — instale o Samsung USB Driver |
| o celular, driver OK | Depuração USB / Depuração sem fio brigando pela porta |
| o celular, com erro de driver | instale o driver e reconecte |
| nenhum celular (só hub) | aí sim: cabo, porta ou desligado |

## Um defeito que eu criei e o teste pegou

Escrevi a validação exigindo **dois** pontos no nome. O teste reprovou
`com.whatsapp` — que é nome válido de pacote e é justamente o exemplo que a
mensagem de erro usa. Um ponto basta. Corrigido antes do commit.

## Números

- suíte **4321** testes; as 4 falhas restantes são de ambiente (não há pendrive
  neste sandbox) e falham igual **sem** estas mudanças — conferido por stash.
- 11 testes novos: 8 no diagnóstico, 3 no agente local.
