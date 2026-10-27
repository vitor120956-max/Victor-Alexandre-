# JARVIS 0.60.3 — o scrcpy baixado agora é encontrado (e o token sai do caminho)

Duas coisas que só apareceriam na primeira tentativa de verdade.

## 1. O bug do layout do zip

O `celular.preparar` baixava certo e extraía certo — e depois dizia que o `scrcpy`
**não estava instalado**. Motivo: o zip oficial do scrcpy extrai numa pasta com a
versão no nome:

```text
storage\ferramentas\scrcpy-win64-v3.3.1\scrcpy.exe
```

E o código procurava em `storage\ferramentas\scrcpy\scrcpy.exe`. O download era um
sucesso; o relatório dizia falha.

Agora:

- `normalizar()` renomeia a pasta extraída para o nome canônico
  (`ferramentas\scrcpy\`), preservando o conteúdo;
- `_achar()` ganhou um passo recursivo como rede de segurança — se alguém baixar
  na mão e descompactar com outro nome, ele acha do mesmo jeito, preferindo sempre
  o caminho canônico.

O teste `test_preparar_deixa_o_layout_que_as_skills_enxergam` monta os dois zips
com o layout real e exige que `ferramentas()` termine dizendo `completo: true`.

## 2. O modo dono entra no atalho

`ligar-celular.bat` agora ajusta **três** variáveis:

| Variável | Para quê |
|---|---|
| `JARVIS_HOST_REDE=1` | baixar o `adb` e o `scrcpy` é download |
| `JARVIS_HOST_CELULAR=1` | liga as cinco skills `celular.*` |
| `JARVIS_HOST_CONFIAR_LOCAL=1` | **modo dono**: na própria máquina não se digita token |

A terceira é o que tira o campo de token da frente. Sem ela, o `celular.preparar`
pediria o token de host, porque baixar é efeito colateral. Com ela, o servidor
preenche sozinho **quando a requisição vem de `127.0.0.1`** — de outra máquina da
rede o token continua sendo exigido. Para desligar, troque `=1` por `=0` e
reinicie; o banner mostra `dono=LIGADO` enquanto estiver ativo.

## Como atualizar

Duplo clique em **`atualizar.bat`**. Depois:

```bat
ligar-celular.bat
```

E na janela da API: **Ctrl+C** → `.venv\Scripts\python iniciar.py`.

Banner esperado:

```text
(rede=ligada, instalar=desligado, root=desligado, pc=desligado, celular=ligado, dono=LIGADO (sem digitar token nesta máquina))
```

## Depois disso

No chat:

```text
baixa o adb e o scrcpy
```

Sem token, sem senha: confirma e ele baixa. Ao final, o resumo mostra o SHA-256 de
cada arquivo e o caminho dos dois executáveis:

```text
storage\ferramentas\platform-tools\adb.exe
storage\ferramentas\scrcpy\scrcpy.exe
```

E então, com o celular no cabo:

```text
meu celular não tem tela, dá para usar?
```

## Testes

- `pytest server/tests` → **2.662 passed** (6 novos: pasta com versão, preferência
  pelo caminho canônico, renomeação, no-op quando já está certo, layout final do
  preparo e o modo dono no configurador).
- `vitest` 117, `tsc` limpo, build embutido ok.

### Arquivos

- `server/celular.py` — `normalizar()` e busca recursiva em `_achar()`.
- `configurar-celular.py` — terceira variável, com explicação no output.
- `server/tests/test_celular.py` — os seis testes novos.
- `README.md` e `docs/CELULAR-LINUX.md` — o atalho e o layout das pastas.
