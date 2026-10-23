import { useState } from 'react';
import { Bell, BrainCircuit, Check, Database, Download, Mic2, Palette, RotateCcw, ShieldCheck, UserRound, Volume2 } from 'lucide-react';
import { Modal } from '../components/Modal';
import { useApp } from '../context/AppContext';
import type { Preferences } from '../types';

export function SettingsPage() {
  const { preferences, updatePreferences, exportBackup, resetWorkspace, pushToast, aiStatus, backendOnline } = useApp();
  const [resetOpen, setResetOpen] = useState(false);

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
            {!aiStatus.configured && <p className="ai-config-note">Para ativar, defina <code>JARVIS_AI_API_KEY</code>, <code>JARVIS_AI_MODEL</code> e o endpoint compatível no arquivo <code>.env</code> do servidor. Não cole chaves no chat ou nesta tela.</p>}
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
          <section className="panel about-card"><div><span>VERSÃO</span><strong>0.5.0</strong></div><div><span>NÚCLEO</span><strong>React + Python</strong></div><div><span>IDIOMA</span><strong>Português (BR)</strong></div></section>
          <button className="reset-button" onClick={() => setResetOpen(true)}><RotateCcw size={16} /> Restaurar dados de exemplo</button>
        </aside>
      </div>
      <Modal open={resetOpen} onClose={() => setResetOpen(false)} title="Restaurar o núcleo?" eyebrow="AÇÃO DESTRUTIVA">
        <div className="reset-confirm"><p>Suas tarefas, notas, conversas e preferências atuais serão substituídas pelos dados iniciais. Essa ação não pode ser desfeita.</p><p>Recomendamos exportar um backup antes de continuar.</p><div className="modal-actions"><button className="button button-ghost" onClick={() => setResetOpen(false)}>Cancelar</button><button className="button button-danger" onClick={() => { resetWorkspace(); setResetOpen(false); }}>Sim, restaurar</button></div></div>
      </Modal>
    </div>
  );
}
