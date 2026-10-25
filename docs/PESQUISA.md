# Pesquisar e ler a web

Resposta curta para a pergunta mais comum: **o JARVIS consegue usar a web para responder?**

| O que você quer | Existe hoje? | Onde |
|---|---|---|
| Abrir uma busca no navegador | sim | chat: `pesquisar por X` |
| Buscar na web de dentro do JARVIS | sim | skill `sistema.rede`, ação `buscar` |
| Ler o texto de uma página | sim | skill `sistema.rede`, ação `olhar` |
| **Redigir a resposta a partir do que leu** | **não** | falta ligar as duas pontas |

Ou seja: as peças existem separadas. O que não existe é o fluxo "pesquise, leia e me responda" automático.

## O que o chat faz

```text
pesquisar por Machado de Assis
```

Isso **abre o Google numa aba nova**. O JARVIS não lê os resultados e não responde: é um atalho de navegador. Sem chave de IA, perguntas abertas ("quem foi Machado de Assis") caem na mensagem de IA não configurada.

## O que a skill faz

A skill **Busca e leitura na web** (`sistema.rede`) tem duas ações:

| Ação | O que devolve |
|---|---|
| `buscar` | título e link de até 25 resultados do **DuckDuckGo** (não do Google), sem resumo |
| `olhar` | o texto extraído da página informada, até **20.000 caracteres**, com status e tipo |

Medido nesta máquina, `olhar` numa página do GitHub devolveu **4 linhas de metadados** (url, status, tipo, caracteres) mais o texto raspado. A busca usa a página HTML do DuckDuckGo e depende de ela responder sem captcha — por isso ela pode voltar vazia mesmo com internet boa.

## As três travas

A skill não liga sozinha, e é de propósito:

1. **Rede desligada por padrão.** A API precisa subir com `JARVIS_HOST_REDE=1`.
2. **Token de host.** O valor está em `storage/host-token.txt` e vai no campo `autorizacao`.
3. **Endereço privado é recusado.** `localhost`, `192.168.x.x`, `10.x.x.x` e link-local são bloqueados — sem isso, uma skill poderia ler a sua rede interna.

## Passo a passo

1. Suba a API com a rede ligada:

```bat
cd /d D:\JARVIS
set JARVIS_HOST_REDE=1
.venv\Scripts\python iniciar.py
```

2. Abra `D:\JARVIS\storage\host-token.txt` no Bloco de Notas e copie a linha. O terminal também mostra os 4 primeiros e os 4 últimos caracteres.

3. Na interface, abra **Skills → Busca e leitura na web**.

4. Ação `buscar`, consulta `Machado de Assis`, limite 8. Cole o token e execute. Você recebe uma tabela de títulos e links.

5. Para ler uma das páginas: ação `olhar`, cole o link no campo `url`. Você recebe o texto extraído.

Não há resumo: o que vem é o texto da página, truncado. Quem interpreta é você.

## O que mudaria com uma IA configurada

Com chave, o JARVIS **responde** perguntas abertas — mas com o conhecimento que o modelo já tem, **não** com o resultado de uma busca feita agora.

O canal para isso já existe: o campo `material` da requisição de IA aceita até 60.000 caracteres de texto do usuário e o envia como dado citável, nunca como instrução. Hoje, porém, **nada alimenta esse canal com resultado de busca**. Ligar as duas pontas é um trabalho de integração, não uma configuração.

Enquanto isso não existe, a divisão é esta:

| Sem chave | Com chave |
|---|---|
| a skill **encontra** e **lê** | a IA **explica** |
| você interpreta | a IA interpreta, sem citar fonte |
| nada sai da sua máquina (fora a busca e a página) | a pergunta vai ao provedor |

## Limites que precisam ficar ditos

- **DuckDuckGo, não Google.** O Google bloqueia esse tipo de acesso; o DuckDuckGo aguenta, mas muda a marcação da página de vez em quando e a busca passa a voltar vazia.
- **Sem resumo automático.** Texto bruto, truncado em 20 mil caracteres.
- **Resultado vazio não prova que o assunto não existe.** Pode ser bloqueio, captcha ou marcação nova.
- **Nada é gravado.** A skill não salva arquivo; quem baixa é `sistema.baixar`, e só para a quarentena.
