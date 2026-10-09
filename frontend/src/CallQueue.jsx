import React, { useEffect, useRef, useState } from 'react';
import { api } from './api';

const activeStates = ['dispatching', 'waiting', 'connected'];
export default function CallQueue({ session, enabled, onActivity, onSession }) {
  const [jobs, setJobs] = useState([]), [due, setDue] = useState(''), [approval, setApproval] = useState('');
  const [consent, setConsent] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const mounted = useRef(false), runningJob = useRef(null), revision = useRef(session.revision);
  const callbacks = useRef({ onActivity, onSession }); callbacks.current = { onActivity, onSession };
  async function refresh() {
    try {
      const values = await api('/call-queue');
      if (!mounted.current) return;
      setJobs(values);
      const running = values.find(j => j.session_id === session.id && activeStates.includes(j.state));
      runningJob.current = running?.id || null;
      callbacks.current.onActivity(!!running);
      if (values.some(j => j.session_id === session.id && j.call_id)) {
        const current = await api(`/lab/sessions/${session.id}`);
        if (mounted.current && current.revision !== revision.current) {
          revision.current = current.revision; callbacks.current.onSession(current);
        }
      }
    } catch (e) { if (mounted.current) setError(e.message); }
  }
  useEffect(() => {
    mounted.current = true; refresh();
    return () => {
      mounted.current = false;
      if (runningJob.current) api(`/call-queue/${runningJob.current}/cancel`, 'POST').catch(() => {});
      callbacks.current.onActivity(false);
    };
  }, [session.id]);
  const own = jobs.filter(j => j.session_id === session.id);
  const running = own.some(j => activeStates.includes(j.state));
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(refresh, 1000);
    return () => clearInterval(timer);
  }, [running, session.id]);
  async function action(work, dispatch = false) {
    setBusy(true); setError('');
    if (dispatch) callbacks.current.onActivity(true);
    try {
      const result = await work();
      if (!mounted.current) {
        if (dispatch && result?.call_id) await api(`/call-queue/${result.id}/cancel`, 'POST');
        return;
      }
      await refresh();
    } catch (e) { if (mounted.current) { setError(e.message); if (dispatch) callbacks.current.onActivity(false); } }
    finally { if (mounted.current) setBusy(false); }
  }
  return <div className="local-voice-panel"><h3>Approved private outbound queue</h3>
    <p>Calls only the consenting SIP test endpoint 1001. The participant must be registered in the private lab. No phone-number dialing, automatic dispatch or retries.</p>
    <form className="form-grid" onSubmit={e => { e.preventDefault(); action(() => api('/call-queue', 'POST', {
      session_id: session.id, due_at: new Date(due).toISOString(), approval_source: approval,
      private_test_approved: consent, audio_processing_consent: consent,
    })); }}>
      <label>Private test time<input type="datetime-local" required value={due} onChange={e => setDue(e.target.value)}/></label>
      <label>Approval evidence<input required maxLength={300} value={approval} onChange={e => setApproval(e.target.value)}/></label>
      <label className="check-label full"><input type="checkbox" required checked={consent} onChange={e => setConsent(e.target.checked)}/>Participant 1001 approved this private call and local audio/transcript processing.</label>
      <button className="secondary" disabled={!enabled || busy || running || session.state !== 'active' || !consent}>Add approved job</button>
    </form>
    <button className="secondary" disabled={busy} onClick={refresh}>Refresh queue</button>
    {own.map(j => <div key={j.id}><p>{new Date(j.due_at).toLocaleString()} · {j.state}{j.error && ` · ${j.error}`}</p>
      <div className="lab-controls">
        <button className="primary" disabled={!enabled || busy || running || j.state !== 'queued' || new Date(j.due_at) > new Date()} onClick={() => action(() => api(`/call-queue/${j.id}/dispatch`, 'POST'), true)}>Call consenting test user 1001</button>
        <button className="secondary" disabled={busy || !['queued','waiting','connected'].includes(j.state)} onClick={() => action(() => api(`/call-queue/${j.id}/cancel`, 'POST'))}>Cancel job</button>
      </div></div>)}
    {error && <p className="error" role="alert">{error}</p>}
  </div>;
}
