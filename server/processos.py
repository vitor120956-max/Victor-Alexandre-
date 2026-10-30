"""O que está rodando no PC — e o que não precisa estar.

A pergunta que gerou isto é literal: *“no gerenciador de tarefas tem algumas
coisas que estão abertas e não precisam, tipo o nvidia container”*. A resposta
útil não é “pode fechar” nem “não mexa”: é dizer **o que cada processo é**, **o
que se perde se ele parar**, **como parar agora** e **como desfazer**.

Três grupos, e a diferença entre eles é o que evita estrago:

- **essencial** — núcleo do Windows e shell. Fechar não “libera memória”: derruba
  sessão, som, rede ou a área de trabalho. Aqui a resposta é *não mexa*, e o
  relatório diz por quê em uma linha.
- **do driver / da máquina** — o caso do **NVIDIA Container**: não é vírus, não
  é telemetria escondida de terceiro; é peça do pacote de driver da NVIDIA que
  roda o painel de controle, o ShadowPlay e as verificações de atualização. Parar
  **não melhora a imagem nem o FPS** — devolve RAM (uns 60 a 150 MB) e tira
  recursos que você talvez nem use. É reversível, e o caminho está escrito.
- **sobra** — atualizador que só serve para se atualizar, assistente que ninguém
  pediu, overlay de jogo, aplicativo de loja que abre sozinho. Este é o grupo em
  que fechar é ganho limpo.

Regra do módulo: **ele não mata nada**. Só lê a lista de processos e devolve o
diagnóstico com o comando exato — quem decide e quem executa é você, na frente
da máquina. Fechar processo alheio sem aviso é o tipo de esperteza que quebra
sessão de trabalho no meio.

No Windows ele lê com `Get-Process` (bytes, sem depender de formato de número) e
a lista de inicialização com `Win32_StartupCommand`. Fora do Windows, devolve um
relatório vazio com o motivo dito.
"""
from __future__ import annotations

import json
import platform
import subprocess
from typing import Any

LIMITE_LEITURA = 30

# ---------------------------------------------------------------------------
# Catálogo: nome (sem .exe, minúsculo) -> o que é, o que acontece se parar.
#
# `veredito`:
#   essencial  -> nunca fechar; o texto diz o que cai junto
#   driver     -> peça de driver; fechar devolve RAM e tira recurso do fabricante
#   sobra      -> atualizador, assistente, overlay ou app de loja sem uso
#   cuidado    -> pode ser útil; depende de você estar usando agora
#   proprio    -> o próprio JARVIS
# ---------------------------------------------------------------------------

