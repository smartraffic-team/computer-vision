# Referência técnica de configuração da simulação SUMO

**Projeto:** SmartTraffic  
**Cenário:** cruzamento único `single_intersection`  
**Data do levantamento:** 26/10/2026  
**Versão executada:** Eclipse SUMO 1.28.0, build Windows AMD64 Release  
**Escopo:** configuração virtual atual; não descreve nem valida webcam, YOLO ou Arduino

## 1. Finalidade deste documento

Este documento registra os parâmetros efetivamente utilizados para construir, executar,
visualizar e avaliar o cenário virtual do SmartTraffic. Ele serve como linha de base para:

- reproduzir os experimentos;
- justificar escolhas metodológicas no artigo;
- distinguir valores definidos pelo projeto de valores herdados do SUMO;
- avaliar sensibilidade a parâmetros no futuro;
- evitar que mudanças de rede, versão ou código alterem silenciosamente o experimento.

O documento descreve o estado atual do repositório. Valores aqui registrados são parâmetros
experimentais da simulação, não tempos homologados para um semáforo real ou para a maquete.

## 2. Arquivos que formam o cenário

| Responsabilidade | Arquivo |
|---|---|
| Configuração principal | `scenarios/single_intersection/smarttraffic.sumocfg` |
| Nós e coordenadas | `scenarios/single_intersection/network/nodes.nod.xml` |
| Vias, faixas e velocidades | `scenarios/single_intersection/network/edges.edg.xml` |
| Movimentos permitidos | `scenarios/single_intersection/network/connections.con.xml` |
| Programas semafóricos | `scenarios/single_intersection/network/traffic_lights.tll.xml` |
| Rede compilada | `scenarios/single_intersection/network/smarttraffic.net.xml` |
| Veículos, rotas e fluxos | `scenarios/single_intersection/routes/traffic.rou.xml` |
| Detectores E2 | `scenarios/single_intersection/detectors/detectors.add.xml` |
| Aparência da interface | `scenarios/single_intersection/viewsettings.xml` |
| Base, zonas e rótulos visuais | `scenarios/single_intersection/visuals/smarttraffic.poly.xml` |
| Compilação da rede | `build_network.py` |
| Execução e integração TraCI | `run_simulation.py` |
| Política de decisão | `adaptive_controller.py` |
| Experimento comparativo | `run_experiment.py` |

A rede `.net.xml` é derivada dos quatro XMLs da pasta `network/`, é ignorada pelo Git e
deve ser reconstruída quando as fontes forem alteradas.

## 3. Ambiente de execução

### 3.1 Instalação observada

- SUMO: `1.28.0`.
- Plataforma do binário: Windows AMD64.
- Instalação local usada no desenvolvimento:
  `C:\Users\fatec-dsm5\Downloads\sumo-win64-1.28.0`.
- Binários usados: `sumo.exe`, `sumo-gui.exe` e `netconvert.exe`.
- API de controle: TraCI fornecida em `%SUMO_HOME%\tools`.

O caminho local não está gravado no código. A descoberta ocorre nesta ordem:

1. pasta `bin` indicada pela variável `SUMO_HOME`;
2. executável disponível no `PATH`.

Se o módulo Python `traci` não estiver instalado no ambiente, `sumo_tools.py` adiciona
`%SUMO_HOME%\tools` ao `sys.path` e tenta importá-lo dali.

### 3.2 Preparação no PowerShell

```powershell
$env:SUMO_HOME = 'C:\Users\fatec-dsm5\Downloads\sumo-win64-1.28.0'
$env:Path = "$env:SUMO_HOME\bin;$env:Path"
```

Para registrar a versão usada em uma futura rodada:

```powershell
sumo --version
netconvert --version
python --version
```

Recomenda-se guardar essas versões junto com cada conjunto de resultados. Uma atualização do
SUMO pode alterar defaults, geração da rede, dinâmica veicular ou formato das saídas.

## 4. Ordem de aplicação das configurações

O comportamento final resulta de várias camadas. Da mais estrutural para a mais dinâmica:

1. os XMLs de nós, arestas, conexões e semáforo são compilados pelo `netconvert`;
2. `smarttraffic.sumocfg` carrega rede, rotas, detectores, elementos visuais e tempo;
3. `run_simulation.py` acrescenta opções de linha de comando, como semente e saída;
4. depois da conexão, TraCI seleciona o programa semafórico e força a fase inicial;
5. no modo adaptativo, Python pode encerrar o verde chamando `setPhase`;
6. no experimento, um observador coleta dados a cada passo.

