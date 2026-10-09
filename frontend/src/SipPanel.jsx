import React, { useEffect, useRef, useState } from 'react';
import { api } from './api';

export default function SipPanel({ session, enabled, onSession, onActivity }) {
  const [status, setStatus] = useState(null), [consent, setConsent] = useState(false);
  const [call, setCall] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const mounted = useRef(false), current = useRef(null), revision = useRef(session.revision);
  const callbacks = useRef({ onSession, onActivity }); callbacks.current = { onSession, onActivity };
  const running = !!call && ['preparing', 'waiting', 'connected'].includes(call.state);
  useEffect(() => {
    mounted.current = true;
    api('/telephony/status').then(s => { if (mounted.current) setStatus(s); }).catch(e => { if (mounted.current) setError(e.message); });
    return () => {
      mounted.current = false;
      if (current.current) api(`/telephony/calls/${current.current}/stop`, 'POST').catch(() => {});
      callbacks.current.onActivity(false);
    };
  }, [session.id]);
  useEffect(() => {
    if (!running) return;
    let disposed = false, timer;
    async function poll() {
      try {
        const result = await api(`/telephony/calls/${call.id}`);
        if (disposed) return;
        setCall(result);
        if (result.session.revision !== revision.current) {
          revision.current = result.session.revision; callbacks.current.onSession(result.session);
        }
        if (['ended', 'failed', 'cancelled'].includes(result.state)) {
          current.current = null; callbacks.current.onActivity(false); return;
        }
      } catch (e) { if (!disposed) setError(e.message); }
      if (!disposed) timer = setTimeout(poll, 1000);
    }
    poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [call?.id, running]);
  async function reserve() {
    setBusy(true); setError(''); callbacks.current.onActivity(true);
    try {
      const result = await api(`/telephony/sessions/${session.id}/connect`, 'POST', { audio_processing_consent: true });
      if (!mounted.current) { await api(`/telephony/calls/${result.id}/stop`, 'POST'); return; }
      current.current = result.id; setCall(result);
    } catch (e) { if (mounted.current) setError(e.message); callbacks.current.onActivity(false); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function stop() {
    setBusy(true);
    try {
      const result = await api(`/telephony/calls/${call.id}/stop`, 'POST');
      if (mounted.current) { current.current = null; setCall(result); callbacks.current.onActivity(false); }
    } catch (e) { if (mounted.current) setError(e.message); }
    finally { if (mounted.current) setBusy(false); }
  }
  return <div className="local-voice-panel">
    <h3>Private SIP conversation</h3>
    <p>{status?.detail || 'Checking private SIP setup…'}</p>
    <p>Linux AudioSocket lab. Reserve this session, then consenting test user 1001 can dial 1002. No mobile or landline connection.</p>
    <label className="check-label"><input type="checkbox" checked={consent} disabled={busy || running} onChange={e => setConsent(e.target.checked)} />The SIP test participant agreed to local audio processing and transcript storage.</label>
    <div className="lab-controls">
      <button className="primary" disabled={!enabled || !status?.enabled || !status?.configured || !consent || busy || running || session.state !== 'active'} onClick={reserve}>{busy && !running ? 'Warming models…' : 'Reserve private SIP session'}</button>
      <button className="secondary" disabled={busy || !running} onClick={stop}>Disconnect SIP call</button>
    </div>
    {call && <>
      <p role="status">SIP: {call.state} · {call.stage}</p>
      {call.transcript && <p>Recognized over SIP: {call.transcript}</p>}
      {call.timings?.total_ms && <p>STT {call.timings.stt_ms} ms · Model {call.timings.llm_ms} ms · TTS {call.timings.tts_ms} ms · Total {call.timings.total_ms} ms</p>}
      {call.error && <p role="alert" className="error">{call.error}</p>}
    </>}
    {error && <p role="alert" className="error">{error}</p>}
  </div>;
}
