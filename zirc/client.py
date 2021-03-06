from .connection import Socket
from .event import Event
from .flood import floodProtect
from .loop import EventLoop
from .errors import *
from . import util
from .wrappers import connection_wrapper

from base64 import b64encode
import sys,time

class Client(object):
    listeners = []
    def connect(self, config_class = None):

        self.fp = floodProtect()
        if not hasattr(self, "connection"):
            raise NoSocket("{0} has no attribute 'connection'".format(self))
        if config_class is None:
            raise NoConfig("config_class not a argument when calling connect")
            
        self._config = config_class
        self.socket = self.connection((self._config["host"], self._config["port"]))

        self._config["caps"](self)
        
        self.send("NICK {0}".format(self._config["nickname"]))
        self.send("USER {0} * * :{1}".format(self._config["ident"], self._config["realname"]))
        
        self._channels = self._config["channels"]
        self.loop = EventLoop(self.recv)
    def recv(self):
        self.buffer= ""
        while not self.buffer.endswith("\r\n"):
            self.buffer += self.socket.recv(2048).decode("utf-8", errors="replace")
        self.buffer = self.buffer.strip().split("\r\n")
        return self.buffer
    def send(self, data):
        if hasattr(self, "on_send"):
            self.on_send(data)
        self.fp.queue_add(self.socket, "{0}\r\n".format(data).encode("UTF-8"))
    def start(self):
        self.loop.create_job("main", self.main_job)
        self.loop.run()
    def main_job(self, event):
        """loop job to provide a event based system for clients."""
        args = {"event": event, "bot": self, "irc": connection_wrapper(self), "args": " ".join(event.arguments).split(" ")[1:]}
        
        #add arguments from event, for easier access
        args.update({k: getattr(event, k) for k in dir(event) if not k.startswith("__") and not k.endswith("__")})
    
        if event.type == "001":
            for channel in self._channels:
                self.send("JOIN {0}".format(channel))

        to_call = []
        
        if hasattr(self, "on_all"):
            to_call.append(self.on_all)
        
        if hasattr(self, "on_"+event.type.lower()):
            to_call.append(getattr(self, "on_"+event.type.lower()))
        
        if event.type != event.text_type:
            if hasattr(self, "on_"+event.text_type.lower()):
                to_call.append(getattr(self, "on_"+event.text_type.lower()))

        for event_name, func in self.listeners:
            if event_name == event.text_type.lower() or event_name == event.type.lower():
                to_call.append(func)
        #Call the functions here
        for call_func in to_call:
            util.function_argument_call(call_func, args)()
    
        if event.type == "PING":
            self.send("PONG :{0}".format(" ".join(event.arguments)))
    
        #CTCP Replies
        if event.type == "PRIVMSG" and " ".join(event.arguments).startswith("\x01") and hasattr(self, "ctcp"):
            ctcp_message = " ".join(event.arguments).replace("\x01", "").upper()
            if ctcp_message in self.ctcp.keys():
                if callable(self.ctcp[ctcp_message]):
                    result = self.ctcp[ctcp_message]()
                else:
                    result = self.ctcp[ctcp_message]
                self.send("NOTICE {0} :{1} {2}".format(event.source.nick, ctcp_message, result))
    #Basic client use
    def privmsg(self, channel, message):
        MSGLEN = 400 - len("PRIVMSG {} :\r\n".format(channel).encode())
        strings = [message[i:i+MSGLEN] for i in range(0, len(message), MSGLEN)]
        for message in strings:
            self.send("PRIVMSG {0} :{1}".format(channel, message))
    def reply(self, event, message):
        self.privmsg(event.target, message)
    def listen(self, func, event_name):
        self.listeners.append((event_name.lower(), func))