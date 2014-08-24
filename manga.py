#!/usr/bin/env python3

# imports
import datetime
import inspect
import logging
import os
import re
import signal
import sys
# see file:///Users/luc/tmp/python-3.4.1-docs-html/library/concurrency.html
import threading
import queue
import traceback
import urllib.request

from bs4 import BeautifulSoup

# constants
MAIOR_VERSION = 0
MINOR_VERSION = 2
PROG = os.path.basename(sys.argv[0])
VERSION_STRING = PROG + ' ' + str(MAIOR_VERSION) + '.' + str(MINOR_VERSION)
BASE = logging.INFO
DECREMENT = 1
logging.USER = BASE - DECREMENT

# variables
quiet = True
debug = False
global_mangadir = os.path.realpath(os.getenv("MANGADIR") or
        os.path.join(os.getenv("HOME"), "comic"))
logging_levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'VERBOSE': logging.INFO,
        'WARNING': logging.WARNING,
        'NORMAL': logging.WARNING,
        'QUIET': logging.ERROR,
        }


def timestring():
    return datetime.datetime.now().strftime('%H:%M:%S')


def check_url(string):
    '''Check if the given string can be used as an url.  Return the string
    unchanged, if so.'''
    url = urllib.parse.urlparse(string)
    if url.netloc is None or url.netloc == '':
        raise BaseException('This url is no good.')
    return string


def find_class_from_url(url):
    '''
    Parse the given url and try to find a class that can load from that
    domain.  Return the class.
    '''
    for cls in Crawler.__subclasses__():
        if cls.can_load(url):
            return cls
    raise NotImplementedError(
            'There is no class available to work with this url.')


def download_missing(directory, logfile):
    '''
    Load all images which are mentioned in the logfile but not present in the
    directory.
    '''
    logfile = open(logfile, 'r')
    for index, line in enumerate(logfile.readlines()):
        url, img, filename = line.split(' ', 2)
        if not os.path.exists(filename):
            start_thread(download_image, (index, img, filename, logger))


class LoggingFilter():

    '''A filter to select only the logging messages of a predefined
    severity.'''

    def __init__(self, base=BASE, decrement=DECREMENT):
        '''Set up the filter with a base severity and a decrement (positive
        integer).'''
        self._base = base
        self._decrement = decrement


    def filter(self, record):
        '''Filter the record.  Only returnes True for records of
        self._base-self._decrement.'''
        return self._base - self._decrement == record.level



class Loader():

    '''The manager to organize the threads that will download the pages to
    find the image urls and that will download the actual images.'''

    def __init__(self, directory, logfile, url, queue_size=10, threads=5):
        """@todo: to be defined1.

        :directory: @todo
        :logfile: @todo
        :url: @todo

        """
        self._directory = directory
        self._logfile = logfile
        self._url = url
        self._queue = queue.Queue(queue_size)
        self._producer_finished = threading.Event()
        self._threads = threads
        #filelogger = logging.FileHandler(os.path.join(directory, logfile))
        #filelogger.setLevel(logging.USER)
        #formatter = logging.Formatter('%(url)s %(img)s %(file)s')
        #filelogger.setFormatter(formatter)
        #filelogger.addFilter(LoggingFilter())
        #logging.getLogger('').addHandler(filelogger)
        cls = find_class_from_url(url)
        self._worker = cls(self._queue, self._producer_finished)


    def _download(self, url, filename):
        '''Download the url to the given filename.'''
        try:
            logging.debug('Starting to load {} to {}.'.format(url, filename))
            urllib.request.urlretrieve(url, os.path.join(self._directory,
                    filename))
        except urllib.error.ContentTooShortError:
            os.remove(filename)
            logging.exception('Could not download %s to %s.', url, filename)
        #logging.log(logging.USER, '',
        #        extra={'url':None, 'img':url, 'file':filename})


    @staticmethod
    def _thread(function, arguments=tuple()):
        '''Start the given function with the arguments in a new thread.'''
        t = threading.Thread(target=function, args=arguments)
        logging.debug('Created thread {}.'.format(t.name))
        t.start()
        #threads.append(t)


    def _load_images(self):
        """Repeatedly get urls and filenames from the queue and load them."""
        while True:
            try:
                key, url, filename = self._queue.get(timeout=2)
            except queue.Empty:
                logging.debug('Could not get item from queue.')
                if self._producer_finished.is_set():
                    return
            else:
                self._download(url, filename)
                self._queue.task_done()


    def start(self, url, after=False):
        #'''Load all images starting at a specific url.  If after is True start
        #loading images just after the given url.'''
        self._thread(self._worker.start, (url, after))
        for i in range(self._threads):
            logging.debug('Starting image loader thread {}.'.format(i))
            self._thread(self._load_images)



