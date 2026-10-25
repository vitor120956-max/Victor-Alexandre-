"""Testes da camada de revisão de código (0.25.0).

A camada é determinística: lê diff e achados em texto, não chama modelo, não
executa git e não publica comentário. As fixtures são diffs unificados
mínimos, escritos à mão.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.revisao import (
    CLASSES,
    LIMIAR_COBERTURA,
    LIMIAR_PRECISAO,
    MAX_ACHADOS,
    MAX_ARQUIVOS,
    MODOS,
    SEVERIDADES,
    SIMILARIDADE_DUPLICATA,
    TOLERANCIA_LINHA,
    RevisaoError,
    analisar_escopo,
    comparar_duplicatas,
    ler_achados,
    ler_diff,
    medir_cobertura,
    montar_lotes,
    normalizar_achados,
    propor_regras,
    verificar_posicao,
)
from server.skill_registry import build_registry

# ------------------------------------------------------------------ fixtures

DIFF = """diff --git a/src/app.py b/src/app.py
index 1111111..2222222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,6 @@
 import os
+import sys
+API_KEY = "sk-abcdefghijklmnopqrstuvwx"
 def main():
-    print("oi")
+    print("olá")
     return 0
diff --git a/src/test_app.py b/src/test_app.py
new file mode 100644
--- /dev/null
+++ b/src/test_app.py
@@ -0,0 +1,3 @@
+def test_main():
+    assert main() == 0
+
diff --git a/web/i18n/messages_pt.properties b/web/i18n/messages_pt.properties
--- a/web/i18n/messages_pt.properties
+++ b/web/i18n/messages_pt.properties
@@ -1 +1,2 @@
 hello=Oi
+bye=Tchau
diff --git a/web/i18n/messages_en.properties b/web/i18n/messages_en.properties
--- a/web/i18n/messages_en.properties
+++ b/web/i18n/messages_en.properties
@@ -1 +1,2 @@
 hello=Hi
+bye=Bye
diff --git a/package-lock.json b/package-lock.json
--- a/package-lock.json
+++ b/package-lock.json
@@ -1 +1,2 @@
 {}
+{"lockfileVersion": 3}
"""

DIFF_DOC = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Projeto
+Mais uma linha.
"""

DIFF_SEM_LINHAS = """diff --git a/publico/logo.png b/publico/logo.png
Binary files a/publico/logo.png and b/publico/logo.png differ
"""

DIFF_MIGRACAO = """diff --git a/migrations/001_add_email.sql b/migrations/001_add_email.sql
--- a/migrations/001_add_email.sql
+++ b/migrations/001_add_email.sql
@@ -1 +1,2 @@
 CREATE TABLE usuario (id INT);
+ALTER TABLE usuario ADD COLUMN email TEXT;
"""

DIFF_RENOMEADO = """diff --git a/src/antigo.py b/src/novo.py
similarity index 90%
rename from src/antigo.py
rename to src/novo.py
--- a/src/antigo.py
+++ b/src/novo.py
@@ -1 +1,2 @@
 x = 1
+y = 2
"""

ACHADOS = json.dumps(
    [
        {
            "file": "src/app.py",
            "line": 2,
            "severity": "critical",
            "source": "rule",
            "rule": "W0611",
            "message": "import sys não é usado neste módulo",
        },
        {
            "path": "src/app.py",
            "line": 3,
            "severity": "erro",
            "source": "agent",
            "message": "Import sys nao esta sendo usado",
        },
        {
            "file": "src/app.py",
            "line": 5,
            "severity": "warning",
            "source": "llm",
            "message": "Função longa demais, considere dividir em partes menores",
        },
        {
            "file": "src/app.py",
            "line": 5,
            "severity": "warning",
            "source": "llm",
            "message": "Função longa demais, considere dividir em partes menores",
        },
    ],
    ensure_ascii=False,
)

ACHADOS_LINHAS = """src/app.py:2 | critical | rule | W0611 | import sys não é usado
src/app.py:5 | warning | agent | | função longa demais
"""


def kinds(resultado: dict) -> set[str]:
    return {item["kind"] for item in resultado["findings"]}


@pytest.fixture()
def client(tmp_path) -> TestClient:
    from server.app import create_app

    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


# ------------------------------------------------------------------- leitura


