# Scanner do celular — o que está errado e o que fazer (0.92.3)

> *“vou testar com o meu cll quero ver se consigo melhorar e otimizar e ver uns
> problemas q ele ta apresentando talvez passando um escaner nele talvez
> conseguimos resolver”*

O JARVIS lê o aparelho desde a 0.92.2. **Ler não é diagnosticar.** Esta versão
transforma a leitura em **achados**: cada um com a medida que o sustenta, a
causa provável, o passo a passo e o limite.

## 1. Como rodar

Duas portas, mesmo motor:

- **No PC, sem abrir tela:** dois cliques em **`escanear-celular.bat`**. Ele lê,
  imprime, e salva o relatório em `storage/diagnosticos/`.
- **Na tela:** **Anatomia** → cartão do Android → **“Passar o scanner”**.
- **No chat:** “passa um scanner no meu celular”.

Antes, no celular: **Depuração USB ligada** e o toque em **“Permitir”** no aviso
que aparece na tela. O `adb` precisa estar instalado — se não estiver, a própria
resposta manda para **Máquina → Preparar celular**.

## 2. O que ele mede (tudo de leitura)

| área | comando | vira achado quando |
|---|---|---|
| armazenamento | `df -k` | ≥ 88% de `/data` usado (alerta a partir de 78%) |
| memória | `/proc/meminfo` | menos de 12% de RAM disponível |
| processos | `ps -A -o RSS,NAME` | um processo com 700 MB ou mais |
| bateria | `dumpsys battery`, `charge_full`/`charge_full_design` | abaixo de 80% da capacidade de fábrica |
| temperatura | `/sys/class/thermal/thermal_zone*` | qualquer zona acima de 70 °C |
| segurança | `ro.build.version.security_patch` | último patch há 240 dias ou mais |
| travamentos | `logcat -b crash -d` | aparece `Process:` de um app |
| não responde | `logcat -b system -d` | aparece `ANR in <pacote>` |
| quadros | `dumpsys gfxinfo` | 10% ou mais de quadros travados |
| toque | `dumpsys input`, `dumpsys window displays` | dispositivo de entrada e janela em foco |
| origem | `ro.build.tags`, `which su` | `test-keys` ou binário de root |
| ajustes | `settings get global …` | animação em 1.0 (vira sugestão, não problema) |

**Nenhum comando altera nada.** Não existe `pm uninstall`, `settings put`,
`reboot`, `push`, `rm` nem `su` na lista — e há teste que varre essa lista
palavra por palavra.

## 2.1 O relato do dono vira pergunta (0.92.4)

> *“as vezes minha tela trava ou ta lenta o frame meio q fica lento do nada ou
> ele comeca a se mexer sozinho so para quando desliga a tela e ligo de volta”*

Esse relato é uma **assinatura**, não um sintoma solto. A cadeia é:

1. o controlador de toque entrega evento que ninguém pediu (*toque fantasma*);
2. o Android espera o app responder (vira **ANR**);
3. a fila de desenho atrasa (**quadro travado**);
4. o app reage a toques fora de hora — e a tela “se mexe”.

**Apagar a tela desliga o controlador de toque e esvazia a fila.** É a única
causa em que esse gesto resolve na hora. Diagnóstico de toque fantasma não
técnico, mas é a leitura que fecha com o sintoma.

Por isso o scanner passou a perguntar **o que você vê** (cinco perguntas, com
número para teclar) e a ordenar as suspeitas cruzando relato + medida:

| pergunta | o que ela separa |
|---|---|
| A tela congela e volta? | app travado (ANR) × controlador |
| O rolar fica lento? | quadro travado × memória × calor |
| Se mexe sozinha? | **controlador de toque** (a única que gera toque sem dedo) |
| Só para ao apagar e ligar a tela? | **controlador** (desliga o hardware de toque) |
| Esquenta antes? | throttling |

Cada suspeita vem com **o teste mais barato** — tirar capa e película, testar
sem carregador, ligar “Mostrar toques” — e com **o que confirma**. A tela marca
`medido no aparelho` ou `sem medida no aparelho`: o relato ordena, mas não vira
laudo.

### O que o scanner **não** consegue ver

