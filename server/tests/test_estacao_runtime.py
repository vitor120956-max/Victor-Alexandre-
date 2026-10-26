from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.estacao_runtime import (
    FERRAMENTAS,
    INTERROMPIDA,
    PERMISSOES,
    EstacaoRuntime,
    EstacaoRuntimeError,
)
from server.skill_registry import build_registry


@pytest.fixture()
def runtime(tmp_path) -> EstacaoRuntime:
    return EstacaoRuntime(root=tmp_path / "files")


@pytest.fixture()
def aberto(tmp_path) -> EstacaoRuntime:
    """Executor com tudo liberado — o caso de uso quando a pessoa escolhe assim."""
    executor = EstacaoRuntime(root=tmp_path / "files")
    for permissao in PERMISSOES:
        executor.definir_politica(permissao, "allow")
    return executor


@pytest.fixture()
def client(tmp_path) -> TestClient:
    arquivos = tmp_path / "files"
    return TestClient(create_app(registry=build_registry(arquivos), estacao=EstacaoRuntime(root=arquivos)))


def executar(executor: EstacaoRuntime, ferramenta: str, **argumentos):
    return executor.solicitar(ferramenta, argumentos)


# ---------------------------------------------------------------- ferramentas

def test_catalogo_de_ferramentas() -> None:
    assert set(FERRAMENTAS) == {"exec", "read_file", "write_file", "list_dir", "grep", "cron"}


def test_permissoes_do_executor() -> None:
    assert set(PERMISSOES) == {"computer.exec", "files.read", "files.write", "automations"}
    assert PERMISSOES["computer.exec"]["padrao"] == "ask"


def test_exec_roda_de_verdade(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "exec", comando="echo ola")
    assert chamada["estado"] == "ok"
    assert chamada["resultado"]["saida"].strip() == "ola"
    assert chamada["resultado"]["codigo"] == 0
    assert chamada["executou"] is True


def test_exec_roda_no_diretorio_da_estacao(aberto: EstacaoRuntime) -> None:
    saida = executar(aberto, "exec", comando="pwd")["resultado"]["saida"].strip()
    assert Path(saida).resolve() == aberto.root


def test_exec_captura_codigo_de_saida(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "exec", comando="exit 3")
    assert chamada["estado"] == "erro"
    assert chamada["resultado"]["codigo"] == 3


def test_exec_captura_stderr(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "exec", comando="echo erro >&2; exit 1")
    assert "[stderr]" in chamada["resultado"]["saida"]
    assert "erro" in chamada["resultado"]["saida"]


def test_exec_timeout_encerra(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "exec", comando="sleep 5", timeout_s=1)
    assert chamada["estado"] == "erro"
    assert chamada["resultado"]["timeout"] is True


def test_exec_nao_herda_segredos(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "exec", comando="env | grep -c JARVIS || true")
    assert chamada["resultado"]["saida"].strip() == "0"


def test_exec_env_limpo(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "exec", comando="env | sort")
    nomes = {linha.split("=")[0] for linha in chamada["resultado"]["saida"].splitlines() if "=" in linha}
    assert {"PATH", "HOME", "LANG"} <= nomes
    assert "JARVIS_AI_API_KEY" not in nomes


def test_exec_subdiretorio(aberto: EstacaoRuntime) -> None:
    aberto.solicitar("write_file", {"caminho": "sub/a.txt", "conteudo": "x"})
    chamada = executar(aberto, "exec", comando="cat a.txt", diretorio="sub")
    assert chamada["resultado"]["saida"].strip() == "x"
    assert chamada["resultado"]["diretorio"] == "sub"


def test_exec_diretorio_inexistente(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "exec", comando="ls", diretorio="nao-existe")
    assert chamada["estado"] == "erro"


def test_exec_comando_vazio_rejeitado(aberto: EstacaoRuntime) -> None:
    with pytest.raises(EstacaoRuntimeError):
        executar(aberto, "exec", comando="   ")


def test_exec_timeout_fora_da_faixa(aberto: EstacaoRuntime) -> None:
    with pytest.raises(EstacaoRuntimeError):
        executar(aberto, "exec", comando="ls", timeout_s=9_999)


