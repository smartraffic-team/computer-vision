"""Executa o cenário inicial e exibe as filas virtuais observadas."""

import argparse
from pathlib import Path

from adaptive_controller import AdaptiveSettings, ApproachState, decide_next_green
from build_network import build_network, network_needs_rebuild
from sumo_tools import find_binary, import_traci


BASE_DIRECTORY = Path(__file__).resolve().parent
SCENARIO_DIRECTORY = BASE_DIRECTORY / 'scenarios' / 'single_intersection'
CONFIGURATION_FILE = SCENARIO_DIRECTORY / 'smarttraffic.sumocfg'
OUTPUT_DIRECTORY = BASE_DIRECTORY / 'output'
DETECTORS = {
    'A': ('queue_A_0', 'queue_A_1'),
    'B': ('queue_B_0', 'queue_B_1'),
}
TRAFFIC_LIGHT_ID = 'J0'
PROGRAMS = {
    'fixed': 'safe_fixed_cycle',
    'adaptive': 'safe_adaptive',
}
GREEN_PHASES = {
    'A_GREEN': 'A',
    'B_GREEN': 'B',
}
YELLOW_PHASE_INDEX = {
    'A': 1,
    'B': 4,
}


def non_negative_float(raw_value: str) -> float:
    try:
        value = float(raw_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('o atraso deve ser um número') from error
    if value < 0:
        raise argparse.ArgumentTypeError('o atraso não pode ser negativo')
    return value


def positive_float(raw_value: str) -> float:
    value = non_negative_float(raw_value)
    if value == 0:
        raise argparse.ArgumentTypeError('o valor deve ser maior que zero')
    return value


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Executa o cruzamento virtual do SmartTraffic no SUMO.')
    parser.add_argument('--gui', action='store_true', help='abre a visualização gráfica do SUMO')
    parser.add_argument(
        '--mode',
        choices=tuple(PROGRAMS),
        default='adaptive',
        help='política semafórica utilizada (padrão: adaptive)',
    )
    parser.add_argument(
        '--delay-ms',
        type=non_negative_float,
        default=200.0,
        help='atraso entre passos no modo gráfico, em milissegundos (padrão: 200)',
    )
    parser.add_argument(
        '--rebuild-network',
        action='store_true',
        help='recompila a rede antes da execução',
    )
    parser.add_argument('--min-green', type=positive_float, default=8.0, help='verde mínimo adaptativo em segundos')
    parser.add_argument('--max-green', type=positive_float, default=20.0, help='verde máximo adaptativo em segundos')
    parser.add_argument('--max-wait', type=positive_float, default=30.0, help='espera máxima adaptativa em segundos')
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='semente aleatória do SUMO para reproduzir a execução (padrão: 42)',
    )
    return parser.parse_args()


def read_approach_states(traci, simulation_time: float, arrival_times):
    queues_by_lane = {}
    approach_states = {}

    for via, detector_ids in DETECTORS.items():
        vehicle_ids_by_lane = tuple(
            tuple(traci.lanearea.getLastStepVehicleIDs(detector_id))
            for detector_id in detector_ids
        )
        present_vehicle_ids = {
            vehicle_id
            for lane_vehicle_ids in vehicle_ids_by_lane
            for vehicle_id in lane_vehicle_ids
        }
        arrivals = arrival_times[via]
        for vehicle_id in tuple(arrivals):
            if vehicle_id not in present_vehicle_ids:
                del arrivals[vehicle_id]
        for vehicle_id in present_vehicle_ids:
            arrivals.setdefault(vehicle_id, simulation_time)

        halted_ids_by_lane = tuple(
            tuple(
                vehicle_id
                for vehicle_id in lane_vehicle_ids
                if traci.vehicle.getSpeed(vehicle_id) < 0.1
            )
            for lane_vehicle_ids in vehicle_ids_by_lane
        )
        halted_vehicle_ids = {
            vehicle_id
            for lane_vehicle_ids in halted_ids_by_lane
            for vehicle_id in lane_vehicle_ids
        }
        queues_by_lane[via] = tuple(len(ids) for ids in halted_ids_by_lane)
        oldest_waiting = max(
            (simulation_time - arrivals[vehicle_id] for vehicle_id in halted_vehicle_ids),
            default=0.0,
        )
        approach_states[via] = ApproachState(
            queue_length=len(halted_vehicle_ids),
            oldest_waiting_seconds=oldest_waiting,
        )

    return approach_states, queues_by_lane


