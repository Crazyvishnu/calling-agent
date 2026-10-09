export async function api(url, method = 'GET', payload) {
  const options = { method, headers: { 'Content-Type': 'application/json', 'X-Akki-Request': '1' } };
  if (payload !== undefined) options.body = JSON.stringify(payload);
  const response = await fetch('/api' + url, options);
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({ detail: 'Unknown server error' }));
  if (response.status === 401) window.dispatchEvent(new Event('akki-login-required'));
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
