#!python

"""
A crawler/download script to download mangas and other comics from some websites.
"""

import argparse
import asyncio
import logging
import os.path
import pathlib
import pickle
from typing import cast, Dict, Iterable, Generic, Optional, Tuple, Type, TypeVar
import urllib.error
import urllib.parse

import bs4
import requests


NAME = 'comic-dl'
VERSION = '0.6-dev'
T = TypeVar("T")
Images = Iterable[Tuple[str, pathlib.Path]]


class Job:
    pass


class PageDownload(Job):

    def __init__(self, url: str):
        self.url = url

    def __str__(self) -> str:
        return "PageDownload({})".format(self.url)

    def __hash__(self) -> int:
        return hash((self.__class__, self.url))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.url == other.url


class FileDownload(Job):

    def __init__(self, url: str, path: pathlib.Path):
        self.url = url
        self.path = path

    def __str__(self) -> str:
        return "FileDownload(url={}, path={})".format(self.url, self.path)

    def __hash__(self) -> int:
        return hash((self.__class__, self.url, self.path))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) \
            and (self.url, self.path) == (other.url, other.path)


class Queue(Generic[T]):
    """An asynchrounous queue with duplicate detection.

    The queue caches items that are added and ignores them if they are added
    again.  The interface should mostly be identcal to asyncio.Queue.
    """

    def __init__(self, state: Optional[Dict[T, bool]] = None) -> None:
        """Initialize the queue optionally filling some entries

        :param state: an optional dictionary of entries to put in the queue.
            The keys are the items for the queue, the values indicate if the
            item still needs to be retrieved from the queue
        """
        state = state or {}
        self._set = set(state.keys())
        self._queue: asyncio.Queue[T] = asyncio.Queue()
        for job, done in state.items():
            if not done:
                self._queue.put_nowait(job)
        self._lock = asyncio.Lock()

    async def put(self, item: T) -> None:
        async with self._lock:
            if item in self._set:
                return
            self._set.add(item)
            return await self._queue.put(item)

    async def get(self) -> T:
        async with self._lock:
            return await self._queue.get()

    async def join(self) -> None:
        await self._queue.join()  # TODO

    def task_done(self) -> None:
        return self._queue.task_done()

    def dump(self, filename: pathlib.Path) -> None:
        """Dump the internal state of the queue to a file

        The file can be loaded again with pickle and the state can be used to
        recreate a new Queue object which will pick up where this Queue left
        of.
        """
        dump = {}
        while not self._queue.empty():
            item = self._queue.get_nowait()
            dump[item] = False
            self._queue.task_done()
        for item in self._set.difference(dump.keys()):
            dump[item] = True
        with filename.open('wb') as fp:
            pickle.dump(dump, fp)


class Site:

    DOMAIN: str = None  # type: ignore

    def __init__(self, queue: Queue[Job], directory: pathlib.Path):
        self._session = requests.Session()
        self.queue = queue
        self.directory = directory

    def get(self, url: str) -> bytes:
        req = self._session.get(url)
        req.raise_for_status()
        return req.content

    def download(self, url: str, path: pathlib.Path) -> None:
        data = self.get(url)
        with path.open("wb") as f:
            f.write(data)

    @staticmethod
    def extract_images(html: bs4.BeautifulSoup) -> Images:
        raise NotImplementedError

    @staticmethod
    def extract_pages(html: bs4.BeautifulSoup) -> Iterable[str]:
        raise NotImplementedError

    @classmethod
    def find_parser(cls, url: str) -> Optional[Type["Site"]]:
        if cls.DOMAIN and urllib.parse.urlparse(url).hostname == cls.DOMAIN:
            return cls
        for subcls in cls.__subclasses__():
            maybe = subcls.find_parser(url)
            if maybe:
                return maybe
        return None

    async def start(self) -> None:
        while True:
            job: Job = await self.queue.get()
            logging.debug("Processing %s", job)
            try:
                if isinstance(job, PageDownload):
                    await self.handle_page(job)
                else:
                    job = cast(FileDownload, job)
                    self.handle_image(job)
            except Exception as e:
                logging.exception("Processing of %s failed: %s", job, e)
            self.queue.task_done()

    async def handle_page(self, job: PageDownload) -> None:
        page = self.get(job.url)
        html = bs4.BeautifulSoup(page)
        for url in self.extract_pages(html):
            await self.queue.put(PageDownload(url))
        for url, filename in self.extract_images(html):
            await self.queue.put(FileDownload(url, filename))
        logging.info('Finished parsing %s', job.url)

    def handle_image(self, job: FileDownload) -> None:
        filename = self.directory / job.path
        if filename.exists():
            logging.debug("The file %s was already loaded.", filename)
        else:
            filename.parent.mkdir(parents=True, exist_ok=True)
            try:
                self.download(job.url, filename)
            except urllib.error.ContentTooShortError:
                filename.unlink()
                logging.exception('Could not download %s to %s.',
                                  job.url, filename)
            else:
                logging.info('Done: %s -> %s', job.url, filename)


