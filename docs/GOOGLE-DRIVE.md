# Google Drive como espaço de fora (0.47.0)

O Drive serve para uma coisa: guardar o que é **grande e parado** — livro, PDF,
vídeo baixado, repositório. Ele não serve para o que o JARVIS regrava a cada
resposta. Este guia separa as duas coisas, mostra o passo a passo e diz o que
fazer para o PC de 4 GB não travar.

---

## 1. A regra que evita travamento

| O que | Onde fica | Por quê |
| --- | --- | --- |
| `biblioteca/` (livros, PDFs, legendas, índices) | **Drive** | grava uma vez por importação e só lê depois |
| `repos/` (repositórios copiados) | **Drive** | idem |
| `historico.json`, `fila.json`, `skills.json`, `host-*.json` | **PC** | são regravados toda hora; no Drive cada gravação vira uma sincronização |
| `.venv/`, `node_modules/`, `web-dist/` | **PC** | milhares de arquivos pequenos; o Drive vai a 100% de CPU tentando acompanhar |

Se o JARVIS inteiro fosse para o Drive, cada resposta do agente faria o app de
sincronização subir um arquivo. É exatamente o que já aconteceu com os `.cas`:
**33% de CPU e 13,8 MB/s de disco** só para sincronizar.

---

## 2. Jeito mais rápido: peça para o JARVIS

O JARVIS faz tudo isso sozinho, pelas skills `armazenamento.drive` (só olha) e
`armazenamento.drive-copiar` (copia e grava). No chat:

| Você diz | Ele faz |
| --- | --- |
| `como configuro o drive?` · `o drive tá configurado?` | mostra o estado: onde estão os arquivos hoje, o que o `.env` aponta, espaço livre — **sem tocar em nada** |
| `configura o google drive pra mim` | mostra o que vai copiar e **pede o seu "sim"**; depois copia, confere e grava as duas linhas no `.env` |
| `tira a biblioteca do drive` | só apaga as linhas do `.env`; **nada é apagado do Drive** |
| `limita a banda do drive` · `limita o drive em 500` | grava o limite de banda do app do Drive e confere lendo de volta |

Na interface, o pedido cai na tela de confirmação antes de qualquer escrita — é
o mesmo portão das skills que baixam ou executam alguma coisa. Depois de
confirmar, ele responde com quantos arquivos copiou, para onde, e lembra de
reiniciar.

Pelo terminal dá no mesmo: `usar-drive.bat` faz a mesma cópia com progresso na
tela (é o jeito bom quando são milhares de arquivos).

---

## 2b. O que o JARVIS faz e o que só você faz

| Ajuste | O JARVIS consegue? | Por quê |
| --- | --- | --- |
| apontar `biblioteca`/`repos` para o Drive | **sim** | mexe em pasta e no `.env` |
| conferir se continua tudo no lugar | **sim** | lê pasta e processo |
| **limitar a banda** (download/upload) | **sim** | o app do Drive lê `BandwidthRxKBPS`/`BandwidthTxKBPS` de `HKCU\Software\Google\DriveFS`, e isso a Google documenta |
| marcar a pasta como *disponível off-line* | **não** | é estado interno do app; não há chave nem linha de comando pública |
| pausar/retomar a sincronização | **não** | idem — só pelo menu do app |
| mostrar se o Drive está pesando | **sim** | `diagnostico-lento.bat` mede CPU e disco do `googledrivefs` |

Para limitar a banda pelo chat:

```text
limita a banda do drive            → 1 MB/s de download e 0,5 MB/s de upload
limita o drive em 500              → 500 KB/s
reduz a banda do drive para 300 e 150   → 300 KB/s de download, 150 de upload
devolve a banda toda pro drive     → remove o limite
```

O valor vale **quando o app do Drive reiniciar** (feche pelo ícone da bandeja e
abra de novo). O comando grava só em `HKEY_CURRENT_USER`, sem pedir senha de
administrador. Para desfazer sem o chat: apague os dois valores em
`HKEY_CURRENT_USER\Software\Google\DriveFS` (ou rode `limita o drive em 0`).

## 3. Passo a passo

### Passo 1 — conferir o Drive

1. Clique no ícone do Drive na bandeja (perto do relógio).
2. Veja se aparece **"Sincronização pausada"**. Se estiver pausado, ótimo para
   começar: nada vai subir enquanto você mexe.
3. Clique na engrenagem → **Preferências** → **Google Drive** e confira a letra
   da unidade (normalmente `G:`) ou a pasta mostrada, algo como
   `C:\Users\SeuNome\Google Drive\Meu Drive`.

> Não tem o app instalado? Instale pelo site do Google Drive para desktop e
> entre com a sua conta. Sem o app, o JARVIS não tem como gravar na nuvem — o
> Drive da web não aparece como pasta no Windows.

### Passo 2 — rodar o atalho (duplo clique)

Na pasta do JARVIS existe **`usar-drive.bat`**. Duplo clique nele.

Ele faz quatro coisas, nesta ordem:

1. procura sozinho a pasta do Drive (`Google Drive`, `GoogleDrive`, `Drive`,
   `Meu Drive` e as letras `G:` a `Z:`);
2. cria `JARVIS-DADOS\biblioteca` e `JARVIS-DADOS\repos` dentro do Drive;
3. **copia** (não move) o que já existe, e confere arquivo por arquivo;
4. escreve duas linhas no `.env` apontando para lá:

```text
JARVIS_BIBLIOTECA=C:\Users\SeuNome\Google Drive\Meu Drive\JARVIS-DADOS\biblioteca
JARVIS_REPOS=C:\Users\SeuNome\Google Drive\Meu Drive\JARVIS-DADOS\repos
```

