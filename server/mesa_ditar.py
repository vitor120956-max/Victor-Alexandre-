"""Ditar num programa: abrir se preciso, escrever e conferir (0.89.0).

A 0.88.0 provou que o JARVIS consegue escrever numa janela que já está aberta.
O que faltava para ele ter mãos de verdade era o começo: **a janela pode não
estar aberta**. Mandar a pessoa abrir o Bloco de Notas antes é, de novo, pedir
trabalho a quem pediu que o JARVIS fizesse.

Esta camada junta as duas peças que já existiam:

1. `pc.abrir_programa` — lista fechada de programas, sem caminho livre;
2. `mesa_agir.escrever_na_janela` — acha o campo, escreve, confere.

E acrescenta o que nenhuma das duas fazia: **esperar a janela aparecer**. Abrir
um programa e ler a tela no mesmo instante é ler o vazio; o Windows leva de
algumas centenas de milissegundos a alguns segundos para desenhar a janela.

O que continua igual, e por decisão:

- **sem `executar`, nada é aberto e nada é escrito** — o plano diz o que faria;
- abrir programa continua passando pela lista fechada (nada de caminho livre);
- a skill pela API continua exigindo `JARVIS_HOST_PC=1`, porque quem chama é o
  modelo, não a pessoa. Na sonda, quem autoriza é a linha que a pessoa digitou.
"""
from __future__ import annotations

import subprocess
import time
from typing import Any, Callable

from server import arvore, mesa_agir, pc


class DitarError(ValueError):
    """Não deu para ditar: programa fora da lista, janela não apareceu, etc."""


DORMIR = time.sleep
ESPERA_PADRAO = 12.0
# Depois de a janela existir, o campo leva mais um pouco: o processo aparece
# antes do controle. 15s é folga suficiente para não fazer a pessoa esperar
# diante de uma tela parada se algo deu errado de verdade.
ESPERA_CAMPO = 15.0
INTERVALO = 0.4
INTERVALO_CAMPO = 0.5


def _norm(texto: str) -> str:
    return " ".join(str(texto or "").lower().split())


def janela_do_programa(janelas: list[dict[str, Any]], executavel: str, rotulo: str) -> dict[str, Any] | None:
    """A janela daquele programa, se estiver aberta.

    Casa pelo **processo** (`notepad.exe`) e, quando o processo não vem, pelo
    título com o rótulo em português (“Bloco de notas”). Nada de casar por
    pedaço solto: “calc” está dentro de “calculadora”, mas também de
    “calculator-service” de outro programa.
    """
    # Janela sem título é janela que ainda está nascendo: o processo já existe,
    # mas o Windows ainda não desenhou nada. Casar com ela é casar com o vazio.
    achadas = janelas_do_programa(janelas, executavel, rotulo)
    return achadas[0] if achadas else None


def janelas_do_programa(
    janelas: list[dict[str, Any]], executavel: str, rotulo: str
) -> list[dict[str, Any]]:
    """Todas as janelas daquele programa, na ordem em que apareceram.

    Existe porque um programa pode ter **mais de uma** janela viva — e só uma
    delas publica o campo. Na medição da 0.89.0 havia duas `notepad.exe` e a
    escolhida era a que só publicava moldura; o JARVIS então dizia “não achei
    lugar para escrever” olhando para a janela errada.
    """
    exe = _norm(executavel)
    nome = _norm(rotulo)
    vivas = [janela for janela in (janelas or []) if _norm(janela.get("titulo"))]
    por_processo = [janela for janela in vivas if _norm(janela.get("processo")) == exe]
    if por_processo:
        return por_processo
    return [
        janela
        for janela in vivas
        if nome and (nome == _norm(janela.get("titulo")) or nome in _norm(janela.get("titulo")))
    ]


