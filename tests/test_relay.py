"""Authenticated reverse relay admission and duplex forwarding without a PBX."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, mock_open
from uuid import uuid4

from telephony import audio_relay as relay
from backend.media import packet

class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=TemporaryDirectory(); self.path=str(Path(self.temp.name)/'relay.sock')
        self.credentials=patch('telephony.audio_relay.open',mock_open(read_data='{"bridge_key":"fictional-test-key"}'),create=True); self.credentials.start()
        self.astdb=patch('telephony.audio_relay.astdb'); self.cli=self.astdb.start()
        relay.binding=None
        self.server=await asyncio.start_unix_server(relay.control,self.path,limit=1024)
        self.audio_server=await asyncio.start_server(relay.audio,'127.0.0.1',0)
        self.port=self.audio_server.sockets[0].getsockname()[1]
        self.streams=[]
    async def asyncTearDown(self):
        for stream in self.streams: stream.close()
        for _ in range(100):
            if relay.binding is None: break
            await asyncio.sleep(.005)
        self.server.close();self.audio_server.close()
        await self.server.wait_closed();await self.audio_server.wait_closed()
        self.credentials.stop();self.astdb.stop();self.temp.cleanup()
    async def hello(self,key='fictional-test-key',identity=None):
        reader,writer=await asyncio.open_unix_connection(self.path);self.streams.append(writer)
        writer.write((json.dumps({'key':key,'session':str(identity or uuid4())})+'\n').encode());await writer.drain()
        return reader,writer
    async def test_wrong_credential_never_reserves_dialplan(self):
        reader,_=await self.hello(key='wrong')
        self.assertEqual(await asyncio.wait_for(reader.read(),1),b'')
        self.assertIsNone(relay.binding);self.cli.assert_not_called()
    async def test_single_reservation_identity_and_duplex_cleanup(self):
        identity=uuid4();host,host_writer=await self.hello(identity=identity)
        self.assertTrue(json.loads(await host.readline())['ready'])
        other,_=await self.hello();self.assertIn('error',json.loads(await other.readline()))
        bad,bad_writer=await asyncio.open_connection('127.0.0.1',self.port);self.streams.append(bad_writer)
        bad_writer.write(packet(1,uuid4().bytes));await bad_writer.drain()
        self.assertEqual(await asyncio.wait_for(bad.read(),1),b'')
        ast,ast_writer=await asyncio.open_connection('127.0.0.1',self.port);self.streams.append(ast_writer)
        identity_frame=packet(1,identity.bytes);ast_writer.write(identity_frame);await ast_writer.drain()
        self.assertEqual(await asyncio.wait_for(host.readexactly(19),1),identity_frame)
        audio_frame=packet(0x10,bytes(320))
        ast_writer.write(audio_frame);await ast_writer.drain()
        self.assertEqual(await asyncio.wait_for(host.readexactly(323),1),audio_frame)
        host_writer.write(audio_frame);await host_writer.drain()
        self.assertEqual(await asyncio.wait_for(ast.readexactly(323),1),audio_frame)
        host_writer.close();await host_writer.wait_closed()
        self.assertEqual(await asyncio.wait_for(ast.readexactly(3),1),packet(0))
        for _ in range(100):
            if relay.binding is None:break
            await asyncio.sleep(.005)
        self.assertIsNone(relay.binding)
        self.cli.assert_any_call('put',str(identity));self.cli.assert_any_call('del')

    async def test_outbound_destination_is_constant_and_uuid_validated(self):
        identity=uuid4()
        with patch('telephony.audio_relay.subprocess.run') as command:
            relay.originate_private(identity)
            self.assertEqual(command.call_args.args[0],['asterisk','-rx',f'channel originate PJSIP/1001 application AudioSocket {identity},127.0.0.1:9092'])
            command.reset_mock()
            with self.assertRaises(ValueError): relay.originate_private('1001; arbitrary-command')
            command.assert_not_called()
    async def test_unrecognized_destination_cannot_reach_cli(self):
        reader,writer=await asyncio.open_unix_connection(self.path);self.streams.append(writer)
        writer.write((json.dumps({'key':'fictional-test-key','session':str(uuid4()),'destination':'919999999999','outbound_private':True})+'\n').encode());await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(),1),b'')
        self.cli.assert_not_called()
