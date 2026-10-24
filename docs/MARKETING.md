# Marketing mensurável

Calcular o funil, dimensionar o teste, limpar a URL de campanha, revisar o e-mail, auditar a página e conferir o anúncio. A camada parte de [`coreyhaines31/marketingskills`](https://github.com/coreyhaines31/marketingskills) — **MIT** —, mas o que entra aqui é só a parte **verificável**: nenhum texto de copy, nenhum criativo e nenhuma skill de redação do upstream foram portados. O JARVIS mede; não escreve anúncio.

| Camada | O que faz | Toca a rede? |
|---|---|---|
| **Motor** (`server/marketing.py`, 7 skills) | Faz a conta do funil, da amostra e do payback, confere URL, e-mail, HTML e peça de anúncio | **Não** — tudo é número ou texto que você cola |
| **Página** (`/marketing`) | Formulário por verbo, métricas, a conta aberta, achados e o parecer para copiar | Não |

O módulo reaproveita `server/review.py`: mesmos grupos (`must`, `should`, `nice`), mesmas contagens, veredito e Markdown. O resultado é determinístico — mesma entrada, mesmo parecer — e nenhuma skill grava arquivo, abre conta de anúncio ou lê pixel.

---

## As sete skills

| Rota | Entrada | O que devolve |
|---|---|---|
| `marketing.orcamento` | orçamento, CPM, CTR, conversão, fechamento, ticket, margem | impressões, cliques, leads, clientes, CAC, ROAS, payback, LTV/CAC e alavanca para o CAC alvo |
| `marketing.teste` | linha de base, MDE, tráfego/dia, variantes, alfa, poder | amostra por variante, total, duração em dias, alfa ajustado e viabilidade |
| `marketing.utm` | URLs de campanha, uma por linha | URL canônica, situação e achado por parâmetro |
| `marketing.email` | assunto, pré-cabeçalho, corpo, CTA, tipo e HTML opcional | tamanho de cada campo, links, marcas de texto gerado e achados |
| `marketing.seo` | HTML da página, palavra-chave e URL | título, description, hierarquia, alt, canonical, idioma, JSON-LD e links |
| `marketing.anuncio` | plataforma, títulos, descrições, texto principal e URL final | caractere por peça contra o limite, mínimo e máximo de peças |
| `marketing.regras` | nada | limites por plataforma, vocabulário de `medium`, faixas, fórmulas, grade de amostra e rubrica |

Todos aceitam `modo` com `lite`, `full` (padrão) ou `ultra`. `lite` devolve só o que bloqueia, `full` inclui as correções e `ultra` inclui as perguntas que faltam para decidir.

---

## 1. Orçamento e economia unitária

A conta é linear, do investimento ao cliente:

| Etapa | Fórmula |
|---|---|
| Impressões | `orçamento ÷ CPM × 1000` |
| Cliques | `impressões × CTR` |
| Leads | `cliques × conversão` |
| Clientes | `leads × fechamento` |
| CAC | `orçamento ÷ clientes` |
| Receita | `clientes × ticket` |
| ROAS | `receita ÷ investimento` |
| Payback | `CAC ÷ (ticket × margem)` |
| LTV | `ticket × margem × vida útil` |
| LTV/CAC | `LTV ÷ CAC` |

Com 30.000 de orçamento, CPM 28, CTR 1,8%, conversão 6%, fechamento 22%, ticket 199, margem 78% e 18 meses de vida útil: 1.071.428,57 impressões, 19.285,71 cliques, 1.157,14 leads, 254,571 clientes, CAC de 117,85, receita de 50.659,71, ROAS de 1,689, LTV de 2.793,96, LTV/CAC de 23,709 e payback de 0,76 mês. Nenhum número é benchmark: as taxas são as que você informa.

**Faixas de sanidade.** CTR acima de 10% e conversão acima de 60% são tratados como erro de medição, não como bom desempenho. LTV/CAC saudável começa em 3×; payback acima de 12 meses é caixa preso; margem abaixo de 30% deixa pouca folga para CAC. `modelo: "unica"` troca a leitura do payback de meses para vendas e dispensa a vida útil.

**CAC alvo.** Com `cac_alvo`, o parecer calcula quanto cada alavanca — CPM, CTR, conversão, fechamento, ticket, margem — precisaria mudar para o funil chegar lá. Quando o CAC atual está acima do alvo, o achado `cac-alvo-distante` mostra a distância; a tabela de sensibilidade diz o quanto cada alavanca precisaria subir.

**Meta de ARR.** Com `meta_arr`, `arpc` e `retencao_anual`, o orçamento por meta usa `(ARR ÷ (ARPC × 12) × CAC) ÷ retenção anual`. Sem os três, a seção não aparece — e o achado `meta-sem-verba` aponta a falta.

---

## 2. Dimensionar teste A/B

Duas proporções, dois lados, amostras iguais:

```
n = ((z_α√(2p̄(1−p̄)) + z_β√(p1(1−p1) + p2(1−p2)))²) ÷ (p2−p1)²
duração = (n × variantes) ÷ (tráfego diário × exposição)
```

| Situação | Resultado |
|---|---|
| Linha de base 10%, MDE 20%, 5.000 por dia | ~3.800 por variante, 2 dias — sobe para o mínimo de 7 |
| Linha de base 3%, MDE 20%, 4.000 por dia, poder 80% | 13.914 por variante, 27.828 no total, 9 dias → `curto-demais` (B2B exige 14) |
| Linha de base 3%, 120 por dia, poder 50% | 843 por variante, `viavel: False` + `inviavel` |
| 4 variantes | alfa ajustado para 0,01667 e amostra maior, com `muitas-variantes` |

O mínimo é uma semana para B2C e duas para B2B, porque o ciclo de compra não cabe em três dias. O máximo padrão é 56 dias (`duracao_maxima`): além disso o teste pega sazonalidade e fadiga de criativo em vez do efeito. A duração é sempre arredondada para cima, e o achado `curto-demais` diz quantos dias faltam. O `alfa` é corrigido por Bonferroni quando há mais de duas variantes — o valor devolvido é o que vale para cada comparação.

---

## 3. Higiene de campanha

Cada URL é lida, conferida e reconstruída. As regras e o achado que cada uma gera:

| Regra | Achado |
|---|---|
| `https://`, sem espaço nem metacaractere | `sem-esquema`, `http`, `espaco` |
| `utm_source`, `utm_medium` e `utm_campaign` presentes | `sem-utm`, `utm-incompleta` |
| `utm_medium` no vocabulário declarado | `medium-novo` |
| tudo em minúsculas | `maiuscula` |
| hífen no lugar de espaço, `_`, `%20` ou acento | `separador` |
| nenhum parâmetro repetido na mesma URL | `chave-repetida` |
| nenhuma URL repetida na lista | `duplicada` |
| `utm_source` é o nome do veículo, não um domínio | `origem-dominio` |
| sem fragmento (`#`) numa URL de campanha | `fragmento` |
| sem encurtador (`bit.ly`, `t.co`, `goo.gl`…) | `encurtador` |
| valor curto o bastante para o relatório | `valor-longo` |
| nada de e-mail ou telefone na URL | `pii-email`, `pii-telefone` |
| `utm_content` presente quando o parâmetro separa a peça | `sem-content` |

Vocabulário de `medium`: `cpc`, `ppc`, `paid-social`, `display`, `email`, `newsletter`, `social`, `organic-social`, `creator`, `podcast`, `affiliate`, `community`, `referral`, `event`, `print`, `video`, `retargeting`, `influencer`, `partner`, `qr`, `direct`.

**Padrões por tipo de colocação.** O parecer sugere a grafia da casa: newsletter `{parceiro}/{publicacao}-{aaaa}-{mm}`, creator `{plataforma}/{criador}/creator`, podcast `{podcast}/podcast/{spot}-{aaaa-mm-dd}`, afiliado `{parceiro}/affiliate`, comunidade `{comunidade}/community`. Uma colocação, um link: dois `utm_content` diferentes na mesma peça dividem o crédito.

A URL canônica volta normalizada — minúsculas, hífen, parâmetros na ordem canônica e porta preservada. É essa string que deve ir para o painel, não a original.

---

## 4. E-mail antes do disparo

| Campo | Leitura | Achado |
|---|---|---|
| Assunto | 40–60 caracteres; acima de 80 é corte garantido | `assunto-fora-da-faixa`, `assunto-longo` (must) |
| Pré-cabeçalho | 90–140 caracteres, sem repetir o assunto | `preview-fora-da-faixa`, `preview-repete`, `sem-preview` |
| Corpo | uma ideia por parágrafo; CTA explícito | `paragrafo-longo`, `frase-longa`, `sem-cta`, `longo` |
| Descadastro | obrigatório no HTML de toda lista | `sem-descadastro` (must) |
| Personalização | primeiro nome ou dado declarado | `sem-personalizacao` |
| Assunto | sem `Re:`/`Fwd:` falso, sem caixa alta, sem emoji | `assunto-falso`, `assunto-caixa-alta`, `emoji-assunto` |
| Filtro | caixa alta, `!!!`, “grátis”, “urgente” | `spam`, `exclamacao`, `isca` |
| Links | poucos, todos com destino declarado | `muitos-links` |

**Marcas de texto gerado.** O módulo não julga estilo: aponta os tiques que o leitor sente mesmo sem nomear.

- contraste de negação — “não é X, é Y” (`tell-contraste`);
- lista de negações em sequência (`lista-de-negacao`);
- travessão longo como pausa dramática no assunto ou no pré-cabeçalho (`travessao-assunto`, `travessao-preview`);
- abertura genérica — “Espero que esteja bem”, “No mundo de hoje” (`abertura-generica`).

Cada marca é um `should` com o trecho e a reescrita. `cold` (primeiro contato) e `lifecycle` (lista) mudam o peso da abertura e da personalização.

---

## 5. SEO on-page

O módulo lê o HTML entregue — sem executar JavaScript — e confere o que a página declara:

| Elemento | Faixa / regra | Achado |
|---|---|---|
| `<title>` | até 65 caracteres; 50–60 é o alvo | `title-longo` (must), `title-curto` (< 25) |
| `meta description` | 120–170 aceitável; 150–160 é o alvo | `sem-description` (must), `description-fora-da-faixa` |
| `<h1>` | exatamente um, com a palavra-chave | `sem-h1`, `h1-repetido`, `chave-fora-do-h1` |
| Palavra-chave | presente no `title` | `chave-fora-do-title` |
| Hierarquia | sem salto de nível | `salto-de-nivel` |
| Imagem | `alt` descritivo, largura e altura declaradas | `img-sem-alt`, `alt-generico`, `sem-dimensao` |
| Canonical | autorreferente e em `https://` | `sem-canonical`, `canonical-cruzado` |
| Idioma | `lang` declarado; `en-GB`, nunca `en-UK` | `sem-lang` |
| JSON-LD | válido e com `@context` | `sem-jsonld`, `jsonld-invalido` |
| Links | interno no site; externo para fonte da afirmação | `sem-link-interno`, `sem-fonte`, `muitas-ancoras` |
| Texto | 300 palavras no mínimo | `conteudo-curto` |

**Sinais para motor de resposta.** O bloco de AEO olha o que um motor generativo extrai: abertura que responde a pergunta do título em menos de 110 palavras (`sem-resposta-direta`), subtítulo em forma de pergunta (`sem-pergunta`), texto com ano declarado (`sem-data`) e cada afirmação com fonte (`sem-fonte`). O parágrafo de abertura é lido sem os subtítulos e sem o bloco imediatamente posterior ao `h1`, para não confundir sumário com resposta.

---

## 6. Anúncio dentro do limite

| Plataforma | Campo | Limite | Peças |
|---|---|---|---|
| Google — responsivo de pesquisa | Título | 30 | 3–15 |
| Google — responsivo de pesquisa | Descrição | 90 | 2–4 |
| Meta — feed | Texto principal | 125 (Stories e Reels < 72) | 1 |
| Meta — feed | Título | 40 | 1 |
| Meta — feed | Descrição | 30 | 0–1 |
| LinkedIn — feed | Introdução | 150 | 1 |
| LinkedIn — feed | Título | 70 | 1 |
| LinkedIn — feed | Descrição | 100 | 0–1 |

O Google combina até três títulos e duas descrições, e qualquer um pode aparecer em qualquer posição: cada peça precisa fazer sentido sozinha. O parecer conta caractere por peça e aponta `{campo}-longo`, `{campo}-faltando`, `{campo}-excesso`, `{campo}-repetido`, `{campo}-caixa-alta`, `{campo}-pontuacao` e `{campo}-emoji`, com `campo` em `titulos`, `descricoes` ou `texto_principal`. Na URL final: `url` (sem `https`), `sem-parametro` (sem `utm_`, `gclid` ou `fbclid`) e `sem-url`.

Afirmação não verificável vira achado — `claim-melhor-da-categoria`, `claim-numero-um` e `claim-garantia`; “número 1” e “garantido” são `must`. Anúncio pago precisa de fato: número, prazo, condição.

---

## 7. O catálogo de regras

`marketing.regras` devolve o que o motor usa, para que a regra não fique escondida no código: os limites por plataforma, o vocabulário de `medium`, as faixas de sanidade, as dez fórmulas, a grade de amostra calculada na hora (linha de base 1/3/5/10% × ganho de 10/20/50%) e a **rubrica de integridade da recomendação** — seis regras que valem para qualquer texto que recomende ferramenta: opções reais ao lado, menção no ponto da escolha, sem empurrão, fatos verificáveis, interesse declarado e o teste da troca. Se a ferramenta citada fosse trocada por uma concorrente, o texto continuaria justo? Se não, é publicidade.

---

## O que ficou de fora

As 52 skills de redação do upstream — copy, criativo, plano de marketing, PR, social, pricing narrativo — **não foram portadas**. O JARVIS não escreve anúncio, não escolhe posicionamento e não promete resultado: ele mede o que já existe e aponta o que quebra a conta. Nenhum texto do repositório original foi copiado; as contas e as conferências foram implementadas em Python a partir das fórmulas públicas. Nenhuma conta de anúncio, pixel, CRM ou ferramenta de análise é acessada.

## Atribuição

Código e documentação do upstream sob licença MIT, `Copyright (c) 2025 Corey Haines`. O texto integral está em [`docs/licenses/coreyhaines31-marketingskills.txt`](licenses/coreyhaines31-marketingskills.txt).

## Contrato

Toda resposta traz `executed: false`, `executado: false` e `readOnly: true`; o `analysis` é prefixado com `marketing.` e o `mode` é herdado do `review`. As `limitations` declaram o que a conta não cobre — mídia paga sem salário nem ferramenta no CAC, funil linear sem saturação, e as demais premissas de cada análise.
