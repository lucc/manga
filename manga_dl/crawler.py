"""Module to collect different site crawling classes.  All classes derive from
the basic Crawler class, which implements general crwaling algorithms and
methods.  Subclasses only implement the site specific parsing methods."""


import logging
import urllib.request


from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)
RETRIES = 10


class Crawler():

    """Generic crawler to crawl a site and extract all image links from it.
    Normally a starting url is given and all subsequant pages are loaded and
    parsed.  The urls of the images and destination filenames are pushed onto a
    queue for further processing (possibly in another thread).
    """

    # References to be implement in subclasses.
    PROTOCOL = ''
    DOMAIN = ''
    HANDLED_EXCEPTIONS = ()
    # (urllib.request.http.client.BadStatusLine, urllib.error.HTTPError,
    # urllib.error.URLError)

    def __init__(self, queue, end_event):
        """Initialize the crawler with the given queue and the end_event.  The
        queue will be filled with the image urls and filenames when the start()
        method of this object is run.  The end_event will be set as soon as the
        last page has been parsed.

        :queue: a queue.Queue object
        :end_event: a threading.Event object

        """
        self._queue = queue
        self._done = end_event

    @classmethod
    def expand(cls, url):
        """Expand the given string into a valid URL.  The string is assumed to
        be relative to the site handled by the class cls.

        :url: a url (a string), possibly relative to the site of this class
        :returns: an absolute url pointing to the same resouce

        """
        if '://' in url:
            return url
        elif '//' == url[0:2]:
            return cls.PROTOCOL + ':' + url
        elif '/' == url[0]:
            return cls.PROTOCOL + '://' + cls.DOMAIN + url
        else:
            return cls.PROTOCOL + '://' + cls.DOMAIN + '/' + url

    @classmethod
    def can_load(cls, url):
        """Return True if this class can load from the given url, False
        otherwise.

        :url: a url to test (a string)
        :returns: True or False

        """
        if type(url) is not urllib.parse.ParseResult:
            url = urllib.parse.urlparse(url)
        if url.netloc.split('.')[-2:] == cls.DOMAIN.split('.')[-2:]:
            logger.debug('Found correct subclass: {}'.format(cls))
            return True
        return False

    @classmethod
    def find_subclass(cls, url):
        """Find a (sub) class that can crawl the given url.  Return the class if
        it can and None if no class was found.

        :url: the url that has to be crawled
        :returns: a Crawler subclass or None

        """
        if cls.can_load(url):
            return cls
        for subcls in cls.__subclasses__():
            cls2 = subcls.find_subclass(url)
            if cls2 is not None:
                return cls2
        return None

    def start(self, url, after=False):
        """Start the crawling of the site and push the data found on the
        internal queue.  This is the public entry point for the crawling logic.
        The given url is the position where to start crawling.  The sites
        loaded will then be parsed and the image urls and file names will be
        pushed on the internal job queue for consumtion by a download worker.
        If the optional argument after is True, only the pages after the given
        url will be used to push jobs on the queue.

        :url: a string, the url where to start
        :after: a bool, if true images will be loaded only after the start url
        :returns: None

        """
        raise NotImplementedError()

    def _crawler(self, url):
        """Crawl the site starting at the given url and yield the extracted
        data.  Return when the last page is reached.

        :url: the url where to start crawling the site
        :yields: triples of key, image urls and file names to download

        """
        raise NotImplementedError()

    def _ignore_exception(self, exception):
        """Check an exception that was returned when loading a page in the
        crawler generator.  The exception argument is the exception and is an
        instance of one of the exception classes given in
        self.HANDLED_EXCEPTIONS.  This method should return True if the
        exeption can be ignored and the page should be loaded again, False if
        the error is fatal and loading should be stopped.

        :exeption: an exeption object of one of the types in
            self.HANDLED_EXCEPTIONS
        :returns: True or False

        """
        raise NotImplementedError()

    @classmethod
    def _parse(cls, page):
        """Parse the loaded page and extract the needed data from it.  The data
        should be returned as a touple of a key, next urls(s), image url and
        file name.  The key is used to identify the download job of the image.
        The next url(s) object is used by the crawler to load further pages.
        The file name is where the image url should be saved to.  If no data
        was found in the page None is retuned instead.

        :page: the page loaded in the _crawler generator
        :returns: the extracted data or None

        """
        raise NotImplementedError()

    def _load_page(self, url):
        """Load the given url.  Handle the exceptions given in
        self.HANDLED_EXCEPTIONS and retry to load the page.

        :url: the url of the page to load
        :returns: the page or None if loading failed

        """
        for _ in range(RETRIES):
            try:
                return urllib.request.urlopen(url)
            except self.HANDLED_EXCEPTIONS as e:
                if self._ignore_exception(e):
                    logger.warning(
                        '{} returned {}, retrying ...'.format(url, e))
                    continue
                else:
                    logger.warning(
                        '{} returned {}.  Giving up.'.format(url, e))
                    return
                logger.exception('%s returned %s', url, e)
                return
        else:
            logger.warning(
                'Retry count for {} exceeded.  Giving up.'.format(url))
            return


class LinearPageCrawler(Crawler):

    """A linear crawler that will load the pages sequentially in order to find
    the image download links and filenames.

    This is a generic class that implements the general crawling logic.  Site
     specific parsing methods have to be implemented by subclasses.  These are:
         cls._next(html)
         cls._img(html)
         cls._manga(html)
         cls._chapter(html)
         cls._page(html)
    """

    def start(self, url, after=False):
        """Crawl the site starting at url (or just after url if after=True)
        and queue all image urls with their filenames to be download in
        another thread.

        :url: a string, the url where to start
        :after: a bool, if true images will be loaded only after the start url
        :returns: None

        """
        if after:
            page = self._load_page(url)
            try:
                _, url, _, _ = self._parse(page)
            except AttributeError:
                self._done.set()
                return
        for key, img, filename in self._crawler(url):
            logger.debug('Queueing job {}.'.format(key))
            self._queue.put((key, img, filename))

    def _crawler(self, url):
        """A generic generator to crawl the site.

        This generator catches many exceptions.  Subclasses might impose a more
        find grained logic and might want to overwrite this method.

        :url: the url where to start crawling the site
        :yields: triples of key, image urls and file names to download

        """
        while True:
            logger.debug('Loading page {}.'.format(url))
            page = self._load_page(url)
            try:
                key, url, img, filename = self._parse(page)
            except AttributeError:
                logger.info('{} seems to be the last page.'.format(url))
                self._done.set()
                return
            yield key, img, filename

    @classmethod
    def _parse(cls, page):
        """This method returns a tupel of a key, the next url, the image url and
        the filename to downlowd to.  It should extract these information from
        the supplied html page inline.
        """
        # This is just a dummy implementation which could be overwritten.
        # The actual implementation can extract these information inline.
        html = BeautifulSoup(page)
        key = cls._key(html)
        next = cls._next(html)
        img = cls._img(html)
        filename = cls._filename(html)
        return key, next, img, filename
