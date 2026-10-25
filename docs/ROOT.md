# Root — elevação controlada

A 0.33.0 responde a um pedido direto: *"seria bom o JARVIS ter e poder usar o sistema de root"*.

A resposta do projeto é **canal estreito**, não processo root. A API continua rodando com o seu usuário; o que ganha root é o comando de uma tabela fechada, por um instante, com token e registro de auditoria.

## Por que não "a API como root"

| Comparação | API como root | Canal estreito (o que foi feito) |
|---|---|---|
| Quem tem root | o processo inteiro, sempre | o binário da tabela, na chamada |
| Um bug em qualquer skill | vira bug de root | continua bug de usuário |
| Um patch promovido pela evolução | roda como root | roda como usuário |
| Um instalador baixado da internet | roda como root | só `dpkg`/`rpm` com arquivo da quarentena |
| Token vazado | root remoto | alcance limitado à tabela |
| Arquivos em `storage/` | passam a ser do root | continuam seus |

O argumento decisivo é o terceiro: a camada de evolução pode promover código novo. Com a API como root, todo patch promovido herda root no próximo pedido. O ensaio roda a suíte, mas suíte não julga intenção — isso já está escrito em `EVOLUCAO.md`.

## As três skills

| Skill | Efeito | Travas | O que faz |
|---|---|---|---|
| `sistema.privilegio` | leitura | token de host | Mostra uid/euid, se a API é root, se o `sudo` existe e dispensa senha, os serviços autorizados e a linha de `sudoers` sugerida |
| `sistema.elevar` | leitura | token de host | Monta o argv exato da ação, com SHA-256 e token de uso único. Não executa nada |
| `sistema.elevar_executar` | **root** | token + `JARVIS_HOST_ROOT=1` + `confirmed` + token 8 hex | Roda `sudo -n` com o argv do plano, revalidando alvo, hash e comando |

## A tabela fechada

Seis ações. Não existe campo de comando livre em nenhuma delas.

| Ação | Comando montado | Alvo |
|---|---|---|
| `instalar_deb` | `sudo -n dpkg -i -- <arquivo>` | `.deb` dentro de `storage/host-downloads` |
| `remover_deb` | `sudo -n dpkg -r -- <pacote>` | nome de pacote validado por regex |
| `instalar_rpm` | `sudo -n rpm -Uvh -- <arquivo>` | `.rpm` dentro de `storage/host-downloads` |
| `remover_rpm` | `sudo -n rpm -e -- <pacote>` | nome de pacote validado por regex |
| `reiniciar_servico` | `sudo -n systemctl restart -- <unidade>` | unidade listada em `JARVIS_HOST_SERVICOS` |
| `parar_servico` | `sudo -n systemctl stop -- <unidade>` | unidade listada em `JARVIS_HOST_SERVICOS` |

O `--` não é enfeite: ele encerra as opções do binário e impede que um caminho começando com `-` seja lido como flag. O nome do pacote passa por `^[a-z0-9][a-z0-9+.-]{0,63}$`; a unidade, por `^[A-Za-z0-9][A-Za-z0-9@._:-]{0,63}$` **e** precisa estar na lista que você declarou.

Serviços são opt-in explícito:

```bash
JARVIS_HOST_SERVICOS=meuapp.service,outro.service
```

Sem a variável, `reiniciar_servico` recusa com a mensagem de que nenhum serviço está autorizado.

## As travas, em ordem

1. **Token de host** — `storage/host-token.txt`, o mesmo da camada de sistema.
2. **`JARVIS_HOST_ROOT=1`** — desligada por padrão. Sem ela, `sistema.elevar` planeja e `sistema.elevar_executar` recusa.
3. **`confirmed: true`** — a confirmação da interface contra disparo acidental.
4. **Token de 8 hex** — devolvido pelo plano, válido 10 minutos, uso único, ligado ao alvo e ao SHA-256.
5. **Revalidação na execução** — o arquivo continua na quarentena, o hash é o mesmo, o argv é byte a byte o do plano.
6. **`sudo -n`** — se o sudo pedir senha, o comando falha na hora em vez de ficar esperando num terminal que não existe.

## O sudoers, que é quem manda de verdade

O Python não concede root: ele pede. Quem decide é o `/etc/sudoers`. A linha sugerida, devolvida por `sistema.privilegio`, é:

```sudoers
user ALL=(root) NOPASSWD: /usr/bin/dpkg, /usr/bin/rpm, /usr/bin/systemctl
```

Grave em `/etc/sudoers.d/jarvis-elevacao` com dono `root:root` e modo `0440`, e valide com `visudo -c`.

**O limite honesto:** `NOPASSWD` para `dpkg` ou `rpm` é equivalente a root. Quem pode instalar um pacote pode instalar um pacote que faz qualquer coisa. O ganho do canal estreito não é impedir um processo comprometido de virar root — é:

- impedir que um **bug acidental** vire root (o código só monta seis comandos);
- impedir que **texto do usuário** vire linha de comando;
- deixar **uma linha auditável** em `storage/host-audit.jsonl` por execução;
- fazer o root acontecer **quando você pede**, e não o tempo todo.

Se você quiser mais do que isso, o caminho é `systemd` com unit própria e usuário dedicado — fora do escopo desta camada.

## O que muda na prática

| Antes (0.32.0) | Agora (0.33.0) |
|---|---|
| `dpkg -i` falhava por permissão | `instalar_deb` instala, se o sudoers permitir |
| `systemctl restart` falhava | funciona para unidades autorizadas |
| Root só rodando a API como root | Root por comando, com token e auditoria |
| Patch com `sudo` passava com 10/100 e 10 guardas intactas | `sudo`, `pkexec`, `doas`, `runas`, `su -` e setuid dão **60/100 e bloqueio** |

A última linha é a correção que faltava: medido antes da mudança, um patch com `subprocess.run(["sudo", ...])` recebia nota **10/100 "baixo"** e as dez guardas diziam "preservadas". Agora o mesmo patch soma **60/100, nível alto**, e a G2 acusa violação.

## O que ela recusa

- Comando livre, shell, `bash -c`, `sudo su`, `sudo -i`.
- Arquivo fora da quarentena, inclusive `/tmp`.
- Pacote com espaço, `;`, `/`, maiúscula ou mais de 64 caracteres.
- Serviço fora da lista declarada.
- Elevar sem `JARVIS_HOST_ROOT=1`, mesmo com o token na mão.
- Reaproveitar token: o segundo uso é recusado.
- Executar com o arquivo alterado desde o plano.
- Rodar em máquina sem `sudo` (a skill diz isso no plano, não falha no meio).

## Como conferir

```bash
curl -s -X POST http://127.0.0.1:8000/api/skills/sistema.privilegio/execute \
  -H 'Content-Type: application/json' \
  -d "{\"parameters\":{\"autorizacao\":\"$(cat storage/host-token.txt)\"}}"
```

A resposta traz `metrics.root`, `metrics.semSenha` e a linha de sudoers pronta para copiar.

Para testar o ciclo inteiro sem instalar nada de verdade, use um pacote descartável na quarentena e acompanhe `storage/host-audit.jsonl`.
