# Distributor Logging Guide

## Overview

The distributor now logs all key operations with **colored output** for easy visibility. All distributor logs are prefixed with `[DISTRIBUTOR]` in **bold cyan**.

## Log Types

### 1. **RECEIVED LOG** (Green)
Logged when the distributor receives a log from an emitter.

**Format:**
```
[DISTRIBUTOR] RECEIVED LOG | task=abc12345 | source=emitter-1 | level=INFO | msg='User logged in successfully...' | queue_depth=42
```

**Information shown:**
- Task ID (first 8 chars)
- Source (emitter ID)
- Log level
- Message preview (first 40 chars)
- Current queue depth

---

### 2. **ASSIGNED WORK** (Blue)
Logged when the distributor assigns work to an analyzer in response to a `get_work` call.

**Format:**
```
[DISTRIBUTOR] ASSIGNED WORK | task=abc12345 | to=analyzer-3 | level=INFO | msg='User logged in successfully...' | queue_depth=41
```

**Information shown:**
- Task ID (first 8 chars)
- Analyzer ID (destination)
- Log level
- Message preview (first 40 chars)
- Current queue depth

---

### 3. **HEARTBEAT** (Yellow)
Logged when a heartbeat is received from an analyzer (status update with IN_PROGRESS).

**Format:**
```
[DISTRIBUTOR] HEARTBEAT | task=abc12345 | from=analyzer-3 | status=IN_PROGRESS
```

**Information shown:**
- Task ID (first 8 chars)
- Analyzer ID (source)
- Status

---

### 4. **TASK COMPLETED** (Green)
Logged when a task is successfully completed.

**Format:**
```
[DISTRIBUTOR] TASK COMPLETED | task=abc12345 | by=analyzer-3 | status=COMPLETED
```

**Information shown:**
- Task ID (first 8 chars)
- Analyzer ID (who completed it)
- Status

---

### 5. **TASK FAILED** (Magenta)
Logged when a task fails.

**Format:**
```
[DISTRIBUTOR] TASK FAILED | task=abc12345 | by=analyzer-3 | status=FAILED | reason=Connection timeout
```

**Information shown:**
- Task ID (first 8 chars)
- Analyzer ID (who reported failure)
- Status
- Failure reason/message

---

## Color Scheme

| Event Type | Color | Purpose |
|------------|-------|---------|
| All distributor logs | **Bold Cyan** prefix | Easy identification |
| RECEIVED LOG | Green | New work arriving |
| ASSIGNED WORK | Blue | Work being distributed |
| HEARTBEAT | Yellow | Keep-alive signals |
| TASK COMPLETED | Green | Success |
| TASK FAILED | Magenta | Errors/failures |

## Example Console Output

When you run the demo, you'll see colorized logs like:

```
2025-11-09 16:30:45,123 - [DISTRIBUTOR] RECEIVED LOG | task=a1b2c3d4 | source=emitter-1 | level=INFO | msg='Processing payment for order #12345...' | queue_depth=5
2025-11-09 16:30:45,234 - [DISTRIBUTOR] ASSIGNED WORK | task=a1b2c3d4 | to=analyzer-2 | level=INFO | msg='Processing payment for order #12345...' | queue_depth=4
2025-11-09 16:30:45,345 - [analyzer.analyzer-2] - Processing task a1b2c3d4: Processing payment for order #12345
2025-11-09 16:30:45,456 - [DISTRIBUTOR] HEARTBEAT | task=a1b2c3d4 | from=analyzer-2 | status=IN_PROGRESS
2025-11-09 16:30:47,567 - [analyzer.analyzer-2] - Completed task a1b2c3d4
2025-11-09 16:30:47,678 - [DISTRIBUTOR] TASK COMPLETED | task=a1b2c3d4 | by=analyzer-2 | status=COMPLETED
```

## Benefits

1. **Easy Tracing**: Follow a single task through the entire pipeline
2. **Quick Debugging**: Spot failures and bottlenecks at a glance
3. **Visual Clarity**: Color-coded events help distinguish log types
4. **Complete Context**: Each log includes all relevant metadata

## Implementation Details

- Uses ANSI color codes for terminal output
- Custom `ColoredFormatter` class formats distributor logs
- Colors work in most modern terminals (Linux, macOS, Windows 10+)
- Falls back gracefully in terminals that don't support colors

