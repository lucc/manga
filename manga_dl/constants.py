'Collection of "constants" for manga-dl.'


import os


# constants
version = (0, 2, 0)
name = 'manga-dl'
# variables
directory = os.path.realpath(os.getenv("MANGADIR") or
                             os.path.join(os.getenv("HOME"), "comic"))
