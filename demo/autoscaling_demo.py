"""
Autoscaling Demo: Shows the distributor auto-scaling the analyzer pool.

This demo demonstrates:
1. Starting with a small analyzer pool (2 analyzers)
2. Heavy load from emitters causes queue backpressure
3. Autoscaler detects backpressure and scales up analyzers
4. Load decreases, autoscaler scales down
"""
import asyncio
import logging
import sys
import httpx
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


async def main():
    """Run the autoscaling demo."""
    distributor_url = "http://localhost:8000"
    
    logger.info("="*70)
    logger.info("AUTOSCALING DEMO - Adaptive Capacity Management")
    logger.info("="*70)
    
    # Check distributor is running
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{distributor_url}/health", timeout=2.0)
            if response.status_code != 200:
                logger.error("Distributor is not healthy!")
                return
    except Exception:
        logger.error(f"Cannot connect to distributor at {distributor_url}")
        logger.error("Please start the distributor first: python run_distributor.py")
        return
    
    logger.info("✓ Connected to distributor\n")
    
    # Phase 1: Start with minimal capacity
    logger.info("="*70)
    logger.info("PHASE 1: Starting with minimal capacity (2 analyzers)")
    logger.info("="*70)
    
    analyzer_pool = AnalyzerPool(
        distributor_url=distributor_url,
        num_analyzers=2,
        weights=[0.2, 0.2],         # Start with low capacity
        processing_delay=0.2,       # Slower processing to create backpressure
        # Enable aggressive autoscaling
        enable_autoscaling=True,
        min_size=2,
        max_size=10,                # Higher max capacity
        scale_up_threshold=25,      # Scale up when queue > 25
        scale_down_threshold=5,     # Scale down when queue < 5
        scale_check_interval=5.0,   # Check every 5 seconds
        scale_cooldown=15.0,        # Wait 15s between scaling actions
        scale_up_count=2,           # Add 2 high-capacity analyzers at a time
        scale_down_count=1          # Remove 1 analyzer at a time
    )
    await analyzer_pool.start()
    logger.info("✓ Analyzer pool started with 2 analyzers\n")
    logger.info("✓ Autoscaling enabled\n")
    
    await asyncio.sleep(2)
    
    # Phase 2: Heavy load
    logger.info("="*70)
    logger.info("PHASE 2: Applying heavy load (10 emitters)")
    logger.info("="*70)
    
    emitter_pool = LogEmitterPool(
        distributor_url=distributor_url,
        num_emitters=10,
        base_interval=0.05,  # Very fast emission
        interval_jitter=0.02
    )
    await emitter_pool.start()
    logger.info("✓ Heavy load started - watch the autoscaler respond!\n")
    
    # Monitor for 60 seconds
    logger.info("Monitoring autoscaling behavior for 60 seconds...")
    logger.info("(Watch for 🔼 SCALING UP messages)\n")
    
    for i in range(60):
        await asyncio.sleep(1)
        
        if (i + 1) % 10 == 0:
            queue_depth = await get_queue_depth(distributor_url)
            pool_size = analyzer_pool.get_current_size()
            analyzer_stats = analyzer_pool.get_stats()
            autoscaling_stats = analyzer_stats.get('autoscaling', {})
            
            logger.info(
                f"[{i+1}s] Queue: {queue_depth}, "
                f"Analyzers: {pool_size}, "
                f"Processed: {analyzer_stats['total_processed']}, "
                f"Scale-ups: {autoscaling_stats.get('total_scale_ups', 0)}"
            )
    
    # Phase 3: Reduce load
    logger.info("\n" + "="*70)
    logger.info("PHASE 3: Reducing load (stopping emitters)")
    logger.info("="*70)
    
    await emitter_pool.stop()
    logger.info("✓ Emitters stopped - queue should drain\n")
    
    # Monitor scale down and wait for queue to drain
    logger.info("Monitoring scale-down behavior...")
    logger.info("(Watch for 🔽 SCALING DOWN messages)\n")
    
    queue_drained = False
    for i in range(90):
        await asyncio.sleep(1)
        
        if (i + 1) % 10 == 0:
            queue_depth = await get_queue_depth(distributor_url)
            pool_size = analyzer_pool.get_current_size()
            analyzer_stats = analyzer_pool.get_stats()
            autoscaling_stats = analyzer_stats.get('autoscaling', {})
            
            logger.info(
                f"[{i+1}s] Queue: {queue_depth}, "
                f"Analyzers: {pool_size}, "
                f"Processed: {analyzer_stats['total_processed']}, "
                f"Scale-downs: {autoscaling_stats.get('total_scale_downs', 0)}"
            )
            
            # Check if queue is drained
            if queue_depth == 0 and not queue_drained:
                logger.info(f"\n✓ Queue drained at {i+1} seconds")
                queue_drained = True
    
    # Final statistics
    logger.info("\n" + "="*70)
    logger.info("FINAL STATISTICS")
    logger.info("="*70)
    
    # Capture emitter stats (already stopped)
    emitter_stats = emitter_pool.get_stats()
    
    # Give time for in-flight requests to complete
    logger.info("\nWaiting for in-flight requests and queue to drain...")
    await asyncio.sleep(2)
    
    # Wait for queue to fully drain
    queue_drained = False
    for i in range(30):
        queue_depth = await get_queue_depth(distributor_url)
        dist_stats = await get_distributor_stats(distributor_url)
        in_progress = dist_stats.get('in_progress', 0) if dist_stats else 0
        
        if queue_depth == 0 and in_progress == 0:
            logger.info(f"✓ Queue drained after {i+1} seconds")
            queue_drained = True
            break
        
        if (i + 1) % 5 == 0:
            logger.info(f"  [{i+1}s] Queue: {queue_depth}, In-progress: {in_progress}")
        
        await asyncio.sleep(1)
    
    if not queue_drained:
        logger.warning(f"⚠️  Queue did not fully drain")
    
    # Give final status updates time to reach distributor
    await asyncio.sleep(2)
    
    # Capture analyzer stats before stopping
    analyzer_stats = analyzer_pool.get_stats()
    autoscaling_stats = analyzer_stats.get('autoscaling', {})
    
    # Stop analyzers
    logger.info("\nShutting down analyzers...")
    await analyzer_pool.stop()
    
    # Give distributor time to process final updates
    await asyncio.sleep(1)
    
    # Get final distributor stats
    distributor_stats = await get_distributor_stats(distributor_url)
    
    # Display stats
    logger.info("\nEmitters:")
    logger.info(f"  Total Emitted: {emitter_stats['total_emitted']}")
    
    if distributor_stats:
        logger.info("\nDistributor:")
        logger.info(f"  Total Received: {distributor_stats['total_received']}")
        logger.info(f"  Total Completed: {distributor_stats['total_completed']}")
        logger.info(f"  Total Failed: {distributor_stats['total_failed']}")
        logger.info(f"  In Progress: {distributor_stats.get('in_progress', 0)}")
    
    if autoscaling_stats:
        logger.info("\nAutoscaling:")
        logger.info(f"  Total Scale-Ups: {autoscaling_stats.get('total_scale_ups', 0)}")
        logger.info(f"  Total Scale-Downs: {autoscaling_stats.get('total_scale_downs', 0)}")
        logger.info(f"  Min Size: {autoscaling_stats.get('min_size', 'N/A')}")
        logger.info(f"  Max Size: {autoscaling_stats.get('max_size', 'N/A')}")
        logger.info(f"  Final Size: {analyzer_stats['num_analyzers']}")
    
    logger.info("\nAnalyzers:")
    logger.info(f"  Total Processed (All): {analyzer_stats['total_processed']}")
    if analyzer_stats.get('scaled_down_processed', 0) > 0:
        logger.info(f"    - By Current: {analyzer_stats.get('current_analyzers_processed', 0)}")
        logger.info(f"    - By Scaled-Down: {analyzer_stats.get('scaled_down_processed', 0)}")
    logger.info(f"  Total Failed: {analyzer_stats['total_failed']}")
    logger.info(f"  Final Size: {analyzer_stats['num_analyzers']} analyzers")
    
    logger.info("\n" + "="*70)
    logger.info("DEMO COMPLETE")
    logger.info("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

