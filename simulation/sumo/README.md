# Simulação SUMO do SmartTraffic

Este cenário representa o primeiro cruzamento virtual do projeto:

- Via A no sentido oeste → leste;
- Via B no sentido sul → norte;
- uma faixa por via e somente movimentos retos;
- semáforo com verde, amarelo e vermelho total;
- detectores de área E2 nos 50 metros anteriores ao cruzamento;
- fluxos veiculares determinísticos para permitir repetição.

No modo gráfico, veículos da Via A são azuis e veículos da Via B são amarelos. As regiões transparentes próximas ao cruzamento representam as zonas observadas pelos detectores de fila. O tema, o zoom inicial e os elementos decorativos ficam versionados com o cenário.

O cenário valida a movimentação e os dados virtuais do SUMO. Ele ainda não usa a lógica adaptativa de `smarttraffic_app.py`, não simula a visão computacional e não representa uma validação do Arduino.

## Preparação no PowerShell

```powershell
$env:SUMO_HOME = 'C:\Users\seu-usuario\Downloads\sumo-win64-1.28.0'
$env:Path = "$env:SUMO_HOME\bin;$env:Path"
```

O caminho acima é apenas um exemplo local e não deve ser gravado no código.

## Execução

O script gera a rede automaticamente quando necessário e inicia uma execução sem interface gráfica:

```powershell
python simulation/sumo/run_simulation.py
```

Para acompanhar os veículos no `sumo-gui`:

```powershell
python simulation/sumo/run_simulation.py --gui
```

No modo gráfico, o script aplica por padrão um atraso de 200 milissegundos entre passos. Para deixar a visualização mais lenta:

```powershell
python simulation/sumo/run_simulation.py --gui --delay-ms 500
```

Use `--delay-ms 0` para executar novamente na velocidade máxima. A velocidade também pode ser alterada durante a execução pelos controles do próprio `sumo-gui`.

As opções visuais podem ser ajustadas no `sumo-gui` com `F9`. Para preservar uma alteração para toda a equipe, salve-a em `scenarios/single_intersection/viewsettings.xml`.

Para reconstruir a rede explicitamente:

```powershell
python simulation/sumo/build_network.py
```

Os arquivos gerados em `output/` e a rede compilada `network/smarttraffic.net.xml` não são versionados.

## Fases atuais

| Fase | Duração inicial | Estado |
|---|---:|---|
| `A_GREEN` | 10 s | A verde, B vermelho |
| `A_YELLOW` | 3 s | A amarelo, B vermelho |
| `ALL_RED_TO_B` | 1 s | ambas vermelhas |
| `B_GREEN` | 10 s | A vermelho, B verde |
| `B_YELLOW` | 3 s | A vermelho, B amarelo |
| `ALL_RED_TO_A` | 1 s | ambas vermelhas |

Esses valores servem apenas ao cenário virtual inicial e não são tempos físicos aprovados para a maquete.
