from furhat_remote_api import FurhatRemoteAPI
import os
import re
from langchain_openai import ChatOpenAI
from characteristics import VOICES, FACES
import multiprocessing
from langchain_core.pydantic_v1 import BaseModel
import time

from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)



#from agents.agent import CustomBaseSingleActionAgent

from langchain import hub
import random
import requests

from colorama import Fore,Style

from callback_handler import CustomStreamingStdOutCallbackHandler

from configuration import VERBOSE, TIMEOUT, discussion_floor, discussion_ceil, use_bots
from configuration import IDLE_MIN, IDLE_MAX, LISTEN_MIN, LISTEN_MAX, LINE_WAIT, MODE
from configuration import language, furhat_hosts, furhat_listening_coordinates, furhat_listening_animations , furhat_idle_animations , endpoint 





def get_env_vars():
    f = open(".env", mode = "r")
    lines = f.readlines()
    for line in lines:
        info = line.split("=")
        name = info[0]
        value = info[1].strip("\"").strip()
        #print((name,value))
        os.environ[name] = value


class DialogueManager(BaseModel):
    agents: Dict = {}
    prnt : bool = False
    start: bool = False
    p_queue: object = None



    def get_personalities(self, topic, llm):
        input = f"""This is the topic I want to discuss: {topic}. Please chose two personalities 
with oposing views on the subject, from real history, who would enact the most entertaining
debate on this topic. 
As such they must share some contradictory views on the topic.
Please respond in the following format:
Final Answer: Personality_1(gender);Personality_2(gender)
EXAMPLE:
The topic is physics. Hence, I believe the two best personalities 
to cover this debate are two of the most influential physicists in history.
Final Answer: Isaac Newton(male); Albert Einstein(female)
END OF EXAMPLE"""
        
       
        res = llm.invoke(input).content


        regex = r"Final\s+Answer\s*:\s*(.*)\(\s*([Mm][Aa][Ll][Ee]|[Ff][Ee][Mm][Aa][Ll][Ee]|[Mm][Aa][Nn]|[Ww][Oo][Mm][Aa][Nn])\s*\);(.*)\(\s*([Mm][Aa][Ll][Ee]|[Ff][Ee][Mm][Aa][Ll][Ee]|[Mm][Aa][Nn]|[Ww][Oo][Mm][Aa][Nn])\s*\)"
        female_regex = ["female", "woman"]

        match = re.search(regex, res, flags=re.DOTALL)
        if match:
            individual_1 = match.group(1).strip()
            if match.group(2).strip() in female_regex:
                individual_1_gender = "female"
            else:
                individual_1_gender = "male"

            individual_2 = match.group(3).strip()
            if match.group(4).strip() in female_regex:
                individual_2_gender = "female"
            else:
                individual_2_gender = "male"

        else:
            individual_1 = "Expert 1"
            individual_1_gender = "female"
            individual_2 = "Expert 2"
            individual_2_gender = "male"



        #print(((individual_1, individual_1_gender),(individual_2 , individual_2_gender)))
        return ((individual_1, individual_1_gender),(individual_2 , individual_2_gender))

    def check_for_agent_dialogue(self, agents, res, start, agent):

        agent_names = [agent[0] for agent in agents.items()]
        regex = r"\s*("
        for i, name in enumerate(agent_names):
            if i != len(agent_names)-1:
                regex += f"{name}|"
            else :
                regex+= f"{name}"
                regex += r")\s*:"

        match = re.search(regex, res, flags=re.DOTALL)
        if match:
            res = ""
            start = True
            agent = match.group(1)
        
        else:
            regex2 = r".*\n"
            match2 = re.search(regex2, res, flags=re.DOTALL)

            if match2:
                res = ""
                start = False
                agent = ""
        

        return res, start, agent

    def get_dialogue(self, topic, llm, mode):
        

        if mode == "polite":
            prompt_variables = ["polite", "polite", "polite", "spirited", "spirited", "polite", "polite", "lighthearted" ]
        elif mode == "rude":
            prompt_variables = ["rude", "sarcastic", "sarcastic", "heated", "heated", "rude", "rude", "confrontational" ]

        agent_list = list(self.agents.items())
        #print(agent_list[0])
        agent_1 = agent_list[0][0]
        agent_2 = agent_list[1][0]
        input = f"""A debate for the ages. On "{topic}", two heavy hiters will debate: {agent_1} and {agent_2}.
    Write a {prompt_variables[0]} discussion between these two personalities, as if they were having it right now. 
    They must be consistent with their real beliefs, and defend oposing views.
    They must confront each other's ideas. Do not paraphrase or address 
    the participants by their names, use pronouns instead.
    You must provide this debate in the following format:
    {agent_1} : {prompt_variables[1]} greeting(a polite introduction).
    {agent_2} : {prompt_variables[2]} greeting(a polite introduction).
    from {discussion_floor} to {discussion_ceil} times:
        {agent_1} : {prompt_variables[3]} argument(at most 20 words).
        {agent_2} : {prompt_variables[4]} argument(at most 20 words).
    {agent_1} : {prompt_variables[5]} greeting(a goodbye).
    {agent_2} : {prompt_variables[6]} greeting(a goodbye).
    The arguments must flow coherently from one to the next. 
    The debate must be informative, and interesting. 
    """
        if language.lower()=="dutch":
            input+= f"Please write this debate in dutch language, in a {prompt_variables[7]} style.\n"

        
        chunks = []
        res = ""
        agent_name = ""
        printable = ("", "")
        ag = None
        for chunk in llm.stream(input):
            chunks.append(chunk.content)
            res+= chunk.content
            res, self.start, agent_name = self.check_for_agent_dialogue(self.agents, res, self.start, agent_name)
            res.strip(f"{agent_name}")
            res.strip(":")
            #the dialogue line for a given agent has started - shall we stream the chunks?
            if self.prnt==False and self.start == True:
                self.prnt=self.start
                printable = (agent_name, res)
                if agent_name != "":
                    ag = self.agents[agent_name]
            #the dialogue line for a given agent is in progress - shall we stream the chunks?
            elif self.prnt==True and self.start == True:
                if agent_name != "":
                    ag = self.agents[agent_name]
                    
                printable = (agent_name, res)
            
            #the dialogue line for a given agent has ended
            elif self.prnt==True and self.start == False:
                if ag:
                    if ag["furhat"] != None:
                        s = printable[1] + chunk.content
                    else:
                        s = printable[0] + " : "  + printable[1] + chunk.content
                    self.prnt= self.start
                    self.p_queue.put([printable[0], s])
                ag = None
                printable = (agent_name,res)
                          
        self.p_queue.put(["", None])
        return True
    
    def get_agent(self, index, personality):
        furhat  = None
        voice_name = ""
        face_name = ""
        listenning_coors = ""
        direction = ""
        color = ""
        try:
            host = furhat_hosts[index]
            listenning_coors = furhat_listening_coordinates[index]
            furhat = FurhatRemoteAPI(host)
            gender = personality[1]
            voice_name = random.choice(VOICES[language][gender])["name"]
            face_name = random.choice(FACES[gender])
            if index==0:
                direction = "left"
                color=[0,250,70]
            else:
                direction = "right"
                color = [0,70,250]
        except ValueError:
            furhat = None
            voice_name = ""
            return None
        except IndexError:
            furhat = None
            voice_name = ""
            return None
        except KeyError:
            furhat = None
            voice_name = ""
            return None
        return {personality[0] : {"gender": personality[1], "furhat": furhat, "voice": voice_name, "face": face_name, "list_coords": listenning_coors, "direction": direction, "color": color}}


