"""
Test script to simulate Cloud Run startup environment.
This helps diagnose startup failures by replicating Cloud Run conditions locally.
"""
import os
import sys
import time
import socket
import subprocess
from threading import Thread

def check_port_open(host='0.0.0.0', port=8080, timeout=5):
    """Check if a port is listening."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host if host != '0.0.0.0' else '127.0.0.1', port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"Error checking port: {e}")
        return False

def run_startup_with_timeout(timeout=240):
    """Run startup.py and monitor if it binds to port within timeout."""
    print("=" * 80)
    print("CLOUD RUN STARTUP SIMULATION")
    print("=" * 80)

    # Set Cloud Run environment variables
    os.environ['PORT'] = '8080'
    os.environ['ENVIRONMENT'] = 'production'
    os.environ['REDIS_HOST'] = 'localhost'  # Simulating no Redis like Cloud Run

    print(f"\n1. Environment Variables:")
    print(f"   PORT={os.environ.get('PORT')}")
    print(f"   ENVIRONMENT={os.environ.get('ENVIRONMENT')}")
    print(f"   REDIS_HOST={os.environ.get('REDIS_HOST')}")

    print(f"\n2. Starting application (timeout={timeout}s)...")
    start_time = time.time()

    # Start the application in a subprocess
    proc = subprocess.Popen(
        [sys.executable, 'startup.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    # Monitor output in separate threads
    def print_output(pipe, prefix):
        for line in iter(pipe.readline, ''):
            if line:
                elapsed = time.time() - start_time
                print(f"   [{elapsed:6.2f}s] {prefix}: {line.rstrip()}")

    Thread(target=print_output, args=(proc.stdout, 'STDOUT'), daemon=True).start()
    Thread(target=print_output, args=(proc.stderr, 'STDERR'), daemon=True).start()

    # Wait for port to be available
    port_open = False
    check_interval = 1

    print(f"\n3. Monitoring port 8080...")
    while time.time() - start_time < timeout:
        if check_port_open(port=8080):
            elapsed = time.time() - start_time
            print(f"\n✓ SUCCESS: Port 8080 is listening after {elapsed:.2f} seconds")
            port_open = True
            break
        time.sleep(check_interval)

    if not port_open:
        elapsed = time.time() - start_time
        print(f"\n✗ FAILURE: Port 8080 NOT listening after {elapsed:.2f} seconds")
        print(f"   This matches the Cloud Run timeout error!")

    # Check if process is still running
    if proc.poll() is None:
        print(f"\n4. Process status: RUNNING")
        if port_open:
            print(f"   Startup successful - terminating test...")
        else:
            print(f"   Process running but port not open - checking what's blocking...")
        proc.terminate()
        proc.wait(timeout=5)
    else:
        print(f"\n4. Process status: EXITED with code {proc.returncode}")
        print(f"   The application crashed during startup!")

    print("\n" + "=" * 80)
    print("DIAGNOSIS SUMMARY:")
    print("=" * 80)
    if port_open:
        print("✓ Container would PASS Cloud Run health check")
        print("  - Port 8080 is listening correctly")
        print("  - Startup time is within limits")
    else:
        print("✗ Container would FAIL Cloud Run health check")
        print("  - Port 8080 is NOT listening")
        print("  - Possible causes:")
        print("    1. Application crashed during startup")
        print("    2. Blocking operation preventing port binding")
        print("    3. Port configuration error")
        print("    4. Import errors or dependency issues")
    print("=" * 80)

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    run_startup_with_timeout(timeout=60)  # 60s timeout for testing
