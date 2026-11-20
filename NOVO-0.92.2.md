# 0.92.2 — Anatomia: ler o aparelho sem mudar nada nele

> tem como pedir para uma IA se implementar 100 a um dispositivo para ele pd ver
> gpu cpu temperatura tudo do aparelho e ter acesso total atraves de uma
> varredura da ia onde ela estiver estalada

> ja tenho uma IA local q estou programando mas queria integrar para ter acesso
> total em um aparelho so de conectar ele no usb tipo fazer uma varredura ou uma
> endinare reverse nao para modicar mas para entender todo os componentes do
> dispositivos e arquivos e como eles sao feitos e moldados para melhor
> compreensao igual a anatomia humana

> ou se eu quiser conectar por exemplo uma tv antiga q pega wifi tipo uma tcl

> Roku TV

## A resposta curta

O JARVIS **já consegue** ler o aparelho — e agora tem uma aba para isso: menu
**Anatomia**, entre “Reversa” e “Meu jogo”. Três alvos, uma regra: **ler não é
mexer**.

| alvo | pluga | lê |
|---|---|---|
| **Este computador** | nada | CPU, núcleos, memória, discos, GPU, temperatura |
| **Android (USB)** | cabo de dados | modelo, SoC, Android, bateria, memória, armazenamento, partições, térmica, apps |
| **TV Roku (Wi-Fi)** | o IP da TV | modelo, série, Roku OS, canais, canal ativo, portas |

## O que a resposta que você colou prometia a mais

Você trouxe a conversa inteira de outro assistente. Ela acertou o caminho
(`adb` para o Android, ECP 8060 para a Roku) e exagerou em quatro pontos — que
agora estão escritos no código e nos testes:

1. **“varredura automática ao plugar o cabo”** — não existe. A Depuração USB
   ligada e o toque em “Permitir depuração USB?” na tela são consentimento de
   uma pessoa, uma vez por computador. Nenhum programa contorna isso.
2. **“temperatura sem root”** — depende do aparelho. Muitos Androids escondem
   `/sys/class/thermal`. Quando esconde, o JARVIS diz **“não exposta”** com o
   motivo, em vez de mostrar zero.
3. **“temperatura da TV pela API”** — o Roku não publica temperatura no ECP.
   Quem mostra é a tela de engenharia **no aparelho**, com o controle na mão.
4. **“binwalk no firmware da TV”** — o firmware do Roku é assinado e
   criptografado; não há cabeçalho para o binwalk reconhecer.

E uma coisa que a conversa sugeriu e este módulo **não** faz de propósito:
`POST /keypress` no Roku. Apertar botão muda o estado da TV, e o pedido era
entender — não mexer.

## O que mudou no código

- **`server/anatomia.py`** (novo): `ler_local`, `ler_android`, `ler_roku`,
  `fontes`. Cada número carrega a fonte; cada ausência carrega o motivo.
- **`/api/anatomia/fontes`**, **`/local`**, **`/android`**, **`/roku`** —
  leitura por `GET`; erro explicado em `409` com a frase que resolve.
- **Aba Anatomia** (`/anatomia`): cartões dos três alvos, campo de IP da TV com
  instrução, e o resultado em seções de rótulo/valor, com “o que a leitura não
  alcança” e “o que o JARVIS não faz” embaixo.
- **Guarda de escrita**: o Android continua atrás de `JARVIS_HOST_CELULAR=1`
  e a rede atrás de `JARVIS_HOST_REDE=1` — as mesmas variáveis do resto do
  projeto. A leitura do computador não pede nada.

## Defeito achado e corrigido no caminho

`dumpsys battery` publica a temperatura em **décimos** de grau. O primeiro
código tratou como milésimos e mostrava **0,3 °C** onde o aparelho dizia
**31,2 °C**. O teste fixa o valor certo, e a conversão ganhou nome próprio
(`_decimos_celsius`) para não voltar.

## Medido

- `pytest server/tests` — **4 169 casos, 0 falhas, 7 pulados** (21 novos).
- `pytest server/tests/test_anatomia.py` — 21/21.
- `npx tsc --noEmit` limpo; `vitest` **243/243**; `npm run build:embutido` ok.
- Servidor real na 8011: `/api/anatomia/local` devolveu CPU Intel Xeon, 2
  núcleos, 3,8 GB de RAM e **“não exposta”** para GPU/temperatura — a máquina de
  teste não tem sensor acessível, e a resposta disse isso em vez de inventar.
  `/api/anatomia/android` → **409** com “o `adb` não está instalado: use
  ‘Preparar celular’ na aba Máquina”. `/api/anatomia/roku?ip=8.8.8.8` → **409**
  (“só endereço da própria rede”). `/anatomia` → **200**.
- Roku: servidor ECP falso em 8060 serviu `device-info`/`apps`/`active-app`
  reais; o módulo leu modelo, Roku OS, 2 canais e o canal ativo pelo caminho
  HTTP de verdade.

## Como testar no seu PC

1. `atualizar.bat` → `iniciar-jarvis.bat`.
2. **Ctrl+F5** e abra **Anatomia** no menu.
3. “Ler este computador” funciona de imediato.
4. Para o celular: ligue a Depuração USB, conecte o cabo e toque em “Permitir”;
   se o `adb` faltar, a própria tela manda para **Máquina → Preparar celular**.
   Acrescente `set JARVIS_HOST_CELULAR=1` no `iniciar-jarvis.bat` e reabra.
5. Para a TV: veja o IP em **Ajustes → Rede** da Roku, digite no campo e clique
   em “Ler a TV”. Precisa de `set JARVIS_HOST_REDE=1` no mesmo arquivo.