def test_write_e_read(aberto: EstacaoRuntime) -> None:
    escrita = executar(aberto, "write_file", caminho="nota.txt", conteudo="linha 1\nlinha 2")
    assert escrita["estado"] == "ok"
    assert escrita["resultado"]["criado"] is True
    leitura = executar(aberto, "read_file", caminho="nota.txt")
    assert leitura["resultado"]["texto"] == "linha 1\nlinha 2"
    assert leitura["resultado"]["linhas"] == 2


def test_write_simular_nao_grava(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "write_file", caminho="x.txt", conteudo="a", simular=True)
    assert chamada["resultado"]["simulado"] is True
    assert not (aberto.root / "x.txt").exists()


def test_write_sobrescreve(aberto: EstacaoRuntime) -> None:
    executar(aberto, "write_file", caminho="a.txt", conteudo="um")
    chamada = executar(aberto, "write_file", caminho="a.txt", conteudo="dois")
    assert chamada["resultado"]["criado"] is False
    assert (aberto.root / "a.txt").read_text() == "dois"


def test_read_arquivo_inexistente(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "read_file", caminho="nao.txt")
    assert chamada["estado"] == "erro"
    assert "não encontrado" in chamada["resultado"]["erro"]


def test_read_binario(aberto: EstacaoRuntime) -> None:
    (aberto.root / "b.bin").write_bytes(b"\x00\x01\x02")
    chamada = executar(aberto, "read_file", caminho="b.bin")
    assert chamada["resultado"]["binario"] is True


def test_read_limite_de_linhas(aberto: EstacaoRuntime) -> None:
    executar(aberto, "write_file", caminho="m.txt", conteudo="\n".join(str(i) for i in range(10)))
    assert executar(aberto, "read_file", caminho="m.txt", limite_linhas=3)["resultado"]["linhas"] == 3


def test_caminho_nao_escapa(aberto: EstacaoRuntime) -> None:
    for caminho in ("../fora.txt", "/etc/passwd", ".oculto", "a/../../b"):
        chamada = executar(aberto, "read_file", caminho=caminho)
        assert chamada["estado"] == "erro", caminho


def test_list_dir(aberto: EstacaoRuntime) -> None:
    executar(aberto, "write_file", caminho="a.txt", conteudo="x")
    executar(aberto, "write_file", caminho="sub/b.txt", conteudo="y")
    chamada = executar(aberto, "list_dir", caminho="", recursivo=True)
    caminhos = {item["caminho"] for item in chamada["resultado"]["itens"]}
    assert {"a.txt", "sub/b.txt"} <= caminhos


def test_list_dir_sem_recursao(aberto: EstacaoRuntime) -> None:
    executar(aberto, "write_file", caminho="sub/b.txt", conteudo="y")
    itens = executar(aberto, "list_dir", caminho="")["resultado"]["itens"]
    assert [item["tipo"] for item in itens] == ["pasta"]


def test_grep_acha(aberto: EstacaoRuntime) -> None:
    executar(aberto, "write_file", caminho="a.txt", conteudo="alfa\nbeta\ngama")
    chamada = executar(aberto, "grep", padrao="beta")
    assert chamada["resultado"]["total"] == 1
    assert chamada["resultado"]["achados"][0]["linha"] == 2


def test_grep_limite(aberto: EstacaoRuntime) -> None:
    executar(aberto, "write_file", caminho="a.txt", conteudo="x\n" * 20)
    assert executar(aberto, "grep", padrao="x", limite=5)["resultado"]["total"] == 5


def test_grep_regex_invalida(aberto: EstacaoRuntime) -> None:
    with pytest.raises(EstacaoRuntimeError):
        executar(aberto, "grep", padrao="[")


def test_ferramenta_desconhecida(aberto: EstacaoRuntime) -> None:
    with pytest.raises(EstacaoRuntimeError):
        executar(aberto, "teleportar")


def test_argumento_extra_rejeitado(aberto: EstacaoRuntime) -> None:
    with pytest.raises(EstacaoRuntimeError):
        executar(aberto, "exec", comando="ls", shell=True)


# -------------------------------------------------------------------- gate

