import re
import urlparse

class Stream(object):
    dbus_signature  = '(ssi)'

    def __init__(self, uri, title, length):
        self.__uri    = uri
        self.__title  = title
        self.__length = length

    def __iter__(self):
        yield self.uri
        yield self.title
        yield self.length

    uri    = property(fget=lambda self: self.__uri)
    title  = property(fget=lambda self: self.__title)
    length = property(fget=lambda self: self.__length)

class Channel(object):
    dbus_signature = '(sasa' + Stream.dbus_signature + ')'

    def __init__(self, station, uri, tags=None, streams=None):
        self.__station = station
        self.__uri     = uri
        self.__tags    = tags
        self.__streams = streams

        aliases = station.aliases

        if self.__tags is None:
            path = urlparse.urlparse(uri)[2].split('/')
            self.__tags = [aliases.get(t, t) for t in
                           path[1:-1] + path[-1].split('.')[:-1]]
        if self.__streams is None:
            self.__streams = []

    def __iter__(self):
        yield self.uri
        yield self.tags
        yield self.streams

    def matches_criterion(self, q):
        if q in self.tags:
            return True
        if q == self.station.id:
            return True
        if self.station.title.find(q) >= 0:
            return True
        if self.title.find(q) >= 0:
            return True

        return False

    def matches(self, query):
        for q in query:
            if not self.matches_criterion(q):
                return False

        return True

    def _get_title(self):
        if self.streams:
            return self.streams[0].title

        return self.__uri

    station = property(fget=lambda self: self.__station)
    uri     = property(fget=lambda self: self.__uri)
    tags    = property(fget=lambda self: self.__tags)
    streams = property(fget=lambda self: self.__streams)
    title   = property(fget=_get_title)

class Station(object):
    dbus_signature = '(sssa' + Channel.dbus_signature + ')'

    def __init__(self, id, title, uri, channels = None):
        self.__id         = id
        self.__title      = title
        self.__uri        = uri
        self.__stream_uri = None
        self.__channels   = channels if channels is not None else []
        self.__aliases    = dict()

        self.__noise_filters = [
            re.compile(re.escape(self.title)),
            re.compile(r'(^\s*-\s*|\s*-\s*$)')
        ]

    def __iter__(self):
        yield self.id
        yield self.title
        yield self.uri
        yield self.channels

    def accept_stream(self, uri):
        if not uri.endswith('.pls'):
            return False
        if self.__stream_uri and uri.startswith(self.__stream_uri):
            return True

        return uri.startswith(self.uri)

    def add_noise_filter(self, pattern):
        self.__noise_filters.insert(-2, re.compile(pattern))

    def filter_noise(self, text):
        for f in self.__noise_filters:
            text = f.subn('', text)[0].strip()

        return text

    def add_alias(self, name, value):
        self.__aliases[name] = value

    def _set_stream_uri(self, uri):
        self.__stream_uri = uri

    id         = property(fget=lambda self: self.__id)
    title      = property(fget=lambda self: self.__title)
    uri        = property(fget=lambda self: self.__uri)
    stream_uri = property(fget=lambda self: self.__stream_uri, fset=_set_stream_uri)
    channels   = property(fget=lambda self: self.__channels)
    aliases    = property(fget=lambda self: self.__aliases)

