# Evidências da Etapa 4 — 10/11/2026

Ambiente: Windows, Python 3.14, Node 24, MySQL 8.4 em Docker Desktop, API NestJS local na porta 3000, Flask na porta 5000. Banco operacional local `smarttraffic`; testes isolados em `smarttraffic_api_teste`. Não houve uso da Aiven nem envio externo de medições.

## Verificações executadas

- 45 testes Python aprovados: captura, validade das contagens, controlador ST1, rotas Flask, fila persistente, reenvio, limite de tentativas, ordem das fases, credenciais, indisponibilidade da API e primeira inicialização concorrente da fila.
- API: build, lint e 4 testes unitários aprovados.
- 6 testes de integração com MySQL separado aprovados, incluindo leituras deduplicadas, reenvio de fases, telemetria concorrente e rejeição de conteúdo conflitante.
- Script oficial `database/scripts/verificar.sh`: schema/seed verificados, dez tabelas, vias A/B e dois semáforos. Nenhuma migração ou `prisma db push` foi necessária.
- Cadastro local pela API: câmera vinculada à Via A, computador e Arduino. IDs dos dois semáforos consultados, sem pressupor IDs fixos.
- Corrigido conflito entre pacotes Python `serial` e `pyserial`: removido `serial` (serializador JSON/XML) e reinstalado `pyserial==3.5`. Após reiniciar o Flask, estados ST1 reais passaram a chegar novamente.

## Fluxo real observado

Primeiro ensaio, lendo o `/status` da instância Flask já aberta: 4 leituras reais da câmera persistidas e consultadas pela API; nenhuma leitura para B. A serial estava indisponível nesse momento, portanto foram enviados estados DESCONHECIDA com origem SISTEMA, não cores fictícias.

Após reiniciar a aplicação com a ingestão interna e o driver corrigido, consulta realizada aproximadamente às 20h29 (America/Sao_Paulo):

| Recurso | Evidência |
|---|---|
| Leituras A | 17 registros reais naquele instante, tipo QUADRO, origem VISAO_COMPUTACIONAL |
| Leituras B | 0 registros — via sem câmera |
| Histórico dos sinais | 26 registros, incluindo fases VERDE, AMARELO e VERMELHO com origem ARDUINO nos dois sinais |
| Telemetria | 27 registros dos dispositivos naquele instante |
| Estado local | Câmera conectada, medição válida, Arduino conectado, fase B_YELLOW e ingestão sem erro/sem eventos pausados |

Os totais aumentam com a aplicação em execução. Contagens por quadro não representam veículos únicos. Os horários das fases representam observação pelo coletor, não medição elétrica.

## Queda da API

Interrompida somente a API local por 8 segundos e reiniciada em seguida. Durante a interrupção, o Flask continuou respondendo: câmera conectada, Arduino conectado, fase B_GREEN; a fila tinha 4 eventos pendentes e indicava timeout/indisponibilidade. Após o retorno, novos envios foram confirmados pela API, sem eventos pausados, mantendo a operação local. Testes automatizados cobrem persistência da fila entre instâncias e preservação do UUID/conteúdo.

## Limites e continuidade

- A validação física dos semáforos/tempos foi relatada pelo usuário. Não foi feita medição elétrica automática dos LEDs.
- Não foi aferida a precisão estatística das detecções nem o desempenho com miniaturas nesta etapa.
- A plataforma web e o mobile ainda precisam de validação própria; esta entrega comprova ingestão e consulta pela API.
- O banco local passou a registrar verde padrão de 12 s e máximo de 25 s, alinhados ao controlador. O seed genérico do repositório continua com seus valores originais; alinhe esses parâmetros ao preparar outro ambiente.
- Credenciais foram geradas aleatoriamente e salvas somente nos arquivos locais ignorados: `api/.env`, `api/.env.local-admin`, `database/.env` e `computer-vision/ingestion.local.json`.
- Após corrigir erro permanente ou esgotar 8 tentativas, use `python ingestion.py retry`. Não apague a fila para tratar indisponibilidade temporária.