class Crawler():

    # References to be implement in subclasses.
    PROTOCOL = None
    DOMAIN = None
    def _next(html): raise NotImplementedError()
    def _img(html): raise NotImplementedError()
    def _manga(html): raise NotImplementedError()
    def _chapter(html): raise NotImplementedError()
    def _page(html): raise NotImplementedError()


    def __init__(self, queue, end_event):
        #logging.debug('', stack_info=True)
        self._queue = queue
        self._done = end_event


    @classmethod
    def _key(cls, html):
        return str(cls._chapter(html)) + '-' + str(cls._page(html))


    @classmethod
    def _filename(cls, html):
        return ('_'.join(cls._manga(html).split()) + '-' +
                str(cls._chapter(html)) + '-' +
                str(cls._page(html)) + '.' +
                os.path.splitext(cls._img(html))[1]).lower()


    @classmethod
    def _parse(cls, html):
        '''
        This method returns a tupel of a key, the next url, the image url and
        the filename to downlowd to.  It should extract these information from
        the supplied html page inline.
        '''
        # This is just a dummy implementation which could be overwritten.
        # The actual implementation can extract these information inline.
        key = cls._key(html)
        next = cls._next(html)
        img = cls._img(html)
        filename = cls._filename(html)
        return key, next, img, filename


    def _crawler(self, url):
        '''A generator to crawl the site.'''
        while True:
            try:
                logging.debug('Starting to load {}.'.format(url))
                request = urllib.request.urlopen(url)
                logging.debug('Finished loading {}.'.format(url))
            except (urllib.request.http.client.BadStatusLine,
                    urllib.error.HTTPError,
                    urllib.error.URLError) as e:
                logging.exception('%s returned %s', url, e)
                self._done.set()
                return
            html = BeautifulSoup(request)
            try:
                key, url, img, filename = self.__class__._parse(html)
            except AttributeError:
                logging.info('{} seems to be the last page.'.format(url))
                self._done.set()
                return
            yield key, img, filename


    @classmethod
    def expand(cls, url):
        '''Expand the given string into a valid URL.  The string is assumed to
        be relative to the site handled by the class cls.'''
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
        '''Return True if this class can load from the given url, False
        otherwise.'''
        if type(url) is not urllib.parse.ParseResult:
            url = urllib.parse.urlparse(url)
        if url.netloc.split('.')[-2:] == cls.DOMAIN.split('.')[-2:]:
            logging.debug('Found correct subclass: {}'.format(cls))
            return True
        return False


    def start(self, url, after=False):
        '''Crawl the site starting at url (or just after url if after=True)
        and queue all image urls with their filenames to be download in
        another thread.'''
        if after:
            try:
                request = urllib.request.urlopen(url)
            except urllib.error.URLError as e:
                logging.exception('%s returned %s', url, e)
                return
            html = BeautifulSoup(request)
            url = self.__class__._next(html)
            logging.debug('Finished preloading.')
        for key, img, filename in self._crawler(url):
            logging.debug(
                    'Queueing image with key {} for downloading.'.format(key))
            self._queue.put((key, img, filename))



