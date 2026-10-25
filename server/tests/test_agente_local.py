"""Testes do agente local (0.39.0) — skills sem modelo nenhum.

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
    assert "209 skills" in texto
    assert "escreve código novo" in texto
    assert "storage/agente-local/skills.json" in texto
    assert "minhas skills locais" in texto


def test_readme_aponta_para_a_doc_do_agente():
    raiz = Path(__file__).resolve().parents[2]
    texto = (raiz / "README.md").read_text(encoding="utf-8")
    assert "docs/AGENTE-LOCAL.md" in texto
    assert "Agente local, sem modelo" in texto
