import os
import vlc
import time
import sys
import tkinter as tk
import threading as td
import json
import tracemalloc
from pympler.tracker import SummaryTracker
from PIL import ImageTk, Image
from screeninfo import get_monitors

if os.environ.get('DISPLAY','') == '':
    print('no display found. Using :0.0')
    os.environ.__setitem__('DISPLAY', ':0.0')

_isLinux   = sys.platform.startswith('linux')
_isWindows = sys.platform.startswith('win')

if _isLinux:
    print("Linux system")
elif _isWindows:
    print("Windows system")
    
""" script_dir = os.path.dirname(__file__)

rel_path = "vlcSchedule.pid"
abs_file_path = os.path.join(script_dir, rel_path)

output_pid = open(abs_file_path, "w")
pid = str(os.getpid())
output_pid.write(pid)
output_pid.close() """

wday = {
    'Monday':0,
    'Tuesday':1,
    'Wednesday':2,
    'Thursday':3,
    'Friday':4,
    'Saturday':5,
    'Sunday':6
}

scheduleCount,scheduleDict = 1,{}
directory = "downloads/schedules"
scheduleName = " ".join(sys.argv[1:]) if len(sys.argv) > 2 else sys.argv[1]

#scheduleName = 'useThis'
configFile = open(f'{directory}/{scheduleName}/{scheduleName}_schedule.json')
scheduleConfig = json.load(configFile)
tracemalloc.start()
scheduleArray = []

# init 3d array of 0
for i in range(7):
    scheduleArray.append([])
    for j in range(24):
        scheduleArray[i].append([])
        for k in range(60):
            scheduleArray[i][j].append(0)

# set timings to number, then map to 3d array of schedule
for timing in scheduleConfig['schedule']:
    for dayStr in timing['days']:
        day = wday[dayStr]
        scheduleDict[scheduleCount] = timing['playlists']
        startTime, endTime = timing['startTime'].split(':'),timing['endTime'].split(':')
        if int(startTime[0]) != int(endTime[0]):
            for minutes in range (int(startTime[1]),60):
                scheduleArray[day][int(startTime[0])][minutes] = scheduleCount
                
            for minutes in range (0,int(endTime[1]) + 1):
                scheduleArray[day][int(endTime[0])][minutes] = scheduleCount
        else:
            for minutes in range (int(startTime[1]),int(endTime[1]) + 1):
                scheduleArray[day][int(startTime[0])][minutes] = scheduleCount
                
        for hours in range(int(startTime[0]) + 1, int(endTime[0])):
            for minutes in range(0,60):
                scheduleArray[day][hours][minutes] = scheduleCount
    scheduleCount += 1
                
currentTime = time.localtime(time.time())
currentTiming = scheduleArray[currentTime.tm_wday][currentTime.tm_hour][currentTime.tm_min]
root = tk.Tk()
root.overrideredirect(True) # remove borders
#print(f"{root.winfo_screenwidth()},{root.winfo_screenheight()}")

x,y= 0,0
monitors = sorted(get_monitors(), key=lambda m:m.x)
for monitor in monitors:
    x += monitor.width
    y = max(monitor.height, y)
    print(str(monitor))
print(f"{x},{y}")
root.geometry(f"{x}x{y}+0+0")
root.configure(background='black')

switchEvent = td.Event()
tracker = SummaryTracker()

def startTiming():
    monitor = monitors[0]

    if currentTiming != 0:
        playlists = scheduleDict[currentTiming]
        
        for index in range(len(playlists)):
            playlistName = playlists[index]
            playlistFile = open(f"{directory}/{scheduleConfig['scheduleName']}/{playlistName}/{playlistName}_config.json")
            playlistConfig = json.load(playlistFile)

            if playlistConfig['aspectRatio'][1] == '8':
                width = monitor.width
                height = monitor.height//2

                columnFrame = tk.Frame(root, width=monitor.width, height=monitor.height)
                columnFrame.configure(background='black')
                columnFrame.grid(row=0, column=index)
                for row in range(len(playlistConfig['playlists'])):
                    root.after(100,initPlaylist,playlistConfig['playlists'][row],playlistName,row,columnFrame,width,height)
            else:
                width = monitor.height * int(playlistConfig['aspectRatio'][0]) // int(playlistConfig['aspectRatio'][1])
                height = monitor.height

                columnFrame = tk.Frame(root, width=width, height=height)
                columnFrame.configure(background='black')
                columnFrame.grid(row=0, column=index)

                root.after(100,initPlaylist,playlistConfig['playlists'][0],playlistName,0,columnFrame,width,height)
                
    root.after(100,waitSwitch)
        
def timingChecker():
    global currentTiming
    while True:
        currentTime = time.localtime(time.time())
        if (currentTiming != scheduleArray[currentTime.tm_wday][currentTime.tm_hour][currentTime.tm_min]):
            switchEvent.set()
            currentTiming = scheduleArray[currentTime.tm_wday][currentTime.tm_hour][currentTime.tm_min]
        time.sleep(1)

def memoryProfiler():
    while True:
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        print("[ Top 10 ]")
        for stat in top_stats[:10]:
            print(stat)
        tracker.print_diff()
        print(time.asctime(time.localtime(time.time())))
        time.sleep(180)

