"""Testes sem webcam/Arduino físicos nem carregamento do modelo real."""

from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision import CameraMonitor, DetectionResult, VisionConfig, YoloDetector, open_camera
import smarttraffic_app as web


def wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('Condição não atingida dentro do prazo.')


class FakeCamera:
    def __init__(self):
        self.reads = 0
        self.failed = False
        self.released = False
        self.gate = threading.Event()
        self.gate.set()
        self.blocked = threading.Event()

    def isOpened(self):
        return not self.released

    def read(self):
        if not self.gate.is_set():
            self.blocked.set()
            self.gate.wait(3)
        self.reads += 1
        return (False, None) if self.failed else (True, np.zeros((24, 32, 3), dtype=np.uint8))

    def release(self):
        self.released = True


class CameraOpeningTests(unittest.TestCase):
    def test_selected_backend_and_device_are_passed_to_opencv(self):
        import cv2
        for name, backend in [('DSHOW', cv2.CAP_DSHOW), ('MSMF', cv2.CAP_MSMF),
                              ('AUTO', cv2.CAP_ANY)]:
            with self.subTest(backend=name), patch('cv2.VideoCapture') as capture:
                camera = open_camera(VisionConfig(camera_index=1, camera_backend=name))
                capture.assert_called_once_with(1, backend)
                self.assertIs(camera, capture.return_value)

    def test_invalid_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            VisionConfig(camera_backend='invalid')


