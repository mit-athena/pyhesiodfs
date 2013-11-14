#!/usr/bin/python2

#    pyHesiodFS:
#    Copyright (c) 2013  Massachusetts Institute of Technology
#    Copyright (C) 2007  Quentin Smith <quentin@mit.edu>
#    "Hello World" pyFUSE example:
#    Copyright (C) 2006  Andrew Straw  <strawman@astraw.com>
#
#    This program can be distributed under the terms of the GNU LGPL.
#    See the file COPYING.
#

import sys
if sys.hexversion < 0x020600f0:
    sys.exit("Python 2.6 or higher is required.")

import os, stat, errno, time
from syslog import *
import fuse
from fuse import Fuse
from ConfigParser import RawConfigParser
from collections import defaultdict

import locker

ATTACHTAB_PATH='.attachtab'

class PyHesiodFSConfigParser(RawConfigParser):
    """
    A subclass of RawConfigParser that provides a single place to
    store defaults, and ensures a section exists, along with
    per-platform default values for the config file.  Also override
    getboolean to provide a method that deals with invalid values.
    """
    CONFIG_FILES = { 'darwin': '/Library/Preferences/PyHesiodFS.ini',
                     '_DEFAULT': '/etc/pyhesiodfs/config.ini',
                     }

    CONFIG_DEFAULTS = { 'show_readme': 'false',
                        'readme_filename': 'README.txt',
                        'readme_contents': """
This is the pyhesiodfs FUSE autmounter.
{blank}
To access a Hesiod filsys, just access {mountpoint}/name.
{blank}
If you're using the Finder, try pressing Cmd+Shift+G and then
entering {mountpoint}/name""",
                        'syslog_unavail': 'true',
                        'syslog_unknown': 'true',
                        'syslog_success': 'false',
                        }

    def __init__(self):
        RawConfigParser.__init__(self, defaults=self.CONFIG_DEFAULTS)
        self.add_section('PyHesiodFS')
        if sys.platform in self.CONFIG_FILES:
            self.read(self.CONFIG_FILES[sys.platform])
        else:
            self.read(self.CONFIG_FILES['_DEFAULT'])

    def getboolean(self, section, option):
        try:
            return RawConfigParser.getboolean(self, section, option)
        except ValueError:
            rv = RawConfigParser.getboolean(self, 'DEFAULT', option)
            syslog(LOG_WARNING,
                   "Invalid boolean value for %s in config file; assuming %s" % (option, rv))
            return rv

class attachtab():
    """
    A dict-like class that stores both normal symlinks and locker
    mounts, and also "serializes" them into the attachtab file
    """
    def __init__(self, fusefs):
        self._mounts = defaultdict(dict)
        self.fusefs = fusefs

    def __getitem__(self, key):
        value = self._mounts[self.fusefs._uid()][key]
        return value.path

    def __setitem__(self, key, value):
        self._mounts[self.fusefs._uid()][key] = value

    def __contains__(self, item):
        return self._mounts[self.fusefs._uid()].__contains__(item)

    def __delitem__(self, key):
        del self._mounts[self.fusefs._uid()][key]

    def mounts(self):
        return self._mounts[self.fusefs._uid()].keys()

    def __str__(self):
        rv = []
        for k, v in self._mounts[self.fusefs._uid()].items():
            rv.append(v._serialize())
        return "\n".join(rv) + "\n"

class negcache(dict):
    """
    A set-like object that automatically expunges entries after
    they're been there for a certain amount of time.
    
    This only supports add, remove, and __contains__
    """
    
    def __init__(self, cache_time=0.5):
        self.cache_time = cache_time
    
    def add(self, obj):
        self[obj] = time.time()
    
    def remove(self, obj):
        try:
            del self[obj]
        except KeyError:
            pass
    
    def __contains__(self, k):
        if super(negcache, self).__contains__(k):
            if self[k] + self.cache_time > time.time():
                return True
            else:
                del self[k]
        return False

# Use the "new" API
fuse.fuse_python_api = (0, 2)

class MyStat(fuse.Stat):
    def __init__(self):
        self.st_mode = 0
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 0
        self.st_uid = 0
        self.st_gid = 0
        self.st_size = 0
        self.st_atime = 0
        self.st_mtime = 0
        self.st_ctime = 0

class FakeFiles(dict):
    """A dict-style object that holds pathnames which behave as fake
    read-only files, and their contents.  Constraints on the keys and
    values are enforced by raising ValueError or TypeError.
    """
    def __init__(self, path='/'):
        super(FakeFiles, self).__init__()
        self.path = path

    def __setitem__(self, k, v):
        if type(k) is not str:
            raise TypeError('Filenames must be strings')
        if type(v) is not str and not callable(v):
            raise TypeError('File contents must be strings or callable')
        f = k.strip()
        if f in ['.', '..', ''] or '/' in f:
            raise ValueError("Invalid filename: '%s'" % (k,))
        super(FakeFiles, self).__setitem__(self.path + f,v)

    def filenames(self):
        return [x[len(self.path):] for x in self]

    def __getitem__(self, k):
        v = super(FakeFiles, self).__getitem__(k)
        return v() if callable(v) else v

