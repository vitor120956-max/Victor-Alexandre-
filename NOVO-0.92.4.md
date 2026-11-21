# 0.92.4 — “a tela trava e se mexe sozinha”: o sintoma agora vira suspeita em ordem

> as vezes minha tela trava ou ta lenta o frame meio q fica lento do nada ou ele
> comeca a se mexer sozinho so para quando desliga a tela e ligo de volta

## O que você descreveu tem uma assinatura

Não são quatro problemas. É **uma cadeia**, e o detalhe que fecha o caso é o
“só para quando desliga a tela e ligo de volta”:

1. o **controlador de toque** entrega um toque que ninguém fez (toque fantasma);
2. o Android espera o app responder → o app **não responde** (ANR);
3. a fila de desenho atrasa → o **frame trava**;
4. o app reage a toques fora de hora → **a tela se mexe sozinha**.

**Apagar a tela desliga o controlador de toque e esvazia a fila.** É a única
causa em que esse gesto resolve na hora.

## O que mudou no scanner

Ele agora mede a tela e **pergunta o que você vê**:

- **`logcat -b system`** → `ANR in <pacote>` + o motivo (ex.: *Input dispatching
  timed out*). É o app que travou, com nome.
- **`dumpsys gfxinfo`** → quantos quadros travaram, por app. 28% de quadros
  travados = grave; 13% = média; 3% **não é achado**.
- **`dumpsys input` + `dumpsys window displays`** → qual controlador de toque o
  aparelho tem e qual janela está em foco.

E cruzou isso com cinco perguntas: *a tela congela? · o rolar fica lento? · se
mexe sozinha? · só para ao apagar e ligar a tela? · esquenta antes?*

O resultado é uma **fila de suspeitas**. Para o seu relato, com o aparelho de
teste, ela saiu assim:

| # | suspeita | medida no aparelho |
|---|---|---|
| 1 | **Toque fantasma no vidro** | nenhuma (o Android não publica “toque sem dedo”) |
| 2 | Calor reduzindo o processador | aquecendo |
| 3 | Memória cheia | memória baixa |

## O teste mais barato, em ordem

Faça **um de cada vez** e veja se o problema some:

1. **Tire a capa e a película** e use um dia inteiro. É a causa mais comum e a
   que não custa nada.
2. **Teste sem carregador**; depois com outro carregador, em tomada aterrada.
3. **Ligue “Mostrar toques”**: Opções do desenvolvedor → Mostrar toques. Se
   aparecer bolinha sem você encostar, é o controlador.
4. No app de diagnóstico do aparelho (Ajustes → Suporte → Toque, o nome muda por
   fabricante): se aparecer toque sozinho **com capa e película fora**, é o
   vidro/controlador — e o conserto é de assistência, não de software.

## A honestidade do achado

O Android **não publica** “toque sem dedo”. O scanner mede a **consequência** e
diz isso na tela: é a leitura mais provável do conjunto, **não um diagnóstico
fechado**. Quem fecha é o teste acima.

## Como rodar

**`escanear-celular.bat`** (duplo clique). Ele pergunta os sintomas, numera as
perguntas, você digita os números separados por espaço, e ele mede. Ou, na tela:
**Anatomia → “Passar o scanner”**, com as caixas de seleção.

## Medido

- **pytest 4 214** (0 falhas, 7 pulados) — **15 casos novos**.
- API real (8013): `/api/anatomia/android/sintomas` → 5 perguntas; `scan?sintomas=se-mexe-sozinho,so-para-apagar-tela,frame-lento` → **200** com toque fantasma em primeiro; `/anatomia` → 200.
- `vitest` 243, `tsc` limpo, manifesto 662 arquivos em 0.92.4.

**Defeito achado no caminho:** o parser do `gfxinfo` exigia a linha sem `**`, e o
Android imprime `** com.app/1234`. O pacote nunca era lido — o achado de frame
lento nunca aparecia. Agora um teste com 28% de quadros travados pega isso.

## O que eu preciso de você

Rode o scanner e **me mande a tela**. Com o número de quadros travados, o ANR e
o controlador de toque do **seu** aparelho eu troco “suspeita” por “é isso”.
