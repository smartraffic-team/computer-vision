"""Regras e protocolo serial com relógio controlado, sem acionar a maquete."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traffic import TrafficController


class TrafficTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.controller = TrafficController('', lambda: {}, clock=lambda: self.now)
        self.sent = []
        def write(data):
            self.sent.append(data)
            return len(data)
        self.controller.arduino = SimpleNamespace(write=write)

    def state(self, phase='A_GREEN', mode='AUTO', seq=0, elapsed=0, duration=12000, target='A'):
        self.controller.receive(f'STATE ST1 {seq} {phase} {elapsed} {duration} {mode} {target}', self.now)

    def sample(self, cars, stamp='one', road='A', valid=True):
        return dict(medicao_valida=valid, carros=cars, registrado_em=stamp, via_observada=road)

    def test_no_commands_before_versioned_handshake(self):
        self.controller.receive('A VERDE | B VERMELHO', self.now)
        self.controller.tick(self.sample(3), self.now)
        self.assertFalse(self.sent)
        self.assertFalse(self.controller.snapshot()['arduino_conectado'])

    def test_green_limits_unobserved_road_and_zero(self):
        for cars, expected in [(0, 8), (3, 14), (100, 25)]:
            self.controller._samples.clear()
            self.controller._sample_id = None
            self.controller._plan(self.sample(cars), self.now)
            self.assertEqual(self.controller.snapshot()['verdes_planejados'], {'A': expected, 'B': 12})

    def test_observed_b_and_people_do_not_control_phases(self):
        self.controller.observed_road = 'B'
        sample = {**self.sample(2, road='B'), 'pedestres': 50}
        self.controller._plan(sample, self.now)
        self.assertEqual(self.controller.snapshot()['verdes_planejados'], {'A': 12, 'B': 12})

    def test_median_deduplicates_frames_and_ignores_single_peak(self):
        for time, count in [(0, 2), (.5, 2), (1, 100)]:
            self.controller._plan(self.sample(count, str(time)), time)
        for _ in range(20):
            self.controller._plan(self.sample(100, '1'), 1.5)
        self.assertEqual(self.controller.snapshot()['carros_filtrados'], 2)
        self.assertEqual(len(self.controller._samples), 3)

    def test_invalid_measurement_immediately_uses_fixed_cycle_and_clears_filter(self):
        self.controller._plan(self.sample(8), 0)
        for sample in [self.sample(None, valid=False), self.sample(3, road='B'), {}]:
            self.controller._plan(sample, 1)
            self.assertEqual(self.controller.snapshot()['verdes_planejados'], {'A': 12, 'B': 12})
            self.assertIsNone(self.controller.snapshot()['carros_filtrados'])
        self.controller._plan(self.sample(0, 'new'), 2)
        self.assertEqual(self.controller.snapshot()['verdes_planejados']['A'], 8)

    def test_old_duplicate_sample_cannot_extend_green_forever(self):
        self.controller._plan(self.sample(100), 0)
        self.controller._plan(self.sample(100), 3)
        self.assertEqual(self.controller.snapshot()['estrategia'], 'ciclo_fixo')

    def test_commands_require_matching_ack_and_missing_ack_times_out(self):
        self.state()
        self.controller.tick(self.sample(3), 0)
        self.assertEqual(self.sent, [b'AUTO 1 14000 12000\n'])
        self.state(seq=0)
        self.controller.tick(self.sample(3), 1)
        self.assertEqual(len(self.sent), 1)
        with self.assertRaises(TimeoutError):
            self.controller.tick({}, 2.1)
        self.state(seq=1)
        self.assertFalse(self.controller.snapshot()['comando_pendente'])

    def test_yellow_and_all_red_reported_without_inventing_green(self):
        self.state(phase='A_YELLOW', duration=3000, target='B')
        state = self.controller.snapshot()
        self.assertEqual(state['sinais'], {'A': 'amarelo', 'B': 'vermelho'})
        self.assertIsNone(state['semaforo'])
        self.state(phase='ALL_RED', duration=1000, target='B')
        self.assertEqual(self.controller.snapshot()['sinais'], {'A': 'vermelho', 'B': 'vermelho'})
        self.now = 3
        self.assertEqual(self.controller.snapshot()['sinais'], {'A': None, 'B': None})

    def test_manual_queued_once_and_no_state_invented_before_ack(self):
        self.state()
        self.assertFalse(self.controller.request_change('B')['ok'])
        self.assertTrue(self.controller.set_mode('manual')['ok'])
        self.assertTrue(self.controller.request_change('B')['ok'])
        self.assertFalse(self.controller.request_change('A')['ok'])
        self.controller.tick({}, 0)
        self.assertEqual(self.sent, [b'MANUAL 1 B\n'])
        self.assertEqual(self.controller.snapshot()['semaforo'], 'A')
        self.state(seq=1, mode='MANUAL', target='B')
        self.assertTrue(self.controller.snapshot()['em_transicao'])
        self.assertFalse(self.controller.request_change('A')['ok'])

    def test_rejected_command_does_not_confirm_target_or_kill_link(self):
        self.state()
        self.controller.set_mode('manual')
        self.controller.request_change('B')
        self.controller.tick({}, 0)
        self.controller.receive('ERROR ST1 1 comando_invalido_ou_transicao', 0)
        self.assertFalse(self.controller.snapshot()['comando_pendente'])
        self.assertEqual(self.controller.snapshot()['semaforo'], 'A')
        self.assertTrue(self.controller.snapshot()['aviso_controle'])

    def test_partial_serial_write_is_failure(self):
        self.state()
        self.controller.arduino.write = Mock(return_value=1)
        with self.assertRaises(OSError):
            self.controller.tick({}, 0)

    def test_serial_disconnect_invalidates_reported_signals(self):
        self.state()
        self.controller.port = 'fake'
        fake = SimpleNamespace(read=Mock(side_effect=OSError('disconnected')), in_waiting=0, close=Mock())
        with patch.dict(sys.modules, {'serial': SimpleNamespace(Serial=Mock(return_value=fake))}):
            with self.assertLogs(level='WARNING'):
                self.controller._run()
        self.assertFalse(self.controller.snapshot()['arduino_conectado'])
        self.assertIsNone(self.controller.snapshot()['semaforo'])
        fake.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
