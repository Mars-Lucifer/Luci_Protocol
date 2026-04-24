# Luci Protocol Server

Серверная часть теперь состоит из трех файлов и не зависит от кода в `Mobile`.

## Что делает каждый файл

### `crypto.py`

- Реализует внутреннюю криптографию поверх `ECDH + HKDF + AES-GCM`.
- Дает 2 режима работы:
  - `SESSION_INFO` для основного VPN-туннеля клиент <-> сервер.
  - `BOOTSTRAP_INFO` для первичного sealed token в `POST /connect/max`.
- Хранит токен клиента в `SecureTokenVault` только в зашифрованном виде.
- Умеет переупаковывать токен при ротации ключей каждые 5 минут без повторного `POST`.

### `vpn.py`

- Реализует многопользовательскую серверную сессию `MaxVpnSession`.
- На каждого клиента поднимает минимум 3 потока:
  - транспортный поток с `MAX websocket`,
  - поток обработки интернет-запросов,
  - поток ротации ключей.
- Делит полезную нагрузку на части под лимит `max_message_size`, собирает обратно по `message_id`, `start`, `end`.
- Читает только пакеты с тегом `[0]`, а ответы отправляет с тегом `[1]`.
- После чтения сообщения из MAX пытается удалить его через `MAX_DELETE_OPCODE`.
- Расшифровывает запрос, выполняет HTTP/HTTPS обращение к целевому ресурсу, упаковывает полный ответ и отправляет его клиенту обратно.

### `server.py`

- Поднимает HTTP API.
- Инициализирует `POST /connect/max`.
- Принимает первичное рукопожатие от клиента, расшифровывает sealed token, создает изолированную сессию на клиента и возвращает серверный публичный ключ для основного туннеля.
- Хранит bootstrap-ключ для начальной передачи токена.
- Умеет вернуть bootstrap public key через `POST /connect/max` с телом `{"action":"bootstrap"}`.

## Конфиг сервера

Сервер читает `.env` из `server/.env` или из корня проекта. Токен здесь не хранится: его обязан присылать клиент в `sealed_token`.

### Обязательные или практически обязательные переменные

- `MAX_WS_URI`
  - Адрес websocket MAX.
  - Пример: `wss://ws-api.oneme.ru/websocket`
- `MAX_ORIGIN`
  - Origin для подключения.
  - Пример: `https://web.max.ru`
