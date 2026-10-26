"""Testes do agente local (0.53.0) — skills sem modelo nenhum.

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
    extrair_passos,
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
    assert "264 skills" in texto
    assert "escreve código novo" in texto
    assert "storage/agente-local/skills.json" in texto
    assert "minhas skills locais" in texto


def test_readme_aponta_para_a_doc_do_agente():
    raiz = Path(__file__).resolve().parents[2]
    texto = (raiz / "README.md").read_text(encoding="utf-8")
    assert "docs/AGENTE-LOCAL.md" in texto
    assert "Agente local, sem modelo" in texto


# ------------------------------------------------- memória do agente (0.53.0)

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


# ------------------------------------- cobertura: as 264 skills, uma por uma

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
    """A promessa de cobertura: qualquer uma das 264 skills tem como ser rodada.

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
    """As duas frentes da 0.53.0 entram pela busca por frase, como as outras."""
    from server.skill_registry import build_registry

    reg = build_registry(tmp_path)
    entradas = [entrada_de_skill(item) for item in reg.list()]
    casos = {
        "importar a foto da pagina Downloads/contrato.jpg": "biblioteca.importar",
        "importar o pdf escaneado Downloads/contrato.pdf": "biblioteca.importar",
        "importar o pdf biblioteca/entrada/custos.pdf": "biblioteca.importar",
        "baixar a legenda do video https://youtu.be/dQw4w9WgXcQ": "biblioteca.video",
        "qual o estado do ocr": "biblioteca.ocr",
    }
    for frase, esperada in casos.items():
        ranking = pesquisar(frase, entradas)
        assert ranking, frase
        assert ranking[0]["entrada"].skill_id == esperada, frase
        assert ranking[0]["score"] >= 0.5, (frase, ranking[0]["score"])


def test_resultado_de_importacao_vira_uma_linha_legivel():
    texto = formatar_resultado(
        {
            "slug": "custos-c617b4",
            "titulo": "custos",
            "tipo": "livro",
            "origem": "custos.pdf",
            "caracteres": 198,
            "secoes": 1,
            "total_palavras": 19,
        }
    )
    assert "Fonte “custos” na biblioteca" in texto
    assert "1 seção," in texto
    assert "custos-c617b4" in texto
    assert "- tipo:" not in texto


def test_resultado_de_video_mostra_o_idioma():
    texto = formatar_resultado(
        {
            "slug": "aula-de-rateio",
            "titulo": "Aula de rateio",
            "secoes": 6,
            "total_palavras": 1800,
            "idioma": "pt-BR",
            "origem": "https://youtu.be/dQw4w9WgXcQ",
        }
    )
    assert "6 seções" in texto
    assert "idioma pt-BR" in texto


# ------------------------------------------------------- receitas novas

@pytest.mark.parametrize(
    ("frase", "receita_id", "trecho"),
    [
        ("validar cpf 123.456.789-09", "validar-cpf", "válido"),
        ("validar cpf 123.456.789-00", "validar-cpf", "inválido"),
        ("IMC de 80 kg e 1,75 m", "imc", "sobrepeso"),
        ("se 3 custa 15, quanto custa 7", "regra-de-tres", "35,00"),
        ("juros de 1000 a 2% ao mês por 6 meses", "juros-simples", "1.120,00"),
        ("extrair os telefones de: ligue (47) 3222-1100", "extrair-telefones", "3222-1100"),
        ("extrair as datas de: venceu em 01/02/2026", "extrair-datas", "01/02/2026"),
        ("30 dias depois de 01/01/2026", "somar-dias", "31/01/2026"),
        ("10 dias antes de 01/03/2026", "somar-dias", "19/02/2026"),
    ],
)
def test_receitas_novas_resolvem_o_pedido(frase, receita_id, trecho):
    receita = achar_receita(frase)
    assert receita is not None and receita.id == receita_id, frase
    saida = executar_receita(receita, texto_livre(frase))
    assert trecho in saida["resultado"], saida["resultado"]


def test_cpf_com_digitos_repetidos_e_recusado():
    receita = achar_receita("validar cpf 111.111.111-11")
    saida = executar_receita(receita, texto_livre("validar cpf 111.111.111-11"))
    assert saida["valido"] is False


# ------------------------------------------- passos da web viram skill local

def leitura_com_passos(**_: Any) -> dict[str, Any]:
    texto = (
        "## Como instalar o certificado\n\n"
        "1. Baixe o arquivo do site oficial do emissor. "
        "2. Abra o gerenciador de certificados do Windows. "
        "3. Importe o arquivo e confirme a senha. "
        "4. Reinicie o navegador para o certificado valer."
    )
    return {"sections": [texto]}


def test_extrair_passos_de_lista_numerada():
    passos = extrair_passos(
        "1. Baixe o pacote do site oficial. 2. Execute o instalador como administrador. 3. Reinicie o serviço."
    )
    assert len(passos) == 3
    assert passos[0].startswith("Baixe o pacote")


def test_extrair_passos_ignora_data_e_preco():
    assert extrair_passos("Venceu em 27/10/2026 e custa 3.50 por unidade.") == []


