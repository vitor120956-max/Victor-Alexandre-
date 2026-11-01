"""“JARVIS já está em uso” — a mensagem certa, e o encerramento seguro.

A frase que apareceu na tela de quem rodou o atalho era verdadeira e inútil:

    Já existe uma API respondendo em http://127.0.0.1:8000
    Não precisa subir outra: abra o endereço no navegador.

Faltava o número que importa: **qual versão** está rodando ali. Numa pasta
recém-atualizada com a janela antiga aberta, o navegador mostra o código velho e
a conclusão natural é “a atualização não funcionou”.

E faltava a saída para quando a janela antiga sumiu: `parar-jarvis.bat`.

O que estes testes travam:

- a decisão da porta é **pura** e cobre os quatro estados (livre, mesma versão,
  outra versão, outro programa), sempre dizendo o que fazer;
- comparar versão é comparar texto exato — nada de “parecido o bastante”;
- `encerrar()` **pergunta ao /api/health quem é antes de procurar o PID**: uma
  porta ocupada por outro programa nunca vira alvo;
- o `.bat` de parada é ASCII puro, CRLF, com `goto` consistente, não chama git
  nem npm, e oferece o Gerenciador de Tarefas como plano B;
- o `iniciar.py` não voltou a ter a lógica duplicada — ele usa `server.instancia`.

Nada aqui mata processo de verdade: o Windows é simulado.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from server import instancia

RAIZ = Path(__file__).resolve().parents[2]
BAT = RAIZ / "parar-jarvis.bat"

SAUDAVEL = {"service": "jarvis-python-api", "version": "0.70.0", "skills": 304}


# ------------------------------------------------------------------ decisão


def test_porta_livre_nao_tem_o_que_fazer():
    situacao = instancia.avaliar(None, "0.70.0", porta=8000, ocupada=False)
    assert situacao["estado"] == "livre"
    assert situacao["o_que_fazer"] == []


def test_mesma_versao_e_so_abrir_o_navegador():
    situacao = instancia.avaliar(SAUDAVEL, "0.70.0", porta=8000, ocupada=True)
    assert situacao["estado"] == "jarvis_mesma"
    assert situacao["versao_rodando"] == "0.70.0"
    assert "http://127.0.0.1:8000" in situacao["o_que_fazer"][0]


def test_versao_diferente_avisa_que_o_navegador_mostraria_codigo_velho():
    situacao = instancia.avaliar(SAUDAVEL, "0.62.6", porta=8000, ocupada=True)
    assert situacao["estado"] == "jarvis_antiga"
    assert "0.70.0" in situacao["detalhe"] and "0.62.6" in situacao["detalhe"]
    assert "código antigo" in situacao["detalhe"]
    juntas = " ".join(situacao["o_que_fazer"])
    assert "parar-jarvis.bat" in juntas


def test_comparacao_de_versao_e_exata():
    """`0.6.8` não é `0.70.0` — e 0.70.0 não é 0.70.0-rc1."""
    for rodando, pasta in (("0.6.8", "0.70.0"), ("0.70.0", "0.70.0-rc1"), ("0.70.0", None)):
        situacao = instancia.avaliar({"service": "jarvis-python-api", "version": rodando}, pasta, porta=8000, ocupada=True)
        assert situacao["estado"] == "jarvis_antiga", (rodando, pasta)


def test_outro_servico_na_porta_nao_e_o_jarvis():
    situacao = instancia.avaliar({"service": "nginx", "version": "1.2"}, "0.70.0", porta=8000, ocupada=True)
    assert situacao["estado"] == "outro_programa"
    assert "nginx" in situacao["detalhe"]
    assert any("não encerre" in passo.lower() for passo in situacao["o_que_fazer"])


def test_porta_ocupada_sem_health_tambem_e_outro_programa():
    situacao = instancia.avaliar(None, "0.70.0", porta=8000, ocupada=True)
    assert situacao["estado"] == "outro_programa"
    assert any("--porta 8001" in passo for passo in situacao["o_que_fazer"])


def test_todo_estado_que_nao_e_livre_diz_o_que_fazer():
    casos = [
        instancia.avaliar(SAUDAVEL, "0.70.0", porta=8000, ocupada=True),
        instancia.avaliar(SAUDAVEL, "0.1.0", porta=8000, ocupada=True),
        instancia.avaliar({"service": "x"}, "0.70.0", porta=8000, ocupada=True),
        instancia.avaliar(None, "0.70.0", porta=8000, ocupada=True),
    ]
    for situacao in casos:
        assert situacao["o_que_fazer"], situacao["estado"]
        assert situacao["titulo"] and situacao["detalhe"]


def test_resumo_mostra_as_duas_versoes():
    situacao = instancia.avaliar(SAUDAVEL, "0.62.6", porta=8000, ocupada=True)
    texto = instancia.resumo(situacao)
    assert "0.70.0" in texto and "0.62.6" in texto


# ------------------------------------------------------------------ netstat


NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:8000           0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:5173         0.0.0.0:0              LISTENING       777
  TCP    192.168.0.2:80000      0.0.0.0:0              LISTENING       9
  TCP    127.0.0.1:8000         127.0.0.1:55600        ESTABLISHED     4242
"""


