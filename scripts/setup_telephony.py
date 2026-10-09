"""Generate private test-only Asterisk config and random credentials (gitignored)."""
import json
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1] / 'telephony' / 'runtime'


def main():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    (ROOT / 'ipc').mkdir(exist_ok=True, mode=0o700)
    conf = ROOT / 'conf'
    conf.mkdir(exist_ok=True, mode=0o700)
    credential_path = ROOT / 'credentials.json'
    if credential_path.exists():
        credentials = json.loads(credential_path.read_text())
    else:
        credentials = {user: secrets.token_urlsafe(24) for user in ('1001', '1002')}
        credential_path.write_text(json.dumps(credentials))
        credential_path.chmod(0o600)
    if 'bridge_key' not in credentials:
        credentials['bridge_key'] = secrets.token_urlsafe(32)
        credential_path.write_text(json.dumps(credentials))
        credential_path.chmod(0o600)
    transport = '''[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060
local_net=127.0.0.0/8
external_media_address=127.0.0.1
external_signaling_address=127.0.0.1
'''
    for user in ('1001', '1002'):
        password = credentials[user]
        transport += f'''
[{user}]
type=endpoint
transport=transport-udp
context=lab-only
disallow=all
allow=ulaw
auth=auth-{user}
aors={user}
direct_media=no
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes

[auth-{user}]
type=auth
auth_type=userpass
username={user}
password={password}

[{user}]
type=aor
max_contacts=1
remove_existing=yes
'''
    configs = {
        'pjsip.conf': transport,
        'extensions.conf': '''[lab-only]
exten => 1001,1,Dial(PJSIP/1001,15)
same => n,Hangup()
exten => 1002,1,Set(AKKI_SESSION=${DB(akki/session)})
same => n,GotoIf($["${AKKI_SESSION}"=""]?sip)
same => n,Answer()
same => n,AudioSocket(${AKKI_SESSION},127.0.0.1:9092)
same => n,Hangup()
same => n(sip),Dial(PJSIP/1002,15)
same => n,Hangup()
exten => 600,1,Answer()
same => n,Echo()
same => n,Hangup()
; No external-number pattern, trunk, forwarding or public-network route.
''',
        'rtp.conf': '[general]\nrtpstart=10000\nrtpend=10019\nstrictrtp=yes\n',
        'http.conf': '[general]\nenabled=no\n',
        'manager.conf': '[general]\nenabled=no\n',
        'modules.conf': '[modules]\nautoload=yes\nnoload=chan_sip.so\n',
        'logger.conf': '[general]\n[logfiles]\nconsole=warning,error\n',
        'asterisk.conf': '''[directories]
astetcdir => /etc/asterisk
astmoddir => /usr/lib/asterisk/modules
astvarlibdir => /var/lib/asterisk
astdbdir => /var/lib/asterisk
astkeydir => /var/lib/asterisk
astdatadir => /usr/share/asterisk
astagidir => /var/lib/asterisk/agi-bin
astspooldir => /var/spool/asterisk
astrundir => /run/asterisk
astlogdir => /var/log/asterisk
[options]
documentation_language = en_US
''',
    }
    for filename, contents in configs.items():
        path = conf / filename
        path.write_text(contents)
        path.chmod(0o600)
    print('Private lab config generated in telephony/runtime (gitignored).')
    print('Credentials are in runtime/credentials.json; do not share or commit that file.')
    print('From telephony: docker compose up --build -d; then docker compose exec asterisk python3 /opt/akki/sip_smoke.py')


if __name__ == '__main__':
    main()