class MonitorTests(unittest.TestCase):
    def start_monitor(self, config=None, detector=None, camera_factory=None, clock=time.monotonic):
        camera = FakeCamera()
        factory = camera_factory or Mock(return_value=camera)
        monitor = CameraMonitor(
            config or VisionConfig(fps=100, detection_interval=0.01, reconnect_interval=0.1),
            camera_factory=factory,
            detector_factory=Mock(return_value=detector or SimpleNamespace(
                detect=lambda frame: DetectionResult(2, 1, frame.copy()))),
            clock=clock,
        )
        def cleanup():
            camera.gate.set()
            monitor.stop()
        self.addCleanup(cleanup)
        monitor.start()
        return monitor, camera, factory

    def test_initial_unavailable_is_not_zero(self):
        state = CameraMonitor(VisionConfig()).snapshot()
        self.assertIsNone(state['carros'])
        self.assertFalse(state['medicao_valida'])
        self.assertEqual(state['vias']['B']['estado'], 'sem_medicao')

    def test_one_camera_and_counts_belong_only_to_configured_road(self):
        monitor, camera, factory = self.start_monitor(
            VisionConfig(observed_road='B', fps=100, detection_interval=0.01))
        wait_until(lambda: monitor.snapshot()['medicao_valida'])
        state = monitor.snapshot()
        self.assertEqual(factory.call_count, 1)
        self.assertEqual((state['vias']['B']['carros'], state['vias']['B']['pedestres']), (2, 1))
        self.assertIsNone(state['vias']['A']['carros'])
        self.assertEqual(state['vias']['A']['estado'], 'sem_medicao')
        self.assertTrue(state['registrado_em'].endswith('+00:00'))
        monitor.stop()
        self.assertTrue(camera.released)

    def test_valid_zero_and_disconnect_are_different(self):
        monitor, camera, _ = self.start_monitor(
            VisionConfig(fps=100, detection_interval=0.01, reconnect_interval=10),
            detector=SimpleNamespace(detect=lambda frame: DetectionResult(0, 0, frame.copy())))
        wait_until(lambda: monitor.snapshot()['medicao_valida'])
        self.assertEqual(monitor.snapshot()['carros'], 0)
        camera.failed = True
        wait_until(lambda: monitor.snapshot()['camera'] == 'desconectada')
        self.assertIsNone(monitor.snapshot()['carros'])
        self.assertIsNone(monitor.latest_frame())
        self.assertIsNone(monitor.display_frame())

    def test_stalled_camera_expires_frame_and_measurement(self):
        now = [0.0]
        monitor, camera, _ = self.start_monitor(clock=lambda: now[0])
        wait_until(lambda: monitor.snapshot()['medicao_valida'])
        camera.gate.clear()
        self.assertTrue(camera.blocked.wait(1))
        now[0] = 6.0
        state = monitor.snapshot()
        self.assertEqual(state['camera'], 'sem_imagem')
        self.assertIsNone(state['carros'])
        self.assertIsNone(monitor.latest_frame())
        self.assertIsNone(monitor.display_frame())

    def test_capture_continues_during_slow_detection_and_old_result_is_discarded(self):
        started, finish = threading.Event(), threading.Event()
        def slow_detect(frame):
            started.set()
            finish.wait(2)
            return DetectionResult(99, 99, frame.copy())
        monitor, camera, _ = self.start_monitor(
            VisionConfig(fps=100, detection_interval=0.01, reconnect_interval=10),
            detector=SimpleNamespace(detect=slow_detect))
        self.addCleanup(finish.set)
        self.assertTrue(started.wait(1))
        initial_reads = camera.reads
        wait_until(lambda: camera.reads >= initial_reads + 3)
        camera.failed = True
        wait_until(lambda: monitor.snapshot()['camera'] == 'desconectada')
        finish.set()
        time.sleep(0.05)
        self.assertIsNone(monitor.snapshot()['carros'])
        self.assertIsNone(monitor.display_frame())

    def test_camera_reconnects_and_releases_failed_device(self):
        first, second = FakeCamera(), FakeCamera()
        factory = Mock(side_effect=[first, second])
        monitor, _, _ = self.start_monitor(camera_factory=factory)
        wait_until(lambda: monitor.snapshot()['medicao_valida'])
        first.failed = True
        wait_until(lambda: first.released)
        wait_until(lambda: factory.call_count == 2 and monitor.snapshot()['medicao_valida'])
        self.assertGreater(second.reads, 0)

    def test_model_load_failure_keeps_video_and_null_counts(self):
        camera = FakeCamera()
        monitor = CameraMonitor(VisionConfig(), lambda config: camera,
                                Mock(side_effect=RuntimeError('modelo indisponível')))
        self.addCleanup(monitor.stop)
        with self.assertLogs(level='ERROR'):
            monitor.start()
            wait_until(lambda: monitor.snapshot()['deteccao'] == 'erro')
        wait_until(lambda: monitor.latest_frame() is not None)
        self.assertIsNone(monitor.snapshot()['carros'])
        np.testing.assert_array_equal(monitor.display_frame(), monitor.latest_frame())

    def test_detection_failure_invalidates_counts_then_recovers(self):
        fail = threading.Event()
        detector = SimpleNamespace()
        def detect(frame):
            if fail.is_set():
                raise RuntimeError('inferência inválida')
            return DetectionResult(1, 2, frame.copy())
        detector.detect = detect
        monitor, _, _ = self.start_monitor(detector=detector)
        wait_until(lambda: monitor.snapshot()['medicao_valida'])
        with self.assertLogs(level='ERROR'):
            fail.set()
            wait_until(lambda: monitor.snapshot()['deteccao'] == 'erro')
            self.assertIsNone(monitor.snapshot()['carros'])
            fail.clear()
        wait_until(lambda: monitor.snapshot()['medicao_valida'])

    def test_display_uses_analyzed_frame_and_drops_expired_annotations(self):
        now = [0.0]
        started, finish = threading.Event(), threading.Event()
        calls = [0]
        annotated = np.full((24, 32, 3), 127, dtype=np.uint8)
        def detect(frame):
            calls[0] += 1
            if calls[0] > 1:
                started.set()
                finish.wait(2)
            return DetectionResult(1, 0, annotated.copy())
        monitor, camera, _ = self.start_monitor(
            detector=SimpleNamespace(detect=detect), clock=lambda: now[0])
        self.addCleanup(finish.set)
        self.assertTrue(started.wait(1))
        reads = camera.reads
        wait_until(lambda: camera.reads >= reads + 2)
        np.testing.assert_array_equal(monitor.display_frame(), annotated)
        self.assertFalse(monitor.latest_frame().any())
        # Alterações feitas pelo stream não podem contaminar o quadro guardado.
        rendered = monitor.display_frame()
        rendered[:] = 255
        np.testing.assert_array_equal(monitor.display_frame(), annotated)
        now[0] = 6.0
        reads = camera.reads
        wait_until(lambda: camera.reads >= reads + 2)
        self.assertFalse(monitor.display_frame().any())
        self.assertIsNone(monitor.snapshot()['carros'])


