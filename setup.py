from distutils.core import setup
import sys

extra_options = {}

if sys.platform == 'darwin':
    extra_options['data_files'] = [('/Library/LaunchDaemons', ('edu.mit.sipb.mit-automounter.plist',))]

setup(name='pyHesiodFS',
      version='1.0',
      author='Quentin Smith',
      author_email='pyhesiodfs@mit.edu',
      scripts=['pyHesiodFS.py'],
      requires=['PyHesiod (>=0.2.0)'],
      **extra_options)
