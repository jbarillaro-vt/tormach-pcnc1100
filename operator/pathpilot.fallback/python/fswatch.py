import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class Watcher:

    def __init__(self, path):
        self.observer = Observer()
        self.path = path

    def start(self, handler):
        self.observer.schedule(handler, self.path, recursive=False)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join()

    def run(self, handler):
        self.start(handler)
        try:
            while True:
                time.sleep(5)
        except:
            pass
        self.stop()
