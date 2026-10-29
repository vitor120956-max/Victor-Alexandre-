# JARVIS 0.61.1 — "API offline" com a API de pé

Você pediu `status do celular` e recebeu:

```
A API Python está offline e nenhum provedor externo foi chamado. Posso continuar
com tarefas, notas, cálculos, foco, automações, legislação, documentos,...
```

Três problemas nessa resposta:

1. ela não diz **o que fazer** — lista capacidades em vez de dizer "suba o
   servidor, aqui está o comando";
2. o comando que o app ensinava, em outros lugares, era **`npm run dev`** — que
   não existe numa instalação por zip (não há Node em `D:\JARVIS`);
3. se a API subisse depois, a tela só percebia em até **60 segundos**.

## O que mudou

**A saúde decide sozinha.** Antes, o app pedia três coisas de uma vez
(`/api/health`, catálogo de skills e status da IA) e **qualquer erro em qualquer
uma** marcava a API inteira como offline — inclusive uma falha só do catálogo.
Agora `/api/health` manda: respondeu, a API está de pé; o resto é complemento.

**Reconexão em 3 segundos.** Com a API de pé, confere a cada 30 s. Caída, tenta
a cada 3 s e volta sozinha, sem recarregar a página.

**A mensagem ensina o comando certo:**

```
A API Python não respondeu em http://127.0.0.1:8000 — nada foi executado.

Para subir, nesta ordem:
  cd /d D:\JARVIS
  .venv\Scripts\python iniciar.py

Quando ela voltar, esta tela reconecta sozinha em até 3 segundos: basta
repetir o pedido.
```

E as **47** ocorrências de `npm run dev` espalhadas pela interface (31 arquivos)
viraram o comando de verdade. Havia páginas inteiras mandando rodar algo que não
existe na sua instalação.

## No `iniciar.py`

**Banner duplicado, resolvido.** O `iniciar.py` importava o servidor só para
descobrir a pasta da interface; esse import já criava a API uma vez, e o uvicorn
criava de novo. Agora ele olha a pasta sozinho e usa a instância que o módulo já
tem — um banner, metade do trabalho de subida (num pendrive, isso conta).

**Porta ocupada agora explica:**

```
  A porta 8000 está ocupada por outro programa (não é o JARVIS).
  Suba em outra porta:  .venv\Scripts\python iniciar.py --porta 8001
```

**E "já está rodando" também:**

```
  Já existe uma API respondendo em http://127.0.0.1:8000
  Não precisa subir outra: abra o endereço no navegador.
```

Antes, os dois casos viravam o mesmo erro de socket do uvicorn.

## Como testar

1. Feche a janela da API no **X** (se estiver aberta).
2. Atualize:

```bat
cd /d D:\JARVIS
```

```bat
atualizar.bat
```

3. Suba de novo:

```bat
cd /d D:\JARVIS
```

```bat
.venv\Scripts\python iniciar.py
```

O banner deve aparecer **uma vez** agora. Se a interface estiver aberta, ela
reconecta sozinha em até 3 segundos.

Se `iniciar.py` reclamar de porta ocupada, é sinal de que outra janela da API
ficou aberta: feche-a no X e rode de novo.

## Testes

- `pytest server/tests` → **2.722 passed**.
- `server/tests/test_iniciar.py` → **7** novos: usa a instância (não a factory),
  não importa `server.app` antes do uvicorn, porta ocupada sai com código 1 e
  explica, JARVIS já rodando sai com 0 e avisa, nenhum `npm run dev` no front, e
  a mensagem de offline traz o comando certo.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
