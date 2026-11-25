"""Do diagnóstico para a ação — o que o JARVIS faz **depois** de medir (0.95.5).

O scanner respondia “a causa é o app X travando” e parava ali. O dono ficava
com a frase e o trabalho: achar o app, achar o botão, decidir. Este módulo
transforma cada causa medida numa **ação concreta**, cada uma declarando:

- o que faz (uma frase, sem promessa que não se mede);
- o que **não** faz (o limite daquela ação em particular);
- se é reversível;
- se o JARVIS pode executar (`jarvis_faz`) ou se é só um passo que o dono dá;
- qual é a medida que sustenta a ação — a mesma que o diagnóstico já usou.

Nada aqui executa nada. O executor é `acoes.py`, com `JARVIS_ACOES=1` e
`confirmado=True`; este módulo só **monta o plano** e diz o que falta.

A regra da casa vale em cada linha: se não há medida, não há ação. Uma causa
“sem medida no aparelho” vira `o_que_falta` (“meça isto antes”), nunca uma
ordem para mexer no aparelho de alguém no escuro.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# O que o JARVIS consegue executar hoje (medido em `acoes.py`, não inventado)
# ---------------------------------------------------------------------------

# Estas são as únicas ações com efeito no celular que o projeto implementou.
# Tudo o mais que aparecer aqui é `jarvis_faz=False` com o motivo escrito.
EXECUTAVEIS: dict[str, str] = {
    "fechar-app": "am force-stop <pacote> — fecha o app, descarta o que não estava salvo",
    "abrir-app": "monkey -p <pacote> — inicia o app que já está instalado",
    "instalar-apk": "adb install -r — reinstala um .apk que já está na área do JARVIS",
}

# O que o JARVIS **recusa** por decisão de projeto, não por falta de código.
RECUSADOS: dict[str, str] = {
    "root": (
        "O JARVIS não usa root. A mesma porta que deixaria ele ler tudo deixaria "
        "qualquer app ler tudo, inclusive o do banco."
    ),
    "desinstalar": (
        "Desinstalar apaga dados de app sem volta. O JARVIS não faz isso sozinho: "
        "abre o caminho (Ajustes → Apps) e você decide."
    ),
    "limpar-dados": (
        "“Limpar dados” apaga conta e conversas. O JARVIS só sugere “Limpar cache”, "
        "que não apaga conta."
    ),
    "formatar": "Formatar apaga o aparelho inteiro. Não existe versão segura disso automática.",
    "flash": "Escrever em partição de sistema pode virar tijolo. Fora, em qualquer versão.",
}


def _acao(
    identificador: str,
    titulo: str,
    faz: str,
    *,
    pacote: str = "",
    jarvis_faz: bool = False,
    comando: str = "",
    reversivel: bool = True,
    limite: str = "",
    onde_no_aparelho: str = "",
    evidencia: list[str] | None = None,
    risco: str = "",
) -> dict[str, Any]:
    return {
        "id": identificador,
        "titulo": titulo,
        "faz": faz,
        "pacote": pacote,
        "jarvis_faz": jarvis_faz,
        "comando": comando,
        "reversivel": reversivel,
        "limite": limite,
        "onde_no_aparelho": onde_no_aparelho,
        "evidencia": list(evidencia or []),
        "risco": risco,
    }


# ---------------------------------------------------------------------------
# Os problemas medidos viram ação (o mapa que faltava)
# ---------------------------------------------------------------------------

# Cada id é o mesmo que `diagnostico_celular.analisar()` emite em `problemas`.
# O teste `test_a_acao_aponta_para_um_problema_que_existe` cobra que não haja
# aqui id que o scanner não emite — foi assim que a 0.93.0 pegou a tabela morta
# de `EVIDENCIA_MEDIDA`.
def acoes_para(relatorio: dict[str, Any]) -> list[dict[str, Any]]:
    """Monta o plano de ação a partir do que o aparelho **mediu**.

    Só entra ação que tem evidência no relatório. Um relatório sem problema
    devolve lista vazia — e isso é a resposta certa, não uma falha.
    """
    problemas = {p["id"]: p for p in relatorio.get("problemas", [])}
    planos: list[dict[str, Any]] = []

    # --- app travando / ANR: o caso do relatório real do dono
    travando = problemas.get("app-nao-responde") or problemas.get("app-travando")
    if travando:
        pacote = _pacote_do_problema(travando)
        evidencia = [travando["id"]]
        if pacote:
            planos.append(_acao(
                "fechar-app-travado",
                f"Fechar {pacote} agora",
                (
                    "Fecha o app que travou. Isso libera a janela que estava presa e "
                    "devolve o toque na hora — o problema não é do Android, é daquele app."
                ),
                pacote=pacote,
                jarvis_faz=True,
                comando=f"celular.fechar-app — pacote: {pacote}",
                reversivel=True,
                limite=(
                    "Fecha agora e o app reabre no próximo toque. Se ele travar de novo, "
                    "o problema é a versão do app — aí é atualizar ou reinstalar."
                ),
                evidencia=evidencia,
                risco="Perde o que não estava salvo dentro do app (rascunho, vídeo em gravação).",
            ))
            planos.append(_acao(
                "atualizar-app-travado",
                f"Atualizar {pacote}",
                "A versão nova quase sempre traz a correção do travamento.",
                pacote=pacote,
                jarvis_faz=False,
                onde_no_aparelho="Play Store → Buscar atualizações",
                limite="O JARVIS não instala pela loja: isso exige a sua conta.",
                evidencia=evidencia,
            ))
        planos.append(_acao(
            "limpar-cache-app-travado",
            "Limpar o cache do app (não os dados)",
            (
                "Cache corrompido é a causa mais comum de app travando sem atualização "
                "disponível. Limpar cache **não** apaga conta nem conversa."
            ),
            pacote=pacote,
            jarvis_faz=False,
            onde_no_aparelho="Ajustes → Apps → [app] → Armazenamento → Limpar cache",
            limite="Só o cache. “Limpar dados” apaga conta e conversa — não toque nele.",
            evidencia=evidencia,
        ))

    # --- armazenamento cheio
    if "armazenamento-cheio" in problemas or "armazenamento-apertado" in problemas:
        chave = "armazenamento-cheio" if "armazenamento-cheio" in problemas else "armazenamento-apertado"
        planos.append(_acao(
            "liberar-espaco",
            "Liberar espaço antes de tudo",
            (
                "Com o disco quase cheio o Android não consegue gravar cache nem "
                "atualizar app — e é isso que faz o sistema inteiro parecer lento."
            ),
            jarvis_faz=False,
            reversivel=False,
            onde_no_aparelho="Ajustes → Armazenamento → Apps (ordene por tamanho)",
            limite=(
                "O JARVIS não apaga arquivo seu. Ele diz o que ocupa e você escolhe; "
                "apagar foto e vídeo não tem volta."
            ),
            evidencia=[chave],
            risco="Apagar mídia é irreversível sem backup.",
        ))

    # --- memória baixa: aqui o JARVIS **pode** agir
    if "memoria-baixa" in problemas:
        pesados = _apps_pesados(relatorio)
        if pesados:
            planos.append(_acao(
                "fechar-app-pesado",
                f"Fechar {pesados[0]}",
                (
                    "É o app que mais ocupa memória agora. Fechar devolve a RAM e o "
                    "Android para de matar outros apps para abrir espaço."
                ),
                pacote=pesados[0],
                jarvis_faz=True,
                comando=f"celular.fechar-app — pacote: {pesados[0]}",
                reversivel=True,
                limite="Volta a ocupar quando você abrir de novo. Não é conserto, é alívio.",
                evidencia=["memoria-baixa"],
            ))
        planos.append(_acao(
            "reduzir-apps-segundo-plano",
            "Restringir apps que você não abre há meses",
            "App que você não abre não precisa ficar acordado gastando RAM e bateria.",
            jarvis_faz=False,
            onde_no_aparelho="Ajustes → Apps → [app] → Bateria → Restringir",
            limite="Restringir pode atrasar notificação desse app. Escolha um que não te avisa.",
            evidencia=["memoria-baixa"],
        ))

    # --- calor
    if "aquecendo" in problemas or "bateria-quente-carregando" in problemas:
        chave = "aquecendo" if "aquecendo" in problemas else "bateria-quente-carregando"
        planos.append(_acao(
            "esfriar",
            "Deixar esfriar sem carregar",
            (
                "Acima de ~70 °C o Android baixa a frequência de propósito. Enquanto "
                "estiver quente, tudo fica lento — e não é defeito."
            ),
            jarvis_faz=False,
            onde_no_aparelho="Tire do carregador e deixe 10 minutos em lugar ventilado",
            limite="Não adianta mexer em ajuste com o aparelho quente: a medida mente.",
            evidencia=[chave],
        ))

    # --- bateria caindo rápido (o que dá para medir sem root)
    if "bateria-gasta" in problemas:
        planos.append(_acao(
            "ver-consumo-bateria",
            "Ver quem está gastando bateria",
            "O próprio Android mostra o consumo por app nas últimas 24 h sem precisar de root.",
            jarvis_faz=False,
            onde_no_aparelho="Ajustes → Bateria → Uso da bateria",
            limite="Consumo por app em detalhe (mA) exige root; o resumo não.",
            evidencia=["bateria-gasta"],
        ))

    # --- patch de segurança velho
    if "patch-antigo" in problemas:
        planos.append(_acao(
            "atualizar-sistema",
            "Procurar atualização do Android",
            "Patch de segurança velho é falha conhecida que o fabricante já corrigiu.",
            jarvis_faz=False,
            onde_no_aparelho="Ajustes → Atualização de software → Baixar e instalar",
            limite=(
                "O JARVIS não instala atualização de sistema: se a bateria acabar no "
                "meio, o aparelho pode não voltar."
            ),
            evidencia=["patch-antigo"],
            risco="Atualização reinicia o aparelho. Faça com bateria acima de 50%.",
        ))

    return planos


def _pacote_do_problema(problema: dict[str, Any]) -> str:
    """O pacote que o achado mediu, lido do texto — sem inventar nome."""
    import re

    # `_problema()` guarda o texto em `medido` (o que sustentou o achado);
    # `titulo` é a frase curta. Os dois, porque o pacote pode estar em qualquer
    # um — no relatório real ele vem em `medido`: “travamento de: com.dti.…”.
    texto = " ".join(str(problema.get(c, "")) for c in ("titulo", "medido", "causa"))
    # pacote Android: pelo menos um ponto, começa com letra
    achado = re.search(r"\b([a-zA-Z][\w]*(\.[\w]+){2,})\b", texto)
    return achado.group(1) if achado else ""


def _apps_pesados(relatorio: dict[str, Any]) -> list[str]:
    """Os pacotes que mais ocupam memória, na ordem — só os que o aparelho disse."""
    for secao in relatorio.get("secoes", []):
        if secao.get("id") not in ("memoria", "processos", "apps"):
            continue
        for item in secao.get("itens", []):
            valor = str(item.get("valor", ""))
            achados = [p for p in _pacotes_no_texto(valor)]
            if achados:
                return achados
    return []


def _pacotes_no_texto(texto: str) -> list[str]:
    import re

    return re.findall(r"\b([a-zA-Z][\w]*(\.[\w]+){2,})\b", texto) and [
        m.group(1) for m in re.finditer(r"\b([a-zA-Z][\w]*(\.[\w]+){2,})\b", texto)
    ]


# ---------------------------------------------------------------------------
# O que **não** dá: dito com o motivo, não com um “não” seco
# ---------------------------------------------------------------------------


def sem_como(relatorio: dict[str, Any]) -> list[dict[str, str]]:
    """O que o dono talvez queira e o JARVIS não faz — com o porquê e a saída.

    Um “não” sem alternativa deixa a pessoa travada. Cada linha aqui tem
    `porque` **e** `em_vez_disso`.
    """
    itens: list[dict[str, str]] = [
        {
            "pedido": "Você entrar no meu celular e resolver sozinho, sem eu tocar em nada",
            "porque": (
                "O JARVIS roda no PC e fala com o celular por `adb`, que é uma porta "
                "estreita: só passa o que o Android publica para depuração. Ele não tem "
                "tela, não vê o que está desenhado e não pode tocar num botão que exija conta."
            ),
            "em_vez_disso": (
                "Ele faz o que a porta permite (fechar o app travado, abrir, instalar) e, "
                "para o resto, entrega o passo exato com o nome do menu."
            ),
        },
        {
            "pedido": "Ler as conversas dos apps",
            "porque": RECUSADOS["root"],
            "em_vez_disso": "Exportar o backup do próprio app, quando ele oferece essa opção.",
        },
        {
            "pedido": "Desinstalar app sozinho",
            "porque": RECUSADOS["desinstalar"],
            "em_vez_disso": "O JARVIS diz qual app ocupa mais e abre o caminho em Ajustes → Apps.",
        },
        {
            "pedido": "Consertar toque fantasma por software",
            "porque": (
                "Toque fantasma é o controlador de toque do vidro, não o Android. Nenhum "
                "comando muda o que o hardware está entregando."
            ),
            "em_vez_disso": (
                "O teste que separa: tire capa e película, use um dia; depois teste sem "
                "carregador. Se parar, a causa é acessório — não é software."
            ),
        },
    ]
    return itens


# ---------------------------------------------------------------------------
# O plano completo, pronto para a tela
# ---------------------------------------------------------------------------


def planejar(relatorio: dict[str, Any]) -> dict[str, Any]:
    """Junta ações, recusas e o que falta medir.

    Devolve três listas separadas, porque misturar “o que eu faço”, “o que você
    faz” e “o que ninguém faz” é o que faz um relatório parecer promessa.
    """
    acoes = acoes_para(relatorio)
    executaveis = [a for a in acoes if a["jarvis_faz"]]
    seus = [a for a in acoes if not a["jarvis_faz"]]

    faltando: list[str] = []
    if not relatorio.get("problemas"):
        faltando.append(
            "Nenhum problema medido: sem medida não há ação. Rode a varredura com o "
            "aparelho conectado antes de mexer em qualquer coisa."
        )
    if any("sem medida" in str(t) for t in _titulos_sem_medida(relatorio)):
        faltando.append(
            "Há suspeita sem medida no aparelho. Ação sem medida é chute — o plano "
            "daquela suspeita é o teste, não o ajuste."
        )

    if executaveis:
        veredito = (
            f"O JARVIS pode agir em {len(executaveis)} ponto(s) agora, "
            f"e {len(seus)} passo(s) dependem de você."
        )
    elif seus:
        veredito = (
            f"Nada que o JARVIS possa executar sozinho: são {len(seus)} passo(s) seus, "
            "cada um com o menu exato."
        )
    elif faltando:
        veredito = "Não há ação: falta medida."
    else:
        veredito = "Nada a fazer — e isso é uma resposta, não uma falha."

    return {
        "veredito": veredito,
        "jarvis_executa": executaveis,
        "voce_faz": seus,
        "falta_medir": faltando,
        "sem_como": sem_como(relatorio),
        "como_autorizar": (
            "Nada aqui roda sozinho. Para o JARVIS executar: `JARVIS_ACOES=1` no `.env` "
            "e `confirmado: true` na chamada. Sem os dois, ele devolve o plano e não "
            "toca no aparelho."
        ),
    }


def _titulos_sem_medida(relatorio: dict[str, Any]) -> list[str]:
    sintomas = relatorio.get("sintomas") or {}
    return [
        causa["titulo"]
        for causa in sintomas.get("fila", [])
        if not causa.get("medido_no_aparelho")
    ]
