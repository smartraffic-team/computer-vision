"""Controle local da maquete; a serial é usada apenas pela thread de controle."""

from collections import deque
import logging
import statistics
import threading
import time


class TrafficController:
    # Valores em segundos, compatíveis com os limites do firmware ST1.
    MIN_GREEN = 8
    MAX_GREEN = 25
    FIXED_GREEN = 12
    FILTER_WINDOW = 2
    SERIAL_TIMEOUT = 2
    PHASES = {'A_GREEN', 'A_YELLOW', 'B_GREEN', 'B_YELLOW', 'ALL_RED'}

    def __init__(self, port, measurement, observed_road='A', clock=time.monotonic):
        self.port = port
        self.measurement = measurement
        self.observed_road = observed_road
        self.clock = clock
        self.arduino = None
        self.mode = 'automatico'
        self.error = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._state = None
        self._received_at = None
        self._pending = None
        self._requested = None
        self._sequence = 0
        self._last_sent = -float('inf')
        self._buffer = bytearray()
        self._samples = deque()
        self._sample_id = None
        self._filtered = None
        self._strategy = 'ciclo_fixo'
        self._durations = (12, 12)
        self._notice = None

    def connect(self):
        if not self.port:
            logging.info('Arduino não configurado; vídeo e contagens continuam.')
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name='traffic-control')
        self._thread.start()

    def _healthy(self, now):
        return (self._state is not None and self._received_at is not None
                and now - self._received_at <= self.SERIAL_TIMEOUT and not self.error)

    def _plan(self, measurement, now):
        valid = (measurement.get('medicao_valida') is True
                 and measurement.get('via_observada') == self.observed_road
                 and type(measurement.get('carros')) is int and measurement['carros'] >= 0)
        if not valid:
            self._samples.clear()
            self._sample_id = None
            self._filtered = None
            self._strategy = 'ciclo_fixo'
            self._durations = (self.FIXED_GREEN, self.FIXED_GREEN)
            return
        stamp = measurement.get('registrado_em')
        if stamp is not None and stamp != self._sample_id:
            self._samples.append((now, measurement['carros']))
            self._sample_id = stamp
        while self._samples and now - self._samples[0][0] > self.FILTER_WINDOW:
            self._samples.popleft()
        if not self._samples:
            self._filtered = None
            self._strategy = 'ciclo_fixo'
            self._durations = (self.FIXED_GREEN, self.FIXED_GREEN)
            return
        self._filtered = statistics.median(value for _, value in self._samples)
        green = min(self.MAX_GREEN, self.MIN_GREEN + 2 * self._filtered)
        self._durations = ((green, self.FIXED_GREEN) if self.observed_road == 'A'
                           else (self.FIXED_GREEN, green))
        self._strategy = 'adaptativo'

    def receive(self, line, now):
        """STATE ST1 seq fase decorrido_ms duracao_ms modo; rejeita outros protocolos."""
        parts = line.split()
        if len(parts) == 4 and parts[:2] == ['ERROR', 'ST1']:
            with self._lock:
                if self._pending and parts[2] == str(self._pending[0]):
                    self._pending = None
                    self._notice = 'Arduino recusou o comando durante a transição; confira o estado e tente novamente.'
            return
        if len(parts) != 8 or parts[:2] != ['STATE', 'ST1']:
            return
        try:
            seq, elapsed, duration = int(parts[2]), int(parts[4]), int(parts[5])
        except ValueError:
            return
        phase, mode, target = parts[3], parts[6], parts[7]
        if (phase not in self.PHASES or mode not in ('AUTO', 'MANUAL', 'FALLBACK')
                or target not in ('A', 'B') or seq < 0 or elapsed < 0
                or not 0 < duration <= self.MAX_GREEN * 1000):
            return
        with self._lock:
            self._state = dict(seq=seq, phase=phase, elapsed=elapsed / 1000,
                               duration=duration / 1000, mode=mode, target=target)
            self._received_at = now
            if self._pending and seq == self._pending[0]:
                self._pending = None

    def _write(self, command, now):
        self._sequence += 1
        wire = command.format(seq=self._sequence).encode('ascii') + b'\n'
        if self.arduino.write(wire) != len(wire):
            raise OSError('Comando serial incompleto.')
        self._pending = (self._sequence, now)
        self._notice = None
        self._last_sent = now

    def tick(self, measurement, now):
        """Uma iteração determinística, também usada nos testes sem hardware."""
        with self._lock:
            self._plan(measurement, now)
            if self._pending and now - self._pending[1] > self.SERIAL_TIMEOUT:
                raise TimeoutError('Arduino não confirmou o comando; reinicie após verificar a serial.')
            if not self._healthy(now):
                return
            if self._pending:
                return
            if self._requested:
                command = self._requested
                self._requested = None
                self._write(command, now)
            elif now - self._last_sent >= 1:
                if self.mode == 'automatico':
                    a, b = (int(value * 1000) for value in self._durations)
                    self._write(f'AUTO {{seq}} {a} {b}', now)
                elif self._state['mode'] != 'MANUAL':
                    if self._state['phase'].endswith('_GREEN'):
                        self._write(f"MANUAL {{seq}} {self._state['target']}", now)
                    else:
                        self._write('KEEP {seq}', now)
                else:
                    self._write('KEEP {seq}', now)

    def _run(self):
        try:
            import serial
            self.arduino = serial.Serial(self.port, 9600, timeout=0, write_timeout=0.5)
            # A abertura pode reiniciar a placa. Aguarda STATE ST1, sem mandar comandos legados.
            started = self.clock()
            while not self._stop.is_set():
                now = self.clock()
                data = self.arduino.read(min(self.arduino.in_waiting, 512))
                self._buffer.extend(data)
                while b'\n' in self._buffer:
                    line, _, rest = self._buffer.partition(b'\n')
                    self._buffer = bytearray(rest)
                    self.receive(line.decode('ascii', errors='replace').strip(), now)
                if len(self._buffer) > 512:
                    raise ValueError('Resposta serial excedeu o limite do protocolo ST1.')
                with self._lock:
                    if self._received_at is None and now - started > 8:
                        raise TimeoutError('Sem resposta ST1. Carregue o novo firmware no Arduino.')
                    if self._received_at is not None and now - self._received_at > self.SERIAL_TIMEOUT:
                        raise TimeoutError('Estado do Arduino expirou; controle indisponível.')
                self.tick(self.measurement(), now)
                self._stop.wait(0.05)
        except Exception as error:
            logging.warning('Controle serial indisponível: %s', error)
            with self._lock:
                self.error = str(error)
        finally:
            if self.arduino:
                self.arduino.close()

    def set_mode(self, mode):
        if mode not in ('manual', 'automatico'):
            return {'ok': False, 'erro': 'Modo deve ser manual ou automatico.'}
        with self._lock:
            if not self._healthy(self.clock()) or self._stop.is_set():
                return {'ok': False, 'erro': 'Arduino sem estado ST1 recente.'}
            if self._requested or self._pending:
                return {'ok': False, 'erro': 'Aguarde a confirmação do comando atual.'}
            self.mode = mode
            self._last_sent = -float('inf')
            return {'ok': True}

    def request_change(self, via):
        with self._lock:
            if via not in ('A', 'B'):
                return {'ok': False, 'erro': 'Selecione a Via A ou B.'}
            if self.mode != 'manual':
                return {'ok': False, 'erro': 'Selecione o modo manual primeiro.'}
            if not self._healthy(self.clock()) or self._stop.is_set():
                return {'ok': False, 'erro': 'Arduino sem estado ST1 recente.'}
            if (self._pending or self._requested or not self._state['phase'].endswith('_GREEN')
                    or self._state['target'] != self._state['phase'][0]):
                return {'ok': False, 'erro': 'Aguarde a confirmação/transição atual.'}
            self._requested = f'MANUAL {{seq}} {via}'
            return {'ok': True}

    def snapshot(self):
        with self._lock:
            now = self.clock()
            healthy = self._healthy(now) and not self._stop.is_set()
            state = self._state if healthy else None
            phase = state['phase'] if state else None
            signals = {'A': None, 'B': None}
            if state:
                signals = {'A': 'vermelho', 'B': 'vermelho'}
                if phase != 'ALL_RED':
                    signals[phase[0]] = 'verde' if phase.endswith('_GREEN') else 'amarelo'
            remaining = max(0, state['duration'] - state['elapsed'] - (now - self._received_at)) if state else None
            return {
                'modo': self.mode, 'modo_arduino': state['mode'] if state else None,
                'estrategia': self._strategy, 'carros_filtrados': self._filtered,
                'arduino_conectado': healthy, 'erro_controle': self.error,
                'aviso_controle': self._notice,
                'fase': phase, 'sinais': signals,
                'semaforo': phase[0] if phase and phase.endswith('_GREEN') else None,
                'em_transicao': bool(state and (not phase.endswith('_GREEN') or state['target'] != phase[0])),
                'comando_pendente': bool(self._pending or self._requested),
                'tempo_restante': round(remaining, 1) if remaining is not None else None,
                'verdes_planejados': dict(zip(('A', 'B'), self._durations)),
            }

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        # Sem heartbeat, o firmware passa ao ciclo fixo por watchdog.
