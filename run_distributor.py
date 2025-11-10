"""
Simple script to run the distributor.

Usage:
    python run_distributor.py
"""
import uvicorn
import logging

# Suppress noisy access logs
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

if __name__ == "__main__":
    uvicorn.run(
        "distributor.distributor:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=False  # Disable access logs
    )

