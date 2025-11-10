# Quick Start Guide - Pull-Based Work Queue

## 🚀 Get Started in 5 Minutes

### Step 1: Install Dependencies

```bash
cd /Users/josephjin/Downloads/1108-distributor
pip install -r requirements.txt
```

### Step 2: Start the Distributor

Open Terminal 1:

```bash
python -m uvicorn distributor.distributor:app --port 8000
```

You should see:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 3: Run the Demo

Open Terminal 2:

```bash
python demo/demo_setup.py
```

This will:
1. ✅ Create analyzer pool (4 analyzers with weights 0.4, 0.3, 0.2, 0.1)
2. ✅ Create emitter pool (10 emitters)
3. ✅ Run for 30 seconds (or until 1000 logs emitted)
4. ✅ Shut down gracefully
5. ✅ Show final statistics

### Expected Output

```
============================================================
LOGS DISTRIBUTOR DEMO - Pull-Based Work Queue
============================================================
✓ Distributor is running at http://localhost:8000

Creating analyzer pool...
Creating emitter pool...

============================================================
STARTING SYSTEM
============================================================
Started analyzer-1 with weight 0.4 (max concurrent: 4)
Started analyzer-2 with weight 0.3 (max concurrent: 3)
Started analyzer-3 with weight 0.2 (max concurrent: 2)
Started analyzer-4 with weight 0.1 (max concurrent: 1)
✓ All components started

Running for up to 30 seconds or 1000 logs...

[5s] Emitted: 51, Processed: 45, Queue: 2
[10s] Emitted: 102, Processed: 95, Queue: 1
[15s] Emitted: 153, Processed: 147, Queue: 0
[20s] Emitted: 204, Processed: 198, Queue: 0
[25s] Emitted: 255, Processed: 250, Queue: 0
[30s] Emitted: 306, Processed: 301, Queue: 0

============================================================
SHUTTING DOWN
============================================================
Stopping emitter pool...
✓ Emitters stopped
Waiting for analyzers to finish processing...
✓ All tasks processed
Stopping analyzer pool...
✓ Analyzers stopped

============================================================
FINAL STATISTICS
============================================================

Distributor:
  Total Received: 306
  Total Completed: 306
  Total Failed: 0
  Queue Depth: 0

Emitters:
  Total Emitted: 306
  Num Emitters: 10

Analyzers:
  Total Processed: 306
  Total Failed: 0

Distribution:
  Analyzer        Weight     Processed    Actual %     Expected %
  ------------------------------------------------------------
  analyzer-1      0.40       123          40.2         40%
  analyzer-2      0.30       92           30.1         30%
  analyzer-3      0.20       61           19.9         20%
  analyzer-4      0.10       30           9.8          10%

============================================================
DEMO COMPLETE
============================================================
```

## ✅ Key Features Demonstrated

1. **Pull-Based Work Queue**: Analyzers actively request work
2. **Weight-Based Distribution**: Work distributed according to weights (40/30/20/10%)
3. **Concurrent Processing**: Each analyzer processes multiple tasks concurrently
4. **Heartbeat Monitoring**: Status updates serve as heartbeats
5. **High Throughput**: Processes hundreds of tasks per second

## 🧪 Quick Tests

### Test 1: Load Testing

```bash
# Terminal 3 (while demo is running or after)
python load_test.py --logs 1000 --concurrent 50
```

### Test 2: Interactive Demo

```bash
# Stop the automated demo (Ctrl+C)
# Run interactive mode
python demo/demo_setup.py interactive
```

Then choose from menu:
- Send 100/500/1000 logs
- Monitor stats
- View distribution

### Test 3: Manual Analyzer

Start your own analyzer:

```bash
python analyzer/analyzer.py my-analyzer http://localhost:8000 0.5
```

### Test 4: Send Logs Programmatically

Create `test_emit.py`:

```python
import asyncio
from emitter.log_emitter import LogEmitter

async def main():
    emitter = LogEmitter("http://localhost:8000")
    
    # Send a log
    task_id = await emitter.emit(
        message="Test message",
        level="INFO",
        source="test-app"
    )
    
    print(f"Submitted task: {task_id}")
    await emitter.close()

asyncio.run(main())
```

Run it:

```bash
python test_emit.py
```

## 📊 Monitoring

### Watch Stats in Real-Time

```bash
# Terminal 3
watch -n 1 'curl -s http://localhost:8000/stats | python -m json.tool'
```

### Check Specific Endpoints

```bash
# Distributor health
curl http://localhost:8000/health

# Queue statistics
curl http://localhost:8000/stats

# Scaling metrics
curl http://localhost:8000/metrics
```

## 🎯 What to Show in Interview

### Demo Flow (5-7 minutes)

1. **Start Distributor** (30 seconds)
   ```bash
   python -m uvicorn distributor.distributor:app --port 8000
   ```

2. **Run Automated Demo** (2-3 minutes)
   ```bash
   python demo/demo_setup.py
   ```
   
   **Point out:**
   - Analyzers with different weights (0.4, 0.3, 0.2, 0.1)
   - Concurrent task processing
   - Real-time queue depth monitoring
   - Final distribution matches weights

3. **Show Architecture** (1 minute)
   - Pull model (analyzers request work)
   - Queue + In-Progress tracking
   - Heartbeat monitoring
   - Weight-based concurrency

