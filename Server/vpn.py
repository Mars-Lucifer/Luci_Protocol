import asyncio
import websockets
import json
import base64
import time


class VpnTunnelNode:
    def __init__(self, role, uri, token, device_id, chat_id=0):
        self.role = role  # 'CLIENT' или 'SERVER'
        self.uri = uri
        self.token = token
        self.device_id = device_id
        self.chat_id = chat_id

        self.crypto = CryptoProtocol()
        self.ws = None
        self.seq_counter = 1000

        # Определяем теги
        self.my_tag = "[C2S]" if role == "CLIENT" else "[S2C]"
        self.peer_tag = "[S2C]" if role == "CLIENT" else "[C2S]"

    async def connect_and_auth(self):
        headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://web.max.ru"}
        self.ws = await websockets.connect(self.uri, additional_headers=headers)

        # Твой этап авторизации
        auth_sequence = [
            {
                "ver": 11,
                "cmd": 0,
                "seq": 0,
                "opcode": 6,
                "payload": {
                    "userAgent": {"deviceType": "WEB"},
                    "deviceId": self.device_id,
                },
            },
            {
                "ver": 11,
                "cmd": 0,
                "seq": 1,
                "opcode": 19,
                "payload": {"token": self.token, "chatsCount": 0, "interactive": True},
            },
        ]
        for packet in auth_sequence:
            await self.ws.send(json.dumps(packet))
            await asyncio.sleep(0.1)

        asyncio.create_task(self.heartbeat())
        asyncio.create_task(self.listener())
        asyncio.create_task(self.key_rotation_task())  # Запуск таймера ротации

    async def heartbeat(self):
        h_seq = 500
        while True:
            try:
                await self.ws.send(
                    json.dumps(
                        {"ver": 11, "cmd": 0, "seq": h_seq, "opcode": 1, "payload": {}}
                    )
                )
                h_seq += 1
                await asyncio.sleep(20)
            except Exception:
                break

    async def send_tunnel_message(self, raw_bytes: bytes, is_control=False):
        """Шифрует и отправляет данные в Избранное"""
        if not self.crypto.aesgcm and not is_control:
            print("❌ Ключи еще не синхронизированы!")
            return

        # Если это не управляющий пакет, шифруем его
        payload_data = raw_bytes if is_control else self.crypto.encrypt(raw_bytes)
        b64_data = base64.b64encode(payload_data).decode()

        # Формат: ТЕГ|TИП|ДАННЫЕ. Тип: 'D' - Data, 'C' - Control
        msg_type = "C" if is_control else "D"
        text_message = f"{self.my_tag}|{msg_type}|{b64_data}"

        packet = {
            "ver": 11,
            "cmd": 0,
            "seq": self.seq_counter,
            "opcode": 64,
            "payload": {
                "chatId": self.chat_id,
                "message": {"text": text_message, "cid": int(time.time() * 1000)},
            },
        }
        self.seq_counter += 1
        await self.ws.send(json.dumps(packet))

    async def delete_message(self, msg_id):
        """Удаляет прочитанное сообщение (нужно найти точный opcode Макса)"""
        # Примерный паттерн, нужно подставить реальный opcode (часто 66 или 68 для удаления)
        packet = {
            "ver": 11,
            "cmd": 0,
            "seq": self.seq_counter,
            "opcode": 68,  # ЗАМЕНИТЬ НА РЕАЛЬНЫЙ
            "payload": {"chatId": self.chat_id, "messageIds": [msg_id]},
        }
        self.seq_counter += 1
        await self.ws.send(json.dumps(packet))

    async def listener(self):
        """Слушает входящие сообщения и фильтрует по тегу"""
        async for message in self.ws:
            data = json.loads(message)
            if data.get("opcode") == 128:  # Новое сообщение
                msg_obj = data.get("payload", {}).get("message", {})
                text = msg_obj.get("text", "")
                msg_id = msg_obj.get("id")

                # Читаем только сообщения с тегом собеседника
                if text.startswith(self.peer_tag):
                    parts = text.split("|")
                    msg_type = parts[1]
                    payload_b64 = parts[2]
                    raw_data = base64.b64decode(payload_b64)

                    if msg_type == "C":  # Управляющий пакет (обмен ключами)
                        self.handle_control_message(raw_data)
                    elif msg_type == "D":  # Данные туннеля
                        decrypted = self.crypto.decrypt(raw_data)
                        print(f"[{self.role}] Получены данные: {len(decrypted)} байт")
                        # Здесь в Android данные пойдут обратно в дескриптор VpnService

                    # Сразу удаляем сообщение, чтобы не оставлять следов
                    if msg_id:
                        await self.delete_message(msg_id)

    def handle_control_message(self, raw_data):
        try:
            ctrl = json.loads(raw_data.decode())
            if ctrl["action"] == "ROTATE_KEY":
                peer_pub = ctrl["public_key"].encode()
                self.crypto.derive_shared_secret(peer_pub)
                print(f"🔑 [{self.role}] Мастер-ключ обновлен!")

                # Если мы сервер и получили запрос от клиента, нужно ответить своим ключом
                if self.role == "SERVER":
                    asyncio.create_task(self.send_rotation_key())
        except Exception as e:
            print(f"Ошибка Control пакета: {e}")

    async def send_rotation_key(self):
        # Генерируем новую пару
        self.crypto = CryptoProtocol()
        pub_bytes = self.crypto.get_public_bytes().decode()
        ctrl_msg = json.dumps(
            {"action": "ROTATE_KEY", "public_key": pub_bytes}
        ).encode()
        await self.send_tunnel_message(ctrl_msg, is_control=True)

    async def key_rotation_task(self):
        """Только клиент инициирует ротацию каждые 5 минут"""
        if self.role != "CLIENT":
            return

        while True:
            await asyncio.sleep(300)  # 5 минут
            print("🔄 Запуск ротации ключей...")
            await self.send_rotation_key()
