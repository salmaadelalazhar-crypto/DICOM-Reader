"""Run slow work (DICOM analysis, gTTS, Gemini) off the UI thread so the window never freezes."""
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)
    progress = Signal(int, int)


class _Task(QRunnable):
    def __init__(self, fn, args, kwargs, with_progress):
        super().__init__()
        self.fn, self.args, self.kwargs, self.with_progress = fn, args, kwargs, with_progress
        self.signals = _Signals()

    def run(self):
        try:
            if self.with_progress:
                result = self.fn(*self.args, progress=self.signals.progress.emit, **self.kwargs)
            else:
                result = self.fn(*self.args, **self.kwargs)
        except Exception as error:  # reported to the UI as a safe message
            self.signals.failed.emit(error)
        else:
            self.signals.done.emit(result)


_alive = set()


def run_task(fn, *args, on_done=None, on_error=None, on_progress=None, **kwargs):
    task = _Task(fn, args, kwargs, on_progress is not None)
    signals = task.signals
    _alive.add(signals)

    def finish(callback):
        def handler(value):
            _alive.discard(signals)
            if callback:
                callback(value)
        return handler

    signals.done.connect(finish(on_done))
    signals.failed.connect(finish(on_error))
    if on_progress:
        signals.progress.connect(on_progress)
    QThreadPool.globalInstance().start(task)
    return signals