Uma opção fornecida ao binário na linha de comando pode sobrescrever o valor equivalente do
arquivo `.sumocfg`. A seleção do programa e da fase via TraCI ocorre depois que o SUMO inicia.

## 5. Geometria e topologia

### 5.1 Nós

| ID | Coordenada (m) | Tipo | Papel |
|---|---:|---|---|
| `west` | (-100, 0) | `dead_end` | origem da Via A |
| `J0` | (0, 0) | `traffic_light` | cruzamento controlado |
| `east` | (100, 0) | `dead_end` | destino da Via A |
| `south` | (0, -100) | `dead_end` | origem da Via B |
| `north` | (0, 100) | `dead_end` | destino da Via B |

Cada aproximação e cada saída possui aproximadamente 100 m. A Via A atravessa de oeste para
leste; a Via B, de sul para norte. Não existem movimentos no sentido inverso.

Na rede compilada, o `netconvert` aplica deslocamento `netOffset="100,100"`: o limite original
de `(-100,-100)` a `(100,100)` passa a `(0,0)` a `(200,200)`. Isso explica por que o viewport,
os polígonos e os POIs visuais usam coordenadas próximas de 100, embora os XMLs de nós estejam
centralizados em zero. O deslocamento não altera distâncias nem tempos de percurso.

### 5.2 Arestas e faixas

| Aresta | De → para | Faixas | Velocidade máxima |
|---|---|---:|---:|
| `A_in` | `west` → `J0` | 2 | 13,89 m/s (aprox. 50 km/h) |
| `A_out` | `J0` → `east` | 2 | 13,89 m/s (aprox. 50 km/h) |
| `B_in` | `south` → `J0` | 2 | 13,89 m/s (aprox. 50 km/h) |
| `B_out` | `J0` → `north` | 2 | 13,89 m/s (aprox. 50 km/h) |

Todas as arestas têm prioridade `1`. Largura de faixa, forma detalhada do cruzamento, faixas
internas e outros atributos geométricos não foram definidos explicitamente; são calculados
pelo `netconvert` segundo a versão instalada.

### 5.3 Movimentos permitidos

Somente movimentos retos são declarados:

- `A_in_0` → `A_out_0`;
- `A_in_1` → `A_out_1`;
- `B_in_0` → `B_out_0`;
- `B_in_1` → `B_out_1`.

Não há conversões, mudança de faixa dentro do cruzamento, retorno, travessia de pedestres,
ciclistas ou transporte coletivo. A compilação usa `--no-turnarounds true`.

### 5.4 Índices efetivos do semáforo

O arquivo-fonte `connections.con.xml` declara A nos índices 0 e 1 e B nos índices 2 e 3.
Entretanto, a rede compilada atualmente pelo `netconvert` 1.28.0 reorganiza os links:

| Índice compilado | Movimento efetivo |
|---:|---|
| 0 | `B_in_0` → `B_out_0` |
| 1 | `B_in_1` → `B_out_1` |
| 2 | `A_in_0` → `A_out_0` |
| 3 | `A_in_1` → `A_out_1` |

Por isso, o estado `rrGG` libera A e `GGrr` libera B. O código de observação também considera
B nas posições 0–1 e A nas posições 2–3. Este mapeamento deve ser conferido novamente sempre
que a geometria, as conexões ou a versão do `netconvert` mudarem. Confiar apenas nos
`linkIndex` do XML-fonte pode inverter a interpretação das vias.

## 6. Tipos de veículo

Os tipos `car_A` e `car_B` têm os mesmos parâmetros físicos e dinâmicos. Cores e formas são
diferentes apenas para identificação visual.

| Parâmetro | `car_A` | `car_B` | Interpretação |
|---|---:|---:|---|
| `vClass` | `passenger` | `passenger` | automóvel de passeio |
| `accel` | 2,6 m/s² | 2,6 m/s² | aceleração máxima desejada |
| `decel` | 4,5 m/s² | 4,5 m/s² | desaceleração confortável/declarada |
| `sigma` | 0,5 | 0,5 | imperfeição/aleatoriedade do modelo de condução |
| `length` | 4,5 m | 4,5 m | comprimento do veículo |
| `minGap` | 2,5 m | 2,5 m | distância mínima ao veículo à frente |
| `maxSpeed` | 13,89 m/s | 13,89 m/s | aproximadamente 50 km/h |
| `color` | `#2196F3` | `#FECD0A` | azul e amarelo |
| `guiShape` | sedan | hatchback | forma somente visual |

