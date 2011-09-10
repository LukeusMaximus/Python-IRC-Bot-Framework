from ircbotframe import ircBot
import sys

# Bot specific function definitions
    
def authFailure(bot, recipient, name):
    bot.say(recipient, "You could not be identified")

def quitSuccess(bot, quitMessage):
    bot.disconnect(quitMessage)
    bot.stop()
    
def joinSuccess(bot, channel):
    bot.join(channel)

def saySuccess(bot, channel, message):
    bot.say(channel, message)

def privmsg(bot, sender, headers, message):
    if message.startswith("!say "):
        firstSpace = message[5:].find(" ") + 5
        print message[5:], firstSpace
        if sender == owner:
            print (message[:firstSpace], message[firstSpace+1:])
            bot.identify(sender, saySuccess, (message[5:firstSpace], message[firstSpace+1:]), authFailure, (sender,))
    elif message.startswith("!quit"):
        if sender == owner:
            if len(message) > 6:
                bot.identify(sender, quitSuccess, (message[6:],), authFailure, (headers[0], sender))
            else:
                bot.identify(sender, quitSuccess, ("",), authFailure, (headers[0], sender))
    elif message.startswith("!join "):
        if sender == owner:
            bot.identify(sender, joinSuccess, (message[6:],), authFailure, (headers[0], sender))

def actionmsg(bot, sender, headers, message):
    print "An ACTION message was sent by " + sender + " with the headers " + headers + ". It says: \"" + sender + " " + message

# Main program begins here
if __name__ == "__main__":
    if len(sys.argv) == 3:
        owner = sys.argv[1]
        chanName = "#" + sys.argv[2]
        bot = ircBot("irc.synirc.net", 6667, "ExampleBot", "An example bot written with the new IRC bot framework")
        bot.bind("PRIVMSG", privmsg)
        bot.bind("ACTION", actionmsg)
        bot.connect()
        bot.join(chanName)
        bot.say(chanName, "I am an example bot.")
        bot.say(chanName, "I have 3 functions, they are Join, Quit and Say.")
        bot.say(chanName, "Join (joins a channel); Usage: \"!join #<channel>\"")
        bot.say(chanName, "Quit (disconnects from the IRC server); Usage: \"!quit [<quit message>]\"")
        bot.say(chanName, "Say (makes the bot say something); Usage: \"!say <channel> <message>\"")
        bot.say(chanName, "The underlying framework is in no way limited to the above functions.")
        bot.say(chanName, "This is merely an example of the framework's usage")
        bot.run()
    else:
        print "Usage: python examplebot.py <your IRC nick> <irc channel (no '#' character please)>"


