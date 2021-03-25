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
import sys
from typing import cast, Dict, Iterable, Generic, Optional, Tuple, Type, TypeVar
import urllib.error
import urllib.parse

import bs4
import requests
import urllib3.exceptions


NAME = 'comic-dl'
VERSION = '0.6-dev'
T = TypeVar("T")


class Job:

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.__dict__ == other.__dict__


class PageDownload(Job):

    def __init__(self, url: str):
        self.url = url

    def __str__(self) -> str:
        return "PageDownload({})".format(self.url)

    def __hash__(self) -> int:
        return hash((self.__class__, self.url))


class FileDownload(Job):

    def __init__(self, url: str, path: pathlib.Path):
        self.url = url
        self.path = path

    def __str__(self) -> str:
        return "FileDownload(url={}, path={})".format(self.url, self.path)

    def __hash__(self) -> int:
        return hash((self.__class__, self.url, self.path))


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

    def get_state(self) -> Dict[T, bool]:
        """Get a dict representation of the internal state

        The dict can be fead to the constructor to recreate the queue.
        """
        state = {}
        while not self._queue.empty():
            item = self._queue.get_nowait()
            state[item] = False
            self._queue.task_done()
        for item in self._set.difference(state.keys()):
            state[item] = True
        return state


class Site:

    DOMAIN: str

    def __init__(self, queue: Queue[Job], directory: pathlib.Path):
        self._session = requests.Session()
        self.queue = queue
        self.directory = directory

    async def get(self, url: str) -> bytes:
        for _ in range(3):
            try:
                req = self._session.get(url)
            except urllib3.exceptions.MaxRetryError as err:
                logging.warning("Failed to connect: %s\nRetrying  ...", err.message)
                await asyncio.sleep(3)
                continue
            req.raise_for_status()
            return req.content
        raise urllib3.exceptions.MaxRetryError

    async def download(self, url: str, path: pathlib.Path) -> None:
        data = await self.get(url)
        with path.open("wb") as f:
            f.write(data)

    @staticmethod
    def extract_images(html: bs4.BeautifulSoup) -> Iterable[FileDownload]:
        raise NotImplementedError

    @staticmethod
    def extract_pages(html: bs4.BeautifulSoup) -> Iterable[PageDownload]:
        raise NotImplementedError

    @classmethod
    def find_crawler(cls, url: str) -> Type["Site"]:
        if cls != Site and urllib.parse.urlparse(url).hostname == cls.DOMAIN:
            return cls
        for subcls in cls.__subclasses__():
            try:
                return subcls.find_crawler(url)
            except NotImplementedError:
                pass
        raise NotImplementedError

    async def start(self) -> None:
        while True:
            job: Job = await self.queue.get()
            logging.debug("Processing %s", job)
            try:
                if isinstance(job, PageDownload):
                    await self.handle_page(job)
                else:
                    job = cast(FileDownload, job)
                    await self.handle_image(job)
            except Exception as e:
                logging.exception("Processing of %s failed: %s", job, e)
            self.queue.task_done()

    async def handle_page(self, job: PageDownload) -> None:
        page = await self.get(job.url)
        html = bs4.BeautifulSoup(page, features="lxml")
        for i in self.extract_pages(html):
            await self.queue.put(i)
        for j in self.extract_images(html):
            await self.queue.put(j)
        logging.info('Finished parsing %s', job.url)

    async def handle_image(self, job: FileDownload) -> None:
        filename = self.directory / job.path
        if filename.exists():
            logging.debug("The file %s was already loaded.", filename)
        else:
            filename.parent.mkdir(parents=True, exist_ok=True)
            try:
                await self.download(job.url, filename)
            except urllib.error.ContentTooShortError:
                filename.unlink()
                logging.exception('Could not download %s to %s.',
                                  job.url, filename)
            else:
                logging.info('Done: %s -> %s', job.url, filename)

    def dump(self) -> None:
        """Dump the internal state of the queue to a file

        The file can be loaded again with self.load() and the new crawler can
        continue where this one left of.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        filename = self.directory / 'state.pickle'
        state = self.queue.get_state()
        with filename.open("wb") as fp:
            pickle.dump(state, fp)

    @classmethod
    async def load(cls, directory: pathlib.Path) -> "Site":
        statefile = directory / 'state.pickle'
        with statefile.open("rb") as fp:
            state = pickle.load(fp)
        page = cls.get_resume_page(state)
        crawler = cls.find_crawler(page.url)
        if crawler.get_resume_page != cls.get_resume_page:
            page = crawler.get_resume_page(state)
        state.pop(page)
        queue: Queue[Job] = Queue(state)
        await queue.put(page)
        return crawler(queue, directory)

    @staticmethod
    def get_resume_page(state: Dict[Job, bool]) -> PageDownload:
        pages = {k: v for k, v in state.items() if isinstance(k, PageDownload)}
        unloaded = [page for page, done in pages.items() if not done]
        if unloaded:
            return unloaded[0]
        if pages:
            return pages.popitem()[0]
        raise ValueError("Found no page to resume loading.")


class Islieb(Site):

    DOMAIN = "islieb.de"
    archive_page = PageDownload('https://islieb.de/comic-archiv/')

    @staticmethod
    def extract_images(html: bs4.BeautifulSoup) -> Iterable[FileDownload]:
        for article in html.find_all('article'):
            url = article.find('img')['src']
            filename = pathlib.Path(*url.split('/')[-3:])
            yield FileDownload(url, filename)

    @classmethod
    def extract_pages(cls, html: bs4.BeautifulSoup) -> Iterable[PageDownload]:
        yield cls.archive_page
        archive = html.find('ul', id='lcp_instance_0')
        if archive:
            for link in archive.find_all('a'):
                yield PageDownload(link['href'])

    @classmethod
    def get_resume_page(cls, state: Dict[Job, bool]) -> PageDownload:
        return cls.archive_page


class MangaReader(Site):

    DOMAIN = "www.mangareader.net"

    @staticmethod
    def extract_images(html: bs4.BeautifulSoup) -> Iterable[FileDownload]:
        img = html.find(id='img')
        url = img['src']
        extension = os.path.splitext(url)[1]
        chapter = pathlib.Path(html.find(id='mangainfo').h1.string)
        filename = chapter / (img['alt'] + extension)
        yield FileDownload(url, filename)

    @classmethod
    def extract_pages(cls, html: bs4.BeautifulSoup) -> Iterable[PageDownload]:
        page_options = html.find(id="pageMenu").find_all("option")
        pages = [page["value"] for page in page_options]
        chapter_links = html.find(id="mangainfofooter").table.find_all("a")
        chapter_links.reverse()
        chapters = [chapter["href"] for chapter in chapter_links]
        for path in pages + chapters:
            yield PageDownload("https://" + cls.DOMAIN + path)


class MangaTown(Site):

    DOMAIN = "www.mangatown.com"

    @staticmethod
    def extract_images(html: bs4.BeautifulSoup) -> Iterable[FileDownload]:
        if img := html.find("img", id="image"):
            url = "https:" + img["src"]
            urlpath = pathlib.Path(urllib.parse.urlparse(url).path)
            chapter = urlpath.parent.parent.name
            yield FileDownload(url, pathlib.Path(chapter) / urlpath.name)

    @classmethod
    def extract_pages(cls, html: bs4.BeautifulSoup) -> Iterable[PageDownload]:
        for option in html.find("div", class_="go_page").find_all("option"):
            yield PageDownload("https://" + cls.DOMAIN + option["value"])


class Xkcd(Site):

    DOMAIN = "xkcd.com"

    @staticmethod
    def extract_images(html: bs4.BeautifulSoup) -> Iterable[FileDownload]:
        image_url = html.find("div", id="comic").img["src"]
        extension = os.path.splitext(image_url)[1]
        base_url = html.find("meta", property="og:url")["content"]
        filename = urllib.parse.urlsplit(base_url).path.strip("/") + extension
        yield FileDownload("https:" + image_url, pathlib.Path(filename))

    @classmethod
    def extract_pages(cls, html: bs4.BeautifulSoup) -> Iterable[PageDownload]:
        if html.find("a", rel="next")["href"] == "#":
            base_url = html.find("meta", property="og:url")["content"]
            number = int(urllib.parse.urlsplit(base_url).path.strip("/"))
            for i in filter(lambda x: x != 404, range(1, number)):
                yield PageDownload("https://" + cls.DOMAIN + "/{}/".format(i))
        else:
            yield PageDownload("https://" + cls.DOMAIN + "/")


async def start(args: argparse.Namespace) -> None:
    try:
        crawler = await Site.load(args.directory)
    except FileNotFoundError:
        if args.resume:
            sys.exit("No statefile found to resume from.")
        try:
            Crawler = Site.find_crawler(args.url)
        except NotImplementedError:
            sys.exit("No crawler available for {}.".format(
                urllib.parse.urlsplit(args.url).hostname or args.url))
        queue: Queue[Job] = Queue()
        await queue.put(PageDownload(args.url))
        crawler = Crawler(queue, args.directory)
    # Set up the event loop and run the tasks
    logging.debug("setting up task pool")
    tasks = [asyncio.create_task(crawler.start()) for _ in range(3)]
    await crawler.queue.join()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    crawler.dump()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog=NAME, description="Download manga from some websites")
    parser.add_argument(
        "-d", "--directory", help="the output directory to save files",
        default=pathlib.Path(), type=pathlib.Path)
    parser.add_argument("--debug", default=logging.INFO, action="store_const",
                        const=logging.DEBUG)
    parser.add_argument('--version', action='version', version=VERSION)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--resume", action="store_true",
                        help="resume downloading from a state file")
    target.add_argument("url", nargs="?", help="the url to start downloading")
    args = parser.parse_args()
    logging.basicConfig(level=args.debug)
    logging.debug("Command line arguments: %s", args)
    asyncio.run(start(args))


if __name__ == "__main__":
    main()
