"""Achar, na página do provedor, o que cria e o que copia a chave (0.91.10).

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
# — mais curto que o “Create Key” da página. A 0.91.10 só conhecia o rótulo
# longo e travou no passo 3 com o diálogo aberto na frente: o dublê do teste
# mostrou isso antes do dono. “Created/at” não é botão, mas entra na conta; por
# isso o nome mais curto vem primeiro.
PADROES_CONFIRMAR = ("create", "criar", "confirmar", "confirm", "save", "salvar")
PADROES_COPIAR = ("copy", "copiar")
PADROES_NOME = ("key name", "nome da chave", "name", "nome")

# O que a página de chaves tem escrito, independentemente do idioma.
# Nada de `keys`/`chaves` sozinhos: qualquer página pode ter a palavra, e um
# falso positivo aqui faria o script clicar na página errada.
MARCAS_DA_PAGINA = ("api keys", "create key", "criar chave", "chaves de api", "openrouter")


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
    achados.sort(key=lambda no: len(normalizar(str(no.get("nome") or ""))))
    return achados


def e_pagina_de_chaves(arvore_montada: dict[str, Any]) -> bool:
    """A janela lida parece a página de chaves do provedor?"""
    texto = normalizar(arvore_montada.get("alvo") or "")
    texto += " " + " ".join(normalizar(str(no.get("nome") or "")) for no in elementos(arvore_montada)[:80])
    return any(marca in texto for marca in MARCAS_DA_PAGINA)


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