class Mangareader(Crawler):

    PROTOCOL = 'http'
    DOMAIN = 'www.mangareader.net'


    @classmethod
    def _next(cls, html):
        return cls.expand(html.find(id='img').parent['href'])


    @classmethod
    def _img(cls, html):
        return html.find(id='img')['src']


    @classmethod
    def _filename(cls, html):
        return re.sub(r'[ -]+', '-', html.find(id="img")["alt"]).lower() + \
                '.' + cls._img(html).split('.')[-1]


    @classmethod
    def _chapter(cls, html):
        return int(html.find(id='mangainfo').h1.string.split()[-1])


    @classmethod
    def _page(cls, html):
        return int(html.find(id='mangainfo').span.string.split()[1])


    @classmethod
    def _manga(cls, html):
        return re.sub(r'(.*) [0-9]+$', r'\1',
                html.find(id='mangainfo').h1.string)



class Unixmanga(Crawler):

    # class constants
    PROTOCOL = 'http'
    DOMAIN = 'unixmanga.com'

    def _next(html):
        s = html.find_all(class_='navnext')[0].script.string.split('\n')[1]
        return re.sub(r'var nextlink = "(.*)";', r'\1', s)



class Mangafox(Crawler):

    DOMAIN='mangafox.me'
    PROTOCOL='http'

    def _next(html):
        tmp = html.find(id='viewer').a['href']
        if tmp == "javascript:void(0);":
            return html.find(id='chnav').p.a['href']
        else:
            url = PROTOCOL + '://' + DOMAIN + '/manga/'
            l = str(html.body.find_all('script')[-2]).split('\n')
            # manga name
            url = url + l[3].split('"')[1]
            # volume and chapter and page (in tmp)
            url = url + l[6].split('"')[1] + tmp
            return url


    def _key(html): raise NotImplementedError()


    def _img(html):
        return html.find(id='image')['src']


    def _filename(html):
        keys = _key_helper(html)
        return keys[0] + ' ' + str(keys[2]) + ' page ' + str(keys[3]) + \
                _img(html).split('.')[-1]


    def _chapter(html):
        return _key_helper()[2]


    def _page(html):
        return _key_helper()[3]


    def _key_helper(html):
        for tmp in html.findAll('link'):
            if tmp.has_key['rel'] and tmp['rel'] == 'canonical':
                val = tmp['href'].split('/')
                break
        if re.march(r'^[0-9]+\.html$', val[-1]) != None:
            page = int(val[-1].split('.')[0])
        else:
            raise BaseException('wrong string while parsing')
        if re.match(r'^c[0-9]+$', val[-2]) != None:
            chapter = int(val[-2][1:])
        else:
            raise BaseException('wrong string while parsing')
        if re.match(r'^v[0-9]+$', val[-3]) != None:
            volume = int(val[-3][1:])
            i = -4
        else:
            volume = None
            i = -3
        manga = val[i]
        return (manga, volume, chapter, page)



