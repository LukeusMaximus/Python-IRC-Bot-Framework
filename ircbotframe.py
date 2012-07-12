import socket
import threading
import re
import time

class ircOutputBuffer:
    # Delays consecutive messages by at least 1 second.
    # This prevents the bot spamming the IRC server.
    def __init__(self, irc):
        self.waiting = False
        self.irc = irc
        self.queue = []
        self.error = False
    def __pop(self):
        if len(self.queue) == 0:
            self.waiting = False
        else:
            self.sendImmediately(self.queue[0])
            self.queue = self.queue[1:]
            self.__startPopTimer()
    def __startPopTimer(self):
        self.timer = threading.Timer(1, self.__pop)
        self.timer.start()
    def sendBuffered(self, string):
        # Sends the given string after the rest of the messages in the buffer.
        # There is a 1 second gap between each message.
        if self.waiting:
            self.queue.append(string)
        else:
            self.waiting = True
            self.sendImmediately(string)
            self.__startPopTimer()
    def sendImmediately(self, string):
        # Sends the given string without buffering.
        if not self.error:
            try:
                self.irc.send(bytes(string) + b"\r\n")
            except socket.error, msg:
                self.error = True
                print "Output error", msg
                print "Was sending \"" + string + "\""
    def isInError(self):
        return self.error

class ircInputBuffer:
    # Keeps a record of the last line fragment received by the socket which is usually not a complete line.
    # It is prepended onto the next block of data to make a complete line.
    def __init__(self, irc):
        self.buffer = ""
        self.irc = irc
        self.lines = []
    def __recv(self):
        # Receives new data from the socket and splits it into lines.
        # Last (incomplete) line is kept for buffer purposes.
        try:
            data = self.buffer + self.irc.recv(4096)
        except socket.error, msg:
            raise socket.error, msg
        self.lines += data.split(b"\r\n")
        self.buffer = self.lines[len(self.lines) - 1]
        self.lines = self.lines[:len(self.lines) - 1]
    def getLine(self):
        # Returns the next line of IRC received by the socket.
        # Converts the received string to standard string format before returning.
        while len(self.lines) == 0:
            try:
                self.__recv()
            except socket.error, msg:
                raise socket.error, msg
            time.sleep(1);
        line = self.lines[0]
        self.lines = self.lines[1:]
        return str(line)

