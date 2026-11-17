# SmartTraffic — visão computacional local

Aplicacao de duas webcams isoladas, uma para cada via, com contagens e streams independentes. O programa principal e **smarttraffic_app.py**; Smartrafic_web.py inicia a mesma aplicacao.

## Executar

No terminal, dentro de computer-vision e no ambiente Python do projeto:

    python -m pip install -r requirements.txt
    python smarttraffic_app.py

Abra **http://localhost:5000**. Encerre com Ctrl+C.

Os caminhos do modelo e do template são relativos aos arquivos Python, portanto também é possível iniciar de outra pasta: python computer-vision/smarttraffic_app.py.

A aplicacao abre uma captura independente para cada via. Cada CameraMonitor possui seu proprio cv2.VideoCapture, thread de captura, estado, deteccao e reconexao. As duas cameras devem usar indices diferentes.

## Mapeamento das cameras

A via e definida pela configuracao da captura, nao pela classe YOLO. Cada camera tem indice, backend e ROI proprios. O padrao e Via A no indice 1 e Via B no indice 0; confirme o mapeamento no terminal ao iniciar. Os indices devem ser distintos.

Se houver webcams adicionais, defina explicitamente os indices que correspondem a cada aproximacao. A regiao de interesse de cada camera deve conter somente a respectiva via.
## Configuração no PowerShell

Exemplo no PowerShell (ajuste os indices se necessario):

    $env:SMARTTRAFFIC_CAMERA_A_INDEX='1'
    $env:SMARTTRAFFIC_CAMERA_B_INDEX='0'
    $env:SMARTTRAFFIC_ARDUINO_PORT='COM5'
    python smarttraffic_app.py

Para observar as duas vias em Flask, abra **/** (Via A) e use os links **Camera A / Camera B** para conferir cada captura. Os streams estao em **/video_feed/A** e **/video_feed/B**.

| Variável | Padrão | Finalidade |
|---|---|---|
| SMARTTRAFFIC_CAMERA_A_INDEX | SMARTTRAFFIC_CAMERA_INDEX or 1 | Index da webcam A |
| SMARTTRAFFIC_CAMERA_BACKEND | DSHOW no Windows; AUTO nos demais | Backend padrao: DSHOW, MSMF ou AUTO |
| SMARTTRAFFIC_CAMERA_A_BACKEND / SMARTTRAFFIC_CAMERA_B_BACKEND | Backend global | Backend individual opcional para cada webcam |
| SMARTTRAFFIC_CAMERA_B_INDEX | 0 | Index da webcam B; deve ser diferente do indice A |
| SMARTTRAFFIC_FRAME_WIDTH / SMARTTRAFFIC_FRAME_HEIGHT | 640 / 480 | Resolução solicitada à câmera |
| SMARTTRAFFIC_FPS | 30 | FPS solicitado e limite do loop de captura |
| SMARTTRAFFIC_DETECTION_INTERVAL | 0.3 | Pausa, em segundos, entre inferências |
| SMARTTRAFFIC_STALE_AFTER | 5 | Validade máxima, em segundos, a partir da captura do quadro |
| SMARTTRAFFIC_STOPPED_SECONDS | 2 | Tempo mínimo com o centro do carro quase imóvel para classificar espera |
| SMARTTRAFFIC_CONFIDENCE | 0.35 | Confiança mínima configurada no YOLO |
| SMARTTRAFFIC_ROI | 0,0,1,1 | ROI legada da Via A; prefira as variaveis por via |
| SMARTTRAFFIC_CAMERA_A_ROI / SMARTTRAFFIC_CAMERA_B_ROI | 0,0,1,1 | ROI independente por via: esquerda, topo, direita, base |
| SMARTTRAFFIC_ARDUINO_PORT | COM5 | Porta serial opcional, a 9600 baud |

A resolução e o FPS efetivos dependem do hardware. A frequência de detecção também depende do tempo da inferência.

### Webcam sem imagem ou presa em “iniciando”

No Windows, a aplicação usa DirectShow explicitamente. Na enumeração deste computador, a HP HD Camera está no índice 0 e a Logitech BRIO no índice 1. Essa ordem pode mudar ao reconectar dispositivos; outros backends também podem usar uma ordem diferente.

Encerre a aplicação com Ctrl+C antes de testar outra configuração. No PowerShell:

    $env:SMARTTRAFFIC_CAMERA_A_INDEX='1'
    $env:SMARTTRAFFIC_CAMERA_B_INDEX='0'
    python smarttraffic_app.py

O terminal informa a abertura, a configuração e o recebimento do primeiro quadro. Se não chegar imagem, feche outros aplicativos que usam a webcam e confira as permissões de câmera para aplicativos da área de trabalho no Windows. É possível testar MSMF ou AUTO alterando a variável de backend e reiniciando.