def esperar_janela(
    leitor: Any,
    executavel: str,
    rotulo: str,
    *,
    segundos: float = ESPERA_PADRAO,
    dormir: Callable[[float], Any] = DORMIR,
    intervalo: float = INTERVALO,
) -> dict[str, Any] | None:
    """Espera a janela do programa aparecer — sem laço infinito.

    Devolve a janela ou `None` quando o tempo acaba. O tempo é curto de
    propósito: se em 12 segundos o programa não abriu a janela, algo está
    errado, e fingir que espera mais só faz a pessoa olhar uma tela parada.
    """
    limite = time.monotonic() + max(0.0, float(segundos))
    while True:
        janela = janela_do_programa(leitor.janelas(), executavel, rotulo)
        if janela:
            return janela
        if time.monotonic() >= limite:
            return None
        dormir(intervalo)


def abrir_direto(executavel: str) -> Any:
    """Abre sem a trava da API — só para a sonda, onde a linha é a autorização.

    Continua valendo a lista fechada: o executável vem de `pc.PROGRAMAS`, nunca
    de um caminho digitado.
    """
    return subprocess.Popen([executavel], shell=False, close_fds=True)


def _esperar_campo(
    *,
    texto: str,
    leitor: Any,
    alvo: str,
    handle: int | None = None,
    profundidade: int,
    limite: int,
    fonte: str,
    acrescentar: bool,
    segundos: float,
    dormir: Callable[[float], Any],
) -> tuple[dict[str, Any] | None, str]:
    """Relê até o campo de escrita existir. `(None, último motivo)` = acabou.

    Devolve também o último motivo para o erro final poder repetir o que a
    janela respondeu — "esperei e nada" sem dizer o que a janela mostrou é
    diagnóstico pela metade.
    

    Planejar (`executar=False`) é o teste certo aqui: ele faz todo o caminho —
    escolhe a janela, lê, acha o campo, valida o texto — **sem tocar em nada**.
    Se o campo ainda não nasceu, a tentativa falha sem consequência.
    """
    limite_de_tempo = time.monotonic() + max(0.0, float(segundos))
    motivo = ""
    while True:
        try:
            return mesa_agir.escrever_na_janela(
                texto=texto,
                executar=False,
                leitor=leitor,
                alvo=alvo,
                profundidade=profundidade,
                limite=limite,
                fonte=fonte,
                acrescentar=acrescentar,
                handle=handle,
            ), ""
        except mesa_agir.AgirError as exc:
            # Só "ainda não há campo" justifica esperar. Janela que sumiu,
            # texto vazio ou ref inválido são erros de outra natureza: repetir
            # não conserta nenhum deles.
            if "não achei lugar para escrever" not in str(exc):
                raise
            motivo = str(exc)
            if time.monotonic() >= limite_de_tempo:
                return None, motivo
            dormir(INTERVALO_CAMPO)