class ircBot(threading.Thread):
    def __init__(self, network, port, name, description):
        threading.Thread.__init__(self)
        self.keepGoing = True
        self.name = name
        self.desc = description
        self.network = network
        self.port = port
        self.identifyNickCommands = []
        self.identifyLock = False
        self.binds = []
        self.debug = False
    # PRIVATE FUNCTIONS
    def __identAccept(self, nick):
        """ Executes all the callbacks that have been approved for this nick
    	"""
        i = 0  
        while i < len(self.identifyNickCommands):
            (nickName, accept, acceptParams, reject, rejectParams) = self.identifyNickCommands[i]
            if nick == nickName:
                accept(*acceptParams)
                self.identifyNickCommands.pop(i)
            else:
                i += 1
    def __identReject(self, nick):
        # Calls the given "denied" callback for all functions called by that nick.
        i = 0
        while i < len(self.identifyNickCommands):
            (nickName, accept, acceptParams, reject, rejectParams) = self.identifyNickCommands[i]
            if nick == nickName:
                reject(*rejectParams)
                self.identifyNickCommands.pop(i)
            else:
                i += 1
    def __callBind(self, msgtype, sender, headers, message):
        # Calls the function associated with the given msgtype.
        for (messageType, callback) in self.binds:
            if (messageType == msgtype):
                callback(sender, headers, message)
    def __processLine(self, line):
        # If a message comes from another user, it will have an @ symbol
        if "@" in line:
            # Location of the @ symbol in the line (proceeds sender's domain)
            at = line.find("@")
            # Location of the first gap, this immediately follows the sender's domain
            gap = line[at:].find(" ") + at + 1
            lastColon = line[gap+1:].find(":") + 2 + gap
        else:
            lastColon = line[1:].find(":") + 1

        # Does most of the parsing of the line received from the IRC network.
        # if there is no message to the line. ie. only one colon at the start of line
        if ":" not in line[1:]:
            headers = line[1:].strip().split(" ")
            message = ""
        else:
            # Split everything up to the lastColon (ie. the headers)
            headers = line[1:lastColon-1].strip().split(" ")
            message = line[lastColon:]
            
        sender = headers[0]
        if len(headers) < 2:
            self.__debugPrint("Unhelpful number of messages in message: \"" + line + "\"")
        else:
            if "!" in sender:
                cut = headers[0].find('!')
                if cut != -1:
                    sender = sender[:cut]
                msgtype = headers[1]
                if msgtype == "PRIVMSG" and message.startswith("ACTION ") and message.endswith(""):
                    msgtype = "ACTION"
                    message = message[8:-1]
                self.__callBind(msgtype, sender, headers[2:], message)
            else:
                self.__debugPrint("[" + headers[1] + "] " + message)
                if (headers[1] == "307" or headers[1] == "330") and len(headers) >= 4:
                    self.__identAccept(headers[3])
                if headers[1] == "318" and len(headers) >= 4:
                    self.__identReject(headers[3])
                    #identifies the next user in the nick commands list
                    if len(self.identifyNickCommands) == 0:
                        self.identifyLock = False
                    else:
                        self.outBuf.sendBuffered("WHOIS " + self.identifyNickCommands[0][0])
                self.__callBind(headers[1], sender, headers[2:], message)
                
    def __debugPrint(self, s):
        if self.debug:
            print s
    # PUBLIC FUNCTIONS
    def ban(self, banMask, channel, reason):
        self.__debugPrint("Banning " + banMask + "...")
        self.outBuf.sendBuffered("MODE +b " + channel + " " + banMask)
        self.kick(nick, channel, reason)
        
    def bind(self, msgtype, callback):
        # Check if the msgtype already exists
        for i in xrange(0, len(self.binds)):
            # Remove msgtype if it has already been "binded" to 
            if self.binds[i][0] == msgtype:
                self.binds.remove(i)
        self.binds.append((msgtype, callback))
        
    def connect(self):
        self.__debugPrint("Connecting...")
        self.irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.irc.connect((self.network, self.port))
        self.inBuf = ircInputBuffer(self.irc)
        self.outBuf = ircOutputBuffer(self.irc)
        self.outBuf.sendBuffered("NICK " + self.name)
        self.outBuf.sendBuffered("USER " + self.name + " " + self.name + " " + self.name + " :" + self.desc)
    def debugging(self, state):
        self.debug = state
    def disconnect(self, qMessage):
        self.__debugPrint("Disconnecting...")
        self.outBuf.sendBuffered("QUIT :" + qMessage)
        self.irc.close()
    def identify(self, nick, approvedFunc, approvedParams, deniedFunc, deniedParams):
        self.__debugPrint("Verifying " + nick + "...")
        self.identifyNickCommands += [(nick, approvedFunc, approvedParams, deniedFunc, deniedParams)]
        if not self.identifyLock:
            self.outBuf.sendBuffered("WHOIS " + nick)
            self.identifyLock = True
    def joinchan(self, channel):
        self.__debugPrint("Joining " + channel + "...")
        self.outBuf.sendBuffered("JOIN " + channel)
    def kick(self, nick, channel, reason):
        self.__debugPrint("Kicking " + nick + "...")
        self.outBuf.sendBuffered("KICK " + channel + " " + nick + " :" + reason)
    def reconnect(self):
        self.disconnect("Reconnecting")
        self.__debugPrint("Pausing before reconnecting...")
        time.sleep(5)
        self.connect()
    def run(self):
        self.__debugPrint("Bot is now running.")
        self.connect()
        while self.keepGoing:
            line = ""
            while len(line) == 0:
                try:
                    line = self.inBuf.getLine()
                except socket.error, msg:
                    print "Input error", msg
                    self.reconnect()
            if line.startswith("PING"):
                self.outBuf.sendImmediately("PONG " + line.split()[1])
            else:
                self.__processLine(line)
            if self.outBuf.isInError():
                self.reconnect()
    def say(self, recipient, message):
        self.outBuf.sendBuffered("PRIVMSG " + recipient + " :" + message)  
    def send(self, string):
        self.outBuf.sendBuffered(string)
    def stop(self):
        self.keepGoing = False
    def unban(self, banMask, channel):
        self.__debugPrint("Unbanning " + banMask + "...")
        self.outBuf.sendBuffered("MODE -b " + channel + " " + banMask)

