from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.estacao import (
    CUSTO_MAX,
    DECISOES,
    ESTADOS,
    FERRAMENTAS,
    PASSOS_MAX,
    PERMISSOES,
    REGRAS_EFEITO,
    EstacaoError,
    auditar_memoria,
    auditar_permissoes,
    auditar_recibos,
    checar_limites,
    estacao_catalog,
    planejar_agenda,
    planejar_tarefa,
)
from server.skill_registry import build_registry


@pytest.fixture()
def client(tmp_path) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


def tarefa(**kwargs):
    base = {
        "objetivo": "baixar o comprovante e salvar em ~/docs",
        "ferramentas": "read_file, write_file, browser_navigate",
        "politica": "files.read=allow\nfiles.write=ask",
        "passos_max": 60,
        "orcamento": 1.0,
        "modo": "full",
    }
    base.update(kwargs)
    return planejar_tarefa(**base)


def permissoes(**kwargs):
    base = {
        "politica": "computer.exec=ask\nfiles.read=allow\nfiles.write=ask\nbrowser.act=ask",
        "ferramentas": "",
        "servidores_mcp": "",
        "limite_passos": 60,
        "limite_custo": 1.0,
        "ocio_minutos": 15,
        "modo": "full",
    }
    base.update(kwargs)
    return auditar_permissoes(**base)


def recibos(log: str, modo: str = "full"):
    return auditar_recibos(log=log, modo=modo)


def agenda(**kwargs):
    base = {
        "automacoes": "relatorio | 0 9 * * 1-5 | 30 | sim",
        "orcamento_diario": 8,
        "presenca": "9-18",
        "modo": "full",
    }
    base.update(kwargs)
    return planejar_agenda(**base)


def limites(acoes: str, modo: str = "full"):
    return checar_limites(acoes=acoes, modo=modo)


def memoria(**kwargs):
    base = {
        "notas": "Ana prefere relatórios em PDF (2026-10-20).\nTrabalha com planilhas (2026-09-02).",
        "skills": "nome: planilha\ngatilho: quando pedirem planilha\npassos: abrir; colar; salvar\nverificacao: arquivo existe",
        "modo": "full",
    }
    base.update(kwargs)
    return auditar_memoria(**base)


def titles(result):
    return [item["title"] for item in result["findings"]]


def kinds(result):
    return [item["kind"] for item in result["findings"]]


# ------------------------------------------------------------------- tarefa

def test_tarefa_abre_com_observacao() -> None:
    result = tarefa()
    assert result["passos"][0]["tipo"] == "observar"
    assert result["passos"][-1]["tipo"] == "registrar"


def test_tarefa_numera_passos_em_ordem() -> None:
    result = tarefa()
    assert [passo["ordem"] for passo in result["passos"]] == list(range(1, len(result["passos"]) + 1))


def test_tarefa_verifica_depois_de_escrever() -> None:
    result = tarefa(ferramentas="read_file, write_file", politica="files.write=allow")
    tipos = [passo["tipo"] for passo in result["passos"]]
    assert "verificar" in tipos
    indice = tipos.index("agir")
    assert tipos[indice + 1] == "verificar"


def test_tarefa_marca_aprovacao_no_passo() -> None:
    result = tarefa(politica="files.read=allow\nfiles.write=ask")
    assert result["passos"][1]["aprovacao"] is True
    assert result["metrics"]["aprovacoes"] >= 1


def test_tarefa_sem_aprovacao_quando_allow() -> None:
    result = tarefa(politica="files.read=allow\nfiles.write=allow")
    assert all(passo["aprovacao"] is False for passo in result["passos"])
    assert "aprovacao-no-plano" not in kinds(result)


def test_tarefa_risco_alto_livre_exige_ask() -> None:
    result = tarefa(objetivo="executar o script de limpeza", ferramentas="read_file, exec",
                    politica="files.read=allow\ncomputer.exec=allow")
    assert "risco-alto-livre" in kinds(result)


def test_tarefa_ferramenta_desconhecida() -> None:
    result = tarefa(ferramentas="read_file, teleportar")
    assert "ferramenta-desconhecida" in kinds(result)
    assert result["counts"]["must"] >= 1


def test_tarefa_sem_leitura() -> None:
    result = tarefa(ferramentas="write_file", politica="files.write=allow")
    assert "sem-leitura" in kinds(result)