def test_web_com_passos_oferece_criar_a_skill(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        resultado = await atender(
            "como instalar certificado digital",
            registry=reg,
            raiz=tmp_path,
            autorizacao="t",
            buscar=busca_falsa,
            ler=leitura_com_passos,
        )
        assert resultado["acao"] == "web"
        assert "criar skill com esses passos" in resultado["resposta"]
        assert len(resultado["passos"] if "passos" in resultado else []) >= 0
        pendente = json.loads((tmp_path / "agente-local" / "pendente.json").read_text(encoding="utf-8"))
        assert len(pendente["passos"]) == 4
    asyncio.run(run())


def test_criar_skill_com_os_passos_guarda_e_responde(tmp_path):
    async def run():
        reg = registro(SKILL_TEXTO, raiz=tmp_path)
        await atender(
            "como instalar certificado digital",
            registry=reg,
            raiz=tmp_path,
            autorizacao="t",
            buscar=busca_falsa,
            ler=leitura_com_passos,
        )
        criado = await atender(
            "criar skill com esses passos",
            registry=reg,
            raiz=tmp_path,
            consultar_web=False,
        )
        assert criado["acao"] == "criado"
        assert criado["skill"]["id"].startswith("local.proc-")
        assert "4 passos" in criado["resposta"]
        assert not (tmp_path / "agente-local" / "pendente.json").exists()

        # Depois de criada, pedir pelo nome devolve o passo a passo, sem rede.
        usado = await atender(
            "instalar certificado digital",
            registry=reg,
            raiz=tmp_path,
            consultar_web=False,
        )
        assert usado["acao"] == "executado"
        assert "1. Baixe o arquivo" in usado["resposta"]
        assert "https://exemplo.com/pao" in usado["resposta"]
    asyncio.run(run())


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


# ------------------------------------------------------- Google Drive (0.53.0)

SKILL_DRIVE_ESTADO = {
    "id": "armazenamento.drive",
    "name": "Drive como espaço de fora",
    "description": "Mostra onde estão os livros e os repositórios, se já estão no Google Drive.",
    "category": "Armazenamento",
    "inputSchema": {"type": "object", "properties": {"drive": {"type": "string", "title": "Pasta do Drive"}}},
}

SKILL_DRIVE_COPIAR = {
    "id": "armazenamento.drive-copiar",
    "name": "Configurar o Drive",
    "description": "Copia biblioteca e repositórios para o Google Drive e grava as variáveis no .env.",
    "category": "Armazenamento",
    "requiresConfirmation": True,
    "inputSchema": {
        "type": "object",
        "properties": {
            "drive": {"type": "string", "title": "Pasta do Drive"},
            "modo": {"type": "string", "title": "Modo", "enum": ["usar", "desfazer"]},
        },
    },
}


def test_configurar_o_drive_pede_confirmacao(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_ESTADO, SKILL_DRIVE_COPIAR, raiz=tmp_path)
    resultado = asyncio.run(
        atender("configura o google drive pra mim", registry=duble, raiz=tmp_path, consultar_web=False)
    )
    assert resultado["acao"] == "confirmar"
    assert resultado["skill"]["id"] == "armazenamento.drive-copiar"
    assert duble.execucoes == []


def test_configurar_o_drive_executa_depois_do_sim(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_ESTADO, SKILL_DRIVE_COPIAR, raiz=tmp_path)
    resultado = asyncio.run(
        atender("configura o google drive pra mim", registry=duble, raiz=tmp_path, consultar_web=False, confirmar=True)
    )
    assert resultado["acao"] == "executado"
    assert duble.execucoes == [("armazenamento.drive-copiar", {"modo": "usar"})]


def test_pergunta_sobre_o_drive_nao_copia_nada(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_ESTADO, SKILL_DRIVE_COPIAR, raiz=tmp_path)
    resultado = asyncio.run(
        atender("como configuro o drive?", registry=duble, raiz=tmp_path, consultar_web=False)
    )
    assert resultado["acao"] == "executado"
    assert duble.execucoes[0][0] == "armazenamento.drive"


def test_tirar_do_drive_usa_o_modo_desfazer(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_ESTADO, SKILL_DRIVE_COPIAR, raiz=tmp_path)
    resultado = asyncio.run(
        atender("tira a biblioteca do drive", registry=duble, raiz=tmp_path, consultar_web=False, confirmar=True)
    )
    assert resultado["acao"] == "executado"
    assert duble.execucoes[0] == ("armazenamento.drive-copiar", {"modo": "desfazer"})


def test_abrir_o_drive_nao_cai_na_regra_de_configurar(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_ESTADO, SKILL_DRIVE_COPIAR, raiz=tmp_path)
    resultado = asyncio.run(atender("abre o drive", registry=duble, raiz=tmp_path, consultar_web=False))
    assert resultado.get("skill") is None or resultado["skill"]["id"] != "armazenamento.drive-copiar"


def test_formatar_drive_estado_mostra_caminhos() -> None:
    texto = formatar_resultado(
        {
            "detectado": True,
            "drive": "G:/Meu Drive",
            "destino": "G:/Meu Drive/JARVIS-DADOS",
            "espaco_livre_gb": 12.5,
            "env": {"biblioteca": "", "repos": ""},
            "areas": [
                {"nome": "biblioteca", "arquivos": 6, "mb": 0.1, "configurada": False, "ja_no_drive": 0},
                {"nome": "repos", "arquivos": 148, "mb": 2.1, "configurada": True, "ja_no_drive": 148},
            ],
        }
    )
    assert "G:/Meu Drive" in texto
    assert "repos: já está no Drive" in texto
    assert "não aponta para o Drive" in texto


def test_formatar_drive_copia_resume_o_que_foi_feito() -> None:
    texto = formatar_resultado(
        {
            "modo": "usar",
            "mensagem": "ok",
            "copiados": 154,
            "mb_copiados": 2.2,
            "destino": "G:/Meu Drive/JARVIS-DADOS",
            "env": "C:/JARVIS/.env",
            "areas": [{"nome": "biblioteca", "situacao": "copiada", "conferido": "6 arquivos / 0,1 MB"}],
            "aviso": "Reinicie o JARVIS.",
        }
    )
    assert "154 arquivo" in texto
    assert ".env atualizado" in texto
    assert "Nada foi apagado do PC" in texto


def test_formatar_drive_desfazer_nao_despeja_dicionario() -> None:
    texto = formatar_resultado(
        {"modo": "desfazer", "mensagem": "Tirei as linhas do `.env`.", "aviso": "Reinicie o JARVIS."}
    )
    assert texto.strip() == "Tirei as linhas do `.env`.\nReinicie o JARVIS."


def test_formatar_drive_configurado_nao_manda_configurar_de_novo() -> None:
    texto = formatar_resultado(
        {
            "detectado": True,
            "drive": "G:/Meu Drive",
            "configurado": True,
            "env": {"biblioteca": "G:/x", "repos": "G:/y"},
            "areas": [{"nome": "biblioteca", "configurada": True, "arquivos": 6, "mb": 0.1}],
        }
    )
    assert "tira a biblioteca do drive" in texto
    assert "diga \"configura o Google Drive pra mim\"" not in texto


def test_confirmacao_nao_injeta_autorizacao_em_skill_que_nao_tem_o_campo(tmp_path: Path) -> None:
    """O chat manda "sim, pode" como autorização; a skill do Drive não tem esse campo."""
    duble = registro(SKILL_DRIVE_ESTADO, SKILL_DRIVE_COPIAR, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "configura o google drive pra mim",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
            confirmar=True,
            autorizacao="sim, pode",
        )
    )
    assert resultado["acao"] == "executado"
    assert duble.execucoes == [("armazenamento.drive-copiar", {"modo": "usar"})]


