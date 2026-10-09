"""Private reverse AudioSocket relay; no PBX admin port, trunk or audio recording."""
import asyncio
import contextlib
import hmac
import json
import subprocess
from pathlib import Path
from uuid import UUID

binding = None


def astdb(command, session=''):
    # UUID is parsed before interpolation; never accept arbitrary CLI text.
    subprocess.run(['asterisk', '-rx', f'database {command} akki session {session}'.strip()],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)


def originate_private(identity):
    # Constant destination and context. The caller cannot supply a number or CLI text.
    identity = UUID(str(identity))
    subprocess.run(['asterisk', '-rx', f'channel originate PJSIP/1001 application AudioSocket {identity},127.0.0.1:9092'],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)


async def copy(reader, writer):
    while data := await reader.read(4096):
        writer.write(data)
        await writer.drain()


async def audio(reader, writer):
    try:
        header = await asyncio.wait_for(reader.readexactly(3), 3)
        if header != b'\x01\x00\x10':
            return
        identity = await asyncio.wait_for(reader.readexactly(16), 3)
        current = binding
        if not current or current['uuid'].bytes != identity or current['call'].done():
            return
        current['call'].set_result((reader, writer, header + identity))
        await current['closed'].wait()
    except (asyncio.IncompleteReadError, asyncio.TimeoutError):
        pass
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def control(reader, writer):
    global binding
    current = None
    tasks = []
    try:
        line = await asyncio.wait_for(reader.readline(), 5)
        if len(line) > 1024:
            return
        hello = json.loads(line)
        with open('/run/akki/credentials.json') as file:
            key = json.load(file)['bridge_key']
        if not isinstance(hello, dict) or not isinstance(hello.get('key'), str) or not hmac.compare_digest(hello['key'], key):
            return
        if set(hello) - {'key', 'session', 'outbound_private'} or type(hello.get('outbound_private', False)) is not bool:
            return
        identity = UUID(hello['session'])
        if binding is not None:
            writer.write(b'{"error":"Private lab already reserved"}\n'); await writer.drain(); return
        current = {'uuid': identity, 'call': asyncio.get_running_loop().create_future(), 'closed': asyncio.Event()}
        binding = current
        await asyncio.to_thread(astdb, 'put', str(identity))
        writer.write(b'{"ready":true,"dial_extension":"1002"}\n'); await writer.drain()
        if hello.get('outbound_private'):
            await asyncio.to_thread(originate_private, identity)
        # Detect operator disconnection while waiting for the first call.
        probe = asyncio.create_task(reader.read(1)); tasks.append(probe)
        done, _ = await asyncio.wait([current['call'], probe], timeout=120, return_when=asyncio.FIRST_COMPLETED)
        if current['call'] not in done or probe in done:
            return
        probe.cancel()
        with contextlib.suppress(asyncio.CancelledError): await probe
        ast_reader, ast_writer, uuid_frame = current['call'].result()
        writer.write(uuid_frame); await writer.drain()
        tasks += [asyncio.create_task(copy(ast_reader, writer)), asyncio.create_task(copy(reader, ast_writer))]
        await asyncio.wait(tasks[1:], return_when=asyncio.FIRST_COMPLETED)
    except (ValueError, KeyError, TypeError, asyncio.TimeoutError, ConnectionError, subprocess.SubprocessError):
        pass  # Never log the credential-bearing handshake or private audio.
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if current:
            current['closed'].set()
            if current['call'].done() and not current['call'].cancelled():
                stream = current['call'].result()[1]
                if not stream.is_closing():
                    with contextlib.suppress(ConnectionError):
                        stream.write(b'\x00\x00\x00'); await stream.drain()
                stream.close()
            if binding is current:
                with contextlib.suppress(subprocess.SubprocessError):
                    await asyncio.to_thread(astdb, 'del')
                binding = None
        writer.close()
        with contextlib.suppress(Exception): await writer.wait_closed()


async def main():
    await asyncio.to_thread(astdb, 'del')  # Remove a stale binding after restart.
    audio_server = await asyncio.start_server(audio, '127.0.0.1', 9092, limit=1024)
    path = Path('/run/akki/ipc/audio.sock')
    path.unlink(missing_ok=True)
    control_server = await asyncio.start_unix_server(control, str(path), limit=1024)
    path.chmod(0o600)
    print('Private AudioSocket relay ready', flush=True)
    async with audio_server, control_server:
        await asyncio.gather(audio_server.serve_forever(), control_server.serve_forever())


if __name__ == '__main__':
    asyncio.run(main())
