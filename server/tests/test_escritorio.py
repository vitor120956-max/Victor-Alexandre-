from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.escritorio import (
    CODIGOS_SAIDA,
    ERROS,
    ESCOPOS,
    FLAGS,
    LOTES,
    PRESETS,
    RECEITAS,
    SERVICOS,
    EscritorioError,
    escritorio_catalog,
    ler_paginas,
    montar_comando,
    planejar_escopos,
    planejar_lote,
    planejar_receita,
    triar_erro,
)
from server.skill_registry import build_registry


@pytest.fixture()
def client(tmp_path) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


def comando(**kwargs):
    base = {
        "servico": "drive", "recurso": "files", "metodo": "list", "params": "",
        "corpo": "", "argumentos": "", "paginas": False, "limite_paginas": 10,
        "atraso_pagina": 100, "simular": False, "upload": "", "sanitizar": "",
        "modo": "full",
    }
    base.update(kwargs)
    return montar_comando(**base)


def titles(result):
    return [item["title"] for item in result["findings"]]


# ------------------------------------------------------------------- comando

def test_comando_simples_lista() -> None:
    result = comando()
    assert result["comando"] == "gws drive files list"
    assert result["risco"] == "leitura"
    assert result["counts"]["must"] == 0
    assert result["rows"][0]["valor"] == "gws"


def test_comando_usa_params_e_aspas_simples() -> None:
    result = comando(metodo="get", params='{"fileId":"abc","fields":"id,name"}')
    assert result["comando"] == 'gws drive files get --params \'{"fileId":"abc","fields":"id,name"}\''
    assert result["metrics"]["parametros"] == 2


def test_comando_json_compacto_e_sem_espacos() -> None:
    result = comando(metodo="get", params='{ "fileId" : "a b" }')
    assert '"fileId":"a b"' in result["comando"]


def test_comando_recusa_json_invalido() -> None:
    with pytest.raises(EscritorioError):
        comando(params='{"fileId":}')


def test_comando_recusa_params_que_nao_sao_objeto() -> None:
    with pytest.raises(EscritorioError):
        comando(params='["fileId"]')


def test_comando_recusa_servico_desconhecido() -> None:
    with pytest.raises(EscritorioError) as erro:
        comando(servico="nuvem")
    assert "nuvem" in str(erro.value)


def test_comando_recusa_metodo_ausente() -> None:
    with pytest.raises(EscritorioError):
        comando(metodo="")


def test_comando_aceita_recurso_com_pontos() -> None:
    result = comando(servico="gmail", recurso="users.messages", metodo="list", params='{"userId":"me"}')
    assert result["comando"] == 'gws gmail users.messages list --params \'{"userId":"me"}\''


def test_comando_aceita_metodo_com_ponto_no_recurso() -> None:
    result = comando(servico="gmail", recurso="users", metodo="messages.list", params='{"userId":"me"}')
    assert result["comando"].startswith("gws gmail users.messages list")


def test_comando_aponta_parametro_obrigatorio_faltando() -> None:
    result = comando(servico="gmail", recurso="users.messages", metodo="get")
    assert "Parâmetro obrigatório ausente" in titles(result)
    assert result["counts"]["must"] == 1


def test_comando_nao_exige_file_id_na_criacao() -> None:
    result = comando(metodo="create", corpo='{"name":"rel.pdf"}')
    assert result["counts"]["must"] == 0


def test_comando_exige_corpo_em_escrita() -> None:
    result = comando(metodo="create")
    assert "Corpo ausente em escrita" in titles(result)


def test_comando_avisa_corpo_em_leitura() -> None:
    result = comando(metodo="get", params='{"fileId":"a"}', corpo='{"name":"x"}')
    assert "Corpo em método de leitura" in titles(result)


def test_comando_pagina_so_com_page_all() -> None:
    result = comando(paginas=True, limite_paginas=3, atraso_pagina=250)
    assert "--page-all" in result["comando"]
    assert "--page-limit 3" in result["comando"]
    assert "--page-delay 250" in result["comando"]