class DetectorTests(unittest.TestCase):
    def test_roi_and_only_car_person_classes(self):
        model = Mock(return_value=[SimpleNamespace(boxes=[
            SimpleNamespace(cls=[2], conf=[0.91], xyxy=[[5, 10, 35, 40]]),
            SimpleNamespace(cls=[0], conf=[0.85], xyxy=[[50, 5, 90, 45]]),
            SimpleNamespace(cls=[5]),
        ])])
        model.names = {2: 'car', 0: 'person', 5: 'bus'}
        with patch.dict(sys.modules, {'ultralytics': SimpleNamespace(YOLO=Mock(return_value=model))}):
            detector = YoloDetector(VisionConfig(roi=(0.25, 0.25, 0.75, 0.75)))
        import cv2
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        with patch('cv2.rectangle', wraps=cv2.rectangle) as rectangles, \
                patch('cv2.putText', wraps=cv2.putText) as texts:
            result = detector.detect(frame)
        self.assertEqual((result.cars, result.people), (1, 1))
        boxes = [call.args[1:3] for call in rectangles.call_args_list if call.args[4] == 2]
        self.assertEqual(boxes, [((55, 35), (85, 65)), ((100, 30), (140, 70))])
        self.assertEqual([call.args[1] for call in texts.call_args_list], ['Carro', 'Pessoa'])
        self.assertFalse(frame.any())
        self.assertTrue(result.annotated_frame.any())
        self.assertEqual(model.call_args.args[0].shape, (50, 100, 3))
        self.assertEqual(model.call_args.kwargs['conf'], 0.35)

    def test_empty_detections_return_original_image_without_old_boxes(self):
        model = Mock(return_value=[SimpleNamespace(boxes=[])])
        with patch.dict(sys.modules, {'ultralytics': SimpleNamespace(YOLO=Mock(return_value=model))}):
            detector = YoloDetector(VisionConfig())
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        result = detector.detect(frame)
        self.assertEqual((result.cars, result.people), (0, 0))
        np.testing.assert_array_equal(result.annotated_frame, frame)

    def test_rejects_invalid_road_roi_and_intervals(self):
        for kwargs in ({'observed_road': 'C'}, {'roi': (0, 0, 0, 1)},
                       {'roi': (0, 0, 2, 1)}, {'fps': 0}, {'stale_after': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                VisionConfig(**kwargs)


class WebTests(unittest.TestCase):
    def setUp(self):
        self.monitor = CameraMonitor(VisionConfig(observed_road='B'))
        self.controller = web.TrafficController('', self.monitor.snapshot, 'B')
        for name, value in (('monitor', self.monitor), ('config', self.monitor.config),
                            ('controller', self.controller)):
            replacement = patch.object(web, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.addCleanup(self.controller.stop)
        self.client = web.app.test_client()

    def test_page_has_single_feed_configured_road_and_no_cdn(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertEqual(html.count('<img '), 1)
        self.assertIn('Via B · Câmera configurada', html)
        self.assertIn('Sem medição · sem câmera', html)
        self.assertNotIn('cdn.socket.io', html)
        self.assertEqual(self.client.get('/video_feed/A').status_code, 404)
        response = self.client.get('/video_feed/B', buffered=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Content-Type: image/jpeg', next(iter(response.response)))
        response.close()

    def test_status_and_commands_without_arduino(self):
        data = self.client.get('/status').get_json()
        self.assertEqual(data['via_observada'], 'B')
        self.assertIsNone(data['carros'])
        self.assertIsNone(data['semaforo'])
        for body in ({'via': 'A'}, {'via': 'C'}, None, []):
            response = self.client.post('/semaforo/manual', json=body)
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.get_json()['ok'])

    def test_mode_endpoint_validates_input_and_requires_firmware(self):
        for body in ({'modo': 'automatico'}, {'modo': 'invalid'}, None, []):
            response = self.client.post('/semaforo/modo', json=body)
            self.assertEqual(response.status_code, 400)
        self.controller.receive('STATE ST1 0 A_GREEN 0 12000 FALLBACK A', self.controller.clock())
        response = self.client.post('/semaforo/modo', json={'modo': 'manual'})
        self.assertTrue(response.get_json()['ok'])
        self.assertTrue(self.client.post('/semaforo/manual', json={'via': 'B'}).get_json()['ok'])
        self.assertFalse(self.client.post('/semaforo/manual', json={'via': 'A'}).get_json()['ok'])
        self.assertTrue(self.client.get('/status').get_json()['comando_pendente'])

    def test_legacy_entrypoint_shares_application(self):
        import Smartrafic_web
        self.assertIs(Smartrafic_web.app, web.app)
        self.assertIs(Smartrafic_web.main, web.main)

    def test_socket_mode_events_use_same_controller(self):
        self.controller.receive('STATE ST1 0 A_GREEN 0 12000 FALLBACK A', self.controller.clock())
        client = web.socketio.test_client(web.app)
        self.addCleanup(client.disconnect)
        client.emit('ativar_manual')
        self.assertEqual(self.controller.snapshot()['modo'], 'manual')
        client.emit('ativar_auto')
        self.assertEqual(self.controller.snapshot()['modo'], 'automatico')


if __name__ == '__main__':
    unittest.main()
