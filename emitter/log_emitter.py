"""
Log Emitter: Sends log messages to the Distributor.

Simple client that applications/agents use to submit logs for processing.
"""
import asyncio
import httpx
import logging
import random
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class LogEmitter:
    """
    Client for emitting logs to the Distributor.
    
    Usage:
        emitter = LogEmitter("http://localhost:8000", emitter_id="emitter-1")
        task_id = await emitter.emit(
            level="INFO",
            message="User logged in",
            source="auth-service"
        )
    """
    
    def __init__(
        self,
        distributor_url: str,
        emitter_id: str = "emitter",
        timeout: float = 5.0
    ):
        """
        Initialize the emitter.
        
        Args:
            distributor_url: Base URL of the Distributor service
            emitter_id: Unique identifier for this emitter
            timeout: Request timeout in seconds
        """
        self.distributor_url = distributor_url.rstrip("/")
        self.emitter_id = emitter_id
        self.client = httpx.AsyncClient(timeout=timeout)
        
        # Create custom logger with emitter ID
        self.logger = logging.getLogger(f"emitter.{emitter_id}")
        
        self.logger.info(f"Initialized (distributor: {distributor_url})")
    
    async def emit(
        self,
        message: str,
        level: str = "INFO",
        source: str = "unknown",
        metadata: Optional[dict] = None,
        timestamp: Optional[datetime] = None
    ) -> str:
        """
        Emit a log message to the distributor.
        
        Args:
            message: Log message content
            level: Log level (DEBUG, INFO, WARN, ERROR, CRITICAL)
            source: Source of the log (app name, service, etc.)
            metadata: Additional metadata as key-value pairs
            timestamp: Log timestamp (defaults to now)
            
        Returns:
            task_id: ID of the created task
            
        Raises:
            Exception: If submission fails
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        if metadata is None:
            metadata = {}
        
        log_data = {
            "timestamp": timestamp.isoformat(),
            "level": level,
            "message": message,
            "source": source,
            "metadata": metadata
        }
        
        try:
            response = await self.client.post(
                f"{self.distributor_url}/submit",
                json=log_data
            )
            response.raise_for_status()
            
            result = response.json()
            task_id = result.get("task_id")
            
            self.logger.debug(f"Emitted log: task_id={task_id}")
            return task_id
            
        except Exception as e:
            self.logger.error(f"Failed to emit log: {e}")
            raise
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

class LogEmitterPool:
    """
    Pool of log emitters that continuously send logs at randomized intervals.
    
    Each emitter runs in its own asyncio task and sends logs every x ± y seconds,
    simulating real-world log traffic patterns.
    
    Usage:
        pool = LogEmitterPool(
            distributor_url="http://localhost:8000",
            num_emitters=5,
            base_interval=1.0,
            interval_jitter=0.5
        )
        await pool.start()
        # ... let it run ...
        await pool.stop()
    """
    
    def __init__(
        self,
        distributor_url: str,
        num_emitters: int = 5,
        base_interval: float = 1.0,
        interval_jitter: float = 0.5,
        emitter_prefix: str = "emitter"
    ):
        """
        Initialize the emitter pool.
        
        Args:
            distributor_url: URL of the distributor
            num_emitters: Number of concurrent emitters
            base_interval: Base time between logs in seconds (x)
            interval_jitter: Random variation in seconds (±y)
            emitter_prefix: Prefix for emitter source names
        """
        self.distributor_url = distributor_url
        self.num_emitters = num_emitters
        self.base_interval = base_interval
        self.interval_jitter = interval_jitter
        self.emitter_prefix = emitter_prefix
        
        # Emitter tasks
        self.emitters: List[LogEmitter] = []
        self.tasks: List[asyncio.Task] = []
        self.running = False
        
        # Statistics (protected by lock for concurrent updates)
        self.stats_lock = asyncio.Lock()
        self.total_emitted = 0
        self.emitter_stats = {}
        
        logger.info(
            f"LogEmitterPool initialized: {num_emitters} emitters, "
            f"interval={base_interval}±{interval_jitter}s"
        )
    
    async def start(self):
        """Start all emitters."""
        if self.running:
            logger.warning("EmitterPool already running")
            return
        
        self.running = True
        
        # Create emitters and start their tasks
        for i in range(self.num_emitters):
            emitter_id = f"{self.emitter_prefix}-{i+1}"
            emitter = LogEmitter(self.distributor_url, emitter_id=emitter_id)
            self.emitters.append(emitter)
            
            # Start emitter task
            task = asyncio.create_task(
                self._emitter_loop(emitter, emitter_id)
            )
            self.tasks.append(task)
            
            self.emitter_stats[emitter_id] = {
                "count": 0,
                "errors": 0
            }
        
        logger.info(f"Started {self.num_emitters} emitters")
    
    async def stop(self):
        """Stop all emitters."""
        if not self.running:
            return
        
        self.running = False
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for cancellation
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Close all emitters
        for emitter in self.emitters:
            await emitter.close()
        
        logger.info(f"Stopped all emitters (total logs emitted: {self.total_emitted})")
        
        # Clear state
        self.tasks.clear()
        self.emitters.clear()
    
    async def _emitter_loop(self, emitter: LogEmitter, emitter_id: str):
        """
        Main loop for a single emitter.
        
        Args:
            emitter: LogEmitter instance
            emitter_id: Unique identifier for this emitter
        """
        log_count = 0
        
        # Random seed per emitter for varied behavior
        random.seed(hash(emitter_id))
        
        try:
            while self.running:
                # Generate and emit log
                try:
                    message = self._generate_log_message(emitter_id, log_count)
                    level = self._generate_log_level()
                    metadata = self._generate_metadata(emitter_id, log_count)
                    
                    await emitter.emit(
                        message=message,
                        level=level,
                        source=emitter_id,
                        metadata=metadata
                    )
                    
                    log_count += 1
                    
                    # Update stats with lock to prevent race conditions
                    async with self.stats_lock:
                        self.total_emitted += 1
                        self.emitter_stats[emitter_id]["count"] += 1
                    
                    emitter.logger.debug(f"Emitted log #{log_count}")
                    
                except Exception as e:
                    emitter.logger.error(f"Failed to emit: {e}")
                    async with self.stats_lock:
                        self.emitter_stats[emitter_id]["errors"] += 1
                
                # Sleep for randomized interval: base ± jitter
                interval = self.base_interval + random.uniform(
                    -self.interval_jitter,
                    self.interval_jitter
                )
                interval = max(0.1, interval)  # Minimum 100ms
                
                await asyncio.sleep(interval)
                
        except asyncio.CancelledError:
            emitter.logger.debug(f"Cancelled (emitted {log_count} logs)")
    
    def _generate_log_message(self, emitter_id: str, log_count: int) -> str:
        """Generate a realistic log message."""
        messages = [
            f"Processing request #{log_count}",
            f"Database query completed in {random.randint(10, 500)}ms",
            f"User authenticated successfully",
            f"Cache hit for key '{random.choice(['user', 'session', 'config'])}_{random.randint(1000, 9999)}'",
            f"API call to external service completed",
            f"Background job #{log_count} started",
            f"File uploaded: {random.randint(100, 10000)} bytes",
            f"Connection established with peer {random.randint(1, 100)}",
            f"Transaction completed successfully",
            f"Health check passed",
        ]
        return random.choice(messages)
    
    def _generate_log_level(self) -> str:
        """Generate a log level with realistic distribution."""
        # 70% INFO, 15% DEBUG, 10% WARN, 4% ERROR, 1% CRITICAL
        rand = random.random()
        if rand < 0.70:
            return "INFO"
        elif rand < 0.85:
            return "DEBUG"
        elif rand < 0.95:
            return "WARN"
        elif rand < 0.99:
            return "ERROR"
        else:
            return "CRITICAL"
    
    def _generate_metadata(self, emitter_id: str, log_count: int) -> dict:
        """Generate metadata for the log."""
        return {
            "emitter_id": emitter_id,
            "sequence": log_count,
            "request_id": f"req-{random.randint(10000, 99999)}",
            "duration_ms": random.randint(1, 1000),
            "status_code": random.choice([200, 200, 200, 201, 304, 400, 404, 500])
        }
    
    def get_stats(self) -> dict:
        """Get statistics for all emitters."""
        return {
            "total_emitted": self.total_emitted,
            "num_emitters": self.num_emitters,
            "emitter_stats": self.emitter_stats,
            "is_running": self.running
        }
    
    async def run_for_duration(self, duration_seconds: float):
        """
        Convenience method to run the pool for a specific duration.
        
        Args:
            duration_seconds: How long to run the pool
        """
        await self.start()
        logger.info(f"Running emitter pool for {duration_seconds} seconds...")
        await asyncio.sleep(duration_seconds)
        await self.stop()
        logger.info(f"Pool run complete: {self.total_emitted} total logs emitted")