def test_comando_sem_page_all_nao_imprime_limite() -> None:
    result = comando(limite_paginas=50)
    assert "--page-limit" not in result["comando"]
    assert "Limite de página sem `--page-all`" in titles(result)


def test_comando_paginar_fora_de_lista() -> None:
    result = comando(metodo="get", params='{"fileId":"a"}', paginas=True)
    assert "Paginação em método que não lista" in titles(result)


def test_comando_recusa_limite_zero() -> None:
    result = comando(paginas=True, limite_paginas=0)
    assert "Limite de páginas inválido" in titles(result)


def test_comando_avisa_limite_alto() -> None:
    result = comando(paginas=True, limite_paginas=5000)
    assert "Limite de páginas alto" in titles(result)


def test_comando_upload_fora_do_drive() -> None:
    result = comando(servico="gmail", recurso="users.messages", metodo="send",
                     params='{"userId":"me"}', corpo='{"raw":"x"}', upload="/tmp/a.pdf")
    assert "Upload fora do Drive" in titles(result)


def test_comando_upload_sem_metadados() -> None:
    result = comando(metodo="create", upload="/tmp/a.pdf")
    assert "Upload sem metadados" in titles(result)


def test_comando_upload_aceito_no_drive() -> None:
    result = comando(metodo="create", corpo='{"name":"a.pdf"}', upload="/tmp/a.pdf")
    assert "--upload '/tmp/a.pdf'" in result["comando"]
    assert result["counts"]["must"] == 0


def test_comando_template_do_model_armor_invalido() -> None:
    result = comando(metodo="list", sanitizar="template-x")
    assert "Template do Model Armor inválido" in titles(result)


def test_comando_template_valido() -> None:
    result = comando(metodo="list", sanitizar="projects/p/locations/l/templates/t")
    assert "--sanitize 'projects/p/locations/l/templates/t'" in result["comando"]
    assert result["counts"]["must"] == 0


def test_comando_destrutivo_pede_ensaio() -> None:
    result = comando(metodo="delete", params='{"fileId":"a"}')
    assert result["risco"] == "destrutivo"
    assert "Operação destrutiva" in titles(result)


def test_comando_simula_escrita() -> None:
    result = comando(metodo="create", corpo='{"name":"a"}', simular=True)
    assert result["comando"].endswith("--dry-run")
    assert "Escrita sem simulação" not in titles(result)


def test_comando_nao_simula_leitura() -> None:
    result = comando(simular=True)
    assert "--dry-run" not in result["comando"]


def test_comando_ajudante_simples() -> None:
    result = comando(servico="gmail", recurso="", metodo="+triage")
    assert result["comando"] == "gws gmail +triage"
    assert result["risco"] == "leitura"


def test_comando_ajudante_com_argumentos() -> None:
    result = comando(servico="gmail", recurso="", metodo="+send",
                     argumentos="--to ana@exemplo.com --subject Oi --body Teste")
    assert result["comando"] == "gws gmail +send --to 'ana@exemplo.com' --subject 'Oi' --body 'Teste'"


def test_comando_ajudante_desconhecido() -> None:
    with pytest.raises(EscritorioError):
        comando(servico="drive", recurso="", metodo="+send")


def test_comando_ajudante_nao_aceita_params() -> None:
    with pytest.raises(EscritorioError):
        comando(servico="gmail", recurso="", metodo="+triage", params='{"q":"x"}')


def test_comando_ajudante_flag_desconhecida() -> None:
    result = comando(servico="gmail", recurso="", metodo="+triage", argumentos="--pages 3")
    assert "Flag fora do ajudante" in titles(result)


def test_comando_ajudante_argumento_solto() -> None:
    result = comando(servico="gmail", recurso="", metodo="+triage", argumentos="tudo")
    assert "Argumento sem flag" in titles(result)


