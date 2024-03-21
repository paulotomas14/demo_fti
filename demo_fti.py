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

from configuration import VERBOSE, TIMEOUT, discussion_floor, discussion_ceil
from configuration import IDLE_MIN, IDLE_MAX, LISTEN_MIN, LISTEN_MAX, LINE_WAIT
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
        input = f"""This is the topic I want to discuss: {topic}. Please chose two personalities,
    from real history, who would enact the most entertaining debate on this topic. 
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








    def get_dialogue(self, topic, llm):
    
        agent_list = list(self.agents.items())
        #print(agent_list[0])
        agent_1 = agent_list[0][0]
        agent_2 = agent_list[1][0]
        input = f"""A debate for the ages. On "{topic}", two heavy hiters will debate: {agent_1} and {agent_2}.
    Write a fun discussion between these two personalities, as if they were having it right now. They must be consistent with their real beliefs,
    and address each other to confront their ideas.
    You must provide this debate in the following format:
    {agent_1} : argument(at most 30 words).
    {agent_2} : argument(at most 30 words).
    (...)
    This debate must be around {discussion_floor} to {discussion_ceil} lines long,
    and the arguments must flow coherently from one to the next. 
    Terminate the debate politely.
    Do not forget polite introductions and goodbyes.
    The debate must be informative, and interesting. 
    """
        if language.lower()=="dutch":
            input+= "Please write this debate in dutch language, in a lighthearted style.\n"

        '''
        Write it in the style of Aaron Sorkin.
        If repetition might be an issue, veer the debate into recent issues an thematics,
        To keep the conversation flow.
        Terminate the debate only once both parties have agreed, or agreed to disagree, 
        '''
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

        try:
            host = furhat_hosts[index]
            listenning_coors = furhat_listening_coordinates[index]
            furhat = FurhatRemoteAPI(host)
            gender = personality[1]
            voice_name = random.choice(VOICES[language][gender])["name"]
            face_name = random.choice(FACES[gender])
            if index==0:
                direction = "left"
            else:
                direction = "right"
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
        return {personality[0] : {"gender": personality[1], "furhat": furhat, "voice": voice_name, "face": face_name, "list_coords": listenning_coors, "direction": direction}}


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
    print(f"endpoint = {endpoint}")
    r = requests.delete(url=endpoint, headers={})
    code = r.status_code
    print(f"Status:{code}")
    print(f"text :{r.text}")

def led_flicker(furhat):
    furhat.set_led(red=250, green=250, blue=250)
    time.sleep(0.2)
    furhat.set_led(red=100, green=100, blue=100)
    time.sleep(0.2)
    furhat.set_led(red=250, green=250, blue=250)


def speak(p_queue, agents, topic):
    line = "something"
    clear_screen_http_req()
    while line != None:

        dialogue = p_queue.get()

        if dialogue is not None:
            
            ag_name, line = dialogue[0],dialogue[1]
            ag_opposing_name = get_opposing_agent_name(ag_name,agents)
            ag = agents.get(ag_name)
            opposing_ag = agents.get(ag_opposing_name)
            if ag and opposing_ag:
                furhat = ag.get("furhat")
                opposing_furhat = opposing_ag.get("furhat")
                if furhat and opposing_furhat:
                    
                    opposing_furhat.set_voice(name= opposing_ag["voice"])
                    opposing_furhat.set_face(character= opposing_ag["face"],  mask="adult")
                    opposing_furhat.set_led(red=0, green=0, blue=0)
                    opposing_furhat.attend(location=opposing_ag["list_coords"])


                    #print(ag["voice"])

                    time.sleep(LINE_WAIT)
                    led_flicker(furhat)
                    furhat.set_voice(name=ag["voice"])
                    furhat.set_face(character=ag["face"], mask="adult")
                    #fade_leds(MIN, MAX, TIME)

                    furhat.attend(location=ag["list_coords"])




                    

                    procs = []

                    p = multiprocessing.Process(target=listening, args=(opposing_furhat,))
                    procs.append(p)
                    p.start()

                    direction = ag.get("direction")
                    send_message_to_screen_http_req(topic, line, ag_name, direction)
                    print(Fore.BLUE + ag_name + " : " + line, end="", flush=True)
                    print(Style.RESET_ALL)
                    
                    furhat.say(text=line, blocking=True)

                    terminate_procs(procs)
                

def play_idle_animations(furhat):
    time.sleep(random.randint(IDLE_MIN,IDLE_MAX))
    

    choice = random.randint(0,1)

    if choice == 1:
        furhat.attend(user="CLOSEST")
    else:
        furhat.gesture(name=random.choice(furhat_idle_animations))

def play_listening_animations(furhat):
    time.sleep(random.randint(LISTEN_MIN,LISTEN_MAX))

    furhat.gesture(name=random.choice(furhat_listening_animations))


        

def idle():
    furhats = [FurhatRemoteAPI(host) for host in furhat_hosts] 

    while True:
        for furhat in furhats:
            play_idle_animations(furhat)


def listening(furhat):
    
    
    while True:
        play_listening_animations(furhat)

    



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
    
    LLM = ChatOpenAI(temperature=0.9, max_tokens=4096, verbose = VERBOSE, model_name='gpt-3.5-turbo', request_timeout = TIMEOUT)# Can be any LLM you want.
    dm = DialogueManager()
    p_queue = multiprocessing.Queue()
    dm.p_queue = p_queue

    topic = ""
    while topic.lower() != "exit":

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
        

        
        
        p = multiprocessing.Process(target=speak, args=(p_queue, dm.agents,topic))
        processes.append(p)
        p.start()

        dialogue = dm.get_dialogue(topic, LLM_DIALOGUE)
        
        join_procs(processes)


    p_queue.close()
        





