import pathlib
import unittest

import bs4

from comic_dl import PageDownload, FileDownload
from comic_dl import Islieb, MangaReader, MangaTown, Xkcd


def load_html(name):
    file = pathlib.Path("test") / name
    with file.open() as f:
        data = f.read()
    return bs4.BeautifulSoup(data, features="lxml")


class StaticJobTests(unittest.TestCase):

    """Tests for Job and subclasses"""

    def test_page_download_equality(self):
        self.assertEqual(PageDownload("foo"), PageDownload("foo"))

    def test_file_download_equality(self):
        cwd = pathlib.Path(".")
        self.assertEqual(FileDownload("foo", cwd), FileDownload("foo", cwd))

    def test_page_download_inequality(self):
        self.assertNotEqual(PageDownload("foo"), PageDownload("bar"))

    def test_file_download_inequality_1(self):
        cwd = pathlib.Path(".")
        self.assertNotEqual(FileDownload("foo", cwd), FileDownload("bar", cwd))

    def test_file_download_inequality_2(self):
        p1 = pathlib.Path(".")
        p2 = pathlib.Path("/")
        self.assertNotEqual(FileDownload("foo", p1), FileDownload("foo", p2))


class StaticParserTests(unittest.TestCase):

    def test_islieb(self):
        html = load_html('islieb.html')
        filename = "2015/08/islieb-was-kerle-wollen.png"
        expected = [FileDownload(
            "http://islieb.de/blog/wp-content/uploads/" + filename,
            pathlib.Path(filename))]
        actual = list(Islieb.extract_images(html))
        self.assertListEqual(actual, expected)
        actual = list(Islieb.extract_pages(html))
        self.assertListEqual(actual, [Islieb.archive_page])
        html = load_html('islieb-archive.html')
        filename = '2014/02/spinnen-phobie.png'
        expected = [FileDownload(
            'https://islieb.de/blog/wp-content/uploads/' + filename,
            pathlib.Path(filename))]
        actual = list(Islieb.extract_images(html))
        self.assertListEqual(actual, expected)
        expected = [Islieb.archive_page] + [
            PageDownload(link['href']) for link in
            html.find('ul', id='lcp_instance_0').find_all('a')]
        actual = list(Islieb.extract_pages(html))
        self.assertListEqual(actual, expected)

    def test_mangareader(self):
        html = load_html("mangareader.html")
        expected = [FileDownload(
            'https://i10.mangareader.net/azumi/1/azumi-4734639.jpg',
            pathlib.Path('Azumi 1/Azumi 1 - Page 1.jpg'))]
        actual = list(MangaReader.extract_images(html))
        self.assertListEqual(actual, expected)
        expected = ['https://www.mangareader.net/azumi/1'] + [
            'https://www.mangareader.net/azumi/1/{}'.format(i)
            for i in range(2, 44)
        ] + ['https://www.mangareader.net/azumi/2']
        expected = [PageDownload(item) for item in expected]
        actual = list(MangaReader.extract_pages(html))
        self.assertListEqual(actual, expected)

    def test_mangatown(self):
        html = load_html("mangatown.com.html")
        expected = [FileDownload("https://zjcdn.mangahere.org/store/manga/"
                                 "13495/264.0/compressed/v000.jpg",
                                 pathlib.Path("264.0/v000.jpg"))]
        actual = list(MangaTown.extract_images(html))
        self.assertListEqual(actual, expected)
        base = "https://www.mangatown.com/manga/azumi/"
        expected = [
            PageDownload(base + "c{:03}/".format(i)) for i in range(1, 283) if
            i not in (162, 181, 193, 201, 208, 215, 280)] + [
            PageDownload(base + "c264/")] + [
            PageDownload(base + "c264/{}.html".format(i))
            for i in range(2, 28)] + [
            PageDownload(base + "c264/featured.html")]
        actual = list(MangaTown.extract_pages(html))
        self.assertListEqual(actual, expected)

    def test_mangatown2(self):
        html = load_html("mangatown.com-2.html")
        expected = [FileDownload("https://zjcdn.mangahere.org/store/manga"
                                 f"/31587/051.0/compressed/h00{i}.jpg",
                                 pathlib.Path(f"051.0/h00{i}.jpg"))
            for i in range(5)]
        actual = list(MangaTown.extract_images(html))
        self.assertListEqual(actual, expected)
        expected = 559
        actual = len(list(MangaTown.extract_pages(html)))
        self.assertEqual(actual, expected)

    def test_xkcd(self):
        html = load_html("xkcd.html")
        expected = [FileDownload(
            "https://imgs.xkcd.com/comics/machine_learning_captcha.png",
            pathlib.Path("2228.png"))]
        actual = list(Xkcd.extract_images(html))
        self.assertListEqual(actual, expected)
        expected = [PageDownload("https://xkcd.com/{}/".format(i))
                    for i in range(1, 2228) if i != 404]
        actual = list(Xkcd.extract_pages(html))
        self.assertListEqual(actual, expected)
