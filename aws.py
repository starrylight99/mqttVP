from tkinter import Event
import boto3
import json
import os
import paho.mqtt.client as mqtt
from pympler.tracker import SummaryTracker
import threading
import shutil
import subprocess
import sys
import signal
import time
import tracemalloc

_isLinux   = sys.platform.startswith('linux')
_isWindows = sys.platform.startswith('win')
script_dir = os.path.dirname(__file__)

tracker = SummaryTracker()
tracemalloc.start()
scheduleEvent = threading.Event()
isPlaying = threading.Event()

if _isWindows:
    p = None
    
with open('config.json', 'r') as f:
    data = json.load(f)

s3 = boto3.resource(
    's3',
    aws_access_key_id = data["accessKeyId"], 
    aws_secret_access_key = data["secretAccessKey"], 
    region_name = data["region"]
)
s3_client = boto3.client(
    's3',
    aws_access_key_id = data["accessKeyId"], 
    aws_secret_access_key = data["secretAccessKey"], 
    region_name = data["region"]
)

def memoryProfiler():
    while True:
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        print("[ Top 10 ]")
        for stat in top_stats[:10]:
            print(stat)
        tracker.print_diff()
        print(time.asctime(time.localtime(time.time())))
        time.sleep(1800)

def deleteSchedule(schedule, client):
    path = 'downloads/schedules/' + schedule
    shutil.rmtree(path, ignore_errors=True)
    client.publish('webApp', 'deleted ' + data['id'])

def ping_listdir(client):
    path = 'downloads/schedules/'
    if os.path.exists(path):
        schedules = os.listdir(path)
        if len(schedules) != 0:
            res = 'online ' + data['id']
            for i in schedules:
                statusFile = open(path + i + '/status.txt','r')
                status = statusFile.readline()
                if status == 'true':
                    client.publish('webApp', f"{res} {i}")
            return
    client.publish('webApp', 'online ' + data['id'] + ' nil')
    sys.exit()
        

def downloadSchedule(group, schedule, client):
    os.makedirs('downloads/schedules/' + schedule, exist_ok=True)
    statusFile = open('downloads/schedules/' + schedule + '/status.txt', 'w')
    statusFile.write('false')
    statusFile.close()

    sched_path = 'downloads/schedules/' + schedule + '/' + schedule + '_schedule.json'
    s3.Bucket('maventest1').download_file(group + '/schedules/' + schedule + '/' + schedule + '_schedule.json', sched_path)
    with open(sched_path, 'r') as f:
        schedule_config = json.load(f)
    for playlist in schedule_config['uniquePlaylist']:
        response = s3_client.list_objects_v2(
            Bucket='maventest1',
            Delimiter='/',
            Prefix= group + '/schedules/' + schedule + '/' + playlist + '/'  
        )
        playlist_path = 'downloads/schedules/' + schedule + '/' + playlist
        os.makedirs(playlist_path, exist_ok=True)
        for key in response["Contents"]:
            s3.Bucket('maventest1').download_file(key["Key"], f"{playlist_path}/{key['Key'].split('/')[-1]}")
    client.publish('webApp', 'Finished Downloading')

    statusFile = open('downloads/schedules/' + schedule + '/status.txt', 'w')
    statusFile.write('true')
    statusFile.close()
    sys.exit()

def startSchedule(scheduleName):
    while not scheduleEvent.is_set():
        rel_path = "startSchedule.pid"
        abs_file_path = os.path.join(script_dir, rel_path)

        if _isLinux:
            p = subprocess.Popen(f'python3 vlcSchedule.py {scheduleName}', shell=True, preexec_fn=os.setsid)
        elif _isWindows:
            p = subprocess.Popen(f'python vlcSchedule.py {scheduleName}')

        output_pid = open(abs_file_path, "w")
        if _isLinux:
            output_pid.write(str(os.getpgid(p.pid)))
        elif _isWindows:
            output_pid.write(str(p.pid))
        output_pid.close()
        p.wait()
    scheduleEvent.clear()
    sys.exit()

        #if p.poll() is not None:
        #    os.kill(p.pid, signal.SIGTERM)

def on_disconnect(client, userdata, rc=0):
    print("Disconnected result code " + str(rc))

def on_connect(client, userdata, flags, rc):
    print("Connected flags" + str(flags) + "result code " + str(rc))

def on_publish(client, userdata, mid):
    print("message published " + str(mid))

def on_log(client, userdata, level, buf):
    print("log: ",buf)

def on_subscribe(client, userdata, mid, granted_qos):
    print('subscribed schedule')

def on_message(client, userdata, message):
    msg = message.payload.decode()
    split_msg = msg.split(' ')
    print(split_msg)
    if split_msg[0] == "ping":
        pingThread = threading.Thread(target=ping_listdir, args=(client,))
        pingThread.start()
    elif split_msg[1] == data['id']:
        if split_msg[0] == 'schedule':
            if len(split_msg) > 3:
                msg = " ".join(split_msg[2:])
                downloadThread = threading.Thread(target=downloadSchedule, args=(data['group'], msg, client))
            else:
                downloadThread = threading.Thread(target=downloadSchedule, args=(data['group'], split_msg[2], client))
            downloadThread.start()
        elif split_msg[0] == 'delete':
            schedule = " ".join(split_msg[2:])
            deleteThread = threading.Thread(target=deleteSchedule, args=(schedule, client))
            deleteThread.start()
        elif split_msg[0] == 'run':
            if not isPlaying.is_set():
                schedule = " ".join(split_msg[2:]) if len(split_msg) > 2 else split_msg[2]
                client.publish('webApp', f'running {schedule}' )
                isPlaying.set()
                scheduleThread = threading.Thread(target=startSchedule, args=(schedule,))
                scheduleThread.start()
            else:
                client.publish('webApp', 'already running, cant run')
        elif split_msg[0] == 'stop':
            if isPlaying.is_set():
                client.publish('webApp', 'stopped')
                isPlaying.clear()
                scheduleEvent.set()
                pidF = open("startSchedule.pid", "r+")
                pid = int(pidF.readline())
                if _isLinux:
                    os.killpg(pid, signal.SIGTERM)
                else:
                    os.kill(pid, signal.SIGTERM)
                pidF.truncate(0)
                pidF.close()
            else:
                client.publish('webApp', 'not running, cant stop')


broker_address = '18.141.182.21'
threading.Thread(target=memoryProfiler).start()
client = mqtt.Client()
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_publish = on_publish
client.on_log = on_log
client.on_subscribe = on_subscribe
client.on_message = on_message
client.username_pw_set(username="maventest",password="12345")
client.tls_set('ca1.crt')
client.tls_insecure_set(True)
client.connect(broker_address, 8883)
client.subscribe('schedule')
client.subscribe('ping')
client.loop_forever()