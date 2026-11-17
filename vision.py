"""Captura e medição de uma via, independentes do controle semafórico."""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import sys
from pathlib import Path
import threading
import time


@dataclass(frozen=True)
class VisionConfig:
    camera_index: int = 0
    camera_backend: str = 'DSHOW' if sys.platform == 'win32' else 'AUTO'
    observed_road: str = 'A'
    width: int = 640
    height: int = 480
    fps: int = 30
    detection_interval: float = 0.3
    stale_after: float = 5.0
    reconnect_interval: float = 2.0
    stopped_seconds: float = 2.0
    confidence: float = 0.35
    # Retângulo normalizado: esquerda, topo, direita, base.
    roi: tuple = (0.0, 0.0, 1.0, 1.0)
    model_path: str = str(Path(__file__).resolve().parent / 'yolov8n.pt')

    def __post_init__(self):
        if self.camera_backend not in ('AUTO', 'DSHOW', 'MSMF'):
            raise ValueError('Backend da câmera deve ser AUTO, DSHOW ou MSMF.')
        if self.observed_road not in ('A', 'B'):
            raise ValueError('A via observada deve ser A ou B.')
        if self.camera_index < 0 or min(self.width, self.height, self.fps) <= 0:
            raise ValueError('Índice, resolução ou FPS inválidos.')
        if min(self.detection_interval, self.stale_after, self.reconnect_interval,
               self.stopped_seconds) <= 0:
            raise ValueError('Os intervalos devem ser positivos.')
        if not 0 < self.confidence <= 1:
            raise ValueError('A confiança deve estar entre 0 e 1.')
        if len(self.roi) != 4:
            raise ValueError('ROI deve conter esquerda,topo,direita,base.')
        left, top, right, bottom = self.roi
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError('ROI deve ser um retângulo válido entre 0 e 1.')

    def pixel_roi(self, frame):
        height, width = frame.shape[:2]
        left, top, right, bottom = self.roi
        x1, y1 = int(left * width), int(top * height)
        return x1, y1, max(x1 + 1, int(right * width)), max(y1 + 1, int(bottom * height))


def open_camera(config):
    import cv2

    backend = {'AUTO': cv2.CAP_ANY, 'DSHOW': cv2.CAP_DSHOW, 'MSMF': cv2.CAP_MSMF}
    logging.info('Abrindo câmera %s com backend %s...',
                 config.camera_index, config.camera_backend)
    camera = cv2.VideoCapture(config.camera_index, backend[config.camera_backend])
    if camera.isOpened():
        logging.info('Câmera aberta; configurando resolução e FPS...')
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
        camera.set(cv2.CAP_PROP_FPS, config.fps)
    return camera


@dataclass(frozen=True)
class DetectionResult:
    cars: int
    people: int
    annotated_frame: object
    car_boxes: tuple = ()
    visual_boxes: tuple = ()


