import React from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, Typography, Space, Select } from 'antd';
import {
  DashboardOutlined,
  ApartmentOutlined,
  ThunderboltOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  LogoutOutlined,
  ShopOutlined,
  AppstoreOutlined,
  BarChartOutlined,
  FundOutlined,
  DatabaseOutlined,
  AuditOutlined,
  RocketOutlined,
  LineChartOutlined,
  FilterOutlined,
  ClockCircleOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '../stores/authStore';
import { useI18n } from '../i18n';
import ChatDrawer from './ChatDrawer/ChatDrawer';

const { Header, Sider, Content } = Layout;

const AppLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const { locale, setLocale, t } = useI18n();

  const menuItems = [
    { key: '/', icon: <DashboardOutlined />, label: t.nav.dashboard },
    { key: '/workflows', icon: <ApartmentOutlined />, label: t.nav.workflows },
    { key: '/skills', icon: <ThunderboltOutlined />, label: t.nav.skills },
    { key: '/runs', icon: <PlayCircleOutlined />, label: t.nav.runs },
    { key: '/marketplace', icon: <ShopOutlined />, label: t.nav.marketplace },
    { key: '/gallery', icon: <AppstoreOutlined />, label: t.nav.gallery },
    { key: '/portfolio', icon: <FundOutlined />, label: t.nav.portfolio },
    { key: '/indicators', icon: <LineChartOutlined />, label: t.nav.indicators },
    { key: '/screener', icon: <FilterOutlined />, label: t.nav.screener },
    { key: '/screener-backtest', icon: <ExperimentOutlined />, label: t.nav.screenerBacktest },
    { key: '/backtest', icon: <AuditOutlined />, label: t.nav.backtest },
    { key: '/evolution', icon: <RocketOutlined />, label: t.nav.evolution },
    { key: '/memory', icon: <DatabaseOutlined />, label: t.nav.memory },
    { key: '/scheduler', icon: <ClockCircleOutlined />, label: t.nav.scheduler },
    { key: '/usage', icon: <BarChartOutlined />, label: t.nav.usage },
    { key: '/settings', icon: <SettingOutlined />, label: t.nav.settings },
  ];

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="dark">
        <div style={{ padding: '16px 24px', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
          <Typography.Title level={4} style={{ color: '#fff', margin: 0 }}>
            StockSage
          </Typography.Title>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ marginTop: 8 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <Space>
            <Select
              value={locale}
              onChange={setLocale}
              size="small"
              options={[
                { value: 'en', label: 'EN' },
                { value: 'zh', label: '中文' },
              ]}
              style={{ width: 80 }}
            />
            <Typography.Text>{user?.username}</Typography.Text>
            <Button icon={<LogoutOutlined />} type="text" onClick={handleLogout}>
              {t.auth.logout}
            </Button>
          </Space>
        </Header>
        <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8 }}>
          <Outlet />
        </Content>
      </Layout>
      <ChatDrawer />
    </Layout>
  );
};

export default AppLayout;