def get_opposing_agent_name(agent_name,agents):
    for i,(k,v) in enumerate(agents.items()):
        if k != agent_name:
            return k
        
def send_message_to_screen_http_req(topic, line, ag_name, direction):

    """{"text": "hello", "name":"Bob", "type":"left", "metadata":"Dogs"}"""
    data = {
        'text': line,
        'name': ag_name,
        'type': direction,
        'metadata': topic
        }
    
    # sending post request and saving response as response object
    r = requests.post(url=endpoint, data=data)
    code = r.status_code
    print(f"Status:{code}")

                    
        


def clear_screen_http_req():

    """{"text": "hello", "name":"Bob", "type":"left", "metadata":"Dogs"}"""
    
    # sending post request and saving response as response object
    r = requests.delete(url=endpoint, headers={})
    code = r.status_code
    print(f"Status:{code}")
    print(f"text :{r.text}")

def led_flicker(furhat, color):
    furhat.set_led(red=color[0], green=color[1], blue=color[2])
    time.sleep(0.2)
    furhat.set_led(red=int(color[0]/2.0), green=int(color[1]/2.0), blue=int(color[2]/2.0))
    time.sleep(0.2)
    furhat.set_led(red=color[0], green=color[1], blue=color[2])


def speak(llm, p_queue, agents, topic):

    line = "something"
    if requests:
        try:
            clear_screen_http_req()
        except Exception:
            print("NO HTTP SERVER")
    start_conversation_flag = True

    while line != None:
        dialogue = p_queue.get()

        if dialogue is not None:
            
            ag_name, line = dialogue[0],dialogue[1]
            ag_opposing_name = get_opposing_agent_name(ag_name,agents)
            ag = agents.get(ag_name)
            opposing_ag = agents.get(ag_opposing_name)
            if use_bots:
                if ag and opposing_ag:
                    


                    furhat = ag.get("furhat")
                    opposing_furhat = opposing_ag.get("furhat")

        
                    if furhat and opposing_furhat:

                        if start_conversation_flag:
                            furhat.set_voice(name=ag["voice"])
                            furhat.set_face(character=ag["face"], mask="adult")
                            opposing_furhat.set_face(character=opposing_ag["face"], mask="adult")
                            opposing_furhat.set_voice(name= opposing_ag["voice"])
                            start_conversation_flag = False

                        opposing_furhat.set_led(red=0, green=0, blue=0)
                        opposing_furhat.attend(location=opposing_ag["list_coords"])



                        time.sleep(LINE_WAIT)
                        led_flicker(furhat, ag["color"])
                        
                        furhat.attend(location=ag["list_coords"])

                        procs = []

                        #params: furhat,personality, llm, opponent, line

                        p = multiprocessing.Process(target=listening, args=(opposing_furhat, ag_name, llm, ag_opposing_name, line))
                        procs.append(p)
                        p.start()

                        direction = ag.get("direction")
                        if requests:
                            try:
                                send_message_to_screen_http_req(topic, line, ag_name, direction)
                            except Exception:
                                print("NO HTTP SERVER")
                        print(Fore.BLUE + ag_name + " : " + line, end="", flush=True)
                        print(Style.RESET_ALL)
                        furhat.say(text=line, blocking=True)

                        terminate_procs(procs)
            elif line is not None:
                time.sleep(2)
                print(Fore.BLUE + ag_name + " : " + line, end="", flush=True)
                print(Style.RESET_ALL)

