#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import pygtk
pygtk.require("2.0")
import gtk
import gobject
import cairo

import os
import sys
import glob
import random
import timer

# this program is started by operator_login just before it calls the 'linuxcnc' script
# it finds all the *.png files under the ./image directory where this file is run from
# these images should be 1024x768 with the surrounding background transparent
# one command line parameter controls the dwell between image changes - default is 2 seconds
# this program will terminate upon a mouse click on the image
# typically it will be killed by the UI once it's loaded and initialized

# this is the directory where this script is running from
PROGRAM_DIR = os.path.abspath(os.path.dirname(sys.argv[0]))


class splash():

    def __init__(self, timeout_ms):

        self.stopwatch = timer.Stopwatch()
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_decorated(False)
        self.window.set_default_size(1024, 768)
        self.window.set_events(gtk.gdk.ALL_EVENTS_MASK)
        self.window.set_position(gtk.WIN_POS_CENTER_ALWAYS)
        self.window.set_app_paintable(True)

        # you really need to test this under both compositing and non-compositing window managers and X configurations.
        # on Mint 17.3, the fastest way was to re-launch the marco window manager between these two commands:
        #
        #   marco --composite --replace &
        #   marco --no-composite --replace &

        if self.window.is_composited():
            screen = self.window.get_screen()
            colormap = screen.get_rgba_colormap()
            if colormap == None:
                colormap = screen.get_rgb_colormap()
            gtk.widget_set_default_colormap(colormap)

        # this is basically the 'paint' signal
        self.window.connect("expose_event", self.on_expose_event)

        # click on image to terminate
        # otherwise wait for UI to kill this process
        self.window.connect("button_press_event", lambda w,e: gtk.main_quit())

        # look for the images and load them all at once
        imagesearchpath = os.path.join(PROGRAM_DIR, 'images', 'Machine*.png')
        self.image_pixbufs = []
        for filename in glob.glob(imagesearchpath):
            if os.path.isfile(filename):
                self.image_pixbufs.append(gtk.gdk.pixbuf_new_from_file(filename))

        # randomize the image order
        random.shuffle(self.image_pixbufs)
        self.current_image_index = 0

        if not self.window.is_composited():
            # we'll need the background image to do the compositing ourselves in this case
            backgroundimagefilepath = os.path.join(PROGRAM_DIR, 'images', 'Tormach-Wallpaper.png')
            self.background_image = gtk.gdk.pixbuf_new_from_file(backgroundimagefilepath)

        # setup the timer to flip between images
        gobject.timeout_add(timeout_ms, self.on_timer_expire)


    def on_expose_event(self, widget, event):
        # if the window manager and X are not compositing, this will get called all the time for
        # even partial window area reveals just like old WM_PAINT Win32 messages
        # but in the compositing case, the window manager must be caching the entire bitmap of the
        # window and unless something is forcing an invalidation, it never needs to call this.

        ctx = self.window.window.cairo_create()

        ctx.save()

        # restrict drawing to just the expose area for speed
        ctx.rectangle(event.area.x, event.area.y, event.area.width, event.area.height)
        ctx.clip()

        if self.window.is_composited():
            ctx.set_source_rgba(0, 0, 0, 0)
            ctx.set_operator(cairo.OPERATOR_SOURCE)
            ctx.paint()
            ctx.set_source_pixbuf(self.image_pixbufs[self.current_image_index], 0, 0)
            ctx.paint()

        else:
            # when we cannot rely on the window manager and X to do the right thing
            # with alpha channels and buggy clipping regions, just do it ourselves.
            # we take the big desktop background and composite our image on top of it
            # off screen and then blit the result to the window.
            # dead simple and works reliably and looks better than the clipping region
            # solution anyway because the semi-transparent alpha edges of the machine
            # images are properly composited.
            ctx.set_source_pixbuf(self.background_image, 0, 0)
            ctx.paint()
            ctx.set_source_pixbuf(self.image_pixbufs[self.current_image_index], 0, 0)
            ctx.paint()

        ctx.restore()

        return False


    def on_timer_expire(self):
        # move to the next image
        self.current_image_index = (self.current_image_index + 1) % len(self.image_pixbufs)

        self.window.queue_draw()   # invalidate the window to force an 'expose' event

        # safeguard - there is no situation where the splash should be up for more than 60 seconds...
        if self.stopwatch.get_elapsed_seconds() >= 60:
            gtk.main_quit()
            return False

        return True     # keep the timer running


if __name__ == "__main__":
    image_display_time_ms = 2000

    if len(sys.argv) > 1:
        # fetch image filename(s) from command line
        image_display_time_ms = int(sys.argv[1]) * 1000

    mysplash = splash(image_display_time_ms)
    mysplash.window.show_all()

    gtk.main()
