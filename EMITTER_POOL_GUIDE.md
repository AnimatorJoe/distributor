# LogEmitterPool Guide

## Overview

`LogEmitterPool` is a class that creates multiple log emitters that continuously send logs at randomized intervals, simulating real-world log traffic patterns.

## Features

✅ **Multiple Concurrent Emitters**: Run N emitters in parallel  
✅ **Randomized Intervals**: Each log sent at `x ± y` seconds  
✅ **Realistic Log Generation**: Varied messages, levels, and metadata  
✅ **Statistics Tracking**: Monitor per-emitter and total stats  
✅ **Easy Control**: Simple start/stop/run_for_duration API  

## Basic Usage

```python
from emitter import LogEmitterPool
import asyncio

async def main():
    # Create pool
    pool = LogEmitterPool(
        distributor_url="http://localhost:8000",
        num_emitters=5,           # 5 concurrent emitters
        base_interval=1.0,        # Base interval (x)
        interval_jitter=0.5       # Random variation (±y)
    )
    
    # Run for 30 seconds
    await pool.run_for_duration(30)
    
    # Check stats
    stats = pool.get_stats()
    print(f"Total logs emitted: {stats['total_emitted']}")

asyncio.run(main())
```

## Configuration Parameters

### `num_emitters` (int)
Number of concurrent emitters to run.
- **Default**: 5
- **Example**: 10 emitters → 10 independent loops sending logs

### `base_interval` (float)
Base time in seconds between log emissions (the "x" in x ± y).
- **Default**: 1.0
- **Example**: 0.5 → logs every ~0.5 seconds

### `interval_jitter` (float)
Random variation in seconds added/subtracted from base_interval (the "±y" in x ± y).
- **Default**: 0.5
- **Example**: base=1.0, jitter=0.5 → logs every 0.5-1.5 seconds

### `emitter_prefix` (str)
Prefix for emitter source names.
- **Default**: "emitter"
- **Result**: "emitter-1", "emitter-2", etc.

## Usage Patterns

### Pattern 1: Run for Fixed Duration

```python
pool = LogEmitterPool(
    distributor_url="http://localhost:8000",
    num_emitters=5,
    base_interval=1.0,
    interval_jitter=0.5
)

# Runs for exactly 30 seconds, then stops
await pool.run_for_duration(30)
```

### Pattern 2: Manual Control

```python
pool = LogEmitterPool(...)

# Start
await pool.start()

# Do something while it runs
await asyncio.sleep(10)

# Check stats
stats = pool.get_stats()
print(f"Emitted so far: {stats['total_emitted']}")

# Keep running
await asyncio.sleep(20)

# Stop
await pool.stop()
```

### Pattern 3: Monitor While Running

```python
pool = LogEmitterPool(...)
await pool.start()

try:
    for i in range(60):
        await asyncio.sleep(1)
        
        if i % 10 == 0:
            stats = pool.get_stats()
            print(f"[{i}s] Total: {stats['total_emitted']}")

finally:
    await pool.stop()
```

### Pattern 4: Multiple Pools

```python
# Different rates for different scenarios
slow_pool = LogEmitterPool(
    distributor_url="http://localhost:8000",
    num_emitters=2,
    base_interval=5.0,
    interval_jitter=1.0,
    emitter_prefix="slow"
)

fast_pool = LogEmitterPool(
    distributor_url="http://localhost:8000",
    num_emitters=10,
    base_interval=0.2,
    interval_jitter=0.1,
    emitter_prefix="fast"
)

# Run both simultaneously
await asyncio.gather(
    slow_pool.start(),
    fast_pool.start()
)

# ... let them run ...

await asyncio.gather(
    slow_pool.stop(),
    fast_pool.stop()
)
```

## Log Generation

Each emitter generates realistic logs with:

### Messages
- "Processing request #N"
- "Database query completed in Xms"
- "User authenticated successfully"
- "Cache hit for key 'user_1234'"
- "API call to external service completed"
- And more...

### Log Levels (Realistic Distribution)
- 70% INFO
- 15% DEBUG
- 10% WARN
- 4% ERROR
- 1% CRITICAL

### Metadata
Each log includes:
```python
{
    "emitter_id": "emitter-1",
    "sequence": 42,
    "request_id": "req-12345",
    "duration_ms": 150,
    "status_code": 200
}
```

## Statistics

Get comprehensive stats with `pool.get_stats()`:

```python
{
    "total_emitted": 150,
    "num_emitters": 5,
    "is_running": True,
    "emitter_stats": {
        "emitter-1": {"count": 32, "errors": 0},
        "emitter-2": {"count": 28, "errors": 0},
        "emitter-3": {"count": 31, "errors": 0},
        "emitter-4": {"count": 29, "errors": 0},
        "emitter-5": {"count": 30, "errors": 0}
    }
}
```

## Demo Scripts

### Basic Demo

```bash
python demo/emitter_pool_demo.py --mode basic
```

Runs 5 emitters for 30 seconds with moderate rate.

### Custom Demo

```bash
python demo/emitter_pool_demo.py --mode custom
```

10 emitters with monitoring and manual control.

### High Volume Demo

```bash
python demo/emitter_pool_demo.py --mode high-volume
```

20 emitters at high frequency (~100 logs/sec).

