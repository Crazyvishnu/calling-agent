import React, { useEffect, useState } from 'react';
import { api } from './api';

export default function OwnerAccess({ children }) {
  const [access, setAccess] = useState(null), [key, setKey] = useState(''), [error, setError] = useState('');
  const check = () => api('/auth/status').then(setAccess).catch(e => setError(e.message));
  useEffect(() => {
    check();
    const expired = () => setAccess({ enabled: true, authenticated: false });
    window.addEventListener('akki-login-required', expired);
    return () => window.removeEventListener('akki-login-required', expired);
  }, []);
  async function login(e) {
    e.preventDefault();
    try { await api('/auth/login', 'POST', { key }); setKey(''); setError(''); await check(); }
    catch (e) { setError(e.message); }
  }
  if (!access || !access.authenticated) return <main className="main"><section className="panel setup-card"><h1>Akki owner access</h1><p>Use the private owner key configured on your server.</p>{error && <p role="alert" className="error">{error}</p>}{access && <form onSubmit={login}><label>Owner key<input type="password" autoComplete="current-password" required value={key} onChange={e => setKey(e.target.value)}/></label><button className="primary">Sign in</button></form>}<button className="secondary" onClick={check}>Check connection</button></section></main>;
  return <>{access.enabled && <div className="owner-bar"><span>Owner session · expires after 8 hours</span><button className="secondary" onClick={async () => { await api('/auth/logout', 'POST'); await check(); }}>Sign out</button></div>}{children}</>;
}
