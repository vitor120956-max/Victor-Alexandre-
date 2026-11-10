# JARVIS 0.84.0 — o Chrome acordou, e eu estava errado

Olhe as suas duas rodadas, uma embaixo da outra:

```
1ª:  chrome.exe   Arena | Benchmar     3     3  nao   nao   uia  1.0
2ª:  chrome.exe   Arena | Benchmar   104   104  sim   SIM   uia  0.9
```

A mesma janela, sem você tocar em nada. **3 elementos** e depois **104**.

## O que aconteceu

O Chrome não deixa a árvore da página pronta o tempo todo. Ele **liga** essa
árvore quando percebe que um programa de acessibilidade está lendo. A primeira
leitura é justamente o que acende a luz — e ela chega antes de a luz acender.

Eu li uma vez, vi 3 elementos, e escrevi “não publica”. Era o **primeiro
estado**, não o único. A conclusão estava errada, e eu a escrevi com toda a
convicção. **O Chrome funciona no seu PC.**

## O que mudou

`ler_janela` agora relê **uma vez**, 0,4 s depois, quando a primeira leitura
vem sem conteúdo. Se a segunda vier melhor, ela vence — e o JARVIS diz por quê:

```
A janela só publicou o conteúdo na segunda leitura — é o caso do navegador,
que liga a acessibilidade quando percebe alguém lendo.
```

Janela que já vem com conteúdo não paga a segunda passada: é só quando a
primeira não serve.

E o `--provados` avisa quais janelas acordaram, para você não achar que
precisa rodar duas vezes:

```
Acordaram na segunda leitura (o navegador liga a acessibilidade quando
percebe alguém lendo — já vem lido, não precisa repetir):
  - chrome.exe — Arena | Benchmark & Compare the Best AI Mode
```

## A regra que eu tirei disso

**Uma leitura não é uma medição quando o objeto muda de estado ao ser tocado.**

Foi o mesmo tipo de erro das duas versões anteriores: primeiro medi o terminal
achando que era o Chrome, depois medi o Chrome uma vez e encerrei. O padrão é
sempre o mesmo — concluir cedo com um número só.

## O que a sua medição provou

```
notepad.exe    Sem título - Blo        49        10  sim       SIM     msaa   0.3
chrome.exe     Arena | Benchmar       104       104  sim       SIM     uia    0.9

2 de 2 janela(s) servem para o JARVIS agir
```

Duas janelas com **conteúdo**, **nome** e **posição**. É exatamente o critério
que eu tinha escrito para liberar a etapa 2:

> uma leitura em que os elementos façam sentido

Ele foi atingido. E ele foi atingido nos dois programas que importam: o Bloco
de Notas (49 elementos) e o Chrome (104 elementos — a página de verdade).

## O próximo passo

**A próxima versão é o clique por `ref`** — a etapa 2. Ela vai funcionar assim:

1. a leitura devolve `@xxxx:e12` para cada elemento acionável;
2. o comando recebe o `ref`, confere que ele pertence à última leitura (não
   aceita `ref` velho), mostra **o que** vai clicar e **onde**;
3. só com `--executar` ele age. Sem isso, só mostra.

Isso é uma versão inteira, não um remendo: agir é diferente de ler, e o teste
tem que provar que ele se recusa a agir com `ref` que não existe mais.

Antes dela, uma leitura só — a que mostra os `ref` do Bloco de Notas:

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --alvo "notepad.exe"
```

Me mande o que aparecer. É a última leitura antes de ele começar a agir.