- `MAX_USER_AGENT`
  - User-Agent для websocket авторизации.
  - Пример: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36`
- `SERVER_HANDSHAKE_PRIVATE_KEY_PATH`
  - Путь до PEM-файла с приватным bootstrap-ключом.
  - Это лучший вариант для продакшена.

### Дополнительные переменные

- `SERVER_HOST`
  - Хост API.
  - По умолчанию: `0.0.0.0`
- `SERVER_PORT`
  - Порт API.
  - По умолчанию: `8080`
- `MAX_MESSAGE_SIZE`
  - Максимальная длина одного сообщения в MAX.
  - По умолчанию: `4000`
- `MAX_DELETE_OPCODE`
  - Opcode удаления прочитанных сообщений.
  - По умолчанию: `68`
  - Если ваш клиент MAX работает с другим opcode, поменяйте его здесь.
- `MAX_HEARTBEAT_INTERVAL`
  - Интервал heartbeat websocket.
  - По умолчанию: `20`
- `VPN_ROTATION_INTERVAL`
  - Интервал ротации ключей в секундах.
  - По умолчанию: `300`
- `VPN_REQUEST_TIMEOUT`
  - Таймаут интернет-запроса на стороне сервера.
  - По умолчанию: `30`
- `VPN_CONNECT_TIMEOUT`
  - Сколько ждать готовности MAX websocket после `POST /connect/max`.
  - По умолчанию: `15`
- `SERVER_HANDSHAKE_PRIVATE_KEY_B64`
  - Bootstrap private key в base64, если не хотите хранить путь.
- `SERVER_HANDSHAKE_PRIVATE_KEY_PEM`
  - PEM ключ прямо в env.

### Что клиент обязан прислать сам

- `token`
  - Только внутри `sealed_token`, никогда не хранится в `.env`.
- `device_id`
  - У каждого клиента свой.
- `chat_id`
  - MAX чат, через который идет туннель.
- `client_id`
  - Идентификатор клиента в вашей системе.
- `client_public_key`
  - Публичный ключ клиента для session ECDH.

## Формат `POST /connect/max`

### Bootstrap-запрос

Этот режим нужен, если клиенту нужно сначала получить публичный bootstrap-ключ сервера.

```json
{
  "action": "bootstrap"
}
```

Ответ:

```json
{
  "bootstrap_public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n",
  "defaults": {
    "max_message_size": 4000,
    "rotation_interval_seconds": 300,
    "inbound_tag": "[0]",
    "outbound_tag": "[1]"
  }
}
```

### Основной connect-запрос

```json
{
  "client_id": "android-user-001",
  "device_id": "e5e3c2e1-7d52-47dc-82d6-c7bbf0bab303",
  "chat_id": 123456789,
  "client_public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n",
  "sealed_token": {
    "ephemeral_public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n",
    "ciphertext": "BASE64_AES_GCM_PAYLOAD"
  },
  "max_message_size": 4000,
  "request_timeout_seconds": 30
}
```

Где:

- `client_public_key`
  - Публичный ключ клиента для основного session secret.
- `sealed_token.ephemeral_public_key`
  - Одноразовый ключ клиента для шифрования токена bootstrap-ключом сервера.
- `sealed_token.ciphertext`
  - Зашифрованный токен MAX.

Ответ:

```json
{
  "session_id": "4ab1f90e3e9740b9",
  "server_public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n",
  "key_version": 1,
  "rotation_interval_seconds": 300,
  "request_timeout_seconds": 30,
  "tunnel": {
    "client_tag": "[0]",
    "server_tag": "[1]",
    "max_message_size": 4000
  }
}
```

## Формат пакетов внутри MAX

Текст каждого сообщения начинается с тега:

- `[0]` для клиента -> сервера
- `[1]` для сервера -> клиента

После тега идет компактный JSON-envelope:

```json
{
  "s": "session_id",
  "m": "message_id",
  "k": 1,
  "i": 0,
  "t": 3,
  "b": 1,
  "e": 0,
  "p": "BASE64_CHUNK"
}
```

Где:

- `m` связывает все куски одного сообщения.
- `i` и `t` отвечают за порядок и общее число частей.
- `b` и `e` обозначают начало и конец цепочки.
- `k` это версия ключа.
- `p` это кусок уже зашифрованной полезной нагрузки.

Полезная нагрузка после расшифровки сейчас ожидается в JSON-виде:

```json
{
  "type": "http_request",
  "request_id": "req-001",
  "method": "GET",
  "url": "https://example.org/",
  "headers": {
    "Accept": "text/html"
  },
  "body": ""
}
```

Ответ сервера:

```json
{
  "type": "http_response",
  "request_id": "req-001",
  "ok": true,
  "status": 200,
  "reason": "OK",
  "url": "https://example.org/",
  "headers": {
    "Content-Type": "text/html; charset=UTF-8"
  },
  "body": "BASE64_RESPONSE_BODY"
}
```

## Запуск сервера

### 1. Подготовить Python

Нужен Python 3.10+ и пакеты:

```powershell
pip install cryptography websockets
```

### 2. Подготовить bootstrap private key

Если хотите увидеть публичный ключ для клиента:

```powershell
python server/server.py --print-bootstrap-public-key
```

Если `SERVER_HANDSHAKE_PRIVATE_KEY_*` не задан, сервер сгенерирует временный ключ только на текущий процесс. Для постоянной работы лучше сохранить PEM и передать путь через `SERVER_HANDSHAKE_PRIVATE_KEY_PATH`.

### 3. Заполнить `.env`

Пример:

```env
SERVER_HOST=0.0.0.0
SERVER_PORT=8080
MAX_WS_URI=wss://ws-api.oneme.ru/websocket
MAX_ORIGIN=https://web.max.ru
MAX_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36
MAX_MESSAGE_SIZE=4000
MAX_DELETE_OPCODE=68
VPN_ROTATION_INTERVAL=300
VPN_REQUEST_TIMEOUT=30
VPN_CONNECT_TIMEOUT=15
SERVER_HANDSHAKE_PRIVATE_KEY_PATH=C:\path\to\bootstrap_private_key.pem
```

### 4. Запустить API

Из корня проекта:

```powershell
python server/server.py
```

После старта сервер выведет:

- адрес API,
- подсказку по `POST /connect/max`,
- bootstrap public key.

## Как тестировать связку сервер + клиент

### Сервер

1. Поднимите `python server/server.py`.
2. Проверьте bootstrap:

```powershell
curl -Method Post -Uri http://127.0.0.1:8080/connect/max -ContentType "application/json" -Body '{"action":"bootstrap"}'
```

3. Убедитесь, что клиент умеет:
   - получить bootstrap public key,
   - зашифровать `token` в `sealed_token`,
   - отправить основной connect-запрос,
   - после ответа использовать `server_public_key` для session key.

### Клиент Android (`Mobile`)

Код `Mobile` не менялся. По текущей структуре это Android Gradle проект.

Запуск:

```powershell
cd Mobile
.\gradlew.bat installDebug
```

Либо открыть папку `Mobile` в Android Studio и запустить модуль `app` на устройстве/эмуляторе.

Что нужно клиенту для теста:

1. Адрес HTTP API сервера, например `http://<server-ip>:8080/connect/max`.
2. Bootstrap public key сервера.
3. `token`, `device_id`, `chat_id`.
4. Локальный клиентский ECDH ключ для `client_public_key`.
5. Обработка MAX-туннеля:
   - отправка сообщений с `[0]`,
   - прием `[1]`,
   - сборка частей по `message_id`,
   - обновление ключей по control-пакетам каждые 5 минут.

## Важные замечания

- Токен теперь не должен жить в конфиге сервера.
- У каждого клиента отдельная сессия, отдельный ключ и отдельная ротация.
- Ротация делается через websocket-туннель, не через повторный `POST`.
- `MAX_DELETE_OPCODE` оставлен конфигурируемым, потому что внутренний API MAX может меняться.
