'''
    Simple python file to brodcast a robot's ip over the network to a central server
    (allows for a central server to keep track of robot IPs)'

    This script will be uploaded to the robots via the botsetup.py script
'''

import subprocess
import socket
import time
import os

SERVER_IP = '127.0.0.1'
SERVER_PORT = 9999
BROADCAST_DELAY = 1 #how mahy seconds to wait between each broadcast attempt

#helper method to get the ip of the machine and return as a string
def get_ip() -> str:
    hostname = socket.gethostname()
    return socket.gethostbyname(hostname)

def get_mac() -> str:
    if os.name == 'nt':
        return "TEST" #for testing purposes on windows machines

    output = subprocess.check_output('sudo ifconfig | grep ether', shell=True, text=True)
    mac = output.strip()[6:23]
    return mac

while True:
    success = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect((SERVER_IP, SERVER_PORT))

            print('[+] Connected! Sending message...')
            msg = get_mac() + '-' + get_ip()
            client.send(msg.encode())
            print('[+] Sent! Awaiting response...')
            resp = client.recv(1024)
            client.close()
            print('[+] Message recieved!')
            success = True
    except:
        pass
    
    if success:
        break
    time.sleep(BROADCAST_DELAY)