Se ele não achar a pasta, passe na mão:

```bat
usar-drive.bat "C:\Users\SeuNome\Google Drive\Meu Drive"
```

Nada é apagado nesse passo: a pasta antiga continua onde está.

### Passo 3 — reiniciar o JARVIS

Feche a janela do `iniciar.py` (Ctrl+C) e abra de novo. O `.env` só é lido na
subida.

### Passo 4 — conferir

1. Na interface, abra **Skills** e rode `armazenamento.status`
   (ou `dados.status`, se preferir pela linha de comando).
2. O retorno mostra `biblioteca`, `repositorios`, `drive_detectado` e a lista
   `no_drive`. As duas primeiras têm de apontar para dentro do Drive.
3. Importe um livro pequeno pela página Biblioteca e veja o arquivo aparecer em
   `JARVIS-DADOS\biblioteca\fontes` no Explorer.
4. Só depois disso apague as pastas antigas `storage\biblioteca` e
   `storage\repos`.

### Passo 5 — deixar o Drive leve

Estas quatro mudanças são o que realmente evita travar:

1. **Espelhar só a pasta do JARVIS.** No Drive, clique com o botão direito em
   `JARVIS-DADOS` → **Disponibilizar off-line** (ou *Fazer backup desta pasta*).
   O resto do Meu Drive pode ficar em *streaming*: nesse modo o arquivo só
   desce quando alguém abre, e o JARVIS abre o mesmo livro dezenas de vezes
   durante a indexação.
2. **Limitar a banda.** Preferências → **Google Drive** → *Limitar largura de
   banda*: 1.000 KB/s de download e 500 KB/s de upload. A sincronização deixa de
   competir com o disco em 13 MB/s.
3. **Pausar enquanto indexa.** Importar 200 PDFs gera 200 arquivos novos. Se a
   sincronização estiver ligada, o Drive sobe tudo isso enquanto a CPU já está
   ocupada com o OCR. Pause, importe, retome depois — ou importe um livro por
   vez.
4. **Não colocar lixo no Drive.** `node_modules` (dezenas de milhares de
   arquivos), `.venv`, `web-dist` e os `.cas` de jogos não vão para o Drive.

### Passo 6 — medir depois

Rode **`diagnostico-lento.bat`** antes e depois de uma importação. O relatório
mostra CPU e disco por processo (`googledrivefs` incluído). Se o Drive aparecer
abaixo de ~10% de CPU e o disco abaixo de 2 MB/s, está no ponto.

---

## 4. As variáveis, para quem quiser fazer na mão

No `.env` (sempre CRLF, sempre sem espaço em volta do `=`):

```text
JARVIS_BIBLIOTECA=D:\Drive\JARVIS-DADOS\biblioteca
JARVIS_REPOS=D:\Drive\JARVIS-DADOS\repos
# opcional: a pasta do Drive, para a detecção automática não procurar
JARVIS_DRIVE=D:\Drive
```

- `JARVIS_BIBLIOTECA` e `JARVIS_REPOS` valem **só** para essas duas pastas; o
  resto continua em `JARVIS_DADOS` (ou em `storage/`).
- Caminho relativo é resolvido a partir da pasta do projeto.
- `JARVIS_DRIVE` tem prioridade sobre a busca automática.
- Nada disso é lido da interface: são variáveis de ambiente, de propósito
  (chave e caminho não ficam no navegador).

---

## 5. Como desfazer

1. Feche o JARVIS.
2. Apague as três linhas acima do `.env` (ou deixe vazias).
3. Copie de volta o que estiver no Drive para `storage\biblioteca` e
   `storage\repos`.
4. Abra o JARVIS e rode `armazenamento.status`: os caminhos voltam para
   `storage\...`.

---

## 6. O que este desenho **não** resolve

- **Não deixa o sincronizador gratuito.** Enquanto o Drive estiver ligado, ele
  consome algo de CPU e disco. Reduzir, sim; zerar, só fechando o app.
- **Não transforma a nuvem em memória RAM.** O JARVIS continua lendo arquivo do
  disco; o Drive é só uma pasta que, por baixo, tem alguém sincronizando.
- **Não substitui cópia local para o que é lido muitas vezes.** Para livros
  grandes, "disponibilizar off-line" é obrigatório; senão cada leitura vira
  download.
- **Não protege contra o arquivo sumir no meio.** Se a sincronização pausar no
  meio de uma importação, o arquivo fica no PC e sobe depois — não se perde.
- **Não foi medido nesta máquina.** Os números citados vêm dos prints do
  Gerenciador de Tarefas do seu PC (Drive 33,2% CPU / 13,8 MB/s; Chrome
  ~1,5 GB). Um teste controlado, com o mesmo livro antes e depois, ainda não
  foi feito.

---

## 7. Checklist

- [ ] o app do Google Drive está instalado e com sessão iniciada;
- [ ] `usar-drive.bat` rodou sem erro de conferência;
- [ ] o JARVIS foi reiniciado depois de mexer no `.env`;
- [ ] `armazenamento.status` mostra as duas pastas dentro do Drive;
- [ ] um livro importado aparece em `JARVIS-DADOS\biblioteca\fontes`;
- [ ] a pasta `JARVIS-DADOS` está disponível off-line;
- [ ] a banda do Drive está limitada (`limita a banda do drive`);
- [ ] `diagnostico-lento.bat` mostra o Drive abaixo de 10% de CPU;
- [ ] as pastas antigas só foram apagadas depois do teste acima.
