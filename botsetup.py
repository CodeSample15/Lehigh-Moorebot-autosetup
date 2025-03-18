import socket
import paramiko
from colorama import Fore, init
import time
import os
import sys
import threading

#start colorama
init()

#to store the names and the mac addresses of the robots
robot_macs_dict = {}

DIRECT_CONNECTION_IP = '10.42.0.1'
DIRECT_CONNECTION_LOCAL_IP = '10.42.0.124'

#for ssh login
ROBOT_USERNAME = 'linaro'
ROBOT_PASSWORD = 'linaro'

#for threading (set to true when config was successful)
success_flag = False

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

def print_conditional(string='', end='\n', output=True):
    if output: #makes it so that there doesn't need to be a bunch of if statements when logging is turned off
        print(string, end=end)

#read from network_conf.txt file
wifi_info = {}
def load_wifi_config():
    global wifi_info
    try:
        with open('network_conf.txt', 'r') as f:
            for line in f:
                line = line.rstrip()
                segs = line.split('=')
                wifi_info[segs[0]] = segs[1]
    except:
        print(Fore.RED + "Unable to open network configuration file!")

def run_setup(ip, set_wifi=True, verbose=True):
    global success_flag

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())

    success_flag = True # will bet to false if an error occurs

    try:
        ssh.connect(ip, 22, username=ROBOT_USERNAME, password=ROBOT_PASSWORD)
        print_conditional(Fore.GREEN + "Connected!", output=verbose)

        #check for root access
        print_conditional(Fore.RESET + "Checking for sudo access...   ", end='', output=verbose)
        sys.stdout.flush()
        _, std_out, std_err = ssh.exec_command('sudo su root')
        wait_for_eof(std_out, 2)
        wait_for_eof(std_err, 2)
        print_conditional(Fore.GREEN + 'Done', output=verbose)

        if len(std_out.read()) == 0 and len(std_err.read()) == 0:
            # we do have root access
            # *Hacker voice*: I'm in
            
            #remove proxies just in case
            print_conditional(Fore.RESET + 'Removing proxies and protecting device...   ', end='', output=verbose)
            sys.stdout.flush()
            ssh.exec_command('rm /opt/sockproxy/proxy_list.json')
            ssh.exec_command('systemctl disable sockproxy.service')
            ssh.exec_command('route add 62.210.208.47 gw 127.0.0.1 lo')
            ssh.exec_command('route add 45.35.33.24 gw 127.0.0.1 lo')
            ssh.exec_command('route add 118.107.244.35 gw 127.0.0.1 lo')
            print_conditional(Fore.GREEN + 'Done', output=verbose)

            #get mac address
            print_conditional(Fore.RESET + 'Detecting robot name...   ', end='', output=verbose)
            sys.stdout.flush()
            _, std_out, _ = ssh.exec_command('sudo ifconfig | grep ether')
            wait_for_eof(std_out)
            mac = std_out.readlines()[0].strip()[6:23]

            robot_name = ''
            for name in robot_macs_dict.keys():
                if robot_macs_dict[name] == mac:
                    #robot found
                    robot_name = name
                    print_conditional(Fore.GREEN + f'{name} found!', output=verbose)
            
            #name robot if a new one is found
            if robot_name == '':
                robot_name = input(Fore.YELLOW + 'New robot detected. Enter name: ')
                robot_macs_dict[robot_name] = mac
                dump_macs() #save new mac address to file

            #save name to file
            print_conditional(Fore.RESET + 'Ensuring correct WiFi name...   ', end='', output=verbose)
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
            print_conditional(Fore.GREEN + 'Done', output=verbose)

            #give robot access to local network
            if set_wifi:
                print_conditional(Fore.RESET + 'Adding wifi information...   ', end='', output=verbose)
                sys.stdout.flush()

                if len(wifi_info) == 0:
                    print_conditional(Fore.RED + 'Failed (No network_conf.txt)', output=verbose)
                else:
                    wifi_info_str = f"{wifi_info['ssid']}\n{wifi_info['pswd']}"
                    _, std_out, std_err = ssh.exec_command(f'echo "{wifi_info_str}" | sudo tee /var/roller_eye/config/wifi')
                    wait_for_eof(std_out)
                    wait_for_eof(std_err)
                    print(Fore.GREEN + 'Done')

            print_conditional(Fore.CYAN + 'Config complete. Reboot robot to apply changes', output=verbose)
            #ssh.exec_command('sudo reboot')
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
                print_conditional(Fore.YELLOW + "NO ROOT ACCESS! Modifications not needed. Please reboot robot and rerun this script", output=verbose)
            else:
                try:
                    print_conditional(Fore.YELLOW + "NO ROOT ACCESS! Modifying files...   ", end='', output=verbose)
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

                    print_conditional(Fore.GREEN + "Done", output=verbose)
                    print_conditional(Fore.YELLOW + "Please reboot robot", output=verbose)
                except Exception as e:
                    print_conditional(output=verbose)
                    print_conditional(Fore.RED + "ERROR: Problem writing to robot! Dumping file contents for debugging:", output=verbose)
                    print_conditional("-"*50, output=verbose)
                    for line in file_contents:
                        print_conditional(line.rstrip(), output=verbose)
                    print_conditional("-"*50, output=verbose)

                    success_flag = False

            os.remove(temp_file_name)
    except Exception as e:
        print_conditional(Fore.RED + str(e), output=verbose)
        print_conditional(Fore.RED + "SSH connection failed! Exiting...", output=verbose)
        ssh.close()

        success_flag = False
    
    ssh.close()

