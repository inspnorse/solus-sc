#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
#  This file is part of solus-sc
#
#  Copyright © 2017 Ikey Doherty <ikey@solus-project.com>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 2 of the License, or
#  (at your option) any later version.
#


import Queue
import multiprocessing
import threading
from gi.repository import GObject, GLib
import os
import hashlib


class ScMediaFetcher(GObject.Object):
    """ The ScMediaFetcher runs a low priority backround queue for handling
        media requests, such as screenshots.
        This allows for background fetching of screenshots and handles all
        the blocking, etc.

        We'll limit to a maximum of 2 threads, and we'll very likely only
        ever use one anyway. This allows us to switch between views with
        minimal transition pain. For single core systems we limit to 1 thread
        and avoid context issues.
    """

    queue = None
    cache_lock = None
    cache = None

    # Emit media-fetched URL local-URL
    __gsignals__ = {
        'media-fetched': (GObject.SIGNAL_RUN_FIRST, None,
                          (str, str))
    }

    __gtype_name__ = "ScMediaFetcher"

    def __init__(self):
        GObject.Object.__init__(self)
        cpuCount = multiprocessing.cpu_count()
        if cpuCount < 2:
            threadCount = 1
        else:
            threadCount = 2
        print("{} CPUs detected, restricting to {} threads".format(
            cpuCount, threadCount))

        # Ensure we have a cache directory before we start
        cacheDir = self.get_cache_dir()
        try:
            if not os.path.exists(cacheDir):
                os.makedirs(cacheDir, 00755)
        except Exception as ex:
            print("Check home directory permissions for {}: {}".format(
                cacheDir, ex))
            pass

        # Set up the basics
        self.cache = dict()
        self.cache_lock = threading.Lock()
        self.queue = Queue.LifoQueue(0)

        # We'll happily let the threads die if required
        for i in range(threadCount):
            t = threading.Thread(target=self.begin_fetch)
            t.daemon = True
            t.start()

    def get_cache_dir(self):
        """ Return the Solus SC cache directory """
        home = os.path.expanduser("~")
        return os.path.join(home, ".cache", "solus-sc", "media")

    def get_cache_filename(self, url):
        """ Return the unique local filename part for a URL """
        f, ext = os.path.splitext(url)
        h = hashlib.sha256(f).hexdigest()
        return "{}.{}".format(h, ext[1:])

    def get_cache_filename_full(self, url):
        """ Return fully qualified local path for the URL """
        return os.path.join(self.get_cache_dir(), self.get_cache_filename(url))

    def is_media_pending(self, uri):
        """ Determine if the media is pending before asking for
            it to be fetched
        """
        with self.cache_lock:
            if uri in self.cache:
                return True
        return False

    def begin_fetch(self):
        """ Main thread body function, will effectively run forever
            based on lock conditions
        """
        while True:
            # Grab the next job and wipe from the cache
            uri = self.queue.get()
            with self.cache_lock:
                del self.cache[uri]

            # TODO: Actually fetch it.
            print("Fetching %s" % uri)
            local_file = self.get_cache_filename_full(uri)
            self.queue.task_done()

            # Let clients know the media is now ready
            GLib.idle_add(lambda: self.emit(
                'media-fetched', uri, local_file),
                priority=GLib.PRIORITY_LOW)

    def fetch_media(self, uri):
        """ Request background fetch of the given media """
        if self.is_media_pending(uri):
            return
        with self.cache_lock:
            self.cache[uri] = True
        self.queue.put(uri)
