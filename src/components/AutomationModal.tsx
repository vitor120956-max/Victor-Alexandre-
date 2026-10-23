import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { Modal } from './Modal';
import { useApp } from '../context/AppContext';
import type { AutomationAction, AutomationFrequency } from '../types';

export function AutomationModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { createAutomation } = useApp();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [action, setAction] = useState<AutomationAction>('summary');
  const [frequency, setFrequency] = useState<AutomationFrequency>('manual');
  const [time, setTime] = useState('08:00');
  const [weekday, setWeekday] = useState(1);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    createAutomation({ name, description, action, schedule: { frequency, time, weekday } });
    setName('');
    setDescription('');
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title="Nova automação" eyebrow="CRIAR ROTINA LOCAL">
      <form className="form-stack" onSubmit={submit}>
        <label className="field"><span>Nome da automação</span><input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="Ex.: Preparar minha manhã" required maxLength={70} /></label>
        <label className="field"><span>Descrição <small>opcional</small></span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="O que esta rotina deve fazer?" rows={2} maxLength={180} /></label>
        <label className="field"><span>Ação executada</span><select value={action} onChange={(event) => setAction(event.target.value as AutomationAction)}><option value="summary">Gerar resumo de tarefas e foco</option><option value="organize">Organizar tarefas por prioridade</option><option value="focus">Iniciar foco de 25 minutos</option><option value="backup">Exportar backup em JSON</option></select></label>
        <div className="field-row">
          <label className="field"><span>Frequência</span><select value={frequency} onChange={(event) => setFrequency(event.target.value as AutomationFrequency)}><option value="manual">Somente manual</option><option value="daily">Todos os dias</option><option value="weekly">Toda semana</option></select></label>
          {frequency !== 'manual' && <label className="field"><span>Horário</span><input type="time" value={time} onChange={(event) => setTime(event.target.value)} required /></label>}
          {frequency === 'weekly' && <label className="field"><span>Dia</span><select value={weekday} onChange={(event) => setWeekday(Number(event.target.value))}><option value={1}>Segunda</option><option value={2}>Terça</option><option value={3}>Quarta</option><option value={4}>Quinta</option><option value={5}>Sexta</option><option value={6}>Sábado</option><option value={0}>Domingo</option></select></label>}
        </div>
        <p className="form-note">Rotinas agendadas são verificadas enquanto o aplicativo estiver aberto. A execução manual sempre fica disponível.</p>
        <div className="modal-actions"><button type="button" className="button button-ghost" onClick={onClose}>Cancelar</button><button type="submit" className="button button-primary" disabled={!name.trim()}>Criar automação <ArrowRight size={17} /></button></div>
      </form>
    </Modal>
  );
}
