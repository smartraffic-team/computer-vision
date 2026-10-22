"""Localização dos executáveis e módulos Python fornecidos pelo SUMO."""

from pathlib import Path
import os
import shutil
import sys


def sumo_home() -> Path:
    raw_path = os.getenv('SUMO_HOME')
    if not raw_path:
        raise RuntimeError(
            'SUMO_HOME não está configurada. Defina a variável com o diretório da instalação do SUMO.'
        )

    path = Path(raw_path).expanduser().resolve()
    if not path.is_dir():
        raise RuntimeError(f'SUMO_HOME não aponta para um diretório válido: {path}')
    return path


def find_binary(name: str) -> Path:
    executable_names = (f'{name}.exe', name) if os.name == 'nt' else (name, f'{name}.exe')

    raw_home = os.getenv('SUMO_HOME')
    if raw_home:
        bin_directory = Path(raw_home).expanduser().resolve() / 'bin'
        for executable_name in executable_names:
            candidate = bin_directory / executable_name
            if candidate.is_file():
                return candidate

    for executable_name in executable_names:
        executable = shutil.which(executable_name)
        if executable:
            return Path(executable).resolve()

    raise RuntimeError(
        f'Executável {name} não encontrado. Configure SUMO_HOME ou adicione a pasta bin do SUMO ao PATH.'
    )


def import_traci():
    try:
        import traci
        return traci
    except ModuleNotFoundError:
        tools_directory = sumo_home() / 'tools'
        if not tools_directory.is_dir():
            raise RuntimeError(f'Pasta de ferramentas do SUMO não encontrada: {tools_directory}')
        sys.path.insert(0, str(tools_directory))
        import traci
        return traci