def test_ler_diff_conta_arquivos_hunks_e_churn() -> None:
    arquivos = ler_diff(DIFF)
    assert [arquivo.caminho for arquivo in arquivos] == [
        "src/app.py",
        "src/test_app.py",
        "web/i18n/messages_pt.properties",
        "web/i18n/messages_en.properties",
        "package-lock.json",
    ]
    app = arquivos[0]
    assert (app.adicionadas, app.removidas, app.contexto) == (3, 1, 3)
    assert app.status == "modificado"
    assert len(app.hunks) == 1


def test_ler_diff_usa_um_como_contagem_omitida() -> None:
    hunk = ler_diff(DIFF_MIGRACAO)[0].hunks[0]
    assert (hunk.antiga_ini, hunk.antiga_qtd, hunk.nova_ini, hunk.nova_qtd) == (1, 1, 1, 2)


def test_ler_diff_marca_arquivo_novo_e_binario() -> None:
    arquivos = ler_diff(DIFF)
    assert arquivos[1].status == "adicionado"
    assert arquivos[1].antigo == ""
    binario = ler_diff(DIFF_SEM_LINHAS)[0]
    assert binario.binario is True
    assert binario.classe == "binario"


def test_ler_diff_reconhece_renomeacao() -> None:
    arquivo = ler_diff(DIFF_RENOMEADO)[0]
    assert arquivo.caminho == "src/novo.py"
    assert arquivo.antigo == "src/antigo.py"
    assert arquivo.status == "renomeado"


def test_ler_diff_classifica_por_caminho() -> None:
    classes = {arquivo.caminho: arquivo.classe for arquivo in ler_diff(DIFF)}
    assert classes["src/app.py"] == "codigo"
    assert classes["src/test_app.py"] == "teste"
    assert classes["web/i18n/messages_pt.properties"] == "config"
    assert classes["package-lock.json"] == "lockfile"
    assert classes["src/app.py"] in CLASSES


def test_ler_diff_marca_lockfile_como_fora_da_revisao() -> None:
    arquivos = {arquivo.caminho: arquivo for arquivo in ler_diff(DIFF)}
    assert arquivos["package-lock.json"].revisar is False
    assert arquivos["src/app.py"].revisar is True


def test_ler_diff_ignora_marcador_de_fim_de_arquivo() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -1 +1 @@\n-velho\n+novo\n\\ No newline at end of file\n"
    )
    arquivo = ler_diff(diff)[0]
    assert arquivo.adicionadas == 1
    assert arquivo.removidas == 1


def test_ler_diff_recusa_texto_vazio_ou_que_nao_e_diff() -> None:
    with pytest.raises(RevisaoError):
        ler_diff("   ")
    with pytest.raises(RevisaoError):
        ler_diff("apenas um texto qualquer sem cabeçalho")


def test_ler_diff_recusa_diff_gigante_e_arquivos_demais() -> None:
    with pytest.raises(RevisaoError):
        ler_diff("+" * 2_000_000)
    blocos = "".join(
        f"diff --git a/f{indice}.py b/f{indice}.py\n--- a/f{indice}.py\n"
        f"+++ b/f{indice}.py\n@@ -1 +1,2 @@\n a=1\n+b=2\n"
        for indice in range(MAX_ARQUIVOS + 1)
    )
    with pytest.raises(RevisaoError):
        ler_diff(blocos)


def test_modos_aceitos_estao_declarados() -> None:
    assert MODOS == ("lite", "full", "ultra")
    assert SEVERIDADES == ("blocker", "major", "minor", "nit")


# -------------------------------------------------------------------- escopo


def test_escopo_separa_revisavel_de_filtrado() -> None:
    resultado = analisar_escopo(diff=DIFF)
    assert resultado["metrics"]["arquivos"] == 5
    assert resultado["metrics"]["revisar"] == 4
    assert resultado["metrics"]["filtrar"] == 1
    assert resultado["metrics"]["segredos"] == 1
    assert resultado["analysis"] == "revisao.escopo"
    assert resultado["readOnly"] is True


def test_escopo_aponta_segredo_em_linha_nova() -> None:
    resultado = analisar_escopo(diff=DIFF)
    assert "segredo-no-diff" in kinds(resultado)
    segredo = next(item for item in resultado["findings"] if item["kind"] == "segredo-no-diff")
    assert segredo["group"] == "must"
    assert "src/app.py:3" in segredo["location"]


