# 0.49.0 — o que mudou para você

## 1. Pesquisar não pede mais token

Antes: `Para buscar na web eu preciso do token de host...`
Agora: só precisa da API ligada com a rede liberada.

```text
pesquisa no youtube sobre python
procura na wikipedia sobre cafe
busca na web sobre gatos
pesquisa no google sobre impostos
```

As fontes (sem chave, sem cadastro): **DuckDuckGo**, **Wikipédia** e **YouTube**.
Sem dizer a fonte, ele usa as três e mostra `[fonte]` em cada resultado.
Se uma cair, as outras continuam.

**Token continua valendo para o que grava ou executa:** baixar, importar,
instalar e rodar. Só isso.

## 2. Mouse e teclado (você autorizou)

```text
onde esta o mouse
clica em 500 300
duplo clique em 40 50 com o botao direito
move o mouse para 800 600
digita ola mundo
aperta ctrl v
foca a janela do bloco de notas
```

Toda ação que mexe no cursor pede **“sim, pode”** antes.
Se você mexer o mouse no meio do movimento, ele **para na hora**.
Não há captura de tela nem OCR: ele vai para a coordenada que você mandou.

## 3. Como atualizar

1. Feche o JARVIS (Ctrl+C na janela do CMD).
2. Baixe o zip novo:
   https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre
3. Extraia por cima de `D:\JARVIS` (substituir arquivos).
4. Não precisa `pip install`: a 0.49.0 não trouxe dependência nova.
5. Suba com rede liberada:

```bat
cd /d D:\JARVIS
set JARVIS_HOST_REDE=1
.venv\Scripts\python iniciar.py
```

6. Confira: `http://127.0.0.1:8000/api/health` deve mostrar
   `"version": "0.49.0"` e `"skills": 237`.

## 4. Números

- 237 skills (6 novas: mesa.status, mesa.mover, mesa.clicar, mesa.digitar, mesa.teclar, mesa.focar).
- 2.288 testes na suíte Python (2288 passed), 110 testes da interface.
- Zero dependência nova: mouse/teclado por `ctypes`, busca por HTTP puro.
