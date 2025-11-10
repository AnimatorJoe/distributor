"""
Distributor: Core work queue and task distribution system.

The Distributor manages:
- A queue of pending tasks
- An in-progress map of tasks being processed
- A data store for actual log data
- Distribution of work to analyzers (pull model)
"""
import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Dict, Optional, Deque
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .models import (
    LogMessage, Task, TaskStatus, StatusUpdate,
    WorkRequest, WorkResponse, ScalingMetrics
)

logger = logging.getLogger(__name__)


# ANSI color codes for distributor logs
class Colors:
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds color to distributor logs."""
    
    def format(self, record):
        # Add color to distributor logs only
        if record.name.startswith('distributor'):
            original = super().format(record)
            # Wrap the entire log in cyan and bold
            return f"{Colors.BOLD}{Colors.CYAN}[DISTRIBUTOR]{Colors.RESET} {original}"
        return super().format(record)


class Distributor:
    """
    Core distributor that manages work queue and task distribution.
    
    Architecture:
    - Queue: deque of Task objects (FIFO, but priority items go to front)
    - In-Progress Map: Dict[task_id, Task] for active tasks
    - Data Store: Dict[task_id, LogMessage] for actual log data
    """
    
    def __init__(
        self,
        task_timeout_seconds: int = 30,
        backpressure_threshold: int = 100,
        monitor_interval_seconds: int = 5
    ):
        """
        Initialize the distributor.
        
        Args:
            task_timeout_seconds: Seconds without heartbeat before task timeout
            backpressure_threshold: Queue depth that triggers scaling
            monitor_interval_seconds: How often to run background monitor
        """
        # Task queue (FIFO)
        self.queue: Deque[Task] = deque()
        
        # In-progress tasks
        self.in_progress: Dict[str, Task] = {}
        
        # Completed/failed tasks (for stats)
        self.completed: Dict[str, Task] = {}
        self.failed: Dict[str, Task] = {}
        
        # Data store (actual log data)
        self.data_store: Dict[str, LogMessage] = {}
        
        # Locks for thread safety
        self.queue_lock = asyncio.Lock()
        self.in_progress_lock = asyncio.Lock()
        self.data_lock = asyncio.Lock()
        
        # Configuration
        self.task_timeout_seconds = task_timeout_seconds
        self.backpressure_threshold = backpressure_threshold
        self.monitor_interval_seconds = monitor_interval_seconds
        
        # Statistics
        self.total_tasks_received = 0
        self.total_tasks_completed = 0
        self.total_tasks_failed = 0
        self.total_tasks_requeued = 0
        
        # Background monitor task
        self.monitor_task: Optional[asyncio.Task] = None
        self.running = False
        
        # Reference to scaler (will be set externally)
        self.scaler = None
        
        # Use distributor logger
        self.logger = logging.getLogger('distributor.core')
        self.logger.info("Initialized")
    
    async def start(self):
        """Start the background monitor."""
        if self.running:
            return
        
        self.running = True
        self.monitor_task = asyncio.create_task(self._background_monitor())
        self.logger.info("Started")
    
    async def stop(self):
        """Stop the background monitor."""
        self.running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Stopped")
    
    async def submit_log(self, log: LogMessage) -> str:
        """
        Submit a log message for processing (called by Emitters).
        
        Args:
            log: The log message to process
            
        Returns:
            task_id: ID of the created task
        """
        # Create task
        task = Task()
        task.data_key = task.task_id
        
        async with self.queue_lock:
            self.queue.append(task)
            self.total_tasks_received += 1
        
        async with self.data_lock:
            self.data_store[task.task_id] = log
        
        # Log receipt with metadata
        self.logger.info(
            f"{Colors.GREEN}RECEIVED LOG{Colors.RESET} | "
            f"task={task.task_id[:8]} | "
            f"source={log.source} | "
            f"level={log.level} | "
            f"msg='{log.message[:40]}...' | "
            f"queue_depth={len(self.queue)}"
        )
        
        return task.task_id
    
    async def get_work(self, request: WorkRequest) -> WorkResponse:
        """
        Get work for an analyzer (called by Analyzers).
        
        Args:
            request: Work request from analyzer
            
        Returns:
            WorkResponse with task and data, or no work available
        """
        async with self.queue_lock:
            if not self.queue:
                return WorkResponse(
                    has_work=False,
                    message="Queue is empty"
                )
            
            # Get task from front of queue
            task = self.queue.popleft()
        
        # Move to in-progress
        task.assign_to_analyzer(request.analyzer_id)
        
        async with self.in_progress_lock:
            self.in_progress[task.task_id] = task
        
        # Get the actual data
        async with self.data_lock:
            log_data = self.data_store.get(task.task_id)
        
        if not log_data:
            logger.error(f"Data not found for task {task.task_id}")
            return WorkResponse(
                has_work=False,
                message="Data not found"
            )
        
        # Log work assignment with metadata
        self.logger.info(
            f"{Colors.BLUE}ASSIGNED WORK{Colors.RESET} | "
            f"task={task.task_id[:8]} | "
            f"to={request.analyzer_id} | "
            f"level={log_data.level} | "
            f"msg='{log_data.message[:40]}...' | "
            f"queue_depth={len(self.queue)}"
        )
        
        return WorkResponse(
            has_work=True,
            task_id=task.task_id,
            log_data=log_data,
            message="Work assigned"
        )
    
    async def update_status(self, update: StatusUpdate):
        """
        Receive status update from analyzer (serves as heartbeat).
        
        Args:
            update: Status update from analyzer
        """
        task_id = update.task_id
        
        async with self.in_progress_lock:
            if task_id not in self.in_progress:
                logger.warning(f"Received update for unknown task {task_id}")
                return
            
            task = self.in_progress[task_id]
            
            if update.status == TaskStatus.IN_PROGRESS:
                # Heartbeat
                task.update_heartbeat()
                self.logger.info(
                    f"{Colors.YELLOW}HEARTBEAT{Colors.RESET} | "
                    f"task={task_id[:8]} | "
                    f"from={update.analyzer_id} | "
                    f"status={update.status}"
                )
            
            elif update.status == TaskStatus.COMPLETED:
                # Task completed
                task.mark_completed()
                self.completed[task_id] = task
                del self.in_progress[task_id]
                self.total_tasks_completed += 1
                
                self.logger.info(
                    f"{Colors.GREEN}TASK COMPLETED{Colors.RESET} | "
                    f"task={task_id[:8]} | "
                    f"by={update.analyzer_id} | "
                    f"status={update.status}"
                )
                
                # Clean up data
                async with self.data_lock:
                    if task_id in self.data_store:
                        del self.data_store[task_id]
            
            elif update.status == TaskStatus.FAILED:
                # Task failed
                task.mark_failed()
                self.failed[task_id] = task
                del self.in_progress[task_id]
                self.total_tasks_failed += 1
                
                self.logger.warning(
                    f"{Colors.MAGENTA}TASK FAILED{Colors.RESET} | "
                    f"task={task_id[:8]} | "
                    f"by={update.analyzer_id} | "
                    f"status={update.status} | "
                    f"reason={update.message or 'N/A'}"
                )
                
                # Clean up data
                async with self.data_lock:
                    if task_id in self.data_store:
                        del self.data_store[task_id]
    
    async def _background_monitor(self):
        """
        Background monitor that runs periodically.
        
        Responsibilities:
        1. Check for timed-out tasks and requeue them
        2. Calculate backpressure and trigger scaling
        """
        while self.running:
            try:
                await self._check_timeouts()
                await self._check_scaling()
            except Exception as e:
                logger.error(f"Error in background monitor: {e}")
            
            await asyncio.sleep(self.monitor_interval_seconds)
    
    async def _check_timeouts(self):
        """Check for timed-out tasks and requeue them."""
        timed_out_tasks = []
        
        async with self.in_progress_lock:
            for task_id, task in list(self.in_progress.items()):
                if task.should_requeue(self.task_timeout_seconds):
                    timed_out_tasks.append((task_id, task))
        
        # Requeue timed-out tasks (to front of queue for priority)
        for task_id, task in timed_out_tasks:
            if task.requeue():
                # Put at front of queue (priority)
                async with self.queue_lock:
                    self.queue.appendleft(task)
                
                async with self.in_progress_lock:
                    if task_id in self.in_progress:
                        del self.in_progress[task_id]
                
                self.total_tasks_requeued += 1
                logger.warning(
                    f"Task {task_id} timed out (assigned to {task.assigned_to}), "
                    f"requeued (retry {task.retry_count}/{task.max_retries})"
                )
            else:
                # Max retries exceeded
                task.mark_failed()
                self.failed[task_id] = task
                self.total_tasks_failed += 1
                
                async with self.in_progress_lock:
                    if task_id in self.in_progress:
                        del self.in_progress[task_id]
                
                logger.error(
                    f"Task {task_id} exceeded max retries, marked as failed"
                )
    
    async def _check_scaling(self):
        """Check if scaling is needed based on backpressure."""
        metrics = await self.get_metrics()
        
        # If we have a scaler, notify it of metrics
        if self.scaler and metrics.queue_depth > self.backpressure_threshold:
            logger.info(
                f"High backpressure detected: queue_depth={metrics.queue_depth}, "
                f"threshold={self.backpressure_threshold}"
            )
            await self.scaler.check_scale_up(metrics)
    
    async def get_metrics(self) -> ScalingMetrics:
        """
        Get current metrics for scaling decisions.
        
        Returns:
            ScalingMetrics object
        """
        async with self.queue_lock:
            queue_depth = len(self.queue)
        
        async with self.in_progress_lock:
            in_progress_count = len(self.in_progress)
        
        # Get analyzer count from scaler
        total_analyzers = 0
        active_analyzers = 0
        if self.scaler:
            total_analyzers = self.scaler.get_total_analyzers()
            active_analyzers = self.scaler.get_active_analyzers()
        
        backpressure = (
            queue_depth / active_analyzers
            if active_analyzers > 0
            else queue_depth
        )
        
        return ScalingMetrics(
            queue_depth=queue_depth,
            in_progress_count=in_progress_count,
            total_analyzers=total_analyzers,
            active_analyzers=active_analyzers,
            queue_backpressure=backpressure
        )
    
    async def get_stats(self) -> Dict:
        """Get distributor statistics."""
        metrics = await self.get_metrics()
        
        return {
            "queue_depth": metrics.queue_depth,
            "in_progress": metrics.in_progress_count,
            "completed": len(self.completed),
            "failed": len(self.failed),
            "total_received": self.total_tasks_received,
            "total_completed": self.total_tasks_completed,
            "total_failed": self.total_tasks_failed,
            "total_requeued": self.total_tasks_requeued,
            "backpressure": metrics.queue_backpressure,
            "analyzers": {
                "total": metrics.total_analyzers,
                "active": metrics.active_analyzers
            }
        }


# FastAPI app for Distributor
app = FastAPI(title="Log Distributor", version="2.0.0")

# Global distributor instance
distributor: Optional[Distributor] = None


@app.on_event("startup")
async def startup():
    """Initialize and start the distributor."""
    global distributor
    
    # Set up colored logging for distributor
    distributor_logger = logging.getLogger('distributor')
    distributor_logger.setLevel(logging.INFO)
    
    # If no handlers, add one
    if not distributor_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(ColoredFormatter('%(asctime)s - [%(name)s] - %(message)s'))
        distributor_logger.addHandler(handler)
        distributor_logger.propagate = False  # Don't propagate to root logger
    else:
        # Apply colored formatter to existing handlers
        for handler in distributor_logger.handlers:
            handler.setFormatter(ColoredFormatter('%(asctime)s - [%(name)s] - %(message)s'))
    
    distributor = Distributor(
        task_timeout_seconds=30,
        backpressure_threshold=100,
        monitor_interval_seconds=5
    )
    await distributor.start()
    logger.info(f"{Colors.BOLD}{Colors.CYAN}Distributor API started{Colors.RESET}")


@app.on_event("shutdown")
async def shutdown():
    """Stop the distributor."""
    if distributor:
        await distributor.stop()
    logger.info("Distributor API stopped")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Log Distributor",
        "version": "2.0.0",
        "architecture": "pull-based-work-queue"
    }


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy"}


@app.post("/submit")
async def submit_log(log: LogMessage):
    """
    Submit a log for processing (called by Emitters).
    
    Args:
        log: Log message to process
        
    Returns:
        task_id and status
    """
    if not distributor:
        raise HTTPException(status_code=503, detail="Distributor not initialized")
    
    task_id = await distributor.submit_log(log)
    
    return {
        "status": "accepted",
        "task_id": task_id
    }


@app.post("/get_work")
async def get_work(request: WorkRequest):
    """
    Get work for an analyzer (called by Analyzers).
    
    Args:
        request: Work request from analyzer
        
    Returns:
        WorkResponse with task or no work available
    """
    if not distributor:
        raise HTTPException(status_code=503, detail="Distributor not initialized")
    
    response = await distributor.get_work(request)
    return response


@app.post("/status")
async def update_status(update: StatusUpdate):
    """
    Receive status update from analyzer (heartbeat).
    
    Args:
        update: Status update from analyzer
    """
    if not distributor:
        raise HTTPException(status_code=503, detail="Distributor not initialized")
    
    await distributor.update_status(update)
    
    return {"status": "acknowledged"}


@app.get("/stats")
async def get_stats():
    """Get distributor statistics."""
    if not distributor:
        raise HTTPException(status_code=503, detail="Distributor not initialized")
    
    stats = await distributor.get_stats()
    return stats


@app.get("/metrics")
async def get_metrics():
    """Get scaling metrics."""
    if not distributor:
        raise HTTPException(status_code=503, detail="Distributor not initialized")
    
    metrics = await distributor.get_metrics()
    return metrics

