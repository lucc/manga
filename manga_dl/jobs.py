'''TODO'''


import logging
import os


from .loader import Loader


logger = logging.getLogger(__name__)


def load(url, directory='.'):
    """Load images starting from the given url.

    :url: the url from which to start loading (string)
    :directory: the directory to save images to (string)
    :returns: None

    """
    Loader(directory, 'manga.log', url).start(url)


def resume(directory='.'):
    """Resume downloading in the given directory.  The log file will be examined
    to find the url to load and then load() will be called.

    :directory: the directory to get the log file and save the images
    :returns: None

    """
    with open(os.path.join(directory, 'manga.log'), 'r') as log:
        line = log.readlines()[-1]
    url = line.split()[0]
    logger.debug('Found url for resumeing: {}'.format(url))
    Loader(directory, 'manga.log', url).start(url, after=True)


def rename(directory='.'):
    """Rename the files in the given directory by padding chapter and page
    numbers with zeros.

    :directory: the directory to work in
    :returns: None

    """
    raise NotImplementedError()


def check(directory='.'):
    """Check all files in the given directory and load missing images and fix
    filenames.

    :directory: the directory to work in
    :returns: None

    """
    raise NotImplementedError()
