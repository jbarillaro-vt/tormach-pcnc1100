# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import pygtk,math,string
pygtk.require('2.0')
import gtk
import os
import sys
import constants


class numpad:
    def __init__(self, entry, qwerty=False, enter_takedown=True):
        self.qwerty = qwerty
        self.enter_takedown = enter_takedown
        self.entry = entry
        self.uparrow_button = None
        self.old_text = self.entry.get_text()
        self.enter_callback = None

        numeric_buttons = (
            (("7", self.numbers), ("8", self.numbers), ("9", self.numbers)),
            (("4", self.numbers), ("5", self.numbers), ("6", self.numbers)),
            (("1", self.numbers), ("2", self.numbers), ("3", self.numbers)),
            (("0", self.numbers), ("+/-", self.invert_sign), (".", self.dot)),
            ((" CLR ", self.clear), ("Bksp",self.bksp), ("Enter", self.enter))
        )

        qwerty_buttons = (
            (("q", self.letters), ("w", self.letters), ("e", self.letters), ("r", self.letters), ("t", self.letters), ("y", self.letters), ("u", self.letters), ("i", self.letters), ("o", self.letters), ("p", self.letters), ("UP", self.uparrow)),
            (("a", self.letters), ("s", self.letters), ("d", self.letters), ("f", self.letters), ("g", self.letters), ("h", self.letters), ("j", self.letters), ("k", self.letters), ("l", self.letters), ("#", self.letters), ("DN", self.downarrow)),
            (("z", self.letters), ("x", self.letters), ("c", self.letters), ("v", self.letters), ("b", self.letters), ("n", self.letters), ("m", self.letters), ("(", self.letters), (")", self.letters))
        )

        space_bar_buttons = (("+", self.letters), ("-", self.letters),  ("*", self.letters), ("Space", self.space_bar), ("/", self.letters), ("[", self.letters), ("]", self.letters))

        # clear the text entry under edit
        self.entry.set_text('')

        self.num_table = gtk.Table(3, 5)
        self.num_table.set_row_spacings(3)
        self.num_table.set_col_spacings(3)
        self.num_table.set_size_request(175, 250)


        y = 0
        for line in numeric_buttons:
            x = 0
            for item in line:
                button = gtk.Button(item[0])
                button.connect("clicked", item[1])
                button.set_size_request(46, 44)
                self.num_table.attach(button, x, x + 1, y, y + 1)
                x += 1
            y += 1

        if qwerty:
            self.qwerty_table = gtk.Table()
            self.qwerty_table.set_row_spacings(3)
            self.qwerty_table.set_col_spacings(3)

            self.space_bar_table = gtk.Table()
            self.space_bar_table.set_row_spacings(3)
            self.space_bar_table.set_col_spacings(3)

            self.qwerty_table.set_size_request(500, 200)
            self.space_bar_table.set_size_request(500, 55)

            y = 0
            for line in qwerty_buttons:
                x = 0
                for item in line:
                    button = gtk.Button(item[0])
                    if item[0] == "UP":
                        self.uparrow_button = button
                    elif item[0] == "DN":
                        self.downarrow_button = button
                    button.connect("clicked", item[1])
                    button.set_size_request(40, 40)
                    self.qwerty_table.attach(button, x, x + 1 , y, y + 1)
                    x += 1
                y += 1

            x = 0
            for item in space_bar_buttons:
                button = gtk.Button(item[0])
                button.connect("clicked", item[1])
                button.set_size_request(40, 50)
                if 'Space' in button.get_label():
                    button.set_size_request(230, 50)
                self.space_bar_table.attach(button, x, x + 1, 0, 1)
                x += 1

        self.fixed = gtk.Fixed()
        if qwerty:
            q_w, q_h = self.qwerty_table.get_size_request()
            n_w, n_h = self.num_table.get_size_request()
            s_w, s_h = self.space_bar_table.get_size_request()
            self.fixed.put(self.qwerty_table, 5, 10)
            self.fixed.put(self.num_table, q_w + 25, 17)
            self.fixed.put(self.space_bar_table, 5, q_h + 13)
            self.fixed.set_size_request(q_w + 25 + n_w + 20, 17 + n_h + 13)
        else:
            # numpad only
            w, h = self.num_table.get_size_request()
            self.fixed.put(self.num_table, 12, 8)
            self.fixed.set_size_request(12 + w + 12, 8 + h + 8)

        # accept real keyboard input
        self.fixed.connect("key_press_event", self.on_key_press)
        self.inside_run_method = False

    def set_enter_callback(self, callback):
        self.enter_callback = callback

    def set_popup_window(self, window):
        self.window = window

    def on_key_press(self, widget, event, data=None):
        kv = event.keyval
        #print 'press kv: %d, %s' % (kv, gtk.gdk.keyval_name(kv))

        # enter must be handled upon press event - release is not seen
        if kv in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            self.enter_action()
        # keys '0' through '9'
        elif (kv >= ord('0') and kv <= ord('9')) or (kv >= gtk.keysyms.KP_0 and kv <= gtk.keysyms.KP_9):
            if kv >= gtk.keysyms.KP_0 and kv <= gtk.keysyms.KP_9:
                kv = kv - gtk.keysyms.KP_0 + ord('0')
            self.append_entry(kv)
        # '.'
        elif kv == ord('.') or kv == gtk.keysyms.KP_Decimal:
            self.dot_action()
        # 'a' through 'z'
        elif (kv >= ord('a') and kv <= ord('z')) or (kv >= ord('A') and kv <= ord('Z')):
            self.append_entry(kv)
        # space
        elif kv == ord(' '):
            self.space_action()
        # other keys
        elif kv == ord('*') or kv == ord('(') or kv == ord(')') or kv == ord('#') or kv == ord('/') or kv == ord('[') or kv == ord(']'):
            self.append_entry(kv)
        # backspace
        elif kv == gtk.keysyms.BackSpace:
            self.bksp_action()
        # qwerty mode minus/plus
        elif (kv == gtk.keysyms.minus or kv == gtk.keysyms.plus or kv == gtk.keysyms.KP_Add or kv == gtk.keysyms.KP_Subtract):
            if kv == gtk.keysyms.KP_Add:
                kv = gtk.keysyms.plus
            elif kv == gtk.keysyms.KP_Subtract:
                kv = gtk.keysyms.minus
            self.append_entry(kv)
        # escape
        elif kv == gtk.keysyms.Escape:
            self.clear_action()
        # up arrow
        elif kv == gtk.keysyms.Up or kv == gtk.keysyms.KP_Up:
            self.uparrow_action()
        # down arrow (not displayed on the popup)
        elif kv == gtk.keysyms.Down or kv == gtk.keysyms.KP_Down:
            self.downarrow_action()

        return True

    def insert_at_cursor(self, text):
        position = self.entry.get_position()
        self.entry.insert_text(text, position)
        self.entry.grab_focus()
        self.entry.set_position(position + len(text))

    def append_entry(self, kv):
        self.entry.set_text(self.entry.get_text() + chr(kv))
        self.entry.grab_focus()
        self.entry.set_position(len(self.entry.get_text()))

    def enter_action(self):
        if self.enter_takedown:
            self.destroy()
        event = gtk.gdk.Event(gtk.gdk.KEY_PRESS)
        event.keyval = gtk.keysyms.Return
        self.entry.emit('key-press-event',event)
        self.entry.emit('activate')

    def destroy(self):
        if self.inside_run_method:
            gtk.main_quit()
        self.window.destroy()
        self.window = None

    # revert to old text and exit dialog
    def clear_action(self):
        self.entry.set_text(self.old_text)
        event = gtk.gdk.Event(gtk.gdk.KEY_PRESS)
        event.keyval = gtk.keysyms.Escape
        event.time = 0
        self.entry.emit("key-press-event", event)
        self.destroy()

    def numbers(self, button):
        text = button.get_label().strip()
        self.insert_at_cursor(text)

    def invert_sign(self, button):
        # invert sign of entry
        val = self.entry.get_text()
        if len(val) == 0:
            return
        if '-' == val[0]:
            val = val[1:]
        else:
            val = '-' + val
        self.entry.set_text(val)

    def dot_action(self):
        if self.qwerty or string.find(self.entry.get_text(), '.') <= 0:
            self.insert_at_cursor('.')

    def bksp_action(self):
        position = self.entry.get_position()
        self.entry.delete_text(position - 1, position)
        self.entry.grab_focus()
        if position != 0:
            self.entry.set_position(position - 1)
        else:
            self.entry.set_position(0)

    def space_action(self):
        self.insert_at_cursor(' ')

    def dot(self, widget):
        self.dot_action()

    def bksp(self, widget):
        self.bksp_action()

    def clear(self, button):
        self.clear_action()

    def letters(self, button):
        text = button.get_label().strip()
        self.insert_at_cursor(text)

    def space_bar(self, button):
        self.space_action()

    def uparrow_action(self):
        # this causes self.uparrow() to be called
        if self.uparrow_button:
            self.uparrow_button.emit("clicked")

    def downarrow_action(self):
        # this causes self.downarrow() to be called
        if self.downarrow_button:
            self.downarrow_button.emit("clicked")

    # TODO: 'emit' does not appear to function for Entry
    def uparrow(self, button):
        event = gtk.gdk.Event(gtk.gdk.KEY_PRESS)
        event.keyval = gtk.keysyms.Up
        self.entry.emit("key-press-event", event)

    def downarrow(self, button):
        event = gtk.gdk.Event(gtk.gdk.KEY_PRESS)
        event.keyval = gtk.keysyms.Down
        self.entry.emit("key-press-event", event)

    def enter(self, widget):
        self.enter_action()

    def size_request(self):
        return self.fixed.size_request()


