"""
Load testing script for the pull-based work queue system.

This script tests:
- High throughput log submission
- Analyzer capacity and concurrency
- Task distribution based on weights
- System behavior under load
"""
import asyncio
import httpx
import time
import logging
import argparse
from datetime import datetime
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress noisy HTTP logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class LoadTester:
    """Load tester for the distributor system."""
    
    def __init__(self, distributor_url: str = "http://localhost:8000"):
        self.distributor_url = distributor_url
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # Statistics
        self.logs_sent = 0
        self.logs_succeeded = 0
        self.logs_failed = 0
        self.start_time = None
    
    async def send_log(self, log_data: dict) -> bool:
        """Send a single log to the distributor."""
        try:
            response = await self.client.post(
                f"{self.distributor_url}/submit",
                json=log_data
            )
            
            if response.status_code == 200:
                self.logs_succeeded += 1
                return True
            else:
                self.logs_failed += 1
                return False
                
        except Exception as e:
            logger.debug(f"Error sending log: {e}")
            self.logs_failed += 1
            return False
    
    async def generate_and_send_log(self, index: int):
        """Generate and send a synthetic log."""
        import random
        
        levels = ["DEBUG", "INFO", "WARN", "ERROR"]
        sources = ["web-app", "api-server", "database", "cache", "worker"]
        
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": random.choice(levels),
            "message": f"Load test log message #{index}",
            "source": random.choice(sources),
            "metadata": {
                "test_id": f"load-test-{index}",
                "iteration": index
            }
        }
        
        self.logs_sent += 1
        return await self.send_log(log_data)
    
    async def run_load_test(
        self,
        total_logs: int = 1000,
        concurrent_requests: int = 50,
        burst_mode: bool = False
    ):
        """
        Run a load test.
        
        Args:
            total_logs: Total number of logs to send
            concurrent_requests: Max concurrent requests
            burst_mode: If True, send all at once; if False, rate limit
        """
        logger.info("="*60)
        logger.info("Starting Load Test")
        logger.info("="*60)
        logger.info(f"Total logs: {total_logs}")
        logger.info(f"Concurrent requests: {concurrent_requests}")
        logger.info(f"Burst mode: {burst_mode}")
        logger.info("="*60)
        
        self.start_time = time.time()
        
        if burst_mode:
            # Send all logs as fast as possible
            await self._burst_load(total_logs, concurrent_requests)
        else:
            # Send with controlled rate
            await self._controlled_load(total_logs, concurrent_requests)
        
        elapsed = time.time() - self.start_time
        self._print_summary(elapsed)
    
    async def _burst_load(self, total_logs: int, concurrency: int):
        """Send logs in burst mode (as fast as possible)."""
        semaphore = asyncio.Semaphore(concurrency)
        
        async def send_with_semaphore(index: int):
            async with semaphore:
                await self.generate_and_send_log(index)
                
                if (index + 1) % 100 == 0:
                    elapsed = time.time() - self.start_time
                    rate = (index + 1) / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"Progress: {index + 1}/{total_logs} "
                        f"({rate:.1f} logs/sec)"
                    )
        
        tasks = [send_with_semaphore(i) for i in range(total_logs)]
        await asyncio.gather(*tasks)
    
    async def _controlled_load(self, total_logs: int, rate_limit: int):
        """Send logs with controlled rate."""
        batch_size = 10
        batches = (total_logs + batch_size - 1) // batch_size
        
        for batch in range(batches):
            start_idx = batch * batch_size
            end_idx = min(start_idx + batch_size, total_logs)
            
            # Send batch
            tasks = [
                self.generate_and_send_log(i)
                for i in range(start_idx, end_idx)
            ]
            await asyncio.gather(*tasks)
            
            # Progress update
            if (batch + 1) % 10 == 0:
                elapsed = time.time() - self.start_time
                rate = end_idx / elapsed if elapsed > 0 else 0
                logger.info(
                    f"Progress: {end_idx}/{total_logs} "
                    f"({rate:.1f} logs/sec)"
                )
            
            # Small delay between batches
            await asyncio.sleep(0.01)
    
    def _print_summary(self, elapsed: float):
        """Print load test summary."""
        logger.info("")
        logger.info("="*60)
        logger.info("Load Test Summary")
        logger.info("="*60)
        logger.info(f"Total time: {elapsed:.2f} seconds")
        logger.info(f"Logs sent: {self.logs_sent}")
        logger.info(f"Logs succeeded: {self.logs_succeeded}")
        logger.info(f"Logs failed: {self.logs_failed}")
        logger.info(
            f"Success rate: {100 * self.logs_succeeded / self.logs_sent:.1f}%"
        )
        logger.info(f"Throughput: {self.logs_sent / elapsed:.1f} logs/sec")
        logger.info("="*60)
    
    async def get_stats(self) -> dict:
        """Get distributor statistics."""
        try:
            response = await self.client.get(f"{self.distributor_url}/stats")
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}
    
    async def verify_processing(self, wait_time: int = 10):
        """
        Verify that logs are being processed.
        
        Args:
            wait_time: How long to wait for processing
        """
        logger.info("")
        logger.info("="*60)
        logger.info(f"Waiting {wait_time} seconds for processing...")
        logger.info("="*60)
        
        for i in range(wait_time):
            await asyncio.sleep(1)
            
            stats = await self.get_stats()
            if stats:
                logger.info(
                    f"[{i+1}/{wait_time}] Queue: {stats.get('queue_depth', 0)}, "
                    f"In-Progress: {stats.get('in_progress', 0)}, "
                    f"Completed: {stats.get('total_completed', 0)}"
                )
    
    async def print_final_stats(self):
        """Print final system statistics."""
        stats = await self.get_stats()
        
        if not stats:
            logger.error("Could not retrieve statistics")
            return
        
        logger.info("")
        logger.info("="*60)
        logger.info("System Statistics")
        logger.info("="*60)
        logger.info(f"Total received: {stats.get('total_received', 0)}")
        logger.info(f"Total completed: {stats.get('total_completed', 0)}")
        logger.info(f"Total failed: {stats.get('total_failed', 0)}")
        logger.info(f"Total requeued: {stats.get('total_requeued', 0)}")
        logger.info(f"Queue depth: {stats.get('queue_depth', 0)}")
        logger.info(f"In progress: {stats.get('in_progress', 0)}")
        logger.info(f"Backpressure: {stats.get('backpressure', 0):.1f}")
        
        analyzers_info = stats.get('analyzers', {})
        logger.info(f"Analyzers: {analyzers_info.get('total', 0)} total, "
                   f"{analyzers_info.get('active', 0)} active")
        logger.info("="*60)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


