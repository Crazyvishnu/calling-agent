"""Actual loopback SIP/RTP test with two consenting simulated users. No PSTN route."""
import hashlib
import json
import math
import re
import select
import socket
import struct
import time
from uuid import uuid4

SERVER = ('127.0.0.1', 5060)


def parse(data):
    text = data.decode()
    head, _, body = text.partition('\r\n\r\n')
    lines = head.split('\r\n')
    headers = {}
    for line in lines[1:]:
        key, _, value = line.partition(':')
        headers.setdefault(key.lower(), []).append(value.strip())
    return lines[0], headers, body


def one(headers, name):
    return headers[name.lower()][0]


def response(request, code, reason, contact=None, body='', tag='recipient'):
    _, h, _ = parse(request)
    lines = [f'SIP/2.0 {code} {reason}']
    lines += ['Via: ' + v for v in h['via']]
    to = one(h, 'to')
    if ';tag=' not in to:
        to += ';tag=' + tag
    lines += ['From: ' + one(h, 'from'), 'To: ' + to, 'Call-ID: ' + one(h, 'call-id'), 'CSeq: ' + one(h, 'cseq')]
    if contact:
        lines += ['Contact: <' + contact + '>']
    if body:
        lines += ['Content-Type: application/sdp']
    lines += ['Content-Length: ' + str(len(body.encode())), '', body]
    return '\r\n'.join(lines).encode()


def sdp(port):
    return f'v=0\r\no=akki 1 1 IN IP4 127.0.0.1\r\ns=Akki private test\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\nm=audio {port} RTP/AVP 0\r\na=rtpmap:0 PCMU/8000\r\na=sendrecv\r\n'


class Phone:
    def __init__(self, user, password, port, rtp_port):
        self.user, self.password, self.port = user, password, port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', port)); self.sock.settimeout(5)
        self.rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp.bind(('127.0.0.1', rtp_port)); self.rtp.setblocking(False)
        self.contact = f'sip:{user}@127.0.0.1:{port}'
        self.tag = uuid4().hex
        self.call_id = uuid4().hex
        self.to = None

    def request(self, method, uri, cseq=1, authorization=None, body='', to=None):
        lines = [f'{method} {uri} SIP/2.0',
                 f'Via: SIP/2.0/UDP 127.0.0.1:{self.port};branch=z9hG4bK{uuid4().hex};rport',
                 'Max-Forwards: 10', f'From: <sip:{self.user}@127.0.0.1>;tag={self.tag}',
                 'To: ' + (to or '<' + uri + '>'), 'Call-ID: ' + self.call_id,
                 f'CSeq: {cseq} {method}', 'Contact: <' + self.contact + '>']
        if method == 'REGISTER':
            lines[4] = f'To: <sip:{self.user}@127.0.0.1>'
            lines += ['Expires: 120']
        if authorization:
            lines += ['Authorization: ' + authorization]
        if body:
            lines += ['Content-Type: application/sdp']
        lines += ['Content-Length: ' + str(len(body.encode())), '', body]
        return '\r\n'.join(lines).encode()

    def auth(self, challenge, method, uri):
        values = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
        realm, nonce = values['realm'], values['nonce']
        md5 = lambda s: hashlib.md5(s.encode()).hexdigest()
        ha1 = md5(f'{self.user}:{realm}:{self.password}')
        ha2 = md5(f'{method}:{uri}')
        cnonce = uuid4().hex
        qop = 'auth' if 'auth' in values.get('qop', '').split(',') else None
        digest = md5(f'{ha1}:{nonce}:00000001:{cnonce}:auth:{ha2}' if qop else f'{ha1}:{nonce}:{ha2}')
        value = f'Digest username="{self.user}", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{digest}", algorithm=MD5'
        if qop:
            value += f', qop=auth, nc=00000001, cnonce="{cnonce}"'
        if 'opaque' in values:
            value += ', opaque="' + values['opaque'] + '"'
        return value

    def register(self):
        uri = 'sip:127.0.0.1'
        self.sock.sendto(self.request('REGISTER', uri), SERVER)
        data, _ = self.sock.recvfrom(65535)
        line, headers, _ = parse(data)
        assert line.startswith('SIP/2.0 401'), 'Registration must require authentication'
        authorization = self.auth(one(headers, 'www-authenticate'), 'REGISTER', uri)
        self.sock.sendto(self.request('REGISTER', uri, 2, authorization), SERVER)
        data, _ = self.sock.recvfrom(65535)
        return parse(data)[0]


def tone(frequency):
    def ulaw(sample):
        sign = 0x80 if sample < 0 else 0
        sample = min(abs(sample), 32635) + 132
        exponent = max(0, min(7, sample.bit_length() - 8))
        mantissa = (sample >> (exponent + 3)) & 15
        return (~(sign | (exponent << 4) | mantissa)) & 255
    return bytes(ulaw(int(9000 * math.sin(2 * math.pi * frequency * i / 8000))) for i in range(160))


