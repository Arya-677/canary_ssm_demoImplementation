"""Memory Leaking Service Implementation for Demo.

A microservice with a critical memory retention bug: request payloads and session
objects are permanently appended to a global uncollected cache (_LEAK_STORE),
causing physical Resident Set Size (RSS) to grow indefinitely (+35 MB per burst).
"""
import time

# Critical bug: unbounded global cache retaining byte buffers
_LEAK_STORE: list[bytearray] = []

def process_request(data: bytes, leak_mb: float = 1.0) -> dict:
    """Process request while leaking uncollected memory on every invocation."""
    t0 = time.perf_counter()
    
    # Intentionally retain byte buffers in physical RAM
    chunk_bytes = int(leak_mb * 1024 * 1024)
    _LEAK_STORE.append(bytearray(b"M" * chunk_bytes))
    
    total_leaked_mb = sum(len(c) for c in _LEAK_STORE) / (1024 * 1024)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    
    return {
        "status": "leaking",
        "retained_chunks": len(_LEAK_STORE),
        "total_leaked_mb": round(total_leaked_mb, 2),
        "latency_ms": round(latency_ms, 3)
    }

if __name__ == "__main__":
    print("Memory Leak Service: retaining buffers indefinitely.")
