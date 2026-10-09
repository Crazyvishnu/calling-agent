"""Synthetic SIP caller for an explicitly reserved private AI session; no PSTN."""
import argparse
import json
import select
import socket
import struct
import time
import wave
from pathlib import Path

from sip_smoke import Phone, invite, parse, response, one


def encode(pcm):
    output = bytearray()
    for (sample,) in struct.iter_unpack('<h', pcm):
        sign = 0x80 if sample < 0 else 0
        sample = min(abs(sample), 32635) + 132
        exponent = max(0, min(7, sample.bit_length() - 8))
        mantissa = (sample >> (exponent + 3)) & 15
        output.append((~(sign | (exponent << 4) | mantissa)) & 255)
    return bytes(output)


def decode(data):
    values = []
    for sample in data:
        sample = (~sample) & 255
        value = (((sample & 15) << 3) + 132) << ((sample >> 4) & 7)
        values.append(132 - value if sample & 128 else value - 132)
    return struct.pack('<' + str(len(values)) + 'h', *values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--speech-pcm', required=True, help='Fictional speech fixture: mono PCM16 8 kHz')
    parser.add_argument('--opt-out-pcm')
    parser.add_argument('--capture-test-wavs', action='store_true', help='Explicitly save synthetic received audio under container /tmp')
    parser.add_argument('--hangup-after-speech', action='store_true')
    parser.add_argument('--barge-in', action='store_true', help='Speak opt-out during the AI reply')
    args = parser.parse_args()
    credentials = json.loads(Path('/run/akki/credentials.json').read_text())
    phone = Phone('1001', credentials['1001'], 5062, 16002)
    assert phone.register().startswith('SIP/2.0 200')
    code, remote, _ = invite(phone, '1002')
    assert code == 200
    speech = encode(Path(args.speech_pcm).read_bytes())
    decline = encode(Path(args.opt_out_pcm).read_bytes()) if args.opt_out_pcm else b''
    phase = 'opening'; offset = seq = 0; last_audio = started = time.monotonic()
    buffers = {'opening': bytearray(), 'reply': bytearray(), 'closing': bytearray()}
    sent_bye = ended = False
    hangup_at = None
    deadline = started
    try:
        while time.monotonic() - started < 100:
            now = time.monotonic()
            if now >= deadline:
                outgoing = speech if phase == 'speech' else decline if phase == 'decline' else b''
                payload = outgoing[offset:offset+160].ljust(160, b'\xff') if outgoing else b'\xff' * 160
                phone.rtp.sendto(struct.pack('!BBHII', 0x80, 0, seq % 65536, (seq*160) % 2**32, 2468) + payload, ('127.0.0.1', remote))
                seq += 1; deadline += .02
                if outgoing:
                    offset += 160
                    if offset >= len(outgoing):
                        phase = 'reply' if phase == 'speech' else 'closing'; offset = 0; last_audio = now
                        if args.hangup_after_speech:
                            hangup_at = now + 3.5
            if hangup_at and now >= hangup_at and not sent_bye:
                phone.sock.sendto(phone.request('BYE', phone.remote_uri, 3, to=phone.to), ('127.0.0.1',5060)); sent_bye = True
            ready, _, _ = select.select([phone.rtp, phone.sock], [], [], max(0,min(.02,deadline-time.monotonic())))
            for sock in ready:
                if sock is phone.rtp:
                    packet, _ = sock.recvfrom(4096)
                    if len(packet) >= 172 and phase in buffers:
                        # Asterisk lab uses fixed PCMU RTP without extensions/CSRCs.
                        buffers[phase].extend(packet[12:]); last_audio = time.monotonic()
                else:
                    packet, addr = sock.recvfrom(65535)
                    line, headers, _ = parse(packet)
                    if line.startswith('BYE '):
                        sock.sendto(response(packet,200,'OK'),addr); ended = True
                    elif sent_bye and line.startswith('SIP/2.0 200') and one(headers,'cseq').endswith('BYE'):
                        ended = True
            if ended:
                break
            if phase == 'opening' and len(buffers['opening']) > 8000 and now - last_audio > .7:
                phase = 'speech'; offset = 0
            elif phase == 'reply' and len(buffers['reply']) > 3000 and (args.barge_in or now - last_audio > .7):
                if decline:
                    phase = 'decline'; offset = 0
                else:
                    phone.sock.sendto(phone.request('BYE',phone.remote_uri,3,to=phone.to),('127.0.0.1',5060)); sent_bye=True
        assert ended, 'Private AI call failed to hang up within the lab limit'
        assert len(buffers['opening']) > 8000, 'AI opening did not reach the SIP user'
        if not args.hangup_after_speech:
            assert len(buffers['reply']) > 3000, 'AI response did not reach the SIP user'
        if decline:
            assert len(buffers['closing']) > 3000, 'Opt-out closing speech did not reach the SIP user'
        for name, data in buffers.items():
            if data and args.capture_test_wavs:
                with wave.open('/tmp/akki-sip-'+name+'.wav','wb') as w:
                    w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(decode(data))
        print(json.dumps({'sip_ai_call':'passed','incoming_pcmu_bytes':{k:len(v) for k,v in buffers.items()},
                          'hangup':'passed','caller_hangup_after_speech':args.hangup_after_speech,'barge_in':args.barge_in,'pstn_connected':False}))
    finally:
        phone.sock.close();phone.rtp.close()


if __name__ == '__main__':
    main()
