# Acesso ao sistema

Todas as camadas anteriores liam texto colado na chamada. Esta é a primeira que toca a máquina: mede disco, enumera pastas, lista drivers e adaptadores Bluetooth, busca na internet, baixa arquivo e executa instalador.

Isso muda o contrato do projeto. Até a 0.29.0, toda resposta marcava `executed: false` e `readOnly: true`, e essa era a garantia de que nada acontecia. Aqui duas skills gravam e executam de verdade, e por isso a camada inteira é construída em volta de três travas que precisam ser **ligadas explicitamente**.

> **Aviso de origem.** Os dados são da máquina que executa a API. Se você roda o JARVIS num contêiner, é o contêiner — não o seu PC. A skill `sistema.ambiente` detecta isso e diz na cara.

## As três travas

| # | Trava | Padrão | Como ligar |
|---|---|---|---|
| 1 | **Token de host** | gerado no primeiro uso | já vem ligada; o valor está em `storage/host-token.txt` e aparece no terminal da API. Só é exigido de quem **grava ou executa** — desde a 0.49.0, buscar e ler página não pedem token. Desde a 0.57.0, `JARVIS_HOST_CONFIAR_LOCAL=1` preenche o token sozinho para quem está na própria máquina |
| 2 | **Rede** | desligada | `JARVIS_HOST_REDE=1` ao subir a API |
| 3 | **Instalação** | desligada | `JARVIS_HOST_INSTALAR=1` (implica rede) |

O token existe porque a API escuta numa porta. Sem ele, qualquer página aberta no navegador poderia ler o disco da máquina. Com ele, a leitura exige um valor que só está no sistema de arquivos do servidor e no terminal de quem o subiu.

```bash
JARVIS_HOST_REDE=1 JARVIS_HOST_INSTALAR=1 .venv/bin/uvicorn server.app:create_app --factory --port 8000
```

O token é impresso assim, com só oito caracteres visíveis:

```
JARVIS modo host: token em storage/host-token.txt -> Ab3d…9xQz (rede=ligada, instalar=ligado)
```

## Modo dono: instalar sem digitar o token (0.57.0)

O token de host não é chave de ninguém: é uma string que o próprio JARVIS sorteia
e guarda em `storage/host-token.txt`. Mas copiar e colar aquilo a cada instalação
é atrito. O **modo dono** tira esse atrito sem apagar as travas:

```bat
set JARVIS_HOST_CONFIAR_LOCAL=1
```

Com ele ligado, a API preenche o token sozinha **somente quando a requisição vem
da própria máquina** (`127.0.0.1` / `::1`). Requisição de outra máquina da rede
continua obrigada a digitar o token, mesmo com o modo ligado. Quando preenche, a
resposta traz `"autorizadoPor": "modo-dono-local"`.

**O que continua valendo no modo dono:**

1. `JARVIS_HOST_INSTALAR=1` — a trava de instalação é outra, e não muda;
2. o plano mostrado antes (`sistema.instalar`), com comando, risco e assinatura;
3. o token de uso único do plano — quando existe **um** plano pendente, ele é
   usado automaticamente; com dois, o JARVIS **não escolhe por você** e pede o
   código;
4. a confirmação da tela (`confirmed: true`), que o servidor exige.

**O que ele custa, dito sem enfeite:** com o modo ligado, qualquer programa que
rode **como você, nesta máquina**, pode disparar instalação pela API sem saber o
token. Antes, ele precisaria abrir `storage/host-token.txt` — que está legível
para o seu usuário. Ou seja: o modo dono não abre a porta para a rede e não abre
para página de outro site (o bloqueio de origem continua), mas reduz a exigência
de quem já está dentro da máquina. Se você usa o computador compartilhado, deixe
desligado.

**Bloqueio de origem (vale sempre).** Requisição `POST` para `/api/` com
`Origin` de outro site é recusada com `403 ORIGEM_RECUSADA`. É o que impede uma
página maliciosa aberta no navegador de chamar a API local.

```text
GET /api/health  →  { "version": "0.61.5", "skills": 288, "confiarLocal": true }
```

## “O que ele já instalou” e a remoção sugerida (0.59.0)

Toda execução bem-sucedida já ficava em `storage/host-audit.jsonl`, mas ninguém
lia de volta. Agora:

- **`sistema.instalados`** (só leitura) lista as instalações e remoções que
  terminaram com **código 0**, com data, alvo, tipo e o comando exato. O que
  falhou continua no registro como tentativa, mas não entra na lista;
