"""Bounded AudioSocket framing and prototype narrowband PCM conversion."""
import asyncio
import io
import struct
import wave


class PCM8To16:
    def __init__(self):
        self.previous = 0
        self.buffer = bytearray()

    def frames(self, pcm):
        if not pcm or len(pcm) % 2:
            raise ValueError('AudioSocket PCM must contain whole signed samples.')
        output = []
        for (sample,) in struct.iter_unpack('<h', pcm):
            output.extend(((self.previous + sample) // 2, sample))
            self.previous = sample
        self.buffer.extend(struct.pack('<' + str(len(output)) + 'h', *output))
        frames = []
        while len(self.buffer) >= 640:
            frames.append(bytes(self.buffer[:640])); del self.buffer[:640]
        return frames


def wav_to_pcm8(wav):
    import numpy as np  # Optional speech dependency; not required for offline API use.
    with wave.open(io.BytesIO(wav), 'rb') as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or not 8000 <= audio.getframerate() <= 48000:
            raise ValueError('Expected mono PCM16 WAV between 8 and 48 kHz.')
        if audio.getnframes() / audio.getframerate() > 30:
            raise ValueError('Voice reply exceeds the 30-second private lab limit.')
        rate = audio.getframerate()
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2')
    if not len(samples):
        return b''
    # Asterisk narrowband lab resampling. This cannot restore lost high frequencies.
    positions = np.arange(round(len(samples) * 8000 / rate)) * rate / 8000
    return np.interp(positions, np.arange(len(samples)), samples).astype('<i2').tobytes()


def packet(kind, payload=b''):
    if len(payload) > 6400:
        raise ValueError('AudioSocket payload exceeds the private lab bound.')
    return bytes([kind]) + struct.pack('!H', len(payload)) + payload


async def read_packet(reader):
    kind, length = struct.unpack('!BH', await reader.readexactly(3))
    if length > 6400:
        raise ValueError('Oversized AudioSocket packet.')
    data = await reader.readexactly(length)
    if kind == 0x01 and length != 16:
        raise ValueError('AudioSocket UUID must contain 16 bytes.')
    if kind == 0x10 and (not length or length % 2):
        raise ValueError('Invalid AudioSocket PCM packet.')
    if kind not in (0x00, 0x01, 0x03, 0x10, 0xff):
        raise ValueError('Unsupported AudioSocket packet type.')
    return kind, data


class AudioSocketBridge:
    """Relay narrowband SIP audio into the existing consent-checked local voice WS."""
    def __init__(self, session_id, key, opening, emit, relay_path=None, api_port=8000, outbound_private=False):
        self.session_id, self.key, self.opening, self.emit = session_id, key, opening, emit
        import os
        from pathlib import Path
        self.relay_path = relay_path or os.environ.get('AKKI_SIP_RELAY_PATH', str(Path(__file__).resolve().parents[1] / 'telephony/runtime/ipc/audio.sock'))
        self.api_port = api_port
        self.outbound_private = outbound_private
        self.reader = self.writer = self.ws = self.player = None
        self.closed = False
        self.connected = False
        self.generation = None
        self.received_frames = self.sent_frames = 0
        self.pcm = PCM8To16()

    async def open(self):
        from websockets.asyncio.client import connect
        self.ws = await connect(f'ws://127.0.0.1:{self.api_port}/api/speech/sessions/{self.session_id}/ws',
                                origin='http://localhost:5173', max_size=2_000_000, open_timeout=5,
                                additional_headers={'Authorization': 'Bearer ' + __import__('os').environ['AKKI_ADMIN_KEY']} if __import__('os').environ.get('AKKI_ADMIN_KEY') else None)
        import json
        await self.ws.send(json.dumps({'type': 'start', 'audio_processing_consent': True}))
        hello = json.loads(await asyncio.wait_for(self.ws.recv(), 10))
        if hello.get('type') != 'ready':
            raise ValueError(hello.get('detail', 'Voice session rejected.'))
        self.generation = hello['generation']
        self.reader, self.writer = await asyncio.wait_for(asyncio.open_unix_connection(self.relay_path), 5)
        self.writer.write((json.dumps({'session': self.session_id, 'key': self.key, 'outbound_private': self.outbound_private}) + '\n').encode())
        await self.writer.drain()
        self.key = None
        reply = json.loads(await asyncio.wait_for(self.reader.readline(), 5))
        if not reply.get('ready'):
            raise ValueError('Private relay reservation rejected.')

    async def stop_playback(self):
        if self.player:
            self.player.cancel()
            with __import__('contextlib').suppress(asyncio.CancelledError, ConnectionError, RuntimeError):
                await self.player
            self.player = None

    async def play(self, pcm, terminal=False):
        # 20 ms pacing; never queue an entire WAV into Asterisk's playback buffer.
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        first = True
        for start in range(0, len(pcm), 320):
            await asyncio.sleep(max(0, deadline - loop.time()))
            self.writer.write(packet(0x10, pcm[start:start+320].ljust(320, b'\x00')))
            await self.writer.drain()
            self.sent_frames += 1
            if first:
                await self.emit({'type': 'playback', 'state': 'speaking'})
                first = False
            # Reset after scheduler stalls rather than bursting stale audio.
            deadline = max(deadline + .02, loop.time())
        if terminal:
            await asyncio.sleep(.04)
            self.writer.write(packet(0x00)); await self.writer.drain()
            self.writer.close()  # Explicit AudioSocket hangup, then transport close.
        else:
            await self.emit({'type': 'playback', 'state': 'listening'})

    async def audio_input(self):
        from uuid import UUID
        kind, data = await asyncio.wait_for(read_packet(self.reader), 120)
        if kind != 0x01 or data != UUID(self.session_id).bytes:
            raise ValueError('Private call/session UUID mismatch.')
        self.connected = True
        await self.emit({'type': 'connected'})
        self.player = asyncio.create_task(self.play(self.opening))
        while True:
            kind, data = await asyncio.wait_for(read_packet(self.reader), 30)
            if kind == 0xff:
                raise ValueError('PBX reported an AudioSocket error.')
            if kind == 0x00:
                return
            if kind == 0x10:
                for frame in self.pcm.frames(data):
                    self.received_frames += 1
                    await self.ws.send(frame)
            elif kind != 0x03:
                raise ValueError('Unexpected AudioSocket identity packet.')

    async def voice_output(self):
        import base64
        import json
        async for raw in self.ws:
            event = json.loads(raw)
            if event.get('type') == 'interrupt':
                self.generation = event['generation']
                await self.stop_playback()
                await self.emit(event)
            elif event.get('type') == 'result':
                if event['generation'] != self.generation:
                    continue
                await self.stop_playback()
                await self.emit(event)
                pcm = await asyncio.to_thread(wav_to_pcm8, base64.b64decode(event['audio'])) if event.get('audio') else b''
                terminal = event['session']['state'] != 'active'
                self.player = asyncio.create_task(self.play(pcm, terminal))
            elif event.get('type') == 'error':
                raise ValueError(event.get('detail', 'Voice pipeline failed.'))
            else:
                await self.emit(event)

    async def keepalive(self):
        while True:
            await asyncio.sleep(10)
            await self.ws.send('{"type":"ping"}')

    async def run(self):
        tasks = [asyncio.create_task(self.audio_input()), asyncio.create_task(self.voice_output()), asyncio.create_task(self.keepalive())]
        try:
            done, _ = await asyncio.wait(tasks, timeout=300, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                raise TimeoutError('Private call exceeded the five-minute lab limit.')
            for task in done:
                try:
                    task.result()
                except asyncio.IncompleteReadError:
                    pass  # PBX hangup/transport EOF; read never returns stale audio.
        finally:
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.close()

    async def close(self):
        if self.closed:
            return
        self.closed = True
        await self.stop_playback()
        if self.writer:
            if self.connected and not self.writer.is_closing():
                with __import__('contextlib').suppress(ConnectionError):
                    self.writer.write(packet(0x00)); await self.writer.drain()
            self.writer.close()
            with __import__('contextlib').suppress(Exception): await self.writer.wait_closed()
        if self.ws:
            await self.ws.close()
