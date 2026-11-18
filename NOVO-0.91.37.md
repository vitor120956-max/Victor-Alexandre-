# JARVIS 0.91.37 — que dia é hoje, quanto falta para o sábado e os feriados

Sua pergunta, em 18/11:

> e se eu perguntar para o javis q dia é hj proximos feriados quantos dias
> faltam para final de semana hj e quarta quinta...?

Fui olhar o que existia de verdade. **Só “que dia é hoje” funcionava.** As
outras três — “quantos dias faltam para o fim de semana”, “hoje é quinta?” e
“próximos feriados” — caíam em `unknown` e iam para o **modelo**, que não tem
relógio. O dia da semana ele pode até acertar; o Carnaval ele chuta com a mesma
confiança com que acerta o Natal.

## O que muda

**Tudo isso agora é conta de calendário feita na máquina** — sem internet, sem
chave, sem gastar cota:

| você pergunta | o JARVIS responde |
|---|---|
| que dia é hoje? | *Hoje é quarta-feira, 18/11/2026. Faltam 3 dias para o sábado (21/11/2026).* |
| hoje é quinta? | *Não — hoje é quarta-feira, 18/11/2026. quinta-feira é amanhã.* |
| quantos dias faltam para o fim de semana? | *Faltam 3 dias para o sábado (21/11/2026).* |
| quantos dias faltam para sexta? | *Faltam 2 dias para sexta-feira (20/11/2026).* |
| próximos feriados | lista com data, dia da semana e “em N dias” |
| quanto falta para o Natal? · quando é o Carnaval? | o próximo de verdade, com a contagem |
| feriados de 2027 | o ano inteiro, em ordem |

O exemplo real de hoje:

    Hoje é quarta-feira, 18/11/2026. Faltam 3 dias para o sábado (21/11/2026).

    Próximos feriados — nacionais, e os facultativos marcados como tal:
    1. 20/11/2026 (sexta-feira) — Dia da Consciência Negra — em 2 dias
    2. 25/12/2026 (sexta-feira) — Natal — em 37 dias
    3. 01/01/2027 (sexta-feira) — Confraternização Universal — em 44 dias
    4. 08/02/2027 (segunda-feira) — Carnaval — ponto facultativo — em 82 dias

## Duas decisões que valem registro

1. **A Páscoa é calculada, não tabelada.** Carnaval, Sexta-feira Santa e Corpus
   Christi saem do domingo de Páscoa (Meeus/Jones/Butcher — o mesmo algoritmo da
   Igreja e do Excel). Conferi **dez anos** no teste, de 2020 a 2038. Tabela de
   feriado móvel envelhece; conta, não.
2. **Ponto facultativo é dito como tal.** Carnaval e Corpus Christi não são
   feriado nacional por lei — aparecem marcados. Chamá-los de feriado seria a
   mesma classe de erro de inventar uma temperatura.

De brinde: **20/11 é feriado nacional desde a Lei 14.759/2023** — aparece na
lista (é o seu próximo, aliás, na sexta).

## O que fazer

```bat
cd /d D:\JARVIS
```

```bat
atualizar.bat
```

```bat
iniciar-jarvis.bat
```

E na conversa, pode mandar tudo junto:

```text
que dia é hoje e os próximos feriados
```

## Testado

37 testes novos em `server/tests/test_calendario.py`: Páscoa em dez anos,
feriados móveis derivados dela, 20/11 como nacional, ponto facultativo
declarado, lista em ordem, o feriado de hoje contando como próximo, dezembro já
mostrando o ano seguinte, “Natal” em 26/12 trazendo o do ano que vem, nome sem
acento achando, e feriado inexistente devolvendo a lista real em vez de uma data
aproximada.

16 casos em `src/lib/calendario.test.ts` (dia da semana, contagem até o sábado,
confirmação e correção de palpite) e 20 casos de frase no parser.

Contra a 0.91.36: **20 casos de frase falham** e `/api/calendario` dá 404.

Suíte: **3.962 testes de API** (7 pulados) e **216 testes web**.
