import ipaddress
import socket
import paramiko
import threading

from botsetup import robot_macs_dict, load_macs, wait_for_eof, ROBOT_USERNAME, ROBOT_PASSWORD

#this you have to set manually
NET_MASK = '24'

found_ips = {}
check_threads = []

def check_ip(ip):
    #attempt to open ssh 
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())

        ssh.connect(ip, 22, username=ROBOT_USERNAME, password=ROBOT_PASSWORD, timeout=5)

        mac = ''
        _, std_out, _ = ssh.exec_command('sudo ifconfig | grep ether')
        wait_for_eof(std_out)
        mac = std_out.readlines()[0].strip()[6:23]

        for name in robot_macs_dict.keys():
            if robot_macs_dict[name] == mac:
                #robot found
                found_ips[name] = ip

        ssh.close()
    except:
        pass #ignore, just keep on scannin

def scan():
    load_macs()

    ip_addr = socket.gethostbyname(socket.gethostname())
    ips = [str(ip) for ip in ipaddress.ip_network(f'{ip_addr}/{NET_MASK}', False).hosts()]

    for ip in ips:
        new_thread = threading.Thread(target=check_ip, args=(ip,))
        new_thread.start()
        check_threads.append(new_thread)

    while len(check_threads) > 0:
        for t in check_threads:
            if not t.is_alive():
                t.join()
                check_threads.remove(t)
        print(f'Waiting for threads to stop...  ({len(check_threads)})', end='\r')
    print("Done" + " "*100)

if __name__ == '__main__':
    scan() #for debugging purposes