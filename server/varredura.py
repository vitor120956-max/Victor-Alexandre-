"""Passar o JARVIS pelo celular inteiro, num comando só (0.92.5).

O dono, com o cabo já conectado: *“ta ja conectei o cll no pc como faço o jarvis
rodar por todo o meu celular”*.

Até a 0.92.4 isso estava espalhado em três lugares: **Anatomia** (o que o
aparelho é), **scanner** (o que está errado) e **Reversa** (o que os arquivos
são). Quem conecta o cabo tem de saber qual dos três usar primeiro — e o pedido
foi “rodar por todo”, não “escolher uma aba”.

Este módulo é o maestro dessa passagem, e ele é **de leitura do começo ao fim**:

1. **estado** — o aparelho está autorizado? qual é?
2. **identidade** — `anatomia.ler_android`: o que o aparelho é.
3. **saúde** — `diagnostico_celular`: o que está errado, com a medida.
4. **ocupantes** — quais apps estão rodando e quais foram instalados.
5. **arquivos** — o mapa das pastas que o Android publica **sem root**.
6. **o que não dá** — a lista do que exige root, dita antes de alguém prometer.

O que ele **não** faz: não copia arquivo do aparelho (isso é `celular.puxar`,
com confirmação), não instala, não desinstala, não abre tela (`scrcpy` é outro
comando), não lê `/data` e não usa root. “Passar por todo o celular” aqui
significa **olhar tudo o que o Android entrega**, não tomar conta do aparelho.

## Sobre “100% de acesso”

O dono pediu *“quero e preciso q o jarvis tenha 100 de acesso ao meu celular”*.
Isso não se resolve com uma linha de código: o Android é feito para **nenhum**
programa ter 100% — nem o da fabricante, sem o desbloqueio do bootloader e o
root. `CONTROLE` mede **o quanto dá para chegar hoje**, em degraus, e diz em
cada um o que falta e o que se perde. Ele não finge: o degrau mais alto que
existe é o 4 (root), e o 4 só vale com o bootloader já desbloqueado pelo dono,
na tela de um PC, com o aparelho apagado no processo.

A varredura leva alguns segundos: são ~25 comandos de leitura, cada um de 1 a 3
segundos no cabo. Ela é resistente a falha parcial: se um comando não responder,
o relatório sai com o resto e diz qual ficou de fora — em vez de não sair.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

from . import anatomia, celular, diagnostico_celular

AMBIENTE = anatomia.AMBIENTE_ANDROID
TIMEOUT = 30
MAX_SAIDA = 120_000

# Só leitura. O teste confere esta lista palavra por palavra.
#
# 0.92.6 — a lista era **escrita à mão** e menor que a do scanner. O scanner só
# enxerga o que está em `saidas`, com a chave exata; o que faltava, ele lia como
# vazio. Um relatório real (SM-A346MU, Android 16) saiu com “Nenhum problema nas
# áreas que o scanner mede” — porque o scanner recebeu zero medida e zero medida
# é indistinguível de aparelho saudável. Agora a lista é **derivada** da do
# scanner: acrescentar leitura lá passa a valer aqui sozinho, e a divergência
# deixou de ser possível.
LEITURAS_DO_SCANNER: tuple[tuple[str, ...], ...] = diagnostico_celular.COMANDOS

# O que só a varredura olha: o mapa de pastas, o resumo do `dumpsys` e a lista
# de apps de fábrica. Nada aqui é de efeito.
LEITURAS_SO_DA_VARREDURA: tuple[tuple[str, ...], ...] = (
    ("shell", "ls", "-la", "/"),
    ("shell", "ls", "-la", "/storage/emulated/0"),
    ("shell", "ls", "-la", "/system"),
    ("shell", "ls", "-la", "/vendor"),
    ("shell", "ls", "-la", "/data/app"),
    ("shell", "cat", "/proc/partitions"),
    ("shell", "dumpsys", "meminfo"),
    ("shell", "ps", "-A", "-o", "PID,RSS,NAME"),
    ("shell", "pm", "list", "packages", "-s"),
)

COMANDOS: tuple[tuple[str, ...], ...] = LEITURAS_DO_SCANNER + LEITURAS_SO_DA_VARREDURA

_PALAVRAS_PROIBIDAS = {
    "install", "uninstall", "push", "pull", "rm", "mv", "cp", "reboot",
    "wipe", "format", "set", "put", "delete", "clear", "keyevent", "input", "su",
}


# A única leitura que cita uma palavra proibida é `which su` — ela **pergunta se
# existe**, não executa. O auditor sabe a diferença em vez de abrir exceção cega.
_LEITURAS_QUE_CITAM = {("which", "su"), ("dumpsys", "input")}


# O que sustenta um “nenhum problema”: sem estas leituras, o scanner não viu
# nada e dizer “está tudo bem” seria mentira por omissão (defeito da 0.92.5, que
# apareceu no primeiro relatório real).
LEITURAS_DE_SAUDE = ("getprop", "dumpsys battery", "df -k", "cat /proc/meminfo", "ps -A -o RSS,NAME")


def _auditar() -> None:
    for comando in COMANDOS:
        palavras = " ".join(comando).split()
        for i, palavra in enumerate(palavras):
            if palavra in _PALAVRAS_PROIBIDAS:
                anterior = palavras[i - 1] if i else ""
                assert (anterior, palavra) in _LEITURAS_QUE_CITAM, (
                    f"comando de efeito na varredura: {' '.join(comando)}"
                )


_auditar()

# As pastas que o Android publica sem root. O mapa é fechado de propósito: o
# que não está aqui não é listado, e o relatório diz o nome do que ficou de fora.
PASTAS = (
    ("/", "Raiz do sistema de arquivos"),
    ("/storage/emulated/0", "Armazenamento do usuário"),
    ("/system", "Sistema (somente leitura)"),
    ("/vendor", "Drivers do fabricante"),
    ("/data/app", "Onde os apps instalados moram"),
)

# O que exige root, dito de uma vez — para ninguém prometer “acesso total”.
SEM_ROOT = (
    "`/data/data` — os dados e as conversas de cada app ficam fora do alcance sem root.",
    "`/data/system` — senhas, contas e ajustes ficam criptografados e fechados.",
    "Partição de recuperação, boot e modem — `adb` não lê sem bootloader desbloqueado.",
    "Memória de outro app em execução — o kernel isola por desenho.",
)


class VarreduraError(RuntimeError):
    """Falha explicada em português, pronta para a tela e para o console."""


def _agora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _cortar(texto: str, limite: int = MAX_SAIDA) -> str:
    return anatomia._cortar(texto, limite)  # noqa: SLF001


def contar_linhas(texto: str) -> int:
    return sum(1 for linha in (texto or "").splitlines() if linha.strip())


def ler_pastas(saida: str, *, limite: int = 12) -> list[dict[str, str]]:
    """Traduz um `ls -la` em itens legíveis — nome, tipo e tamanho.

    O `ls` do Android (toybox) não é o do GNU: colunas variam com o locale. O
    parser lê o que é estável — a linha de permissão, o tamanho e o nome no fim,
    que pode ter espaço (por isso `split(maxsplit=7)`).
    """
    itens: list[dict[str, str]] = []
    for linha in (saida or "").splitlines():
        if not linha or linha.startswith("total"):
            continue
        partes = linha.split(None, 7)
        if len(partes) < 8:
            continue
        permissoes, _, _, _, tamanho, _, _, nome = partes
        if nome in {".", ".."}:
            continue
        if permissoes.startswith("d"):
            tipo = "pasta"
            tamanho_texto = ""
        elif permissoes.startswith("l"):
            tipo = "atalho"
            tamanho_texto = ""
        else:
            tipo = "arquivo"
            tamanho_texto = _tamanho(tamanho)
        if tipo == "atalho" and " -> " in nome:
            # `bin -> /system/bin` vira destino legível, em vez de nome composto.
            nome, _, destino = nome.partition(" -> ")
            itens.append({"nome": nome, "tipo": f"atalho para {destino.strip()}", "tamanho": ""})
        else:
            itens.append({"nome": nome, "tipo": tipo, "tamanho": tamanho_texto})
        if len(itens) >= limite:
            break
    return itens


def _tamanho(bruto: str) -> str:
    try:
        bytes_ = int(bruto)
    except ValueError:
        return bruto
    if bytes_ >= 1_000_000_000:
        return f"{bytes_ / 1e9:.1f} GB".replace(".", ",")
    if bytes_ >= 1_000_000:
        return f"{bytes_ / 1e6:.1f} MB".replace(".", ",")
    if bytes_ >= 1_000:
        return f"{bytes_ / 1e3:.0f} KB"
    return f"{bytes_} B"


def ler_particoes(saida: str, *, limite: int = 14) -> list[dict[str, str]]:
    """`/proc/partitions` — o esqueleto do armazenamento.

    Nome e tamanho só. O conteúdo de cada partição não é lido — é o que separa
    “ver a anatomia” de “mexer no paciente”.
    """
    partes: list[dict[str, str]] = []
    for linha in (saida or "").splitlines()[1:]:
        campos = linha.split()
        if len(campos) < 4:
            continue
        nome = campos[3]
        if not re.match(r"^(mmcblk|sda|sdb|sdc|dm-|nvme|loop)", nome):
            continue
        try:
            mb = int(campos[2]) // 1024
        except ValueError:
            continue
        partes.append({"nome": nome, "tamanho": f"{mb} MB" if mb < 1024 else f"{mb / 1024:.0f} GB"})
        if len(partes) >= limite:
            break
    return partes


def ler_memoria_detalhada(saida: str) -> dict[str, str]:
    """`dumpsys meminfo` sem argumento: o resumo de RAM do sistema inteiro."""
    chaves = {
        "Total RAM": "RAM total",
        "Free RAM": "Livre",
        "Used RAM": "Usada",
        "Lost RAM": "Perdida",
        "ZRAM": "ZRAM",
    }
    achados: dict[str, str] = {}
    for linha in (saida or "").splitlines():
        for chave, rotulo in chaves.items():
            if linha.strip().startswith(chave):
                valor = linha.split(":", 1)[-1].strip()
                if rotulo not in achados and valor:
                    achados[rotulo] = valor
    return achados


def ler_processos(saida: str, *, limite: int = 10) -> list[dict[str, str]]:
    """`ps -A -o PID,RSS,NAME` — quem está rodando agora, do maior para o menor."""
    itens: list[dict[str, str]] = []
    for linha in (saida or "").splitlines():
        partes = linha.split(None, 2)
        if len(partes) != 3 or not partes[0].isdigit() or not partes[1].isdigit():
            continue
        itens.append({"pid": partes[0], "nome": partes[2].strip(), "mb": f"{int(partes[1]) // 1024} MB"})
    itens.sort(key=lambda item: int(item["mb"].split()[0]), reverse=True)
    return itens[:limite]


def ler_apps_de_sistema(saida: str) -> list[str]:
    return sorted(
        linha.strip().removeprefix("package:")
        for linha in (saida or "").splitlines()
        if linha.strip().startswith("package:")
    )


def coletar(
    alvo: str = "",
    *,
    rodar: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """O passo “passar por todo o celular”: roda a lista de leitura e guarda as saídas."""
    if not celular.ligado():
        raise VarreduraError(
            "A varredura do celular está desligada. Acrescente `set "
            f"{AMBIENTE}=1` no iniciar-jarvis.bat, feche e abra de novo."
        )
    executor = rodar or (lambda argumentos: anatomia._rodar(argumentos, timeout=TIMEOUT))  # noqa: SLF001
    try:
        adb = anatomia._adb()  # noqa: SLF001 - mesma mensagem de “Preparar celular”
    except anatomia.AnatomiaError as exc:
        raise VarreduraError(str(exc)) from exc
    try:
        serial = diagnostico_celular._serial(alvo, executor)  # noqa: SLF001 - mesma frase de erro
    except diagnostico_celular.DiagnosticoError as exc:
        raise VarreduraError(str(exc)) from exc

    saidas: dict[str, str] = {}
    falhas: list[str] = []
    for comando in COMANDOS:
        chave = " ".join(comando[1:])
        try:
            codigo, saida, erro = executor([adb, "-s", serial, *comando])
        except anatomia.AnatomiaError as exc:
            falhas.append(f"“{chave}”: {exc}")
            continue
        if codigo != 0 and not saida:
            motivo = (erro or "sem resposta").strip().splitlines()
            falhas.append(f"“{chave}”: {motivo[0][:160] if motivo else 'sem resposta'}")
            continue
        saidas[chave] = _cortar(saida)
    return {"serial": serial, "saidas": saidas, "falhas": falhas}


def _secao(identificador: str, titulo: str, itens: list[dict[str, str]], *, nota: str = "") -> dict[str, Any]:
    return {"id": identificador, "titulo": titulo, "itens": [i for i in itens if i.get("valor")], "nota": nota}


def _limites_sem_repetir(frases: list[str]) -> list[str]:
    """Uma linha por motivo — não três linhas do mesmo `Permission denied`.

    No relatório real do dono a mesma negativa aparecia três vezes: uma do
    `cat /proc/partitions` da varredura, uma do scanner e uma da anatomia. O
    `dict.fromkeys` não resolvia porque cada módulo escreve a frase com um
    prefixo diferente; a comparação aqui é pelo **miolo** (o erro em si).
    """
    vistos: list[str] = []
    restos: set[str] = set()
    for frase in frases:
        limpa = (frase or "").strip()
        if not limpa:
            continue
        miolo = limpa.split("”:", 1)[-1].strip().lower()
        if len(miolo) < 8:
            miolo = limpa.lower()
        if miolo in restos:
            continue
        restos.add(miolo)
        vistos.append(limpa)
    return vistos[:16]


def montar(medido: dict[str, Any], *, agora: str = "") -> dict[str, Any]:
    """Junta a varredura com a anatomia e o scanner — sem repetir leitura.

    0.92.6 — a junção estava **silenciosamente quebrada**: o scanner recebia um
    dicionário montado nesta função (`{"serial", "saidas", "falhas"}`) com as
    chaves de comando erradas, então `getprop`, `df -k` e `/proc/meminfo` não
    existiam para ele e ele devolvia “nenhum problema” — o mesmo texto de um
    aparelho saudável. Num relatório real isso apareceu como “PASTAS” cheia e
    “PARTIÇÕES” vazia na mesma tela.

    Agora há **um dicionário só**: as mesmas saídas alimentam o scanner, a
    anatomia e as seções daqui. E a seção `memoria` que o scanner produz é
    mantida (é a que traz `MemAvailable`, que o `dumpsys meminfo` não dá); o
    `dumpsys meminfo` entra como complemento, não como substituto.
    """
    saidas: dict[str, str] = medido.get("saidas", {})
    serial = medido.get("serial", "")

    # A anatomia precisa saber **qual** aparelho, não o primeiro que aparecer:
    # com dois celulares no cabo, `ler_android()` sem serial podia ler o outro.
    try:
        anatomia_relatorio = anatomia.ler_android(serial)
    except anatomia.AnatomiaError:
        anatomia_relatorio = {}
    try:
        saude = diagnostico_celular.analisar({"serial": serial, "saidas": saidas, "falhas": []})
    except Exception:  # noqa: BLE001 - o diagnóstico não pode derrubar a varredura
        saude = {}

    secoes: list[dict[str, Any]] = [
        _secao(
            "pastas",
            "Pastas que o Android publica",
            [
                _secao_pasta(nome, titulo, saidas)
                for nome, titulo in PASTAS
            ],
            nota="Cada pasta vira uma linha com os primeiros itens. Conteúdo de arquivo não é lido.",
        ),
    ]

    particoes = [
        {"rotulo": p["nome"], "valor": p["tamanho"]}
        for p in ler_particoes(saidas.get("cat /proc/partitions", ""))
    ]
    secoes.append(_secao(
        "particoes",
        "Partições",
        particoes or [{
            "rotulo": "Não publicada",
            "valor": "este Android não entrega /proc/partitions sem root — não é falta de cabo",
        }],
        nota="Nome e tamanho. Nenhuma partição é aberta.",
    ))

    # Memória: a do scanner (MemAvailable, a que importa) + o resumo do dumpsys.
    secao_scanner = next((s for s in saude.get("secoes", []) if s.get("id") == "memoria"), None)
    memoria_dumpsys = ler_memoria_detalhada(saidas.get("dumpsys meminfo", ""))
    itens_memoria = list(secao_scanner["itens"]) if secao_scanner else []
    conjunto = {i["rotulo"] for i in itens_memoria}
    itens_memoria += [
        {"rotulo": k, "valor": v} for k, v in memoria_dumpsys.items() if k not in conjunto
    ]
    if itens_memoria:
        secoes.append(_secao("memoria", "Memória do sistema", itens_memoria))

    # Processos: uma tabela só, com a média dos dois `ps` (o do scanner traz
    # RSS, o daqui traz PID — o nome é a chave para não duplicar linha).
    processos = ler_processos(saidas.get("ps -A -o PID,RSS,NAME", ""))
    if processos:
        secoes.append(_secao(
            "processos",
            "Rodando agora (maiores primeiro)",
            [{"rotulo": p["nome"], "valor": f"{p['mb']} · pid {p['pid']}"} for p in processos],
            nota="É uma foto do instante da varredura — não um histórico.",
        ))
    elif secao_scanner is None:
        secao_ps = next((s for s in saude.get("secoes", []) if s.get("id") == "processos"), None)
        if secao_ps:
            secoes.append(secao_ps)

    sistema = ler_apps_de_sistema(saidas.get("pm list packages -s", ""))
    if sistema:
        secoes.append(_secao(
            "sistema-apps",
            "Apps do sistema",
            [
                {"rotulo": "Total instalado de fábrica", "valor": str(len(sistema))},
                {"rotulo": "Amostra", "valor": ", ".join(sistema[:10])},
            ],
            nota="Desinstalar app de sistema é o que mais quebra aparelho — e o JARVIS não faz isso.",
        ))

    # Identidade: a mesma seção da Anatomia, inteira. Antes eram 6 itens de
    # duas seções — a carga e a temperatura ficavam de fora, e o “O APARELHO”
    # saía sem a marca do modelo no título.
    identidade = next(
        (s for s in anatomia_relatorio.get("secoes", []) if s.get("id") == "identidade"), None
    )
    bateria = next(
        (s for s in anatomia_relatorio.get("secoes", []) if s.get("id") == "bateria"), None
    )
    itens_aparelho = list(identidade["itens"]) if identidade else []
    itens_aparelho += list(bateria["itens"]) if bateria else []
    if itens_aparelho:
        secoes.append(_secao("identidade", "O aparelho", itens_aparelho))

    cobertura = len(saidas)
    total = len(COMANDOS)
    if cobertura >= total:
        frase = (
            f"Passei por {cobertura} de {total} leituras: o aparelho entregou tudo o que o Android "
            "publica sem root."
        )
    else:
        frase = (
            f"Passei por {cobertura} de {total} leituras. As que faltaram estão listadas abaixo — "
            "cada uma diz o motivo, e nenhuma delas foi inventada."
        )

    # “Nenhum problema” só pode ser dito se o scanner **conseguiu olhar**. Sem as
    # leituras de saúde, a frase certa é “não deu para medir” — não “está tudo bem”.
    problemas = saude.get("problemas", [])
    faltam_saude = [k for k in LEITURAS_DE_SAUDE if k not in saidas]
    if problemas:
        frase += (
            f" O scanner achou {len(problemas)} problema(s); o principal é: "
            f"{problemas[0]['titulo'].lower()}."
        )
    elif faltam_saude:
        # Sem as leituras de saúde o scanner devolve “nenhum problema” — e essa
        # frase, sozinha, é uma mentira por omissão. “Não deu para medir” é o
        # que aconteceu.
        frase += (
            " Mas as leituras de saúde não vieram nesta passagem: não dá para dizer que está "
            "tudo bem, só que não deu para medir."
        )
    elif saude.get("veredito"):
        frase += " " + saude["veredito"]

    return {
        "ok": True,
        "alvo": "android",
        "serial": serial,
        "titulo": anatomia_relatorio.get("titulo") or serial,
        "lido_em": agora or _agora(),
        "veredito": frase,
        # 0.92.9 — seção sem item não é seção: saía o título “PASTAS QUE O ANDROID
        # PUBLICA” seguido só da nota, e parecia leitura perdida. Se nada entrou,
        # a seção sai e o motivo fica nas limitações (que já listam o comando).
        "secoes": [s for s in secoes if s["itens"]],
        "problemas": problemas,
        "otimizacoes": saude.get("otimizacoes", []),
        "limitacoes": _limites_sem_repetir(
            list(medido.get("falhas", []))
            + list(saude.get("limitacoes", []))
            + list(anatomia_relatorio.get("limitacoes", []))
        ),
        "sem_root": list(SEM_ROOT),
        "nao_faz": list(diagnostico_celular.NAO_FAZ) + [
            "Não copia arquivo do aparelho: copiar é `celular.puxar`, com confirmação e só nas pastas de mídia.",
            "Não abre a tela do celular: isso é `scrcpy`, outro comando.",
        ],
    }


def _secao_pasta(nome: str, titulo: str, saidas: dict[str, str]) -> dict[str, str]:
    chave = next((k for k in saidas if k.startswith(f"ls -la {nome}")), "")
    itens = ler_pastas(saidas.get(chave, "")) if chave else []
    if not itens:
        return {"rotulo": f"{titulo} ({nome})", "valor": ""}
    resumo = ", ".join(f"{i['nome']}{'/' if i['tipo'] == 'pasta' else ''}" for i in itens[:6])
    resto = len(itens) - 6
    return {
        "rotulo": f"{titulo} ({nome})",
        "valor": resumo + (f" … +{resto}" if resto > 0 else ""),
    }


def varrer(
    alvo: str = "",
    *,
    rodar: Callable[[list[str]], tuple[int, str, str]] | None = None,
    agora: str = "",
    sintomas: list[str] | None = None,
) -> dict[str, Any]:
    """A passagem completa: mede, junta e devolve um relatório só.

    0.92.9 — aceita `sintomas`. Antes a varredura **não perguntava** o que o dono
    vê: ela media e o scanner dizia o que os limiares pegaram. A fila de
    suspeitas da 0.92.4 (que é o que transforma “frame lento” em “toque
    fantasma”) ficava de fora justamente no caminho mais fácil — o do duplo
    clique. Unificar era o pedido: “escanear por completo e ver se descobre os
    problemas” inclui o problema que o dono já sabe descrever.
    """
    medido = coletar(alvo, rodar=rodar)
    relatorio = montar(medido, agora=agora)
    if sintomas:
        relatorio["sintomas"] = _cruzar_sintomas(medido, sintomas)
    return relatorio


def _cruzar_sintomas(medido: dict[str, Any], sintomas: list[str]) -> dict[str, Any]:
    """Cruza o relato do dono com o que a varredura mediu.

    Reusa `diagnostico_celular.cruzar` de propósito: uma segunda implementação
    de pesos e “teste mais barato” divergiria da primeira na primeira mudança.
    A varredura já leu **todas** as saídas que o scanner pede (a lista é
    derivada), então o cruzamento roda sobre a mesma medida, sem reabrir o
    aparelho.
    """
    try:
        return diagnostico_celular.cruzar(
            {"serial": medido.get("serial", ""), "saidas": medido.get("saidas", {}), "falhas": []},
            sintomas,
        )
    except Exception:  # noqa: BLE001 - sintoma não pode derrubar a varredura
        return {
            "sintomas_marcados": list(sintomas),
            "fila": [],
            "veredito": "Não consegui cruzar os sintomas com o que o aparelho mediu nesta passagem.",
            "como_ler": "",
        }


def em_texto(relatorio: dict[str, Any]) -> str:
    linhas = ["", f"  {relatorio['titulo']}", f"  {relatorio['veredito']}", ""]
    sintoma = relatorio.get("sintomas")
    if sintoma and sintoma.get("fila"):
        linhas.append("  PELO QUE VOCÊ RELATOU — SUSPEITAS EM ORDEM")
        for posicao, causa in enumerate(sintoma["fila"][:4], start=1):
            marca = (
                "medido no aparelho"
                if causa.get("medido_no_aparelho")
                else "sem medida no aparelho"
            )
            linhas.append(f"    {posicao}. {causa['titulo']}  ({marca})")
            linhas.append(f"       por que: {causa['porque']}")
            for passo in causa.get("teste", [])[:2]:
                linhas.append(f"       teste: {passo}")
        if sintoma.get("veredito"):
            linhas.append(f"    {sintoma['veredito']}")
        linhas.append("")
    for secao in relatorio["secoes"]:
        linhas.append(f"  {secao['titulo'].upper()}")
        for item in secao["itens"]:
            linhas.append(f"    {item['rotulo']:<34} {item['valor']}")
        if secao.get("nota"):
            linhas.append(f"    ({secao['nota']})")
        linhas.append("")
    if relatorio["problemas"]:
        linhas.append("  O QUE ESTÁ ERRADO")
        for problema in relatorio["problemas"]:
            linhas.append(f"    [{problema['gravidade'].upper()}] {problema['titulo']} — {problema['medido']}")
            for passo in problema.get("o_que_fazer", [])[:3]:
                linhas.append(f"      - {passo}")
            if problema.get("limite"):
                linhas.append(f"      (limite: {problema['limite']})")
        linhas.append("")
    if relatorio.get("otimizacoes"):
        linhas.append("  O QUE DÁ PARA MELHORAR")
        for otimizacao in relatorio["otimizacoes"]:
            marca = "" if otimizacao.get("medido") else "  (ganho de sensação, não medido)"
            linhas.append(f"    - {otimizacao['titulo']}: {otimizacao['ganho']}{marca}")
        linhas.append("")
    if relatorio["sem_root"]:
        linhas.append("  O QUE NÃO DÁ SEM ROOT (e o JARVIS não usa root)")
        for frase in relatorio["sem_root"]:
            linhas.append(f"    - {frase}")
        linhas.append("")
    if relatorio["limitacoes"]:
        linhas.append("  LEITURAS QUE NÃO RESPONDERAM")
        for frase in relatorio["limitacoes"]:
            linhas.append(f"    - {frase}")
        linhas.append("")
    linhas.append("  O QUE ESTA VARREDURA NÃO FAZ")
    for frase in relatorio["nao_faz"]:
        linhas.append(f"    - {frase}")
    linhas.append("")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# “100% de acesso”: o mapa honesto do quanto existe, em degraus (0.92.5)
# ---------------------------------------------------------------------------

# Cada degrau: o que ganha, o que exige, o que custa, e se o JARVIS faz.
#
# O degrau 5 existe para ser dito **e recusado**: não é falta de técnica, é
# escolha — e o documento de limites do projeto já registra o porquê.
CONTROLE: tuple[dict[str, Any], ...] = (
    {
        "degrau": 1,
        "nome": "Cabo + Depuração USB (o que você já tem)",
        "ganha": (
            "Ler identidade, bateria, memória, armazenamento, partições, sensores, apps e "
            "o log; instalar e remover app que você manda; copiar as pastas de mídia; "
            "espelhar a tela e mandar toque/tecla pelo scrcpy; abrir e fechar app."
        ),
        "falta": "Ativar a Depuração USB e tocar em “Permitir” uma vez por computador.",
        "custa": "Nada. Já funciona.",
        "jarvis_faz": True,
        "recusa": "",
    },
    {
        "degrau": 2,
        "nome": "Fio desligado (ADB sem cabo, pela rede)",
        "ganha": "Os mesmos comandos do degrau 1, mas sem cabo, de qualquer lugar da mesma rede.",
        "falta": "Na primeira vez o cabo é obrigatório: `adb tcpip 5555` só roda com o cabo ligado.",
        "custa": "Qualquer aparelho na mesma Wi-Fi com a porta aberta passa a poder mandar comando.",
        "jarvis_faz": True,
        "recusa": "",
    },
    {
        "degrau": 3,
        "nome": "Root (superusuário)",
        "ganha": (
            "Ler `/data/data` (conversas e dados de cada app), `/data/system`, contas, e "
            "apagar/alterar arquivo de sistema; ter as mesmas permissões do sistema."
        ),
        "falta": "Bootloader desbloqueado + Magisk. E o desbloqueio **apaga o aparelho todo**.",
        "custa": (
            "Sem atualização OTA na maioria dos modelos; app de banco e de pagamento "
            "podem recusar o aparelho; e quem tem root pode ser atacado por qualquer app "
            "que peça permissão."
        ),
        "jarvis_faz": False,
        "recusa": (
            "O JARVIS **não** faz root nem usa root. Não é falta de código: é a linha que o "
            "projeto escolheu, porque a mesma porta que deixa o JARVIS ler tudo deixa "
            "qualquer outro programa ler tudo — inclusive o seu banco."
        ),
    },
    {
        "degrau": 4,
        "nome": "Flashear sistema (ROM, recovery, kernel)",
        "ganha": "Trocar o Android inteiro: versão mais nova, recurso que o fabricante tirou.",
        "falta": "Bootloader desbloqueado, ROM compatível exata e um PC para o flash.",
        "custa": (
            "Aparelho pode virar tijolo; perde garantia; perde DRM de vídeo (Netflix em HD); "
            "e o processo é irreversível na prática."
        ),
        "jarvis_faz": False,
        "recusa": "O JARVIS não escreve em partição de boot, sistema ou modem — nem com confirmação.",
    },
    {
        "degrau": 5,
        "nome": "Explorar falha do sistema para virar root",
        "ganha": "Root sem desbloquear o bootloader, em aparelho que o fabricante fechou.",
        "falta": "Uma falha não corrigida naquele modelo e naquela versão.",
        "custa": "Instabilidade, brick, e a falha que você usa fica aberta para outros.",
        "jarvis_faz": False,
        "recusa": (
            "O JARVIS não procura nem usa falha de segurança. Isso não é “acesso”, é "
            "quebrar a proteção de um aparelho que não é o dele."
        ),
    },
)


def _root_sem_reiniciar(
    props: dict[str, Any],
    *,
    adbd_depuravel: bool,
    root_temporario: bool,
    tem_root: bool,
) -> dict[str, Any]:
    """“Root sem reiniciar, sem apagar, sem quebrar nada?” — item por item.

    A pergunta do dono tem três condições, e elas não são do mesmo tipo:

    * **sem reiniciar** — `adb root` e uma sessão de `su` atendem. O primeiro é
      o `adbd` reiniciando o próprio daemon (não é reiniciar o aparelho); o
      segundo pede root **já instalado**.
    * **sem apagar** — `adb root` e `su` atendem; Magisk atende **só depois** de
      alguém ter destravado o bootloader e apagado o aparelho uma vez.
    * **sem quebrar nada** — aqui é onde quase tudo cai. O `adb root` **não**
      quebra: não toca em partição, não muda `verified boot`, some no reinício.
      O Magisk **quebra** `verified boot` de propósito (`orange`), e com ele
      caem OTA, banco, carteira e DRM. Uma sessão de `su` não quebra nada
      **naquele momento**, mas o root que a sustenta já quebrou.

    Resultado: **um** dos três caminhos atende às três condições — `adb root`.
    E ele depende de uma propriedade só, que este aparelho não tem.

    O que o dono **pode** ter hoje, sem root e sem destravar nada, é o
    **privilégio de shell do ADB** (o mesmo que app tipo Shizuku usa): roda com
    a identidade `shell`, sobrevive enquanto o `adb` estiver autorizado, não
    apaga nem quebra. Fica **abaixo** de root — e o campo `o_que_nao_faz` diz o
    que exatamente não dá com ele, para ninguém confundir os dois.
    """
    # Com root já instalado, a pergunta “posso ter root sem quebrar?” não faz
    # sentido: o custo já foi pago. `root_temporario` pode estar `True` por
    # `ro.debuggable`, mas isso é o `adb root` possível — não um atalho novo.
    root_temporario = bool(root_temporario) and not tem_root
    magisk_instalado = tem_root and str(props.get("ro.build.tags", "")).strip() == "test-keys"
    tabela = [
        {
            "caminho": "adb root (adbd vira root)",
            "duravel": "até reiniciar",
            "sem_reiniciar": True,
            "sem_apagar": True,
            "sem_quebrar": True,
            "neste_aparelho": root_temporario,
            "porque": (
                "O daemon do adb reinicia como root; o aparelho não reinicia. Não escreve em "
                "partição nem mexe no verified boot — por isso não quebra OTA, banco nem carteira."
                if root_temporario
                else "O adbd deste aparelho é de build de produção (`ro.debuggable=0`) e recusa: "
                     "“adbd cannot run as root in production builds”."
            ),
        },
        {
            "caminho": "sessão de su (app pede root por N minutos)",
            "duravel": "N minutos",
            "sem_reiniciar": True,
            "sem_apagar": False,
            "sem_quebrar": False,
            "neste_aparelho": bool(magisk_instalado),
            "porque": (
                "O root que empresta o su é o Magisk instalado — e instalar exigiu destravar o "
                "bootloader, que apaga o aparelho e deixa o verified boot em `orange`."
            ),
        },
        {
            "caminho": "Magisk “sem persistência”",
            "duravel": "até desinstalar",
            "sem_reiniciar": True,
            "sem_apagar": False,
            "sem_quebrar": False,
            "neste_aparelho": False,
            "porque": (
                "Continua sendo root instalado: exige destravar o bootloader (apaga tudo) e "
                "quebra OTA, banco, carteira e DRM de vídeo."
            ),
        },
    ]

    # O que dá para fazer **agora**, sem root nenhum: privilégio de shell.
    privilegio = {
        "qual": "privilégio de shell do ADB",
        "como": (
            "É o que o JARVIS já usa: `adb shell` roda como o usuário `shell`, não como root. "
            "Dura enquanto a Depuração USB estiver autorizada e o cabo (ou o `adb tcpip`) "
            "estiver ativo. Não apaga nada, não quebra nada, não mexe no bootloader."
        ),
        "da_para": [
            "ler tudo o que o Android publica (o que a varredura já faz)",
            "instalar e remover app do usuário (com confirmação)",
            "conceder e revogar permissão de app (`pm grant` / `pm revoke`)",
            "mudar ajustes globais (`settings put`) — inclusive os de animação",
            "congelar app (`pm disable-user`), o que equivalente a desativar",
            "espelhar a tela e mandar toque/tecla (`scrcpy`)",
            "copiar as pastas de mídia (`adb pull`)",
        ],
        "nao_da": [
            "ler `/data/data` de outro app (as conversas e os dados de cada app)",
            "ler `/data/system` (senhas, contas, ajustes protegidos)",
            "abrir a partição de boot/recovery/modem",
            "ver a memória de outro app em execução",
            "instalar módulo de sistema (Xposed, Magisk, framework)",
        ],
        "apps_que_usam": (
            "Apps como o Shizuku fazem exatamente isto: sobem um serviço com a identidade "
            "`shell` (via ADB) e emprestam esse privilégio a outros apps. Não é root, e o "
            "próprio projeto do Shizuku diz isso: “ADB privileges are not full root”."
        ),
    }

    if root_temporario:
        resposta = (
            "Sim — `adb root` atende às três: não reinicia o aparelho, não apaga nada e não "
            "quebra OTA, banco nem carteira. Dura até o próximo reinício. O JARVIS não roda o "
            "comando (root é a linha do projeto), mas neste aparelho o passivo seria reversível."
        )
    elif tem_root:
        resposta = (
            "Você já tem root neste aparelho, mas ele não veio de graça: o bootloader foi "
            "destravado em algum momento, e isso apagou o aparelho e quebrou o `verified boot`. "
            "O que dá para fazer agora sem reiniciar nem quebrar mais nada é uma sessão de `su` "
            "— que usa o root que **já** está instalado."
        )
    else:
        resposta = (
            "Não. Root sem reiniciar, sem apagar e sem quebrar exige `adb root`, e o `adbd` "
            "deste aparelho recusa em build de produção. As outras formas de root temporário "
            "(su emprestado, Magisk sem persistência) só existem **depois** de destravar o "
            "bootloader — e destravar apaga o aparelho e quebra OTA, banco, carteira e DRM. "
            "O que existe agora, sem root e sem quebrar nada, é o **privilégio de shell do "
            "ADB** — abaixo de root, e a lista do que ele não alcança está aqui do lado."
        )

    return {
        "resposta": resposta,
        # `true` só quando existe root que atende às TRÊS condições **e ainda
        # não foi obtido**. Num aparelho que já tem root o custo já foi pago no
        # passado (bootloader destravado, aparelho apagado): responder “sim”
        # ali seria esconder a conta atrás do resultado.
        "atende_as_tres": bool(root_temporario) and not tem_root,
        "caminhos": tabela,
        "sem_root_agora": privilegio,
    }


def _root_temporario(
    props: dict[str, Any],
    adbd_depuravel: bool,
    root_temporario: bool,
    tem_root: bool,
) -> dict[str, Any]:
    """“Podemos usar root temporário?” — respondido pelo aparelho, não por opinião.

    Existem **três coisas diferentes** chamadas de “root temporário”, e só uma
    delas é sequer possível sem destravar o bootloader:

    **1. `adb root`** — reinicia o `adbd` como root. Dura até reiniciar o
    aparelho, **não apaga nada**, não mexe no bootloader. É o “temporário” de
    verdade. Funciona só quando o `adbd` é depurável (`ro.debuggable=1`, build
    `userdebug`/`eng`). Num aparelho de fábrica o comando responde
    *“adbd cannot run as root in production builds”* — não é falta de vontade
    do JARVIS, é o `adbd` que se recusa.

    **2. Root que “não persiste”** — instalar Magisk sem o módulo de persistência.
    Continua sendo root de verdade: exige bootloader destravado, e destravar
    **apaga o aparelho**. Isso não é temporário pela porta da frente.

    **3. Root só desta sessão do `su`** — um app pede `su` uma vez, o Magisk
    empresta por N minutos. É temporário **para o app**, mas o root instalado no
    aparelho é permanente, com os mesmos riscos do item 2.

    O JARVIS não executa 1, 2 nem 3: o degrau 3 continua fora por escolha. O que
    esta função faz é dizer **qual dos três o seu aparelho aceitaria** — para a
    resposta não ser um “não” indiferente.
    """
    tags = str(props.get("ro.build.tags", "")).strip()
    tipo = str(props.get("ro.build.type", "")).strip()
    estado_boot = str(props.get("ro.boot.verifiedbootstate", "")).strip().lower()

    if tem_root:
        return {
            "possivel": True,
            "qual": "já tem root",
            "resumo": (
                "Este aparelho já está com root. O JARVIS continua não usando: a mesma porta "
                "que lê a sua conversa lê a senha do seu banco."
            ),
            "precisa_destravar": False,
            "apaga_o_aparelho": False,
        }

    if root_temporario:
        return {
            "possivel": True,
            "qual": "adb root (temporário de verdade)",
            "resumo": (
                f"Este aparelho aceita `adb root`: é build `{tipo}` com `adbd` depurável. "
                "Dura até reiniciar, não apaga nada e não mexe no bootloader — mas o JARVIS "
                "não roda esse comando: root é a linha que o projeto não cruza, em nenhuma "
                "forma. O que muda é o passivo: aqui ele seria reversível."
            ),
            "precisa_destravar": False,
            "apaga_o_aparelho": False,
        }

    if adbd_depuravel:
        return {
            "possivel": False,
            "qual": "nenhum sem destravar",
            "resumo": (
                "O `adbd` é depurável, mas o build não é `userdebug`/`eng`: o `adb root` "
                "provavelmente responde “cannot run as root in production builds”. Só root "
                "instalado (Magisk) resolveria — e isso exige destravar o bootloader."
            ),
            "precisa_destravar": True,
            "apaga_o_aparelho": True,
        }

    return {
        "possivel": False,
        "qual": "nenhum sem destravar o bootloader",
        "resumo": (
            f"Este aparelho é build `{tags or 'user'}` com `adbd` não depurável "
            "(`ro.debuggable=0`): `adb root` responde “adbd cannot run as root in production "
            "builds”. O único root possível aqui é o instalado (Magisk), que exige destravar "
            "o bootloader — e destravar **apaga o aparelho inteiro**, quebra OTA, banco e "
            "carteira. Não existe root temporário por outro caminho neste aparelho."
        ),
        "precisa_destravar": True,
        "apaga_o_aparelho": True,
        "estado_bootloader": estado_boot or "não publicado",
    }


def controle(*, aparelho: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mede o degrau em que o aparelho está e diz o que falta para o próximo.

    `aparelho` é o dicionário de propriedades já lido (ou vazio). Nada é
    executado aqui: a função só interpreta o que `anatomia` já mediu.
    """
    props = aparelho or {}
    adb_ligado = celular.ligado() and bool(celular.ferramentas().get("adb"))
    autorizado = bool(props.get("ro.product.model"))

    # 0.92.7 — três correções que a pergunta “podemos usar root temporário”
    # expôs no próprio mapa:
    #
    # 1. o degrau 2 era decidido por `ro.debuggable == "1"`, que é **build de
    #    depuração** (aparelho de fábrica/teste), não ADB pela rede. O degrau
    #    certo é a porta 5555 aberta depois de `adb tcpip 5555`;
    # 2. `destravado` só olhava `verifiedbootstate` — uma propriedade que a
    #    rota nunca lia e que, ausente, virava “não destravado” sempre;
    # 3. root **temporário** (`adb root`) não era sequer considerado. Ele é
    #    real, dura até reiniciar, e não apaga nada — mas o `adbd` do aparelho
    #    do dono é `user`, então nem chega a valer. O mapa passa a dizer isso.
    estado_boot = str(props.get("ro.boot.verifiedbootstate", "")).strip().lower()
    # `orange` = destravado; `green` = travado e verificado; `yellow` = destravado
    # com chave própria. Sem a propriedade, cai no `flash.locked` (1 = travado).
    if estado_boot:
        destravado = estado_boot in {"orange", "yellow"}
    else:
        destravado = str(props.get("ro.boot.flash.locked", "")).strip() == "0"
    bootloader = str(props.get("ro.bootloader", "")).strip()

    binario_root = bool(str(props.get("_root_binario", "")).strip())
    tem_root = str(props.get("ro.build.tags", "")).strip() == "test-keys" or binario_root

    # `adb root` só funciona quando o `adbd` é depurável. Não é o caso de um
    # aparelho de fábrica (`ro.debuggable = 0`) — e nesse caso a resposta honesta
    # é “não dá”, não “tente”.
    adbd_depuravel = str(props.get("ro.debuggable", "")).strip() == "1"
    root_temporario = adbd_depuravel and str(props.get("ro.build.type", "")).strip() in {"userdebug", "eng"}
    porta_rede = str(props.get("service.adb.tcp.port", "")).strip()

    degrau = 0
    if adb_ligado and autorizado:
        degrau = 1
    if adb_ligado and autorizado and porta_rede not in {"", "-1", "0"}:
        degrau = 2

    return {
        "ok": True,
        "degrau_atual": degrau,
        "degrau_maximo_jarvis": 2,
        "resumo": (
            "Com o que você tem agora, o JARVIS chega ao degrau 1: lê tudo o que o Android "
            "publica, espelha a tela, manda toque e copia as pastas de mídia. O degrau 2 (sem "
            "cabo, pela rede) é o mais alto que ele faz. Root e flash ficam fora por escolha."
            if degrau >= 1
            else "Sem a Depuração USB ligada e o “Permitir” aceito, o JARVIS fica no degrau 0 — "
            "só vê que o cabo está conectado."
        ),
        "aparelho": {
            "modelo": props.get("ro.product.model", ""),
            "bootloader": bootloader,
            "verified_boot": props.get("ro.boot.verifiedbootstate", ""),
            "build": props.get("ro.build.tags", ""),
            "destravado": destravado,
            "root": tem_root,
            "adbd_depuravel": adbd_depuravel,
            "root_temporario": root_temporario,
            "porta_adb_rede": porta_rede,
        },
        # A resposta para “podemos usar root temporário?”, medida no aparelho:
        # não é “sim” nem “não” genérico — é o que o `adbd` deste aparelho aceita.
        "root_temporario": {
            **_root_temporario(props, adbd_depuravel, root_temporario, tem_root),
            **_root_sem_reiniciar(
                props,
                adbd_depuravel=adbd_depuravel,
                root_temporario=root_temporario,
                tem_root=tem_root,
            ),
        },
        "degraus": [
            {
                **degrau_item,
                "alcancado": degrau_item["degrau"] <= degrau,
                "jarvis_faz": bool(degrau_item["jarvis_faz"]),
            }
            for degrau_item in CONTROLE
        ],
        "o_que_o_jarvis_faz_com_esse_acesso": (
            "Com o degrau 1: lê (anatomia, scanner, varredura), espelha a tela, manda toque e "
            "tecla, instala/remove app que você mandar (com confirmação), copia DCIM, Pictures, "
            "Download, Documents, WhatsApp e Telegram."
        ),
        "o_que_nao_faz_e_por_que": [
            "Não usa root: a mesma porta lê a sua conversa e a sua senha de banco.",
            "Não desbloqueia bootloader nem flasheia: o desbloqueio apaga o aparelho e o flash pode matá-lo.",
            "Não procura falha de segurança: isso quebra a proteção de um aparelho que não é o dele.",
        ],
    }
