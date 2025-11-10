"""
Analyzer: Worker that pulls and processes log messages from the Distributor.

Analyzers:
- Pull work from the Distributor (GET /get_work)
- Process logs (simulated work)
- Send heartbeats and status updates
- Support configurable concurrency based on weight
"""
import asyncio
import httpx
import logging
import time
from typing import Optional, List, Union
from datetime import datetime

logger = logging.getLogger(__name__)


class Analyzer:
    """
    Log analyzer worker that pulls work from distributor.
    
    Key features:
    - Pull-based work fetching
    - Concurrent task processing based on weight
    - Automatic heartbeat sending
    - Graceful shutdown
    """
    
    def __init__(
        self,
        analyzer_id: str,
        distributor_url: str,
        weight: float = 1.0,
        heartbeat_interval: float = 5.0,
        poll_interval: float = 1.0,
        processing_delay: float = 0.1
    ):
        """
        Initialize the analyzer.
        
        Args:
            analyzer_id: Unique identifier for this analyzer
            distributor_url: Base URL of the Distributor service
            weight: Capacity/concurrency level (higher = more concurrent tasks)
            heartbeat_interval: Seconds between heartbeats
            poll_interval: Seconds between work polling attempts
            processing_delay: Simulated processing time per log
        """
        self.analyzer_id = analyzer_id
        self.distributor_url = distributor_url.rstrip("/")
        self.weight = weight
        self.heartbeat_interval = heartbeat_interval
        self.poll_interval = poll_interval
        self.processing_delay = processing_delay
        
        # Calculate max concurrent tasks based on weight
        # Weight 0.1 = 1 task, 0.2 = 2 tasks, 0.3 = 3 tasks, 0.4 = 4 tasks
        self.max_concurrent_tasks = max(1, int(weight * 10))
        
        # HTTP client
        self.client = httpx.AsyncClient(timeout=10.0)
        
        # Task tracking
        self.active_tasks: dict[str, asyncio.Task] = {}
        self.current_task_ids: set[str] = set()
        
        # Statistics
        self.total_tasks_processed = 0
        self.total_tasks_failed = 0
        self.start_time = None
        
        # Control
        self.running = False
        self.worker_task: Optional[asyncio.Task] = None
        
        # Create custom logger with analyzer ID
        self.logger = logging.getLogger(f"analyzer.{analyzer_id}")
        
        self.logger.info(
            f"Initialized: weight={weight}, max_concurrent={self.max_concurrent_tasks}"
        )
    
    async def start(self):
        """Start the analyzer worker."""
        if self.running:
            return
        
        self.running = True
        self.start_time = time.time()
        
        # Start the main worker loop
        self.worker_task = asyncio.create_task(self._worker_loop())
        
        self.logger.info("Started")
    
    async def stop(self):
        """Stop the analyzer worker."""
        self.running = False
        
        # Wait for active tasks to complete
        if self.active_tasks:
            self.logger.info(
                f"Waiting for {len(self.active_tasks)} active tasks to complete..."
            )
            await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)
        
        # Cancel worker loop
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        
        await self.client.aclose()
        self.logger.info("Stopped")
    
    async def _worker_loop(self):
        """
        Main worker loop that pulls and processes work.
        """
        while self.running:
            try:
                # Check if we have capacity for more work
                if len(self.active_tasks) < self.max_concurrent_tasks:
                    # Request work from distributor
                    work = await self._request_work()
                    
                    if work and work.get("has_work"):
                        # Start processing in background
                        task_id = work["task_id"]
                        task = asyncio.create_task(
                            self._process_task(task_id, work["log_data"])
                        )
                        self.active_tasks[task_id] = task
                        self.current_task_ids.add(task_id)
                    else:
                        # No work available, wait before polling again
                        await asyncio.sleep(self.poll_interval * 10)
                else:
                    # At capacity, wait before checking again
                    await asyncio.sleep(self.poll_interval)
                
                # Clean up completed tasks
                await self._cleanup_completed_tasks()
                
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                await asyncio.sleep(1.0)
    
    async def _request_work(self) -> Optional[dict]:
        """
        Request work from the distributor.
        
        Returns:
            Work response dict or None
        """
        try:
            request_data = {
                "analyzer_id": self.analyzer_id,
                "weight": self.weight,
                "current_tasks": len(self.active_tasks)
            }
            
            response = await self.client.post(
                f"{self.distributor_url}/get_work",
                json=request_data
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Failed to get work: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error requesting work: {e}")
            return None
    
    async def _process_task(self, task_id: str, log_data: dict):
        """
        Process a single task.
        
        Args:
            task_id: ID of the task
            log_data: Log message data
        """
        try:
            self.logger.debug(
                f"Processing task {task_id}: {log_data.get('message', '')[:50]}"
            )
            
            # Send initial heartbeat
            await self._send_status(task_id, "in_progress")
            
            # Simulate processing work
            # In a real analyzer, this would:
            # - Parse and index the log
            # - Run analytics/aggregations
            # - Store in database
            # - Trigger alerts
            await asyncio.sleep(self.processing_delay)
            
            # Send heartbeats during processing (for longer tasks)
            # For our quick processing, one heartbeat is enough
            
            # Mark as completed
            await self._send_status(task_id, "completed")
            
            self.total_tasks_processed += 1
            self.logger.debug(f"Completed task {task_id}")
            
        except Exception as e:
            self.logger.error(f"Error processing task {task_id}: {e}")
            
            # Mark as failed
            await self._send_status(task_id, "failed", str(e))
            self.total_tasks_failed += 1
        
        finally:
            # Remove from tracking
            if task_id in self.current_task_ids:
                self.current_task_ids.remove(task_id)
    
    async def _send_status(
        self,
        task_id: str,
        status: str,
        message: Optional[str] = None
    ):
        """
        Send status update to distributor (serves as heartbeat).
        
        Args:
            task_id: ID of the task
            status: Status (in_progress, completed, failed)
            message: Optional message
        """
        try:
            status_data = {
                "task_id": task_id,
                "analyzer_id": self.analyzer_id,
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
                "message": message
            }
            
            response = await self.client.post(
                f"{self.distributor_url}/status",
                json=status_data
            )
            
            if response.status_code != 200:
                self.logger.warning(
                    f"Failed to send status for {task_id}: {response.status_code}"
                )
                
        except Exception as e:
            self.logger.error(f"Error sending status: {e}")
    
    async def _cleanup_completed_tasks(self):
        """Clean up completed tasks from active_tasks dict."""
        completed = [
            task_id for task_id, task in self.active_tasks.items()
            if task.done()
        ]
        
        for task_id in completed:
            del self.active_tasks[task_id]
    
    def get_stats(self) -> dict:
        """Get analyzer statistics."""
        uptime = time.time() - self.start_time if self.start_time else 0
        
        return {
            "analyzer_id": self.analyzer_id,
            "weight": self.weight,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "active_tasks": len(self.active_tasks),
            "total_processed": self.total_tasks_processed,
            "total_failed": self.total_tasks_failed,
            "uptime_seconds": uptime,
            "tasks_per_second": (
                self.total_tasks_processed / uptime if uptime > 0 else 0
            ),
            "is_running": self.running
        }

class AnalyzerPool:
    """
    Pool of analyzers that pull and process work from the distributor.
    
    Each analyzer runs independently in its own asyncio task with potentially
    different weights, allowing for flexible capacity management.
    
    Usage:
        pool = AnalyzerPool(
            distributor_url="http://localhost:8000",
            num_analyzers=4,
            weights=[0.4, 0.3, 0.2, 0.1]
        )
        await pool.start()
        # ... let them process work ...
        await pool.stop()
    """
    
    def __init__(
        self,
        distributor_url: str,
        num_analyzers: int = 4,
        weights: Optional[Union[List[float], float]] = None,
        analyzer_prefix: str = "analyzer",
        processing_delay: float = 0.05,
        poll_interval: float = 0.05,
        # Autoscaling parameters
        enable_autoscaling: bool = False,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        scale_up_threshold: int = 50,
        scale_down_threshold: int = 10,
        scale_check_interval: float = 10.0,
        scale_cooldown: float = 30.0,
        scale_up_count: int = 1,
        scale_down_count: int = 1
    ):
        """2025-11-09 22:58:40,369 - [__main__] -   Total Emitted: 5537
2025-11-09 22:58:40,369 - [__main__] - 
Distributor:
2025-11-09 22:58:40,369 - [__main__] -   Total Received: 5537
2025-11-09 22:58:40,369 - [__main__] -   Total Completed: 5537
2025-11-09 22:58:40,369 - [__main__] -   Total Failed: 0
2025-11-09 22:58:40,369 - [__main__] -   In Progress: 0
2025-11-09 22:58:40,369 - [__main__] - 
Autoscaling:
2025-11-09 22:58:40,369 - [__main__] -   Total Scale-Ups: 3
2025-11-09 22:58:40,369 - [__main__] -   Total Scale-Downs: 6
2025-11-09 22:58:40,369 - [__main__] -   Min Size: 2
2025-11-09 22:58:40,369 - [__main__] -   Max Size: 10
2025-11-09 22:58:40,369 - [__main__] -   Final Size: 2
2025-11-09 22:58:40,369 - [__main__] - 
Analyzers:
2025-11-09 22:58:40,369 - [__main__] -   Total Processed (All): 5532
2025-11-09 22:58:40,369 - [__main__] -     - By Current: 897
2025-11-09 22:58:40,369 - [__main__] -     - By Scaled-Down: 4635
2025-11-09 22:58:40,369 - [__main__] -   Total Failed: 0
2025-11-09 22:58:40,369 - [__main__] -   Final Size: 2 analyzers ]
        
        Args:
            distributor_url: URL of the distributor
            num_analyzers: Number of analyzers to create initially
            weights: Either a list of weights (one per analyzer) or a single weight for all.
                     If None, uses default pattern [0.4, 0.3, 0.2, 0.1] cycling
            analyzer_prefix: Prefix for analyzer IDs
            processing_delay: Simulated processing time per task
            poll_interval: Seconds between work polling attempts
            enable_autoscaling: Enable automatic scaling based on queue depth
            min_size: Minimum number of analyzers (defaults to num_analyzers)
            max_size: Maximum number of analyzers (defaults to num_analyzers * 3)
            scale_up_threshold: Queue depth to trigger scale up
            scale_down_threshold: Queue depth to trigger scale down
            scale_check_interval: Seconds between autoscaling checks
            scale_cooldown: Minimum seconds between scaling actions
            scale_up_count: Number of analyzers to add per scale up
            scale_down_count: Number of analyzers to remove per scale down
        """
        self.distributor_url = distributor_url
        self.num_analyzers = num_analyzers
        self.analyzer_prefix = analyzer_prefix
        self.processing_delay = processing_delay
        self.poll_interval = poll_interval
        
        # Parse weights
        self.weights = self._parse_weights(weights, num_analyzers)
        
        # Autoscaling configuration
        self.enable_autoscaling = enable_autoscaling
        self.min_size = min_size if min_size is not None else num_analyzers
        self.max_size = max_size if max_size is not None else num_analyzers * 4  # More aggressive max
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.scale_check_interval = scale_check_interval
        self.scale_cooldown = scale_cooldown
        self.scale_up_count = scale_up_count
        self.scale_down_count = scale_down_count
        
        # Weight for scaled analyzers (high concurrency)
        self.scale_weight = 0.5  # Aggressive: 5 concurrent tasks per scaled analyzer
        
        # Autoscaling state
        self.last_scale_time: Optional[datetime] = None
        self.total_scale_ups = 0
        self.total_scale_downs = 0
        self.autoscale_task: Optional[asyncio.Task] = None
        
        # Stats from scaled-down analyzers (so they're not lost)
        self.scaled_down_processed = 0
        self.scaled_down_failed = 0
        
        # Analyzer instances
        self.analyzers: List[Analyzer] = []
        self.running = False
        
        log_msg = f"AnalyzerPool initialized: {num_analyzers} analyzers, weights={self.weights}"
        if enable_autoscaling:
            log_msg += f", autoscaling enabled (min={self.min_size}, max={self.max_size})"
        logger.info(log_msg)
    
    def _parse_weights(
        self,
        weights: Optional[Union[List[float], float]],
        num_analyzers: int
    ) -> List[float]:
        """
        Parse weights configuration into a list of weights.
        
        Args:
            weights: User-provided weights
            num_analyzers: Number of analyzers
            
        Returns:
            List of weights (one per analyzer)
        """
        if weights is None:
            # Default pattern: cycle through [0.4, 0.3, 0.2, 0.1]
            default_pattern = [0.4, 0.3, 0.2, 0.1]
            return [
                default_pattern[i % len(default_pattern)]
                for i in range(num_analyzers)
            ]
        elif isinstance(weights, (int, float)):
            # Single weight for all analyzers
            return [float(weights)] * num_analyzers
        elif isinstance(weights, list):
            # List of weights
            if len(weights) < num_analyzers:
                # Cycle through provided weights
                return [
                    weights[i % len(weights)]
                    for i in range(num_analyzers)
                ]
            else:
                # Use first N weights
                return weights[:num_analyzers]
        else:
            raise ValueError(f"Invalid weights type: {type(weights)}")
    
    async def start(self):
        """Start all analyzers and autoscaling if enabled."""
        if self.running:
            logger.warning("AnalyzerPool already running")
            return
        
        self.running = True
        
        # Create and start all analyzers
        for i in range(self.num_analyzers):
            analyzer_id = f"{self.analyzer_prefix}-{i+1}"
            weight = self.weights[i]
            
            analyzer = Analyzer(
                analyzer_id=analyzer_id,
                distributor_url=self.distributor_url,
                weight=weight,
                processing_delay=self.processing_delay,
                poll_interval=self.poll_interval
            )
            
            await analyzer.start()
            self.analyzers.append(analyzer)
            
            logger.info(
                f"Started {analyzer_id} with weight {weight} "
                f"(max concurrent: {analyzer.max_concurrent_tasks})"
            )
        
        logger.info(f"Started {self.num_analyzers} analyzers")
        
        # Start autoscaling if enabled
        if self.enable_autoscaling:
            self.autoscale_task = asyncio.create_task(self._autoscale_loop())
            logger.info(
                f"Autoscaling enabled: min={self.min_size}, max={self.max_size}, "
                f"thresholds=({self.scale_down_threshold}, {self.scale_up_threshold})"
            )
    
    async def stop(self):
        """Stop autoscaling and all analyzers."""
        if not self.running:
            return
        
        self.running = False
        
        # Stop autoscaling first
        if self.autoscale_task:
            self.autoscale_task.cancel()
            try:
                await self.autoscale_task
            except asyncio.CancelledError:
                pass
            logger.info("Autoscaling stopped")
        
        logger.info(f"Stopping {len(self.analyzers)} analyzers...")
        
        # Stop all analyzers concurrently
        await asyncio.gather(
            *[analyzer.stop() for analyzer in self.analyzers],
            return_exceptions=True
        )
        
        logger.info("All analyzers stopped")
        
        # Clear state
        self.analyzers.clear()
    
    async def scale_up(self, count: int = 1, weight: Optional[float] = None):
        """
        Add more analyzers to the pool.
        
        Args:
            count: Number of analyzers to add
            weight: Weight for new analyzers (defaults to 0.5 for aggressive scaling)
        """
        if not self.running:
            logger.warning("Cannot scale up: pool not running")
            return
        
        if weight is None:
            # Aggressive scaling: high concurrency analyzers
            weight = 0.5
        
        current_count = len(self.analyzers)
        
        for i in range(count):
            analyzer_id = f"{self.analyzer_prefix}-{current_count + i + 1}"
            
            analyzer = Analyzer(
                analyzer_id=analyzer_id,
                distributor_url=self.distributor_url,
                weight=weight,
                processing_delay=self.processing_delay,
                poll_interval=self.poll_interval
            )
            
            await analyzer.start()
            self.analyzers.append(analyzer)
            
            logger.info(
                f"🚀 Scaled up: {analyzer_id} with weight {weight} "
                f"(max concurrent: {analyzer.max_concurrent_tasks})"
            )
        
        logger.info(f"🚀 Scaled up by {count}. Total analyzers: {len(self.analyzers)} (added {count * int(weight * 10)} total capacity)")
    
    async def scale_down(self, count: int = 1):
        """
        Remove analyzers from the pool.
        
        Args:
            count: Number of analyzers to remove
        """
        if not self.running:
            logger.warning("Cannot scale down: pool not running")
            return
        
        if len(self.analyzers) == 0:
            logger.warning("No analyzers to scale down")
            return
        
        # Don't remove more than we have
        actual_count = min(count, len(self.analyzers))
        
        # Stop the last N analyzers
        to_remove = self.analyzers[-actual_count:]
        
        logger.info(f"Scaling down by {actual_count}...")
        
        # Capture stats from analyzers being removed BEFORE stopping them
        for analyzer in to_remove:
            stats = analyzer.get_stats()
            self.scaled_down_processed += stats['total_processed']
            self.scaled_down_failed += stats['total_failed']
            logger.debug(f"  Captured stats from {analyzer.analyzer_id}: {stats['total_processed']} processed")
        
        await asyncio.gather(
            *[analyzer.stop() for analyzer in to_remove],
            return_exceptions=True
        )
        
        # Remove from list
        self.analyzers = self.analyzers[:-actual_count]
        
        logger.info(f"Scaled down by {actual_count}. Total analyzers: {len(self.analyzers)}")
    
    def get_current_size(self) -> int:
        """Get the current number of analyzers in the pool."""
        return len(self.analyzers)
    
    async def _get_queue_depth(self) -> int:
        """Get current queue depth from distributor."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.distributor_url}/stats",
                    timeout=2.0
                )
                if response.status_code == 200:
                    stats = response.json()
                    return stats.get('queue_depth', 0)
        except Exception as e:
            logger.debug(f"Failed to get queue depth: {e}")
        return 0
    
    async def _autoscale_loop(self):
        """Background loop that monitors and scales the pool."""
        try:
            while self.running:
                await asyncio.sleep(self.scale_check_interval)
                
                try:
                    await self._check_and_scale()
                except Exception as e:
                    logger.error(f"Error in autoscaling: {e}")
        
        except asyncio.CancelledError:
            pass
    
    async def _check_and_scale(self):
        """Check metrics and scale if needed."""
        # Get current state
        queue_depth = await self._get_queue_depth()
        current_size = self.get_current_size()
        
        # Check if we're in cooldown
        if self.last_scale_time:
            from datetime import datetime
            time_since_scale = (datetime.utcnow() - self.last_scale_time).total_seconds()
            if time_since_scale < self.scale_cooldown:
                logger.debug(
                    f"In cooldown: {time_since_scale:.1f}s / {self.scale_cooldown}s"
                )
                return
        
        # Decide on scaling action
        should_scale_up = (
            queue_depth >= self.scale_up_threshold and 
            current_size < self.max_size
        )
        
        should_scale_down = (
            queue_depth <= self.scale_down_threshold and 
            current_size > self.min_size
        )
        
        if should_scale_up:
            # Calculate how many to add (don't exceed max)
            count = min(self.scale_up_count, self.max_size - current_size)
            
            logger.info(
                f"🔼 SCALING UP: queue_depth={queue_depth}, "
                f"current_size={current_size}, adding={count} high-capacity analyzers"
            )
            
            # Use aggressive weight for scaled analyzers
            await self.scale_up(count=count, weight=self.scale_weight)
            from datetime import datetime
            self.last_scale_time = datetime.utcnow()
            self.total_scale_ups += 1
        
        elif should_scale_down:
            # Calculate how many to remove (don't go below min)
            count = min(self.scale_down_count, current_size - self.min_size)
            
            logger.info(
                f"🔽 SCALING DOWN: queue_depth={queue_depth}, "
                f"current_size={current_size}, removing={count}"
            )
            
            await self.scale_down(count=count)
            from datetime import datetime
            self.last_scale_time = datetime.utcnow()
            self.total_scale_downs += 1
        
        else:
            logger.debug(
                f"No scaling needed: queue_depth={queue_depth}, "
                f"size={current_size}/{self.min_size}-{self.max_size}"
            )
    
    def get_stats(self) -> dict:
        """
        Get statistics for all analyzers.
        
        Returns:
            Dict with total and per-analyzer statistics (includes scaled-down analyzers)
        """
        total_processed = 0
        total_failed = 0
        analyzer_stats = {}
        
        for analyzer in self.analyzers:
            stats = analyzer.get_stats()
            total_processed += stats['total_processed']
            total_failed += stats['total_failed']
            
            analyzer_stats[stats['analyzer_id']] = {
                'weight': stats['weight'],
                'max_concurrent': stats['max_concurrent_tasks'],
                'active_tasks': stats['active_tasks'],
                'total_processed': stats['total_processed'],
                'total_failed': stats['total_failed'],
                'tasks_per_second': stats['tasks_per_second'],
                'is_running': stats['is_running']
            }
        
        # Include stats from scaled-down analyzers
        total_processed += self.scaled_down_processed
        total_failed += self.scaled_down_failed
        
        stats = {
            'num_analyzers': len(self.analyzers),
            'total_processed': total_processed,
            'total_failed': total_failed,
            'current_analyzers_processed': total_processed - self.scaled_down_processed,
            'scaled_down_processed': self.scaled_down_processed,
            'scaled_down_failed': self.scaled_down_failed,
            'analyzer_stats': analyzer_stats,
            'is_running': self.running
        }
        
        # Add autoscaling stats if enabled
        if self.enable_autoscaling:
            from datetime import datetime
            stats['autoscaling'] = {
                'enabled': True,
                'min_size': self.min_size,
                'max_size': self.max_size,
                'total_scale_ups': self.total_scale_ups,
                'total_scale_downs': self.total_scale_downs,
                'in_cooldown': (
                    (datetime.utcnow() - self.last_scale_time).total_seconds() < self.scale_cooldown
                    if self.last_scale_time else False
                )
            }
        
        return stats
    
    def get_distribution(self) -> dict:
        """
        Get distribution statistics showing how work is distributed.
        
        Returns:
            Dict with distribution percentages and expected vs actual
        """
        stats = self.get_stats()
        total_processed = stats['total_processed']
        
        if total_processed == 0:
            return {
                'total_processed': 0,
                'distribution': {}
            }
        
        distribution = {}
        for analyzer_id, astats in stats['analyzer_stats'].items():
            processed = astats['total_processed']
            weight = astats['weight']
            
            actual_percentage = (processed / total_processed) * 100
            expected_percentage = weight * 100
            deviation = actual_percentage - expected_percentage
            
            distribution[analyzer_id] = {
                'processed': processed,
                'weight': weight,
                'actual_percentage': round(actual_percentage, 2),
                'expected_percentage': round(expected_percentage, 1),
                'deviation': round(deviation, 2)
            }
        
        return {
            'total_processed': total_processed,
            'distribution': distribution
        }
    
    async def run_for_duration(self, duration_seconds: float):
        """
        Convenience method to run the pool for a specific duration.
        
        Args:
            duration_seconds: How long to run the pool
        """
        await self.start()
        logger.info(f"Running analyzer pool for {duration_seconds} seconds...")
        await asyncio.sleep(duration_seconds)
        await self.stop()
        
        # Print summary
        stats = self.get_stats()
        logger.info(
            f"Pool run complete: {stats['total_processed']} tasks processed, "
            f"{stats['total_failed']} failed"
        )
    
    async def wait_for_idle(self, timeout: float = 30.0, check_interval: float = 1.0):
        """
        Wait until all analyzers are idle (no active tasks).
        
        Args:
            timeout: Maximum time to wait in seconds
            check_interval: How often to check in seconds
            
        Returns:
            True if idle, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            stats = self.get_stats()
            
            # Check if all analyzers have no active tasks
            all_idle = all(
                astats['active_tasks'] == 0
                for astats in stats['analyzer_stats'].values()
            )
            
            if all_idle:
                logger.info("All analyzers are idle")
                return True
            
            await asyncio.sleep(check_interval)
        
        logger.warning(f"Timeout waiting for analyzers to become idle after {timeout}s")
        return False

