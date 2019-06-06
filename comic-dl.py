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
                return
            self._set.add(item)
            return await self._queue.put(item)

    async def get(self):
        async with self._lock:
            return await self._queue.get()

    async def join(self):
        return await self._queue.join()

    def task_done(self):
        return self._queue.task_done()


class Site:

    DOMAIN = None

    def __init__(self, queue, directory):
        self._session = requests.Session()
        self.queue = queue
        self.directory = directory

    def get(self, url):
        req = self._session.get(url)
        req.raise_for_status()
        return req.content

    def download(self, url, path):
        data = self.get(url)
        with path.open("wb") as f:
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

    async def start(self):
        while True:
            job = await self.queue.get()
            logging.debug("Processing %s", job)
            try:
                if type(job) is PageDownload:
                    await self.handle_page(job)
                else:
                    self.handle_image(job)
            except Exception as e:
                logging.exception("Processing of %s failed: %s", job, e)
            self.queue.task_done()

    async def handle_page(self, job):
        page = self.get(job.url)
        html = bs4.BeautifulSoup(page, features='lxml')
        for url in self.extract_pages(html):
            await self.queue.put(PageDownload(url))
        for url, filename in self.extract_images(html):
            await self.queue.put(FileDownload(url, filename))
        logging.info('Finished parsing %s', job.url)

    def handle_image(self, job):
        filename = self.directory / job.path
        if filename.exists():
            logging.debug("The file %s was already loaded.", filename)
        else:
            filename.parent.mkdir(parents=True, exist_ok=True)
            try:
                self.download(job.url, filename)
            except urllib.error.ContentTooShortError:
                filename.remove()
                logging.exception('Could not download %s to %s.',
                                  job.url, filename)
            else:
                logging.info('Done: %s -> %s', job.url, filename)


class MangaLike(Site):

    DOMAIN = "mangalike.net"

    @staticmethod
    def extract_images(html):
        chapter = pathlib.Path(html.find('li', class_='active').text.strip())
        imgs = html.find('div', class_='reading-content').find_all('img')
        urls = [img['src'].strip() for img in imgs]
        count = len(urls)
        fmt = '{{:0{}}}.jpg'.format(len(str(count)))
        for i, url in zip(range(count), urls):
            yield url, chapter / fmt.format(i)

    @staticmethod
    def extract_pages(html):
        opts = html.find('div', class_='chapter-selection').find_all('option')
        return reversed([opt['data-redirect'] for opt in opts])


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
    logging.basicConfig(level=args.debug)

    queue = Queue()
    site = Site.find_parser(args.url)(queue, args.directory)
    await queue.put(PageDownload(args.url))

    logging.debug("setting up task pool")
    tasks = []
    for i in range(3):
        task = asyncio.create_task(site.start())
        tasks.append(task)

    await queue.join()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
