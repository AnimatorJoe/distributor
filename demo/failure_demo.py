"""
Failure Resilience Demo: Shows the system handling analyzer failures.

This demo demonstrates:
1. System running with multiple analyzers
2. Analyzers randomly fail/stop
3. Distributor detects timeouts via heartbeat mechanism
4. Tasks are requeued and processed by healthy analyzers
5. No logs are lost despite analyzer failures
"""
import asyncio
import logging
import sys
import httpx
import random
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer import AnalyzerPool
from emitter import LogEmitterPool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress noisy HTTP logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


async def get_queue_depth(url: str) -> int:
    """Get current queue depth from distributor."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{url}/stats", timeout=2.0)
            if response.status_code == 200:
                stats = response.json()
                return stats.get('queue_depth', 0)
    except:
        return 0


async def get_distributor_stats(url: str) -> dict:
    """Get statistics from distributor."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{url}/stats", timeout=5.0)
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Failed to get distributor stats: {e}")
    return {}


async def random_failures(analyzer_pool, duration: int, failure_rate: float = 0.3, killed_stats: dict = None):
    """
    Randomly kill analyzers during operation.
    
    Args:
        analyzer_pool: The analyzer pool
        duration: How long to run the chaos (seconds)
        failure_rate: Probability of killing an analyzer per check
        killed_stats: Dictionary to accumulate stats from killed analyzers
    """
    start_time = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start_time < duration:
        await asyncio.sleep(random.uniform(5, 15))  # Wait 5-15 seconds
        
        if not analyzer_pool.analyzers:
            logger.warning("⚠️  No analyzers left to kill!")
            continue
        
        if random.random() < failure_rate:
            # Pick a random analyzer to kill
            victim = random.choice(analyzer_pool.analyzers)
            analyzer_id = victim.analyzer_id
            
            # Capture stats before killing
            if killed_stats is not None:
                victim_stats = victim.get_stats()
                killed_stats['analyzers'].append({
                    'id': analyzer_id,
                    'processed': victim_stats['total_processed'],
                    'failed': victim_stats['total_failed']
                })
                killed_stats['total_processed'] += victim_stats['total_processed']
                killed_stats['total_failed'] += victim_stats['total_failed']
            
            logger.warning(f"💀 FAILURE INJECTED: Killing {analyzer_id}")
            
            # Stop the analyzer
            await victim.stop()
            
            # Remove from pool
            analyzer_pool.analyzers.remove(victim)
            
            logger.info(
                f"   Remaining analyzers: {len(analyzer_pool.analyzers)}"
            )