def test_padrao_pede_aprovacao(runtime: EstacaoRuntime) -> None:
    chamada = executar(runtime, "exec", comando="echo ola")
    assert chamada["estado"] == "pendente"
    assert chamada["decisao"] == "ask"
    assert chamada["executou"] is False


def test_padrao_leitura_liberada(runtime: EstacaoRuntime) -> None:
    (runtime.root / "a.txt").write_text("x")
    assert executar(runtime, "read_file", caminho="a.txt")["estado"] == "ok"


def test_allow_executa_na_hora(runtime: EstacaoRuntime) -> None:
    runtime.definir_politica("computer.exec", "allow")
    assert executar(runtime, "exec", comando="echo ok")["estado"] == "ok"


def test_deny_nao_executa(runtime: EstacaoRuntime) -> None:
    runtime.definir_politica("computer.exec", "deny")
    chamada = executar(runtime, "exec", comando="echo ola")
    assert chamada["estado"] == "negado"
    assert chamada["resultado"]["motivo"] == "política deny"


def test_deny_nao_cria_arquivo(runtime: EstacaoRuntime) -> None:
    runtime.definir_politica("files.write", "deny")
    executar(runtime, "write_file", caminho="x.txt", conteudo="a")
    assert not (runtime.root / "x.txt").exists()


def test_politica_persiste(runtime: EstacaoRuntime, tmp_path) -> None:
    runtime.definir_politica("computer.exec", "allow")
    outro = EstacaoRuntime(root=tmp_path / "files")
    assert outro.decisao("computer.exec") == "allow"


def test_politica_desconhecida_rejeitada(runtime: EstacaoRuntime) -> None:
    with pytest.raises(EstacaoRuntimeError):
        runtime.definir_politica("root.tudo", "allow")


def test_decisao_invalida_rejeitada(runtime: EstacaoRuntime) -> None:
    with pytest.raises(EstacaoRuntimeError):
        runtime.definir_politica("computer.exec", "talvez")


def test_permissao_desconhecida_e_deny(runtime: EstacaoRuntime) -> None:
    assert runtime.decisao("inexistente") == "deny"


# ---------------------------------------------------------------- aprovação

def test_aprovar_executa(runtime: EstacaoRuntime) -> None:
    pendente = executar(runtime, "exec", comando="echo aprovado")
    aprovada = runtime.aprovar(pendente["id"], True, "ok")
    assert aprovada["estado"] == "ok"
    assert aprovada["resultado"]["saida"].strip() == "aprovado"


def test_recusar_nao_executa(runtime: EstacaoRuntime) -> None:
    pendente = executar(runtime, "exec", comando="echo nunca")
    recusada = runtime.aprovar(pendente["id"], False, "não agora")
    assert recusada["estado"] == "recusado"
    assert recusada["resultado"]["nota"] == "não agora"
    assert recusada["executou"] is False


def test_segunda_decisao_e_ignorada(runtime: EstacaoRuntime) -> None:
    pendente = executar(runtime, "exec", comando="echo uma vez")
    primeira = runtime.aprovar(pendente["id"], True)
    segunda = runtime.aprovar(pendente["id"], True)
    assert segunda["ignorada"] is True
    assert segunda["estado"] == primeira["estado"] == "ok"


def test_aprovacao_vale_uma_chamada(runtime: EstacaoRuntime) -> None:
    primeira = executar(runtime, "exec", comando="echo 1")
    runtime.aprovar(primeira["id"], True)
    segunda = executar(runtime, "exec", comando="echo 2")
    assert segunda["estado"] == "pendente"


def test_aprovar_duas_vezes_nao_executa_duas(runtime: EstacaoRuntime) -> None:
    pendente = executar(runtime, "exec", comando="echo x >> contagem.txt")
    runtime.aprovar(pendente["id"], True)
    runtime.aprovar(pendente["id"], True)
    conteudo = (runtime.root / "contagem.txt").read_text()
    assert conteudo.count("x") == 1


def test_pendentes_lista(runtime: EstacaoRuntime) -> None:
    executar(runtime, "exec", comando="echo 1")
    executar(runtime, "exec", comando="echo 2")
    assert len(runtime.pendentes()) == 2


def test_chamada_inexistente(runtime: EstacaoRuntime) -> None:
    with pytest.raises(EstacaoRuntimeError):
        runtime.aprovar("nao-existe", True)


