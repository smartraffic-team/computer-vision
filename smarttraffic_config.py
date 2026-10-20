"""Configuração da aplicação SmartTraffic por variáveis de ambiente."""

from dataclasses import dataclass
import os


def _read_int(name: str, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        value = default
    else:
        try:
            value = int(raw_value)
        except ValueError as error:
            raise ValueError(f'{name} deve ser um número inteiro') from error

    if value < minimum or (maximum is not None and value > maximum):
        interval = f'entre {minimum} e {maximum}' if maximum is not None else f'maior ou igual a {minimum}'
        raise ValueError(f'{name} deve ser {interval}')
    return value


def _read_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        value = default
    else:
        try:
            value = float(raw_value)
        except ValueError as error:
            raise ValueError(f'{name} deve ser um número') from error

    if value < minimum:
        raise ValueError(f'{name} deve ser maior ou igual a {minimum}')
    return value


def _read_origins(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    origins = tuple(origin.strip() for origin in raw_value.split(',') if origin.strip())
    if not origins:
        raise ValueError(f'{name} deve conter ao menos uma origem')
    return origins


@dataclass(frozen=True)
class Settings:
    arduino_port: str
    arduino_baud_rate: int
    arduino_timeout_seconds: float
    switch_to_b_threshold: int
    return_to_a_threshold: int
    camera_index: int
    frame_width: int
    frame_height: int
    frame_rate: int
    detection_frame_skip: int
    jpeg_quality: int
    model_path: str
    inactivity_timeout_seconds: float
    normal_cycle_seconds: float
    secret_key: str
    cors_allowed_origins: tuple[str, ...]
    server_host: str
    server_port: int

    @classmethod
    def from_environment(cls) -> 'Settings':
        settings = cls(
            arduino_port=os.getenv('SMARTTRAFFIC_ARDUINO_PORT', '/dev/ttyUSB0'),
            arduino_baud_rate=_read_int('SMARTTRAFFIC_ARDUINO_BAUD_RATE', 9600, minimum=1),
            arduino_timeout_seconds=_read_float('SMARTTRAFFIC_ARDUINO_TIMEOUT_SECONDS', 1.0, minimum=0.1),
            switch_to_b_threshold=_read_int('SMARTTRAFFIC_SWITCH_TO_B_THRESHOLD', 3),
            return_to_a_threshold=_read_int('SMARTTRAFFIC_RETURN_TO_A_THRESHOLD', 1),
            camera_index=_read_int('SMARTTRAFFIC_CAMERA_INDEX', 1),
            frame_width=_read_int('SMARTTRAFFIC_FRAME_WIDTH', 640, minimum=1),
            frame_height=_read_int('SMARTTRAFFIC_FRAME_HEIGHT', 480, minimum=1),
            frame_rate=_read_int('SMARTTRAFFIC_FRAME_RATE', 30, minimum=1),
            detection_frame_skip=_read_int('SMARTTRAFFIC_DETECTION_FRAME_SKIP', 3, minimum=1),
            jpeg_quality=_read_int('SMARTTRAFFIC_JPEG_QUALITY', 80, minimum=1, maximum=100),
            model_path=os.getenv('SMARTTRAFFIC_MODEL_PATH', 'yolov8n.pt'),
            inactivity_timeout_seconds=_read_float('SMARTTRAFFIC_INACTIVITY_TIMEOUT_SECONDS', 15.0, minimum=0.1),
            normal_cycle_seconds=_read_float('SMARTTRAFFIC_NORMAL_CYCLE_SECONDS', 10.0, minimum=0.1),
            secret_key=os.getenv('SMARTTRAFFIC_SECRET_KEY', 'smarttraffic-local-development'),
            cors_allowed_origins=_read_origins(
                'SMARTTRAFFIC_CORS_ALLOWED_ORIGINS',
                ('http://localhost:5000', 'http://127.0.0.1:5000'),
            ),
            server_host=os.getenv('SMARTTRAFFIC_SERVER_HOST', '127.0.0.1'),
            server_port=_read_int('SMARTTRAFFIC_SERVER_PORT', 5000, minimum=1, maximum=65535),
        )

        if settings.return_to_a_threshold > settings.switch_to_b_threshold:
            raise ValueError(
                'SMARTTRAFFIC_RETURN_TO_A_THRESHOLD não pode ser maior que '
                'SMARTTRAFFIC_SWITCH_TO_B_THRESHOLD'
            )
        if not settings.arduino_port.strip():
            raise ValueError('SMARTTRAFFIC_ARDUINO_PORT não pode ser vazia')
        if not settings.model_path.strip():
            raise ValueError('SMARTTRAFFIC_MODEL_PATH não pode ser vazio')
        if not settings.secret_key:
            raise ValueError('SMARTTRAFFIC_SECRET_KEY não pode ser vazia')
        if not settings.server_host.strip():
            raise ValueError('SMARTTRAFFIC_SERVER_HOST não pode ser vazio')

        return settings


settings = Settings.from_environment()
