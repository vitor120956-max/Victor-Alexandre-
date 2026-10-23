import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { ChatPage } from './pages/ChatPage';
import { TasksPage } from './pages/TasksPage';
import { AutomationsPage } from './pages/AutomationsPage';
import { MemoryPage } from './pages/MemoryPage';
import { LegalPage } from './pages/LegalPage';
import { DocumentsPage } from './pages/DocumentsPage';
import { EngineeringPage } from './pages/EngineeringPage';
import { PlanningPage } from './pages/PlanningPage';
import { ReversePage } from './pages/ReversePage';
import { LeanPage } from './pages/LeanPage';
import { AgencyPage } from './pages/AgencyPage';
import { EstudioPage } from './pages/EstudioPage';
import { TastePage } from './pages/TastePage';
import { DiagramPage } from './pages/DiagramPage';
import { SkillsPage } from './pages/SkillsPage';
import { SettingsPage } from './pages/SettingsPage';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="conversa" element={<ChatPage />} />
        <Route path="tarefas" element={<TasksPage />} />
        <Route path="automacoes" element={<AutomationsPage />} />
        <Route path="memoria" element={<MemoryPage />} />
        <Route path="leis" element={<LegalPage />} />
        <Route path="documentos" element={<DocumentsPage />} />
        <Route path="engenharia" element={<EngineeringPage />} />
        <Route path="planejamento" element={<PlanningPage />} />
        <Route path="reversa" element={<ReversePage />} />
        <Route path="lean" element={<LeanPage />} />
        <Route path="agencia" element={<AgencyPage />} />
        <Route path="estudio" element={<EstudioPage />} />
        <Route path="direcao" element={<TastePage />} />
        <Route path="diagramas" element={<DiagramPage />} />
        <Route path="skills" element={<SkillsPage />} />
        <Route path="configuracoes" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
