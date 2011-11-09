from ConfigParser       import SafeConfigParser
from dbus               import Interface, SessionBus
from dbus.mainloop.glib import DBusGMainLoop
from dbus.service       import BusName, Object, method, signal
from glib               import MainLoop, idle_add, source_remove, timeout_add_seconds
from gtk.gdk            import threads_init
from httplib2           import Http
from threading          import Thread
from urlparse           import urljoin
from webradio.model     import Channel, Station, Stream
from webradio.player    import Player
from webradio.xdg       import get_cache_filename, get_config_filename
from StringIO           import StringIO

import gst
import os.path
import re
import sys

class Favorites(object):
    def __init__(self):
        self.__filename = get_config_filename('favorites')
        self.__parser = SafeConfigParser()
        self.__parser.read(self.__filename)
        self.__current_uri = None
        self.__top_score = 0
        self.__update_id = 0

    def _update_cb(self):
        score = self._get_score(self.__current_uri)
        self._set_score(self.__current_uri, score + 1)

        print (self.top_score,
               self.get_absolute_score(self.__current_uri),
               self.get_relative_score(self.__current_uri))

    def set_state(self, playing, uri):
        self.__current_uri = uri

        if playing and not self.__update_id:
            self.__update_id = timeout_add_seconds(300, self._update_cb)
            self._update_cb()

        elif not playing and self.__update_id:
            source_remove(self.__update_id)
            self.__update_id = 0

    def _get_key(self, uri):
        return 'Scoreboard', uri

    def _get_score(self, uri):
        key = self._get_key(uri)

        if self.__parser.has_option(*key):
            return self.__parser.getint(*key)

        return 0

    def _set_score(self, uri, score):
        key = self._get_key(uri)

        if not self.__parser.has_section(key[0]):
            self.__parser.add_section(key[0])

        self.__parser.set(*(key + (str(score), )))
        self.__parser.write(file(self.__filename, 'w'))
        self.__top_score = max(self.__top_score, score)

    def get_relative_score(self, uri):
        print self.__top_score

        if self.__top_score > 0:
            return (float(self._get_score(uri)) /
                    float(self.__top_score))

        return 0

    top_score = property(fget=lambda self: self.__top_score)
    get_absolute_score = _get_score

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
                    self.__favorites.set_state(*self.GetState())

                return True

            if gst.MESSAGE_TAG == message.type:
                valid_types = float, int, str, unicode

                tags = [(k, v) for k, v
                        in dict(message.structure).items()
                        if isinstance(v, valid_types)]

                self.StreamTagsChanged(dict(tags))

                return True

            return True

        self.__data_stage = 0
        self.__player = Player()
        self.__player.get_bus().add_watch(player_message_cb)
        self.__httplib = Http(cache=get_cache_filename())
        self.__favorites = Favorites()
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
                    if station.accept_stream(uri):
                        pending_channels.append([station, uri])

                print '%d stations found...' % len(pending_channels)

            else:
                print 'Bad response: %s %s' % (response.reason,
                                               response.status)

        def find_config_file(basename):
            filename = get_config_filename(basename)

            if os.path.isfile(filename):
                return filename

            for libdir in sys.path:
                prefix = os.path.commonprefix([__file__, libdir])

                if not prefix or prefix != libdir:
                    continue

                libdir_parent, libdir_name = os.path.split(libdir)

                if 'site-packages' == libdir_name:
                    prefix = os.path.join(libdir_parent, '..', '..')
                    filename = os.path.join(prefix, 'share', 'webradio', basename)

                    if os.path.isfile(filename):
                        return filename

                for filename in [
                        os.path.join(libdir, 'data', basename),
                        os.path.join(libdir_parent, 'data', basename)]:
                    if os.path.isfile(filename):
                        return filename

            return None

        def load_station_list():
            filename = find_config_file('stations')

            if filename is None:
                raise RuntimeError, 'Cannot find station list'

            print 'reading stations from %r' % filename

            parser = SafeConfigParser()
            parser.read(filename)

            for station_id in parser.sections():
                uri = parser.get(station_id, 'uri')
                title = parser.get(station_id, 'title')
                stream_uri = parser.get(station_id, 'streams')
                station = Station(station_id, title, uri)

                if stream_uri:
                    station.stream_uri = stream_uri

                i = 1

                while True:
                    key = 'noise%d' % i
                    i += 1

                    if not parser.has_option(station_id, key):
                        break

                    noise = parser.get(station_id, key)
                    station.add_noise_filter(noise)
                for key in parser.options(station_id):
                    if key.startswith('alias.'):
                        name = key[len('alias.'):]
                        value = parser.get(station_id, key)
                        station.add_alias(name, value)
                        continue

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
        self.__player.uri = uri
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
        channel_uri = self.__player.uri or ''
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

    @method(dbus_interface=interface, in_signature='', out_signature='as')
    def ListEqualizerProfiles(self):
        return self.__player.get_profile_names()

    @method(dbus_interface=interface, in_signature='', out_signature='s')
    def GetEqualizerProfile(self):
        return self.__player.profile

    @method(dbus_interface=interface, in_signature='s', out_signature='')
    def SetEqualizerProfile(self, profile_name):
        self.__player.profile = profile_name

if '__main__' == __name__:
    threads_init()
    DBusGMainLoop(set_as_default=True)
    Service(SessionBus()).run()