CATALOGO: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------- núcleo
    "system": {"nome": "System", "veredito": "essencial", "o_que_e": "processo do núcleo do Windows",
               "se_parar": "o Windows não sobrevive a isso", "risco": "alto"},
    "idle": {"nome": "System Idle", "veredito": "essencial", "o_que_e": "tempo ocioso da CPU",
             "se_parar": "não existe o que parar: é a CPU sem trabalho", "risco": "alto"},
    "registry": {"nome": "Registry", "veredito": "essencial", "o_que_e": "cache do registro do Windows",
                 "se_parar": "travamentos e reinício forçado", "risco": "alto"},
    "smss": {"nome": "Session Manager", "veredito": "essencial", "o_que_e": "cria sessões do Windows",
             "se_parar": "o sistema reinicia sozinho", "risco": "alto"},
    "csrss": {"nome": "Client Server Runtime", "veredito": "essencial", "o_que_e": "subsistema do modo usuário",
              "se_parar": "tela azul", "risco": "alto"},
    "wininit": {"nome": "Windows Init", "veredito": "essencial", "o_que_e": "inicialização do Windows",
                "se_parar": "o sistema reinicia sozinho", "risco": "alto"},
    "winlogon": {"nome": "Windows Logon", "veredito": "essencial", "o_que_e": "login e bloqueio de tela",
                 "se_parar": "a sessão cai", "risco": "alto"},
    "services": {"nome": "Services", "veredito": "essencial", "o_que_e": "gerenciador de serviços",
                 "se_parar": "quase tudo que é serviço para de responder", "risco": "alto"},
    "lsass": {"nome": "Local Security Authority", "veredito": "essencial", "o_que_e": "autenticação e senhas",
              "se_parar": "o Windows reinicia imediatamente (e é tratado como ataque)", "risco": "alto"},
    "svchost": {"nome": "Service Host", "veredito": "essencial", "o_que_e": "hospeda dezenas de serviços do sistema",
                "se_parar": "som, rede, atualização ou área de trabalho param, conforme o serviço", "risco": "alto"},
    "explorer": {"nome": "Explorer", "veredito": "essencial", "o_que_e": "área de trabalho, barra de tarefas e pastas",
                 "se_parar": "a barra e os ícones somem (voltam ao reiniciar o Explorer)", "risco": "alto"},
    "dwm": {"nome": "Desktop Window Manager", "veredito": "essencial", "o_que_e": "desenho das janelas",
            "se_parar": "a tela pisca e o Windows reinicia o processo", "risco": "alto"},
    "fontdrvhost": {"nome": "Font Driver Host", "veredito": "essencial", "o_que_e": "renderização das fontes",
                    "se_parar": "texto some ou embaralha", "risco": "alto"},
    "sihost": {"nome": "Shell Infrastructure", "veredito": "essencial", "o_que_e": "infraestrutura da interface",
               "se_parar": "menu iniciar e notificações falham", "risco": "médio"},
    "ctfmon": {"nome": "Text Input / idioma", "veredito": "essencial", "o_que_e": "entrada de texto e idioma do teclado",
               "se_parar": "acentos e troca de idioma param (volta ao reiniciar)", "risco": "baixo"},
    "conhost": {"nome": "Console Host", "veredito": "essencial", "o_que_e": "janelas de console (cmd)",
                "se_parar": "fecha a janela de terminal que ele hospeda", "risco": "baixo"},
    "taskmgr": {"nome": "Gerenciador de Tarefas", "veredito": "essencial", "o_que_e": "a janela que você está olhando",
                "se_parar": "ela fecha. Só isso", "risco": "baixo"},

    # ------------------------------------------------------------- NVIDIA
    "nvcontainer": {
        "nome": "NVIDIA Container",
        "veredito": "driver",
        "o_que_e": "peça do pacote de driver da NVIDIA: hospeda o painel de controle, o ShadowPlay e a checagem de atualização do driver",
        "se_parar": "não desenha nada — quem desenha é o driver de vídeo, que continua funcionando com imagem e FPS iguais. Perde o painel da NVIDIA, o ShadowPlay/gravação e a checagem de driver. Volta sozinho no próximo boot ou quando o painel é aberto",
        "como_parar": 'taskkill /IM nvcontainer.exe /F',
        "como_desfazer": 'sc config NvContainerLocalSystem start= auto  &&  net start NvContainerLocalSystem',
        "ganho": "60 a 150 MB de RAM",
        "risco": "baixo",
    },
    "nvdisplay.container": {
        "nome": "NVIDIA Display Container",
        "veredito": "driver",
        "o_que_e": "container do driver de vídeo (painel NVIDIA e ajustes de cor/escala)",
        "se_parar": "o Windows reinicia o processo na hora; ajustes de cor e o painel ficam indisponíveis por um tempo",
        "como_parar": "não vale a pena: ele se recria",
        "como_desfazer": "nada a desfazer — ele mesmo volta",
        "ganho": "pouco (ele reinicia)",
        "risco": "médio",
    },
    "nvsphelper64": {
        "nome": "NVIDIA ShadowPlay Helper",
        "veredito": "sobra",
        "o_que_e": "auxiliar de captura de vídeo do GeForce Experience",
        "se_parar": "nada, se você não grava a tela pelo GeForce",
        "como_parar": 'taskkill /IM nvsphelper64.exe /F',
        "como_desfazer": "abrir o GeForce Experience uma vez (ele recria)",
        "ganho": "30 a 80 MB de RAM",
        "risco": "baixo",
    },
    "nvtelemetrycontainer": {
        "nome": "NVIDIA Telemetry",
        "veredito": "sobra",
        "o_que_e": "coleta de estatísticas de uso da NVIDIA",
        "se_parar": "nada visível; a NVIDIA deixa de receber telemetria",
        "como_parar": 'taskkill /IM nvtelemetrycontainer.exe /F',
        "como_desfazer": 'sc config NvTelemetryContainer start= auto  &&  net start NvTelemetryContainer',
        "ganho": "20 a 60 MB de RAM",
        "risco": "baixo",
    },
    "nvidia web helper": {
        "nome": "NVIDIA Web Helper",
        "veredito": "sobra",
        "o_que_e": "auxiliar do GeForce Experience para conteúdo web",
        "se_parar": "nada, se você não usa o GeForce Experience",
        "como_parar": 'taskkill /IM "nvidia web helper.exe" /F',
        "como_desfazer": "abrir o GeForce Experience",
        "ganho": "20 a 60 MB",
        "risco": "baixo",
    },

    # ------------------------------------------------------------- sobra
    "googlecrashhandler": {
        "nome": "Google Crash Handler",
        "veredito": "sobra",
        "o_que_e": "relatório de falha dos programas do Google instalados no PC",
        "se_parar": "nada, a não ser que um programa do Google caia e você queira o relatório",
        "como_parar": 'taskkill /IM GoogleCrashHandler.exe /F',
        "como_desfazer": "abre sozinho no próximo boot",
        "ganho": "10 a 40 MB",
        "risco": "baixo",
    },
    "googlecrashhandler64": {
        "nome": "Google Crash Handler (64)", "veredito": "sobra",
        "o_que_e": "o mesmo, versão 64 bits", "se_parar": "nada",
        "como_parar": 'taskkill /IM GoogleCrashHandler64.exe /F', "como_desfazer": "volta no próximo boot",
        "ganho": "10 a 40 MB", "risco": "baixo",
    },
    "steamwebhelper": {
        "nome": "Steam Web Helper",
        "veredito": "sobra",
        "o_que_e": "a loja e a interface da Steam, desenhadas em navegador",
        "se_parar": "a janela da Steam perde a loja (jogo já aberto continua)",
        "como_parar": "fechar a Steam pela bandeja; ou Configurações > Interface > desligar navegador interno",
        "como_desfazer": "abrir a Steam de novo",
        "ganho": "150 a 400 MB",
        "risco": "baixo",
    },
    "searchui": {
        "nome": "Search UI (Cortana / busca)",
        "veredito": "sobra",
        "o_que_e": "a caixa de busca do Windows com a Cortana",
        "se_parar": "a busca do menu iniciar fica mais lenta; a Cortana não responde",
        "como_parar": "Configurações > Privacidade > Fala/Entrada: desligar a Cortana",
        "como_desfazer": "religar a mesma opção",
        "ganho": "40 a 120 MB",
        "risco": "baixo",
    },
    "yourphone": {
        "nome": "Seu Telefone (Your Phone)",
        "veredito": "sobra",
        "o_que_e": "espelhamento de celular da Microsoft (e ele exige um celular compatível)",
        "se_parar": "nada, se você não usa o Seu Telefone",
        "como_parar": "Configurações > Aplicativos > desinstalar o Seu Telefone",
        "como_desfazer": "reinstalar pela loja, se precisar",
        "ganho": "50 a 150 MB",
        "risco": "baixo",
    },
    "gamebar": {
        "nome": "Xbox Game Bar",
        "veredito": "sobra",
        "o_que_e": "barra de jogos do Windows (gravação e sobreposição)",
        "se_parar": "Win+G deixa de abrir a barra",
        "como_parar": "Configurações > Jogos > Barra de jogos: desligar",
        "como_desfazer": "religar a mesma opção",
        "ganho": "30 a 100 MB",
        "risco": "baixo",
    },
    "onedrive": {
        "nome": "OneDrive",
        "veredito": "sobra",
        "o_que_e": "sincronização da pasta OneDrive",
        "se_parar": "arquivos param de sincronizar (o que está no PC continua lá)",
        "como_parar": "clique direito no ícone da nuvem > Configurações > desligar sincronização",
        "como_desfazer": "religar a mesma opção",
        "ganho": "80 a 250 MB",
        "risco": "médio",
    },
    "node": {"nome": "Node.js", "veredito": "proprio",
             "o_que_e": "a interface do JARVIS (Vite) roda em Node", "se_parar": "a tela do JARVIS cai",
             "risco": "médio"},
    "python": {"nome": "Python (API do JARVIS)", "veredito": "proprio",
               "o_que_e": "a API do JARVIS", "se_parar": "as skills param de responder",
               "risco": "médio"},
    "pythonw": {"nome": "Python (API do JARVIS)", "veredito": "proprio",
                "o_que_e": "a API do JARVIS", "se_parar": "as skills param de responder", "risco": "médio"},

    # ------------------------------------------------------------- cuidado
    "chrome": {"nome": "Google Chrome", "veredito": "cuidado",
               "o_que_e": "navegador (cada aba pode virar um processo)",
               "se_parar": "fecha as abas abertas", "ganho": "100 MB a 1 GB, depende das abas", "risco": "médio"},
    "msedge": {"nome": "Microsoft Edge", "veredito": "cuidado",
               "o_que_e": "navegador da Microsoft (abre sozinho se for o padrão)",
               "se_parar": "fecha as abas abertas", "ganho": "100 MB a 800 MB", "risco": "médio"},
    "msedgewebview2": {"nome": "Edge WebView2", "veredito": "cuidado",
                       "o_que_e": "motor do Edge usado por outros programas (WhatsApp Web, Teams)",
                       "se_parar": "o programa que o usa perde a janela", "ganho": "50 a 300 MB", "risco": "médio"},
    "searchindexer": {"nome": "Windows Search (indexador)", "veredito": "cuidado",
                      "o_que_e": "indexa arquivos para a busca ser rápida",
                      "se_parar": "a busca fica lenta; o índice é refeito depois",
                      "como_parar": "Serviços > Windows Search > Parar",
                      "como_desfazer": "Serviços > Windows Search > Iniciar",
                      "ganho": "30 a 200 MB (e alivia o disco)", "risco": "médio"},
    "antimalware service executable": {"nome": "Microsoft Defender", "veredito": "cuidado",
                                       "o_que_e": "antivírus do Windows",
                                       "se_parar": "a proteção em tempo real cai e o Windows religa sozinho",
                                       "ganho": "100 a 300 MB", "risco": "alto"},
    "audiodg": {"nome": "Audio Device Graph", "veredito": "essencial",
                "o_que_e": "processamento de áudio", "se_parar": "som para e pode falhar até reiniciar",
                "risco": "médio"},
}

