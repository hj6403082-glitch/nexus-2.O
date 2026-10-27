"""Local wake-word listening ("Hey Zeno") on its own thread.

A plain ``threading.Thread`` reads microphone frames and scores each with an
openwakeword model. It never touches the asyncio loop or the EventBus directly:
on a detection it calls ``loop.call_soon_threadsafe`` to hand a ``"wake"`` event
to the loop, which is the only safe bridge from a foreign thread into asyncio and
does not block. So a slow or stuck microphone read can never stall the EventBus.

sounddevice and openwakeword are imported lazily (Windows-only, optional), and the
audio stream and the detector are injected, so every test runs with fakes on any
OS and never opens a real microphone.
"""

import asyncio
import logging
import threading
import time
from collections.abc import Callable, Mapping
from typing import Protocol

from zeno.senses.events import DeviceEvent, EventBus

log = logging.getLogger(__name__)

DEVICE = "microphone"
FRAME_SAMPLES = 1280  # openwakeword wants 80 ms of 16 kHz mono 16-bit audio
SAMPLE_RATE = 16000


class AudioStream(Protocol):
    def read(self, frames: int) -> bytes: ...

    def close(self) -> None: ...


class Detector(Protocol):
    def predict(self, frame: bytes) -> Mapping[str, float]: ...


StreamFactory = Callable[[], AudioStream]
DetectorFactory = Callable[[], Detector]


class WakeWordListener:
    """Runs the microphone scan on a background thread; publishes ``wake`` events."""

    def __init__(
        self,
        bus: EventBus,
        *,
        detector_factory: DetectorFactory,
        stream_factory: StreamFactory,
        threshold: float = 0.6,
        refractory: float = 2.0,
        frame_samples: int = FRAME_SAMPLES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bus = bus
        self._detector_factory = detector_factory
        self._stream_factory = stream_factory
        self._threshold = threshold
        self._refractory = refractory
        self._frame_samples = frame_samples
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_fire = float("-inf")
        self.detections = 0

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Capture the running loop and start the listening thread."""
        if self._thread is not None:
            return
        self._loop = loop or asyncio.get_running_loop()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="zeno-wake-word", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the thread to finish and wait briefly for it. Safe to call twice."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
        self._thread = None

    def _run(self) -> None:
        try:
            detector = self._detector_factory()
            stream = self._stream_factory()
        except Exception:
            log.exception("Wake word listener could not start; voice wake is off")
            return
        try:
            while not self._stop.is_set():
                try:
                    frame = stream.read(self._frame_samples)
                except Exception:
                    log.exception("Microphone read failed; stopping wake word listener")
                    break
                if not frame:  # the stream ended
                    break
                hit = self._scan(detector, frame)
                if hit is not None:
                    self._deliver(*hit)
        finally:
            try:
                stream.close()
            except Exception:
                log.debug("Closing the microphone stream failed", exc_info=True)

    def _scan(self, detector: Detector, frame: bytes) -> tuple[str, float] | None:
        """The loudest model over the threshold, unless we just fired (refractory)."""
        try:
            scores = detector.predict(frame)
        except Exception:
            log.exception("Wake word model failed on a frame")
            return None
        if not scores:
            return None
        model, score = max(scores.items(), key=lambda item: item[1])
        if score < self._threshold:
            return None
        now = self._clock()
        if now - self._last_fire < self._refractory:
            return None
        self._last_fire = now
        return model, score

    def _deliver(self, model: str, score: float) -> None:
        """Hand the detection to the loop. The only thread->loop bridge here."""
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._publish, model, score)
        except RuntimeError:
            # The loop is closed (shutdown raced us); nothing more to do.
            log.debug("Event loop gone; dropping wake detection")

    def _publish(self, model: str, score: float) -> None:
        """Runs on the loop thread: put the event on the bus."""
        self.detections += 1
        self._bus.publish(
            DeviceEvent(
                device=DEVICE,
                kind="wake",
                data={"model": model, "confidence": round(score, 3)},
                received_at=time.time(),
            )
        )


def build_listener(settings: object, bus: EventBus) -> WakeWordListener:
    """Wire a listener from settings with the real (lazy) sounddevice + openwakeword
    factories. The imports only run when the thread starts, so this is safe to call
    anywhere; the daemon only starts it on Windows."""
    threshold = float(getattr(settings, "wakeword_confidence", 0.6))
    model_path = getattr(settings, "wakeword_model_path", None)
    detector = (
        default_detector_factory(str(model_path)) if model_path else _builtin_detector_factory()
    )
    return WakeWordListener(
        bus,
        detector_factory=detector,
        stream_factory=default_stream_factory(),
        threshold=threshold,
    )


def _builtin_detector_factory() -> DetectorFactory:
    """openwakeword with its bundled models when no path is set."""

    def open_detector() -> Detector:
        import numpy as np
        from openwakeword.model import Model

        model = Model()

        class _OpenWakeWord:
            def predict(self, frame: bytes) -> Mapping[str, float]:
                samples = np.frombuffer(frame, dtype=np.int16)
                return {name: float(score) for name, score in model.predict(samples).items()}

        return _OpenWakeWord()

    return open_detector


def default_stream_factory(frame_samples: int = FRAME_SAMPLES) -> StreamFactory:
    """A sounddevice microphone stream. Imported lazily; Windows/optional."""

    def open_stream() -> AudioStream:
        import sounddevice  # optional, loaded only when voice wake is on

        stream = sounddevice.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=frame_samples,
        )
        stream.start()

        class _SoundDeviceStream:
            def read(self, frames: int) -> bytes:
                data, _overflowed = stream.read(frames)
                return bytes(data)

            def close(self) -> None:
                stream.stop()
                stream.close()

        return _SoundDeviceStream()

    return open_stream


def default_detector_factory(model_path: str) -> DetectorFactory:
    """An openwakeword model. Imported lazily; Windows/optional."""

    def open_detector() -> Detector:
        import numpy as np
        from openwakeword.model import Model

        model = Model(wakeword_models=[model_path])

        class _OpenWakeWord:
            def predict(self, frame: bytes) -> Mapping[str, float]:
                samples = np.frombuffer(frame, dtype=np.int16)
                return {name: float(score) for name, score in model.predict(samples).items()}

        return _OpenWakeWord()

    return open_detector