def test_tarefa_objetivo_curto_rejeitado() -> None:
    with pytest.raises(EstacaoError):
        tarefa(objetivo="testar")


def test_tarefa_sem_ferramentas_rejeitada() -> None:
    with pytest.raises(EstacaoError):
        tarefa(ferramentas=" , ; ")


def test_tarefa_politica_invalida_rejeitada() -> None:
    with pytest.raises(EstacaoError):
        tarefa(politica="files.read=maybe")


def test_tarefa_politica_com_dois_pontos() -> None:
    result = tarefa(politica="files.read: allow")
    assert all(passo["aprovacao"] is False for passo in result["passos"])


def test_tarefa_orcamento_curto_avisa() -> None:
    result = tarefa(passos_max=4)
    assert "orcamento-curto" in kinds(result)


def test_tarefa_custo_alto_avisa() -> None:
    result = tarefa(orcamento=9)
    assert "custo-alto" in kinds(result)


def test_tarefa_plano_maior_que_orcamento() -> None:
    result = tarefa(passos_max=3)
    assert "passos-acima" in kinds(result)


def test_tarefa_objetivo_de_navegacao_usa_navegador() -> None:
    result = tarefa(objetivo="abrir o portal e baixar a guia")
    ferramentas_usadas = [passo["ferramenta"] for passo in result["passos"]]
    assert "browser_navigate" in ferramentas_usadas


def test_tarefa_objetivo_recorrente_pede_automacao() -> None:
    result = tarefa(objetivo="agendar o relatório toda semana", ferramentas="read_file, cron")
    permissoes_usadas = [passo["permissao"] for passo in result["passos"]]
    assert "automations" in permissoes_usadas


def test_tarefa_acao_sem_ferramenta() -> None:
    result = tarefa(objetivo="clicar em enviar", ferramentas="read_file")
    assert "acao-sem-ferramenta" in kinds(result)


def test_tarefa_modo_lite_so_must() -> None:
    result = tarefa(modo="lite", orcamento=9)
    assert result["counts"]["should"] == 0
    assert all(item["group"] == "must" for item in result["findings"])


def test_tarefa_e_deterministica() -> None:
    assert tarefa()["passos"] == tarefa()["passos"]


def test_tarefa_e_somente_leitura() -> None:
    result = tarefa()
    assert result["executado"] is False
    assert result["readOnly"] is True


def test_tarefa_metricas_completas() -> None:
    result = tarefa()
    assert set(result["metrics"]) == {
        "passos", "ferramentas", "aprovacoes", "risco_alto", "passos_max", "orcamento"
    }


def test_tarefa_markdown_tem_parada() -> None:
    result = tarefa()
    assert "## Parada" in result["markdown"]
    assert "não verificado" in result["markdown"].lower()


# -------------------------------------------------------------- permissões

def test_permissoes_contam_decisoes() -> None:
    result = permissoes()
    assert result["metrics"]["ask"] == 3
    assert result["metrics"]["allow"] == 1


def test_permissoes_exec_allow_bloqueia() -> None:
    result = permissoes(politica="computer.exec=allow")
    assert "risco-alto-livre" in kinds(result)
    assert result["counts"]["must"] >= 1


def test_permissoes_automations_allow_bloqueia() -> None:
    result = permissoes(politica="automations=allow")
    assert any(item["location"] == "automations=allow" for item in result["findings"])


def test_permissoes_delete_ask_nao_bloqueia() -> None:
    result = permissoes(politica="browser.identity.delete=ask")
    assert result["counts"]["must"] == 0


def test_permissoes_desconhecida() -> None:
    result = permissoes(politica="computer.teleport=allow")
    assert "permissao-desconhecida" in kinds(result)


def test_permissoes_mcp_sem_servidor() -> None:
    result = permissoes(politica="mcp.planilhas=ask")
    assert "mcp-nao-declarado" in kinds(result)


def test_permissoes_mcp_com_servidor() -> None:
    result = permissoes(politica="mcp.planilhas=ask", servidores_mcp="planilhas")
    assert "mcp-nao-declarado" not in kinds(result)


def test_permissoes_ferramenta_negada() -> None:
    result = permissoes(politica="files.read=deny", ferramentas="read_file")
    assert "ferramenta-negada" in kinds(result)


def test_permissoes_ferramenta_usa_padrao() -> None:
    result = permissoes(politica="files.read=allow", ferramentas="write_file")
    assert "permissao-implícita" in kinds(result) or "permissao-implícita" in titles(result)


