import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { Badge, CrudPage } from '../components/ui';
import { fmtDate, ROLES } from '../dicts';
import Hint from '../components/Hint';

/* ------------------------------------------ Пользователи (11.13 ТЗ) */
export function UsersPage() {
  return (
    <CrudPage
      title={<>Пользователи<Hint id="users" /></>}
      endpoint="/api/users"
      canEdit
      canDelete={false}  /* пользователей не удаляем — отключаем (14.2.6) */
      emptyText="Пользователей нет."
      columns={[
        { key: 'name', label: 'Имя' },
        { key: 'email', label: 'Email' },
        { key: 'role', label: 'Роль', render: (r) => ROLES[r.role] || r.role },
        { key: 'is_active', label: 'Статус', render: (r) => (
            <Badge map={{ true: { label: 'Активен', tone: 'green' }, false: { label: 'Отключён', tone: 'gray' } }}
                   value={String(r.is_active)} />) },
        { key: 'last_login_at', label: 'Последний вход', render: (r) => fmtDate(r.last_login_at) },
      ]}
      fields={[
        { name: 'name', label: 'Имя', required: true },
        { name: 'email', label: 'Email', type: 'email', required: true },
        { name: 'role', label: 'Роль', type: 'select', options: ROLES, default: 'editor', required: true },
        { name: 'password', label: 'Пароль (мин. 10 символов; при редактировании — оставьте пустым)', type: 'password', minLength: 10 },
        { name: 'is_active', label: 'Активен', type: 'checkbox' },
      ]}
    />
  );
}

/* ------------------------------- Безопасность и логи (11.13 ТЗ) */
export function SecurityPage() {
  const [rows, setRows] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/api/audit?limit=200').then(setRows).catch((e) => setError(e.message));
    api('/api/health').then(setHealth).catch(() => setHealth({ status: 'error', database: 'error' }));
  }, []);

  const ACTION = {
    login: { label: 'Вход', tone: 'green' },
    logout: { label: 'Выход', tone: 'gray' },
    login_failed: { label: 'Ошибка входа', tone: 'red' },
    login_blocked: { label: 'Вход заблокирован', tone: 'red' },
    create: { label: 'Создание', tone: 'blue' },
    update: { label: 'Изменение', tone: 'blue' },
    delete: { label: 'Удаление', tone: 'yellow' },
    status_change: { label: 'Смена статуса', tone: 'blue' },
  };

  return (
    <>
      <div className="page-head"><h1>Безопасность и логи<Hint id="security" /></h1></div>
      {health && (
        <div className="cards">
          <div className="card">
            <div className="num">{health.status === 'ok' ? 'OK' : 'Сбой'}</div>
            <div className="cap">Healthcheck сервиса</div>
          </div>
          <div className="card">
            <div className="num">{health.database === 'ok' ? 'OK' : 'Сбой'}</div>
            <div className="cap">База данных</div>
          </div>
        </div>
      )}
      {error && <div className="error-box">{error}</div>}
      <div className="table-wrap">
        {rows === null ? <div className="empty">Загрузка…</div>
        : rows.length === 0 ? <div className="empty">Журнал пуст.</div>
        : (
          <table>
            <thead>
              <tr><th>Время</th><th>Пользователь</th><th>Действие</th><th>Детали</th><th>IP</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{fmtDate(r.created_at)}</td>
                  <td>{r.user_email || '—'}</td>
                  <td><Badge map={ACTION} value={r.action} /></td>
                  <td>{r.detail || (r.entity ? `${r.entity} №${r.entity_id}` : '—')}</td>
                  <td className="muted">{r.ip || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
