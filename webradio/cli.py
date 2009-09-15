from dbus.mainloop.glib import DBusGMainLoop
from sys                import argv
from webradio.client    import Client
from webradio.ui        import MainWindow

__commands__ = []

def command(fun):
    __commands__.append(fun)
    return fun

class CommandLineClient(object):
    def __init__(self):
        self.__client = Client()

    @staticmethod
    def list_channels(channels):
        stations = dict()

        for c in channels:
            l = stations.get(c.station, []) + [c]
            stations[c.station] = l

        for s, l in stations.items():
            print '\n - '.join(
                ['%s: %s' % (s.id, s.title)] +
                ['%s [%s]' % (c.title, ' '.join(c.tags)) for c in l])

    @command
    def list(self, args):
        '''List matching stations'''

        self.__client.wait(Client.STATE_CHANNELS_LOADED)
        channels = self.__client.find_channels(args[2:])
        self.list_channels(channels)

    @command
    def status(self, args=None):
        '''Print service status'''

        state = self.__client.is_playing and 'playing' or 'paused'
        channel = self.__client.current_channel

        if channel is not None:
            state += (': "%s" from "%s" [%s]' % (
                channel.title, channel.station.title,
                ' '.join(channel.tags)))

        print state

    @command
    def play(self, args):
        '''Play music from matching station'''

        query = args[2:]
        self.__client.wait(Client.STATE_CHANNELS_LOADED)
        channels = self.__client.find_channels(query)
        channels = list(channels)

        if not channels:
            print 'No matching channels found'
            return

        self.list_channels(channels)

        if 1 == len(channels):
            self.__client.play(channels[0])

    @command
    def pause(self, args=None):
        '''Pause music player'''
        self.__client.pause()

    @command
    def resume(self, args=None):
        '''Resume music player'''
        self.__client.resume()

    @command
    def tags(self, args=None):
        '''Lists known tags'''

        self.__client.wait(Client.STATE_STATIONS_LOADED)
        for tag in self.__client.get_tags():
            print tag

    @command
    def ui(self, args):
        '''Run user interface'''
        MainWindow(self.__client).run()

    @command
    def help(self, args):
        '''Show usage information'''

        commands = [(f.__name__, f.__doc__) for f in __commands__]
        length = max([len(name) for name, desc in commands])

        print 'Usage: %s COMMAND [ARGS]' % args[0]
        print
        print 'Commands:'
        print

        for name, desc in commands:
            print '  %-*s - %s' % (length, name, desc)

        print

    @command
    def quit(self, args):
        '''Stop the background service'''

        self.__client.quit()

    def run(self, args):
        command_name = len(args) > 1 and args[1]
        command_table = dict([(f.__name__, f) for f in __commands__])
        command_table.get(command_name, CommandLineClient.help)(self, args)

if '__main__' == __name__:
    DBusGMainLoop(set_as_default=True)
    CommandLineClient().run(argv[1:])