- cada plano de instalação pendente traz **`remocao`**, com a sugestão de
  remoção quando ela é dedutível do próprio arquivo:

| Tipo | Sugestão | O que a nota avisa |
|---|---|---|
| `.deb` | `dpkg:nome` | confira o nome do pacote |
| `.rpm` | `rpm:nome` | confira o nome do pacote |
| `.msi` / `.msix` | — | Windows exige o GUID do produto |
| `.exe` | — | cada fabricante define o próprio desinstalador |
| `.AppImage` | — | não se instala: apagar o arquivo é a remoção |

No painel de planos da página **Skills**, um plano de instalação ganha o botão
**Desinstalar (dpkg:nome)**, que monta o plano de remoção — e esse plano, por sua
vez, aparece na mesma lista com **Executar remoção**. São dois passos de propósito:
montar não é executar.

```json
GET /api/host/planos
{"planos": [{
  "confirmacao": "665422bd", "acao": "instalar", "rotulo": "app_2.0_amd64.deb",
  "remocao": {"pacote": "dpkg:app", "nota": "Confira o nome do pacote antes de confirmar."}
}]}
```

## O botão “Executar este plano” (0.58.0)

Antes, o plano de instalação saía com um código de uso único e o passo seguinte
era chamar `sistema.executar` por conta própria. Agora a tela faz isso:

1. você executa `sistema.instalar` (ou `sistema.desinstalar`) e a resposta traz
   `confirmacao` mais a lista `rows` com alvo, tipo, comando, risco e SHA-256;
2. o próprio formulário mostra o cartão **“Plano pronto para executar”**, com o
   comando exato e uma caixa de confirmação;
3. a página **Skills** mostra, no topo, os planos pendentes que ainda valem —
   vindos de `GET /api/host/planos`, atualizado a cada 30 segundos;
4. o botão **Executar este plano** manda `sistema.executar` com o código, e só
   depois de você marcar a caixa.

O que o botão **não** faz: não escolhe plano por você (com dois pendentes, cada
um tem o seu botão), não ignora `JARVIS_HOST_INSTALAR=1` (com a trava desligada
os botões ficam desativados e a página diz qual variável ligar), não reusa
código (cada execução consome o token) e não esconde o comando — ele aparece em
texto antes do clique.

`GET /api/host/planos` devolve o código de uso único **só** para requisição vinda
da própria máquina. De fora, a resposta diz que existe plano, mas omite
`confirmacao`.

```json
{
  "ok": true,
  "local": true,
  "instalar": true,
  "total": 1,
  "planos": [
    {
      "confirmacao": "665422bd",
      "acao": "instalar",
      "rotulo": "pacote-teste.deb",
      "tipo": "deb",
      "comando": "dpkg -i /tmp/host-downloads/pacote-teste.deb",
      "sha256": "48a62627…",
      "expira_em": 599
    }
  ]
}
```

## As doze skills

| Rota | Efeito | O que devolve |
|---|---|---|
| `sistema.ambiente` | leitura | sistema, arquitetura, núcleos, memória, tempo ligado, detecção de contêiner e estado das travas |
| `sistema.disco` | leitura | total, usado e livre por unidade, com alerta em 15% e 5% |
| `sistema.pastas` | leitura | nome, tipo, tamanho e data até a profundidade pedida |
| `sistema.drivers` | leitura | módulos do kernel no Linux, drivers PnP assinados no Windows |
| `sistema.bluetooth` | leitura | adaptadores e dispositivos pareados |
| `sistema.rede` | leitura | resultados de busca ou texto de uma página |
| `sistema.baixar` | **grava** | arquivo em `storage/host-downloads`, bytes e SHA-256 |
| `sistema.assinatura` | leitura | SHA-256 comparado e assinatura digital verificada |
| `sistema.instalar` | leitura | comando exato, risco, SHA-256, assinatura e token de uso único |
| `sistema.desinstalar` | leitura | comando de remoção, risco e token de uso único |
| `sistema.executar` | **executa** | código de saída e mensagens do instalador |
| `sistema.regras` | leitura | guardas, allowlist, limites e recusas |

Leitura e efeito nunca dividem a mesma skill. `sistema.rede` não baixa, `sistema.instalar` não executa: quem escreve e quem executa são skills separadas, para que a fronteira apareça no catálogo e no `requiresConfirmation` da API.

## 1. Ambiente: saber em que máquina você está

