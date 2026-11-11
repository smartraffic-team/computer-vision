"""Uma câmera e controle local adaptativo dos dois sinais da maquete."""

import logging
import os
from pathlib import Path
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response, render_template, request
from flask_socketio import SocketIO, emit

from vision import CameraMonitor, VisionConfig
from traffic import TrafficController
from ingestion import IngestionClient, IngestionConfig


logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
BASE_DIR = Path(__file__).resolve().parent
PORTA_ARDUINO = os.getenv('SMARTTRAFFIC_ARDUINO_PORT', 'COM5')
CAMERA_INDEX = int(os.getenv('SMARTTRAFFIC_CAMERA_INDEX', '0'))
VIA_OBSERVADA = os.getenv('SMARTTRAFFIC_OBSERVED_ROAD', 'A').upper()
config = VisionConfig(
    camera_index=CAMERA_INDEX,
    camera_backend=os.getenv('SMARTTRAFFIC_CAMERA_BACKEND', VisionConfig.camera_backend).upper(),
    observed_road=VIA_OBSERVADA,
    width=int(os.getenv('SMARTTRAFFIC_FRAME_WIDTH', '640')),
    height=int(os.getenv('SMARTTRAFFIC_FRAME_HEIGHT', '480')),
    fps=int(os.getenv('SMARTTRAFFIC_FPS', '30')),
    detection_interval=float(os.getenv('SMARTTRAFFIC_DETECTION_INTERVAL', '0.3')),
    stale_after=float(os.getenv('SMARTTRAFFIC_STALE_AFTER', '5')),
    confidence=float(os.getenv('SMARTTRAFFIC_CONFIDENCE', '0.35')),
    roi=tuple(float(value) for value in os.getenv('SMARTTRAFFIC_ROI', '0,0,1,1').split(',')),
)
monitor = CameraMonitor(config)
app = Flask(__name__, template_folder=str(BASE_DIR / 'templates'))
socketio = SocketIO(app, async_mode='threading')


controller = TrafficController(PORTA_ARDUINO, monitor.snapshot, config.observed_road)


def operational_snapshot():
    return {**monitor.snapshot(), **controller.snapshot()}


try:
    ingestion = IngestionClient(IngestionConfig.load(), operational_snapshot)
except (ValueError, TypeError, OSError):
    logging.warning('Configuração de ingestão inválida; controle local permanece disponível.')
    ingestion = IngestionClient(IngestionConfig(), operational_snapshot)
    ingestion.update_status(erro='Configuração de ingestão inválida.')


def status_payload():
    return {**operational_snapshot(), 'ingestao': ingestion.status()}


def generate_stream():
    while True:
        frame = monitor.display_frame()
        if frame is None:
            # Substitui um frame antigo quando a câmera não entrega imagem válida.
            frame = np.zeros((config.height, config.width, 3), dtype=np.uint8)
            cv2.putText(frame, 'Camera sem imagem', (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 205, 254), 2)
        else:
            x1, y1, x2, y2 = config.pixel_roi(frame)
            cv2.rectangle(frame, (x1, y1), (x2 - 1, y2 - 1), (0, 205, 254), 2)
        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if success:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                   + buffer.tobytes() + b'\r\n')
        time.sleep(1 / config.fps)


@app.route('/')
def index():
    return render_template('index.html', via=config.observed_road,
                           outra_via='B' if config.observed_road == 'A' else 'A')


@app.route('/video_feed')
@app.route('/video_feed/<via>')
def video_feed(via=None):
    if via is not None and via.upper() != config.observed_road:
        return 'Esta via não possui câmera configurada.', 404
    return Response(generate_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/status')
def status():
    return status_payload()


@app.post('/semaforo/manual')
def manual_command():
    data = request.get_json(silent=True)
    result = controller.request_change(data.get('via') if isinstance(data, dict) else None)
    return result, 200 if result['ok'] else 400


@app.post('/semaforo/modo')
def change_mode():
    data = request.get_json(silent=True)
    result = controller.set_mode(data.get('modo') if isinstance(data, dict) else None)
    return result, 200 if result['ok'] else 400


@socketio.on('connect')
def handle_connect():
    emit('status_inicial', status_payload())


@socketio.on('alternar_semaforo_manual')
def handle_manual(data):
    via = data.get('via') if isinstance(data, dict) else None
    result = controller.request_change(via)
    emit('comando_resultado', result)
    return result


@socketio.on('ativar_manual')
def handle_ativar_manual():
    emit('comando_resultado', controller.set_mode('manual'))


@socketio.on('ativar_auto')
def handle_ativar_auto():
    emit('comando_resultado', controller.set_mode('automatico'))


def publish_status(stop_event):
    while not stop_event.is_set():
        socketio.emit('status_update', status_payload())
        stop_event.wait(0.5)


def main():
    stop_event = threading.Event()
    publisher = None
    try:
        monitor.start()
        controller.connect()
        ingestion.start()
        publisher = threading.Thread(target=publish_status, args=(stop_event,), daemon=True)
        publisher.start()
        logging.info('Via observada: %s. Interface: http://localhost:5000', config.observed_road)
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    finally:
        stop_event.set()
        if publisher:
            publisher.join(timeout=2)
        controller.stop()
        monitor.stop()
        ingestion.stop()


if __name__ == '__main__':
    main()