class YoloDetector:
    def __init__(self, config):
        from ultralytics import YOLO

        self.config = config
        self.model = YOLO(config.model_path)

    def detect(self, frame):
        import cv2

        x1, y1, x2, y2 = self.config.pixel_roi(frame)
        results = self.model(
            frame[y1:y2, x1:x2], conf=self.config.confidence, verbose=False,
        )
        annotated = frame.copy()
        cars = people = 0
        car_boxes = []
        visual_boxes = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                label = self.model.names[int(box.cls[0])]
                if label not in ('car', 'person'):
                    continue
                # As coordenadas do YOLO são relativas ao recorte; o vídeo é completo.
                left, top, right, bottom = (float(value) for value in box.xyxy[0])
                left = max(x1, min(x2 - 1, int(left) + x1))
                right = max(x1, min(x2 - 1, int(right) + x1))
                top = max(y1, min(y2 - 1, int(top) + y1))
                bottom = max(y1, min(y2 - 1, int(bottom) + y1))
                if right <= left or bottom <= top:
                    continue
                cars += label == 'car'
                people += label == 'person'
                if label == 'car':
                    car_boxes.append((left, top, right, bottom))
                name = 'Carro' if label == 'car' else 'Pessoa'
                color = (255, 160, 60) if label == 'car' else (80, 210, 80)
                caption = f'{name}'
                visual_boxes.append((left, top, right, bottom, caption, color))
                cv2.rectangle(annotated, (left, top), (right, bottom), color, 2)
                (text_width, text_height), baseline = cv2.getTextSize(
                    caption, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1,
                )
                text_x = max(0, min(left, frame.shape[1] - text_width - 6))
                text_y = min(frame.shape[0] - baseline - 3, max(text_height + 6, top - 6))
                cv2.rectangle(annotated, (text_x, text_y - text_height - 4),
                              (text_x + text_width + 6, text_y + baseline + 3), color, -1)
                cv2.putText(annotated, caption, (text_x + 3, text_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        return DetectionResult(cars, people, annotated, tuple(car_boxes), tuple(visual_boxes))


class CameraMonitor:
    def __init__(self, config, camera_factory=open_camera,
                 detector_factory=YoloDetector, clock=time.monotonic):
        self.config = config
        self._camera_factory = camera_factory
        self._detector_factory = detector_factory
        self._clock = clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads = []
        self._frame = None
        self._frame_number = 0
        self._generation = 0
        self._frame_time = 0.0
        self._frame_date = None
        self._reading = None
        self._annotated_frame = None
        self._visual_boxes = ()
        self._visual_boxes_time = 0.0
        self._queue_tracks = []
        self._stopped_cars = 0
        self._oldest_wait_seconds = 0.0
        self._camera_status = 'iniciando'
        self._model_status = 'carregando'

    def start(self):
        if self._threads:
            raise RuntimeError('Monitor já iniciado; crie outro após encerrar.')
        for target in (self._capture_loop, self._detection_loop):
            thread = threading.Thread(target=target, daemon=True, name=target.__name__)
            self._threads.append(thread)
            thread.start()

    def stop(self):
        self._stop.set()
        self._invalidate_camera()
        for thread in self._threads:
            thread.join(timeout=2)
            if thread.is_alive():
                logging.warning('Aguardando término do dispositivo/modelo: %s', thread.name)

    def _invalidate_camera(self):
        with self._lock:
            self._camera_status = 'desconectada'
            self._frame = None
            self._reading = None
            self._annotated_frame = None
            self._visual_boxes = ()
            self._visual_boxes_time = 0.0
            self._queue_tracks = []
            self._stopped_cars = 0
            self._oldest_wait_seconds = 0.0
            self._generation += 1

    def _capture_loop(self):
        while not self._stop.is_set():
            camera = None
            try:
                camera = self._camera_factory(self.config)
                if not camera.isOpened():
                    raise RuntimeError('Não foi possível abrir a câmera.')
                logging.info('Aguardando primeiro quadro da câmera %s (Via %s)...',
                             self.config.camera_index, self.config.observed_road)
                first_frame = True
                while not self._stop.is_set():
                    success, frame = camera.read()
                    if not success or frame is None:
                        raise RuntimeError('A câmera deixou de fornecer imagens.')
                    if first_frame:
                        logging.info('Primeiro quadro recebido: %sx%s.', frame.shape[1], frame.shape[0])
                        first_frame = False
                    with self._lock:
                        if self._stop.is_set():
                            break
                        self._frame = frame
                        self._frame_number += 1
                        self._frame_time = self._clock()
                        self._frame_date = datetime.now(timezone.utc).isoformat()
                        self._camera_status = 'conectada'
            except Exception as error:
                logging.warning('Captura indisponível: %s', error)
            finally:
                self._invalidate_camera()
                if camera is not None:
                    camera.release()  # Somente a thread de captura usa o dispositivo.
            self._stop.wait(self.config.reconnect_interval)

    def _latest_sample(self):
        with self._lock:
            if self._frame is None or self._clock() - self._frame_time > self.config.stale_after:
                return None
            return (self._frame.copy(), self._frame_number, self._generation,
                    self._frame_time, self._frame_date)

    def latest_frame(self):
        sample = self._latest_sample()
        return sample[0] if sample else None

    def display_frame(self):
        """Mostra o quadro mais recente com a última detecção válida sobreposta."""
        with self._lock:
            now = self._clock()
            if self._frame is None or now - self._frame_time > self.config.stale_after:
                return None
            frame = self._frame.copy()
            overlay_max_age = min(
                self.config.stale_after,
                max(1.5, self.config.detection_interval * 5),
            )
            # Mantém o último overlay por alguns frames mesmo quando a detecção
            # falha temporariamente. Isso reduz o efeito de "piscar" sem esconder
            # o estado real da leitura.
            if self._visual_boxes and now - self._visual_boxes_time <= overlay_max_age:
                visual_boxes = self._visual_boxes
            else:
                visual_boxes = ()

        if visual_boxes:
            import cv2

            for left, top, right, bottom, caption, color in visual_boxes:
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                (text_width, text_height), baseline = cv2.getTextSize(
                    caption, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1,
                )
                text_x = max(0, min(left, frame.shape[1] - text_width - 6))
                text_y = min(frame.shape[0] - baseline - 3, max(text_height + 6, top - 6))
                cv2.rectangle(frame, (text_x, text_y - text_height - 4),
                              (text_x + text_width + 6, text_y + baseline + 3), color, -1)
                cv2.putText(frame, caption, (text_x + 3, text_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        return frame

    def _detection_loop(self):
        try:
            detector = self._detector_factory(self.config)
        except Exception:
            logging.exception('Falha ao carregar YOLO; o vídeo continua disponível.')
            with self._lock:
                self._model_status = 'erro'
            return
        with self._lock:
            self._model_status = 'pronto'
        last_frame = -1
        while not self._stop.is_set():
            sample = self._latest_sample()
            if sample is not None and sample[1] != last_frame:
                frame, number, generation, captured_at, captured_date = sample
                last_frame = number
                try:
                    detection = detector.detect(frame)
                    with self._lock:
                        # Descarta uma inferência que terminou depois de desconexão/reinício.
                        if generation == self._generation and not self._stop.is_set():
                            stopped = self._update_queue_tracks(
                                detection.car_boxes, frame.shape, captured_at,
                            )
                            self._reading = (detection.cars, detection.people,
                                             captured_at, captured_date, stopped)
                            self._annotated_frame = detection.annotated_frame
                            self._visual_boxes = detection.visual_boxes
                            self._visual_boxes_time = captured_at
                            self._model_status = 'pronto'
                except Exception:
                    logging.exception('Falha na detecção; mantendo o último overlay por alguns quadros.')
                    with self._lock:
                        # Mantém o último overlay visível por um breve intervalo,
                        # mas continua marcando a contagem como indisponível.
                        if self._visual_boxes and self._clock() - self._visual_boxes_time <= max(1.5, self.config.detection_interval * 5):
                            self._reading = None
                            self._annotated_frame = None
                            self._model_status = 'erro'
                            continue
                        self._reading = None
                        self._annotated_frame = None
                        self._visual_boxes = ()
                        self._model_status = 'erro'
            self._stop.wait(self.config.detection_interval)

    def _update_queue_tracks(self, boxes, shape, now):
        """Estimate stopped cars from box-center movement in the configured ROI."""
        width = shape[1]
        movement_limit = max(6.0, width * 0.01)
        match_limit = max(40.0, width * 0.12)
        tracks = [track for track in self._queue_tracks if now - track['seen'] <= 1.0]
        used = set()
        updated = []
        for box in boxes:
            x1, y1, x2, y2 = box
            center = ((x1 + x2) / 2, (y1 + y2) / 2)
            candidates = [
                (index, ((track['center'][0] - center[0]) ** 2
                         + (track['center'][1] - center[1]) ** 2) ** 0.5)
                for index, track in enumerate(tracks) if index not in used
            ]
            candidate = min(candidates, key=lambda item: item[1], default=None)
            if candidate and candidate[1] <= match_limit:
                index, distance = candidate
                used.add(index)
                track = tracks[index]
                stable_since = track['stable_since'] if distance <= movement_limit else now
            else:
                stable_since = now
            updated.append({'center': center, 'seen': now, 'stable_since': stable_since})
        self._queue_tracks = updated
        self._stopped_cars = sum(
            now - track['stable_since'] >= self.config.stopped_seconds
            for track in updated
        )
        eligible_waits = [
            now - track['stable_since'] for track in updated
            if now - track['stable_since'] >= self.config.stopped_seconds
        ]
        self._oldest_wait_seconds = max(eligible_waits, default=0.0)
        return self._stopped_cars

    def snapshot(self):
        with self._lock:
            now = self._clock()
            camera_status = self._camera_status
            if camera_status == 'conectada' and now - self._frame_time > self.config.stale_after:
                camera_status = 'sem_imagem'
            reading = self._reading
            valid = (camera_status == 'conectada' and self._model_status == 'pronto'
                     and reading is not None and now - reading[2] <= self.config.stale_after)
            if self._model_status != 'pronto':
                detection_status = self._model_status
            elif camera_status != 'conectada':
                detection_status = 'indisponivel'
            elif reading is None:
                detection_status = 'aguardando'
            else:
                detection_status = 'ativa' if valid else 'desatualizada'
            cars, people = (reading[0], reading[1]) if valid else (None, None)
            stopped_cars = reading[4] if valid and len(reading) > 4 else (0 if valid else None)
            oldest_wait_seconds = self._oldest_wait_seconds if valid else None
            via = self.config.observed_road
            roads = {road: {'carros': None, 'pedestres': None, 'estado': 'sem_medicao'}
                     for road in ('A', 'B')}
            roads[via] = {'carros': cars, 'pedestres': people,
                          'estado': 'valida' if valid else 'indisponivel'}
            return {
                'via_observada': via, 'camera': camera_status,
                'deteccao': detection_status, 'medicao_valida': valid,
                'carros': cars, 'pedestres': people,
                'veiculos_parados': stopped_cars,
                'espera_mais_antiga_seg': round(oldest_wait_seconds, 1)
                    if oldest_wait_seconds is not None else None,
                'demanda_via_a': via == 'A' and bool(stopped_cars),
                'registrado_em': reading[3] if reading else None,
                'vias': roads,
            }
