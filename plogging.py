import os
import gzip
import datetime


logs_dir = "./logs"
log_history = []
log_filepath = None
web_sharing = False
global sharing
sharing = False


if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

def get_log_filename():
    """Возвращает имя файла журнала на основе текущего времени."""
    time_now_logs = datetime.datetime.now()
    formatted_time_logs = time_now_logs.strftime("%d-%m-%Y_%H-%M-%S")
    return f"log_{formatted_time_logs}.txt"

def create_log_file():
    """Создает новый файл журнала и возвращает путь к нему."""
    global log_filepath
    log_filename = get_log_filename()
    log_filepath = os.path.join(logs_dir, log_filename)
    
    try:
        with open(log_filepath, 'w') as f:
            pass
        print(f"Log file created: {log_filepath}")
    except Exception as e:
        print(f"Error on creating log file: {e}")

def archive_logs():
    """Архивирует старые файлы журнала и удаляет их."""
    log_files = [file for file in os.listdir(logs_dir) if file.endswith(".txt")]

    if log_files:
        for file in log_files:
            archive_filename = f"{file[:-4]}_archive.gz"
            archive_filepath = os.path.join(logs_dir, archive_filename)

            with open(os.path.join(logs_dir, file), 'rb') as f_in, gzip.open(archive_filepath, 'wb') as f_out:
                f_out.writelines(f_in)
            
            os.remove(os.path.join(logs_dir, file))
            print(f"Log file {file} successfully zipped in {archive_filepath}")

def enable_logging():
    """Включает логирование, архивирует старые файлы и создает новый файл журнала."""
    archive_logs()
    create_log_file()

def get_current_date():
    """Возвращает текущую дату в формате YYYY-MM-DD."""
    return datetime.datetime.now().strftime("%Y-%m-%d")

last_log_date = get_current_date()

async def plogging(a):
    global log_filepath, last_log_date

    current_date = get_current_date()
    if current_date != last_log_date:
        # Дата изменилась, закрываем и архивируем текущий файл
        if log_filepath and os.path.exists(log_filepath):
            archive_logs()
        # Создаем новый файл для журнала
        create_log_file()
        last_log_date = current_date

    from rainbotAPI_server import is_client_connected, send_packet
    # Логируем сообщение
    time_now = datetime.datetime.now()
    formatted_time = time_now.strftime("%H:%M:%S")
    print(f"[{formatted_time}] {a}")
    new_log_message = (f"[{formatted_time}] {a}")
    if is_client_connected():
        await send_packet('new_log_message', new_log_message)

    log_history.append(new_log_message)
    with open(log_filepath, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{formatted_time}] {a} \n")

def get_history():
    return list(log_history) if log_history is not None else "Log history clear."
def get_last_log_message():
    return str(log_history[-1:])