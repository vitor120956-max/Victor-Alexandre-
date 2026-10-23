import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { Modal } from './Modal';
import { useApp } from '../context/AppContext';
import { todayISO } from '../lib/utils';
import type { Priority } from '../types';

export function TaskModal() {
  const { taskModalOpen, closeTaskModal, addTask, pushToast } = useApp();
  const [title, setTitle] = useState('');
  const [project, setProject] = useState('JARVIS');
  const [priority, setPriority] = useState<Priority>('media');
  const [dueDate, setDueDate] = useState(todayISO());

  const close = () => {
    setTitle('');
    closeTaskModal();
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim()) return;
    addTask({ title, project, priority, dueDate });
    pushToast('Tarefa adicionada', title.trim());
    close();
  };

  return (
    <Modal open={taskModalOpen} onClose={close} title="Nova tarefa" eyebrow="PLANEJAR PRÓXIMO PASSO">
      <form className="form-stack" onSubmit={submit}>
        <label className="field">
          <span>O que precisa ser feito?</span>
          <input autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Ex.: Revisar o próximo módulo" maxLength={140} required />
        </label>
        <div className="field-row">
          <label className="field">
            <span>Projeto</span>
            <input value={project} onChange={(event) => setProject(event.target.value)} placeholder="Pessoal" maxLength={40} />
          </label>
          <label className="field">
            <span>Prazo</span>
            <input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} required />
          </label>
        </div>
        <fieldset className="field priority-field">
          <span>Prioridade</span>
          <div className="segmented-control">
            {(['baixa', 'media', 'alta'] as Priority[]).map((value) => (
              <button type="button" key={value} className={priority === value ? 'selected' : ''} onClick={() => setPriority(value)}>
                {value === 'media' ? 'Média' : value[0].toUpperCase() + value.slice(1)}
              </button>
            ))}
          </div>
        </fieldset>
        <div className="modal-actions">
          <button type="button" className="button button-ghost" onClick={close}>Cancelar</button>
          <button type="submit" className="button button-primary" disabled={!title.trim()}>
            Criar tarefa <ArrowRight size={17} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
