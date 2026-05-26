import logging
import time
import threading
import serial
import cv2
from flask import Flask, render_template, Response
from flask_socketio import SocketIO, emit
from ultralytics import YOLO

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

PORTA_ARDUINO = '/dev/ttyUSB0'  # No Windows pode ser 'COM3', 'COM4', etc.
LIMIAR_TROCA_B = 3
LIMIAR_VOLTA_A = 1
CAMERA_INDEX = 1
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FRAME_RATE = 30
DETECTION_FRAME_SKIP = 3
JPEG_QUALITY = 80
MODEL_PATH = 'yolov8n.pt'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sua_chave_secreta_aqui'
socketio = SocketIO(app, cors_allowed_origins='*')


class TrafficController:
    def __init__(self):
        self.current_light = 'A'
        self.manual_mode = False
        self.manual_light = 'A'
        self.car_count = 0
        self.pedestrian_count = 0
        self.frame = None
        self.cap = None
        self.arduino = None
        self.model = None
        self.running = threading.Event()
        self.frame_counter = 0
        self.yellow_blink = False

    def connect_arduino(self) -> bool:
        try:
            self.arduino = serial.Serial(PORTA_ARDUINO, 9600, timeout=1)
            time.sleep(2)
            logging.info('Arduino conectado na porta %s', PORTA_ARDUINO)
            return True
        except Exception as error:
            logging.warning('Erro ao conectar Arduino: %s', error)
            self.arduino = None
            return False

    def initialize_camera(self) -> bool:
        self.cap = cv2.VideoCapture(CAMERA_INDEX)
        if not self.cap.isOpened():
            logging.warning('Câmera não inicializada no índice %s', CAMERA_INDEX)
            return False

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, FRAME_RATE)
        logging.info('Câmera inicializada com sucesso')
        return True

    def load_model(self) -> bool:
        try:
            self.model = YOLO(MODEL_PATH)
            logging.info('Modelo carregado: %s', MODEL_PATH)
            return True
        except Exception as error:
            logging.error('Falha ao carregar o modelo YOLO: %s', error)
            self.model = None
            return False

    def send_command(self, command: str) -> bool:
        if not self.arduino or not self.arduino.is_open:
            return False

        try:
            self.arduino.write(command.encode())
            logging.info('Comando enviado ao Arduino: %s', command)
            time.sleep(0.1)
            while self.arduino.in_waiting:
                response = self.arduino.readline().decode().strip()
                logging.info('Resposta Arduino: %s', response)
            return True
        except Exception as error:
            logging.warning('Erro ao enviar comando: %s', error)
            return False

    def detect_objects(self, frame):
        if self.model is None:
            return 0, 0

        frame_resized = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        results = self.model(frame_resized, verbose=False)

        cars = 0
        pedestrians = 0
        for result in results:
            for box in result.boxes:
                label = self.model.names[int(box.cls[0])]
                if label == 'car':
                    cars += 1
                elif label == 'person':
                    pedestrians += 1

        return cars, pedestrians

    def update_traffic_state(self, cars, pedestrians):
        self.car_count = cars
        self.pedestrian_count = pedestrians

        if self.manual_mode:
            if self.manual_light != self.current_light:
                self.current_light = self.manual_light
                self.yellow_blink = False
                self.send_command(self.current_light)
        else:
            if self.current_light == 'A' and cars >= LIMIAR_TROCA_B:
                self.current_light = 'B'
                self.yellow_blink = False
                self.send_command('B')
            elif self.current_light == 'B' and cars <= LIMIAR_VOLTA_A:
                self.current_light = 'A'
                self.yellow_blink = False
                self.send_command('A')

        # Emitir atualizações para todos os clientes
        socketio.emit('status_update', self.status_payload())
        socketio.emit('contadores_update', {
            'carros': self.car_count,
            'pedestres': self.pedestrian_count
        })

    def status_payload(self):
        return {
            'semaforo': self.current_light,
            'carros': self.car_count,
            'pedestres': self.pedestrian_count,
            'modo': 'manual' if self.manual_mode else 'auto',
            'amarelo': self.yellow_blink
        }

    def detection_loop(self):
        if not self.load_model():
            logging.error('Detecção desativada: modelo não carregado')
            return

        self.running.set()
        while self.running.is_set():
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.1)
                continue

            success, frame = self.cap.read()
            if not success or frame is None:
                time.sleep(0.1)
                continue

            self.frame = frame.copy()
            self.frame_counter += 1

            if self.frame_counter % DETECTION_FRAME_SKIP == 0:
                try:
                    cars, pedestrians = self.detect_objects(frame)
                    self.update_traffic_state(cars, pedestrians)
                except Exception as error:
                    logging.warning('Erro na detecção: %s', error)

            time.sleep(1 / FRAME_RATE)

        logging.info('Loop de detecção encerrado')

    def generate_stream(self):
        while self.running.is_set():
            if self.frame is None:
                time.sleep(1 / FRAME_RATE)
                continue

            frame_display = self.frame.copy()
            success, buffer = cv2.imencode('.jpg', frame_display, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if success:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n\r\n')

            time.sleep(1 / FRAME_RATE)

    def activate_manual(self):
        self.manual_mode = True
        logging.info('Modo manual ativado - aguardando seleção de via')
        socketio.emit('status_update', self.status_payload())

    def set_manual_light(self, via):
        if self.manual_mode:
            if via in ['A', 'B']:
                self.manual_light = via
                self.current_light = via
                self.yellow_blink = False
                self.send_command(via)
                logging.info('Modo manual - alterado para via %s', via)
                socketio.emit('status_update', self.status_payload())

    def activate_auto(self):
        self.manual_mode = False
        self.yellow_blink = False
        logging.info('Modo automático ativado')
        self.send_command(self.current_light)
        socketio.emit('status_update', self.status_payload())


controller = TrafficController()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    return Response(controller.generate_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')


@socketio.on('connect')
def handle_connect():
    logging.info('Cliente conectado')
    emit('status_inicial', controller.status_payload())


@socketio.on('ativar_manual')
def handle_ativar_manual():
    controller.activate_manual()


@socketio.on('ativar_auto')
def handle_ativar_auto():
    controller.activate_auto()


@socketio.on('alternar_semaforo_manual')
def handle_alternar_manual(data):
    if controller.manual_mode:
        via = data.get('via')
        controller.set_manual_light(via)


if __name__ == '__main__':
    logging.info('Iniciando semáforo inteligente')
    
    # No Windows, a porta serial geralmente é COMx
    # Se estiver no Linux/Mac, mantenha '/dev/ttyUSB0'
    # Descomente a linha apropriada:
    
    # Para Windows:
    # PORTA_ARDUINO = 'COM3'  # ou COM4, COM5, etc.
    
    # Para Linux/Mac:
    # PORTA_ARDUINO = '/dev/ttyUSB0'
    
    controller.connect_arduino()

    if not controller.initialize_camera():
        logging.warning('Câmera não encontrada, executando em modo simulação')

    thread_deteccao = threading.Thread(target=controller.detection_loop, daemon=True)
    thread_deteccao.start()

    logging.info('Servidor web iniciado em: http://localhost:5000')
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)