# SmarTraffic - Visão Computacional

Sistema de detecção de veículos, pedestres e PCDs usando **YOLOv8**, com streaming web via **Flask** e comunicação serial com **Arduino**.

---

## Estrutura Atual
```
computer-vision/
├── Smartrafic_web.py # Script principal (Flask + YOLO + Serial)
├── Teste_camera.py # Teste rápido da câmera
├── yolov8n.pt # Modelo YOLO treinado
├── templates/ # Templates HTML da interface web
├── LICENSE # Licença do projeto
└── README.md # Este arquivo
```

---

## Como rodar

### Configurações importantes

No arquivo `Smartrafic_web.py`:
```python

# Câmera (troque o índice se necessário)
cap = cv2.VideoCapture(0)

# Porta serial do Arduino
ser = serial.Serial('COM3', 9600)      # Windows
# ser = serial.Serial('/dev/ttyUSB0', 9600)  # Linux/Mac
```

### 1.Instalar dependências

```bash
pip install flask opencv-python ultralytics pyserial
```
### 2.Testar

```bash
python Smartrafic_web.py
```

## 3.Acessar a interface

Abra o navegador em: http://localhost:5000
