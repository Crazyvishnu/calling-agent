"""Explicit synthetic end-to-end SIP/AI check. Local Linux Docker only, no PSTN."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import httpx

from backend.media import wav_to_pcm8
from backend.speech_engine import engine

ROOT = Path(__file__).resolve().parents[1]
DOCKER = ['docker', '--host=unix:///var/run/docker.sock']
COMPOSE = DOCKER + ['compose', '-f', str(ROOT / 'telephony/compose.yaml')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-private-test', action='store_true')
    parser.add_argument('--barge-in', action='store_true')
    parser.add_argument('--hangup-during-inference', action='store_true')
    args = parser.parse_args()
    if not args.run_private_test:
        parser.error('Use --run-private-test to create fictional CRM records and run the consenting synthetic SIP caller.')
    if sys.platform != 'linux':
        raise SystemExit('This bridge check currently requires Linux; native Windows support is not implemented.')
    if args.barge_in and args.hangup_during_inference:
        parser.error('Choose one interruption scenario per test.')
    if not engine.status()['ready']:
        raise SystemExit('Install the optional local speech dependencies/models first.')
    names = []
    call = None
    with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False, timeout=120) as client:
        try:
            for name, text in [('speech', 'I need a restaurant website with a menu. My budget is twelve thousand rupees.'),
                               ('decline', 'Please do not call me again.')]:
                path = '/tmp/akki-' + name + '-8k.pcm'; names.append(path)
                pcm = wav_to_pcm8(engine.synthesize(text, 'en-IN'))
                subprocess.run(COMPOSE + ['exec', '-T', 'asterisk', 'python3', '-c',
                               'import sys;open(sys.argv[1],"wb").write(sys.stdin.buffer.read())', path], input=pcm, check=True)
            response = client.post('/api/leads', json={'business_name': 'Fictional Akki SIP Qualification Test',
                'contact_allowed': True, 'consent_source': 'Consenting synthetic SIP test; not a real business'})
            response.raise_for_status(); lead = response.json()
            response = client.post('/api/lab/sessions', json={'lead_id': lead['id'], 'collection_consent': True})
            response.raise_for_status(); session = response.json()
            response = client.post(f'/api/telephony/sessions/{session["id"]}/connect', json={'audio_processing_consent': True})
            response.raise_for_status(); call = response.json()
            command = COMPOSE + ['exec', '-T', 'asterisk', 'python3', '/opt/akki/ai_sip_smoke.py', '--speech-pcm', names[0]]
            if args.hangup_during_inference:
                command += ['--hangup-after-speech']
            else:
                command += ['--opt-out-pcm', names[1]]
                if args.barge_in: command += ['--barge-in']
            print('Reserved fictional session; running private SIP caller…', flush=True)
            stages = []
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            deadline = time.monotonic() + 120
            while process.poll() is None:
                if time.monotonic() > deadline:
                    process.kill(); process.communicate(); raise TimeoutError('Synthetic SIP caller timed out.')
                response = client.get(f'/api/telephony/calls/{call["id"]}'); response.raise_for_status()
                stages.append(response.json()['stage']); time.sleep(.2)
            stdout, stderr = process.communicate()
            if process.returncode:
                raise RuntimeError('Synthetic SIP caller failed: ' + stderr[-1000:])
            print(stdout.strip(), flush=True)
            for _ in range(30):
                call = client.get(f'/api/telephony/calls/{call["id"]}').json()
                if call['state'] not in ('waiting', 'connected'): break
                time.sleep(.1)
            assert call['state'] == 'ended', 'Private call did not cleanly end.'
            if args.hangup_during_inference:
                assert 'thinking' in stages, 'Hangup did not exercise model inference.'
                assert call['session']['revision'] == 0, 'Canceled turn was saved.'
            else:
                assert '12000' in str(call['session']['draft']).replace(',', ''), 'Spoken budget missing.'
                assert 'menu' in str(call['session']['draft']).lower(), 'Spoken menu missing.'
                assert call['session']['state'] == 'declined'
                lead = client.get(f'/api/leads/{lead["id"]}').json()
                assert lead['do_not_call'] and not lead['contact_allowed'], 'Opt-out not enforced.'
            assert not client.get('/api/telephony/status').json()['active_call_id'], 'Private reservation leaked.'
            print(json.dumps({'sip_ai_check': 'passed', 'call_id': call['id'], 'turn_timings': call['turn_timings'],
                'saved_revision': call['session']['revision'], 'pstn_connected': False}, indent=2))
            print('Synthetic English speech only; human review, accents and real-user quality remain unverified.')
        finally:
            if call:
                client.post(f'/api/telephony/calls/{call["id"]}/stop')
            if names:
                subprocess.run(COMPOSE + ['exec', '-T', 'asterisk', 'python3', '-c',
                    'from pathlib import Path;import sys;[Path(p).unlink(missing_ok=True) for p in sys.argv[1:]]', *names], check=False,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
