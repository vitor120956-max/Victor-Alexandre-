# JARVIS 0.82.0 — ele passa a ver o que há dentro da janela

Esta versão tem duas partes: o JARVIS **lê** os elementos da janela (sem clicar),
e você pode **ligar conectores** colando a chave que o próprio serviço te dá.

## 1. `mesa.arvore` — ver os botões, não só o título

Antes o JARVIS sabia que existia uma janela chamada “Cadastro de cliente”. Agora
ele lê a **árvore de acessibilidade** dela:

```
janela “Cadastro de cliente”
  painel
    botão “Salvar”              @a1b2c3d4:e3
    botão “Cancelar”            @a1b2c3d4:e4
    caixa de seleção “Aceito”   @a1b2c3d4:e6
```

Pergunte no chat:

```
vê os elementos da janela
lê a janela do chrome
o que dá para clicar no bloco de notas
```

- **só leitura**: não clica, não digita, não move o mouse, não tira foto;
- **não trava o JARVIS**: a leitura roda numa **sonda separada** (`arvore_sonda.py`);
  se o programa alvo travar, cai a sonda e não a API;
- **não finge**: o que foi cortado vem marcado (`completo: false`), papel
  desconhecido não ganha nome inventado, e fora do Windows ele recusa com frase
  clara em vez de devolver vazio;
- **ref** só aparece no que dá para acionar, e vale **só** para aquela leitura —
  se a tela mudar, o ref antigo não serve mais.

Clicar por `ref` é a **etapa 2**, e só entra depois que você rodar isto aí e me
disser o que apareceu. O teste de agora é o Bloco de Notas:

```
cd /d D:\JARVIS
.venv\Scripts\python arvore_sonda.py
```

## 2. Conectores por token — Notion, Linear, Dropbox, Vercel, Supabase

Em **Configurações → Conectores → Serviços com token pessoal**:

- **Colar token** → **Guardar token** → **Testar**;
- o **Teste** é uma leitura de verdade e diz o nome da conta/workspace;
- o token **nunca** volta na tela nem numa resposta (só `secr…cdef`);
- **Esquecer** apaga só aquela chave do `.env`.

Onde pegar cada chave está em `docs/CONECTORES.md` (tabela nova no fim).

## O que **não** entrou, e por quê

- **Clicar por `ref`**: depende de medir quais programas publicam árvore no seu
  PC. Prometer isso antes da medição seria repetir o erro de versões anteriores.
- **Gmail/Drive/Agenda por OAuth**: exige que **você** crie um projeto no Google
  Cloud. O Gmail já funciona por IMAP; o resto fica para quando você quiser.
- **WhatsApp**: não existe API para conta pessoal — segue como está.
- **Ações dentro dos conectores** (criar página no Notion, tarefa no Linear…):
  a porta está ligada e testada; as ações entram na próxima, começando pelo
  serviço que você disser que usa mais.

## Para atualizar

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

Se algo parecer a versão antiga:

```
conferir-versao.bat
```

Ele diz a versão real do código, a que o servidor está rodando e se há arquivo
fora do manifesto.
