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

PORTA_ARDUINO = '/dev/ttyUSB0'  # No Windows: 'COM3', 'COM4', etc.
LIMIAR_TROCA_B = 3
LIMIAR_VOLTA_A = 1
CAMERA_INDEX = 1
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FRAME_RATE = 30
DETECTION_FRAME_SKIP = 3
JPEG_QUALITY = 80
MODEL_PATH = 'yolov8n.pt'
INACTIVITY_TIMEOUT = 15
NORMAL_CYCLE_TIME = 10

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
        self.is_changing = False  # Evita mudanças durante transição
        
        # Controle de inatividade
        self.last_detection_time = time.time()
        self.in_normal_cycle = False
        self.cycle_start_time = 0

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
            return True
        except Exception as error:
            logging.warning('Erro ao enviar comando: %s', error)
            return False

    def simulate_yellow_blink_on_web(self, via):
        """Simula o pisca-pisca amarelo na web enquanto o Arduino faz o dele"""
        logging.info('Simulando pisca-pisca amarelo na web para via %s', via)
        
        if via == 'A':
            luz_amarela = 'luzAAmarela'
        else:
            luz_amarela = 'luzAAmarelaB'
        
        # Pisca 3 vezes (cada ciclo liga/desliga dura 1 segundo)
        for i in range(6):  # 6 eventos = 3 piscadas completas
            if i % 2 == 0:
                socketio.emit('yellow_blink_web', {'via': via, 'state': 'on'})
            else:
                socketio.emit('yellow_blink_web', {'via': via, 'state': 'off'})
            time.sleep(0.5)
        
        # Garante que o amarelo apaga no final
        socketio.emit('yellow_blink_web', {'via': via, 'state': 'off'})

    def change_light(self, new_light):
        """Muda o semáforo enviando comando para o Arduino e sincronizando a web"""
        if self.is_changing:
            logging.warning('Já está em processo de mudança, ignorando...')
            return
        
        self.is_changing = True
        
        if new_light == 'B':
            # Vai trocar de A para B
            logging.info('Trocando de A para B - aguardando Arduino piscar amarelo')
            
            # Notifica web que vai começar o pisca-pisca
            socketio.emit('yellow_blink_web', {'via': 'A', 'state': 'start'})
            
            # Envia comando para o Arduino (ele vai piscar amarelo B 3x)
            self.send_command('B')
            
            # Simula o pisca-pisca na web em paralelo
            self.simulate_yellow_blink_on_web('A')
            
            # Aguarda o tempo do pisca-pisca do Arduino (3 piscadas * 1 segundo = 3 segundos)
            time.sleep(3)
            
            # Atualiza estado após troca
            self.current_light = 'B'
            
        elif new_light == 'A':
            # Vai trocar de B para A
            logging.info('Trocando de B para A - aguardando Arduino piscar amarelo')
            
            # Notifica web que vai começar o pisca-pisca
            socketio.emit('yellow_blink_web', {'via': 'B', 'state': 'start'})
            
            # Envia comando para o Arduino (ele vai piscar amarelo A 3x)
            self.send_command('A')
            
            # Simula o pisca-pisca na web em paralelo
            self.simulate_yellow_blink_on_web('B')
            
            # Aguarda o tempo do pisca-pisca do Arduino
            time.sleep(3)
            
            # Atualiza estado após troca
            self.current_light = 'A'
        
        self.yellow_blink = False
        self.is_changing = False
        
        # Atualiza interface web
        socketio.emit('status_update', self.status_payload())
        logging.info('Troca concluída - Via %s liberada', self.current_light)

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

    def check_inactivity_and_cycle(self):
        """Verifica se está inativo e gerencia o ciclo normal"""
        if self.is_changing:
            return  # Não faz nada durante transição
            
        current_time = time.time()
        time_since_last_detection = current_time - self.last_detection_time
        
        if not self.manual_mode and time_since_last_detection >= INACTIVITY_TIMEOUT:
            if not self.in_normal_cycle:
                logging.info('Inatividade detectada - iniciando ciclo normal')
                self.start_normal_cycle()
        
        if self.in_normal_cycle and not self.is_changing:
            if current_time - self.cycle_start_time >= NORMAL_CYCLE_TIME:
                self.alternate_normal_cycle()

    def start_normal_cycle(self):
        """Inicia o ciclo normal do semáforo"""
        self.in_normal_cycle = True
        self.cycle_start_time = time.time()
        if self.current_light != 'A':
            self.change_light('A')

    def alternate_normal_cycle(self):
        """Alterna entre as vias no ciclo normal"""
        if self.current_light == 'A':
            self.change_light('B')
        else:
            self.change_light('A')
        
        self.cycle_start_time = time.time()

    def stop_normal_cycle(self):
        """Para o ciclo normal quando veículos são detectados"""
        if self.in_normal_cycle:
            self.in_normal_cycle = False
            logging.info('Veículos detectados - ciclo normal interrompido')

    def update_traffic_state(self, cars, pedestrians):
        if self.is_changing:
            return  # Não atualiza estado durante transição
            
        self.car_count = cars
        self.pedestrian_count = pedestrians
        
        # Atualiza detecção se houver veículos
        if cars > 0:
            self.last_detection_time = time.time()
            if self.in_normal_cycle:
                self.stop_normal_cycle()

        if self.manual_mode:
            if self.manual_light != self.current_light and not self.is_changing:
                self.change_light(self.manual_light)
        else:
            # Verifica inatividade e ciclo normal
            self.check_inactivity_and_cycle()
            
            # Lógica normal de tráfego (só se não estiver em ciclo normal)
            if not self.in_normal_cycle and not self.is_changing:
                if self.current_light == 'A' and cars >= LIMIAR_TROCA_B:
                    self.change_light('B')
                    self.last_detection_time = time.time()
                    logging.info('Fluxo alto na A -> trocando para B')
                elif self.current_light == 'B' and cars <= LIMIAR_VOLTA_A:
                    self.change_light('A')
                    self.last_detection_time = time.time()
                    logging.info('Fluxo baixo na B -> voltando para A')

        # Emite atualizações de contadores
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
        self.last_detection_time = time.time()
        
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
        if self.is_changing:
            logging.warning('Aguardando troca atual finalizar...')
            return
            
        self.manual_mode = True
        self.stop_normal_cycle()
        logging.info('Modo manual ativado')
        socketio.emit('status_update', self.status_payload())

    def set_manual_light(self, via):
        if self.manual_mode and via in ['A', 'B'] and not self.is_changing:
            self.manual_light = via
            self.change_light(via)
            self.stop_normal_cycle()

    def activate_auto(self):
        if self.is_changing:
            logging.warning('Aguardando troca atual finalizar...')
            return
            
        self.manual_mode = False
        self.yellow_blink = False
        self.in_normal_cycle = False
        self.last_detection_time = time.time()
        logging.info('Modo automático ativado')
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
    controller.connect_arduino()

    if not controller.initialize_camera():
        logging.warning('Câmera não encontrada, executando em modo simulação')

    thread_deteccao = threading.Thread(target=controller.detection_loop, daemon=True)
    thread_deteccao.start()

    logging.info('Servidor web iniciado em: http://localhost:5000')
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)