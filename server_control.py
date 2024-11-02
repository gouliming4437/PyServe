import os
import sys
import subprocess
import socket
import time

def is_server_running():
    try:
        # Try to create a socket on port 8000
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 8000))
        sock.close()
        return result == 0
    except:
        return False

def find_pid_by_port():
    try:
        # Use netstat to find the process using port 8000
        output = subprocess.check_output('netstat -aon | find ":8000" | find "LISTENING"', shell=True)
        return output.decode().strip().split()[-1]
    except:
        return None

def stop_server():
    pid = find_pid_by_port()
    if pid:
        os.system(f'taskkill /F /PID {pid}')
        print("Server stopped!")
    else:
        print("Server is not running!")

def start_server():
    if is_server_running():
        print("Server is already running!")
        return
    
    vbs_path = os.path.abspath("start_hidden.vbs")
    subprocess.Popen(['wscript.exe', vbs_path])
    print("Server started!")

def restart_server():
    stop_server()
    time.sleep(2)
    start_server()
    print("Server restarted!")

def show_status():
    if is_server_running():
        print("Server is running!")
    else:
        print("Server is not running!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python server_control.py [start|stop|restart|status]")
        sys.exit(1)

    command = sys.argv[1].lower()
    
    if command == "start":
        start_server()
    elif command == "stop":
        stop_server()
    elif command == "restart":
        restart_server()
    elif command == "status":
        show_status()
    else:
        print("Invalid command. Use: start, stop, restart, or status") 