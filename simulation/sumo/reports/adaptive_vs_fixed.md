# Relatório experimental — controle fixo versus adaptativo

**Data da execução:** 26/10/2026  
**Simulador:** SUMO 1.28.0  
**Cenário:** cruzamento único SmartTraffic, duas vias de sentido único, duas faixas por via  
**Repetições pareadas:** 10 por política (20 execuções)  
**Sementes:** 1, 2, 3, 4, 5, 6, 7, 8, 9, 10

## Objetivo e desenho do experimento

O experimento compara somente a política semafórica. Para cada semente, os modos fixo e adaptativo recebem a mesma geometria, fluxos, tipos de veículo, período de geração, parâmetros de condução e horizonte de 360 s. A Via A recebe um veículo a cada 4 s e a Via B, um a cada 6 s, entre 0 e 300 s. O pareamento reduz a influência da escolha aleatória de faixa e da variabilidade do modelo de condução.

O ciclo fixo usa 10 s de verde, 3 s de amarelo e 1 s de vermelho total para cada direção. O adaptativo usa verde mínimo de 8 s, máximo de 20 s e limite de espera observado de 30 s, mantendo os mesmos 3 s de amarelo e 1 s de vermelho total.

## Resultados agregados

Os valores são média entre execuções ± desvio-padrão. Na coluna “redução”, valor positivo significa que o adaptativo reduziu a métrica; para número de trocas, a coluna expressa apenas a variação relativa, não um benefício automático.

| Métrica | Fixo | Adaptativo | Redução adaptativa |
|---|---:|---:|---:|
| Espera média por veículo (s) | 4.44 ± 0.13 | 3.84 ± 0.18 | +13.5% |
| Mediana da espera (s) | 2.90 ± 0.32 | 1.90 ± 0.32 | +34.5% |
| Percentil 95 da espera (s) | 13.58 ± 0.50 | 12.48 ± 0.63 | +8.1% |
| Maior espera individual (s) | 15.20 ± 0.79 | 14.80 ± 0.42 | +2.6% |
| Duração média da viagem (s) | 24.82 ± 0.25 | 24.06 ± 0.35 | +3.1% |
| Tempo perdido médio (s) | 9.65 ± 0.24 | 8.88 ± 0.31 | +8.0% |
| Fila média total (veículos) | 1.54 ± 0.05 | 1.33 ± 0.06 | +13.5% |
| Maior fila total (veículos) | 4.50 ± 0.53 | 4.50 ± 0.53 | +0.0% |
| Trocas entre verdes | 25.00 ± 0.00 | 24.00 ± 0.00 | +4.0% |

### Resultados por via

| Métrica | Fixo | Adaptativo | Redução adaptativa |
|---|---:|---:|---:|
| Via A — espera média (s) | 4.73 ± 0.21 | 3.95 ± 0.26 | +16.4% |
| Via A — P95 da espera (s) | 13.59 ± 0.45 | 12.42 ± 0.76 | +8.6% |
| Via A — duração média (s) | 25.45 ± 0.29 | 24.30 ± 0.50 | +4.5% |
| Via B — espera média (s) | 4.02 ± 0.07 | 3.68 ± 0.30 | +8.4% |
| Via B — P95 da espera (s) | 13.23 ± 0.48 | 12.04 ± 0.93 | +9.0% |
| Via B — duração média (s) | 23.86 ± 0.23 | 23.69 ± 0.50 | +0.7% |

### Diferenças pareadas e dispersão

- Diferença adaptativo − fixo na espera média: **-0.60 s**, IC 95% de Student **[-0.71; -0.50] s**.
- Diferença adaptativo − fixo na fila média total: **-0.21 veículo(s)**, IC 95% de Student **[-0.25; -0.17]**.
- O adaptativo apresentou menor espera média em **10 de 10** pares de execução; tamanho de efeito pareado exploratório **dz = 4.07**.
- Veículos concluídos, somando as repetições: fixo **1250**, adaptativo **1250**.
- Veículos ainda não concluídos ao final: fixo **0**, adaptativo **0**.
- Instantes com verdes conflitantes detectados: fixo **0**, adaptativo **0**.

### Espera média em cada repetição

| Semente | Fixo (s) | Adaptativo (s) | Redução |
|---:|---:|---:|---:|
| 1 | 4.40 | 3.90 | +11.3% |
| 2 | 4.38 | 3.98 | +9.0% |
| 3 | 4.31 | 3.65 | +15.4% |
| 4 | 4.41 | 3.64 | +17.4% |
| 5 | 4.46 | 4.05 | +9.2% |
| 6 | 4.63 | 3.89 | +16.1% |
| 7 | 4.72 | 4.03 | +14.6% |
| 8 | 4.30 | 3.51 | +18.2% |
| 9 | 4.41 | 3.91 | +11.3% |
| 10 | 4.44 | 3.86 | +13.0% |

## Definição das métricas

- **Espera:** `waitingTime` do SUMO, tempo acumulado em que o veículo permaneceu praticamente parado (velocidade abaixo do limiar interno do simulador).
- **Tempo perdido:** diferença estimada pelo SUMO entre o tempo real e o tempo de percurso em condições ideais.
- **Fila:** quantidade de veículos parados dentro dos detectores E2, que cobrem os 50 m anteriores ao cruzamento. A fila média é a média das amostras de 1 s; veículos além da área detectada não entram nessa métrica.
- **P95:** valor abaixo do qual estão 95% das observações; ajuda a observar casos ruins que a média pode ocultar.
- **Segurança lógica:** verificação, a cada passo, de que A e B não exibiram verde simultaneamente. Isso não valida circuito, firmware ou tempos físicos.

## Interpretação e limites

Os números demonstram o comportamento do controlador no cenário virtual especificado, não comprovam desempenho em tráfego urbano real nem na maquete física. A demanda usada é regular e assimétrica, sem pedestres, conversões, falhas, colisões de percepção ou ruído de câmera. O “veículo mais antigo” usado pela decisão adaptativa é estimado desde a entrada na zona de detecção enquanto o veículo está parado; não é ainda uma medição por webcam.

Antes de usar uma afirmação causal no artigo, recomenda-se repetir o protocolo com demandas equilibrada, saturada, variável e em rajadas, além da validação posterior com webcams e Arduino. Este relatório pode sustentar resultados de **simulação**, desde que essas limitações sejam declaradas.

## Texto-base para o artigo

> Em 10 repetições pareadas de 360 s no SUMO, mantendo-se constantes a geometria, a demanda e os parâmetros veiculares, o controle adaptativo apresentou tempo médio de espera de 3.84 ± 0.18 s, contra 4.44 ± 0.13 s no controle fixo, redução de 13.5%. A diferença pareada foi de -0.60 s por veículo (IC 95% [-0.71; -0.50] s), com menor espera adaptativa nas 10 repetições. A fila média total caiu de 1.54 para 1.33 veículos (13.5%), sem diferença na maior fila agregada e sem ocorrência de verdes conflitantes na verificação lógica. Esses resultados são restritos ao cenário virtual regular e assimétrico avaliado e não constituem validação da percepção por câmera nem da atuação pelo Arduino.

## Reprodutibilidade

Com `SUMO_HOME` configurado para a instalação 1.28.0:

```powershell
python simulation/sumo/run_experiment.py --seeds 1,2,3,4,5,6,7,8,9,10 --min-green 8 --max-green 20 --max-wait 30
```

Os dados por execução ficam em `reports/experiment_runs.csv`; os dados por veículo e as séries temporais ficam em `output/experiments/`.
