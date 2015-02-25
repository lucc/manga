'''TODO'''


import argparse
import logging
import os
import sys
import threading
import urllib.parse

from manga_dl.loader import Loader
from manga_dl import constants


logger = logging.getLogger(__name__)


def check_url(string):
    '''Check if the given string can be used as an url.  Return the string
    unchanged, if so.'''
    url = urllib.parse.urlparse(string)
    if url.netloc is None or url.netloc == '':
        raise BaseException('This url is no good.')
    return string


def download_missing(directory, logfile):
    '''
    Load all images which are mentioned in the logfile but not present in the
    directory.
    '''
    logfile = open(logfile, 'r')
    for index, line in enumerate(logfile.readlines()):
        url, img, filename = line.split(' ', 2)
        if not os.path.exists(filename):
            start_thread(download_image, (index, img, filename, logger))


def resume(directory, logfile):
    with open(logfile, 'r') as log:
        line = log.readlines()[-1]
    url = line.split()[0]
    logger.debug('Found url for resumeing: {}'.format(url))
    Loader(directory, logfile, url).start(url, after=True)


def resume_all():
    for dd in os.path.listdir(constants.directory):
        for d in os.path.join(constants.directory, dd):
            os.chdir(d)
            logger.info('Working in {}.'.format(os.path.realpath(
                os.path.curdir)))
            resume(os.path.join(constants.directory, d), 'manga.log')


def join_threads():
    try:
        current = threading.current_thread()
        for thread in threading.enumerate():
            if thread != current:
                thread.join()
        logger.debug('All threads joined.')
    except:
        logger.info('Could not get current thread. %s',
                    'Not waiting for other threads.')


def start_thread(*args, **kwargs):
    """Not implemented stub."""
    raise NotImplementedError()


def download_image(*args, **kwargs):
    """Not implemented stub."""
    raise NotImplementedError()


def main():
    '''Parse the command line, check the resulting namespace, prepare the
    environment and load the images.'''
    parser = argparse.ArgumentParser(
        prog=constants.name, description="Download manga from some websites.")
    # output group
    output = parser.add_argument_group(title='Output options')
    output.add_argument(
        '-x', '--debug', dest='verbose', action='store_const', const=100,
        help='debuging output')
    output.add_argument(
        '-v', '--verbose', action='count', help='verbose output')
    output.add_argument(
        '-q', '--quiet', dest='verbose', action='store_const', const=0,
        help='supress output')
    # general group
    general = parser.add_argument_group(title='General options')
    general.add_argument(
        '-b', '--background', action='store_true',
        help='fork to background')
    # can we hand a function to the parser to check the directory?
    general.add_argument('-d', '--directory', metavar='DIR', default='.',
                         help='the directory to work in')
    general.add_argument(
        '-f', '--logfile', metavar='LOG', default='manga.log',
        help='the filename of the logfile to use')
    general.add_argument(
        '-m', '--load-missing', action='store_true', dest='missing',
        help='''Load all files which are stated in the logfile but are
        missing on disk.''')
    # unimplemented group
    unimplemented = parser.add_argument_group(
        'These are not yet implemented')
    # the idea for 'auto' was to find the manga name and the directory
    # automatically.
    unimplemented.add_argument(
        '-a', '--auto', action='store_true', default=True,
        help='do everything automatically')
    # or use the logfile from within for downloading.
    # idea for "archive": tar --wildcards -xOf "$OPTARG" "*/$LOGFILE"
    unimplemented.add_argument(
        '-A', '--archive',
        help='display the logfile from within an archive')
    unimplemented.add_argument('--view', help='create a html page')
    unimplemented.add_argument(
        '-r', '--resume', action='store_true',
        help='resume from a logfile')
    unimplemented.add_argument(
        '-R', '--resume-all', action='store_true',
        help='visit all directorys in the manga dir and resume there')
    # general group
    parser.add_argument('-V', '--version', action='version',
                        version='{} {}.{}.{}'.format(constants.name,
                                                     *constants.version),
                        help='print version information')
    parser.add_argument('name', nargs='?', metavar='url/name',
                        type=check_url)
    args = parser.parse_args()
    if args.resume and (args.name is not None or args.missing):
        parser.error('You can only use -r or -m or give an url.')
    elif not args.resume and args.name is None and not args.missing:
        parser.error('You must specify -r or -m or an url.')

    # configure the logger
    levels = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG)
    try:
        level = levels[args.verbose]
    except IndexError:
        level = levels[-1]
    logging.basicConfig(
        format='%(name)s[%(threadName)s] %(asctime)s: %(msg)s',
        level=level)
    logger.debug(
        'The parsed command line arguments are {}.'.format(args))

    # set up the directory
    directory = args.directory
    # TODO can the directory be retrieved from the manga name?
    mangadir = os.path.curdir
    if not directory == os.path.curdir and os.path.sep not in directory:
        mangadir = constants.directory
        directory = os.path.realpath(os.path.join(mangadir, directory))
    if os.path.isdir(directory):
        pass
    else:
        try:
            os.mkdir(directory)
        except FileExistsError:
            parser.error('Path exists but is not a directory.')
    logger.debug('Directory set to "{}".'.format(directory))

    # start downloading
    if args.resume_all:
        resume_all()
    elif args.resume:
        resume(directory, args.logfile)
    elif args.missing:
        download_missing(directory, args.logfile)
    else:
        Loader(directory, args.logfile, args.name).start(args.name)
    join_threads()
    logger.debug('Exiting ...')
    sys.exit()
