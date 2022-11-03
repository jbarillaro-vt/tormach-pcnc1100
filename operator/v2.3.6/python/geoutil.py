#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# geo_util.py
#     general utility classes geometry aid.
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import math

def fequal(_a, _b, _limit=1e-7): return math.fabs(_a-_b)<_limit

class _rect:
    _left, _top, _right, _bottom = range(4)
    
    def __init__(self, _list):
        self.__left = float(_list[_rect._left])
        self.__top = float(_list[_rect._top])
        self.__width = float(_list[2])
        self.__height = float(_list[3])
        self.__mk_center()
        
    def left(self) :  return self.__left
    def top(self):    return self.__top
    def right(self) : return self.__left+self.__width
    def bottom(self): return self.__top-self.__height
    def width(self):  return self.__width
    def height(self):  return self.__height
    def center_point(self):  return (self.__cx, self.__cy)
    def invalid(self): return self.__height<0.0 or self.__width<0.0
    def all_invalid(self): return self.__height<0.0 and self.__width<0.0
    def zero_dimension(self): return fequal(self.__width, 0.0) or fequal(self.__height, 0.0)
    def has_width(self): return self.__width>0.0
    def has_height(self): return self.__height>0.0
    def has_dimension(self): return self.has_width() and self.has_height()
    def is_horizontal(self): return self.__width>=self.__height
    def is_vertical(self): return self.__width<=self.__height
    def __add__(self, other_rect):
        if isinstance(other_rect, self.__class__):
            if other_rect.left() < self.__left: self.move_left(other_rect.left()-self.left)
            if other_rect.top() > self.__top: self.move_top(other_rect.top()-self.__top)
            if other_rect.right() > self.right(): self.move_right(other_rect.right()-self.right())
            if other_rect.bottom() < self.bottom(): self.move_bottom(other_rect.bottom()-self.bottom)
        return self
    
    def __eq__(self, other_rect):
        if not fequal(self.left(), other_rect.left()): return False
        if not fequal(self.top(), other_rect.top()): return False
        if not fequal(self.width(), other_rect.width()): return False
        if not fequal(self.height(), other_rect.height()): return False
        return True
    
    def __ne__(self, other_rect):
        return not self.__eq__(other_rect)

    def copy(self) : return self.offset(0.0)

    def offset(self, offset):
        if isinstance(offset, float) or isinstance(offset, int) or isinstance(offset, str):
            try:
                offset = float(offset)
            except ValueError:
                offset = 0.0 
            return _rect([self.__left-offset, self.__top+offset, self.__width+2.0*offset, self.__height+2.0*offset])
        elif isinstance(offset, list) or isinstance(offset, tuple):
            rv = self.copy()
            if len(offset) != 4: return rv
            if not fequal(offset[0],0.0): rv.move_left(offset[0])
            if not fequal(offset[1],0.0): rv.move_top(offset[1])
            if not fequal(offset[2],0.0): rv.move_right(offset[2])
            if not fequal(offset[3],0.0): rv.move_bottom(offset[3])
            return rv
        return self.copy()
                    
    def expand_height(self, offset):
        offset = float(offset)
        self.__top += offset
        self.__height += 2.0*offset
                        
    def expand_width(self, offset):
        offset = float(offset)
        self.__left -= offset
        self.__width += 2.0*offset

    def mk_square(self):
        wh = min(self.__width, self.__height)
        return _rect([self.__cx-wh/2.0, self.__cy+wh/2.0, wh, wh])
    
    def wh_ratio(self):
        if self.__width == self.__height: return 1.0
        return self.__height/self.__width
    
    # the following 'shift' methods move a
    # rectangle an incremental amount in the horizontal
    # or vertical direction
    def shift_horizontal(self, offset):
        self.__left += offset
        self.__cx += offset
    
    def shift_vertical(self, offset):
        self.__top += offset
        self.__cy += offset
    
    # the following 'shrink' methods expand or contract a
    # rectangle an incremental amount in the horizontal
    # or vertical direction
    def shrink_vertical(self, offset):
        _offset = min(self.__height/2.0, math.fabs(offset))
        if offset<0.0: _offset = -_offset
        self.__height -= _offset*2.0
        self.__top -= _offset
    
    def shrink_horizontal(self, offset):
        _offset = min(self.__width/2.0, math.fabs(offset))
        if offset<0.0: _offset = -_offset
        self.__width -= _offset*2.0
        self.__left += _offset

    def __mk_center(self):
        self.__cx = self.__left+self.__width/2.0
        self.__cy = self.__top-self.__height/2.0
        
    # the following 'move' methods move a side of the
    # rectangle an incremental amount
    def move_bottom(self, _dy):
        self.__height -= _dy
        self.__cy += _dy/2.0
        
    def move_right(self, _dx):
        self.__width += _dx
        self.__cx += _dx/2.0

    def move_top(self, _dy):
        self.__top += _dy
        self.__height += _dy
        self.__cy += _dy/2.0
        
    def move_left(self, _dx):
        self.__left += _dx
        self.__width -= _dx
        self.__cx += _dx/2.0

    # the following 'set' methods move a side of the
    # rectangle an absolute value
    def set_bottom(self, _y):
        self.__height = self.__top-_y
        self.__cy = self.__top-self.__height/2.0
        
    def set_right(self, _x):
        self.__width = _x-self.__left
        self.__cx = self.__left+self.__width/2.0

    def set_top(self, _y):
        _dy = self.__top-_y
        self.__top = _y
        self.__height -= _dy
        self.__cy = self.__top-self.__height/2.0
        
    def set_left(self, _x):
        _dx = _x-self.__left
        self.__left = _x
        self.__width -= _dx
        self.__cx = self.__left+self.__width/2.0
