"""Compara os controles fixo e adaptativo sob entradas pareadas no SUMO."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import date
import json
import math
from pathlib import Path
from statistics import mean, median, stdev
import xml.etree.ElementTree as ET

from adaptive_controller import AdaptiveSettings
from run_simulation import run


BASE_DIRECTORY = Path(__file__).resolve().parent
REPORT_DIRECTORY = BASE_DIRECTORY / 'reports'
RAW_DIRECTORY = BASE_DIRECTORY / 'output' / 'experiments'
DEFAULT_SEEDS = tuple(range(1, 11))


def percentile(values: list[float], percentage: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


@dataclass
class RunObserver:
    rows: list[dict] = field(default_factory=list)
    departed_ids: set[str] = field(default_factory=set)
    arrived_ids: set[str] = field(default_factory=set)
    green_changes: int = 0
    safety_violations: int = 0
    previous_green: str | None = None

    def __call__(
        self,
        *,
        traci,
        simulation_time: float,
        approach_states,
        queues_by_lane,
        phase_name: str,
    ) -> None:
        self.departed_ids.update(traci.simulation.getDepartedIDList())
        self.arrived_ids.update(traci.simulation.getArrivedIDList())

        signal_state = traci.trafficlight.getRedYellowGreenState('J0')
        green_a = any(symbol in 'Gg' for symbol in signal_state[2:4])
        green_b = any(symbol in 'Gg' for symbol in signal_state[0:2])
        if green_a and green_b:
            self.safety_violations += 1

        current_green = 'A' if green_a else 'B' if green_b else None
        if current_green is not None and self.previous_green not in (None, current_green):
            self.green_changes += 1
        if current_green is not None:
            self.previous_green = current_green

        self.rows.append(
            {
                'time': simulation_time,
                'phase': phase_name,
                'signal_state': signal_state,
                'queue_a': approach_states['A'].queue_length,
                'queue_b': approach_states['B'].queue_length,
                'oldest_wait_a': approach_states['A'].oldest_waiting_seconds,
                'oldest_wait_b': approach_states['B'].oldest_waiting_seconds,
                'queue_a_lane_0': queues_by_lane['A'][0],
                'queue_a_lane_1': queues_by_lane['A'][1],
                'queue_b_lane_0': queues_by_lane['B'][0],
                'queue_b_lane_1': queues_by_lane['B'][1],
            }
        )


def parse_tripinfo(path: Path) -> list[dict]:
    vehicles = []
    root = ET.parse(path).getroot()
    for item in root.findall('tripinfo'):
        vehicle_type = item.attrib['vType']
        vehicles.append(
            {
                'id': item.attrib['id'],
                'via': 'A' if vehicle_type == 'car_A' else 'B',
                'duration': float(item.attrib['duration']),
                'waiting_time': float(item.attrib['waitingTime']),
                'time_loss': float(item.attrib['timeLoss']),
                'depart_delay': float(item.attrib['departDelay']),
                'waiting_count': int(item.attrib['waitingCount']),
            }
        )
    return vehicles


def vehicle_statistics(vehicles: list[dict], via: str | None = None) -> dict:
    selected = vehicles if via is None else [vehicle for vehicle in vehicles if vehicle['via'] == via]
    waits = [vehicle['waiting_time'] for vehicle in selected]
    durations = [vehicle['duration'] for vehicle in selected]
    losses = [vehicle['time_loss'] for vehicle in selected]
    return {
        'vehicles': len(selected),
        'mean_wait': mean(waits) if waits else 0.0,
        'median_wait': median(waits) if waits else 0.0,
        'p95_wait': percentile(waits, 0.95),
        'max_wait': max(waits, default=0.0),
        'mean_duration': mean(durations) if durations else 0.0,
        'mean_time_loss': mean(losses) if losses else 0.0,
    }


def summarize_run(mode: str, seed: int, observer: RunObserver, vehicles: list[dict]) -> dict:
    queue_a = [row['queue_a'] for row in observer.rows]
    queue_b = [row['queue_b'] for row in observer.rows]
    overall = vehicle_statistics(vehicles)
    summary = {
        'mode': mode,
        'seed': seed,
        'simulation_seconds': len(observer.rows),
        'departed': len(observer.departed_ids),
        'arrived': len(observer.arrived_ids),
        'unfinished': len(observer.departed_ids - observer.arrived_ids),
        'green_changes': observer.green_changes,
        'safety_violations': observer.safety_violations,
        'mean_queue_a': mean(queue_a) if queue_a else 0.0,
        'mean_queue_b': mean(queue_b) if queue_b else 0.0,
        'mean_queue_total': mean([a + b for a, b in zip(queue_a, queue_b)]) if queue_a else 0.0,
        'max_queue_a': max(queue_a, default=0),
        'max_queue_b': max(queue_b, default=0),
        'max_queue_total': max((a + b for a, b in zip(queue_a, queue_b)), default=0),
        **overall,
    }
    for via in ('A', 'B'):
        for key, value in vehicle_statistics(vehicles, via).items():
            summary[f'{key}_{via.lower()}'] = value
    return summary


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def aggregate(runs: list[dict], mode: str, metric: str) -> tuple[float, float]:
    values = [run[metric] for run in runs if run['mode'] == mode]
    return mean(values), stdev(values) if len(values) > 1 else 0.0


def paired_interval(runs: list[dict], seeds: tuple[int, ...], metric: str) -> tuple[float, float, float]:
    by_key = {(run['mode'], run['seed']): run for run in runs}
    differences = [
        by_key[('adaptive', seed)][metric] - by_key[('fixed', seed)][metric]
        for seed in seeds
    ]
    average = mean(differences)
    if len(differences) < 2:
        return average, average, average
    critical_values = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
        6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
    }
    critical = critical_values.get(len(differences) - 1, 1.96)
    margin = critical * stdev(differences) / math.sqrt(len(differences))
    return average, average - margin, average + margin


def format_comparison(runs: list[dict], metric: str) -> tuple[str, str, str]:
    fixed_mean, fixed_sd = aggregate(runs, 'fixed', metric)
    adaptive_mean, adaptive_sd = aggregate(runs, 'adaptive', metric)
    improvement = ((fixed_mean - adaptive_mean) / fixed_mean * 100) if fixed_mean else 0.0
    return (
        f'{fixed_mean:.2f} ± {fixed_sd:.2f}',
        f'{adaptive_mean:.2f} ± {adaptive_sd:.2f}',
        f'{improvement:+.1f}%',
    )


def generate_report(
    runs: list[dict],
    seeds: tuple[int, ...],
    settings: AdaptiveSettings,
) -> str:
    metric_rows = (
        ('Espera média por veículo (s)', 'mean_wait'),
        ('Mediana da espera (s)', 'median_wait'),
        ('Percentil 95 da espera (s)', 'p95_wait'),
        ('Maior espera individual (s)', 'max_wait'),
        ('Duração média da viagem (s)', 'mean_duration'),
        ('Tempo perdido médio (s)', 'mean_time_loss'),
        ('Fila média total (veículos)', 'mean_queue_total'),
        ('Maior fila total (veículos)', 'max_queue_total'),
        ('Trocas entre verdes', 'green_changes'),
    )
    table = []
    for label, metric in metric_rows:
        fixed, adaptive, change = format_comparison(runs, metric)
        table.append(f'| {label} | {fixed} | {adaptive} | {change} |')

    by_key = {(run['mode'], run['seed']): run for run in runs}
    completed_fixed = sum(by_key[('fixed', seed)]['arrived'] for seed in seeds)
    completed_adaptive = sum(by_key[('adaptive', seed)]['arrived'] for seed in seeds)
    unfinished_fixed = sum(by_key[('fixed', seed)]['unfinished'] for seed in seeds)
    unfinished_adaptive = sum(by_key[('adaptive', seed)]['unfinished'] for seed in seeds)
    violations_fixed = sum(by_key[('fixed', seed)]['safety_violations'] for seed in seeds)
    violations_adaptive = sum(by_key[('adaptive', seed)]['safety_violations'] for seed in seeds)

    wait_delta, wait_low, wait_high = paired_interval(runs, seeds, 'mean_wait')
    queue_delta, queue_low, queue_high = paired_interval(runs, seeds, 'mean_queue_total')
    fixed_wait_mean, fixed_wait_sd = aggregate(runs, 'fixed', 'mean_wait')
    adaptive_wait_mean, adaptive_wait_sd = aggregate(runs, 'adaptive', 'mean_wait')
    wait_reduction = (fixed_wait_mean - adaptive_wait_mean) / fixed_wait_mean * 100
    fixed_queue_mean, _ = aggregate(runs, 'fixed', 'mean_queue_total')
    adaptive_queue_mean, _ = aggregate(runs, 'adaptive', 'mean_queue_total')
    queue_reduction = (fixed_queue_mean - adaptive_queue_mean) / fixed_queue_mean * 100
    wait_differences = [
        by_key[('adaptive', seed)]['mean_wait'] - by_key[('fixed', seed)]['mean_wait']
        for seed in seeds
    ]
    adaptive_wins = sum(difference < 0 for difference in wait_differences)
    effect_size = (
        abs(mean(wait_differences) / stdev(wait_differences))
        if len(wait_differences) > 1 and stdev(wait_differences) > 0
        else 0.0
    )
    seed_rows = []
    for seed in seeds:
        fixed_wait = by_key[('fixed', seed)]['mean_wait']
        adaptive_wait = by_key[('adaptive', seed)]['mean_wait']
        reduction = (fixed_wait - adaptive_wait) / fixed_wait * 100 if fixed_wait else 0.0
        seed_rows.append(
            f'| {seed} | {fixed_wait:.2f} | {adaptive_wait:.2f} | {reduction:+.1f}% |'
        )

    via_rows = []
    for via in ('A', 'B'):
        for label, metric in (
            (f'Via {via} — espera média (s)', f'mean_wait_{via.lower()}'),
            (f'Via {via} — P95 da espera (s)', f'p95_wait_{via.lower()}'),
            (f'Via {via} — duração média (s)', f'mean_duration_{via.lower()}'),
        ):
            fixed, adaptive, change = format_comparison(runs, metric)
            via_rows.append(f'| {label} | {fixed} | {adaptive} | {change} |')

    return f"""# Relatório experimental — controle fixo versus adaptativo

