"""Amostragem e envio HTTP em threads próprias, com fila durável SQLite."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
from urllib import request, error, parse
from uuid import uuid4

BASE = Path(__file__).resolve().parent


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


@dataclass(frozen=True)
class IngestionConfig:
    enabled: bool = False
    api_url: str = 'http://127.0.0.1:3000/api/v1'
    ingestion_key: str = field(default='', repr=False)
    camera_id: str = ''
    camera_b_id: str = ''
    arduino_id: str = ''
    computer_id: str = ''
    signal_a_id: str = ''
    signal_b_id: str = ''
    reading_interval: float = 1.5
    telemetry_interval: float = 15
    timeout: float = 3
    max_attempts: int = 8
    max_queue: int = 50000
    queue_path: str = str(BASE / 'data' / 'ingestion.sqlite3')

    def __post_init__(self):
        if not self.enabled:
            return
        url = parse.urlsplit(self.api_url)
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username
                or url.password or url.query or url.fragment):
            raise ValueError('URL da API inválida; não inclua credenciais na URL.')
        if url.scheme == 'http' and url.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('Use HTTPS para API fora da máquina local.')
        if len(self.ingestion_key) < 32 or not self.camera_id:
            raise ValueError('Configure chave de ingestão e ID da câmera cadastrada.')
        if self.camera_b_id and self.camera_b_id == self.camera_id:
            raise ValueError('As câmeras A e B devem ter IDs diferentes.')
        for name in ('camera_id', 'camera_b_id', 'arduino_id', 'computer_id', 'signal_a_id', 'signal_b_id'):
            value = getattr(self, name)
            if value and (not isinstance(value, str) or not value.isascii()
                          or not value.isdigit() or int(value) <= 0):
                raise ValueError(f'{name} deve ser um ID positivo em texto.')
        if bool(self.signal_a_id) != bool(self.signal_b_id) or (self.signal_a_id and self.signal_a_id == self.signal_b_id):
            raise ValueError('Configure IDs distintos para os dois semáforos.')
        if (self.reading_interval < 1.5 or self.telemetry_interval < 10
                or not 0 < self.timeout <= 10 or self.max_attempts < 1 or self.max_queue < 1):
            raise ValueError('Intervalos, timeout ou limites de fila inválidos.')

    @classmethod
    def load(cls, path=BASE / 'ingestion.local.json'):
        if not Path(path).exists():
            return cls()
        return cls(**json.loads(Path(path).read_text(encoding='utf-8-sig')))


class Outbox:
    def __init__(self, config, initialize=True):
        self.config = config
        Path(config.queue_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(config.queue_path, timeout=1)
        self.db.row_factory = sqlite3.Row
        if not initialize:
            return
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, stream TEXT NOT NULL, route TEXT NOT NULL,
                payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                next_at REAL NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'pending',
                failure TEXT);
            CREATE INDEX IF NOT EXISTS stream_order ON events(stream, id);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        target = config.api_url.rstrip('/')
        previous = self.get('destination')
        if previous and previous != target:
            self.db.close()
            raise ValueError('Fila pertence a outra API; use outro queue_path.')
        with self.db:
            self.set('destination', target)

    def get(self, key):
        row = self.db.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
        return row[0] if row else None

    def set(self, key, value):
        self.db.execute('INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))

    def enqueue(self, stream, route, payload, marker=None):
        with self.db:
            if marker and self.get(marker[0]) == marker[1]:
                return False
            if self.db.execute('SELECT count(*) FROM events').fetchone()[0] >= self.config.max_queue:
                raise RuntimeError('Fila cheia; coleta de novas amostras suspensa até liberar espaço.')
            self.db.execute('INSERT INTO events(stream,route,payload) VALUES (?,?,?)',
                            (stream, route, json.dumps(payload, separators=(',', ':'))))
            if marker:
                self.set(*marker)
        return True

    def next(self, now):
        # Uma falha não permite que fases posteriores ultrapassem a fase pendente.
        return self.db.execute('''SELECT * FROM events e WHERE state='pending' AND next_at<=?
            AND NOT EXISTS (SELECT 1 FROM events older WHERE older.stream=e.stream AND older.id<e.id)
            ORDER BY id LIMIT 1''', (now,)).fetchone()

    def acknowledge(self, event_id):
        with self.db:
            self.db.execute('DELETE FROM events WHERE id=?', (event_id,))

    def fail(self, event, reason, retryable, now):
        attempts = event['attempts'] + 1
        state = 'pending' if retryable and attempts < self.config.max_attempts else 'paused'
        with self.db:
            self.db.execute('UPDATE events SET attempts=?,next_at=?,state=?,failure=? WHERE id=?',
                            (attempts, now + min(60, 2 ** min(attempts, 6)), state, reason, event['id']))

    def counts(self):
        return dict(self.db.execute('SELECT state,count(*) FROM events GROUP BY state').fetchall())

    def retry_paused(self):
        with self.db:
            self.db.execute("UPDATE events SET state='pending',attempts=0,next_at=0,failure=NULL WHERE state='paused'")

    def close(self):
        self.db.close()


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Não encaminha a chave para outro destino em um redirect.


def post(config, route, payload):
    req = request.Request(config.api_url.rstrip('/') + route, data=payload.encode('utf-8'),
                          headers={'Content-Type': 'application/json', 'x-ingestion-key': config.ingestion_key},
                          method='POST')
    with request.build_opener(NoRedirect()).open(req, timeout=config.timeout) as response:
        if not 200 <= response.status < 300:
            raise error.HTTPError(req.full_url, response.status, '', {}, None)


class IngestionClient:
    def __init__(self, config, snapshot, sender=post):
        self.config = config
        self.source = snapshot
        self.sender = sender
        self._stop = threading.Event()
        self._threads = []
        self._lock = threading.Lock()
        self._status = {'habilitada': config.enabled, 'pendentes': 0, 'pausados': 0,
                        'ultimo_envio': None, 'erro': None}
        self._next_reading = {'A': 0, 'B': 0}
        self._next_telemetry = 0
        self._phase_keys = {}

    def status(self):
        with self._lock:
            return dict(self._status)

    def update_status(self, **values):
        with self._lock:
            self._status.update(values)

    def sample(self, outbox, data, now, stamp):
        c = self.config
        lanes = data.get('vias')
        if not isinstance(lanes, dict):
            road = data.get('via_observada')
            lanes = {road: data} if road in ('A', 'B') else {}
        for road, device in (('A', c.camera_id), ('B', c.camera_b_id)):
            lane = lanes.get(road, {})
            if (device and now >= self._next_reading[road]
                    and lane.get('medicao_valida') and lane.get('registrado_em')):
                payload = {'identificadorEvento': str(uuid4()), 'dispositivoId': device,
                           'via': road, 'registradoEm': datetime.fromisoformat(
                               lane['registrado_em'].replace('Z', '+00:00')).astimezone(timezone.utc).isoformat(timespec='milliseconds'),
                           'tipoLeitura': 'QUADRO', 'origemLeitura': 'VISAO_COMPUTACIONAL',
                           'carrosDetectados': lane['carros'], 'pedestresDetectados': lane['pedestres']}
                outbox.enqueue('reading:' + device, '/leituras', payload,
                               ('reading:' + device, payload['registradoEm']))
                self._next_reading[road] = now + c.reading_interval
        if c.signal_a_id:
            known = data.get('arduino_conectado') is True
            mode = ('MANUAL' if data.get('modo_arduino') == 'MANUAL' else
                    'FIXO' if data.get('modo_arduino') == 'FALLBACK' or data.get('estrategia') == 'ciclo_fixo'
                    else 'ADAPTATIVO') if known else 'DESCONHECIDO'
            for road, signal in [('A', c.signal_a_id), ('B', c.signal_b_id)]:
                color = data.get('sinais', {}).get(road) if known else None
                key = (color, mode)
                if self._phase_keys.get(road) != key:
                    payload = {'semaforoId': signal, 'cor': color.upper() if color else 'DESCONHECIDA',
                               'inicioEm': stamp, 'origemEstado': 'ARDUINO' if color else 'SISTEMA',
                               'modoOperacao': mode}
                    outbox.enqueue('phase:' + signal, '/historico-fases', payload)
                    self._phase_keys[road] = key
        if now >= self._next_telemetry:
            camera_statuses = []
            for road, device in (('A', c.camera_id), ('B', c.camera_b_id)):
                lane = lanes.get(road, {})
                camera_status = ('ONLINE' if lane.get('medicao_valida') else
                                 'ALERTA' if lane.get('camera') == 'conectada' else 'OFFLINE')
                camera_statuses.append((device, camera_status))
            for device, status in [*camera_statuses, (c.computer_id, 'ONLINE'),
                                   (c.arduino_id, 'ONLINE' if data.get('arduino_conectado') else 'OFFLINE')]:
                if device:
                    outbox.enqueue('telemetry:' + device, '/telemetria',
                                   {'dispositivoId': device, 'registradoEm': stamp, 'status': status})
            self._next_telemetry = now + c.telemetry_interval

    def deliver_one(self, outbox, now):
        event = outbox.next(now)
        if event is None:
            return
        try:
            self.sender(self.config, event['route'], event['payload'])
        except error.HTTPError as exc:
            # 409 nunca significa sucesso genérico: pode ser conflito real de conteúdo.
            reason = f'HTTP {exc.code} em {event["route"]}'
            outbox.fail(event, reason, exc.code in (408, 425, 429) or exc.code >= 500, now)
            self.update_status(erro=reason)
        except (OSError, error.URLError, TimeoutError):
            outbox.fail(event, 'API indisponível ou timeout', True, now)
            self.update_status(erro='API indisponível ou timeout')
        else:
            outbox.acknowledge(event['id'])
            self.update_status(ultimo_envio=utc_now(), erro=None)

    def _run(self, collecting):
        outbox = None
        try:
            outbox = Outbox(self.config, initialize=False)
            while not self._stop.is_set():
                try:
                    if collecting:
                        self.sample(outbox, self.source(), time.monotonic(), utc_now())
                    else:
                        self.deliver_one(outbox, time.time())
                        counts = outbox.counts()
                        self.update_status(pendentes=counts.get('pending', 0), pausados=counts.get('paused', 0))
                except (sqlite3.Error, RuntimeError):
                    self.update_status(erro='Falha na fila local; verifique espaço e permissões.')
                self._stop.wait(0.2)
        except Exception as exc:
            # Não inclui configurações, resposta HTTP ou segredos em logs/status.
            logging.warning('Ingestão indisponível (%s); confira configuração e fila local.', type(exc).__name__)
            self.update_status(erro='Ingestão indisponível; confira configuração e fila local.')
        finally:
            if outbox:
                outbox.close()

    def start(self):
        if not self.config.enabled:
            return
        if self._threads:
            raise RuntimeError('Cliente de ingestão já iniciado.')
        # Inicializa schema/WAL antes das duas conexões; evita corrida na primeira execução.
        try:
            outbox = Outbox(self.config)
            outbox.close()
        except (sqlite3.Error, OSError, ValueError):
            self.update_status(erro='Não foi possível iniciar a fila local; confira destino e permissões.')
            return
        for collecting in (True, False):
            thread = threading.Thread(target=self._run, args=(collecting,), daemon=True)
            self._threads.append(thread)
            thread.start()

    def stop(self):
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=self.config.timeout + 1)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Inspeciona ou retoma a fila local sem abrir câmera/serial.')
    parser.add_argument('command', choices=['status', 'retry'])
    args = parser.parse_args()
    config = IngestionConfig.load()
    if not config.enabled:
        parser.error('Configure ingestion.local.json antes de usar a fila.')
    outbox = Outbox(config)
    try:
        if args.command == 'retry':
            outbox.retry_paused()
        print(outbox.counts())
    finally:
        outbox.close()