Uma chamada bloqueada no driver pode manter a captura em “iniciando”; a reconexão só ocorre quando a chamada retorna com falha. Nesse caso, encerre o processo e reinicie após conferir dispositivo e backend.

### Área de contagem

O padrão usa a imagem inteira. Para usar somente a região central:

    $env:SMARTTRAFFIC_ROI='0.2,0.1,0.8,0.9'
    python smarttraffic_app.py

O retângulo amarelo mostra a região enviada ao YOLO. O recorte não garante que um carro seja daquela via se o enquadramento também incluir outra via. Verifique a posição física e a área escolhida.

### Marcações no vídeo

Cada pessoa detectada recebe uma caixa verde com o rótulo **Pessoa**; cada carro recebe uma caixa azul com o rótulo **Carro**. Apenas carros e pessoas da área de contagem são marcados.

As caixas são desenhadas no mesmo quadro que gerou a medição, incluindo o deslocamento da região de contagem dentro da imagem. Por isso, o vídeo marcado atualiza na frequência da detecção, que pode ser menor que a captura da webcam. Enquanto o modelo carrega, falha ou produz uma leitura vencida, o vídeo mostra a captura recente sem caixas. Desconexões descartam as marcações anteriores.

O rótulo Pessoa indica a classe detectada; não reconhece a identidade de quem aparece.

## Semântica das contagens

- Cada medição substitui a anterior e recebe o horário UTC de captura do quadro.
- **0** significa que o modelo processou um quadro válido e não encontrou objetos daquela classe.
- **—** na tela e **null** no status significam que a medição está indisponível.
- Não some contagens entre quadros para obter veículos únicos: o mesmo carro pode aparecer em muitas leituras.
- A contagem não representa automaticamente fila, pessoas únicas ou solicitação de travessia.
- Só as classes car e person são contadas. Outros tipos de veículos não estão incluídos.
- O modelo não foi validado nesta entrega com miniaturas da maquete. Enquadramento, iluminação e tamanho dos objetos precisam de avaliação física.

## Controle local dos semáforos — Etapa 3

O Python calcula os tempos; o Arduino executa as transições e impõe os limites. A API e a internet não participam do controle. A câmera continua associada somente à via configurada. Pessoas são exibidas, mas não acionam travessias.

| Regra inicial da maquete | Valor |
|---|---|
| Verde da via observada | `min(25, 20 + 2 × mediana de carros)` segundos |
| Filtro | Mediana das leituras distintas recebidas nos últimos 2 segundos |
| Via sem câmera | 20 segundos de verde por ciclo |
| Carro parado aguardando em uma via | O verde da outra via pode ser encerrado com duração 0; o Arduino executa amarelo e intervalo todo vermelho antes de abrir a via priorizada |
| Câmera/modelo sem medição válida | 20 segundos de verde em ambas as vias |
| Amarelo contínuo | 3 segundos |
| Ambos vermelhos entre vias | 1 segundo |
| Inicialização da placa | Ambos vermelhos por 1 segundo; depois ciclo fixo |
| Sem comando válido do Python por 4 segundos | Arduino assume ciclo fixo local |
| Estado/ACK serial sem atualização por 2 segundos | Python invalida os sinais e interrompe comandos |

O plano é atualizado aproximadamente uma vez por segundo, sem reiniciar o relógio da fase. Zero carros válidos leva ao verde mínimo de 20 segundos; ausência de medição leva ao ciclo fixo de 20 segundos. Leituras repetidas não entram novamente no filtro. A janela começa com as amostras disponíveis e é descartada em falhas. Após a câmera voltar, o controle retoma a adaptação com novas leituras.

A primeira estimativa de espera acompanha os centros das caixas de carros de cada câmera, sem compartilhar rastros entre vias. Considera parado o veículo com deslocamento inferior a 1% da largura da imagem por `SMARTTRAFFIC_STOPPED_SECONDS`. Configure `SMARTTRAFFIC_CAMERA_A_ROI` e `SMARTTRAFFIC_CAMERA_B_ROI` para as respectivas zonas de espera. É uma heurística visual para demonstração, sujeita a vibração, oclusão, perspectiva e erros do detector. Quando apenas uma via apresenta demanda, o verde da outra pode ser encerrado sem tempo mínimo; amarelo (3 s) e ambos vermelhos (1 s) continuam obrigatórios. Se ambas tiverem demanda, o controlador mantém o plano adaptativo sem prioridade exclusiva. A regra só atua no modo automático.

Sem prioridade, as vias alternam sempre. Cada via volta a receber verde em até 33 segundos após o fim de seu verde (até 25 segundos na outra via + duas transições de 4 segundos). Com demanda prioritária, o verde da via cedente pode ser encerrado em 0 segundos, preservando amarelo e ambos vermelhos. Não se trata de comparação de filas nem de contagem de veículos únicos.

### Modo manual e estados