# De onde vem cada enfeite e qual é o comando que impede voltar no boot.
INICIO_DICA = {
    "nvcontainer": "Serviços > NvContainerLocalSystem > Inicialização: Manual",
    "nvtelemetrycontainer": "Serviços > NvTelemetryContainer > Inicialização: Desabilitado",
    "googlecrashhandler": "Agendador de Tarefas > GoogleUpdate > desabilitar",
    "steamwebhelper": "Steam > Configurações > Interface > desligar navegador interno",
    "searchui": "Configurações > Privacidade > Fala: desligar Cortana",
    "onedrive": "OneDrive > Configurações > desligar início automático",
    "gamebar": "Configurações > Jogos > Barra de jogos > desligar",
    "yourphone": "Configurações > Aplicativos > desinstalar",
}


class ProcessosError(ValueError):
    """Erro esperado do diagnóstico, seguro para o usuário."""


# --------------------------------------------------------------------- leitura


def _powershell(script: str, timeout: int = 25) -> str:
    """Roda um script PowerShell fixo e devolve a saída. Sem shell, sem entrada livre."""
    concluido = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    return concluido.stdout or ""


def coletar(*, limite: int = 400) -> list[dict[str, Any]]:
    """Lista os processos com memória em MB. Vazio fora do Windows, com motivo."""
    if platform.system() != "Windows":
        return []
    script = (
        "Get-Process | Sort-Object -Property WS -Descending | "
        "Select-Object -First {n} -Property ProcessName,WS,Id | ConvertTo-Json -Compress"
    ).format(n=int(limite))
    saida = _powershell(script).strip()
    if not saida:
        return []
    try:
        dados = json.loads(saida)
    except json.JSONDecodeError as exc:
        raise ProcessosError("Não consegui ler a lista de processos do Windows.") from exc
    if isinstance(dados, dict):
        dados = [dados]
    linhas = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("ProcessName") or "").strip()
        if not nome:
            continue
        linhas.append(
            {
                "nome": nome,
                "pid": item.get("Id"),
                "memoria_mb": round(float(item.get("WS") or 0) / (1024 * 1024), 1),
            }
        )
    return linhas