def test_comando_escopos_por_servico() -> None:
    assert [item["chave"] for item in comando()["escopos"]] == ["drive.readonly"]
    enviar = comando(servico="gmail", recurso="users.messages", metodo="send",
                     params='{"userId":"me"}', corpo='{"raw":"x"}')
    assert [item["chave"] for item in enviar["escopos"]] == ["gmail.send"]


def test_comando_mascarado_no_modo_lite() -> None:
    result = comando(metodo="get", modo="lite")
    assert all(item["group"] == "must" for item in result["findings"])


def test_comando_markdown_tem_bloco_bash() -> None:
    assert "```bash" in comando()["markdown"]
    assert "Não verificado" in comando()["markdown"]


# ------------------------------------------------------------------ receitas

def test_catalogo_de_receitas_tem_dez_ou_mais() -> None:
    assert len(RECEITAS) >= 10


def test_receita_expoe_passos_com_verificacao() -> None:
    result = planejar_receita(receita="agenda-do-dia", entradas='{"FUSO":"America/Sao_Paulo"}',
                              simular=False, modo="full")
    assert result["receita"] == "agenda-do-dia"
    assert len(result["passos"]) >= 2
    assert all(passo["verifica"] for passo in result["passos"])
    assert result["verificacao"]


def test_receita_reclama_entrada_obrigatoria() -> None:
    result = planejar_receita(receita="enviar-email", entradas="{}", simular=False, modo="full")
    assert result["counts"]["must"] >= 3
    assert "Entrada obrigatória vazia" in titles(result)


def test_receita_marca_marcador_quando_opcional_vazio() -> None:
    result = planejar_receita(receita="agenda-do-dia", entradas="{}", simular=False, modo="full")
    assert any("${FUSO}" in passo["comando"] for passo in result["passos"])


def test_receita_simula_globalmente() -> None:
    result = planejar_receita(receita="subir-arquivo",
                              entradas='{"ARQUIVO":"/tmp/a.pdf","NOME":"A"}',
                              simular=True, modo="full")
    assert result["passos"][1]["simular"] is True
    assert "--dry-run" in result["passos"][1]["comando"]
    assert "Plano inteiro em ensaio" in titles(result)


def test_receita_escopos_combinados() -> None:
    result = planejar_receita(receita="standup", entradas="{}", simular=False, modo="full")
    chaves = {item["chave"] for item in result["escopos"]}
    assert {"calendar.readonly", "gmail.readonly", "tasks"} <= chaves


def test_receita_desconhecida() -> None:
    with pytest.raises(EscritorioError):
        planejar_receita(receita="voar", entradas="{}", simular=False, modo="full")


def test_toda_receita_monta_sem_erro() -> None:
    for chave, plano in RECEITAS.items():
        entradas = {entrada["nome"]: entrada["exemplo"] for entrada in plano["entradas"]}
        result = planejar_receita(receita=chave, entradas=json.dumps(entradas),
                                  simular=False, modo="full")
        assert result["passos"], chave
        assert result["counts"]["must"] == 0, chave


def test_receita_com_rollback_declara_saida() -> None:
    result = planejar_receita(receita="enviar-email",
                              entradas='{"PARA":"a@b.com","ASSUNTO":"s","CORPO":"c"}',
                              simular=False, modo="full")
    assert "desfazer" in result["rollback"].lower()
    assert "Se der errado" in result["markdown"]


# ------------------------------------------------------------------ páginas

def paginas(texto, **kwargs):
    base = {"chave_itens": "", "campo_id": "id", "comando_base": "", "params_base": "",
            "modo": "full"}
    base.update(kwargs)
    return ler_paginas(paginas=texto, **base)


def test_pagina_unica_completa() -> None:
    result = paginas('{"files":[{"id":"a"},{"id":"b"}]}')
    assert result["completa"] is True
    assert result["metrics"]["itens"] == 2
    assert result["metrics"]["unicos"] == 2


