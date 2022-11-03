#!/usr/bin/env python

import gtk, glib
from hal import *
from tormach_console import TormachConsoleInputDevice, HalWrapper
import errors

eh = errors.error_handler_base()

class ConsoleTest(gtk.Window):
    def __init__(self):
        super(ConsoleTest, self).__init__()

        self.hal_component = component("consoletest")
        self.hal_component.setprefix("TCTest")
        self.wrapper = HalWrapper(self.hal_component)
        
        self.set_title("Tormach Console Test")
        self.set_size_request(500, 600)
        self.set_position(gtk.WIN_POS_CENTER)

        self.test_components = []
        
        parent_layout = gtk.VBox()

        for wheel in TormachConsoleInputDevice.wheels:
            wtest = WheelTest(TormachConsoleInputDevice.codes[wheel], self.wrapper)
            
            self.test_components.append(wtest)
            parent_layout.pack_start(wtest, expand=False, padding=2)
        hsep = gtk.HSeparator()
        parent_layout.pack_start(hsep, expand=False, padding=5)

        for absolute in TormachConsoleInputDevice.absolute:
            wtest = AbsTest(TormachConsoleInputDevice.codes[absolute], self.wrapper)
            
            self.test_components.append(wtest)
            parent_layout.pack_start(wtest, expand=False, padding=2)
        hsep = gtk.HSeparator()
        parent_layout.pack_start(hsep, expand=False, padding=5)

        for button in [TormachConsoleInputDevice.codes[button] for button in TormachConsoleInputDevice.buttons] + ["axis.0.enabled","axis.1.enabled","axis.2.enabled","axis.3.enabled"]:
            wtest = ButtonTest(button, self.wrapper)
            
            self.test_components.append(wtest)
            parent_layout.pack_start(wtest, expand=False)
        hsep = gtk.HSeparator()
        parent_layout.pack_start(hsep, expand=False, padding=5)

        for multi in ['step-select-counts']:
            wtest = MultiswitchTest(multi, self.wrapper, 3)
            
            self.test_components.append(wtest)
            parent_layout.pack_start(wtest, expand=False)
        hsep = gtk.HSeparator()
        parent_layout.pack_start(hsep, expand=False, padding=5)

        #Test for RGB leds on console face
        wtest = RGBTest(['led.red', 'led.green', 'led.blue'], self.wrapper)

        self.test_components.append(wtest)
        parent_layout.pack_start(wtest, expand=False)
        hsep = gtk.HSeparator()
        parent_layout.pack_start(hsep, expand=False, padding=5)

        #Test which aggregates the results of all other tests
        # wtest = AllPassTest(self.test_components)

        # self.test_components.append(wtest)
        # parent_layout.pack_start(wtest, expand=False)
        # hsep = gtk.HSeparator()
        # parent_layout.pack_start(hsep, expand=False, padding=5)
        
        self.connect("destroy", gtk.main_quit)
        
        self.add(parent_layout)
        self.show_all()

        self.wrapper.newpin("console-device-connected",HAL_BIT, HAL_IN)

        self.hal_component.ready()

        glib.timeout_add(50, self.update_all)

    def unload(self):
        self.hal_component.exit()

    def update_all(self):
        if(self.wrapper["console-device-connected"]):
            for test in self.test_components:
                test.update()
        return True

class PassableTest(object):
    def is_passed(self):
        return hasattr(self, "passed") and self.passed == True

    def do_pass(self):
        self.passed = True


class WheelTest(PassableTest, gtk.HBox):
    def __init__(self, hal_name, hal_wrapper, target=200.0):
        super(WheelTest, self).__init__()
        self.wrapper = hal_wrapper
        self.hal_name = hal_name
        self.wrapper.newpin("{}".format(self.hal_name),HAL_S32, HAL_IN)
        self.starting_value = None
        self.target = target

        self.image = gtk.Image()
        self.image.set_from_stock(gtk.STOCK_NO, gtk.ICON_SIZE_LARGE_TOOLBAR)
        
        label = gtk.Label(self.hal_name)
        self.progress = gtk.ProgressBar()
        self.progress.set_text("0 steps")
        self.pack_start(self.image, expand=False)
        self.pack_start(label, expand=False, padding=5)
        self.pack_start(self.progress, expand=True)

    def update(self):
        current_value = self.wrapper["{}".format(self.hal_name)]
        if self.starting_value == None:
            self.starting_value = current_value
        self.progress.set_text("{} steps".format(current_value - self.starting_value))
        if (current_value - self.starting_value) > self.target:
            self.image.set_from_stock(gtk.STOCK_YES, gtk.ICON_SIZE_LARGE_TOOLBAR)
            self.do_pass()
        self.progress.set_fraction(max(min(((current_value - self.starting_value) / self.target), 1.0), 0.0))