def test_permissoes_leitura_negada() -> None:
    result = permissoes(politica="files.read=deny")
    assert "leitura-negada" in kinds(result)


def test_permissoes_agir_sem_ler() -> None:
    result = permissoes(politica="browser.act=ask\nbrowser.read=deny")
    assert "agir-sem-ler" in kinds(result)


def test_permissoes_passos_altos() -> None:
    result = permissoes(limite_passos=400)
    assert "passos-altos" in kinds(result)


def test_permissoes_custo_alto() -> None:
    result = permissoes(limite_custo=9)
    assert "custo-alto" in kinds(result)


def test_permissoes_ocio_zero() -> None:
    result = permissoes(ocio_minutos=0)
    assert "nunca-dorme" in kinds(result)


def test_permissoes_vazia_rejeitada() -> None:
    with pytest.raises(EstacaoError):
        permissoes(politica="")


def test_permissoes_linha_sem_valor_rejeitada() -> None:
    with pytest.raises(EstacaoError):
        permissoes(politica="files.read")


def test_permissoes_rotulo_e_padrao_na_matriz() -> None:
    result = permissoes()
    linha = next(item for item in result["matriz"] if item["permissao"] == "computer.exec")
    assert linha["rotulo"] == "Executar comandos"
    assert linha["padrao"] == "allow"
    assert linha["risco"] == "alto"


def test_permissoes_modo_lite() -> None:
    result = permissoes(politica="computer.exec=allow\nfiles.read=deny", modo="lite")
    assert all(item["group"] == "must" for item in result["findings"])


def test_permissoes_ask_nao_conta_como_livre() -> None:
    result = permissoes(politica="computer.exec=ask\nbrowser.act=ask")
    assert result["metrics"]["risco_alto_livre"] == 0


def test_permissoes_soma_decisoes() -> None:
    result = permissoes(politica="a=allow\nb=deny\nc=ask")
    assert result["metrics"]["permissoes"] == 3


def test_permissoes_markdown_lista_matriz() -> None:
    result = permissoes()
    assert "## Matriz" in result["markdown"]


# ------------------------------------------------------------------ recibos

def test_recibos_ok_limpo() -> None:
    result = recibos("id=c1 tool=read_file status=ok result=conteudo")
    assert result["counts"]["total"] == 0


def test_recibos_intent_sem_resultado() -> None:
    result = recibos("id=c1 tool=write_file status=intent")
    assert "sem-resultado" in kinds(result)


def test_recibos_interrompido_sem_conclusao() -> None:
    result = recibos("id=c1 tool=write_file status=interrompido")
    assert result["interrompidas"] == ["c1"]
    assert result["counts"]["must"] >= 1


def test_recibos_execucao_dupla() -> None:
    result = recibos("id=c1 tool=write_file status=ok result=a\nid=c1 tool=write_file status=ok result=b")
    assert "execucao-dupla" in kinds(result)


def test_recibos_aprovacao_repetida() -> None:
    result = recibos("id=c1 tool=write_file status=ok approval=ap1\nid=c2 tool=write_file status=ok approval=ap1")
    assert "aprovacao-repetida" in kinds(result)


def test_recibos_retomada_sem_conferir() -> None:
    result = recibos("id=c1 tool=write_file status=interrompido\nid=c1 tool=write_file status=ok result=a")
    assert "retomada-sem-checagem" in kinds(result)


def test_recibos_retomada_conferida_passa() -> None:
    result = recibos("id=c1 tool=write_file status=interrompido\n"
                     "id=c1 tool=write_file status=ok result=a verificado=sim")
    assert "retomada-sem-checagem" not in kinds(result)
    assert "sem-resultado" not in kinds(result)


def test_recibos_status_invalido() -> None:
    result = recibos("id=c1 tool=read_file status=quase")
    assert "status-invalido" in kinds(result)


def test_recibos_ferramenta_fora_do_catalogo() -> None:
    result = recibos("id=c1 tool=teleportar status=ok result=x")
    assert "ferramenta-fora" in kinds(result)


def test_recibos_aceita_prefixo_mcp() -> None:
    result = recibos("id=c1 tool=mcp_planilhas_ler status=ok result=x")
    assert "ferramenta-fora" not in kinds(result)


def test_recibos_ok_sem_resultado() -> None:
    result = recibos("id=c1 tool=read_file status=ok")
    assert "ok-sem-resultado" in kinds(result)


