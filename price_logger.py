import os
import time
import pickle
import lz4.frame

class PriceLogger:
    def __init__(self, filepath, flush_interval=10):
        self.filepath = filepath
        self.flush_interval = flush_interval
        self.buffer = []
        self.capacity = 1000
        self.last_flush = time.time()

    def save_tuple(self, data: tuple):
        """Ajoute un tuple utilisateur (ticker, price)."""
        if not isinstance(data, tuple) or len(data) != 2:
            raise ValueError("Le tuple doit être de la forme (ticker, price)")
        timestamp = time.time()
        ticker, price = data
        self.buffer.append((timestamp, ticker, price))
        if len(self.buffer) >= self.capacity or time.time() - self.last_flush >= self.flush_interval:
            self.flush()

    def flush(self):
        """Sauvegarde le buffer dans le fichier compressé"""
        if not self.buffer:
            return
        with lz4.frame.open(self.filepath, mode='ab') as f:
            pickle.dump(self.buffer, f, protocol=pickle.HIGHEST_PROTOCOL)
        # Commenter l'affichage
        # print(f"[FLUSH] {len(self.buffer)} tuples enregistrés.")
        self.buffer.clear()
        self.last_flush = time.time()

    def read_all(self):
        """Générateur qui renvoie les tuples un par un (timestamp, ticker, price)"""
        if not os.path.exists(self.filepath):
            return
        with lz4.frame.open(self.filepath, mode='rb') as f:
            while True:
                try:
                    for tup in pickle.load(f):
                        yield tup
                except EOFError:
                    break