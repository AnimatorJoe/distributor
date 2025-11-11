"""
Simple demo of the pull-based work queue system.

This script demonstrates the complete system:
1. Creates analyzer pool
2. Creates emitter pool  
3. Runs for a duration
4. Shuts down and shows stats
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


async def main():
    """Run the demo."""
    distributor_url = "http://localhost:8000"
    
    # Configuration
    run_duration_seconds = 30
    max_logs_cutoff = 1000  # Stop if we reach this many logs
    
    logger.info("="*60)
    logger.info("LOGS DISTRIBUTOR DEMO - Pull-Based Work Queue")
    logger.info("="*60)
    
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
            
    except Exception as e:
        logger.error(f"Cannot connect to distributor at {distributor_url}")
        logger.error("Please start the distributor first:")
        logger.error("  python run_distributor.py")
        return
    
    logger.info(f"✓ Distributor is running at {distributor_url}\n")
    
    # Create analyzer pool
    logger.info("Creating analyzer pool...")
    analyzer_pool = AnalyzerPool(
        distributor_url=distributor_url,
        num_analyzers=4,
        weights=[0.4, 0.3, 0.2, 0.1],
        processing_delay=0.1
    ) 
    
    # Create emitter pool
    logger.info("Creating emitter pool...")
    emitter_pool = LogEmitterPool(
        distributor_url=distributor_url,
        num_emitters=10,
        base_interval=0.5,
        interval_jitter=0.2
    )
    
    # Start both pools
    logger.info("\n" + "="*60)
    logger.info("STARTING SYSTEM")
    logger.info("="*60)
    await analyzer_pool.start()
    await emitter_pool.start()
    logger.info("✓ All components started\n")
    
    try:
        # Monitor while running
        logger.info(f"Running for up to {run_duration_seconds} seconds or {max_logs_cutoff} logs...\n")
        
        for i in range(run_duration_seconds):
            await asyncio.sleep(1)
            
            # Check cutoffs
            emitter_stats = emitter_pool.get_stats()
            analyzer_stats = analyzer_pool.get_stats()
            
            # Print progress every 5 seconds
            if (i + 1) % 5 == 0:
                logger.info(
                    f"[{i+1}s] "
                    f"Emitted: {emitter_stats['total_emitted']}, "
                    f"Processed: {analyzer_stats['total_processed']}, "
                    f"Queue: {await get_queue_depth(distributor_url)}"
                )
            
            # Check if we hit the log cutoff
            if emitter_stats['total_emitted'] >= max_logs_cutoff:
                logger.info(f"\n✓ Reached {max_logs_cutoff} logs cutoff")
                break
    
    except KeyboardInterrupt:
        logger.info("\n✓ Received interrupt signal")
    
    finally:
        # Shutdown sequence
        logger.info("\n" + "="*60)
        logger.info("SHUTTING DOWN")
        logger.info("="*60)
        
        # Step 1: Stop emitters (no more new logs)
        logger.info("\n[1/3] Stopping emitter pool...")
        await emitter_pool.stop()
        
        # Capture emitter stats immediately after stopping
        emitter_stats = emitter_pool.get_stats()
        logger.info(f"✓ Emitters stopped (total emitted: {emitter_stats['total_emitted']})")
        
        # Give a moment for in-flight requests to reach distributor
        logger.info("   Waiting for in-flight requests to complete...")
        await asyncio.sleep(2)
        
        # Step 2: Wait for distributor queue to drain
        logger.info("\n[2/3] Waiting for distributor queue to drain...")
        queue_drained = False
        for i in range(60):  # Wait up to 60 seconds
            queue_depth = await get_queue_depth(distributor_url)
            in_progress = (await get_distributor_stats(distributor_url)).get('in_progress', 0)
            
            if queue_depth == 0 and in_progress == 0:
                logger.info(f"✓ Queue drained after {i+1} seconds")
                queue_drained = True
                break
            
            if (i + 1) % 5 == 0:
                logger.info(f"   [{i+1}s] Queue: {queue_depth}, In-progress: {in_progress}")
            
            await asyncio.sleep(1)
        
        if not queue_drained:
            queue_depth = await get_queue_depth(distributor_url)
            logger.warning(f"⚠️  Queue did not fully drain (remaining: {queue_depth})")
        
        # Give a moment for final status updates to reach distributor
        await asyncio.sleep(2)
        
        # Step 3: Stop analyzers
        logger.info("\n[3/3] Stopping analyzer pool...")
        
        # Capture stats BEFORE stopping (stopping clears the analyzer list)
        analyzer_stats = analyzer_pool.get_stats()
        distribution = analyzer_pool.get_distribution()
        
        await analyzer_pool.stop()
        logger.info("✓ Analyzers stopped")
        
        # Give distributor a moment to process final updates
        await asyncio.sleep(1)
        
        # Output final statistics
        logger.info("\n" + "="*60)
        logger.info("FINAL STATISTICS")
        logger.info("="*60)
        
        # Get final distributor stats
        distributor_stats = await get_distributor_stats(distributor_url)
        
        # Display stats
        logger.info("\nEmitters:")
        logger.info(f"  Total Emitted: {emitter_stats['total_emitted']}")
        logger.info(f"  Num Emitters: {emitter_stats['num_emitters']}")
        
        if distributor_stats:
            logger.info("\nDistributor:")
            logger.info(f"  Total Received: {distributor_stats['total_received']}")
            logger.info(f"  Total Completed: {distributor_stats['total_completed']}")
            logger.info(f"  Total Failed: {distributor_stats['total_failed']}")
            logger.info(f"  Queue Depth: {distributor_stats['queue_depth']}")
            logger.info(f"  In Progress: {distributor_stats['in_progress']}")
        logger.info("\nAnalyzers (Overall):")
        logger.info(f"  Total Processed: {analyzer_stats['total_processed']}")
        if analyzer_stats.get('scaled_down_processed', 0) > 0:
            logger.info(f"    - By Current: {analyzer_stats.get('current_analyzers_processed', 0)}")
            logger.info(f"    - By Scaled-Down: {analyzer_stats.get('scaled_down_processed', 0)}")
        logger.info(f"  Total Failed: {analyzer_stats['total_failed']}")
        logger.info(f"  Num Analyzers: {analyzer_stats['num_analyzers']}")
        
        # Per-analyzer breakdown
        if analyzer_stats['analyzer_stats']:
            logger.info("\nPer-Analyzer Statistics:")
            logger.info(f"  {'Analyzer ID':<20} {'Weight':<10} {'Logs Processed':<15} {'Failed':<10} {'Tasks/sec':<12}")
            logger.info("  " + "-"*70)
            
            for analyzer_id, astats in analyzer_stats['analyzer_stats'].items():
                logger.info(
                    f"  {analyzer_id:<20} "
                    f"{astats['weight']:<10.2f} "
                    f"{astats['total_processed']:<15} "
                    f"{astats['total_failed']:<10} "
                    f"{astats['tasks_per_second']:<12.2f}"
                )
        
        # Distribution (expected vs actual - already captured before stopping)
        if distribution['total_processed'] > 0:
            logger.info("\nWork Distribution (Expected vs Actual):")
            logger.info(f"  {'Analyzer':<20} {'Expected %':<12} {'Actual %':<12} {'Deviation'}")
            logger.info("  " + "-"*60)
            
            for analyzer_id, dist in distribution['distribution'].items():
                deviation = dist['actual_percentage'] - dist['expected_percentage']
                deviation_str = f"{deviation:+.1f}%"
                logger.info(
                    f"  {analyzer_id:<20} "
                    f"{dist['expected_percentage']:<12.1f} "
                    f"{dist['actual_percentage']:<12.1f} "
                    f"{deviation_str}"
                )
        
        logger.info("\n" + "="*60)
        logger.info("DEMO COMPLETE")
        logger.info("="*60 + "\n")


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


if __name__ == "__main__":
    asyncio.run(main())
