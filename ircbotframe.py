import socket
import threading
import sys
import re
import time

class ircOutputBuffer:
    def __init__(self, irc):
        self.waiting = False
        self.irc = irc
        self.queue = []
    def sendIRCLine(self, string):
        print("Sending \"" + string + "\"")
        self.irc.send(bytes(string) + b"\r\n" )
    def startPopTimer(self):
        self.timer = threading.Timer(1, self.pop)
        self.timer.start()
    def push(self, string):
        if self.waiting:
            self.queue.append(string)
        else:
            self.waiting = True
            self.sendIRCLine(string)
            self.startPopTimer()
    def pop(self):
        if len(self.queue) == 0:
            self.waiting = False
        else:
            self.sendIRCLine(self.queue[0])
            self.queue = self.queue[1:]
            self.startPopTimer()

class ircInputBuffer:
    def __init__(self, irc):
        self.buffer = ""
        self.irc = irc
        self.lines = []
    def getLine(self):
        while len(self.lines) == 0:
            #this is the input waiting loop, it is blocking
            self.recv()
            time.sleep(1);
        #take the first line in the queue
        line = self.lines[0]
        self.lines = self.lines[1:]
        # return sanitised line
        return str(line)
    def recv(self):
        #append new data to the buffer
        data = self.buffer + self.irc.recv(4096)
        #add new lines to the queue
        self.lines += data.split(b"\r\n")
        #make take the last part of the split the new buffer value
        self.buffer = self.lines[len(self.lines) - 1]
        self.lines = self.lines[:len(self.lines) - 1]

class ircBot:
    def __init__(self, network, port, name, description):
        self.keepGoing = True
        self.name = name
        self.desc = description
        self.network = network
        self.port = port
        self.identifyNickCommands = []
        self.serverName = ""
        self.binds = []
    #functions you are not supposed to use (which have been privatised)
    def __identAccept(self, nick):
        for (nickName, accept, acceptParams, reject, rejectParams) in self.identifyNickCommands:
            if nickName == nick:
                print nickName + " has been verified."
                accept(self, *acceptParams) #calls the approved callback
                self.identifyNickCommands.remove((nickName, accept, acceptParams, reject, rejectParams))
    def __identReject(self, nick):
        for (nickName, accept, acceptParams, reject, rejectParams) in self.identifyNickCommands:
            if nickName == nick:
                print nickName + " could not be verified."
                reject(self, *rejectParams) #calls the denied callback
                self.identifyNickCommands.remove((nickName, accept, acceptParams, reject, rejectParams))
    def __callBind(self, msgtype, sender, headers, message):
        for (messageType, callback) in self.binds:
            if (messageType == msgtype):
                callback(self, sender, headers, message)
    def __processLine(self, line):
        lineParts = line[1:].split(":")
        headers = lineParts[0].split()
        message = ""
        if len(lineParts) > 1:
            message = line[1:].split(":")[1]
        #id the server
        if self.serverName == "":
            self.serverName = headers[0]
        sender = headers[0]
        if sender == self.serverName:
            print "Received " + headers[1] + " from server."
            if headers[1] == "307" and len(headers) >= 4:
                #is a registered nick
                self.__identAccept(headers[3])
            if headers[1] == "318" and len(headers) >= 4:
                #end of WHOIS message
                #won't reject any accepted commands as they have already been removed from the list
                self.__identReject(headers[3])
            self.__callBind(headers[1], sender, headers[2:], message)
        else:
            #chop the non-nick part off
            cut = headers[0].find('!')
            if cut != -1:
                sender = sender[:cut]
            msgtype = headers[1]
            #split ACTION msgtype from PRIVMSG msgtype and treat as seperate msgtype
            if msgtype == "PRIVMSG" and message.startswith("ACTION ") and message.endswith(""):
                msgtpye = "ACTION"
            print "Received " + msgtype + " from " + sender + "."
            self.__callBind(msgtype, sender, headers[2:], message)
    #functions you are supposed to use
    def identify(self, nick, callbackApproved, approvedParameters, callbackDenied, deniedParameters):
        print "Verifying " + nick + "..."
        self.identifyNickCommands += [(nick, callbackApproved, approvedParameters, callbackDenied, deniedParameters)]
        self.outBuf.push("WHOIS " + nick)
    def connect(self):
        print "Connecting..."
        self.irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.irc.connect((self.network, self.port))
        self.inBuf = ircInputBuffer(self.irc)
        self.outBuf = ircOutputBuffer(self.irc)
        self.outBuf.push("NICK " + self.name)
        self.outBuf.push("USER " + self.name + " " + self.name + " " + self.name + " :" + self.desc)
    def disconnect(self, qMessage):
        print "Disconnecting..."
        self.outBuf.push("QUIT :" + qMessage) 
        self.irc.close()
    def reconnect(self):
        self.disconnect("Reconnecting")
        print "Pausing before reconnecting..."
        time.sleep(5)
        self.connect()
    def join(self, channel):
        print "Joining " + channel + "..."
        self.outBuf.push("JOIN " + channel)
    def say(self, recipient, message):
        self.outBuf.push("PRIVMSG " + recipient + " :" + message)
    def send(self, string):
        self.outBuf.push(string)    
    def bind(self, msgtype, callback):
        for i in xrange(0, len(self.binds)):
            if self.binds[i][0] == msgtype:
                self.binds.remove(i)
        self.binds.append((msgtype, callback))
    def run(self):
        while self.keepGoing:
            # get a new line to process
            line = self.inBuf.getLine()
            #making sure the line isn't empty
            while len(line) == 0:
                line = self.inBuf.getLine()
            # sanitise the data to something we can work with more easily
            line = str(line)
            if line.startswith("PING"):
                #this is rather time critical so it bypasses the output buffer to prevent timeout
                self.outBuf.sendIRCLine("PONG " + line.split()[1])
            else:
                self.__processLine(line)
    def stop(self):
        self.keepGoing = False

