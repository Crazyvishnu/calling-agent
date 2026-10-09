import React, { useEffect, useRef, useState } from 'react';
import { api } from './api';
import VoicePanel from './VoicePanel';
import SipPanel from './SipPanel';
import CallQueue from './CallQueue';

export default function AiLab({ lead, leads, onSelect, onRefresh }) {
  return <section className="panel lab-panel">
    <div className="panel-heading"><div><h2>Local AI conversation lab</h2><p>Test website requirements through local conversation or private SIP audio.</p></div></div>
    <label>Test business <select value={lead?.id || ''} onChange={e => onSelect(leads.find(l => l.id === Number(e.target.value)) || null)}>
      <option value="">Choose a consented test lead</option>
      {leads.map(l => <option key={l.id} value={l.id}>{l.business_name}</option>)}
    </select></label>
    <LabSession key={lead?.id || 'empty'} lead={lead} onRefresh={onRefresh} />
  </section>;
}

function LabSession({ lead, onRefresh }) {
  const [status, setStatus] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [session, setSession] = useState(null);
  const [language, setLanguage] = useState('en-IN');
  const [permission, setPermission] = useState(false);
  const [voice, setVoice] = useState(false);
  const [entry, setEntry] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [voiceActive, setVoiceActive] = useState(false);
  const [sipActive, setSipActive] = useState(false);
  const [queueActive, setQueueActive] = useState(false);
  const mounted = useRef(false);
  const eligible = lead?.contact_allowed && !lead?.do_not_call && lead?.status !== 'not_interested';

  useEffect(() => {
    mounted.current = true;
    api('/lab/status').then(r => { if (mounted.current) setStatus(r); }).catch(e => { if (mounted.current) setError(e.message); });
    if (lead) api(`/lab/sessions?lead_id=${lead.id}`).then(r => { if (mounted.current) setSessions(r); }).catch(e => { if (mounted.current) setError(e.message); });
    return () => { mounted.current = false; window.speechSynthesis?.cancel(); };
  }, [lead?.id]);

  useEffect(() => { if (!eligible) window.speechSynthesis?.cancel(); }, [eligible]);

  async function action(work) {
    if (busy) return;
    setBusy(true); setError('');
    try { await work(); } catch (e) { if (mounted.current) setError(e.message); }
    finally { if (mounted.current) setBusy(false); }
  }

  function speak(text, lang) {
    if (!voice || !mounted.current || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    window.speechSynthesis.speak(utterance);
  }

  async function show(result, read = false) {
    if (!mounted.current) return;
    setSession(result);
    if (read) speak(result.messages.at(-1).message, result.language);
    const history = await api(`/lab/sessions?lead_id=${lead.id}`);
    if (mounted.current) setSessions(history);
  }

  function start() {
    action(async () => {
      const result = await api('/lab/sessions', 'POST', { lead_id: lead.id, language, collection_consent: permission });
      await show(result, true);
    });
  }

  function send(e) {
    e.preventDefault();
    if (!entry.trim() || !canReply) return;
    action(async () => {
      window.speechSynthesis?.cancel();
      const result = await api(`/lab/sessions/${session.id}/reply`, 'POST', { message: entry.trim(), revision: session.revision });
      if (!mounted.current) return;
      setEntry('');
      await show(result, true);
      onRefresh();
    });
  }

  const canReply = eligible && session?.state === 'active' && !busy && !voiceActive && !sipActive && !queueActive;
  return <>
    <div className="lab-status" role="status">
      {status ? `${status.model}: ${status.detail}` : 'Checking local model…'}
      <button className="secondary" disabled={busy} onClick={() => action(async () => {
        const r = await api('/lab/status'); if (mounted.current) setStatus(r);
      })}>Check model</button>
    </div>
    {!eligible && <p className="notice">Select a test lead with documented contact permission. Declined and do-not-call leads are blocked.</p>}
    <div className="lab-controls">
      <label>Conversation language <select value={language} disabled={busy} onChange={e => setLanguage(e.target.value)}>
        <option value="en-IN">English</option><option value="hi-IN">Hindi (experimental)</option><option value="te-IN">Telugu (experimental)</option>
      </select></label>
      <label className="check-label"><input type="checkbox" disabled={voiceActive || sipActive} checked={voice} onChange={e => {
        setVoice(e.target.checked); if (!e.target.checked) window.speechSynthesis?.cancel();
      }} />Read replies using browser speech</label>
      <button className="secondary" onClick={() => window.speechSynthesis?.cancel()}>Stop audio</button>
    </div>
    <label className="check-label lab-permission"><input type="checkbox" checked={permission} disabled={busy} onChange={e => setPermission(e.target.checked)} />
      The test participant agreed to collect requirements, save this conversation on this computer, and process it with the local model. Browser speech may use an online service. No audio recording is stored.
    </label>
    <div className="lab-controls">
      <button className="primary" disabled={!eligible || !permission || !status?.ready || busy || session?.state === 'active'} onClick={start}>Start local AI session</button>
      <label>Saved sessions <select value={session?.id || ''} disabled={busy} onChange={e => {
        if (e.target.value) action(async () => { window.speechSynthesis?.cancel(); await show(await api(`/lab/sessions/${e.target.value}`)); });
      }}><option value="">Choose a session</option>{sessions.map(s => <option key={s.id} value={s.id}>{s.created_at} · {s.language} · {s.state}</option>)}</select></label>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {session && <>
      <VoicePanel key={session.id} session={session} enabled={!!eligible && !busy && !sipActive && !queueActive}
        onSession={result => { setSession(result); onRefresh(); }}
        onActivity={value => { setVoiceActive(value); if (value) { setVoice(false); window.speechSynthesis?.cancel(); } }} />
      <SipPanel key={'sip-'+session.id} session={session} enabled={!!eligible && !busy && !voiceActive && !queueActive}
        onSession={result => { setSession(result); onRefresh(); }}
        onActivity={value => { setSipActive(value); if (value) { setVoice(false); window.speechSynthesis?.cancel(); } }} />
      <CallQueue session={session} enabled={!!eligible && !busy && !voiceActive && !sipActive} onActivity={setQueueActive} onSession={result => { setSession(result); onRefresh(); }}/>
      <p className="lab-session-state">Session: {session.state} · Interest draft: {session.interest} · {session.revision}/20 turns</p>
      <div className="messages lab-messages" aria-live="polite">{session.messages.map((m, i) => <div className={'chat-line ' + m.role} key={i}>
        <span className="chat-author">{m.role === 'agent' ? 'Akki · local AI' : 'Test participant'}</span><div className="chat-bubble">{m.message}</div>
      </div>)}</div>
      <form className="chat-compose" onSubmit={send}>
        <input aria-label="Reply to local AI" maxLength={2000} disabled={!canReply} value={entry} onChange={e => setEntry(e.target.value)} placeholder="Type your response…" />
        <button className="primary" disabled={!canReply || !entry.trim()}>{busy ? 'Thinking…' : 'Send'}</button>
      </form>
      <div className="lab-controls">
        <button className="secondary" disabled={busy || session.state !== 'active'} onClick={() => action(async () => {
          window.speechSynthesis?.cancel(); await show(await api(`/lab/sessions/${session.id}/end`, 'POST'));
        })}>End session</button>
        <button className="danger-action" disabled={busy || voiceActive || sipActive || queueActive} onClick={() => action(async () => {
          await api(`/lab/sessions/${session.id}`, 'DELETE');
          if (!mounted.current) return;
          window.speechSynthesis?.cancel(); setSession(null);
          const r = await api(`/lab/sessions?lead_id=${lead.id}`); if (mounted.current) setSessions(r);
        })}>Delete transcript and draft</button>
      </div>
      <div className="lab-controls">
        <button className="secondary" disabled={busy || voiceActive || sipActive || queueActive || !eligible || session.state === 'declined'} onClick={() => action(async () => {
          await show(await api(`/lab/sessions/${session.id}/handoff`, 'POST')); onRefresh();
        })}>Hand to developer for follow-up</button>
      </div>
      {session.handoff_requested === 1 && <p className="notice">Personal follow-up requested. Schedule a callback in Follow-ups &amp; reports. No live transfer or automatic customer callback was placed.</p>}
      <div className="lab-draft"><h3>Requirements draft · human review needed</h3>
        <p>Model extraction can be wrong. This draft does not change CRM qualification or authorize a callback.</p>
        <dl>{Object.entries(session.draft).map(([key, value]) => <React.Fragment key={key}>
          <dt>{key.replaceAll('_', ' ')}</dt><dd>{Array.isArray(value) ? value.join(', ') : value}</dd>
        </React.Fragment>)}</dl>
        <button className="primary" disabled={busy || voiceActive || sipActive || queueActive || !eligible || session.state === 'declined' || !Object.keys(session.draft).length || session.reviewed_revision === session.revision} onClick={() => action(async () => {
          await show(await api(`/lab/sessions/${session.id}/review`, 'POST', { revision: session.revision, reviewed: true })); onRefresh();
        })}>{session.reviewed_revision === session.revision ? 'Saved reviewed requirements' : 'I reviewed this draft — save to CRM'}</button>
        {!Object.keys(session.draft).length && <p>No requirements collected yet.</p>}
      </div>
    </>}
    <p className="convo-disclaimer">No PSTN calls. Local microphone speech and private Asterisk SIP bridge with prototype interruption detection. English speech is tested; other languages need matching models and separate evaluation.</p>
  </>;
}