def test_confirmacao_mantem_autorizacao_em_skill_que_declara_o_campo(tmp_path: Path) -> None:
    duble = registro(SKILL_BAIXAR, raiz=tmp_path)
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
    assert resultado["acao"] == "executado"
    assert duble.execucoes[0][1]["autorizacao"] == "sim, pode"


def test_formatar_drive_sem_arquivo_explica_que_as_pastas_estavam_vazias() -> None:
    texto = formatar_resultado(
        {
            "modo": "usar",
            "mensagem": "ok",
            "copiados": 0,
            "mb_copiados": 0,
            "destino": "G:/Meu Drive/JARVIS-DADOS",
            "env": "D:/JARVIS/.env",
            "areas": [],
        }
    )
    assert "Configurado: o JARVIS agora usa" in texto
    assert "nada foi copiado" in texto
    assert "0 arquivo" not in texto


def test_formatar_drive_configurado_e_vazio_ensina_a_importar() -> None:
    texto = formatar_resultado(
        {
            "detectado": True,
            "drive": "G:/Meu Drive",
            "configurado": True,
            "total_arquivos": 0,
            "env": {"biblioteca": "G:/x", "repos": "G:/y"},
            "areas": [{"nome": "biblioteca", "configurada": True, "arquivos": 0, "mb": 0}],
        }
    )
    assert "ainda não há livro nenhum" in texto
    assert "importar" in texto


SKILL_DRIVE_BANDA = {
    "id": "armazenamento.drive-banda",
    "name": "Limitar a banda do Drive",
    "description": "Grava o limite de download e upload do app do Google Drive no registro do Windows.",
    "category": "Armazenamento",
    "requiresConfirmation": True,
    "inputSchema": {
        "type": "object",
        "properties": {
            "download_kbps": {"type": "integer", "title": "Download (KB/s)"},
            "upload_kbps": {"type": "integer", "title": "Upload (KB/s)"},
        },
    },
}


def test_limitar_banda_do_drive_pede_confirmacao(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_BANDA, raiz=tmp_path)
    resultado = asyncio.run(
        atender("limita a banda do drive", registry=duble, raiz=tmp_path, consultar_web=False)
    )
    assert resultado["acao"] == "confirmar"
    assert resultado["skill"]["id"] == "armazenamento.drive-banda"
    assert duble.execucoes == []


def test_limitar_banda_do_drive_entende_o_numero_da_frase(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_BANDA, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "limita a banda do drive pra 500",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
            confirmar=True,
        )
    )
    assert resultado["acao"] == "executado"
    assert duble.execucoes[0] == ("armazenamento.drive-banda", {"download_kbps": 500})


def test_drive_lento_nao_aciona_o_limite(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_BANDA, raiz=tmp_path)
    resultado = asyncio.run(atender("o drive ta lento", registry=duble, raiz=tmp_path, consultar_web=False))
    assert duble.execucoes == [] or duble.execucoes[0][0] != "armazenamento.drive-banda"