async def run_comprehensive_test():
    """Run a comprehensive test suite."""
    tester = LoadTester()
    
    try:
        logger.info("\n" + "="*60)
        logger.info("COMPREHENSIVE LOAD TEST SUITE")
        logger.info("="*60 + "\n")
        
        # Test 1: Warm-up
        logger.info("Test 1: Warm-up (100 logs)")
        logger.info("-" * 40)
        await tester.run_load_test(total_logs=100, concurrent_requests=10)
        await tester.verify_processing(5)
        
        # Reset stats
        tester.logs_sent = 0
        tester.logs_succeeded = 0
        tester.logs_failed = 0
        
        # Test 2: Medium load
        logger.info("\nTest 2: Medium load (1000 logs, 50 concurrent)")
        logger.info("-" * 40)
        await tester.run_load_test(total_logs=1000, concurrent_requests=50)
        await tester.verify_processing(10)
        
        # Reset stats
        tester.logs_sent = 0
        tester.logs_succeeded = 0
        tester.logs_failed = 0
        
        # Test 3: High load
        logger.info("\nTest 3: High load (5000 logs, 100 concurrent)")
        logger.info("-" * 40)
        await tester.run_load_test(
            total_logs=5000,
            concurrent_requests=100,
            burst_mode=True
        )
        await tester.verify_processing(20)
        
        # Print final stats
        await tester.print_final_stats()
        
    finally:
        await tester.close()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Load test the distributor")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Distributor URL"
    )
    parser.add_argument(
        "--logs",
        type=int,
        default=1000,
        help="Number of logs to send"
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=50,
        help="Concurrent requests"
    )
    parser.add_argument(
        "--burst",
        action="store_true",
        help="Burst mode (send as fast as possible)"
    )
    parser.add_argument(
        "--comprehensive",
        action="store_true",
        help="Run comprehensive test suite"
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=10,
        help="Seconds to wait after test for processing"
    )
    
    args = parser.parse_args()
    
    # Check if distributor is running
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{args.url}/health", timeout=2.0)
            if response.status_code != 200:
                logger.error("Distributor is not healthy!")
                return
    except Exception:
        logger.error(f"Cannot connect to distributor at {args.url}")
        logger.error("Please start the distributor first:")
        logger.error("  python -m uvicorn distributor.distributor:app --port 8000")
        return
    
    if args.comprehensive:
        await run_comprehensive_test()
    else:
        tester = LoadTester(args.url)
        try:
            await tester.run_load_test(
                total_logs=args.logs,
                concurrent_requests=args.concurrent,
                burst_mode=args.burst
            )
            await tester.verify_processing(args.wait)
            await tester.print_final_stats()
        finally:
            await tester.close()


if __name__ == "__main__":
    asyncio.run(main())