def test_acha_o_pid_da_porta_sem_duplicar():
    assert instancia.pids_da_saida_netstat(NETSTAT, 8000) == [4242]


def test_nao_confunde_porta_com_numero_parecido():
    assert instancia.pids_da_saida_netstat(NETSTAT, 8000) != [9]
    assert instancia.pids_da_saida_netstat(NETSTAT, 800) == []


def test_ignora_conexao_estabelecida_e_pega_so_quem_escuta():
    texto = "  TCP    127.0.0.1:9000         127.0.0.1:55600        ESTABLISHED     321"
    assert instancia.pids_da_saida_netstat(texto, 9000) == []


def test_netstat_com_varios_pids_na_mesma_porta():
    texto = (
        "  TCP    0.0.0.0:8000    0.0.0.0:0    LISTENING    11\n"
        "  TCP    [::]:8000       [::]:0       LISTENING    22\n"
    )
    assert instancia.pids_da_saida_netstat(texto, 8000) == [11, 22]


def test_saida_vazia_nao_quebra():
    assert instancia.pids_da_saida_netstat("", 8000) == []


# ------------------------------------------------------------ encerramento


def test_recusa_encerrar_quando_nao_ha_jarvis(monkeypatch):
    monkeypatch.setattr(instancia, "ler_health", lambda *a, **k: None)
    monkeypatch.setattr(instancia, "pids_na_porta", lambda *a, **k: pytest.fail("não devia procurar PID"))
    resultado = instancia.encerrar(8000)
    assert resultado["encerrado"] is False
    assert "Não há JARVIS" in resultado["motivo"]


def test_recusa_encerrar_quando_quem_responde_nao_e_o_jarvis(monkeypatch):
    monkeypatch.setattr(instancia, "ler_health", lambda *a, **k: {"service": "outro", "version": "1.0"})
    monkeypatch.setattr(instancia, "pids_na_porta", lambda *a, **k: pytest.fail("não devia procurar PID"))
    monkeypatch.setattr(instancia, "encerrar_pid", lambda *a, **k: pytest.fail("não devia matar nada"))
    resultado = instancia.encerrar(8000)
    assert resultado["encerrado"] is False
    assert "não é o JARVIS" in resultado["motivo"]


def test_sem_pid_conhecido_nao_mata_nada(monkeypatch):
    monkeypatch.setattr(instancia, "ler_health", lambda *a, **k: SAUDAVEL)
    monkeypatch.setattr(instancia, "pids_na_porta", lambda *a, **k: [])
    monkeypatch.setattr(instancia, "encerrar_pid", lambda *a, **k: pytest.fail("não devia matar nada"))
    resultado = instancia.encerrar(8000)
    assert resultado["encerrado"] is False
    assert "netstat vazio" in resultado["motivo"]


def test_encerra_o_pid_certo_e_confirma_que_a_porta_ficou_livre(monkeypatch):
    mortos: list[int] = []
    monkeypatch.setattr(instancia, "ler_health", lambda *a, **k: SAUDAVEL)
    monkeypatch.setattr(instancia, "pids_na_porta", lambda *a, **k: [4242])
    monkeypatch.setattr(instancia, "encerrar_pid", lambda pid, *a, **k: mortos.append(pid) or True)
    monkeypatch.setattr(instancia.time, "sleep", lambda *_: None)

    chamadas = {"n": 0}

    def health_que_some(*a, **k):
        chamadas["n"] += 1
        return SAUDAVEL if chamadas["n"] <= 1 else None

    monkeypatch.setattr(instancia, "ler_health", health_que_some)
    resultado = instancia.encerrar(8000, espera=1)
    assert mortos == [4242]
    assert resultado["encerrado"] is True
    assert resultado["porta_livre"] is True


