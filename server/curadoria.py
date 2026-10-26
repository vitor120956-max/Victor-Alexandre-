"""Motor de curadoria de listas — elegibilidade, entrada, catálogo, README, ticker e higiene.

Inspirado na mecânica de `hesreallyhim/awesome-claude-code` (CC BY-NC-ND 4.0).
A licença do upstream **não permite derivados nem uso comercial**: por isso nada
do catálogo curado, das descrições ou das categorias dele é copiado aqui. O que
esta adaptação implementa é o **mecanismo** — o schema, as regras de aceitação,
a validação da entrada, o ID opaco, o agrupamento, o gerador de README, o ticker
de estrelas e a auditoria de higiene — sobre um catálogo que é seu.

Tudo é estático e determinístico: não há requisição de rede, descoberta de
licença via API, leitura de repositório nem escrita de arquivo.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import secrets
import unicodedata
from datetime import date, datetime
from typing import Any

from .review import common, finalize, finding

VERSAO = "0.54.0"
MAX_TEXTO = 400_000
MAX_LINHAS = 5_000

# --------------------------------------------------------------- schema

COLUNAS = (
    "id",
    "nome",
    "categoria",
    "subcategoria",
    "link",
    "autor",
    "link_autor",
    "ativo",
    "adicionado_em",
    "checado_em",
    "descricao",
    "estagnado",
)

# Aceita o schema em inglês do upstream: o cabeçalho é normalizado antes de ler.
APELIDOS = {
    "id": "id",
    "display name": "nome",
    "display_name": "nome",
    "nome": "nome",
    "name": "nome",
    "category": "categoria",
    "categoria": "categoria",
    "sub-category": "subcategoria",
    "sub_category": "subcategoria",
    "subcategory": "subcategoria",
    "subcategoria": "subcategoria",
    "link": "link",
    "url": "link",
    "author name": "autor",
    "author_name": "autor",
    "autor": "autor",
    "author link": "link_autor",
    "author_link": "link_autor",
    "link_autor": "link_autor",
    "active": "ativo",
    "ativo": "ativo",
    "date added": "adicionado_em",
    "date_added": "adicionado_em",
    "adicionado_em": "adicionado_em",
    "last checked": "checado_em",
    "last_checked": "checado_em",
    "checado_em": "checado_em",
    "description": "descricao",
    "descricao": "descricao",
    "stale": "estagnado",
    "estagnado": "estagnado",
}

OBRIGATORIAS = ("nome", "categoria", "link", "autor", "link_autor", "descricao")
VERDADEIROS = {"true", "1", "sim", "s", "yes", "y", "ativo"}
FALSOS = {"false", "0", "nao", "não", "n", "no", "inativo", ""}

CATEGORIAS: list[dict[str, Any]] = [
    {"nome": "Comece aqui", "descricao": "O que instalar primeiro e o que só serve depois.", "subcategorias": []},
    {"nome": "Skills e comandos", "descricao": "Fluxos empacotados que mudam como o agente trabalha.",
     "subcategorias": [
         {"nome": "Revisão de código", "descricao": "Leitura crítica antes do merge."},
         {"nome": "Testes", "descricao": "Geração, cobertura e regressão."},
     ]},
    {"nome": "Memória e contexto", "descricao": "O que sobrevive à janela de contexto.", "subcategorias": []},
    {"nome": "Observabilidade", "descricao": "Custo, uso e o que aconteceu na sessão.",
     "subcategorias": [
         {"nome": "Custo e uso", "descricao": "Quanto gastou e onde."},
         {"nome": "Sessões", "descricao": "Replay, trilha e auditoria."},
     ]},
    {"nome": "Segurança e permissões", "descricao": "Limites declarados antes do primeiro comando.", "subcategorias": []},
    {"nome": "Design e interface", "descricao": "Cor, tipografia e hierarquia com critério.", "subcategorias": []},
    {"nome": "Infraestrutura e entrega", "descricao": "Build, deploy e ambiente reproduzível.", "subcategorias": []},
    {"nome": "Qualidade e revisão", "descricao": "Lint, formatação e padrões de código.", "subcategorias": []},
    {"nome": "Coleções", "descricao": "Listas que agregam outras listas.", "subcategorias": [], "submetivel": False},
]

# --------------------------------------------------------------- regras

REGRAS_ELEGIBILIDADE = [
    {"id": "idade", "regra": "A primeira submissão na branch padrão tem ao menos 14 dias."},
    {"id": "desenvolvimento", "regra": "Há commits além do primeiro dia — o projeto continua vivo."},
    {"id": "estrelas", "regra": "Alternativa às duas anteriores: ao menos 100 estrelas."},
    {"id": "um-por-vez", "regra": "Uma recomendação por pessoa e por vez; a linha traz um único link."},
]

REGRAS_ESTILO = [
    {"id": "descricao", "regra": "Descreve o que o software faz, no presente, sem falar com o leitor."},
    {"id": "uma-linha", "regra": "Uma linha, sem quebra, entre 10 e 500 caracteres."},
    {"id": "sem-emoji", "regra": "Sem emoji, sem caixa alta e sem ponto de exclamação."},
    {"id": "sem-pitch", "regra": "Sem superlativo de venda: “o melhor”, “revolucionário”, “imperdível”, “10x”."},
    {"id": "factual", "regra": "Sem promessa de resultado, sem número inventado, sem “clique aqui”."},
]

REGRAS_LICENCA = [
    {"id": "descoberta", "regra": "A licença é descoberta na fonte; se não é identificável, isso atrapalha a revisão."},
    {"id": "fechado", "regra": "Projeto fechado não é proibido, mas é barreira de revisão."},
    {"id": "acesso", "regra": "Cadastro ou pagamento obrigatório bloqueia a recomendação: só resta o sinal de adoção."},
]

SEGURANCA_TICKER = {
    "donos_banidos": [],
    "nomes_exatos": ["claude-code", "claudecode", "claude_code", "claude.code"],
    "nomes_contem": ["source-code", "sourcecode", "source-map", "sourcemap"],
    "nomes_completos": [],
}

EMOJI = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U0001F1E6-\U0001F1FF" "\u2600-\u27BF" "\u2B00-\u2BFF" "\uFE0F" "]"
)
SEGUNDA_PESSOA = re.compile(r"\b(voc[êe]|seu|sua|seus|suas|ti|te|you|your|yours)\b", re.I)
PITCH = re.compile(
    r"\b(o melhor|a melhor|melhor do mundo|revolucion\w+|incr[íi]vel|imperd[íi]vel|"
    r"essencial para todos|game[- ]?changer|blazing\w*|must[- ]have|n[ãa]o perca|"
    r"the best|world[- ]class|10x|100x|m[áa]gico|definitiv[oa])\b",
    re.I,
)
CLIQUE = re.compile(r"\b(clique aqui|clique no link|saiba mais|link abaixo|veja abaixo)\b", re.I)
LINK_PROIBIDO = re.compile(r"""[\s"'<>`\\)]""")
URL = re.compile(r"^https://([A-Za-z0-9\-]+\.)+[A-Za-z]{2,}(/[^\s]*)?$")
ID = re.compile(r"^[0-9a-f]{8}$")
DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CuradoriaError(ValueError):
    """Entrada inválida do motor de curadoria; a API devolve 200 com `ok:false`."""


# --------------------------------------------------------------- utilidades

def _norm(valor: str) -> str:
    base = "".join(c for c in unicodedata.normalize("NFD", str(valor)) if unicodedata.category(c) != "Mn")
    return base.casefold().strip()


