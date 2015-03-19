"""Module to collect different site crawling classes.  All classes derive from
the basic Crawler class, which implements general crwaling algorithms and
methods.  Subclasses only implement the site specific parsing methods."""


import logging
import queue
import threading
import urllib.request


import bs4


logger = logging.getLogger(__name__)


def notimplemented(*methods):
    """Add several methods to a class which all simply raise a
    NotImplementedError and tell the programmer to implement this method in a
    subclass.  Every method name is checked and if the class already has a
    method with this name, it is skipped.

    :cls: the class which should recive the methods
    :*methods: a list of method names (strings)
    :returns: the class with the methods added

    """
    def decorator(cls):
        def dummy(*args, **kwargs): raise NotImplementedError()
        for name in methods:
            if hasattr(cls, name):
                continue
            else:
                setattr(cls, name, dummy)
        return cls
    return decorator


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
    PRE_PARSER = bs4.BeautifulSoup
    RETRIES = 10
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
        raise NotImplementedError(
            "Crawler.start has to be implemented in a subclass.")

    def _crawler(self, url):
        """Crawl the site starting at the given url and yield the extracted
        data.  Return when the last page is reached.

        :url: the url where to start crawling the site
        :yields: triples of key, image urls and file names to download

        """
        raise NotImplementedError(
            "Crawler._crawler has to be implemented in a subclass.")

    def _parse(self, page):
        """Parse the loaded page and extract the needed data from it.  The data
        should be returned as a touple of a key, next urls(s), image url and
        file name.  The key is used to identify the download job of the image.
        The next url(s) object is used by the crawler to load further pages.
        The file name is where the image url should be saved to.  If no data
        was found in the page None is retuned instead.

        :page: the page loaded in the _crawler generator
        :returns: the extracted data or None

        """
        raise NotImplementedError(
            "Crawler._parse has to be implemented in a subclass.")

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
        return False

    def _set_manga_info(self, url, page=None):
        """Set some information about the current manga in this instance.  This
        info can be used by other methods in the class.  This implementation
        does nothing but it can be overwritten by subclasses which would like
        to save some information befor or after loading the initial page.

        :url: the url of the initial page
        :page: the initial page or None
        :returns: None

        """
        pass

    def _load_page(self, url):
        """Load the given url.  Handle the exceptions given in
        self.HANDLED_EXCEPTIONS and retry to load the page.

        :url: the url of the page to load
        :returns: the page or None if loading failed

        """
        for _ in range(self.RETRIES):
            try:
                page = urllib.request.urlopen(url)
                break
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
        return self.PRE_PARSER(page)


@notimplemented('_key', '_img', '_filename')
class ThreadedParser(Crawler):

    """A threaded parser has an internal queue onto which urls will be pushed.
    Several threads should be spanwned by the start method using the
    _parse_worker method to consume this internal queue.  The worker function
    will load the url and parse it and then put the result on the external
    queue for images."""

    PARSER_COUNT = 10

    def __init__(self, *args, **kwargs):
        """TODO: to be defined1. """
        """Initialize the internal page queue and call super().__init__."""
        super().__init__(*args, **kwargs)
        self._internal_queue = queue.Queue()
        self._internal_producer_finished = threading.Event()

    @staticmethod
    def _thread(function, arguments=()):
        """Start the given function with the arguments in a new thread.

        :function: the function object to execute in the new thread
        :arguments: the argument tupel for the function object
        :returns: None

        """
        t = threading.Thread(target=function, args=arguments)
        t.start()

    def _parse_worker(self):
        """Worker to download and parse pages from the internal page queue and
        push the resulting image urls and filenames onto the internal image
        queue.

        :returns: None

        """
        while True:
            try:
                # TODO set a reasonable timeout
                page_url = self._internal_queue.get(timeout=2)
            except queue.Empty:
                logger.debug('Could not get item from queue.')
                if self._internal_producer_finished.is_set():
                    self._done.set()
                    return
                else:
                    continue
            page = self._load_page(page_url)
            try:
                logger.debug('Parsing {} ...'.format(page_url))
                key, img_url, filename = self._parse(page)
            except AttributeError as e:
                logger.exception(
                    'Parsing {} returned {}.  Giving up.'.format(page_url, e))
                self._internal_queue.task_done()
            self._queue.put((key, img_url, filename))
            self._internal_queue.task_done()

    def _start_parsers(self):
        """Start all the parsing worker threads."""
        for _ in range(self.PARSER_COUNT):
            logger.debug('Starting parser thread ...')
            self._thread(self._parse_worker)

    def _parse(self, html):
        """This method returns a tupel of a key, the image url and the filename
        to downlowd to.  It is intended for use in the parser thread, where
        only this information needs to be extracted from a page.  A subclass
        should either implement the methods self._key(html), self._img(html)
        and self._filename(html) or overwrite this method.

        :html: the page as retuned by self._load_page(url)
        :returns: a triple of key, image url and filen name

        """
        key = self._key(html)
        img = self._img(html)
        filename = self._filename(html)
        return key, img, filename


