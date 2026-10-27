# Simulação SUMO do SmartTraffic

Este cenário representa o primeiro cruzamento virtual do projeto:

- Via A no sentido oeste → leste;
- Via B no sentido sul → norte;
- duas faixas por via e somente movimentos retos;
- semáforo com verde, amarelo e vermelho total;
- um detector de área E2 por faixa nos 50 metros anteriores ao cruzamento;
- fluxos veiculares determinísticos para permitir repetição.

No modo gráfico, veículos da Via A são azuis e veículos da Via B são amarelos. As regiões transparentes próximas ao cruzamento representam as zonas observadas pelos detectores de fila. O tema, o zoom inicial e os elementos decorativos ficam versionados com o cenário.

O tema também amplia visualmente veículos, marcadores e vias para facilitar a leitura. Essa ampliação é apenas gráfica: dimensões físicas, capacidade das faixas e métricas da simulação não são modificadas.

O cenário valida a movimentação e os dados virtuais do SUMO. Ele possui uma primeira política adaptativa Python em `adaptive_controller.py`, mas ainda não simula a visão computacional e não representa uma validação do Arduino. A aplicação física `smarttraffic_app.py` ainda não utiliza esse novo controlador.

## Preparação no PowerShell

```powershell
$env:SUMO_HOME = 'C:\Users\seu-usuario\Downloads\sumo-win64-1.28.0'
$env:Path = "$env:SUMO_HOME\bin;$env:Path"
```

O caminho acima é apenas um exemplo local e não deve ser gravado no código.

## Execução

O script gera a rede automaticamente quando necessário e inicia uma execução adaptativa sem interface gráfica:

```powershell
python simulation/sumo/run_simulation.py
```

O modo pode ser escolhido explicitamente:

```powershell
# Controle adaptativo (padrão)
python simulation/sumo/run_simulation.py --mode adaptive

# Ciclo fixo para comparação
python simulation/sumo/run_simulation.py --mode fixed
```

Para acompanhar os veículos no `sumo-gui`:

```powershell
python simulation/sumo/run_simulation.py --gui
```

No modo gráfico, o script aplica por padrão um atraso de 200 milissegundos entre passos. Para deixar a visualização mais lenta:

```powershell
python simulation/sumo/run_simulation.py --gui --delay-ms 500
```

Para observar o controle adaptativo mais lentamente:

```powershell
python simulation/sumo/run_simulation.py --gui --mode adaptive --delay-ms 500
```

Use `--delay-ms 0` para executar novamente na velocidade máxima. A velocidade também pode ser alterada durante a execução pelos controles do próprio `sumo-gui`.

As opções visuais podem ser ajustadas no `sumo-gui` com `F9`. Para preservar uma alteração para toda a equipe, salve-a em `scenarios/single_intersection/viewsettings.xml`.

Para reconstruir a rede explicitamente:

```powershell
python simulation/sumo/build_network.py
```

Os arquivos gerados em `output/` e a rede compilada `network/smarttraffic.net.xml` não são versionados.

## Controle adaptativo

A política virtual inicial aplica estas regras:

1. mantém cada verde por no mínimo 8 segundos;
2. depois do mínimo, prioriza a via com maior fila;
3. em empate, prioriza o veículo aguardando há mais tempo;
4. troca ao atingir 20 segundos de verde quando existe demanda oposta;
5. atende uma fila oposta que alcançar 30 segundos de espera;
6. toda troca passa automaticamente por amarelo e vermelho total.

Os valores podem ser alterados para experimentos:

```powershell
python simulation/sumo/run_simulation.py --mode adaptive --min-green 8 --max-green 20 --max-wait 30
```

Esses parâmetros são valores do cenário virtual, não tempos físicos aprovados para a maquete.

## Comparação experimental

O comparador executa os modos fixo e adaptativo pelo mesmo horizonte de 360 segundos,
com as mesmas sementes e configurações de tráfego. Por padrão são feitas dez repetições
pareadas por política:

```powershell
python simulation/sumo/run_experiment.py
```

O relatório consolidado e os dados por execução são gravados em `reports/`. Os XMLs por
veículo e as séries temporais de 1 segundo são artefatos reproduzíveis mantidos em
`output/experiments/` e ignorados pelo Git. Para escolher sementes ou parâmetros:

```powershell
python simulation/sumo/run_experiment.py --seeds 1,2,3 --min-green 8 --max-green 20 --max-wait 30
```

As métricas incluem tempo de espera, duração da viagem, tempo perdido, filas por via,
trocas de verde, veículos não concluídos e verificação lógica de verdes conflitantes.
Elas validam somente o cenário virtual; não substituem testes com webcams e Arduino.

A referência abrangente dos parâmetros, defaults, precedência de configuração, limitações e
possíveis refinamentos está em `reports/sumo_configuration_reference.md`.

## Fases do ciclo fixo

| Fase | Duração inicial | Estado |
|---|---:|---|
| `A_GREEN` | 10 s | A verde, B vermelho |
| `A_YELLOW` | 3 s | A amarelo, B vermelho |
| `ALL_RED_TO_B` | 1 s | ambas vermelhas |
| `B_GREEN` | 10 s | A vermelho, B verde |
| `B_YELLOW` | 3 s | A vermelho, B amarelo |
| `ALL_RED_TO_A` | 1 s | ambas vermelhas |

O modo adaptativo usa as mesmas transições de amarelo e vermelho total, mas decide em Python quando encerrar cada verde.
