# High-Throughput Logs Distributor

A scalable, pull-based work queue system for distributing and processing log messages with automatic load balancing, failure resilience, and autoscaling capabilities.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                EMITTER POOL                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │Emitter-1 │  │Emitter-2 │  │Emitter-3 │  │Emitter-4 │  │Emitter-5 │     │
│  │  emit()  │  │  emit()  │  │  emit()  │  │  emit()  │  │  emit()  │     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
└───────┼─────────────┼─────────────┼─────────────┼─────────────┼────────────┘
        │             │             │             │             │
        │   HTTP POST /submit (push logs to distributor)       │
        └─────────────┴─────────────┴─────────────┴─────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DISTRIBUTOR                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  FastAPI Service (Port 8000)                                           │ │
│  │                                                                         │ │
│  │  POST /submit        - Receive logs from emitters                      │ │
│  │  POST /get_work      - Analyzers pull work (returns log if available) │ │
│  │  POST /status        - Receive status updates & heartbeats             │ │
│  │  GET  /stats         - Get system statistics                           │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────────┐   │
│  │   Task Queue    │  │  In-Progress Map │  │  Background Monitor     │   │
│  │   (FIFO deque)  │  │  {task_id: Task} │  │  - Heartbeat timeout    │   │
│  │                 │  │  + heartbeats    │  │  - Task requeuing       │   │
│  │  [Task, Task,   │  │                  │  │  - Runs every 5s        │   │
│  │   Task, ...]    │  │                  │  │                         │   │
│  └─────────────────┘  └──────────────────┘  └─────────────────────────┘   │
└───────────────────────┬──────────────────────────────────────┬──────────────┘
                        │                                      │
        HTTP POST /get_work (pull)              HTTP POST /status (heartbeat)
                        │                                      │
        ┌───────────────┴──────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             ANALYZER POOL                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Autoscaler (optional)                                              │    │
│  │  - Monitors queue depth                                             │    │
│  │  - Scales up when queue > threshold                                 │    │
│  │  - Scales down when queue < threshold                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Weight-Based Load Balancing (Implicit):                                    │
│                                                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │   Analyzer-1     │  │   Analyzer-2     │  │   Analyzer-3     │          │
│  │   weight: 0.2    │  │   weight: 0.3    │  │   weight: 0.5    │          │
│  │   ──────────     │  │   ──────────     │  │   ──────────     │          │
│  │   max_tasks: 2   │  │   max_tasks: 3   │  │   max_tasks: 5   │          │
│  │                  │  │                  │  │                  │          │
│  │  ┌─────┐┌─────┐  │  │  ┌─────┐┌─────┐ │  │  ┌─────┐┌─────┐ │          │
│  │  │Task ││Task │  │  │  │Task ││Task │ │  │  │Task ││Task │ │          │
│  │  │  1  ││  2  │  │  │  │  3  ││  4  │ │  │  │  6  ││  7  │ │          │
│  │  └─────┘└─────┘  │  │  └─────┘└─────┘ │  │  └─────┘└─────┘ │          │
│  │                  │  │  ┌─────┐        │  │  ┌─────┐┌─────┐ │          │
│  │  (polling slow)  │  │  │Task │        │  │  │Task ││Task │ │          │
│  │                  │  │  │  5  │        │  │  │  8  ││  9  │ │          │
│  │                  │  │  └─────┘        │  │  └─────┘└─────┘ │          │
│  │                  │  │                  │  │  ┌─────┐        │          │
│  │                  │  │  (polling med)   │  │  │Task │        │          │
│  │                  │  │                  │  │  │ 10  │        │          │
│  └──────────────────┘  └──────────────────┘  │  └─────┘        │          │
│                                               │                  │          │
│                                               │  (polling fast)  │          │
│                                               └──────────────────┘          │
│                                                                              │
│  Result: Analyzer-3 processes ~50% of work, Analyzer-2 ~30%, Analyzer-1 ~20%│
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Descriptions

### 1. Emitter

**Purpose**: Generates and sends log messages to the distributor.

**Key Features**:
- Generates realistic log messages with various levels (INFO, WARN, ERROR, etc.)
- Sends logs via HTTP POST to `/submit` endpoint
- Runs independently with configurable emission intervals
- Includes metadata (timestamp, source, request IDs)

**Implementation**: `emitter/log_emitter.py` - `LogEmitter` class

---

### 2. Emitter Pool

**Purpose**: Manages multiple emitters running concurrently.

**Key Features**:
- Creates and manages N emitter instances
- Each emitter runs in its own asyncio task
- Randomized emission intervals for realistic traffic patterns
- Thread-safe statistics tracking (total emitted, per-emitter counts)
- Graceful start/stop of all emitters

**Implementation**: `emitter/log_emitter.py` - `LogEmitterPool` class