def initPlaylist(playlist,playlistName,row,columnFrame,width,height):

    # for if screensize is dynamic
    """ if y - height > 0:
        bufferHeight = y - height """
    
    # init mediaFrames

    imageFrames = []
    for media in playlist:
        extension = media[0].split('.')[1]
        if extension == 'jpeg' or extension == 'png' or extension == 'jpg':
            tempFrame = tk.Frame(columnFrame, width=width, height=height)
            tempFrame.grid(row=row)
            image = Image.open(f"{directory}/{scheduleConfig['scheduleName']}/{playlistName}/" + media[0])
            display = ImageTk.PhotoImage(image.resize((width,height)))
            label = tk.Label(tempFrame,image=display,borderwidth=0,highlightthickness=0)
            label.image = display
            label.grid(row=0)
            tempFrame.grid_remove()
            imageFrames.append(tempFrame)
        else:
            imageFrames.append(0)
    
    # for if screensize is dynamic
    """ paddingFrame = None
    if (monitor.height != y):
        paddingFrame = tk.Frame(columnFrame, width=width, height=bufferHeight)
        paddingFrame.configure(background='black')
        paddingFrame.grid(row=1) """
    
    root.after(0,playMedia,playlist,playlistName,columnFrame,imageFrames,0,None,width,height)
    root.after(0,waitDestroy,columnFrame,imageFrames)

def waitSwitch():
    thread = td.Thread(target=waitSwitchThread)
    thread.start()

def waitSwitchThread():
    switch_isSet = switchEvent.wait()
    time.sleep(3)
    switchEvent.clear()
    root.after(0,startTiming)
    
def waitDestroy(columnFrame,imageFrames):
    thread = td.Thread(target=waitDestroyThread,args=(columnFrame,imageFrames))
    thread.start()
    
def waitDestroyThread(columnFrame,imageFrames):
    switch_isSet = switchEvent.wait()
    time.sleep(1)
    if imageFrames != None:
        for frames in imageFrames:
            if frames != 0:
                frames.destroy()
        if columnFrame != None:
            columnFrame.destroy()

def waitVideoThread(playlist,playlistName,columnFrame,imageFrames,instance,player,mediaIndex,previousFrame,width,height):
    time.sleep(0.5)
    while player.is_playing() and not switchEvent.is_set():
        time.sleep(0.1)
    
    if player.is_playing():
        player.stop()
    player.get_media().release()
    player.release()
    instance.release()
    previousFrame.destroy()
    if not switchEvent.is_set():
        root.after(0,playMedia,playlist,playlistName,columnFrame,imageFrames,mediaIndex,None,width,height)

def waitVideo(playlist,playlistName,columnFrame,imageFrames,instance,player,mediaIndex,previousFrame,width,height):
    thread = td.Thread(target=waitVideoThread,args=(playlist,playlistName,columnFrame,imageFrames,instance,player,mediaIndex,previousFrame,width,height))
    thread.start()

def waitImageThread(playlist,playlistName,columnFrame,imageFrames,mediaIndex,previousFrame,width,height,delay):
    switch_isSet = switchEvent.wait(int(delay))
    if not switch_isSet:
        root.after(0,playMedia,playlist,playlistName,columnFrame,imageFrames,mediaIndex,previousFrame,width,height)
    
def waitImage(playlist,playlistName,columnFrame,imageFrames,mediaIndex,previousFrame,width,height,delay):
    thread = td.Thread(target=waitImageThread,args=(playlist,playlistName,columnFrame,imageFrames,mediaIndex,previousFrame,width,height,delay))
    thread.start()

def playMedia(playlist,playlistName,columnFrame,imageFrames,mediaIndex,previousFrame,width,height):
    if mediaIndex == len(playlist):
        mediaIndex = 0

    media = playlist[mediaIndex]
    extension = media[0].split('.')[1]

    if previousFrame != None:
        previousFrame.grid_forget()

    if extension == 'jpeg' or extension == 'jpg' or extension == 'png':
        print('jpeg')
        imageFrame = imageFrames[mediaIndex]
        imageFrame.grid()
        root.after(0,waitImage,playlist,playlistName,columnFrame,imageFrames,mediaIndex+1,imageFrame,width,height,media[1])
    elif extension == 'mp4' or extension == 'mov':
        print('mp4')
        mediaFrame = tk.Frame(columnFrame, width=width, height=height)
        mediaFrame.configure(background='black')
        mediaFrame.grid(row=0)
        mediaFrame.grid_remove()
        if _isLinux:
            instance = vlc.Instance('--no-xlib --aout=adummy')
        else:
            instance = vlc.Instance('--aout=adummy')

        player = instance.media_player_new()
        vlcMedia = instance.media_new(f"{directory}/{scheduleConfig['scheduleName']}/{playlistName}/" + media[0])
        player.set_media(vlcMedia)
        window = mediaFrame.winfo_id()
        if _isLinux:
            player.set_xwindow(window)
        elif _isWindows:
            player.set_hwnd(window)
        player.video_set_aspect_ratio(f"{width}:{height}")

        root.after(0,player.play)
        root.after(300,mediaFrame.grid)
        root.after(500,waitVideo,playlist,playlistName,columnFrame,imageFrames,instance,player,mediaIndex+1,mediaFrame,width,height)

td.Thread(target=timingChecker).start()
#td.Thread(target=memoryProfiler).start()
root.after(0,startTiming)
root.mainloop()