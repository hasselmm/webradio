import gst
import glib
import sys

class Player(gst.Pipeline):
    __profiles = {
        'flat': [0, 0, 0],
        'pop':  [8, 0, 8],
    }

    def __init__(self):
        super(Player, self).__init__()

        elements = [
            ('uridecodebin',     'decoder'),
            ('audioconvert',     'converter'),
            ('volume',           'volume'),
            ('equalizer-3bands', 'equalizer'),
            ('autoaudiosink',    'audiosink'),
        ]

        for factory, name in elements:
            self.add(gst.element_factory_make(factory, name))

        def pad_added_cb(decoder, pad):
            converter = self.get_by_name('converter')
            volume    = self.get_by_name('volume')
            equalizer = self.get_by_name('equalizer')
            audiosink = self.get_by_name('audiosink')

            pad.link(converter.get_static_pad('sink'))

            converter.link(volume)
            volume   .link(equalizer)
            equalizer.link(audiosink)

        decoder = self.get_by_name('decoder')
        decoder.connect('pad_added', pad_added_cb)

        self.profile = 'pop'

    @classmethod
    def get_profile_names(cls):
        return cls.__profiles.keys()

    def __set_profile(self, value):
        equalizer = self.get_by_name('equalizer')
        profile = self.__profiles[value]

        for i in range(0, len(profile)):
            equalizer.set_property('band%d' % i, profile[i])

        self.__profile_name = value

    def __get_profile(self):
        return self.__profile_name

    def __set(self, name, key, value):
        self.get_by_name(name).set_property(key, value)
    def __get(self, name, key):
        return self.get_by_name(name).get_property(key)

    def __set_uri(self, value):
        self.__set('decoder', 'uri', value)
    def __get_uri(self):
        return self.__get('decoder', 'uri')

    def __set_volume(self, value):
        self.__set('volume', 'volume', value)
    def __get_volume(self):
        return self.__get('volume', 'volume')

    def run(self, uri):
        def bus_cb(bus, msg):
            if gst.MESSAGE_TAG == msg.type:
                print dict(msg.structure)

            return True

        def test_cb():
            if 'flat' == self.profile:
                self.profile = 'pop'
            else:
                self.profile = 'flat'

            return True

        glib.timeout_add(5000, test_cb)
        self.get_bus().add_watch(bus_cb)

        self.uri = uri
        self.volume = 0.5
        self.set_state(gst.STATE_PLAYING)

        try: glib.MainLoop().run()
        except KeyboardInterrupt: pass

    profile = property(fget=__get_profile, fset=__set_profile)
    uri     = property(fget=__get_uri,     fset=__set_uri)
    volume  = property(fget=__get_volume,  fset=__set_volume)

if '__main__' == __name__:
    Player().run(sys.argv[1])
