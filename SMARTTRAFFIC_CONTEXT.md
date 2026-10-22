# SmartTraffic — Contexto de desenvolvimento (Computer Vision)

> **Atualizado em:** 21/10/2026
> **Objetivo:** documento de handoff para retomar o desenvolvimento do repositório [`smartraffic-team/computer-vision`](https://github.com/smartraffic-team/computer-vision) com um desenvolvedor ou agente de programação.
> **Fonte do estado técnico:** inspeção da branch `main` no GitHub em 20/10/2026, em conjunto com decisões do projeto e do artigo acadêmico.
> **Importante:** este documento é uma especificação/contexto, **não** indica que todas as funcionalidades foram implementadas. Conferir o código e testar antes de alterar.

## 1. Visão geral e propósito

**SmartTraffic** é um protótipo acadêmico de controle semafórico adaptativo para **um único cruzamento** simulado em escala reduzida, com **duas vias perpendiculares de sentido único (A e B)**, duas aproximações monitoradas por webcams, dois conjuntos de semáforos e um **Arduino** acionando LEDs. Veículos em miniatura (Hot Wheels) representam o fluxo de trânsito. O processamento de imagens ocorre inicialmente em notebook/computador com **Python + OpenCV + Ultralytics YOLOv8n**.

**Objetivo principal:** investigar se decisões baseadas na demanda veicular podem reduzir o **tempo médio de retenção semafórica** em relação a uma configuração com tempos fixos, sem deixar qualquer via aguardando indefinidamente e sem violar as transições de segurança. A retenção semafórica física pode ser medida do posicionamento de um carrinho em região de espera sob sinal que impede passagem até a liberação do verde da via correspondente. A medição é limitada pela operação manual; não equivale ao tempo total de deslocamento real.

**Escopo do MVP:** veículos **e pedestres**. Pessoas detectadas em uma **região de espera** podem gerar solicitação de travessia; isso não significa liberar a travessia imediatamente. Acessibilidade/identificação específica de pessoas com deficiência **não** é compromisso obrigatório desta primeira versão; não deduzir PCD por aparência. A operação é **exclusivamente de laboratório/maquete**, não adequada a semáforos reais.

### Conceito de arquitetura

```text
[Webcam A] --imagem--> [Visão computacional] --\
                                           [Análise por via + estado]
[Webcam B] --imagem--> [Visão computacional] --/          |
                                                         v
                                             [Controlador adaptativo]
                                             [segurança + temporização]
                                                         |
                                               Serial USB/Arduino
                                                         |
                                            LEDs semáforos A e B

                    [Eventos/telemetria locais]
                                 |
                       [API remota: futuro]
                                 |
                         [MySQL Aiven]
                                 |
                          [Painel React]
```

A divisão entre infraestrutura local e serviços de nuvem é **planejada**; o controle não deve depender de uma chamada de rede externa para garantir operação física básica.

## 2. Repositórios, arquivos e estado verificado

### Repositório principal
- URL: https://github.com/smartraffic-team/computer-vision
- Branch inspecionada: `main`.
- **Entrada de referência mais completa atualmente:** `smarttraffic_app.py`, renomeado de `Teste_camera.py` (blob de origem SHA `9877dd5256aa23fb65c5e8052eca03c1cbe78d77`).
- Arquivos na raiz verificados: `.github/`, `.gitignore`, `LICENSE`, `README.md`, `Smartrafic_web.py`, `smarttraffic_app.py`, `requirements.txt`, `templates/`, `yolov8n.pt`.
- `smarttraffic_app.py` contém Flask, Flask-SocketIO, YOLO, serial Arduino, modos manual/automático, lógica de alternância e stream de vídeo.
- `Smartrafic_web.py` é um script menor de streaming de câmera com Flask, sem o controlador completo. Avaliar legado/uso real antes de remover.
- `README.md` foi atualizado para indicar `smarttraffic_app.py` como aplicação principal e diferenciar recursos implementados dos planejados.
- Configurações de câmera, serial, imagem, limiares e servidor foram externalizadas em `smarttraffic_config.py`, com variáveis documentadas em `.env.example`; a aplicação continua usando uma única câmera.
- `requirements.txt` inclui `flask==3.0.0`, `flask-socketio>=5.3.0`, `opencv-python-headless==4.8.1.78`, `pyserial==3.5`, `ultralytics>=8.0.0`. Validar a compatibilidade das versões e registrar versão de Python suportada; não assumir que o ambiente está pronto.
- `yolov8n.pt` é o arquivo de pesos presente no repo; **não existe evidência verificada de que seja um modelo treinado especificamente para miniaturas, pedestres de maquete ou PCD**.

### Firmware Arduino
- Repositório: https://github.com/smartraffic-team/arduino
- Arquivo: `arduino_code.ino` (blob SHA `98272a5c11b12e14fa6d8ada34ded7d9cf4d21d5`), branch `main`.
- Serial: **9600 baud**; comandos atuais **`A`** (liberar via A) e **`B`** (liberar via B).
- Pinos: A = verde `9`, amarelo `10`, vermelho `11`; B = verde `3`, amarelo `5`, vermelho `6`.
- Inicia em A verde, B vermelho. A troca contém três piscadas de amarelo por `delay(500)` ligado/desligado, e em seguida atualiza LEDs.
- **Lacunas relevantes:** não existe mecanismo de confirmação de comando/estado estruturado, máquina de estados segura, watchdog independente, intertravamento comprovado, configuração formal de amarelo e vermelho total. O mecanismo atual **não deve ser conectado a trânsito real**.

## 3. O que o código Python realmente faz hoje

Em `smarttraffic_app.py`, conferido inicialmente na versão citada:

- `CAMERA_INDEX = 1`: abertura de **uma câmera**, não duas.
- `FRAME_WIDTH=640`, `FRAME_HEIGHT=480`, `FRAME_RATE=30`; `DETECTION_FRAME_SKIP=3`.
- YOLOv8n reconhece apenas os rótulos `car` e `person` para contagem. Cada frame gera números totais de detecções; **não faz tracking persistente nem separa as vias A/B**.
- Contadores `car_count` e `pedestrian_count` e exibição via Socket.IO; stream MJPEG em `/video_feed`, página principal em `/`.
- `LIMIAR_TROCA_B=3` e `LIMIAR_VOLTA_A=1`: se via A liberada e número global de carros >=3, solicita B; se B liberada e número <=1, solicita A. É uma **prova de conceito**, não o algoritmo final de filas.
- Modos manual/automático via eventos Socket.IO (`ativar_manual`, `ativar_auto`, `alternar_semaforo_manual`), sem autenticação verificada.
- `INACTIVITY_TIMEOUT=15` segundos e `NORMAL_CYCLE_TIME=10` segundos: alternância cíclica quando não há carros detectados; **não é fallback confiável para falhas**.
- A porta serial e os demais parâmetros operacionais agora são configuráveis por variáveis de ambiente, mantendo `/dev/ttyUSB0` como padrão legado.
- `SECRET_KEY` literal de exemplo e `cors_allowed_origins='*'`: somente apropriados a laboratório isolado; externalizar configurações, restringir acesso e evitar expor comandos a redes não confiáveis.
- `change_light` envia comando e simula pisca amarelo na interface, com esperas bloqueantes. O estado web é atualizado por suposição temporal, sem ACK real do Arduino. Existe risco de divergência entre interface e hardware, além de bloqueio do ciclo de detecção.
- Se câmera/Arduino não inicializar, há comportamentos de erro/simulação parcial, mas **não há política verificada de estado físico seguro**.
- O `README.md` agora descreve esse estado e separa as capacidades atuais das planejadas.

**Não afirmar como implementado:** duas câmeras simultâneas, contagem de filas por via, chegada individual persistente, decisão por primeiro veículo, detecção de intenção de travessia, fase pedestre, API NestJS conectada, sincronismo confirmado, watchdog/fallback seguro, redução comprovada de espera.

## 4. Requisitos funcionais acordados (MVP alvo)

### 4.1 Duas aproximações e visão computacional

1. Capturar **duas webcams simultaneamente**, uma para Via A e outra para Via B, com identificação/configuração de câmera por via e possibilidade de testes com fontes simuladas/arquivos de vídeo.
2. Definir, calibrar e mostrar **regiões de interesse (ROIs)**: aproximação, zona de fila/parada e zona de espera de pedestres; não confundir presença de pessoa em qualquer lugar do frame com intenção de travessia.
3. Detectar `car` e `person` por frame usando YOLOv8n/OpenCV e **avaliar a qualidade da detecção na escala de miniaturas** (distância, iluminação, oclusão, ângulo), antes de prometer métricas robustas. Considerar ajuste fino do modelo somente se necessário e se existirem dados rotulados.
4. Diferenciar **detecção**, **rastreamento**, **ocupação de ROI** e **estimativa de fila**. A contagem bruta de boxes pode variar de um quadro para outro e contar repetidamente o mesmo veículo.
5. Implementar o mecanismo de histórico/identidade ou alternativa consistente para estimar **quando o veículo mais antigo ainda presente na fila entrou na área de espera**. O reconhecimento da chegada individual é objetivo, não capacidade já existente.

### 4.2 Estratégia semafórica

1. Prioridade por **maior quantidade de veículos efetivamente aguardando** na aproximação A ou B (não simplesmente quantidade de carros visíveis).
2. **Empate:** escolher a via cujo veículo **mais antigo ainda aguardando** tenha chegado primeiro. Se não houver rastreamento confiável, não inventar o tempo de chegada: definir regra secundária determinística e sinalizar limitação.
3. Impor **tempo mínimo de verde**, **tempo máximo**, fase de amarelo, **vermelho total (all-red)** nas transições e proteção contra troca rápida/oscilações. Valores serão definidos por teste e configuração, não assumir números fechados sem validação.
4. Impedir starvation: nenhuma aproximação pode permanecer indefinidamente sem atendimento; implementar limite de espera configurável ou equivalente.
5. **Pedestres:** presença consistente de pessoa na ROI de espera pode criar `pedestrian_request`. Não interromper fluxo instantaneamente: entrar em fase de travessia somente após transição segura e encerramento dos fluxos veiculares conflitantes, com tempo mínimo para travessia. Definir se protótipo representa uma fase pedestre exclusiva (ambas as vias no vermelho) ou fases compatíveis por travessia; escolha inicial mais simples: **fase exclusiva com A/B vermelhos**, desde que Arduino/maquete suportem sinalização inequívoca. Não prometer detecção de PCD.
6. Modos `automatic`, `manual`, `fixed_cycle`, `failsafe`, com comportamentos documentados. Manual **nunca** pode ignorar restrições físicas de transição.
7. Falhas de captura, modelo, leitura, serial ou ausência de confirmação do Arduino devem levar a comportamento **conservador previamente definido e testado**, evitando assumir que alternância fixa já foi acionada fisicamente. Definir política concreta de contingência com equipe; um fallback fixo de software não resolve a perda de conexão com Arduino. Exigir autoridade do microcontrolador sobre intertravamentos básicos.

### 4.3 Integração, comunicação e observabilidade

1. Manter controle semafórico **local e funcional sem acesso à nuvem**.
2. Formalizar protocolo serial com comandos, ACKs/estados, versão, timeout e tratamento de erros. Manter compatibilidade legada `A`/`B` apenas se necessário durante migração; planejar alteração coordenada do firmware.
3. O estado da interface deve ser refletido a partir de **confirmações ou telemetria real**, não de sleeps usados para estimar tempo de ação.
4. Logs estruturados de `camera_id`, via, contagens, solicitações de pedestres, transições, modo, alarmes, timestamps e ACKs para depuração/experimentos.
5. Interface Flask atual pode continuar como monitor local de desenvolvimento; API NestJS, painel React e persistência remota são **trilha separada**, não requisito bloqueante do controle.

## 5. Arquitetura de código recomendada (PROPOSTA; não existe ainda)

Evitar reescrever tudo de uma só vez. Evoluir gradualmente, mantendo modo manual e a capacidade de testar sem Arduino real.

```text
computer-vision/
  README.md                         # Atualizar a documentação
  requirements.txt                  # Fixar versões verificadas
  .env.example                      # Portas/câmeras/configs sem segredos
  src/smarttraffic/
    config.py                       # Tipos e validação de parâmetros
    models.py                       # Detection, QueueState, PedestrianRequest, Phase
    capture.py                      # Entradas webcam A/B, vídeo, mock
    perception.py                   # YOLO e resultados normalizados
    tracking.py                     # Ocupação ROI e histórico/chegadas
    controller.py                   # Lógica PURA de decisão, testável sem CV
    safety.py                       # Máquina de estados e temporizações
    serial_transport.py             # Protocolo Arduino e ACKs
    telemetry.py                    # Logs e métricas
    web.py                          # Flask/Socket.IO local
  tests/
    test_controller.py
    test_safety.py
    test_pedestrians.py
    test_serial_transport.py
    test_camera_sources.py
  scripts/
    run_local.py
    replay_scenarios.py
```

Interfaces sugeridas (conceito; validar com a equipe):

```python
@dataclass
class ApproachState:
    via: str                          # 'A' ou 'B'
    waiting_vehicle_count: int
    oldest_waiting_since: float | None  # monotonic time
    signal_state: str

@dataclass
class IntersectionSnapshot:
    a: ApproachState
    b: ApproachState
    pedestrian_request: bool
    current_phase: str
    phase_elapsed_seconds: float

# Uma função pura e testável sugere a mudança, sem ligar LEDs diretamente.
def propose_next_phase(snapshot: IntersectionSnapshot, policy: Config) -> Decision:
    ...
```

Separar: (a) coleta/percepção, (b) estado estimado, (c) decisão de política, (d) validação de segurança, (e) atuação física, (f) observabilidade. Usar relógio monotônico para temporizações e timestamps absolutos para logs persistentes. Prever concorrência/controlador em único loop serializável para evitar comandos simultâneos.

## 6. Ordem de execução sugerida

### P0 — Base estável e segurança (antes do algoritmo novo)

- [ ] Documentar comandos e comportamento atuais do Arduino e escrever **testes sem hardware** para sequência de fases.
- [ ] Corrigir divergências de sincronização software ↔ Arduino; não bloquear detecção com `sleep` durante transições. Definir máquina de estados explícita e validação de ACK/timeout.
- [ ] Definir estados seguros de inicialização, perda de câmera e serial, e atuação de contingência no firmware. Impedir A e B verdes simultâneos, incluindo durante comandos repetidos/falhas.
- [ ] Atualizar README, settings/env, instruções Windows/Linux e testes básicos. Não expor Flask sem proteção em rede aberta.

### P1 — Captura/contagem por via

- [ ] Suporte a webcam A + B e fontes gravadas, com recuperação de falha.
- [ ] Calibração e visualização de ROI por via e pedestre.
- [ ] Testar YOLOv8n com carrinhos Hot Wheels da maquete; documentar exemplos de falsos positivos/negativos.
- [ ] Estado separado A/B: fila aproximada e estimativa confiável de permanência/chegada.

### P2 — Controle adaptativo e pedestres

- [ ] Contagem por via + desempate por veículo mais antigo ainda presente.
- [ ] Limites de verde, anti-oscilações, fairness/starvation.
- [ ] Solicitação de travessia e fase pedestre exclusiva com transições seguras, após decisão da equipe.
- [ ] Modos manual, automático, fixo e contingência sem comandos inseguros.

### P3 — Evidência experimental

- [ ] Salvar logs com timestamps e estado real dos sinais.
- [ ] **Em andamento:** um primeiro cenário veicular repetível foi criado em `simulation/sumo/`; a integração com o controlador adaptativo e os cenários de falha ainda estão pendentes.
- [ ] Estabelecer métrica do artigo: **tempo de retenção semafórica** do carrinho colocado em espera sob vermelho até a liberação do sinal; documentar limites de medição.
- [ ] Comparar políticas `fixed_cycle` e `adaptive` sob entradas tão equivalentes quanto possível; relatar configuração, número de testes, médias, dispersão e falhas.
- [ ] Verificar segurança e pedestres, não apenas a média dos carros.

### P4 — Integrações complementares (não bloquear MVP)

- [ ] API NestJS + banco MySQL/Aiven para telemetria/histórico, se a interface formal estiver definida.
- [ ] Dashboard React com status/alertas/históricos.
- [ ] **Em andamento:** simulação SUMO retomada como apoio ao desenvolvimento sem hardware; existe um cenário veicular inicial, ainda sem integração com visão computacional, Arduino ou controlador adaptativo.

## 7. Critérios mínimos de aceitação do MVP

- [ ] A e B são tratadas como aproximações diferentes, com aquisição e contagem independentes.
- [ ] O controlador decide com maior fila; empate é resolvido pela chegada mais antiga **quando houver dados confiáveis**.
- [ ] Nunca existem verdes conflitantes; toda troca segue temporização e sequência de segurança, inclusive no modo manual.
- [ ] Há prevenção de espera indefinida e de oscilações frequentes.
- [ ] Existe solicitação de pedestre por ROI, atendimento com tempo protegido e sem liberação imediata insegura.
- [ ] Falhas de hardware/software acionam um comportamento seguro testado, e a interface não mente sobre o estado físico.
- [ ] Operação local independente da nuvem.
- [ ] Contagens, estados, eventos e erros são registráveis; há testes automatizados do núcleo e protocolo.
- [ ] Comparação experimental só é publicada após testes reais; **não alegar percentuais de melhoria antecipadamente**.

## 8. Questões pendentes de definição com a equipe

1. Qual geometria final de posicionamento das duas webcams e o campo de visão/ROIs de cada uma?
2. O rastreamento por objeto nas miniaturas é viável? Se não, qual aproximação à ordem de chegada será aceita?
3. Qual será a representação física da fase de pedestres (LED exclusivo? semáforos veiculares vermelhos)?
4. Quais tempos min/max de verde, amarelo, vermelho total e tempo de pedestres serão configurados na maquete? **Não escolher tempos arbitrários como se fossem norma de trânsito real.**
5. Qual comportamento físico terá o Arduino se perder serial ou receber comandos inválidos/repetidos?
6. Como serão coletados dados experimentais (log de fase, vídeo, cronometragem manual)? Como registrar carrinhos ainda aguardando no final de um teste?
7. Quais versões de Python, OpenCV, Ultralytics, drivers e placa Arduino serão oficialmente suportadas?
8. Confirmar se e quando a camada NestJS/MySQL/dashboard será integrada; atualmente são iniciativas paralelas, não funcionalidades constatadas em `smarttraffic_app.py`.

## 9. Contexto acadêmico e restrições de comunicação

O artigo SmartTraffic organiza a metodologia em Pesquisa de Campo, Arquitetura, Funcionamento do Controle Semafórico e Procedimentos Experimentais/Avaliação, seguido de Resultados e Discussões e Conclusão. Pesquisa exploratória presencial em Registro-SP com **25 respondentes gerais e 2 profissionais**; **92%** dos respondentes gerais relatam já ter esperado no vermelho com via transversal vazia; **44%** estimam 10+ minutos diários em paradas. **São relatos subjetivos, não medidas de trânsito.**

Os testes físicos com carrinhos movidos manualmente têm limitação de velocidade/chegada; medir **retenção semafórica**, não extrapolar para desempenho real. Não existem resultados de redução percentual comprovados pelo projeto até este registro. O artigo deve refletir o estado efetivamente implementado, diferenciando claramente planejamento de entrega.

**Sistema de dados do projeto (contexto fornecido pela equipe):** banco MySQL na Aiven denominado `smarttraffic`, com tabelas de usuários, cruzamentos, vias, dispositivos, semáforos, leituras de tráfego, histórico de fases e alertas; não afirmar que o código Python já persiste nele. Não copiar credenciais para o repo nem adicionar acesso MySQL direto às webcams/controlador sem interface aprovada.

## 10. Instrução recomendada para o próximo agente/desenvolvedor

> Leia este `SMARTTRAFFIC_CONTEXT.md`, depois confira o conteúdo atual da branch antes de propor mudanças. Use `smarttraffic_app.py` como referência funcional e `arduino_code.ino` como referência de firmware. Primeiro faça um diagnóstico sucinto dos riscos de sincronização/transição e sugira uma migração incremental com testes automatizados, preservando o comportamento atual quando possível. Priorize P0 e P1; não implemente tudo em um único PR. Identifique explicitamente decisões pendentes, não invente validação de Hardware/YOLO e não use dados da simulação futura como se fossem percepção real.

### Fontes de código

- https://github.com/smartraffic-team/computer-vision/blob/main/smarttraffic_app.py
- https://github.com/smartraffic-team/computer-vision/blob/main/README.md
- https://github.com/smartraffic-team/computer-vision/blob/main/requirements.txt
- https://github.com/smartraffic-team/arduino/blob/main/arduino_code.ino

*Documento elaborado para continuidade do projeto em 20/10/2026 e atualizado em 21/10/2026. Caso o código seja alterado, atualizar esta seção de estado e as prioridades.*
