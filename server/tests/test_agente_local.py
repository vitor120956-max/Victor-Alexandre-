"""Testes do agente local (0.43.0) — skills sem modelo nenhum.

Nada aqui chama rede, provedor de IA ou subprocesso: o registro é um dublê, a
busca e a leitura da web são funções injetadas e as receitas são puras.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from server.agente_local import (
    RECEITAS,
    AgenteError,
    achar_receita,
    atender,
    carregar_locais,
    criar_skill,
    entrada_de_local,
    entrada_de_skill,
    executar_receita,
    extrair_parametros,
    formatar_resultado,
    indexar,
    normalizar,
    palavras,
    pesquisar,
    pontuar,
    procurar_na_web,
    texto_livre,
    _RECEITAS_POR_ID,
)
from server.app import create_app


# ------------------------------------------------------------------- dublês

SKILL_TEXTO = {
    "id": "text.analyze",
    "name": "Analisar texto",
    "description": "Conta palavras, caracteres, frases, tempo de leitura e termos frequentes.",
    "category": "Texto",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string", "title": "Texto", "format": "textarea", "minLength": 1}},
        "required": ["text"],
    },
}

SKILL_ARTIGO = {
    "id": "legal.article",
    "name": "Artigo de lei",
    "description": "Devolve o texto exato de um artigo do corpus legal brasileiro.",
    "category": "Legislação",
    "inputSchema": {
        "type": "object",
        "properties": {
            "documentId": {"type": "string", "title": "Documento", "enum": ["constituicao", "cdc", "lgpd"], "enumLabels": ["Constituição Federal", "Código de Defesa do Consumidor", "LGPD"]},
            "article": {"type": "string", "title": "Artigo"},
        },
        "required": ["documentId", "article"],
    },
}

SKILL_ARQUIVO = {
    "id": "files.read",
    "name": "Ler arquivo",
    "description": "Abre um arquivo de texto da área isolada.",
    "category": "Arquivos",
    "inputSchema": {
        "type": "object",
        "properties": {"path": {"type": "string", "title": "Arquivo"}},
        "required": ["path"],
    },
}

SKILL_EXPORTAR = {
    "id": "dados.exportar",
    "name": "Exportar planilha",
    "description": "Gera relatório em CSV com a quantidade de linhas pedida.",
    "category": "Dados",
    "inputSchema": {
        "type": "object",
        "properties": {"quantidade": {"type": "integer", "title": "Quantidade", "minimum": 1}},
        "required": ["quantidade"],
    },
}


SKILL_CONTROLE = {
    "id": "dados.controle",
    "name": "Controle de dados",
    "description": "Mostra o relatório de controle das últimas execuções.",
    "category": "Dados",
    "inputSchema": {
        "type": "object",
        "properties": {"periodo": {"type": "string", "title": "Período"}},
        "required": ["periodo"],
    },
}


SKILL_PLANILHA = {
    "id": "dados.planilha",
    "name": "Ler planilha",
    "description": "Abre uma planilha XLSX e lista as abas.",
    "category": "Dados",
    "inputSchema": {
        "type": "object",
        "properties": {"path": {"type": "string", "title": "Planilha"}},
        "required": ["path"],
    },
}


class RegistroFalso:
    """Imita o SkillRegistry: lista e executa, sem tocar em Python real."""

    def __init__(self, skills: list[dict[str, Any]], raiz: Path) -> None:
        self.skills = skills
        self.files_root = raiz
        self.execucoes: list[tuple[str, dict[str, Any]]] = []

    def list(self) -> list[dict[str, Any]]:
        return self.skills

    async def execute(self, skill_id: str, parameters: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        self.execucoes.append((skill_id, parameters))
        return {"summary": f"Skill {skill_id} executada com {len(parameters)} campo(s).", "eco": parameters}


def registro(*skills: dict[str, Any], raiz: Path) -> RegistroFalso:
    return RegistroFalso(list(skills), raiz)


def busca_falsa(**_: Any) -> dict[str, Any]:
    return {"rows": [{"titulo": "Como fazer pão", "url": "https://exemplo.com/pao"}, {"titulo": "Outro", "url": "https://exemplo.com/outro"}]}


def leitura_falsa(**_: Any) -> dict[str, Any]:
    return {"sections": ["## Conteúdo da página\n\nMisture a farinha com a água e sove por dez minutos."]}


# -------------------------------------------------------------- normalização

def test_normalizar_tira_acento_e_caixa():
    assert normalizar("Análise de TEXTO  Ção") == "analise de texto cao"


def test_palavras_ignora_curtas_vazias_e_repetidas():
    assert palavras("que a de texto texto analisar x") == ["texto", "analisar"]


# ------------------------------------------------------------------- índice

def test_indexar_usa_nome_descricao_e_campos():
    entrada = indexar([SKILL_TEXTO])[0]
    assert "analisar" in entrada.fortes
    assert "texto" in entrada.fortes
    assert "palavras" in entrada.fracos
    assert "textarea" not in entrada.fracos


def test_pesquisar_acha_pela_descricao():
    ranking = pesquisar("contar palavras", indexar([SKILL_TEXTO, SKILL_ARQUIVO]))
    assert ranking[0]["entrada"].skill_id == "text.analyze"
    assert 0 < ranking[0]["score"] <= 1


def test_pesquisar_nao_inventa_para_pedido_sem_relacao():
    assert pesquisar("qual a capital da frança", indexar([SKILL_TEXTO, SKILL_ARQUIVO])) == []


def test_pesquisar_ordena_do_maior_para_o_menor():
    ranking = pesquisar("ler arquivo de texto", indexar([SKILL_TEXTO, SKILL_ARQUIVO]))
    notas = [item["score"] for item in ranking]
    assert notas == sorted(notas, reverse=True)


def test_bonus_quando_o_nome_aparece_inteiro_na_frase():
    entrada = indexar([SKILL_TEXTO])[0]
    com_nome = pontuar("analisar texto", entrada)[0]
    sem_nome = pontuar("texto", entrada)[0]
    assert com_nome >= sem_nome


# -------------------------------------------------------------- texto livre

@pytest.mark.parametrize(
    "pedido, esperado",
    [
        ("analisar texto: a vida é bela", "a vida é bela"),
        ("contar as palavras de: um dois três", "um dois três"),
        ("transformar texto: tudo em maiúsculas", "tudo em maiúsculas"),
        ("por favor, analisar: linha única", "linha única"),
    ],
)
def test_texto_livre_tira_o_comando(pedido, esperado):
    assert texto_livre(pedido) == esperado


def test_texto_livre_nao_corta_url():
    assert texto_livre("veja https://exemplo.com/a:b") == "veja https://exemplo.com/a:b"


# ---------------------------------------------------------------- parâmetros

def test_extrair_texto_de_campo_unico():
    parametros, faltando = extrair_parametros("analisar texto: a vida é bela", SKILL_TEXTO["inputSchema"])
    assert parametros == {"text": "a vida é bela"}
    assert faltando == []


def test_extrair_enum_e_artigo():
    parametros, faltando = extrair_parametros("artigo 49 do CDC", SKILL_ARTIGO["inputSchema"])
    assert parametros == {"documentId": "cdc", "article": "49"}
    assert faltando == []


def test_extrair_caminho():
    parametros, _ = extrair_parametros("ler PDF documentos/relatorio.pdf", SKILL_ARQUIVO["inputSchema"])
    assert parametros["path"] == "documentos/relatorio.pdf"


def test_extrair_numero_inteiro():
    parametros, faltando = extrair_parametros("exportar 250 linhas", SKILL_EXPORTAR["inputSchema"])
    assert parametros == {"quantidade": 250}
    assert faltando == []


def test_campo_obrigatorio_sem_valor_vira_faltando():
    parametros, faltando = extrair_parametros("ler arquivo", SKILL_ARQUIVO["inputSchema"])
    assert parametros == {}
    assert faltando == ["path"]


def test_extrair_url():
    schema = {"properties": {"url": {"type": "string", "title": "Endereço"}}, "required": ["url"]}
    parametros, _ = extrair_parametros("abrir https://exemplo.com/pagina?x=1 agora", schema)
    assert parametros["url"] == "https://exemplo.com/pagina?x=1"


def test_extrair_lista_entre():
    schema = {"properties": {"entries": {"type": "string", "title": "Participantes", "format": "textarea"}}, "required": ["entries"]}
    parametros, _ = extrair_parametros("sortear entre Ana, Bruno e Carla", schema)
    assert parametros["entries"] == "Ana, Bruno e Carla"


def test_extrair_minutos():
    schema = {"properties": {"minutos": {"type": "integer", "title": "Minutos"}}, "required": ["minutos"]}
    parametros, _ = extrair_parametros("iniciar foco de 25 minutos", schema)
    assert parametros == {"minutos": 25}


# ------------------------------------------------------------------ receitas

@pytest.mark.parametrize(
    "pedido, receita",
    [
        ("contar as palavras de: um dois três", "contar-palavras"),
        ("quantos caracteres tem o texto", "contar-caracteres"),
        ("contar as linhas do texto", "contar-linhas"),
        ("extrair os links de: https://a.com", "extrair-links"),
        ("extrair os emails do texto", "extrair-emails"),
        ("extrair os números do texto", "extrair-numeros"),
        ("somar 10 20 30", "somar"),
        ("qual a média de 4 8 12", "media"),
        ("maior e menor de 4 9 2", "maior-menor"),
        ("quanto é 20% de 350", "porcentagem"),
        ("ordenar: Ana, Carla, Bruno", "ordenar"),
        ("remover repetidos de: Ana, Ana, Bruno", "unicos"),
        ("contar repetições em: Ana, Bruno, Ana", "frequencia"),
        ("deixar em maiúsculas: oi", "maiusculas"),
        ("deixar em minúsculas: OI", "minusculas"),
        ("criar slug de: Café com Pão", "slug"),
        ("inverter o texto: abc", "inverter"),
        ("converter 10 km em milhas", "converter-unidades"),
        ("quantos dias entre 01/01/2026 e 25/10/2026", "diferenca-datas"),
        ("hash sha256 de: senha", "hash-sha256"),
    ],
)
def test_achar_receita(pedido, receita):
    achada = achar_receita(pedido)
    assert achada is not None, pedido
    assert achada.id == receita


def test_achar_receita_devolve_none_para_pedido_sem_receita():
    assert achar_receita("qual a capital da frança") is None


def test_achar_receita_porcentagem_sem_a_palavra_porcento():
    assert achar_receita("20% de 350") is not None


@pytest.mark.parametrize(
    "receita, entrada, esperado",
    [
        ("contar-palavras", "um dois três", "3 palavras."),
        ("contar-caracteres", "abc", "3 caracteres no total"),
        ("contar-linhas", "a\nb\n\nc", "3 linhas"),
        ("extrair-links", "veja https://a.com", "https://a.com"),
        ("extrair-emails", "fale com ana@exemplo.com", "ana@exemplo.com"),
        ("extrair-numeros", "custou 12 e 30", "12, 30"),
        ("somar", "10 20 30", "= 60"),
        ("media", "4 8 12", "= 8"),
        ("maior-menor", "4 9 2", "Maior: 9"),
        ("porcentagem", "20% de 350", "70"),
        ("ordenar", "Carla, Ana", "Ana\nCarla"),
        ("unicos", "Ana, Ana, Bruno", "1 repetido removido"),
        ("frequencia", "Ana, Ana", "ana: 2×"),
        ("maiusculas", "oi", "OI"),
        ("minusculas", "OI", "oi"),
        ("slug", "Café com Pão", "cafe-com-pao"),
        ("inverter", "abc", "cba"),
        ("converter-unidades", "converter 10 km em milhas", "6,2137 milhas"),
        ("diferenca-datas", "entre 01/01/2026 e 02/01/2026", "1 dias"),
        ("hash-sha256", "abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    ],
)
def test_executar_receita(receita, entrada, esperado):
    assert esperado in executar_receita(_RECEITAS_POR_ID[receita], entrada)["resultado"]


def test_converter_unidades_recusa_grandeza_diferente():
    assert "coisas diferentes" in executar_receita(_RECEITAS_POR_ID["converter-unidades"], "10 kg em litros")["resultado"]


def test_converter_celsius_para_fahrenheit():
    assert "212 °F" in executar_receita(_RECEITAS_POR_ID["converter-unidades"], "100 celsius em fahrenheit")["resultado"]


def test_porcentagem_sem_padrao_pede_exemplo():
    assert "20%" in executar_receita(_RECEITAS_POR_ID["porcentagem"], "quanto é")["resultado"]


def test_todas_as_receitas_tem_operacao():
    for receita in RECEITAS:
        resultado = executar_receita(receita, "10 20 30" if receita.tipo == "numeros" else "um dois três")
        assert isinstance(resultado.get("resultado"), str)


# -------------------------------------------------------------- skills locais

def test_criar_skill_grava_arquivo(tmp_path):
    skill, criada = criar_skill(_RECEITAS_POR_ID["contar-palavras"], tmp_path)
    assert criada is True
    assert skill.id == "local.contar-palavras"
    arquivo = tmp_path / "agente-local" / "skills.json"
    assert arquivo.exists()
    conteudo = json.loads(arquivo.read_text(encoding="utf-8"))
    assert conteudo["skills"][0]["id"] == "local.contar-palavras"


def test_criar_skill_e_idempotente(tmp_path):
    primeira, criada = criar_skill(_RECEITAS_POR_ID["somar"], tmp_path)
    segunda, criada_de_novo = criar_skill(_RECEITAS_POR_ID["somar"], tmp_path)
    assert criada is True and criada_de_novo is False
    assert primeira.id == segunda.id
    assert len(carregar_locais(tmp_path)) == 1


def test_carregar_locais_arquivo_corrompido(tmp_path):
    arquivo = tmp_path / "agente-local" / "skills.json"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_text("{isso não é json", encoding="utf-8")
    assert carregar_locais(tmp_path) == []


def test_carregar_locais_ignora_receita_desconhecida(tmp_path):
    arquivo = tmp_path / "agente-local" / "skills.json"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_text(json.dumps({"skills": [{"id": "local.x", "receita": "nao-existe"}]}), encoding="utf-8")
    assert carregar_locais(tmp_path) == []


def test_entrada_de_local_fica_pesquisavel(tmp_path):
    skill, _ = criar_skill(_RECEITAS_POR_ID["contar-palavras"], tmp_path)
    entrada = entrada_de_local(skill)
    assert entrada.local is True
    assert entrada.receita == "contar-palavras"
    assert pesquisar("contar palavras", [entrada])[0]["entrada"].skill_id == skill.id


# ------------------------------------------------------------------ formato

def test_formatar_resultado_usa_summary():
    assert formatar_resultado({"summary": "Tudo certo."}) == "Tudo certo."


def test_formatar_resultado_lista_linhas():
    texto = formatar_resultado({"rows": [{"nome": "Ana"}, {"nome": "Bruno"}]})
    assert "Ana" in texto and "Bruno" in texto


def test_formatar_resultado_cai_para_json():
    assert "palavras" in formatar_resultado({"palavras": 3})


# ------------------------------------------------------------- agente: fluxo

def test_atender_executa_skill_com_confianca_alta(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        resultado = await atender("analisar texto: a vida é bela", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["acao"] == "executado"
        assert resultado["skill"]["id"] == "text.analyze"
        assert reg.execucoes == [("text.analyze", {"text": "a vida é bela"})]
    asyncio.run(run())



def test_atender_pede_parametro_que_falta(tmp_path):
    async def run():
        reg = registro(SKILL_ARQUIVO, raiz=tmp_path)
        resultado = await atender("ler arquivo", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["acao"] == "faltando"
        assert resultado["faltando"] == ["path"]
        assert "Arquivo" in resultado["resposta"]
        assert reg.execucoes == []
    asyncio.run(run())



def test_atender_sugere_quando_a_confianca_e_media_e_ha_empate(tmp_path):
    async def run():
        reg = registro(SKILL_EXPORTAR, SKILL_PLANILHA, raiz=tmp_path)
        resultado = await atender("planilha do mes passado", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["acao"] == "sugerir"
        assert "Exportar planilha" in resultado["resposta"]
    asyncio.run(run())


def test_atender_pede_o_campo_quando_a_skill_e_a_unica_parecida(tmp_path):
    async def run():
        reg = registro(SKILL_EXPORTAR, raiz=tmp_path)
        resultado = await atender("planilha do mes", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["acao"] == "faltando"
        assert resultado["faltando"] == ["quantidade"]
        assert "Exportar planilha" in resultado["resposta"]
    asyncio.run(run())



def test_atender_cria_skill_local_e_executa(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        resultado = await atender("contar as palavras de: um dois três", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["acao"] == "criado"
        assert resultado["skill"]["id"] == "local.contar-palavras"
        assert "3 palavras" in resultado["resposta"]
        assert "Criei" in resultado["resposta"]
        assert len(carregar_locais(tmp_path)) == 1
    asyncio.run(run())



def test_atender_reusa_skill_criada(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        await atender("contar as palavras de: um dois três", registry=reg, raiz=tmp_path, consultar_web=False)
        segundo = await atender("contar as palavras de: quatro cinco", registry=reg, raiz=tmp_path, consultar_web=False)
        assert segundo["acao"] in {"criado", "executado"}
        assert "2 palavras" in segundo["resposta"]
        assert len(carregar_locais(tmp_path)) == 1
    asyncio.run(run())



def test_atender_nao_executa_nada_na_faixa_media(tmp_path):
    async def run():
        reg = registro(SKILL_EXPORTAR, SKILL_PLANILHA, raiz=tmp_path)
        resultado = await atender("planilha do mes passado", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["acao"] == "sugerir"
        assert reg.execucoes == []
    asyncio.run(run())



def test_atender_vai_para_a_web_sem_ia(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        resultado = await atender(
            "como fazer pão caseiro",
            registry=reg,
            raiz=tmp_path,
            autorizacao="token",
            buscar=busca_falsa,
            ler=leitura_falsa,
        )
        assert resultado["acao"] == "web"
        assert resultado["fontes"][0]["url"] == "https://exemplo.com/pao"
        assert "sove por dez minutos" in resultado["resposta"]
        assert any("Não criei skill" in aviso for aviso in resultado["avisos"])
    asyncio.run(run())



def test_atender_web_sem_resultado_nao_quebra(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)

        def busca_vazia(**_: Any) -> dict[str, Any]:
            return {"rows": []}

        resultado = await atender("como fazer pão caseiro", registry=reg, raiz=tmp_path, autorizacao="t", buscar=busca_vazia, ler=leitura_falsa)
        assert resultado["acao"] in {"web", "nada"}
        assert resultado["avisos"]
    asyncio.run(run())



def test_atender_sem_web_quando_desligada(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        resultado = await atender("como fazer pão caseiro", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["acao"] == "nada"
        assert "ajuda" in resultado["resposta"]
    asyncio.run(run())



def test_atender_recusa_pedido_curto(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        with pytest.raises(AgenteError):
            await atender("oi", registry=reg, raiz=tmp_path)
    asyncio.run(run())



def test_atender_funciona_sem_provedor_nenhum(tmp_path):
    """O registro do dublê não conhece provedor: se algo pedisse IA, estouraria."""
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        resultado = await atender("analisar texto: um dois", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["acao"] == "executado"
        assert reg.execucoes and reg.execucoes[0][0] == "text.analyze"
    asyncio.run(run())



def test_procurar_na_web_sem_provedor_e_sem_busca_nao_estoura():
    async def run():
        def busca_quebrada(**_: Any) -> dict[str, Any]:
            raise RuntimeError("sem rede")

        from server.sistema import SistemaError

        def busca_recusa(**_: Any) -> dict[str, Any]:
            raise SistemaError("Falha de rede.")

        resultado = await procurar_na_web("qualquer coisa", autorizacao="t", buscar=busca_recusa, ler=leitura_falsa)
        assert resultado["acao"] == "nada"
        assert "Falha de rede" in resultado["avisos"][0]
    asyncio.run(run())



# ------------------------------------------------------------------- rotas

def test_rota_executa_skill(tmp_path):
    app = create_app(registry=registro(SKILL_TEXTO, raiz=tmp_path), agente_root=tmp_path)
    with TestClient(app) as cliente:
        resposta = cliente.post("/api/agente/executar", json={"pedido": "analisar texto: a vida é bela", "consultarWeb": False})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert corpo["result"]["acao"] == "executado"


def test_rota_recusa_pedido_curto(tmp_path):
    app = create_app(registry=registro(SKILL_TEXTO, raiz=tmp_path), agente_root=tmp_path)
    with TestClient(app) as cliente:
        resposta = cliente.post("/api/agente/executar", json={"pedido": "oi"})
    assert resposta.status_code == 422


def test_rota_cria_skill_local(tmp_path):
    app = create_app(registry=registro(SKILL_TEXTO, raiz=tmp_path), agente_root=tmp_path)
    with TestClient(app) as cliente:
        resposta = cliente.post("/api/agente/executar", json={"pedido": "somar 10 20 30", "consultarWeb": False})
        listagem = cliente.get("/api/agente/skills")
    assert resposta.status_code == 200
    assert resposta.json()["result"]["acao"] == "criado"
    corpo = listagem.json()["result"]
    assert len(corpo["receitas"]) == len(RECEITAS)
    assert corpo["locais"][0]["id"] == "local.somar"


def test_rota_lista_receitas_sem_skill_criada(tmp_path):
    app = create_app(registry=registro(SKILL_TEXTO, raiz=tmp_path), agente_root=tmp_path)
    with TestClient(app) as cliente:
        corpo = cliente.get("/api/agente/skills").json()["result"]
    assert corpo["locais"] == []
    assert {receita["id"] for receita in corpo["receitas"]} == {receita.id for receita in RECEITAS}


def test_doc_descreve_o_agente_local():
    raiz = Path(__file__).resolve().parents[2]
    texto = (raiz / "docs" / "AGENTE-LOCAL.md").read_text(encoding="utf-8")
    assert "225 skills" in texto
    assert "escreve código novo" in texto
    assert "storage/agente-local/skills.json" in texto
    assert "minhas skills locais" in texto


def test_readme_aponta_para_a_doc_do_agente():
    raiz = Path(__file__).resolve().parents[2]
    texto = (raiz / "README.md").read_text(encoding="utf-8")
    assert "docs/AGENTE-LOCAL.md" in texto
    assert "Agente local, sem modelo" in texto


# ------------------------------------------------- memória do agente (0.43.0)

from server.agente_local import (  # noqa: E402
    apelido_de,
    ensinar,
    ensinar_por_nome,
    esquecer,
    guardar_resposta,
    listar_fila,
    listar_historico,
    painel,
    parametros_explicitos,
    registrar_falha,
    registrar_execucao,
    remover_falha,
    remover_local,
    resposta_guardada,
)


def test_ensinar_guarda_apelido_e_executa_depois(tmp_path):
    async def run():
        reg = registro(SKILL_ARQUIVO, raiz=tmp_path)
        ensinar("meu relatorio do mes", "files.read", tmp_path)
        assert apelido_de("meu relatorio do mes", tmp_path)["skill_id"] == "files.read"
        resultado = await atender("meu relatorio do mes com path=documentos/relatorio.pdf", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["via"] == "apelido"
        assert resultado["acao"] == "executado"
        assert reg.execucoes[-1][0] == "files.read"
    asyncio.run(run())


def test_apelido_com_pedido_sem_parametro_pede_o_campo(tmp_path):
    async def run():
        reg = registro(SKILL_ARQUIVO, raiz=tmp_path)
        ensinar("abre meu arquivo", "files.read", tmp_path)
        resultado = await atender("abre meu arquivo", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["acao"] == "faltando"
        assert "Você me ensinou" in resultado["resposta"]
    asyncio.run(run())


def test_esquecer_remove_apelido_e_resposta(tmp_path):
    ensinar("pedido qualquer", "files.read", tmp_path)
    guardar_resposta("pedido qualquer", "texto", [], tmp_path)
    assert esquecer("pedido qualquer", tmp_path) == 2
    assert apelido_de("pedido qualquer", tmp_path) is None
    assert resposta_guardada("pedido qualquer", tmp_path) is None


def test_fila_guarda_o_que_nao_foi_resolvido(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        await atender("como fazer pão caseiro", registry=reg, raiz=tmp_path, consultar_web=False)
        fila = listar_fila(tmp_path)
        assert len(fila) == 1
        assert fila[0]["pedido"] == "como fazer pão caseiro"
        assert fila[0]["tentativas"] == 1
    asyncio.run(run())


def test_fila_conta_tentativas_sem_duplicar(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        await atender("como fazer pão caseiro", registry=reg, raiz=tmp_path, consultar_web=False)
        await atender("como fazer pão caseiro", registry=reg, raiz=tmp_path, consultar_web=False)
        fila = listar_fila(tmp_path)
        assert len(fila) == 1
        assert fila[0]["tentativas"] == 2
    asyncio.run(run())


def test_remover_falha(tmp_path):
    registro_falha = registrar_falha("pedido perdido", "motivo", tmp_path)
    assert remover_falha(registro_falha["id"], tmp_path) is True
    assert remover_falha(registro_falha["id"], tmp_path) is False
    assert listar_fila(tmp_path) == []


def test_resposta_guardada_volta_sem_pesquisar(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        guardar_resposta("quem inventou o pão", "Foi um padeiro.\n\n(fonte: https://exemplo.com)", [{"titulo": "Pão", "url": "https://exemplo.com", "lida": True}], tmp_path)
        resultado = await atender("quem inventou o pão", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["acao"] == "guardado"
        assert "padeiro" in resultado["resposta"]
        assert resultado["fontes"][0]["url"] == "https://exemplo.com"
        assert "esqueça" in resultado["resposta"]
    asyncio.run(run())


def test_forcar_web_guarda_a_resposta(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        resultado = await atender(
            "como fazer pão",
            registry=reg,
            raiz=tmp_path,
            autorizacao="t",
            buscar=busca_falsa,
            ler=leitura_falsa,
            forcar_web=True,
        )
        assert resultado["acao"] == "web"
        assert resposta_guardada("como fazer pão", tmp_path) is not None
        assert "sove por dez minutos" in resultado["resposta"]
    asyncio.run(run())


def test_historico_registra_o_que_foi_feito(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        await atender("analisar texto: a vida é bela", registry=reg, raiz=tmp_path, consultar_web=False)
        historico = listar_historico(tmp_path)
        assert historico[0]["acao"] == "executado"
        assert historico[0]["skill"] == "text.analyze"
        assert "a vida é bela" in historico[0]["pedido"]
    asyncio.run(run())


def test_historico_nao_cresce_sem_limite(tmp_path):
    for indice in range(5):
        registrar_execucao(f"pedido {indice}", acao="executado", skill="x.y", confianca=1.0, resposta="ok", raiz=tmp_path)
    assert len(listar_historico(tmp_path, limite=3)) == 3


def test_painel_junta_tudo(tmp_path):
    criar_skill(_RECEITAS_POR_ID["somar"], tmp_path)
    registrar_falha("pedido perdido", "motivo", tmp_path)
    dados = painel(tmp_path)
    assert len(dados["locais"]) == 1
    assert len(dados["receitas"]) == len(RECEITAS)
    assert len(dados["fila"]) == 1
    assert dados["apelidos"] == []
    assert dados["historico"] == []


def test_remover_local(tmp_path):
    skill, _ = criar_skill(_RECEITAS_POR_ID["somar"], tmp_path)
    assert remover_local(skill.id, tmp_path) is True
    assert remover_local(skill.id, tmp_path) is False
    assert carregar_locais(tmp_path) == []


def test_parametros_explicitos_converte_pelo_tipo():
    schema = {
        "properties": {
            "texto": {"type": "string"},
            "quantidade": {"type": "integer"},
            "taxa": {"type": "number"},
            "ativo": {"type": "boolean"},
        }
    }
    valores = parametros_explicitos("texto=olá mundo, quantidade=12, taxa=3,5, ativo=sim", schema)
    assert valores == {"texto": "olá mundo", "quantidade": 12, "taxa": 3.5, "ativo": True}


def test_parametros_explicitos_ignora_campo_desconhecido():
    assert parametros_explicitos("inventado=1", {"properties": {"texto": {"type": "string"}}}) == {}


def test_campo_explicito_cobre_skill_sem_texto(tmp_path):
    async def run():
        reg = registro(SKILL_ARQUIVO, raiz=tmp_path)
        resultado = await atender("ler arquivo path=documentos/relatorio.pdf", registry=reg, raiz=tmp_path, consultar_web=False)
        assert resultado["acao"] == "executado"
        assert resultado["parametros"] == {"path": "documentos/relatorio.pdf"}
    asyncio.run(run())


def test_ensinar_por_nome_aceita_id_e_nome(tmp_path):
    reg = registro(SKILL_TEXTO, raiz=tmp_path)
    ensinar_por_nome("resume isso", "text.analyze", tmp_path, reg)
    assert apelido_de("resume isso", tmp_path)["skill_id"] == "text.analyze"
    ensinar_por_nome("resume aquilo", "Analisar texto", tmp_path, reg)
    assert apelido_de("resume aquilo", tmp_path)["skill_id"] == "text.analyze"


def test_ensinar_por_nome_recusa_ambiguo(tmp_path):
    reg = registro(SKILL_TEXTO, SKILL_ARQUIVO, raiz=tmp_path)
    with pytest.raises(AgenteError):
        ensinar_por_nome("qualquer coisa", "zzz", tmp_path, reg)


def test_indice_nao_quebra_com_arquivo_corrompido(tmp_path):
    for nome in ("apelidos.json", "fila.json", "respostas.json", "historico.json"):
        arquivo = tmp_path / "agente-local" / nome
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text("não é json", encoding="utf-8")
    assert listar_fila(tmp_path) == []
    assert listar_historico(tmp_path) == []
    assert apelido_de("qualquer", tmp_path) is None
    assert resposta_guardada("qualquer", tmp_path) is None


# ------------------------------------- cobertura: as 225 skills, uma por uma

def _valor_de_exemplo(nome: str, spec: dict[str, Any]) -> Any:
    if spec.get("enum"):
        return spec["enum"][0]
    tipo = spec.get("type")
    chave = nome.lower()
    if tipo == "integer":
        return int(spec.get("minimum") if spec.get("minimum") is not None else 1)
    if tipo == "number":
        return float(spec.get("minimum") if spec.get("minimum") is not None else 1)
    if tipo == "boolean":
        return True
    if tipo == "array":
        return ["exemplo"]
    if "email" in chave:
        return "ana@exemplo.com"
    if "url" in chave or "link" in chave:
        return "https://exemplo.com/pagina"
    if "data" in chave or "date" in chave:
        return "2026-01-31"
    if "path" in chave or "arquivo" in chave or "caminho" in chave:
        return "documentos/relatorio.pdf"
    if "sha" in chave or "{64}" in str(spec.get("pattern") or ""):
        return "a" * 64
    minimo = int(spec.get("minLength") or 1)
    maximo = int(spec.get("maxLength") or 400)
    alvo = max(3, min(minimo, maximo))
    base = "exemplo de texto"
    texto = base
    while len(texto) < alvo:
        texto += " " + base
    texto = texto[:alvo]
    # espaço no fim é removido pela validação, então completa com uma letra
    return texto[:-1] + "x" if texto.endswith(" ") else texto


def _valores_para_schema(schema: dict[str, Any]) -> dict[str, Any]:
    propriedades = schema.get("properties") or {}
    return {
        campo: _valor_de_exemplo(campo, propriedades.get(campo) or {})
        for campo in schema.get("required") or []
    }


def test_todas_as_skills_podem_ser_preenchidas_pelo_caminho_explicito(tmp_path):
    """A promessa de cobertura: qualquer uma das 225 skills tem como ser rodada.

    Monta `campo=valor` para todo campo obrigatório de todo schema, relê com o
    mesmo parser que o chat usa e valida no modelo Pydantic da skill — sem
    executar nada.
    """
    from server.skill_registry import build_registry

    reg = build_registry(tmp_path)
    problemas: list[tuple[str, str]] = []
    for skill in reg.list():
        schema = skill["inputSchema"] or {}
        valores = _valores_para_schema(schema)
        consulta = "skill " + skill["id"] + " " + ", ".join(f"{campo}={valor}" for campo, valor in valores.items())
        lidos = parametros_explicitos(consulta, schema)
        faltando = [campo for campo in schema.get("required") or [] if campo not in lidos]
        if faltando:
            problemas.append((skill["id"], "não leu: " + ", ".join(faltando)))
            continue
        try:
            reg.get(skill["id"]).input_model.model_validate(lidos)
        except Exception as exc:  # schema recusou o exemplo
            problemas.append((skill["id"], str(exc).splitlines()[0][:120]))
    assert problemas == [], problemas[:10]


def test_pedidos_de_ocr_e_video_acham_as_skills_novas(tmp_path: Path):
    """As duas frentes da 0.43.0 entram pela busca por frase, como as outras."""
    from server.skill_registry import build_registry

    reg = build_registry(tmp_path)
    entradas = [entrada_de_skill(item) for item in reg.list()]
    casos = {
        "importar a foto da pagina Downloads/contrato.jpg": "biblioteca.importar",
        "importar o pdf escaneado Downloads/contrato.pdf": "biblioteca.importar",
        "baixar a legenda do video https://youtu.be/dQw4w9WgXcQ": "biblioteca.video",
        "qual o estado do ocr": "biblioteca.ocr",
    }
    for frase, esperada in casos.items():
        ranking = pesquisar(frase, entradas)
        assert ranking, frase
        assert ranking[0]["entrada"].skill_id == esperada, frase
        assert ranking[0]["score"] >= 0.5, (frase, ranking[0]["score"])


# ------------------------------------------------- confirmação de efeito

SKILL_BAIXAR = {
    "id": "repos.baixar",
    "name": "Baixar repositório",
    "description": "Baixa um repositório público do GitHub como .zip para storage/repos, sem Git instalado.",
    "category": "Repositórios",
    "requiresConfirmation": True,
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "title": "Repositório"},
            "autorizacao": {"type": "string", "title": "Autorização"},
        },
        "required": ["url"],
    },
}


def test_skill_com_efeito_pede_confirmacao_em_vez_de_executar(tmp_path: Path):
    duble = registro(SKILL_BAIXAR, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "baixar o repositório virgiliojr94/book-to-skill",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
        )
    )
    assert resultado["acao"] == "confirmar"
    assert resultado["parametros"]["url"] == "virgiliojr94/book-to-skill"
    assert "Responda “sim, pode”" in resultado["resposta"]
    assert duble.execucoes == []


def test_confirmacao_executa_a_skill_de_verdade(tmp_path: Path):
    duble = registro(SKILL_BAIXAR, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "baixar o repositório virgiliojr94/book-to-skill",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
            confirmar=True,
        )
    )
    assert resultado["acao"] == "executado"
    assert duble.execucoes == [("repos.baixar", {"url": "virgiliojr94/book-to-skill"})]


def test_confirmacao_nao_entra_na_fila_nem_no_historico(tmp_path: Path):
    duble = registro(SKILL_BAIXAR, raiz=tmp_path)
    asyncio.run(
        atender(
            "baixar o repositório virgiliojr94/book-to-skill",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
        )
    )
    from server.agente_local import listar_fila, listar_historico

    assert listar_fila(tmp_path) == []
    assert listar_historico(tmp_path) == []


def test_url_completa_do_github_tambem_vira_parametro(tmp_path: Path):
    duble = registro(SKILL_BAIXAR, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "baixar o repositório https://github.com/virgiliojr94/book-to-skill",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
        )
    )
    assert resultado["parametros"]["url"] == "https://github.com/virgiliojr94/book-to-skill"


def test_rota_do_agente_aceita_confirmar(tmp_path: Path):
    duble = registro(SKILL_BAIXAR, raiz=tmp_path)
    app = create_app(registry=duble, agente_root=tmp_path)
    with TestClient(app) as cliente:
        primeiro = cliente.post(
            "/api/agente/executar",
            json={"pedido": "baixar o repositório virgiliojr94/book-to-skill", "consultarWeb": False},
        ).json()
        assert primeiro["result"]["acao"] == "confirmar"
        segundo = cliente.post(
            "/api/agente/executar",
            json={
                "pedido": "baixar o repositório virgiliojr94/book-to-skill",
                "consultarWeb": False,
                "confirmar": True,
            },
        ).json()
        assert segundo["result"]["acao"] == "executado"


def test_confirmacao_repassa_a_autorizacao_para_skill(tmp_path: Path):
    duble = registro(SKILL_BAIXAR, raiz=tmp_path)
    asyncio.run(
        atender(
            "baixar o repositório virgiliojr94/book-to-skill",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
            confirmar=True,
            autorizacao="sim, pode",
        )
    )
    assert duble.execucoes[0][1]["autorizacao"] == "sim, pode"


class RegistroQueRecusa(RegistroFalso):
    async def execute(self, skill_id: str, parameters: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        self.execucoes.append((skill_id, parameters))
        raise RuntimeError("Só repositório público do GitHub.")


def test_erro_da_skill_aparece_em_vez_de_virar_sugestao(tmp_path: Path):
    duble = RegistroQueRecusa([SKILL_BAIXAR], tmp_path)
    resultado = asyncio.run(
        atender(
            "baixar o repositório virgiliojr94/book-to-skill",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
            confirmar=True,
            autorizacao="sim, pode",
        )
    )
    assert resultado["acao"] == "nada"
    assert "recusou o pedido" in resultado["resposta"]
    assert "Só repositório público" in resultado["resposta"]


def test_resumo_de_repositorio_no_chat():
    texto = formatar_resultado(
        {
            "slug": "dono--repo",
            "nome": "repo",
            "arquivos": 130,
            "bytes": 2_000_000,
            "sugestao": "Nada foi instalado nem executado.",
            "linguagens": [{"nome": "Python", "arquivos": 83}],
            "entradas": [{"comando": "python -m pacote", "porque": "tem __main__.py"}],
        }
    )
    assert "Baixei “repo” — 130 arquivos, 2.0 MB" in texto
    assert "Python (83)" in texto
    assert "python -m pacote" in texto
    assert "Nada foi instalado" in texto


def test_saida_de_execucao_no_chat():
    texto = formatar_resultado({"comando": "python main.py", "codigo": 0, "saida": "rodou 4", "erro": ""})
    assert "código 0" in texto
    assert "rodou 4" in texto


SKILL_EXEC_REPO = {
    "id": "repos.executar",
    "name": "Executar no repositório",
    "description": "Roda um comando dentro do repositório baixado.",
    "category": "Repositórios",
    "requiresConfirmation": True,
    "inputSchema": {
        "type": "object",
        "properties": {
            "repo": {"type": "string", "title": "Repositório"},
            "comando": {"type": "string", "title": "Comando"},
            "autorizacao": {"type": "string", "title": "Autorização"},
        },
        "required": ["repo", "comando"],
    },
}

SKILL_LER_REPO = {
    "id": "repos.ler",
    "name": "Ler arquivo do repositório",
    "description": "Mostra o texto de um arquivo de dentro do repositório.",
    "category": "Repositórios",
    "inputSchema": {
        "type": "object",
        "properties": {
            "repo": {"type": "string", "title": "Repositório"},
            "caminho": {"type": "string", "title": "Arquivo"},
        },
        "required": ["repo", "caminho"],
    },
}


def test_rodar_comando_no_repositorio_pede_confirmacao(tmp_path: Path):
    duble = registro(SKILL_EXEC_REPO, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "rodar python -m pacote --help no repositório dono--repo",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
        )
    )
    assert resultado["acao"] == "confirmar"
    assert resultado["parametros"] == {"repo": "dono--repo", "comando": "python -m pacote --help"}
    assert duble.execucoes == []


def test_rodar_comando_confirmado_leva_autorizacao(tmp_path: Path):
    duble = registro(SKILL_EXEC_REPO, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "rodar python -m pacote --help no repositório dono--repo",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
            confirmar=True,
            autorizacao="sim, pode",
        )
    )
    assert resultado["acao"] == "executado"
    assert duble.execucoes[0][1]["autorizacao"] == "sim, pode"


def test_ler_arquivo_do_repositorio_e_direto(tmp_path: Path):
    duble = registro(SKILL_LER_REPO, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "ler o README.md do repositório dono--repo",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
        )
    )
    assert resultado["acao"] == "executado"
    assert duble.execucoes == [("repos.ler", {"repo": "dono--repo", "caminho": "README.md"})]


def test_stderr_com_codigo_zero_nao_vira_erro():
    texto = formatar_resultado({"comando": "python -m x --help", "codigo": 0, "saida": "", "erro": "Usage: x"})
    assert "Avisos do programa" in texto
    assert "Erro:" not in texto


def test_resposta_vem_da_biblioteca_antes_da_web(tmp_path: Path, monkeypatch):
    from server import biblioteca

    monkeypatch.setattr(biblioteca.dados, "raiz", lambda: tmp_path)
    biblioteca.importar_texto(
        "Manual de custo",
        "O rateio do custo indireto distribui a despesa entre os produtos. "
        "O critério precisa ser estável e documentado, senão a margem mente. " * 3,
    )
    duble = registro(raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "como funciona o rateio de custo indireto",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
        )
    )
    assert resultado["acao"] == "biblioteca"
    assert resultado["via"] == "biblioteca"
    assert "Manual de custo" in resultado["resposta"]
    assert duble.execucoes == []


SKILL_CUSTOS = {
    "id": "custos.relatorio",
    "name": "Relatório de custos",
    "description": "Monta relatório de custos por centro.",
    "category": "Financeiro",
    "inputSchema": {
        "type": "object",
        "properties": {"centro": {"type": "string", "title": "Centro"}},
        "required": ["centro"],
    },
}


def test_biblioteca_vence_skill_de_confianca_media(tmp_path: Path, monkeypatch):
    from server import biblioteca

    monkeypatch.setattr(biblioteca.dados, "raiz", lambda: tmp_path)
    biblioteca.importar_texto(
        "Manual de custo",
        "O rateio do custo indireto distribui a despesa entre os produtos e precisa "
        "de critério estável, documentado e defensável para a margem não mentir. " * 3,
    )
    duble = registro(SKILL_CUSTOS, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "como funciona o rateio de custo indireto",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
        )
    )
    assert resultado["acao"] == "biblioteca"
    assert duble.execucoes == []
