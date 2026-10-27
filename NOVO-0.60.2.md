# JARVIS 0.60.2 — achar e ligar o `.env` sem abrir o Bloco de Notas

Duas correções de usabilidade que só apareceram na máquina de verdade: o `.env`
não é fácil de achar, e o Bloco de Notas costuma salvá-lo com o nome errado.

## 1. `ligar-celular.bat` — um duplo clique

Novo atalho na raiz do projeto. Ele chama `configurar-celular.py`, que:

- acha o `.env` na raiz (o mesmo que `server/app.py` carrega com `load_dotenv`);
- **se não existir**, cria a partir do `.env.example`;
- ajusta `JARVIS_HOST_REDE=1` e `JARVIS_HOST_CELULAR=1` **substituindo** a linha
  se ela já estiver lá — sem duplicar chave, ao contrário de quem só dá `append`
  no fim do arquivo;
- grava em **UTF-8 sem BOM** e com **CRLF**, que é o que o resto do projeto usa;
- se achar um **`.env.txt`** perdido (o Bloco de Notas adora fazer isso quando
  você digita só `.env` no campo de nome), renomeia para `.env`;
- ignora comentário que cite a chave (`# JARVIS_HOST_REDE=0` continua comentário);
- mostra o **antes e o depois** de cada variável e não toca em nenhuma outra.

Exemplo de saída:

```text
  Gravado em: D:\JARVIS\.env

  antes:   JARVIS_HOST_REDE=0
  agora:   JARVIS_HOST_REDE=1

  antes:   (não existia)
  agora:   JARVIS_HOST_CELULAR=1
```

## 2. Por que o banner dizia `rede=desligada`

Não era bug: o `.env` não tinha as linhas. Como `load_dotenv` roda com
`override=False`, um valor já presente no ambiente do processo vence o arquivo —
mas num processo novo isso não acontece, então basta salvar o `.env` e reiniciar.
O banner (0.60.1) passou a mostrar `celular=ligado/desligado`, o que dá o teste em
uma linha.

## Como atualizar

Duplo clique em **`atualizar.bat`** (ele sabe que a instalação é por zip).
Depois:

```bat
ligar-celular.bat
```

E, na janela da API: **Ctrl+C** → `.venv\Scripts\python iniciar.py`.

Banner esperado:

```text
(rede=ligada, instalar=desligado, root=desligado, pc=desligado, celular=ligado, dono=desligado)
```

## Testes

- `pytest server/tests` → **2.656 passed** (6 novos: troca sem duplicar,
  acréscimo, comentário ignorado, idempotência, CRLF sem BOM e leitura com BOM).
- `vitest` 117, `tsc` limpo, build embutido ok.

### Arquivos

- `configurar-celular.py` — ajuste do `.env`, com funções puras e testáveis.
- `ligar-celular.bat` — atalho de duplo clique (ASCII puro, CRLF).
- `server/tests/test_celular.py` — os seis testes novos.
- `README.md` e `docs/CELULAR-LINUX.md` — como ligar sem errar o arquivo.