def ditar(
    *,
    programa: str,
    texto: str,
    executar: bool = False,
    acrescentar: bool = False,
    leitor: Any = None,
    alvo: str = "",
    abrir: Callable[[str], Any] | None = None,
    espera: float = ESPERA_PADRAO,
    espera_campo: float = ESPERA_CAMPO,
    dormir: Callable[[float], Any] = DORMIR,
    profundidade: int = arvore.PROFUNDIDADE_PADRAO,
    limite: int = arvore.LIMITE_PADRAO,
    fonte: str = "auto",
) -> dict[str, Any]:
    """Abre o programa se preciso, espera o campo, escreve e confere.

    `abrir` é o que executa o programa. Em branco, usa `pc.abrir_programa` —
    que respeita `JARVIS_HOST_PC=1`. A sonda passa `abrir_direto`.
    """
    if leitor is None:
        raise DitarError("ditar num programa só existe no Windows hoje.")

    try:
        info = pc.resolver(programa)
    except pc.PcError as exc:
        raise DitarError(str(exc)) from exc

    executavel = info["executavel"]
    rotulo = info["rotulo"]
    base: dict[str, Any] = {"programa": info["chave"], "rotulo": rotulo, "executavel": executavel}

    candidatas = janelas_do_programa(leitor.janelas(), executavel, rotulo)
    janela = candidatas[0] if candidatas else None
    abriu = False
    if janela is None:
        if not executar:
            base.update(
                {
                    "ok": True,
                    "executou": False,
                    "precisa_abrir": True,
                    "resumo": (
                        f"o {rotulo} não está aberto: eu abriria, esperaria a janela e escreveria "
                        f"{_cita(texto)}. Nada foi aberto e nada foi escrito."
                    ),
                    "como_autorizar": "repita o comando com --executar para fazer de verdade.",
                }
            )
            return base
        acao_abrir = abrir or (lambda exe: pc.abrir_programa(exe))
        try:
            acao_abrir(executavel if abrir is None else programa)
        except pc.PcError as exc:
            raise DitarError(str(exc)) from exc
        except OSError as exc:
            raise DitarError(f"o Windows recusou abrir {executavel}: {exc}") from exc
        abriu = True
        janela = esperar_janela(leitor, executavel, rotulo, segundos=espera, dormir=dormir)
        if janela is None:
            raise DitarError(
                f"abri o {rotulo} ({executavel}), mas nenhuma janela dele apareceu em {espera:.0f}s. "
                "Se a janela estiver na barra de tarefas, clique nela uma vez e rode de novo."
            )

    alvo_final = alvo or executavel
    # Se o programa tem mais de uma janela, a que serve é a que publica campo
    # — e descobrir isso relendo é barato. Antes de esperar 15s numa janela
    # que nunca vai servir, uma sondagem de uma leitura em cada candidata.
    if len(candidatas) > 1:
        for tentativa in candidatas:
            rapido, _ = _esperar_campo(
                texto=texto,
                leitor=leitor,
                alvo=alvo_final,
                handle=int(tentativa.get("handle") or 0) or None,
                profundidade=profundidade,
                limite=limite,
                fonte=fonte,
                acrescentar=acrescentar,
                segundos=0,
                dormir=dormir,
            )
            if rapido is not None:
                janela = tentativa
                break

    # O handle fixa a janela: escolher de novo poderia cair na outra.
    handle_escolhido = int(janela.get("handle") or 0) or None
    plano, motivo = _esperar_campo(
        texto=texto,
        leitor=leitor,
        alvo=alvo_final,
        handle=handle_escolhido,
        profundidade=profundidade,
        limite=limite,
        fonte=fonte,
        acrescentar=acrescentar,
        segundos=espera_campo,
        dormir=dormir,
    )
    if plano is None:
        raise DitarError(
            f"a janela do {rotulo} está aberta, mas em {espera_campo:.0f}s ela não publicou nenhum "
            f"lugar de escrever. O que ela respondeu: {motivo or '(sem detalhe)'} "
            "Se ela aparecer servível em `--provados`, repita o comando; se não aparecer, o "
            "programa abre numa janela que não publica conteúdo."
        )
    if not executar:
        plano.update(base)
        plano["abriu"] = abriu
        if abriu:
            plano["resumo"] = f"Abri o {rotulo}. " + str(plano.get("resumo") or "")
        return plano

    resposta = mesa_agir.escrever_na_janela(
        texto=texto,
        executar=True,
        leitor=leitor,
        alvo=alvo_final,
        profundidade=profundidade,
        limite=limite,
        fonte=fonte,
        acrescentar=acrescentar,
        handle=handle_escolhido,
    )
    resposta.update(base)
    resposta["abriu"] = abriu
    if abriu:
        resposta["resumo"] = f"Abri o {rotulo}. " + str(resposta.get("resumo") or "")
    return resposta


def _cita(texto: str) -> str:
    limpo = str(texto or "")
    return f"{limpo!r}" if limpo else "(sem texto)"
