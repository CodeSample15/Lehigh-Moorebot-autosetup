import socket
import paramiko
from colorama import Fore, init
import time
import os
import sys

#start colorama
init()

#to store the names and the mac addresses of the robots
robot_macs_dict = {}

DIRECT_CONNECTION_IP = '10.42.0.1'
DIRECT_CONNECTION_LOCAL_IP = '10.42.0.124'

#for ssh login
ROBOT_USERNAME = 'linaro'
ROBOT_PASSWORD = 'linaro'

#read values from mac_addresses file into dictionary mapping robot names to mac addresses
def load_macs():
    with open('mac_addresses.txt', 'r') as f:
        for line in f.readlines():
            line = line.rstrip()
            name = line.split('-')[0]
            mac = line.split('-')[1]
            robot_macs_dict[name] = mac

def dump_macs():
    with open('mac_addresses.txt', 'w') as f:
        for name in robot_macs_dict.keys():
            f.write(f'{name}-{robot_macs_dict[name]}')

def wait_for_eof(channel, timeout=5):
    #fix for paramiko eof problem described here: https://github.com/paramiko/paramiko/issues/109
    #code from https://stackoverflow.com/questions/35266753/paramiko-python-module-hangs-at-stdout-read
    end_t = time.time() + timeout
    while not channel.channel.eof_received:
        time.sleep(1)
        if time.time() > end_t:
            channel.channel.close()
            break

def sftp_file_transaction(ip, remote_path, local_path, get=True):
    transport = paramiko.Transport(ip)
    transport.connect(username=ROBOT_USERNAME, password=ROBOT_PASSWORD)
    sftp = paramiko.SFTPClient.from_transport(transport)

    if get:
        sftp.get(remotepath=remote_path, localpath=local_path)
    else:
        sftp.put(localpath=local_path, remotepath=remote_path)

    sftp.close()
    transport.close()

#read from network_conf.txt file
wifi_info = {}
try:
    with open('network_conf.txt', 'r') as f:
        for line in f:
            line = line.rstrip()
            segs = line.split('=')
            wifi_info[segs[0]] = segs[1]
except:
    print(Fore.RED + "Unable to open network configuration file!")

