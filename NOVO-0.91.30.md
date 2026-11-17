# JARVIS 0.91.30 — funcionou; agora ele prova

O seu print fechou o assunto: a chave foi criada **sem navegador**

    Chave criada: sk-or-…ae3e (73 caracteres)
    Gravado em D:\JARVIS\.env

Três segundos, sem página, sem espera. O caminho da chave de gestão ficou
guardado, então da próxima vez é ainda mais rápido.

## O que muda agora

**Gravado não é provado.** Antes, o programa dizia “está no `.env`” e ia embora.
Só que a próxima coisa que pode dar errado não é a chave — é a **conta**:

- se a sua conta é gratuita, ela só atende modelos terminados em **`:free`**;
- se o modelo do `.env` é pago, o JARVIS abre, aceita a chave, e erra na
  primeira resposta falando de “modelo”, longe da causa.

Agora, logo depois de gravar, o JARVIS pergunta ao OpenRouter o estado da chave
que ele mesmo criou (`GET /api/v1/key` — é leitura de conta, **não gasta
crédito**) e mostra na mesma tela:

     A chave respondeu — ela é válida.
     crédito restante: US$ 4.72 · usado: US$ 0.28

ou

     conta gratuita: só modelos terminados em :free

E, se a conta for gratuita e o modelo do `.env` for pago, ele avisa ali mesmo,
com o que fazer. Se o site não responder na hora da conferência, **nada é
apagado**: a chave já está no `.env` e o caminho é `conferir-ia.py --testar`.

## O que fazer agora

Você **não precisa** atualizar para usar a chave — ela já está funcionando.
Mas, antes de abrir o JARVIS, vale conferir se a conta e o modelo combinam:

```bat
cd /d D:\JARVIS
```

```bat
.venv\Scripts\python conferir-ia.py --testar
```

Ele diz, em três linhas, se a chave responde e se o modelo existe na sua conta —
e, se não existir, sugere os nomes certos. Se aparecer “conta gratuita” e o
modelo for pago, troque para um que termine em `:free`.

Depois disso, atualize (`atualizar.bat`) para a próxima chave já nascer
conferida.

## Testado

- a conferência lê `GET /key`, sem gastar crédito;
- falha da conferência **não** apaga a chave gravada;
- conta gratuita + modelo pago no `.env` → aviso com `:free` e o nome do
  script;
- conta gratuita + modelo `:free` → nenhum aviso (nada de barulho à toa).

Suíte: **3.847 testes**, 7 pulados.
