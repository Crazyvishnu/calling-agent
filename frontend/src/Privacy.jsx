import React, { useEffect, useState } from 'react';
import { api } from './api';

export default function Privacy({ leads, onRefresh }) {
  const [leadId, setLeadId] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [readiness, setReadiness] = useState(null);
  useEffect(() => { api('/privacy/readiness').then(setReadiness).catch(e => setMessage(e.message)); }, []);
  async function download() {
    setBusy(true);
    try {
      const data = await api(`/privacy/leads/${leadId}/export`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      const a = document.createElement('a');
      a.href = url; a.download = `akki-lead-${leadId}.json`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage('Export downloaded. Store it privately and delete it when no longer needed.');
    } catch (e) { setMessage(e.message); }
    finally { setBusy(false); }
  }
  async function erase() {
    setBusy(true);
    try {
      await api(`/privacy/leads/${leadId}/erase`, 'POST', { reviewed: confirmed });
      setMessage('Lead data erased from the application. Review existing backups and exports separately.');
      setLeadId(''); setConfirmed(false); await onRefresh();
    } catch (e) { setMessage(e.message); }
    finally { setBusy(false); }
  }
  return <section className="panel setup-card"><h2>Privacy &amp; readiness</h2><p>Export a business record or erase its personal data. A hashed phone suppression and minimal call-attempt ledger remain to prevent further outreach and quota resets. Existing backups and exports need separate removal.</p>
    <label>Business record<select value={leadId} onChange={e => { setLeadId(e.target.value); setConfirmed(false); }}><option value="">Select a lead</option>{leads.map(l => <option key={l.id} value={l.id}>{l.business_name}</option>)}</select></label>
    <p><button className="secondary" disabled={!leadId || busy} onClick={download}>Download private export</button></p>
    <label className="check-label"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/><span>I reviewed this record and authorize permanent erasure of its application data.</span></label>
    <p><button className="danger-action" disabled={!leadId || !confirmed || busy} onClick={erase}>Erase selected lead data</button></p>
    {message && <p role="status">{message}</p>}
    {readiness && <><h3>Deployment checks</h3><p>Database: {readiness.database_ok ? 'healthy' : 'needs repair'}. Owner access: {readiness.owner_authentication ? 'configured' : 'local development only'}. Public telephone network: disconnected.</p><p>Production acceptance remains incomplete:</p><ul>{readiness.remaining_checks.map(x => <li key={x}>{x}</li>)}</ul></>}
  </section>;
}
