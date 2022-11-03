#!/usr/bin/env python
#    Copyright 2018 Tormach, Inc
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

from hal import *
import evdev
from evdev import ecodes, _input, util
from select import select
from itertools import count, ifilterfalse
import errors
import constants
import time
import os
import sys
import datetime


# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

NUMBER_SUPPORTED = 1

class UpdatableInputDevice(evdev.InputDevice):
    def forceHIDUpdate(self):
        """
        Update _rawcapabilties, which contains the max, min, and value for each absolute axis
        """
        self._rawcapabilities = _input.ioctl_capabilities(self.fd)

    def keys(self, verbose=True):
        """
        Force an update of the keys and buttons on this device. Returns the codes of the buttons that are currently pressed
        """
        keys = _input.ioctl_EVIOCG_bits(self.fd, ecodes.EV_KEY)
        if verbose:
            return util.resolve_ecodes(ecodes.keys, keys)
        return keys

def tohalname(s): return str(s).lower().replace("_", "-")

class HalWrapper:
    def __init__(self, comp):
        self._comp = comp
        self._pins = set()
        self._params = set()

    def newpin(self, *args):
        self._pins.add(args[0])
        return self._comp.newpin(*args)
    def newparam(self, *args):
        self._params.add(args[0])
        return self._comp.newparam(*args)

    def __getitem__(self, k):
        return self._comp[k]

    def __setitem__(self, k, v):
        if k in self._params:
            self._comp[k] = v; return
        elif k in self._pins:
            self._comp[k] = v; return
        else:
            raise KeyError, k


