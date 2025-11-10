# AnalyzerPool Guide

## Overview

`AnalyzerPool` is a class that creates and manages multiple analyzer workers that pull and process logs from the distributor, with flexible weight configuration for different capacity requirements.

## Features

✅ **Multiple Concurrent Analyzers**: Run N analyzers in parallel  
✅ **Flexible Weight Configuration**: Different weights per analyzer or uniform  
✅ **Automatic Distribution**: Work naturally distributed based on weights  
✅ **Statistics & Monitoring**: Track per-analyzer and total stats  
✅ **Distribution Analysis**: Compare actual vs expected distribution  
✅ **Easy Control**: Simple start/stop/run_for_duration API  

## Basic Usage

```python
from analyzer import AnalyzerPool
import asyncio

async def main():
    # Create pool with 4 analyzers (default weights: 0.4, 0.3, 0.2, 0.1)
    pool = AnalyzerPool(
        distributor_url="http://localhost:8000",
        num_analyzers=4
    )
    
    # Start all analyzers
    await pool.start()
    
    # Let them process work...
    await asyncio.sleep(30)
    
    # Stop all analyzers
    await pool.stop()
    
    # Check stats
    stats = pool.get_stats()
    print(f"Total processed: {stats['total_processed']}")

asyncio.run(main())
```

## Configuration Parameters

### `num_analyzers` (int)
Number of analyzers to create.
- **Default**: 4
- **Example**: 10 analyzers → 10 independent workers pulling work

### `weights` (Optional[Union[List[float], float]])
Weight configuration for analyzers.
- **None** (default): Cycles through [0.4, 0.3, 0.2, 0.1]
- **Single float**: All analyzers get same weight (e.g., 0.25)
- **List of floats**: Specific weight per analyzer

```python
# Default weights (cycles pattern)
pool = AnalyzerPool(num_analyzers=4)  # [0.4, 0.3, 0.2, 0.1]
pool = AnalyzerPool(num_analyzers=6)  # [0.4, 0.3, 0.2, 0.1, 0.4, 0.3]

# Uniform weights
pool = AnalyzerPool(num_analyzers=4, weights=0.25)  # All 0.25

# Custom weights
pool = AnalyzerPool(
    num_analyzers=4,
    weights=[0.7, 0.1, 0.1, 0.1]  # One heavy, three light
)
```

### `analyzer_prefix` (str)
Prefix for analyzer IDs.
- **Default**: "analyzer"
- **Result**: "analyzer-1", "analyzer-2", etc.

### `processing_delay` (float)
Simulated processing time per task in seconds.
- **Default**: 0.1 (100ms)
- **Example**: 0.01 → 10ms per task (fast), 0.5 → 500ms (slow)

### `poll_interval` (float)
Seconds between work polling attempts.
- **Default**: 1.0
- **Lower**: More responsive but more requests
- **Higher**: Less responsive but fewer requests

## Weight Behavior

### How Weights Affect Concurrency

```python
weight = 0.4 → max_concurrent_tasks = 4
weight = 0.3 → max_concurrent_tasks = 3
weight = 0.2 → max_concurrent_tasks = 2
weight = 0.1 → max_concurrent_tasks = 1
```

Formula: `max_concurrent = max(1, int(weight * 10))`

### How Weights Affect Distribution

Over time, analyzers process work proportional to their weight:

```
weights = [0.4, 0.3, 0.2, 0.1]
→ analyzer-1: ~40% of tasks
→ analyzer-2: ~30% of tasks
→ analyzer-3: ~20% of tasks
→ analyzer-4: ~10% of tasks
```

This happens naturally because:
- Higher weight = more concurrent tasks
- More concurrent tasks = request work more often
- Request work more often = process more tasks

## Usage Patterns

### Pattern 1: Default Configuration

```python
# Simple: 4 analyzers with standard weights
pool = AnalyzerPool(distributor_url="http://localhost:8000")
await pool.start()
await asyncio.sleep(60)
await pool.stop()
```

### Pattern 2: Uniform Distribution

```python
# All analyzers equal
pool = AnalyzerPool(
    distributor_url="http://localhost:8000",
    num_analyzers=5,
    weights=0.2  # Each gets 20%
)
```

