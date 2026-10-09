import React, { useEffect, useState } from 'react';
import { api } from './api';
import Privacy from './Privacy';

export default function Operations({ leads, onRefresh }) {
  const [items, setItems] = useState([]), [events, setEvents] = useState([]), [reports, setReports] = useState(null), [notifications, setNotifications] = useState(null);
  const [leadId, setLeadId] = useState(''), [due, setDue] = useState(''), [notes, setNotes] = useState(''), [error, setError] = useState('');
  async function refresh() {
    try {
      const [f, a, r, n] = await Promise.all(['followups', 'audit', 'reports', 'notifications'].map(x => api('/operations/' + x)));
      setItems(f); setEvents(a); setReports(r); setNotifications(n); setError('');
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { refresh(); }, []);
  async function schedule(e) {
    e.preventDefault();
    try { await api('/operations/followups', 'POST', { lead_id: Number(leadId), due_at: new Date(due).toISOString(), notes }); setDue(''); setNotes(''); await refresh(); }
    catch (e) { setError(e.message); }
  }
  async function complete(id) { try { await api(`/operations/followups/${id}/complete`, 'POST'); await refresh(); } catch (e) { setError(e.message); } }
  async function queue() { try { await api(`/operations/notifications/leads/${leadId}`, 'POST'); await refresh(); } catch (e) { setError(e.message); } }
  return <div className="left-stack"><Privacy leads={leads} onRefresh={onRefresh}/>{error && <p className="error" role="alert">{error}</p>}<section className="panel setup-card"><h2>Follow-ups &amp; reminders</h2><p>Times use your browser timezone. Scheduling a reminder does not place a call or grant contact permission.</p><form onSubmit={schedule} className="form-grid"><label htmlFor="callback-lead">Business<select id="callback-lead" aria-label="Business" required value={leadId} onChange={e => setLeadId(e.target.value)}><option value="">Select a lead</option>{leads.map(l => <option key={l.id} value={l.id}>{l.business_name}</option>)}</select></label><label>Preferred callback time<input type="datetime-local" required value={due} onChange={e => setDue(e.target.value)}/></label><label className="full">Notes<textarea maxLength={1000} value={notes} onChange={e => setNotes(e.target.value)}/></label><button className="primary">Schedule follow-up</button></form><div className="table-scroll"><table><thead><tr><th>Business</th><th>Due</th><th>Contact permission</th><th>Action</th></tr></thead><tbody>{items.map(f => <tr key={f.id}><td>{f.business_name}<small>{f.notes}</small></td><td>{new Date(f.due_at).toLocaleString()}{!f.completed && new Date(f.due_at) < new Date() && ' · overdue'}</td><td>{f.contact_eligible ? 'Verified' : 'Blocked — review consent'}</td><td>{f.completed ? 'Completed' : <button className="secondary" onClick={() => complete(f.id)}>Mark complete</button>}</td></tr>)}</tbody></table></div></section><section className="panel setup-card"><h2>Operations report</h2><p>Overdue follow-ups: {reports?.overdue_followups ?? '…'}. Public telephone network: disconnected.</p><p>{Object.entries(reports?.pipeline || {}).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'No leads yet'}</p><h3>Telegram outbox</h3><p>{notifications?.enabled ? 'Configured. Sending requires the explicit worker command.' : 'Delivery disabled. No external messages are sent.'}</p><button className="secondary" disabled={!leadId} onClick={queue}>Queue selected qualified lead</button>{notifications?.items.map(n => <p key={n.id}>{n.business_name} · {n.state}{n.error && ` · ${n.error}`}</p>)}</section><section className="panel setup-card"><h2>Audit history</h2><p>Recent owner operations. No credentials or message contents are stored in audit events.</p>{events.map(e => <p key={e.id}>{e.created_at} UTC · {e.action} · {e.resource}</p>)}</section></div>;
}
