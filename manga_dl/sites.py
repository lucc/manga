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


class Mangafox(crawler.LinearChapterDirectPageCrawler):

    DOMAIN = 'mangafox.me'
    PROTOCOL = 'http'

    def _next(self, html):
        prev_and_next_chap = html.find(id='chnav').find_all('p')
        if prev_and_next_chap[1].span.text == 'Next Chapter:':
            return prev_and_next_chap[1].a['href']
        elif prev_and_next_chap[0].span.text == 'Next Chapter:':
            return prev_and_next_chap[0].a['href']
        else:
            raise AttributeError('No next chapter found.')

    def _img(self, html):
        return html.find(id='image')['src']

    def _filename(self, html):
        return '{}-{}-page-{}.{}'.format(
            self._manga, self._chapter(html), self._page(html),
            self._img(html).split('.')[-1])

    def _chapter(self, html):
        return self._canonical_link(html).split('/')[-2].strip('c')

    def _page(self, html):
        return self._canonical_link(html).split('/')[-1].split('.')[0]

    def _rss_link(self, html):
        return html.head.find('link', rel='alternate')['href']

    def _canonical_link(self, html):
        return html.head.find('link', rel='canonical')['href']

    def _key(self, html):
        return '{}-{}'.format(self._chapter(html), self._page(html))

    def _pages(self, html):
        """Find all the pages in a chapter page.

        :html: the chapter entry point page
        :yields: the page urls for this chapter

        """
        # Substract two from the length of the list because the first page has
        # already been parsed and the last page is a comment page (page indices
        # start at one, range() starts at zero).
        url = self._canonical_link(html).rsplit('/', maxsplit=1)[0]
        for number in range(2, len(self._options_array(html))):
            yield '{}/{}.html'.format(url, number)

    def _slice_first_chapter(self, url, html):
        pagenr = int(self._page(html).split('.')[0])
        url = url.rsplit('/', maxsplit=1)[0]
        for number in range(pagenr, len(self._options_array(html))):
            yield url+'/'+str(number)+'.html'

    def _options_array(self, html):
        return html.find('form', id='top_bar').find(
            'select', class_='m').find_all('option')

    def _set_manga_info(self, url, html):
        self._manga = self._rss_link(html).split('/')[-1].rsplit(
            '.', maxsplit=1)[0]


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


class Xkcd(crawler.DirectPageCrawler):

    """Crawler for the normal xkcd site at http://xkcd.com."""

    DOMAIN = 'xkcd.com'
    PROTOCOL = 'http'
    METAPAGE = 'http://xkcd.com/archive'

    def _parse_meta_page(self, html, url, after):
        logger.debug('Enter Xkcd._parse_meta_page')
        threshold = int(url.rstrip('/').split('/')[-1])
        if after:
            threshold += 1
        for tag in html.find('div', id='middleContainer').find_all('a'):
            url = int(tag['href'].strip('/'))
            if url >= threshold:
                yield self.expand(str(url))

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
