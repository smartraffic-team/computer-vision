"""Compila os arquivos XML básicos para a rede utilizada pela simulação."""

from pathlib import Path
import subprocess

from sumo_tools import find_binary


BASE_DIRECTORY = Path(__file__).resolve().parent
NETWORK_DIRECTORY = BASE_DIRECTORY / 'scenarios' / 'single_intersection' / 'network'
NETWORK_FILE = NETWORK_DIRECTORY / 'smarttraffic.net.xml'


def build_network() -> Path:
    command = [
        str(find_binary('netconvert')),
        '--node-files',
        str(NETWORK_DIRECTORY / 'nodes.nod.xml'),
        '--edge-files',
        str(NETWORK_DIRECTORY / 'edges.edg.xml'),
        '--connection-files',
        str(NETWORK_DIRECTORY / 'connections.con.xml'),
        '--tllogic-files',
        str(NETWORK_DIRECTORY / 'traffic_lights.tll.xml'),
        '--output-file',
        str(NETWORK_FILE),
        '--no-turnarounds',
        'true',
    ]
    subprocess.run(command, check=True)
    return NETWORK_FILE


if __name__ == '__main__':
    generated_file = build_network()
    print(f'Rede SUMO gerada: {generated_file}')
