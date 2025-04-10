import os

def _load_token(token_type):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Строим путь относительно папки RainBot
    secrets_path = os.path.join(base_dir, 'secrets', f'{token_type}.txt')
    # Проверим, что файл существует перед его открытием
    if not os.path.exists(secrets_path):
        raise FileNotFoundError(f"Token file {secrets_path} not found")
    with open(secrets_path, 'r', encoding='utf-8') as f:
        return f.read().strip()

DISCORD_TOKEN = _load_token("discord_token")
TELEGRAM_TOKEN = _load_token("telegram_token")