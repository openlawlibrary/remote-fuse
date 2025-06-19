import asyncio
import threading


class AsyncExecutor:
    """I am helper class that handles asynchronous code execution inside syncronous functions"""
    def __init__(self):
        # Create a fresh event loop and run it in a separate thread
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start_loop, daemon=True)
        self.thread.start()

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro):
        """
        Schedule the coroutine 'coro' to run in the background event loop,
        and wait for its result.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()  # Blocks until the coroutine completes

    def __del__(self):
        self.loop.call_soon_threadsafe(self.loop.stop())
        self.thread.join()
