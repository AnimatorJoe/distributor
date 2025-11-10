# Autoscaling Guide

## Overview

The autoscaler automatically adjusts the number of analyzer instances based on queue backpressure, ensuring optimal throughput while managing resources efficiently.

## How It Works

### Monitoring
- Periodically checks queue depth
- Compares against configured thresholds
- Respects min/max pool size limits

### Scaling Up
**Trigger:** Queue depth >= `scale_up_threshold`

**Actions:**
- Adds `scale_up_count` new analyzers
- Each new analyzer starts immediately
- Won't exceed `max_size`

### Scaling Down
**Trigger:** Queue depth <= `scale_down_threshold`

**Actions:**
- Removes `scale_down_count` analyzers (gracefully stops them)
- Won't go below `min_size`

### Cooldown Period
After each scaling action, the autoscaler waits `cooldown_seconds` before considering another scale. This prevents rapid oscillation and gives the system time to stabilize.

## Configuration

```python
from distributor.autoscaler import Autoscaler

autoscaler = Autoscaler(
    analyzer_pool=analyzer_pool,
    get_queue_depth_func=lambda: get_queue_depth(distributor_url),
    
    # Capacity limits
    min_size=2,              # Minimum analyzers (always running)
    max_size=10,             # Maximum analyzers (cost ceiling)
    
    # Thresholds
    scale_up_threshold=50,   # Queue depth to trigger scale up
    scale_down_threshold=10, # Queue depth to trigger scale down
    
    # Timing
    check_interval=10.0,     # Check every 10 seconds
    cooldown_seconds=30.0,   # Wait 30s between scaling actions
    
    # Scale amounts
    scale_up_count=2,        # Add 2 analyzers per scale-up
    scale_down_count=1       # Remove 1 analyzer per scale-down
)

await autoscaler.start()
```

## Best Practices

### 1. **Set Appropriate Thresholds**

```python
# For bursty workloads
scale_up_threshold=30    # React quickly to spikes
scale_down_threshold=5   # Be conservative about scaling down

# For steady workloads
scale_up_threshold=100   # Allow more queuing before scaling
scale_down_threshold=20  # Scale down more aggressively
```

### 2. **Tune Cooldown Period**

```python
# Fast-changing load
cooldown_seconds=15.0    # Quick response

# Stable load with occasional spikes
cooldown_seconds=60.0    # Prevent thrashing
```

### 3. **Choose Scale Increments Wisely**

```python
# Gradual scaling (cost-conscious)
scale_up_count=1
scale_down_count=1

# Aggressive scaling (performance-focused)
scale_up_count=3
scale_down_count=1
```

### 4. **Set Realistic Min/Max**

```python
# Development/testing
min_size=1
max_size=5

# Production
min_size=5     # Ensure baseline capacity
max_size=50    # Control costs
```

## Example: Handling Traffic Spike

```python
# Initial state: 2 analyzers, queue depth: 5
# ✓ Normal operation

# Traffic spike: 100 logs/sec
# Queue depth rises to 60
# 🔼 SCALE UP: Add 2 analyzers (now 4 total)

# Still high load
# Queue depth: 85
# Wait cooldown...
# 🔼 SCALE UP: Add 2 analyzers (now 6 total)

# Queue processing catches up
# Queue depth drops to 8
# Wait cooldown...
# 🔽 SCALE DOWN: Remove 1 analyzer (now 5 total)

# Load normalizes
# Queue depth: 3
# 🔽 SCALE DOWN: Remove 1 analyzer (now 4 total)
# Eventually returns to min_size
```

## Monitoring

```python
stats = autoscaler.get_stats()
print(f"Current size: {stats['current_size']}")
print(f"Scale ups: {stats['total_scale_ups']}")
print(f"Scale downs: {stats['total_scale_downs']}")
print(f"In cooldown: {stats['in_cooldown']}")
```

## Running the Demo

```bash
# Terminal 1: Start distributor
python run_distributor.py

# Terminal 2: Run autoscaling demo
cd demo
python autoscaling_demo.py
```

The demo will:
1. Start with 2 analyzers (minimal capacity)
2. Apply heavy load (10 emitters)
3. Watch autoscaler scale up to handle load
4. Stop load and watch scale down

## Integration with Your Code

```python
async def main():
    # Create analyzer pool
    analyzer_pool = AnalyzerPool(
        distributor_url="http://localhost:8000",
        num_analyzers=2  # Start small
    )
    await analyzer_pool.start()
    
    # Create and start autoscaler
    autoscaler = Autoscaler(
        analyzer_pool=analyzer_pool,
        get_queue_depth_func=lambda: get_queue_depth(distributor_url),
        min_size=2,
        max_size=10
    )
    await autoscaler.start()
    
    # Your application runs here...
    # Autoscaler continuously adjusts capacity
    
    # Cleanup
    await autoscaler.stop()
    await analyzer_pool.stop()
```

## Troubleshooting

### Autoscaler not scaling up
- Check `scale_up_threshold` isn't too high
- Verify queue depth is actually rising
- Check cooldown period hasn't just elapsed

### Autoscaler scaling up too aggressively
- Increase `cooldown_seconds`
- Decrease `scale_up_count`
- Raise `scale_up_threshold`

### Pool oscillating (up and down rapidly)
- Increase `cooldown_seconds`
- Widen gap between thresholds
- Use asymmetric scale counts (scale up faster, down slower)

## Cost Optimization

```python
# Conservative autoscaling (minimize costs)
Autoscaler(
    min_size=1,              # Single analyzer when idle
    max_size=5,              # Cap maximum cost
    scale_up_threshold=100,  # Tolerate more queuing
    scale_down_threshold=10,
    cooldown_seconds=120,    # Long cooldown
    scale_up_count=1,        # Gradual increases
    scale_down_count=1
)
```

## Performance Optimization

```python
# Aggressive autoscaling (maximize throughput)
Autoscaler(
    min_size=5,              # Always have baseline capacity
    max_size=50,             # High ceiling
    scale_up_threshold=20,   # React quickly
    scale_down_threshold=5,
    cooldown_seconds=15,     # Short cooldown
    scale_up_count=3,        # Rapid increases
    scale_down_count=1       # Gradual decreases
)
```

