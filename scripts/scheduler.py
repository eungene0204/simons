import time
import subprocess
import os
import sys
from datetime import datetime, timedelta
import pytz

def run_sync():
    """Execute the sync_data.py script."""
    print(f"[{datetime.now()}] Starting daily synchronization...")
    try:
        # Run sync_data.py from the project root
        result = subprocess.run([sys.executable, "scripts/sync_data.py"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[{datetime.now()}] Synchronization completed successfully.")
            # print(result.stdout)
        else:
            print(f"[{datetime.now()}] Synchronization failed with exit code {result.returncode}.")
            print(result.stderr)
    except Exception as e:
        print(f"[{datetime.now()}] Error running synchronization: {e}")

def get_seconds_until_midnight_kst():
    """Calculate seconds until next 00:00 KST."""
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)
    
    # Next midnight
    next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    wait_seconds = (next_run - now).total_seconds()
    return wait_seconds

def main():
    print("=== Simons Data Scheduler Started ===")
    print(f"Current Server Time: {datetime.now()}")
    
    # Optional: Initial sync on start
    # run_sync()
    
    while True:
        wait_sec = get_seconds_until_midnight_kst()
        target_time = (datetime.now(pytz.timezone('Asia/Seoul')) + timedelta(seconds=wait_sec)).strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"Next sync scheduled for: {target_time} KST (Waiting {wait_sec/3600:.2f} hours)")
        
        # Sleep until midnight (or check every hour to be safe)
        if wait_sec > 3600:
            time.sleep(3600)
        else:
            time.sleep(wait_sec + 1) # Add 1s buffer
            run_sync()
            time.sleep(60) # Prevent multiple runs within the same minute

if __name__ == "__main__":
    main()