### Pattern 3: Heavy/Light Mix

```python
# One heavy analyzer, rest light
pool = AnalyzerPool(
    distributor_url="http://localhost:8000",
    num_analyzers=4,
    weights=[0.7, 0.1, 0.1, 0.1]
)
```

### Pattern 4: Run for Duration

```python
# Convenience method
pool = AnalyzerPool(...)
await pool.run_for_duration(60)  # Runs for 60 seconds
```

### Pattern 5: Wait for Idle

```python
pool = AnalyzerPool(...)
await pool.start()

# ... do something ...

# Wait for all tasks to complete
await pool.wait_for_idle(timeout=30.0)
await pool.stop()
```

### Pattern 6: Monitoring

```python
pool = AnalyzerPool(...)
await pool.start()

# Monitor while running
for i in range(60):
    await asyncio.sleep(1)
    
    if i % 10 == 0:
        stats = pool.get_stats()
        print(f"Processed: {stats['total_processed']}")

await pool.stop()
```

## Statistics

### Get Stats

```python
stats = pool.get_stats()
```

Returns:
```python
{
    "num_analyzers": 4,
    "total_processed": 1000,
    "total_failed": 5,
    "is_running": True,
    "analyzer_stats": {
        "analyzer-1": {
            "weight": 0.4,
            "max_concurrent": 4,
            "active_tasks": 3,
            "total_processed": 412,
            "total_failed": 2,
            "tasks_per_second": 13.7,
            "is_running": True
        },
        # ... more analyzers
    }
}
```

### Get Distribution

```python
distribution = pool.get_distribution()
```

Returns:
```python
{
    "total_processed": 1000,
    "distribution": {
        "analyzer-1": {
            "processed": 412,
            "weight": 0.4,
            "actual_percentage": 41.2,
            "expected_percentage": 40.0,
            "deviation": +1.2
        },
        # ... more analyzers
    }
}
```

## Demo Scripts

### Basic Demo

```bash
python demo/analyzer_pool_demo.py --mode basic
```

4 analyzers with default weights, processes logs for 30 seconds.

### Custom Weights Demo

```bash
python demo/analyzer_pool_demo.py --mode custom-weights
```

One heavy analyzer (0.7) and three light (0.1 each).

### Uniform Demo

```bash
python demo/analyzer_pool_demo.py --mode uniform
```

All analyzers with same weight (0.2 each).

### Scalability Demo

```bash
python demo/analyzer_pool_demo.py --mode scalability
```

Shows scaling from 2 to 6 analyzers mid-run.

### Monitoring Demo

```bash
python demo/analyzer_pool_demo.py --mode monitoring
```

Detailed real-time monitoring with per-analyzer stats.

## Complete Example

```python
import asyncio
import logging
from analyzer import AnalyzerPool
from emitter import LogEmitterPool

logging.basicConfig(level=logging.INFO)

async def main():
    # Check distributor
    import httpx
    async with httpx.AsyncClient() as client:
        await client.get("http://localhost:8000/health")
    
    # Create analyzer pool
    analyzer_pool = AnalyzerPool(
        distributor_url="http://localhost:8000",
        num_analyzers=4,
        weights=[0.4, 0.3, 0.2, 0.1]
    )
    
    # Create emitter pool to generate logs
    emitter_pool = LogEmitterPool(
        distributor_url="http://localhost:8000",
        num_emitters=10,
        base_interval=0.5,
        interval_jitter=0.2
    )
    
    # Start both
    await analyzer_pool.start()
    await emitter_pool.start()
    
    try:
        # Monitor for 30 seconds
        for i in range(30):
            await asyncio.sleep(1)
            
            if (i + 1) % 10 == 0:
                emitter_stats = emitter_pool.get_stats()
                analyzer_stats = analyzer_pool.get_stats()
                
                print(
                    f"[{i+1}s] Emitted: {emitter_stats['total_emitted']}, "
                    f"Processed: {analyzer_stats['total_processed']}"
                )
    
    finally:
        # Stop emitters first
        await emitter_pool.stop()
        
        # Wait for analyzers to finish
        await analyzer_pool.wait_for_idle(timeout=10.0)
        
        # Stop analyzers
        await analyzer_pool.stop()
        
        # Show distribution
        distribution = analyzer_pool.get_distribution()
        print(f"\nTotal processed: {distribution['total_processed']}")
        for aid, dist in distribution['distribution'].items():
            print(
                f"{aid}: {dist['actual_percentage']:.1f}% "
                f"(expected: {dist['expected_percentage']:.0f}%)"
            )

asyncio.run(main())
```