def test_aprovacao_registra_recibo(runtime: EstacaoRuntime) -> None:
    pendente = executar(runtime, "exec", comando="echo r")
    runtime.aprovar(pendente["id"], True, "visto")
    eventos = [item["evento"] for item in runtime.recibos(pendente["id"])]
    assert {"intent", "aprovado", "ok"} <= set(eventos)


# ------------------------------------------------------------------ recibos

def test_recibo_de_intent(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "exec", comando="echo a")
    primeiro = [item for item in aberto.recibos(chamada["id"]) if item["evento"] == "intent"]
    assert primeiro and "exec echo a" in primeiro[0]["detalhe"]


def test_recibo_de_erro(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "exec", comando="exit 1")
    assert "erro" in [item["evento"] for item in aberto.recibos(chamada["id"])]


def test_recibo_de_negado(runtime: EstacaoRuntime) -> None:
    runtime.definir_politica("computer.exec", "deny")
    chamada = executar(runtime, "exec", comando="ls")
    assert "negado" in [item["evento"] for item in runtime.recibos(chamada["id"])]


def test_recibos_em_ordem_inversa(aberto: EstacaoRuntime) -> None:
    executar(aberto, "exec", comando="echo a")
    executar(aberto, "exec", comando="echo b")
    seqs = [item["seq"] for item in aberto.recibos()]
    assert seqs == sorted(seqs, reverse=True)


def test_recibos_filtrados_por_chamada(aberto: EstacaoRuntime) -> None:
    a = executar(aberto, "exec", comando="echo a")
    executar(aberto, "exec", comando="echo b")
    assert {item["chamada"] for item in aberto.recibos(a["id"])} == {a["id"]}


# ------------------------------------------------------------- recuperação

def test_recuperar_marca_interrompida(runtime: EstacaoRuntime) -> None:
    chamada = executar(runtime, "exec", comando="echo x")
    with sqlite3.connect(runtime.db_path) as conn:
        conn.execute("UPDATE chamadas SET estado = 'executando' WHERE id = ?", (chamada["id"],))
    resultado = runtime.recuperar()
    assert resultado["interrompidas"] == 1
    depois = runtime.obter(chamada["id"])
    assert depois["estado"] == "interrompido"
    assert depois["resultado"]["mensagem"] == INTERROMPIDA
    assert depois["resultado"]["resultado_desconhecido"] is True


def test_recuperar_sem_pendencia(runtime: EstacaoRuntime) -> None:
    assert runtime.recuperar()["interrompidas"] == 0


def test_interrompida_nao_reexecuta(runtime: EstacaoRuntime) -> None:
    chamada = executar(runtime, "exec", comando="echo x >> feito.txt")
    with sqlite3.connect(runtime.db_path) as conn:
        conn.execute("UPDATE chamadas SET estado = 'executando' WHERE id = ?", (chamada["id"],))
    runtime.recuperar()
    runtime.aprovar(chamada["id"], True)
    assert not (runtime.root / "feito.txt").exists()
    assert runtime.obter(chamada["id"])["estado"] == "interrompido"


def test_recuperar_deixa_recibo(runtime: EstacaoRuntime) -> None:
    chamada = executar(runtime, "exec", comando="echo x")
    with sqlite3.connect(runtime.db_path) as conn:
        conn.execute("UPDATE chamadas SET estado = 'executando' WHERE id = ?", (chamada["id"],))
    runtime.recuperar()
    assert "interrompido" in [item["evento"] for item in runtime.recibos(chamada["id"])]


# --------------------------------------------------------------- automações

def test_criar_automacao(aberto: EstacaoRuntime) -> None:
    chamada = executar(aberto, "cron", nome="relatorio", cron="0 9 * * 1-5", comando="echo r", minutos=5)
    assert chamada["estado"] == "ok"
    agenda = aberto.automacoes()
    assert agenda[0]["nome"] == "relatorio"
    assert agenda[0]["ativa"] is True


def test_automacao_nome_repetido(aberto: EstacaoRuntime) -> None:
    executar(aberto, "cron", nome="a", cron="0 9 * * *", comando="echo 1")
    with pytest.raises(EstacaoRuntimeError):
        aberto.criar_automacao("a", "0 9 * * *", "echo 2")