def _slug(valor: str) -> str:
    texto = _norm(valor)
    texto = re.sub(r"[^0-9a-z\s-]", "", texto)
    return re.sub(r"\s+", "-", texto.strip()) or "secao"


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _n(total: int, um: str, muitos: str) -> str:
    return f"{total} {um if total == 1 else muitos}"


def _bool(valor: str) -> bool:
    return _norm(valor) in VERDADEIROS


def _data(valor: str) -> date | None:
    valor = _texto(valor)
    if not valor or not DATA.match(valor):
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None


def _hoje(valor: str) -> date:
    if not valor.strip():
        return date.today()
    achado = _data(valor)
    if achado is None:
        raise CuradoriaError("`hoje` precisa estar em AAAA-MM-DD.")
    return achado


def _id(semente: str) -> str:
    if semente.strip():
        return hashlib.sha256(semente.strip().encode("utf-8")).hexdigest()[:8]
    return secrets.token_hex(4)


def _config(categorias: str) -> list[dict[str, Any]]:
    """Lê a configuração de categorias em JSON; vazio usa o exemplo embutido."""
    if not categorias.strip():
        return [dict(item) for item in CATEGORIAS]
    import json

    try:
        dados = json.loads(categorias)
    except json.JSONDecodeError as erro:
        raise CuradoriaError(f"JSON de categorias inválido: {erro.msg} (linha {erro.lineno}).") from erro
    if isinstance(dados, dict):
        dados = dados.get("categorias", [])
    if not isinstance(dados, list) or not dados:
        raise CuradoriaError("A configuração precisa de uma lista `categorias` com ao menos um item.")
    saida: list[dict[str, Any]] = []
    for indice, item in enumerate(dados, start=1):
        if not isinstance(item, dict) or not _texto(item.get("nome")):
            raise CuradoriaError(f"A categoria {indice} precisa de `nome`.")
        subs = item.get("subcategorias") or item.get("subcategories") or []
        if not isinstance(subs, list):
            raise CuradoriaError(f"As subcategorias de `{item['nome']}` precisam ser lista.")
        limpas = []
        for sub in subs:
            if isinstance(sub, str):
                limpas.append({"nome": sub.strip()})
            elif isinstance(sub, dict) and _texto(sub.get("nome")):
                limpas.append(dict(sub))
            else:
                raise CuradoriaError(f"Subcategoria inválida em `{item['nome']}`.")
        saida.append({
            "nome": _texto(item["nome"]),
            "descricao": _texto(item.get("descricao") or item.get("description")),
            "submetivel": bool(item.get("submetivel", item.get("submittable", True))),
            "subcategorias": limpas,
        })
    nomes = [_norm(item["nome"]) for item in saida]
    if len(set(nomes)) != len(nomes):
        raise CuradoriaError("Há categoria repetida na configuração.")
    return saida


def _subcategoria_valida(config: list[dict[str, Any]], categoria: str, subcategoria: str) -> str | None:
    """Devolve o motivo da recusa, ou None quando o par é válido."""
    if not _texto(subcategoria):
        return None
    for item in config:
        if _norm(item["nome"]) == _norm(categoria):
            declaradas = {_norm(sub["nome"]) for sub in item["subcategorias"]}
            if _norm(subcategoria) in declaradas:
                return None
            return f"Subcategoria `{subcategoria}` não está declarada em `{item['nome']}`."
    return None


# --------------------------------------------------------------- 1. entrada

def _url_valida(valor: str) -> str | None:
    if not valor:
        return "vazio"
    if not valor.startswith("https://"):
        return "precisa começar com `https://`"
    if LINK_PROIBIDO.search(valor):
        return "tem espaço, aspas ou metacaractere de Markdown/HTML"
    if not URL.match(valor):
        return "não parece uma URL com domínio"
    return None


def auditar_descricao(descricao: str) -> list[dict[str, str]]:
    """Achados de estilo de uma descrição; usado pela entrada e pela higiene."""
    achados: list[dict[str, str]] = []
    texto = descricao.strip()
    if not texto:
        return [{"kind": "descricao-vazia", "titulo": "Descrição vazia"}]
    if "\n" in texto:
        achados.append({"kind": "descricao-multilinha", "titulo": "Descrição em mais de uma linha"})
    if len(texto) < 10:
        achados.append({"kind": "descricao-curta", "titulo": "Descrição com menos de 10 caracteres"})
    if len(texto) > 500:
        achados.append({"kind": "descricao-longa", "titulo": "Descrição com mais de 500 caracteres"})
    if EMOJI.search(texto):
        achados.append({"kind": "descricao-emoji", "titulo": "Emoji na descrição"})
    if "!" in texto:
        achados.append({"kind": "descricao-exclamacao", "titulo": "Ponto de exclamação na descrição"})
    if SEGUNDA_PESSOA.search(texto):
        achados.append({"kind": "descricao-segunda-pessoa", "titulo": "Descrição fala com o leitor em segunda pessoa"})
    if PITCH.search(texto):
        achados.append({"kind": "descricao-pitch", "titulo": "Descrição usa superlativo de venda"})
    if CLIQUE.search(texto):
        achados.append({"kind": "descricao-chamada", "titulo": "Descrição chama para clicar em vez de descrever"})
    if texto.isupper() and len(texto) > 20:
        achados.append({"kind": "descricao-caixa-alta", "titulo": "Descrição inteira em caixa alta"})
    return achados