class TormachConsoleInputDevice(object):
    codes = {
        'BTN_0': "button.feedhold",
        'BTN_1': "button.cycle-start",
        'BTN_2': "button.hold2run",
        'BTN_3': "switch.mode-select",
        'BTN_4': "switch.defeatured-mode",
        'BTN_5': "button.pendant-1",
        'BTN_6': "button.pendant-2",
        'ABS_RX':"axis-select",
        'ABS_RY':'step-select',
        'ABS_X':'feed-override',
        'ABS_Y':'rpm-override',
        'ABS_Z':'rapid-override',
        'ABS_MISC':"pendant-knob",
        'ABS_WHEEL':'jog-wheel',
        'ABS_GAS':'jog-wheel-2',
        'LED_NUML': "led.ready",
        'LED_CAPSL': "led.board",
        'LED_SCROLLL': "led.red",
        'LED_COMPOSE': "led.green",
        'LED_KANA': "led.blue"
    }
    buttons = ['BTN_0', 'BTN_1', 'BTN_2', 'BTN_3', 'BTN_5', 'BTN_6']
    jumpers = ['BTN_4']
    leds = ['LED_NUML', 'LED_CAPSL', 'LED_SCROLLL', 'LED_COMPOSE', 'LED_KANA']
    absolute = ['ABS_X', 'ABS_Y', 'ABS_Z', 'ABS_MISC']
    wheels = ['ABS_WHEEL', 'ABS_GAS']

    def __init__(self, error_handler, wrapped_comp, index, event_device):
        self._eh = error_handler
        self._event_device = event_device
        self.wrapped_comp = wrapped_comp
        self.index = index
        self.last_jog_count = {}
        # self.codes os the mapping of HID device inputs to HAL pins

        for button in self.buttons + self.jumpers:
            self.newpin(self.codes[button], HAL_BIT, HAL_OUT)
            # The latch pin is an IO pin, so that UI components can keep track of whether a given button press has been responded to
            # It is set to True on a key release event and can be cleared to False by the UI once it has responded to the key press
            self.newpin("%s-latch" % self.codes[button], HAL_BIT, HAL_IO)
            self.set(self.codes[button], 0)
            self.set(self.codes[button] + "-latch", 0)

        for led in self.leds:
            self.newpin(self.codes[led], HAL_BIT, HAL_IN)
            self.newpin("%s-invert" % self.codes[led], HAL_BIT, HAL_IN)
            self.set(self.codes[led], 0)
            self.set(self.codes[led] + "-invert", 0)

        self.newpin("%s-counts" % self.codes['ABS_RX'], HAL_S32, HAL_OUT)
        for i in range(4):
            self.newpin("%s" % "axis.{}.enabled".format(i), HAL_BIT, HAL_OUT)

        self.newpin("%s-counts" % self.codes['ABS_RY'], HAL_S32, HAL_OUT)
        self.newpin("%s-value" % self.codes['ABS_RY'], HAL_FLOAT, HAL_OUT)
        self.newpin("%s-scale" % self.codes['ABS_RY'], HAL_FLOAT, HAL_IN)
        self.set(self.codes['ABS_RY'] + "-scale", 0.0001)
        for i in range(4):
            self.newpin("%s" % "step-select.{}.enabled".format(i), HAL_BIT, HAL_OUT)

        for wheel in self.wheels:
            self.newpin("%s-counts" % self.codes[wheel], HAL_S32, HAL_OUT)
            self.newpin("%s-counts-adjusted" % self.codes[wheel], HAL_S32, HAL_OUT)

        for name in [self.codes[code] for code in self.absolute]:
            self.newpin("%s-position" % name, HAL_FLOAT, HAL_OUT)
            self.newpin("%s-counts" % name, HAL_S32, HAL_OUT)
            self.newpin("%s-scale" % name, HAL_FLOAT, HAL_IN)
            self.newpin("%s-center" % name, HAL_FLOAT, HAL_IN)
            self.newpin("%s-flat" % name, HAL_FLOAT, HAL_IN)
            self.set(name + "-counts", 0)
            self.set(name + "-position", 0)
            # scale is the number of raw counts that translates to a change of 1.0 for "position"
            # For example, a scale of 512 would mean a counts value of 1024 would be 2.0
            # we set it a little smaller to give some deadzone on the ends of travel
            self.set(name + "-scale", 480)
            # "center" is the value that represents 50% of knob travel in output units
            self.set(name + "-center", 1.0)
            # "flat" is the deadzone around "center" where the value is set to center
            self.set(name + "-flat", 0.05)

    def handleUpdateEvent(self, event):
        event = evdev.categorize(event)
        if isinstance(event, evdev.KeyEvent):
            code = event.keycode
            if not isinstance(code, basestring):
                code = code[0] #sometimes multiple keycodes are returned for one button
            if code in self.codes:
                self.set(self.codes[code], event.keystate != 0)
                # set the latch pin on a key down event.  use case is stabbing the physical feedhold button
                # as a panic and you really want it to stop on the button push, not release.
                if (event.keystate == event.key_down):
                    self.set(self.codes[code] + "-latch", 1)
        # pylint: disable=no-member
        if isinstance(event, evdev.AbsEvent) and ecodes.ABS[event.event.code] in self.wheels:
            # Jog wheel
            jog_count = event.event.value
            ecode = ecodes.ABS[event.event.code]
            # if we have no previous value to delta from, just record this as the current position
            if(ecode not in self.last_jog_count):
                self.last_jog_count[ecode] = jog_count
            else:
                halname = self.codes[ecode]
                # we need to account for the fact that the encoder goes from 0 to 2^16
                # when turned in the negative direction past 0
                # and from 2^16 back to 0 when it overflows
                delta = jog_count - self.last_jog_count[ecode]
                if(delta > 2**15):
                    #if we underflowed the encoder
                    delta = delta - 2 ** 16
                elif(delta < -(2**15)):
                    #if we overflowed the encoder
                    delta = delta + 2 ** 16
                countDiv = 4
                self.last_jog_count[ecode] = jog_count

                current_value = self.get(halname + "-counts") + delta
                self.set(halname + "-counts", current_value)
                self.set(halname + "-counts-adjusted", current_value / countDiv)
        elif isinstance(event, evdev.AbsEvent) and ecodes.ABS[event.event.code] in self.codes:
            self.set(self.codes[ecodes.ABS[event.event.code]] + "-counts", event.event.value)


    def readEvents(self):
        for event in self._event_device.read():
            self.handleUpdateEvent(event)
        self.doHALUpdates()

    def doForcedUpdate(self):
        #force an update, which grabs to current position of each abs axis including the jog encoder
        self._event_device.forceHIDUpdate()

        #create fake events for all keys that are pressed
        # This doesn't create fake keyRelease events for the keys that are not pressed, because it would cause weird "latch" logic
        # if needed, that could be changed in the future
        for key in self._event_device.keys():
            #print key
            event = evdev.InputEvent(0,0,ecodes.EV_KEY,key[1],0x1)
            self.handleUpdateEvent(event)

        #create fake event with the current position of each absolute axis
        for absData in self._event_device.capabilities()[ecodes.EV_ABS]:
            event = evdev.InputEvent(0,0,ecodes.EV_ABS, absData[0], absData[1].value)
            #print event
            self.handleUpdateEvent(event)

    def doLEDUpdate(self):
        current_active_leds = [l[0] for l in self._event_device.leds(verbose=True)]
        #write led values
        for led in self.leds:
            value = led in current_active_leds
            #if this name is in the active list, then the value is True
            halname = self.codes[led]
            hal_val = self.wrapped_comp["%s.%s" % (self.index, halname)] != self.wrapped_comp["%s.%s-invert" % (self.index, halname)]
            if hal_val != value:
                self._event_device.set_led(ecodes.ecodes[led], not value)


    def doHALUpdates(self):
        """
        Update calculated HAL pins based on the values from handleUpdateEvent

        This means calculating the "position" value for ABS axes, as well as setting axis enabled pins
        """
        # axis select
        halname = self.codes['ABS_RX']
        value = self.get(halname + "-counts") - 1
        # counts starts from 0 for OFF, so shift it so -1 is OFF and 0 is X etc
        for i in range(4):
            self.set("axis.{}.enabled".format(i), 0)
        # Make sure this is a valid axis for the hauto to enable, otherwise don't enable one at all
        if value in range(4):
            self.set("axis.{}.enabled".format(value), 1)

        # step select
        halname = self.codes['ABS_RY']
        value = self.get(halname + "-counts")
        scale = self.get(halname + "-scale")
        self.set(halname + "-value", scale * 10**value)


        # override knobs
        for code in self.absolute:
            name = self.codes[code]
            value = self.get(name + "-counts")
            scale = self.get(name + "-scale") or 1
            center = self.get(name + "-center")
            flat = self.get(name + "-flat")
            # center of the range in counts
            center_counts = 1024 / 2
            #calculate a position relative to the center of knob travel
            position = center + (value - center_counts) / scale
            position = round(position, 2)
            position = max(min(center*2, position), 0)
            if (center-flat) <= position <= (center+flat):
                position=center
            self.set(name + "-position", position)


    def get(self, name):
        name = "%s.%s" % (self.index, name)
        return self.wrapped_comp[name]

    def set(self, name, value):
        name = "%s.%s" % (self.index, name)
        self.wrapped_comp[name] = value

    def newpin(self, name, *args):
        name = "%s.%s" % (self.index, name)
        if name not in self.wrapped_comp._pins:
            self.wrapped_comp.newpin(name, *args)

    def device_connected(self):
        return self._event_device != None

    @property
    def event_device(self):
        return self._event_device

    @event_device.setter
    def event_device(self, event_device):
        self._event_device = event_device
        # when we change devices, we need to reset the jog wheel raw counts to 0
        # to avoid a possible huge jump
        #self._eh.log("TormachConsole : Changing connected device, resetting jog wheel counts to 0")
        self.last_jog_count = {}



