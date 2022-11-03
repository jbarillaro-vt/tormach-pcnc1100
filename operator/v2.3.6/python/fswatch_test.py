import sys
import fswatch
from watchdog.events import FileSystemEventHandler


class Handler(FileSystemEventHandler):

    @staticmethod
    def on_any_event(event):
        print "Event notification ", event.event_type, event

        if event.event_type == 'created':
            event.src_path

        elif event.event_type == 'modified':
            event.src_path


if __name__ == '__main__':
    event_handler = Handler()
    w = fswatch.Watcher(sys.argv[1])
    w.run(event_handler)
