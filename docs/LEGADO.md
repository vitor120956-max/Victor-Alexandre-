# Inventário seguro do workspace recebido

O arquivo enviado pelo usuário era um ZIP com aproximadamente 94 MB e 128 entradas. A revisão foi feita sem executar os scripts.

## Conteúdo identificado

- `canal/agentes/`: módulos Python de montagem, corte e animação do personagem Lino.
- `canal/`: frames, sprites, vídeos e scripts de composição com OpenCV e FFmpeg.
- `historia/`: duas páginas HTML com histórias do Lino.
- `tmp-pr/`: automações de canais, leitura de propostas, backup de estado e testes.
- Arquivos de cofre, cookies e sessão: tratados como sensíveis e excluídos da importação.

## Decisões

- Nenhum script legado foi executado.
- Nenhuma credencial foi lida para uso, impressa ou incorporada ao projeto.
- Nenhuma automação de publicação ou renovação de sessão foi ativada.
- As mídias não foram copiadas para o Git, evitando um pacote inicial desnecessariamente pesado.
- O conector Python foi implementado com skills novas e seguras; os scripts legados ainda precisam de adaptação porque usam caminhos absolutos e dependências específicas.

O ZIP original permanece no Google Drive do usuário. Esta documentação registra apenas a estrutura necessária para continuar o desenvolvimento com segurança.

A migração dos módulos do Lino está fora do escopo da versão 0.5.0. Os incrementos atuais são independentes e implementam consulta local à legislação brasileira, documentos, skills de produtividade e workflows determinísticos de engenharia.
