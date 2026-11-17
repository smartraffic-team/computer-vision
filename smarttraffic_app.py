"""Uma câmera e controle local adaptativo dos dois sinais da maquete."""

import logging
import os
from pathlib import Path
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request
from flask_socketio import SocketIO, emit

from vision import CameraMonitor, VisionConfig
from traffic import TrafficController
from ingestion import IngestionClient, IngestionConfig


logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
BASE_DIR = Path(__file__).resolve().parent
PORTA_ARDUINO = os.getenv('SMARTTRAFFIC_ARDUINO_PORT', 'COM4')
CAMERA_A_INDEX = int(os.getenv('SMARTTRAFFIC_CAMERA_A_INDEX',
                               os.getenv('SMARTTRAFFIC_CAMERA_INDEX', '1')))
CAMERA_B_INDEX = int(os.getenv('SMARTTRAFFIC_CAMERA_B_INDEX', '2'))
if CAMERA_A_INDEX == CAMERA_B_INDEX:
    raise ValueError('Configure índices diferentes para as câmeras A e B.')
CAMERA_BACKEND = os.getenv(
    'SMARTTRAFFIC_CAMERA_BACKEND', VisionConfig.camera_backend,
).upper()
FRAME_WIDTH = int(os.getenv('SMARTTRAFFIC_FRAME_WIDTH', '640'))
FRAME_HEIGHT = int(os.getenv('SMARTTRAFFIC_FRAME_HEIGHT', '480'))
FPS = int(os.getenv('SMARTTRAFFIC_FPS', '30'))
DETECTION_INTERVAL = float(os.getenv('SMARTTRAFFIC_DETECTION_INTERVAL', '0.3'))
STALE_AFTER = float(os.getenv('SMARTTRAFFIC_STALE_AFTER', '5'))
STOPPED_SECONDS = float(os.getenv('SMARTTRAFFIC_STOPPED_SECONDS', '2'))
CONFIDENCE = float(os.getenv('SMARTTRAFFIC_CONFIDENCE', '0.35'))


def make_config(road, camera_index):
    default_roi = (os.getenv('SMARTTRAFFIC_ROI', '0,0,1,1')
                   if road == 'A' else '0,0,1,1')
    roi = os.getenv(f'SMARTTRAFFIC_CAMERA_{road}_ROI', default_roi)
    backend = os.getenv(f'SMARTTRAFFIC_CAMERA_{road}_BACKEND', CAMERA_BACKEND).upper()
    return VisionConfig(
        camera_index=camera_index, camera_backend=backend, observed_road=road,
        width=FRAME_WIDTH, height=FRAME_HEIGHT, fps=FPS,
        detection_interval=DETECTION_INTERVAL, stale_after=STALE_AFTER,
        stopped_seconds=STOPPED_SECONDS, confidence=CONFIDENCE,
        roi=tuple(float(value) for value in roi.split(',')),
    )


configs = {
    'A': make_config('A', CAMERA_A_INDEX),
    'B': make_config('B', CAMERA_B_INDEX),
}
monitors = {road: CameraMonitor(camera_config)
            for road, camera_config in configs.items()}
# Aliases da Via A para integrações locais antigas.
config = configs['A']
monitor = monitors['A']
app = Flask(__name__, template_folder=str(BASE_DIR / 'templates'))
socketio = SocketIO(app, async_mode='threading')


def get_monitor(road):
    return monitor if road == 'A' else monitors[road]


def get_config(road):
    return config if road == 'A' else configs[road]


def traffic_measurement():
    return {'vias': {road: get_monitor(road).snapshot() for road in ('A', 'B')}}


controller = TrafficController(PORTA_ARDUINO, traffic_measurement)


def operational_snapshot():
    lanes = {road: get_monitor(road).snapshot() for road in ('A', 'B')}
    return {**lanes['A'], **controller.snapshot(), 'vias': lanes}


try:
    ingestion = IngestionClient(IngestionConfig.load(), operational_snapshot)
except (ValueError, TypeError, OSError):
    logging.warning('Configuração de ingestão inválida; controle local permanece disponível.')
    ingestion = IngestionClient(IngestionConfig(), operational_snapshot)
    ingestion.update_status(erro='Configuração de ingestão inválida.')


def status_payload():
    return {**operational_snapshot(), 'ingestao': ingestion.status()}


def generate_stream(via):
    stream_monitor = get_monitor(via)
    stream_config = get_config(via)
    while True:
        frame = stream_monitor.display_frame()
        if frame is None:
            # Substitui um frame antigo quando a câmera não entrega imagem válida.
            frame = np.zeros((stream_config.height, stream_config.width, 3), dtype=np.uint8)
            cv2.putText(frame, f'Camera da Via {via} sem imagem', (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 205, 254), 2)
        else:
            x1, y1, x2, y2 = stream_config.pixel_roi(frame)
            cv2.rectangle(frame, (x1, y1), (x2 - 1, y2 - 1), (0, 205, 254), 2)
        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if success:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                   + buffer.tobytes() + b'\r\n')
        time.sleep(1 / stream_config.fps)


@app.route('/')
def index():
    return render_template('index.html', via='A', outra_via='B')


@app.route('/camera/<via>')
def camera_page(via):
    road = via.upper()
    if road not in monitors:
        return 'Via inválida.', 404
    return render_template('index.html', via=road,
                           outra_via='B' if road == 'A' else 'A')


@app.route('/video_feed')
@app.route('/video_feed/<via>')
def video_feed(via=None):
    road = (via or 'A').upper()
    if road not in monitors:
        return 'Via sem câmera configurada.', 404
    return Response(generate_stream(road), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/status')
def status():
    response = jsonify(status_payload())
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Cache-Control'] = 'no-store'
    return response


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
        for road, camera_monitor in monitors.items():
            logging.info('Câmera da Via %s configurada no índice %s.',
                         road, configs[road].camera_index)
            camera_monitor.start()
        controller.connect()
        ingestion.start()
        publisher = threading.Thread(target=publish_status, args=(stop_event,), daemon=True)
        publisher.start()
        logging.info('Câmeras A/B: índices %s/%s. Interface: http://localhost:5000',
                     CAMERA_A_INDEX, CAMERA_B_INDEX)
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    finally:
        stop_event.set()
        if publisher:
            publisher.join(timeout=2)
        controller.stop()
        for camera_monitor in monitors.values():
            camera_monitor.stop()
        ingestion.stop()


if __name__ == '__main__':
    main()