def test_paginas_ndjson_incompleta() -> None:
    texto = '{"files":[{"id":"a"}],"nextPageToken":"T"}\n{"files":[{"id":"b"}]}'
    result = paginas(texto)
    assert result["completa"] is False
    assert result["metrics"]["tokens"] == 1
    assert "A coleta terminou antes do fim" in titles(result)


def test_paginas_array_de_paginas() -> None:
    result = paginas('[{"files":[{"id":"a"}]},{"files":[{"id":"b"}]}]')
    assert result["metrics"]["paginas"] == 2


def test_paginas_detectam_duplicata() -> None:
    texto = '{"files":[{"id":"a"},{"id":"a"}]}'
    result = paginas(texto)
    assert result["metrics"]["duplicados"] == 1
    assert "IDs repetidos na coleta" in titles(result)


def test_paginas_item_sem_id() -> None:
    result = paginas('{"files":[{"name":"sem id"}]}')
    assert result["metrics"]["sem_id"] == 1
    assert "Item sem identificador" in titles(result)


def test_paginas_ids_como_string() -> None:
    result = paginas('{"messages":["m1","m2"]}', chave_itens="messages")
    assert result["metrics"]["unicos"] == 2
    assert "Itens só com ID" in titles(result)


def test_paginas_chave_fixa_ausente() -> None:
    result = paginas('{"files":[]}', chave_itens="messages")
    assert "Chave de itens ausente" in titles(result)


def test_paginas_chaves_misturadas() -> None:
    texto = '{"files":[{"id":"a"}]}\n{"messages":[{"id":"m"}]}'
    result = paginas(texto)
    assert "Chaves de itens diferentes" in titles(result)


def test_paginas_token_repetido_e_laco() -> None:
    texto = '{"files":[{"id":"a"}],"nextPageToken":"T"}\n{"files":[{"id":"b"}],"nextPageToken":"T"}'
    result = paginas(texto)
    assert "Token repetido entre páginas" in titles(result)


def test_paginas_proximo_comando_com_base() -> None:
    result = paginas('{"files":[{"id":"a"}],"nextPageToken":"T"}',
                     comando_base="gws drive files list", params_base='{"q":"trashed = false"}')
    assert "pageToken" in result["proximoComando"]
    assert result["proximoComando"].startswith("gws drive files list --params")
    assert "T" in result["proximoComando"]


def test_paginas_sem_base_usa_instrucao() -> None:
    result = paginas('{"files":[{"id":"a"}],"nextPageToken":"T"}')
    assert "pageToken" in result["proximoComando"]


def test_paginas_recusa_texto_vazio() -> None:
    with pytest.raises(EscritorioError):
        paginas("   ")


def test_paginas_recusa_json_invalido() -> None:
    with pytest.raises(EscritorioError):
        paginas('{"files": [}')


def test_paginas_pagina_com_erro() -> None:
    result = paginas('{"error":{"code":403,"message":"negado"}}')
    assert "Página trouxe erro" in titles(result)


def test_paginas_markdown_lista_paginas() -> None:
    result = paginas('{"files":[{"id":"a"},{"id":"b"}]}')
    assert "## Páginas" in result["markdown"]
    assert "## IDs" in result["markdown"]


# --------------------------------------------------------------------- lotes

def lote(**kwargs):
    base = {"operacao": "gmail.ids", "itens": '["a","b"]', "parametros": "",
            "limite": 0, "simular": False, "modo": "full"}
    base.update(kwargs)
    return planejar_lote(**base)


def test_lote_gmail_monta_envelope() -> None:
    result = lote(parametros='{"removeLabelIds":["INBOX"]}')
    assert result["lotes"][0]["corpo"]["ids"] == ["a", "b"]
    assert result["lotes"][0]["corpo"]["removeLabelIds"] == ["INBOX"]