def connected_devices():
    return [dev for dev in devices if dev.device_connected()]


#If we have new USB devices, we find the first TormachConsoleInputDevice where event_device==None
#and set the event_device to the new device
def check_for_devices(eh):
    device_list = [dev for dev in [UpdatableInputDevice(path) for path in evdev.list_devices()] if (dev.name=="FranksWorkshop Generic HID Device" or dev.name=="Tormach Console Controller")]
    for dev in device_list:
        if dev not in [idev.event_device for idev in devices]:
            indexes = [idev.index for idev in devices if idev.device_connected()]
            try:
                next_index = next(ifilterfalse(set(indexes).__contains__, range(NUMBER_SUPPORTED)))
            except StopIteration as e:
                eh.log("TormachConsole : More console devices were plugged in than are supported on this system.")
            devices[next_index].event_device = dev
            #devices[next_index].doForcedUpdate()
    #eh.log("TormachConsole : {:d} console devices found.".format(len(connected_devices())))



if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(),'w',0)

    eh = errors.error_handler_base()  # use the simple version without UI deps so that we get consistent log structure vs. print statements

    eh.log("TormachConsole : initializing.")

    hal_component = component("tormach_console")
    wrapper = HalWrapper(hal_component)
    hal_component.setprefix("tormach-console")

    #We need to initialize these devices up front because HAL needs all pins created now
    devices = [TormachConsoleInputDevice(eh, wrapper, index, None) for index in range(NUMBER_SUPPORTED)]

    check_for_devices(eh)
    wrapper.newpin('device-connected', HAL_BIT, HAL_OUT)

    hal_component.ready()

    last_check = datetime.datetime.now()
    last_forced_update = datetime.datetime.now()
    last_led_update = datetime.datetime.now()

    try:
        while True:
            # Check for new console devices every 5 seconds
            if (datetime.datetime.now() - last_check).total_seconds() > 5:
                check_for_devices(eh)
                last_check = datetime.datetime.now()
            if len( connected_devices() ) == 0:
                wrapper['device-connected']=0
                time.sleep(1)
            else:
                wrapper['device-connected']=1
            try:
                if (datetime.datetime.now() - last_forced_update).total_seconds() > 1:
                    #every one second we'll do a forced updated of all key and abs values
                    for dev in connected_devices():
                        dev.doForcedUpdate()
                    last_forced_update = datetime.datetime.now()
                if (datetime.datetime.now() - last_led_update).total_seconds() > 0.1:
                    for dev in connected_devices():
                        dev.doLEDUpdate()
                    last_led_update = datetime.datetime.now()

                fds = {dev.event_device.fd: dev for dev in devices if dev.device_connected()}
                readable, w, x = select(fds.keys(), [], [], 0.1)
                for fd in readable:
                    fds[fd].readEvents()

            except IOError as e:
                for dev in connected_devices():
                    if os.fstat(dev.event_device.fd).st_mode == 8192:
                        eh.log("TormachConsole : console device {} disappeared".format(str(dev.index)))
                        dev.event_device = None

    except KeyboardInterrupt:
        # this is the expected signal from linuxcnc for the hal user comp to terminate
        eh.log("TormachConsole : caught KeyboardInterrupt, hal comp shutting down.")