def inicio_automatico() -> list[dict[str, str]]:
    """O que abre com o Windows. Só leitura; não desabilita nada."""
    if platform.system() != "Windows":
        return []
    script = (
        "Get-CimInstance Win32_StartupCommand | "
        "Select-Object -Property Name,Command,Location | ConvertTo-Json -Compress"
    )
    saida = _powershell(script).strip()
    if not saida:
        return []
    try:
        dados = json.loads(saida)
    except json.JSONDecodeError:
        return []
    if isinstance(dados, dict):
        dados = [dados]
    itens = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        itens.append(
            {
                "nome": str(item.get("Name") or "").strip(),
                "comando": str(item.get("Command") or "").strip()[:300],
                "onde": str(item.get("Location") or "").strip()[:60],
            }
        )
    return itens


# --------------------------------------------------------------------- análise


def _chave(nome: str) -> str:
    """Normaliza o nome do processo: sem caminho, sem .exe, minúsculo."""
    base = str(nome or "").split("\\")[-1].split("/")[-1].strip()
    if base.lower().endswith(".exe"):
        base = base[:-4]
    return base.strip().lower()


def conhecer(nome: str) -> dict[str, Any] | None:
    """O que o catálogo sabe sobre este processo — ou None, sem inventar."""
    chave = _chave(nome)
    ficha = CATALOGO.get(chave)
    if not ficha:
        # "nvcontainer#0", "chrome (3)": o Windows repete nome com sufixo.
        for candidato in (chave.split("#")[0], chave.split(" (")[0]):
            ficha = CATALOGO.get(candidato)
            if ficha:
                break
    if not ficha:
        return None
    saida = dict(ficha)
    saida["processo"] = chave
    saida["inicio"] = INICIO_DICA.get(chave, "")
    return saida