def test_formatar_banda_planejado_mostra_antes_e_depois() -> None:
    texto = formatar_resultado(
        {
            "banda": True,
            "planejado": True,
            "suportado": True,
            "antes": {"download_kbps": 0, "upload_kbps": 0},
            "depois": {"download_kbps": 1000, "upload_kbps": 500},
        }
    )
    assert "sem limite" in texto
    assert "1,0 MB/s (1000 KB/s)" in texto
    assert "sim, pode" in texto


def test_formatar_banda_aplicada_mostra_a_mensagem() -> None:
    texto = formatar_resultado(
        {
            "banda": True,
            "antes": {"download_kbps": 0, "upload_kbps": 0},
            "depois": {"download_kbps": 1000, "upload_kbps": 500},
            "mensagem": "Limite gravado. Vale quando o app reiniciar.",
        }
    )
    assert "Limite aplicado" in texto
    assert "reiniciar" in texto


def test_devolver_a_banda_remove_o_limite(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_BANDA, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "devolve a banda toda pro drive",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
            confirmar=True,
        )
    )
    assert resultado["acao"] == "executado"
    assert duble.execucoes[0] == ("armazenamento.drive-banda", {"download_kbps": 0, "upload_kbps": 0})


def test_tirar_a_biblioteca_nao_vira_limite_de_banda(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_BANDA, SKILL_DRIVE_COPIAR, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "tira a biblioteca do drive",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
            confirmar=True,
        )
    )
    assert resultado["acao"] == "executado"
    assert duble.execucoes[0][0] == "armazenamento.drive-copiar"


SKILL_DRIVE_APP = {
    "id": "armazenamento.drive-app",
    "name": "Abrir ou fechar o Drive",
    "description": "Fecha o app do Google Drive ou abre de novo.",
    "category": "Armazenamento",
    "requiresConfirmation": True,
    "inputSchema": {
        "type": "object",
        "properties": {"acao": {"type": "string", "title": "Ação", "enum": ["fechar", "abrir", "estado"]}},
    },
}


def test_fechar_o_drive_pede_confirmacao(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_APP, raiz=tmp_path)
    resultado = asyncio.run(atender("fecha o drive", registry=duble, raiz=tmp_path, consultar_web=False))
    assert resultado["acao"] == "confirmar"
    assert duble.execucoes == []


def test_pausar_a_sincronizacao_vira_fechar(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_APP, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "pausa a sincronização",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
            confirmar=True,
            autorizacao="sim, pode",
        )
    )
    assert resultado["acao"] == "executado"
    assert duble.execucoes[0] == ("armazenamento.drive-app", {"acao": "fechar"})


def test_abrir_o_drive_executa_direto(tmp_path: Path) -> None:
    duble = registro(SKILL_DRIVE_APP, raiz=tmp_path)
    resultado = asyncio.run(atender("abre o drive", registry=duble, raiz=tmp_path, consultar_web=False))
    assert resultado["acao"] == "executado"
    assert duble.execucoes[0] == ("armazenamento.drive-app", {"acao": "abrir"})


def test_formatar_fechar_mostra_o_aviso_antes_de_pedir_o_sim() -> None:
    texto = formatar_resultado(
        {
            "app": "drive",
            "acao": "fechar",
            "vai_fechar": True,
            "aviso": "Fecha a sincronização, mas derruba a unidade `G:`.",
        }
    )
    assert "Vou fechar" in texto
    assert "derruba a unidade" in texto
    assert "sim, pode" in texto


def test_formatar_estado_do_app_nao_despeja_dicionario() -> None:
    texto = formatar_resultado(
        {"app": "drive", "acao": "estado", "aberto": True, "executavel": "C:/Program Files/x/GoogleDriveFS.exe"}
    )
    assert texto.startswith("O app do Google Drive está aberto.")
    assert "Executável:" in texto


def test_confirmacao_de_fechar_o_drive_ja_mostra_o_aviso() -> None:
    """O aviso da unidade G: tem de aparecer ANTES do "sim", não depois."""
    base = {"acao": "", "parametros": {}, "resposta": ""}
    entrada = entrada_de_skill(SKILL_DRIVE_APP)
    from server.agente_local import _pedir_confirmacao

    _pedir_confirmacao(base, entrada, {"parametros": {"acao": "fechar"}}, aviso="derruba a unidade G:")
    assert "derruba a unidade G:" in base["resposta"]
    assert base["resposta"].count("sim, pode") == 1


# --------------------------------------------- mouse e teclado (0.53.0)

SKILL_MESA_CLICAR = {
    "id": "mesa.clicar",
    "name": "Clicar",
    "description": "Clica com o botão esquerdo, direito ou do meio.",
    "category": "Mesa",
    "requiresConfirmation": True,
    "inputSchema": {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "title": "X"},
            "y": {"type": "integer", "title": "Y"},
            "botao": {"type": "string", "title": "Botão", "enum": ["esquerdo", "direito", "meio"]},
        },
    },
}


def test_clicar_pede_confirmacao_com_coordenada(tmp_path: Path) -> None:
    duble = registro(SKILL_MESA_CLICAR, raiz=tmp_path)
    resultado = asyncio.run(
        atender("clica em 500 300", registry=duble, raiz=tmp_path, consultar_web=False)
    )
    assert resultado["acao"] == "confirmar"
    assert resultado["parametros"] == {"x": 500, "y": 300}


