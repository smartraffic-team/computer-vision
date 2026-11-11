# SmartTraffic — visão computacional local

Aplicação de uma webcam para contar **carros e pessoas visíveis** na via configurada e mostrar o vídeo em Flask. O programa principal é **Teste_camera.py**. Smartrafic_web.py é um atalho para a mesma aplicação.

## Executar

No terminal, dentro de computer-vision e no ambiente Python do projeto:

    python -m pip install -r requirements.txt
    python Teste_camera.py

Abra **http://localhost:5000**. Encerre com Ctrl+C.

Os caminhos do modelo e do template são relativos aos arquivos Python, portanto também é possível iniciar de outra pasta: python computer-vision/Teste_camera.py.

A aplicação abre somente uma webcam. Captura, detecção, controle serial e publicação de estado usam threads separadas. O YOLO pode carregar ou falhar sem impedir o vídeo. O controle inicia em modo automático e exige o firmware ST1 de `../arduino/arduino_code.ino`; o firmware antigo não é compatível. Encerre o Python e o Monitor Serial antes de carregar o firmware e reinicie o Python depois.

## Qual via está sendo observada?

A origem é uma configuração vinculada ao enquadramento da câmera. O YOLO identifica as classes car e person, não o nome da via.

- Padrão atual: câmera de índice **0**, observando a **Via A**. O índice depende da enumeração dos dispositivos neste computador.
- Posicione a câmera para que a área delimitada contenha apenas a via configurada.
- A outra via aparece como **sem medição**; não recebe a contagem da câmera nem um zero artificial.
- Se uma câmera mostrar as duas vias, será necessário implementar regiões distintas e atribuição de objetos a cada região. Isso não faz parte desta entrega.
- Os índices de webcam dependem da enumeração do computador. Se aparecer o dispositivo errado, encerre a aplicação, altere o índice e reinicie.

## Configuração no PowerShell

Exemplo para usar a webcam de índice 1 observando A e preservar a porta COM5:

    $env:SMARTTRAFFIC_CAMERA_INDEX='1'
    $env:SMARTTRAFFIC_OBSERVED_ROAD='A'
    $env:SMARTTRAFFIC_ARDUINO_PORT='COM5'
    python Teste_camera.py

Para observar B, configure SMARTTRAFFIC_OBSERVED_ROAD como B antes de iniciar. Reinicie a aplicação ao alterar configurações.

| Variável | Padrão | Finalidade |
|---|---|---|
| SMARTTRAFFIC_CAMERA_INDEX | 0 | Índice da única webcam aberta |
| SMARTTRAFFIC_CAMERA_BACKEND | DSHOW no Windows; AUTO nos demais | Backend de captura: DSHOW, MSMF ou AUTO |
| SMARTTRAFFIC_OBSERVED_ROAD | A | Via à qual pertencem as medições: A ou B |
| SMARTTRAFFIC_FRAME_WIDTH / SMARTTRAFFIC_FRAME_HEIGHT | 640 / 480 | Resolução solicitada à câmera |
| SMARTTRAFFIC_FPS | 30 | FPS solicitado e limite do loop de captura |
| SMARTTRAFFIC_DETECTION_INTERVAL | 0.3 | Pausa, em segundos, entre inferências |
| SMARTTRAFFIC_STALE_AFTER | 5 | Validade máxima, em segundos, a partir da captura do quadro |
| SMARTTRAFFIC_CONFIDENCE | 0.35 | Confiança mínima configurada no YOLO |
| SMARTTRAFFIC_ROI | 0,0,1,1 | Área de contagem: esquerda, topo, direita, base; valores entre 0 e 1 |
| SMARTTRAFFIC_ARDUINO_PORT | COM5 | Porta serial opcional, a 9600 baud |

A resolução e o FPS efetivos dependem do hardware. A frequência de detecção também depende do tempo da inferência.

### Webcam sem imagem ou presa em “iniciando”

