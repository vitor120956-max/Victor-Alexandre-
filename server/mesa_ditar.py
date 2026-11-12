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
INTERVALO = 0.4


def _norm(texto: str) -> str:
    return " ".join(str(texto or "").lower().split())


def janela_do_programa(janelas: list[dict[str, Any]], executavel: str, rotulo: str) -> dict[str, Any] | None:
    """A janela daquele programa, se estiver aberta.

    Casa pelo **processo** (`notepad.exe`) e, quando o processo não vem, pelo
    título com o rótulo em português (“Bloco de notas”). Nada de casar por
    pedaço solto: “calc” está dentro de “calculadora”, mas também de
    “calculator-service” de outro programa.
    """
    exe = _norm(executavel)
    nome = _norm(rotulo)
    for janela in janelas or []:
        if _norm(janela.get("processo")) == exe:
            return janela
    for janela in janelas or []:
        titulo = _norm(janela.get("titulo"))
        if nome and (titulo == nome or nome in titulo):
            return janela
    return None


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
    dormir: Callable[[float], Any] = DORMIR,
    profundidade: int = arvore.PROFUNDIDADE_PADRAO,
    limite: int = arvore.LIMITE_PADRAO,
    fonte: str = "auto",
) -> dict[str, Any]:
    """Abre o programa se preciso, acha o campo, escreve e confere.

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

    janela = janela_do_programa(leitor.janelas(), executavel, rotulo)
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

    resposta = mesa_agir.escrever_na_janela(
        texto=texto,
        executar=executar,
        leitor=leitor,
        alvo=alvo or executavel,
        profundidade=profundidade,
        limite=limite,
        fonte=fonte,
        acrescentar=acrescentar,
    )
    resposta.update(base)
    resposta["abriu"] = abriu
    if abriu:
        resposta["resumo"] = f"Abri o {rotulo}. " + str(resposta.get("resumo") or "")
    return resposta


def _cita(texto: str) -> str:
    limpo = str(texto or "")
    return f"{limpo!r}" if limpo else "(sem texto)"