**Configuration**:
```python
emitter_pool = LogEmitterPool(
    distributor_url="http://localhost:8000",
    num_emitters=5,           # Number of concurrent emitters
    base_interval=1.0,        # Base emission interval (seconds)
    interval_jitter=0.5       # Random variance (±0.5s)
)
```

---

### 3. Analyzer

**Purpose**: Worker that pulls and processes log messages from the distributor.

**Key Features**:
- **Pull-based**: Actively requests work from distributor (no push)
- **Weighted concurrency**: Weight determines max concurrent tasks
- **Heartbeat mechanism**: Sends periodic status updates
- **Graceful failure handling**: Tasks timeout and requeue if analyzer fails
- **Statistics tracking**: Tracks processed count, failures, throughput

**Weight to Concurrency Conversion**:
```python
weight = 0.3
max_concurrent_tasks = max(1, int(weight * 10))  # = 3 tasks

# Examples:
# weight 0.1 → 1 concurrent task
# weight 0.2 → 2 concurrent tasks
# weight 0.3 → 3 concurrent tasks
# weight 0.5 → 5 concurrent tasks
# weight 1.0 → 10 concurrent tasks
```

**How Load Balancing Works (Implicit)**:

The system achieves weighted load distribution **naturally** through the pull model:

1. **Higher weight = More capacity**
   - Analyzer with weight 0.5 has 5 task slots
   - Analyzer with weight 0.2 has 2 task slots

2. **Higher capacity = More frequent pulling**
   - Analyzer with 5 slots completes tasks faster → polls more often
   - Analyzer with 2 slots completes tasks slower → polls less often

3. **Result: Proportional work distribution**
   - Over time, work naturally distributes according to weights
   - No explicit routing logic needed!
   - Self-balancing through pull frequency

**Example**:
```
3 Analyzers: weights [0.2, 0.3, 0.5]
Total work: 1000 tasks

Expected distribution:
- Analyzer-1 (0.2): ~200 tasks (20%)
- Analyzer-2 (0.3): ~300 tasks (30%)
- Analyzer-3 (0.5): ~500 tasks (50%)

Actual distribution matches expected within 1-2%!
```

**Implementation**: `analyzer/analyzer.py` - `Analyzer` class

---

### 4. Analyzer Pool

**Purpose**: Manages multiple analyzers with flexible capacity and optional autoscaling.

**Key Features**:
- Creates and manages N analyzer instances
- Configurable weights per analyzer (or default patterns)
- **Autoscaling** (optional):
  - Monitors distributor queue depth
  - Scales up when queue exceeds threshold
  - Scales down when queue is low
  - Respects min/max size limits
  - Cooldown period prevents oscillation
- Preserves stats from scaled-down analyzers
- Distribution analysis (expected vs actual)

**Autoscaling Behavior**:
```python
analyzer_pool = AnalyzerPool(
    distributor_url="http://localhost:8000",
    num_analyzers=2,              # Start with 2
    enable_autoscaling=True,      # Enable autoscaling
    min_size=2,                   # Never go below 2
    max_size=10,                  # Never exceed 10
    scale_up_threshold=50,        # Scale up if queue > 50
    scale_down_threshold=10,      # Scale down if queue < 10
    scale_up_count=2,             # Add 2 at a time (weight 0.5 each)
    scale_down_count=1            # Remove 1 at a time
)
```

**Scaling Actions**:
- **Scale Up**: Adds high-capacity analyzers (weight 0.5 = 5 concurrent tasks)
- **Scale Down**: Removes excess analyzers, preserves their stats
- **Cooldown**: Waits 30s between scaling actions to stabilize

**Implementation**: `analyzer/analyzer.py` - `AnalyzerPool` class

---

### 5. Distributor

**Purpose**: Central work queue and task distribution service.

**Key Features**:

**API Endpoints**:
- `POST /submit` - Emitters submit logs
- `POST /get_work` - Analyzers request work
- `POST /status` - Analyzers send status updates & heartbeats
- `GET /stats` - Get system statistics
- `GET /metrics` - Get scaling metrics

**Core Components**:

1. **Task Queue** (FIFO deque)
   - Stores pending tasks
   - New tasks appended to back
   - Work requests pull from front
   - Priority requeuing (failed tasks go to front)

2. **In-Progress Map**
   - Tracks tasks currently being processed
   - Maps `task_id` → `Task` object
   - Includes last heartbeat timestamp
   - Used for timeout detection

3. **Background Monitor** (runs every 5 seconds)
   - Checks heartbeat timeouts
   - Requeues timed-out tasks (30s timeout)
   - Monitors for autoscaling triggers

4. **Data Store**
   - Separates task metadata from actual log data
   - Efficient memory usage
   - Fast lookup by task ID

**Failure Resilience**:
- Heartbeat monitoring detects failed analyzers
- Tasks automatically timeout after 30s of no heartbeat
- Failed tasks requeued to front of queue
- Other analyzers pick up the work
- **No data loss** - all logs eventually processed