No Windows, a aplicação usa DirectShow explicitamente. Na enumeração deste computador, a HP HD Camera está no índice 0 e a Logitech BRIO no índice 1. Essa ordem pode mudar ao reconectar dispositivos; outros backends também podem usar uma ordem diferente.

Encerre a aplicação com Ctrl+C antes de testar outra configuração. No PowerShell:

    $env:SMARTTRAFFIC_CAMERA_INDEX='1'
    $env:SMARTTRAFFIC_CAMERA_BACKEND='DSHOW'
    python Teste_camera.py

O terminal informa a abertura, a configuração e o recebimento do primeiro quadro. Se não chegar imagem, feche outros aplicativos que usam a webcam e confira as permissões de câmera para aplicativos da área de trabalho no Windows. É possível testar MSMF ou AUTO alterando a variável de backend e reiniciando.

Uma chamada bloqueada no driver pode manter a captura em “iniciando”; a reconexão só ocorre quando a chamada retorna com falha. Nesse caso, encerre o processo e reinicie após conferir dispositivo e backend.

### Área de contagem

O padrão usa a imagem inteira. Para usar somente a região central:

    $env:SMARTTRAFFIC_ROI='0.2,0.1,0.8,0.9'
    python Teste_camera.py

O retângulo amarelo mostra a região enviada ao YOLO. O recorte não garante que um carro seja daquela via se o enquadramento também incluir outra via. Verifique a posição física e a área escolhida.

### Marcações no vídeo

Cada pessoa detectada recebe uma caixa verde com o rótulo **Pessoa**; cada carro recebe uma caixa azul com o rótulo **Carro**. O percentual ao lado é a confiança atribuída pelo modelo à detecção. Apenas carros e pessoas da área de contagem são marcados.

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
| Verde da via observada | `min(25, 8 + 2 × mediana de carros)` segundos |
| Filtro | Mediana das leituras distintas recebidas nos últimos 2 segundos |
| Via sem câmera | 12 segundos de verde por ciclo |
| Câmera/modelo sem medição válida | 12 segundos de verde em ambas as vias |
| Amarelo contínuo | 3 segundos |
| Ambos vermelhos entre vias | 1 segundo |
| Inicialização da placa | Ambos vermelhos por 1 segundo; depois ciclo fixo |
| Sem comando válido do Python por 4 segundos | Arduino assume ciclo fixo local |
| Estado/ACK serial sem atualização por 2 segundos | Python invalida os sinais e interrompe comandos |

O plano é atualizado aproximadamente uma vez por segundo, sem reiniciar o relógio da fase. Zero carros válidos leva ao verde mínimo de 8 segundos; ausência de medição leva ao ciclo fixo. Leituras repetidas não entram novamente no filtro. A janela começa com as amostras disponíveis e é descartada em falhas. Após a câmera voltar, o controle retoma a adaptação com novas leituras.

As vias alternam sempre. No automático, a via sem câmera volta a receber verde em até 33 segundos após o fim de seu verde (25 + duas transições de 4 segundos). A observada espera até 20 segundos (12 + 8). Não se trata de comparação de filas nem de contagem de veículos únicos.

### Modo manual e estados

Selecione **Manual** na interface e depois solicite A ou B. Uma troca aguarda pelo menos 8 segundos de verde atual, segue por amarelo e ambos vermelhos e só então libera a outra via. O manual também alterna automaticamente após no máximo 25 segundos. Pedidos não reiniciam esse prazo. Uma transição aceita não pode ser redirecionada. Ao mudar de modo durante uma transição, ela termina normalmente.

A tela distingue modo solicitado, modo informado pela placa, comando aguardando confirmação e fase recebida. O tempo restante é uma estimativa baseada no último estado e pode mudar com o plano adaptativo. Não há sensores de confirmação elétrica dos LEDs. Sem estado recente, ambos os sinais ficam sem informação na tela.

O protocolo está em `../arduino/README.md`. Os tempos estão em `traffic.py` e no firmware; altere os dois de forma compatível ao recalibrar a maquete. Após falha serial, confira a conexão e reinicie o Python. Não há reconexão serial automática nesta versão.

