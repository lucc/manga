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
    for cls in SiteHandler.__subclasses__():
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
    logger = BaseLogger('/dev/null', quiet)
    for index, line in enumerate(logfile.readlines()):
        url, img, filename = line.split(' ', 2)
        if not os.path.exists(filename):
            start_thread(download_image, (index, img, filename, logger))


class BaseLogger():

    def __init__(self, logfile, quiet=False):
        self.log = dict()
        self.logfile = open(logfile, 'a')
        self.quiet = quiet

    def __del__(self):
        self.cleanup()

    def add(self, key, url, img, filename):
        self.log[key] = (url, img, filename)
        self.logfile.write(' '.join(self.log[key]) + '\n')
        if not self.quiet:
            logging.info(PROG + ': ' + timestring() + ' downloading ' + img +
                    ' -> ' + filename)

    def remove(self, key):
        del self.log[key]

    def cleanup(self):
        self.logfile.close()
        for item in self.log:
            os.remove(item[2])


class Logger(BaseLogger):

    # Some constants to indicate errors and success
    ERROR = 1
    FAIL = 2
    SUCCESS = 3

    #def __init__(self, logfile, quiet=False):
    #    logfile = open(logfile, 'r')
    #    self.log = [line.split(' ', 2) for line in logfile.readlines()]
    #    logfile.close()
    #    for item in self.log:
    #        if os.path.exists(item[2]):
    #            item.append(True)
    #        else:
    #            item.append(False)
    #            _thread.start_new_thread(
    #                    download_image, (item[1], item[2], self))

    def __del__(self):
        self.write_logfile()
        self.super().__del__()
        # Do I need to del these manually?
        #del self.logfile
        #del self.log
        #del self.quiet

    def add(self, chap, count, nr=None, url=None, img=None, filename=None):
        if nr is None and url is None and img is None and filename is None:
            if chap in self.log:
                if count != self.log[chap][0]:
                    raise BaseException(
                            'Adding chapter twice with different length!')
                else:
                    # It is ok to add the chapter agoin with the same length.
                    return
            else:
                self.log[chap] = [count for i in range(count+1)]
        elif nr is None or url is None or img is None or filename is None:
            raise BaseException('Missing parameter!')
        elif chap in self.log:
            if self.log[chap][0] != count:
                raise BaseException('Inconsistend parameter!')
            elif self.log[chap][nr] != count and self.log[chap][nr][0:3] != \
                    [url, img, filename]:
                raise BaseException('Adding item twice.')
            else:
                self.log[chap][nr] = [url, img, filename, None]
        else:
            self.log[chap] = [count for i in range(count+1)]
            self.log[chap][nr] = [url, img, filename, None]
        if not self.quiet:
            logging.info(PROG + ': ' + timestring() + ' downloading ' + img +
                    ' -> ' + filename)

    def success(self, chap, nr):
        if chap not in self.log:
            raise BaseException('This key was not present:', chap)
        self.log[chap][nr][3] = True
        ## By now we only remove the item maybe we will do more in the future.
        #for item in self.log:
        #    if item[2] == filename:
        #        self.log.remove(item)
        #        return

    def failed(self, chap, nr):
        if chap not in self.log:
            raise BaseException('This key was not present:', chap)
        self.log[chap][nr][3] = False
        ## By now we only remove the item maybe we will do more in the future.
        #for item in self.log:
        #    if item[2] == filename:
        #        self.log.remove(item)
        if not self.quiet:
            logging.info(PROG + ': ' + timestring() + 'download failed: ' +
                    item[1] + ' -> ' + item[2])


class SiteHandler():

    # References to be implement in subclasses.
    PROTOCOL = None
    DOMAIN = None
    def _next(html): raise NotImplementedError()
    def _img(html): raise NotImplementedError()
    def _manga(html): raise NotImplementedError()
    def _chapter(html): raise NotImplementedError()
    def _page(html): raise NotImplementedError()


    def __init__(self, directory, logfile):
        logfile = os.path.realpath(os.path.join(directory, logfile))
        self.log = BaseLogger(logfile, quiet)
        signal.signal(signal.SIGTERM, self.log.cleanup)
        # This is not optimal: try to not change the dir.
        os.chdir(directory)


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
        # This is just a dummy implementation which should be overwritten.
        # The actual implementation should extract these information inline.
        key = cls._key(html)
        next = cls._next(html)
        img = cls._img(html)
        filename = cls._filename(html)
        return key, next, img, filename


    @staticmethod
    def _download(key, url, filename, logger):
        '''Download the url to the given filename.'''
        try:
            urllib.request.urlretrieve(url, filename)
        except urllib.error.ContentTooShortError:
            os.remove(filename)
            logging.exception('Could not download %s to %s.', url, filename)
            #logger.remove(key)
            #return
        #logger.remove(key)


    @staticmethod
    def _thread(function, arguments):
        #t = _thread.start_new_thread(function, arguments)
        #return
        t = threading.Thread(target=function, args=arguments)
        t.start()
        #threads.append(t)


    def _crawler(self, url):
        '''A generator to crawl the site.'''
        while True:
            try:
                request = urllib.request.urlopen(url)
            except (urllib.request.http.client.BadStatusLine,
                    urllib.error.HTTPError,
                    urllib.error.URLError) as e:
                logging.exception('%s returned %s', url, e)
                return
            html = BeautifulSoup(request)
            try:
                key, url, img, filename = self.__class__._parse(html)
            except AttributeError:
                logging.info('%s seems to be the last page.', url)
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
        '''Load all images starting at a specific url.  If after is True start
        loading images just after the given url.'''
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
            logging.debug('Starting thread to load {} to {}.'.format(img,
                filename))
            self._thread(self._download, (key, img, filename, None))