def main(config_wifi=False):
    load_macs() #load mac addresses from disk
    load_wifi_config() #load 

    #print welcome/start message
    print(Fore.RESET + "--------------------------------------")
    print(Fore.MAGENTA + "Moorebot setup tool")
    print(Fore.RESET + "--------------------------------------")
    print("")

    # Check to see if connected to robot directly
    ip = socket.gethostbyname(socket.gethostname())
    if ip == DIRECT_CONNECTION_LOCAL_IP:
        print(Fore.CYAN + "DIRECT MODE: " + Fore.RESET + " Attempting SSH...   ", end='')
        sys.stdout.flush()

        # SSH into robot directly
        run_setup(DIRECT_CONNECTION_IP, set_wifi=config_wifi, verbose=True)
    else:
        #robot not directly connected, search wifi
        print(Fore.CYAN + "INDIRECT MODE:" + Fore.RESET + " Starting network scan...")

        #get ips from scanner
        netscanner.scan()

        if len(netscanner.found_ips) == 0:
            print(Fore.YELLOW + 'No bots found on network.')
        else:
            print(Fore.GREEN + f'Found {len(netscanner.found_ips)} bot(s)!')

            for bot in netscanner.found_ips.keys():
                x = threading.Thread(target=run_setup, args=(netscanner.found_ips[bot], False, False))
                x.start()

                num_dots = 0
                while x.is_alive():
                    print(Fore.RESET + f'Configuring {bot}{'.'*num_dots}   ', end='\r')
                    num_dots = num_dots + 1 if num_dots <= 2 else 0

                    time.sleep(0.5)

                x.join()
                if success_flag:
                    print(Fore.RESET + f'Configuring {bot}...   ' + Fore.GREEN + 'Success!')
                else:
                    print(Fore.RESET + f'Configuring {bot}...   ' + Fore.RED + 'Failed!')

            print(Fore.CYAN + 'Done. Please reboot robots to apply changes.')

    print(Fore.RESET, end='')

#only import once everything is initialized (prevents error with circular import)
import netscanner
import argparse

parser = argparse.ArgumentParser(
            prog='Moorebot Setup',
            description='Sets up the Moorebot robots for lab')

parser.add_argument('-cn', '--config_network', help='Push network configuration to directly connected robot', action='store_true')

if __name__ == '__main__':
    args = parser.parse_args()
    main(args.config_network)

#reset text color no matter what
print(Fore.RESET)