def test_se_a_porta_continuar_respondendo_ele_avisa(monkeypatch):
    monkeypatch.setattr(instancia, "ler_health", lambda *a, **k: SAUDAVEL)
    monkeypatch.setattr(instancia, "pids_na_porta", lambda *a, **k: [4242])
    monkeypatch.setattr(instancia, "encerrar_pid", lambda *a, **k: True)
    monkeypatch.setattr(instancia.time, "sleep", lambda *_: None)
    # espera=0: não fica esperando de verdade, e o health continua respondendo
    resultado = instancia.encerrar(8000, espera=0)
    assert resultado["encerrado"] is False
    assert "ainda responde" in resultado["motivo"]


# ------------------------------------------------------------- leitura


def test_versao_da_pasta_sai_do_package_json(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"version": "9.9.9"}), encoding="utf-8")
    assert instancia.versao_da_pasta(tmp_path) == "9.9.9"


def test_package_json_ausente_ou_quebrado_devolve_none(tmp_path):
    assert instancia.versao_da_pasta(tmp_path) is None
    (tmp_path / "package.json").write_text("{quebrado", encoding="utf-8")
    assert instancia.versao_da_pasta(tmp_path) is None


def test_cli_nao_trata_porta_livre_como_erro(monkeypatch, capsys):
    """“Nada a encerrar” é informação; o `.bat` só pede plano B em falha real."""
    monkeypatch.setattr(instancia, "ler_health", lambda *a, **k: None)
    vazia = lambda *a, **k: False  # noqa: E731 — porta livre
    monkeypatch.setattr(instancia, "porta_ocupada", vazia)
    assert instancia._cli(["--parar", "--sim", "--porta", "8099"]) == 0
    assert "Nada a encerrar" in capsys.readouterr().out


# --------------------------------------------------------------- o .bat


def test_o_bat_de_parar_existe_em_ascii_crlf():
    bruto = BAT.read_bytes()
    assert [b for b in bruto if b > 127] == []
    assert bruto.count(b"\n") == bruto.count(b"\r\n")


def test_o_bat_de_parar_tem_goto_consistente():
    texto = BAT.read_text(encoding="ascii")
    rotulos = set(re.findall(r"^:([A-Za-z_]\w*)", texto, flags=re.MULTILINE))
    destinos = set(re.findall(r"goto\s+([A-Za-z_]\w*)", texto, flags=re.IGNORECASE))
    assert destinos - rotulos == set()


def test_o_bat_de_parar_nao_chama_git_nem_npm():
    for linha in BAT.read_text(encoding="ascii").splitlines():
        limpa = linha.strip().lower()
        if limpa.startswith(("echo", "rem", "::")):
            continue
        for proibido in ("git ", "npm ", "npx "):
            assert proibido not in limpa, linha


def test_o_bat_de_parar_usa_o_python_do_venv_e_o_modulo():
    texto = BAT.read_text(encoding="ascii")
    assert r".venv\Scripts\python.exe" in texto
    assert "-m server.instancia --parar" in texto


def test_o_bat_de_parar_tem_plano_b_manual():
    """Se o netstat não achar, o usuário precisa de uma saída por conta própria."""
    texto = BAT.read_text(encoding="ascii")
    assert "Gerenciador de Tarefas" in texto
    assert "Finalizar tarefa" in texto


def test_o_bat_de_parar_avisa_que_so_mexe_no_jarvis():
    texto = BAT.read_text(encoding="ascii")
    assert "se identifica como ele mesmo" in texto


# ------------------------------------------------------------- iniciar.py


def test_iniciar_py_usa_o_modulo_em_vez_de_logica_duplicada():
    texto = (RAIZ / "iniciar.py").read_text(encoding="utf-8")
    assert "instancia.avaliar" in texto
    assert "instancia.ler_health" in texto
    assert "def _ja_esta_rodando" not in texto
    assert '"jarvis-python-api"' not in texto, "a comparação de identidade mora em server/instancia.py"