def validar_entrada(
    *,
    nome: str,
    link: str,
    autor: str,
    link_autor: str,
    categoria: str,
    descricao: str,
    subcategoria: str = "",
    licenca: str = "",
    dias_desde_o_primeiro_commit: int = 0,
    commits_depois_do_primeiro_dia: int = 0,
    estrelas: int = 0,
    exige_cadastro: bool = False,
    pago: bool = False,
    existentes: str = "",
    categorias: str = "",
    hoje: str = "",
    semente: str = "",
    modo: str = "full",
) -> dict[str, Any]:
    config = _config(categorias)
    referencia = _hoje(hoje)
    achados: list[dict[str, Any]] = []
    nome, link, autor, link_autor = nome.strip(), link.strip(), autor.strip(), link_autor.strip()
    categoria, subcategoria = categoria.strip(), subcategoria.strip()

    if len(nome) > 80:
        raise CuradoriaError("O nome passa de 80 caracteres; encurte para a lista.")
    if dias_desde_o_primeiro_commit < 0 or dias_desde_o_primeiro_commit > 20_000:
        raise CuradoriaError("Dias desde o primeiro commit fora da faixa 0–20 000.")
    if commits_depois_do_primeiro_dia < 0 or commits_depois_do_primeiro_dia > 1_000_000:
        raise CuradoriaError("Commits fora de faixa.")
    if estrelas < 0 or estrelas > 10_000_000:
        raise CuradoriaError("Estrelas fora de faixa.")

    # --- campos obrigatórios
    for rotulo, valor in (("nome", nome), ("link", link), ("autor", autor),
                          ("link do autor", link_autor), ("descrição", descricao.strip())):
        if not valor:
            achados.append(finding(
                "must", "campo-obrigatorio", f"Campo obrigatório vazio: {rotulo}", rotulo,
                "A entrada só existe com os seis campos.",
                "Sem o campo, a linha não pode ser gerada nem revisada.",
                f"Preencha `{rotulo}`.",
                "A recomendação volta como incompleta.",
            ))

    # --- URL
    for rotulo, valor in (("link", link), ("link do autor", link_autor)):
        motivo = _url_valida(valor)
        if valor and motivo:
            achados.append(finding(
                "must", "url-invalida", f"{rotulo.capitalize()} inválido", valor[:60],
                "O link entra no README e em badge: só `https` sem espaço nem metacaractere.",
                motivo[0].upper() + motivo[1:] + ".",
                "Use a URL canônica do repositório ou da página.",
                "O link quebra o Markdown ou não abre.",
            ))
    if link.count("://") > 1 or " " in link:
        achados.append(finding(
            "must", "um-por-vez", "Mais de um link na mesma entrada", link[:60],
            "A regra é uma recomendação por vez.",
            "Duas entradas numa linha não podem ser revisadas nem aceitas em separado.",
            "Envie uma recomendação por recurso.",
            "A submissão é recusada.",
        ))

    # --- categoria
    nomes = {_norm(item["nome"]): item for item in config}
    alvo = nomes.get(_norm(categoria))
    if not categoria:
        achados.append(finding(
            "must", "categoria-obrigatoria", "Categoria vazia", "categoria",
            "A categoria decide a seção do README e a ordem de leitura.",
            "Sem categoria, a entrada não tem lugar.",
            "Escolha uma das categorias declaradas.",
            "A entrada fica fora do índice.",
        ))
    elif alvo is None:
        achados.append(finding(
            "must", "categoria-desconhecida", "Categoria não declarada", categoria[:60],
            "Só entram categorias que a configuração declara.",
            "Uma categoria inventada some do README ou vira seção órfã.",
            "Use uma das declaradas: " + ", ".join(item["nome"] for item in config) + ".",
            "A linha é agrupada fora do sumário.",
        ))
    else:
        if not alvo.get("submetivel", True):
            achados.append(finding(
                "must", "categoria-fechada", "Categoria não aceita submissão", alvo["nome"],
                "Esta seção é curada pelo dono da lista.",
                "Aceitar aqui fura a regra da própria seção.",
                "Escolha uma categoria aberta.",
                "A submissão é recusada.",
            ))
        motivo = _subcategoria_valida(config, categoria, subcategoria)
        if motivo:
            achados.append(finding(
                "must", "subcategoria-orfa", "Subcategoria não declarada", motivo,
                "A subcategoria precisa existir sob a categoria escolhida.",
                "Sem declaração, ela não aparece no formulário nem no README.",
                "Declare a subcategoria na configuração ou use a categoria direta.",
                "A entrada é recusada.",
            ))

    # --- elegibilidade
    idade = dias_desde_o_primeiro_commit
    estrelas_ok = estrelas >= 100
    idade_ok = idade >= 14 and commits_depois_do_primeiro_dia >= 1
    if not estrelas_ok and not idade_ok:
        if idade < 14:
            kind, titulo = "inelegivel", "Recurso ainda não é elegível"
            motivo, correcao = f"{idade} dia(s) desde o primeiro commit", "Volte depois de 14 dias de desenvolvimento."
        else:
            kind, titulo = "sem-atividade", "Idade sem atividade"
            motivo, correcao = f"{idade} dias e nenhum commit depois do primeiro", "Mostre sinal de vida além do primeiro dia, ou 100 estrelas."
        achados.append(finding(
            "must", kind, titulo, motivo,
            "Aceita-se (a) 14 dias com desenvolvimento ativo, ou (b) 100 estrelas.",
            "Aceitar o imaturo enche a lista de projetos que param na primeira semana.",
            correcao,
            "A recomendação é recusada até amadurecer.",
        ))
    elif estrelas_ok and idade >= 14 and commits_depois_do_primeiro_dia >= 1:
        achados.append(finding(
            "nice", "elegivel-duplo", "Elegível pelas duas regras", f"{idade} dias · {estrelas} estrelas",
            "Idade com desenvolvimento e estrelas suficientes.",
            "Nenhum: os dois caminhos foram cumpridos.",
            "Siga para a revisão de estilo e licença.",
            "Nada.",
        ))

    # --- licença e acesso
    licenca_norm = _norm(licenca)
    if not licenca_norm or licenca_norm in {"desconhecida", "unknown", "?", "-"}:
        achados.append(finding(
            "should", "licenca-ausente", "Licença não identificada", licenca or "—",
            "A licença precisa ser descobrível na fonte.",
            "Sem licença clara, quem adota não sabe o que pode fazer.",
            "Inclua um LICENSE na raiz e informe o identificador SPDX.",
            "A revisão fica mais lenta e a entrada pode ser adiada.",
        ))
    if _norm(licenca) in {"nenhuma", "proprietaria", "proprietary", "closed"}:
        achados.append(finding(
            "should", "licenca-fechada", "Projeto fechado", licenca,
            "Fechado não é proibido, mas é barreira de revisão.",
            "Sem código para ler, resta o sinal de adoção.",
            "Aceite consciente: registre por que vale mesmo assim.",
            "A entrada depende de reputação, não de inspeção.",
        ))
    if exige_cadastro or pago:
        achados.append(finding(
            "must", "acesso-bloqueado", "Exige cadastro ou pagamento", "cadastro" if exige_cadastro else "pagamento",
            "Cadastro ou pagamento obrigatório bloqueia a recomendação.",
            "Ninguém revisa o que não consegue abrir.",
            "Ofereça acesso de avaliação ou mostre adoção pública suficiente.",
            "A entrada não pode ser verificada.",
        ))

    # --- descrição
    for item in auditar_descricao(descricao):
        grupo = "must" if item["kind"] in {"descricao-vazia", "descricao-multilinha", "descricao-longa",
                                           "descricao-emoji", "descricao-pitch"} else "should"
        achados.append(finding(
            grupo, item["kind"], item["titulo"], descricao.strip()[:60] or "—",
            "A descrição diz o que o software faz, em uma linha, sem falar com o leitor.",
            "Descrição de venda transforma a lista em catálogo publicitário.",
            "Reescreva no presente: “Faz X com Y, para Z”.",
            "A lista perde credibilidade a cada linha assim.",
        ))
    if nome and len(nome) < 2:
        achados.append(finding(
            "must", "nome-curto", "Nome curto demais", nome,
            "O nome aparece como link principal da linha.",
            "Um nome de um caractere não identifica o recurso.",
            "Use o nome como o projeto se apresenta.",
            "Ninguém sabe o que é.",
        ))
    if nome and _norm(nome) in {"test", "teste", "testing", "example", "exemplo"}:
        achados.append(finding(
            "should", "nome-de-teste", "Nome parece de teste", nome,
            "A lista é pública; um nome de teste confunde.",
            "Alguém vai tentar instalar.",
            "Use o nome real do projeto.",
            "A entrada vira ruído.",
        ))

    # --- duplicata
    for linha in existentes.splitlines():
        if not linha.strip():
            continue
        partes = [parte.strip() for parte in linha.split("|")]
        antigo_link = partes[0] if partes else ""
        antigo_nome = partes[1] if len(partes) > 1 else ""
        if antigo_link and link and _norm(antigo_link) == _norm(link):
            achados.append(finding(
                "must", "duplicata-link", "Link já está no catálogo", antigo_nome or antigo_link,
                "A deduplicação é por link, não por ID.",
                "Duas linhas para o mesmo projeto dividem a atenção e quebram a contagem.",
                "Atualize a linha existente em vez de criar outra.",
                "O catálogo passa a mentir sobre o tamanho.",
            ))
        elif antigo_nome and nome and _norm(antigo_nome) == _norm(nome):
            achados.append(finding(
                "should", "duplicata-nome", "Nome já está no catálogo", antigo_nome,
                "Nome repetido costuma significar o mesmo projeto com outra URL.",
                "O leitor não sabe qual das duas abrir.",
                "Confirme se é outro projeto; se não, atualize a entrada existente.",
                "Duas entradas parecem uma.",
            ))

    identificador = _id(semente)
    linha_csv = _linha({
        "id": identificador,
        "nome": nome,
        "categoria": categoria,
        "subcategoria": subcategoria,
        "link": link,
        "autor": autor,
        "link_autor": link_autor,
        "ativo": "TRUE",
        "adicionado_em": referencia.isoformat(),
        "checado_em": referencia.isoformat(),
        "descricao": descricao.strip(),
        "estagnado": "FALSE",
    })

    metrics = {
        "dias": idade,
        "commits": commits_depois_do_primeiro_dia,
        "estrelas": estrelas,
        "regra": "estrelas" if estrelas_ok and not (idade >= 14 and commits_depois_do_primeiro_dia >= 1)
        else "idade" if idade_ok else "nenhuma",
        "caracteres": len(descricao.strip()),
        "id": identificador,
    }
    perguntas = ["A licença aparece na raiz do projeto e é reconhecida por ferramenta automática?"]
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Linha pronta para o catálogo", "", "```csv", linha_csv, "```", "",
             "## Elegibilidade", "",
             f"- Idade: {idade} dia(s) · commits depois do primeiro dia: {commits_depois_do_primeiro_dia}",
             f"- Estrelas: {estrelas}",
             f"- Caminho cumprido: {metrics['regra'] if metrics['regra'] != 'nenhuma' else 'nenhum — recusado'}",
             "", "## Regras de elegibilidade", ""]
    for regra in REGRAS_ELEGIBILIDADE:
        extra += [f"- **{regra['id']}** — {regra['regra']}"]
    extra += ["", "## Regras de estilo", ""]
    for regra in REGRAS_ESTILO:
        extra += [f"- **{regra['id']}** — {regra['regra']}"]
    extra += [""]
    return {
        **common(
            analysis="curadoria.entrada",
            mode=modo,
            title="Entrada de catálogo",
            summary=[
                f"{nome or '—'} em `{categoria or '—'}`{f' › {subcategoria}' if subcategoria else ''}.",
                f"Elegibilidade: {idade} dia(s), {commits_depois_do_primeiro_dia} commit(s) depois, {estrelas} estrela(s).",
                "A linha CSV volta pronta, com ID opaco de 8 dígitos hexadecimais.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=[{"campo": coluna, "valor": _linha_campos(linha_csv, coluna)} for coluna in COLUNAS],
            metrics=metrics,
            limitations=LIMITES_ENTRADA,
            extra_sections=extra,
        ),
        "id": identificador,
        "linha": linha_csv,
        "elegivel": metrics["regra"] != "nenhuma",
        "executado": False,
    }


LIMITES_ENTRADA = [
    "A elegibilidade usa os números que você declara: idade, commits e estrelas não são consultados na fonte.",
    "A licença é texto livre; nenhuma API de descoberta é chamada.",
    "O ID sai aleatório por padrão; com semente, é determinístico e serve para teste.",
    "A deduplicação compara link e nome normalizados contra a lista de existentes que você colar.",
]


def _linha(campos: dict[str, str]) -> str:
    buffer = io.StringIO()
    escritor = csv.writer(buffer, lineterminator="")
    escritor.writerow([campos.get(coluna, "") for coluna in COLUNAS])
    return buffer.getvalue()


def _linha_campos(linha: str, coluna: str) -> str:
    partes = next(csv.reader([linha]))
    return partes[COLUNAS.index(coluna)] if COLUNAS.index(coluna) < len(partes) else ""


# --------------------------------------------------------------- leitura do CSV

def _ler(csv_texto: str) -> tuple[list[dict[str, str]], list[str]]:
    """Lê o catálogo e devolve (linhas normalizadas, avisos de schema)."""
    if not csv_texto.strip():
        raise CuradoriaError("Cole o catálogo em CSV.")
    if len(csv_texto) > MAX_TEXTO:
        raise CuradoriaError(f"O catálogo passa de {MAX_TEXTO:,} caracteres.".replace(",", "."))
    leitor = csv.reader(io.StringIO(csv_texto.lstrip("\ufeff")))
    try:
        cabecalho = next(leitor)
    except StopIteration as erro:
        raise CuradoriaError("O CSV está vazio.") from erro
    colunas = [APELIDOS.get(_norm(nome), _norm(nome)) for nome in cabecalho]
    avisos: list[str] = []
    faltando = [coluna for coluna in COLUNAS if coluna not in colunas]
    if faltando:
        raise CuradoriaError(
            "Faltam colunas obrigatórias: " + ", ".join(faltando) +
            ". Use " + ", ".join(COLUNAS) + "."
        )
    desconhecidas = [nome for nome in cabecalho if _norm(nome) not in APELIDOS]
    if desconhecidas:
        avisos.append("Colunas ignoradas: " + ", ".join(desconhecidas))
    linhas: list[dict[str, str]] = []
    for numero, bruto in enumerate(leitor, start=2):
        if not any(celula.strip() for celula in bruto):
            continue
        if len(linhas) >= MAX_LINHAS:
            raise CuradoriaError(f"Mais de {MAX_LINHAS} linhas; divida o catálogo.")
        registro = {coluna: "" for coluna in COLUNAS}
        for indice, coluna in enumerate(colunas):
            if coluna in registro and indice < len(bruto):
                registro[coluna] = bruto[indice].strip()
        registro["_linha"] = str(numero)
        linhas.append(registro)
    return linhas, avisos


def _ordem(linha: dict[str, str]) -> tuple[str, str]:
    return (_norm(linha.get("nome", "")), _norm(linha.get("subcategoria", "")))


def _ativo(linha: dict[str, str]) -> bool:
    return _bool(linha.get("ativo", "TRUE")) if linha.get("ativo", "").strip() else True


def _arvore(linhas: list[dict[str, str]], config: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa no ordem da configuração; categoria desconhecida cai no fim."""
    por_categoria: dict[str, list[dict[str, str]]] = {}
    for linha in linhas:
        por_categoria.setdefault(_norm(linha.get("categoria", "")), []).append(linha)

    arvore: list[dict[str, Any]] = []
    vistas: set[str] = set()
    for item in config:
        chave = _norm(item["nome"])
        vistas.add(chave)
        membros = sorted(por_categoria.get(chave, []), key=_ordem)
        declaradas = [_norm(sub["nome"]) for sub in item["subcategorias"]]
        grupos: list[dict[str, Any]] = []
        for sub in item["subcategorias"]:
            filhos = [linha for linha in membros if _norm(linha.get("subcategoria", "")) == _norm(sub["nome"])]
            grupos.append({"nome": sub["nome"], "descricao": _texto(sub.get("descricao")),
                           "linhas": filhos, "declarada": True})
        soltos = [linha for linha in membros if _norm(linha.get("subcategoria", "")) not in declaradas]
        diretos = [linha for linha in soltos if not linha.get("subcategoria", "").strip()]
        orfaos: dict[str, list[dict[str, str]]] = {}
        for linha in soltos:
            if linha.get("subcategoria", "").strip():
                orfaos.setdefault(linha["subcategoria"], []).append(linha)
        arvore.append({
            "nome": item["nome"],
            "descricao": item.get("descricao", ""),
            "submetivel": item.get("submetivel", True),
            "subcategorias": grupos,
            "diretos": diretos,
            "orfaos": [{"nome": nome, "linhas": ordenadas} for nome, ordenadas in sorted(orfaos.items())],
            "total": len(membros),
            "desconhecida": False,
        })

    for chave, membros in sorted(por_categoria.items()):
        if chave in vistas:
            continue
        arvore.append({
            "nome": membros[0].get("categoria", "") or "(sem categoria)",
            "descricao": "",
            "submetivel": True,
            "subcategorias": [],
            "diretos": sorted(membros, key=_ordem),
            "orfaos": [],
            "total": len(membros),
            "desconhecida": True,
        })
    return arvore


def _metrica_catalogo(arvore: list[dict[str, Any]], linhas: list[dict[str, str]], referencia: date) -> dict[str, Any]:
    estagnados = sum(1 for linha in linhas if _bool(linha.get("estagnado", "")))
    nunca = sum(1 for linha in linhas if not _data(linha.get("checado_em", "")))
    vazias = sum(1 for item in arvore if item["total"] == 0)
    return {
        "linhas": len(linhas),
        "ativos": sum(1 for linha in linhas if _ativo(linha)),
        "inativos": sum(1 for linha in linhas if not _ativo(linha)),
        "categorias": len(arvore),
        "vazias": vazias,
        "subcategorias": sum(len(item["subcategorias"]) for item in arvore),
        "estagnados": estagnados,
        "nunca_checados": nunca,
        "desconhecidas": sum(1 for item in arvore if item["desconhecida"]),
        "hoje": referencia.isoformat(),
    }


# --------------------------------------------------------------- 2. catálogo

def montar_catalogo(*, csv_texto: str, categorias: str = "", hoje: str = "", modo: str = "full") -> dict[str, Any]:
    config = _config(categorias)
    referencia = _hoje(hoje)
    linhas, avisos = _ler(csv_texto)
    if not linhas:
        raise CuradoriaError("O CSV tem cabeçalho, mas nenhuma linha de recurso.")
    arvore = _arvore(linhas, config)
    metrics = _metrica_catalogo(arvore, linhas, referencia)

    achados: list[dict[str, Any]] = []
    for aviso in avisos:
        achados.append(finding(
            "nice", "coluna-ignorada", "Coluna fora do schema", aviso,
            "O schema tem 12 colunas.",
            "Uma coluna a mais não é lida por ninguém.",
            "Remova a coluna ou renomeie para uma das 12.",
            "O dado fica invisível.",
        ))
    for item in arvore:
        if item["desconhecida"]:
            achados.append(finding(
                "must", "categoria-desconhecida", "Categoria fora da configuração", item["nome"],
                "Só categorias declaradas entram no índice.",
                f"{_n(item['total'], 'linha fica', 'linhas ficam')} fora do sumário gerado.",
                "Declare a categoria ou mova as linhas para uma existente.",
                "O README perde essas entradas.",
            ))
        if item["total"] == 0:
            achados.append(finding(
                "nice", "categoria-vazia", "Categoria sem nenhum recurso", item["nome"],
                "Seção vazia no README é ruído.",
                "O leitor abre uma seção e não encontra nada.",
                "Preencha ou remova a categoria da configuração.",
                "O sumário promete o que não entrega.",
            ))
        for grupo in item["orfaos"]:
            achados.append(finding(
                "should", "subcategoria-orfa", "Subcategoria não declarada", f"{item['nome']} › {grupo['nome']}",
                "A subcategoria precisa existir na configuração da categoria.",
                f"{_n(len(grupo['linhas']), 'linha cai', 'linhas caem')} depois das seções oficiais.",
                "Declare na configuração ou funda com uma subcategoria existente.",
                "A ordem do README fica imprevisível.",
            ))
    estagnados = [linha for linha in linhas if _bool(linha.get("estagnado", ""))]
    if estagnados:
        achados.append(finding(
            "should", "estagnados", "Recursos marcados como estagnados", f"{len(estagnados)} linha(s)",
            "A marca vem da última checagem: projeto parado ou arquivado.",
            "Lista que nunca remove nada vira catálogo de museu.",
            "Reavalie ou mova para uma seção de arquivo.",
            "A seleção perde o sentido.",
        ))
    if metrics["nunca_checados"]:
        achados.append(finding(
            "should", "nunca-checados", "Linhas sem data de checagem", f"{metrics['nunca_checados']} linha(s)",
            "Toda linha tem `checado_em`; o esquecido apodrece calado.",
            "Sem data, ninguém sabe o que ainda vale.",
            "Preencha `checado_em` na próxima revisão.",
            "A idade real do catálogo fica desconhecida.",
        ))

    perguntas = ["Alguma seção existe só porque a categoria foi criada antes do primeiro recurso?"]
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Sumário gerado", ""]
    for item in arvore:
        marca = " (fora da configuração)" if item["desconhecida"] else ""
        extra += [f"- **{item['nome']}**{marca} — {item['total']} recurso(s)"]
        for grupo in item["subcategorias"]:
            extra += [f"  - {grupo['nome']} — {len(grupo['linhas'])}"]
        for grupo in item["orfaos"]:
            extra += [f"  - {grupo['nome']} (não declarada) — {len(grupo['linhas'])}"]
    extra += [""]
    rows = []
    for item in arvore:
        rows.append({"categoria": item["nome"], "total": item["total"],
                     "subcategorias": len(item["subcategorias"]), "declarada": "não" if item["desconhecida"] else "sim"})
    return {
        **common(
            analysis="curadoria.catalogo",
            mode=modo,
            title="Catálogo por categoria",
            summary=[
                f"{_n(metrics['linhas'], 'linha', 'linhas')} em {_n(metrics['categorias'], 'categoria', 'categorias')}.",
                f"{_n(metrics['ativos'], 'ativo', 'ativos')}, {_n(metrics['estagnados'], 'marcado', 'marcados')} como estagnado, "
                f"{metrics['nunca_checados']} sem data de checagem.",
                "A ordem é a da configuração; dentro da seção, ordem alfabética sem acento.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_CATALOGO,
            extra_sections=extra,
        ),
        "arvore": arvore,
        "executado": False,
    }


LIMITES_CATALOGO = [
    "A leitura aceita o cabeçalho em português ou no inglês do schema original; colunas a mais são ignoradas com aviso.",
    "Nada é buscado na rede: categoria, atividade e data são o que o CSV declara.",
    "Linhas com categoria desconhecida não são descartadas: aparecem no fim, marcadas.",
]


# --------------------------------------------------------------- 3. README

def _escapar_markdown(valor: str) -> str:
    return valor.replace("[", "\\[").replace("]", "\\]").replace("|", "\\|")


def _entrada_markdown(linha: dict[str, str]) -> str:
    nome = _escapar_markdown(linha.get("nome", "") or "(sem nome)")
    link = linha.get("link", "")
    autor = linha.get("autor", "")
    descricao = linha.get("descricao", "").replace("\n", " ").strip()
    alvo = f"[{nome}]({link})" if link.startswith("https://") else nome
    sufixo = f" — {descricao}" if descricao else ""
    credito = f" · por {autor}" if autor and not descricao else ""
    return f"- {alvo}{sufixo}{credito}"


def gerar_readme(*, csv_texto: str, categorias: str = "", titulo: str = "Recursos escolhidos",
                 intro: str = "", hoje: str = "", modo: str = "full") -> dict[str, Any]:
    config = _config(categorias)
    referencia = _hoje(hoje)
    linhas, avisos = _ler(csv_texto)
    if not linhas:
        raise CuradoriaError("O CSV tem cabeçalho, mas nenhuma linha de recurso.")
    titulo = titulo.strip() or "Recursos escolhidos"
    if len(titulo) > 90:
        raise CuradoriaError("O título passa de 90 caracteres.")
    arvore = _arvore(linhas, config)
    metrics = _metrica_catalogo(arvore, linhas, referencia)

    usados: dict[str, int] = {}

    def ancora(nome: str) -> str:
        base = _slug(nome)
        contagem = usados.get(base, 0)
        usados[base] = contagem + 1
        return base if contagem == 0 else f"{base}-{contagem}"

    achados: list[dict[str, Any]] = []
    if metrics["desconhecidas"]:
        achados.append(finding(
            "should", "fora-do-sumario", "Categoria desconhecida no README", f"{metrics['desconhecidas']}",
            "O sumário é montado a partir da configuração.",
            "As linhas dessas categorias aparecem no fim, sem entrada no sumário.",
            "Declare a categoria antes de gerar o README.",
            "O leitor não encontra a seção pelo índice.",
        ))
    vazias = [item["nome"] for item in arvore if item["total"] == 0]
    if vazias:
        achados.append(finding(
            "nice", "secao-vazia", "Seções sem recurso no arquivo gerado", ", ".join(vazias),
            "Seção vazia ainda aparece com cabeçalho.",
            "Um README com seções ocas parece abandonado.",
            "Remova da configuração ou preencha.",
            "A primeira impressão é de lista incompleta.",
        ))

    # --- montagem
    linhas_md: list[str] = [f"# {titulo}", ""]
    if intro.strip():
        linhas_md += [intro.strip(), ""]
    linhas_md += [
        f"**{_n(metrics['linhas'], 'recurso', 'recursos')}** em "
        f"{_n(metrics['categorias'], 'categoria', 'categorias')} · "
        f"{_n(metrics['ativos'], 'ativo', 'ativos')} · atualizado em {referencia.isoformat()}",
        "",
        "## Sumário",
        "",
    ]
    ancoras: list[tuple[int, str, str]] = []
    for item in arvore:
        if item["total"] == 0:
            continue
        ancoras.append((2, item["nome"], ancora(item["nome"])))
        for grupo in item["subcategorias"]:
            if grupo["linhas"]:
                ancoras.append((3, f"{item['nome']} › {grupo['nome']}", ancora(f"{item['nome']} {grupo['nome']}")))
    for nivel, rotulo, alvo in ancoras:
        recuo = "  " * (nivel - 2)
        linhas_md.append(f"{recuo}- [{rotulo}](#{alvo})")
    linhas_md += [""]

    for item in arvore:
        if item["total"] == 0:
            continue
        linhas_md += [f"## {item['nome']}", ""]
        if item["descricao"]:
            linhas_md += [f"_{item['descricao']}_", ""]
        if item["diretos"]:
            linhas_md += [_entrada_markdown(linha) for linha in sorted(item["diretos"], key=_ordem)]
            linhas_md.append("")
        for grupo in item["subcategorias"]:
            if not grupo["linhas"]:
                continue
            linhas_md += [f"### {grupo['nome']}", ""]
            if grupo["descricao"]:
                linhas_md += [f"_{grupo['descricao']}_", ""]
            linhas_md += [_entrada_markdown(linha) for linha in sorted(grupo["linhas"], key=_ordem)]
            linhas_md.append("")
        for grupo in item["orfaos"]:
            linhas_md += [f"### {grupo['nome']}", ""]
            linhas_md += [_entrada_markdown(linha) for linha in sorted(grupo["linhas"], key=_ordem)]
            linhas_md.append("")
    linhas_md += ["---", "",
                  f"Gerado a partir do CSV com {_n(metrics['linhas'], 'linha', 'linhas')}. "
                  "A ordem das seções vem da configuração; a ordem interna é alfabética.", ""]
    markdown = "\n".join(linhas_md)

    perguntas = ["O sumário cabe na primeira tela do README?"]
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    metrics = {**metrics, "secoes": len(ancoras), "caracteres": len(markdown)}
    extra = ["", "## README gerado", "", "```markdown", markdown[:20000], "```", ""]
    return {
        **common(
            analysis="curadoria.readme",
            mode=modo,
            title="README do catálogo",
            summary=[
                f"{_n(metrics['linhas'], 'recurso', 'recursos')} em {_n(len(ancoras), 'seção', 'seções')} do sumário.",
                "Âncoras no padrão do GitHub, sem acento e em minúsculas.",
                "Nenhum conteúdo de terceiro é copiado: o texto vem do seu CSV.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=[{"nivel": nivel, "secao": rotulo, "ancora": f"#{alvo}"} for nivel, rotulo, alvo in ancoras],
            metrics=metrics,
            limitations=LIMITES_README,
            extra_sections=extra,
        ),
        "markdown": markdown,
        "executado": False,
    }


LIMITES_README = [
    "O README é montado por regra, sem IA: título, descrição e links saem exatamente como estão no CSV.",
    "A âncora segue a convenção do GitHub, mas um título repetido recebe sufixo numérico.",
    "A data do rodapé é a de `hoje` (por padrão, o dia da execução).",
]


# --------------------------------------------------------------- 4. ticker

def _snapshot(texto: str, rotulo: str) -> dict[str, int]:
    if not texto.strip():
        raise CuradoriaError(f"Cole o snapshot {rotulo} no formato `dono/repo,estrelas`.")
    dados: dict[str, int] = {}
    leitor = csv.reader(io.StringIO(texto.lstrip("\ufeff")))
    for numero, bruto in enumerate(leitor, start=1):
        if not any(celula.strip() for celula in bruto):
            continue
        if numero == 1 and not re.search(r"\d", bruto[-1]):
            continue
        if len(bruto) < 2:
            raise CuradoriaError(f"Linha {numero} do snapshot {rotulo} precisa de `dono/repo,estrelas`.")
        nome = bruto[0].strip().lower()
        if "/" not in nome:
            raise CuradoriaError(f"Linha {numero}: `{bruto[0].strip()}` não está no formato dono/repo.")
        try:
            dados[nome] = int(float(bruto[1].strip()))
        except ValueError as erro:
            raise CuradoriaError(f"Linha {numero}: estrelas não numéricas.") from erro
        if len(dados) > MAX_LINHAS:
            raise CuradoriaError(f"Mais de {MAX_LINHAS} repositórios no snapshot.")
    if not dados:
        raise CuradoriaError(f"O snapshot {rotulo} está vazio.")
    return dados


def comparar_ticker(*, anterior: str, atual: str, protecoes: str = "", modo: str = "full") -> dict[str, Any]:
    import json

    filtros = dict(SEGURANCA_TICKER)
    if protecoes.strip():
        try:
            dados = json.loads(protecoes)
        except json.JSONDecodeError as erro:
            raise CuradoriaError(f"JSON de proteções inválido: {erro.msg}.") from erro
        if not isinstance(dados, dict):
            raise CuradoriaError("`protecoes` precisa ser um objeto JSON.")
        for chave in filtros:
            if chave in dados:
                valor = dados[chave]
                filtros[chave] = list(valor) if isinstance(valor, (list, tuple)) else [str(valor)]

    antes = _snapshot(anterior, "anterior")
    depois = _snapshot(atual, "atual")
    donos = {_norm(item) for item in filtros["donos_banidos"] if _texto(item)}
    exatos = {_norm(item) for item in filtros["nomes_exatos"] if _texto(item)}
    contem = tuple(_norm(item) for item in filtros["nomes_contem"] if _texto(item))
    completos = {_norm(item) for item in filtros["nomes_completos"] if _texto(item)}

    def motivo(nome: str) -> str:
        dono, _, repo = nome.partition("/")
        if nome in completos:
            return "nome completo na lista de bloqueio"
        if dono in donos:
            return "dono bloqueado"
        if repo in exatos:
            return f"repositório chamado `{repo}` — imitação do produto"
        for trecho in contem:
            if trecho and trecho in repo:
                return f"nome contém `{trecho}` — provável cópia de código-fonte"
        return ""

    rows: list[dict[str, Any]] = []
    excluidos: list[dict[str, str]] = []
    for nome in sorted(set(antes) | set(depois)):
        bloqueio = motivo(nome)
        base, topo = antes.get(nome), depois.get(nome)
        if bloqueio:
            excluidos.append({"repo": nome, "motivo": bloqueio})
            continue
        if base is None:
            estado = "novo"
            delta = topo or 0
        elif topo is None:
            estado = "saiu"
            delta = -(base or 0)
        else:
            delta = topo - base
            estado = "subiu" if delta > 0 else "caiu" if delta < 0 else "estável"
        percentual = 0.0
        if base:
            percentual = round((delta / base) * 100, 1)
        rows.append({
            "repo": nome, "antes": base or 0, "depois": topo or 0, "delta": delta,
            "percentual": percentual, "estado": estado,
        })

    rows.sort(key=lambda item: (-item["delta"], item["repo"]))
    subiram = [item for item in rows if item["delta"] > 0]
    chamadas = rows[:5]

    achados: list[dict[str, Any]] = []
    if excluidos:
        achados.append(finding(
            "nice", "protecao-ativa", "Repositórios fora do ranking", f"{_n(len(excluidos), 'repo', 'repos')}",
            "O ticker não exibe imitação de produto nem provável cópia de código-fonte.",
            "Sem o aviso, o ranking pareceria menor do que é e ninguém saberia o motivo.",
            "Nenhuma ação: a filtragem é intencional. Revise as proteções se um projeto legítimo cair nelas.",
            "Alguém procura um projeto e não o encontra no ranking, sem explicação.",
        ))
    if not subiram:
        achados.append(finding(
            "nice", "sem-crescimento", "Nenhum repositório cresceu", "0",
            "Os dois snapshots são idênticos ou todos caíram.",
            "Snapshots do mesmo dia não mostram movimento.",
            "Cole snapshots com pelo menos um dia de intervalo.",
            "O ticker não conta história nenhuma.",
        ))
    if len(antes) > 0 and len(set(antes) & set(depois)) == 0:
        achados.append(finding(
            "should", "snapshots-distintos", "Snapshots sem repositório em comum", "0",
            "O ticker compara o mesmo conjunto de repos entre datas.",
            "Conjuntos disjuntos sugerem arquivo errado colado no lugar.",
            "Use o mesmo recorte nos dois arquivos.",
            "Todo mundo aparece como novo.",
        ))

    metrics = {
        "antes": len(antes),
        "depois": len(depois),
        "comum": len(set(antes) & set(depois)),
        "novos": sum(1 for item in rows if item["estado"] == "novo"),
        "sairam": sum(1 for item in rows if item["estado"] == "saiu"),
        "subiram": len(subiram),
        "excluidos": len(excluidos),
        "delta_total": sum(item["delta"] for item in rows),
    }
    perguntas = ["Algum repositório cresceu por campanha e não por uso?"]
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Maiores movimentos", ""]
    for item in chamadas:
        extra += [f"- `{item['repo']}` {item['antes']} → {item['depois']} "
                  f"({item['delta']:+d}, {item['percentual']:+.1f}%) · {item['estado']}"]
    if excluidos:
        extra += ["", "## Excluídos", ""]
        for item in excluidos[:20]:
            extra += [f"- `{item['repo']}` — {item['motivo']}"]
    extra += ["", "## Proteções aplicadas", "",
              f"- Donos bloqueados: {len(donos)}",
              f"- Nomes exatos: {', '.join(sorted(exatos)) or '—'}",
              f"- Trechos no nome: {', '.join(contem) or '—'}",
              f"- Nomes completos: {len(completos)}", ""]
    return {
        **common(
            analysis="curadoria.ticker",
            mode=modo,
            title="Movimento de estrelas",
            summary=[
                f"{_n(metrics['comum'], 'repositório', 'repositórios')} em comum; {_n(metrics['novos'], 'novo', 'novos')}, {metrics['sairam']} saíram.",
                f"{metrics['subiram']} cresceram; variação total de {metrics['delta_total']:+d} estrelas.",
                "Proteções contra imitação de produto e cópia de código-fonte são aplicadas antes do ranking.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows[:80],
            metrics=metrics,
            limitations=LIMITES_TICKER,
            extra_sections=extra,
        ),
        "excluidos": excluidos,
        "executado": False,
    }


LIMITES_TICKER = [
    "As estrelas vêm dos dois arquivos que você cola; nenhuma chamada à API do GitHub é feita.",
    "As proteções são heurísticas de nome e dono: elas não provam má-fé nem verificam o conteúdo do repositório.",
    "Repositório renomeado aparece como um que saiu e outro que nasceu — a comparação é por nome completo.",
]


# --------------------------------------------------------------- 5. higiene

def auditar_higiene(*, csv_texto: str, categorias: str = "", hoje: str = "",
                    dias_para_checar: int = 90, modo: str = "full") -> dict[str, Any]:
    config = _config(categorias)
    referencia = _hoje(hoje)
    if dias_para_checar < 1 or dias_para_checar > 3650:
        raise CuradoriaError("`dias_para_checar` precisa ficar entre 1 e 3650.")
    linhas, avisos = _ler(csv_texto)
    if not linhas:
        raise CuradoriaError("O CSV tem cabeçalho, mas nenhuma linha de recurso.")
    arvore = _arvore(linhas, config)
    metrics = _metrica_catalogo(arvore, linhas, referencia)
    achados: list[dict[str, Any]] = []
    for aviso in avisos:
        achados.append(finding(
            "nice", "coluna-ignorada", "Coluna fora do schema", aviso,
            "O schema tem 12 colunas.", "Coluna a mais não é lida.",
            "Remova ou renomeie.", "O dado fica invisível.",
        ))

    vistos_id: dict[str, int] = {}
    vistos_link: dict[str, str] = {}
    vistos_nome: dict[str, str] = {}
    for linha in linhas:
        numero = linha.get("_linha", "?")
        identificador = linha.get("id", "")
        link = linha.get("link", "")
        nome = linha.get("nome", "")
        if not identificador:
            achados.append(finding(
                "must", "id-ausente", "Linha sem ID", f"linha {numero}",
                "O ID é o identificador opaco da linha.",
                "Sem ID não há como mover ou atualizar a entrada com segurança.",
                "Gere um ID de 8 dígitos hexadecimais.",
                "A linha só existe por posição.",
            ))
        elif not ID.match(identificador):
            achados.append(finding(
                "should", "id-formato", "ID fora do padrão", f"linha {numero}: {identificador}",
                "O padrão é 8 dígitos hexadecimais minúsculos, sem prefixo.",
                "IDs com prefixo antigo ficam, mas novos não devem nascer assim.",
                "Gere um ID opaco novo ao editar a linha.",
                "Ferramentas que comparam ID começam a divergir.",
            ))
        if identificador:
            vistos_id[identificador] = vistos_id.get(identificador, 0) + 1
        if _norm(link) and _norm(link) in vistos_link:
            achados.append(finding(
                "must", "link-duplicado", "Link repetido no catálogo", link[:80],
                "A deduplicação é por link.",
                "Duas linhas para o mesmo projeto quebram a contagem e a revisão.",
                "Una as duas linhas.",
                "O catálogo conta duas vezes o mesmo recurso.",
            ))
        elif _norm(link):
            vistos_link[_norm(link)] = nome
        if _norm(nome) and _norm(nome) in vistos_nome:
            achados.append(finding(
                "should", "nome-duplicado", "Nome repetido no catálogo", nome,
                "Nomes distintos ajudam o leitor a diferenciar.",
                "Dois nomes iguais costumam ser a mesma coisa.",
                "Diferencie ou una.",
                "O leitor não sabe qual abrir.",
            ))
        else:
            vistos_nome[_norm(nome)] = nome
        motivo = _url_valida(link)
        if motivo:
            achados.append(finding(
                "must", "link-invalido", "Link inválido", f"{nome or 'linha ' + numero}: {motivo}",
                "Todo link começa com `https://` e não tem espaço nem metacaractere.",
                "Link quebrado ou perigoso dentro do README.",
                "Corrija a URL.",
                "O leitor caiu num 404 ou num link armado.",
            ))
        motivo_autor = _url_valida(linha.get("link_autor", "")) if linha.get("link_autor") else None
        if motivo_autor:
            achados.append(finding(
                "should", "link-autor-invalido", "Link do autor inválido", f"{nome}: {motivo_autor}",
                "O crédito aponta para uma URL https válida.",
                "Crédito quebrado é pior que crédito ausente.",
                "Corrija ou esvazie o campo.",
                "O autor não é encontrado.",
            ))
        adicionado = _data(linha.get("adicionado_em", ""))
        if linha.get("adicionado_em", "").strip() and adicionado is None:
            achados.append(finding(
                "should", "data-invalida", "Data de inclusão inválida", f"{nome}: {linha.get('adicionado_em')}",
                "Datas usam AAAA-MM-DD.",
                "Data malformada quebra ordenação e relatório.",
                "Corrija o formato.",
                "A entrada não pode ser datada.",
            ))
        checado = _data(linha.get("checado_em", ""))
        if checado is None:
            achados.append(finding(
                "should", "sem-checagem", "Linha nunca checada", nome or f"linha {numero}",
                "Toda linha tem uma data de checagem.",
                "Sem data, ninguém sabe se o projeto ainda existe.",
                "Abra o link e registre a data.",
                "O catálogo envelhece sem avisar.",
            ))
        elif (referencia - checado).days > dias_para_checar:
            dias = (referencia - checado).days
            achados.append(finding(
                "nice", "checagem-antiga", "Checagem antiga", f"{nome}: {dias} dias",
                f"Revisão a cada {dias_para_checar} dias mantém a lista honesta.",
                "Projeto de um ano atrás pode estar arquivado.",
                "Reabra o link ou marque como estagnado.",
                "A lista vira arquivo morto sem dizer.",
            ))
        for item in auditar_descricao(linha.get("descricao", "")):
            achados.append(finding(
                "should", "descricao", f"{item['titulo']} — {nome or 'linha ' + numero}", item["kind"],
                "A descrição diz o que faz, em uma linha.",
                "O padrão de escrita é o que separa lista de catálogo.",
                "Reescreva no presente, sem superlativo.",
                "A credibilidade da seção cai.",
            ))
        if _bool(linha.get("estagnado", "")) and _data(linha.get("checado_em", "")) is None:
            achados.append(finding(
                "nice", "estagnado-sem-checagem", "Estagnado sem data de checagem",
                nome or f"linha {numero}",
                "A marca de estagnação nasce de uma checagem.",
                "Marcar sem checar é opinião disfarçada de dado.",
                "Registre a data que justificou a marca.",
                "A marca não é auditável.",
            ))

    for identificador, total in vistos_id.items():
        if total > 1:
            achados.append(finding(
                "must", "id-duplicado", "ID repetido", identificador,
                "Cada linha tem ID único.",
                "Mover ou atualizar por ID fica ambíguo.",
                "Gere um ID novo para a linha duplicada.",
                "Uma edição pode atingir a linha errada.",
            ))
    for item in arvore:
        if item["desconhecida"]:
            achados.append(finding(
                "must", "categoria-desconhecida", "Categoria fora da configuração", item["nome"],
                "Categoria e subcategoria precisam existir na configuração.",
                f"{_n(item['total'], 'linha fora', 'linhas fora')} do índice.",
                "Declare ou mova.",
                "O README gerado perde a seção.",
            ))
        for grupo in item["orfaos"]:
            achados.append(finding(
                "should", "subcategoria-orfa", "Subcategoria não declarada", f"{item['nome']} › {grupo['nome']}",
                "A subcategoria precisa constar sob a categoria.",
                "Ela aparece fora de ordem no README.",
                "Declare na configuração.",
                "A navegação fica imprevisível.",
            ))

    metrics = {**metrics, "dias_para_checar": dias_para_checar,
               "ids_repetidos": sum(1 for total in vistos_id.values() if total > 1)}
    perguntas = ["Qual linha você removeria hoje se tivesse que remover uma?"]
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## O que a higiene confere", ""]
    for item in CHECKLIST_HIGIENE:
        extra += [f"- {item}"]
    extra += [""]
    return {
        **common(
            analysis="curadoria.higiene",
            mode=modo,
            title="Higiene do catálogo",
            summary=[
                f"{_n(metrics['linhas'], 'linha auditada', 'linhas auditadas')} contra {len(CHECKLIST_HIGIENE)} checagens.",
                f"{_n(metrics['ids_repetidos'], 'ID repetido', 'IDs repetidos')}; {metrics['nunca_checados']} sem checagem.",
                "O critério de checagem antiga é de "
                f"{dias_para_checar} dias contra {referencia.isoformat()}.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=[{"checagem": item} for item in CHECKLIST_HIGIENE],
            metrics=metrics,
            limitations=LIMITES_HIGIENE,
            extra_sections=extra,
        ),
        "executado": False,
    }


CHECKLIST_HIGIENE = [
    "ID presente, único e no formato de 8 dígitos hexadecimais",
    "Link https válido, sem espaço nem metacaractere",
    "Link e nome sem duplicata no catálogo",
    "Link do autor válido quando declarado",
    "Categoria declarada na configuração",
    "Subcategoria declarada sob a categoria",
    "Data de inclusão no formato AAAA-MM-DD",
    "Data de checagem presente e recente",
    "Descrição em uma linha, 10–500 caracteres, sem emoji, pitch ou segunda pessoa",
    "Estagnação acompanhada da checagem que a justifica",
]

LIMITES_HIGIENE = [
    "A auditoria é do CSV: nenhum link é aberto e nenhum repositório é consultado.",
    "Checagem antiga é um lembrete, não prova de abandono.",
    "O estilo da descrição é lexical: um texto honesto pode esbarrar numa palavra da lista de pitch.",
]


# --------------------------------------------------------------- 6. regras

def curadoria_catalogo() -> dict[str, Any]:
    return {
        "fonte": "hesreallyhim/awesome-claude-code (CC BY-NC-ND 4.0)",
        "versao": VERSAO,
        "principio": "Uma lista boa é uma decisão editorial: entra pouco, entra revisado, e o que envelhece sai.",
        "licenca": {
            "id": "CC BY-NC-ND 4.0",
            "resumo": "Atribuição, não comercial, sem derivados.",
            "efeito": "O catálogo do upstream não é copiado nem adaptado: este módulo implementa só o mecanismo, com dados seus.",
        },
        "colunas": list(COLUNAS),
        "categorias": [
            {
                "nome": item["nome"],
                "descricao": item.get("descricao", ""),
                "submetivel": item.get("submetivel", True),
                "subcategorias": [sub["nome"] for sub in item["subcategorias"]],
            }
            for item in CATEGORIAS
        ],
        "elegibilidade": REGRAS_ELEGIBILIDADE,
        "estilo": REGRAS_ESTILO,
        "licenca_regras": REGRAS_LICENCA,
        "protecoes": SEGURANCA_TICKER,
        "higiene": CHECKLIST_HIGIENE,
        "executado": False,
    }