@notimplemented('_next', '_img', '_manga', '_chapter', '_page', '_filename')
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
            logger.debug('Loading initial page ...')
            page = self._load_page(url)
            self._set_manga_info(url, page)
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

    def _parse(self, html):
        """This method returns a tupel of a key, the next url, the image url
        and the filename to downlowd to.  It should extract these information
        from the supplied html page inline.

        :html: the page as retuned by self._load_page(url)
        :returns: a quadrupel of key, next url, image url and filen name

        """
        # This is just a dummy implementation which could be overwritten.
        # The actual implementation can extract these information inline.
        key = self._key(html)
        next = self._next(html)
        img = self._img(html)
        filename = self._filename(html)
        return key, next, img, filename

    def _key(self, html):
        """Format a key for the given page from the chapter and page number.

        :html: a parsed page where the image data can be found
        :retruns: a key to identify the job to load from the given page

        """
        return '{}-{}'.format(self._chapter(html), self._page(html))


@notimplemented('_next', '_key', '_img', '_filename')
class LinearChapterDirectPageCrawler(ThreadedParser):

    """A linear chapter crawler will load a page for every chapter
    sequentially.  From this chapter entry point it will be possible to
    directly find the next chapter url (linear chapter crawling) and also all
    the urls of the pages for this chapter (direct page crawler).  The crwaler
    will crawl the chapters sequentially and put all pages to be parsed on an
    internal queue.  Some worker threads can then process the pages and put the
    image links on the dedicated queue.

    self._next(page)
    self._key(html)
    self._img(html)
    self._filename(html)

    """

    def start(self, url, after=False):
        """Crawl the site starting at url (or just after url if after=True)
        and queue all image urls with their filenames to be download in
        another thread.

        :url: a string, the url where to start
        :after: a bool, if true images will be loaded only after the start url
        :returns: None

        """
        logger.debug('Loading initial page ...')
        page = self._load_page(url)
        self._set_manga_info(url, page)
        next_chapter = self._next(page)
        logger.debug('The next chapter is at {}.'.format(next_chapter))
        if not after:
            try:
                key, img, filename = self._parse(page)
            except AttributeError:
                self._done.set()
                return
            self._queue.put((key, img, filename))
        for page_url in self._slice_first_chapter(url, page):
            self._internal_queue.put(page_url)
        self._start_parsers()
        for page_url in self._crawler(next_chapter):
            self._internal_queue.put(page_url)

    def _crawler(self, url):
        """Crawl all chapters in order and extract the page urls from each
        chapter entry point.  Put the image information og the cahpter entry
        point on the image queue and yield the other page urls.

        :url: url to the chapter entry page
        :yields: the page urls from all chapters in order

        """
        while True:
            # First load the chapter entry point (normally the first page of
            # the chapter.
            logger.debug('Loading page {}.'.format(url))
            html = self._load_page(url)
            # When the page is already loaded extract the final image data
            # directly.
            try:
                key, img, filename = self._parse(html)
            except (AttributeError, TypeError):
                logger.info('{} seems to be the last chapter.'.format(url))
                self._internal_producer_finished.set()
                return
            self._queue.put((key, img, filename))
            # Extract the urls of all the pages in this chapter.
            for page_url in self._pages(html):
                yield page_url
            # Try to find the url of the next chapter.
            try:
                url = self._next(html)
            except AttributeError:
                logger.info('{} seems to be the last chapter.'.format(url))
                self._internal_producer_finished.set()
                return

    def _slice_first_chapter(self, url, html):
        """Slice the pages list of the first chapter and yield all page urls
        after the given initial url.

        :url: the initial url after which all other urls should be used
        :html: the html of the chapter entry page
        :yields: all page urls from the first chapter which should still be
            loaded

        """
        raise NotImplementedError()


class DirectPageCrawler(ThreadedParser):

    """A direct page crawler will load one page first and find the urls for all
    other pages to load from that page.  The initial page can be the url
    supplied by the user or a site specific meta page.  The urls of all the
    pages are put on a queue and parsed in parallel by several workers.

    This is a generic class that implements the general crawling logic.  Site
    specific parsing methods have to be implemented by subclasses.  These are:
        self._parse_meta_page(page)
        self._img(html)
        self._manga(html)
        self._chapter(html)
        self._page(html)
    """

    METAPAGE = None

    def start(self, url, after=False):
        """Crawl the site starting at url (or just after url if after=True)
        and queue all image urls with their filenames to be download in
        another thread.

        :url: a string, the url where to start
        :after: a bool, if true images will be loaded only after the start url
        :returns: None

        """
        self._set_manga_info(url)
        for page_url in self._find_pages(url, after):
            self._page_queue.put(page_url)
        for _ in range(self.PARSER_COUNT):
            self._thread(self._parse_worker)

    def _find_pages(self, url, after):
        """Return the urls for all pages to load.

        :url: the initial url
        :after: bool wheather the image of the initial url should also be
            loaded
        :returns: an iterable of all the urls of the pages where the image
            links can be found

        """
        page = self._load_page(self.METAPAGE or url)
        return self._parse_meta_page(page, url, after)

    def _parse_meta_page(self, page, url, after):
        """Parse the meta page for this site to find all the page links where
        image links can be found.  Return an itarable of all the page urls.

        :page: the meta page to parse
        :url: the initial url
        :after: wheather the initial page should be included in the result
        :returns: an itarable of urls

        """
        raise NotImplementedError()