4. **Demonstrate Failure Recovery** (2-3 minutes)
   ```bash
   # Terminal 1: Run demo interactively
   python demo/demo_setup.py interactive
   
   # Terminal 2: Monitor
   watch -n 1 'curl -s http://localhost:8000/stats'
   
   # Terminal 1: Send lots of logs
   Menu > 3 (send 1000 logs)
   
   # Terminal 3: Kill an analyzer
   # (find pid): ps aux | grep analyzer
   # kill <pid>
   
   # Watch Terminal 2: See tasks get requeued after timeout
   ```

5. **Run Load Test** (1 minute)
   ```bash
   python load_test.py --logs 5000 --concurrent 100 --burst
   ```
   
   **Point out:**
   - High throughput (1000+ logs/sec)
   - All tasks complete successfully
   - Distribution still respects weights

## 🔑 Key Talking Points

### 1. Architecture Choice: Pull vs Push

**"I chose a pull-based architecture because..."**
- Analyzers control their own rate (backpressure handling)
- Natural load balancing (work at their own pace)
- Better failure recovery (tasks stay in queue)
- No risk of overwhelming workers

### 2. Weight-Based Concurrency

**"Weight determines concurrent capacity..."**
- Weight 0.4 → 4 concurrent tasks
- Weight 0.3 → 3 concurrent tasks
- Formula: `max(1, int(weight * 10))`
- Over time, distribution matches weights

### 3. Heartbeat Monitoring

**"Status updates serve dual purpose..."**
- Report progress (in_progress, completed, failed)
- Act as heartbeat (liveness check)
- If no heartbeat for 30 seconds → timeout
- Task automatically requeued (retry with backoff)

### 4. Scalability

**"System scales both vertically and horizontally..."**
- Vertical: Add more concurrent tasks per analyzer (increase weight)
- Horizontal: Add more analyzers (scaler manages pool)
- Auto-scaling based on backpressure (queue depth / active analyzers)
- Production: Integrate with K8s HPA or AWS ECS

### 5. Production Ready Features

**"For production, I would add..."**
- Persistent queue (Redis, RabbitMQ, Kafka)
- Distributed distributor (stateless, external state)
- Observability (Prometheus metrics, OpenTelemetry tracing)
- Priority queues (different priorities for different logs)
- Dead letter queue (for permanently failed tasks)

## 🐛 Troubleshooting

### "Distributor won't start"

```bash
# Check if port 8000 is in use
lsof -i :8000

# If something is using it, kill it or use different port
python -m uvicorn distributor.distributor:app --port 8001
```

### "Analyzers not processing"

```bash
# Check distributor is running
curl http://localhost:8000/health

# Check logs
python -m uvicorn distributor.distributor:app --port 8000 --log-level debug
```

### "Tasks stuck in queue"

```bash
# Make sure analyzers are running
# Check stats
curl http://localhost:8000/stats

# Start more analyzers
python analyzer/analyzer.py analyzer-5 http://localhost:8000 0.5
```

### "Distribution doesn't match weights"

- **Normal**: With few tasks (<100), distribution varies
- **Solution**: Send more tasks (1000+) for convergence
- **Check**: Ensure analyzers have different weights

## 📁 Files Overview

```
logs-distributor/
├── distributor/
│   ├── models.py           # Data models (Task, LogMessage, etc.)
│   ├── distributor.py      # Core queue + FastAPI app
│   └── scaler.py           # Auto-scaling logic
│
├── analyzer/
│   └── analyzer.py         # Worker that pulls and processes
│
├── emitter/
│   └── log_emitter.py      # Client to submit logs
│
├── demo/
│   └── demo_setup.py       # Automated demo
│
├── load_test.py            # Load testing script
├── README.md              # Full documentation
├── ARCHITECTURE.md        # Deep dive into design
├── IMPROVEMENTS.md        # Production considerations
└── QUICKSTART.md          # This file
```

## 🎓 Understanding the Flow

### Log Submission

```
Application → LogEmitter.emit() → POST /submit → Distributor
                                                    ↓
                                                Task created
                                                    ↓
                                                Added to queue
```

### Work Distribution

```
Analyzer → Request work (POST /get_work) → Distributor
                                              ↓
                                          Dequeue task
                                              ↓
                                      Move to in-progress
                                              ↓
                                        Return to analyzer
```

### Task Processing

```
Analyzer receives task
    ↓
Send heartbeat (POST /status: in_progress)
    ↓
Process log (simulated work)
    ↓
Send completion (POST /status: completed)
    ↓
Distributor removes from in-progress
```

### Timeout & Requeue

```
Task in-progress without heartbeat > 30 seconds
              ↓
    Background monitor detects
              ↓
    Task requeued (to front of queue)
              ↓
    Next analyzer picks it up
```

## ⚡ Performance Tips

### For Demo

- Keep processing_delay = 0.1 (100ms)
- Start with 4 analyzers
- Send 500-1000 logs for good distribution

### For Load Testing

- Increase concurrent requests: `--concurrent 100`
- Use burst mode: `--burst`
- Send lots of logs: `--logs 10000`

### For Development

- Enable debug logging: `--log-level debug`
- Monitor stats: `watch -n 1 'curl -s http://localhost:8000/stats'`
- Start analyzers with different weights to see effect

## 🎉 Success Criteria

After running the demo, you should see:

✅ All 4 analyzers started  
✅ All logs processed (queue depth = 0)  
✅ No failures  
✅ Distribution matches weights (±5%)  
✅ High throughput (500-1000 logs/sec)  
✅ Heartbeats working (no timeouts in normal operation)  

---

**Ready? Run the demo and impress! 🚀**

```bash
python -m uvicorn distributor.distributor:app --port 8000 &
sleep 2
python demo/demo_setup.py
```
