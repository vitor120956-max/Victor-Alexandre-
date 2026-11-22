# 0.92.9 — “conectar o celular e escanear por completo para descobrir os problemas”

> ta ent oq podemos e fazer posso conetar meu cll no pc para o jarvis escanear
> ele por completo e ver se ele descobre os problemas?

**Sim. E dava para fazer melhor do que estava.**

O JARVIS já tinha dois scanners:

- **o scanner** (`escanear-celular.bat`) — pergunta o que você vê e cruza com o
  que mediu, gerando uma fila de suspeitas;
- **a varredura completa** (`ver-tudo-no-celular.bat`) — passa por 28 leituras e
  monta o mapa do aparelho.

O problema é que **a varredura não perguntava nada**. Ela media, e o scanner
dizia só o que os limiares pegaram. A fila de suspeitas — a parte que transforma
“frame lento” em “toque fantasma” — ficava de fora **justamente no caminho mais
fácil**, o do duplo clique.

## O que mudou

**A varredura completa agora pergunta o que você vê** e cruza com o que mediu. Um
duplo clique faz as duas coisas:

1. pergunta os cinco sintomas (pode pular com Enter);
2. passa pelas 28 leituras;
3. cruza relato × medida e monta a fila;
4. mostra **o que está errado** com a medida que sustenta;
5. mostra **o que dá para melhorar**;
6. diz o que **não deu para ler** e por quê.

Saída real (com um `adb` imitando um SM-A346MU com 28% de quadros travados no
Instagram e os sintomas que você relatou):

```
SM-A346MU · Android 16
Passei por 28 de 28 leituras... O scanner achou 1 problema(s);
o principal é: os quadros estão travando.

PELO QUE VOCÊ RELATOU — SUSPEITAS EM ORDEM
  1. Toque fantasma no vidro (controlador de toque)  (sem medida no aparelho)
     por que: Apagar a tela desliga o controlador e esvazia a fila de eventos...
     teste: Tire capa e película e use um dia inteiro.
  2. Um app específico travando (ANR) ...
  3. Calor reduzindo o processador (throttling) ...

O QUE ESTÁ ERRADO
  [ALTA] Os quadros estão travando — com.instagram.android: 280 de 1.000
         quadros travados (28%).
```

## Dois defeitos que a mudança expôs

**1. A skill descartava os sintomas.** O campo `sintomas` existia no input da
skill `celular.varredura` e o handler **não o usava** — quem chamava pelo chat
com sintomas recebia a fila vazia. Agora repassa.

**2. Seção sem item virava título solto.** A saída mostrava
“PASTAS QUE O ANDROID PUBLICA” seguido só da nota, sem nenhum item: parecia
leitura perdida. Agora seção vazia **sai** da lista, e o motivo fica nas
limitações.

## Como usar

**Duplo clique em `ver-tudo-no-celular.bat`.**

Ele pergunta os sintomas numerados — digite os números separados por espaço, ou
aperte Enter para pular. Depois mede, cruza e escreve o relatório em
`storage/diagnosticos/`.

Pela tela: **Anatomia** → marque os sintomas nas caixas → **Ver tudo no
aparelho**.

Pelo chat: `celular.varredura` com os sintomas.

## O que ele **não** descobre

Vale dizer antes de você rodar, para a expectativa ser a certa:

| o que | por quê |
|---|---|
| **toque fantasma** com certeza | o Android não publica “toque sem dedo”. O JARVIS mede a consequência e diz que é suspeita, não laudo |
| **o que está dentro de um app** | `/data/data` exige root — o JARVIS não usa |
| **saúde da célula da bateria** | o Android não publica para o `adb` |
| **defeito de hardware** | só medindo sintoma; quando é físico, ele diz que é físico |
| **o que aconteceu antes do último reinício** | os contadores do Android zeram no boot |

O resto — armazenamento, memória, bateria, calor, ANR, quadros travados, patch,
app que travou, tela que se mexe — ele mede.

## Medido

- **pytest 4 282** (0 falhas, 7 pulados) — **7 casos novos**; `test_varredura.py`
  agora com **56 casos**.
- `vitest` 243, `tsc` limpo, build OK, manifesto **672** arquivos em 0.92.9.
- Ponta a ponta com `adb` imitando o seu aparelho: **28 de 28 leituras**, fila
  com toque fantasma em 1º, achado de 28% de quadros travados, seção de pastas
  vazia corretamente removida.
- A rota `/api/anatomia/android/varredura` aceita `?sintomas=` e a skill repassa.

## O que eu preciso de você

Rode o **`atualizar.bat`**, depois o **`ver-tudo-no-celular.bat`**, marque os
sintomas que você vê e **me mande a tela**. Com a fila + as medidas eu troco
“suspeita” por “é isso”.
