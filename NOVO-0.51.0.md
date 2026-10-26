# 0.51.0 — correio e lista de 100 skills

## 1. “Mando a lista de 100 skills para ele ou para você?”

**Manda para mim** os links — eu transformo em código de verdade quando a skill
dá para virar código (conferência, regra, cálculo) e descarto o que é só prosa.

**Para ele** também funciona: basta colar os links no chat.

```text
importa estas habilidades:
https://github.com/vercel-labs/agent-skills/tree/main/skills/react-best-practices
https://github.com/anthropics/skills/tree/main/skills/frontend-design
https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs
```

Limites que eu não escondo:

- **até 20 links por chamada** (o resto volta como “sobrou N; mande em outra leva”);
- o GitHub público aceita **60 pedidos por hora** sem token — 100 links de uma vez
  vão bater nesse teto. Faça em levas de 10–15;
- **o que ele guarda é o texto** da skill. Sem modelo, é roteiro, não raciocínio.

## 2. Gmail: o que é possível e o que não é

**“Entrar no meu Gmail” não é possível sem credencial.** Ler a caixa em tempo real
exige OAuth do Google — é uma chave, e o projeto é sem chave por decisão sua.

O que existe agora, **sem chave nenhuma**: você exporta e ele lê o arquivo.

### Como exportar

- **Uma mensagem:** Gmail → menu ⋮ → **Baixar mensagem** (`.eml`).
- **A caixa toda:** [takeout.google.com](https://takeout.google.com) → só **Mail**,
  com “incluir todos os rótulos” → o `.zip` traz um `.mbox`.

Ponha o arquivo em `D:\JARVIS\storage\correio`.

### O que ele faz com isso

```text
filtra meus e-mails por importância
```

Resultado real do teste que eu fiz aqui:

```text
Triagem de 3 mensagem(ns): 2 urgente(s).

[100] Intimação / processo — Intimação — processo nº 0001234
    de contato@tjsc.jus.br
[95] Fatura / boleto — Sua fatura de outubro
    de financeiro@energia.com.br — vence 2026-10-30 (em 4 dia(s))
[45] Pessoal — Re: reunião

Por categoria — Pessoal: 1, Fatura / boleto: 1, Intimação / processo: 1.

Nada foi aberto no Gmail: isto é o que você exportou em storage/correio.
```

A regra, em ordem: **intimação/processo 100** · **fatura 85** (+10 se vence em até
7 dias) · **governo 75** · **segurança 70** · **pessoal 45** · **newsletter 5**.
Nada de modelo: são listas de termos em português.

### Os padrões do que você escreve

```text
analisa meus e-mails enviados
```

```text
Seu jeito de escrever (medido em 1 e-mail(s) enviado(s)):

• Saudação mais comum: olá
• Fecho mais comum: abraços
• Assinatura: Victor
• Tamanho: média de 10.0 palavras (mediana 10)
• Usa lista com marcadores: 100% das mensagens
```

Só entram as **enviadas** (rótulo `Sent`/`Enviados`).

### Escrever no seu estilo

```text
escreve um e-mail para a Ana sobre o relatório: enviar planilha; pedir retorno
```

```text
Para: Ana
Assunto: relatório

Olá,

Sobre o assunto “relatório”:

- enviar planilha
- pedir retorno

Abraços,
Victor
```

**Ele não envia e não abre o Gmail.** É texto para você revisar e colar.

## O que continua fora

1. Ler a caixa em tempo real (OAuth), marcar como lido, arquivar, apagar.
2. Enviar e-mail pelo JARVIS.
3. Usar Copilot ou qualquer serviço de assinatura.
4. Gerar imagem por IA.

O caminho para (1) e (2) já existe em outra camada: `escritorio.*` monta os
comandos do `gws` — mas quem autentica e executa é você, com a sua credencial.

## Números

- **250 skills** (5 novas: `correio.arquivos`, `correio.triar`, `correio.padroes`,
  `correio.rascunho` e `habilidades.importar-varias`).
- **2.367 testes** Python + **110** da interface, todos passando.
- Testado de verdade: triagem, padrões e rascunho rodaram nesta máquina com
  `.eml` reais montados no teste.

## Atualizar no seu PC

1. Feche o JARVIS (Ctrl+C).
2. Baixe:
   `https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre`
3. Extraia por cima de `D:\JARVIS`. Sem `pip install` — nenhuma dependência nova.
4. Suba:

```bat
cd /d D:\JARVIS
set JARVIS_HOST_REDE=1
.venv\Scripts\python iniciar.py
```

5. `http://127.0.0.1:8000/api/health` → `"version": "0.51.0"` e `"skills": 250`.

Detalhes em `docs/CORREIO.md` e `docs/HABILIDADES.md`.