VEREDITO_ORDEM = {"essencial": 0, "proprio": 1, "cuidado": 2, "driver": 3, "sobra": 4}
VEREDITO_ROTULO = {
    "essencial": "Não mexa",
    "proprio": "Faz parte do JARVIS",
    "cuidado": "Depende do que você está usando",
    "driver": "Peça de driver (a NVIDIA)",
    "sobra": "Sobra: dá para desligar",
}


def analisar(linhas: list[dict[str, Any]]) -> dict[str, Any]:
    """Classifica uma lista de processos. Função pura — é o que os testes exercitam."""
    grupos: dict[str, list[dict[str, Any]]] = {chave: [] for chave in VEREDITO_ROTULO}
    desconhecidos: list[dict[str, Any]] = []
    total_mb = 0.0

    for linha in linhas:
        nome = str(linha.get("nome") or "").strip()
        if not nome:
            continue
        mb = float(linha.get("memoria_mb") or 0)
        total_mb += mb
        ficha = conhecer(nome)
        if not ficha:
            desconhecidos.append({"nome": nome, "memoria_mb": mb, "pid": linha.get("pid")})
            continue
        grupos[ficha["veredito"]].append(
            {
                "nome": ficha["nome"],
                "processo": ficha["processo"],
                "memoria_mb": mb,
                "pid": linha.get("pid"),
                "o_que_e": ficha.get("o_que_e", ""),
                "se_parar": ficha.get("se_parar", ""),
                "como_parar": ficha.get("como_parar", ""),
                "como_desfazer": ficha.get("como_desfazer", ""),
                "inicio": ficha.get("inicio", ""),
                "ganho": ficha.get("ganho", ""),
                "risco": ficha.get("risco", ""),
            }
        )

    for chave in grupos:
        grupos[chave].sort(key=lambda item: -item["memoria_mb"])

    ganho = sum(item["memoria_mb"] for item in grupos["sobra"])
    ganho_driver = sum(item["memoria_mb"] for item in grupos["driver"])
    maiores_sobras = grupos["sobra"][:3]

    return {
        "processos_lidos": len(linhas),
        "memoria_total_mb": round(total_mb, 1),
        "grupos": grupos,
        "rotulos": VEREDITO_ROTULO,
        "desconhecidos": sorted(desconhecidos, key=lambda item: -item["memoria_mb"])[:15],
        "desconhecidos_total": len(desconhecidos),
        "ganho_sobra_mb": round(ganho, 1),
        "ganho_driver_mb": round(ganho_driver, 1),
        "ganho_total_mb": round(ganho + ganho_driver, 1),
        "resumo": _resumo(ganho, ganho_driver, maiores_sobras, total_mb),
        "aviso": (
            "Nada foi fechado: este relatório só leu a lista. Para parar algo, use o "
            "comando da própria linha; para não voltar no boot, use o campo “início”."
        ),
    }


