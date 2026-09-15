"""Exercise headless routing, station transitions, queue restart and HTTP controls."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from console import make_server
from state import State
from station import Station
from transfer import import_folder
from worker import Worker


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'server'; self.root.mkdir()
        self.card = self.base / 'card'; (self.card / 'DCIM').mkdir(parents=True)
        (self.card / 'DCIM/DJI_0001.MP4').write_bytes(b'camera-original' * 10000)
        self.command = [sys.executable, str(Path(__file__).with_name('receiver.py')), '--root', str(self.root)]
        self.state = State(self.root); self.addCleanup(self.state.close)

    def ingest(self):
        return import_folder(self.card / 'DCIM', None, None, self.command, source_uuid='1234-ABCD')

    def test_stable_route_reinsert_does_not_queue_paid_job_twice(self):
        self.ingest()
        row = self.state.imports()[0]
        key = row['id']
        self.state.write('jobs/' + key + '.json', {'id':key, 'status':'complete', 'notes':'done'})
        self.state.write('policy.json', {'project':'new-project'})
        result = self.ingest()
        self.assertIn('Projects/Inbox/', result['manifest'])
        self.assertEqual(len(self.state.imports()), 1)
        self.assertEqual(self.state.read('jobs/' + key + '.json')['status'], 'complete')
        self.assertEqual((self.card / 'DCIM/DJI_0001.MP4').read_bytes(), b'camera-original' * 10000)

    def test_station_automatic_import_safe_eject_and_reinsert(self):
        present = [True]
        actions = []
        def mount(operation, uuid=None):
            actions.append(operation)
            if operation == 'list': return {'cards':[{'uuid':'1234-ABCD'}] if present[0] else []}
            if operation == 'mount': return {'path':str(self.card)}
            return {'safe_to_remove':True}
        station = Station(self.command, mount_helper=mount)
        station.tick()
        self.assertEqual(station.event['phase'], 'safe')
        self.assertTrue(self.state.read('station.json')['safe_to_remove'])
        station.tick()
        self.assertEqual(actions.count('mount'), 1)
        present[0] = False; station.tick()
        self.assertEqual(station.event['phase'], 'waiting')
        present[0] = True; station.tick()
        self.assertEqual(actions.count('mount'), 2)
        self.assertEqual(len(self.state.imports()), 1)

    def test_station_failure_backoff_and_remote_retry(self):
        tries = []
        def mount(operation, uuid=None):
            if operation == 'list': return {'cards':[{'uuid':'1234-ABCD'}]}
            if operation == 'mount': return {'path':str(self.card)}
            return {'safe_to_remove':True}
        def fail(*args, **kwargs):
            tries.append(1); raise ConnectionError('simulated disconnect')
        station = Station(self.command, mount_helper=mount, importer=fail, now=lambda:100)
        station.tick(); station.tick()
        self.assertEqual(len(tries), 1)
        self.assertFalse(station.event['safe_to_remove'])
        self.state.write('policy.json', {'retry_nonce':'retry-now'})
        station.tick()
        self.assertEqual(len(tries), 2)
        self.assertEqual(self.state.imports(), [])

    def test_worker_queue_failure_recovery_retry_and_assignment(self):
        self.ingest(); row = self.state.imports()[0]; key=row['id']
        calls = []
        def run(payload): calls.append(payload); return 'Metadata-only review.'
        worker = Worker(self.root, run); self.addCleanup(worker.state.close)
        worker.tick(); worker.tick()
        self.assertEqual(len(calls), 1)
        self.state.write('assignments/' + key + '.json', {'project':'River film', 'session':'Sunrise'})
        self.state.write('requests/' + key + '.json', {'nonce':'second'})
        worker.tick(); self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1]['assignment']['project'], 'River film')
        self.assertNotIn('sha256', calls[-1]['listed_files'][0])
        self.state.write('jobs/' + key + '.json', {'id':key,'status':'running','request_nonce':'second'})
        worker.tick()
        self.assertEqual(self.state.read('jobs/' + key + '.json')['status'], 'failed')
        self.assertEqual(len(calls), 2)

    def test_console_origin_validation_assignment_and_escaped_input_data(self):
        self.ingest(); row=self.state.imports()[0]
        server=make_server(self.root, '127.0.0.1', 0, 'http://ingest.lan')
        thread=threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join()))
        url='http://127.0.0.1:' + str(server.server_port)
        def post(path, data, origin='http://ingest.lan'):
            request=urllib.request.Request(url+path, json.dumps(data).encode(), {'Content-Type':'application/json','Origin':origin})
            return urllib.request.urlopen(request)
        with self.assertRaises(urllib.error.HTTPError) as error:
            post('/api/policy',{'project':'oops'},'http://evil.test')
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError): post('/api/policy',{'project':'../escape'})
        with post('/api/assign',{'id':row['id'],'project':'<script>text</script>','session':'Sunrise'}): pass
        with urllib.request.urlopen(url+'/api/state') as response:
            data=json.load(response)
        self.assertEqual(data['imports'][0]['assignment']['session'],'Sunrise')
        self.assertEqual(data['imports'][0]['project'],'Inbox')
        with urllib.request.urlopen(url+'/') as response:
            self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])
        with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(url+'/../state.py')


if __name__ == '__main__': unittest.main()
