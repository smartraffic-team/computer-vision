"""Executa o cenário inicial e exibe as filas virtuais observadas."""

import argparse
from pathlib import Path

from build_network import NETWORK_FILE, build_network
from sumo_tools import find_binary, import_traci


BASE_DIRECTORY = Path(__file__).resolve().parent
SCENARIO_DIRECTORY = BASE_DIRECTORY / 'scenarios' / 'single_intersection'
CONFIGURATION_FILE = SCENARIO_DIRECTORY / 'smarttraffic.sumocfg'
OUTPUT_DIRECTORY = BASE_DIRECTORY / 'output'
DETECTORS = {'A': 'queue_A', 'B': 'queue_B'}


def non_negative_float(raw_value: str) -> float:
    try:
        value = float(raw_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('o atraso deve ser um número') from error
    if value < 0:
        raise argparse.ArgumentTypeError('o atraso não pode ser negativo')
    return value


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Executa o cruzamento virtual do SmartTraffic no SUMO.')
    parser.add_argument('--gui', action='store_true', help='abre a visualização gráfica do SUMO')
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
    return parser.parse_args()


def run(*, use_gui: bool, rebuild_network: bool, delay_ms: float) -> None:
    if rebuild_network or not NETWORK_FILE.exists():
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
    ]
    if use_gui:
        command.extend(['--delay', str(delay_ms)])

    print(f'Iniciando cenário com {binary.name}')
    traci.start(command)
    last_reported_second = -10

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            simulation_time = int(traci.simulation.getTime())
            if simulation_time - last_reported_second < 10:
                continue

            queues = {
                via: traci.lanearea.getLastStepHaltingNumber(detector_id)
                for via, detector_id in DETECTORS.items()
            }
            phase_name = traci.trafficlight.getPhaseName('J0')
            print(
                f't={simulation_time:>3}s | fase={phase_name:<12} | '
                f'fila A={queues["A"]} | fila B={queues["B"]}'
            )
            last_reported_second = simulation_time
    finally:
        traci.close()

    print('Simulação concluída.')


if __name__ == '__main__':
    arguments = parse_arguments()
    run(
        use_gui=arguments.gui,
        rebuild_network=arguments.rebuild_network,
        delay_ms=arguments.delay_ms,
    )
