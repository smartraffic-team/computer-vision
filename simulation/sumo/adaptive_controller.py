"""Política adaptativa independente do SUMO e de hardware físico."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ApproachState:
    queue_length: int
    oldest_waiting_seconds: float


@dataclass(frozen=True)
class AdaptiveSettings:
    minimum_green_seconds: float = 8.0
    maximum_green_seconds: float = 20.0
    maximum_wait_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.minimum_green_seconds <= 0:
            raise ValueError('O tempo mínimo de verde deve ser positivo')
        if self.maximum_green_seconds < self.minimum_green_seconds:
            raise ValueError('O tempo máximo de verde não pode ser menor que o mínimo')
        if self.maximum_wait_seconds <= 0:
            raise ValueError('O limite de espera deve ser positivo')


@dataclass(frozen=True)
class Decision:
    should_switch: bool
    target: str | None
    reason: str


def decide_next_green(
    *,
    current_green: str,
    green_elapsed_seconds: float,
    approach_a: ApproachState,
    approach_b: ApproachState,
    settings: AdaptiveSettings,
) -> Decision:
    if current_green not in {'A', 'B'}:
        raise ValueError(f'Via verde inválida: {current_green}')

    if green_elapsed_seconds < settings.minimum_green_seconds:
        return Decision(False, None, 'tempo mínimo de verde ainda não cumprido')

    current = approach_a if current_green == 'A' else approach_b
    opposing = approach_b if current_green == 'A' else approach_a
    target = 'B' if current_green == 'A' else 'A'

    if opposing.queue_length == 0:
        return Decision(False, None, 'via oposta sem veículos aguardando')

    if opposing.oldest_waiting_seconds >= settings.maximum_wait_seconds:
        return Decision(True, target, 'limite de espera da via oposta atingido')

    if green_elapsed_seconds >= settings.maximum_green_seconds:
        return Decision(True, target, 'tempo máximo de verde atingido')

    if opposing.queue_length > current.queue_length:
        return Decision(
            True,
            target,
            f'fila oposta maior ({opposing.queue_length} > {current.queue_length})',
        )

    if (
        opposing.queue_length == current.queue_length
        and opposing.oldest_waiting_seconds > current.oldest_waiting_seconds
    ):
        return Decision(True, target, 'empate resolvido pelo veículo mais antigo')

    return Decision(False, None, 'verde atual mantido pela demanda observada')