`platform` dá o sistema; `/proc` dá memória, carga e tempo ligado; e a detecção de contêiner procura cinco evidências — `/.dockerenv`, `/run/.containerenv`, runtime no `/proc/1/cgroup`, `KUBERNETES_SERVICE_HOST` e o processo 1 não ser um init de sistema.

Quando alguma aparece, a resposta ganha um achado **must** dizendo que disco, pastas e drivers são do contêiner. Sem esse aviso, o diagnóstico de Bluetooth mais cuidadoso do mundo estaria olhando para a máquina errada.

Em Windows, memória e carga ficam **indisponíveis** em vez de estimadas: `psutil` seria dependência nova e ler `Win32_OperatingSystem` por PowerShell para um número secundário custa mais do que vale.

## 2. Disco: o número que responde "cabe?"

`shutil.disk_usage` é a fonte. Em volta dele, três decisões:

- **Pseudo-filesystems fora.** `/proc`, `sysfs`, `selinuxfs`, `ramfs`, `rpc_pipefs` e parentes nunca representam espaço do usuário. Sem o filtro, o relatório de um contêiner trazia seis unidades de zero byte e seis alertas de "disco cheio".
- **Bind mount não duplica.** Dois pontos de montagem com o mesmo `st_dev` viram uma linha só.
- **Volátil não alarma.** `tmpfs` e `overlay` aparecem na lista, marcados, mas nunca geram alerta de espaço: um `tmpfs` cheio é memória, não disco.

Faixas: até 5% livres é **must** — abaixo disso o sistema falha em gravar log e atualizar pacote. Até 15% é **should** — instalador grande tende a ser recusado.

## 3. Pastas: inventário sem abrir nada

A promessa é literal: nome, tipo, tamanho, data, nível. **Nenhum byte de conteúdo.** O teste da camada verifica isso procurando o conteúdo dos arquivos de fixture no JSON de saída.

Cinco cuidados:

| Situação | Comportamento |
|---|---|
| `.ssh`, `.gnupg`, `.aws`, `id_rsa`, `*.pem`, `*.key`, `.env` | reconhecido pelo nome, listado com tamanho **zero** e achado `nice` |
| link simbólico | listado como `link`, nunca seguido |
| pasta sem permissão | contada em `metrics.negados` e alertada |
| árvore maior que o limite | truncada, com achado — listagem incompleta que se declara completa é pior que erro |
| pasta vazia | achado `nice`, para não confundir ausência com invisibilidade |

Profundidade é o número de níveis abaixo da raiz: `2` lista a raiz, as subpastas e o conteúdo delas.

## 4. Drivers: duas plataformas, duas verdades

No Linux, `/proc/modules` lista módulos do kernel — nome, bytes, contagem de uso, dependências, estado. Versão vem de `/sys/module/<nome>/version`, quando o módulo declara.

No Windows, `Get-CimInstance Win32_PnPSignedDriver` via PowerShell com `-NoProfile -NonInteractive`, devolvendo JSON compacto. Traz versão, fornecedor, data e assinatura.

A limitação é dita em vez de escondida: módulo embutido no kernel não aparece em `/proc/modules`, e driver PnP do Windows depende do provedor CIM estar disponível. Lista vazia por falha é diferente de lista vazia por ausência — por isso quando o PowerShell não responde sai achado, não tabela vazia.

## 5. Bluetooth: por que o fone não conecta

Este é o caso de uso que abriu a camada, então a skill não devolve só a lista: devolve o diagnóstico.

| Achado | Grupo | O que significa |
|---|---|---|
| nenhum adaptador | **must** | não existe rádio Bluetooth. Nenhum programa resolve: precisa de hardware |
| adaptador desligado ou com erro | **must** | rádio presente, mas fora do ar |
| adaptador sem nenhum pareado | **should** | o fone não entrou em modo de emparelhamento |
| consulta indisponível | **should** | lista vazia pode ser falha, não ausência |

No Linux, adaptadores vêm de `/sys/class/bluetooth` e pareados de `/var/lib/bluetooth/<adaptador>/<mac>/info`. No Windows, `Get-PnpDevice -Class Bluetooth`.

O parecer repete o que não é óbvio: **não existe programa leve que faça fone Bluetooth funcionar**. Quem pareia é o serviço nativo do sistema. O que falha é hardware, driver ou modo de emparelhamento.

## 6. Rede: buscar e ler