def test_recibos_metricas() -> None:
    result = recibos("id=c1 tool=read_file status=ok result=a\nid=c2 tool=write_file status=erro result=b")
    assert result["metrics"] == {
        "linhas": 2, "chamadas": 2, "interrompidas": 0, "duplicadas": 0,
        "com_aprovacao": 0, "erros": 1,
    }


def test_recibos_log_vazio_rejeitado() -> None:
    with pytest.raises(EstacaoError):
        recibos("\n\n# só comentário")


def test_recibos_deterministico() -> None:
    log = "id=c1 tool=read_file status=ok result=x"
    assert recibos(log)["recibos"] == recibos(log)["recibos"]


def test_recibos_separa_por_barra() -> None:
    result = recibos("id=c1 | tool=read_file | status=ok | result=x")
    assert result["metrics"]["chamadas"] == 1
    assert result["recibos"][0]["ferramenta"] == "read_file"


def test_recibos_preserva_ordem() -> None:
    result = recibos("id=c1 tool=read_file status=ok result=a\nid=c2 tool=read_file status=ok result=b")
    assert [linha["chamada"] for linha in result["recibos"]] == ["c1", "c2"]


def test_recibos_markdown_lista_interrompidas() -> None:
    result = recibos("id=c1 tool=write_file status=interrompido")
    assert "Podem ter sido aplicadas" in result["markdown"]


def test_recibos_aproximacao_de_erro() -> None:
    result = recibos("id=c1 tool=read_file status=recusado result=negado")
    assert result["metrics"]["erros"] == 1


# ------------------------------------------------------------------- agenda

def test_agenda_uma_automacao() -> None:
    result = agenda()
    assert result["metrics"]["automacoes"] == 1
    assert result["metrics"]["disparos_semana"] == 5


def test_agenda_cron_invalido() -> None:
    result = agenda(automacoes="ruim | 9h * * * | 10 | nao")
    assert "cron-invalido" in kinds(result)


def test_agenda_cron_campos_demais() -> None:
    result = agenda(automacoes="ruim | 0 0 9 * * * | 10 | nao")
    assert "cron-invalido" in kinds(result)


def test_agenda_cron_a_cada_minuto() -> None:
    result = agenda(automacoes="pulso | * * * * * | 1 | nao")
    assert "cron-tempestade" in kinds(result)


def test_agenda_sobreposicao() -> None:
    result = agenda(automacoes="a | 0 9 * * 1 | 60 | nao\nb | 30 9 * * 1 | 30 | nao")
    assert "sobreposicao" in kinds(result)


def test_agenda_sem_sobreposicao_quando_separa() -> None:
    result = agenda(automacoes="a | 0 9 * * 1 | 30 | nao\nb | 0 11 * * 1 | 30 | nao")
    assert "sobreposicao" not in kinds(result)


def test_agenda_presenca_fora_da_janela() -> None:
    result = agenda(automacoes="madrugada | 30 3 * * 1 | 20 | sim", presenca="9-18")
    assert "presenca-fora" in kinds(result)


def test_agenda_sem_presenca_nao_checa() -> None:
    result = agenda(automacoes="madrugada | 30 3 * * 1 | 20 | nao", presenca="9-18")
    assert "presenca-fora" not in kinds(result)


def test_agenda_duracao_longa() -> None:
    result = agenda(automacoes="longa | 0 9 * * 1 | 180 | nao")
    assert "longa" in kinds(result)


def test_agenda_nome_repetido() -> None:
    result = agenda(automacoes="a | 0 9 * * 1 | 10 | nao\na | 0 11 * * 1 | 10 | nao")
    assert "nome-repetido" in kinds(result)


def test_agenda_orcamento_de_acordadas() -> None:
    linhas = "\n".join(f"a{indice} | 0 {8 + indice} * * 1 | 10 | nao" for indice in range(5))
    result = agenda(automacoes=linhas, orcamento_diario=2)
    assert "acorda-demais" in kinds(result)


def test_agenda_vazia_rejeitada() -> None:
    with pytest.raises(EstacaoError):
        agenda(automacoes="  \n # nada")


def test_agenda_linha_incompleta_rejeitada() -> None:
    with pytest.raises(EstacaoError):
        agenda(automacoes="a | 0 9 * * 1")


