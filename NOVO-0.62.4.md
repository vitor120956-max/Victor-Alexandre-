# JARVIS 0.62.4 — a sonda não estava olhando o lugar certo

O resultado que você mandou:

```
Nenhum aparelho Samsung (VID_04E8) na lista USB do Windows.
```

Está correto — e **incompleto**. Eu escrevi a sonda com dois furos meus:

## Furo 1: procurei MTP dentro da lista de USB

A versão 0.62.3 consultava:

```
DeviceID LIKE 'USB%'
```

e depois procurava `MTP`/`Portable` **dentro desse resultado**. Só que o MTP do
seu J7 aparece como `SWD\WPDBUSENUM\...` — **não começa com `USB`**. Ou seja: a
sonda nunca poderia ver o "Dispositivo portátil" que ela mesma mandava você
procurar. O aviso estava lá, a capacidade de confirmá-lo não.

Agora é **uma consulta só, sem filtro**, e a classificação é feita dentro:
nós `USB\VID_04E8` (Samsung), nós `SWD\WPDBUSENUM` (MTP/WPD) e nomes com
"MTP/Android/Samsung/Portable" — cada um impresso separado.

## Furo 2: falha de consulta virava "não há aparelho"

`$ErrorActionPreference = "SilentlyContinue"` engolia erro de WMI. Se a consulta
falhasse, a lista vinha vazia e a sonda dizia *"Sem aparelho na USB não há driver
a consertar"* com toda a confiança — um falso negativo com cara de diagnóstico.

Agora existe o **código 3**: "não consegui consultar o Windows". Ele é diferente
de "não achei o aparelho" e diz isso na tela.

## O que a sonda mostra agora

```
O Windows tem 214 dispositivos; 37 sao nos USB.

Dispositivo portatil / MTP que o Windows esta vendo:
    Dispositivo MTP USB
      id:     SWD\WPDBUSENUM\...
      driver: WudfRd

VID dos nos USB ligados agora: 8087 046D 058F 04E8
(04E8 seria Samsung; 058F e o leitor de cartao; 046D e mouse/teclado)
```

O `VID dos nos USB` é a prova do que foi visto. Se `04E8` não estiver lá, o
celular **não está enumerando** — e aí não é driver, é antes disso.

## `sonda-otg.bat` agora sabe esperar

Se não achar nada, ele pergunta:

```
Quer que eu fique olhando por 30 segundos, para voce mexer no cabo
e na tela sem correr contra o tempo?
  Digite S e Enter para esperar (ou so Enter para sair):
```

Durante a espera ele imprime a contagem (`aguardando o celular aparecer...
27s`) a cada 3 segundos — sinal de vida, não tela parada. Você desplugа e
repluga o cabo enquanto ele olha.

## Como ler os códigos

| código | significa | o que fazer |
| --- | --- | --- |
| **0** | driver de OTG já instalado | abrir `teclado-pelo-pc.bat` |
| **1** | MTP segurando o aparelho | Zadig (a sonda imprime o `VID_x&PID_y` exato) |
| **2** | o Windows não vê nenhum Samsung | cabo, porta ou tela apagada |
| **3** | a consulta ao Windows falhou | nada a concluir; rodar de novo |

## Detalhe de repositório

`vigiar-usb.ps1` voltou com LF depois de uma reinicialização do ambiente e o
teste de CRLF pegou. Além disso, o `.gitattributes` só protegia `*.bat` da
normalização de quebra de linha — agora protege `*.ps1` também.

## Testes

- `pytest server/tests` → **2.821 passed** (`test_celular.py`: 165).
- Novos: a sonda não usa mais filtro `LIKE 'USB%'` no código, olha
  `SWD\WPDBUSENUM`, separa falha de consulta (código 3) de aparelho ausente
  (código 2), imprime os VID e a contagem de nós, tem modo de espera com
  `Start-Sleep`, e o `.bat` só oferece a espera quando o código é 2.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