# Bot specific function definitions

def authSuccess(bot, recipient, name):
    bot.say(recipient, name + " has been identifed successfully")
    
def authFailure(bot, recipient, name):
    bot.say(recipient, name + " has not been identified")

def quitSuccess(bot, quitMessage):
    bot.disconnect(quitMessage)
    bot.stop()

def reconnectSuccess(bot, channel):
    bot.reconnect()
    bot.join(channel)

def privmsg(bot, sender, headers, message):
    if message.startswith("!send "):
        bot.send(message[6:])
    elif message.startswith("!say "):
        firstSpace = message[5:].find(" ")
        bot.say(message[5:firstSpace], message[firstSpace+1:])
    elif message.startswith("!quit"):
        if sender == "Lukeus_Maximus":
            if len(message) > 6:
                bot.identify(sender, quitSuccess, (message[6:],), authFailure, (headers[0], sender))
            else:
                bot.identify(sender, quitSuccess, ("",), authFailure, (headers[0], sender))
    elif message == "!reconnect":
        if sender == "Lukeus_Maximus":
            bot.identify(sender, reconnectSuccess, (chanName,), authFailure, (headers[0], sender))
    elif message.startswith("!auth "):
        if len(headers) > 0:
            bot.identify(message[6:], authSuccess, (headers[0], message[6:]), authFailure, (headers[0], message[6:]))
        else:
            bot.identify(message[6:], authSuccess, (sender, message[6:]), authFailure, (sender, message[6:]))
    else:
        print "PRIVMSG", sender, headers, message

def actionmsg(bot, sender, headers, message):
    print "ACTION", sender, headers, message

# Main program begins here
if len(sys.argv) == 2:
    chanName = "#" + sys.argv[1]
else:
    chanName = "#maximustestchannel"

bot = ircBot("irc.synirc.net", 6667, "PyBot", "A new bot framework written in python")
bot.bind("PRIVMSG", privmsg)
bot.bind("ACTION", actionmsg)
bot.connect()
bot.join(chanName)
bot.run()

