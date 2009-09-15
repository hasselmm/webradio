from ctypes      import CDLL, CFUNCTYPE, c_char_p
from ctypes.util import find_library

import os.path

libglib = CDLL(find_library('glib-2.0'))
prototype = CFUNCTYPE(c_char_p)

get_cache_dir  = prototype(('g_get_user_cache_dir',  libglib))
get_config_dir = prototype(('g_get_user_config_dir', libglib))
get_data_dir   = prototype(('g_get_user_data_dir',   libglib))

del prototype
del libglib

def get_cache_filename(*args):
    return os.path.join(get_cache_dir(), 'webradio', *args)
def get_config_filename(*args):
    return os.path.join(get_config_dir(), 'webradio', *args)
def get_data_filename(*args):
    return os.path.join(get_data_dir(), 'webradio', *args)