def test_agenda_duracao_invalida_rejeitada() -> None:
    with pytest.raises(EstacaoError):
        agenda(automacoes="a | 0 9 * * 1 | dez | nao")


def test_agenda_dia_do_mes_rejeitado() -> None:
    result = agenda(automacoes="a | 0 9 15 * * | 10 | nao")
    assert "cron-invalido" in kinds(result)


def test_agenda_semana_util_cinco_dias() -> None:
    assert agenda()["metrics"]["disparos_semana"] == 5


def test_agenda_passo_de_quinze_minutos() -> None:
    result = agenda(automacoes="pulso | */15 * * * * | 1 | nao")
    assert result["metrics"]["disparos_semana"] == 4 * 24 * 7


def test_agenda_conflitos_listados() -> None:
    result = agenda(automacoes="a | 0 9 * * 1 | 60 | nao\nb | 30 9 * * 1 | 30 | nao")
    assert result["conflitos"]
    assert {"dia", "minuto", "a", "b"} == set(result["conflitos"][0])


def test_agenda_deterministica() -> None:
    assert agenda()["agenda"] == agenda()["agenda"]


def test_agenda_metricas() -> None:
    result = agenda()
    assert result["metrics"]["orcamento"] == 8
    assert result["metrics"]["com_presenca"] == 1


def test_agenda_markdown_tem_atraso() -> None:
    result = agenda()
    assert "## Atraso e queda" in result["markdown"]


def test_agenda_aceita_cron_com_lista() -> None:
    result = agenda(automacoes="a | 0 9,18 * * 1,3 | 10 | nao")
    assert result["metrics"]["disparos_semana"] == 4


# ------------------------------------------------------------------ limites

def test_limites_leitura_liberada() -> None:
    result = limites("ler o extrato do banco")
    assert result["acoes"][0]["nivel"] == "liberado"


def test_limites_captcha_nao_e_assunto_da_ferramenta() -> None:
    result = limites("resolver o captcha do login")
    assert result["acoes"][0]["nivel"] == "confirmar"
    assert result["counts"]["must"] == 0


def test_limites_indetectavel_nao_e_bloqueado() -> None:
    result = limites("ficar indetectável para o site")
    assert result["acoes"][0]["nivel"] == "confirmar"


def test_limites_fingerprint_nao_e_bloqueado() -> None:
    result = limites("falsificar o fingerprint do navegador")
    assert result["acoes"][0]["nivel"] != "irreversivel"


def test_limites_apagar_e_irreversivel() -> None:
    result = limites("apagar os comprovantes antigos")
    assert result["acoes"][0]["nivel"] == "irreversivel"
    assert result["acoes"][0]["regra"] == "exclusao"


def test_limites_pagar_e_irreversivel() -> None:
    result = limites("pagar a fatura do cartão")
    assert result["acoes"][0]["regra"] == "pagamento"


def test_limites_enviar_confirma() -> None:
    result = limites("enviar e-mail para o cliente")
    assert result["acoes"][0]["nivel"] == "confirmar"
    assert result["acoes"][0]["regra"] == "envio"


def test_limites_instalar_confirma() -> None:
    result = limites("instalar o programa auxiliar")
    assert result["acoes"][0]["regra"] == "instalacao"


def test_limites_permissao_confirma() -> None:
    result = limites("mudar permissão para allow")
    assert result["acoes"][0]["regra"] == "permissao"


def test_limites_conta_confirma() -> None:
    result = limites("criar conta no portal")
    assert result["acoes"][0]["nivel"] == "confirmar"
    assert result["acoes"][0]["regra"] == "conta"


def test_limites_acao_desconhecida_confirma() -> None:
    result = limites("organizar a pasta")
    assert result["acoes"][0]["nivel"] == "confirmar"
    assert result["acoes"][0]["regra"] == "indefinido"


def test_limites_vazio_rejeitado() -> None:
    with pytest.raises(EstacaoError):
        limites("")


def test_limites_modo_lite_so_must() -> None:
    result = limites("enviar e-mail\napagar arquivos", modo="lite")
    assert all(item["group"] == "must" for item in result["findings"])


def test_limites_metricas_somam() -> None:
    result = limites("ler o site\nenviar e-mail\napagar arquivos")
    total = result["metrics"]["liberadas"] + result["metrics"]["confirmar"] + result["metrics"]["irreversiveis"]
    assert total == result["metrics"]["acoes"] == 3


