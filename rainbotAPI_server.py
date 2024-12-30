import asyncio
import websockets
import json
from plogging import Plogging
import inspect
import os
import gzip
import datetime

class WebSocketServer:
    def __init__(self, host='192.168.0.106', port=8765):
        self.plogging = Plogging()
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

    async def execute_func(self, func_name, arguments):
        if self.registered_functions is not None:
            func = self.registered_functions.get(func_name)
        else:
            return {"type": "response", "message": f"Error: Function '{func_name}' is not registered."}

        # Process arguments
        processed_args = []
        for arg in arguments:
            if arg.isdigit():
                processed_args.append(int(arg))
            else:
                processed_args.append(arg)

        try:
            if inspect.iscoroutinefunction(func):
                # Directly await the coroutine
                result = await func(*processed_args)
            else:
                result = func(*processed_args)
            return {"type": "response", "message": "Function executed successfully.", "result": result}
        except Exception as e:
            return {"type": "response", "message": f"Error executing function '{func_name}': {e}"}

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

    async def handler(self, websocket):
        # Get client address
        client_address = websocket.remote_address
        await self.plogging.info(f"New connection: {client_address}")

        # Receive initial message from client indicating connection type
        try:
            initial_message = await websocket.recv()
            data = json.loads(initial_message)
            connection_type = data.get('connection-type')
            if not connection_type:
                await self.plogging.warn(f"Client {client_address} did not send connection type.")
                await websocket.close()
                return
            # Store client info
            self.clients[websocket] = {
                'address': client_address,
                'connection_type': connection_type
            }
            # Trigger on_connect signal
            if self.on_connect_callback:
                self.on_connect_callback(client_address)
        except Exception as e:
            await self.plogging.error(f"Error during initial handshake with {client_address}: {e}")
            await websocket.close()
            return

        try:
            async for message in websocket:
                await self.plogging.debug(f"Message received from {client_address}: {message}")
                if message.startswith('@'):
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
                elif message.startswith('/'):
                    temp = message[1:].split()
                    func_name = temp[0]
                    arguments = temp[1:]
                    response = await self.execute_func(func_name, arguments)
                    await websocket.send(json.dumps(response))
                else:
                    response = {"type": "error", "message": "Error: Command should start with '/' or '@'."}
                    await websocket.send(json.dumps(response))
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