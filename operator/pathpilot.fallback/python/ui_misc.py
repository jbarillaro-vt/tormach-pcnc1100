# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#
# UI misc funcitons that do NOT have any dependencies on stuff in
# ui_common or ui_support or tormach_mill_ui or tormach_lathe_ui, etc.
#
# The intent is this has nothing but clean non-Tormach imports and its the
# 'lowest level' UI library.
#
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

import gtksourceview2
import gtk
import time


# return (True, float) if the passed string can be successfuly cast to float
# and False, 0.0 if not
def is_number(s):
    try:
        val = float(s)
        return (True, val)
    except ValueError:
        return (False, 0.0)


class size():
    def __init__(self, cx=0, cy=0):
        self.cx = cx
        self.cy = cy

    def __str__(self):
        return "cx %d cy %d" % (self.cx, self.cy)


class point():
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y

    def __add__(self, pt):
        assert(isinstance(pt,point))
        self.x += pt.x
        self.y += pt.y
        return self

    def __str__(self):
        return "x %d y %d" % (self.x, self.y)


# get widget x/y positions
def get_x_pos(widget):
    container = widget.get_parent()
    return container.child_get_property(widget, "x")

def get_y_pos(widget):
    container = widget.get_parent()
    return container.child_get_property(widget, "y")

def get_xy_pos(widget):
    # returns a point object
    container = widget.get_parent()
    pt = point()
    pt.x = container.child_get_property(widget, "x")
    pt.y = container.child_get_property(widget, "y")
    return pt


def set_sourceview_gcode_syntaxcoloring(sourceview, enabled):
    # set the language for syntax highlighting manually for the buffer
    result = False
    try:
        if enabled:
            mgr = gtksourceview2.LanguageManager()
            if mgr:
                gcodelang = mgr.get_language("gcode")
                if gcodelang:
                    sourceview.set_language(gcodelang)
                    result = True
        else:
            sourceview.set_language(None)
            result = True
    except IOError:
        pass

    return result


def humanbytes(bytecount):
    'Return the given bytes as a human friendly KB, MB, GB, or TB string'
    B = float(bytecount)
    KB = float(1024)
    MB = float(KB**2)  # 1,048,576
    GB = float(KB**3)  # 1,073,741,824
    TB = float(KB**4)  # 1,099,511,627,776
    if B < KB:
        return '{0:d} {1}'.format(bytecount, 'bytes' if B > 1 else 'byte')
    elif KB <= B < MB:
        return '{0:.2f} KB'.format(B / KB)
    elif MB <= B < GB:
        return '{0:.2f} MB'.format(B / MB)
    elif GB <= B < TB:
        return '{0:.2f} GB'.format(B / GB)
    elif TB <= B:
        return '{0:.2f} TB'.format(B / TB)


def escape_markup(text):
    '''
    Parse text looking for characters that will confuse the pango markup engine and properly esacpe them out.
    e.g. <module> in the text would become &lt;module&gt;
    '''
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    return text



def force_window_painting():
    '''
    Update everything in the gtk/gdk/x11 stack such that all windows are properly painted
    This is a desperate attempt at re-creating the simple synchronous Win32 UpdateWindow(hwnd) api.
    This is used at times where the GUI thread has to do something for awhile and cannot service
    the main gtk event loop. So right before it goes off on a walkabout, it calls this to make
    sure the operator is informed.
    '''

    gtk.gdk.window_process_all_updates()

    # Documentation on these are poor, but I've tried a ton of things here to get this to work
    # reliably, none of which resulted in any behavior difference during testing. sigh.
    #
    # Force necessary window repainting to make sure message dialog is fully removed from screen
    # statusdlg.window.window.flush()
    # gtk.gdk.flush()
    # display = gtk.gdk.display_get_default()
    # display.flush()

    # pump the GTK event loop for awhile to make sure message dialog is fully painted on screen
    # the event_count limit is necessary because we've seen cases where gtk timeouts are scheduled
    # and they are always 'pending' so the event queue never fully drains such that events_pending()
    # becomes False.

    event_count = 0
    while gtk.events_pending() and event_count < 250:
        gtk.main_iteration(False)
        event_count += 1

    # sooooooo frustrating. for some reason we need to stick a sleep in here to get this reliable.
    # have no idea why. it is critical to have or the reliability of the window update degrades to "maybe".
    time.sleep(0.05)

    event_count = 0
    while gtk.events_pending() and event_count < 250:
        gtk.main_iteration(False)
        event_count += 1
