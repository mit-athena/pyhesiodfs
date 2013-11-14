from distutils.core import setup
from distutils.command.build_scripts import build_scripts
from distutils.command.clean import clean
import sys, os, shutil, filecmp

extra_options = {}

if sys.platform == 'darwin':
    extra_options['data_files'] = [('/Library/LaunchDaemons', ('edu.mit.sipb.mit-automounter.plist',))]
    copy_file = None
    script_name = 'pyHesiodFS.py'
else:
    script_name='pyhesiodfs'
    copy_file = ('pyHesiodFS.py', 'pyhesiodfs')

class BuildScriptsCommand(build_scripts):
    def finalize_options(self):
        build_scripts.finalize_options(self)
        if copy_file is not None:
            if os.path.isfile(copy_file[1]) and not filecmp.cmp(*copy_file, shallow=False):
                raise Exception("Will not overwrite existing '%s' with '%s'" % tuple(reversed(copy_file)))
            shutil.copyfile(*copy_file)

class CleanCommand(clean):
    def finalize_options(self):
        clean.finalize_options(self)
        if copy_file is not None and os.path.isfile(copy_file[1]):
            if not filecmp.cmp(*copy_file, shallow=False):
                raise Exception("Will not remove '%s', it's not the same as '%s'" % tuple(reversed(copy_file)))
            os.unlink(copy_file[1])

setup(name='pyHesiodFS',
      version='1.1',
      author='Quentin Smith',
      author_email='pyhesiodfs@mit.edu',
      maintainer='Debathena Project',
      maintainer_email='debathena@mit.edu',
      scripts=[script_name],
      requires=['PyHesiod (>=0.2.0)'],
      cmdclass={
        'clean': CleanCommand,
        'build_scripts': BuildScriptsCommand,
        },
      **extra_options)
