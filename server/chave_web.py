"""Achar, na página do provedor, o que cria e o que copia a chave (0.91.14).

Por que a lógica mora aqui e não no script: achar o botão numa árvore de
acessibilidade é regra, e regra se testa sem Chrome, sem Windows e sem tela. O
script `chave-no-navegador.py` só faz o que não dá para testar — ler e clicar.

## O limite honesto, medido antes de escrever isto

O OpenRouter mostra a chave **uma vez**, no instante em que ela é criada, e
nunca mais. A lista de chaves guarda só o prefixo mascarado. Não existe leitura
automática de chave existente — nem por este módulo, nem por nenhum outro; quem
promete isso está lendo outra coisa.

O que dá para automatizar é o **caminho de criar uma nova**:

    abrir a página → clicar em "Create Key" → dar um nome → criar
    → clicar em "Copy" → ler a área de transferência → gravar no .env

Cada uma dessas setas depende de a página publicar o botão na árvore de
acessibilidade. Isso **não foi medido no Chrome do usuário ainda** — e é por
isso que o primeiro modo do script é só leitura: ele diz o que existe antes de
qualquer clique.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

# Nomes de botão/link que interessam, em ordem de preferência. Acentos e
# maiúsculas não importam (a comparação normaliza).
PADROES_CRIAR = ("create key", "criar chave", "new key", "nova chave", "add key", "adicionar chave")
# O botão que **fecha** o diálogo de criação costuma ser só “Create”/“Criar”
# — mais curto que o “Create Key” da página. A 0.91.14 só conhecia o rótulo
# longo e travou no passo 3 com o diálogo aberto na frente: o dublê do teste
# mostrou isso antes do dono. “Created/at” não é botão, mas entra na conta; por
# isso o nome mais curto vem primeiro.
PADROES_CONFIRMAR = ("create", "criar", "confirmar", "confirm", "save", "salvar")
PADROES_COPIAR = ("copy", "copiar")
PADROES_NOME = ("key name", "nome da chave", "name", "nome")

# O que a página de chaves tem escrito, independentemente do idioma.
# Nada de `keys`/`chaves` sozinhos: qualquer página pode ter a palavra, e um
# falso positivo aqui faria o script clicar na página errada.
#
# 0.91.14 — `openrouter` saiu daqui. A tela de **login** do OpenRouter tem
# “OpenRouter” no título, e com essa marca o JARVIS achava que já estava na
# página de chaves, parava e pedia um botão que não existia. Marcas agora são as
# que só existem **depois** de entrar.
MARCAS_DA_PAGINA = ("api keys", "chaves de api", "new key", "nova chave", "create key", "criar chave")

# ---------------------------------------------------------------------------
# Onde estou? (0.91.14)
#
# Medido nas telas do dono: abrir openrouter.ai/keys sem sessão cai em
# “Sign In | OpenRouter”, com os botões GitHub / Google / Reddit; clicar no
# Google abre “Fazer login nas Contas do Google”, com a lista de contas; só
# depois da conta escolhida é que aparece “API keys” com o botão “New key”.
#
# São três páginas diferentes na mesma janela do Chrome. Sem saber em qual se
# está, qualquer clique é chute — e foi o que aconteceu.
# ---------------------------------------------------------------------------

ESTADO_CHAVES = "pagina de chaves"
ESTADO_LOGIN = "pagina de login"
ESTADO_GOOGLE = "escolha de conta do Google"
ESTADO_DESCONHECIDO = "pagina desconhecida"

PADROES_ENTRAR = ("sign in", "log in", "login", "entrar", "acessar", "fazer login")

# O botão do Google na tela de login do provedor.
PADROES_GOOGLE = ("google",)

# Marcas que só existem na tela de escolha de conta do Google.
_MARCAS_DO_GOOGLE = (
    "accounts.google.com",
    "contas do google",
    "escolha uma conta",
    "choose an account",
    "prosseguir para",
    "to continue to",
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento — a mesma forma de comparar do resto do projeto."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def _achatar(no: Any) -> list[dict[str, Any]]:
    """Percorre a árvore montada e devolve os nós com nome, em ordem."""
    if not isinstance(no, dict):
        return []
    itens = [no]
    for filho in no.get("filhos") or []:
        itens.extend(_achatar(filho))
    return itens


def elementos(arvore_montada: dict[str, Any]) -> list[dict[str, Any]]:
    """Todos os nós com nome — o que a página publica de legível."""
    raiz = arvore_montada.get("arvore")
    return [no for no in _achatar(raiz) if str(no.get("nome") or "").strip()]


def procurar(arvore_montada: dict[str, Any], padroes: tuple[str, ...]) -> list[dict[str, Any]]:
    """Nós cujo nome contém um dos padrões, do mais curto para o mais longo.

    Nome mais curto primeiro: "Copy" ganha de "Copy the key to the clipboard",
    porque o botão costuma ser o rótulo curto e o texto longo é o do vizinho.
    """
    alvos = [normalizar(p) for p in padroes]
    achados: list[dict[str, Any]] = []
    for no in elementos(arvore_montada):
        nome = normalizar(str(no.get("nome") or ""))
        if any(alvo in nome for alvo in alvos):
            achados.append(no)
    # O que dá para apertar vem antes do que só está escrito. Na página de
    # chaves existe o texto “Create and manage your API keys.”; sem esta ordem,
    # o passo do diálogo podia “clicar” num parágrafo e dizer que deu certo.
    achados.sort(key=lambda no: (0 if no.get("acionavel") else 1, len(normalizar(str(no.get("nome") or "")))))
    return achados


def texto_da_janela(arvore_montada: dict[str, Any], limite: int = 80) -> str:
    """Título + nomes dos primeiros elementos, normalizados. A “cara” da página."""
    texto = normalizar(str(arvore_montada.get("alvo") or ""))
    texto += " " + " ".join(
        normalizar(str(no.get("nome") or "")) for no in elementos(arvore_montada)[:limite]
    )
    return " ".join(texto.split())


def e_pagina_de_chaves(arvore_montada: dict[str, Any]) -> bool:
    """A janela lida parece a página de chaves do provedor?"""
    texto = texto_da_janela(arvore_montada)
    return any(marca in texto for marca in MARCAS_DA_PAGINA)


def contas_visiveis(arvore_montada: dict[str, Any]) -> list[dict[str, Any]]:
    """As contas listadas na tela de escolha do Google.

    Cada item: `nome` (o que está escrito), `email` e `no` (o nó, para clicar).
    Conta repetida aparece uma vez só — o Google repete o nome em mais de um nó.
    """
    vistas: list[dict[str, Any]] = []
    for no in elementos(arvore_montada):
        texto = str(no.get("nome") or "")
        achado = _EMAIL.search(texto)
        if not achado:
            continue
        email = achado.group(0)
        if any(item["email"].lower() == email.lower() for item in vistas):
            continue
        vistas.append({"nome": texto[:80], "email": email, "no": no})
    return vistas


def casar_conta(contas: list[dict[str, Any]], alvo: str) -> dict[str, Any] | None:
    """Qual conta é a pedida? `None` quando não dá para decidir sem chutar.

    Casa por pedaço do e-mail ou do nome, sem diferenciar maiúscula. Se o pedido
    casar com duas contas (por exemplo “vitor” em dois e-mails), também devolve
    `None`: escolher a conta errada é pior do que perguntar.
    """
    pedido = normalizar(alvo).strip()
    if not pedido:
        return None
    achadas = [
        conta
        for conta in contas
        if pedido in normalizar(str(conta.get("email") or ""))
        or pedido in normalizar(str(conta.get("nome") or ""))
    ]
    return achadas[0] if len(achadas) == 1 else None


def onde_estou(arvore_montada: dict[str, Any], conta: str = "") -> dict[str, Any]:
    """Em qual das três páginas esta janela está — e o que fazer daqui."""
    texto = texto_da_janela(arvore_montada)
    contas = contas_visiveis(arvore_montada)

    if any(marca in texto for marca in _MARCAS_DO_GOOGLE):
        escolhida = casar_conta(contas, conta) if conta else None
        return {
            "estado": ESTADO_GOOGLE,
            "contas": contas,
            "conta_escolhida": escolhida,
            "elementos": len(elementos(arvore_montada)),
        }
    if e_pagina_de_chaves(arvore_montada):
        return {"estado": ESTADO_CHAVES, "contas": contas, "conta_escolhida": None,
                "elementos": len(elementos(arvore_montada))}
    if any(marca in texto for marca in PADROES_ENTRAR):
        return {"estado": ESTADO_LOGIN, "contas": contas, "conta_escolhida": None,
                "elementos": len(elementos(arvore_montada))}
    return {"estado": ESTADO_DESCONHECIDO, "contas": contas, "conta_escolhida": None,
            "elementos": len(elementos(arvore_montada))}


def texto_do_estado(dados: dict[str, Any]) -> str:
    """“Onde estou” em uma linha, para a tela do dono."""
    estado = dados.get("estado") or ESTADO_DESCONHECIDO
    if estado == ESTADO_CHAVES:
        return "  onde estou: a página de chaves (essa é a certa)"
    if estado == ESTADO_LOGIN:
        return "  onde estou: a tela de login — preciso entrar pelo Google"
    if estado == ESTADO_GOOGLE:
        contas = dados.get("contas") or []
        lista = ", ".join(str(conta.get("email")) for conta in contas[:4]) or "(nenhuma conta visível)"
        return f"  onde estou: a escolha de conta do Google — {lista}"
    return "  onde estou: uma página que não reconheci"


def caixa_de(no: dict[str, Any] | None) -> list[int] | None:
    """A posição medida de um nó — é o que permite clicar com o mouse.

    Sem posição não existe clique físico: a leitura diz o nome, mas não onde o
    botão está na tela. Por isso o diagnóstico separa “achei” de “achei e sei
    onde fica”.
    """
    if not isinstance(no, dict):
        return None
    caixa = no.get("caixa")
    if isinstance(caixa, (list, tuple)) and len(caixa) == 4:
        valores = [int(valor) for valor in caixa]
        if valores[2] > 0 and valores[3] > 0:
            return valores
    return None


def diagnostico(arvore_montada: dict[str, Any]) -> dict[str, Any]:
    """O que existe na página agora — sem clique nenhum.

    É o modo de estreia do script: primeiro medir, depois agir. Se o Chrome não
    publicar o botão, o diagnóstico diz isso e ninguém perde tempo clicando no
    vazio.
    """
    criar = procurar(arvore_montada, PADROES_CRIAR)
    copiar = procurar(arvore_montada, PADROES_COPIAR)
    nome = procurar(arvore_montada, PADROES_NOME)
    total = len(elementos(arvore_montada))

    def resumo(lista: list[dict[str, Any]], limite: int = 3) -> list[str]:
        return [str(no.get("nome") or "")[:60] for no in lista[:limite]]

    posicoes = {
        "criar": caixa_de(criar[0]) if criar else None,
        "copiar": caixa_de(copiar[0]) if copiar else None,
        "nome": caixa_de(nome[0]) if nome else None,
    }
    return {
        "pagina_de_chaves": e_pagina_de_chaves(arvore_montada),
        "elementos_com_nome": total,
        "criar": resumo(criar),
        "copiar": resumo(copiar),
        "nome": resumo(nome),
        "pode_criar": bool(criar),
        "pode_copiar": bool(copiar),
        "posicoes": posicoes,
        "pode_clicar_com_mouse": bool(posicoes["criar"] or posicoes["copiar"]),
        "fonte": str(arvore_montada.get("fonte") or ""),
        "alvo": str(arvore_montada.get("alvo") or ""),
    }


def texto_do_diagnostico(dados: dict[str, Any]) -> str:
    """O diagnóstico em português, com o que fazer em cada caso."""
    linhas = [f"  janela: {dados['alvo'] or '?'}   (fonte: {dados['fonte'] or '?'})"]
    if not dados["elementos_com_nome"]:
        linhas.append(
            "  NADA: esta janela não publicou nenhum elemento com nome. O Chrome pode estar "
            "com a página dentro de uma janela filha — feche outras abas e rode de novo."
        )
        return "\n".join(linhas)
    if not dados["pagina_de_chaves"]:
        linhas.append("  Esta não parece a página de chaves. Abra openrouter.ai/keys e rode de novo.")
    linhas.append(f"  elementos com nome: {dados['elementos_com_nome']}")
    for rotulo, chave in (("botão de criar", "criar"), ("botão de copiar", "copiar"), ("campo de nome", "nome")):
        achados = dados[chave]
        if not achados:
            linhas.append(f"  {rotulo}: não encontrado")
            continue
        caixa = (dados.get("posicoes") or {}).get(chave)
        onde = (
            f"  (em {caixa[0]},{caixa[1]} — o mouse acerta)"
            if caixa
            else "  (sem posição medida: só a ação do elemento)"
        )
        linhas.append(f"  {rotulo}: SIM — " + " | ".join(f"“{nome}”" for nome in achados) + onde)
    if dados["pode_criar"]:
        linhas.append("")
        linhas.append("  Dá para tentar: `--criar --autorizar` (cria uma chave NOVA na sua conta).")
    else:
        linhas.append("")
        linhas.append(
            "  Sem o botão de criar na árvore, automatizar a criação não é possível nesta janela. "
            "O caminho que funciona sempre: criar no navegador e rodar `--pegar` (lê o que você copiou)."
        )
    return "\n".join(linhas)


def nome_sugerido(prefixo: str = "jarvis") -> str:
    """Nome da chave, com data — para a pessoa reconhecer depois e poder apagar."""
    from datetime import datetime  # noqa: PLC0415 - só quem cria precisa

    return f"{prefixo}-{datetime.now().strftime('%Y-%m-%d')}"