def _resumo(ganho: float, ganho_driver: float, maiores: list[dict[str, Any]], total: float) -> str:
    if not total:
        return "Nenhum processo lido."
    partes = [f"{round(total)} MB em processos agora."]
    if ganho >= 50:
        nomes = ", ".join(item["nome"] for item in maiores) or "as sobras"
        partes.append(
            f"Dá para devolver cerca de {round(ganho)} MB fechando sobras — "
            f"os maiores são {nomes}."
        )
    elif ganho > 0:
        partes.append(f"Só {round(ganho)} MB em sobras: o ganho grande não está aqui.")
    if ganho_driver >= 20:
        partes.append(
            f"O driver da NVIDIA ocupa {round(ganho_driver)} MB; desligar é seguro, mas tira "
            "painel, ShadowPlay e checagem de driver."
        )
    return " ".join(partes)


def relatorio() -> dict[str, Any]:
    """Junta leitura e análise. Fora do Windows, explica em vez de fingir."""
    sistema = platform.system()
    if sistema != "Windows":
        return {
            "sistema": sistema,
            "lido": False,
            "motivo": "Esta leitura é do Windows; fora dele não há o que listar.",
            "processos_lidos": 0,
            "grupos": {chave: [] for chave in VEREDITO_ROTULO},
            "rotulos": VEREDITO_ROTULO,
            "desconhecidos": [],
            "desconhecidos_total": 0,
            "ganho_sobra_mb": 0,
            "ganho_driver_mb": 0,
            "ganho_total_mb": 0,
            "memoria_total_mb": 0,
            "resumo": "Rode no Windows para ver os processos desta máquina.",
            "aviso": "",
            "inicio": [],
        }
    linhas = coletar()
    dados = analisar(linhas)
    dados["sistema"] = sistema
    dados["lido"] = bool(linhas)
    dados["inicio"] = inicio_automatico()
    return dados


def nvidia() -> dict[str, Any]:
    """Só a resposta da pergunta original: e o NVIDIA Container?"""
    ficha = conhecer("nvcontainer") or {}
    return {
        "pergunta": "O NVIDIA Container precisa estar aberto?",
        "resposta": (
            "Não precisa para a imagem: ele não desenha nada. Ele serve ao painel da "
            "NVIDIA, ao ShadowPlay e à checagem de atualização do driver. Fechar não "
            "aumenta FPS nem melhora a imagem — devolve RAM."
        ),
        "ficha": ficha,
        "como_parar": ficha.get("como_parar", ""),
        "como_voltar": ficha.get("como_desfazer", ""),
        "para_nao_voltar": INICIO_DICA.get("nvcontainer", ""),
    }


# --------------------------------------------------------------------- CLI


def _cli() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="O que está rodando no PC e o que não precisa.")
    parser.add_argument("--json", action="store_true", help="dados crus, para conferir")
    args = parser.parse_args()

    dados = relatorio()
    if args.json:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0

    print()
    print("  JARVIS - o que esta rodando e o que nao precisa")
    print()
    if not dados.get("lido"):
        print("  " + str(dados.get("resumo") or dados.get("motivo") or "Nada lido."))
        print()
        return 0

    print(f"  {dados['resumo']}")
    print()
    for chave in ("sobra", "driver", "proprio", "cuidado", "essencial"):
        itens = dados["grupos"].get(chave) or []
        if not itens:
            continue
        print(f"  {VEREDITO_ROTULO[chave].upper()}")
        for item in itens[:LIMITE_LEITURA]:
            memoria = f"{item['memoria_mb']:7.1f} MB"
            print(f"    {memoria}  {item['nome']}")
            if chave in ("sobra", "driver") and item.get("se_parar"):
                print(f"               parar: {item['se_parar']}")
            if chave in ("sobra", "driver") and item.get("como_parar"):
                print(f"               comando: {item['como_parar']}")
            if item.get("inicio"):
                print(f"               nao voltar no boot: {item['inicio']}")
        print()

    if dados["desconhecidos"]:
        print("  NAO CONHECO ESTES (nao vou opinar sem saber)")
        for item in dados["desconhecidos"][:10]:
            print(f"    {item['memoria_mb']:7.1f} MB  {item['nome']}")
        print()

    print("  " + dados["aviso"])
    print()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