A 0.49.0 tirou o token do caminho da leitura: `buscar` e `olhar` só precisam de `JARVIS_HOST_REDE=1`. O token continua obrigatório em `sistema.baixar`, `sistema.executar` e `sistema.elevar_executar`, que gravam ou rodam — a regra é o efeito, não a rede.

Busca usa três fontes que não cobram chave, em `server/busca_web.py`: a página HTML do **DuckDuckGo** (sem chave e sem SDK), a **API da Wikipédia** (opensearch) e a página de resultado do **YouTube**. Sem fonte pedida, as três se intercalam; com `fonte=duckduckgo`, `wikipedia` ou `youtube`, só aquela responde. Cada linha devolve `fonte` e `tipo` (`web`, `enciclopedia`, `video`), e a resposta separa “Fontes que responderam” de “Fontes que não responderam” — uma fonte fora do ar não apaga as outras.

Leitura de página extrai o texto: remove `script`, `style` e `noscript`, tira as tags, resolve as entidades, colapsa espaço.

Antes de qualquer requisição, a URL passa por uma guarda que recusa:

- esquema diferente de `http`/`https` (`file:`, `ftp:`, `javascript:`);
- `localhost`, `*.local`, `*.internal`;
- IP literal em faixa privada, laço local ou link-local;
- host que **resolve** para endereço privado — o DNS também é checado, não só o texto da URL.

Essa última linha é a que importa: sem ela, um domínio público apontando para `127.0.0.1` transformaria a API em proxy para ela mesma.

## 7. Baixar: quarentena com hash

Download vai para `storage/host-downloads` com prefixo aleatório, teto de 256 MB e SHA-256 calculado durante a escrita. Nome vindo da URL é sanitizado para `[A-Za-z0-9._-]`: `..%2F..%2Fetc%2Fpasswd.msi` vira `.._.._etc_passwd.msi` dentro da quarentena, nunca fora.

Cada download vira uma linha em `storage/host-audit.jsonl`. Arquivo de zero byte e extensão fora da allowlist geram achado.

## 8. Instalar: plano, risco e token

O plano mostra o comando exato, o tipo, o risco e devolve um token de oito caracteres válido por **10 minutos** e **de uso único**.

| Tipo | Comando | Risco |
|---|---|---|
| `msi` / `msix` | `msiexec /i <arquivo> /qb /norestart` | médio |
| `deb` | `dpkg -i <arquivo>` | médio |
| `rpm` | `rpm -Uvh <arquivo>` | médio |
| `exe` | `<arquivo> /S` | **alto** |
| `appimage` | `chmod +x` e nada mais | baixo |
| `pip` | `<python> -m pip install <nome>` | médio |
| `npm` | `npm install <nome>` | médio |

Só arquivo que está **dentro** da quarentena entra no plano. `sistema.instalar` com `/etc/passwd` é recusado antes de qualquer coisa.

## 9. Executar: o único lugar que roda algo

Quatro condições simultâneas:

1. `JARVIS_HOST_INSTALAR=1` no processo da API;
2. token de host válido;
3. token de confirmação devolvido pelo plano;
4. `confirmed: true` na chamada HTTP.

O token é consumido na primeira tentativa — inclusive quando falha. O comando executado é **exatamente** o que o plano mostrou, montado a partir de uma lista fechada de binários; nenhum texto do usuário entra numa linha de comando, e `subprocess` roda com `shell=False`.

## 10. Assinatura e integridade

Assinatura válida é a única prova de origem que não depende de confiar no domínio. A camada chama o verificador que a plataforma oferece e **declara quando não consegue verificar** — nunca trata ausência de verificação como aprovação.

| Alvo | Fonte | O que significa o resultado |
|---|---|---|
| `.msi`, `.msix`, `.exe` no Windows | `Get-AuthenticodeSignature` | `Valid` → válida; `NotSigned` → ausente; `HashMismatch`/`NotTrusted` → **inválida** |
| `.rpm` no Linux | `rpm -K` | `digests signatures OK` → válida; só `digests OK` → ausente; `NOT OK` → inválida |
| `.deb` no Linux | `dpkg-sig --verify` | sem o pacote instalado → **não verificável**, e isso é dito |
| assinatura destacada `.sig`/`.asc` | `gpg --verify` | `Good signature` → válida com o nome do assinante |
| qualquer arquivo | SHA-256 em fluxo | comparado com o hash publicado pelo projeto |

