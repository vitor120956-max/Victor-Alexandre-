# JARVIS 0.60.6 — o zip que existia e o código não achava

O primeiro download real do celular parou em:

```
A skill "Baixar adb e scrcpy" recusou o pedido: O download de platform-tools
não deixou arquivo utilizável.
```

O download tinha funcionado. O arquivo estava lá. O código procurava no lugar
errado.

## O que aconteceu

`sistema.baixar` não devolve o arquivo solto: ele é uma skill de análise e
devolve o **envelope** (`analysis`, `rows`, `metrics`, `findings`) com o bônus
guardado em uma chave chamada `download`:

```python
{
  "analysis": "baixar",
  "rows": [...],
  "metrics": {"bytes": 62384123, ...},
  "download": {"arquivo": "D:\\JARVIS\\storage\\host-downloads\\ab12cd34-platform-tools.zip",
               "sha256": "...", "bytes": 62384123, "tipo": "application/zip"}
}
```

`celular.preparar` lia `baixado["arquivo"]` — que nessa estrutura **não existe**.
Recebia string vazia, `Path("")` não é arquivo, e a skill recusava com a mensagem
de "não deixou arquivo utilizável". Os testes não pegaram porque o `baixar` falso
deles devolvia `{"arquivo": ...}`, o formato que o código esperava — não o que o
`sistema.baixar` entrega de verdade.

## O que mudou

- `celular._dados_do_download()` acha o arquivo nos dois formatos: dentro de
  `download` (o real) ou na raiz do dicionário. A leitura do `sha256` e do
  `bytes` segue a mesma regra.
- A mensagem de erro, quando o arquivo realmente não existir, agora **mostra o
  caminho** e diz o que conferir: se `storage\host-downloads` está vazia, o
  problema é conexão, não extração.
- Depois de extrair, o JARVIS **apaga o zip**. São ~90 MB no pendrive; deixá-los
  na quarentena só ocupa espaço e atrapalha a próxima tentativa.
- `sistema.baixar` separa **disco cheio** de falha de rede. Pendrive cheio agora
  diz "sem espaço em disco", em vez de mandar conferir a internet.
- O tempo limite da skill subiu de 600 s para 900 s: ~90 MB em conexão de 3G/4G
  fraca não cabiam com folga.

## Dois testes que faltavam

- `test_sistema_baixar_guarda_o_arquivo_em_download` — fixa o contrato real:
  o caminho mora em `download`, não na raiz.
- `test_preparar_com_o_sistema_baixar_de_verdade` — chama `preparar` contra o
  `sistema.baixar` de verdade (com `urlopen` servindo zip em memória) e exige
  `adb.exe` e `scrcpy.exe` no lugar. Era este que teria pego o bug.

Mais um: `test_preparar_apaga_o_zip_depois_de_extrair`.

## Como repetir o teste

Não precisa atualizar nada à mão além do normal:

```bat
cd /d D:\JARVIS
```

```bat
atualizar.bat
```

Feche a janela da API no X antes, suba de novo:

```bat
cd /d D:\JARVIS
```

```bat
.venv\Scripts\python iniciar.py
```

Depois, na interface: **baixar adb e scrcpy** → `sim, pode`.

O que deve acontecer: dois downloads seguidos (platform-tools do Google, scrcpy
do GitHub), cada um com SHA-256 no relatório, extração em
`storage\ferramentas\` e a mensagem final:

```
Baixei e extraí as duas ferramentas em ...\storage\ferramentas.
adb: ...\platform-tools\adb.exe · scrcpy: ...\scrcpy\scrcpy.exe.
Nada foi executado — o primeiro uso é `celular.status`.
```

## Testes

- `pytest server/tests` → **2.683 passed**.
- `test_celular.py` → **59** (4 novos: contrato do `download`, preparo contra o
  `sistema.baixar` real, mensagem com caminho e limpeza do zip).
- `vitest` → 120, `tsc -b` limpo, build embutido ok.