Não foram explicitados `carFollowModel`, parâmetros completos de reação, mudança de faixa,
largura, velocidade individual (`speedFactor`) ou distribuição de tipos. Esses aspectos usam
defaults do SUMO 1.28.0 e devem ser fixados antes de estudos mais rigorosos de sensibilidade.
A semente controla as decisões pseudoaleatórias, mas não transforma o modelo em determinístico
entre versões diferentes do simulador.

## 7. Demanda, rotas e inserção

### 7.1 Rotas

| Rota | Sequência |
|---|---|
| `route_A` | `A_in A_out` |
| `route_B` | `B_in B_out` |

Cada veículo cruza uma única vez e deixa a rede. Não há escolha de rota ou rerroteamento.

### 7.2 Fluxos

| Fluxo | Intervalo de geração | Período | Taxa nominal | Total atual |
|---|---:|---:|---:|---:|
| `flow_A` | 0 a 300 s | 4 s | 900 veículos/h | 75 veículos |
| `flow_B` | 0 a 300 s | 6 s | 600 veículos/h | 50 veículos |
| Total | 0 a 300 s | — | 1.500 veículos/h | 125 veículos |

A divisão nominal é 60% para A e 40% para B. Os totais de 75 e 50 foram confirmados nas
execuções atuais. `departLane="random"` sorteia uma das duas faixas; portanto, a divisão por
faixa varia conforme a semente. `departSpeed="max"` solicita inserção na velocidade máxima
permitida quando as condições da rede possibilitam.

A demanda é periódica, regular e assimétrica. Não representa flutuações, pelotões, horário de
pico, chegadas Poisson, incidentes ou comportamento observado em campo. Esse padrão simples é
útil para a primeira comparação controlada, mas limita a generalização dos resultados.

## 8. Configuração temporal do SUMO

Definições em `smarttraffic.sumocfg`:

| Parâmetro | Valor | Efeito |
|---|---:|---|
| `begin` | 0 s | início do relógio simulado |
| `end` | 360 s | limite superior do cenário |
| `step-length` | 1 s | resolução do avanço e da decisão |
| `time-to-teleport` | -1 | desabilita teleporte automático por espera excessiva |

O fluxo termina em 300 s, deixando até 60 s para dissipar as filas. No experimento comparativo,
o Python força exatamente 360 passos, mesmo se todos os veículos terminarem antes. Na execução
interativa normal, o loop termina quando `getMinExpectedNumber()` chega a zero; por isso ela
pode encerrar antes de 360 s.

O passo de 1 s significa que filas, segurança e decisões são observadas uma vez por segundo.
Ele é suficiente para o protótipo atual, mas torna transições e tempos quantizados em segundos.
Uma futura análise de segurança temporal pode exigir `step-length` menor, por exemplo 0,1 s,
com revalidação completa dos resultados.

Com `time-to-teleport=-1`, congestionamentos não são resolvidos removendo ou teleportando
veículos. Isso preserva filas reais do modelo, mas pode impedir o término espontâneo de um
cenário bloqueado.

## 9. Programas semafóricos

### 9.1 Estados

Na rede compilada, a sequência de quatro caracteres segue B0, B1, A0, A1:

| Estado | Significado |
|---|---|
| `rrGG` | A verde e B vermelho |
| `rryy` | A amarelo e B vermelho |
| `rrrr` | vermelho total |
| `GGrr` | B verde e A vermelho |
| `yyrr` | B amarelo e A vermelho |

Letras maiúsculas `G` representam passagem prioritária; `r` indica vermelho; `y`, amarelo.

### 9.2 Ciclo fixo `safe_fixed_cycle`

| Índice | Nome | Duração | Estado |
|---:|---|---:|---|
| 0 | `A_GREEN` | 10 s | `rrGG` |
| 1 | `A_YELLOW` | 3 s | `rryy` |
| 2 | `ALL_RED_TO_B` | 1 s | `rrrr` |
| 3 | `B_GREEN` | 10 s | `GGrr` |
| 4 | `B_YELLOW` | 3 s | `yyrr` |
| 5 | `ALL_RED_TO_A` | 1 s | `rrrr` |

