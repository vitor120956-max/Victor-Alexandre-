# 0.95.0 — o JARVIS mostrou o app travando. Agora ele fecha.

Seu relatório real dizia: **“Há app fechando sozinho — o sistema registrou
travamento de: `com.dti.telefonica`”**. E parava ali. Você lia, fechava o app
na mão, e a próxima varredura dizia a mesma coisa.

Agora o relatório termina com o que fazer — e separa **três** coisas que estavam
misturadas numa frase só:

```
O QUE O JARVIS FAZ NISSO (com a sua confirmação)
  - Fechar com.dti.telefonica agora
    limite: Fecha agora e o app reabre no próximo toque. Se ele travar de novo,
    o problema é a versão do app — aí é atualizar ou reinstalar.
    se doer: Perde o que não estava salvo dentro do app.

O QUE SÓ VOCÊ PODE FAZER (com o caminho pronto)
  - Limpar o cache do app  →  Ajustes → Apps → [app] → Armazenamento → Limpar cache
```

## Por que só três ações o JARVIS executa

Porque só três têm executor escrito: fechar app, abrir app, instalar APK. Marcar
outra como “o JARVIS faz” não faria nada além de mentir na tela — e um teste
cobra isso.

## A regra que segura o resto

**Ação sem medida é chute.** Um relatório sem problema devolve plano vazio,
dizendo “falta medida”. Toque fantasma, por exemplo, não vira ação nenhuma no
aparelho: o plano é o *teste* (tirar capa e película), porque nenhum comando
muda o que o controlador do vidro entrega.

## O que ninguém faz — com o porquê, não com um “não”

| você pede | por que não | em vez disso |
|---|---|---|
| entrar no celular e resolver tudo sozinho | o `adb` é uma porta estreita: não tem tela, não vê o desenho, não toca em botão que exija conta | ele faz o que a porta permite e entrega o menu exato do resto |
| ler as conversas dos apps | precisaria de root — e a mesma porta que deixa o JARVIS ler tudo deixa qualquer app ler tudo | exportar o backup do próprio app |
| desinstalar app sozinho | apaga dados sem volta | diz qual ocupa mais e abre o caminho em Ajustes → Apps |
| consertar toque fantasma por software | é o controlador do vidro, não o Android | o teste que separa acessório de hardware |

## Dois erros meus que os testes pegaram antes de você ver

1. Eu escrevi `bateria-caindo`. O scanner emite **`bateria-gasta`**. A ação
   nunca apareceria.
2. Eu lia o campo `detalhe`. O campo real é **`medido`** — e era onde estava o
   `com.dti.telefonica`. A ação de fechar o app existia no código e não saía na
   tela, com o nome do app três linhas acima.

O teste que pegou os dois não confere texto: ele lê o código do diagnóstico e
compara **identificador por identificador**. É a mesma doença da 0.92.9
(`EVIDENCIA_MEDIDA` apontando para id que não existia), e agora ela está presa.

## Nada roda sozinho

Para o JARVIS executar: `JARVIS_ACOES=1` no `.env` **e** `confirmado: true` na
chamada. Sem os dois, ele devolve o plano e não toca no aparelho. E ele continua
não usando root: fechar app, abrir app e instalar APK funcionam no degrau 1,
com o cabo e a Depuração USB que você já tem.
