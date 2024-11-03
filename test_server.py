import threading
import http.client
import time
from urllib.parse import quote

def make_request(user_id, path="/"):
    try:
        start_time = time.time()
        conn = http.client.HTTPConnection("localhost", 8000)
        
        # Encode path for Chinese characters
        encoded_path = quote(path)
        conn.request("GET", encoded_path)
        
        response = conn.getresponse()
        end_time = time.time()
        
        print(f"User {user_id}: Response time {end_time - start_time:.2f} seconds")
        print(f"User {user_id}: Status {response.status}")
        
        # Clean up
        response.read()
        conn.close()
        
    except Exception as e:
        print(f"User {user_id}: Error - {str(e)}")

def run_test():
    # Test different pages
    test_paths = [
        "/",
        "/page/tech_python",
        "/page/文件入口",
        "/search?q=python"
    ]
    
    threads = []
    users_per_path = 5  # 5 concurrent users per path
    
    # Create threads for each test case
    for path in test_paths:
        for i in range(users_per_path):
            thread = threading.Thread(
                target=make_request,
                args=(f"{i}-{path}", path)
            )
            threads.append(thread)
    
    # Start all threads
    print(f"Starting test with {len(threads)} concurrent requests...")
    test_start = time.time()
    
    for thread in threads:
        thread.start()
        time.sleep(0.1)  # Small delay between starts
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    test_end = time.time()
    print(f"\nTest completed in {test_end - test_start:.2f} seconds")

if __name__ == "__main__":
    run_test() 