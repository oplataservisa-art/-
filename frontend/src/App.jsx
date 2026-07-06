import React, { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { api, clearToken, getToken } from './api';
import Layout from './components/Layout';
import { SecurityPage, UsersPage } from './pages/Admin';
import { ArticlePage, ArticlesPage } from './pages/Articles';
import Dashboard from './pages/Dashboard';
import CalendarPage from './pages/Calendar';
import { KnowledgePage, SourcesPage, TopicsPage } from './pages/Directories';
import InfoEventsPage from './pages/InfoEvents';
import Login from './pages/Login';
import PromptsPage from './pages/Prompts';
import HelpPage from './pages/Help';
import MaterialsPage from './pages/Materials';
import ChannelsPage from './pages/Channels';
import SourceCardPage from './pages/SourceCard';

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) { setLoading(false); return; }
    api('/api/auth/me')
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, []);

  const logout = async () => {
    try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* журналирование, не критично */ }
    clearToken();
    setUser(null);
  };

  if (loading) return <div className="empty">Загрузка…</div>;

  if (!user) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<Login onLogin={setUser} />} />
        </Routes>
      </BrowserRouter>
    );
  }

  const adminOnly = (el) => (user.role === 'admin' ? el : <Navigate to="/" replace />);

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout user={user} onLogout={logout} />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/sources" element={<SourcesPage user={user} />} />
          <Route path="/info-events" element={<InfoEventsPage user={user} />} />
          <Route path="/topics" element={<TopicsPage user={user} />} />
          <Route path="/articles" element={<ArticlesPage user={user} />} />
          <Route path="/articles/:id" element={<ArticlePage user={user} />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/channels" element={<ChannelsPage />} />
          <Route path="/materials" element={<MaterialsPage user={user} />} />
          <Route path="/sources/:id" element={<SourceCardPage user={user} />} />
          <Route path="/help" element={<HelpPage user={user} />} />
          <Route path="/prompts" element={<PromptsPage user={user} />} />
          <Route path="/knowledge" element={<KnowledgePage user={user} />} />
          <Route path="/users" element={adminOnly(<UsersPage />)} />
          <Route path="/security" element={adminOnly(<SecurityPage />)} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
