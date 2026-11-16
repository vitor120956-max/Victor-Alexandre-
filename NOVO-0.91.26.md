# JARVIS 0.91.26 — a página aparecia e sumia em segundos

O seu log respondeu tudo. Olhe as duas rodadas do diagnóstico, **na mesma
janela, sem nada mudar na tela**:

    antes:  msaa 85 elementos — diálogo: SIM — campos: nome
    depois: auto 3 — uia 3 — uia_raw 3 — uia_content 3 — msaa 2

O Chrome **liga** a árvore da página quando alguém a pede e **desliga** quando
para de pedir. A 0.91.25 ligava o sinal uma vez, lá no meio do caminho: a
página aparecia, era lida, e três passos depois já tinha sumido de novo. Foi
exatamente o que o `pegar-chave.bat` mostrou — “liguei o modo leitor de tela” e
logo em seguida “3 elementos” outra vez.

## O que mudou

**1. O sinal é dado antes da primeira leitura.** Não na primeira falha — antes
de qualquer coisa. E volta ao normal no fim.

**2. Toda leitura pede a árvore de novo.** O pedido (`WM_GETOBJECT`) entrou
dentro da função por onde **todas** as leituras passam: preencher o painel,
achar o botão “Create”, conferir o clique, copiar a chave. Se a leitura vem
pobre, ele pede de novo e relê, quantas vezes for preciso.

**3. O pedido foi consertado.** O `OBJID_CLIENT` ia sem sinal; no Windows de 64
bits virava 4294967292 e o programa **ignorava**. Agora vai com sinal (−4), que
é o que o Windows espera. E são três pedidos com pausa, porque o Chrome leva de
um a dois segundos para ligar o modo completo.

**4. A MSAA vai primeiro.** Na sua máquina foi ela a única que viu o painel
aberto (85 elementos, contra 43–58 das vistas da UIAutomation).

**5. O `chrome-acessibilidade.bat` espera o Chrome fechar de verdade.** Antes
ele abria 2 segundos depois do `taskkill`; se o Chrome ainda estivesse saindo, o
Windows entregava a chamada ao processo antigo e a opção de acessibilidade era
ignorada. Agora ele confere a lista de processos por até 15 segundos.

**6. O diagnóstico insiste e conta.** Ele faz até três rodadas de pedido de
árvore e diz em qual delas a página apareceu — ou diz que não apareceu em
nenhuma, e o que ainda dá para tentar.

## O que fazer agora

1. Atualize para a 0.91.26.
2. Rode o `pegar-chave.bat`. Com o sinal dado desde o começo e o pedido
   repetido, é a vez com mais chance até agora.
3. Se falhar, rode `diagnostico-chave.bat` **com o painel aberto**. Ele agora
   mostra três rodadas; se a página aparecer em alguma e sumir depois, isso já
   está no relatório.

## O que foi provado

Um Chrome falso que publica a página e **para de publicar depois de seis
leituras** — a sua sequência, em teste. O programa pede de novo e termina com a
chave no `.env`.

Os dois testes novos **reprovam** o código da 0.91.25 — conferi rodando contra
ele.

## O que continua igual

- nada é criado sem `--autorizar`;
- **No expiration**, **No limit**, nome `jarvis-AAAA-MM-DD`;
- botão apagado não é clicado;
- cursor volta para o dono;
- configuração do Windows volta ao que era no fim;
- sem chave, o `.env` não é tocado.

Suíte inteira: **3.788 testes passando** (7 pulados: dependem do Windows real).
