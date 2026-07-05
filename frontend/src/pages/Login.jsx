import React, { useState } from 'react';
import { api, setToken } from '../api';

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const data = await api('/api/auth/login', { method: 'POST', body: { email, password } });
      setToken(data.access_token);
      const me = await api('/api/auth/me');
      onLogin(me);
    } catch (err) {
      setError(err.message || 'Не удалось войти');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="login-box" onSubmit={submit}>
        <h1>EFFEСOM · Контент-сервис</h1>
        <p>Вход для сотрудников</p>
        {error && <div className="error-box">{error}</div>}
        <label className="field">
          <span>Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            autoComplete="username" required />
        </label>
        <label className="field">
          <span>Пароль</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password" required />
        </label>
        <button type="submit" disabled={busy}>{busy ? 'Вход…' : 'Войти'}</button>
      </form>
    </div>
  );
}
