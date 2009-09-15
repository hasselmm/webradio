from ConfigParser       import SafeConfigParser
from dbus               import Interface, SessionBus
from dbus.mainloop.glib import DBusGMainLoop
from dbus.service       import BusName, Object, method, signal
from glib               import MainLoop, idle_add
from gtk.gdk            import threads_init
from httplib2           import Http
from threading          import Thread
from urlparse           import urljoin
from webradio.model     import Channel, Station, Stream
from webradio.xdg       import get_cache_filename, get_config_filename
from StringIO           import StringIO

import gst
import re

class Service(Object):
    name = 'de.taschenorakel.webradio'
    interface = '%s.Service' % name

    def __init__(self, bus):
        def player_message_cb(bus, message):
            if gst.MESSAGE_EOS == message.type:
                self.__player.set_state(gst.STATE_NULL)
                return True

            if gst.MESSAGE_ERROR == message.type:
                print message.structure and message.structure.to_string() or ''
                self.__player.set_state(gst.STATE_NULL)
                return True

            if gst.MESSAGE_STATE_CHANGED == message.type:
                if message.src == self.__player:
                    self.StateChanged(*self.GetState())

                return True

            if gst.MESSAGE_TAG == message.type:
                self.StreamTagsChanged(dict(message.structure))
                return True

            #print message.src, message.type, message.structure and message.structure.to_string() or ''
            return True

        self.__data_stage = 0
        self.__player = gst.element_factory_make('playbin')
        self.__player.get_bus().add_watch(player_message_cb)
        self.__httplib = Http(cache=get_cache_filename())
        self.__stations = list()
        self.__stream_tags = dict()

        proxy = SessionBus().get_object('org.freedesktop.Notifications', '/org/freedesktop/Notifications')
        self.__notifications = Interface(proxy, 'org.freedesktop.Notifications')
        self.__notify_id = 0

        name = BusName(Service.name, bus)
        super(Service, self).__init__(bus, '/', name)
        self.__loop = MainLoop(None, True)

        Thread(target=self.__load).start()

    def __fetch(self, uri):
        print 'fetching %s' % uri
        return self.__httplib.request(uri)

    def __notify(self, summary, body=None, id=0, icon='rhythmbox',
                 app_name='webradio', actions=None, hints=None, timeout=-1):
        return self.__notifications.Notify(
            app_name or '', int(id), icon or '', summary,
            body or '', actions or [], hints or {}, int(timeout))

    def __load(self):
        def load_station_details(station):
            response, content = self.__fetch(station.uri)

            if 200 == response.status:
                pattern = re.compile(r'href="([^"]+\.pls)"')

                for uri in pattern.findall(content):
                    if uri.startswith('/'):
                        uri = urljoin(station.uri, uri)
                    if uri.startswith(station.uri):
                        pending_channels.append([station, uri])

        def load_station_list():
            parser = SafeConfigParser()
            parser.read(get_config_filename('stations'))

            for station_id in parser.sections():
                uri = parser.get(station_id, 'uri')
                title = parser.get(station_id, 'title')
                station = Station(station_id, title, uri)

                i = 1

                while True:
                    key = 'noise%d' % i
                    i += 1

                    if not parser.has_option(station_id, key):
                        break

                    noise = parser.get(station_id, key)
                    station.add_noise_filter(noise)

                load_station_details(station)
                self.StationAdded(station)

        def load_streams(channel, content):
            parser = SafeConfigParser()
            parser.readfp(StringIO(content))

            playlist = dict(parser.items('playlist'))
            length = int(playlist['numberofentries'])

            for i in range(1, length + 1):
                uri = playlist['file%d' % i]
                title = playlist.get('title%d' % i)
                length = int(playlist.get('length%d' % i, -1))

                if title:
                    title = channel.station.filter_noise(title)

                stream = Stream(uri, title, length)
                channel.streams.append(stream)

        def load_pending_channels():
            for station, uri in pending_channels:
                response, content = self.__fetch(uri)

                if 200 == response.status:
                    channel = Channel(station, uri)
                    station.channels.append(channel)
                    load_streams(channel, content)
                    self.ChannelAdded(station.id, channel)

        pending_channels = []

        load_station_list()
        idle_add(self.DataReady, 1)

        load_pending_channels()
        idle_add(self.DataReady, 2)

    def run(self):
        try:
            self.__loop.run()

        except KeyboardInterrupt:
            self.__loop.quit()

    @method(dbus_interface=interface, utf8_strings=True,
            in_signature='', out_signature='a' + Station.dbus_signature)
    def GetStations(self):
        return self.__stations

    @method(dbus_interface=interface, utf8_strings=True,
            in_signature='', out_signature='a{sv}')
    def GetStreamTags(self):
        print self.__stream_tags
        return self.__stream_tags

    @method(dbus_interface=interface, utf8_strings=True, in_signature='as',
            out_signature='a(s' + Channel.dbus_signature + ')')
    def Find(self, query):
        result = list()

        for station in self.__stations:
            for channel in station.channels:
                if channel.matches(query):
                    match = station.id, channel
                    result.append(match)

        return result

    @method(dbus_interface=interface, in_signature='s', out_signature='')
    def Play(self, uri):
        self.__player.set_state(gst.STATE_NULL)
        self.__player.set_property('uri', uri)
        self.__player.set_state(gst.STATE_PLAYING)

    @method(dbus_interface=interface, in_signature='', out_signature='')
    def Pause(self):
        self.__player.set_state(gst.STATE_PAUSED)

    @method(dbus_interface=interface, in_signature='', out_signature='')
    def Resume(self):
        self.__player.set_state(gst.STATE_PLAYING)

    @method(dbus_interface=interface, in_signature='', out_signature='')
    def Quit(self):
        self.__loop.quit()

    @method(dbus_interface=interface, in_signature='', out_signature='i')
    def GetDataStage(self):
        return self.__data_stage

    @method(dbus_interface=interface, in_signature='', out_signature='bs')
    def GetState(self):
        playing = (gst.STATE_PLAYING == self.__player.get_state()[1])
        channel_uri = self.__player.get_property('uri') or ''
        return playing, channel_uri

    @signal(dbus_interface=interface, signature='i')
    def DataReady(self, stage):
        self.__data_stage = stage

    @signal(dbus_interface=interface, signature=Station.dbus_signature)
    def StationAdded(self, station):
        self.__stations.append(station)

    @signal(dbus_interface=interface, signature='s' + Channel.dbus_signature)
    def ChannelAdded(self, station_id, channel):
        pass

    @signal(dbus_interface=interface, signature='bs')
    def StateChanged(self, playing, stream_uri):
        pass

    @signal(dbus_interface=interface, signature='a{sv}')
    def StreamTagsChanged(self, tags):
        self.__stream_tags.update(tags)

        summary = self.__stream_tags.get('title') or ''
        body = self.__stream_tags.get('organization') or ''
        self.__notify_id = self.__notify(summary, body, id=self.__notify_id)

    @method(dbus_interface=interface, in_signature='', out_signature='as')
    def GetTags(self):
        tags = dict()

        for s in self.__stations:
            for c in s.channels:
                for t in c.tags:
                    tags[t] = True

            tags[s.id] = True

        tags = list(tags)
        tags.sort()

        return tags

if '__main__' == __name__:
    threads_init()
    DBusGMainLoop(set_as_default=True)
    Service(SessionBus()).run()
