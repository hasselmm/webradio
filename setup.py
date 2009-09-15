#!/usr/bin/env python

from distutils.core import setup

setup(name='WebRadio',
      version='0.1',
      description='My sleek webradio player',
      author='Mathias Hasselmann',
      author_email='mathias@taschenorakel.de',
      url='http://github.com/hasselmm/webradio',

      classifiers=[
          'Development Status :: 3 - Alpha',
          'Environment :: Console',
          'Environment :: X11 Applications :: GTK',
          'Intended Audience :: End Users/Desktop',
          'License :: OSI Approved :: GNU General Public License (GPL)',
          'Operating System :: POSIX',
          'Programming Language :: Python',
          'Topic :: Multimedia :: Sound/Audio :: Players',
      ],

      packages=['data', 'webradio'],
      package_dir={'data': 'data'},
      package_data={'data': ['stations']},
      scripts=['bin/webradio', 'bin/webradio-service'],

      data_files=[
          ('share/dbus-1/services', ['data/de.taschenorakel.webradio.service']),
          ('share/webradio', ['data/stations']),
      ],
)

