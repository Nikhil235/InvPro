import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { DashboardHome } from './components/views/DashboardHome';
import { JournalView } from './components/views/JournalView';
import { LogsView } from './components/views/LogsView';
import { SignalsView } from './components/views/SignalsView';
import { SettingsView } from './components/views/SettingsView';
import { PaperTradesView } from './components/views/PaperTradesView';
import { PerformanceView } from './components/views/PerformanceView';
import { RiskView } from './components/views/RiskView';
import { AlertsView } from './components/views/AlertsView';
import { LiveDataProvider } from './contexts/LiveDataContext';

// Placeholder views until implemented
const Placeholder = ({ title }) => (
  <div className="flex h-full items-center justify-center text-secondary">
    <h1 className="text-2xl font-bold">{title} View (Under Construction)</h1>
  </div>
);

function App() {
  return (
    <LiveDataProvider>
      <Router>
        <DashboardLayout>
          <Routes>
            <Route path="/" element={<DashboardHome />} />
            <Route path="/signals" element={<SignalsView />} />
            <Route path="/trades" element={<PaperTradesView />} />
            <Route path="/journal" element={<JournalView />} />
            <Route path="/performance" element={<PerformanceView />} />
            <Route path="/risk" element={<RiskView />} />
            <Route path="/alerts" element={<AlertsView />} />
            <Route path="/logs" element={<LogsView />} />
            <Route path="/settings" element={<SettingsView />} />
          </Routes>


        </DashboardLayout>
      </Router>
    </LiveDataProvider>
  );
}

export default App;