def invite(caller, target, receiver=None):
    uri = f'sip:{target}@127.0.0.1'
    body = sdp(caller.rtp.getsockname()[1])
    caller.call_id = uuid4().hex
    caller.sock.sendto(caller.request('INVITE', uri, body=body), SERVER)
    authorization = None
    deadline = time.monotonic() + 10
    receiver_remote = None
    while time.monotonic() < deadline:
        sockets = [caller.sock] + ([receiver.sock] if receiver else [])
        ready, _, _ = select.select(sockets, [], [], 1)
        for sock in ready:
            data, addr = sock.recvfrom(65535)
            line, h, content = parse(data)
            if sock is caller.sock:
                if line.startswith('SIP/2.0 401'):
                    caller.sock.sendto(caller.request('ACK', uri, 1, to=one(h, 'to')), SERVER)
                    authorization = caller.auth(one(h, 'www-authenticate'), 'INVITE', uri)
                    caller.sock.sendto(caller.request('INVITE', uri, 2, authorization, body=body), SERVER)
                elif line.startswith('SIP/2.0 200'):
                    caller.to = one(h, 'to')
                    caller.remote_uri = one(h, 'contact').strip('<>')
                    caller.sock.sendto(caller.request('ACK', caller.remote_uri, 2, to=caller.to), SERVER)
                    remote = int(re.search(r'm=audio (\d+)', content)[1])
                    if receiver is not None:
                        assert receiver_remote is not None, 'Called endpoint did not answer'
                    return 200, remote, receiver_remote
                elif line.startswith(('SIP/2.0 403', 'SIP/2.0 404', 'SIP/2.0 484')):
                    code = int(line.split()[1])
                    caller.sock.sendto(caller.request('ACK', uri, 2, to=one(h, 'to')), SERVER)
                    return code, None, None
            elif line.startswith('INVITE '):
                receiver_remote = int(re.search(r'm=audio (\d+)', content)[1])
                sock.sendto(response(data, 100, 'Trying'), addr)
                sock.sendto(response(data, 200, 'OK', receiver.contact, sdp(receiver.rtp.getsockname()[1])), addr)
    raise TimeoutError('Private SIP call did not reach a terminal response')


def main():
    credentials = json.load(open('/run/akki/credentials.json'))
    wrong = Phone('1001', 'incorrect-test-password', 5066, 16006)
    assert wrong.register().startswith('SIP/2.0 401'), 'Incorrect password accepted'
    wrong.sock.close(); wrong.rtp.close()
    caller = Phone('1001', credentials['1001'], 5062, 16002)
    receiver = Phone('1002', credentials['1002'], 5064, 16004)
    assert caller.register().startswith('SIP/2.0 200')
    assert receiver.register().startswith('SIP/2.0 200')
    rejected, _, _ = invite(caller, '919999999999')
    assert rejected in (403, 404, 484), 'External-style destination was not blocked'
    code, caller_remote, receiver_remote = invite(caller, '1002', receiver)
    assert code == 200
    payloads = {caller.rtp: tone(440), receiver.rtp: tone(660)}
    destinations = {caller.rtp: caller_remote, receiver.rtp: receiver_remote}
    expected = {caller.rtp: payloads[receiver.rtp], receiver.rtp: payloads[caller.rtp]}
    counts = {caller.rtp: 0, receiver.rtp: 0}
    for index in range(100):
        for sock in payloads:
            packet = struct.pack('!BBHII', 0x80, 0, index, index * 160, 1234 if sock is caller.rtp else 5678) + payloads[sock]
            sock.sendto(packet, ('127.0.0.1', destinations[sock]))
        deadline = time.monotonic() + .02
        while time.monotonic() < deadline:
            ready, _, _ = select.select(list(payloads), [], [], max(0, deadline - time.monotonic()))
            for sock in ready:
                packet, _ = sock.recvfrom(2048)
                if len(packet) >= 172 and packet[12:] == expected[sock]:
                    counts[sock] += 1
    assert min(counts.values()) >= 20, 'Bidirectional RTP payload verification failed'
    caller.sock.sendto(caller.request('BYE', caller.remote_uri, 3, to=caller.to), SERVER)
    got_bye = got_ok = False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not (got_bye and got_ok):
        ready, _, _ = select.select([caller.sock, receiver.sock], [], [], .5)
        for sock in ready:
            data, addr = sock.recvfrom(65535)
            line, h, _ = parse(data)
            if sock is receiver.sock and line.startswith('BYE '):
                sock.sendto(response(data, 200, 'OK'), addr); got_bye = True
            if sock is caller.sock and line.startswith('SIP/2.0 200') and one(h, 'cseq').endswith('BYE'):
                got_ok = True
    assert got_bye and got_ok, 'SIP hangup failed'
    print(json.dumps({'registered_test_users': 2, 'authenticated_sip_call': 'passed',
                      'rtp_packets_received_by_1001': counts[caller.rtp],
                      'rtp_packets_received_by_1002': counts[receiver.rtp],
                      'incorrect_password_rejected': True, 'external_destination_rejected': rejected,
                      'hangup': 'passed', 'pstn_connected': False}))
    for phone in (caller, receiver):
        phone.sock.close(); phone.rtp.close()


if __name__ == '__main__':
    main()