**Data da execução:** {date.today().strftime('%d/%m/%Y')}  
**Simulador:** SUMO 1.28.0  
**Cenário:** cruzamento único SmartTraffic, duas vias de sentido único, duas faixas por via  
**Repetições pareadas:** {len(seeds)} por política ({len(seeds) * 2} execuções)  
**Sementes:** {', '.join(map(str, seeds))}

## Objetivo e desenho do experimento

O experimento compara somente a política semafórica. Para cada semente, os modos fixo e adaptativo recebem a mesma geometria, fluxos, tipos de veículo, período de geração, parâmetros de condução e horizonte de 360 s. A Via A recebe um veículo a cada 4 s e a Via B, um a cada 6 s, entre 0 e 300 s. O pareamento reduz a influência da escolha aleatória de faixa e da variabilidade do modelo de condução.

O ciclo fixo usa 10 s de verde, 3 s de amarelo e 1 s de vermelho total para cada direção. O adaptativo usa verde mínimo de {settings.minimum_green_seconds:g} s, máximo de {settings.maximum_green_seconds:g} s e limite de espera observado de {settings.maximum_wait_seconds:g} s, mantendo os mesmos 3 s de amarelo e 1 s de vermelho total.

## Resultados agregados

Os valores são média entre execuções ± desvio-padrão. Na coluna “redução”, valor positivo significa que o adaptativo reduziu a métrica; para número de trocas, a coluna expressa apenas a variação relativa, não um benefício automático.