O Android não publica “toque sem dedo”. O scanner mede a **consequência** (ANR,
quadro travado, janela em foco) e diz, na cara, que a conclusão de hardware é
suspeita — não diagnóstico fechado. Quem fecha é o teste de toque do próprio
aparelho, com capa e película fora.

## 3. O formato de um achado

```
[ALTA] O armazenamento está quase cheio
    medido: 93% de /data usado; restam 8,1 GB.
    causa:  Android fica lento quando falta espaço…
    -> Ajustes → Armazenamento (a lista é por categoria e por app)
    -> …
    limite: Apagar cache não devolve espaço de foto; app do sistema não sai sem root.
```

Quatro campos, sempre. Sem “medido”, não é achado — é opinião, e opinião não
entra no relatório.

## 4. As otimizações dizem quando o ganho é sensação

Cada sugestão de melhoria carrega um campo: **o ganho foi medido ou é
sensação?**

- *fechar o Instagram quando não usa* → **medido**: libera 928 MB da RAM medida.
- *reiniciar o aparelho* → **medido**: devolve memória e encerra serviço travado.
- *diminuir a animação para 0,5x* → **não medido**: deixa a sensação de mais
  rápido, **não** aumenta desempenho. A tela marca isso com
  “sensação, não número medido”.

Essa distinção existe porque “deixa mais rápido” é a frase mais vendida da
internet de otimização, e quase nunca é verdade medida.

## 5. O que ele não faz

1. Não desinstala, não limpa cache, não muda ajuste, não reinicia, não apaga.
2. Não usa root — nem para ler.
3. Não mede memória por app em detalhe nem saúde de célula (o Android não publica
   sem root).
4. Não conserta hardware: bateria inflada, conector quebrado e tela ruim são
   casos de assistência, e o relatório diz isso.
5. Não promete ganho: quando não mediu, escreve “sensação, não número medido”.

## 6. Como testar

1. `atualizar.bat` → `iniciar-jarvis.bat`.
2. No celular: ligue a Depuração USB, conecte o cabo, toque em “Permitir”.
3. **`escanear-celular.bat`** (duplo clique) — ou **Anatomia → Passar o scanner**.
4. Me mande o texto da tela. O relatório também fica em
   `storage/diagnosticos/<serial>-<data>.json`, e ele não tem dado pessoal.

## 7. Medido

- `pytest server/tests/test_diagnostico_celular.py` — **30 casos**.
- API real na 8012 com um `adb` de teste servindo saídas de um SM-A346B:
  `/api/anatomia/android/scan` → **200**, 7 achados na ordem certa
  (armazenamento cheio, aquecendo, memória baixa, bateria gasta, bateria quente,
  patch antigo, app travando); `/anatomia` → 200.
- Defeitos achados e corrigidos no caminho: vírgula sobrando (“42,8 °C
  carregando,”), “lista abaixo” quando a lista estava acima, 11,8% arredondado
  para “12%” (disfarçava o limiar) e `**negrito**` de markdown vazando no
  console.

## 8. “Rodar por todo o celular”: a varredura completa (0.92.5)

O scanner da §2 mede o que costuma dar problema. A varredura da 0.92.5 **passa por
tudo o que o Android deixa ler** — 12 leituras em 6 seções — e não julga: ela
descreve, para você achar o que só faz sentido conhecendo o seu aparelho.

| seção | o que entra |
|---|---|
| **pastas** | as pastas de dados do aparelho, com dono e permissão (e o que o `adb` não vê) |
| **partições** | tabela de partições, tamanho e uso das que importam (`system`, `data`, `cache`) |
| **memória** | RAM total/livre, `MemAvailable`, swap e o que está segurando memória |
| **processos** | os que mais gastam CPU e os que estão em `D`/`Z` (presos) |
| **sistema-apps** | versão do Android, patch, uptime, e os apps instalados por tamanho |
| **identidade** | modelo, build, bootloader, `verified boot`, `test-keys` |

Rodar: **`ver-tudo-no-celular.bat`** (duplo clique, uma pergunta só — o nome do
relatório) ou `python escanear-celular.py --completo --sem-perguntas`. Pela tela:
**Anatomia → Passar a varredura**. Pelo chat: `celular.varredura`.

O contrato da resposta é o mesmo das outras rotas: `{ok, alvo, serial, titulo,
lido_em, veredito, secoes[], problemas[], limitacoes[], sem_root[], nao_faz[]}`.
O `veredito` é sempre “Passei por **N de 12** leituras…” — nunca “seu celular está
bem”, porque o que ele não leu está listado logo abaixo.

