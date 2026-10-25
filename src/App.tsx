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
import { CuradoriaPage } from './pages/CuradoriaPage';
import { MarketingPage } from './pages/MarketingPage';
import { CienciaPage } from './pages/CienciaPage';
import { ConfiancaPage } from './pages/ConfiancaPage';
import { ContextoPage } from './pages/ContextoPage';
import { SelecaoPage } from './pages/SelecaoPage';
import { RevisaoPage } from './pages/RevisaoPage';
import { SubmissaoPage } from './pages/SubmissaoPage';
import { MemoriaPage } from './pages/MemoriaPage';
import { PortabilidadePage } from './pages/PortabilidadePage';
import { ContinuidadePage } from './pages/ContinuidadePage';
import { SistemaPage } from './pages/SistemaPage';
import { EvolucaoPage } from './pages/EvolucaoPage';
import { DistilarPage } from './pages/DistilarPage';
import { CareerPage } from './pages/CareerPage';
import { NavegadorPage } from './pages/NavegadorPage';
import { EscritorioPage } from './pages/EscritorioPage';
import { EstacaoPage } from './pages/EstacaoPage';
import { SkillsPage } from './pages/SkillsPage';
import { AgentePage } from './pages/AgentePage';
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
        <Route path="curadoria" element={<CuradoriaPage />} />
        <Route path="marketing" element={<MarketingPage />} />
        <Route path="ciencia" element={<CienciaPage />} />
        <Route path="confianca" element={<ConfiancaPage />} />
        <Route path="contexto" element={<ContextoPage />} />
        <Route path="selecao" element={<SelecaoPage />} />
        <Route path="revisao" element={<RevisaoPage />} />
        <Route path="submissao" element={<SubmissaoPage />} />
        <Route path="memoria-ia" element={<MemoriaPage />} />
        <Route path="portabilidade" element={<PortabilidadePage />} />
        <Route path="continuidade" element={<ContinuidadePage />} />
        <Route path="sistema" element={<SistemaPage />} />
        <Route path="evolucao" element={<EvolucaoPage />} />
        <Route path="pessoa" element={<DistilarPage />} />
        <Route path="carreira" element={<CareerPage />} />
        <Route path="navegador" element={<NavegadorPage />} />
        <Route path="escritorio" element={<EscritorioPage />} />
        <Route path="estacao" element={<EstacaoPage />} />
        <Route path="skills" element={<SkillsPage />} />
        <Route path="agente" element={<AgentePage />} />
        <Route path="configuracoes" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