def main():
    #load mac addresses from disk
    load_macs()

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())

    #print welcome/start message
    print(Fore.RESET + "--------------------------------------")
    print(Fore.MAGENTA + "Moorebot setup tool")
    print(Fore.RESET + "--------------------------------------")
    print("")
    print("Detecting connection mode...")

    # Check to see if connected to robot directly
    ip = socket.gethostbyname(socket.gethostname())
    if ip == DIRECT_CONNECTION_LOCAL_IP:
        print(Fore.CYAN + "DIRECT MODE: " + Fore.RESET + " Attempting SSH...   ", end='')
        sys.stdout.flush()

        # SSH into robot directly
        try:
            ssh.connect(DIRECT_CONNECTION_IP, 22, username=ROBOT_USERNAME, password=ROBOT_PASSWORD)
            print(Fore.GREEN + "Connected!")

            #check for root access
            print(Fore.RESET + "Checking for sudo access...   ", end='')
            sys.stdout.flush()
            _, std_out, std_err = ssh.exec_command('sudo su root')
            wait_for_eof(std_out, 2)
            wait_for_eof(std_err, 2)
            print(Fore.GREEN + 'Done')

            if len(std_out.read()) == 0 and len(std_err.read()) == 0:
                # we do have root access
                # *Hacker voice*: I'm in
                
                #remove proxies just in case
                print(Fore.RESET + 'Removing proxies and protecting device...   ', end='')
                sys.stdout.flush()
                ssh.exec_command('rm /opt/sockproxy/proxy_list.json')
                ssh.exec_command('systemctl disable sockproxy.service')
                ssh.exec_command('route add 62.210.208.47 gw 127.0.0.1 lo')
                ssh.exec_command('route add 45.35.33.24 gw 127.0.0.1 lo')
                ssh.exec_command('route add 118.107.244.35 gw 127.0.0.1 lo')
                print(Fore.GREEN + 'Done')

                #get mac address
                print(Fore.RESET + 'Detecting robot name...   ', end='')
                sys.stdout.flush()
                _, std_out, _ = ssh.exec_command('sudo ifconfig | grep ether')
                wait_for_eof(std_out)
                mac = std_out.readlines()[0].strip()[6:23]

                robot_name = ''
                for name in robot_macs_dict.keys():
                    if robot_macs_dict[name] == mac:
                        #robot found
                        robot_name = name
                        print(Fore.GREEN + f'{name} found!')
                
                #name robot if a new one is found
                if robot_name == '':
                    robot_name = input(Fore.YELLOW + 'New robot detected. Enter name: ')
                    robot_macs_dict[robot_name] = mac
                    dump_macs() #save new mac address to file

                #save name to file
                print(Fore.RESET + 'Ensuring correct WiFi name...   ', end='')
                sys.stdout.flush()

                _, std_out, _ = ssh.exec_command('cat /etc/hostapd/hostapd.conf')
                wait_for_eof(std_out)

                #read and edit file contents
                file_contents = [line for line in std_out.readlines()]
                if len(file_contents) == 0:
                    raise Exception('Error reading hostapd file contents')

                file_contents[3] = f'ssid={robot_name}\n'
                new_file_str = ''.join(file_contents)
                #write to remote
                _, std_out, std_err = ssh.exec_command(f'echo "{new_file_str}" | sudo tee /etc/hostapd/hostapd.conf')
                wait_for_eof(std_out)
                wait_for_eof(std_err)
                print(Fore.GREEN + 'Done')

                #give robot access to local network
                print(Fore.RESET + 'Adding wifi information...   ', end='')
                sys.stdout.flush()

                if len(wifi_info) == 0:
                    print(Fore.RED + 'Failed')
                else:
                    wifi_info_str = f"{wifi_info['ssid']}\n{wifi_info['pswd']}"
                    _, std_out, std_err = ssh.exec_command(f'echo "{wifi_info_str}" | sudo tee /var/roller_eye/config/wifi')
                    wait_for_eof(std_out)
                    wait_for_eof(std_err)
                    print(Fore.GREEN + 'Done')

                print(Fore.CYAN + 'Config complete, shutting down robot for reboot.')
                ssh.exec_command('sudo reboot')
            else:
                # do not have root access, fix that
                temp_file_name = "temp_local"
                remote_file_name = "/etc/rc.local"
                sftp_file_transaction(DIRECT_CONNECTION_IP, remote_file_name, temp_file_name) #fetch remote rc.local file

                new_line = 'chmod 4755 /usr/bin/sudo\n' #line to be written to file to get sudo access
                end_line = 'exit 0\n' #last line in the file, used as reference for line write location

                file_contents = []
                with open(temp_file_name, "r") as f:
                    for line in f.readlines():
                        file_contents.append(line)

                #file already has the line we need, request user to reboot the robot
                if new_line in file_contents:
                    print(Fore.YELLOW + "NO ROOT ACCESS! Modifications not needed. Please reboot robot and rerun this script")
                else:
                    try:
                        print(Fore.YELLOW + "NO ROOT ACCESS! Modifying files...   ", end='')
                        sys.stdout.flush()

                        #make edits to file contents in memory
                        end_line_old_index = file_contents.index(end_line)
                        file_contents.append(end_line) #make sure file ends with this line
                        file_contents[end_line_old_index] = new_line #replace the old end-of-file location with the new line

                        #write file contents to local file
                        with open(temp_file_name, "w", newline='\n') as f:
                            for line in file_contents:
                                f.write(line)

                        #upload local file to robot
                        sftp_file_transaction(DIRECT_CONNECTION_IP, remote_file_name, temp_file_name, get=False)

                        print(Fore.GREEN + "Done")
                        print(Fore.YELLOW + "Please reboot robot")
                    except Exception as e:
                        print()
                        print(Fore.RED + "ERROR: Problem writing to robot! Dumping file contents for debugging:")
                        print("-"*50)
                        for line in file_contents:
                            print(line.rstrip())
                        print("-"*50)

                os.remove(temp_file_name)
        except Exception as e:
            print(Fore.RED + str(e))
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