O caminho do arquivo **não entra na linha de comando** do PowerShell: ele viaja na variável de ambiente `JARVIS_ALVO`, e o script é fixo no código. É a mesma regra do resto da camada — nenhum texto do usuário em comando.

O SHA-256 é sempre calculado. Com `hash_esperado`, vira comparação: divergência é achado **must**, porque hash errado significa arquivo alterado, download truncado ou hash copiado de outro pacote — e os três terminam igual.

Assinatura válida prova **origem e integridade**, não segurança. Um instalador assinado por fabricante sério ainda pode ser um programa ruim.

## 11. Instalação com exigência de assinatura

O plano de instalação mostra agora SHA-256 e estado da assinatura, e aceita `exigir_assinatura`:

- `exigir_assinatura: false` (padrão) — a assinatura é reportada e o plano só alerta;
- `exigir_assinatura: true` — se a verificação não confirmar `válida`, o plano ganha achado **must** e o `sistema.executar` **recusa**, mesmo com token válido.

## 12. Desinstalação simétrica

O desinstalador reaproveita o mesmo caminho de execução: ele só **planeja** e devolve token; quem roda é `sistema.executar`.

| Alvo | Comando |
|---|---|
| `dpkg:nome` | `dpkg -r nome` |
| `rpm:nome` | `rpm -e nome` |
| `pip:nome` | `<python> -m pip uninstall -y nome` |
| `npm:nome` | `npm uninstall nome` |
| `msi:{GUID}` | `msiexec /x {GUID} /qb /norestart` |
| arquivo `.msi` da quarentena | `msiexec /x <arquivo> /qb /norestart` |

Risco **alto** para pacote de sistema: remover um pacote leva dependências junto. Por isso o achado **must** pede que você confira o que depende dele antes de confirmar. E o achado **should** lembra que remoção não apaga resíduo: configuração em `~/.config` e `AppData` continua ocupando espaço.

AppImage não tem desinstalador — apagar o arquivo seria remoção de arquivo, e esta camada não apaga nada.

## 13. Revalidação entre plano e execução

O token não é um cheque em branco. O plano grava o SHA-256 do arquivo, e `sistema.executar` recalcula antes de rodar:

- **arquivo mudou depois do plano** → recusa e pede plano novo (proteção contra troca de binário entre revisão e execução);
- **`exigir_assinatura` ligado** → revalida a assinatura na hora de executar, não só no plano;
- **token consumido** → não serve de novo, nem quando a execução falha.

Cada execução — instalar ou remover — vira uma linha em `storage/host-audit.jsonl` com a ação, o alvo, o comando e o código de saída.

## O que esta camada recusa fazer

- **Shell livre.** Não existe campo de comando. Rodar binário arbitrário transformaria a API num executor genérico.
- **Ler conteúdo de arquivo.** A enumeração é metadado.
- **Parear Bluetooth.** Lista e diagnostica, não conecta.
- **Confiar sem verificar.** A assinatura é validada quando a plataforma permite e declarada como não verificável quando não permite.
- **Elevar privilégio por conta própria.** Instalador que pede administrador falha nesta camada. A elevação existe em camada separada — `sistema.elevar` e `sistema.elevar_executar` (0.33.0), com token próprio, tabela fechada de seis ações e auditoria —; esta camada não a chama por dentro nem a esconde. Detalhes em [`ROOT.md`](ROOT.md).
- **Apagar, mover ou renomear.** O desinstalador chama o gerenciador de pacotes; nenhum arquivo do usuário é removido por esta camada.
- **Alcançar rede privada.** Bloqueado por política, inclusive via DNS.

## Limites de volume

1,8 MB de texto, 200 linhas de tabela, 2.000 entradas por listagem, profundidade 6, página de 2 MB, download de 256 MB, timeout de rede de 20 s e de instalador de 300 s.

## Como rodar

```bash
npm run dev                     # API 8000 + Vite 5173
JARVIS_HOST_REDE=1 npm run dev  # libera busca, leitura de página e download
# página: /sistema
curl -s localhost:8000/api/health
```

```bash
.venv/bin/python -m pytest server/tests/test_sistema.py -q
```

## Sem upstream

Esta camada não adapta um repositório. O desenho vem do problema — diagnosticar a própria máquina e instalar software com autorização — e das APIs padrão de cada sistema: `shutil.disk_usage`, `/proc`, `/sys`, `Get-PnpDevice` e `Win32_PnPSignedDriver`. Não há arquivo de licença a acrescentar em `docs/licenses/` porque não há obra de terceiro copiada ou adaptada.
