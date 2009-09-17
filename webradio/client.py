from dbus             import Interface, SessionBus
from glib             import MainLoop, timeout_add, source_remove
from gobject          import GObject, SIGNAL_RUN_LAST, TYPE_NONE
from webradio.model   import Channel, Station, Stream
from webradio.service import Service

import sys

class Client(GObject):
    (STATE_INITIALIZED,
     STATE_STATIONS_LOADED,
     STATE_CHANNELS_LOADED) = range(3)

    __gtype_name__ = 'WebRadioClient'

    __gsignals__ = {
        'station-added':       (SIGNAL_RUN_LAST, TYPE_NONE, (object,)),
        'channel-added':       (SIGNAL_RUN_LAST, TYPE_NONE, (object,)),
        'state-changed':       (SIGNAL_RUN_LAST, TYPE_NONE, ()),
        'stream-tags-changed': (SIGNAL_RUN_LAST, TYPE_NONE, ()),
    }

    @staticmethod
    def decode_stream(uri, title, length):
        return Stream(uri, title, length)

    @classmethod
    def decode_channel(cls, station, uri, tags, streams):
        streams = [cls.decode_stream(*s) for s in streams]
        return Channel(station, uri, tags, streams)

    def __init__(self):
        super(Client, self).__init__()

        self.__stations = dict()
        self.__channels = dict()
        self.__stream_tags = dict()

        self.__current_channel = None
        self.__is_playing = False

        def register_channel(station, channel):
            if station:
                station.channels.append(channel)

            for stream in channel.streams:
                self.__channels[stream.uri] = channel

            self.__channels[channel.uri] = channel

        def station_added_cb(station):
            id, title, uri, channels = station
            station = Station(id, title, uri)

            for channel in channels:
                channel = self.decode_channel(station, *channel)
                register_channel(station, channel)

            self.__stations[station.id] = station
            self.emit('station-added', station)

        def channel_added_cb(station_id, channel):
            station = self.find_station(station_id)
            channel = self.decode_channel(station, *channel)
            register_channel(station, channel)
            self.emit('channel-added', channel)

        def state_changed_cb(playing, stream_uri):
            self.__stream_tags = self.__service.GetStreamTags()
            self.__current_channel = self.__channels.get(stream_uri)
            self.__is_playing = playing
            self.emit('state-changed')

        def stream_tags_changed_cb(tags):
            self.__stream_tags.update(tags)
            self.emit('stream-tags-changed')

        def name_owner_cb(new_owner):
            if not new_owner:
                # FIXME
                from gtk import main_quit
                main_quit()

        self.__bus = SessionBus()
        proxy = self.__bus.get_object(Service.name, '/')
        self.__bus.watch_name_owner(Service.name, name_owner_cb)
        self.__service = Interface(proxy, Service.interface)
        self.__service.connect_to_signal('StationAdded',      station_added_cb)
        self.__service.connect_to_signal('ChannelAdded',      channel_added_cb)
        self.__service.connect_to_signal('StateChanged',      state_changed_cb)
        self.__service.connect_to_signal('StreamTagsChanged', stream_tags_changed_cb)

        for station in self.__service.GetStations():
            station_added_cb(station)

        state_changed_cb(*self.__service.GetState())

    def wait(self, stage=STATE_CHANNELS_LOADED):
        loop = MainLoop(None, True)

        def data_ready_cb(new_stage):
            if new_stage >= stage:
                loop.quit()

        self.__service.connect_to_signal('DataReady', data_ready_cb)

        if self.__service.GetDataStage() >= stage:
            loop.quit()

        progress_id = 0

        if loop.is_running():
            if sys.stdout.isatty():
                progress = ['-\r', '\\\r', '|\r', '/\r']

                def progress_cb():
                    c = progress.pop(0)
                    sys.stdout.write(c)
                    sys.stdout.flush()
                    progress.append(c)
                    return True

                progress_id = timeout_add(250, progress_cb)
                sys.stdout.write('  loading...\r')

            loop.run()

        if progress_id:
            source_remove(progress_id)
            sys.stdout.write('\r\033[K')
            sys.stdout.flush()

    def find_channels(self, query=[]):
        result = list()

        for station_id, channel in self.__service.Find(query):
            station = self.__stations.get(station_id)
            channel = self.decode_channel(station, *channel)
            result.append(channel)

        return result

    def find_station(self, id):
        return self.__stations.get(id)
    def get_stations(self):
        return self.__stations.values()

    def get_tags(self):
        return self.__service.GetTags()

    def play(self, channel):
        self.__service.Play(channel.streams[0].uri)

    def pause(self):
        self.__service.Pause()

    def resume(self):
        self.__service.Resume()

    def quit(self):
        self.__service.Quit()

    def get_equalizer_profiles(self):
        return self.__service.ListEqualizerProfiles()
    def __get_equalizer_profile(self):
        return self.__service.GetEqualizerProfile()
    def __set_equalizer_profile(self, value):
        self.__service.SetEqualizerProfile(value)

    is_playing = property(fget=lambda self: self.__is_playing)
    current_channel = property(fget=lambda self: self.__current_channel)
    stream_tags = property(fget=lambda self: self.__stream_tags)
    equalizer_profile = property(fget=__get_equalizer_profile, fset=__set_equalizer_profile)

