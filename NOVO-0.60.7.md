# JARVIS 0.60.7 — o primeiro contato com o celular

As ferramentas estão no lugar:

```
D:\JARVIS\storage\ferramentas\platform-tools\adb.exe
D:\JARVIS\storage\ferramentas\scrcpy\scrcpy.exe
```

O próximo passo é `celular.status` — e é aqui que a maior parte das tentativas
trava, quase sempre por um dos três motivos abaixo. Esta versão responde qual
deles antes de você procurar no escuro.

## As três perguntas quando o `adb` não vê nada

`adb devices` vazio pode significar **três coisas diferentes**, e cada uma tem
um remédio diferente:

| O que o Windows vê | O que significa | O que fazer |
|---|---|---|
| o aparelho, status **OK** | cabo e porta bons — falta a Depuração USB | o plano do caminho sem tela |
| o aparelho, com **⚠** | falta o driver USB da Samsung | instalar o Samsung USB Driver |
| **nada** | problema físico (cabo, porta, bateria, placa USB) | trocar cabo/porta antes de tudo |

Antes, o `celular.status` só sabia dizer "vazio" e mandava abrir o Gerenciador
de Dispositivos para descobrir qual dos três era. Agora ele mesmo consulta o
Windows (`Get-PnpDevice`, só leitura) e o `celular.plano` começa pelo passo
certo — o "abra o Gerenciador" sai do caminho quando a resposta já veio.

## Também nesta versão

**Primeira execução do adb.** Subir o serviço do adb na primeira vez pode passar
de 25 s num PC de 4 GB com antivírus escaneando o executável. O tempo limite
subiu para 45 s, e o erro agora diz que pode ser isso (em vez de "passou de 25s",
que parecia defeito).

**Conflito de versão do adb.** Se outra ferramenta já subiu um `adb` de versão
diferente na porta 5037, o primeiro comando falha com `server version ... doesn't
match this client`. O JARVIS derruba esse servidor (`adb kill-server`) e tenta de
novo sozinho.

**Nada de janela preta piscando.** No Windows, cada chamada do `adb` abre e fecha
uma janela de console quando o processo pai não tem console — agora ela é
suprimida (`CREATE_NO_WINDOW`).

## Como testar agora

1. Conecte o J7 Prime no PC com o cabo **micro-USB** (de preferência o original),
   direto numa porta USB do PC — sem hub.
2. Na interface, rode **`celular.status`** (não pede confirmação, é só leitura).
3. Se o resultado for `vazio`, rode **`celular.plano`** — ele já vem com o
   primeiro passo certo para o que o Windows viu.

O que **continua** impossível, e nenhuma versão vai mudar: ligar a Depuração USB
e tocar em "Permitir depuração USB?" na tela do aparelho. É consentimento do
Android. O JARVIS automatiza todo o resto.

## Testes

- `pytest server/tests` → **2.689 passed**.
- `test_celular.py` → **65** (6 novos: sonda fora do Windows, leitura do
  PowerShell com linha repetida, ausência de aparelho sem inventar driver, plano
  mudando o primeiro passo, sonda só quando o adb não vê nada, e `kill-server`
  no conflito de versão).
- `vitest` → 120, `tsc -b` limpo.
