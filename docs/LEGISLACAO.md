# Skill de legislação brasileira

## Escopo

O JARVIS inclui um recorte local inspirado em [`ctresb/leis`](https://github.com/ctresb/leis), fixado no commit registrado em `server/legal_data/index.json`. Não é um clone do acervo completo.

O recorte atual indexa **4.427 artigos** em oito documentos: Constituição Federal, Código Civil, Código Penal, CLT, ECA, CDC, LGPD e Marco Civil da Internet.

Os textos são usados para pesquisa informativa. Conversões, OCR, lacunas e alterações legislativas podem gerar divergências. O JARVIS sempre orienta conferir texto e vigência na fonte oficial; o recurso não presta orientação jurídica profissional.

## Consultar pela interface

Abra **Legislação** na navegação lateral ou `/leis`.

- **Buscar por tema:** informe um assunto e, opcionalmente, filtre um documento.
- **Consultar artigo:** selecione o documento e informe o número.
- **Ler artigo:** abre o texto retornado pelo corpus em uma janela de leitura.
- **Fonte oficial:** abre o link preservado para aquele documento em uma nova aba.
- **Documentos e fontes:** mostra a quantidade de artigos e o commit do recorte.

A página informa quando a API está offline e não apresenta dados simulados como resultado.

## Consultar pela conversa

Exemplos reconhecidos pelo parser local:

```text
artigo 5 da Constituição
artigo 49 do CDC
consultar art. 1.046 do Código Civil
leia artigo 54-F do CDC
pesquisar na legislação sobre liberdade de expressão
pesquisar no CDC sobre direito de arrependimento
o que diz a lei sobre proteção de dados
fontes da legislação
```

Numeração com separador de milhar (`1.046`) e sufixo (`54-F`) é normalizada pelo backend. A conversa limita artigos muito longos a 6.000 caracteres e orienta usar a página Legislação para continuar a leitura.

## Skills da API

### `legal.search`

```json
{
  "parameters": {
    "query": "proteção de dados pessoais",
    "documentId": "lgpd",
    "limit": 6
  }
}
```

- `query`: de 2 a 240 caracteres;
- `documentId`: vazio para todos ou um dos oito IDs declarados;
- `limit`: de 1 a 12 resultados;
- resposta: total de ocorrências, resultados ranqueados, snippets, texto, fonte e aviso.

A normalização remove acentos para comparar termos. Stopwords evitam consultas vazias de conteúdo. Cobertura dos termos, proximidade e uma pequena tabela de variantes lexicais influenciam o ranking. Não há interpretação semântica ou jurídica por IA.

### `legal.article`

```json
{
  "parameters": {
    "documentId": "cdc",
    "article": "49"
  }
}
```

Retorna o artigo exato, texto, fonte e aviso. Um artigo individual é limitado a 16.000 caracteres; quando esse limite é atingido, o resultado é marcado como `truncated` e aponta para a fonte oficial.

### `legal.sources`

Não recebe parâmetros. Retorna os documentos, contagens, caminhos de origem, fontes e o commit do recorte.

Todas as skills jurídicas são **somente leitura**, sem `dryRun`, confirmação de gravação ou efeitos externos.

## Origem e atribuição

- Dados: `server/legal_data/*.md`.
- Índice e commit: `server/legal_data/index.json`.
- Atribuição e aviso: `server/legal_data/ATTRIBUTION.md`.
- Parser e busca: `server/legal_corpus.py`.

Conforme a documentação do projeto de origem, textos de atos oficiais não são protegidos pelo art. 8º, I, da Lei 9.610/98. Os scripts do upstream são MIT; nenhum script de coleta foi copiado.

## Sincronização controlada

A sincronização não roda na inicialização nem é exposta pela API. Ela usa somente os caminhos declarados em `index.json` e a API oficial do GitHub.

Comparar o recorte atual sem gravar:

```bash
.venv/bin/python scripts/sync_legal.py --check
```

Comparar com um commit revisado, ainda sem gravar:

```bash
.venv/bin/python scripts/sync_legal.py --check --commit COMMIT_COMPLETO
```

Baixar esse commit e atualizar a referência somente após as requisições:

```bash
.venv/bin/python scripts/sync_legal.py --commit COMMIT_COMPLETO
npm test
npm run build
```

Revise o diff, as fontes, os artigos e o aviso antes de aceitar uma atualização. A variável de ambiente `JARVIS_GITHUB_TOKEN` é opcional para o limite de requisições do GitHub; não a coloque no chat nem no Git.

## Ampliar o recorte

Novas normas exigem mudança explícita no índice, download revisado, atribuição, IDs allowlisted nos modelos Pydantic, aliases do parser da conversa e testes. Nenhum caminho arbitrário do acervo pode ser solicitado pela interface.

## Limites importantes

- O corpus não é completo nem atualizado em tempo real.
- A busca é lexical e pode ranquear trechos com sentido diferente do pretendido.
- Um resultado não é uma conclusão jurídica sobre um caso concreto.
- Links e avisos fazem parte do resultado; não devem ser removidos na apresentação.
- O provedor de IA não é necessário e não é usado para produzir as referências da skill.
