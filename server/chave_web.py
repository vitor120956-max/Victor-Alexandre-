"""Achar, na página do provedor, o que cria e o que copia a chave (0.91.16).

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
# — mais curto que o “Create Key” da página. A 0.91.15 só conhecia o rótulo
# longo e travou no passo 3 com o diálogo aberto na frente: o dublê do teste
# mostrou isso antes do dono. “Created/at” não é botão, mas entra na conta; por
# isso o nome mais curto vem primeiro.
PADROES_CONFIRMAR = ("create", "criar", "confirmar", "confirm", "save", "salvar")
PADROES_COPIAR = ("copy", "copiar")

# ---------------------------------------------------------------------------
# O diálogo “Create API key” (0.91.16) — medido na tela do dono
#
# Ele não é só nome e botão. Tem três campos com asterisco:
#
#     Name *        (caixa de texto)
#     Expiration *  (“Select expiration” — lista suspensa)
#     Credit limit * (“Choose a credit limit” — lista suspensa)
#
# Com só o nome preenchido, o botão “Create” fica desabilitado e o clique não
# faz nada. Era esse o travamento: o JARVIS “clicava em Create” e a chave não
# nascia, e o relatório dizia que tinha dado certo.
# ---------------------------------------------------------------------------

# O título do painel. **Não** entra aqui o rótulo “Create Key”: é o botão da
# página, e ele existe o tempo todo — com ele na lista, a página das chaves
# passava por diálogo aberto e o script ia preencher uma caixa que não estava lá.
PADROES_DIALOGO = ("create api key", "criar chave de api", "nova chave de api", "chave de api nova")
PADROES_EXPIRACAO = ("select expiration", "expiration", "expiração", "selecione a expiração")
PADROES_LIMITE = ("choose a credit limit", "credit limit", "limite de crédito")

# Valores que resolvem uma lista sem limite de tempo/valor, em inglês e português.
SEM_LIMITE = ("never", "nunca", "no limit", "unlimited", "sem limite", "ilimitado", "no expiration")

_UNIDADES = {
    "day": 1, "dias": 1, "dia": 1, "days": 1,
    "week": 7, "semana": 7, "semanas": 7, "weeks": 7,
    "month": 30, "mês": 30, "mes": 30, "meses": 30, "months": 30,
    "year": 365, "ano": 365, "anos": 365, "years": 365,
}
_NUMERO_E_UNIDADE = re.compile(r"(\d+)\s*([a-zçãéêíóôõ]+)")


def _dias(texto: str) -> int | None:
    """Quanto tempo um rótulo como “30 days” ou “1 year” dura, em dias."""
    normalizado = normalizar(texto)
    if any(marca in normalizado for marca in SEM_LIMITE):
        return 10**6  # "nunca expira" ganha de qualquer prazo
    achado = _NUMERO_E_UNIDADE.search(normalizado)
    if not achado:
        return None
    unidade = achado.group(2)
    return int(achado.group(1)) * _UNIDADES.get(unidade, 0) or None


def melhor_expiracao(opcoes: list[str]) -> str | None:
    """Qual prazo escolher na lista do diálogo — o **mais longo**.

    Por que o mais longo e não o mais curto: a chave que expira em 90 dias
    derruba o JARVIS três meses depois, sem ninguém ligar uma coisa à outra.
    “Never”, quando existe, ganha de tudo.
    """
    validas = [(dia, opcao) for opcao in opcoes if (dia := _dias(opcao)) is not None]
    if not validas:
        return None
    validas.sort(key=lambda par: (-par[0], len(par[1])))
    return validas[0][1]


def melhor_limite(opcoes: list[str], aceitar_maior: bool = False) -> str | None:
    """A opção de crédito que não trava a chave — “No limit”/“Sem limite”.

    Não escolher limite é o que evita a chave parar sozinha no meio do mês;
    se a lista só tiver valores (5, 10, 20…), devolve `None` e o dono decide.

    `aceitar_maior` é para o caminho automático, quando parar significa não
    criar chave nenhuma: aí o maior valor da lista é o mais perto de “sem
    limite” que o site oferece — e quem chama avisa que foi isso que escolheu.
    """
    for opcao in opcoes:
        normalizada = normalizar(opcao)
        if any(marca in normalizada for marca in SEM_LIMITE):
            return opcao
    if not aceitar_maior:
        return None
    numeros: list[tuple[float, str]] = []
    for opcao in opcoes:
        achado = _NUMERO_E_UNIDADE.search(normalizar(opcao)) or re.search(r"(\d+(?:[.,]\d+)?)", normalizar(opcao))
        if not achado:
            continue
        try:
            valor = float(achado.group(1).replace(",", "."))
        except ValueError:
            continue
        numeros.append((valor, opcao))
    if not numeros:
        return None
    return max(numeros, key=lambda par: par[0])[1]


# Marcas que **só** existem no diálogo de criação — valem mais que o título.
# Medido no PC do dono (0.91.16): o painel abriu, o clique em “New key” acertou,
# e a leitura não trouxe o texto “Create API key” — trouxe os campos. Procurar
# o título sozinho dizia “o diálogo não apareceu” com o diálogo na tela.
MARCAS_DO_DIALOGO = (
    "select expiration",
    "choose a credit limit",
    "credit limit",
    "key limit",
    "reset limit",
    "expiração",
    "limite de crédito",
)


def e_dialogo_de_criacao(arvore_montada: dict[str, Any]) -> bool:
    """A janela está com o diálogo “Create API key” aberto?

    Duas provas, e qualquer uma serve: o título (“Create API key”) **ou** os
    campos que só existem ali (expiração/limite). A segunda é a que funciona
    quando a leitura não alcança o título — que foi o que aconteceu de verdade.
    """
    texto = texto_da_janela(arvore_montada, limite=200)
    if any(marca in texto for marca in PADROES_DIALOGO):
        return True
    achou_marca = any(marca in texto for marca in MARCAS_DO_DIALOGO)
    tem_nome = bool(procurar(arvore_montada, PADROES_NOME))
    return achou_marca and (tem_nome or "create" in texto or "criar" in texto)


def nomes_novos(antes: dict[str, Any], depois: dict[str, Any], limite: int = 60) -> list[dict[str, Any]]:
    """Nós que apareceram entre duas leituras — as opções de uma lista aberta.

    Abrir uma lista suspensa não muda o nome de nada: ela **acrescenta** nós.
    Comparar as duas leituras pelo nome é o jeito de achar as opções sem saber
    como o site as desenha.
    """
    vistos = {str(no.get("nome") or "").strip() for no in elementos(antes)}
    novos = [
        no
        for no in elementos(depois)
        if str(no.get("nome") or "").strip()
        and str(no.get("nome") or "").strip() not in vistos
        and len(str(no.get("nome") or "").strip()) <= limite
    ]
    return novos
# O rótulo do campo é “Name”; dentro da caixa há o exemplo “e.g. “ChatbotKey””.
# Os dois entram: em uns Chrome a caixa se apresenta pelo rótulo, em outros pelo
# texto de exemplo — e quem digita é a caixa, não o rótulo.
PADROES_NOME = ("key name", "nome da chave", "chatbotkey", "digite o nome", "name", "nome")

# Ações que significam “aqui se escreve”. A MSAA diz “digitar”; a UIAutomation
# diz “escrever” — é o mesmo campo.
ACOES_DE_ESCRITA = ("escrever", "digitar")

# O que a página de chaves tem escrito, independentemente do idioma.
# Nada de `keys`/`chaves` sozinhos: qualquer página pode ter a palavra, e um
# falso positivo aqui faria o script clicar na página errada.
#
# 0.91.15 — `openrouter` saiu daqui. A tela de **login** do OpenRouter tem
# “OpenRouter” no título, e com essa marca o JARVIS achava que já estava na
# página de chaves, parava e pedia um botão que não existia. Marcas agora são as
# que só existem **depois** de entrar.
MARCAS_DA_PAGINA = ("api keys", "chaves de api", "new key", "nova chave", "create key", "criar chave")

# ---------------------------------------------------------------------------
# Onde estou? (0.91.16)
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


def todos(arvore_montada: dict[str, Any]) -> list[dict[str, Any]]:
    """Todos os nós montados, inclusive os **sem nome** — o campo costuma ser um deles."""
    return _achatar(arvore_montada.get("arvore"))


def e_campo_de_escrita(no: dict[str, Any]) -> bool:
    """Este nó é onde se digita — e não o rótulo ao lado dele?

    Medido no painel do OpenRouter: “Name” e a caixa de texto são **dois nós**.
    Clicar no rótulo e mandar as teclas escreve no nada — o campo fica vazio e o
    script achava que tinha escrito. O que separa um do outro é a **ação**: só
    a caixa aceita escrever.
    """
    if not isinstance(no, dict) or no.get("desativado"):
        return False
    acao = normalizar(str(no.get("acao") or ""))
    if any(marca in acao for marca in ACOES_DE_ESCRITA):
        return True
    # Sem ação declarada, o papel de caixa de texto ainda serve — mas só com
    # posição medida: sem caixa não há como clicar nela.
    try:
        codigo = int(no.get("codigo") or 0)
    except (TypeError, ValueError):
        codigo = 0
    # Papel de caixa de texto com posição medida. Não se exige ação declarada:
    # há campo de edição que não publica `ValuePattern` e mesmo assim recebe
    # teclas quando é clicado — recusá-lo deixaria o nome sem onde ser escrito.
    return codigo in (42, 15) and caixa_de(no) is not None


def campos_de_escrita(arvore_montada: dict[str, Any]) -> list[dict[str, Any]]:
    """Onde dá para digitar, na ordem da leitura."""
    return [no for no in todos(arvore_montada) if e_campo_de_escrita(no)]


def _e_rotulo_de_nome(texto: str) -> bool:
    """“Name”, “Name *”, “Nome”: rótulo curto, não a frase de busca da página."""
    limpo = normalizar(texto).rstrip("*· ").strip()
    return limpo in {"name", "nome", "key name", "nome da chave"}


def campo_do_nome(arvore_montada: dict[str, Any]) -> dict[str, Any] | None:
    """A **caixa** onde vai o nome da chave, dentro do painel de criação.

    Quatro regras, da mais direta à mais grosseira:

    1. uma caixa de escrita cujo nome/texto casa com o campo de nome
       (“Name”, “nome da chave”, o exemplo “ChatbotKey”);
    2. a caixa de escrita mais próxima **acima** da lista de expiração — é a
       ordem do painel (Name, Expiration, Credit limit);
    3. a caixa de escrita logo **abaixo** do rótulo “Name”;
    4. a caixa mais alta do painel.

    A página continua atrás do painel na mesma leitura, e ela tem uma caixa de
    busca (“Search by name or paste a key…”). Por isso a lista é filtrada por
    posição quando o título do painel tem posição medida: o que está acima dele
    não é do painel.
    """
    campos = campos_de_escrita(arvore_montada)
    if not campos:
        return None

    # Fora do painel não serve: se o título mede, o campo tem de estar abaixo.
    titulo = next(
        (
            no
            for no in todos(arvore_montada)
            if "create api key" in normalizar(str(no.get("nome") or "")) or "criar chave de api" in normalizar(str(no.get("nome") or ""))
        ),
        None,
    )
    caixa_titulo = caixa_de(titulo or {})
    if caixa_titulo:
        dentro = [no for no in campos if (c := caixa_de(no)) and c[1] >= caixa_titulo[1] - 10]
        if dentro:
            campos = dentro

    alvos = [normalizar(padrao) for padrao in PADROES_NOME]
    for no in campos:  # 1
        if any(alvo in normalizar(str(no.get("nome") or "")) for alvo in alvos):
            return no

    expiracao = next(
        (
            no
            for no in elementos(arvore_montada)
            if any(padrao in normalizar(str(no.get("nome") or "")) for padrao in ("select expiration", "selecione a expiracao"))
            and caixa_de(no)
        ),
        None,
    )
    caixa_expiracao = caixa_de(expiracao or {})
    if caixa_expiracao:  # 2
        acima = [no for no in campos if (c := caixa_de(no)) and c[1] < caixa_expiracao[1]]
        if acima:
            return max(acima, key=lambda no: caixa_de(no)[1])

    for rotulo in todos(arvore_montada):  # 3
        if _e_rotulo_de_nome(str(rotulo.get("nome") or "")) and caixa_de(rotulo):
            base = caixa_de(rotulo)[1]
            abaixo = [no for no in campos if (c := caixa_de(no)) and c[1] >= base]
            if abaixo:
                return min(abaixo, key=lambda no: caixa_de(no)[1])

    com_caixa = [no for no in campos if caixa_de(no)]
    return min(com_caixa, key=lambda no: caixa_de(no)[1]) if com_caixa else campos[0]


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