O ciclo completo dura 28 s. Cada via recebe 10 s de verde por ciclo, e cada troca contém 3 s
de amarelo e 1 s de vermelho total. O `offset` é zero e a execução força a fase 0 no início,
logo A inicia verde.

### 9.3 Programa `safe_adaptive`

Possui os mesmos seis estados e as mesmas transições de 3 s de amarelo e 1 s de vermelho
total. As duas fases verdes têm duração XML de 1.000 s. Esse valor não é o verde desejado:
funciona como duração de espera longa para que o Python decida quando chamar `setPhase` e
entrar no amarelo correspondente.

Se o processo Python deixar de controlar o SUMO durante um verde adaptativo, o simulador pode
manter essa via por até 1.000 s. Não surgem verdes conflitantes por esse motivo, mas pode haver
starvation da via oposta. Isso deve ser tratado como característica técnica, não como fallback.

### 9.4 Seleção e inicialização

O modo solicitado é mapeado assim:

- `fixed` → `safe_fixed_cycle`;
- `adaptive` → `safe_adaptive`.

Após abrir TraCI, o código chama `setProgram('J0', ...)` e `setPhase('J0', 0)`. Portanto, todas
as execuções começam em A verde, independentemente do modo e da semente. Essa escolha pode
beneficiar A no início e deve ser avaliada em futuros ensaios com fase inicial alternada.

## 10. Política adaptativa em Python

### 10.1 Parâmetros padrão

| Parâmetro | Valor | Validação |
|---|---:|---|
| `minimum_green_seconds` | 8 s | deve ser positivo |
| `maximum_green_seconds` | 20 s | deve ser ≥ mínimo |
| `maximum_wait_seconds` | 30 s | deve ser positivo |

### 10.2 Ordem exata das regras

Para a via atualmente verde, a decisão é avaliada nesta ordem:

1. antes de 8 s, manter para cumprir o verde mínimo;
2. se não houver fila oposta, manter o verde atual;
3. se o veículo oposto mais antigo atingir 30 s, trocar;
4. se o verde atual atingir 20 s e houver demanda oposta, trocar;
5. se a fila oposta for maior que a atual, trocar;
6. se as filas empatarem e a espera mais antiga oposta for maior, trocar;
7. nos demais casos, manter.

Ao decidir pela troca, o código não ativa diretamente o verde oposto. Ele força o índice do
amarelo da via corrente (`1` para A e `4` para B), e o programa SUMO percorre amarelo,
vermelho total e próximo verde.

O máximo de 20 s não encerra o verde quando a fila oposta está vazia, porque a regra de demanda
oposta vem antes. Assim, “verde máximo” significa máximo condicionado à existência de demanda
oposta, não um limite absoluto.

### 10.3 Estado de fila fornecido ao controlador

Para cada via, o sistema lê IDs presentes nos dois detectores e considera parado o veículo
com velocidade estritamente menor que `0,1 m/s`. A fila é o conjunto desses IDs, evitando
duplicação entre faixas.

O instante registrado como “chegada” é a primeira observação do veículo dentro do detector,
mesmo que ele ainda estivesse em movimento. A variável `oldest_waiting_seconds` é calculada
para veículos atualmente parados, mas mede desde a entrada na zona, não necessariamente desde
o primeiro instante de parada. Portanto, ela é uma aproximação de antiguidade na aproximação e
não equivale exatamente ao `waitingTime` calculado pelo SUMO.

Quando o veículo deixa os detectores, seu histórico local é removido. Não existe tracking fora
dos 50 m, persistência entre execuções ou fusão com dados de câmera.

## 11. Detectores de fila

Existem quatro detectores de área E2, um por faixa de entrada:

| ID | Faixa | Posição inicial | Comprimento | Período de arquivo |
|---|---|---:|---:|---:|
| `queue_A_0` | `A_in_0` | -50 m | 50 m | 1 s |
| `queue_A_1` | `A_in_1` | -50 m | 50 m | 1 s |
| `queue_B_0` | `B_in_0` | -50 m | 50 m | 1 s |
| `queue_B_1` | `B_in_1` | -50 m | 50 m | 1 s |

