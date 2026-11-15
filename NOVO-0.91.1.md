# JARVIS 0.91.2 — o `.env` também vale para a sonda

Uma correção pequena, achada antes de você tropeçar nela.

## O que estava errado

O `arvore_sonda.py` roda solto no terminal. Só o `server/app.py` carregava o
`.env` — então, com o arquivo dizendo `JARVIS_HOST_REDE=1`, a sonda continuava
respondendo:

```
Parei no passo 1 (sistema.rede): SkillError: Rede desligada.
```

O mesmo valia para `JARVIS_FILES_ROOT`: um arquivo gravado pelo maestro podia
cair numa pasta diferente da que a página **Arquivos** mostra.

## Como foi medido

No sandbox, com `JARVIS_HOST_REDE=1` **só** no `.env` e a variável fora do
ambiente, a fila parava no passo 1 com "Rede desligada". Depois da correção, o
mesmo comando passou a falhar por **rede de verdade** (as três fontes não
respondem no sandbox) — que é a prova de que a variável foi lida.

## O que mudou

- `_configurar_ambiente(pasta)`: lê o `.env` com `load_dotenv`, **sem
  sobrescrever** o que já está no ambiente. Quem exportou a variável no terminal
  continua mandando — e há teste para isso.
- `_abrir_registro` chama essa função antes de montar o registro.
- **2 testes novos** (49 no arquivo): um prova que o `.env` é lido, outro que
  ele não passa por cima do ambiente.

## O que continua igual

Nada mais mudou de comportamento: os 4 procedimentos, a parada por autorização
e a parada por erro estão exatamente como na 0.91.0.

## O que ainda não foi medido

O maestro continua **sem nunca ter rodado no seu PC**. A correção de hoje só
garante que, quando você pedir "pesquisa X e guarda em Y", o erro que aparecer
— se aparecer — vai ser o erro verdadeiro, e não um "Rede desligada" falso.
