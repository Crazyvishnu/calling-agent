import React, { useEffect, useRef, useState } from 'react';
import { api } from './api';

export default function VoicePanel({ session, enabled, onSession, onActivity }) {
  const [status, setStatus] = useState(null), [permission, setPermission] = useState(false);
  const [active, setActive] = useState(false), [state, setState] = useState('off');
  const [error, setError] = useState(''), [heard, setHeard] = useState(''), [timings, setTimings] = useState(null);
  const resources = useRef(null), epoch = useRef(0), mounted = useRef(false);
  const callbacks = useRef({ onSession, onActivity }); callbacks.current = { onSession, onActivity };

  function stopPlayback() {
    const r = resources.current;
    if (r?.player) { try { r.player.stop(); } catch {} r.player = null; }
    if (r) r.playEpoch++;
  }
  function stop() {
    epoch.current++;
    const r = resources.current; resources.current = null;
    if (r) {
      r.playEpoch++;
      try { r.player?.stop(); } catch {}
      r.stream?.getTracks().forEach(track => track.stop());
      r.node?.disconnect(); r.source?.disconnect(); r.mute?.disconnect();
      if (r.socket?.readyState === WebSocket.OPEN) r.socket.send(JSON.stringify({ type: 'stop' }));
      r.socket?.close(); r.context?.close().catch(() => {});
    }
    callbacks.current.onActivity(false);
    if (mounted.current) { setActive(false); setState('off'); }
  }
  useEffect(() => {
    mounted.current = true;
    api(`/speech/status?language=${encodeURIComponent(session.language)}`).then(s => { if (mounted.current) setStatus(s); })
      .catch(e => { if (mounted.current) setError(e.message); });
    return () => { mounted.current = false; stop(); };
  }, [session.id, session.language]);
  useEffect(() => { if (!enabled || session.state !== 'active') stop(); }, [enabled, session.state]);

  async function start() {
    if (active || !permission || !enabled) return;
    const token = ++epoch.current;
    const r = { playEpoch: 0, ready: false, generation: 0 };
    resources.current = r; setError(''); setActive(true); setState('connecting'); callbacks.current.onActivity(true);
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw Error('Local microphone capture requires localhost or HTTPS and a compatible browser.');
      r.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      if (epoch.current !== token) { r.stream.getTracks().forEach(t => t.stop()); return; }
      r.context = new AudioContext(); await r.context.resume();
      await r.context.audioWorklet.addModule('/pcm-capture.js');
      if (epoch.current !== token) return;
      r.source = r.context.createMediaStreamSource(r.stream);
      r.node = new AudioWorkletNode(r.context, 'pcm-capture');
      r.mute = r.context.createGain(); r.mute.gain.value = 0;
      r.source.connect(r.node); r.node.connect(r.mute); r.mute.connect(r.context.destination);
      const url = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/speech/sessions/${session.id}/ws`;
      r.socket = new WebSocket(url);
      r.node.port.onmessage = event => {
        if (r.ready && epoch.current === token && r.socket.readyState === WebSocket.OPEN) {
          if (r.socket.bufferedAmount > 64000) { setError('Audio connection cannot keep up. Reconnect the microphone.'); stop(); return; }
          r.socket.send(event.data);
        }
      };
      r.socket.onopen = () => r.socket.send(JSON.stringify({ type: 'start', audio_processing_consent: true }));
      r.socket.onerror = () => { if (epoch.current === token) setError('Voice connection failed. Check the speech dependencies and backend.'); };
      r.socket.onclose = () => { if (epoch.current === token) stop(); };
      r.socket.onmessage = async event => {
        if (epoch.current !== token) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'ready') { r.ready = true; r.generation = data.generation; setState('listening'); }
          else if (data.type === 'interrupt') { r.generation = data.generation; stopPlayback(); setState('listening'); }
          else if (data.type === 'state') setState(data.state);
          else if (data.type === 'transcript') setHeard(data.text);
          else if (data.type === 'error') { setError(data.detail); setState('listening'); }
          else if (data.type === 'result' && data.generation === r.generation) {
            callbacks.current.onSession(data.session); setTimings(data.timings);
            if (data.session.state !== 'active') { stop(); return; }
            stopPlayback(); const playbackToken = r.playEpoch;
            if (!data.audio) { setState('listening'); return; }
            const bytes = Uint8Array.from(atob(data.audio), c => c.charCodeAt(0));
            const buffer = await r.context.decodeAudioData(bytes.buffer);
            if (epoch.current !== token || r.playEpoch !== playbackToken || r.generation !== data.generation) return;
            r.player = r.context.createBufferSource(); r.player.buffer = buffer; r.player.connect(r.context.destination);
            r.player.onended = () => { if (epoch.current === token && r.playEpoch === playbackToken) { r.player = null; setState('listening'); } };
            r.player.start(); setState('speaking');
          }
        } catch (e) { if (epoch.current === token) { setError(e.message); stop(); } }
      };
    } catch (e) { if (epoch.current === token) { setError(e.message); stop(); } }
  }

  function interrupt() {
    stopPlayback();
    const r = resources.current;
    if (r?.socket?.readyState === WebSocket.OPEN) r.socket.send(JSON.stringify({ type: 'interrupt' }));
    setState('listening');
  }
  return <div className="local-voice-panel">
    <h3>Local microphone conversation</h3>
    <p>{status?.detail || 'Checking local speech assets…'} · Language: {session.language}</p>
    <label className="check-label"><input type="checkbox" disabled={active} checked={permission} onChange={e => setPermission(e.target.checked)} />I agree to process this microphone audio locally and save the recognized text. Raw audio is not recorded.</label>
    <div className="lab-controls">
      <button className="primary" disabled={!enabled || !status?.ready || !permission || active || session.state !== 'active'} onClick={start}>Start local microphone</button>
      <button className="secondary" disabled={!active} onClick={interrupt}>Interrupt reply</button>
      <button className="secondary" disabled={!active} onClick={stop}>Stop microphone</button>
      <button className="secondary" disabled={active} onClick={() => api(`/speech/status?language=${encodeURIComponent(session.language)}`).then(setStatus).catch(e => setError(e.message))}>Check speech setup</button>
    </div>
    <p role="status">Voice: {state}</p>
    {heard && <p>Recognized: {heard}</p>}
    {timings && <p>STT {timings.stt_ms} ms · Model {timings.llm_ms} ms · TTS {timings.tts_ms} ms · Total {timings.total_ms} ms</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <p>Use headphones. Detected speech stops the current reply; silence for 600 ms submits your turn. Maximum utterance: 15 seconds. Speech detection is an energy-based prototype and can react to noise or speaker echo.</p>
  </div>;
}
