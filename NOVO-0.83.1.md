# JARVIS 0.83.1 — sim, ele sabe onde fica. Só não sabe o que é.

Sua pergunta foi certeira: **“ue mas ele está reconhecendo onde fica cada
coisa né”**.

Está. Para a moldura, está. E eu nunca mostrei isso na tela — o que é falha
minha, não sua dúvida.

## O que já era medido e não aparecia

Cada elemento vem com `caixa`: x, y, largura, altura. O desenho mostrava o
papel, o nome e o `ref` — **e engolia a coordenada**. Daí parecer que ele não
reconhece nada.

Agora sai assim:

```
janela “Chrome”  em 0,0 (1200x800)
  botão “Fechar”  @568600ab:e2  em 1180,5 (30x20)
  botão “Minimizar”  @568600ab:e3  em 1140,5 (30x20)
```

Essa é a posição exata de cada peça na sua tela.

## A diferença, em uma tabela

| o que | ele sabe? |
|---|---|
| a janela existe, e onde ela está | **sim** — coordenada |
| barra de título, minimizar, maximizar, fechar, rolagem | **sim** — nome, ação e coordenada |
| o que está **dentro** da página | **não** — o Chrome não entrega |

Não é “não sei onde está o link”. É **“não sei que o link existe”**. O Chrome
devolveu 1 elemento na janela onde a página deveria estar; não há o que
apontar.

## A coluna nova

`--provados` agora mostra `posicoes`:

```
  janela aberta                    elementos  posicoes  conteudo  serve?  fonte  seg
  --------------------------------------------------------------------------------------
  chrome.exe     Arena | Benchmar         4         4  nao       nao     uia    1.2
  explorer.exe   Downloads               88        88  sim       SIM     msaa   0.9
  notepad.exe    Sem título - B          31        31  sim       SIM     uia    0.4
```

`posicoes` alto com `conteudo` baixo é exatamente a situação do Chrome: **ele vê
as peças e onde estão; não vê o que elas são.**

Moldura tem posição e não serve para trabalhar. Conteúdo é o que serve.

## Uma correção minha

Na 0.83.0 eu escrevi “o Chrome não publica a página — é o programa”. Foi rápido
demais.

O mais provável é que o Chrome **só ligue a árvore da página quando percebe um
programa de acessibilidade**, e neste PC ela tenha ficado desligada. É ajuste
do Chrome, não limitação do JARVIS.

Não vou pedir para você abrir o Chrome com parâmetro nenhum — você disse que
não quer ter que fazer nada, e continua valendo. Fica registrado como o que é:
a explicação mais provável, não uma promessa.

## O comando

```
.venv\Scripts\python arvore_sonda.py --provados
```

Com o Bloco de Notas e uma pasta do Explorer abertos. A tabela mostra, para
cada janela, quantos elementos ele enxerga, **quantos com posição** e se dá
para trabalhar ali.