def test_escopo_nao_cobra_teste_quando_o_teste_esta_no_diff() -> None:
    assert "sem-teste" not in kinds(analisar_escopo(diff=DIFF))


def test_escopo_cobra_teste_de_codigo_novo_sem_teste() -> None:
    sem_teste = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1,2 @@
 x = 1
+y = 2
"""
    resultado = analisar_escopo(diff=sem_teste)
    assert "sem-teste" in kinds(resultado)


def test_escopo_cobra_rollback_de_migracao() -> None:
    resultado = analisar_escopo(diff=DIFF_MIGRACAO)
    assert "migracao-sem-rollback" in kinds(resultado)
    assert resultado["metrics"]["risco"] >= 4


def test_escopo_avisa_quando_o_diff_so_tem_documentacao() -> None:
    resultado = analisar_escopo(diff=DIFF_DOC)
    assert "diff-so-de-documentacao" in kinds(resultado)
    assert resultado["metrics"]["revisar"] == 0


def test_escopo_avisa_quando_nao_ha_linha_para_comentar() -> None:
    resultado = analisar_escopo(diff=DIFF_SEM_LINHAS)
    assert "diff-sem-linhas" in kinds(resultado)


def test_escopo_lite_so_devolve_bloqueios() -> None:
    resultado = analisar_escopo(diff=DIFF, modo="lite")
    assert all(item["group"] == "must" for item in resultado["findings"])
    assert resultado["questions"] == []


def test_escopo_ultra_devolve_perguntas() -> None:
    resultado = analisar_escopo(diff=DIFF, modo="ultra")
    assert len(resultado["questions"]) >= 2


def test_escopo_recusa_modo_invalido() -> None:
    with pytest.raises(RevisaoError):
        analisar_escopo(diff=DIFF, modo="turbo")


def test_escopo_rows_ordenam_por_risco_e_churn() -> None:
    rows = analisar_escopo(diff=DIFF)["rows"]
    assert len(rows) == 5
    riscos = [row["risco"] for row in rows]
    assert riscos == sorted(riscos, reverse=True)


def test_escopo_markdown_tem_titulo_veredito_e_limites() -> None:
    markdown = analisar_escopo(diff=DIFF)["markdown"]
    assert markdown.startswith("# Escopo da revisão")
    assert "**Veredito:**" in markdown
    assert "## Não verificado" in markdown


# --------------------------------------------------------------------- lotes


def test_lotes_juntam_codigo_e_teste() -> None:
    resultado = montar_lotes(diff=DIFF)
    assert resultado["metrics"]["lotes"] == 2
    assert resultado["metrics"]["arquivos"] == 4
    assert resultado["metrics"]["maior_lote"] == 2


def test_lotes_juntam_locales_do_mesmo_bundle() -> None:
    resultado = montar_lotes(diff=DIFF)
    rows = resultado["rows"]
    assert all(row["arquivos"] <= 2 for row in rows)
    assert resultado["metrics"]["tokens"] > 0


def test_lotes_recusam_teto_fora_da_faixa() -> None:
    with pytest.raises(RevisaoError):
        montar_lotes(diff=DIFF, max_arquivos=1)
    with pytest.raises(RevisaoError):
        montar_lotes(diff=DIFF, max_arquivos=51)


def test_lotes_recusam_diff_sem_arquivo_revisavel() -> None:
    with pytest.raises(RevisaoError):
        montar_lotes(diff=DIFF_DOC)


def test_lotes_avisam_quando_tudo_cai_em_um_lote() -> None:
    diff = "".join(
        f"diff --git a/src/f{indice}.py b/src/f{indice}.py\n--- a/src/f{indice}.py\n"
        f"+++ b/src/f{indice}.py\n@@ -1 +1,2 @@\n a=1\n+b={indice}\n"
        for indice in range(6)
    )
    resultado = montar_lotes(diff=diff)
    assert resultado["metrics"]["lotes"] == 1
    assert "lote-unico" in kinds(resultado)


# ------------------------------------------------------------------- achados


def test_achados_normalizam_severidade_e_fonte() -> None:
    resultado = normalizar_achados(achados=ACHADOS)
    rows = resultado["rows"]
    assert [row["severidade"] for row in rows] == ["blocker", "major", "minor"]
    assert rows[0]["fonte"] == "regra"
    assert rows[1]["fonte"] == "agente"
    assert resultado["metrics"]["brutos"] == 4
    assert resultado["metrics"]["normalizados"] == 3


def test_achados_juntam_repetido_exato() -> None:
    resultado = normalizar_achados(achados=ACHADOS)
    assert resultado["metrics"]["duplicados"] == 1
    assert "achados-duplicados" in kinds(resultado)


def test_achados_ordenam_do_mais_grave_para_o_mais_leve() -> None:
    rows = normalizar_achados(achados=ACHADOS)["rows"]
    ordem = {"blocker": 0, "major": 1, "minor": 2, "nit": 3}
    assert [ordem[row["severidade"]] for row in rows] == sorted(ordem[row["severidade"]] for row in rows)


def test_achados_respeitam_severidade_minima() -> None:
    resultado = normalizar_achados(achados=ACHADOS, severidade_minima="major")
    assert resultado["metrics"]["normalizados"] == 2
    assert all(row["severidade"] in {"blocker", "major"} for row in resultado["rows"])


def test_achados_respeitam_limite_de_pagina() -> None:
    resultado = normalizar_achados(achados=ACHADOS, limite=1)
    assert len(resultado["rows"]) == 1
    assert resultado["metrics"]["mostrados"] == 1


def test_achados_recusam_lista_sem_texto() -> None:
    achados = json.dumps([{"file": "src/app.py", "line": 1, "severity": "warning", "message": ""}])
    resultado = normalizar_achados(achados=achados)
    assert "sem-mensagem" in kinds(resultado)
    assert next(item for item in resultado["findings"] if item["kind"] == "sem-mensagem")["group"] == "must"


def test_achados_avisam_severidade_desconhecida() -> None:
    achados = json.dumps([{"file": "src/app.py", "line": 1, "severity": "urgente", "message": "algo aqui"}])
    resultado = normalizar_achados(achados=achados)
    assert "severidade-desconhecida" in kinds(resultado)
    assert resultado["rows"][0]["severidade"] == "minor"


def test_achados_inferem_fonte_pelo_id_de_regra() -> None:
    achados = json.dumps([{"file": "src/app.py", "line": 1, "severity": "warning", "rule": "R1", "message": "algo aqui"}])
    assert normalizar_achados(achados=achados)["rows"][0]["fonte"] == "regra"
    achados = json.dumps([{"file": "src/app.py", "line": 1, "severity": "warning", "message": "algo aqui"}])
    assert normalizar_achados(achados=achados)["rows"][0]["fonte"] == "agente"


def test_achados_avisam_inflacao_de_bloqueios() -> None:
    itens = [
        {"file": "src/app.py", "line": indice + 1, "severity": "critical", "message": f"bloqueio {indice}"}
        for indice in range(4)
    ]
    resultado = normalizar_achados(achados=json.dumps(itens))
    assert "severidade-inflada" in kinds(resultado)


def test_achados_recusam_parametros_fora_da_faixa() -> None:
    with pytest.raises(RevisaoError):
        normalizar_achados(achados=ACHADOS, limite=0)
    with pytest.raises(RevisaoError):
        normalizar_achados(achados=ACHADOS, severidade_minima="grave")


def test_ler_achados_aceita_json_linhas_e_objeto() -> None:
    assert len(ler_achados(ACHADOS)) == 4
    assert len(ler_achados(ACHADOS_LINHAS)) == 2
    objeto = json.dumps({"findings": json.loads(ACHADOS)})
    assert len(ler_achados(objeto)) == 4


def test_ler_achados_limpa_prefixo_de_caminho() -> None:
    achados = json.dumps([{"file": "b/src/app.py", "line": 1, "message": "algo aqui"}])
    assert ler_achados(achados)[0]["arquivo"] == "src/app.py"


def test_ler_achados_recusa_json_invalido_e_lista_vazia() -> None:
    with pytest.raises(RevisaoError):
        ler_achados("{quebrado")
    with pytest.raises(RevisaoError):
        ler_achados("[]")
    with pytest.raises(RevisaoError):
        ler_achados("   ")


def test_ler_achados_recusa_volume_acima_do_teto() -> None:
    with pytest.raises(RevisaoError):
        ler_achados("[" + ",".join('{"file":"a.py","line":1}' for _ in range(MAX_ACHADOS + 1)) + "]")


# ------------------------------------------------------------------- posição


def test_posicao_aceita_linha_adicionada_e_de_contexto() -> None:
    achados = json.dumps(
        [
            {"file": "src/app.py", "line": 2, "message": "linha adicionada"},
            {"file": "src/app.py", "line": 4, "message": "linha de contexto"},
        ]
    )
    resultado = verificar_posicao(diff=DIFF, achados=achados)
    assert [row["situacao"] for row in resultado["rows"]] == ["exato", "contexto"]
    assert resultado["metrics"]["precisao"] == 100.0


def test_posicao_aceita_linha_dentro_da_tolerancia() -> None:
    achados = json.dumps([{"file": "src/app.py", "line": 7, "message": "perto da adição"}])
    resultado = verificar_posicao(diff=DIFF, achados=achados, tolerancia=TOLERANCIA_LINHA)
    assert resultado["rows"][0]["situacao"] == "proximo"
    assert resultado["rows"][0]["sugestao"] == "linha 5"


def test_posicao_sem_tolerancia_acha_linha_inexistente() -> None:
    achados = json.dumps([{"file": "src/app.py", "line": 99, "message": "linha inventada"}])
    resultado = verificar_posicao(diff=DIFF, achados=achados)
    assert resultado["rows"][0]["situacao"] == "linha-inexistente"
    assert "linha-inexistente" in kinds(resultado)
    assert resultado["counts"]["must"] >= 1


def test_posicao_recusa_arquivo_fora_do_diff() -> None:
    achados = json.dumps([{"file": "src/outro.py", "line": 1, "message": "arquivo ausente"}])
    resultado = verificar_posicao(diff=DIFF, achados=achados)
    assert resultado["rows"][0]["situacao"] == "arquivo-fora-do-diff"
    assert resultado["metrics"]["precisao"] == 0.0


def test_posicao_sinaliza_precisao_abaixo_do_piso() -> None:
    achados = json.dumps(
        [
            {"file": "src/app.py", "line": 2, "message": "ok"},
            {"file": "src/outro.py", "line": 1, "message": "fora"},
            {"file": "src/app.py", "line": 99, "message": "inventada"},
        ]
    )
    resultado = verificar_posicao(diff=DIFF, achados=achados)
    assert resultado["metrics"]["precisao"] < LIMIAR_PRECISAO
    assert "precisao-baixa" in kinds(resultado)


def test_posicao_trata_comentario_sem_linha_como_de_arquivo() -> None:
    achados = json.dumps([{"file": "src/app.py", "message": "problema no arquivo"}])
    resultado = verificar_posicao(diff=DIFF, achados=achados)
    assert resultado["rows"][0]["situacao"] == "arquivo"
    assert resultado["metrics"]["precisao"] == 100.0


def test_posicao_recusa_tolerancia_fora_da_faixa() -> None:
    with pytest.raises(RevisaoError):
        verificar_posicao(diff=DIFF, achados=ACHADOS, tolerancia=51)


# ---------------------------------------------------------------- duplicatas


def test_duplicatas_acham_o_mesmo_problema_nas_duas_fontes() -> None:
    achados = json.dumps(
        [
            {"file": "src/app.py", "line": 2, "severity": "warning", "source": "rule", "message": "import sys não é usado neste módulo"},
            {"file": "src/app.py", "line": 3, "severity": "warning", "source": "agent", "message": "import sys nao e usado neste modulo"},
            {"file": "src/app.py", "line": 40, "severity": "minor", "source": "rule", "message": "função longa demais, considere dividir"},
        ]
    )
    resultado = comparar_duplicatas(achados=achados)
    assert resultado["metrics"]["duplicatas"] == 1
    assert resultado["metrics"]["grupos"] == 1
    assert "duplicata-entre-fontes" in kinds(resultado)
    assert resultado["rows"][0]["fontes"] == "agente + regra"


def test_duplicatas_bloqueiam_conflito_de_severidade() -> None:
    achados = json.dumps(
        [
            {"file": "src/app.py", "line": 2, "severity": "critical", "source": "rule", "message": "import sys não usado"},
            {"file": "src/app.py", "line": 3, "severity": "warning", "source": "agent", "message": "import sys não usado"},
        ]
    )
    resultado = comparar_duplicatas(achados=achados)
    assert resultado["metrics"]["conflitos"] == 1
    assert "conflito-severidade" in kinds(resultado)
    assert next(item for item in resultado["findings"] if item["kind"] == "conflito-severidade")["group"] == "must"


def test_duplicatas_cobram_a_outra_camada_quando_so_uma_revisou() -> None:
    so_regra = json.dumps(
        [
            {"file": "src/app.py", "line": 2, "severity": "warning", "source": "rule", "message": "import sys não é usado"},
            {"file": "src/app.py", "line": 40, "severity": "minor", "source": "rule", "message": "função longa demais"},
        ]
    )
    resultado = comparar_duplicatas(achados=so_regra)
    assert "fonte-unica" in kinds(resultado)
    assert resultado["metrics"]["duplicatas"] == 0


def test_duplicatas_ignoram_comentarios_em_arquivos_diferentes() -> None:
    achados = json.dumps(
        [
            {"file": "src/app.py", "line": 2, "severity": "warning", "source": "rule", "message": "import sys não usado"},
            {"file": "src/outro.py", "line": 2, "severity": "warning", "source": "agent", "message": "import sys não usado"},
        ]
    )
    assert comparar_duplicatas(achados=achados)["metrics"]["duplicatas"] == 0


def test_duplicatas_juntam_repeticao_transitiva() -> None:
    achados = json.dumps(
        [
            {"file": "src/app.py", "line": 2, "severity": "warning", "source": "rule", "message": "import sys não é usado neste módulo"},
            {"file": "src/app.py", "line": 3, "severity": "warning", "source": "agent", "message": "import sys não é usado no módulo"},
            {"file": "src/app.py", "line": 4, "severity": "warning", "source": "rule", "message": "import sys não é usado neste arquivo"},
        ]
    )
    assert comparar_duplicatas(achados=achados)["metrics"]["grupos"] == 1


def test_duplicatas_recusam_similaridade_fora_da_faixa() -> None:
    with pytest.raises(RevisaoError):
        comparar_duplicatas(achados=ACHADOS, similaridade=1.5)
    assert SIMILARIDADE_DUPLICATA == 0.5


# ------------------------------------------------------------------ cobertura


def test_cobertura_cobra_arquivo_revisavel_nao_lido() -> None:
    resultado = medir_cobertura(diff=DIFF, revisados="src/app.py")
    assert resultado["metrics"]["revisaveis"] == 4
    assert resultado["metrics"]["revisados"] == 1
    assert resultado["metrics"]["cobertura"] == 25.0
    assert "cobertura-baixa" in kinds(resultado)
    assert resultado["metrics"]["cobertura"] < LIMIAR_COBERTURA


def test_cobertura_completa_nao_gera_bloqueio() -> None:
    revisados = "src/app.py, src/test_app.py, web/i18n/messages_pt.properties, web/i18n/messages_en.properties"
    resultado = medir_cobertura(diff=DIFF, revisados=revisados)
    assert resultado["metrics"]["cobertura"] == 100.0
    assert resultado["counts"]["must"] == 0


def test_cobertura_avisa_caminho_que_nao_esta_no_diff() -> None:
    resultado = medir_cobertura(diff=DIFF, revisados="src/app.py\nsrc/inexistente.py")
    assert resultado["metrics"]["desconhecidos"] == 1
    assert "caminho-desconhecido" in kinds(resultado)


def test_cobertura_cobra_risco_alto_esquecido() -> None:
    resultado = medir_cobertura(diff=DIFF_MIGRACAO, revisados="")
    assert "risco-alto-sem-revisao" in kinds(resultado)
    assert resultado["metrics"]["risco_alto"] == 1


def test_cobertura_de_diff_so_com_filtrado_avisa() -> None:
    resultado = medir_cobertura(diff=DIFF_DOC, revisados="")
    assert "nada-a-revisar" in kinds(resultado)
    assert resultado["metrics"]["revisaveis"] == 0


def test_cobertura_mostra_status_por_arquivo() -> None:
    rows = medir_cobertura(diff=DIFF, revisados="src/app.py")["rows"]
    status = {row["arquivo"]: row["status"] for row in rows}
    assert status["src/app.py"] == "revisado"
    assert status["package-lock.json"] == "filtrado"
    assert status["src/test_app.py"] == "não revisado"


# -------------------------------------------------------------------- regras


def test_regras_montam_rule_json_valido() -> None:
    resultado = propor_regras(diff=DIFF)
    assert resultado["metrics"]["regras"] == 4
    inicio = resultado["markdown"].index("```json") + len("```json")
    fim = resultado["markdown"].index("```", inicio)
    documento = json.loads(resultado["markdown"][inicio:fim])
    assert set(documento) == {"rules"}
    assert [regra["path"] for regra in documento["rules"]][0] == "src/app.py"
    assert all(regra["merge_system_rule"] is True for regra in documento["rules"])


def test_regras_incluem_as_convencoes_do_projeto() -> None:
    resultado = propor_regras(diff=DIFF, convencoes="Erro sempre com contexto; log estruturado.")
    assert "Erro sempre com contexto" in resultado["markdown"]
    assert resultado["metrics"]["com_convencoes"] == 1


def test_regras_avisam_quando_nao_ha_convencoes() -> None:
    resultado = propor_regras(diff=DIFF)
    assert "sem-convencoes" in kinds(resultado)


def test_regras_avisam_repeticao_do_mesmo_guia() -> None:
    diff = "".join(
        f"diff --git a/src/f{indice}.py b/src/f{indice}.py\n--- a/src/f{indice}.py\n"
        f"+++ b/src/f{indice}.py\n@@ -1 +1,2 @@\n a=1\n+b={indice}\n"
        for indice in range(4)
    )
    resultado = propor_regras(diff=diff)
    assert resultado["metrics"]["repetidas"] == 3
    assert "regras-repetidas" in kinds(resultado)


def test_regras_respeitam_o_teto_e_avisam_os_omitidos() -> None:
    resultado = propor_regras(diff=DIFF, max_regras=1)
    assert resultado["metrics"]["regras"] == 1
    assert resultado["metrics"]["omitidos"] == 3
    assert "regras-omitidas" in kinds(resultado)


def test_regras_sem_caminho_revisavel_bloqueiam() -> None:
    resultado = propor_regras(diff=DIFF_DOC)
    assert "sem-regras" in kinds(resultado)
    assert resultado["counts"]["must"] >= 1


def test_regras_recusam_parametros_fora_da_faixa() -> None:
    with pytest.raises(RevisaoError):
        propor_regras(diff=DIFF, max_regras=0)
    with pytest.raises(RevisaoError):
        propor_regras(diff=DIFF, convencoes="x" * 20_001)


# ------------------------------------------------------------------ registro


def test_registro_tem_as_sete_skills_de_revisao(tmp_path) -> None:
    registro = build_registry(tmp_path / "files")
    itens = registro.list()
    revisao = [item for item in itens if item["id"].startswith("revisao.")]
    assert len(revisao) == 7
    assert {item["category"] for item in revisao} == {"Revisão"}
    assert len(itens) == 209
    assert all(item["sideEffects"] is False for item in revisao)


def test_registro_recusa_parametro_extra_nas_skills_de_revisao() -> None:
    from server.skill_registry import RevisaoEscopoInput

    with pytest.raises(Exception):
        RevisaoEscopoInput(diff=DIFF, extra="x")


def test_endpoint_de_revisao_responde_no_formato_comum(client: TestClient) -> None:
    resposta = client.post(
        "/api/skills/revisao.escopo/execute",
        json={"parameters": {"diff": DIFF}, "dryRun": False, "confirmed": True},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert corpo["result"]["analysis"] == "revisao.escopo"
    assert corpo["result"]["metrics"]["arquivos"] == 5
    assert isinstance(corpo["result"]["markdown"], str)


def test_endpoint_de_revisao_devolve_erro_de_entrada(client: TestClient) -> None:
    resposta = client.post(
        "/api/skills/revisao.escopo/execute",
        json={"parameters": {"diff": "texto que não é diff"}, "dryRun": False, "confirmed": True},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is False
    assert corpo["error"]["code"] == "SKILL_ERROR"


def test_endpoint_de_achados_nao_exige_confirmed(client: TestClient) -> None:
    resposta = client.post(
        "/api/skills/revisao.achados/execute",
        json={"parameters": {"achados": ACHADOS}},
    )
    assert resposta.status_code == 200
    assert resposta.json()["result"]["metrics"]["duplicados"] == 1