def play_idle_animations(furhat):


    time.sleep(random.randint(IDLE_MIN,IDLE_MAX))
    
    choice = random.randint(0,1)

    if choice == 1:
        furhat.attend(user="CLOSEST")
    else:
        furhat.gesture(name=random.choice(furhat_idle_animations))



def play_listening_animations(evaluation, furhat):
    time.sleep(random.randint(LISTEN_MIN,LISTEN_MAX))

    furhat.gesture(name=random.choice(furhat_listening_animations.get(evaluation)))


        

def idle():
    try:
        furhats = [FurhatRemoteAPI(host) for host in furhat_hosts] 
    except Exception:
        return

    while True:
        for furhat in furhats:
            play_idle_animations(furhat)




def evaluate_line(llm, personality, opponent, line):
    
    #  "BrowRaise", "BrowFrown", "Nod", "OpenEyes", "Shake", "Roll", "Thoughtful", "GazeAway"

    #group by emotion type: brow_frown, shake, gaze_away - disagree
    # brow_raise, roll, thoughtfull - considering
    # Nod, Open eyes - agree


    input = f"""As {personality}, do you agree, disagree, or want to further consider the idea put forth by {opponent}, when they told you:
    {line}?
    Respond in the following format:
    Final Answer: Agree/Disagree/Consider
    """
        
       
    res = llm.invoke(input).content
    #print("RESULT = " + str(res))

    regex = r"Final\s+Answer\s*:\s*([Aa][Gg][Rr][Ee][Ee]|[Dd][Ii][Ss][Aa][Gg][Rr][Ee][Ee]|[Cc][Oo][Nn][Ss][Ii][Dd][Ee][Rr]).*"

    match = re.search(regex, res, flags=re.DOTALL)
    if match:
        return match.group(1).strip().lower()
    else:
        return "consider"







def listening(furhat,personality, llm, opponent, line):
    

    evaluation = evaluate_line(llm, personality, opponent, line)
    while True:
        play_listening_animations(evaluation, furhat)

    



def join_procs(processes):
    procs_to_terminate = []

    for p in processes:
        
        ind = processes.index(p)
        procs_to_terminate.append(p)
                    
            
    for p in procs_to_terminate:
        processes.pop(processes.index(p))
        p.join()




def terminate_procs(processes):
    procs_to_terminate = []

    for p in processes:
        
        ind = processes.index(p)
        procs_to_terminate.append(p)
                    
            
    for p in procs_to_terminate:
        processes.pop(processes.index(p))
        p.terminate()


if __name__=="__main__":
    
    get_env_vars()
    #gpt-3.5-turbo
    LLM_DIALOGUE = ChatOpenAI(temperature=0.9, max_tokens=2000, verbose = VERBOSE, model_name='gpt-3.5-turbo', request_timeout = TIMEOUT, streaming=True,  # ! important
        callbacks=[CustomStreamingStdOutCallbackHandler()] )# Can be any LLM you want.
    
    LLM = ChatOpenAI(temperature=0.9, max_tokens=2000, verbose = VERBOSE, model_name='gpt-3.5-turbo', request_timeout = TIMEOUT)# Can be any LLM you want.
    

    topic = ""
    while topic.lower() != "exit":
        dm = DialogueManager()
        p_queue = multiprocessing.Queue()
        dm.p_queue = p_queue
        processes = []


        p = multiprocessing.Process(target=idle, args=())
        processes.append(p)
        p.start()

        topic = input("Choose a topic for this conversation: ")
        terminate_procs(processes)
        if topic.lower() == "exit":
            p_queue.close()
            break
        personalities = dm.get_personalities(topic, LLM )
        print(personalities)

        for i, personality in enumerate(personalities):
            dm.agents.update(dm.get_agent(i, personality))
        
        print(dm.agents)
        
        p = multiprocessing.Process(target=speak, args=(LLM_DIALOGUE, p_queue, dm.agents,topic, ))
        processes.append(p)
        p.start()
        dialogue = dm.get_dialogue(topic, LLM_DIALOGUE, MODE)
        join_procs(processes)
        p_queue.close()
        if requests:
            try:
                clear_screen_http_req()
            except Exception:
                print("NO HTTP SERVER")
        dm.agents = {}
        





