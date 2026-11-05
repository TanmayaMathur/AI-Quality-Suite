from collections import deque
from math import ceil
from threading import Lock


def percentile(values: list[float], fraction: float) -> float | None:
    return sorted(values)[ceil(len(values) * fraction) - 1] if values else None


class Telemetry:
    def __init__(self):
        self.requests = 0
        self.errors = 0
        self.samples: deque[float] = deque(maxlen=1000)
        self.lock = Lock()

    def record(self, latency_ms: float, error: bool):
        with self.lock:
            self.requests += 1
            self.errors += error
            self.samples.append(latency_ms)

    def snapshot(self):
        with self.lock:
            samples = list(self.samples)
            return {
                "requests": self.requests,
                "errors": self.errors,
                "error_rate": self.errors / self.requests if self.requests else None,
                "sample_count": len(samples),
                "p50_ms": percentile(samples, 0.5),
                "p95_ms": percentile(samples, 0.95),
            }
