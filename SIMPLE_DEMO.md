# Simple Demo Guide

## What the Demo Does

The demo is now **super simple** - just one file that:

1. ✅ Creates analyzer pool (4 workers)
2. ✅ Creates emitter pool (10 log generators)
3. ✅ Runs for 30 seconds (or 1000 logs)
4. ✅ Shuts down gracefully
5. ✅ Shows statistics

**No classes, no boilerplate, just a straightforward script!**

## Running the Demo

### Terminal 1: Start Distributor

```bash
python -m uvicorn distributor.distributor:app --port 8000
```

### Terminal 2: Run Demo

```bash
python demo/demo_setup.py
```

That's it! 🎉

## What You'll See

```
============================================================
LOGS DISTRIBUTOR DEMO - Pull-Based Work Queue
============================================================
✓ Distributor is running

Creating analyzer pool...
Creating emitter pool...

============================================================
STARTING SYSTEM
============================================================
✓ All components started

Running for up to 30 seconds or 1000 logs...

[5s] Emitted: 51, Processed: 45, Queue: 2
[10s] Emitted: 102, Processed: 95, Queue: 1
[15s] Emitted: 153, Processed: 147, Queue: 0
...

============================================================
SHUTTING DOWN
============================================================
✓ Emitters stopped
✓ All tasks processed
✓ Analyzers stopped

============================================================
FINAL STATISTICS
============================================================

Distributor:
  Total Received: 306
  Total Completed: 306
  Queue Depth: 0

Distribution:
  analyzer-1: 40.2% (expected: 40%) ✓
  analyzer-2: 30.1% (expected: 30%) ✓
  analyzer-3: 19.9% (expected: 20%) ✓
  analyzer-4: 9.8%  (expected: 10%) ✓

============================================================
DEMO COMPLETE
============================================================
```

## Configuration

Edit these variables in `demo_setup.py`:

```python
# How long to run
run_duration_seconds = 30

# Or stop after this many logs
max_logs_cutoff = 1000

# Analyzer weights (capacity)
weights=[0.4, 0.3, 0.2, 0.1]

# Number of log emitters
num_emitters=10

# Log emission rate
base_interval=0.5  # seconds
interval_jitter=0.2  # ± variation
```

## The Code

Here's the entire main logic (simplified view):

```python
# Create pools
analyzer_pool = AnalyzerPool(
    distributor_url="http://localhost:8000",
    num_analyzers=4,
    weights=[0.4, 0.3, 0.2, 0.1]
)

emitter_pool = LogEmitterPool(
    distributor_url="http://localhost:8000",
    num_emitters=10,
    base_interval=0.5
)

# Start
await analyzer_pool.start()
await emitter_pool.start()

# Run for duration
for i in range(30):
    await asyncio.sleep(1)
    # Print stats every 5 seconds

# Stop
await emitter_pool.stop()
await analyzer_pool.wait_for_idle()
await analyzer_pool.stop()

# Show stats
distribution = analyzer_pool.get_distribution()
print(distribution)
```

That's literally it! No complex classes, just create → start → run → stop → stats.

## Customization Examples

### Run Longer

```python
run_duration_seconds = 60  # 1 minute
```

### More Logs

```python
max_logs_cutoff = 5000  # Stop after 5000 logs
```

### Different Weights

```python
# One heavy analyzer
weights=[0.7, 0.1, 0.1, 0.1]

# All equal
weights=0.25  # or [0.25, 0.25, 0.25, 0.25]

# More analyzers
num_analyzers=10
```

### Faster/Slower Logs

```python
# Fast
num_emitters=20
base_interval=0.2

# Slow
num_emitters=5
base_interval=2.0
```

## Advanced Demos

For more complex scenarios, see:

- `demo/analyzer_pool_demo.py` - Various analyzer configurations
- `demo/emitter_pool_demo.py` - Various emitter patterns
- `load_test.py` - High-throughput load testing

## Troubleshooting

### "Cannot connect to distributor"

Start the distributor first:
```bash
python -m uvicorn distributor.distributor:app --port 8000
```

### "Import errors"

Install dependencies:
```bash
pip install -r requirements.txt
```

### Distribution doesn't match exactly

This is normal! With small sample sizes, there's variance. Run longer or with more logs for better convergence.

---

**Simple, clean, and easy to understand! 🚀**