class numpad_popup(numpad):
    def __init__(self, parentwindow, entry, qwerty=False, x=0, y=0, enter_takedown = True):
        numpad.__init__(self, entry, qwerty, enter_takedown)
        # CLR button becomes escape button
        for child in self.num_table.get_children():
            if 'CLR' in child.get_label():
                child.set_label(" ESC ")
#       Note: AVS - using WINDOW_TOPLEVEL results in a premature 'editing-canceled' signal being
#       put into the queue for this window, at least in the case where is 'editable' is associated
#       with a CellRendererText object. When 'gtk.main' is executed this signal is sent which
#       in turn pre-empts and stops an 'edited' signal being sent from the 'editable' to which is 
#       the target of the active numpad object. 
#       Window type of WINDOW_POPUP doesn;t seem to do this.
#       self.window = gtk.Window(type=gtk.WINDOW_TOPLEVEL)
        self.window = gtk.Window(type=gtk.WINDOW_POPUP)
        self.parentwindow = parentwindow
        self.set_popup_window(self.window)
        # setting the hint type to dialog keeps this window in front of the main UI screen (Z order)
        self.window.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        self.window.set_transient_for(parentwindow)
        self.window.set_destroy_with_parent(True)
        self.window.set_modal(True)
        self.window.set_resizable(False)
        self.window.set_decorated(False)
        self.window.set_position(gtk.WIN_POS_CENTER)
        background = gtk.Image()
        background.set_from_file(os.path.join(constants.GLADE_DIR, 'dark_background.jpg'))
        container = gtk.Fixed()
        container.put(background, 0, 0)
        container.put(self.fixed, 0, 0)
        if qwerty:
            self.window.set_size_request(710, 280)
        else:
            self.window.set_size_request(195, 270)
        xp,yp = self.window.get_position()
        self.window.move(xp + x, yp + y)
        self.window.add(container)

    def run(self):
        self.window.show_all()
        self.inside_run_method = True
        gtk.main()
        self.inside_run_method = False

        # Smack Gtk 2 in order to clue it in which window should be at the top of the z-order.
        # This is not needed by default if you create your top level modal window decorated (with a title bar).
        # But the soft keyboard never has that.
        self.parentwindow.present()