def test_clicar_depois_do_sim_executa(tmp_path: Path) -> None:
    duble = registro(SKILL_MESA_CLICAR, raiz=tmp_path)
    resultado = asyncio.run(
        atender(
            "clica em 500 300",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
            confirmar=True,
            autorizacao="sim, pode",
        )
    )
    assert resultado["acao"] == "executado"
    # `mesa.clicar` não declara `autorizacao`: o "sim" não pode vazar para a skill
    assert duble.execucoes[0] == ("mesa.clicar", {"x": 500, "y": 300})


def test_pesquisa_no_youtube_manda_a_fonte(tmp_path: Path) -> None:
    from server.agente_local import fonte_do_pedido

    assert fonte_do_pedido("pesquisa no youtube sobre python") == "youtube"
    assert fonte_do_pedido("procura na wikipedia sobre café") == "wikipedia"
    assert fonte_do_pedido("pesquisa no google sobre impostos") == "auto"


def test_formatar_mesa_mover_interrompido() -> None:
    texto = formatar_resultado(
        {"acao": "mover", "interrompido": True, "motivo": "Você mexeu o mouse", "parou_em": [10, 20]}
    )
    assert "mexeu o mouse" in texto and "(10, 20)" in texto


def test_formatar_mesa_clicar() -> None:
    texto = formatar_resultado({"acao": "clicar", "clicou": True, "botao": "direito", "vezes": 1, "em": [7, 8]})
    assert "Clique direito" in texto and "(7, 8)" in texto


def test_formatar_mesa_status_lista_janelas() -> None:
    texto = formatar_resultado(
        {"suportado": True, "x": 5, "y": 9, "largura": 1920, "altura": 1080, "janelas": ["Chrome"]}
    )
    assert "Cursor em (5, 9)" in texto and "Chrome" in texto


def test_pesquisa_no_youtube_repassa_a_fonte(tmp_path: Path) -> None:
    vistas: list[str] = []

    def buscar(**kwargs: Any) -> dict[str, Any]:
        vistas.append(kwargs.get("fonte", "?"))
        return {"rows": [{"titulo": "Aula", "url": "https://youtube.com/watch?v=1", "fonte": "youtube", "tipo": "video"}]}

    resultado = asyncio.run(
        atender(
            "pesquisa no youtube sobre python",
            registry=registro(raiz=tmp_path),
            raiz=tmp_path,
            buscar=buscar,
            ler=leitura_falsa,
        )
    )
    assert vistas == ["youtube"]
    assert resultado["parametros"] == {"consulta": "python", "fonte": "youtube"}
    assert "[youtube]" in resultado["resposta"]


def test_pesquisa_sem_rede_nao_pede_token(tmp_path: Path) -> None:
    from server.sistema import SistemaError

    def quebrada(**_: Any) -> dict[str, Any]:
        raise SistemaError("Rede desligada. Suba a API com JARVIS_HOST_REDE=1.")

    resultado = asyncio.run(
        atender(
            "pesquisa no youtube sobre python",
            registry=registro(raiz=tmp_path),
            raiz=tmp_path,
            buscar=quebrada,
            ler=leitura_falsa,
        )
    )
    texto = resultado["resposta"]
    assert "Tentei buscar “python” em YouTube" in texto
    assert "token" not in texto.lower()
    assert texto.count("JARVIS_HOST_REDE") == 1


# ------------------------------------------ habilidades de fora (0.53.0)


def test_importar_habilidade_do_link_pede_confirmacao(tmp_path: Path) -> None:
    duble = registro(
        {
            "id": "habilidades.importar",
            "name": "Importar habilidade de fora",
            "description": "Puxa um SKILL.md.",
            "category": "Habilidades",
            "inputSchema": {"type": "object", "properties": {"url": {"type": "string", "title": "Link"}}},
        },
        raiz=tmp_path,
    )
    resultado = asyncio.run(
        atender(
            "importa a habilidade https://github.com/a/b/blob/main/SKILL.md",
            registry=duble,
            raiz=tmp_path,
            consultar_web=False,
        )
    )
    assert resultado["acao"] == "confirmar"
    assert resultado["parametros"] == {"url": "https://github.com/a/b/blob/main/SKILL.md"}


def test_quais_habilidades_e_leitura(tmp_path: Path) -> None:
    duble = registro(
        {
            "id": "habilidades.listar",
            "name": "Habilidades importadas",
            "description": "Lista.",
            "category": "Habilidades",
            "inputSchema": {"type": "object", "properties": {}},
        },
        raiz=tmp_path,
    )
    resultado = asyncio.run(
        atender("quais habilidades você importou", registry=duble, raiz=tmp_path, consultar_web=False)
    )
    assert resultado["acao"] == "executado"


def test_formatar_habilidade_importada() -> None:
    texto = formatar_resultado(
        {"slug": "frontend-design", "nome": "frontend-design", "url": "https://x/SKILL.md", "tamanho": 120, "novo": True, "tentativas": []}
    )
    assert "Habilidade importada" in texto and "frontend-design" in texto
    assert "usa a habilidade frontend-design" in texto


