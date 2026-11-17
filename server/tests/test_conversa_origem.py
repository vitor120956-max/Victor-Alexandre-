"""A tela tem de dizer de onde veio a resposta (0.91.34).

O dono perguntou “funcionou?” olhando a conversa: mandou “oi” e recebeu
*“Olá, Victor. Estou por aqui. Você pode me pedir uma tarefa…”*. Parecia o
modelo. Não era: é a skill local de saudação (`case 'greeting'`), que responde
sem chave nenhuma. Doze versões atrás de uma chave, e a primeira prova na tela
não provava nada.

Estes testes são de texto porque o defeito é de texto: a interface precisa

1. dizer, na própria saudação, que aquela resposta é local;
2. oferecer um comando que **pede ao modelo de verdade** (`testar ia`) e mostra
   o provedor e o tempo;
3. continuar marcando a mensagem do modelo como `IA EXTERNA` no balão.

Se alguém apagar qualquer uma das três, o dono volta a olhar para a tela sem
saber o que está vendo.
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MOTOR = RAIZ / "src" / "lib" / "jarvisEngine.ts"
CONTEXTO = RAIZ / "src" / "context" / "AppContext.tsx"
TESTE_WEB = RAIZ / "src" / "lib" / "jarvisEngine.test.ts"


def _motor() -> str:
    return MOTOR.read_text(encoding="utf-8")


def _contexto() -> str:
    return CONTEXTO.read_text(encoding="utf-8")


def test_a_saudacao_diz_que_e_local_e_ensina_o_teste():
    """“oi” não passa pelo modelo — e agora a resposta diz isso."""
    texto = _contexto()
    trecho = texto[texto.index("case 'greeting':") :][:900]
    assert "resposta é local" in trecho, "a saudação voltou a parecer resposta do modelo"
    assert "testar ia" in trecho, "a saudação tem de ensinar como provar a IA"


def test_existe_um_comando_que_pede_ao_modelo_de_verdade():
    """`testar ia` chama `/api/ai/chat` e marca a resposta como IA externa."""
    texto = _contexto()
    assert "intent.type === 'ai:testar'" in texto
    bloco = texto[texto.index("intent.type === 'ai:testar'") :][:2600]
    assert "requestAIChat(" in bloco, "o teste da IA tem de falar com o modelo"
    assert "'ai'" in bloco, "a resposta do modelo tem de sair marcada como IA externa"
    assert "respondeu em" in bloco, "o teste tem de cronometrar: ‘funcionou’ inclui ‘em quanto tempo’"
    assert "conferir-ia.py --corrigir" in bloco, "se falhar, tem de dizer o comando que conserta"


def test_sem_api_ou_sem_chave_o_comando_explica_em_vez_de_fingir():
    texto = _contexto()
    bloco = texto[texto.index("intent.type === 'ai:testar'") :][:2600]
    assert "não há como falar com o modelo" in bloco, "API fora tem de ser dita com todas as letras"
    assert "não está configurada" in bloco, "chave ausente tem de ser dita com todas as letras"


def test_o_motor_reconhece_o_pedido_e_nao_rouba_os_vizinhos():
    texto = _motor()
    assert "type: 'ai:testar'" in texto
    assert "testar|testa|teste" in texto
    # O comando tem de estar no `helpText`: comando que ninguém acha não existe.
    assert "testar ia" in texto
    # E não pode capturar os vizinhos.
    assert "status do sistema" in texto


def test_o_teste_da_interface_cobre_o_comando():
    assert TESTE_WEB.is_file()
    texto = TESTE_WEB.read_text(encoding="utf-8")
    assert "ai:testar" in texto
    for entrada in ("testar ia", "conferir a ia", "status da ia"):
        assert entrada in texto, f"o teste da interface não cobre “{entrada}”"


def test_a_mensagem_do_modelo_continua_marcada_no_balao():
    """O balão já marcava `· IA EXTERNA` — e é essa marca que o dono lê."""
    painel = (RAIZ / "src" / "components" / "ChatPanel.tsx").read_text(encoding="utf-8")
    assert "IA EXTERNA" in painel
    assert "SKILL PYTHON" in painel
