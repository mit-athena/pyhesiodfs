from distutils.core import setup
import sys

extra_options = {}

# The script is named this on all platforms except OS X
script_name='pyhesiodfs'
if sys.platform == 'darwin':
    extra_options['data_files'] = [('/Library/LaunchDaemons', ('edu.mit.sipb.mit-automounter.plist',))]
    script_name='pyHesiodFS.py

setup(name='pyHesiodFS',
      version='1.0.1',
      author='Quentin Smith',
      author_email='pyhesiodfs@mit.edu',
      maintainer='Debathena Project',
      maintainer_email='debathena@mit.edu',
      scripts=[script_name],
      requires=['PyHesiod (>=0.2.0)'],
      **extra_options)
