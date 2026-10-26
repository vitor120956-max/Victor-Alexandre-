"""Estação assistida — tarefa, permissões, recibos, agenda, limites e memória.

Inspirado em feder-cr/invisible_dots (MIT, 2026). Implementação própria e
determinística. Nada do upstream é instalado ou executado: não há VM, QEMU,
imagem dourada, navegador, OpenRouter, MCP, Telegram, WhatsApp nem servidor.

O recorte é o que sobrevive sem máquina: o **contrato de governança** de um
agente de computador — o plano de uma tarefa durável, a matriz de permissões
(allow/ask/deny), a auditoria de execução com recuperação após queda, a agenda
de automações, a classificação de limites e a higiene das notas e skills que o
próprio agente escreve.

Uma decisão declarada: o upstream se anuncia como "indetectável por anti-bots".
Esse ponto **não** é adaptado. `estacao.limites` bloqueia evasão de detecção,
resolução de CAPTCHA, rotação de contas para furar limite e desrespeito a
termos ou robots.txt, e explica a alternativa legítima em cada caso.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .review import common, finalize, finding


class EstacaoError(ValueError):
    """Erro de entrada da estação; a API devolve 200 com `ok:false`."""


VERSAO = "0.51.0"
MAX_TEXTO = 40_000
MAX_LISTA = 60

PASSOS_MAX = 60
CUSTO_MAX = 1.0
CUSTO_TETO = 100.0
PASSOS_TETO = 500


# --------------------------------------------------------------- vocabulário

FERRAMENTAS: dict[str, dict[str, Any]] = {
    "exec": {"permissao": "computer.exec", "risco": "alto", "efeito": "execução",
             "nota": "Roda `bash -lc` na máquina do agente, com timeout de 60 s por padrão e 600 s no máximo."},
    "exec_session": {"permissao": "computer.exec", "risco": "alto", "efeito": "execução",
                     "nota": "Envia entrada, espera, lê ou encerra um trabalho em segundo plano."},
    "list_exec_sessions": {"permissao": "computer.exec", "risco": "médio", "efeito": "leitura",
                           "nota": "Lista os trabalhos em segundo plano."},
    "read_file": {"permissao": "files.read", "risco": "baixo", "efeito": "leitura",
                  "nota": "Lê um arquivo de texto por janela de linhas."},
    "list_dir": {"permissao": "files.read", "risco": "baixo", "efeito": "leitura",
                 "nota": "Lista um diretório, opcionalmente recursivo."},
    "find_files": {"permissao": "files.read", "risco": "baixo", "efeito": "leitura",
                   "nota": "Procura arquivos por termo, glob ou tipo."},
    "grep": {"permissao": "files.read", "risco": "baixo", "efeito": "leitura",
             "nota": "Procura expressão regular no conteúdo dos arquivos."},
    "write_file": {"permissao": "files.write", "risco": "médio", "efeito": "escrita",
                   "nota": "Escreve um arquivo inteiro."},
    "edit_file": {"permissao": "files.write", "risco": "médio", "efeito": "escrita",
                  "nota": "Substitui texto em um arquivo."},
    "apply_patch": {"permissao": "files.write", "risco": "médio", "efeito": "escrita",
                    "nota": "Aplica edições estruturadas, com simulação."},
    "cron": {"permissao": "automations", "risco": "alto", "efeito": "futuro",
             "nota": "Cria, lista e remove automações agendadas do próprio agente."},
    "computer_screenshot": {"permissao": "computer.screenshot", "risco": "médio", "efeito": "leitura",
                            "nota": "Captura a tela inteira do desktop do agente."},
    "browser_identity_list": {"permissao": "browser.identity.list", "risco": "baixo", "efeito": "leitura",
                              "nota": "Lista identidades, estado e limite de abertas."},
    "browser_identity_create": {"permissao": "browser.identity.create", "risco": "médio", "efeito": "escrita",
                                "nota": "Cria uma identidade fechada, com perfil próprio."},
    "browser_identity_delete": {"permissao": "browser.identity.delete", "risco": "alto", "efeito": "destrutivo",
                                "nota": "Apaga a identidade e o perfil dela."},
    "browser_identity_launch": {"permissao": "browser.identity.launch", "risco": "médio", "efeito": "escrita",
                                "nota": "Abre o navegador de uma identidade."},
    "browser_identity_close": {"permissao": "browser.identity.close", "risco": "baixo", "efeito": "escrita",
                               "nota": "Fecha o navegador mantendo o perfil."},
    "browser_navigate": {"permissao": "browser.navigate", "risco": "baixo", "efeito": "rede",
                         "nota": "Abre http:// ou https://; outros esquemas são recusados."},
    "browser_snapshot": {"permissao": "browser.read", "risco": "baixo", "efeito": "leitura",
                         "nota": "Lista elementos interativos com seletor e coordenada."},
    "browser_read_text": {"permissao": "browser.read", "risco": "baixo", "efeito": "leitura",
                          "nota": "Lê o texto da página ou de um elemento."},
    "browser_read_html": {"permissao": "browser.read", "risco": "baixo", "efeito": "leitura",
                          "nota": "Lê o HTML limpo da página."},
    "browser_take_screenshot": {"permissao": "browser.read", "risco": "baixo", "efeito": "leitura",
                                "nota": "Captura a página para o modelo."},
    "browser_evaluate": {"permissao": "browser.read", "risco": "médio", "efeito": "leitura",
                         "nota": "Lê com script; recusa um script que age na página."},
    "browser_click": {"permissao": "browser.act", "risco": "alto", "efeito": "escrita",
                      "nota": "Clica no elemento que o seletor nomeia."},
    "browser_click_at": {"permissao": "browser.act", "risco": "alto", "efeito": "escrita",
                         "nota": "Clica em um ponto e devolve a página depois."},
    "browser_type": {"permissao": "browser.act", "risco": "alto", "efeito": "escrita",
                     "nota": "Preenche um campo tecla por tecla."},
    "browser_press_key": {"permissao": "browser.act", "risco": "alto", "efeito": "escrita",
                          "nota": "Pressiona uma tecla ou atalho."},
    "browser_select_option": {"permissao": "browser.act", "risco": "alto", "efeito": "escrita",
                              "nota": "Escolhe uma opção por rótulo ou valor."},
    "browser_upload_files": {"permissao": "browser.act", "risco": "alto", "efeito": "escrita",
                             "nota": "Anexa arquivos do agente a um campo de arquivo."},
    "add_mcp_server": {"permissao": "mcp.servers.add", "risco": "alto", "efeito": "futuro",
                       "nota": "Adiciona um servidor MCP — e com ele novas ferramentas."},
}

PERMISSOES: dict[str, dict[str, Any]] = {
    "computer.exec": {"risco": "alto", "padrao": "allow", "rotulo": "Executar comandos"},
    "computer.screenshot": {"risco": "médio", "padrao": "allow", "rotulo": "Capturar a tela"},
    "files.read": {"risco": "baixo", "padrao": "allow", "rotulo": "Ler arquivos"},
    "files.write": {"risco": "médio", "padrao": "allow", "rotulo": "Escrever arquivos"},
    "automations": {"risco": "alto", "padrao": "ask", "rotulo": "Criar automações"},
    "browser.identity.list": {"risco": "baixo", "padrao": "allow", "rotulo": "Listar identidades"},
    "browser.identity.create": {"risco": "médio", "padrao": "allow", "rotulo": "Criar identidade"},
    "browser.identity.delete": {"risco": "alto", "padrao": "ask", "rotulo": "Apagar identidade"},
    "browser.identity.launch": {"risco": "médio", "padrao": "allow", "rotulo": "Abrir identidade"},
    "browser.identity.close": {"risco": "baixo", "padrao": "allow", "rotulo": "Fechar identidade"},
    "browser.navigate": {"risco": "baixo", "padrao": "allow", "rotulo": "Navegar"},
    "browser.read": {"risco": "baixo", "padrao": "allow", "rotulo": "Ler a página"},
    "browser.act": {"risco": "alto", "padrao": "allow", "rotulo": "Agir na página"},
    "mcp.servers.add": {"risco": "alto", "padrao": "ask", "rotulo": "Adicionar servidor MCP"},
}

DECISOES = ("allow", "ask", "deny")
DECISAO_PADRAO = "deny"

ESTADOS = {
    "pronta": "Sem trabalho em curso; aceita mensagem, tarefa ou automação.",
    "trabalhando": "Executando um turno: uma chamada de ferramenta por vez, na ordem.",
    "aguardando-aprovacao": "Um pedido `ask` parou a rodada e espera decisão humana.",
    "dormindo": "Computador desligado por ócio; acorda com mensagem, tarefa ou automação.",
    "interrompida": "O processo caiu ou foi parado durante uma chamada; o resultado é desconhecido.",
    "falhou": "A tarefa estourou passos, orçamento ou erros repetidos.",
}

# ------------------------------------------------------------------ utilidades

def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _normal(texto: str) -> str:
    return re.sub(r"\s+", " ", _sem_acento(texto).lower()).strip()


def _linhas(texto: str) -> list[str]:
    return [linha.strip() for linha in texto.splitlines() if linha.strip() and not linha.strip().startswith("#")]


def _moeda(valor: float) -> str:
    return f"US$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- ferramentas

def _permissao_da(ferramenta: str) -> str:
    dado = FERRAMENTAS.get(ferramenta)
    return dado["permissao"] if dado else ""


def _risco(permissao: str) -> str:
    if permissao.startswith("mcp."):
        return "médio"
    return PERMISSOES.get(permissao, {}).get("risco", "alto")


def _efetiva(politica: dict[str, str], permissao: str) -> str:
    if permissao in politica:
        return politica[permissao]
    if permissao.startswith("mcp."):
        return "ask"
    return PERMISSOES.get(permissao, {}).get("padrao", DECISAO_PADRAO)


def _politica_do_texto(texto: str) -> dict[str, str]:
    politica: dict[str, str] = {}
    for linha in _linhas(texto):
        nome, separador, valor = linha.partition("=")
        if not separador:
            nome, separador, valor = linha.partition(":")
        if not separador:
            raise EstacaoError(f"Linha de política sem `=` nem `:`: `{linha}`.")
        chave = nome.strip().lower()
        decisao = valor.strip().lower()
        if decisao not in DECISOES:
            raise EstacaoError(f"Decisão inválida em `{linha}`: use allow, ask ou deny.")
        politica[chave] = decisao
    return politica


def _ferramentas_da_lista(texto: str) -> list[str]:
    brutas = [item.strip() for item in re.split(r"[,\n;]+", texto) if item.strip()]
    vistos: list[str] = []
    for item in brutas:
        chave = item.split()[0].strip().lower()
        if chave and chave not in vistos:
            vistos.append(chave)
    return vistos


# -------------------------------------------------------------------- tarefa

ACOES_DO_OBJETIVO: list[tuple[str, str, str, str]] = [
    (r"\b(abrir|navegar|visitar|acessar|entrar em)\b", "browser_navigate", "browser.navigate", "abrir a página"),
    (r"\b(clicar|selecionar|marcar|preencher|digitar|enviar formul)\b", "browser_click", "browser.act", "agir na página"),
    (r"\b(baixar|download|salvar|gravar|escrever|exportar)\b", "write_file", "files.write", "gravar o resultado"),
    (r"\b(ler|conferir|extrair|listar|buscar)\b", "read_file", "files.read", "ler o estado"),
    (r"\b(executar|rodar|comando|instalar|processar)\b", "exec", "computer.exec", "executar o programa"),
    (r"\b(agendar|automatizar|todo dia|toda semana|recorrente)\b", "cron", "automations", "criar a automação"),
    (r"\b(enviar|mandar|avisar|notificar|telegram|whatsapp|e-?mail)\b", "browser_click", "browser.act", "enviar a mensagem"),
]


def planejar_tarefa(
    *,
    objetivo: str,
    ferramentas: str,
    politica: str,
    passos_max: int,
    orcamento: float,
    modo: str,
) -> dict[str, Any]:
    objetivo = objetivo.strip()
    if len(objetivo) < 8:
        raise EstacaoError("Descreva o objetivo em uma frase: o que deve estar verdadeiro no fim.")
    declaradas = _ferramentas_da_lista(ferramentas)
    if not declaradas:
        raise EstacaoError("Declare ao menos uma ferramenta disponível (exec, read_file, browser_click…).")
    if len(declaradas) > MAX_LISTA:
        raise EstacaoError(f"Mais de {MAX_LISTA} ferramentas; o agente oferece poucas por vez.")
    polit = _politica_do_texto(politica)
    passos_max = max(3, min(int(passos_max), PASSOS_TETO))
    orcamento = max(0.01, min(float(orcamento), CUSTO_TETO))

    achados: list[dict[str, Any]] = []
    desconhecidas = [item for item in declaradas if item not in FERRAMENTAS]
    for item in desconhecidas:
        achados.append(finding(
            "must", "ferramenta-desconhecida", "Ferramenta fora do catálogo", item,
            "A tabela de permissões do upstream só oferece ferramentas declaradas.",
            f"`{item}` não existe no catálogo; não seria oferecida ao modelo.",
            "Use uma ferramenta da lista (`read_file`, `browser_click`, `exec`…) ou declare o MCP que a serve.",
            "A chamada nunca chega à política e o plano falha.",
        ))
    permitidas = [item for item in declaradas if item in FERRAMENTAS]
    tem_leitura = any(FERRAMENTAS[item]["efeito"] == "leitura" for item in permitidas)
    tem_escrita = any(FERRAMENTAS[item]["efeito"] in {"escrita", "execução", "futuro"} for item in permitidas)
    if not tem_leitura:
        achados.append(finding(
            "must", "sem-leitura", "Plano sem ferramenta de leitura", "ferramentas",
            "Observar é o primeiro passo do laço: sem ler, não há como decidir nem verificar.",
            "Toda ação ficaria às cegas.",
            "Declare `read_file`, `grep`, `browser_read_text` ou `browser_snapshot`.",
            "O agente age sem saber o estado e não consegue provar o resultado.",
        ))
    if tem_escrita and not tem_leitura:
        achados.append(finding(
            "should", "escrita-sem-prova", "Escrita sem verificação", "ferramentas",
            "Escrever sem ler de volta não prova efeito.",
            "O recibo diria 'chamado', não 'aplicado'.",
            "Acrescente uma leitura depois da escrita.",
            "Você acredita no sucesso sem evidência.",
        ))
    if passos_max < 5:
        achados.append(finding(
            "should", "orcamento-curto", "Poucos passos para o laço", f"{passos_max} passos",
            "O laço mínimo é observar, agir e verificar, com margem para erro.",
            "Com menos de cinco turnos, uma falha transitória encerra a tarefa.",
            "Use ao menos 10; 60 é o padrão do upstream.",
            "A tarefa falha por orçamento, não por dificuldade.",
        ))
    if orcamento > 5:
        achados.append(finding(
            "should", "custo-alto", "Orçamento alto por tarefa", _moeda(orcamento),
            "O custo é do modelo, por tarefa ou turno.",
            "Um laço travado pode gastar o teto inteiro.",
            "Comece com US$ 1,00 e aumente depois de medir.",
            "O gasto real passa do que você esperava.",
        ))
    if passos_max > 200:
        achados.append(finding(
            "nice", "passos-demais", "Muitos passos", f"{passos_max} passos",
            "Tarefa longa sem checkpoint é difícil de retomar.",
            "Uma queda no meio perde o contexto do que já foi feito.",
            "Divida a tarefa em partes com critério de concluído próprio.",
            "A retomada recomeça do zero.",
        ))

    alvo_acoes = [(ferramenta, permissao, rotulo) for padrao, ferramenta, permissao, rotulo
                  in ACOES_DO_OBJETIVO if re.search(padrao, _normal(objetivo))]
    if not alvo_acoes:
        alvo_acoes = [("read_file", "files.read", "ler o estado")]
    escolhidas: list[tuple[str, str, str]] = []
    for ferramenta, permissao, rotulo in alvo_acoes:
        if any(item[0] == ferramenta for item in escolhidas):
            continue
        if ferramenta not in permitidas:
            proxima = next((item for item in permitidas
                            if FERRAMENTAS[item]["permissao"] == permissao), "")
            if proxima:
                ferramenta = proxima
            else:
                achados.append(finding(
                    "must", "acao-sem-ferramenta", "Ação pedida sem ferramenta disponível", rotulo,
                    "O objetivo exige uma ação que não está declarada.",
                    f"A permissão `{permissao}` não tem ferramenta na lista.",
                    f"Declare a ferramenta da permissão `{permissao}` ou mude o objetivo.",
                    "O plano para no meio.",
                ))
                continue
        escolhidas.append((ferramenta, permissao, rotulo))

    passos: list[dict[str, Any]] = [{
        "ordem": 1, "tipo": "observar", "ferramenta": "read_file", "permissao": "files.read",
        "acao": "Ler o estado atual antes de decidir",
        "prova": "o arquivo, a página ou a lista existe e foi lida",
        "aprovacao": _efetiva(polit, "files.read") != "allow",
    }]
    ordem = 2
    for ferramenta, permissao, rotulo in escolhidas:
        decisao = _efetiva(polit, permissao)
        passos.append({
            "ordem": ordem, "tipo": "agir", "ferramenta": ferramenta, "permissao": permissao,
            "acao": rotulo.capitalize(),
            "prova": "a chamada devolveu resultado sem erro",
            "aprovacao": decisao != "allow",
        })
        ordem += 1
        if FERRAMENTAS.get(ferramenta, {}).get("efeito") in {"escrita", "execução", "futuro"}:
            passos.append({
                "ordem": ordem, "tipo": "verificar", "ferramenta": "read_file", "permissao": "files.read",
                "acao": "Ler de volta e comparar com o critério de concluído",
                "prova": "o estado observado bate com o que o objetivo pediu",
                "aprovacao": _efetiva(polit, "files.read") != "allow",
            })
            ordem += 1
    passos.append({
        "ordem": ordem, "tipo": "registrar", "ferramenta": "write_file", "permissao": "files.write",
        "acao": "Registrar o que foi feito e onde ficou",
        "prova": "a nota cita arquivo, dia e resultado",
        "aprovacao": _efetiva(polit, "files.write") != "allow",
    })

    aprovacoes = [passo for passo in passos if passo["aprovacao"]]
    if aprovacoes:
        achados.append(finding(
            "should", "aprovacao-no-plano", "O plano depende de aprovação", f"{len(aprovacoes)} passo(s)",
            "Um `ask` para a rodada e persiste a chamada com os argumentos.",
            "Enquanto ninguém decidir, a tarefa fica parada em `aguardando-aprovação`.",
            "Avise a pessoa antes de começar e leve os argumentos completos para a decisão.",
            "A tarefa parece travada sem motivo visível.",
        ))
    altos = [item for item in escolhidas if _risco(item[1]) == "alto" and _efetiva(polit, item[1]) == "allow"]
    if altos:
        achados.append(finding(
            "must", "risco-alto-livre", "Risco alto sem aprovação", ", ".join(item[1] for item in altos),
            "Ação de risco alto muda o mundo ou cria trabalho futuro.",
            "`allow` deixa o agente agir sem revisão humana.",
            "Mude a permissão para `ask` — a decisão fica registrada e vale uma vez só.",
            "Um erro de julgamento do modelo chega direto ao seu computador.",
        ))
    if len(passos) > passos_max:
        achados.append(finding(
            "should", "passos-acima", "Plano maior que o orçamento", f"{len(passos)} > {passos_max}",
            "O orçamento é o número de turnos do modelo.",
            "O plano não termina dentro do teto declarado.",
            "Aumente `passos_max` ou divida a tarefa.",
            "A tarefa falha por orçamento no último passo.",
        ))

    metrics = {
        "passos": len(passos),
        "ferramentas": len(permitidas),
        "aprovacoes": len(aprovacoes),
        "risco_alto": sum(1 for item in escolhidas if _risco(item[1]) == "alto"),
        "passos_max": passos_max,
        "orcamento": orcamento,
    }
    perguntas = [
        "Qual é a prova observável de que a tarefa terminou?",
        "Quem aprova as chamadas `ask` e em quanto tempo?",
    ]
    if any(item[1] == "automations" for item in escolhidas):
        perguntas.append("A automação criada pode rodar sem você por perto?")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)

    extra = ["", "## Passos", ""]
    for passo in passos:
        extra += [f"{passo['ordem']}. **{passo['acao']}** — `{passo['ferramenta']}` ({passo['permissao']})"
                  + (" · **aprovação**" if passo["aprovacao"] else ""),
                  f"   - Prova: {passo['prova']}", ""]
    extra += ["## Parada", ""]
    extra += ["- **Concluída:** a prova do objetivo foi observada, não só a chamada devolveu ok.",
              "- **Sem progresso:** três observações idênticas seguidas — pare e peça ajuda.",
              "- **Aprovação pendente:** a rodada para; nada depois dela roda.",
              f"- **Orçamento:** {passos_max} passos ou {_moeda(orcamento)} — o que vier primeiro.",
              "- **Queda:** releia a última observação; não repita chamada sem resultado.",
              ""]
    rows = [{
        "ordem": passo["ordem"], "tipo": passo["tipo"], "ferramenta": passo["ferramenta"],
        "permissao": passo["permissao"], "acao": passo["acao"], "prova": passo["prova"],
        "aprovacao": passo["aprovacao"],
    } for passo in passos]
    return {
        **common(
            analysis="estacao.tarefa",
            mode=modo,
            title="Plano de tarefa durável",
            summary=[
                f"Objetivo: {objetivo}",
                f"{len(passos)} passos em {len(permitidas)} ferramenta(s); {len(aprovacoes)} com aprovação.",
                "O laço é observar → agir → verificar → registrar; a parada é a prova, não o recibo.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_TAREFA,
            extra_sections=extra,
        ),
        "objetivo": objetivo,
        "passos": passos,
        "parada": [
            "Concluída quando a prova do objetivo for observada",
            "Sem progresso após três observações idênticas",
            "Aprovação pendente para a rodada",
            f"Orçamento de {passos_max} passos ou {_moeda(orcamento)}",
        ],
        "executado": False,
    }


LIMITES_TAREFA = [
    "O plano é texto: nenhuma ferramenta é oferecida, chamada ou aprovada aqui.",
    "O catálogo de ferramentas vem da tabela pública do upstream em outubro de 2026; ferramentas de MCP mudam por servidor.",
    "A escolha de ferramenta por verbo do objetivo é lexical e conservadora, não um julgamento do modelo.",
    "O custo é estimativa declarada: o gasto real depende do modelo e do provedor.",
]


# -------------------------------------------------------------- permissões

def auditar_permissoes(
    *,
    politica: str,
    ferramentas: str,
    servidores_mcp: str,
    limite_passos: int,
    limite_custo: float,
    ocio_minutos: int,
    modo: str,
) -> dict[str, Any]:
    polit = _politica_do_texto(politica)
    if not polit:
        raise EstacaoError("Declare ao menos uma permissão, por exemplo `computer.exec=ask`.")
    if len(polit) > MAX_LISTA:
        raise EstacaoError(f"Mais de {MAX_LISTA} permissões numa revisão só.")
    usadas = _ferramentas_da_lista(ferramentas)
    servidores = [item.strip().lower() for item in re.split(r"[,\n;]+", servidores_mcp) if item.strip()]
    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []

    for chave, decisao in sorted(polit.items()):
        if chave.startswith("mcp.") and chave != "mcp.servers.add":
            nome = chave.split(".", 1)[1]
            if nome not in servidores:
                achados.append(finding(
                    "must", "mcp-nao-declarado", "Permissão de MCP sem servidor declarado", chave,
                    "As ferramentas de um MCP só existem depois que a pessoa declara o servidor.",
                    f"`{chave}` não corresponde a nenhum servidor da lista.",
                    f"Declare o servidor `{nome}` ou remova a permissão.",
                    "A permissão não faz nada e esconde a ausência do servidor.",
                ))
        elif chave not in PERMISSOES:
            achados.append(finding(
                "must", "permissao-desconhecida", "Permissão fora do catálogo", chave,
                "O upstream recusa um nome que a tabela não conhece.",
                "Qualquer nome desconhecido é `deny` na prática.",
                "Use um nome de `PERMISSOES` ou `mcp.<servidor>`.",
                "Você acha que liberou algo e continua bloqueado.",
            ))
        risco = "médio" if chave.startswith("mcp.") else PERMISSOES.get(chave, {}).get("risco", "alto")
        linhas.append({
            "permissao": chave, "decisao": decisao, "risco": risco,
            "padrao": PERMISSOES.get(chave, {}).get("padrao", "deny"),
            "rotulo": PERMISSOES.get(chave, {}).get("rotulo", "Servidor MCP"),
        })

    for chave, rotulo in (
        ("computer.exec", "execução de comandos"),
        ("browser.act", "ação na página"),
        ("automations", "automações futuras"),
        ("mcp.servers.add", "novos servidores MCP"),
        ("browser.identity.delete", "exclusão de identidade"),
    ):
        if polit.get(chave) == "allow":
            achados.append(finding(
                "must" if chave in {"computer.exec", "automations", "mcp.servers.add"} else "should",
                "risco-alto-livre", f"Risco alto liberado: {rotulo}", f"{chave}=allow",
                "Essa permissão alcança execução, publicação futura ou destruição.",
                f"`{chave}` em `allow` dispensa revisão humana.",
                f"Use `{chave}=ask`; a aprovação mostra os argumentos completos e vale uma vez.",
                "O agente age sem revisão num ponto irreversível.",
            ))
    if polit.get("automations") == "deny":
        achados.append(finding(
            "nice", "automacao-negada", "Automação desligada", "automations=deny",
            "O agente não pode agendar nada.",
            "Tarefas recorrentes ficam manuais.",
            "Ligue para `ask` se quiser automação com revisão.",
            "Nada é agendado, por escolha.",
        ))
    if polit.get("files.read") == "deny":
        achados.append(finding(
            "should", "leitura-negada", "Leitura negada", "files.read=deny",
            "Sem leitura o agente não observa o próprio trabalho.",
            "Toda ação fica sem verificação.",
            "Mantenha `files.read=allow`.",
            "O agente age às cegas.",
        ))
    if polit.get("browser.read") == "deny" and polit.get("browser.act") in {"allow", "ask"}:
        achados.append(finding(
            "should", "agir-sem-ler", "Agir na página sem ler", "browser.read=deny",
            "A ação na página precisa de snapshot e texto.",
            "Sem leitura não há alvo nem prova.",
            "Libere `browser.read` junto de `browser.act`.",
            "O clique vira adivinhação.",
        ))
    if usadas:
        cobertas = {FERRAMENTAS[item]["permissao"] for item in usadas if item in FERRAMENTAS}
        negadas = sorted(chave for chave in cobertas if polit.get(chave) == "deny")
        if negadas:
            achados.append(finding(
                "must", "ferramenta-negada", "Ferramenta usada com permissão negada", ", ".join(negadas),
                "O agente recebe a ferramenta e não consegue usá-la.",
                "O plano falha na primeira chamada.",
                "Mude para `ask`/`allow` ou remova a ferramenta da lista.",
                "A tarefa para sem explicação.",
            ))
        fora = [item for item in usadas if item in FERRAMENTAS
                and FERRAMENTAS[item]["permissao"] not in polit]
        if fora:
            achados.append(finding(
                "nice", "permissao-implícita", "Ferramenta usa o padrão", ", ".join(fora),
                "Permissão ausente recebe o padrão do upstream.",
                "O comportamento depende de um valor que você não declarou.",
                "Declare explicitamente as permissões das ferramentas que usa.",
                "Uma mudança de padrão altera o seu agente.",
            ))
    if limite_passos > 120:
        achados.append(finding(
            "should", "passos-altos", "Limite de passos alto", str(limite_passos),
            "O limite existe para parar laço improdutivo.",
            "Acima de 120 turnos, o custo cresce sem sinal.",
            "Use 60 e divida a tarefa.",
            "Um laço travado consome o orçamento inteiro.",
        ))
    if limite_custo > 5:
        achados.append(finding(
            "should", "custo-alto", "Custo por tarefa alto", _moeda(limite_custo),
            "O teto é por tarefa ou turno, não por dia.",
            "Várias tarefas somam rápido.",
            "Comece em US$ 1,00.",
            "A fatura surpreende.",
        ))
    if ocio_minutos == 0:
        achados.append(finding(
            "nice", "nunca-dorme", "Máquina nunca dorme", "idle_timeout=0",
            "O upstream dorme quando não há trabalho.",
            "Manter a VM ligada custa recurso o tempo todo.",
            "Use 15 minutos.",
            "Consumo contínuo sem trabalho.",
        ))

    metrics = {
        "permissoes": len(polit),
        "allow": sum(1 for item in polit.values() if item == "allow"),
        "ask": sum(1 for item in polit.values() if item == "ask"),
        "deny": sum(1 for item in polit.values() if item == "deny"),
        "risco_alto_livre": sum(1 for chave, decisao in polit.items()
                                if decisao == "allow"
                                and (PERMISSOES.get(chave, {}).get("risco") == "alto" or chave.startswith("mcp."))),
    }
    perguntas = ["Quem responde os pedidos `ask` e em quanto tempo?"]
    if metrics["risco_alto_livre"]:
        perguntas.append("Alguma permissão de risco alto pode voltar para `ask`?")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Matriz", ""]
    for linha in linhas:
        extra += [f"- `{linha['permissao']}` → **{linha['decisao']}** ({linha['risco']}; padrão `{linha['padrao']}`)"]
    extra += ["", "## Padrões do upstream", "",
              "`computer.*`, `files.*`, `browser.*` e `memory.*` são `allow`; `browser.identity.delete` e `automations` são `ask`; nome desconhecido é `deny`.", ""]
    return {
        **common(
            analysis="estacao.permissoes",
            mode=modo,
            title="Matriz de permissões",
            summary=[
                f"{len(polit)} permissões: {metrics['allow']} allow, {metrics['ask']} ask, {metrics['deny']} deny.",
                f"{metrics['risco_alto_livre']} permissão(ões) de risco alto liberada(s) sem revisão.",
                "A decisão `ask` para a rodada, persiste os argumentos e vale uma vez só.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=linhas,
            metrics=metrics,
            limitations=LIMITES_PERMISSOES,
            extra_sections=extra,
        ),
        "matriz": linhas,
        "executado": False,
    }


LIMITES_PERMISSOES = [
    "A auditoria lê o texto da política; ela não altera a configuração nem fala com o host.",
    "Os padrões e riscos vêm da documentação pública do upstream em outubro de 2026 e podem mudar.",
    "Permissões de MCP dependem do servidor declarado; a auditoria só confere o nome.",
]


# ------------------------------------------------------------------ recibos

STATUS_RECIBO = {"intent", "ok", "erro", "interrompido", "recusado"}


@dataclass
class Recibo:
    ordem: int
    chamada: str
    ferramenta: str
    status: str
    resultado: str
    aprovacao: str
    verificado: bool
    linha: str


def _parse_recibo(linha: str, ordem: int) -> Recibo:
    campos: dict[str, str] = {}
    for parte in re.split(r"\s*\|\s*|\s+(?=[a-z_]+=)", linha):
        chave, separador, valor = parte.partition("=")
        if not separador:
            continue
        campos[chave.strip().lower()] = valor.strip()
    chamada = campos.get("id", "") or campos.get("chamada", "")
    ferramenta = campos.get("tool", "") or campos.get("ferramenta", "")
    status = (campos.get("status", "") or "ok").lower()
    if not chamada:
        chamada = f"linha-{ordem}"
    return Recibo(
        ordem=ordem,
        chamada=chamada,
        ferramenta=ferramenta,
        status=status,
        resultado=campos.get("result", "") or campos.get("resultado", ""),
        aprovacao=campos.get("approval", "") or campos.get("aprovacao", ""),
        verificado=(campos.get("verificado", "").lower() in {"sim", "true", "1"}),
        linha=linha,
    )


def auditar_recibos(*, log: str, modo: str) -> dict[str, Any]:
    linhas = _linhas(log)
    if not linhas:
        raise EstacaoError("Cole ao menos uma linha de execução.")
    if len(linhas) > 400:
        raise EstacaoError("Mais de 400 linhas; divida o log.")
    recibos = [_parse_recibo(linha, indice) for indice, linha in enumerate(linhas, start=1)]
    achados: list[dict[str, Any]] = []
    por_chamada: dict[str, list[Recibo]] = {}
    for recibo in recibos:
        por_chamada.setdefault(recibo.chamada, []).append(recibo)
        if recibo.ferramenta and recibo.ferramenta not in FERRAMENTAS and not recibo.ferramenta.startswith("mcp_"):
            achados.append(finding(
                "should", "ferramenta-fora", "Ferramenta fora do catálogo", recibo.ferramenta,
                "O log cita uma ferramenta que a tabela não conhece.",
                "Pode ser MCP ou um nome inventado pelo modelo.",
                "Confirme se o servidor está declarado; se não, a chamada não deveria existir.",
                "O recibo não prova nada sobre o efeito.",
            ))
        if recibo.status not in STATUS_RECIBO:
            achados.append(finding(
                "should", "status-invalido", "Status desconhecido", recibo.status,
                "O recibo usa intent, ok, erro, interrompido ou recusado.",
                f"`{recibo.status}` não diz se a chamada terminou.",
                "Normalize o log antes de auditar.",
                "A conclusão fica ambígua.",
            ))

    interrompidos: list[Recibo] = []
    for chamada, lista in por_chamada.items():
        concluidas = [item for item in lista if item.status == "ok"]
        intents = [item for item in lista if item.status in {"intent", "interrompido"}]
        if intents and not concluidas:
            interrompidos.extend(intents)
            achados.append(finding(
                "must", "sem-resultado", "Chamada sem resultado", chamada,
                "O processo caiu ou parou durante a chamada.",
                "Ela pode ter sido aplicada e pode ainda estar rodando.",
                "Leia o estado atual antes de repetir; não presuma que não aconteceu.",
                "Você repete uma escrita que já valeu.",
            ))
        if len(concluidas) > 1:
            achados.append(finding(
                "must", "execucao-dupla", "A mesma chamada com dois resultados", chamada,
                "Uma chamada roda no máximo uma vez.",
                f"`{chamada}` aparece ok {len(concluidas)} vezes.",
                "Investigue: pode ser reenvio do log ou execução dupla real.",
                "O efeito foi aplicado mais de uma vez.",
            ))
    por_aprovacao: dict[str, set[str]] = {}
    for recibo in recibos:
        if recibo.aprovacao:
            por_aprovacao.setdefault(recibo.aprovacao, set()).add(recibo.chamada)
    for aprovacao, chamadas in por_aprovacao.items():
        if len(chamadas) > 1:
            achados.append(finding(
                "must", "aprovacao-repetida", "Aprovação usada em mais de uma chamada", aprovacao,
                "A decisão vale uma vez e é registrada uma vez.",
                f"`{aprovacao}` libera {len(chamadas)} chamadas distintas.",
                "Cada chamada `ask` precisa da sua própria decisão.",
                "A pessoa aprovou uma coisa e o agente fez outra.",
            ))
    for recibo in recibos:
        if recibo.status == "ok" and not recibo.resultado:
            achados.append(finding(
                "nice", "ok-sem-resultado", "Resultado vazio", recibo.chamada,
                "O recibo diz ok sem dizer o que voltou.",
                "Sem conteúdo não há como verificar o efeito.",
                "Guarde ao menos o identificador ou o trecho relevante.",
                "O log não serve de prova.",
            ))
        if recibo.status == "interrompido" and FERRAMENTAS.get(recibo.ferramenta, {}).get("efeito") in {"escrita", "execução", "futuro"}:
            interrompidos.append(recibo)
    retomadas = [recibo for recibo in recibos
                 if recibo.status == "ok"
                 and any(item.chamada == recibo.chamada for item in interrompidos)
                 and not recibo.verificado]
    if retomadas:
        achados.append(finding(
            "must", "retomada-sem-checagem", "Repetição sem conferir o estado",
            ", ".join(sorted({item.chamada for item in retomadas})),
            "Um recibo interrompido pode ter valido; repetir sem checar duplica.",
            "A nova chamada rodou sem `verificado=sim`.",
            "Leia o recurso (ou rode `list_dir`/`grep`) e só então repita.",
            "O efeito aparece duas vezes.",
        ))

    metrics = {
        "linhas": len(recibos),
        "chamadas": len(por_chamada),
        "interrompidas": len({item.chamada for item in interrompidos}),
        "duplicadas": sum(1 for lista in por_chamada.values()
                          if sum(1 for item in lista if item.status == "ok") > 1),
        "com_aprovacao": sum(1 for item in recibos if item.aprovacao),
        "erros": sum(1 for item in recibos if item.status in {"erro", "recusado"}),
    }
    perguntas = []
    if metrics["interrompidas"]:
        perguntas.append("Qual é o estado atual de cada chamada interrompida?")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Recibos", ""]
    for recibo in recibos:
        extra += [f"- `{recibo.chamada}` · {recibo.ferramenta or '—'} · **{recibo.status}**"
                  + (f" · aprovação `{recibo.aprovacao}`" if recibo.aprovacao else "")]
    if interrompidos:
        extra += ["", "## Podem ter sido aplicadas", ""]
        extra += [f"- `{item.chamada}` ({item.ferramenta or '—'}): confira antes de repetir." for item in interrompidos]
    rows = [{
        "ordem": item.ordem, "chamada": item.chamada, "ferramenta": item.ferramenta,
        "status": item.status, "aprovacao": item.aprovacao, "verificado": item.verificado,
    } for item in recibos]
    return {
        **common(
            analysis="estacao.recibos",
            mode=modo,
            title="Execução e recuperação",
            summary=[
                f"{len(recibos)} linhas, {len(por_chamada)} chamada(s), {metrics['interrompidas']} interrompida(s).",
                "Uma chamada roda no máximo uma vez; o resultado desconhecido é dito ao modelo.",
                "Recibo é despacho; prova é o estado observado depois.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_RECIBOS,
            extra_sections=extra,
        ),
        "recibos": rows,
        "interrompidas": sorted({item.chamada for item in interrompidos}),
        "executado": False,
    }


LIMITES_RECIBOS = [
    "A auditoria lê o log colado; ela não conhece o banco do agente nem o estado real do recurso.",
    "O formato aceito é `id=… tool=… status=… [approval=…] [result=…] [verificado=sim]`, com `|` ou espaço.",
    "`interrompido` é ambíguo por natureza: só uma leitura do recurso resolve.",
]


# -------------------------------------------------------------------- agenda

DIAS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")


def _campo_cron(campo: str, minimo: int, maximo: int) -> set[int]:
    valores: set[int] = set()
    for parte in campo.split(","):
        parte = parte.strip()
        passo = 1
        if "/" in parte:
            parte, _, passo_texto = parte.partition("/")
            passo = int(passo_texto)
            if passo < 1:
                raise EstacaoError("Passo de cron inválido.")
        if parte == "*":
            inicio, fim = minimo, maximo
        elif "-" in parte:
            a, _, b = parte.partition("-")
            inicio, fim = int(a), int(b)
        else:
            inicio = fim = int(parte)
        if inicio < minimo or fim > maximo or inicio > fim:
            raise EstacaoError(f"Valor de cron fora da faixa {minimo}..{maximo}: `{campo}`.")
        valores.update(range(inicio, fim + 1, passo))
    return valores


def _slots(expressao: str) -> set[tuple[int, int]]:
    campos = expressao.split()
    if len(campos) != 5:
        raise EstacaoError(f"Cron precisa de 5 campos: `{expressao}`.")
    minutos = _campo_cron(campos[0], 0, 59)
    horas = _campo_cron(campos[1], 0, 23)
    dias_mes = _campo_cron(campos[2], 1, 31)
    meses = _campo_cron(campos[3], 1, 12)
    semanas = _campo_cron(campos[4].replace("7", "0"), 0, 6)
    if dias_mes != set(range(1, 32)) or meses != set(range(1, 13)):
        raise EstacaoError("Só o campo de dia da semana é aceito sem data; dia do mês e mês ficam em `*`.")
    semana_map = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
    dias = {semana_map[item] for item in semanas}
    return {(dia, hora * 60 + minuto) for dia in dias for hora in horas for minuto in minutos}


def planejar_agenda(
    *,
    automacoes: str,
    orcamento_diario: int,
    presenca: str,
    modo: str,
) -> dict[str, Any]:
    linhas = _linhas(automacoes)
    if not linhas:
        raise EstacaoError("Liste ao menos uma automação: `nome | cron | minutos | presenca`.")
    if len(linhas) > 40:
        raise EstacaoError("Mais de 40 automações; divida a revisão.")
    orcamento_diario = max(1, min(int(orcamento_diario), 96))
    janela = _janela_presenca(presenca)
    achados: list[dict[str, Any]] = []
    planos: list[dict[str, Any]] = []
    nomes: set[str] = set()

    for linha in linhas:
        partes = [item.strip() for item in linha.split("|")]
        if len(partes) < 3:
            raise EstacaoError(f"Cada linha precisa de `nome | cron | minutos`: `{linha}`.")
        nome, expressao = partes[0], partes[1]
        if nome in nomes:
            achados.append(finding(
                "must", "nome-repetido", "Automação com nome repetido", nome,
                "O nome é a identidade na lista e no aviso.",
                "Duas tarefas com o mesmo nome não podem ser distinguidas.",
                "Renomeie uma delas.",
                "A remoção apaga a errada.",
            ))
        nomes.add(nome)
        try:
            duracao = max(1, int(partes[2]))
        except ValueError as erro:
            raise EstacaoError(f"Duração inválida em `{linha}`: use minutos inteiros.") from erro
        requer_presenca = len(partes) > 3 and _normal(partes[3]).startswith(("sim", "s", "true", "1"))
        try:
            slots = _slots(expressao)
        except ValueError as erro:
            achados.append(finding(
                "must", "cron-invalido", "Expressão de cron inválida", f"{nome}: {expressao}",
                "Cinco campos: minuto hora dia do mês mês dia da semana.",
                str(erro),
                "Use `*/15 * * * *` para cada 15 minutos ou `0 9 * * 1-5` para dias úteis às 9h.",
                "A automação nunca dispara ou dispara errado.",
            ))
            continue
        if len(slots) >= 7 * 1440:
            achados.append(finding(
                "must", "cron-tempestade", "Automação a cada minuto", nome,
                "Um slot por minuto mantém a máquina acordada o dia inteiro.",
                "Sessenta execuções por hora esgotam cota e orçamento.",
                "Espaçe para 15 minutos ou mais, ou use um gatilho por evento.",
                "A conta do modelo explode.",
            ))
        if duracao > 120:
            achados.append(finding(
                "should", "longa", "Automação longa", f"{nome}: {duracao} min",
                "A duração define a janela ocupada.",
                "Acima de duas horas, a máquina fica presa a uma tarefa.",
                "Divida em etapas ou reduza o escopo.",
                "Outra automação não cabe no dia.",
            ))
        if requer_presenca and janela is not None:
            fora = [slot for slot in slots if not _dentro(slot[1], janela)]
            if fora:
                achados.append(finding(
                    "should", "presenca-fora", "Automação com presença fora da janela", nome,
                    "O pedido diz que uma pessoa precisa estar por perto.",
                    f"{len(fora)} disparo(s) caem fora de {presenca}.",
                    "Mova o horário ou marque a automação como sem presença.",
                    "O agente para esperando alguém que não está.",
                ))
        planos.append({
            "nome": nome, "cron": expressao, "duracao": duracao,
            "presenca": requer_presenca, "slots": slots,
        })

    # sobreposição e orçamento de acordadas por dia
    por_dia: dict[int, list[tuple[int, int, str]]] = {dia: [] for dia in range(7)}
    for plano in planos:
        for dia, inicio in plano["slots"]:
            por_dia[dia].append((inicio, inicio + plano["duracao"], plano["nome"]))
    conflitos: list[dict[str, Any]] = []
    for dia, intervalos in por_dia.items():
        intervalos.sort()
        for indice in range(len(intervalos)):
            inicio, fim, nome = intervalos[indice]
            for outro in intervalos[indice + 1:]:
                if outro[0] >= fim:
                    break
                if outro[0] < fim:
                    conflitos.append({"dia": DIAS[dia], "minuto": inicio,
                                      "a": nome, "b": outro[2]})
    if conflitos:
        achados.append(finding(
            "must", "sobreposicao", "Automações sobrepostas",
            f"{len(conflitos)} choque(s)",
            "Uma máquina executa uma tarefa por vez.",
            "A segunda automação espera ou falha, e o horário dela deixa de valer.",
            "Espaçe os horários ou una as duas tarefas.",
            "O resultado de uma das duas não sai no horário.",
        ))
    for dia, intervalos in por_dia.items():
        if not intervalos:
            continue
        ocupado = sum(fim - inicio for inicio, fim, _ in intervalos)
        acordadas = len({(inicio // 60) for inicio, _, _ in intervalos})
        if acordadas > orcamento_diario:
            achados.append(finding(
                "should", "acorda-demais", "Acordadas acima do orçamento", f"{DIAS[dia]}: {acordadas}",
                "Cada automação liga a máquina e gasta um turno.",
                f"O orçamento declarado é {orcamento_diario} por dia.",
                "Junte tarefas no mesmo horário ou reduza a frequência.",
                "O custo diário passa do previsto.",
            ))
            break
        if ocupado > 12 * 60:
            achados.append(finding(
                "nice", "dia-cheio", "Dia quase todo ocupado", f"{DIAS[dia]}: {ocupado // 60}h",
                "Automação longa em série ocupa a máquina.",
                "Sobra pouca janela para mensagem ou tarefa sob demanda.",
                "Reserve ao menos algumas horas livres.",
                "Seu pedido espera a fila.",
            ))
            break

    metrics = {
        "automacoes": len(planos),
        "disparos_semana": sum(len(item["slots"]) for item in planos),
        "conflitos": len(conflitos),
        "com_presenca": sum(1 for item in planos if item["presenca"]),
        "orcamento": orcamento_diario,
    }
    perguntas = []
    if conflitos:
        perguntas.append("Qual das duas automações cede o horário?")
    if metrics["disparos_semana"] > 100:
        perguntas.append("Todos esses disparos são necessários, ou algum pode ser por evento?")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Agenda", ""]
    for plano in planos:
        extra += [f"- **{plano['nome']}** · `{plano['cron']}` · {plano['duracao']} min"
                  + (" · presença" if plano["presenca"] else "")
                  + f" · {len(plano['slots'])} disparo(s)/semana"]
    if conflitos:
        extra += ["", "## Choques", ""]
        extra += [f"- {item['dia']} às {item['minuto'] // 60:02d}:{item['minuto'] % 60:02d}: "
                  f"`{item['a']}` × `{item['b']}`" for item in conflitos[:20]]
    extra += ["", "## Atraso e queda", "",
              "- Automação perdida enquanto a máquina dormia roda no próximo acordar, uma vez.",
              "- Uma automação que falha três vezes seguidas para e avisa.",
              "- Mudar a agenda é `automations`, que pede aprovação por padrão.",
              ""]
    rows = [{
        "nome": plano["nome"], "cron": plano["cron"], "duracao": plano["duracao"],
        "presenca": plano["presenca"], "disparos": len(plano["slots"]),
    } for plano in planos]
    return {
        **common(
            analysis="estacao.agenda",
            mode=modo,
            title="Agenda de automações",
            summary=[
                f"{len(planos)} automação(ões), {metrics['disparos_semana']} disparo(s) por semana.",
                f"{len(conflitos)} choque(s) de horário; orçamento de {orcamento_diario} acordada(s) por dia.",
                "Agenda é código: quem pode mudá-la é a permissão `automations`.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_AGENDA,
            extra_sections=extra,
        ),
        "agenda": rows,
        "conflitos": conflitos[:20],
        "executado": False,
    }


def proxima_execucao(expressao: str, depois: datetime) -> datetime:
    """Primeiro instante >= `depois + 1 min` que casa com o cron (semana genérica)."""
    if depois.tzinfo is None:
        depois = depois.replace(tzinfo=timezone.utc)
    slots = _slots(expressao)
    por_dia: dict[int, set[int]] = {}
    for dia, minuto in slots:
        por_dia.setdefault(dia, set()).add(minuto)
    if not por_dia:
        raise EstacaoError("O cron não produz nenhum disparo.")
    inicio = (depois + timedelta(minutes=1)).replace(second=0, microsecond=0)
    for passo in range(0, 400):
        base = inicio + timedelta(days=passo)
        minutos = por_dia.get(base.weekday())
        if not minutos:
            continue
        for minuto in sorted(minutos):
            hora, resto = divmod(minuto, 60)
            alvo = base.replace(hour=hora, minute=resto)
            if alvo >= inicio:
                return alvo
    raise EstacaoError("Não foi possível achar o próximo disparo em 400 dias.")


def _janela_presenca(texto: str) -> tuple[int, int] | None:
    achado = re.search(r"(\d{1,2})h?\s*(?:-|a|às|as)\s*(\d{1,2})h?", texto.strip().lower())
    if not achado:
        return None
    inicio, fim = int(achado.group(1)), int(achado.group(2))
    if inicio > fim:
        return None
    return inicio * 60, fim * 60


def _dentro(minuto: int, janela: tuple[int, int]) -> bool:
    return janela[0] <= minuto < janela[1]


LIMITES_AGENDA = [
    "A agenda é calculada numa semana genérica (seg a dom), sem fuso nem horário de verão.",
    "Só o campo de dia da semana aceita restrição; dia do mês e mês precisam ser `*`.",
    "A duração é declarada por você; a auditoria não mede a execução real.",
    "Nada é agendado: o plano é texto para revisar antes de gravar.",
]


# ------------------------------------------------------------------- limites

PADROES_EFEITO: list[tuple[str, str]] = [
    (r"\b(apagar|excluir|deletar|remover|sobrescrever|formatar)\b", "exclusao"),
    (r"\b(pagar|pagamento|comprar|cobranca|pix|cartao|assinatura|contratar)\b", "pagamento"),
    (r"\b(enviar|mandar|publicar|postar|responder|compartilhar|convidar)\b", "envio"),
    (r"\b(instalar|desinstalar|atualizar)\b", "instalacao"),
    (r"\b(permissao|permissões|allow|deny|conceder|revogar)\b", "permissao"),
    (r"\b(conta|senha|credencial|token|login|cadastro|login)\b", "conta"),
]

REGRAS_EFEITO: dict[str, dict[str, str]] = {
    "pagamento": {"nivel": "irreversivel", "porque": "O dinheiro sai e a confirmação costuma não ter desfazer."},
    "exclusao": {"nivel": "irreversivel", "porque": "Apagar não tem desfazer; o conteúdo não volta sozinho."},
    "envio": {"nivel": "confirmar", "porque": "Uma vez enviado, o destinatário já recebeu."},
    "instalacao": {"nivel": "confirmar", "porque": "Instalar muda o que existe na máquina."},
    "permissao": {"nivel": "confirmar", "porque": "Mudar permissão altera quem pode o quê."},
    "conta": {"nivel": "confirmar", "porque": "Conta e credencial falam em nome de alguém."},
}

ALLOW_LIMITE = re.compile(r"\b(ler|abrir|navegar|consultar|listar|baixar|conferir|buscar|pesquisar|ver|medir|contar)\b")


def checar_limites(*, acoes: str, modo: str) -> dict[str, Any]:
    """Classifica cada ação pelo efeito declarado, sem julgar o tema."""
    linhas = _linhas(acoes)
    if not linhas:
        raise EstacaoError("Liste ao menos uma ação pretendida, uma por linha.")
    if len(linhas) > 80:
        raise EstacaoError("Mais de 80 ações; divida a revisão.")
    achados: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for linha in linhas:
        normal = _normal(linha)
        nivel = "liberado"
        regra = ""
        motivo = "Leitura: não muda o estado fora do agente."
        for padrao, grupo in PADROES_EFEITO:
            if re.search(padrao, normal):
                nivel = REGRAS_EFEITO[grupo]["nivel"]
                regra = grupo
                motivo = REGRAS_EFEITO[grupo]["porque"]
                break
        if nivel == "liberado" and not ALLOW_LIMITE.search(normal):
            nivel, regra = "confirmar", "indefinido"
            motivo = "Não há verbo de leitura; o efeito não está declarado."
        rows.append({"acao": linha, "nivel": nivel, "regra": regra, "motivo": motivo})
        if nivel == "irreversivel":
            achados.append(finding(
                "must", "irreversivel", "Efeito sem desfazer", linha, motivo,
                "Não existe reversão automática para esta ação.",
                "Confirme o alvo e o conteúdo antes; prefira um ensaio quando houver.",
                "O resultado não volta atrás.",
            ))
        elif nivel == "confirmar" and modo != "lite":
            achados.append(finding(
                "should", "confirmar", "Efeito externo declarado", linha, motivo,
                "A ação alcança algo fora do agente.",
                "Mostre o alvo e o conteúdo a quem vai autorizar.",
                "A ação acontece em nome de alguém sem revisão.",
            ))

    metrics = {
        "acoes": len(rows),
        "irreversiveis": sum(1 for item in rows if item["nivel"] == "irreversivel"),
        "confirmar": sum(1 for item in rows if item["nivel"] == "confirmar"),
        "liberadas": sum(1 for item in rows if item["nivel"] == "liberado"),
    }
    perguntas = ["Quem confirma cada efeito externo e como vê o alvo antes?"]
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Veredito por ação", ""]
    for item in rows:
        extra += [f"- **{item['nivel']}** · {item['acao']}", f"   - Motivo: {item['motivo']}", ""]
    extra += ["## Como ler", "",
              "A classificação é por **efeito declarado**, não por tema: leitura é liberada, efeito externo pede confirmação e o que não tem desfazer é marcado como irreversível.",
              "Nada aqui aplica uma política que você não escreveu: o nível é informativo, e a decisão de executar fica com a permissão da ferramenta.",
              ""]
    return {
        **common(
            analysis="estacao.limites",
            mode=modo,
            title="Limites e consentimento",
            summary=[
                f"{metrics['acoes']} ações: {metrics['liberadas']} liberada(s), "
                f"{metrics['confirmar']} para confirmar, {metrics['irreversiveis']} irreversível(is).",
                "A classificação é por efeito, não por assunto.",
                "A política que decide a execução é a sua, na matriz de permissões.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_LIMITES,
            extra_sections=extra,
        ),
        "acoes": rows,
        "executado": False,
    }


LIMITES_LIMITES = [
    "A classificação é lexical e conservadora: o que não é leitura vira confirmação.",
    "Ela lê palavras, não intenção; um texto ambíguo pode cair no lado mais restritivo.",
    "Regras de empresa, termos do site e legislação local continuam valendo por cima disto.",
    "O nível é informativo: quem decide executar é o gate de permissões do executor.",
]


# -------------------------------------------------------------------- memória

SEGREDOS = re.compile(
    r"(sk-[A-Za-z0-9]{10,}|api[_-]?key\s*[:=]|token\s*[:=]\s*\S{8,}|senha\s*[:=]|password\s*[:=]"
    r"|BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{10,})",
    re.I,
)
DATA = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b|\b(\d{2})/(\d{2})/(20\d{2})\b")


def auditar_memoria(*, notas: str, skills: str, modo: str) -> dict[str, Any]:
    notas = notas.strip()
    if len(notas) < 10:
        raise EstacaoError("Cole as notas do agente (MEMORY.md ou equivalente).")
    if len(notas) > 40_000:
        raise EstacaoError("Notas acima de 40 000 caracteres; recorte.")
    achados: list[dict[str, Any]] = []
    if len(notas) > 25_000:
        achados.append(finding(
            "should", "memoria-longa", "Notas acima do teto do prompt", f"{len(notas)} caracteres",
            "O MEMORY.md entra em todo prompt até 25 000 caracteres.",
            "Acima disso o fim é cortado e o agente não vê.",
            "Mova o excedente para notas temáticas.",
            "O que você escreveu no fim nunca é lido.",
        ))
    for achado in SEGREDOS.finditer(notas):
        trecho = achado.group(0)[:24]
        achados.append(finding(
            "must", "segredo", "Segredo aparente nas notas", trecho,
            "Notas são lidas pelo modelo e podem sair no relatório.",
            "Credencial em texto claro vaza por qualquer cópia.",
            "Guarde o segredo no cofre do host e cite só o nome da variável.",
            "A chave aparece em prompt, log e backup.",
        ))
    fatos = [linha for linha in _linhas(notas) if not linha.startswith("#")]
    sem_data = 0
    for linha in fatos:
        if len(linha) < 12 or linha.startswith("- **"):
            continue
        if not DATA.search(linha):
            sem_data += 1
    if sem_data:
        achados.append(finding(
            "should", "fato-sem-data", "Fato sem dia", f"{sem_data} linha(s)",
            "O upstream guarda cada fato com o dia em que foi aprendido.",
            "Sem data não há como saber se o fato envelheceu.",
            "Acrescente `(2026-10-23)` ao lado do fato.",
            "O agente repete informação vencida.",
        ))
    absolutos = [linha for linha in fatos if re.search(r"\b(sempre|nunca|jamais|todos os dias)\b", _normal(linha))]
    if absolutos:
        achados.append(finding(
            "nice", "absoluto", "Regra absoluta", absolutos[0][:60],
            "Generalização sem exceção envelhece mal.",
            f"{len(absolutos)} linha(s) usam sempre/nunca.",
            "Prefira “em geral” e diga a exceção conhecida.",
            "O agente aplica uma regra que deixou de valer.",
        ))

    blocos = [bloco.strip() for bloco in re.split(r"\n\s*---+\s*\n", skills.strip()) if bloco.strip()]
    cartoes: list[dict[str, Any]] = []
    gatilhos: dict[str, str] = {}
    if skills.strip() and not blocos:
        raise EstacaoError("A seção de skills precisa de blocos separados por `---`.")
    for bloco in blocos:
        campos: dict[str, str] = {}
        for linha in bloco.splitlines():
            chave, separador, valor = linha.partition(":")
            if separador and not linha.startswith(" "):
                campos[chave.strip().lower()] = valor.strip()
        nome = campos.get("nome", "") or "sem-nome"
        gatilho = campos.get("gatilho", "")
        passos_texto = campos.get("passos", "")
        verificacao = campos.get("verificacao", "") or campos.get("verificação", "")
        if not gatilho:
            achados.append(finding(
                "must", "skill-sem-gatilho", "Skill sem gatilho", nome,
                "O agente precisa saber quando aplicar a skill.",
                "Sem gatilho ela nunca é lembrada ou é aplicada sempre.",
                "Escreva o gatilho em uma frase, com o sintoma que a dispara.",
                "A skill vira texto morto.",
            ))
        if not verificacao:
            achados.append(finding(
                "must", "skill-sem-prova", "Skill sem verificação", nome,
                "Toda skill precisa dizer como saber que funcionou.",
                "Sem prova, o resultado é fé.",
                "Acrescente `verificacao:` com um estado observável.",
                "O erro se repete na próxima execução.",
            ))
        if SEGREDOS.search(bloco):
            achados.append(finding(
                "must", "skill-segredo", "Segredo dentro da skill", nome,
                "Skills são lidas, copiadas e versionadas.",
                "Credencial embutida vaza junto com a skill.",
                "Referencie o nome da variável ou do cofre.",
                "A chave vai para o repositório.",
            ))
        gatilho_normal = _normal(gatilho)
        if gatilho_normal:
            if gatilho_normal in gatilhos:
                achados.append(finding(
                    "should", "gatilho-duplicado", "Dois gatilhos iguais",
                    f"{gatilhos[gatilho_normal]} × {nome}",
                    "Dois caminhos para o mesmo pedido confundem a escolha.",
                    "O agente escolhe a primeira ou nenhuma.",
                    "Una as skills ou diferencie o gatilho.",
                    "A skill certa nunca é escolhida.",
                ))
            gatilhos[gatilho_normal] = nome
        passos = [item.strip() for item in re.split(r"[;\n]", passos_texto) if item.strip()]
        cartoes.append({
            "nome": nome, "gatilho": gatilho or "—", "passos": len(passos),
            "verificacao": verificacao or "—", "permissoes": campos.get("permissoes", "—"),
        })
    if len(cartoes) == 0:
        achados.append(finding(
            "nice", "sem-skills", "Nenhuma skill declarada", "skills",
            "O agente escreve as próprias skills para não repetir raciocínio.",
            "Sem skill, cada tarefa recomeça do zero.",
            "Registre ao menos o caminho que funcionou, com gatilho e verificação.",
            "O trabalho não acumula experiência.",
        ))

    metrics = {
        "notas": len(notas),
        "linhas": len(fatos),
        "skills": len(cartoes),
        "segredos": sum(1 for item in achados if item["kind"] in {"segredo", "skill-segredo"}),
        "sem_data": sem_data,
    }
    perguntas = ["Quem revisa as notas e as skills antes de elas entrarem em uso?"]
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Skills", ""]
    for cartao in cartoes:
        extra += [f"- **{cartao['nome']}** · gatilho: {cartao['gatilho']} · {cartao['passos']} passo(s)"
                  f" · prova: {cartao['verificacao']}"]
    extra += ["", "## Higiene", "",
              "- Fato com dia; nota sem data envelhece sem aviso.",
              "- Segredo só no cofre, nunca na nota.",
              "- Skill com gatilho, passos e verificação.",
              "- Nota que deixou de valer é corrigida ou apagada, não empilhada.",
              ""]
    rows = [{
        "nome": cartao["nome"], "gatilho": cartao["gatilho"], "passos": cartao["passos"],
        "verificacao": cartao["verificacao"],
    } for cartao in cartoes]
    return {
        **common(
            analysis="estacao.memoria",
            mode=modo,
            title="Notas e skills do agente",
            summary=[
                f"{len(fatos)} linha(s) de nota, {len(cartoes)} skill(s), {metrics['segredos']} segredo(s) aparente(s).",
                "A memória é do agente, mas a revisão é da pessoa.",
                "Fato sem dia e skill sem prova não sustentam decisão.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_MEMORIA,
            extra_sections=extra,
        ),
        "skills": cartoes,
        "executado": False,
    }


LIMITES_MEMORIA = [
    "A auditoria é lexical: não julga se o fato é verdadeiro, só se está datado, seguro e verificável.",
    "O formato de skill aceito é `nome:`, `gatilho:`, `passos:`, `verificacao:`, separados por `---`.",
    "A nota é lida como texto; nenhum arquivo do agente é aberto por esta skill.",
]


# ------------------------------------------------------------------ catálogo

def estacao_catalog() -> dict[str, Any]:
    return {
        "fonte": "feder-cr/invisible_dots (MIT)",
        "versao": VERSAO,
        "principio": "Permissão declarada, aprovação registrada, chamada que roda no máximo uma vez.",
        "ferramentas": [
            {"id": chave, "permissao": valor["permissao"], "risco": valor["risco"],
             "efeito": valor["efeito"], "nota": valor["nota"]}
            for chave, valor in sorted(FERRAMENTAS.items())
        ],
        "permissoes": [
            {"nome": chave, "risco": valor["risco"], "padrao": valor["padrao"],
             "rotulo": valor["rotulo"]}
            for chave, valor in sorted(PERMISSOES.items())
        ],
        "decisoes": list(DECISOES),
        "estados": [{"estado": chave, "nota": valor} for chave, valor in ESTADOS.items()],
        "limites": [
            {"regra": chave, "nivel": valor["nivel"], "porque": valor["porque"]}
            for chave, valor in REGRAS_EFEITO.items()
        ],
        "orcamento": [
            {"regra": "Passos por tarefa", "valor": f"padrão {PASSOS_MAX}, teto {PASSOS_TETO}"},
            {"regra": "Custo por tarefa", "valor": f"padrão {_moeda(CUSTO_MAX)}"},
            {"regra": "Timeout de exec", "valor": "60 s por padrão, 600 s no máximo"},
            {"regra": "Ócio até dormir", "valor": "15 min por padrão"},
            {"regra": "Notas no prompt", "valor": "25 000 caracteres"},
        ],
        "executado": False,
    }
