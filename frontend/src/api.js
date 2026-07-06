// API-клиент. Токен хранится в sessionStorage (живёт до закрытия вкладки).
// Сессия: токен истекает через ACCESS_TOKEN_MINUTES неактивности, но при
// работе продлевается автоматически (см. maybeRefresh) вплоть до абсолютного
// предела SESSION_MAX_HOURS. При 401 пользователь отправляется на вход.
const TOKEN_KEY = 'effecom_token';
const REFRESH_BEFORE_MS = 10 * 60 * 1000; // продлеваем за 10 минут до истечения

export const getToken = () => sessionStorage.getItem(TOKEN_KEY);
export const setToken = (t) => sessionStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => sessionStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
  }
}

function tokenPayload(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

let refreshInFlight = null;

/* Скользящее продление: если токен скоро истечёт — обновляем его одним
   запросом на все параллельные вызовы api(). Ошибки продления не фатальны:
   запрос уйдёт со старым токеном и при необходимости получит честный 401. */
async function maybeRefresh() {
  const token = getToken();
  if (!token) return;
  const payload = tokenPayload(token);
  if (!payload || !payload.exp) return;
  const msLeft = payload.exp * 1000 - Date.now();
  if (msLeft <= 0 || msLeft > REFRESH_BEFORE_MS) return;

  refreshInFlight = refreshInFlight || fetch('/api/auth/refresh', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => { if (d && d.access_token) setToken(d.access_token); })
    .catch(() => { /* продлить не удалось — обработает обычный 401 */ })
    .finally(() => { refreshInFlight = null; });
  await refreshInFlight;
}

export async function api(path, { method = 'GET', body } = {}) {
  if (!path.startsWith('/api/auth/')) await maybeRefresh();
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    clearToken();
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = '/login';
    }
    throw new ApiError(401, 'Сессия истекла');
  }

  if (res.status === 204) return null;

  let data = null;
  try { data = await res.json(); } catch { /* пустой ответ */ }

  if (!res.ok) {
    const detail = data && data.detail
      ? (typeof data.detail === 'string' ? data.detail : 'Проверьте заполнение полей')
      : `Ошибка ${res.status}`;
    throw new ApiError(res.status, detail);
  }
  return data;
}

/* Скачивание файла экспорта (MD/HTML). Идёт через fetch с токеном (авторизация
   в заголовке, а не в cookie), затем отдаёт браузеру Blob на сохранение. */
export async function downloadFile(path, fallbackName = 'export.txt') {
  await maybeRefresh();
  const token = getToken();
  const res = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (res.status === 401) {
    clearToken();
    if (!window.location.pathname.startsWith('/login')) window.location.href = '/login';
    throw new ApiError(401, 'Сессия истекла');
  }
  if (!res.ok) throw new ApiError(res.status, `Ошибка экспорта ${res.status}`);

  const cd = res.headers.get('Content-Disposition') || '';
  const m = cd.match(/filename="?([^"]+)"?/);
  const name = m ? m[1] : fallbackName;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
