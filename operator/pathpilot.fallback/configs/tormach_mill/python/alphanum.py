# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# Portions Copyright © 2014-2018 Z-Bot LLC.
# License: GPL Version 2
#-----------------------------------------------------------------------


#pylint: disable=import-error

import traceback
import linuxcnc
import math
from interpreter import *
from constants import *  #goody bag of values from Tormach

class alphanum():

    # NOTE: values are imperial
    _x_extent = .18
    _y_extent = .18
    _x_min = .02
    _y_min = .02
    _average_spacing = .008
    _kern_extra = .04
    _metric_factor = 1
    _vector_data = {      0: ((.00, .04, 'Zdown'),
                              (None, .14, None),
                              (.04, .18, None),
                              (.14, None, None),
                              (.18, .14, None),
                              (None, .04, None),
                              (.14, .00, None),
                              (.04, None, None),
                              (.00, .04, 'Zup'),
                              (.00, .00, 'Zdown'),
                              (.18, .18, None)),

                          1: ((.01, .14, 'Zdown'),
                              (.07, .18, None),
                              (None, .00, 'Zup'),
                              (.01, .00, 'Zdown'),
                              (.12, None, None)),

                          2: ((.00, .14, 'Zdown'),
                              (.04, .18, None),
                              (.14, None, None),
                              (.18, .14, None),
                              (None, .11, None),
                              (.00, .00, None),
                              (.18, None, None)),

                          3: ((.00, .14, 'Zdown'),
                              (.03, .18, None),
                              (.15, None, None),
                              (.18, .15, None),
                              (None, .12, None),
                              (.15, .09, None),
                              (.02, None, 'Zup'),
                              (.15, None, 'Zdown'),
                              (.18, .06, None),
                              (None, .03, None),
                              (.15, .00, None),
                              (.03, None, None),
                              (.00, .03, None)),

                          4: ((.00, .18, 'Zdown'),
                              (None, .09, None),
                              (.16, None, 'Zup'),
                              (.13, .18, 'Zdown'),
                              (None, .00, None)),

                          5: ((.15, .18, 'Zdown'),
                              (.00, None, None),
                              (None, .09, None),
                              (.15, None, None),
                              (.18, .06, None),
                              (None, .03, None),
                              (.15, .00, None),
                              (.03, None, None),
                              (.00, .03, None)),

                          6: ((.18, .15, 'Zdown'),
                              (.15, .18, None),
                              (.03, None, None),
                              (.00, .15, None),
                              (None, .03, None),
                              (.03, .00, None),
                              (.15, None, None),
                              (.18, .03, None),
                              (None, .06, None),
                              (.15, .09, None),
                              (.03, None, None),
                              (.00, .06, None)),

                          7: ((.00, .18, 'Zdown'),
                              (.18, None, None),
                              (.05, .00, None)),

                          8: ((.00, .12, 'Zdown'),
                              (.00, .15, None),
                              (.03, .18, None),
                              (.15, None, None),
                              (.18, .15, None),
                              (None, .12, None),
                              (.15, .09, None),
                              (.03, None, None),
                              (.00, .12, 'Zup'),
                              (.15, .09, 'Zdown'),
                              (.18, .06, None),
                              (None, .03, None),
                              (.15, .00, None),
                              (.03, None, None),
                              (.00, .03, None),
                              (None, .06, None),
                              (.03, .09, None)),

                          9: ((.18, .12, 'Zdown'),
                              (.15, .09, None),
                              (.03, None, None),
                              (.00, .12, None),
                              (None, .15, None),
                              (.03, .18, None),
                              (.15, None, None),
                              (.18, .15, None),
                              (None, .03, None),
                              (.15, .00, None),
                              (.03, None, None),
                              (.00, .03, None)) }

    def __init__(self, interpRef, xSize, ySize, zPos, zRetract, retract_at_end = True):
        self._interp_reference = interpRef
        self._x_scale = xSize / self._x_extent
        self._y_scale = ySize / self._y_extent
        self._z_depth = zPos
        self._z_retract = zRetract
        self._retract_at_end_generate = retract_at_end

    # extents is
    @classmethod
    def extents(cls):
        x_extent = cls._x_extent * cls._metric_factor
        y_extent = cls._y_extent * cls._metric_factor
        return x_extent, y_extent

    @classmethod
    def minimum_size(cls):
        x_min = cls._x_min * cls._metric_factor
        y_min = cls._y_min * cls._metric_factor
        return x_min, y_min


    def _execute(self, move_command, prt = True):
        if prt is True:
            print move_command
        self._interp_reference.execute(move_command)

    def _transform(self, x_origin, y_origin, data, rotation = 0):
        new_x, new_y = None, None

        if data[0] is not None:
            new_x = x_origin + (self._x_scale * data[0] )
        if data[1] is not None:
            new_y = y_origin + (self._y_scale * data[1] )
        return new_x, new_y

    def generate(self, index, x_origin, y_origin, rotation = 0):
        G0_move = True
        number_data = self._vector_data[index]
        kerningValue = 0

        for n in number_data:
            moveCommand = 'G0' if G0_move is True else 'G1'
            G0_move = False
            new_x_pos, new_y_pos = self._transform(x_origin, y_origin, n)

            if new_x_pos is not None:
                kernTmp = new_x_pos - x_origin
                kerningValue = kernTmp if kernTmp > kerningValue else kerningValue
                moveCommand += ' X%.4f' % (new_x_pos)

            if new_y_pos is not None:
                moveCommand += ' Y%.4f' % (new_y_pos)

            self._execute(moveCommand)

            if n[2] == 'Zup':
                moveCommand = 'G0 Z%.4f' % (self._z_retract)
                self._execute(moveCommand)
                G0_move = True

            elif n[2] == 'Zdown':
                moveCommand = 'G1 Z%.4f' % (self._z_depth)
                self._execute(moveCommand)

        if self._retract_at_end_generate is True:
            moveCommand = 'G0 Z%.4f' % (self._z_retract)
            self._execute(moveCommand)

        kerningValue += (self._kern_extra * self._metric_factor)
        return kerningValue