class MangaLike(Site):

    DOMAIN = "mangalike.net"

    @staticmethod
    def extract_images(html: bs4.BeautifulSoup) -> Images:
        chapter = pathlib.Path(html.find('li', class_='active').text.strip())
        imgs = html.find('div', class_='reading-content').find_all('img')
        urls = [img['src'].strip() for img in imgs]
        count = len(urls)
        fmt = '{{:0{}}}.jpg'.format(len(str(count)))
        for i, url in zip(range(count), urls):
            yield url, chapter / fmt.format(i)

    @staticmethod
    def extract_pages(html: bs4.BeautifulSoup) -> Iterable[str]:
        opts = html.find('div', class_='chapter-selection').find_all('option')
        return reversed([opt['data-redirect'] for opt in opts])


class MangaReader(Site):

    DOMAIN = "www.mangareader.net"

    @staticmethod
    def extract_images(html: bs4.BeautifulSoup) -> Images:
        img = html.find(id='img')
        url = img['src']
        extension = os.path.splitext(url)[1]
        chapter = pathlib.Path(html.find(id='mangainfo').h1.string)
        filename = chapter / (img['alt'] + extension)
        yield url, filename

    @classmethod
    def extract_pages(cls, html: bs4.BeautifulSoup) -> Iterable[str]:
        page_options = html.find(id="pageMenu").find_all("option")
        pages = [page["value"] for page in page_options]
        chapter_links = html.find(id="mangainfofooter").table.find_all("a")
        chapter_links.reverse()
        chapters = [chapter["href"] for chapter in chapter_links]
        for path in pages + chapters:
            yield "https://" + cls.DOMAIN + path


class Taadd(Site):

    DOMAIN = "www.taadd.com"

    @staticmethod
    def extract_images(html: bs4.BeautifulSoup) -> Images:
        img = html.find("img", id="comicpic")
        url = img["src"]
        extension = os.path.splitext(url)[1]
        current = html.find('select', id='page').find('option', selected=True)
        number = current.text
        chapter = pathlib.Path(img["alt"])
        yield url, chapter / (number + extension)

    @staticmethod
    def extract_pages(html: bs4.BeautifulSoup) -> Iterable[str]:
        for opt in html.find_all("select", id="chapter")[1].find_all("option"):
            yield opt["value"]
        for opt in html.find("select", id="page").find_all("option"):
            yield opt["value"]


async def start(url: str, directory: pathlib.Path) -> None:
    statefile = directory / 'state.pickle'
    if statefile.exists():
        with statefile.open('rb') as fp:
            state = pickle.load(fp)
        queue: Queue[Job] = Queue(state)
    else:
        queue = Queue()
    site = Site.find_parser(url)(queue, directory) # type: ignore
    await queue.put(PageDownload(url))

    logging.debug("setting up task pool")
    tasks = [asyncio.create_task(site.start()) for _ in range(3)]

    await queue.join()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    queue.dump(statefile)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog=NAME, description="Download manga from some websites")
    parser.add_argument(
        "-d", "--directory", help="the output directory to save files",
        default=pathlib.Path(), type=pathlib.Path)
    parser.add_argument("--debug", default=logging.INFO, action="store_const",
                        const=logging.DEBUG)
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument("url", help="the url to start downloading")
    args = parser.parse_args()
    logging.basicConfig(level=args.debug)

    asyncio.run(start(args.url, args.directory))


if __name__ == "__main__":
    main()
