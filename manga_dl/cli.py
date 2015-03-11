"""Command line interface for the manga downloading package."""


import argparse
import logging
import os
import threading
import urllib.parse

from . import name, __version__ as version
from . import jobs


logger = logging.getLogger(__name__)


def check_url(string):
    """Check if the given string can be used as an url.  Return the string
    unchanged, if so.

    :string: the command line argument to check, a string
    :returns: the argument unchanged

    """
    url = urllib.parse.urlparse(string)
    if url.netloc is None or url.netloc == '':
        raise argparse.ArgumentError('This url is no good.')
    return string


def join_threads():
    """Wait for all currently running threads to finish.

    :returns: None

    """
    try:
        current = threading.current_thread()
        for thread in threading.enumerate():
            if thread != current:
                thread.join()
        logger.debug('All threads joined.')
    except:
        logger.info('Could not get current thread.  '
                    'Not waiting for other threads.')


def parse_commandline():
    """Parse the command line and return the namespace.
    :returns: TODO

    """
    parser = argparse.ArgumentParser(
        prog=name, description="Download manga from some websites.")
    # output group
    output = parser.add_argument_group(title='Output options')
    output.add_argument(
        '-v', '--verbose', action='count', default=1, help='verbose output')
    output.add_argument(
        '-q', '--quiet', dest='verbose', action='store_const', const=0,
        help='supress output')
    output.add_argument(
        '-x', '--debug', dest='verbose', action='store_const', const=100,
        help='debuging output')
    # general group
    general = parser.add_argument_group(title='General options')
    general.add_argument(
        '-b', '--background', action='store_true', help='fork to background')
    # can we hand a function to the parser to check the directory?
    general.add_argument(
        '-d', '--directory', metavar='DIR', default='.',
        help='the directory to work in')
    general.add_argument(
        '-f', '--logfile', metavar='LOG', default='manga.log',
        help='the filename of the logfile to use')
    general.add_argument(
        '-m', '--load-missing', action='store_true', dest='missing',
        help='''Load all files which are stated in the logfile but are
        missing on disk.''')
    # unimplemented group
    unimplemented = parser.add_argument_group('These are not yet implemented')
    # the idea for 'auto' was to find the manga name and the directory
    # automatically.
    unimplemented.add_argument(
        '-a', '--auto', action='store_true', default=True,
        help='do everything automatically')
    # or use the logfile from within for downloading.
    # idea for "archive": tar --wildcards -xOf "$OPTARG" "*/$LOGFILE"
    unimplemented.add_argument(
        '-A', '--archive', help='display the logfile from within an archive')
    unimplemented.add_argument('--view', help='create a html page')
    unimplemented.add_argument(
        '-r', '--resume', action='store_true', help='resume from a logfile')
    unimplemented.add_argument(
        '-R', '--resume-all', action='store_true',
        help='visit all directorys in the manga dir and resume there')
    # general group
    parser.add_argument(
        '-V', '--version', action='version', help='print version information',
        version='{} {}.{}.{}'.format(name, *version))
    parser.add_argument('name', nargs='?', metavar='url/name', type=check_url)
    args = parser.parse_args()
    # Make some sanity checks.
    if args.resume and (args.name is not None or args.missing):
        parser.error('You can only use -r or -m or give an url.')
    elif not args.resume and args.name is None and not args.missing:
        parser.error('You must specify -r or -m or an url.')
    setup_logger(args.verbose)
    logger.debug(
        'The parsed command line arguments are {}.'.format(args))
    try:
        args.directory = prepare_directory(args.directory)
    except FileExistsError:
        parser.error('Path exists but is not a directory.')
    except:
        parser.error('Strange error.')
    # Finally return the namespace.
    return args


def prepare_directory(path):
    """Prepare the download directory.

    :path: TODO
    :returns: TODO

    """
    if path != os.path.curdir and os.path.sep not in path:
        path = os.path.join(
            os.path.realpath(
                os.getenv("MANGADIR") or
                os.path.join(os.getenv("HOME"), "comic")),
            path
        )
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        os.mkdir(path)  # this can throw a FileExistsError.
    logger.debug('Directory set to "{}".'.format(path))
    return path


def setup_logger(level):
    """Set up the logging module with the given level.

    :level: a valid logging level
    :returns: TODO

    """
    levels = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG)
    try:
        level = levels[level]
    except IndexError:
        level = levels[-1]
    logging.basicConfig(
        format='%(name)s[%(threadName)s] %(asctime)s: %(msg)s',
        level=level)


def main():
    """Parse the command line, check the resulting namespace, prepare the
    environment and load the images.

    :returns: True

    """
    args = parse_commandline()
    # start downloading
    if args.resume_all:
        for dd in os.path.listdir(args.directory):
            for d in os.path.join(args.directory, dd):
                jobs.resume(os.path.join(args.directory, d))
    elif args.resume:
        jobs.resume(args.directory)
    elif args.missing:
        jobs.check(args.directory)
    else:
        jobs.load(args.name, args.directory)
    join_threads()
    logger.debug('Exiting ...')
    return True