**Colored Logging**:
- All distributor logs prefixed with `[DISTRIBUTOR]` in cyan
- Different colors for different events:
  - 🟢 Green: RECEIVED LOG, TASK COMPLETED
  - 🔵 Blue: ASSIGNED WORK
  - 🟡 Yellow: HEARTBEAT
  - 🟣 Magenta: TASK FAILED

**Implementation**: `distributor/distributor.py`

---

## Running the Demos

### Prerequisites

```bash
# Create virtual environment
python3.14 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Terminal Setup

All demos require the distributor running in a separate terminal:

**Terminal 1 (Distributor)**:
```bash
python run_distributor.py
```

Then run any demo in Terminal 2:

---

### Demo 1: Basic System Demo (`demo_setup.py`)

Demonstrates weighted load distribution with 3 fixed-capacity analyzers (weights 0.2, 0.3, 0.5) and shows that work naturally distributes proportionally (20%, 30%, 50%).

```bash
python demo/demo_setup.py
```

---

### Demo 2: Autoscaling Demo (`autoscaling_demo.py`)

Starts with 2 low-capacity analyzers, applies heavy load to trigger autoscaling (watch for 🔼 SCALING UP), then reduces load to demonstrate scale-down (🔽 SCALING DOWN).

```bash
python demo/autoscaling_demo.py
```

---

### Demo 3: Failure Resilience Demo (`failure_demo.py`)

Randomly kills analyzers during operation (💀 FAILURE INJECTED) to prove the distributor detects timeouts, requeues failed tasks, and achieves 100% completion with no data loss.

```bash
python demo/failure_demo.py
```

---

## Key Features Summary

### ✅ Pull-Based Architecture
- Analyzers actively request work (no push)
- Natural backpressure handling
- No complex routing logic needed

### ✅ Weighted Load Balancing
- Weight determines concurrent task capacity
- Load automatically distributes proportionally
- Self-balancing through pull frequency

### ✅ Autoscaling
- Monitors queue depth automatically
- Adds high-capacity analyzers when needed
- Removes excess capacity when load decreases
- Configurable thresholds and cooldown

### ✅ Failure Resilience
- Heartbeat-based health monitoring
- Automatic timeout detection (30s)
- Failed tasks requeued automatically
- No data loss despite analyzer failures

### ✅ Comprehensive Logging
- Colored distributor logs for visibility
- Per-component log prefixes (emitter-1, analyzer-2, etc.)
- Event-specific colors (received, assigned, completed, failed)
- Detailed statistics and distribution analysis

### ✅ Accurate Metrics
- Thread-safe statistics tracking
- Stats preserved from scaled-down/killed analyzers
- Graceful shutdown with queue draining
- Perfect alignment: Emitted = Received = Processed

---

## Project Structure

```
.
├── distributor/
│   ├── distributor.py      # Core distributor logic
│   └── models.py           # Data models (LogMessage, Task, etc.)
│
├── analyzer/
│   ├── analyzer.py         # Analyzer and AnalyzerPool classes
│   └── __init__.py
│
├── emitter/
│   ├── log_emitter.py      # LogEmitter and LogEmitterPool classes
│   └── __init__.py
│
├── demo/
│   ├── demo_setup.py       # Basic system demo
│   ├── autoscaling_demo.py # Autoscaling demonstration
│   └── failure_demo.py     # Failure resilience demo
│
├── run_distributor.py      # Start distributor server
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

---

## Configuration Tips

### For High Throughput
```python
# More emitters
emitter_pool = LogEmitterPool(num_emitters=20)

# More high-weight analyzers
analyzer_pool = AnalyzerPool(
    num_analyzers=10,
    weights=0.5  # All high capacity
)
```

### For Testing Autoscaling
```python
# Aggressive autoscaling
analyzer_pool = AnalyzerPool(
    enable_autoscaling=True,
    scale_up_threshold=20,      # Scale up quickly
    scale_check_interval=3.0,   # Check frequently
    scale_cooldown=10.0,        # Short cooldown
    scale_up_count=3            # Add capacity aggressively
)
```

### For Testing Failure Resilience
```python
# In failure_demo.py, adjust:
failure_rate=0.6  # Kill 60% of checks (more chaos!)
```

---

## Additional Documentation

- **`NEW_FEATURES.md`** - Overview of autoscaling and failure resilience
- **`AUTOSCALING_GUIDE.md`** - Detailed autoscaling configuration and tuning
- **`DISTRIBUTOR_LOGGING.md`** - Guide to distributor log format and colors

---

## Requirements

- Python 3.10+
- FastAPI
- Uvicorn
- Pydantic
- httpx

Install with:
```bash
pip install -r requirements.txt
```

---

## License

MIT
