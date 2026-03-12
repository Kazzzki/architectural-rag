import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from .llm_agent import LLMAgent
from .persistence import merge_ai_nodes

class NoteEventHandler(FileSystemEventHandler):
    def __init__(self):
        self.agent = LLMAgent()
        self.last_trigger = {}

    def on_modified(self, event):
        if event.is_directory: return
        if not event.src_path.endswith(".md"): return
        
        # Debounce
        now = time.time()
        if now - self.last_trigger.get(event.src_path, 0) < 1.0:
            return
        self.last_trigger[event.src_path] = now

        print(f"File modified: {event.src_path}")
        self.process_file(event.src_path)
    
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            print(f"File created: {event.src_path}")
            self.process_file(event.src_path)

    def process_file(self, filepath):
        print(f"Analyzing {filepath}...")
        nodes = self.agent.analyze_file(filepath)
        merge_ai_nodes(nodes)
        print(f"Updated graph with {len(nodes)} nodes.")

def start_watcher(path_to_watch):
    event_handler = NoteEventHandler()
    observer = Observer()
    if not os.path.exists(path_to_watch):
        os.makedirs(path_to_watch)
    observer.schedule(event_handler, path_to_watch, recursive=False)
    observer.start()
    return observer
