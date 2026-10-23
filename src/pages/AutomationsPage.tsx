import { useState } from 'react';
import { Info, Plus, Workflow } from 'lucide-react';
import { ActivityFeed } from '../components/ActivityFeed';
import { AutomationCard } from '../components/AutomationCard';
import { AutomationModal } from '../components/AutomationModal';
import { useApp } from '../context/AppContext';

export function AutomationsPage() {
  const { automations, activities } = useApp();
  const [modalOpen, setModalOpen] = useState(false);
  const enabled = automations.filter((automation) => automation.enabled).length;
  const executions = activities.filter((activity) => activity.kind === 'automation').length;

  return (
    <div className="automations-page">
      <header className="page-heading">
        <div><span className="eyebrow">ROTINAS E GATILHOS</span><h1>Automações<span>.</span></h1><p>Delegue o repetitivo. Mantenha o controle das decisões.</p></div>
        <button className="button button-primary" onClick={() => setModalOpen(true)}><Plus size={17} /> Nova automação</button>
      </header>
      <div className="local-notice"><Info size={17} /><div><strong>Agenda local, sem promessas ocultas.</strong><span>As rotinas são verificadas enquanto esta página estiver aberta no navegador. Nenhuma publicação externa é feita automaticamente.</span></div><span className="local-badge"><i /> {enabled} ATIVAS</span></div>
      <div className="automation-page-layout">
        <div>
          <div className="automation-summary"><span><Workflow size={16} /> {automations.length} rotinas configuradas</span><span>{executions} execuções registradas</span></div>
          <div className="automation-grid">
            {automations.map((automation) => <AutomationCard key={automation.id} automation={automation} />)}
          </div>
        </div>
        <aside className="panel automation-history">
          <div className="section-heading compact-heading"><div><span className="eyebrow">AUDITORIA</span><h2>Atividade recente</h2></div></div>
          <ActivityFeed limit={9} />
        </aside>
      </div>
      <AutomationModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}
