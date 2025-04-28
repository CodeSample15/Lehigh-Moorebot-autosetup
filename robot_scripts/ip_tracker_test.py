'''
    This script is a test file for the ip_server.py script.
    Continuously listens for new IPs from different robots
'''

import socket
import threading

IP = '127.0.0.1'
PORT = 9999

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((IP, PORT))

server.listen(5)

def handle_connection(client_sock):
    request = client_sock.recv(1024)
    print(f'[+] Recieved: {request}')

    client_sock.send("RECIEVED".encode()) #tell the ip_server.py script to stop running
    client_sock.close()

while True:
    #run server
    client, addr = server.accept()
    print(f"[+] Accepted connection from: {addr[0]}:{addr[1]}")

    client_handle = threading.Thread(target=handle_connection, args=(client,), daemon=True)
    client_handle.start()