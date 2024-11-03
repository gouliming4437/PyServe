import threading
import http.client
import time
from urllib.parse import quote

def make_request(user_id, path="/"):
    try:
        start_time = time.time()
        conn = http.client.HTTPConnection("localhost", 8000)
        
        # Encode the path for Chinese characters
        encoded_path = quote(path)
        conn.request("GET", encoded_path)
        
        response = conn.getresponse()
        end_time = time.time()
        
        print(f"User {user_id}: Response time {end_time - start_time:.2f} seconds")
        print(f"User {user_id}: Status {response.status}")
        
        # Read and close the response to free up the connection
        response.read()
        conn.close()
        
    except Exception as e:
        print(f"User {user_id}: Error - {str(e)}")

def test_concurrent_users():
    # Test different pages
    test_paths = [
        "/",  # Home page
        "/page/tech_python",  # Python page
        "/search?q=python",  # Search
        "/page/文件入口"  # Chinese page
    ]
    
    threads = []
    num_users_per_path = 5  # 5 users per path
    
    # Create threads for each path
    for path in test_paths:
        for i in range(num_users_per_path):
            thread = threading.Thread(
                target=make_request, 
                args=(f"{i}-{path}", path)
            )
            threads.append(thread)
    
    # Start all threads with a small delay
    for thread in threads:
        thread.start()
        time.sleep(0.1)  # Small delay between starts
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()

if __name__ == "__main__":
    print("Starting concurrent user test...")
    print(f"Testing with {5} concurrent users per page type...")
    test_start = time.time()
    
    test_concurrent_users()
    
    test_end = time.time()
    print(f"\nTotal test time: {test_end - test_start:.2f} seconds") 