'''TODO'''


import os
import urllib.request
import re
import logging


from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


class Crawler():

    '''TODO'''

    # References to be implement in subclasses.
    PROTOCOL = ''
    DOMAIN = ''

    def _next(html): raise NotImplementedError()

    def _img(html): raise NotImplementedError()

    def _manga(html): raise NotImplementedError()

    def _chapter(html): raise NotImplementedError()

    def _page(html): raise NotImplementedError()

    def __init__(self, queue, end_event):
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
                logger.debug('Loading page {}.'.format(url))
                request = urllib.request.urlopen(url)
            except (urllib.request.http.client.BadStatusLine,
                    urllib.error.HTTPError,
                    urllib.error.URLError) as e:
                logger.exception('%s returned %s', url, e)
                self._done.set()
                return
            html = BeautifulSoup(request)
            try:
                key, url, img, filename = self.__class__._parse(html)
            except AttributeError:
                logger.info('{} seems to be the last page.'.format(url))
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
            logger.debug('Found correct subclass: {}'.format(cls))
            return True
        return False

    @classmethod
    def find_subclass(cls, url):
        """Find a (sub) class that can crawl the given url.  Return the class if
        it can and raise an Error otherwise.

        :url: the url that has to be crawled
        :returns: a Crawler subclass

        """
        if cls.can_load(url):
            return cls
        for subcls in cls.__subclasses__():
            if subcls.can_load(url):
                return subcls
        for subcls in cls.__subclasses__():
            subcls.find_subclass(url)
        raise NotImplementedError(
            'There is no class available to work with this url.')

    def start(self, url, after=False):
        '''Crawl the site starting at url (or just after url if after=True)
        and queue all image urls with their filenames to be download in
        another thread.'''
        if after:
            try:
                request = urllib.request.urlopen(url)
            except urllib.error.URLError as e:
                logger.exception('%s returned %s', url, e)
                return
            html = BeautifulSoup(request)
            url = self.__class__._next(html)
        for key, img, filename in self._crawler(url):
            logger.debug('Queueing job {}.'.format(key))
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

    DOMAIN = 'mangafox.me'
    PROTOCOL = 'http'

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
        if re.march(r'^[0-9]+\.html$', val[-1]) is not None:
            page = int(val[-1].split('.')[0])
        else:
            raise BaseException('wrong string while parsing')
        if re.match(r'^c[0-9]+$', val[-2]) is not None:
            chapter = int(val[-2][1:])
        else:
            raise BaseException('wrong string while parsing')
        if re.match(r'^v[0-9]+$', val[-3]) is not None:
            volume = int(val[-3][1:])
            i = -4
        else:
            volume = None
            i = -3
        manga = val[i]
        return (manga, volume, chapter, page)