"""Broken Service Implementation for Demo.

A regressed microservice with an algorithmic slowdown / spinlock that causes
excessive CPU utilization, request latency degradation (+25%), and sporadic errors.
"""
import time

def process_request(data: bytes) -> dict:
    """Simulate a broken handler that degrades latency and triggers 500 errors."""
    t0 = time.perf_counter()
    
    # Inefficient CPU spin / delay regression
    total = 0
    for i in range(1_000_000):
        total += (i % 7)
        
    latency_ms = (time.perf_counter() - t0) * 1000.0
    
    # Broken regression causing high latency
    return {
        "status": "error_regression",
        "error": "LatencySLABreached",
        "latency_ms": round(latency_ms + 45.0, 3),
        "cpu_burn": True
    }

if __name__ == "__main__":
    print("Broken Service: executing with CPU and Latency regressions.")