**Só leitura, e cobrado por teste.** O teste varre a lista `COMANDOS` e recusa
`install`, `push`, `pull`, `rm`, `reboot`, `su`, `settings put` e `keyevent`; todo
comando leva `-s <serial>` para não acertar o aparelho errado.

## 9. “100% de acesso”: os cinco degraus (0.92.5)

`GET /api/anatomia/android/controle`, o cartão **“Até onde o JARVIS chega”** na aba
Anatomia, ou a skill `celular.controle`.

| degrau | ganha | exige | custa | JARVIS |
|---|---|---|---|---|
| 1 | ler tudo o que o Android publica, espelhar, toque/tecla, instalar/remover, mídia | cabo + Depuração USB + Permitir | nada | **faz** |
| 2 | o mesmo sem cabo | `adb tcpip 5555` | aparelho escutando na rede local | **faz** |
| 3 | root: dados de qualquer app, arquivos de sistema | bootloader + Magisk | **apaga o aparelho**; quebra OTA/banco/carteira | não faz |
| 4 | trocar o sistema (ROM, kernel) | bootloader destravado + imagem sua | risco de tijolo | não faz |
| 5 | escapar da caixa por falha de segurança | falha não corrigida | é crime se não for o seu aparelho | não faz |

Cada degrau recusado traz a `recusa` escrita — o motivo, não um “não”. O texto
“100%” não aparece como promessa em lugar nenhum do código; aparece como o nome do
**pedido** que o cartão responde.

**Sem aparelho a rota não mente**: 409 `CONTROLE_CELULAR` com o que ligar, e
`degrau_atual = 0`.

## 10. A varredura agora mede o que jura medir (0.92.6)

O primeiro relatório de verdade (SM-A346MU, Android 16) saiu com **“Nenhum
problema nas áreas que o scanner mede”** — e estava errado. A varredura rodava
12 leituras; o scanner procura 19, por nome exato. As 7 que faltavam eram
`getprop`, `dumpsys battery`, `df -k`, `/proc/meminfo`, `logcat`, `gfxinfo` e
`dumpsys input`. O scanner recebia um dicionário sem elas, não achava nada, e o
“nada” virava “aparelho saudável”.

Três regras ficaram no código para não voltar:

1. **A lista é derivada.** `varredura.LEITURAS_DO_SCANNER = diagnostico_celular.COMANDOS`.
   Uma leitura nova no scanner passa a valer na varredura sozinha.
2. **Sem medida não há atestado.** Faltando `getprop`, bateria, `df -k`,
   `/proc/meminfo` ou `ps`, o veredito é **“não deu para medir”** — nunca
   “está tudo bem”.
3. **Seção vazia é defeito.** Partição negada (`Permission denied` no Android 16)
   vira uma linha que explica, em vez de uma seção em branco.

O texto do console também passou a ter **O QUE ESTÁ ERRADO** (medida, causa e o
que fazer) e **O QUE DÁ PARA MELHORAR**. Antes ele imprimia o mapa e o rodapé, e
nada do diagnóstico.

Total: **28 leituras** — 19 do scanner + 9 só da varredura.

## 11. “Podemos usar root temporário?” (0.92.7)

Três coisas diferentes usam esse nome, e só a primeira é temporária pela porta
da frente:

| # | o que é | dura | destrava bootloader? | apaga? |
|---|---|---|---|---|
| 1 | `adb root` (reiniciam o `adbd` como root) | até reiniciar | não | **não** |
| 2 | Magisk sem módulo de persistência | até desinstalar | sim | sim |
| 3 | `su` emprestado por N minutos | N minutos | sim | sim (antes) |

**O `adb root` depende do `adbd`, não do bootloader.** Num aparelho de fábrica
(`ro.debuggable=0`, build `user`) ele responde `adbd cannot run as root in
production builds` — é o aparelho recusando, não o JARVIS. O mapa lê isso e
devolve `root_temporario` com `possivel`, `qual`, `precisa_destravar` e
`apaga_o_aparelho`.

O JARVIS **não roda** `adb root`, nem quando ele é possível (build `userdebug`):
root é a linha que o projeto não cruza em nenhuma forma. A diferença que o mapa
registra é o **passivo** — num `userdebug` seria reversível; num aparelho travado
seria apagar tudo.

