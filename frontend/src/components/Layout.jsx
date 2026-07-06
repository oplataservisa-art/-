import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { ROLES } from '../dicts';
import { useHints } from './hints';

// Разделы меню и роли, которым они доступны (11.2 ТЗ: показывать только доступное).
const NAV = [
  { to: '/', label: 'Дашборд', roles: ['admin', 'editor', 'expert', 'content_manager', 'manager'] },
  { to: '/sources', label: 'Источники', roles: ['admin', 'editor', 'expert'] },
  { to: '/materials', label: 'Материалы', roles: ['admin', 'editor', 'expert', 'content_manager', 'manager'] },
  { to: '/info-events', label: 'Инфоповоды', roles: ['admin', 'editor', 'expert', 'manager'] },
  { to: '/topics', label: 'Темы', roles: ['admin', 'editor', 'expert', 'manager'] },
  { to: '/articles', label: 'Статьи', roles: ['admin', 'editor', 'expert', 'content_manager', 'manager'] },
  { to: '/calendar', label: 'Календарь', roles: ['admin', 'editor', 'expert', 'content_manager', 'manager'] },
  { to: '/channels', label: 'Каналы', roles: ['admin', 'content_manager', 'manager'] },
  { to: '/knowledge', label: 'База знаний', roles: ['admin', 'editor', 'expert', 'content_manager'] },
  { to: '/prompts', label: 'Промпты', roles: ['admin', 'editor'] },
  { to: '/users', label: 'Пользователи', roles: ['admin'] },
  { to: '/security', label: 'Безопасность и логи', roles: ['admin'] },
  { to: '/help', label: 'Помощь', roles: ['admin', 'editor', 'expert', 'content_manager', 'manager'] },
];

export default function Layout({ user, onLogout }) {
  const items = NAV.filter((n) => n.roles.includes(user.role));
  const [hints, setHints] = useHints();
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">EFFEСOM<small>Контент-сервис</small></div>
        <nav>
          {items.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'}
              className={({ isActive }) => (isActive ? 'active' : '')}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <label className="sidebar-foot" title="Короткие подсказки «?» на экранах">
          <input type="checkbox" checked={hints}
            onChange={(e) => setHints(e.target.checked)} />
          <span>Подсказки</span>
        </label>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="user"><b>{user.name}</b> · {ROLES[user.role] || user.role}</div>
          <button className="secondary small" onClick={onLogout}>Выйти</button>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