class Mangareader(SiteHandler):

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



class Unixmanga(SiteHandler):

    # class constants
    PROTOCOL = 'http'
    DOMAIN = 'unixmanga.com'

    def __init__(self, directory, logfile):
        suoer().__init__(directory, logfile)

    def _next(html):
        s = html.find_all(class_='navnext')[0].script.string.split('\n')[1]
        return re.sub(r'var nextlink = "(.*)";', r'\1', s)


class Mangafox(SiteHandler):
    DOMAIN='mangafox.me'
    PROTOCOL='http'

    def __init__(self, directory, logfile):
        super().__init__(directory, logfile)

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
        #return html.find(id='viewer').a.img['src']
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

    def parse_comand_line():
        '''Parse the command line and return the arguments object returned by
        the parser.'''
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
        #parser.add_argument('url', nargs='+')
        #parser.add_argument('url', nargs='?')
        parser.add_argument('name', nargs='?', metavar='url/name',
                type=check_url)
        args = parser.parse_args()
        if args.resume and (args.name is not None or args.missing):
            parser.error('You can only use -r or -m or give an url.')
        elif not args.resume and args.name is None and not args.missing:
            parser.error('You must specify -r or -m or an url.')
        logging.basicConfig(
                #format='%(filename)s [%(levelname)s]: %(msg)s',
                format='%(levelname)s: %(msg)s',
                level=args.loglevel
                )
        logging.debug(
                'The parsed command line arguments are {}.'.format(args))
        return args


    def prepare_output_dir(directory, string):
        # or should we used a named argument and detect the manga name
        # automatically if it is not given.
        '''Find the correct directory to save output files to and set
        directory'''

        #mangadir = os.path.join(os.getenv("HOME"), "comic")
        #if directory == '.':
        #    if os.path.exists(os.path.join(mangadir, string)):
        #        directory = os.path.exists(os.path.join(mangadir, string))
        #    elif is_url(string):

        mangadir = '.'
        if not directory == '.' and not os.path.sep in directory:
            mangadir = global_mangadir
            directory = os.path.realpath(os.path.join(mangadir, directory))
        if os.path.exists(directory):
            if not os.path.isdir(directory):
                raise EnvironmentError("Path exists but is not a directory.")
        else:
            os.mkdir(directory)
        # We change to the directory. We could only just return its path an let
        # the caller handle the rest (this is the aim for the future)
        os.chdir(directory)
        logging.info('Working in ' + os.path.realpath(os.path.curdir) + '.')
        return os.path.curdir
        return directory


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
        for d in [os.path.join(global_mangadir, dd) for dd in
                os.listdir(global_mangadir)]:
            os.chdir(d)
            logging.info('Working in ' + os.path.realpath(os.path.curdir) + '.')
            resume(os.path.join(global_mangadir, d), 'manga.log')


    def automatic(string):
        if os.path.exists(os.path.join(args.directory, string)):
            pass
        else:
            try:
                l = url.parse.urlparse(string)
            except:
                logging.critical('The fucking ERROR!')


    def parse_args_version_1(directory=None, name=None, resume=None, logfile=None):
        directory = prepare_output_dir(directory, name)
        if resume:
            resume(directory, logfile)
        else:
            cls = find_class_from_url(name)
            worker = cls(directory, logfile)
            worker.start_at(name)


    def parse_args_version_2(directory=None, name=None, resume=None,
            logfile=None, string=None, url=None):
        # Define the base directory for the directory to load to.
        mangadir = '.'
        if not os.path.sep in directory:
            mangadir = os.getenv("MANGADIR")
            if mangadir is None or mangadir == "":
                mangadir = os.path.join(os.getenv("HOME"), "comic")
            mangadir = os.path.realpath(mangadir)
        # Find the actual directory to work in.
        if directory == '.':
            # There was no directory given on command line.  Try to find the
            # directory in name.
            pass
        else:
            # We got a directory from the command line.
            directory = os.path.join(mangadir, directory)
        # Create the directory if necessary.
        if os.path.exists(directory):
            if not os.path.isdir(directory):
                raise EnvironmentError("Path exists but is not a directory.")
        else:
            os.mkdir(directory)
        os.chdir(directory)
        logging.info('Working in ' + os.path.realpath(os.path.curdir) + '.')
        directory = prepare_output_dir(directory, string)
        #if args.auto:
        #    automatic(string)
        #el
        # running
        if resume:
            resume(directory, logfile)
        else:
            cls = find_class_from_url(url)
            worker = cls(directory, logfile)
            #worker = Mangareader(directory, logfile)
            #worker.run(url)
            worker.start_at(url)


    def parse_args_version_3(directory=None, name=None, resume=None,
            logfile=None, string=None, url=None, resume_all=None, missing=None, **kwargs):
        directory = prepare_output_dir(directory, name)
        #if args.auto:
        #    automatic(string)
        #el
        if resume_all:
            resume_all()
            sys.exit()
        # running
        if resume:
            resume(directory, logfile)
            logging.info('missing was %s', missing)
        elif missing:
            download_missing(directory, logfile)
            logging.info('resume was %s', resume)
        else:
            cls = find_class_from_url(name)
            worker = cls(directory, logfile)
            #worker = Mangareader(directory, logfile)
            #worker.run(url)
            worker.start(name)


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


    args = parse_comand_line()
    # set global variables from cammand line values
    #quiet = args.quiet
    #debug = args.debug
    parse_args_version_3(**args.__dict__)
    join_threads()
    logging.debug('Exiting ...')

