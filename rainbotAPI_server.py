import asyncio
import websockets
import json
from plogging import Plogging
from stats import StatisticsTracker
import inspect
import os
import gzip
import datetime

class WebSocketServer:
    def __init__(self, host='192.168.0.106', port=8765, plogging: Plogging | None = None, stats: StatisticsTracker | None = None):
        self.stats = stats
        self.plogging = Plogging() if plogging is None else plogging
        self.plogging.on_log_message.connect(self._send_new_log_message)
        self.host = host
        self.port = port
        self.server = None
        self.on_connect_callback = None
        self.on_disconnect_callback = None
        self.registered_functions = None
        # Dictionary to keep track of connected clients
        self.clients = {}  # {websocket: {'address': (ip, port), 'connection_type': str}}
        
    

    def register_funcs(self, registered_functions: dict):
        self.registered_functions = registered_functions

    def _send_new_log_message(self):
        new_message = self.plogging.get_last_log_message()
        asyncio.create_task(self.broadcast_packet('new_log_message', new_message, 'gui_client'))

    def on_connect(self, callback):
        """Register a callback for when a client connects."""
        self.on_connect_callback = callback

    def on_disconnect(self, callback):
        """Register a callback for when a client disconnects."""
        self.on_disconnect_callback = callback

    async def execute_func(self, func_string: str, websocket):
        import shlex
        """
        Разбирает строку команды, определяет имя функции и аргументы.
        Поддерживает два вида передачи аргументов:
        
        1. Именованные аргументы в формате:
            --arg="Текст с пробелами"
        2. Позиционные аргументы (без префикса), например:
            /function_name 10 20
        
        В итоге функция вызывается с использованием распаковки:
            func(*positional_args, **keyword_args)
        """
        try:
            # Разбиваем строку с учетом кавычек
            tokens = shlex.split(func_string)
            if not tokens:
                await websocket.send(json.dumps({
                    "type": "response",
                    "message": "Error: command null."
                }))
                return

            # Первый токен — имя функции
            func_name = tokens[0].lstrip('/')
            positional_args = []
            keyword_args = {}

            # Обрабатываем оставшиеся токены
            for token in tokens[1:]:
                # Если токен начинается с '--' и содержит двоеточие, считаем его именованным аргументом
                if token.startswith('--') and '=' in token:
                    # Убираем префикс '--' и разделяем по первому двоеточию
                    arg_key, arg_value = token[2:].split('=', 1)
                    # Если значение состоит только из цифр, преобразуем в int
                    if arg_value.isdigit():
                        arg_value = int(arg_value)
                    keyword_args[arg_key] = arg_value
                else:
                    # Позиционный аргумент
                    if token.isdigit():
                        token = int(token)
                    positional_args.append(token)
        except Exception as e:
            await websocket.send(json.dumps({
                "type": "response",
                "message": f"Error: {e}"
            }))
            return


        if self.registered_functions is None or func_name not in self.registered_functions:
            await websocket.send(json.dumps({
                "type": "response",
                "message": f"Error: Function '{func_name}' not registered."
            }))
            return

        func = self.registered_functions.get(func_name)

        try:
            # Выполнение функции (асинхронная или обычная)
            if inspect.iscoroutinefunction(func):
                result = await func(*positional_args, **keyword_args)
            else:
                result = func(*positional_args, **keyword_args)
            await websocket.send(json.dumps({
                "type": "response",
                "message": "Function executed successfully.",
                "result": result
            }))
        except Exception as e:
            await websocket.send(json.dumps({
                "type": "response",
                "message": f"Error while executing '{func_name}': {e}"
            }))

    async def send_packet(self, websocket, type, message):
        if websocket:
            try:
                response = {
                    "type": type,
                    "message": message
                }
                await websocket.send(json.dumps(response))
            except Exception as e:
                await self.plogging.error(f"Error sending message: {e}")
                
    async def get_registered_functions(self, websocket):
        response = {
            "type": "registered_functions",
            "data": list(self.registered_functions.keys())
        }
        await websocket.send(json.dumps(response))

    async def broadcast_packet(self, type, message, client_type=None):
        """Send a packet to all connected clients, optionally filtering by client type."""
        response = {
            "type": type,
            "message": message
        }
        disconnected_clients = []
        for ws, info in self.clients.items():
            if client_type is None or info['connection_type'] == client_type:
                try:
                    await ws.send(json.dumps(response))
                except Exception as e:
                    await self.plogging.error(f"Error sending message to {info['address']}: {e}")
                    disconnected_clients.append(ws)
        # Remove disconnected clients
        for ws in disconnected_clients:
            await self.remove_client(ws)

    async def remove_client(self, websocket):
        info = self.clients.pop(websocket, None)
        if info:
            await self.plogging.info(f"Client {info['address']} disconnected.")
            if self.on_disconnect_callback:
                self.on_disconnect_callback(info['address'])
            try:
                await websocket.close()
            except:
                pass

    async def get_archived_logs_for_period(self, websocket, days: int):
        """
        Отправляет клиенту заархивированные логи за последние N полных дней + текущий день.
        Пример: если days = 5, то будут отобраны логи за последние 5 полных дней и за сегодня.
        """

        # Текущая дата
        now = datetime.datetime.now()
        # Начальная граница: N дней назад (включая весь сегодняшний день)
        start_date = (now - datetime.timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        # Конечная граница: текущее время
        end_date = now

        # Создадим маппинг "папка -> уровни логирования"
        folder_levels_map = {}
        for level, folder in self.plogging.log_folders.items():
            folder_levels_map.setdefault(folder, []).append(level)

        # Структура для результата: { "debug": [ {"filename": "...", "date": "..."} ], "debug + error": [ ... ] }
        logs_response = {}

        # Формат имени файла архива: "log_dd-mm-YYYY_HH-MM-SS_archive.gz"
        # Нам нужно распарсить дату из имени файла.
        def parse_datetime_from_filename(filename):
            # Ожидается формат: log_dd-mm-YYYY_HH-MM-SS_archive.gz
            try:
                base_name = filename[len("log_"):-len("_archive.gz")]
                # base_name = "19-12-2024_10-30-00"
                date_str, time_str = base_name.split('_')
                day, month, year = date_str.split('-')
                hour, minute, second = time_str.split('-')
                dt = datetime.datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
                return dt
            except Exception:
                return None

        # Обходим все папки
        for folder, levels in folder_levels_map.items():
            if not os.path.exists(folder):
                continue

            # Получаем список архивных файлов
            files = [f for f in os.listdir(folder) if f.endswith("_archive.gz")]

            for f in files:
                file_dt = parse_datetime_from_filename(f)
                if file_dt is None:
                    continue
                # Проверяем попадает ли файл в интервал
                if start_date <= file_dt <= end_date:
                    # Формируем ключ по уровням
                    # Отсортируем уровни для консистентности
                    levels_str = " + ".join(sorted(levels))

                    # Отправляем только имя и дату
                    logs_response.setdefault(levels_str, []).append({
                        "filename": f,
                        "date": file_dt.isoformat(),
                        "folder": folder  # Добавим путь к папке для последующего доступа
                    })

        # Отправляем ответ клиенту
        response = {
            "type": "archived_logs",
            "data": logs_response
        }
        await websocket.send(json.dumps(response))

    async def send_log_file_content(self, websocket, folder, filename):
        """
        Отправляет содержимое указанного лог-файла.
        """
        file_path = os.path.join(folder, filename)
        if not os.path.exists(file_path):
            response = {"type": "error", "message": f"File '{filename}' not found in folder '{folder}'."}
            await websocket.send(json.dumps(response))
            return

        try:
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            response = {"type": "error", "message": f"Error reading file '{filename}': {e}"}
            await websocket.send(json.dumps(response))
            return

        # Отправляем содержимое файла
        response = {
            "type": "log_file_content",
            "filename": filename,
            "content": content
        }
        await websocket.send(json.dumps(response))
        
    async def specificator_function(self, websocket, message):
        """
        Обрабатывает сообщения, начинающиеся с '@'.
        """
        
        if message.startswith('@get_logs'):
            await self.send_packet(websocket=websocket, type='logs', message=self.plogging.get_history())
        elif message.startswith('@get_archived_logs'):
            parts = message.split()
            if len(parts) == 2 and parts[1].isdigit():
                days = int(parts[1])
                await self.get_archived_logs_for_period(websocket, days)
            else:
                response = {
                    "type": "response",
                    "message": "Invalid format for @get_archived_logs. Use '@get_archived_logs <days>'."
                }
                await websocket.send(json.dumps(response))
        elif message.startswith('@get_log_file'):
            parts = message.split()
            if len(parts) == 3:
                folder = parts[1]
                filename = parts[2]
                await self.send_log_file_content(websocket, folder, filename)
        elif message.startswith('@registered_functions'):
            await self.get_registered_functions(websocket)
        else:
            response = {"type": "error", "message": f"Unknown command @{message[1:]}."}
            await websocket.send(json.dumps(response))

    async def handler(self, websocket):
        client_address = websocket.remote_address
        await self.plogging.info(f"New connection: {client_address}")

        try:
            initial_message = await websocket.recv()
            data = json.loads(initial_message)
            # Обработка начального сообщения в формате JSON
            connection_type = data.get('arguments', {}).get('connection_type')
            if not connection_type:
                await self.plogging.warn(f"Client {client_address} did not send connection type.")
                await websocket.close()
                return
            self.clients[websocket] = {
                'address': client_address,
                'connection_type': connection_type
            }
            if self.on_connect_callback:
                self.on_connect_callback(client_address)
        except Exception as e:
            await self.plogging.error(f"Error during initial handshake with {client_address}: {e}")
            await websocket.close()
            return

        try:
            async for message in websocket:
                await self.plogging.debug(f"Message received from {client_address}: {message}")
                try:
                    data = json.loads(message)
                except Exception as e:
                    await self.plogging.error(f"Error parsing JSON from {client_address}: {e}")
                    continue

                # Обработка запроса по полю "request"
                request = data.get("request")
                arguments = data.get("arguments", {})

                if request:
                    match request:
                        case "GET_LOGS":
                            await self.send_packet(websocket, 'logs', self.plogging.get_history())
                        case "GET_ARCHIVED_LOGS":
                            days = arguments.get("days")
                            if isinstance(days, int):
                                await self.get_archived_logs_for_period(websocket, days)
                            else:
                                await websocket.send(json.dumps({
                                    "type": "response",
                                    "message": "Invalid argument for GET_ARCHIVED_LOGS."
                                }))
                        case "GET_LOG_FILE":
                            folder = arguments.get("folder")
                            filename = arguments.get("filename")
                            if folder and filename:
                                await self.send_log_file_content(websocket, folder, filename)
                            else:
                                await websocket.send(json.dumps({
                                    "type": "response",
                                    "message": "Invalid arguments for GET_LOG_FILE."
                                }))
                        case "REGISTERED_FUNCTIONS":
                            await self.get_registered_functions(websocket)
                        case "SLASH_COMMAND":
                            # Если запрос на вызов функции, ожидаем поле "command" внутри аргументов
                            func_command = arguments.get("command")
                            if func_command:
                                await self.execute_func(func_command, websocket)
                            else:
                                await websocket.send(json.dumps({
                                    "type": "response",
                                    "message": "Missing 'command' in CALL_FUNCTION request."
                                }))
                        case "GET_DISCORD_MEMBERS":
                            data = self.stats.get_all_users()
                            await self.send_packet(websocket, 'discord_members', data)
                        case "GET_DISCORD_MEMBER_STAT":
                            date = arguments.get("date")
                            user_id = arguments.get("member_id")
                            timelined_stat = self.stats.get_user_timeline(user_id=user_id, day=date)
                            if timelined_stat is None:
                                timelined_stat = "No data available"
                            total_date_stat = self.stats.get_user_stats(user_id=user_id, day=date)
                            if total_date_stat is None:
                                total_date_stat = "No data available"
                            responce_data = {"timeline": timelined_stat, "total": total_date_stat}
                            await self.send_packet(websocket, 'discord_member_stat', responce_data)
                            
                        case _:
                            await websocket.send(json.dumps({
                                "type": "error",
                                "message": f"Unknown request: {request}"
                            }))
                else:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid message format: missing 'request' field."
                    }))
        except websockets.exceptions.ConnectionClosed as e:
            await self.plogging.warn(f"Connection closed: {client_address}, reason: {e.code} - {e.reason}")
        except Exception as e:
            await self.plogging.error(f"Error with {client_address}: {e}")
        finally:
            await self.remove_client(websocket)

    async def start(self):
        while True:
            try:
                self.server = await websockets.serve(self.handler, self.host, self.port, max_size=16777216)
                
                await self.plogging.info(f"WebSocket server started on ws://{self.host}:{self.port}")
                await self.server.wait_closed()
            except Exception as e:
                await self.plogging.error(f"Server error: {e}")
                await asyncio.sleep(5)

    def run(self):
        asyncio.create_task(self.start())