Três propriedades passaram a ser lidas por causa desta pergunta:

- `ro.boot.verifiedbootstate` (`green` travado · `orange` destravado · `yellow`
  destravado com chave própria);
- `ro.boot.flash.locked` (`1` travado) — fallback quando a primeira não vem;
- `service.adb.tcp.port` — é **ela** que marca o degrau 2, não `ro.debuggable`
  (que é build de fábrica/teste, e estava errado desde a 0.92.5).

## 12. “Root sem reiniciar, sem apagar, sem quebrar?” (0.92.8)

Três condições, e cada caminho falha em uma diferente:

| caminho | sem reiniciar | sem apagar | sem quebrar | neste aparelho |
|---|---|---|---|---|
| `adb root` | sim | sim | **sim** | não (`ro.debuggable=0`) |
| sessão de `su` | sim | não | não | não |
| Magisk “sem persistência” | sim | não | não | não |

**`adb root` é o único que atende às três** — reinicia o daemon do `adb`, não o
aparelho; não escreve em partição; não toca no `verified boot`. Ele depende de
`ro.debuggable=1` e build `userdebug`/`eng`. Em produção o `adbd` responde
`adbd cannot run as root in production builds`.

O que **existe agora** e não quebra nada é o **privilégio de shell do ADB**: a
identidade `shell` (a mesma que o Shizuku empresta a apps). Alcança leitura,
instalação, permissões (`pm grant`), ajustes globais, congelar app, espelhar e
copiar mídia. **Não** alcança `/data/data`, `/data/system`, partições de boot,
memória de outro app nem módulo de sistema.

O `controle()` expõe `root_temporario.atende_as_tres` (booleano), `resposta`
(texto medido), `caminhos[]` (a tabela) e `sem_root_agora` (o privilégio, com
`da_para` e `nao_da`). Um aparelho que **já tem root** devolve `false`: o custo já
foi pago, e “sim” esconderia a conta.

## 13. A varredura completa agora pergunta os sintomas (0.92.9)

Até a 0.92.8 havia dois caminhos e nenhum fazia tudo:

| caminho | pergunta sintomas? | mede tudo? | fila de suspeitas? |
|---|---|---|---|
| `escanear-celular.bat` | sim | não (19 leituras) | sim |
| `ver-tudo-no-celular.bat` | **não** | sim (28 leituras) | **não** |

A 0.92.9 uniu: `varredura.varrer(serial, sintomas=[...])` roda as 28 leituras e,
se receber sintomas, chama `diagnostico_celular.cruzar()` sobre **as mesmas
saídas** — sem reabrir o aparelho e sem uma segunda tabela de pesos que
divergiria da primeira.

O cruzamento é o mesmo da 0.92.4: para “se mexe sozinho” + “só para ao apagar a
tela” + “frame lento”, a primeira suspeita é **toque fantasma no vidro** — a
única causa em que apagar a tela resolve na hora.

Dois defeitos achados ao unir:

1. o handler de `celular.varredura` **descartava** o campo `sintomas` que o input
   declarava;
2. seção sem item saía como título solto (o caso de “PASTAS” quando nenhum `ls`
   responde). Agora a seção sai da lista e o motivo fica nas limitações.

## 14. O que o primeiro relatório real ensinou (0.93.0)

O dono rodou o `ver-tudo-no-celular.bat` no SM-A346M (Android 16): 25 de 28
leituras, fila de suspeitas montada, achado real (`com.dti.telefonica` travando).
Funcionou — e mentiu em quatro pontos.

| sintoma no relatório | causa | correção |
|---|---|---|
| “«which su»: sem resposta” em leituras que não responderam | `which` sem root devolve **código 1 e saída vazia**; a varredura tratava como falha | sem mensagem de erro = resposta; a chave é guardada vazia e o texto diz “não é alarme” |
| **toda** suspeita “sem medida no aparelho” | `EVIDENCIA_MEDIDA` pedia `app-travado`, id que o scanner **nunca emite**; `app-travando` não estava ligado a nada | tabela corrigida + teste que a compara com os ids reais |
| modelo podia sair truncado | parser aceitava `[ro.product.model]: [SM-A346` como valor inteiro | linha sem `]` final é descartada; fallback por comando |
| “440 de fábrica” e “55 instalados” | `pm list packages -s` lista **quais** são de sistema, não o total do aparelho | dois rótulos: “Pacotes de sistema” e “Apps instalados no aparelho” |

