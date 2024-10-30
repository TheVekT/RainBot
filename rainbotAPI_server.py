import asyncio
import websockets
import json
from plogging import Plogging
import inspect

class WebSocketServer:
    def __init__(self, host='192.168.0.106', port=8765):
        self.plogging = Plogging()
        self.plogging.on_log_message.connect(self._send_new_log_message)
        self.host = host
        self.port = port
        self.server = None
        self.current_websocket = None
        self.is_connected = False
        self.on_connect_callback = None
        self.on_disconnect_callback = None

        # Dictionary of registered functions
        self.registered_functions = {
            'print': print,
            'plogging': self.plogging.info,  
            # Add more functions as needed
        }
    def _send_new_log_message(self):
        if self.is_connected:
            new_message = self.plogging.get_last_log_message()
            asyncio.create_task(self.send_packet(self.current_websocket, 'new_log_message', new_message))

    def on_connect(self, callback):
        """Register a callback for when a client connects."""
        self.on_connect_callback = callback

    def on_disconnect(self, callback):
        """Register a callback for when a client disconnects."""
        self.on_disconnect_callback = callback

    async def execute_func(self, func_name, arguments):
        func = self.registered_functions.get(func_name)
        if not func:
            return {"type": "error", "message": f"Error: Function '{func_name}' is not registered."}

        # Process arguments
        processed_args = []
        for arg in arguments:
            if arg.isdigit():
                processed_args.append(int(arg))
            else:
                processed_args.append(arg)

        try:
            if inspect.iscoroutinefunction(func):
                result = await func(*processed_args)
            else:
                result = func(*processed_args)
            return {"type": "response", "message": "Function executed successfully.", "result": result}
        except Exception as e:
            return {"type": "error", "message": f"Error executing function '{func_name}': {e}"}

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

    async def handler(self, websocket, path):
        self.current_websocket = websocket
        self.is_connected = True
        await self.plogging.info(f"New connection: {websocket.remote_address}")

        # Trigger on_connect signal
        if self.on_connect_callback:
            self.on_connect_callback(websocket.remote_address)

        try:
            async for message in websocket:
                await self.plogging.debug(f"Message received from {websocket.remote_address}: {message}")
                if message.startswith('@'):
                    if message[1:] == 'get_logs':
                        await self.send_packet(websocket=websocket, type='logs', message=self.plogging.get_history())
                    elif message[1:] == 'get_all_logs':
                        await self.send_packet(websocket=websocket, type='all_logs', message=)
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
            await self.plogging.warn(f"Connection closed: {websocket.remote_address}, reason: {e.code} - {e.reason}")
        except Exception as e:
            await self.plogging.error(f"Error with {websocket.remote_address}: {e}")
        finally:
            self.is_connected = False
            self.current_websocket = None
            await self.plogging.info(f"Client {websocket.remote_address} disconnected. Waiting for new connections.")

            # Trigger on_disconnect signal
            if self.on_disconnect_callback:
                self.on_disconnect_callback(websocket.remote_address)

    async def start(self):
        while True:
            try:
                self.server = await websockets.serve(self.handler, self.host, self.port)
                await self.plogging.info(f"WebSocket server started on ws://{self.host}:{self.port}")
                await self.server.wait_closed()
            except Exception as e:
                await self.plogging.error(f"Server error: {e}")
                await asyncio.sleep(5)

    def run(self):
        asyncio.create_task(self.start())