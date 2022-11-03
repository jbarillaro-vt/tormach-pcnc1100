# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import gtk
import pango
import os
import numpad
import tooltipmgr
from constants import *


class ImageButton(gtk.EventBox):
    """ The ImageButton is an extension of the design pattern used in the rest
    of the GUI. Instead of having a separate EventBox and Image, this class
    wraps the two of them together in one widget. This makes it much easier to
    add common methods to the class itself, and prevents a lot of code-copying.

    The ImageButton class behaves essentially the same as an eventbox, but you
    don't have to store a reference to the image separately.
    """

    __gtype_name__ = 'ImageButton'

    def __init__(self, image_file=None, name=None, x=0, y=0):
        """ Initialize the ImageButton.
            The image_file argument is an optional file name. If provided, the
            image file is loaded into a Gtk.Image and added as a child of the
            ImageButton. If the image file is not provided, then it is assumed that the button's "
            child" is its image (it's up to you or Glade to create the Image and add it).
        """
        gtk.EventBox.__init__(self)

        # Allow "two-way" toggling of button. Button is enabled if either entry
        # of the mask matches the latch state.
        # However, this isn't an event, so it won't work if you set the mask
        # directly. Use enable(1) to set the 2nd entry (and disable(1) to
        # disable it)
        self.mask = [False, False]
        self.latch_state = True

        # Load images from files to local pixbufs
        self.width = 0
        self.height = 0
        if image_file:
            self.load_image(image_file)

        #Default to enabled button
        self.enable()

        if name:
            self.set_name(name)

        self._orig_x = -1
        self._orig_y = -1

        # Set the default machine states where the button action can be performed
        self.permitted_states = STATE_IDLE | STATE_IDLE_AND_REFERENCED

        # an "invisible" window means that the eventbox only traps events, and
        # does not appear to the user directly.
        self.set_visible_window(False)

        # this lets us do grab_focus() to buttons so that we can treat the enter key
        # as a click
        self.set_flags(gtk.CAN_FOCUS | gtk.CAN_DEFAULT)
        self.connect("key-press-event", self.on_key_press_event)

        self.connect("button-press-event", self.on_button_press_event)
        self.connect("button-release-event", self.on_button_release_event)

        # Would be nice to auto-connect these, but critically need to set a builder ID also
        # so the lookup for the tooltip works.
        #self.connect("enter-notify-event", on_mouse_enter)
        #self.connect("leave-notify_event", on_mouse_leave)

    def __del__(self):
        if self.image:
            self.remove(self.image)
            self.image = None


    def on_key_press_event(self, widget, ev):
        # when we have keyboard focus, treat either enter key as a button click.
        if ev.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            # need both as the press usually shifts the image and the release unshifts it and is dependent on shift being done once before)
            self.emit('button-press-event', None)
            self.emit('button-release-event', None)


    @staticmethod
    def copy(source_button, image, name, place=True):
        try:
            new_image_button = ImageButton(image, name, source_button.x, source_button.y)
            source_width,source_height = source_button.get_size_request()
            new_image_button.set_size_request(source_width, source_height)
            if not place:
                return new_image_button
            source_parent = source_button.get_parent()
            source_parent.put(new_image_button, source_button.x, source_button.y)
        except:
            new_image_button = None
        return new_image_button


    def set_enable_from_mask(self):
        if self.latch_state in self.mask:
            state = self.latch_state
        else:
            state = not self.latch_state
        self.set_sensitive(state)


    def set_defaults(self):
        """ This function sets properties that are typically set by glade / gtk-builder.
            Use this if you're creating an ImageButton directly from python, rather than through Glade.
        """
        # Default the button to be visible (inspired by glade defaults)
        self.set_visible(True)

        # See documentation page:
        #   http://www.pygtk.org/pygtk2reference/class-gtkeventbox.html#method-gtkeventbox--get-above-child
        # Basically, make sure that event box captures events (not the
        # children)
        self.set_above_child(True)


    def on_button_press_event(self, widget, event, data=None):
        self.shift()
        ttmgr = tooltipmgr.TTMgr()
        if ttmgr:
            ttmgr.on_button_press(widget, event, data)

    def on_button_release_event(self, widget, data=None):
        self.unshift()


    @property
    def image(self):
        """ Get the child image of the button.
            By using a python property, the child image is accessible as if it were a class member. Ex:

                mybutton.image ---implies---> (EventBox).get_child()
        """
        return self.get_child()


    @image.setter
    def image(self, image_obj):
        """ Set the child image of the button.
            The "setter" method stores the image object locally so that it's
            preserved, and adds it as the child so that it can be accessed.
            This way, a locally-created image for a button can be accessed the
            same way as the default image.
        """
        #Store a local reference to the image
        #TODO reject bad images?
        self._image=image_obj

        # Check if an Image is already loaded in the button. If so, remove it
        # first to prevent a GTK warning
        if self.image:
            self.remove(self.image)
        self.add(image_obj)

        #KLUDGE add a suffix and give it a matching name to the button
        if self.name is not None:
            self._image.set_name(self.name+'_image')


    def enable(self,index=0):
        """ Wrap the set_sensitive method to make a button "sensitive" to
        inputs. Enable is a simple synonym for set_sensitive, which makes big
        blocks of code more readable."""
        self.mask[index] = True
        self.set_enable_from_mask()


    def disable(self, index=0):
        """ Wrap the set_sensitive method to make a button "insensitive", or grayed-out."""
        self.mask[index] = False
        self.set_enable_from_mask()


    def load_image(self, name, searchpath=None):
        """ Load an image from a name and optional path.

            From a file name, load up the image file into a new image object,
            and add it to the button as a child. This lets you create the image
            for a button separately from initializing the button.

            Ex:
                mybutton = ImageButton()
                mybutton.load_image('my_image_file.png')

                vs.

                mybutton = ImageButton('my_image_file.png')
        """
        # Use glade directory as default image location
        if searchpath is None:
            searchpath = GLADE_DIR

        img_path = os.path.join(searchpath, name)

        if os.path.isfile(img_path):
            self.image = gtk.image_new_from_file(img_path)
        else:
            raise IOError("Unable to find image file: {}".format(img_path))

        self.width = self.image.get_pixbuf().get_width()
        self.height = self.image.get_pixbuf().get_height()
        self.set_size_request(self.width, self.height)


    def shift(self):
        ImageButton.shift_button(self)


    def unshift(self):
        ImageButton.unshift_button(self)


    @staticmethod
    def shift_button(widget):
        # widget is probably a gtk.EventBox that was created from the glade file by a Builder.
        # so it doesn't use the shift_button() member below.
        # if the _orix_x and _orig_y attributes don't exist, add them to the object
        # and initialize them.
        if not hasattr(widget, "_orig_x"): setattr(widget, "_orig_x", -1)
        if not hasattr(widget, "_orig_y"): setattr(widget, "_orig_y", -1)

        container = widget.get_parent()
        x = container.child_get_property(widget, "x")
        y = container.child_get_property(widget, "y")

        # there was wonky bugs with trying to remember how far the button was shifted and then try to just shift it back
        # if you kept clicking a button it would crawl down the screen, but not consistently.
        # I think some of that may be because some button actions were double clicks, I'd sometimes see
        # two button press events and then one button release, etc.
        # once a button is clicked on, we don't ever dynamically position it somewhere else in the container (other than to
        # shift the image slightly).
        # so just remember the original location on the very first button click and always restore to that spot.
        # solves the bug easily.
        if widget._orig_x == -1: widget._orig_x = x
        if widget._orig_y == -1: widget._orig_y = y
        container.move(widget, x + 1, y + 1)

    @staticmethod
    def unshift_button(widget):
        container = widget.get_parent()
        if hasattr(widget, "_orig_x") and hasattr(widget, "_orig_y"):
            if widget._orig_x == -1 and widget._orig_y == -1:
                assert False, "shift_button() never called on widget"
            else:
                container.move(widget, widget._orig_x, widget._orig_y)
        else:
            assert False, "shift_button() never called on widget"
