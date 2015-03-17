"""TODO"""

import logging
import os
import re
import urllib


from . import crawler


logger = logging.getLogger(__name__)


def find_crawler(url):
    """Find a suitable crawler.Crawler subclass that can handle the given url.

    :url: an url
    :returns: a subclass of crawler.Crawler

    """
    return crawler.Crawler.find_subclass(url)


class Mangareader(crawler.LinearPageCrawler):

    PROTOCOL = 'http'
    DOMAIN = 'www.mangareader.net'
    HANDLED_EXCEPTIONS = (urllib.request.http.client.BadStatusLine,
                          urllib.error.HTTPError, urllib.error.URLError)

    def _next(self, html):
        return self.expand(html.find(id='img').parent['href'])

    def _img(self, html):
        return html.find(id='img')['src']

    def _filename(self, html):
        return re.sub(r'[ -]+', '-', html.find(id="img")["alt"]).lower() + \
            '.' + self._img(html).split('.')[-1]

    def _chapter(self, html):
        return int(html.find(id='mangainfo').h1.string.split()[-1])

    def _page(self, html):
        return int(html.find(id='mangainfo').span.string.split()[1])

    def _manga(self, html):
        return re.sub(r'(.*) [0-9]+$', r'\1',
                      html.find(id='mangainfo').h1.string)

    def _ignore_exception(self, exeption):
        """Overwriding LinearPageCrawler._ignore_exception."""
        return str(exeption) == 'HTTP Error 503: Service Unavailable'


class Unixmanga(crawler.Crawler):

    # class constants
    PROTOCOL = 'http'
    DOMAIN = 'unixmanga.com'

    def _next(self, html):
        s = html.find_all(class_='navnext')[0].script.string.split('\n')[1]
        return re.sub(r'var nextlink = "(.*)";', r'\1', s)


class Mangafox(crawler.Crawler):

    DOMAIN = 'mangafox.me'
    PROTOCOL = 'http'

    def _next(self, html):
        tmp = html.find(id='viewer').a['href']
        if tmp == "javascript:void(0);":
            return html.find(id='chnav').p.a['href']
        else:
            url = self.PROTOCOL + '://' + self.DOMAIN + '/manga/'
            l = str(html.body.find_all('script')[-2]).split('\n')
            # manga name
            url = url + l[3].split('"')[1]
            # volume and chapter and page (in tmp)
            url = url + l[6].split('"')[1] + tmp
            return url

    def _key(self, html): raise NotImplementedError()

    def _img(self, html):
        return html.find(id='image')['src']

    def _filename(self, html):
        keys = self._key_helper(html)
        return keys[0] + ' ' + str(keys[2]) + ' page ' + str(keys[3]) + \
            self._img(html).split('.')[-1]

    def _chapter(self, html):
        return self._key_helper()[2]

    def _page(self, html):
        return self._key_helper()[3]

    def _key_helper(self, html):
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

    def _next(self, html):
        return self.__class__.expand(
            html.find('area', alt="Next Day's Cartoon")['href'])

    def _img(self, html):
        return html.find('img', alt=re.compile('^Strip for'))['src']

    def _key(self, html):
        return html.find('img', alt=re.compile(
            '^Strip for')).parent['href'].split('=')[-1]

    def _filename(self, html):
        return '.'.join([self._key(html), self._img(html).split('.')[-1]])


class Xkcd(crawler.Crawler):

    """Crawler for the normal xkcd site at http://xkcd.com."""

    DOMAIN = 'xkcd.com'
    PROTOCOL = 'http'

    def _next(self, html):
        return self.expand(html.find('a', accesskey='n')['href'])

    def _img(self, html):
        return html.find('div', id='comic').img['src']

    def _key(self, html):
        try:
            key = int(html.find('a', accesskey='n')['href'].strip('/')) - 1
        except ValueError:
            key = int(html.find('a', accesskey='p')['href'].strip('/')) + 1
        return key

    def _filename(self, html):
        return str(self._key(html)) + '-' + os.path.basename(self._img(html))


class Mxkcd(Xkcd):

    """Crawler for the mobile xkcd site at http://m.xkcd.com"""

    DOMAIN = 'm.xkcd.com'
