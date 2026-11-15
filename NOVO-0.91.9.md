# JARVIS 0.91.9 — a chave pelo navegador

Você pediu: entrar no site e gerar a chave sozinho. Dá — com uma ressalva que
muda o desenho, e com um caminho novo que é melhor do que eu tinha proposto.

## A ressalva (checada na documentação do OpenRouter)

A chave **não está na página**. O OpenRouter mostra o valor uma vez, no instante
da criação, e nunca mais: a lista guarda só o prefixo mascarado. Então "entrar
no site e coletar a chave" não tem o que coletar — a chave que existe hoje não é
legível por ninguém, nem por mim, nem por extensão.

O que dá para automatizar é **criar uma nova**: clicar em Create Key, dar um
nome, criar e copiar.

## O caminho novo (este funciona sempre)

`--pegar`: você copia no site, o JARVIS lê a área de transferência e grava no
`.env`. Nada é digitado no console — que é onde as chaves estavam se estragando
(o `\x16` da 0.91.7 era Ctrl+V).

```
.venv\Scripts\python chave-no-navegador.py --abrir    abre openrouter.ai/keys
   (no site: Create Key → nome → botão COPIAR)
.venv\Scripts\python chave-no-navegador.py --pegar    lê o que você copiou e grava
```

A leitura usa `ctypes` da biblioteca padrão: sem instalar nada, sem ler tela, sem
ler navegador. Um item só — o que você acabou de copiar — e só quando o comando
pede.

## O caminho automático (existe, mas tem de ser medido)

```
.venv\Scripts\python chave-no-navegador.py --ver
```

Isto **só lê** a janela do Chrome e diz o que ela publica:

```
  janela: chrome — API Keys | OpenRouter   (fonte: uia)
  botão de criar: SIM — “Create Key”
  botão de copiar: SIM — “Copy”
  campo de nome: SIM — “Key name”
  Dá para tentar: `--criar --autorizar`
```

Se os três aparecerem, o `--criar --autorizar` tenta a sequência inteira:
clica em Create Key, escreve o nome `jarvis-AAAA-MM-DD`, confirma, clica em
Copy, lê a área de transferência e grava. Se um passo não aparecer, ele para
naquele passo e diz qual.

O `--ver` existe por um motivo de método: **medir antes de prometer**. Não sei
ainda se o Chrome do seu PC publica esses botões na árvore de acessibilidade —
programas modernos escondem muita coisa. Em dois segundos você sabe; sem isso,
seriam vinte cliques no vazio.

## Regras que não mudei

- `--criar` só roda com `--autorizar`, e diz o que vai fazer antes de fazer.
  Criar uma chave é mexer na sua conta: é ação, não leitura.
- Nada de segundo plano, nada de automático por conversa. É um comando que você
  digita.
- A chave nunca aparece inteira na tela nem em log: só mascarada, como sempre.
- Não lê tela por imagem e não abre o navegador escondido.

## Testes

Oito novos em `test_chave_web.py`: acha os botões, casa português e inglês,
nome curto ganha do longo, página sem botão diz que não dá e aponta o caminho
que funciona, janela sem árvore não inventa diagnóstico, árvore aninhada é
percorrida, e o nome da chave leva a data para poder ser apagada depois.

## O que não foi medido

**Nada disto rodou no seu Chrome.** O que está provado é a regra de achar e
dizer o que existe. O clique de verdade depende do que o `--ver` responder — e é
por isso que ele vem primeiro.