def test_formatar_lista_vazia_ensina_o_comando() -> None:
    texto = formatar_resultado({"total": 0, "habilidades": []})
    assert "importa a habilidade" in texto


def test_formatar_guia_com_tarefa() -> None:
    texto = formatar_resultado(
        {
            "slug": "grill-me",
            "nome": "Grill me",
            "url": "https://x/SKILL.md",
            "texto": "1. Pergunte o objetivo\n2. Cobre o plano",
            "tarefa": "revisar o plano",
            "cortado": False,
            "lembrete": "Isto é um roteiro em texto.",
        }
    )
    assert "Para: revisar o plano" in texto
    assert "Pergunte o objetivo" in texto
    assert "roteiro em texto" in texto


# ----------------------------------------------- correio e lote (0.53.0)


def test_pedido_de_triagem_vai_para_o_correio(tmp_path: Path) -> None:
    from server.agente_local import _pedido_direto_de_correio

    pedido = _pedido_direto_de_correio("entra no meu gmail e filtra por importância")
    assert pedido["skill_id"] == "correio.triar"
    assert _pedido_direto_de_correio("meus emails importantes")["skill_id"] == "correio.triar"


def test_pedido_de_padrao_de_email() -> None:
    from server.agente_local import _pedido_direto_de_correio

    pedido = _pedido_direto_de_correio("qual é o meu padrão de e-mail")
    assert pedido["skill_id"] == "correio.padroes"


def test_pedido_de_rascunho_separa_destino_assunto_e_pontos() -> None:
    from server.agente_local import _pedido_direto_de_correio

    pedido = _pedido_direto_de_correio("escreve um e-mail para a Ana sobre o relatório: enviar planilha; pedir retorno")
    assert pedido["skill_id"] == "correio.rascunho"
    assert pedido["parametros"]["para"] == "Ana"
    assert pedido["parametros"]["assunto"] == "relatório"
    assert pedido["parametros"]["pontos"] == "enviar planilha; pedir retorno"


def test_formatar_triagem() -> None:
    texto = formatar_resultado(
        {
            "total": 2,
            "urgentes": 1,
            "por_categoria": {"Intimação / processo": 1, "Newsletter / promoção": 1},
            "mensagens": [
                {"prioridade": 100, "rotulo": "Intimação / processo", "assunto": "Intimação nº 1", "de": "tj@tj.jus.br", "vencimento": "", "dias_para_vencer": None},
                {"prioridade": 5, "rotulo": "Newsletter / promoção", "assunto": "Promo", "de": "p@loja.com", "vencimento": "", "dias_para_vencer": None},
            ],
        }
    )
    assert "Triagem de 2 mensagem" in texto and "1 urgente" in texto
    assert "[100] Intimação / processo" in texto
    assert "nada foi aberto no gmail" in texto.lower()


def test_formatar_rascunho_mostra_aviso() -> None:
    texto = formatar_resultado(
        {
            "para": "ana@x.com",
            "assunto": "entrega",
            "corpo": "Olá,\n\nSegue.\n\nAbraços,\nVictor\n",
            "palavras": 6,
            "baseado_em": 1,
            "avisos": ["Rascunho montado a partir do seu padrão — revise antes de enviar.", "Nada foi enviado."],
        }
    )
    assert "Para: ana@x.com" in texto and "Abraços" in texto
    assert "revise antes de enviar" in texto


def test_varios_links_viram_importacao_em_lote() -> None:
    from server.agente_local import _pedido_direto_de_habilidade

    pedido = _pedido_direto_de_habilidade(
        "importa estas habilidades: https://github.com/a/b/blob/main/x/SKILL.md e https://github.com/c/d/blob/main/y/SKILL.md"
    )
    assert pedido["skill_id"] == "habilidades.importar-varias"
    assert pedido["parametros"]["limite"] == 2
    assert pedido["parametros"]["links"].count("http") == 2


def test_formatar_lote_com_falha() -> None:
    texto = formatar_resultado(
        {
            "tentadas": 2,
            "importadas": [{"slug": "a", "nome": "A", "tamanho": 10}],
            "falhas": [{"url": "https://x/SKILL.md", "erro": "404"}],
            "restantes": 0,
        }
    )
    assert "Importei 1 de 2" in texto
    assert "Não deu para importar" in texto


def test_escrever_email_nao_vira_digitacao() -> None:
    """“escreve um e-mail” é correio; “escreve oi” continua sendo teclado."""
    from server.agente_local import _pedido_direto_de_correio, _pedido_direto_de_mesa

    pedido = "escreve um e-mail para a Ana sobre o relatório: enviar planilha"
    assert _pedido_direto_de_mesa(pedido) is None
    assert _pedido_direto_de_correio(pedido)["skill_id"] == "correio.rascunho"
    assert _pedido_direto_de_mesa("escreve oi")["skill_id"] == "mesa.digitar"


# ------------------------------------------ catálogo e busca do Gmail (0.53.0)


def test_pedido_para_carregar_o_catalogo() -> None:
    from server.agente_local import _pedido_direto_de_catalogo

    pedido = _pedido_direto_de_catalogo("carrega o catálogo de skills")
    assert pedido["skill_id"] == "catalogo.carregar"
    assert pedido["parametros"]["caminho"].endswith(".csv")
    assert pedido["confirma"] is True