Selecione **Manual** na interface e depois solicite A ou B. Uma troca aguarda pelo menos 20 segundos de verde atual, segue por amarelo e ambos vermelhos e só então libera a outra via. O manual também alterna automaticamente após no máximo 25 segundos. Pedidos não reiniciam esse prazo. Uma transição aceita não pode ser redirecionada. Ao mudar de modo durante uma transição, ela termina normalmente.

A tela distingue modo solicitado, modo informado pela placa, comando aguardando confirmação e fase recebida. O tempo restante é uma estimativa baseada no último estado e pode mudar com o plano adaptativo. Não há sensores de confirmação elétrica dos LEDs. Sem estado recente, ambos os sinais ficam sem informação na tela.

O protocolo está em `../arduino/README.md`. Os tempos estão em `traffic.py` e no firmware; altere os dois de forma compatível ao recalibrar a maquete. Após falha serial, confira a conexão e reinicie o Python. Não há reconexão serial automática nesta versão.

## Falhas de captura

A câmera tenta reconectar a cada dois segundos após falha de abertura/leitura. Quadros antigos deixam de ser exibidos e leituras antigas ficam indisponíveis. Uma inferência iniciada antes de uma desconexão não é reaproveitada após a reconexão.

Se o modelo não carregar, o vídeo permanece disponível e a interface informa erro na detecção. Corrija a dependência/modelo e reinicie. Se ocorrer erro durante uma inferência, a contagem fica indisponível e o próximo quadro é tentado.

A interface usa recursos locais e consultas HTTP periódicas; não precisa de um CDN para atualizar contadores. Um atraso de mais de cinco segundos na medição a invalida, inclusive se o modelo estiver demorando para processar.

A falta do Arduino não impede vídeo e contagens. Se aparecer **module 'serial' has no attribute 'Serial'**, confira a instalação de **pyserial** e possíveis conflitos com outro pacote chamado serial no mesmo interpretador Python.

Ao encerrar o Python, o Arduino energizado deixa de receber comandos e assume o ciclo fixo pelo watchdog. Isso não é um desligamento dos LEDs.

## Estrutura

- smarttraffic_app.py: configuração, Flask, status e comandos de modo/manual.
- traffic.py: filtragem das contagens, planos de verde, protocolo serial e validade do estado.
- vision.py: captura, reconexão, validade de medições e detecção YOLO.
- Smartrafic_web.py: entrada compatível para a mesma aplicação.
- templates/index.html: vídeo, contagens, disponibilidade e botões manuais.
- tests/: testes com câmera, detector e serial simulados.

Rotas locais: **/**, **/camera/A**, **/camera/B**, **/video_feed/A**, **/video_feed/B**, **/status**, **POST /semaforo/manual** e **POST /semaforo/modo**. Os dois streams e snapshots permanecem independentes; o estado serial pertence ao controlador compartilhado.

Essas rotas pertencem ao Flask local na porta 5000. O envio à API NestJS é opcional e configurado por `ingestion.local.json`. Consulte [INGESTION.md](INGESTION.md) para configurar dispositivos, fila persistente, reenvios e validação. O estado da ingestão aparece na interface e em `/status`, sem expor a chave.

## Validação

    python -m unittest discover -s tests -v

Os testes não abrem webcams nem enviam comandos a hardware. Para validar fisicamente:

1. Conecte duas webcams, confirme que os indices A e B sao distintos e confira cada imagem em /camera/A e /camera/B.
2. Compare carros/pessoas visíveis na região amarela com as contagens exibidas.
3. Confirme que contagens e estados de captura nao se misturam entre as vias.
4. Desconecte uma camera de cada vez: a outra deve continuar capturando; a via desconectada deve ficar indisponivel ate reconectar.
5. Carregue o firmware ST1, feche o Monitor Serial e inicie o Python. Confira alternância automática, amarelo e ambos vermelhos, sem verde simultâneo.
6. Varie a quantidade de carros; confira os limites de 20–25 segundos por via (a via sem leitura válida usa o padrão fixo de 20 segundos). Pessoas sozinhas não devem aumentar o verde.
7. Desconecte a câmera e confira o ciclo fixo; reconecte e confira o retorno da adaptação.
8. Selecione Manual, solicite A/B e confira verde mínimo, limite máximo e vídeo fluido nas transições.
9. Encerre o Python com Ctrl+C mantendo a placa energizada: após 4 segundos sem comandos, confira FALLBACK/ciclo fixo. Reinicie e confira recuperação. Teste também perda da serial mantendo alimentação independente da placa.
10. Registre tempos e resultados físicos. Confirme que a câmera pode ser aberta novamente após encerrar.

## Próxima etapa

A operação física dos semáforos e os tempos foram validados pelo usuário. A Etapa 4 adiciona envio Python → API/banco; após validar as leituras persistidas, seguir para a plataforma com dados reais (Etapa 5).
