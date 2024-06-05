VERBOSE = False
TIMEOUT = 10
discussion_floor = 10
discussion_ceil = 20
IDLE_MIN = 1
IDLE_MAX = 3
LISTEN_MIN = 1
LISTEN_MAX = 3
LINE_WAIT = 0.2

language = "english"
MODE = "rude"

# 172.22.160.1
#192.168.0.118

furhat_hosts = ["192.168.0.164", "192.168.0.118"]
furhat_listening_coordinates = [ "0.1,0.0,0.3", "-0.1, 0.0, 0.3"]

#group by emotion type: brow_frown, shake, gaze_away - disagree
    # brow_raise, roll, thoughtfull - considering
    # Nod, Open eyes - agree

furhat_listening_animations = {"agree": [ "Nod", "OpenEyes"], "disagree": [ "BrowFrown", "Shake", "GazeAway"] , "consider": ["BrowRaise", "Roll", "Thoughtful"]}

furhat_idle_animations = [  "Nod" , "Roll", "Thoughtful"]

endpoint = "https://echoweb.hri.ilabt.imec.be/api/fti"

requests=True
use_bots = True