def run(
    *,
    use_gui: bool,
    rebuild_network: bool,
    delay_ms: float,
    mode: str,
    adaptive_settings: AdaptiveSettings,
    seed: int = 42,
    tripinfo_output: Path | None = None,
    observer=None,
    verbose: bool = True,
    simulation_end_seconds: float | None = None,
) -> None:
    if rebuild_network or network_needs_rebuild():
        build_network()

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    traci = import_traci()
    binary = find_binary('sumo-gui' if use_gui else 'sumo')
    command = [
        str(binary),
        '--configuration-file',
        str(CONFIGURATION_FILE),
        '--start',
        '--quit-on-end',
        '--seed',
        str(seed),
    ]
    if tripinfo_output is not None:
        tripinfo_output.parent.mkdir(parents=True, exist_ok=True)
        command.extend(['--tripinfo-output', str(tripinfo_output)])
    if use_gui:
        command.extend(['--delay', str(delay_ms)])

    if verbose:
        print(f'Iniciando cenário com {binary.name} no modo {mode} (semente {seed})')
    traci.start(command)
    last_reported_second = -10
    arrival_times = {'A': {}, 'B': {}}
    current_green = None
    green_started_at = 0.0

    try:
        traci.trafficlight.setProgram(TRAFFIC_LIGHT_ID, PROGRAMS[mode])
        traci.trafficlight.setPhase(TRAFFIC_LIGHT_ID, 0)

        while (
            traci.simulation.getTime() < simulation_end_seconds
            if simulation_end_seconds is not None
            else traci.simulation.getMinExpectedNumber() > 0
        ):
            traci.simulationStep()
            simulation_time = traci.simulation.getTime()
            approach_states, queues_by_lane = read_approach_states(
                traci,
                simulation_time,
                arrival_times,
            )
            phase_name = traci.trafficlight.getPhaseName(TRAFFIC_LIGHT_ID)
            active_green = GREEN_PHASES.get(phase_name)

            if active_green is not None and active_green != current_green:
                current_green = active_green
                green_started_at = simulation_time

            if mode == 'adaptive' and active_green is not None:
                decision = decide_next_green(
                    current_green=active_green,
                    green_elapsed_seconds=simulation_time - green_started_at,
                    approach_a=approach_states['A'],
                    approach_b=approach_states['B'],
                    settings=adaptive_settings,
                )
                if decision.should_switch:
                    traci.trafficlight.setPhase(
                        TRAFFIC_LIGHT_ID,
                        YELLOW_PHASE_INDEX[active_green],
                    )
                    if verbose:
                        print(
                            f't={simulation_time:>3.0f}s | decisão: {active_green} -> '
                            f'{decision.target} | {decision.reason}'
                        )
                    phase_name = traci.trafficlight.getPhaseName(TRAFFIC_LIGHT_ID)
                    current_green = None

            if observer is not None:
                observer(
                    traci=traci,
                    simulation_time=simulation_time,
                    approach_states=approach_states,
                    queues_by_lane=queues_by_lane,
                    phase_name=phase_name,
                )

            if not verbose or simulation_time - last_reported_second < 10:
                continue

            print(
                f't={simulation_time:>3.0f}s | fase={phase_name:<12} | '
                f'fila A={approach_states["A"].queue_length} {queues_by_lane["A"]} '
                f'espera={approach_states["A"].oldest_waiting_seconds:.0f}s | '
                f'fila B={approach_states["B"].queue_length} {queues_by_lane["B"]} '
                f'espera={approach_states["B"].oldest_waiting_seconds:.0f}s'
            )
            last_reported_second = simulation_time
    finally:
        traci.close()

    if verbose:
        print('Simulação concluída.')


if __name__ == '__main__':
    arguments = parse_arguments()
    policy = AdaptiveSettings(
        minimum_green_seconds=arguments.min_green,
        maximum_green_seconds=arguments.max_green,
        maximum_wait_seconds=arguments.max_wait,
    )
    run(
        use_gui=arguments.gui,
        rebuild_network=arguments.rebuild_network,
        delay_ms=arguments.delay_ms,
        mode=arguments.mode,
        adaptive_settings=policy,
        seed=arguments.seed,
    )