if __name__ == '__main__':

    def main():
        '''Parse the command line, check the resulting namespace, prepare the
        environment and load the images.'''
        import argparse
        parser = argparse.ArgumentParser(prog=PROG,
                description="Download manga from some websites.")
        # output group
        output = parser.add_argument_group(title='Output options')
        output.add_argument('-l', '--loglevel',
                type=lambda x: logging_levels[x],
                default=logging_levels['NORMAL'],
                choices=logging_levels.keys(),
                help='specify the logging level')
        output.add_argument('-x', '--debug', dest='loglevel',
                action='store_const', const=logging.DEBUG,
                help='debuging output')
        output.add_argument('-v', '--verbose', dest='loglevel',
                action='store_const',
                const=logging.INFO, help='verbose output')
        output.add_argument('-q', '--quiet', dest='loglevel',
                action='store_const',
                const=logging.CRITICAL, help='supress output')
        # general group
        general = parser.add_argument_group(title='General options')
        general.add_argument('-b', '--background', action='store_true',
                help='fork to background')
        # can we hand a function to the parser to check the directory?
        general.add_argument('-d', '--directory', metavar='DIR', default='.',
                help='the directory to work in')
        general.add_argument('-f', '--logfile', metavar='LOG',
                default='manga.log',
                help='the filename of the logfile to use')
        general.add_argument('-m', '--load-missing', action='store_true',
                dest='missing',
                help='Load all files which are stated in the logfile but ' +
                'are missing on disk.')
        # unimplemented group
        unimplemented = parser.add_argument_group(
                'These are not yet implemented')
        # the idea for 'auto' was to find the manga name and the directory
        # automatically.
        unimplemented.add_argument('-a', '--auto', action='store_true',
                default=True, help='do everything automatically')
        # or use the logfile from within for downloading.
        ## idea for "archive": tar --wildcards -xOf "$OPTARG" "*/$LOGFILE"
        unimplemented.add_argument('-A', '--archive',
                help='display the logfile from within an archive')
        unimplemented.add_argument('--view', help='create a html page')
        unimplemented.add_argument('-r', '--resume', action='store_true',
                help='resume from a logfile')
        unimplemented.add_argument('-R', '--resume-all', action='store_true',
                help='visit all directorys in the manga dir and resume there')
        #general group
        parser.add_argument('-V', '--version', action='version',
                version=VERSION_STRING, help='print version information')
        parser.add_argument('name', nargs='?', metavar='url/name',
                type=check_url)
        args = parser.parse_args()
        if args.resume and (args.name is not None or args.missing):
            parser.error('You can only use -r or -m or give an url.')
        elif not args.resume and args.name is None and not args.missing:
            parser.error('You must specify -r or -m or an url.')

        # configure the logger
        logging.basicConfig(
                format='%(levelname)s[%(threadName)s] %(asctime)s: %(msg)s',
                level=args.loglevel
                )
        logging.debug(
                'The parsed command line arguments are {}.'.format(args))

        # set up the directory
        directory = args.directory
        # TODO can the directory be retrieved from the manga name?
        mangadir = os.path.curdir
        if not directory == os.path.curdir and not os.path.sep in directory:
            mangadir = global_mangadir
            directory = os.path.realpath(os.path.join(mangadir, directory))
        if os.path.isdir(directory):
            pass
        else:
            try:
                os.mkdir(directory)
            except FileExistsError:
                parser.error('Path exists but is not a directory.')
        logging.debug('Directory set to "{}".'.format(directory))

        # start downloading
        if args.resume_all:
            resume_all()
        elif args.resume:
            resume(directory, args.logfile)
        elif args.missing:
            download_missing(directory, args.logfile)
        else:
            Loader(directory, args.logfile, args.name).start(args.name)
        join_threads()
        logging.debug('Exiting ...')
        sys.exit()


    def resume(directory, logfile):
        log = open(logfile, 'r')
        line = log.readlines()[-1]
        log.close()
        url = line.split()[0]
        logging.debug('Found url for resumeing: %s', url)
        cls = find_class_from_url(url)
        worker = cls(directory, logfile)
        worker.start_after(url)


    def resume_all():
        for dd in os.path.listdir(global_mangadir):
            for d in os.path.join(global_mangadir, dd):
                os.chdir(d)
                logging.info('Working in {}.'.format(os.path.realpath(
                        os.path.curdir)))
                resume(os.path.join(global_mangadir, d), 'manga.log')


    def join_threads():
        try:
            current = threading.current_thread()
            for thread in threading.enumerate():
                if thread != current:
                    thread.join()
            logging.debug('All threads joined.')
        except:
            logging.info('Could not get current thread. %s',
                    'Not waiting for other threads.')


    def interrupt_cleanup():
        """Stop all threads and write the logfile before exiting.  This
        function should be called when an interrupt signal is called."""
        pass


    main()