def test_limites_nao_tem_nivel_bloqueado() -> None:
    result = limites("resolver captcha\nraspar e-mails\nignorar robots.txt")
    assert {item["nivel"] for item in result["acoes"]} <= {"liberado", "confirmar", "irreversivel"}


def test_limites_catalogo_tem_seis_regras_de_efeito() -> None:
    catalog = estacao_catalog()
    assert len(catalog["limites"]) == 6
    assert {item["regra"] for item in catalog["limites"]} == set(REGRAS_EFEITO)


def test_limites_pagar_nao_casa_com_apagar() -> None:
    assert limites("apagar a pasta")["acoes"][0]["regra"] == "exclusao"
    assert limites("pagar a conta")["acoes"][0]["regra"] == "pagamento"


# ------------------------------------------------------------------ memória

def test_memoria_notas_limpas() -> None:
    result = memoria()
    assert result["counts"]["must"] == 0


def test_memoria_segredo_aparente() -> None:
    result = memoria(notas="API key: sk-abcdef123456\n(2026-10-20)")
    assert "segredo" in kinds(result)


def test_memoria_chave_privada() -> None:
    result = memoria(notas="-----BEGIN RSA PRIVATE KEY-----\nxyz")
    assert "segredo" in kinds(result)


def test_memoria_tamanho_acima_do_teto() -> None:
    result = memoria(notas="a" * 26_000)
    assert "memoria-longa" in kinds(result)


def test_memoria_fato_sem_data() -> None:
    result = memoria(notas="Ana prefere reuniões pela manhã e detesta interrupção.")
    assert "fato-sem-data" in kinds(result)


def test_memoria_fato_com_data_passa() -> None:
    result = memoria(notas="Ana prefere reuniões pela manhã (2026-10-20).")
    assert "fato-sem-data" not in kinds(result)


def test_memoria_data_brasileira_passa() -> None:
    result = memoria(notas="Ana prefere reuniões pela manhã (20/10/2026).")
    assert "fato-sem-data" not in kinds(result)


def test_memoria_absoluto() -> None:
    result = memoria(notas="Sempre manda cópia para o financeiro (2026-10-20).")
    assert "absoluto" in kinds(result)


def test_memoria_sem_skills() -> None:
    result = memoria(skills="")
    assert "sem-skills" in kinds(result)


def test_memoria_skill_sem_gatilho() -> None:
    result = memoria(skills="nome: planilha\npassos: abrir; salvar\nverificacao: arquivo existe")
    assert "skill-sem-gatilho" in kinds(result)


def test_memoria_skill_sem_verificacao() -> None:
    result = memoria(skills="nome: planilha\ngatilho: quando pedirem planilha\npassos: a; b")
    assert "skill-sem-prova" in kinds(result)


def test_memoria_gatilho_repetido() -> None:
    bloco = "nome: {nome}\ngatilho: quando pedirem planilha\npassos: a; b\nverificacao: arquivo existe"
    result = memoria(skills=bloco.format(nome="a") + "\n---\n" + bloco.format(nome="b"))
    assert "gatilho-duplicado" in kinds(result)


def test_memoria_skill_com_segredo() -> None:
    result = memoria(skills="nome: a\ngatilho: token\npassos: usar token=abcdefgh123\nverificacao: ok")
    assert "skill-segredo" in kinds(result)


def test_memoria_conta_skills() -> None:
    result = memoria()
    assert result["metrics"]["skills"] == 1
    assert result["skills"][0]["nome"] == "planilha"


def test_memoria_notas_vazias_rejeitadas() -> None:
    with pytest.raises(EstacaoError):
        memoria(notas="curto")


def test_memoria_deterministica() -> None:
    assert memoria()["skills"] == memoria()["skills"]


def test_memoria_passa_a_conta_passos() -> None:
    result = memoria()
    assert result["skills"][0]["passos"] == 3


def test_memoria_metricas() -> None:
    result = memoria()
    assert set(result["metrics"]) == {"notas", "linhas", "skills", "segredos", "sem_data"}


def test_memoria_markdown_tem_higiene() -> None:
    result = memoria()
    assert "## Higiene" in result["markdown"]


# ---------------------------------------------------------------- catálogo

def test_catalogo_tem_as_chaves() -> None:
    catalog = estacao_catalog()
    assert {
        "fonte", "versao", "ferramentas", "permissoes", "decisoes", "estados",
        "limites", "orcamento", "principio",
    } <= set(catalog)


