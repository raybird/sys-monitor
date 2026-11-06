"""Raw Docker samples: boundaries that would otherwise create false evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('container_probe', Path(__file__).resolve().parents[1] / 'src/container_probe.py')
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class CounterTests(unittest.TestCase):
    def test_rates_use_elapsed_time_and_identity(self):
        prev = {'id': 'abc', 'started': 'start', 'epoch': 100, 'read': 1000, 'write': 50}
        self.assertEqual(probe.io_rates(prev, 'abc', 'start', 104, 1400, 90), (100, 10))
        for old in ({}, dict(prev, id='new'), dict(prev, started='restart'), dict(prev, epoch=105)):
            self.assertEqual(probe.io_rates(old, 'abc', 'start', 104, 1400, 90), (None, None))
        self.assertEqual(probe.io_rates(prev, 'abc', 'start', 104, 2, 90), (None, None))
        self.assertEqual(probe.io_rates(prev, 'abc', 'start', 104, None, None), (None, None))

    def test_raw_block_bytes_and_missing_accounting(self):
        self.assertEqual(probe.block_bytes({'blkio_stats': {'io_service_bytes_recursive': [
            {'op': 'Read', 'value': 100}, {'op': 'Read', 'value': 30}, {'op': 'Write', 'value': 70}, {'op': 'Total', 'value': 200}
        ]}}), (130, 70))
        self.assertEqual(probe.block_bytes({}), (None, None))

    def test_bounded_processes_preserve_dstate_and_never_argv(self):
        titles = ['PID', 'STAT', '%CPU', '%MEM', 'COMMAND']
        rows = [[str(n), 'R', str(n), str(40-n), 'worker'] for n in range(1, 25)]
        rows.append(['99', 'D', '0', '0', 'io-worker'])
        processes, count, zombies, dstate = probe.process_sample({'Titles': titles, 'Processes': rows})
        self.assertLessEqual(len(processes), 15)
        self.assertEqual(count, 25)
        self.assertEqual(zombies, 0)
        self.assertEqual(dstate, 1)
        self.assertTrue(any(p['pid'] == '99' for p in processes))
        self.assertEqual(set(processes[0]), {'pid', 'state', 'cpu', 'memory', 'name'})

    def test_no_process_output_is_unknown(self):
        with self.assertRaises(ValueError):
            probe.process_sample({'Titles': [], 'Processes': []})


class SamplingTests(unittest.TestCase):
    def test_unavailable_endpoint_records_explicit_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(probe, 'endpoint', side_effect=OSError('denied')):
                state, rows = probe.collect('2026-11-06T00:00:00Z', 100, 'a,b', Path(td))
        self.assertEqual(state, 'unavailable')
        self.assertEqual(rows[0]['container'], '')
        self.assertEqual(rows[0]['sample_status'], 'unavailable')

    def test_multi_project_raw_stats_and_private_cache(self):
        class Engine:
            def get(self, path):
                if path == '/containers/json?all=1':
                    return [{'Id': 'abc', 'State': 'running', 'Names': ['/worker'], 'Labels': {'com.docker.compose.project': 'b', 'com.docker.compose.service': 'worker'}}]
                if path.endswith('/json'):
                    return {'State': {'StartedAt': 'start', 'OOMKilled': False}, 'RestartCount': 0}
                if '/stats?' in path:
                    return {'memory_stats': {'usage': 100, 'limit': 1000}, 'pids_stats': {'current': 2}, 'blkio_stats': {'io_service_bytes_recursive': [{'op': 'Read', 'value': 100}, {'op': 'Write', 'value': 50}]}}
                return {'Titles': ['PID', 'STAT', '%CPU', '%MEM', 'COMMAND'], 'Processes': [['3', 'D', '1', '2', 'worker']]}
        with tempfile.TemporaryDirectory() as td, patch.object(probe, 'endpoint', return_value='/unused'), patch.object(probe, 'Engine', return_value=Engine()):
            state, rows = probe.collect('now', 100, 'a,b', Path(td))
            self.assertEqual(state, 'ok')
            self.assertEqual(rows[0]['is_tracked_project'], 1)
            self.assertEqual(rows[0]['read_bytes'], 100)
            self.assertIsNone(rows[0]['read_bps'])
            self.assertEqual(rows[0]['health'], 'not_configured')
            self.assertEqual(rows[0]['dstate'], 1)
            self.assertEqual((Path(td) / 'docker-counters.json').stat().st_mode & 0o777, 0o600)
            _, rows = probe.collect('later', 110, 'a,b', Path(td))
            self.assertEqual(rows[0]['read_bps'], 0)

    def test_deadline_limits_calls(self):
        engine = probe.Engine('/unused', time.monotonic() - 1)
        with self.assertRaises(TimeoutError):
            engine.get('/containers/json')

class CollectorIntegrationTests(unittest.TestCase):
    def run_collector(self, root, body):
        import os
        import subprocess
        helper = Path(root) / 'probe.py'
        helper.write_text(body)
        env = dict(os.environ, XDG_STATE_HOME=root, FREEZE_WATCH_CONTAINER_PROBE=str(helper),
                   FREEZE_WATCH_PYTHON='/usr/bin/python3', FREEZE_WATCH_MAX_SAMPLES='1',
                   FREEZE_WATCH_JOURNALCTL='/bin/false')
        result = subprocess.run(['bash', str(Path(__file__).resolve().parents[1] / 'src/freeze-monitor')],
                                env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return Path(root) / 'freeze-monitor'

    def test_real_shell_writes_compatible_rows_and_anomaly(self):
        import csv
        row = dict.fromkeys(probe.FIELDS, 'NA')
        row.update(container='worker', is_tracked_project=1, cpu_pct=12, tasks=3, processes=2,
                   zombies=0, oom_killed='false', restart_count=0, container_id='abc', project='b',
                   service='worker', health='unhealthy', dstate=1, container_state='running', process_sample=json.dumps([
                       dict(pid='3', state='D', cpu=0, memory=1, name='程式')]), sample_status='ok', process_status='ok')
        body = "import csv, sys\nrow=" + repr(row) + "\nrow.update(timestamp=sys.argv[1],epoch=sys.argv[2])\nprint('ok')\ncsv.writer(sys.stdout, delimiter='\\t',lineterminator='\\n').writerow(row[k] for k in " + repr(probe.FIELDS) + ")\n"
        with tempfile.TemporaryDirectory() as td:
            state = self.run_collector(td, body)
            rows = list(csv.DictReader(next(state.glob('docker-*.tsv')).read_text().splitlines(), delimiter='\t'))
            self.assertEqual(rows[0]['container_id'], 'abc')
            self.assertEqual(json.loads(rows[0]['process_sample'])[0]['name'], '程式')
            metrics = list(csv.DictReader(next(state.glob('metrics-*.tsv')).read_text().splitlines(), delimiter='\t'))
            self.assertEqual(metrics[0]['tracked_processes'], '2')
            self.assertIn('Docker anomaly: worker:', (state / 'events.log').read_text())

    def test_failed_helper_cannot_stop_host_metrics_or_keep_old_snapshot(self):
        import csv
        with tempfile.TemporaryDirectory() as td:
            state = self.run_collector(td, 'raise SystemExit(1)\n')
            rows = list(csv.DictReader(next(state.glob('docker-*.tsv')).read_text().splitlines(), delimiter='\t'))
            self.assertEqual(rows[0]['container'], '')
            self.assertEqual(rows[0]['sample_status'], 'unavailable')
            self.assertEqual(len(list(csv.DictReader(next(state.glob('metrics-*.tsv')).read_text().splitlines(), delimiter='\t'))), 1)

class FailureAndLimitTests(unittest.TestCase):
    def test_empty_snapshot_and_missing_stats_have_distinct_states(self):
        class Empty:
            def get(self, path):
                return []
        with tempfile.TemporaryDirectory() as td, patch.object(probe, 'endpoint', return_value='/unused'), patch.object(probe, 'Engine', return_value=Empty()):
            state, rows = probe.collect('now', 100, 'a,b', Path(td))
            self.assertEqual(state, 'ok')
            self.assertEqual(rows[0]['sample_status'], 'empty')
        class Broken:
            def get(self, path):
                if path == '/containers/json?all=1':
                    return [{'Id': 'abc', 'State': 'running', 'Names': ['/worker'], 'Labels': None}]
                raise TimeoutError('timeout')
        with tempfile.TemporaryDirectory() as td, patch.object(probe, 'endpoint', return_value='/unused'), patch.object(probe, 'Engine', return_value=Broken()):
            state, rows = probe.collect('now', 100, 'a,b', Path(td))
            self.assertEqual(state, 'partial')
            self.assertEqual(rows[0]['sample_status'], 'unavailable_or_timeout')
            self.assertIsNone(rows[0]['cpu_pct'])

    def test_more_than_32_containers_do_not_starve_deep_projects(self):
        seen = []
        class Many:
            def get(self, path):
                if path == '/containers/json?all=1':
                    return [{'Id': str(n).zfill(3), 'State':'running', 'Labels': {'com.docker.compose.project': 'tracked'}, 'Names': ['/worker'+str(n)]} for n in range(80)]
                if path.endswith('/json'):
                    return {'State': {'StartedAt': 'start'}}
                if '/stats?' in path:
                    return {}
                seen.append(path.split('/')[2])
                return {'Titles': ['PID', 'STAT', '%CPU', '%MEM', 'COMMAND'], 'Processes': []}
        with tempfile.TemporaryDirectory() as td, patch.object(probe, 'endpoint', return_value='/unused'), patch.object(probe, 'Engine', return_value=Many()):
            for epoch in range(0, 300, 30):
                state, rows = probe.collect('now', epoch, 'tracked', Path(td))
                self.assertEqual(state, 'partial')
                self.assertEqual(len(rows), 32)
                self.assertEqual(sum(r['process_status'] == 'ok' for r in rows), 8)
        self.assertEqual(len(set(seen)), 80)

    def test_engine_rejects_nonlocal_endpoint(self):
        with patch.dict('os.environ', {'DOCKER_HOST': 'tcp://remote:2375'}):
            with self.assertRaises(OSError):
                probe.endpoint()

    def test_exact_fields_match_dashboard_and_shell_header(self):
        text = (Path(__file__).resolve().parents[1] / 'src/freeze-monitor').read_text()
        expected = '\\t'.join(probe.FIELDS) + '\\n'
        self.assertIn(expected, text)

    def test_helper_main_roundtrips_json_without_double_escaping(self):
        import csv
        import io
        row = dict(timestamp='now', epoch=100, container='worker', process_sample=json.dumps([{'name': '程式', 'pid': '2'}]))
        output = io.StringIO()
        with patch.object(probe, 'collect', return_value=('ok', [row])), patch('sys.argv', ['probe', 'now', '100', 'a', '/tmp']), patch('sys.stdout', output):
            probe.main()
        record = next(csv.DictReader(output.getvalue().splitlines()[1:], fieldnames=probe.FIELDS, delimiter='\t'))
        self.assertEqual(json.loads(record['process_sample'])[0]['name'], '程式')

class HardTimeoutTest(CollectorIntegrationTests):
    def test_hung_helper_has_hard_limit_and_host_survives(self):
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as td:
            state = self.run_collector(td, 'import sys,time\nfrom pathlib import Path\n(Path(sys.argv[4])/"docker-counters.json").write_text("{}")\ntime.sleep(60)\n')
            self.assertTrue(next(state.glob('metrics-*.tsv')).read_text().count('\n') >= 2)
            self.assertFalse((state / 'docker-counters.json').exists())
        self.assertLess(time.monotonic() - started, 11)

class RecoveryRegressionTests(unittest.TestCase):
    class EngineFixture:
        def __init__(self, state='running', read=100, fail_stats=False, cpu=1000, system=10000, started='start', cores=2):
            self.state, self.read, self.fail_stats = state, read, fail_stats
            self.cpu, self.system, self.started, self.cores = cpu, system, started, cores
            self.calls = []

        def get(self, path):
            self.calls.append(path)
            if path.startswith('/containers/json'):
                if self.state != 'running' and 'all=1' not in path:
                    return []
                return [{'Id':'abc','Names':['/worker'],'Labels':{'com.docker.compose.project':'tracked'},'State':self.state}]
            if path.endswith('/json'):
                return {'State':{'StartedAt':self.started,'Status':self.state,'OOMKilled':self.state=='exited'},'RestartCount':2}
            if '/stats?' in path:
                if self.fail_stats:
                    raise OSError('stats unavailable')
                return {'cpu_stats':{'cpu_usage':{'total_usage':self.cpu},'system_cpu_usage':self.system,'online_cpus':self.cores},
                        'blkio_stats':{'io_service_bytes_recursive':[{'op':'Read','value':self.read},{'op':'Write','value':0}]}}
            return {'Titles':['PID','STAT','%CPU','%MEM','COMMAND'],'Processes':[]}

    def sample(self, td, engine, epoch=100):
        with patch.object(probe, 'endpoint', return_value='/unused'), patch.object(probe, 'Engine', return_value=engine):
            return probe.collect('then', epoch, 'tracked', Path(td))

    def test_exited_oom_is_inspected_without_stats_or_top(self):
        engine = self.EngineFixture(state='exited')
        with tempfile.TemporaryDirectory() as td:
            state, rows = self.sample(td, engine)
        self.assertEqual(rows[0]['container'], 'worker')
        self.assertEqual(rows[0]['container_state'], 'exited')
        self.assertEqual(rows[0]['oom_killed'], 'true')
        self.assertEqual(rows[0]['restart_count'], 2)
        self.assertEqual(rows[0]['process_status'], 'stopped')
        self.assertIsNone(rows[0]['cpu_pct'])
        self.assertFalse(any('/stats?' in p or '/top?' in p for p in engine.calls))

    def test_inspect_evidence_survives_stats_failure(self):
        with tempfile.TemporaryDirectory() as td:
            _, rows = self.sample(td, self.EngineFixture(fail_stats=True))
        self.assertEqual(rows[0]['restart_count'], 2)
        self.assertEqual(rows[0]['oom_killed'], 'false')
        self.assertEqual(rows[0]['sample_status'], 'unavailable_or_timeout')

    def test_daemon_outage_invalidates_cpu_and_io_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            self.sample(td, self.EngineFixture(), 100)
            with patch.object(probe, 'endpoint', side_effect=OSError('offline')):
                probe.collect('offline', 130, 'tracked', Path(td))
            _, rows = self.sample(td, self.EngineFixture(read=700,cpu=2000,system=20000), 160)
            self.assertIsNone(rows[0]['read_bps'])
            self.assertIsNone(rows[0]['cpu_pct'])

    def test_cpu_requires_identity_positive_cores_and_forward_time(self):
        for first, second, epoch in [
            (self.EngineFixture(started=''), self.EngineFixture(started='',cpu=2000,system=20000), 130),
            (self.EngineFixture(), self.EngineFixture(cpu=2000,system=20000,cores=0), 130),
            (self.EngineFixture(), self.EngineFixture(cpu=2000,system=20000), 90),
        ]:
            with self.subTest(epoch=epoch,cores=second.cores,started=second.started), tempfile.TemporaryDirectory() as td:
                self.sample(td, first, 100)
                _, rows = self.sample(td, second, epoch)
                self.assertIsNone(rows[0]['cpu_pct'])

    def test_valid_cpu_delta_matches_one_core_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            self.sample(td, self.EngineFixture(), 100)
            _, rows = self.sample(td, self.EngineFixture(cpu=3000,system=20000), 130)
        self.assertEqual(rows[0]['cpu_pct'], 40)

    def test_corrupt_cache_entry_recovers_as_first_sample(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'docker-counters.json').write_text('{"abc": []}')
            _, rows = self.sample(td, self.EngineFixture())
            self.assertEqual(rows[0]['sample_status'], 'ok')
            self.assertIsNone(rows[0]['read_bps'])
            self.assertIsNone(rows[0]['cpu_pct'])

class MixedRotationRegressionTests(unittest.TestCase):
    def test_running_priority_cannot_starve_exited_oom_containers(self):
        inspected=set()
        class Mixed:
            def get(self, path):
                if path.startswith('/containers/json'):
                    return [{'Id':str(n).zfill(3),'Names':['/worker'+str(n)],'Labels':{'com.docker.compose.project':'tracked'},'State':'running' if n<8 else 'exited'} for n in range(64)]
                identity=int(path.split('/')[2])
                if path.endswith('/json'):
                    inspected.add(identity)
                    return {'State':{'Status':'running' if identity<8 else 'exited','StartedAt':'start','OOMKilled':identity>=8},'RestartCount':0}
                if '/stats?' in path:
                    return {}
                return {'Titles':['PID','STAT','%CPU','%MEM','COMMAND'],'Processes':[]}
        with tempfile.TemporaryDirectory() as td, patch.object(probe,'endpoint',return_value='/unused'), patch.object(probe,'Engine',return_value=Mixed()):
            for epoch in range(0,600,30):
                _, rows=probe.collect('now',epoch,'tracked',Path(td))
                self.assertEqual(len(rows),32)
                self.assertEqual(sum(r['container_state']=='running' for r in rows),8)
                self.assertTrue(all(r['oom_killed']=='true' for r in rows if r['container_state']=='exited'))
        self.assertEqual(inspected,set(range(64)))