## Use Cases

### 1. Standard Setup (Default Weights)

```python
# Typical setup with varied capacity
pool = AnalyzerPool(
    distributor_url="http://localhost:8000",
    num_analyzers=4
)
```

Good for: Testing, demos, general use

### 2. Equal Distribution

```python
# All analyzers process equally
pool = AnalyzerPool(
    distributor_url="http://localhost:8000",
    num_analyzers=5,
    weights=0.2
)
```

Good for: Uniform machines, simple load balancing

### 3. Tiered Capacity

```python
# Different tiers of analyzers
pool = AnalyzerPool(
    distributor_url="http://localhost:8000",
    num_analyzers=6,
    weights=[0.5, 0.3, 0.1, 0.05, 0.03, 0.02]
)
```

Good for: Mixed hardware, priority systems

### 4. Primary/Backup

```python
# One primary, others backup
pool = AnalyzerPool(
    distributor_url="http://localhost:8000",
    num_analyzers=4,
    weights=[0.8, 0.1, 0.05, 0.05]
)
```

Good for: Dedicated primary with failover

### 5. High Capacity

```python
# Many analyzers, uniform
pool = AnalyzerPool(
    distributor_url="http://localhost:8000",
    num_analyzers=20,
    weights=0.05  # Each handles 5%
)
```

Good for: High throughput, horizontal scaling

## Integration with Demo

The main demo now uses AnalyzerPool:

```python
# In demo_setup.py

async def start_analyzers(self):
    self.analyzer_pool = AnalyzerPool(
        distributor_url=self.distributor_url,
        num_analyzers=4,
        processing_delay=0.1
    )
    await self.analyzer_pool.start()
```

## Integration with Emitter Pool

Perfect combination for testing:

```python
# Create both pools
analyzer_pool = AnalyzerPool(
    distributor_url="http://localhost:8000",
    num_analyzers=4
)

emitter_pool = LogEmitterPool(
    distributor_url="http://localhost:8000",
    num_emitters=10,
    base_interval=0.5
)

# Start both
await analyzer_pool.start()
await emitter_pool.start()

# Let them run
await asyncio.sleep(60)

# Stop gracefully
await emitter_pool.stop()          # Stop new logs
await analyzer_pool.wait_for_idle() # Finish processing
await analyzer_pool.stop()          # Stop analyzers
```

## Tips

1. **Start with Default**: Begin with default 4 analyzers
2. **Match Capacity**: Set weights based on actual machine capacity
3. **Monitor Distribution**: Check if actual matches expected
4. **Use wait_for_idle()**: Before stopping, let tasks complete
5. **Scale Gradually**: Test with small pool, then scale up

## Troubleshooting

### Distribution doesn't match weights

- **Small sample**: Need more tasks for convergence (>100)
- **Check stats**: Use `get_distribution()` to see deviation
- **Normal variance**: ±5% is typical

### Analyzers not processing

- Check distributor is running
- Check queue has tasks
- Look for errors in logs

### Low throughput

- Increase `num_analyzers`
- Increase weights (more concurrent tasks)
- Decrease `processing_delay`

### Tasks timing out

- Check analyzer logs
- Increase heartbeat frequency
- Check network connectivity

## Advanced: Dynamic Scaling

```python
# Start with base pool
pool = AnalyzerPool(num_analyzers=2)
await pool.start()

# ... monitor load ...

# Scale up by creating new pool
await pool.stop()
pool = AnalyzerPool(num_analyzers=6)
await pool.start()
```

For production, integrate with Kubernetes HPA or AWS ECS auto-scaling.

---

**The AnalyzerPool provides flexible, configurable worker management for the log processing system!**

