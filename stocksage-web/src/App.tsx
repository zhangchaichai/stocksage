import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import { useAuthStore } from './stores/authStore';
import RequireAuth from './components/RequireAuth';
import AppLayout from './components/AppLayout';
import LoginPage from './pages/Auth/LoginPage';
import RegisterPage from './pages/Auth/RegisterPage';
import DashboardPage from './pages/Dashboard/DashboardPage';
import WorkflowListPage from './pages/Workflows/WorkflowListPage';
import WorkflowBuilderPage from './pages/WorkflowBuilder/WorkflowBuilderPage';
import SkillsPage from './pages/Skills/SkillsPage';
import RunListPage from './pages/Runs/RunListPage';
import RunDetailPage from './pages/Runs/RunDetailPage';
import SettingsPage from './pages/Settings/SettingsPage';
import MarketplacePage from './pages/Marketplace/MarketplacePage';
import TemplateGalleryPage from './pages/Gallery/TemplateGalleryPage';
import UsageDashboardPage from './pages/Usage/UsageDashboardPage';
import PortfolioPage from './pages/Portfolio/PortfolioPage';
import MemoryPage from './pages/Memory/MemoryPage';
import BacktestDashboardPage from './pages/Backtest/BacktestDashboardPage';
import BacktestDetailPage from './pages/Backtest/BacktestDetailPage';
import EvolutionPage from './pages/Evolution/EvolutionPage';
import IndicatorDashboardPage from './pages/Indicators/IndicatorDashboardPage';
import ScreenerPage from './pages/Screener/ScreenerPage';
import SchedulerPage from './pages/Scheduler/SchedulerPage';
import ScreenerBacktestPage from './pages/ScreenerBacktest/ScreenerBacktestPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

const AppRoutes: React.FC = () => {
  const { init } = useAuthStore();

  useEffect(() => {
    init();
  }, [init]);

  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Protected routes */}
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/workflows" element={<WorkflowListPage />} />
        <Route path="/workflows/new" element={<WorkflowBuilderPage />} />
        <Route path="/workflows/:id/edit" element={<WorkflowBuilderPage />} />
        <Route path="/skills" element={<SkillsPage />} />
        <Route path="/runs" element={<RunListPage />} />
        <Route path="/runs/:id" element={<RunDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/marketplace" element={<MarketplacePage />} />
        <Route path="/gallery" element={<TemplateGalleryPage />} />
        <Route path="/usage" element={<UsageDashboardPage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/memory" element={<MemoryPage />} />
        <Route path="/backtest" element={<BacktestDashboardPage />} />
        <Route path="/backtest/:id" element={<BacktestDetailPage />} />
        <Route path="/evolution" element={<EvolutionPage />} />
        <Route path="/indicators" element={<IndicatorDashboardPage />} />
        <Route path="/screener" element={<ScreenerPage />} />
        <Route path="/scheduler" element={<SchedulerPage />} />
        <Route path="/screener-backtest" element={<ScreenerBacktestPage />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

const App: React.FC = () => {
  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
        },
      }}
    >
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  );
};

export default App;
