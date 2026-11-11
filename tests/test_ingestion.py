import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from unittest.mock import Mock
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion import IngestionConfig, IngestionClient, Outbox


class IngestionTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parents[1] / 'data' / 'tests'
        test_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_root)
        self.addCleanup(self.temp.cleanup)
        self.config = IngestionConfig(enabled=True, ingestion_key='x' * 32, camera_id='10',
                                      arduino_id='11', computer_id='12', signal_a_id='1', signal_b_id='2',
                                      queue_path=str(Path(self.temp.name) / 'queue.sqlite3'))
        self.outbox = Outbox(self.config)
        self.addCleanup(self.outbox.close)
        self.sender = Mock()
        self.client = IngestionClient(self.config, lambda: {}, self.sender)
        self.stamp = '2026-11-10T20:00:00.000Z'
        self.data = dict(medicao_valida=True, registrado_em=self.stamp, via_observada='A',
                         carros=2, pedestres=1, camera='conectada', arduino_conectado=True,
                         modo_arduino='AUTO', estrategia='adaptativo',
                         sinais={'A': 'verde', 'B': 'vermelho'})

    def events(self, route):
        return [json.loads(row[0]) for row in self.outbox.db.execute(
            'SELECT payload FROM events WHERE route=? ORDER BY id', (route,))]

    def test_valid_readings_only_for_observed_road_without_invented_fields(self):
        self.client.sample(self.outbox, self.data, 0, self.stamp)
        reading, = self.events('/leituras')
        self.assertEqual(reading['via'], 'A')
        self.assertEqual(reading['carrosDetectados'], 2)
        self.assertEqual(reading['tipoLeitura'], 'QUADRO')
        self.assertNotIn('veiculosUnicos', reading)
        self.assertNotIn('veiculosEmEspera', reading)

    def test_invalid_reading_is_not_zero_but_valid_zero_is_sent(self):
        self.client.sample(self.outbox, {**self.data, 'medicao_valida': False}, 0, self.stamp)
        self.assertEqual(self.events('/leituras'), [])
        self.client.sample(self.outbox, {**self.data, 'carros': 0}, 1, self.stamp)
        self.assertEqual(self.events('/leituras')[0]['carrosDetectados'], 0)

    def test_same_frame_is_not_enqueued_twice_even_after_restart(self):
        self.client.sample(self.outbox, self.data, 0, self.stamp)
        restarted = IngestionClient(self.config, lambda: {})
        restarted.sample(self.outbox, self.data, 10, '2026-11-10T20:00:10.000Z')
        self.assertEqual(len(self.events('/leituras')), 1)

    def test_uuid_and_payload_survive_network_failure_and_restart(self):
        payload = {'identificadorEvento': 'stable'}
        self.outbox.enqueue('reading:10', '/leituras', payload)
        self.sender.side_effect = TimeoutError()
        self.client.deliver_one(self.outbox, 100)
        sent = self.sender.call_args.args[2]
        reopened = Outbox(self.config)
        try:
            self.assertEqual(reopened.next(103)['payload'], sent)
            self.sender.side_effect = None
            self.client.deliver_one(reopened, 103)
            self.assertEqual(self.sender.call_args.args[2], sent)
            self.assertEqual(reopened.counts(), {})
        finally:
            reopened.close()

    def test_phase_changes_and_loss_of_state_are_recorded_for_both_signals(self):
        self.client.sample(self.outbox, self.data, 0, self.stamp)
        self.client.sample(self.outbox, self.data, .2, '2026-11-10T20:00:00.200Z')
        self.assertEqual(len(self.events('/historico-fases')), 2)
        self.client.sample(self.outbox, {**self.data, 'arduino_conectado': False}, 1, '2026-11-10T20:00:01.000Z')
        unknown = self.events('/historico-fases')[-2:]
        self.assertTrue(all(p['cor'] == 'DESCONHECIDA' and p['origemEstado'] == 'SISTEMA' for p in unknown))

    def test_telemetry_does_not_invent_cpu_fps_or_temperature(self):
        self.client.sample(self.outbox, self.data, 0, self.stamp)
        self.assertEqual(len(self.events('/telemetria')), 3)
        for payload in self.events('/telemetria'):
            self.assertEqual(set(payload), {'dispositivoId', 'registradoEm', 'status'})

    def test_conflict_pauses_event_not_treated_as_success_and_preserves_order(self):
        self.outbox.enqueue('phase:1', '/historico-fases', {'order': 1})
        self.outbox.enqueue('phase:1', '/historico-fases', {'order': 2})
        self.outbox.enqueue('reading:10', '/leituras', {'other': True})
        self.sender.side_effect = HTTPError('http://localhost', 409, '', {}, None)
        self.client.deliver_one(self.outbox, 0)
        self.assertEqual(self.outbox.counts(), {'paused': 1, 'pending': 2})
        self.assertEqual(self.outbox.next(100)['route'], '/leituras')

    def test_auth_error_pauses_without_exposing_key_or_response(self):
        self.outbox.enqueue('read', '/leituras', {})
        self.sender.side_effect = HTTPError('http://localhost', 401, 'secret-response', {}, None)
        self.client.deliver_one(self.outbox, 0)
        self.assertNotIn('secret-response', str(self.client.status()))
        self.assertNotIn(self.config.ingestion_key, str(self.client.status()))
        self.assertEqual(self.outbox.counts()['paused'], 1)

    def test_rate_limit_retries_then_exhaustion_requires_explicit_resume(self):
        self.outbox.enqueue('read', '/leituras', {})
        self.sender.side_effect = HTTPError('http://localhost', 429, '', {}, None)
        for i in range(8):
            self.client.deliver_one(self.outbox, i * 100)
        self.assertEqual(self.outbox.counts(), {'paused': 1})
        self.outbox.retry_paused()
        self.assertEqual(self.outbox.next(900)['attempts'], 0)

    def test_full_queue_preserves_existing_events(self):
        config = IngestionConfig(**{**self.config.__dict__, 'max_queue': 1})
        queue = Outbox(config)
        try:
            queue.enqueue('a', '/leituras', {'keep': True})
            with self.assertRaises(RuntimeError):
                queue.enqueue('b', '/leituras', {})
            self.assertEqual(queue.counts(), {'pending': 1})
        finally:
            queue.close()

    def test_queue_cannot_be_silently_reused_for_other_api(self):
        config = IngestionConfig(**{**self.config.__dict__, 'api_url': 'http://localhost:4000/api/v1'})
        with self.assertRaises(ValueError):
            Outbox(config)

    def test_config_rejects_remote_plaintext_and_missing_device(self):
        for change in ({'api_url': 'http://remote.example/api'}, {'camera_id': ''}, {'signal_b_id': ''}):
            with self.assertRaises(ValueError):
                IngestionConfig(**{**self.config.__dict__, **change})

    def test_blocked_network_does_not_block_status_or_sampling(self):
        gate, started = threading.Event(), threading.Event()
        def slow_sender(*args):
            started.set()
            gate.wait(2)
        client = IngestionClient(self.config, lambda: self.data, slow_sender)
        client.start()
        try:
            self.assertTrue(started.wait(2))
            self.assertTrue(client.status()['habilitada'])
            # A conexão do coletor pode gravar enquanto a thread HTTP está bloqueada.
            self.outbox.enqueue('independent', '/leituras', {})
        finally:
            gate.set()
            client.stop()

    def test_first_start_initializes_fresh_queue_before_workers(self):
        config = IngestionConfig(**{**self.config.__dict__,
                                    'queue_path': str(Path(self.temp.name) / 'fresh.sqlite3')})
        delivered = threading.Event()
        client = IngestionClient(config, lambda: self.data, lambda *args: delivered.set())
        client.start()
        try:
            self.assertTrue(delivered.wait(3))
            self.assertIsNone(client.status()['erro'])
            self.assertTrue(all(thread.is_alive() for thread in client._threads))
        finally:
            client.stop()


if __name__ == '__main__':
    unittest.main()
