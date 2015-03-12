"""TODO"""

import logging
import os
import re
import time
import urllib


from . import crawler


logger = logging.getLogger(__name__)


def find_crawler(url):
    """Find a suitable crawler.Crawler subclass that can handle the given url.

    :url: an url
    :returns: a subclass of crawler.Crawler

    """
    return crawler.Crawler.find_subclass(url)


class Mangareader(crawler.Crawler):

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

    def _get_page(self, url):
        for _ in range(5):
            try:
                return urllib.request.urlopen(url)
            except (urllib.request.http.client.BadStatusLine,
                    urllib.error.HTTPError,
                    urllib.error.URLError) as e:
                if str(e) == 'HTTP Error 503: Service Unavailable':
                    logger.warning('{} returned {}, retrying ...'.format(
                        url, e))
                    time.sleep(1)
                    continue
                logger.warning('{} returned {}, giving up.'.format(url, e))
                return


class Unixmanga(crawler.Crawler):

    # class constants
    PROTOCOL = 'http'
    DOMAIN = 'unixmanga.com'

    def _next(html):
        s = html.find_all(class_='navnext')[0].script.string.split('\n')[1]
        return re.sub(r'var nextlink = "(.*)";', r'\1', s)


class Mangafox(crawler.Crawler):

    DOMAIN = 'mangafox.me'
    PROTOCOL = 'http'

    @classmethod
    def _next(cls, html):
        tmp = html.find(id='viewer').a['href']
        if tmp == "javascript:void(0);":
            return html.find(id='chnav').p.a['href']
        else:
            url = cls.PROTOCOL + '://' + cls.DOMAIN + '/manga/'
            l = str(html.body.find_all('script')[-2]).split('\n')
            # manga name
            url = url + l[3].split('"')[1]
            # volume and chapter and page (in tmp)
            url = url + l[6].split('"')[1] + tmp
            return url

    @classmethod
    def _key(cls, html): raise NotImplementedError()

    @classmethod
    def _img(cls, html):
        return html.find(id='image')['src']

    @classmethod
    def _filename(cls, html):
        keys = cls._key_helper(html)
        return keys[0] + ' ' + str(keys[2]) + ' page ' + str(keys[3]) + \
            cls._img(html).split('.')[-1]

    @classmethod
    def _chapter(cls, html):
        return cls._key_helper()[2]

    @classmethod
    def _page(cls, html):
        return cls._key_helper()[3]

    @classmethod
    def _key_helper(cls, html):
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


class Userfriendly(crawler.Crawler):

    DOMAIN = 'ars.userfriendly.org'
    PROTOCOL = 'http'

    @classmethod
    def _next(cls, html):
        return cls.expand(html.find('area', alt="Next Day's Cartoon")['href'])

    @classmethod
    def _img(cls, html):
        return html.find('img', alt=re.compile('^Strip for'))['src']

    @classmethod
    def _key(cls, html):
        return html.find('img', alt=re.compile(
            '^Strip for')).parent['href'].split('=')[-1]

    @classmethod
    def _filename(cls, html):
        return '.'.join([cls._key(html), cls._img(html).split('.')[-1]])


class Xkcd(crawler.Crawler):

    """Crawler for the normal xkcd site at http://xkcd.com."""

    DOMAIN = 'xkcd.com'
    PROTOCOL = 'http'

    @classmethod
    def _next(cls, html):
        return cls.expand(html.find('a', accesskey='n')['href'])

    @classmethod
    def _img(cls, html):
        return html.find('div', id='comic').img['src']

    @classmethod
    def _key(cls, html):
        try:
            key = int(html.find('a', accesskey='n')['href'].strip('/')) - 1
        except ValueError:
            key = int(html.find('a', accesskey='p')['href'].strip('/')) + 1
        return key

    @classmethod
    def _filename(cls, html):
        return str(cls._key(html)) + '-' + os.path.basename(cls._img(html))


class Mxkcd(Xkcd):

    """Crawler for the mobile xkcd site at http://m.xkcd.com"""

    DOMAIN = 'm.xkcd.com'
