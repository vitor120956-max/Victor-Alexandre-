"""Agir por `ref` — a etapa 2 (0.86.0).

A etapa 1 leu a janela sem tocar em nada. Esta é a parte que age, e ela tem
uma regra que vale mais do que qualquer funcionalidade: **um `ref` só vale
para a leitura que o criou**. `ref` não é um nome estável do elemento, é o
número dele naquela leitura — e a tela muda.

Por isso o fluxo é sempre este:

1. **ler de novo** (a leitura de agora é a única que vale);
2. **procurar o ref** nela. Não achou? Recusa e lista o que existe agora;
3. **mostrar o plano** — o que é, onde está, o que será feito;
4. só com `executar=True` **agir**.

Sem `executar`, nada acontece. É o mesmo desenho do `dry_run` das skills: o
passo perigoso é sempre o último, e é sempre explícito.

O que este módulo **não** faz: mover o ponteiro do mouse. A ação vem do próprio
elemento (ação padrão da MSAA / padrão de invocação da UIA). Você disse que a
tela não responde a toque e que não tem mouse USB — clicar por coordenada
seria justamente o que não funciona aí. Quando o elemento só aceita clique
físico, isso é dito, e não fingido.
"""
from __future__ import annotations

from typing import Any, Protocol

from server import arvore


class AgirError(ValueError):
    """Não deu para agir: ref inválido, elemento sem ação, leitura falhou."""


ACOES = {"clicar", "digitar", "escrever"}


class Executor(Protocol):
    """Quem executa de verdade. No Windows é `arvore_windows`; nos testes, um dublê."""

    def executar_ref(
        self,
        handle: int,
        caminho: list[int],
        acao: str,
        texto: str = "",
        caixa: list[int] | None = None,
    ) -> dict[str, Any]: ...


def _arq_escolher(alvo: str, leitor: Any) -> dict[str, Any]:
    """Escolhe a janela do mesmo jeito que a leitura escolhe.

    `leitor.escolher_janela` existe no Windows e nos dublês; se não existir,
    monta-se aqui com a função de `arvore` — uma regra só, dois caminhos.
    """
    proprio = getattr(leitor, "escolher_janela", None)
    if callable(proprio):
        return proprio(alvo, janelas=leitor.janelas(), foco=leitor.janela_em_foco())
    return arvore.escolher_janela(alvo, janelas=leitor.janelas(), foco=leitor.janela_em_foco())


def _achar(resultado: dict[str, Any], ref: str) -> dict[str, Any]:
    pedido = (ref or "").strip()
    if not pedido:
        raise AgirError("informe o `ref` do elemento (ex.: @4ab283d9:e11).")
    for no in arvore.achatar(resultado.get("arvore")):
        if no.get("ref") == pedido:
            return no
    # Mensagem útil: o que existe agora, em vez de só "não achei".
    disponiveis = [no["ref"] for no in arvore.acionaveis(resultado, 8)]
    agora = ", ".join(disponiveis) if disponiveis else "nenhum"
    raise AgirError(
        f"o ref {pedido} não existe nesta leitura — ele deve ser de uma leitura anterior, "
        f"e a tela já mudou. Refs válidos agora: {agora}. "
        "Rode a leitura de novo e use um dos que aparecerem."
    )


