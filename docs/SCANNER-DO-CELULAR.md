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
