import { useCallback, useEffect, useRef, useState } from 'react';
import { Bell, BrainCircuit, Check, Database, Download, Eye, EyeOff, KeyRound, Mic2, Palette, RotateCcw, ShieldCheck, Trash2, UserRound, Volume2, Zap } from 'lucide-react';
import { Modal } from '../components/Modal';
import { useApp } from '../context/AppContext';
import { apagarChavesIA, getChavesIA, getModelosIA, salvarChavesIA, salvarModeloIA, testarChavesIA } from '../lib/api';
import type { ChaveTesteResultado, ChavesIA, ModelosIA } from '../lib/api';
import type { Preferences } from '../types';

export function SettingsPage() {
  const { preferences, updatePreferences, exportBackup, resetWorkspace, pushToast, aiStatus, backendOnline, backendVersion, refreshBackend } = useApp();
  const [resetOpen, setResetOpen] = useState(false);

  // --- chaves de IA -------------------------------------------------------
  // A chave vive só no .env do servidor: ela é enviada uma vez, gravada, e o
  // campo é limpo. Nada de guardar em localStorage nem exibir de volta.
  const [chaves, setChaves] = useState<ChavesIA | null>(null);
  const [chavesAbertas, setChavesAbertas] = useState(false);
  const [textoChaves, setTextoChaves] = useState('');
  const [mostrarTexto, setMostrarTexto] = useState(false);
  const [acrescentar, setAcrescentar] = useState(false);
  const [salvandoChaves, setSalvandoChaves] = useState(false);
  const [teste, setTeste] = useState<ChaveTesteResultado | null>(null);
  const campoChaves = useRef<HTMLTextAreaElement | null>(null);

  // --- modelo de IA -------------------------------------------------------
  // “e sobre os modelos, como funcionam?”: cada opção vem com o que ela custa,
  // e a escolha é gravada no `.env` sem ninguém decorar nome de modelo.
  const [modelos, setModelos] = useState<ModelosIA | null>(null);
  const [modeloEscolhido, setModeloEscolhido] = useState('');
  const [modeloLivre, setModeloLivre] = useState('');
  const [salvandoModelo, setSalvandoModelo] = useState(false);

  const recarregarModelos = useCallback(async () => {
    if (!backendOnline) {
      setModelos(null);
      return;
    }
    try {
      const dados = await getModelosIA();
      setModelos(dados);
      setModeloEscolhido(dados.modelo || dados.padrao);
      setModeloLivre(dados.modelo && !dados.opcoes.some((item) => item.id === dados.modelo) ? dados.modelo : '');
    } catch {
      setModelos(null);
    }
  }, [backendOnline]);

  useEffect(() => { void recarregarModelos(); }, [recarregarModelos]);

  const usarModeloEspecifico = async (alvo: string) => {
    setSalvandoModelo(true);
    try {
      const dados = await salvarModeloIA(alvo);
      setModelos(dados);
      setModeloEscolhido(dados.modelo);
      setModeloLivre('');
      await refreshBackend();
      pushToast('Modelo trocado', `Agora respondendo com ${dados.modelo}.`, 'success');
    } catch (erro) {
      pushToast('Não deu para trocar o modelo', erro instanceof Error ? erro.message : undefined, 'warning');
    } finally {
      setSalvandoModelo(false);
    }
  };

  const usarModelo = async () => {
    const alvo = (modeloLivre.trim() || modeloEscolhido).trim();
    if (!alvo) {
      pushToast('Escolha um modelo', 'Selecione na lista ou digite o nome exato.', 'warning');
      return;
    }
    setSalvandoModelo(true);
    try {
      const dados = await salvarModeloIA(alvo);
      setModelos(dados);
      setModeloEscolhido(dados.modelo);
      setModeloLivre('');
      await refreshBackend();
      pushToast('Modelo trocado', `Agora respondendo com ${dados.modelo}. Vale na próxima mensagem.`, 'success');
    } catch (erro) {
      pushToast('Não deu para trocar o modelo', erro instanceof Error ? erro.message : undefined, 'warning');
    } finally {
      setSalvandoModelo(false);
    }
  };

  const recarregarChaves = useCallback(async () => {
    if (!backendOnline) {
      setChaves(null);
      return;
    }
    try {
      setChaves(await getChavesIA());
    } catch {
      setChaves(null);
    }
  }, [backendOnline]);

  useEffect(() => { void recarregarChaves(); }, [recarregarChaves]);

  useEffect(() => {
    if (chavesAbertas) campoChaves.current?.focus();
  }, [chavesAbertas]);

  const fecharChaves = () => {
    setChavesAbertas(false);
    setTextoChaves('');       // o texto colado não fica na memória da tela
    setMostrarTexto(false);
    setTeste(null);
  };

  const salvarChaves = async (eTestar: boolean) => {
    if (!textoChaves.trim()) {
      pushToast('Cole a chave primeiro', 'O campo está vazio.', 'warning');
      return;
    }
    setSalvandoChaves(true);
    setTeste(null);
    try {
      const estado = await salvarChavesIA(textoChaves, acrescentar);
      setChaves(estado);
      setTextoChaves('');
      pushToast(
        `${estado.quantidade} chave(s) guardada(s)`,
        estado.local ? 'Modelo local: chave não é usada.' : `Provedor ${estado.provedor || '—'} já respondendo, sem reiniciar.`,
        'success',
      );
      await refreshBackend();
      if (eTestar) {
        const resultado = await testarChavesIA();
        setTeste(resultado);
        pushToast(resultado.resumo, resultado.ok ? 'O cérebro está de pé.' : 'Veja chave por chave.', resultado.ok ? 'success' : 'warning');
      }
    } catch (erro) {
      pushToast('Não deu para gravar a chave', erro instanceof Error ? erro.message : undefined, 'warning');
    } finally {
      setSalvandoChaves(false);
    }
  };

  const testarAgora = async (indice?: number) => {
    setSalvandoChaves(true);
    try {
      const resultado = await testarChavesIA(indice);
      setTeste(resultado);
      pushToast(resultado.resumo, undefined, resultado.ok ? 'success' : 'warning');
    } catch (erro) {
      pushToast('O teste não rodou', erro instanceof Error ? erro.message : undefined, 'warning');
    } finally {
      setSalvandoChaves(false);
    }
  };

  const apagarTudo = async () => {
    setSalvandoChaves(true);
    try {
      const estado = await apagarChavesIA();
      setChaves(estado);
      setTeste(null);
      await refreshBackend();
      pushToast('Chaves apagadas', 'As skills locais continuam funcionando.', 'success');
    } catch (erro) {
      pushToast('Não deu para apagar', erro instanceof Error ? erro.message : undefined, 'warning');
    } finally {
      setSalvandoChaves(false);
    }
  };

  const testVoice = () => {
    if (typeof speechSynthesis === 'undefined') {
      pushToast('Voz não suportada neste navegador', undefined, 'warning');
      return;
    }
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(`Olá, ${preferences.name}. Este é um teste de voz do seu núcleo pessoal.`);
    utterance.lang = 'pt-BR';
    utterance.rate = preferences.voiceRate;
    speechSynthesis.speak(utterance);
  };

  return (
    <div className="settings-page">
      <header className="page-heading"><div><span className="eyebrow">PREFERÊNCIAS DO NÚCLEO</span><h1>Configurações<span>.</span></h1><p>Ajuste o JARVIS ao seu jeito de trabalhar.</p></div><span className="saved-indicator"><Check size={14} /> Salvamento automático</span></header>
      <div className="settings-layout">
        <div className="settings-main">
          <section className="panel settings-section">
            <div className="settings-section-heading"><span><UserRound size={19} /></span><div><h2>Perfil</h2><p>Como o assistente deve se dirigir a você.</p></div></div>
            <label className="field settings-name-field"><span>Seu nome</span><input value={preferences.name} onChange={(event) => updatePreferences({ name: event.target.value.slice(0, 40) })} placeholder="Como quer ser chamado?" /></label>
          </section>
          <section className="panel settings-section ai-settings-section">
            <div className="settings-section-heading"><span><BrainCircuit size={19} /></span><div><h2>Inteligência generativa</h2><p>Provedor externo configurado exclusivamente no servidor.</p></div></div>
            <div className="ai-provider-status"><div><span className={aiStatus.configured && backendOnline ? 'skill-status active' : 'skill-status'}><i />{backendOnline ? aiStatus.configured ? 'CONFIGURADA' : 'NÃO CONFIGURADA' : 'API OFFLINE'}</span><strong>{backendOnline && aiStatus.configured ? aiStatus.provider : 'Comandos locais continuam disponíveis'}</strong></div>{backendOnline && aiStatus.configured && aiStatus.model && <code>{aiStatus.model}</code>}</div>
            <div className="setting-row"><div><strong>Usar IA para perguntas abertas</strong><p>Somente pedidos fora das skills locais são enviados ao provedor.</p></div><button className={`switch ${preferences.aiEnabled && aiStatus.configured ? 'switch-on' : ''}`} role="switch" aria-checked={preferences.aiEnabled && aiStatus.configured} disabled={!aiStatus.configured} onClick={() => updatePreferences({ aiEnabled: !preferences.aiEnabled })}><span /></button></div>
            <div className="setting-row"><div><strong>Compartilhar tarefas e notas como contexto</strong><p>Desativado por padrão. O histórico recente da conversa ainda é enviado nas chamadas de IA.</p></div><button className={`switch ${preferences.shareContextWithAI ? 'switch-on' : ''}`} role="switch" aria-checked={preferences.shareContextWithAI} disabled={!aiStatus.configured || !preferences.aiEnabled} onClick={() => updatePreferences({ shareContextWithAI: !preferences.shareContextWithAI })}><span /></button></div>
            <div className="chaves-card" id="chaves-de-ia">
              <h3 className="chaves-titulo"><KeyRound size={13} /> Chaves de IA</h3>
              <div className="chaves-topo">
                <div>
                  <strong>
                    {!backendOnline
                      ? 'API desligada'
                      : chaves && chaves.quantidade > 0
                        ? `${chaves.quantidade} chave${chaves.quantidade > 1 ? 's' : ''} guardada${chaves.quantidade > 1 ? 's' : ''}`
                        : 'Nenhuma chave guardada'}
                  </strong>
                  <p>
                    {chaves && chaves.quantidade > 0
                      ? `${chaves.provedor || 'Provedor'} · ${chaves.modelo || 'modelo não definido'}`
                      : 'Cole aqui as chaves do provedor. Elas ficam só no .env desta máquina.'}
                  </p>
                </div>
                <div className="chaves-botoes">
                  <button
                    className="button button-primary"
                    onClick={() => setChavesAbertas(true)}
                    disabled={!backendOnline || chaves?.podeEditar === false}
                    title={chaves?.podeEditar === false ? 'Só a própria máquina grava chave' : 'Colar as chaves'}
                  >
                    <KeyRound size={15} /> Colar chaves
                  </button>
                  {chaves && chaves.quantidade > 0 && (
                    <button className="button button-secondary" onClick={() => void testarAgora()} disabled={salvandoChaves}>
                      <Zap size={15} /> Testar
                    </button>
                  )}
                </div>
              </div>

              {chaves && chaves.quantidade > 0 && (
                <ul className="chaves-lista">
                  {chaves.mascaradas.map((mascarada, indice) => (
                    <li key={mascarada}>
                      <span>{indice + 1}</span>
                      <code>{mascarada}</code>
                    </li>
                  ))}
                </ul>
              )}

              {/* 0.79.0 — cota: o que o provedor respondeu por último em cada
                  chave. Sem isso, o aviso vermelho não tinha onde ser conferido. */}
              {aiStatus.saude && aiStatus.saude.situacao !== 'local' && aiStatus.saude.situacao !== 'sem_chave' && (
                <div className={`chaves-cota chaves-cota-${aiStatus.saude.situacao}`}>
                  <strong>{aiStatus.saude.resumo}</strong>
                  <ul>
                    {aiStatus.saude.chaves.map((item) => (
                      <li key={item.numero} className={`chave-${item.estado}`}>
                        <span>{item.estado === 'ok' ? <Check size={13} /> : '×'}</span>
                        chave {item.numero}:{' '}
                        {item.estado === 'no_limite'
                          ? `no limite do minuto (HTTP ${item.codigo})${item.retry_after ? `, tente em ${Math.round(item.retry_after)}s` : ''}`
                          : item.estado === 'recusada'
                            ? `recusada (HTTP ${item.codigo}) — troque esta chave`
                            : item.aperto === 'pedidos'
                              ? `restam ${item.restam_pedidos} de ${item.limite_pedidos} pedidos neste minuto`
                              : item.aperto === 'tokens'
                                ? `restam ${item.restam_tokens} de ${item.limite_tokens} tokens neste minuto`
                                : 'respondendo'}
                      </li>
                    ))}
                  </ul>
                  {aiStatus.saude.situacao !== 'ok' && <p>{aiStatus.saude.aviso}</p>}
                </div>
              )}

              {chaves && chaves.podeEditar === false && (
                <p className="ai-config-note">Esta tela está aberta em outro aparelho. A chave só é gravada na própria máquina.</p>
              )}

              {teste && (
                <div className="chaves-resultado">
                  {/* 0.79.2 — o resumo agora diz QUAL das três coisas aconteceu:
                      chave inválida, cota da conta, ou só o modelo fora do ar. */}
                  <strong>{teste.resumo}</strong>
                  {teste.modelo_sugerido && (
                    <button
                      className="button button-primary chaves-trocar-modelo"
                      onClick={() => void usarModeloEspecifico(teste.modelo_sugerido as string)}
                      disabled={salvandoModelo}
                    >
                      <Zap size={14} /> Usar {teste.modelo_sugerido}
                    </button>
                  )}
                  <ul>
                    {teste.resultados.map((item) => (
                      <li key={item.indice} className={item.ok ? 'chave-ok' : 'chave-falhou'}>
                        <span>{item.ok && !item.modelo_que_respondeu ? <Check size={13} /> : item.ok ? '!' : '×'}</span>
                        <div>
                          chave {item.indice}: {item.motivo}
                          {/* A frase do provedor: “tente em 12m34s — limite 100000, usado 100000”.
                              Sem ela, “HTTP 429” não diz se espera 30 s ou 8 h. */}
                          {item.detalhe ? <small className="chave-detalhe">{item.detalhe}</small> : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* 0.79.1 — o modelo é a segunda metade de “o cérebro”: a chave
                abre a porta, o modelo é quem responde. */}
            <div className="modelos-card" id="modelos-de-ia">
              <h3 className="chaves-titulo"><BrainCircuit size={13} /> Modelos de IA</h3>
              <p className="modelos-resumo">
                {modelos?.local
                  ? 'Modelo local: não há catálogo — o modelo é o arquivo .gguf que o llama-server carrega.'
                  : 'A chave abre a porta; o modelo é quem responde. Grande entende melhor e gasta mais cota; pequeno responde rápido e rende muito mais. Cada modelo tem a sua cota: quando um estoura, trocar de modelo renova.'}
              </p>
              {modelos && !modelos.local && (
                <>
                  <label className="field">
                    <span>Modelo do provedor</span>
                    <select value={modeloEscolhido} onChange={(event) => setModeloEscolhido(event.target.value)}>
                      {modelos.opcoes.map((opcao) => (
                        <option key={opcao.id} value={opcao.id}>{opcao.nome} — {opcao.perfil}</option>
                      ))}
                      {modeloEscolhido && !modelos.opcoes.some((item) => item.id === modeloEscolhido) && (
                        <option value={modeloEscolhido}>{modeloEscolhido} (fora da lista)</option>
                      )}
                    </select>
                  </label>
                  <p className="modelos-detalhe">
                    {modelos.opcoes.find((item) => item.id === modeloEscolhido)?.quando
                      || 'Modelo fora da lista: confira o nome no painel do provedor.'}
                  </p>
                </>
              )}
              <label className="field">
                <span>Ou o nome exato do modelo {modelos?.local ? '(arquivo .gguf)' : ''}</span>
                <input
                  value={modeloLivre}
                  onChange={(event) => setModeloLivre(event.target.value)}
                  placeholder={modelos?.modelo || 'ex.: llama-3.3-70b-versatile'}
                  maxLength={120}
                />
              </label>
              <div className="modelos-acoes">
                <button className="button button-primary" onClick={() => void usarModelo()} disabled={!backendOnline || salvandoModelo}>
                  <Zap size={15} /> {salvandoModelo ? 'Gravando…' : 'Usar este modelo'}
                </button>
                <button className="button button-secondary" onClick={() => { setModeloLivre(''); setModeloEscolhido(modelos?.padrao || ''); }} disabled={salvandoModelo}>
                  <RotateCcw size={15} /> Voltar ao padrão
                </button>
              </div>
              <p className="modelos-nota">
                A cota de cada modelo é do provedor e muda. Se um nome sair do ar, o botão <strong>Testar</strong> das chaves mostra o erro na hora.
              </p>
            </div>
          </section>
          <section className="panel settings-section">
            <div className="settings-section-heading"><span><Mic2 size={19} /></span><div><h2>Voz e respostas</h2><p>Controle quando o JARVIS fala em voz alta.</p></div></div>
            <div className="setting-row"><div><strong>Responder por voz</strong><p>As respostas da conversa serão faladas após seus comandos.</p></div><button className={`switch ${preferences.voiceResponse ? 'switch-on' : ''}`} role="switch" aria-checked={preferences.voiceResponse} onClick={() => updatePreferences({ voiceResponse: !preferences.voiceResponse })}><span /></button></div>
            <div className="setting-row voice-rate-row"><div><strong>Velocidade da fala</strong><p>Ajuste entre mais pausada e mais rápida.</p></div><div className="rate-control"><input type="range" min="0.7" max="1.4" step="0.1" value={preferences.voiceRate} onChange={(event) => updatePreferences({ voiceRate: Number(event.target.value) })} aria-label="Velocidade da fala" /><span>{preferences.voiceRate.toFixed(1)}×</span></div></div>
            <button className="button button-secondary test-voice-button" onClick={testVoice}><Volume2 size={16} /> Testar voz do navegador</button>
          </section>
          <section className="panel settings-section">
            <div className="settings-section-heading"><span><Palette size={19} /></span><div><h2>Aparência</h2><p>Escolha o sinal visual do seu núcleo.</p></div></div>
            <div className="setting-row"><div><strong>Cor de destaque</strong><p>Aplicada a botões, estados ativos e ao núcleo.</p></div><div className="accent-options">{(['mint', 'cyan', 'amber'] as Preferences['accent'][]).map((accent) => <button key={accent} className={`accent-option accent-${accent} ${preferences.accent === accent ? 'selected' : ''}`} onClick={() => updatePreferences({ accent })} aria-label={`Usar cor ${accent}`}><span />{preferences.accent === accent && <Check size={13} />}</button>)}</div></div>
            <div className="setting-row"><div><strong>Reduzir movimento</strong><p>Desativa rotações e animações não essenciais.</p></div><button className={`switch ${preferences.reduceMotion ? 'switch-on' : ''}`} role="switch" aria-checked={preferences.reduceMotion} onClick={() => updatePreferences({ reduceMotion: !preferences.reduceMotion })}><span /></button></div>
          </section>
          <section className="panel settings-section">
            <div className="settings-section-heading"><span><Bell size={19} /></span><div><h2>Notificações</h2><p>Alertas do navegador para foco e automações.</p></div></div>
            <div className="setting-row"><div><strong>Notificações do sistema</strong><p>Opcional. Os avisos dentro do app continuam funcionando.</p></div><button className={`switch ${preferences.notifications ? 'switch-on' : ''}`} role="switch" aria-checked={preferences.notifications} onClick={() => updatePreferences({ notifications: !preferences.notifications })}><span /></button></div>
          </section>
        </div>
        <aside className="settings-aside">
          <section className="panel data-card"><span className="settings-aside-icon"><Database size={21} /></span><h2>Seus dados</h2><p>Leve uma cópia das tarefas, notas, conversas, rotinas e preferências.</p><button className="button button-secondary" onClick={exportBackup}><Download size={16} /> Exportar backup</button><small>Arquivo JSON · gerado localmente</small></section>
          <section className="panel security-settings"><ShieldCheck size={20} /><div><strong>Modo local-first</strong><p>Skills locais não exigem chave. A IA externa é opcional e recebe contexto pessoal somente com sua autorização.</p></div></section>
          <section className="panel about-card"><div><span>VERSÃO</span><strong>{backendVersion ?? (backendOnline ? '—' : 'API OFFLINE')}</strong></div><div><span>NÚCLEO</span><strong>React + Python</strong></div><div><span>IDIOMA</span><strong>Português (BR)</strong></div></section>
          <button className="reset-button" onClick={() => setResetOpen(true)}><RotateCcw size={16} /> Restaurar dados de exemplo</button>
        </aside>
      </div>
      <Modal open={chavesAbertas} onClose={fecharChaves} title="Colar as chaves" eyebrow="FICAM SÓ NO .ENV DESTA MÁQUINA">
        <div className="chaves-colar">
          <p>
            Cole o bloco inteiro, com ou sem os rótulos — o JARVIS pega só o que é chave
            (<code>gsk_…</code>, <code>sk-…</code>, <code>AIza…</code>). Uma por linha ou separadas por vírgula.
          </p>
          <div className="chaves-campo">
            <textarea
              ref={campoChaves}
              value={textoChaves}
              onChange={(event) => setTextoChaves(event.target.value)}
              placeholder={'gsk_...\ngsk_...\ngsk_...'}
              spellCheck={false}
              autoComplete="off"
              className={mostrarTexto ? '' : 'chaves-oculto'}
              rows={5}
            />
            <button type="button" className="chaves-olho" onClick={() => setMostrarTexto((v) => !v)} title={mostrarTexto ? 'Esconder' : 'Mostrar'}>
              {mostrarTexto ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
          <label className="chaves-check">
            <input type="checkbox" checked={acrescentar} onChange={(event) => setAcrescentar(event.target.checked)} />
            Manter as que já estão (acrescentar em vez de trocar)
          </label>
          {/* 0.79.2 — a verdade que faltava: no Groq a cota é por CONTA, não por
              chave. Quatro chaves do mesmo login não são quatro cotas, e foi
              exatamente isso que fez as quatro falharem juntas no print. */}
          <p className="chaves-aviso">
            A chave é enviada uma vez para o servidor local e gravada no <code>.env</code>. Depois de salvar,
            o campo é limpo e a chave nunca mais é mostrada — nem aqui, nem no chat. Como você já compartilhou
            essas chaves em algum lugar, o certo é gerar novas no painel do provedor.
          </p>
          <p className="chaves-aviso chaves-aviso-conta">
            <strong>No Groq a cota é por conta, não por chave.</strong> Várias chaves criadas no mesmo login
            dividem o mesmo limite — elas servem para trocar quando uma falha, não para somar cota. Cada
            <em> modelo </em> tem a sua cota própria: trocar de modelo no cartão abaixo é o que renova.
          </p>
          <div className="modal-actions">
            <button className="button button-ghost" onClick={fecharChaves}>Cancelar</button>
            {chaves && chaves.quantidade > 0 && (
              <button className="button button-ghost chaves-apagar" onClick={() => void apagarTudo()} disabled={salvandoChaves}>
                <Trash2 size={15} /> Apagar todas
              </button>
            )}
            <button className="button button-secondary" onClick={() => void salvarChaves(false)} disabled={salvandoChaves}>
              Só salvar
            </button>
            <button className="button button-primary" onClick={() => void salvarChaves(true)} disabled={salvandoChaves}>
              {salvandoChaves ? 'Salvando…' : 'Salvar e testar'}
            </button>
          </div>
        </div>
      </Modal>
      <Modal open={resetOpen} onClose={() => setResetOpen(false)} title="Restaurar o núcleo?" eyebrow="AÇÃO DESTRUTIVA">
        <div className="reset-confirm"><p>Suas tarefas, notas, conversas e preferências atuais serão substituídas pelos dados iniciais. Essa ação não pode ser desfeita.</p><p>Recomendamos exportar um backup antes de continuar.</p><div className="modal-actions"><button className="button button-ghost" onClick={() => setResetOpen(false)}>Cancelar</button><button className="button button-danger" onClick={() => { resetWorkspace(); setResetOpen(false); }}>Sim, restaurar</button></div></div>
      </Modal>
    </div>
  );
}