def test_catalogo_tem_trinta_ferramentas() -> None:
    assert len(estacao_catalog()["ferramentas"]) == 30
    assert len(FERRAMENTAS) == 30


def test_catalogo_tem_quatorze_permissoes() -> None:
    assert len(estacao_catalog()["permissoes"]) == 14
    assert len(PERMISSOES) == 14


def test_toda_ferramenta_aponta_permissao_conhecida() -> None:
    for nome, dado in FERRAMENTAS.items():
        assert dado["permissao"] in PERMISSOES, nome


def test_toda_permissao_tem_risco_padrao_rotulo() -> None:
    for nome, dado in PERMISSOES.items():
        assert dado["risco"] in {"baixo", "médio", "alto"}, nome
        assert dado["padrao"] in DECISOES, nome
        assert dado["rotulo"], nome


def test_catalogo_nao_julga_tema() -> None:
    catalog = estacao_catalog()
    assert "evasao" not in catalog
    assert "nao_adaptado" not in catalog
    assert all(item["nivel"] in {"confirmar", "irreversivel"} for item in catalog["limites"])


def test_catalogo_tres_decisoes() -> None:
    assert estacao_catalog()["decisoes"] == ["allow", "ask", "deny"]


def test_catalogo_seis_estados() -> None:
    assert len(estacao_catalog()["estados"]) == 6
    assert set(ESTADOS) == {item["estado"] for item in estacao_catalog()["estados"]}


def test_catalogo_orcamentos() -> None:
    valores = {item["regra"]: item["valor"] for item in estacao_catalog()["orcamento"]}
    assert f"padrão {PASSOS_MAX}" in valores["Passos por tarefa"]
    assert "1,00" in valores["Custo por tarefa"]


def test_catalogo_versao_nova() -> None:
    assert estacao_catalog()["versao"] == "0.44.0"


def test_catalogo_e_somente_leitura() -> None:
    assert estacao_catalog()["executado"] is False
    assert CUSTO_MAX == 1.0


# ---------------------------------------------------------------------- API

def test_api_lista_as_skills_da_estacao(client: TestClient) -> None:
    skills = client.get("/api/skills").json()["skills"]
    ids = {skill["id"] for skill in skills}
    assert {
        "estacao.tarefa", "estacao.permissoes", "estacao.recibos",
        "estacao.agenda", "estacao.limites", "estacao.memoria", "estacao.regras",
    } <= ids
    assert "Estação" in {skill["category"] for skill in skills}


def test_api_limites_classifica_por_efeito(client: TestClient) -> None:
    response = client.post("/api/skills/estacao.limites/execute", json={
        "parameters": {"acoes": "resolver captcha do login\napagar os comprovantes", "modo": "full"},
    }).json()
    assert response["ok"] is True
    niveis = [item["nivel"] for item in response["result"]["acoes"]]
    assert niveis == ["confirmar", "irreversivel"]
    assert response["result"]["executado"] is False


def test_api_regras_devolve_fonte(client: TestClient) -> None:
    response = client.post("/api/skills/estacao.regras/execute", json={"parameters": {}}).json()
    assert response["ok"] is True
    assert response["result"]["fonte"].startswith("feder-cr/invisible_dots")


def test_api_erro_de_entrada_vira_ok_false(client: TestClient) -> None:
    response = client.post("/api/skills/estacao.agenda/execute", json={
        "parameters": {"automacoes": "sem campos"},
    }).json()
    assert response["ok"] is False
    assert response["error"]["code"]


def test_api_parametro_extra_recusado(client: TestClient) -> None:
    response = client.post("/api/skills/estacao.tarefa/execute", json={
        "parameters": {"objetivo": "ler o arquivo de ontem", "campo": 1},
    }).json()
    assert response["ok"] is False
    assert response["error"]["code"]


def test_api_skill_inexistente_404(client: TestClient) -> None:
    response = client.post("/api/skills/estacao.inexistente/execute", json={"parameters": {}})
    assert response.status_code == 404


def test_registry_executa_permissoes(tmp_path) -> None:
    registry = build_registry(tmp_path / "files")

    async def run():
        return await registry.execute("estacao.permissoes", {
            "politica": "computer.exec=ask\nfiles.read=allow", "modo": "full",
        }, False)

    result = asyncio.run(run())
    assert result["metrics"]["permissoes"] == 2
    assert result["executado"] is False
