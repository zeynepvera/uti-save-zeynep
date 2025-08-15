import threading
import numpy as np

def buffer_push_frame(self, frame: np.ndarray):
    buffer = {}
    """
    Gelen NumPy frame'i bootstrap içindeki kalıcı buffer'a ekler
    ve güncel buffer listesini döner.
    """
    if frame is None or not isinstance(frame, np.ndarray):
        return []

    # store ve lock bootstrap üzerinde yoksa oluştur
    store = getattr(self.bootstrap, "_videosave_store", None)
    if store is None:
        store = {}
        setattr(self.bootstrap, "_videosave_store", store)

    lock = getattr(self.bootstrap, "_videosave_lock", None)
    if lock is None:
        lock = threading.Lock()
        setattr(self.bootstrap, "_videosave_lock", lock)

    # benzersiz buffer anahtarı
    buf_key = getattr(self, "buf_key", None)
    if not buf_key:
        title = getattr(self, "title", "untitled_video")
        buf_key = f"vs:{title}:frames"
        setattr(self, "buf_key", buf_key)

    # ekleme ve listeyi döndürme
    with lock:
        lst = store.get(buf_key)
        if lst is None:
            lst = []
            store[buf_key] = lst
        lst.append(frame)

        buffer["lst"] =lst
        return buffer
