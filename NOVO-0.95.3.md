# 0.95.3 — o driver instala de verdade (e eu te mandei comando de terminal, desculpa)

A sua tela tem quatro erros. **Três são meus**, e um deles é o pior tipo: eu
escrevi qual é o problema e depois te entreguei o trabalho.

## O que a sua tela provou

| o que você digitou | o que realmente era |
|---|---|
| `JARVIS_HOST_REDE=1` | não é comando do Windows — é **linha de `.env`** |
| `curl -X POST ...` | `curl` **não existe** no Windows 10 build 14393 (2016) |
| `{"parameters":...}` | colar JSON solto no prompt não é nada |
| — | e **nada disso** deveria ter sido pedido a você |

A regra desta conversa é você não fazer nada manual. Eu viollei a regra.

## 1. O defeito grave: ele baixava e não instalava

`driver_do_celular` chamava `instalar()` e achava que tinha instalado.
Só que `instalar()` **monta o plano** e devolve um token; quem executa é
`executar()`. Então o JARVIS baixaria os 33 MB, mostraria "plano pronto" e você
ficaria com o driver não instalado — achando que estava.

Agora ele chama as duas: `instalar()` → token → `executar(token)`. E se o token
não vier, **falha alto** em vez de fingir que deu certo.

## 2. `instalar-driver-celular.bat` — duplo clique e pronto

É o que resolve o seu caso, sem prompt de comando:

```
instalar-driver-celular.bat   (duplo clique)
```

Ele faz três coisas:

1. **escreve no `.env`** as duas permissões que faltavam (`JARVIS_HOST_REDE=1`,
   `JARVIS_HOST_INSTALAR=1`) — sem duplicar linha, sem apagar o que você já tem;
2. baixa o driver do site oficial da Samsung, confere o SHA-256 e instala;
3. diz o que fazer depois: desconectar o cabo, reconectar, tocar em "Permitir".

O `.env` é lido no começo de todo script do projeto, então não existe mais
"exportar variável no terminal" — era exatamente aí que você tropeçou.

## 3. A recusa agora é uma frase, não um rastro

Fora do Windows:

> O driver só existe no Windows. No Linux o kernel já traz o driver do Android;
> no macOS o `adb` funciona sem instalar nada.

## Sobre o `curl`

Ele não existe no seu Windows (build 14393 é de 2016, e o `curl.exe` só entrou
de série no Windows 10 1803). **Não precisa dele**: o `.bat` faz o trabalho, e o
chat do JARVIS também. Meu erro foi sugerir o caminho do terminal.

## Testes

3 novos, e os 3 **falham** sem o conserto (provei com `git stash`):

- `driver_confirmado_baixa_e_instala_pela_quarentena` — exige a ordem
  baixar → plano → executar, com o token certo;
- `driver_nao_diz_instalado_quando_o_plano_nao_devolve_token` — sem token,
  `SistemaError`, e **nada executa**;
- `escanear_driver_instala_de_ponta_a_ponta_com_janela_falsa` — o caminho real
  do `.bat`, até a frase final;
- mais um do `.env`: rodar duas vezes não duplica linha e não apaga as do dono.
