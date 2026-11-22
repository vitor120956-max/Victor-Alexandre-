# 0.95.2 — o JARVIS instala o driver sozinho (e sabe quando o `raw` está bloqueado)

Duas coisas que você pediu, na ordem em que elas travam o seu caminho.

## 1. O driver do celular deixou de ser tarefa sua

Até a 0.95.1 o JARVIS dizia, com todas as letras: *falta o driver da Samsung,
instale*. Correto, e inútil — você respondeu que não quer fazer nada manual, e
está certo. O JARVIS agora **baixa e instala**.

Como funciona, em três travas:

| passo | o que acontece |
|---|---|
| você pede | `sistema.driver-celular` no chat |
| sem `confirmado` | devolve o plano: URL oficial, ~33 MB, e **que nada é instalado no celular** |
| com `confirmado` | baixa para a quarentena, confere o SHA-256, confere a assinatura, instala |

A URL é a oficial (`developer.samsung.com/sdp/file/de97d0ea-…`), o arquivo é
assinado pela Samsung Electronics e o instalador roda no Windows. **Nada é
instalado no aparelho** — o driver é do PC. Depois de instalar, reconecte o cabo
e o `adb devices` passa a listar o A34.

E onde ele se recusa:

- **fora do Windows** → `SistemaError`. No Linux e no macOS o driver é do kernel;
  instalar um `.exe` ali seria teatro.
- **fabricante que eu não conheço** → diz que só conheço `samsung` e que o
  caminho para os outros é o site oficial. Não inventa URL.

## 2. O updater sabe explicar quando o `raw` está bloqueado

Medi na minha própria caixa: `raw.githubusercontent.com` devolve **000**,
enquanto `github.com` e `codeload` devolvem 200. Se isso acontecer no seu PC, a
pergunta “tem versão nova?” morria num `ConnectionError` mudo.

Agora existe uma sonda, `rota_funciona()`, que **nunca lança** e responde:

| situação | resposta |
|---|---|
| `raw` responde | `rota: raw` — caminho normal |
| `raw` cai, `codeload` responde | `rota: codeload` — **use o `.bat`**, que baixa o zip |
| os dois caem | `rota: nenhuma` — e diz o motivo real |
| `codeload` devolve HTML de erro | `nenhuma` — página de erro não é zip |

E o `except` de `verificar()` passou a incluir `rota` e um **plano B** escrito
em português, em vez de só o rastro da exceção.

> Uma correção de honestidade: o `atualizar-baixar.ps1` **já** caía para o
> `codeload` desde antes. Ele nunca esteve totalmente quebrado com o `raw`
> bloqueado. O que faltava era a *mensagem* explicar isso — e a sonda medir.

## Testes

11 novos, todos falhando antes da correção:

- driver: sem confirmar não baixa · confirmado baixa e instala · fabricante
  desconhecido · não existe fora do Windows · a skill está no registro e diz
  “no PC, não no celular”
- rota: `raw` ok · `raw` bloqueado → `codeload` · os dois caem · HTML não é zip
- e o `verificar` com rede morta tem de mencionar a rota e o plano B

## O que continua valendo

A varredura do celular, o pacote de diagnóstico e o token do dono não mudaram.
Se você já rodou `atualizar.bat` uma vez, o próximo `.bat` traz esta versão.
