# Configurar a IA externa

A camada generativa é opcional. As skills locais e Python não dependem dela.

## 1. Escolha um provedor compatível

O backend chama `POST {JARVIS_AI_BASE_URL}/chat/completions` com o formato OpenAI Chat Completions. Consulte a documentação do provedor escolhido para obter:

- a base da API compatível;
- o nome exato do modelo;
- uma chave com o menor escopo e limite de gasto adequado.

Não use uma chave de administrador e não compartilhe a credencial no chat.

## 2. Crie o arquivo de ambiente no servidor

```bash
cp .env.example .env
```

Edite `.env`:

```dotenv
JARVIS_AI_PROVIDER=Nome exibido na interface
JARVIS_AI_BASE_URL=https://api.exemplo.com/v1
JARVIS_AI_MODEL=modelo-disponivel-na-sua-conta
JARVIS_AI_API_KEY=valor-da-chave
```

Não inclua `/chat/completions` na base: o backend acrescenta esse caminho. O `.env` já está no `.gitignore`.

## 3. Reinicie e verifique

```bash
npm run dev
```

Abra **Configurações → Inteligência generativa**. O painel deve mostrar `CONFIGURADA`, o provedor e o modelo. Também é possível verificar o status público, que nunca inclui a chave:

```bash
curl http://127.0.0.1:8000/api/ai/status
```

## 4. Teste uma pergunta aberta

Na conversa, envie uma pergunta que não seja um comando local. A resposta deverá exibir a marca `IA EXTERNA`. Comandos como `calcular 8 * 7` continuam locais, e `analisar texto ...` continua usando Python. Consultas como `artigo 49 do CDC` e `pesquisar na legislação sobre privacidade` usam o corpus local e não são enviadas ao provedor.

## Privacidade

Por padrão, a IA recebe a pergunta e até 12 mensagens recentes, mas não recebe sua lista de tarefas ou notas. Para permitir esse contexto, ative **Compartilhar tarefas e notas como contexto**. Desative essa opção se a conversa tratar de dados sensíveis.

## Diagnóstico

- **NÃO CONFIGURADA:** revise os nomes das variáveis e reinicie o processo.
- **HTTP 401/403:** confira a chave e as permissões no provedor.
- **HTTP 404:** revise a base e o nome do modelo.
- **HTTP 429:** aguarde ou revise cota e limites de gasto.
- **Timeout/conexão:** verifique se o ambiente do servidor tem rota de saída para o provedor.

Os erros de resposta do provedor não são copiados integralmente para a interface, para reduzir risco de vazamento de dados.
