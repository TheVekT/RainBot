import asyncio
import inspect

class Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        """Connects a function (slot) to the signal. The slot will be called when the signal is emitted."""
        if slot not in self._slots:
            self._slots.append(slot)

    def emit(self, *args, **kwargs):
        """Emits the signal, calling all connected slots."""
        for slot in self._slots:
            try:
                if inspect.iscoroutinefunction(slot):
                    asyncio.create_task(slot(*args, **kwargs))
                else:
                    slot(*args, **kwargs)
            except Exception as e:
                print(f"Error in signal slot {slot.__name__}: {e}")