def test_lote_respeita_limite_do_usuario() -> None:
    result = lote(itens='["a","b","c","d","e"]', limite=2)
    assert [item["itens"] for item in result["lotes"]] == [2, 2, 1]
    assert result["metrics"]["chamadas"] == 3


def test_lote_nao_passa_do_teto_curado() -> None:
    result = lote(itens=json.dumps(["x"] * 1200), limite=5000)
    assert result["metrics"]["limite"] == 1000


def test_lote_item_invalido_e_apontado() -> None:
    result = lote(operacao="sheets.valores", itens='[{"range":"A1","values":[]}]')
    assert result["counts"]["must"] >= 1
    assert "Item fora do formato" in titles(result)


def test_lote_sheets_valores_valido() -> None:
    result = lote(operacao="sheets.valores",
                  itens='[{"range":"A1:B2","values":[["a","b"]]}]',
                  parametros='{"valueInputOption":"USER_ENTERED"}')
    corpo = result["lotes"][0]["corpo"]
    assert corpo["valueInputOption"] == "USER_ENTERED"
    assert corpo["data"][0]["range"] == "A1:B2"


def test_lote_sheets_requisicoes_exige_uma_chave() -> None:
    result = lote(operacao="sheets.requisicoes", itens='[{"updateCells":{},"repeatCell":{}}]')
    assert "Item fora do formato" in titles(result)


def test_lote_sheets_requisicoes_valido() -> None:
    result = lote(operacao="sheets.requisicoes", itens='[{"repeatCell":{"range":{}}}]')
    assert result["lotes"][0]["corpo"]["requests"][0]["repeatCell"] == {"range": {}}


def test_lote_atomico_avisa() -> None:
    result = lote(operacao="docs.requisicoes", itens='[{"insertText":{"text":"oi"}}]')
    assert "Lote é atômico" in titles(result)


def test_lote_sem_lote_por_item() -> None:
    result = lote(operacao="drive.permissoes",
                  itens='[{"fileId":"f","permission":{"role":"reader","type":"user"}}]')
    assert result["metrics"]["chamadas"] == 1
    assert "Operação não tem lote" in titles(result)


def test_lote_calendar_valida_datas() -> None:
    result = lote(operacao="calendar.eventos", itens='[{"summary":"Reunião"}]')
    assert "Item fora do formato" in titles(result)


def test_lote_vazio_e_erro() -> None:
    with pytest.raises(EscritorioError):
        lote(itens="[]")


def test_lote_operacao_desconhecida() -> None:
    with pytest.raises(EscritorioError):
        lote(operacao="drive.zip")


def test_lote_simula_por_padrao() -> None:
    result = lote(simular=True)
    assert result["lotes"][0]["comando"].endswith("--dry-run")


def test_lote_markdown_lista_lotes() -> None:
    result = lote(itens='["a","b","c"]', limite=2)
    assert "## Lotes" in result["markdown"]
    assert "## Como verificar" in result["markdown"]


# ------------------------------------------------------------------- escopos

def escopos(**kwargs):
    base = {"operacoes": "", "concedidos": "", "modo": "full"}
    base.update(kwargs)
    return planejar_escopos(**base)


def test_escopos_lista_exigidos() -> None:
    result = escopos(operacoes="gmail users.messages list", concedidos="gmail.readonly")
    assert result["metrics"]["exigidos"] == 1
    assert result["metrics"]["faltando"] == 0


def test_escopos_aponta_faltando() -> None:
    result = escopos(operacoes="gmail users.messages send")
    assert "Escopo necessário não concedido" in titles(result)
    assert result["faltando"] == ["gmail.send"]


def test_escopos_aponta_sobrando() -> None:
    result = escopos(operacoes="gmail users.messages list", concedidos="gmail.readonly,tasks")
    assert result["sobrando"] == ["tasks"]
    assert "Escopo concedido sem uso" in titles(result)


