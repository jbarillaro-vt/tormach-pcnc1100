# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import gettext
import locale
import os
import constants

def _UT(str):
    '''
    This is a way we can use strings within the source code and MARK them
    so that all developers realize that they are "Untranslated Text" that should
    never be localized.  Otherwise without some way of marking a string,
    you don't know if somebody overlooked translation or not.
    '''
    return str


def init_localization(newlocale):
    '''
    Initialize a locale and install relevant string resources into the runtime
    Setups up the proper POSIX locale stuff so that date functions and such
    support the right behavior as well.
    '''
    locale.setlocale(locale.LC_ALL, newlocale)

    loc = locale.getlocale()
    print "Using locale {0}".format(loc)

    # We use parts of the official locale name to find the resource files
    # that contain the translated strings and install them into the runtime.
    # These are *.mo files and are located in a python/res subdirectory.

    filename = os.path.join(constants.RES_DIR, 'pathpilot_%s.mo' % loc[0][0:2])
    try:
        with open(filename, 'rb') as fp:
            translate = gettext.GNUTranslations(fp)
    except IOError as ex:
        print ex
        # This is a fallback translation which doesn't do any translation, pass through dict really
        translate = gettext.NullTranslations()

    translate.install()
