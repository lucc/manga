"""Module for the Loader class."""


import queue
import threading
import os
import urllib
import logging


from .crawler import Crawler


logger = logging.getLogger(__name__)


class Loader():

    """The manager to organize the threads that will download the pages to
    find the image urls and that will download the actual images."""

    def __init__(self, directory, logfile, url, queue_size=10, threads=5):
        """Initialize the loader class with a directory to save the images to
        and an url from which to load.

        :directory: the directory to save the image files, a string
        :logfile: currently unused (TODO)
        :url: url to decide which crawler to use, a string
        :queue_size: size of the queue for image downloading, an int
        :threads: number of threads to spawn for image downloading, an int

        """
        self._directory = directory
        self._logfile = logfile
        self._url = url
        self._queue = queue.Queue(queue_size)
        self._producer_finished = threading.Event()
        self._threads = threads
        # filelogger = logging.FileHandler(os.path.join(directory, logfile))
        # filelogger.setLevel(logging.USER)
        # formatter = logging.Formatter('%(url)s %(img)s %(file)s')
        # filelogger.setFormatter(formatter)
        # filelogger.addFilter(LoggingFilter())
        # logging.getLogger('').addHandler(filelogger)
        cls = Crawler.find_subclass(url)
        self._worker = cls(self._queue, self._producer_finished)

    def _download(self, url, filename):
        """Download the url to the given filename.

        :url: an image url, a string
        :filename: the filename where to save the image, a string
        :returns: None

        """
        try:
            urllib.request.urlretrieve(url, os.path.join(self._directory,
                                                         filename))
        except urllib.error.ContentTooShortError:
            os.remove(filename)
            logger.exception('Could not download %s to %s.', url, filename)
        else:
            logger.info('Done: {} -> {}'.format(url, filename))
            # TODO write info to logfile

    @staticmethod
    def _thread(function, arguments=()):
        """Start the given function with the arguments in a new thread.

        :function: the function object to execute in the new thread
        :arguments: the argument tupel for the function object
        :returns: None

        """
        t = threading.Thread(target=function, args=arguments)
        t.start()

    def _load_images(self):
        """Repeatedly get urls and filenames from the queue and load them.

        :returns: None

        """
        while True:
            try:
                # TODO set a reasonable timeout
                key, url, filename = self._queue.get(timeout=2)
            except queue.Empty:
                logger.debug('Could not get item from queue.')
                if self._producer_finished.is_set():
                    return
            else:
                self._download(url, filename)
                self._queue.task_done()

    def start(self, url, after=False):
        """Start the crawler and the image loading function each in a
        seperate thread.  Set the crawler up to start at (or just after, if
        after=True) the given url.

        :url: the url, where to start loading, passed to crawler.Crawler.start
        :after: a boolean switch, passed to crawler.Crawler.start
        :returns: None

        """
        logger.debug('Starting crawler and {} image loader threads.'.format(
            self._threads))
        self._thread(self._worker.start, (url, after))
        for i in range(self._threads):
            self._thread(self._load_images)