## Falhas de captura

A câmera tenta reconectar a cada dois segundos após falha de abertura/leitura. Quadros antigos deixam de ser exibidos e leituras antigas ficam indisponíveis. Uma inferência iniciada antes de uma desconexão não é reaproveitada após a reconexão.

Se o modelo não carregar, o vídeo permanece disponível e a interface informa erro na detecção. Corrija a dependência/modelo e reinicie. Se ocorrer erro durante uma inferência, a contagem fica indisponível e o próximo quadro é tentado.

A interface usa recursos locais e consultas HTTP periódicas; não precisa de um CDN para atualizar contadores. Um atraso de mais de cinco segundos na medição a invalida, inclusive se o modelo estiver demorando para processar.

A falta do Arduino não impede vídeo e contagens. Se aparecer **module 'serial' has no attribute 'Serial'**, confira a instalação de **pyserial** e possíveis conflitos com outro pacote chamado serial no mesmo interpretador Python.

Ao encerrar o Python, o Arduino energizado deixa de receber comandos e assume o ciclo fixo pelo watchdog. Isso não é um desligamento dos LEDs.

## Estrutura

- Teste_camera.py: configuração, Flask, status e comandos de modo/manual.
- traffic.py: filtragem das contagens, planos de verde, protocolo serial e validade do estado.
- vision.py: captura, reconexão, validade de medições e detecção YOLO.
- Smartrafic_web.py: entrada compatível para a mesma aplicação.
- templates/index.html: vídeo, contagens, disponibilidade e botões manuais.
- tests/: testes com câmera, detector e serial simulados.

Rotas locais: **/**, **/video_feed**, **/status**, **POST /semaforo/manual** (`{"via":"A"}`) e **POST /semaforo/modo** (`{"modo":"manual"}` ou `{"modo":"automatico"}`). Resposta HTTP positiva significa solicitação recebida pelo Python; confira o estado posterior da placa. A rota legada /video_feed/A ou /video_feed/B só funciona para a via observada. A outra retorna 404. Eventos Socket.IO de estado e comando manual continuam disponíveis para compatibilidade.

Essas rotas pertencem ao Flask local na porta 5000. O envio à API NestJS é opcional e configurado por `ingestion.local.json`. Consulte [INGESTION.md](INGESTION.md) para configurar dispositivos, fila persistente, reenvios e validação. O estado da ingestão aparece na interface e em `/status`, sem expor a chave.

## Validação

    python -m unittest discover -s tests -v

Os testes não abrem webcams nem enviam comandos a hardware. Para validar fisicamente:

1. Conecte somente uma webcam, confirme a via e o enquadramento.
2. Compare carros/pessoas visíveis na região amarela com as contagens exibidas.
3. Confira que a via sem câmera continua sem medição.
4. Desconecte a webcam: vídeo antigo e contagens devem ficar indisponíveis; reconecte e confira recuperação.
5. Carregue o firmware ST1, feche o Monitor Serial e inicie o Python. Confira alternância automática, amarelo e ambos vermelhos, sem verde simultâneo.
6. Varie a quantidade de carros; confira os limites de 8–25 segundos da via observada e os 12 segundos da outra. Pessoas sozinhas não devem aumentar o verde.
7. Desconecte a câmera e confira o ciclo fixo; reconecte e confira o retorno da adaptação.
8. Selecione Manual, solicite A/B e confira verde mínimo, limite máximo e vídeo fluido nas transições.
9. Encerre o Python com Ctrl+C mantendo a placa energizada: após 4 segundos sem comandos, confira FALLBACK/ciclo fixo. Reinicie e confira recuperação. Teste também perda da serial mantendo alimentação independente da placa.
10. Registre tempos e resultados físicos. Confirme que a câmera pode ser aberta novamente após encerrar.

## Próxima etapa

A operação física dos semáforos e os tempos foram validados pelo usuário. A Etapa 4 adiciona envio Python → API/banco; após validar as leituras persistidas, seguir para a plataforma com dados reais (Etapa 5).