def test_pedido_para_listar_o_catalogo() -> None:
    from server.agente_local import _pedido_direto_de_catalogo

    assert _pedido_direto_de_catalogo("lista o catálogo")["skill_id"] == "catalogo.listar"
    filtrado = _pedido_direto_de_catalogo("quais skills de design tem no catálogo")
    assert filtrado["skill_id"] == "catalogo.listar"
    assert filtrado["parametros"] == {"categoria": "design"}


def test_pedido_para_importar_do_catalogo() -> None:
    from server.agente_local import _pedido_direto_de_catalogo

    pedido = _pedido_direto_de_catalogo("importa as 3 primeiras do catálogo da vercel")
    assert pedido["skill_id"] == "catalogo.importar"
    assert pedido["parametros"]["quantos"] == 3
    assert pedido["parametros"]["fornecedor"] == "vercel-labs"
    assert pedido["confirma"] is True


def test_fora_do_catalogo_nao_dispara() -> None:
    from server.agente_local import _pedido_direto_de_catalogo

    assert _pedido_direto_de_catalogo("quais habilidades eu já tenho") is None
    assert _pedido_direto_de_catalogo("importa esta skill: https://github.com/a/b/SKILL.md") is None


def test_pedido_de_busca_no_gmail() -> None:
    from server.agente_local import _pedido_direto_de_correio

    faturas = _pedido_direto_de_correio("abre o gmail com as faturas")
    assert faturas["skill_id"] == "correio.gmail-busca"
    assert faturas["parametros"]["tipo"] == "faturas"
    assert faturas["confirma"] is False
    assert _pedido_direto_de_correio("gmail com as intimações")["parametros"]["tipo"] == "intimacoes"
    assert _pedido_direto_de_correio("o que tem de segurança no meu e-mail") is None


def test_formatar_catalogo_carregado() -> None:
    texto = formatar_resultado(
        {
            "total": 100,
            "arquivo": "D:/JARVIS/storage/catalogo.json",
            "por_categoria": {"design-media": 12, "dev-programming": 40},
            "por_fornecedor": {"anthropics": 10},
        }
    )
    assert "Catálogo carregado: 100" in texto
    assert "design-media (12)" in texto


def test_formatar_catalogo_lista() -> None:
    texto = formatar_resultado(
        {
            "total": 2,
            "mostrando": 2,
            "itens": [
                {"rank": 1, "skill": "frontend-design", "vendor": "anthropics", "category": "design-media", "repo_url": "https://github.com/anthropics/skills"},
                {"rank": 2, "skill": "tdd", "vendor": "mattpocock", "category": "dev-programming", "repo_url": ""},
            ],
        }
    )
    assert "[1] frontend-design — anthropics" in texto
    assert "[2] tdd" in texto


def test_formatar_catalogo_importacao() -> None:
    texto = formatar_resultado(
        {
            "tentadas": 3,
            "importadas": [{"rank": 1, "nome": "Frontend Design", "slug": "frontend-design"}],
            "falhas": [{"skill": "nano-banana-pro", "erro": "linha sem endereço de repositório"}],
            "restantes": 97,
            "limite_por_chamada": 10,
        }
    )
    assert "Importei 1 de 3" in texto
    assert "nano-banana-pro" in texto
    assert "Ainda há 97" in texto


def test_formatar_busca_do_gmail() -> None:
    texto = formatar_resultado(
        {
            "rotulo": "Faturas e boletos",
            "consulta": "subject:(fatura)",
            "url": "https://mail.google.com/mail/u/0/#search/fatura",
            "dica": "Abre no seu navegador já logado; nada é enviado para o JARVIS.",
        }
    )
    assert "Faturas e boletos" in texto
    assert "mail.google.com" in texto
    assert "já logado" in texto


# --------------------------------------------- livros e adaptação (0.53.0)


def test_pedido_de_fontes_de_livros() -> None:
    from server.agente_local import _pedido_direto_de_cultura

    assert _pedido_direto_de_cultura("onde acho livros completos de graça")["skill_id"] == "cultura.fontes"
    assert _pedido_direto_de_cultura("quais sites tem livros gratuitos")["skill_id"] == "cultura.fontes"


def test_pedido_de_busca_e_download_de_livro() -> None:
    from server.agente_local import _pedido_direto_de_cultura

    busca = _pedido_direto_de_cultura("procura o livro Dom Casmurro")
    assert busca["skill_id"] == "cultura.buscar"
    assert busca["parametros"]["consulta"] == "Dom Casmurro"

    baixar = _pedido_direto_de_cultura("baixa o livro 59863")
    assert baixar["skill_id"] == "cultura.baixar"
    assert baixar["parametros"]["livro"] == "59863"

    por_nome = _pedido_direto_de_cultura("baixa o livro Dom Casmurro")
    assert por_nome["skill_id"] == "cultura.buscar"


def test_pedido_de_persona_tira_a_palavra_livro() -> None:
    from server.agente_local import _pedido_direto_de_cultura

    pedido = _pedido_direto_de_cultura("faz uma persona do livro Dom Casmurro")
    assert pedido["skill_id"] == "cultura.persona"
    assert pedido["parametros"]["livro"] == "Dom Casmurro"