Posição negativa indica medição relativa ao final da faixa. Assim, cada detector cobre os
50 m imediatamente anteriores ao cruzamento. `friendlyPos=true` permite ao SUMO ajustar a
posição se necessário em vez de rejeitar o detector.

Os detectores escrevem XML a cada 1 s, porém o controlador usa os valores instantâneos via
TraCI. Veículos parados além de 50 m não entram na fila observada; em demanda saturada, isso
pode truncar a métrica e alterar a decisão.

## 12. Parâmetros da aplicação de execução

Comando principal:

```powershell
python simulation/sumo/run_simulation.py [opções]
```

| Opção | Padrão | Efeito |
|---|---|---|
| `--gui` | desativado | usa `sumo-gui`; sem ela, usa `sumo` headless |
| `--mode` | `adaptive` | seleciona `fixed` ou `adaptive` |
| `--delay-ms` | 200 | atraso visual entre passos; somente GUI |
| `--rebuild-network` | desativado | força recompilação da rede |
| `--min-green` | 8 | verde mínimo adaptativo em segundos |
| `--max-green` | 20 | verde máximo condicionado em segundos |
| `--max-wait` | 30 | limite da antiguidade oposta em segundos |
| `--seed` | 42 | semente pseudoaleatória do SUMO |

O script também recompila automaticamente a rede se o `.net.xml` estiver ausente ou se algum
XML-fonte tiver data de modificação mais recente.

Comandos típicos:

```powershell
# Adaptativo headless, parâmetros padrão
python simulation/sumo/run_simulation.py

# Fixo e reproduzível
python simulation/sumo/run_simulation.py --mode fixed --seed 42

# Adaptativo visual em velocidade reduzida
python simulation/sumo/run_simulation.py --gui --mode adaptive --delay-ms 500

# Política alternativa para análise de sensibilidade
python simulation/sumo/run_simulation.py --min-green 10 --max-green 30 --max-wait 45
```

`delay-ms` altera somente a velocidade de apresentação da GUI, não o relógio simulado nem os
resultados. Já `step-length`, tempos semafóricos, demanda e política alteram o experimento.

## 13. Comando efetivamente enviado ao SUMO

Em execução headless, a forma lógica é:

```text
sumo --configuration-file <smarttraffic.sumocfg>
     --start
     --quit-on-end
     --seed <semente>
```

Quando uma saída exclusiva é solicitada pelo experimento, acrescenta-se:

```text
--tripinfo-output <arquivo-da-execução.xml>
```

Na GUI, também é acrescentado `--delay <milissegundos>`. O argumento `--start` inicia a
simulação sem exigir acionamento manual; `--quit-on-end` encerra a GUI ao final.

## 14. Experimento comparativo

Comando padrão:

```powershell
python simulation/sumo/run_experiment.py
```

### 14.1 Configuração atual

- sementes: 1 a 10;
- duas políticas por semente: primeiro fixa, depois adaptativa;
- total: 20 execuções;
- horizonte forçado: 360 s em todas as execuções;
- interface: headless;
- atraso visual: 0;
- verde mínimo: 8 s;
- verde máximo condicionado: 20 s;
- limite de espera observado: 30 s;
- mesma rede, demanda e tipos de veículo nos pares;
- saída `tripinfo` separada por política e semente.

Opções do comparador:

| Opção | Padrão |
|---|---|
| `--seeds` | `1,2,3,4,5,6,7,8,9,10` |
| `--min-green` | 8 |
| `--max-green` | 20 |
| `--max-wait` | 30 |

### 14.2 Dados coletados a cada segundo

- tempo simulado;
- nome e estado textual da fase;
- fila total de A e B;
- fila em cada uma das quatro faixas;
- maior antiguidade observada em A e B;
- IDs de veículos que partiram e chegaram;
- número de mudanças entre verdes;
- ocorrência de verde simultâneo nas duas vias.

### 14.3 Dados por veículo obtidos do `tripinfo`

- identificador e via;
- duração total da viagem;
- `waitingTime`;
- `timeLoss`;
- atraso de partida;
- quantidade de episódios de espera.

### 14.4 Agregações

- média, mediana, percentil 95 e máximo da espera;
- duração e tempo perdido médios;
- fila média e máxima, total e por via;
- veículos iniciados, concluídos e não concluídos;
- média e desvio-padrão entre repetições;
- diferença pareada adaptativo menos fixo;
- intervalo de confiança de 95% baseado em Student;
- tamanho de efeito pareado exploratório `dz`.

