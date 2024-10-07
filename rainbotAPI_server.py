import asyncio
import websockets
import json
from plogging import plogging

registered_functions = [
    'print',
    'plogging'
]

# Глобальная переменная для хранения текущего подключения WebSocket
current_websocket = None

def execute_func(func_name, arguments):
    processed_args = [arg if arg.isdigit() else f"'{arg}'" for arg in arguments]
    eval_command = f"{func_name}({', '.join(processed_args)})"
    eval(eval_command)

async def send_packet(type, message):
    global current_websocket
    if current_websocket:
        try:
            response = {
                "type": type,
                "logs": message
            }
            await current_websocket.send(json.dumps(response))
        except Exception as e:
            print(f"Error sending logs: {e}")

async def send_logging_history():
    global current_websocket
    if current_websocket:
        try:
            from plogging import get_history
            response = {
                "type": "logs",
                "logs": get_history()
            }
            await current_websocket.send(json.dumps(response))
        except Exception as e:
            print(f"Error sending logs: {e}")

async def handler(websocket, path):
    global current_websocket
    current_websocket = websocket
    print(f"New connection: {websocket.remote_address}")
    try:
        async for message in websocket:
            print(f"Message received from {websocket.remote_address}: {message}")
            if message.startswith('@'):
                if message[1:] == 'get_logs':
                    await send_logging_history()
            elif message.startswith('/'):
                temp = message[1:].split()
                func_name = temp[0]
                arguments = temp[1:]
                if func_name in registered_functions:
                    execute_func(func_name, arguments)
                    response = {"type": "response", "message": "Function successfully executed."}
                else:
                    response = {"type": "error", "message": f"Error: Function '{func_name}' is not registered."}
                await websocket.send(json.dumps(response))
            else:
                response = {"type": "error", "message": "Error: Command should start with '/' or '@'."}
                await websocket.send(json.dumps(response))
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {websocket.remote_address}, reason: {e.code} - {e.reason}")
    except Exception as e:
        print(f"Error with {websocket.remote_address}: {e}")
    finally:
        current_websocket = None
        print(f"Client {websocket.remote_address} disconnected. Waiting for new connections.")

async def start_server():
    while True:
        try:
            server = await websockets.serve(handler, "192.168.0.108", 8765)
            print("WebSocket opened on ws://192.168.0.108:8765")
            await server.wait_closed()
        except Exception as e:
            print(f"Server error: {e}")
            await asyncio.sleep(5)

def is_client_connected():
    global current_websocket
    return current_websocket is not None