class PyHesiodFS(Fuse):

    def __init__(self, *args, **kwargs):
        Fuse.__init__(self, *args, **kwargs)
        
        openlog('pyhesiodfs', 0, LOG_DAEMON)
        
        try:
            self.fuse_args.add("allow_other", True)
        except AttributeError:
            self.allow_other = 1

        if sys.platform == 'darwin':
            self.fuse_args.add("noappledouble", True)
            self.fuse_args.add("noapplexattr", True)
            self.fuse_args.add("volname", "MIT")
            self.fuse_args.add("fsname", "pyHesiodFS")
        self.attachtab = attachtab(self)
        
        self.files = FakeFiles()

        self.syslog_unavail = True
        self.syslog_unknown = True
        self.syslog_success = False

        # Cache deletions for half a second - should give `ln -nsf`
        # enough time to make a new symlink
        self.negcache = defaultdict(negcache)
    
    def parse(self, *args, **kwargs):
        Fuse.parse(self, *args, **kwargs)
        self.mountpoint = self.fuse_args.mountpoint
        # Ensure that we know where we're mounted at this point
        assert self.mountpoint is not None

    def _initializeConfig(self, config):
        self.syslog_unavail = config.getboolean('PyHesiodFS', 'syslog_unavail')
        self.syslog_unknown = config.getboolean('PyHesiodFS', 'syslog_unknown')
        self.syslog_success = config.getboolean('PyHesiodFS', 'syslog_success')
        self.show_readme = config.getboolean('PyHesiodFS', 'show_readme')

        if self.show_readme:
            try:
                contents = config.get('PyHesiodFS', 'readme_contents') + "\n"
                self.files[config.get('PyHesiodFS', 'readme_filename')] = \
                    contents.format(mountpoint=self.mountpoint, blank='')
            except ValueError as e:
                syslog(LOG_WARNING,
                       "config file: bad value for 'readme_filename'")
            except KeyError as e:
                syslog(LOG_WARNING,
                       "config file: bad substitution key (%s) in 'readme_contents'" % (e.message,))

        self.files[ATTACHTAB_PATH] = self.attachtab.__str__

    def _uid(self):
        return fuse.FuseGetContext()['uid']
    
    def _gid(self):
        return fuse.FuseGetContext()['gid']
    
    def _pid(self):
        return fuse.FuseGetContext()['pid']
    
    def getattr(self, path):
        st = MyStat()
        if path == '/':
            st.st_mode = stat.S_IFDIR | 0755
            st.st_gid = self._gid()
            st.st_nlink = 2
        elif path in self.files:
            st.st_mode = stat.S_IFREG | 0444
            st.st_nlink = 1
            st.st_size = len(self.files[path])
        elif '/' not in path[1:]:
            if path[1:] not in self.negcache[self._uid()] and self.findLocker(path[1:]):
                st.st_mode = stat.S_IFLNK | 0777
                st.st_uid = self._uid()
                st.st_nlink = 1
                st.st_size = len(self.findLocker(path[1:]))
            else:
                return -errno.ENOENT
        else:
            return -errno.ENOENT
        return st

    def findLocker(self, name):
        """Lookup a locker in hesiod and return its path"""
        if name in self.attachtab:
            return self.attachtab[name]
        else:
            try:
                lockers = locker.lookup(name)
            except locker.LockerNotFoundError as e:
                if self.syslog_unknown:
                    syslog(LOG_NOTICE, str(e))
                return None
            except locker.LockerUnavailableError as e:
                if self.syslog_unavail:
                    syslog(LOG_NOTICE, str(e))
                return None
            except locker.LockerError as e:
                syslog(LOG_WARNING, str(e))
                return None
            # TODO: Check if the first locker is valid
            #       See Debathena Trac #583
            for l in lockers:
                if l.automountable():
                    self.attachtab[name] = l
                    if self.syslog_success:
                        syslog(LOG_INFO, "Mounting "+name+" on "+l.path)
                    return l.path
            syslog(LOG_WARNING, "Lookup succeeded for %s but no lockers could be attached." % (name))
        return None

    def getdir(self, path):
        return [(i, 0) for i in (['.', '..'] + self.files.filenames() + self.attachtab.mounts())]

    def readdir(self, path, offset):
        for (r, zero) in self.getdir(path):
            yield fuse.Direntry(r)
            
    def readlink(self, path):
        return self.findLocker(path[1:])

    def open(self, path, flags):
        if path not in self.files:
            return -errno.ENOENT
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES

    def read(self, path, size, offset):
        if path not in self.files:
            return -errno.ENOENT
        contents = self.files[path]
        slen = len(contents)
        if offset < slen:
            if offset + size > slen:
                size = slen - offset
            buf = contents[offset:offset+size]
        else:
            buf = ''
        return buf

    def symlink(self, src, path):
        if path == '/' or path in self.files:
            return -errno.EPERM
        elif '/' not in path[1:]:
            self.attachtab[path[1:]] = locker.fromSymlink(src,
                                                          path[1:],
                                                          self.mountpoint)
            self.negcache[self._uid()].remove(path[1:])
        else:
            return -errno.EPERM
    
    def unlink(self, path):
        if path == '/' or path in self.files:
            return -errno.EPERM
        elif '/' not in path[1:]:
            del self.attachtab[path[1:]]
            self.negcache[self._uid()].add(path[1:])
        else:
            return -errno.EPERM

def main():
    config = PyHesiodFSConfigParser()

    usage = Fuse.fusage
    server = PyHesiodFS(version="%prog " + fuse.__version__,
                        usage=usage,
                        dash_s_do='setsingle')
    server.parse(errex=1)

    server._initializeConfig(config)
    try:
        server.main()
    except fuse.FuseError as fe:
        print >>sys.stderr, "An error occurred while starting PyHesiodFS:"
        print >>sys.stderr, fe
        sys.exit(1)

if __name__ == '__main__':
    main()