As sementes pareiam a aleatoriedade, mas políticas diferentes alteram a interação entre os
veículos ao longo do tempo. O desenho controla a entrada nominal; não exige que as trajetórias
microscópicas permaneçam idênticas depois que os sinais divergem.

## 15. Saídas e persistência

### 15.1 Saídas configuradas

- execução comum: `simulation/sumo/output/tripinfo.xml`;
- detectores: `detector_A_0.xml`, `detector_A_1.xml`, `detector_B_0.xml` e
  `detector_B_1.xml`;
- experimento: XMLs `tripinfo`, CSV por veículo, CSV de séries temporais e JSON consolidado em
  `simulation/sumo/output/experiments/`;
- resumo versionável: `reports/experiment_runs.csv`;
- relatório de resultados: `reports/adaptive_vs_fixed.md`.

O conteúdo de `output/` é ignorado pelo Git, exceto `.gitkeep`. Isso evita versionar grandes
artefatos reproduzíveis. Os relatórios consolidados permanecem fora dessa exclusão.

### 15.2 Logs desativados

`no-step-log=true` remove o log padrão de cada passo e `duration-log.disable=true` remove o
resumo de duração do processo. Isso reduz ruído e melhora a leitura do terminal, mas elimina
informações úteis de desempenho computacional. Ativar esses logs pode ajudar a diagnosticar
execuções grandes, sem mudar a dinâmica do tráfego.

## 16. Configuração visual

A aparência não modifica a física ou as métricas.

### 16.1 Viewport e atualização

| Item | Valor |
|---|---:|
| zoom inicial | 190 |
| centro do viewport | (100, 100) |
| ângulo | 0° |
| atraso visual padrão | 200 ms |
| antialiasing | ligado |
| grade | oculta |
| fundo | branco |

O `--delay-ms` fornecido pelo script pode sobrescrever o atraso do arquivo visual.

### 16.2 Vias, veículos e elementos

- pista uniforme em cinza-escuro;
- bordas de faixa visíveis;
- largura visual exagerada em 1,25;
- conectores ocultos;
- qualidade veicular 2;
- tamanho visual dos veículos exagerado em 1,8;
- setas/piscas visíveis;
- elementos adicionais exagerados em 1,5;
- POIs exagerados em 2 e nomes visíveis;
- legenda de escala visível.

### 16.3 Elementos decorativos

- base branca `maquette_base`;
- zona de fila A azul translúcida;
- zona de fila B amarela translúcida;
- marcadores “VIA A” e “VIA B”.

As coordenadas decorativas são adequadas à transformação visual gerada na rede, mas não são
usadas pelo controlador. Os polígonos que destacam as filas não substituem os detectores E2.

## 17. Parâmetros explícitos versus defaults

### Explicitamente controlados

- geometria básica e sentidos;
- duas faixas por via;
- limite de velocidade;
- tipos e dimensões principais dos veículos;
- aceleração, desaceleração, `sigma` e distância mínima;
- rotas, períodos e intervalo dos fluxos;
- sorteio de faixa e velocidade de partida;
- passo e horizonte da simulação;
- teleporte desabilitado;
- detectores e comprimento observado;
- estados e tempos semafóricos;
- regras e limites adaptativos;
- sementes do experimento;
- arquivos de saída e aparência principal.

### Herdados ou calculados pelo SUMO

- largura das faixas;
- forma final do nó e faixas internas;
- ordenação efetiva dos links semafóricos;
- modelo de seguimento e seus parâmetros não declarados;
- modelo de mudança de faixa e seus parâmetros;
- fatores individuais de velocidade;
- limites e atributos não declarados dos detectores;
- vários detalhes de inserção e resolução de conflitos;
- precisão numérica e comportamento associado à versão.

Para um artigo mais maduro, parâmetros que possam influenciar a hipótese devem ser
explicitados no XML, mesmo quando o valor escolhido for igual ao default atual.

## 18. Limitações da configuração atual

