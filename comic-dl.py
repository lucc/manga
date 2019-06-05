#!python

"""
A crawler/download script to download mangas and other comics from some websites.
"""

import argparse
import asyncio
import logging
import pathlib
import urllib.parse

import bs4
import requests


NAME = 'comic-dl'
VERSION = '0.5-dev'


class Job:
    pass


class PageDownload(Job):

    def __init__(self, url):
        self.url = url

    def __str__(self):
        return "PageDownload({})".format(self.url)

    def __hash__(self):
        return hash((self.__class__, self.url))

    def __eq__(self, other):
        return (type(self), self.url) == (type(other), other.url)


class FileDownload(Job):

    def __init__(self, url, path):
        self.url = url
        self.path = path

    def __str__(self):
        return "FileDownload(url={}, path={})".format(self.url, self.path)

    def __hash__(self):
        return hash((self.__class__, self.url, self.path))

    def __eq__(self, other):
        return (type(self), self.url, self.path) == \
                (type(other), other.url, other.path)


class Queue:

    def __init__(self):
        self._set = set()
        self._queue = asyncio.Queue()
        self._lock = asyncio.Lock()

    async def put(self, item):
        async with self._lock:
            if item in self._set:
                logging.debug("Item %s is already queued.", item)
                return
            logging.debug("Queueing item %s.", item)
            self._set.add(item)
            return await self._queue.put(item)

    async def get(self):
        async with self._lock:
            return await self._queue.get()

    async def join(self):
        return await self._queue.join()


class Site:

    DOMAIN = None

    def __init__(self):
        self._session = requests.Session()

    def get(self, url):
        req = self._session.get(url)
        req.raise_for_status()
        return req.content

    def download(self, url, path):
        data = self.get(url)
        with path.open("w") as f:
            f.write(data)

    @staticmethod
    def extract_images(html):
        raise NotImplemented

    @staticmethod
    def extract_pages(html):
        raise NotImplemented

    @classmethod
    def find_parser(cls, url):
        if cls.DOMAIN and urllib.parse.urlparse(url).hostname == cls.DOMAIN:
            return cls
        for subcls in cls.__subclasses__():
            maybe = subcls.find_parser(url)
            if maybe:
                return maybe


class MangaLike(Site):

    DOMAIN = "mangalike.net"

    @staticmethod
    def extract_images(html):
        chapter = pathlib.Path(html.find('li', class_='active').text.strip())
        imgs = html.find('div', class_='reading-content').find_all('img')
        urls = [img['src'].strip() for img in imgs]
        jobs = zip(urls, [chapter/'{}.jpg'.format(i) for i in range(len(urls))])
        return jobs

    @staticmethod
    def extract_pages(html):
        opts = html.find('div', class_='chapter-selection').find_all('option')
        return [opt['data-redirect'] for opt in opts]


async def worker(site, queue, directory):
    while True:
        job = await queue.get()
        logging.debug("Processing %s", job)
        if type(job) is PageDownload:
            page = site.get(job.url)
            logging.debug("Parsing html ...")
            html = bs4.BeautifulSoup(page)
            for url in site.extract_pages(html):
                logging.debug("storing new page job")
                await queue.put(PageDownload(url))
            for url, filename in site.extract_images(html):
                logging.debug("storing new image job")
                await queue.put(FileDownload(url, filename))
        else:
            filename = directory/job.path
            try:
                site.download(job.url, filename)
            except urllib.error.ContentTooShortError:
                filename.remove()
                logger.exception('Could not download %s to %s.', url, filename)
            else:
                logger.info('Done: {} -> {}'.format(url, filename))
        queue.task_done()


async def main():

    parser = argparse.ArgumentParser(
        prog=NAME, description="Download manga from some websites")
    parser.add_argument(
        "-d", "--directory", help="the output directory to save files",
        default=pathlib.Path(), type=pathlib.Path)
    parser.add_argument("--debug", default=logging.INFO, action="store_const",
                        const=logging.DEBUG)
    parser.add_argument("url", help="the url to start downloading")
    args = parser.parse_args()

    site = Site.find_parser(args.url)()
    logging.basicConfig(level=args.debug)

    queue = Queue()
    await queue.put(PageDownload(args.url))

    logging.debug("setting up task pool")
    tasks = []
    for i in range(3):
        task = asyncio.create_task(worker(site, queue, args.directory))
        tasks.append(task)

    await queue.join()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
