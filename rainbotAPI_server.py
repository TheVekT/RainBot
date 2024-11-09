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
        self.on_connect_callback = None
        self.on_disconnect_callback = None

        # Dictionary to keep track of connected clients
        self.clients = {}  # {websocket: {'address': (ip, port), 'connection_type': str}}
        self.register_funcs()
        
    def register_funcs(self):
        # Dictionary of registered functions
        from main import shlepay, nalivai
        self.registered_functions = {
            'print': print,
            'plogging': self.plogging.info,
            'shlepay': shlepay,
            'nalivai': nalivai
            # Add more functions as needed
        }

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
                # Execute the asynchronous function using asyncio.create_task
                task = asyncio.create_task(func(*processed_args))
                result = await task  # Await the task to get the result
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

    async def handler(self, websocket, path):
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
                    if message[1:] == 'get_logs':
                        await self.send_packet(websocket=websocket, type='logs', message=self.plogging.get_history())
                    elif message[1:] == 'get_all_logs':
                        pass  # Implement as needed
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
                self.server = await websockets.serve(self.handler, self.host, self.port)
                await self.plogging.info(f"WebSocket server started on ws://{self.host}:{self.port}")
                await self.server.wait_closed()
            except Exception as e:
                await self.plogging.error(f"Server error: {e}")
                await asyncio.sleep(5)

    def run(self):
        asyncio.create_task(self.start())