1. Existe apenas um padrão regular e assimétrico de demanda.
2. O horizonte de 360 s é curto para extrapolações de capacidade.
3. Dez sementes ajudam na repetibilidade, mas não cobrem diversidade de cenários.
4. O passo de 1 s limita a resolução temporal do controle.
5. A fila é visível somente nos 50 m anteriores ao sinal.
6. A espera mais antiga da política inclui tempo em movimento dentro do detector.
7. Todos os testes iniciam com A verde.
8. O verde adaptativo de 1.000 s depende da atuação contínua do Python.
9. Não há pedestres, conversões, veículos prioritários, bloqueios ou acidentes.
10. Não há ruído de percepção, falso positivo, falso negativo ou atraso de câmera.
11. Não há latência, perda serial, ACK ou dinâmica elétrica do Arduino.
12. O modelo usa dimensões urbanas, não uma escala física de carrinhos.
13. Alguns defaults relevantes do SUMO ainda não foram fixados.
14. A validação de segurança observa estados lógicos, não conflitos geométricos ou hardware.

## 19. Plano de refinamento dos parâmetros

| Prioridade | Refinamento | Motivo | Comparação sugerida |
|---|---|---|---|
| Alta | corrigir/documentar definitivamente os índices de links | evitar inversão silenciosa das vias | validar rede compilada automaticamente |
| Alta | variar demanda | testar robustez da vantagem adaptativa | equilibrada, A dominante, B dominante, rajadas |
| Alta | testar saturação | identificar truncamento de fila e capacidade | taxas crescentes até formar fila residual |
| Alta | variar tempos adaptativos | evitar escolha baseada em um único ajuste | grade de mínimo, máximo e espera |
| Alta | alternar fase inicial | medir viés de inicialização | A inicial, B inicial e início aleatório pareado |
| Média | reduzir `step-length` | avaliar sensibilidade temporal | 1,0; 0,5; 0,1 s |
| Média | ampliar detectores | evitar fila truncada | 50; 75; 100 m |
| Média | fixar modelos veiculares | reduzir dependência de defaults | declarar car-follow e lane-change |
| Média | ampliar duração e sementes | melhorar estabilidade estatística | 900–3.600 s e ≥30 sementes |
| Média | incluir demanda estocástica | aproximar chegadas não periódicas | distribuição de headways documentada |
| Futura | pedestres e fases exclusivas | cobrir requisito do MVP | taxas e limites de espera pedestre |
| Futura | emular percepção | aproximar câmera/YOLO | atraso, perda e erro de contagem |
| Futura | emular comunicação | aproximar Arduino | latência, timeout, ACK e falha segura |

Cada alteração deve gerar um identificador de cenário, preservar os XMLs utilizados e produzir
nova tabela de resultados. Não é recomendável ajustar parâmetros usando as mesmas execuções
empregadas como evidência final sem separar calibração de avaliação.

## 20. Checklist de reprodutibilidade para futuras rodadas

- [ ] registrar hash/commit do repositório;
- [ ] registrar versões de SUMO, `netconvert` e Python;
- [ ] reconstruir a rede e guardar eventuais avisos;
- [ ] conferir índices semafóricos na rede compilada;
- [ ] registrar todos os XMLs e parâmetros CLI;
- [ ] usar a mesma lista de sementes nas políticas comparadas;
- [ ] manter o mesmo horizonte e passo de simulação;
- [ ] confirmar total de veículos inseridos e concluídos;
- [ ] verificar veículos teleportados ou não concluídos;
- [ ] verificar verdes conflitantes e sequência amarelo/vermelho total;
- [ ] guardar resultados brutos antes de gerar agregações;
- [ ] relatar média, dispersão, percentis e máximos;
- [ ] declarar se houve seleção ou descarte de execuções;
- [ ] separar resultados de simulação dos resultados físicos;
- [ ] registrar toda mudança de parâmetro em relação a esta linha de base.

## 21. Linha de base resumida

Para reproduzir exatamente a configuração comparativa atual:

```powershell
$env:SUMO_HOME = 'C:\Users\fatec-dsm5\Downloads\sumo-win64-1.28.0'
python simulation/sumo/build_network.py
python simulation/sumo/run_experiment.py --seeds 1,2,3,4,5,6,7,8,9,10 --min-green 8 --max-green 20 --max-wait 30
```

Resumo metodológico: cruzamento de 200 m por eixo, duas faixas por aproximação, velocidade de
13,89 m/s, 125 veículos em demanda periódica 60/40, geração até 300 s, observação até 360 s,
passo de 1 s, detectores E2 de 50 m, ciclo fixo de 28 s e controle adaptativo com verde mínimo
de 8 s, máximo condicionado de 20 s e limite de antiguidade de 30 s.