Mais uma: a mesma negativa aparecia duas vezes porque cada módulo formata o erro
de um jeito (`“cmd”: erro` vs `erro`). A dedup passou a comparar o **miolo** e a
ficar com a versão que diz qual comando falhou.

O total de leituras foi para **29** (`pm list packages` entrou).

## 15. O que o segundo relatório real ensinou (0.94.0)

`RXCW400ZV3F-20261122-195132.json` — mesmo aparelho, 27 de 29 leituras, sintomas
`1 2 3 4`. Três defeitos, todos de **apresentação de um dado que já estava certo**.

| sintoma no relatório | causa | correção |
|---|---|---|
| fila inteira “sem medida no aparelho”, com ANR medido duas telas acima | `_cruzar_sintomas` passava as **saídas cruas** a `cruzar()`, que lê `relatorio["problemas"]`; sem `problemas`, toda evidência vira “não achei” | `montar()` guarda `_saude`; o cruzamento usa a saúde já calculada e `_saude` sai antes de imprimir |
| “495 instalados” no total e “55 instalados” na otimização | o total é `pm list packages` (495); `-3` é só o que o dono instalou (55) | `Apps instalados (sistema + seus) 495` e `Fora da loja do fabricante 55`; a otimização diz “são 55 apps que você mesmo instalou” |
| limitação térmica em duas linhas seguidas | `diagnostico_celular` e `anatomia` escreviam a mesma coisa com miolos diferentes | um texto idêntico nos dois módulos — a dedup pega, e a lista mostra uma linha |

A lição da 0.93.0 se repetiu de lado: lá eu consertei a **tabela** de evidências;
aqui, o que chegava na tabela. Nos dois casos o teste que faltava era o que usa o
**caminho real** (`montar()` → `_cruzar_sintomas()`), não a função isolada.

O que o relatório **não** acusou e agora está escrito: RAM com 35% disponível e
bateria a 30,7 °C tiram memória e calor da frente das suspeitas — mesmo sem
leitura térmica de CPU, que este Android esconde.

## 16. O celular entra no PC de quem conserta (0.94.1)

O relatório salvo sempre guardou o **resultado** e nunca as **respostas do
`adb`**. Isso obrigava a depurar por print: quem recebia via a conclusão, não a
medida. Dois comandos fecham o ciclo.

```
ver-tudo-no-celular.bat --pacote          # grava tambem o .zip das leituras
escanear-celular.py --refazer ARQUIVO.zip # refaz o relatorio sem celular
```

O zip tem `leituras.json`, `falhas.json`, `limites.json`, `relatorio.json` e um
`LEIA-ME.txt`. Antes de sair, passa por `limpar_saidas_para_pacote`:

| o que identifica | vira |
|---|---|
| `ro.serialno`, IMEI, operadora | `<removido>` |
| `package:com.whatsapp` | `package:app-N` — a **contagem** sobrevive |
| nome de arquivo em `ls -la` | `item` |
| e-mail, telefone | `<email>`, `<telefone>` |
| `Process: com.x` / `mCurrentFocus` | `com.<app>` / `<app>/<tela>` |

`test_varredura.py` cobra os dois lados: os 9 marcadores de vida privada **não
podem** aparecer, e o que reproduz o defeito **tem de** aparecer. E
`test_o_pacote_refaz_o_mesmo_relatorio_sem_o_celular` compara o relatório
refeito com o original — foi ele que achou que o pacote omitia
`pm list packages`, que o `ps` de duas colunas ficava ilegível e que faltavam
`thermal` e as falhas da anatomia.

`--pacote` funciona nos **dois** caminhos: `ver-tudo-no-celular.bat --pacote`
(varredura completa) e `escanear-celular.bat --pacote` (scanner sozinho). O
segundo ficou de fora na 0.94.1 por descuido — a opção era aceita e o zip não
saía.

O zip **não** leva a chave `comandos` do `coletar`: cada item dela é
`adb -s RXCW400ZV3F shell …`, ou seja, o serial do aparelho em texto. Quem refaz
remonta a lista vazia.
