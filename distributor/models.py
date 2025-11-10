"""
Data models for the pull-based work queue system.
"""
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, validator
from enum import Enum
import uuid


class LogLevel(str, Enum):
    """Log severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogMessage(BaseModel):
    """
    Individual log message.
    
    This is the actual data payload that gets processed.
    """
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: LogLevel = LogLevel.INFO
    message: str
    source: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskStatus(str, Enum):
    """Status of a task in the system."""
    QUEUED = "queued"           # In the main queue waiting
    IN_PROGRESS = "in_progress" # Being processed by an analyzer
    COMPLETED = "completed"     # Successfully processed
    FAILED = "failed"           # Failed processing
    TIMEOUT = "timeout"         # Timed out (will be requeued)


class Task(BaseModel):
    """
    Task metadata that lives in the queue.
    
    The actual log data is stored separately and referenced by task_id.
    This allows the queue to be lightweight (just metadata).
    """
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: TaskStatus = TaskStatus.QUEUED
    
    # Analyzer assignment
    assigned_to: Optional[str] = None  # Analyzer ID
    assigned_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    
    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    
    # Reference to actual data (stored in Distributor's data store)
    data_key: str = ""  # Will be same as task_id by default
    
    def assign_to_analyzer(self, analyzer_id: str):
        """Mark task as assigned to an analyzer."""
        self.status = TaskStatus.IN_PROGRESS
        self.assigned_to = analyzer_id
        self.assigned_at = datetime.utcnow()
        self.last_heartbeat = datetime.utcnow()
    
    def update_heartbeat(self):
        """Update the last heartbeat timestamp."""
        self.last_heartbeat = datetime.utcnow()
    
    def mark_completed(self):
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
    
    def mark_failed(self):
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
    
    def should_requeue(self, timeout_seconds: int = 30) -> bool:
        """
        Check if task should be requeued due to timeout.
        
        Args:
            timeout_seconds: How long without heartbeat before timeout
            
        Returns:
            True if task should be requeued
        """
        if self.status != TaskStatus.IN_PROGRESS:
            return False
        
        if not self.last_heartbeat:
            return False
        
        elapsed = (datetime.utcnow() - self.last_heartbeat).total_seconds()
        return elapsed > timeout_seconds
    
    def requeue(self):
        """
        Reset task for requeuing.
        
        Returns False if max retries exceeded, True otherwise.
        """
        if self.retry_count >= self.max_retries:
            self.status = TaskStatus.FAILED
            return False
        
        self.status = TaskStatus.QUEUED
        self.assigned_to = None
        self.assigned_at = None
        self.last_heartbeat = None
        self.retry_count += 1
        return True


class StatusUpdate(BaseModel):
    """
    Status update from an analyzer (serves as heartbeat).
    """
    task_id: str
    analyzer_id: str
    status: TaskStatus
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message: Optional[str] = None


class WorkRequest(BaseModel):
    """
    Request from an analyzer for work.
    """
    analyzer_id: str
    weight: float  # Capacity/concurrency level
    current_tasks: int  # How many tasks currently processing


class WorkResponse(BaseModel):
    """
    Response to an analyzer's work request.
    """
    task_id: Optional[str] = None
    log_data: Optional[LogMessage] = None
    has_work: bool = False
    message: str = "No work available"


class ScalingMetrics(BaseModel):
    """
    Metrics used for scaling decisions.
    """
    queue_depth: int
    in_progress_count: int
    total_analyzers: int
    active_analyzers: int
    queue_backpressure: float  # Queue depth / active analyzers
    timestamp: datetime = Field(default_factory=datetime.utcnow)