def test_automacao_nome_invalido(aberto: EstacaoRuntime) -> None:
    with pytest.raises(EstacaoRuntimeError):
        aberto.criar_automacao("Com Espaço", "0 9 * * *", "echo")


def test_automacao_cron_invalido(aberto: EstacaoRuntime) -> None:
    with pytest.raises(EstacaoRuntimeError):
        aberto.criar_automacao("a", "todo dia", "echo")


def test_automacao_remover(aberto: EstacaoRuntime) -> None:
    executar(aberto, "cron", nome="a", cron="0 9 * * *", comando="echo")
    assert aberto.remover_automacao("a")["removida"] == "a"
    assert aberto.automacoes() == []


def test_automacao_alternar(aberto: EstacaoRuntime) -> None:
    executar(aberto, "cron", nome="a", cron="0 9 * * *", comando="echo")
    assert aberto.alternar_automacao("a", False)["ativa"] is False


def test_tick_dispara_vencida(aberto: EstacaoRuntime) -> None:
    executar(aberto, "cron", nome="a", cron="0 9 * * *", comando="echo tick >> log.txt")
    futuro = datetime.now(timezone.utc) + timedelta(days=2)
    resultado = aberto.tick(futuro)
    assert resultado["total"] == 1
    assert resultado["disparadas"][0]["estado"] == "ok"
    assert (aberto.root / "log.txt").exists()


def test_tick_nao_dispara_futura(aberto: EstacaoRuntime) -> None:
    executar(aberto, "cron", nome="a", cron="0 9 * * *", comando="echo")
    assert aberto.tick()["total"] == 0


def test_tick_respeita_gate(runtime: EstacaoRuntime) -> None:
    runtime.definir_politica("automations", "allow")
    runtime.solicitar("cron", {"nome": "a", "cron": "0 9 * * *", "comando": "echo"})
    resultado = runtime.tick(datetime.now(timezone.utc) + timedelta(days=2))
    assert resultado["disparadas"][0]["estado"] == "pendente"
    assert len(runtime.pendentes()) == 1


def test_tick_conta_falha(aberto: EstacaoRuntime) -> None:
    executar(aberto, "cron", nome="a", cron="0 9 * * *", comando="exit 1")
    aberto.tick(datetime.now(timezone.utc) + timedelta(days=2))
    assert aberto.automacao("a")["falhas"] == 1


def test_tick_para_apos_tres_falhas(aberto: EstacaoRuntime) -> None:
    executar(aberto, "cron", nome="a", cron="* * * * *", comando="exit 1")
    base = datetime.now(timezone.utc)
    for passo in range(3):
        aberto.tick(base + timedelta(days=1, minutes=passo + 1))
    assert aberto.automacao("a")["ativa"] is False


# ------------------------------------------------------------------- estado

def test_estado_traz_politica_e_contagem(aberto: EstacaoRuntime) -> None:
    executar(aberto, "exec", comando="echo a")
    estado = aberto.estado()
    assert estado["contagem"]["ok"] == 1
    assert set(estado["politica"]) == set(PERMISSOES)
    assert estado["versao"] == "0.48.0"
    assert estado["executado"] is True


def test_estado_lista_ferramentas(aberto: EstacaoRuntime) -> None:
    nomes = {item["nome"] for item in aberto.estado()["ferramentas"]}
    assert nomes == set(FERRAMENTAS)


def test_banco_fica_fora_da_area_de_arquivos(tmp_path) -> None:
    executor = EstacaoRuntime(root=tmp_path / "files")
    assert tmp_path / "files" not in executor.db_path.parents


def test_diretorio_criado(tmp_path) -> None:
    raiz = tmp_path / "nova"
    EstacaoRuntime(root=raiz)
    assert raiz.is_dir()


def test_duas_instancias_mesmo_banco(tmp_path) -> None:
    primeira = EstacaoRuntime(root=tmp_path / "files")
    primeira.definir_politica("computer.exec", "allow")
    primeira.solicitar("exec", {"comando": "echo a"})
    segunda = EstacaoRuntime(root=tmp_path / "files")
    assert len(segunda.chamadas()) == 1