### Variable Rate Demo

```bash
python demo/emitter_pool_demo.py --mode variable-rate
```

Multiple pools with different rates running simultaneously.

## Rate Calculations

### Expected Rate
```
rate ≈ num_emitters / base_interval
```

**Examples:**
- 5 emitters, 1.0s interval → ~5 logs/sec
- 10 emitters, 0.5s interval → ~20 logs/sec
- 20 emitters, 0.2s interval → ~100 logs/sec

### Actual Rate (with jitter)
```
actual_rate ≈ num_emitters / (base_interval ± jitter)
```

The jitter adds variation:
- Emitter 1 might emit at 0.8s
- Emitter 2 might emit at 1.3s
- Emitter 3 might emit at 1.0s
- etc.

This creates realistic, non-uniform traffic patterns.

## Use Cases

### 1. Load Testing
```python
# Simulate 100 logs/sec
pool = LogEmitterPool(
    num_emitters=20,
    base_interval=0.2,
    interval_jitter=0.05
)
await pool.run_for_duration(60)  # 1 minute
```

### 2. Stress Testing
```python
# Ramp up gradually
for rate in [10, 50, 100, 200]:
    pool = LogEmitterPool(
        num_emitters=rate,
        base_interval=0.1
    )
    await pool.run_for_duration(10)
```

### 3. Continuous Background Load
```python
# Low background traffic
pool = LogEmitterPool(
    num_emitters=3,
    base_interval=2.0,
    interval_jitter=1.0
)
await pool.start()

# Keep running indefinitely
# (until manually stopped)
```

### 4. Simulate Multiple Applications
```python
# Different apps with different patterns
web_app = LogEmitterPool(
    num_emitters=10,
    base_interval=0.5,
    emitter_prefix="web-app"
)

batch_job = LogEmitterPool(
    num_emitters=2,
    base_interval=5.0,
    emitter_prefix="batch-job"
)

api_server = LogEmitterPool(
    num_emitters=15,
    base_interval=0.3,
    emitter_prefix="api-server"
)
```

## Error Handling

Emitters handle errors gracefully:

```python
# If a log fails to emit:
# 1. Error is logged
# 2. Error count incremented
# 3. Emitter continues (doesn't crash)
# 4. Check stats for errors

stats = pool.get_stats()
for emitter_id, emitter_stats in stats['emitter_stats'].items():
    if emitter_stats['errors'] > 0:
        print(f"{emitter_id} had {emitter_stats['errors']} errors")
```

## Complete Example

```python
import asyncio
import logging
from emitter import LogEmitterPool

# Configure logging
logging.basicConfig(level=logging.INFO)

async def main():
    # Check distributor is running
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            await client.get("http://localhost:8000/health")
    except:
        print("Start distributor first!")
        return
    
    # Create pool
    print("Starting emitter pool...")
    pool = LogEmitterPool(
        distributor_url="http://localhost:8000",
        num_emitters=5,
        base_interval=1.0,
        interval_jitter=0.5,
        emitter_prefix="demo"
    )
    
    # Start it
    await pool.start()
    
    try:
        # Monitor for 30 seconds
        for i in range(30):
            await asyncio.sleep(1)
            
            if (i + 1) % 5 == 0:
                stats = pool.get_stats()
                rate = stats['total_emitted'] / (i + 1)
                print(f"[{i+1}s] Emitted: {stats['total_emitted']}, Rate: {rate:.1f}/s")
    
    finally:
        # Clean up
        print("\nStopping pool...")
        await pool.stop()
        
        # Final stats
        stats = pool.get_stats()
        print(f"\nFinal: {stats['total_emitted']} logs emitted")
        print("\nPer-emitter breakdown:")
        for eid, estats in stats['emitter_stats'].items():
            print(f"  {eid}: {estats['count']} logs, {estats['errors']} errors")

if __name__ == "__main__":
    asyncio.run(main())
```

## Tips

1. **Start Small**: Begin with 5 emitters at 1.0s interval
2. **Monitor First**: Check distributor can handle the load
3. **Increase Gradually**: Ramp up num_emitters or decrease interval
4. **Use Jitter**: Adds realism and prevents synchronized bursts
5. **Check Errors**: Monitor `emitter_stats` for any failures

## Troubleshooting

### Pool doesn't emit logs
- Check distributor is running: `curl http://localhost:8000/health`
- Check network connectivity
- Look for errors in logs

### Rate is lower than expected
- Check if distributor is overloaded
- Look at analyzer capacity
- Check for backpressure in queue

### Too many errors
- Distributor might be down
- Network issues
- Check distributor logs for problems

## Integration with Demo

You can use `LogEmitterPool` in the main demo:

```python
# In demo_setup.py

from emitter import LogEmitterPool

async def demo_with_pool():
    # Start analyzers
    await env.start_analyzers()
    
    # Use emitter pool instead of manual sending
    pool = LogEmitterPool(
        distributor_url="http://localhost:8000",
        num_emitters=10,
        base_interval=0.5,
        interval_jitter=0.2
    )
    
    await pool.run_for_duration(60)
    
    # Check stats
    await env.print_final_stats()
```

---

**The LogEmitterPool provides realistic, configurable log traffic for testing and demonstrating the distributor system!**

