# Instalador — onde guardar, se roda, e só então instalar

A pergunta que abriu esta camada: *“se eu pedir para baixar um programa, ele
pergunta onde deixar o arquivo, me dá as opções, avisa se pode instalar e, antes
de instalar, confere se o programa é compatível com o meu PC?”*

**Sim — e a conferência vem antes do download.** A ordem é esta:

```text
destinos  →  analisar  →  baixar  →  sistema.instalar  →  sistema.executar
(onde)       (roda?)      (guarda)   (plano + token)      (executa, com trava)
```

Nenhum passo instala por conta própria. `instalador.*` **não executa nada**: ele
mede, guarda e explica. Quem executa é `sistema.executar`, com token de uso único
e `JARVIS_HOST_INSTALAR=1`.

## 1. Onde guardar — `instalador.destinos`

Quatro opções, todas **dentro da quarentena** (`storage/host-downloads`), com o
espaço livre real de cada uma:

| Nome | Pasta | Para quê |
|---|---|---|
| `padrao` | `host-downloads` | o caminho normal |
| `programas` | `host-downloads/programas` | separar instalador de download avulso |
| `temporarios` | `host-downloads/temporarios` | o que você apaga depois de instalar |
| `por-data` | `host-downloads/2026-10` | uma pasta por mês |

Também aparecem, marcadas como **“guardar sim, instalar não”**, a pasta
`Downloads`, a Área de Trabalho e cada disco. O motivo é a trava: `sistema.executar`
só instala arquivo que está dentro da quarentena. Mudar de pasta não muda a trava
— e é melhor dizer isso do que deixar você salvar em `D:\Programas` e descobrir
depois que não instala.

Nome livre também vale: `instalador.baixar` aceita `destino: "jogos"` e cria
`host-downloads/jogos`. Barra, `..` e nome começando com ponto são recusados.

## 2. Se roda no seu PC — `instalador.analisar`

**Não executa o arquivo.** Lê o cabeçalho e compara com o PC medido.

### O que ele mede na máquina (`instalador.maquina`)

Windows e build (1607 é build 14393), arquitetura (x64/x86/ARM64), RAM,
núcleos, espaço livre de cada disco e as versões do .NET Framework instaladas.

### O que ele lê no arquivo

| Formato | O que é lido |
|---|---|
| `.exe` (PE) | 32/64 bits, arquitetura (x86, x64, ARM64, Itanium), **versão mínima de Windows declarada no próprio binário**, subsistema (janela/console), se é .NET e qual |
| `.exe` antigo (NE/MZ) | programa de 16 bits — recusado, o Windows 10 x64 não roda |
| `.msi` | é um MSI de verdade (assinatura OLE), arquitetura declarada (`Intel;`/`x64;`) |
| `.msix` / `.appx` | exige build mínimo (MSIX só existe a partir do 1809) |
| `.zip` | lista o instalador que está dentro, sem extrair |
| `.dmg`, `.deb`, `.rpm`, `.apk` | pacote de outro sistema — recusado com o motivo |
| `.bat`, `.cmd`, `.ps1` | script — roda o que está escrito, sem tela de instalação |

Além disso: **assinatura Authenticode** (`válida`, `não assinada`, `inválida`) por
`Get-AuthenticodeSignature`, tamanho contra o espaço livre e o que você informar
da página do fabricante:

```json
{"arquivo": "setup.exe", "min_os": "1809", "ram_gb": 8, "disco_gb": 20}
```

### O veredito

- **roda** — nada no arquivo nem na máquina impede;
- **roda com ressalva** — roda, com um motivo dito (sem assinatura, .NET 3.5
  desligado, espaço apertado, ZIP sem instalador reconhecido);
- **não roda** — e o motivo: 16 bits, ARM64 no seu x64, MSIX no 1607, pede
  Windows maior, pede mais RAM que a instalada, pacote de outro sistema;
- **não dá para saber** — o arquivo não declara o suficiente. Ele diz isso em vez
  de chutar.

Duas listas separadas deixam o texto honesto: **bloqueios** e **ressalvas** são
do arquivo; **avisos** são do seu PC (ex.: “Windows 1607 é antigo — muitos
instaladores de 2025 pedem 1809 e recusam na instalação”; “4 GB de RAM:
programas com Electron ficam pesados”). Aviso não muda o veredito.

## 3. Baixar — `instalador.baixar`

Reusa `sistema.baixar` (trava de rede, teto de tamanho, SHA-256, quarentena) e
move o arquivo para a subpasta escolhida. Depois **já analisa** o que chegou e
devolve o veredito no mesmo retorno. Link sem nome de arquivo (tipo
`/refs/heads/main`) ganha extensão pelo `content-type`.

## 4. Instalar — de propósito, fora daqui

```text
sistema.instalar   → mostra o comando, a assinatura e devolve um token de uso único
sistema.executar   → exige o token, JARVIS_HOST_INSTALAR=1 e revalida o SHA-256
sistema.desinstalar → monta a remoção pelo gerenciador certo
```

`instalador.analisar` deixa esses passos prontos em `proximos_passos`, com o
caminho do arquivo. Nada é instalado por esta camada.

## 5. O que ela não faz

1. **Não baixa sem rede ligada e token** — `instalador.baixar` depende de
   `sistema.baixar`.
2. **Não executa, não descompacta, não instala.** Extrair um ZIP é ação sua (ou
   de `sistema.executar`, com o arquivo certo).
3. **Não inventa requisito.** Se o `.exe` não declara versão mínima, o texto diz
   “não declarado”; o aviso sobre o Windows 1607 é sobre a máquina, não sobre o
   arquivo.
4. **Não promete rodar fora do Windows.** A análise de cabeçalho funciona em
   qualquer sistema; a medição da máquina vira “Linux/macOS” e o texto avisa que
   a camada de instalação é do Windows.

## 6. Onde ficam os arquivos

| Peça | Caminho |
|---|---|
| medição, leitura de cabeçalho, veredito | `server/instalador.py` |
| skills | `instalador.maquina`, `instalador.destinos`, `instalador.analisar`, `instalador.baixar` |
| testes | `server/tests/test_instalador.py` (40, com PE/MSI/MSIX de mentira e download dublê) |

Os testes montam cabeçalhos PE à mão (x64, x86, ARM64, 16 bits, .NET, MSIX) e
**não abrem, baixam ou instalam nada**. O download é uma função injetada.
