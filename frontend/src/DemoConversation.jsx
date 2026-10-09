import React, { useEffect, useRef, useState } from 'react';
import { AudioLines, Headphones, Mic, MicOff, Send, ShieldCheck, Volume2 } from 'lucide-react';
import { api } from './api';

export default function Conversation({ lead, onRefresh }) {
  const [msgs, setMsgs] = useState([]), [entry, setEntry] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [listening, setListening] = useState(false), [voice, setVoice] = useState(false);
  const [language, setLanguage] = useState('en-IN'), [ended, setEnded] = useState(false);
  const recRef = useRef(null), mounted = useRef(false), scroll = useRef(null);
  const eligible = lead && lead.contact_allowed && !lead.do_not_call && lead.status !== 'not_interested';

  function stopAudio() {
    window.speechSynthesis?.cancel();
    const rec = recRef.current;
    if (rec) { rec.onresult = rec.onerror = rec.onend = null; rec.abort(); recRef.current = null; }
  }
  useEffect(() => {
    mounted.current = true;
    if (lead) api(`/leads/${lead.id}/demo/messages`).then(r => { if (mounted.current) setMsgs(r); })
      .catch(e => { if (mounted.current) setError(e.message); });
    return () => { mounted.current = false; stopAudio(); };
  }, [lead?.id]);
  useEffect(() => { if (!eligible) { stopAudio(); setListening(false); } }, [eligible]);
  useEffect(() => { scroll.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs]);

  function speak(text) {
    if (!voice || !mounted.current || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text); u.lang = language; u.rate = 0.94;
    window.speechSynthesis.speak(u);
  }
  async function start() {
    setBusy(true); setError('');
    try {
      const r = await api(`/leads/${lead.id}/demo/start`, 'POST');
      if (!mounted.current) return;
      setMsgs([{ role: 'agent', message: r.reply }]); setEnded(false); speak(r.reply);
    } catch (e) { if (mounted.current) setError(e.message); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function send(e) {
    e.preventDefault(); if (!entry.trim() || busy || ended || !eligible) return;
    const msg = entry.trim(); setBusy(true); setError('');
    try {
      const r = await api(`/leads/${lead.id}/demo/reply`, 'POST', { message: msg });
      if (!mounted.current) return;
      setEntry(''); setEnded(r.ended);
      setMsgs(v => [...v, { role: 'customer', message: msg }, { role: 'agent', message: r.reply }]);
      speak(r.reply); onRefresh();
    } catch (e) { if (mounted.current) setError(e.message); }
    finally { if (mounted.current) setBusy(false); }
  }
  function listen() {
    const C = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!C) { setError('This browser has no speech recognition support. Type your reply instead.'); return; }
    if (recRef.current) { recRef.current.stop(); return; }
    window.speechSynthesis?.cancel();
    const rec = new C(); rec.lang = language; rec.interimResults = false; rec.maxAlternatives = 1;
    recRef.current = rec;
    rec.onresult = e => { if (mounted.current) setEntry(e.results[0][0].transcript); };
    rec.onerror = e => { if (mounted.current) setError('Microphone recognition: ' + e.error); };
    rec.onend = () => { recRef.current = null; if (mounted.current) setListening(false); };
    try { rec.start(); setListening(true); } catch (e) { recRef.current = null; setError(e.message); }
  }
  const canReply = eligible && msgs.length > 0 && !busy && !ended;
  return <section className="panel convo-panel">
    <div className="convo-head"><div className="avatar-agent"><AudioLines size={19}/></div><div><h3>Akki voice simulator</h3><p>{lead ? `Practice with ${lead.business_name}` : 'Select a business to begin'}</p></div><span className="simulation-pill">SCRIPTED</span></div>
    <div className="convo-toolbar"><label><span>Browser voice language</span><select value={language} onChange={e => setLanguage(e.target.value)}><option value="en-IN">English (India)</option><option value="hi-IN">Hindi</option><option value="te-IN">Telugu</option></select></label><label className="toggle-voice"><input type="checkbox" checked={voice} onChange={e => { setVoice(e.target.checked); if (!e.target.checked) window.speechSynthesis?.cancel(); }}/><Volume2 size={15}/> Read replies aloud</label></div>
    <div className="convo-body">{!lead ? <div className="empty-convo"><Headphones size={27}/><h4>Choose a test business</h4></div> : !eligible ? <div className="empty-convo"><ShieldCheck size={31}/><h4>Contact permission required</h4><p>Declined and do-not-call businesses are blocked.</p></div> : msgs.length === 0 ? <div className="empty-convo"><AudioLines size={27}/><h4>Practice a scripted conversation</h4><p>No phone number is dialed. This demo uses rules and browser speech.</p><button className="primary" disabled={busy} onClick={start}>Start voice demo</button></div> : <div className="messages">{msgs.map((m, i) => <div key={i} className={'chat-line ' + m.role}><span className="chat-author">{m.role === 'agent' ? 'Akki · scripted agent' : 'Customer'}</span><div className="chat-bubble">{m.message}</div></div>)}<div ref={scroll}/></div>}</div>
    {ended && <p className="convo-disclaimer">This demo has ended.</p>}
    {error && <p className="convo-error" role="alert">{error}</p>}
    <form className="chat-compose" onSubmit={send}><button type="button" aria-label="Dictate reply" onClick={listen} disabled={!canReply} className={'mic-button ' + (listening ? 'recording' : '')}>{listening ? <MicOff size={19}/> : <Mic size={19}/>}</button><input aria-label="Scripted demo reply" maxLength={2000} placeholder="Type a customer response…" disabled={!canReply} value={entry} onChange={e => setEntry(e.target.value)}/><button type="submit" aria-label="Send response" className="send-button" disabled={!canReply || !entry.trim()}><Send size={18}/></button></form>
    {eligible && msgs.length > 0 && <button className="secondary" disabled={busy} onClick={start}>Restart scripted demo</button>}
    <div className="convo-disclaimer">This scripted demo stores entered text locally. Browser voice may use an online service. Changing voice language does not translate the English script. No real calls.</div>
  </section>;
}
