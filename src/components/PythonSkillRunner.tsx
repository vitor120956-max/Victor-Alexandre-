import { useEffect, useState } from 'react';
import { Check, Clipboard, Code2, Download, Play, ShieldAlert } from 'lucide-react';
import { Modal } from './Modal';
import { useApp } from '../context/AppContext';
import { normalizeSkillParameters } from '../lib/api';
import type { PythonSkill, SchemaProperty, SkillExecution } from '../lib/api';

function initialParameters(skill: PythonSkill | null): Record<string, unknown> {
  if (!skill) return {};
  return Object.fromEntries(Object.entries(skill.inputSchema.properties).map(([name, property]) => {
    if (property.default !== undefined) return [name, property.default];
    if (property.type === 'boolean') return [name, false];
    if (property.enum?.length) return [name, property.enum[0]];
    return [name, ''];
  }));
}

function resultText(execution: SkillExecution): string {
  if (!execution.result) return '';
  const result = execution.result;
  if (typeof result.content === 'string') return result.content;
  if (typeof result.text === 'string') return result.text;
  if (typeof result.markdown === 'string') return result.markdown;
  if (Array.isArray(result.winners)) return `Sorteados: ${result.winners.join(', ')}`;
  if (typeof result.result === 'string') return result.result;
  return JSON.stringify(result, null, 2);
}

export function PythonSkillRunner({ skill, onClose }: { skill: PythonSkill | null; onClose: () => void }) {
  const { executeSkill, pushToast } = useApp();
  const [parameters, setParameters] = useState<Record<string, unknown>>({});
  const [dryRun, setDryRun] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [running, setRunning] = useState(false);
  const [execution, setExecution] = useState<SkillExecution | null>(null);
  const [requestError, setRequestError] = useState('');

  useEffect(() => {
    setParameters(initialParameters(skill));
    setDryRun(Boolean(skill?.sideEffects));
    setConfirmed(false);
    setExecution(null);
    setRequestError('');
  }, [skill]);

  const update = (name: string, value: unknown) => {
    setParameters((current) => ({ ...current, [name]: value }));
    setExecution(null);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!skill || running) return;
    setExecution(null);
    setRequestError('');
    let normalizedParameters: Record<string, unknown>;
    try {
      normalizedParameters = normalizeSkillParameters(skill, parameters);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : 'Parâmetro numérico inválido.');
      return;
    }
    setRunning(true);
    try {
      const response = await executeSkill(skill.id, normalizedParameters, { dryRun, confirmed });
      setExecution(response);
      if (response.ok) pushToast(dryRun ? 'Simulação concluída' : 'Skill Python executada', skill.name);
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : 'Falha ao executar a skill.');
    } finally {
      setRunning(false);
    }
  };

  const copyResult = async () => {
    if (!execution) return;
    try {
      await navigator.clipboard.writeText(resultText(execution));
      pushToast('Resultado copiado');
    } catch {
      pushToast('Não foi possível copiar', 'Selecione o texto do resultado manualmente.', 'warning');
    }
  };

  const renderField = (name: string, property: SchemaProperty) => {
    const required = skill?.inputSchema.required?.includes(name) ?? false;
    const value = parameters[name];
    const label = property.title ?? name;
    if (property.type === 'boolean') {
      return <label className="python-boolean-field" key={name}><input type="checkbox" checked={Boolean(value)} onChange={(event) => update(name, event.target.checked)} /><span>{label}</span></label>;
    }
    return (
      <label className="field" key={name}>
        <span>{label}{required ? ' *' : ''}</span>
        {property.enum ? (
          <select value={String(value ?? '')} onChange={(event) => update(name, event.target.value)} required={required}>
            {property.enum.map((option, index) => <option key={option} value={option}>{property.enumLabels?.[index] ?? option}</option>)}
          </select>
        ) : property.format === 'textarea' ? (
          <textarea value={String(value ?? '')} onChange={(event) => update(name, event.target.value)} rows={5} maxLength={property.maxLength} required={required} placeholder={property.description} />
        ) : (
          <input
            type={property.type === 'integer' || property.type === 'number' ? 'number' : 'text'}
            step={property.type === 'number' ? 'any' : property.type === 'integer' ? 1 : undefined}
            value={String(value ?? '')}
            onChange={(event) => update(name, event.target.value)}
            maxLength={property.maxLength}
            required={required}
            placeholder={property.description}
          />
        )}
        {property.description && property.format !== 'textarea' && <small className="field-description">{property.description}</small>}
      </label>
    );
  };

  return (
    <Modal open={Boolean(skill)} onClose={onClose} title={skill?.name ?? ''} eyebrow="SKILL PYTHON · API LOCAL" className="python-runner-modal">
      {skill && (
        <div className="python-runner">
          <div className="python-runner-intro"><span><Code2 size={18} /></span><div><strong>{skill.id}</strong><p>{skill.description}</p></div></div>
          <form onSubmit={submit} className="form-stack">
            {Object.entries(skill.inputSchema.properties).map(([name, property]) => renderField(name, property))}
            {Object.keys(skill.inputSchema.properties).length === 0 && <p className="form-note">Esta skill não precisa de parâmetros. A execução consultará o núcleo Python diretamente.</p>}
            {skill.dryRunSupported && <div className="setting-row dry-run-row"><div><strong>Modo de simulação</strong><p>Valida tudo e mostra o que seria feito, sem gravar alterações.</p></div><button type="button" className={`switch ${dryRun ? 'switch-on' : ''}`} role="switch" aria-checked={dryRun} onClick={() => { setDryRun((value) => !value); setExecution(null); }}><span /></button></div>}
            {skill.requiresConfirmation && !dryRun && <label className="confirmation-box"><ShieldAlert size={18} /><span>Revise os parâmetros e confirme a gravação na área isolada do JARVIS.</span><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /></label>}
            {requestError && <div className="execution-error">{requestError}</div>}
            <div className="modal-actions"><button type="button" className="button button-ghost" onClick={onClose}>Fechar</button><button type="submit" className="button button-primary" disabled={running || (skill.requiresConfirmation && !dryRun && !confirmed)}><Play size={15} />{running ? 'Executando...' : dryRun ? 'Simular skill' : skill.requiresConfirmation ? 'Confirmar e executar' : 'Executar skill'}</button></div>
          </form>
          {execution && (
            <div className={execution.ok ? 'execution-result' : 'execution-result execution-refused'}>
              <div className="execution-result-heading"><span>{execution.ok ? <Check size={15} /> : <ShieldAlert size={15} />}{execution.ok ? execution.dryRun ? 'Simulação concluída' : 'Resultado da execução' : 'Execução recusada'}</span>{execution.durationMs !== undefined && <small>{execution.durationMs} ms</small>}</div>
              {execution.error && <p>{execution.error.message}</p>}
              {execution.ok && <><pre>{resultText(execution)}</pre><div className="execution-result-actions"><button className="copy-result" onClick={copyResult}><Clipboard size={14} /> Copiar resultado</button>{typeof execution.result?.downloadUrl === 'string' && <a className="copy-result" href={execution.result.downloadUrl} download><Download size={14} /> Baixar arquivo</a>}</div></>}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