def test_escopos_superconjunto_satisfaz() -> None:
    result = escopos(operacoes="drive files list", concedidos="drive")
    assert result["faltando"] == []
    assert result["sobrando"] == []


def test_escopos_readonly_satisfeito_por_completo() -> None:
    result = escopos(operacoes="sheets +read", concedidos="spreadsheets")
    assert result["faltando"] == []


def test_escopos_ajudante_de_workflow() -> None:
    result = escopos(operacoes="workflow +standup-report", concedidos="")
    assert set(result["faltando"]) == {"calendar.readonly", "gmail.readonly", "tasks"}


def test_escopos_escopo_desconhecido() -> None:
    result = escopos(operacoes="drive files list", concedidos="drive.inventado")
    assert "Escopo fora do catálogo" in titles(result)


def test_escopos_limite_de_consentimento() -> None:
    linhas = "\n".join([
        "drive files get", "drive files create", "drive permissions create",
        "gmail users.messages list", "gmail users.messages send", "gmail users.messages modify",
        "gmail users.labels create", "calendar events list", "calendar events insert",
        "calendar acl insert", "sheets spreadsheets get", "sheets spreadsheets batchUpdate",
        "docs documents get", "docs documents batchUpdate", "slides presentations get",
        "slides presentations batchUpdate", "chat spaces messages list",
        "chat spaces messages create", "tasks tasks list", "people people get",
        "admin users list", "admin users insert", "classroom courses list",
        "forms forms get", "forms forms create", "keep notes list", "meet spaces get",
        "script projects get", "script deployments list", "events subscriptions list",
        "modelarmor templates get",
    ])
    result = escopos(operacoes=linhas)
    assert result["metrics"]["exigidos"] > 25
    assert "Acima do limite de consentimento" in titles(result)


def test_escopos_comando_de_login() -> None:
    result = escopos(operacoes="gmail users.messages list\ndrive files create")
    assert result["comando"].startswith("gws auth login --scopes ")
    assert "gmail.readonly" in result["comando"]


def test_escopos_recusa_servico_desconhecido() -> None:
    with pytest.raises(EscritorioError):
        escopos(operacoes="nuvem files list")


def test_escopos_recusa_lista_vazia() -> None:
    with pytest.raises(EscritorioError):
        escopos(operacoes="   ")


def test_escopos_recusa_ajudante_de_outro_servico() -> None:
    with pytest.raises(EscritorioError):
        escopos(operacoes="drive +send")


def test_escopos_linha_sem_metodo() -> None:
    with pytest.raises(EscritorioError):
        escopos(operacoes="drive")


# --------------------------------------------------------------------- erros

def erro(**kwargs):
    base = {"codigo": 1, "mensagem": "", "tentativas": 0, "idempotente": True, "modo": "full"}
    base.update(kwargs)
    return triar_erro(**base)


def test_erro_429_regeta_com_espera() -> None:
    result = erro(mensagem='{"error":{"code":429,"reason":"rateLimitExceeded"}}', tentativas=1)
    assert result["triagem"]["repetir"] is True
    assert result["triagem"]["espera"] == 30
    assert result["triagem"]["grupo"] == "cota"


def test_erro_401_pede_login() -> None:
    result = erro(codigo=2, mensagem='{"error":{"code":401,"reason":"invalid_token"}}')
    assert result["triagem"]["grupo"] == "autenticacao"
    assert result["triagem"]["repetir"] is False
    assert "gws auth login" in result["triagem"]["comando"]


def test_erro_api_nao_habilitada() -> None:
    result = erro(mensagem='{"error":{"code":403,"reason":"accessNotConfigured"}}')
    assert result["triagem"]["grupo"] == "configuracao"
    assert result["triagem"]["repetir"] is True


def test_erro_sem_reason_usa_status() -> None:
    result = erro(mensagem='HTTP 404: File not found')
    assert result["triagem"]["reason"] == ""
    assert result["triagem"]["status"] == 404
    assert result["triagem"]["grupo"] == "nao-encontrado"