def planejar(
    resultado: dict[str, Any],
    ref: str,
    acao: str = "clicar",
    texto: str = "",
) -> dict[str, Any]:
    """Confere o ref na leitura de agora e descreve o que seria feito.

    Nada é executado aqui. Serve para o usuário ver o plano antes de autorizar.
    """
    pedido = (acao or "clicar").strip().lower()
    if pedido == "escrever":
        pedido = "digitar"
    if pedido not in ACOES:
        raise AgirError(f"ação desconhecida: {acao}. Use clicar ou digitar.")

    no = _achar(resultado, ref)
    if arvore.e_moldura(no):
        raise AgirError(
            f"{ref} é moldura de janela (“{no.get('nome') or no.get('papel')}”). "
            "Fechar/minimizar/rolar não é trabalhar no programa — recuso."
        )

    caminho = no.get("caminho")
    if not isinstance(caminho, list):
        raise AgirError(
            "a leitura veio sem caminho até o elemento; leia de novo com `com_caminho`."
        )

    caixa = no.get("caixa") if isinstance(no.get("caixa"), list) else None
    escrito = " ".join((texto or "").split())
    if pedido == "digitar":
        if not escrito:
            raise AgirError("para digitar, informe o texto.")
        if len(escrito) > 500:
            raise AgirError("texto grande demais para uma vez (limite de 500 caracteres).")
        pode = str(no.get("acao") or "").strip().lower() in arvore.ACAO_DE_TEXTO
        if not pode:
            raise AgirError(
                f"{ref} é “{no.get('nome') or no.get('papel')}” e não aceita escrita "
                f"(ação do elemento: {no.get('acao') or 'nenhuma'})."
            )

    janela = resultado.get("janela") or {}
    plano = {
        "ref": ref,
        "acao": pedido,
        "texto": escrito if pedido == "digitar" else "",
        "papel": no.get("papel") or "",
        "nome": no.get("nome") or "",
        "caixa": caixa,
        "caminho": [int(item) for item in caminho],
        "janela": str(janela.get("titulo") or ""),
        "processo": str(janela.get("processo") or ""),
        "fonte": str(resultado.get("fonte") or ""),
        "leitura": str(resultado.get("id") or ""),
    }
    if caixa:
        plano["centro"] = [caixa[0] + caixa[2] // 2, caixa[1] + caixa[3] // 2]
    plano["o_que_vai_fazer"] = _frase(plano)
    return plano


def _frase(plano: dict[str, Any]) -> str:
    alvo = plano.get("nome") or plano.get("papel") or "elemento"
    onde = ""
    if plano.get("caixa"):
        caixa = plano["caixa"]
        onde = f" em {caixa[0]},{caixa[1]} ({caixa[2]}x{caixa[3]})"
    if plano["acao"] == "digitar":
        return f'digitar {plano["texto"]!r} em {alvo}{onde}'
    return f"clicar em {alvo}{onde}"


def agir(
    *,
    ref: str,
    acao: str = "clicar",
    texto: str = "",
    executar: bool = False,
    leitor: Any = None,
    alvo: str = "foco",
    profundidade: int = arvore.PROFUNDIDADE_PADRAO,
    limite: int = arvore.LIMITE_PADRAO,
    fonte: str = "auto",
) -> dict[str, Any]:
    """Lê de novo, confere o ref e — só com `executar` — age.

    `leitor` é o módulo do Windows (tem `ler_janela`, `escolher_janela`,
    `executar_ref`). Nos testes é um dublê.
    """
    if leitor is None:
        raise AgirError("agir por ref só existe no Windows hoje — aqui a leitura é só leitura.")

    bruto, janela = _ler_agora(leitor, alvo, profundidade, limite, fonte)
    montada = arvore.montar(bruto, profundidade, limite, com_caminho=True)

    plano = planejar(montada, ref, acao, texto)
    resposta: dict[str, Any] = {
        "ok": True,
        "executou": False,
        "plano": plano,
        "resumo": ("Ação pronta (nada foi feito): " if not executar else "Executando: ")
        + plano["o_que_vai_fazer"],
    }
    if not executar:
        resposta["como_autorizar"] = "repita o comando com --executar para fazer de verdade."
        return resposta

    try:
        feito = leitor.executar_ref(
            int(janela["handle"]),
            plano["caminho"],
            plano["acao"],
            plano["texto"],
            plano.get("caixa"),
        )
    except Exception as exc:  # noqa: BLE001 - COM de terceiros
        raise AgirError(f"a ação falhou: {type(exc).__name__}: {exc}") from exc

    resposta["executou"] = bool(feito.get("executou", True))
    resposta["resultado"] = feito
    resposta["resumo"] = ("Feito: " if resposta["executou"] else "Não foi feito: ") + plano["o_que_vai_fazer"]
    if feito.get("motivo"):
        resposta["resumo"] += f" — {feito['motivo']}"
    return resposta


def escrever_na_janela(
    *,
    texto: str,
    executar: bool = False,
    leitor: Any = None,
    alvo: str = "foco",
    profundidade: int = arvore.PROFUNDIDADE_PADRAO,
    limite: int = arvore.LIMITE_PADRAO,
    fonte: str = "auto",
) -> dict[str, Any]:
    """Acha o lugar de escrever **sozinho** e digita. Sem ref, sem cópia.

    Por que existe: o comando com `--ref` obrigava a pessoa a copiar um código
    da saída anterior. O usuário colou o marcador `@SEU_REF_AQUI` — e a recusa
    estava certa, mas o trabalho de copiar não devia existir. O JARVIS já sabe
    apontar onde se escreve (`prontidao().onde_escrever`); agora ele usa isso.

    Continua igual em tudo o mais: relê a janela, mostra o plano, e só age com
    `executar=True`.
    """
    if leitor is None:
        raise AgirError("escrever na janela só existe no Windows hoje.")

    bruto, janela = _ler_agora(leitor, alvo, profundidade, limite, fonte)
    montada = arvore.montar(bruto, profundidade, limite, com_caminho=True)
    lido = montada.get("pronto") or arvore.prontidao(montada)
    campo = lido.get("onde_escrever")
    if not campo or not campo.get("ref"):
        raise AgirError(
            "não achei lugar para escrever nesta janela. "
            + str(lido.get("motivo") or "")
            + " Rode `--provados` para ver quais janelas aceitam escrita."
        )
    return agir(
        ref=campo["ref"],
        acao="digitar",
        texto=texto,
        executar=executar,
        leitor=leitor,
        alvo=alvo,
        profundidade=profundidade,
        limite=limite,
        fonte=fonte,
    )


def _ler_agora(
    leitor: Any,
    alvo: str,
    profundidade: int,
    limite: int,
    fonte: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Escolhe a janela e lê. Uma regra de escolha, a mesma do resto."""
    try:
        janela = _arq_escolher(alvo, leitor)
    except Exception as exc:  # noqa: BLE001
        raise AgirError(f"não achei a janela: {exc}") from exc
    try:
        bruto = leitor.ler_janela(int(janela["handle"]), profundidade, limite, fonte=fonte)
    except TypeError:
        bruto = leitor.ler_janela(int(janela["handle"]), profundidade, limite)
    bruto.setdefault("janela", janela)
    return bruto, janela
