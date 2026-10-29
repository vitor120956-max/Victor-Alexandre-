# JARVIS 0.61.8 — a vigia deixa de consultar a lista (e de mentir sem querer)

O log de vocês dois mostrou o defeito da 0.61.7, com número:

```
(a consulta levou 4.746 ms; o intervalo efetivo e esse)
(a consulta levou 5.348 ms; ...)
(a consulta levou 6.345 ms; ...)
```

**O "modo atento" não estava atento.** Ele foi pedido para olhar 5 vezes por
segundo, mas cada olhada custa **4,7 a 6,3 segundos** nesta máquina — o
`Get-PnpDevice` percorre todos os dispositivos PnP do Windows, e num Windows 10
1607 com chipset ICH7 e 4 GB isso é caro. Resultado: a vigia "atenta" estava
olhando a cada ~6 s, mais devagar que a vigia normal de 2 s.

E o pior não é a lentidão: é que **"nada mudou na USB"** só valia para aqueles
instantes. Um aparelho que aparecesse e desaparecesse entre duas consultas ficava
invisível — exatamente o sintoma de conector com mau contato.

## O que mudou: o Windows avisa, em vez de o JARVIS perguntar

A vigia agora **assina o evento de PnP do Windows**
(`Register-WmiEvent` sobre `__InstanceOperationEvent` com `Win32_PnPEntity`) e
espera com `Wait-Event`. Quem avisa é o sistema, no instante em que o dispositivo
é criado ou removido. **Não existe intervalo** — logo, não existe piscada que
passe batido.

Detalhes que importam:

- **`__InstanceModificationEvent` não é entrada nem saída.** O mesmo evento
  dispara quando muda status ou driver. A versão antiga trataria isso como
  "saiu" e imprimiria um SAIU falso. Agora cada evento é classificado em
  `entrou` / `saiu` / `mudou`, e só os dois primeiros são anunciados.
- **A espera custa zero.** `Wait-Event -Timeout 2` fica bloqueado sem consumir
  CPU; o ciclo de vida (tempo esgotado, sinal de vida a cada 30 s) continua.
- **Se o Windows recusar a assinatura**, o script cai sozinho para o modo
  consulta e diz isso na tela — nesse caso ele também avisa, **uma vez por
  minuto** (antes repetia a cada volta e enchia o log), quão lenta está a
  consulta.
- `-Modo consulta` força o jeito antigo; `-Modo evento` força o novo. O padrão é
  `auto`.

## Como repetir o teste

```bat
cd /d D:\JARVIS
```

```bat
atualizar.bat
```

```bat
cd /d D:\JARVIS
```

```bat
vigiar-usb-atento.bat
```

Na abertura deve aparecer:

```
  Modo evento: o Windows avisa na hora (nao existe intervalo para passar batido).
```

Se aparecer isso, o teste do conector passa a valer: com o J7 ligado, aperte e
mexa o conector devagar por dois minutos. **Qualquer** linha `ENTROU` com
`VID_04E8` muda o diagnóstico para "conector".

Se em vez disso aparecer "O Windows recusou a assinatura de eventos", me diga: o
script continua funcionando por consulta, e aí o caminho honesto é o
`celular.eventos` (o log do Windows guarda o que passou, mesmo entre consultas).

## Testes

- `pytest server/tests` → **2.782 passed**.
- Novos/corrigidos em `test_celular.py` e `test_vigiar_usb.py`:
  - `vigiar-usb-atento.bat` usa `-Modo evento` (e **não** mais `-Intervalo 400`,
    que não entregava o prometido);
  - o `.ps1` assina `Register-WmiEvent`/`Wait-Event` com
    `__InstanceOperationEvent` e `Win32_PnPEntity`, desassina no fim
    (`Unregister-Event`) e cai para consulta quando recusado;
  - os três estados (`entrou`/`saiu`/`mudou`) existem, para modificação não virar
    saída falsa;
  - o aviso de consulta lenta sai no máximo a cada 60 s;
  - o plano e as respostas do chat apontam para o modo evento.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
