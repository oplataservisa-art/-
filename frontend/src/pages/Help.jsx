import React, { useState } from 'react';
import { HELP_SECTIONS } from '../content/help';
import { useHints } from '../components/hints';

/* Stage 3.2: справочная страница. Весь контент — статический,
   из content/help.js; ни запросов к backend, ни AI здесь нет. */

export default function HelpPage({ user }) {
  const [active, setActive] = useState(HELP_SECTIONS[0].id);
  const [hints, setHints] = useHints();
  const section = HELP_SECTIONS.find((s) => s.id === active) || HELP_SECTIONS[0];

  return (
    <div>
      <div className="page-head"><h1>Помощь</h1></div>
      <div className="panel" style={{ marginBottom: 16 }}>
        <label className="hints-toggle">
          <input type="checkbox" checked={hints}
            onChange={(e) => setHints(e.target.checked)} />
          <span>
            Показывать подсказки «?» на экранах — короткие пояснения рядом
            с ключевыми блоками. Настройка личная, хранится в этом браузере.
          </span>
        </label>
      </div>
      <div className="help-layout">
        <nav className="help-nav panel">
          {HELP_SECTIONS.map((s) => (
            <button key={s.id} type="button"
              className={s.id === active ? 'active' : ''}
              onClick={() => setActive(s.id)}>
              {s.title}
            </button>
          ))}
        </nav>
        <div className="help-body panel">
          <h2>{section.title}</h2>
          {(section.body || []).map((p, i) => <p key={i}>{p}</p>)}

          {section.roles && (
            <table className="help-table">
              <thead><tr><th>Роль</th><th>Что делает</th></tr></thead>
              <tbody>
                {section.roles.map(([role, what]) => (
                  <tr key={role} className={roleMatches(role, user) ? 'help-me' : ''}>
                    <td>{role}{roleMatches(role, user) ? ' — это вы' : ''}</td>
                    <td>{what}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {section.statuses && (
            <table className="help-table">
              <thead><tr><th>Статус</th><th>Что означает</th></tr></thead>
              <tbody>
                {section.statuses.map(([name, meaning]) => (
                  <tr key={name}><td>{name}</td><td>{meaning}</td></tr>
                ))}
              </tbody>
            </table>
          )}

          {section.errors && (
            <div>
              {section.errors.map(([msg, action]) => (
                <div key={msg} className="help-error">
                  <div className="help-error-msg">{msg}</div>
                  <div>{action}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const ROLE_BY_LABEL = {
  'Администратор': 'admin',
  'Редактор': 'editor',
  'Эксперт': 'expert',
  'Контент-менеджер': 'content_manager',
  'Руководитель': 'manager',
};

function roleMatches(label, user) {
  return user && ROLE_BY_LABEL[label] === user.role;
}