def test_erro_sem_reason_usa_codigo_de_saida() -> None:
    auth = erro(codigo=2, mensagem="credenciais ausentes")
    assert auth["triagem"]["grupo"] == "autenticacao"
    validacao = erro(codigo=3, mensagem="flag errada")
    assert validacao["triagem"]["grupo"] == "validacao"


def test_erro_escrita_nao_repete_as_cegas() -> None:
    result = erro(mensagem='{"error":{"code":503,"reason":"backendError"}}',
                  tentativas=2, idempotente=False)
    assert result["triagem"]["repetir"] is False
    assert "Não repita escrita às cegas" in titles(result)


def test_erro_escopo_sugere_revisao() -> None:
    result = erro(mensagem='{"error":{"code":403,"reason":"insufficientPermissions"}}')
    assert "Confira o escopo antes do login" in titles(result)


def test_erro_interno_pede_log() -> None:
    result = erro(codigo=5, mensagem="panic at src/main.rs")
    assert "Erro interno do CLI" in titles(result)


def test_erro_sem_erro_nao_inventa() -> None:
    result = erro(codigo=0, mensagem="")
    assert "Nada a triar" in titles(result)


def test_erro_codigo_fora_da_faixa() -> None:
    with pytest.raises(EscritorioError):
        erro(codigo=9)


def test_erro_markdown_tem_diagnostico() -> None:
    result = erro(mensagem='{"error":{"code":403,"reason":"quotaExceeded"}}')
    assert "## Diagnóstico" in result["markdown"]
    assert "quotaExceeded" in result["markdown"]


def test_erro_desconhecido() -> None:
    result = erro(mensagem="algo deu errado")
    assert "Erro sem classificação" in titles(result)


# ------------------------------------------------------------------ catálogo

def test_catalogo_tem_o_vocabulario() -> None:
    catalogo = escritorio_catalog()
    assert catalogo["versao"] == "0.52.0"
    assert len(catalogo["servicos"]) == len(SERVICOS) >= 15
    assert len(catalogo["flags"]) == len(FLAGS) == 10
    assert len(catalogo["codigos"]) == len(CODIGOS_SAIDA) == 6
    assert len(catalogo["escopos"]) == len(ESCOPOS) >= 25
    assert len(catalogo["receitas"]) == len(RECEITAS)
    assert len(catalogo["lotes"]) == len(LOTES) == 6
    assert len(catalogo["erros"]) == len(ERROS) >= 10
    assert set(PRESETS) <= {item["id"] for item in catalogo["presets"]}
    assert catalogo["executado"] is False


# ----------------------------------------------------------------------- API

def test_api_health_reflete_versao_e_catalogo(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["version"] == "0.52.0"
    assert health["skills"] == 254


def test_api_lista_as_sete_skills(client: TestClient) -> None:
    skills = client.get("/api/skills").json()["skills"]
    ids = {skill["id"] for skill in skills}
    assert {
        "escritorio.comando", "escritorio.receita", "escritorio.paginas",
        "escritorio.lote", "escritorio.escopos", "escritorio.erros", "escritorio.regras",
    } <= ids


def test_api_executa_comando(client: TestClient) -> None:
    response = client.post("/api/skills/escritorio.comando/execute", json={
        "parameters": {"servico": "drive", "recurso": "files", "metodo": "list",
                       "params": '{"pageSize":5}'},
    }).json()
    assert response["ok"] is True
    assert response["result"]["comando"] == 'gws drive files list --params \'{"pageSize":5}\''


def test_api_executa_regras(client: TestClient) -> None:
    response = client.post("/api/skills/escritorio.regras/execute", json={"parameters": {}}).json()
    assert response["ok"] is True
    assert response["result"]["fonte"].startswith("googleworkspace/cli")