# ---------------------------------------------------------------------- API

def test_api_estado(client: TestClient) -> None:
    resposta = client.get("/api/estacao/estado").json()
    assert resposta["ok"] is True
    assert resposta["result"]["raiz"]


def test_api_executa_e_executa_de_verdade(client: TestClient) -> None:
    client.put("/api/estacao/politica", json={"permissao": "computer.exec", "decisao": "allow"})
    resposta = client.post("/api/estacao/executar", json={
        "ferramenta": "exec", "argumentos": {"comando": "echo api"},
    }).json()
    assert resposta["ok"] is True
    assert resposta["result"]["resultado"]["saida"].strip() == "api"


def test_api_fluxo_de_aprovacao(client: TestClient) -> None:
    criada = client.post("/api/estacao/executar", json={
        "ferramenta": "exec", "argumentos": {"comando": "echo aprovado"},
    }).json()
    pendente = criada["result"]
    assert pendente["estado"] == "pendente"

    lista = client.get("/api/estacao/aprovacoes").json()
    assert len(lista["result"]["pendentes"]) == 1

    decidida = client.post(f"/api/estacao/aprovacoes/{pendente['id']}/decidir", json={
        "aprovado": True, "nota": "ok",
    }).json()
    assert decidida["result"]["estado"] == "ok"


def test_api_recusa(client: TestClient) -> None:
    pendente = client.post("/api/estacao/executar", json={
        "ferramenta": "exec", "argumentos": {"comando": "echo x"},
    }).json()["result"]
    decidida = client.post(f"/api/estacao/aprovacoes/{pendente['id']}/decidir", json={"aprovado": False}).json()
    assert decidida["result"]["estado"] == "recusado"


def test_api_politica_invalida(client: TestClient) -> None:
    resposta = client.put("/api/estacao/politica", json={"permissao": "x.y", "decisao": "allow"}).json()
    assert resposta["ok"] is False
    assert resposta["error"]["code"] == "ESTACAO_ERROR"


def test_api_ferramenta_invalida(client: TestClient) -> None:
    resposta = client.post("/api/estacao/executar", json={"ferramenta": "nada", "argumentos": {}}).json()
    assert resposta["ok"] is False


def test_api_argumento_extra_422(client: TestClient) -> None:
    resposta = client.post("/api/estacao/executar", json={
        "ferramenta": "exec", "argumentos": {"comando": "ls"}, "extra": 1,
    })
    assert resposta.status_code == 422


def test_api_agenda(client: TestClient) -> None:
    client.put("/api/estacao/politica", json={"permissao": "automations", "decisao": "allow"})
    criada = client.post("/api/estacao/agenda", json={
        "nome": "diario", "cron": "0 9 * * *", "comando": "echo oi", "minutos": 5,
    }).json()
    assert criada["ok"] is True
    assert len(client.get("/api/estacao/agenda").json()["result"]["automacoes"]) == 1
    assert client.delete("/api/estacao/agenda/diario").json()["ok"] is True


def test_api_agenda_alternar(client: TestClient) -> None:
    client.put("/api/estacao/politica", json={"permissao": "automations", "decisao": "allow"})
    client.post("/api/estacao/agenda", json={"nome": "a", "cron": "0 9 * * *", "comando": "echo"})
    resposta = client.post("/api/estacao/agenda/a/alternar?ativa=false").json()
    assert resposta["result"]["ativa"] is False


def test_api_recuperar(client: TestClient) -> None:
    resposta = client.post("/api/estacao/recuperar").json()
    assert resposta["ok"] is True
    assert resposta["result"]["interrompidas"] == 0


def test_api_recibos_e_chamadas(client: TestClient) -> None:
    client.put("/api/estacao/politica", json={"permissao": "computer.exec", "decisao": "allow"})
    client.post("/api/estacao/executar", json={"ferramenta": "exec", "argumentos": {"comando": "echo a"}})
    assert len(client.get("/api/estacao/chamadas").json()["result"]["chamadas"]) == 1
    assert len(client.get("/api/estacao/recibos").json()["result"]["recibos"]) >= 2


def test_api_health_versao_nova(client: TestClient) -> None:
    assert client.get("/api/health").json()["version"] == "0.48.0"
