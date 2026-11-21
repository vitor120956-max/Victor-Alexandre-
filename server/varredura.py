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
COMANDOS: tuple[tuple[str, ...], ...] = (
    ("shell", "ls", "-la", "/"),
    ("shell", "ls", "-la", "/storage/emulated/0"),
    ("shell", "ls", "-la", "/sdcard"),
    ("shell", "ls", "-la", "/system"),
    ("shell", "ls", "-la", "/vendor"),
    ("shell", "ls", "-la", "/data/app"),
    ("shell", "df", "-h"),
    ("shell", "cat", "/proc/partitions"),
    ("shell", "dumpsys", "meminfo"),
    ("shell", "dumpsys", "cpuinfo"),
    ("shell", "ps", "-A", "-o", "PID,RSS,NAME"),
    ("shell", "pm", "list", "packages", "-s"),
)

_PALAVRAS_PROIBIDAS = {
    "install", "uninstall", "push", "pull", "rm", "mv", "cp", "reboot",
    "wipe", "format", "set", "put", "delete", "clear", "keyevent", "input", "su",
}


def _auditar() -> None:
    for comando in COMANDOS:
        corpo = " ".join(comando)
        for palavra in corpo.split():
            assert palavra not in _PALAVRAS_PROIBIDAS, f"comando de efeito na varredura: {corpo}"


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


def montar(medido: dict[str, Any], *, agora: str = "") -> dict[str, Any]:
    """Junta a varredura com a anatomia e o scanner — sem repetir leitura."""
    saidas: dict[str, str] = medido.get("saidas", {})
    serial = medido.get("serial", "")

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
        _secao(
            "particoes",
            "Partições",
            [
                {"rotulo": p["nome"], "valor": p["tamanho"]}
                for p in ler_particoes(saidas.get("cat /proc/partitions", ""))
            ],
            nota="Nome e tamanho. Nenhuma partição é aberta.",
        ),
    ]

    memoria = ler_memoria_detalhada(saidas.get("dumpsys meminfo", ""))
    if memoria:
        secoes.append(_secao("memoria", "Memória do sistema", [{"rotulo": k, "valor": v} for k, v in memoria.items()]))

    processos = ler_processos(saidas.get("ps -A -o PID,RSS,NAME", ""))
    if processos:
        secoes.append(_secao(
            "processos",
            "Rodando agora (maiores primeiro)",
            [{"rotulo": f"{p['nome']}", "valor": f"{p['mb']} · pid {p['pid']}"} for p in processos],
            nota="É uma foto do instante da varredura — não um histórico.",
        ))

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

    if anatomia_relatorio.get("secoes"):
        secoes.append(_secao(
            "identidade",
            "O aparelho",
            [
                item
                for secao in anatomia_relatorio["secoes"]
                if secao["id"] in {"identidade", "bateria"}
                for item in secao["itens"][:6]
            ],
        ))

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

    problemas = saude.get("problemas", [])
    return {
        "ok": True,
        "alvo": "android",
        "serial": serial,
        "titulo": anatomia_relatorio.get("titulo") or serial,
        "lido_em": agora or _agora(),
        "veredito": frase + (
            f" O scanner achou {len(problemas)} problema(s); o principal é: {problemas[0]['titulo'].lower()}."
            if problemas else " Nenhum problema nas áreas que o scanner mede."
        ),
        "secoes": secoes,
        "problemas": problemas,
        "limitacoes": list(dict.fromkeys(list(medido.get("falhas", [])) + list(anatomia_relatorio.get("limitacoes", []))))[:12],
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
) -> dict[str, Any]:
    """A passagem completa: mede, junta e devolve um relatório só."""
    return montar(coletar(alvo, rodar=rodar), agora=agora)


def em_texto(relatorio: dict[str, Any]) -> str:
    linhas = ["", f"  {relatorio['titulo']}", f"  {relatorio['veredito']}", ""]
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


def controle(*, aparelho: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mede o degrau em que o aparelho está e diz o que falta para o próximo.

    `aparelho` é o dicionário de propriedades já lido (ou vazio). Nada é
    executado aqui: a função só interpreta o que `anatomia` já mediu.
    """
    props = aparelho or {}
    adb_ligado = celular.ligado() and bool(celular.ferramentas().get("adb"))
    autorizado = bool(props.get("ro.product.model"))
    tem_root = str(props.get("ro.build.tags", "")).strip() == "test-keys" or bool(
        str(props.get("_root_binario", "")).strip()
    )
    bootloader = str(props.get("ro.bootloader", "")).strip()
    destravavel = str(props.get("ro.boot.verifiedbootstate", "")).strip() in {"orange", "yellow"}

    degrau = 0
    if adb_ligado and autorizado:
        degrau = 1
    if adb_ligado and autorizado and props.get("ro.debuggable") == "1":
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
            "destravado": destravavel,
            "root": tem_root,
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