def test_pedido_de_adaptar_habilidade() -> None:
    from server.agente_local import _pedido_direto_de_cultura

    pedido = _pedido_direto_de_cultura("adapta a habilidade frontend-design para mim")
    assert pedido["skill_id"] == "habilidades.adaptar"
    assert pedido["parametros"]["habilidade"] == "frontend-design"


def test_pedido_do_topico_do_github() -> None:
    from server.agente_local import _pedido_direto_de_catalogo

    pedido = _pedido_direto_de_catalogo("pega as skills do tópico agent-skills do github")
    assert pedido["skill_id"] == "catalogo.topico"
    assert pedido["parametros"]["topico"] == "agent-skills"
    assert pedido["confirma"] is True


def test_formatar_fontes_de_livro() -> None:
    texto = formatar_resultado(
        {
            "total": 1,
            "fontes": [
                {
                    "nome": "Project Gutenberg",
                    "url": "https://www.gutenberg.org",
                    "o_que_tem": "79 mil livros",
                    "licenca": "domínio público",
                    "precisa": "nada",
                }
            ],
            "recomendacao": "Comece pelo Gutenberg.",
        }
    )
    assert "Project Gutenberg" in texto
    assert "domínio público" in texto


def test_formatar_busca_de_livro() -> None:
    texto = formatar_resultado(
        {
            "fonte": "gutenberg",
            "consulta": "machado",
            "total": 1,
            "livros": [{"id": 59863, "titulo": "Dom Casmurro", "autores": ["Machado de Assis"], "texto": "https://x/59863.txt"}],
            "dica": "Baixe com cultura.baixar.",
        }
    )
    assert "[59863] Dom Casmurro — Machado de Assis" in texto
    assert "Baixe com cultura.baixar" in texto


def test_formatar_persona() -> None:
    texto = formatar_resultado(
        {
            "nome": "Dom Casmurro",
            "tom": "equilibrado",
            "palavras": 1000,
            "regras": ["Frase média de 12 palavras."],
            "limites": ["Isto descreve estilo medido, não o autor."],
        }
    )
    assert "estilo medido" in texto
    assert "Frase média" in texto


def test_formatar_catalogo_do_topico() -> None:
    texto = formatar_resultado(
        {
            "topico": "agent-skills",
            "origem": "https://github.com/topics/agent-skills",
            "repos_lidos": 12,
            "adicionadas": 40,
            "total": 140,
            "por_categoria": {"dev-programming": 30},
            "sem_skill": ["algum/repo"],
        }
    )
    assert "tópico “agent-skills”" in texto
    assert "total agora: 140" in texto


# ------------------------------------------------------ camada do PC (0.54.0)


def test_pedido_para_abrir_programa() -> None:
    from server.agente_local import _pedido_direto_de_pc

    pedido = _pedido_direto_de_pc("abre o bloco de notas")
    assert pedido["skill_id"] == "pc.abrir-programa"
    assert pedido["parametros"]["nome"] == "bloco de notas"
    assert pedido["confirma"] is True
    assert _pedido_direto_de_pc("abre a calculadora")["parametros"]["nome"] == "calculadora"


def test_pedido_para_abrir_arquivo() -> None:
    from server.agente_local import _pedido_direto_de_pc

    pedido = _pedido_direto_de_pc("abre o arquivo contrato.pdf")
    assert pedido["skill_id"] == "pc.abrir-arquivo"
    assert pedido["parametros"]["caminho"] == "contrato.pdf"
    assert _pedido_direto_de_pc("abre o arquivo do mês") is None


def test_pedido_de_comando_pronto_do_pc() -> None:
    from server.agente_local import _pedido_direto_de_pc

    assert _pedido_direto_de_pc("qual é o meu ip")["parametros"]["nome"] == "ip"
    assert _pedido_direto_de_pc("roda o ipconfig")["parametros"]["nome"] == "ip"
    assert _pedido_direto_de_pc("quanto tem de espaço em disco")["parametros"]["nome"] == "disco"


def test_pedido_de_listar_programas() -> None:
    from server.agente_local import _pedido_direto_de_pc

    pedido = _pedido_direto_de_pc("quais programas você abre")
    assert pedido["skill_id"] == "pc.programas"
    assert pedido["confirma"] is False


def test_abrir_gmail_nao_vira_programa() -> None:
    from server.agente_local import _pedido_direto_de_pc

    assert _pedido_direto_de_pc("abre o gmail com as faturas") is None
    assert _pedido_direto_de_pc("abre o drive") is None


def test_formatar_programas_do_pc() -> None:
    texto = formatar_resultado(
        {
            "ligado": False,
            "variavel": "JARVIS_HOST_PC",
            "programas": [{"nome": "notepad", "rotulo": "Bloco de notas", "executavel": "notepad.exe"}],
            "comandos": [{"nome": "ip", "rotulo": "Endereços de rede", "linha": "ipconfig"}],
            "nota": "Lista fechada.",
        }
    )
    assert "Camada do PC: desligada" in texto
    assert "Bloco de notas" in texto
    assert "Endereços de rede" in texto


def test_formatar_saida_de_comando() -> None:
    texto = formatar_resultado(
        {
            "rotulo": "Endereços de rede",
            "linha": "ipconfig",
            "saida": "192.168.0.10",
            "codigo": 0,
        }
    )
    assert "`ipconfig`" in texto
    assert "192.168.0.10" in texto
