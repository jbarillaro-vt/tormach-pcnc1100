# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import gtk
import time
import ui_misc

_stop_all_jogging_callback = None

def PlexiglassInitialize(stop_all_jogging_callback):
    global _stop_all_jogging_callback
    assert _stop_all_jogging_callback == None, "PlexiglassInitialize getting called multiple times, something wrong"
    _stop_all_jogging_callback = stop_all_jogging_callback

def PlexiglassInstance(window_to_cover, full_screen=True):
    # Be sure to top all jogging to prevent any runaway axis movement
    # this could happen because to get the damn watch cursor to show up and spin
    # we have to pause in here a little and pump the gtk main loop which can
    # end up using this GUI thread to make a periodic 50ms or 500ms timer callback.
    # and that can kick off a jog, but then the UI goes off and is busy for 10+ seconds
    # not servicing the loop and the jog cannot be stopped...

    global _stop_all_jogging_callback
    assert _stop_all_jogging_callback != None, "PlexiglassInitialize must be called prior to use!!"
    _stop_all_jogging_callback()

    return _Plexiglass(window_to_cover, full_screen)

def ConditionalPlexiglassInstance(needs_plexiglass, window_to_cover, full_screen=True):
    # Be sure to top all jogging to prevent any runaway axis movement
    # this could happen because to get the damn watch cursor to show up and spin
    # we have to pause in here a little and pump the gtk main loop which can
    # end up using this GUI thread to make a periodic 50ms or 500ms timer callback.
    # and that can kick off a jog, but then the UI goes off and is busy for 10+ seconds
    # not servicing the loop and the jog cannot be stopped...

    global _stop_all_jogging_callback
    assert _stop_all_jogging_callback != None, "PlexiglassInitialize must be called prior to use!!"
    _stop_all_jogging_callback()

    return _ConditionalPlexiglass(needs_plexiglass, window_to_cover, full_screen)



# Stacking a plexiglass up when there already is one causes strange drawing.
# So just keep track of this within the module
_plexiglass_up = False

# Sort of a hack to tell if plexy is up or not WITHOUT calling the instance methods
# above which have the side effect of stopping jogging.
def is_plexiglass_up():
    global _plexiglass_up
    return _plexiglass_up


class _Plexiglass():
    # Ideally this would use a transparent top level window (i.e. plexiglass) which can
    # catch and ignore all mouse and keyboard events and throw them away, but lets the user
    # see the current state of the app.  But transparent windows are fragile and seem to rely
    # on the union of X, GDK, GTK, X graphics drivers, window manager compositing, and phase of the
    # moon.  Even if we get it working, there is no guarantee that some controller in the
    # field doesn't work.
    #
    # So the next best alternative is to fake transparency by taking the current top level
    # window bitmap as a screenshot and drawing that as our top level window contents.
    # To the user it *looks* like the app is still visible, but in reality there is a
    # big fake plexiglass up with a watch cursor set that keeps them from going frantic
    # on the keyboard or mouse.

    def __init__(self, window_to_cover, full_screen=True):
        self.target_window = window_to_cover
        self.full_screen = full_screen
        self.plexiglass = None


    def show(self):
        assert self.plexiglass is None
        global _plexiglass_up
        if not _plexiglass_up:
            _plexiglass_up = True

            watch = gtk.gdk.Cursor(gtk.gdk.WATCH)

            # Force a fresh repaint so there are no window turds laying around on the screen
            # without this, there might be some remnant of a dialog frame not cleaned up yet and
            # when we screenshot the window, we get these ugly remnants.
            gdkwindow = self.target_window.window
            window_size = gdkwindow.get_size()
            rect = gtk.gdk.Rectangle(0, 0, window_size[0], window_size[1])
            gdkwindow.invalidate_rect(rect, True)

            # Force necessary window repainting to make sure the 'snapshot' we take is accurate
            ui_misc.force_window_painting()

            # Screenshot the target window
            pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, window_size[0], window_size[1])
            colormap = gdkwindow.get_colormap()
            if colormap is None:
                colormap = gtk.gdk.colormap_get_system()
            pixbuf = pixbuf.get_from_drawable(gdkwindow, colormap, 0, 0, 0, 0, window_size[0], window_size[1])
            background = gtk.Image()
            background.set_from_pixbuf(pixbuf)

            self.plexiglass = gtk.Window(gtk.WINDOW_TOPLEVEL)
            # setting the hint type to dialog keeps this window in front of the target window
            self.plexiglass.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
            self.plexiglass.set_transient_for(self.target_window)
            self.plexiglass.set_destroy_with_parent(True)
            self.plexiglass.set_decorated(False)
            self.plexiglass.set_resizable(False)
            self.plexiglass.set_modal(True)
            if self.full_screen:
                # TODO dynamically get size of display and use them.  This works for now for customer scenarios.
                self.plexiglass.set_size_request(1024, 768)
            else:
                # this is here for the dropbox_helper utility app which uses the classic Gtk theme with decorated windows
                # and title bars and such.  Throwing up a large plexiglass in front of that looks a little odd.
                self.plexiglass.set_size_request(window_size[0], window_size[1])
            self.plexiglass.set_position(gtk.WIN_POS_CENTER_ON_PARENT)

            # Add the Image of the target window as our top level window's content
            self.plexiglass.add(background)

            self.plexiglass.show_all()

            # The plexiglass window must be realized before you can set the cursor
            self.plexiglass.window.set_cursor(watch)

            # The watch cursor is animated and I'm guessing there is some timer that needs to
            # run at least once to get it reliable.  So that's what the hack of the tiny sleep is in
            # here.  Without it, we get the watch about 75% of the time.
            while gtk.events_pending():
                gtk.main_iteration()
            time.sleep(0.01)
            while gtk.events_pending():
                gtk.main_iteration()

            # Force necessary window repainting to make sure message dialog is fully removed from screen
            ui_misc.force_window_painting()


    def destroy(self):
        if self.plexiglass:
            self.plexiglass.destroy()

            self.plexiglass = None

            # Smack Gtk 2 in order to clue it in which window should be at the top of the z-order.
            # This is not needed by default if you create your top level modal window decorated (with a title bar).
            # But the title bar leaks access out to the window manager menu.
            self.target_window.present()

            ui_misc.force_window_painting()

            global _plexiglass_up
            _plexiglass_up = False


    def __enter__(self):
        """ Enter function returns a popup object when using the with statement. Ex:

            with plexiglass(...) as p:
                do something on main UI thread that takes a long time and is blocking

            This will automatically call the "__exit__" method and clean up the
            dialog, no matter what happens in the with block
        """
        self.show()
        return self


    def __exit__(self, type, value, traceback):
        """ Automatically called at the end of a with statement."""
        self.destroy()


class _ConditionalPlexiglass(_Plexiglass):
    # This variant of the plexiglass just makes it really easy to keep using
    # the with python syntax, but pass into the constructor a boolean
    # which tells us whether or not to really do anything.
    # Otherwise it makes the use of a plexiglass conditionally needlessly difficult.

    def __init__(self, needs_plexiglass, window_to_cover, full_screen=True):
        _Plexiglass.__init__(self, window_to_cover, full_screen)
        self.needs_plexiglass = needs_plexiglass

    def show(self):
        if self.needs_plexiglass:
            _Plexiglass.show(self)
