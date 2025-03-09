import socket
import paramiko
from colorama import Fore, init
import time

#start colorama
init()

#to store the names and the mac addresses of the robots
robot_macs_dict = {}

DIRECT_CONNECTION_IP = '10.42.0.1'
DIRECT_CONNECTION_LOCAL_IP = '10.42.0.124'

#for ssh login
ROBOT_USERNAME = 'linaro'
ROBOT_PASSWORD = 'linaro'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())

#read values from mac_addresses file into dictionary mapping robot names to mac addresses
def load_macs():
    with open('mac_addresses.txt', 'r') as f:
        for line in f.readlines():
            line = line.rstrip()
            name = line.split('-')[0]
            mac = line.split('-')[1]
            robot_macs_dict[name] = mac

def wait_for_eof(channel, timeout=5):
    #fix for paramiko eof problem described here: https://github.com/paramiko/paramiko/issues/109
    #code from https://stackoverflow.com/questions/35266753/paramiko-python-module-hangs-at-stdout-read
    end_t = time.time() + timeout
    while not channel.channel.eof_received:
        time.sleep(1)
        if time.time() > end_t:
            channel.channel.close()
            break

def main():
    #load mac addresses from disk
    load_macs()

    #print welcome/start message
    print(Fore.RESET + "--------------------------------------")
    print(Fore.CYAN + "Moorebot setup tool")
    print(Fore.RESET + "--------------------------------------")
    print("")
    print("Detecting connection mode...")

    # Check to see if connected to robot directly
    ip = socket.gethostbyname(socket.gethostname())
    if ip == DIRECT_CONNECTION_LOCAL_IP:
        print(Fore.CYAN + "DIRECT MODE: " + Fore.RESET + " Attempting SSH...   ", end='')

        # SSH into robot directly
        try:
            ssh.connect(DIRECT_CONNECTION_IP, 22, username=ROBOT_USERNAME, password=ROBOT_PASSWORD)
            print(Fore.GREEN + "Connected!")

            #check for root access
            _, std_out, std_err = ssh.exec_command('sudo su root')
            wait_for_eof(std_out)
            wait_for_eof(std_err)

            if len(std_out.read()) == 0 and len(std_err.read()) == 0:
                # we do have root access
                # *Hacker voice*: I'm in
                
                #remove proxies just in case
                print(Fore.RESET + 'Removing proxies and protecting device...   ', end='')
                ssh.exec_command('rm /opt/sockproxy/proxy_list.json')
                ssh.exec_command('systemctl disable sockproxy.service')
                ssh.exec_command('route add 62.210.208.47 gw 127.0.0.1 lo')
                ssh.exec_command('route add 45.35.33.24 gw 127.0.0.1 lo')
                ssh.exec_command('route add 118.107.244.35 gw 127.0.0.1 lo')
                print(Fore.GREEN + 'Done')

                #get mac address

                #name robot
            else:
                pass
            # do not have root access, fix that
            _, std_out, _ = ssh.exec_command('cat /etc/rc.local')
            wait_for_eof(std_out)

            new_line = 'chmod 4755 /usr/bin/sudo\n' #line to be written to file to get sudo access
            end_line = 'exit 0\n' #last line in the file, used as reference for line write location

            file_contents = []
            for line in std_out:
                file_contents.append(line)

            #file already has the line we need, request user to reboot the robot
            if new_line in file_contents:
                print(Fore.YELLOW + "NO ROOT ACCESS! Modifications not needed. Please reboot robot and rerun this script")
            else:
                try:
                    print(Fore.YELLOW + "NO ROOT ACCESS! Modifying files...   ", end='')
                    #write new file
                    end_line_old_index = file_contents.index(end_line)
                    file_contents.append(end_line) #make sure file ends with this line
                    file_contents[end_line_old_index] = new_line #replace the old end-of-file location with the new line

                    _, o, e = ssh.exec_command(f'echo {''.join(file_contents)} >> /etc/rc.local')
                    wait_for_eof(o)
                    wait_for_eof(e)
                    print(o.read())
                    print(e.read())

                    print(Fore.GREEN + "Done")
                except:
                    print(Fore.RED + "ERROR: Problem writing to robot! Dumping file contents for debugging:")
                    print("-"*50)
                    for line in file_contents:
                        print(line.rstrip())
                    print("-"*50)
        except:
            print()
            print(Fore.RED + "SSH connection failed! Exiting...")
            ssh.close()
            return
    else:
        #robot not directly connected, search wifi
        print(Fore.CYAN + "INDIRECT MODE:" + Fore.RESET + " Starting network scan...")

    #clean up
    ssh.close()
    print(Fore.RESET, end='')

if __name__ == '__main__':
    main()

#reset text color no matter what
print(Fore.RESET)