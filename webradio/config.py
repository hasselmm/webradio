from ConfigParser import SafeConfigParser
from webradio.xdg import get_config_filename

class Configuration(object):
    def __init__(self):
        self.__parser = SafeConfigParser()
        self.__parser.add_section('WebRadio')

        self.read()

    def read(self, target=None):
        if target is None:
            target = self.filename

        self.__parser.read(target)

    def write(self, target=None):
        if target is None:
            target = self.filename
        if isinstance(target, str):
            target = file(target, 'w')

        self.__parser.write(target)

    def _get(self, section, key, default=None):
        if not section:
            section = 'WebRadio'
        if self.__parser.has_option(section, key):
            return self.__parser.get(section, key)

        return default

    def _set(self, section, key, value):
        if not section:
            section = 'WebRadio'

        return self.__parser.set(section, key, value)

    filename = property(
        fget=lambda self: get_config_filename('settings'))

    tags = property(
        fget=lambda self: self._get(None, 'tags'),
        fset=lambda self, value: self._set(None, 'tags', value))

    channel_uri = property(
        fget=lambda self: self._get(None, 'channel-uri'),
        fset=lambda self, value: self._set(None, 'channel-uri', value))