| Métrica | Fixo | Adaptativo | Redução adaptativa |
|---|---:|---:|---:|
{chr(10).join(table)}

### Resultados por via

| Métrica | Fixo | Adaptativo | Redução adaptativa |
|---|---:|---:|---:|
{chr(10).join(via_rows)}

### Diferenças pareadas e dispersão

- Diferença adaptativo − fixo na espera média: **{wait_delta:+.2f} s**, IC 95% de Student **[{wait_low:+.2f}; {wait_high:+.2f}] s**.
- Diferença adaptativo − fixo na fila média total: **{queue_delta:+.2f} veículo(s)**, IC 95% de Student **[{queue_low:+.2f}; {queue_high:+.2f}]**.
- O adaptativo apresentou menor espera média em **{adaptive_wins} de {len(seeds)}** pares de execução; tamanho de efeito pareado exploratório **dz = {effect_size:.2f}**.
- Veículos concluídos, somando as repetições: fixo **{completed_fixed}**, adaptativo **{completed_adaptive}**.
- Veículos ainda não concluídos ao final: fixo **{unfinished_fixed}**, adaptativo **{unfinished_adaptive}**.
- Instantes com verdes conflitantes detectados: fixo **{violations_fixed}**, adaptativo **{violations_adaptive}**.

### Espera média em cada repetição

