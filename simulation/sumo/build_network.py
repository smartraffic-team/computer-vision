"""Compila os arquivos XML básicos para a rede utilizada pela simulação."""

from pathlib import Path
import subprocess

from sumo_tools import find_binary


BASE_DIRECTORY = Path(__file__).resolve().parent
NETWORK_DIRECTORY = BASE_DIRECTORY / 'scenarios' / 'single_intersection' / 'network'
NETWORK_FILE = NETWORK_DIRECTORY / 'smarttraffic.net.xml'
NETWORK_SOURCES = (
    NETWORK_DIRECTORY / 'nodes.nod.xml',
    NETWORK_DIRECTORY / 'edges.edg.xml',
    NETWORK_DIRECTORY / 'connections.con.xml',
    NETWORK_DIRECTORY / 'traffic_lights.tll.xml',
)


def network_needs_rebuild() -> bool:
    if not NETWORK_FILE.exists():
        return True
    network_modified_at = NETWORK_FILE.stat().st_mtime
    return any(source.stat().st_mtime > network_modified_at for source in NETWORK_SOURCES)


def build_network() -> Path:
    command = [
        str(find_binary('netconvert')),
        '--node-files',
        str(NETWORK_SOURCES[0]),
        '--edge-files',
        str(NETWORK_SOURCES[1]),
        '--connection-files',
        str(NETWORK_SOURCES[2]),
        '--tllogic-files',
        str(NETWORK_SOURCES[3]),
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
