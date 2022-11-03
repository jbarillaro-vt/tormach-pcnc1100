#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import freetype
import numpy
import sys

def freetype_y_range(e_string, font_path):
    face = freetype.Face(font_path)
    face.set_pixel_sizes(64, 64)
    y_max_list = []
    y_min_list = []

    x_end = 0.0

    #print "--kaw engrave string =", e_string

    for char in e_string:
        #print "char =", char
        face.load_char(char)
        slot = face.glyph
        outline = slot.outline
        #print "outline points\n", outline.points
        points = numpy.array(outline.points, dtype=[('x',float), ('y',float)])
        #print "--kaw   points.size =", points.size
        if points.size > 0:
            x, y = points['x'], points['y']
            #print "points = \n", points
            y_max_list.append(max(y))
            y_min_list.append(min(y))

        x_end += slot.advance.x
        #print "--kaw slot advance =", slot.advance.x

    str_y_max = max(y_max_list)
    str_y_min = min(y_min_list)
    #print "y max list\n", y_max_list
    #print "y min list\n", y_min_list
    #print "\nstring y max =", str_y_max
    #print "string y min =", str_y_min

    #print "--kaw x end =", x_end

    return str_y_max, str_y_min, x_end

if __name__ == '__main__':
    freetype_y_range(sys.argv[1], sys.argv[2])