async def main():
    """Run the failure resilience demo."""
    distributor_url = "http://localhost:8000"
    
    logger.info("="*70)
    logger.info("FAILURE RESILIENCE DEMO - Handling Analyzer Failures")
    logger.info("="*70)
    
    # Check distributor is running
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{distributor_url}/health", timeout=2.0)
            if response.status_code != 200:
                logger.error("Distributor is not healthy!")
                return
            
            # Reset distributor statistics for clean metrics
            logger.info("Resetting distributor statistics...")
            response = await client.post(f"{distributor_url}/reset", timeout=2.0)
            if response.status_code == 200:
                logger.info("✓ Distributor statistics reset")
            
    except Exception:
        logger.error(f"Cannot connect to distributor at {distributor_url}")
        logger.error("Please start the distributor first: python run_distributor.py")
        return
    
    logger.info("✓ Connected to distributor\n")
    
    # Start with a good number of analyzers
    logger.info("="*70)
    logger.info("PHASE 1: Starting system with 6 analyzers")
    logger.info("="*70)
    
    analyzer_pool = AnalyzerPool(
        distributor_url=distributor_url,
        num_analyzers=6,
        weights=[0.2, 0.2, 0.15, 0.15, 0.15, 0.15],
        processing_delay=0.1
    )
    await analyzer_pool.start()
    logger.info("✓ Analyzer pool started with 6 analyzers\n")
    
    await asyncio.sleep(2)
    
    # Start emitters with moderate load
    logger.info("="*70)
    logger.info("PHASE 2: Starting moderate workload (5 emitters)")
    logger.info("="*70)
    
    emitter_pool = LogEmitterPool(
        distributor_url=distributor_url,
        num_emitters=5,
        base_interval=0.3,
        interval_jitter=0.1
    )
    await emitter_pool.start()
    logger.info("✓ Emitters started\n")
    
    await asyncio.sleep(5)
    
    # Start chaos - random failures
    logger.info("="*70)
    logger.info("PHASE 3: CHAOS MODE - Random analyzer failures")
    logger.info("="*70)
    logger.info("Analyzers will randomly fail over the next 60 seconds...")
    logger.info("Watch how the distributor handles timeouts and requeues tasks!\n")
    
    # Track stats from killed analyzers
    killed_stats = {
        'analyzers': [],
        'total_processed': 0,
        'total_failed': 0
    }
    
    # Track initial stats
    initial_stats = await get_distributor_stats(distributor_url)
    initial_received = initial_stats.get('total_received', 0) if initial_stats else 0
    
    # Run chaos and monitoring concurrently
    chaos_task = asyncio.create_task(
        random_failures(analyzer_pool, duration=60, failure_rate=0.4, killed_stats=killed_stats)
    )
    
    # Monitor progress
    for i in range(60):
        await asyncio.sleep(1)
        
        if (i + 1) % 10 == 0:
            queue_depth = await get_queue_depth(distributor_url)
            pool_size = analyzer_pool.get_current_size()
            analyzer_stats = analyzer_pool.get_stats()
            dist_stats = await get_distributor_stats(distributor_url)
            
            if dist_stats:
                logger.info(
                    f"[{i+1}s] "
                    f"Analyzers: {pool_size}/6, "
                    f"Queue: {queue_depth}, "
                    f"Received: {dist_stats['total_received']}, "
                    f"Completed: {dist_stats['total_completed']}, "
                    f"In-Progress: {dist_stats['in_progress']}"
                )
    
    await chaos_task
    
    # Let remaining analyzers finish processing
    logger.info("\n" + "="*70)
    logger.info("PHASE 4: Draining queue with remaining analyzers")
    logger.info("="*70)
    
    await emitter_pool.stop()
    logger.info("✓ Emitters stopped\n")
    
    # Wait for in-flight requests
    await asyncio.sleep(2)
    
    # Wait for queue to drain
    logger.info("Waiting for remaining work to complete...")
    queue_drained = False
    for i in range(60):
        queue_depth = await get_queue_depth(distributor_url)
        dist_stats = await get_distributor_stats(distributor_url)
        in_progress = dist_stats.get('in_progress', 0) if dist_stats else 0
        
        if queue_depth == 0 and in_progress == 0:
            logger.info(f"✓ Queue drained after {i+1} seconds (all tasks completed)")
            queue_drained = True
            break
        
        if (i + 1) % 5 == 0:
            logger.info(f"   [{i+1}s] Queue: {queue_depth}, In-progress: {in_progress}")
        
        await asyncio.sleep(1)
    
    if not queue_drained:
        logger.warning(f"⚠️  Queue did not fully drain in 60 seconds")
    
    # Extra time for final status updates
    await asyncio.sleep(2)
    
    # Final statistics
    logger.info("\n" + "="*70)
    logger.info("FINAL STATISTICS")
    logger.info("="*70)
    
    # Give time for final updates
    await asyncio.sleep(2)
    
    # Capture emitter stats (already stopped) - do this LATE to get final count
    emitter_stats = emitter_pool.get_stats()
    
    # Capture analyzer stats before stopping
    surviving_stats = analyzer_pool.get_stats()
    
    # Stop remaining analyzers
    logger.info("\nShutting down remaining analyzers...")
    await analyzer_pool.stop()
    
    # Give distributor time to process final updates
    await asyncio.sleep(1)
    
    # Get final distributor stats
    distributor_stats = await get_distributor_stats(distributor_url)
    
    # Calculate total analyzer stats (surviving + killed)
    total_analyzer_processed = surviving_stats['total_processed'] + killed_stats['total_processed']
    total_analyzer_failed = surviving_stats['total_failed'] + killed_stats['total_failed']
    
    # Display stats
    logger.info("\nEmitters:")
    logger.info(f"  Total Emitted: {emitter_stats['total_emitted']}")
    
    if distributor_stats:
        logger.info("\nDistributor:")
        logger.info(f"  Total Received: {distributor_stats['total_received']}")
        logger.info(f"  Total Completed: {distributor_stats['total_completed']}")
        logger.info(f"  Total Failed: {distributor_stats['total_failed']}")
        logger.info(f"  In Progress: {distributor_stats.get('in_progress', 0)}")
        logger.info(f"  Queue Depth: {distributor_stats['queue_depth']}")
        
        # Calculate success rate
        total_received = distributor_stats['total_received']
        total_completed = distributor_stats['total_completed']
        if total_received > 0:
            success_rate = (total_completed / total_received) * 100
            logger.info(f"  Success Rate: {success_rate:.1f}%")
    
    logger.info("\nAnalyzers:")
    logger.info(f"  Started With: 6 analyzers")
    logger.info(f"  Ended With: {len(surviving_stats['analyzer_stats'])} analyzers")
    logger.info(f"  Analyzers Lost: {len(killed_stats['analyzers'])}")
    logger.info(f"  Total Processed (All): {total_analyzer_processed}")
    logger.info(f"    - By Survivors: {surviving_stats['total_processed']}")
    logger.info(f"    - By Killed: {killed_stats['total_processed']}")
    
    # Show which analyzers survived
    if surviving_stats['analyzer_stats']:
        logger.info("\n  Surviving Analyzers:")
        for analyzer_id, astats in surviving_stats['analyzer_stats'].items():
            logger.info(
                f"    {analyzer_id}: processed {astats['total_processed']} tasks"
            )
    
    # Show which analyzers were killed
    if killed_stats['analyzers']:
        logger.info("\n  Killed Analyzers:")
        for killed in killed_stats['analyzers']:
            logger.info(
                f"    {killed['id']}: processed {killed['processed']} tasks before death"
            )
    
    logger.info("\n" + "="*70)
    logger.info("KEY TAKEAWAY: Despite random failures, the system continued")
    logger.info("processing logs. The distributor's heartbeat mechanism detected")
    logger.info("failed analyzers and requeued their tasks for other analyzers.")
    logger.info("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