| Semente | Fixo (s) | Adaptativo (s) | Redução |
|---:|---:|---:|---:|
{chr(10).join(seed_rows)}

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

> Em {len(seeds)} repetições pareadas de 360 s no SUMO, mantendo-se constantes a geometria, a demanda e os parâmetros veiculares, o controle adaptativo apresentou tempo médio de espera de {adaptive_wait_mean:.2f} ± {adaptive_wait_sd:.2f} s, contra {fixed_wait_mean:.2f} ± {fixed_wait_sd:.2f} s no controle fixo, redução de {wait_reduction:.1f}%. A diferença pareada foi de {wait_delta:.2f} s por veículo (IC 95% [{wait_low:.2f}; {wait_high:.2f}] s), com menor espera adaptativa nas {adaptive_wins} repetições. A fila média total caiu de {fixed_queue_mean:.2f} para {adaptive_queue_mean:.2f} veículos ({queue_reduction:.1f}%), sem diferença na maior fila agregada e sem ocorrência de verdes conflitantes na verificação lógica. Esses resultados são restritos ao cenário virtual regular e assimétrico avaliado e não constituem validação da percepção por câmera nem da atuação pelo Arduino.

## Reprodutibilidade

Com `SUMO_HOME` configurado para a instalação 1.28.0:

```powershell
python simulation/sumo/run_experiment.py --seeds {','.join(map(str, seeds))} --min-green {settings.minimum_green_seconds:g} --max-green {settings.maximum_green_seconds:g} --max-wait {settings.maximum_wait_seconds:g}
```

Os dados por execução ficam em `reports/experiment_runs.csv`; os dados por veículo e as séries temporais ficam em `output/experiments/`.
"""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Compara os controles fixo e adaptativo no SUMO.')
    parser.add_argument('--seeds', default=','.join(map(str, DEFAULT_SEEDS)), help='sementes separadas por vírgula')
    parser.add_argument('--min-green', type=float, default=8.0)
    parser.add_argument('--max-green', type=float, default=20.0)
    parser.add_argument('--max-wait', type=float, default=30.0)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    seeds = tuple(int(value.strip()) for value in arguments.seeds.split(',') if value.strip())
    if not seeds:
        raise ValueError('Informe pelo menos uma semente')
    settings = AdaptiveSettings(arguments.min_green, arguments.max_green, arguments.max_wait)
    runs = []

    RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for seed in seeds:
        for mode in ('fixed', 'adaptive'):
            print(f'Executando modo={mode}, semente={seed}...')
            observer = RunObserver()
            tripinfo_path = RAW_DIRECTORY / f'tripinfo_{mode}_seed_{seed}.xml'
            run(
                use_gui=False,
                rebuild_network=False,
                delay_ms=0,
                mode=mode,
                adaptive_settings=settings,
                seed=seed,
                tripinfo_output=tripinfo_path,
                observer=observer,
                verbose=False,
                simulation_end_seconds=360.0,
            )
            vehicles = parse_tripinfo(tripinfo_path)
            runs.append(summarize_run(mode, seed, observer, vehicles))
            write_csv(RAW_DIRECTORY / f'timeseries_{mode}_seed_{seed}.csv', observer.rows)
            write_csv(RAW_DIRECTORY / f'vehicles_{mode}_seed_{seed}.csv', vehicles)

    write_csv(REPORT_DIRECTORY / 'experiment_runs.csv', runs)
    report = generate_report(runs, seeds, settings)
    report_path = REPORT_DIRECTORY / 'adaptive_vs_fixed.md'
    report_path.write_text(report, encoding='utf-8')
    metadata = {
        'seeds': seeds,
        'adaptive_settings': settings.__dict__,
        'runs': runs,
    }
    (RAW_DIRECTORY / 'experiment.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f'Relatório gerado em: {report_path}')


if __name__ == '__main__':
    main()