class AbsTest(PassableTest, gtk.HBox):
    def __init__(self, hal_name, hal_wrapper, target=0.05):
        super(AbsTest, self).__init__()
        self.wrapper = hal_wrapper
        self.hal_name = hal_name
        self.wrapper.newpin("{}".format(self.hal_name),HAL_FLOAT, HAL_IN)
        self.min_value = 1.0
        self.max_value = 0.0
        self.target = target

        self.image = gtk.Image()
        self.image.set_from_stock(gtk.STOCK_NO, gtk.ICON_SIZE_LARGE_TOOLBAR)
        
        label = gtk.Label(self.hal_name)
        self.progress = gtk.ProgressBar()
        self.progress.set_text("0%")
        self.pack_start(self.image, expand=False)
        self.pack_start(label, expand=False, padding=5)
        self.pack_start(self.progress, expand=True)

    def update(self):
        current_value = self.wrapper["{}".format(self.hal_name)]
        self.min_value = min(current_value, self.min_value)
        self.max_value = max(current_value, self.max_value)
        self.progress.set_text("{}%".format(current_value*100))
        if self.min_value < self.target and self.max_value > (1.0 - self.target):
            self.image.set_from_stock(gtk.STOCK_YES, gtk.ICON_SIZE_LARGE_TOOLBAR)
            self.do_pass()
        self.progress.set_fraction(max(min(current_value,1.0), 0.0))

class ButtonTest(PassableTest, gtk.HBox):
    def __init__(self, hal_name, hal_wrapper, target=0.05):
        super(ButtonTest, self).__init__()
        self.wrapper = hal_wrapper
        self.hal_name = hal_name
        self.wrapper.newpin("{}".format(self.hal_name),HAL_BIT, HAL_IN)
        self.min_value = 1
        self.max_value = 0
        self.target = target

        self.image = gtk.Image()
        self.image.set_from_stock(gtk.STOCK_NO, gtk.ICON_SIZE_LARGE_TOOLBAR)
        
        label = gtk.Label(self.hal_name)
        self.pack_start(self.image, expand=False)
        self.pack_start(label, expand=False, padding=5)

    def update(self):
        current_value = self.wrapper["{}".format(self.hal_name)]
        self.min_value = min(current_value, self.min_value)
        self.max_value = max(current_value, self.max_value)
        if self.min_value < self.target and self.max_value > (1.0 - self.target):
            self.image.set_from_stock(gtk.STOCK_YES, gtk.ICON_SIZE_LARGE_TOOLBAR)
            self.do_pass()

class MultiswitchTest(PassableTest, gtk.HBox):
    def __init__(self, hal_name, hal_wrapper, positions=4):
        super(MultiswitchTest, self).__init__()
        self.wrapper = hal_wrapper
        self.hal_name = hal_name
        self.wrapper.newpin(self.hal_name,HAL_S32, HAL_IN)
        self.positions = positions

        self.images = [gtk.Image() for i in range(self.positions)]
        self.test_results = [False for i in range(self.positions)]
        for image in self.images:
            image.set_from_stock(gtk.STOCK_NO, gtk.ICON_SIZE_LARGE_TOOLBAR)
            self.pack_start(image, expand=False)
        
        label = gtk.Label(self.hal_name)
        
        self.pack_start(label, expand=False, padding=5)

    def update(self):
        current_value = self.wrapper["{}".format(self.hal_name)]
        if(current_value <= len(self.images)+1):
            self.images[current_value].set_from_stock(gtk.STOCK_YES, gtk.ICON_SIZE_LARGE_TOOLBAR)
            self.test_results[current_value] = True
        if False not in self.test_results:
            self.do_pass()

class AllPassTest(PassableTest, gtk.HBox):
    def __init__(self, tests):
        super(AllPassTest, self).__init__()
       
        self.tests = tests
        self.image = gtk.Image()
        self.image.set_from_stock(gtk.STOCK_NO, gtk.ICON_SIZE_LARGE_TOOLBAR)
        
        label = gtk.Label("All Tests Passed")
        self.pack_start(self.image, expand=False)
        self.pack_start(label, expand=False, padding=5)

    def update(self):
        all_pass = False
        for test in tests:
            all_pass = all_pass and test.is_passed()
        if all_pass:
            self.image.set_from_stock(gtk.STOCK_YES, gtk.ICON_SIZE_LARGE_TOOLBAR)
            self.do_pass()

class RGBTest(PassableTest, gtk.HBox):
    def __init__(self, hal_names, hal_wrapper):
        super(RGBTest, self).__init__()
        self.wrapper = hal_wrapper
        self.hal_names = hal_names

        self.image = gtk.Image()
        self.image.set_from_stock(gtk.STOCK_YES, gtk.ICON_SIZE_LARGE_TOOLBAR)
        
        label = gtk.Label("LEDs")
        self.pack_start(self.image, expand=False)
        self.pack_start(label, expand=False, padding=5)

        for hal_name in self.hal_names:
            self.wrapper.newpin(hal_name,HAL_BIT, HAL_OUT)
            check = gtk.CheckButton(hal_name)
            def set_led(widget, pin):
                self.wrapper[pin] = widget.get_active()
            check.connect('toggled', set_led, hal_name)
            self.pack_start(check, expand=False, padding=5)

    def update(self):
        pass

if __name__ == "__main__":
    try:
        test = ConsoleTest()
        gtk.main()
    except KeyboardInterrupt:
        eh.log("THCSim : caught KeyboardInterrupt, hal comp shutting down.")
    test.unload()