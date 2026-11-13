# Integração local — Etapa 4

`ingestion.py` coleta snapshots em uma thread e envia HTTP em outra. Captura, detecção e serial nunca esperam pela API. SQLite em `data/ingestion.sqlite3` guarda os eventos antes do envio. Não há acesso direto do Python ao MySQL.

## Configuração

Copie `ingestion.example.json` para `ingestion.local.json`, preencha e habilite `enabled`. O arquivo local e a fila são ignorados pelo Git. Sem configuração, vídeo e sinais funcionam com ingestão desativada. Reinicie o Python após alterar o arquivo.

- `api_url`: endereço base com `/api/v1`. HTTP somente em localhost; use HTTPS fora desta máquina.
- `ingestion_key`: mesma chave do servidor NestJS; nunca colocar no frontend, mobile ou repositório.
- `camera_id`: ID da camera ativa associada a Via A. Nao confundir o ID do banco com o indice OpenCV.
- `camera_b_id`: ID opcional da camera ativa associada a Via B. Deve ser diferente de `camera_id`; configure-o para exportar leituras e telemetria independentes da camera B.
- `computer_id` e `arduino_id`: IDs opcionais dos dispositivos cadastrados, para telemetria.
- `signal_a_id` e `signal_b_id`: IDs dos semáforos A/B. Configure os dois para enviar fases; omita ambos para enviar somente contagens/telemetria.
- `reading_interval`: 1,5 segundo por padrão; mínimo de 1,5 segundo. `telemetry_interval`: 15 segundos por padrão; mínimo de 10.
- `timeout`: 3 segundos por requisição; `max_attempts`: 8 tentativas por evento; `max_queue`: 50 mil eventos.
- `queue_path`: opcional, caminho do arquivo SQLite. Uma fila fica vinculada ao endereço da API; use outro arquivo ao trocar de ambiente.

O utilitario `node scripts/setup-local-ingestion.cjs` (dentro de `api/`) cadastra as duas cameras A/B quando cria uma configuracao nova. Se `ingestion.local.json` ja existir, execute `node scripts/setup-local-ingestion.cjs --add-camera-b`; ele reutiliza/cria o dispositivo B e atualiza somente `camera_b_id`, preservando os demais campos locais.

## Dados enviados

| Recurso | Conteúdo e frequência |
|---|---|
| `/leituras` | Uma leitura valida de cada camera configurada a cada 1,5 s, tipo QUADRO, UUID, camera, via, horario UTC da captura, carros e pessoas |
| `/historico-fases` | Mudanças de cor/modo dos dois sinais, conforme estado recebido do Arduino |
| `/telemetria` | Disponibilidade individual das cameras configuradas, computador e Arduino a cada 15 s |

Nao sao enviados zeros artificiais para uma camera/via sem medicao valida. A estimativa visual de carros parados e usada localmente no controle; nao e persistida como tamanho de fila nem como veiculos unicos.

O horário da fase é o instante em que o coletor observou a mudança, com resolução de coleta de aproximadamente 200 ms, não uma medição elétrica nem o instante exato do LED. Perda do estado serial gera `DESCONHECIDA`, origem `SISTEMA`. O modo informado pela placa e a estratégia local distinguem manual, fixo e adaptativo. Sem resposta serial válida, não se registram cores como confirmadas pelo Arduino.

Ao parar o Python abruptamente, ele não consegue registrar eventos posteriores; uma fase aberta no banco não comprova que a placa ainda está nessa fase. Clientes devem verificar a atualização da telemetria. Reinícios recomeçam a observação e preservam eventos pendentes.

## Falhas e reenvios

- UUID e conteúdo da leitura permanecem iguais em todas as tentativas.
- Atualize também a API desta entrega: fases deduplicam por semáforo/início e telemetria por dispositivo/horário, verificando o conteúdo. Reenvios não reabrem fases antigas nem revertem a saúde atual do dispositivo.
- Timeout, 408, 425, 429 e erros 5xx têm novas tentativas com espera crescente de até 60 s. O remetente verifica a fila a cada 200 ms e envia até cinco eventos por segundo.
- Após 8 tentativas, o evento é pausado. Erros permanentes, inclusive 400/401/403/409, pausam imediatamente. Um conflito 409 não é considerado sucesso.
- Eventos posteriores do mesmo fluxo aguardam o anterior, preservando a ordem das fases. Outros fluxos podem continuar.
- Fila cheia mantém eventos existentes e suspende novas amostras; transições ocorridas enquanto a coleta está suspensa não podem ser reconstruídas. Monitore a fila e o espaço em disco.
- A interface Flask mostra quantidade pendente, pausada, erro e último envio. Segredos e respostas HTTP completas não aparecem nos logs nem no `/status`.

Após corrigir a causa e reiniciar a API, no diretório `computer-vision`:

```powershell
python ingestion.py status
python ingestion.py retry
```

`retry` libera os eventos pausados e antecipa a próxima tentativa dos pendentes, mantendo payloads e IDs. Não apague a fila para tratar indisponibilidade temporária. Execute apenas uma instância da aplicação por câmera/fila.

## Execução e validação

1. Inicie Docker Desktop e, em `database/`, execute `docker compose up -d --wait`.
2. Em `api/`, execute `npm.cmd run start` (após instalar dependências, gerar Prisma e compilar).
3. Em `computer-vision/`, execute `python Teste_camera.py`. Abra localhost:5000 e acompanhe o indicador da API.
4. Com JWT de usuário, consulte `/api/v1/leituras?via=A` e confirme contagens e horário da câmera. A via não observada deve continuar sem leituras dessa câmera.
5. Pare apenas a API: o vídeo e o controle devem continuar; a fila cresce. Reinicie a API e confira o escoamento. Se ultrapassar o limite de tentativas, use `retry`.
6. Confira fases dos dois semáforos e telemetria via API. Testes automatizados de integração usam banco separado cujo nome contém `teste`; nunca inserem dados simulados no banco operacional.

Para validar uma instância Flask que já está rodando sem reiniciá-la, é possível ler seu `/status` em um processo de diagnóstico e entregá-lo ao mesmo cliente de ingestão, sem abrir outra câmera ou serial. Não execute esse diagnóstico simultaneamente com a ingestão interna habilitada.
