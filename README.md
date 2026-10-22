# SmartTraffic — Visão Computacional

Protótipo acadêmico de controle semafórico adaptativo para uma maquete de cruzamento. A aplicação combina detecção de veículos e pessoas com YOLOv8, monitor local em Flask/Socket.IO e comunicação serial com Arduino.

> O projeto é destinado exclusivamente a laboratório e maquete. Não deve ser usado para controlar trânsito real.

## Estado atual

Atualmente o projeto possui:

- captura de uma câmera;
- contagem global, por quadro, das classes `car` e `person`;
- transmissão de vídeo por MJPEG;
- modos manual e automático;
- regra experimental de alternância por limiares;
- comandos seriais legados `A` e `B` para o Arduino.

Ainda não estão implementados: duas câmeras simultâneas, filas separadas por via, rastreamento persistente, fase de pedestres, protocolo serial com confirmação e máquina de estados completa com vermelho total e contingência.

## Estrutura principal

```text
computer-vision/
├── smarttraffic_app.py       # Aplicação principal atual
├── smarttraffic_config.py    # Configuração por variáveis de ambiente
├── .env.example              # Referência das opções disponíveis
├── simulation/sumo/          # Cruzamento e sensores virtuais
├── Smartrafic_web.py         # Protótipo legado de streaming
├── templates/index.html      # Interface web local
├── requirements.txt          # Dependências Python
├── yolov8n.pt                # Pesos YOLOv8n presentes no repositório
└── SMARTTRAFFIC_CONTEXT.md    # Contexto, requisitos e prioridades
```

## Execução

O CI do projeto usa Python 3.11. Recomenda-se criar um ambiente virtual com essa versão enquanto a compatibilidade com outras versões não for validada.

```bash
python -m venv venv
```

Ative o ambiente virtual e instale as dependências:

```bash
python -m pip install -r requirements.txt
```

As configurações possuem valores padrão e podem ser alteradas por variáveis de ambiente. O arquivo `.env.example` documenta todas as opções, mas não é carregado automaticamente pela aplicação.

Exemplo no PowerShell:

```powershell
$env:SMARTTRAFFIC_CAMERA_INDEX = '0'
$env:SMARTTRAFFIC_ARDUINO_PORT = 'COM3'
python smarttraffic_app.py
```

Para executar sem modificar os valores padrão:

```bash
python smarttraffic_app.py
```

A interface fica disponível por padrão em `http://127.0.0.1:5000`. Para permitir acesso a partir de outros dispositivos da rede, o host e as origens CORS precisam ser configurados explicitamente.

As principais opções são:

- `SMARTTRAFFIC_CAMERA_INDEX` e `SMARTTRAFFIC_ARDUINO_PORT`;
- resolução, FPS, intervalo de detecção e qualidade JPEG;
- limiares e tempos da lógica experimental atual;
- caminho dos pesos YOLO;
- host, porta, chave da aplicação e origens CORS.

## Limitações de validação

O código pode ser desenvolvido e testado com fontes e transportes simulados, mas a captura, a qualidade da detecção e as transições físicas precisam ser validadas posteriormente com a webcam, a maquete e o Arduino reais.

## Simulação SUMO

O primeiro cenário veicular virtual está documentado em [`simulation/sumo/README.md`](simulation/sumo/README.md). Ele permite observar filas nas vias A e B e as fases de um ciclo fixo seguro sem depender de webcam ou Arduino.
