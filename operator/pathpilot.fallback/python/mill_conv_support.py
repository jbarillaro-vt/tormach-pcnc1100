# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

#
# Module for G-code generator support classes
#

import sys
import gtk
import math
import re
from math import *
import itertools

def round_number(x, n):
    return math.ceil(x * math.pow(10, n)) / math.pow(10, n)
def float_round(x):
    return round_number(x,6)

def real_eq(a, b):
    limit = 0.0000001
    return math.fabs(a-b) < limit

def intersect_rect(rect_in_question, rect):
    # check fi a side is equal within floating point error
    if real_eq(rect['right'], rect_in_question['left']):
        return False
    if real_eq(rect['left'], rect_in_question['right']):
        return False
    if real_eq(rect['bottom'], rect_in_question['top']):
        return False
    if real_eq(rect['top'], rect_in_question['bottom']):
        return False

    return (rect_in_question['left']    < rect['right'])   and \
           (rect_in_question['right']   > rect['left'])    and \
           (rect_in_question['bottom']  < rect['top'])     and \
           (rect_in_question['top']     > rect['bottom'])

def increase_rect(rect,by):
    rect['right'] += by
    rect['bottom'] -= by
    rect['left'] -= by
    rect['top'] += by

def pt_in_rect(pt, rect):
    x,y = pt
    return x >= rect['left']  and \
           x <= rect['right'] and \
           y <= rect['top']   and \
           y >= rect['bottom']

def rect_pts_in_rect(rect_in_question, rect):
    pts = ((rect_in_question['left'],rect_in_question['bottom']),
           (rect_in_question['left'],rect_in_question['top']),
           (rect_in_question['right'],rect_in_question['top']),
           (rect_in_question['right'],rect_in_question['bottom']))
    rval = []
    for pt in pts:
        if pt_in_rect(pt, rect):
            rval.append(pt)
    return rval


class profile_path_generator:

    _sides = [
               { 'side'                : 'bottom', # bottom
                 'next'                : 'left',
                 'last'                : 'right',
                 'opposite'            : 'top',
                 'index'               : 0,
                 'tool_edge'           : 0,
                 'dir_to_center'       : 1,
                 'dir_from_center'     : -1,
                 'dir_to_arc_start'    : 1,
                 'dir_to_arc_end'      : 1,
                 'side_is_x'           : True,
                 'increment'           : 1.0,
                 'increment_persist'   : True,
                 'i_j_past_corner'     : (-1,0),
                 'i_j_next_corner'     : (0,1),
                 'last_edge'           : False },

               { 'side'                : 'left', # left
                 'next'                : 'top',
                 'last'                : 'bottom',
                 'opposite'            : 'right',
                 'index'               : 1,
                 'tool_edge'           : 0,
                 'dir_to_center'       : 1,
                 'dir_from_center'     : -1,
                 'dir_to_arc_start'    : -1,
                 'dir_to_arc_end'      : -1,
                 'side_is_x'           : False,
                 'increment'           : 0,
                 'increment_persist'   : False,
                 'i_j_past_corner'     : (0,1),
                 'i_j_next_corner'     : (1,0),
                 'last_edge'           : False  },

               { 'side'                : 'top', # top
                 'next'                : 'right',
                 'last'                : 'left',
                 'opposite'            : 'bottom',
                 'index'               : 2,
                 'tool_edge'           : 0,
                 'dir_to_center'       : -1,
                 'dir_from_center'     : 1,
                 'dir_to_arc_start'    : -1,
                 'dir_to_arc_end'      : 1,
                 'side_is_x'           : True,
                 'increment'           : 0,
                 'increment_persist'   : False,
                 'i_j_past_corner'     : (1,0),
                 'i_j_next_corner'     : (0,-1),
                 'last_edge'           : False  },

               { 'side'                : 'right', # right
                 'next'                : 'bottom',
                 'last'                : 'top',
                 'opposite'            : 'left',
                 'index'               : 3,
                 'tool_edge'           : 0,
                 'dir_to_center'       : -1,
                 'dir_from_center'     : 1,
                 'dir_to_arc_start'    : 1,
                 'dir_to_arc_end'      : -1,
                 'side_is_x'           : False,
                 'increment'           : 0,
                 'increment_persist'   : False,
                 'i_j_past_corner'     : (0,-1),
                 'i_j_next_corner'     : (-1,0),
                 'last_edge'           : True  }
             ]

    _z_up_str = 'z_up'
    _z_dn_str = 'z_down'

    # encapsulate the cursor...
    class cursor:
        _curr_side = None
        _z_state = None
        _stepover = None
        _radius_stepover_increase = None
        _cursor_tr_rect = None
        _cursor_radius_tr_rect = None
        _num_passes = None
        _pass_count = None
        _sides = None

        def __init__(self, sides, stock_rect, profile_rect, step_over, tool_radius, corner_radius = 0):

            profile_path_generator.cursor._z_state = profile_path_generator._z_up_str
            profile_path_generator.cursor._stepover = step_over

            x_largest = max( math.fabs(profile_rect['right'] - stock_rect['right']), math.fabs(profile_rect['left'] - stock_rect['left']))
            y_largest = max( math.fabs(profile_rect['top'] - stock_rect['top']), math.fabs(profile_rect['bottom'] - stock_rect['bottom']))
            xy_largest = float_round(max( x_largest, y_largest ))

            # get the difference betwee the corner_radius and the corner...
            corner_radius_extend = float_round(math.sqrt( 2 * ( corner_radius * corner_radius ) ) - corner_radius)
            profile_path_generator.cursor._radius_stepover_increase = 0 if corner_radius == 0 else corner_radius_extend
            normalize_cursor_side = xy_largest + profile_path_generator.cursor._radius_stepover_increase# + tool_radius
            num_passes = 0
            if step_over > 0:
                normalize_cursor_side_1 = float_round(math.floor(normalize_cursor_side / step_over))
                normalize_cursor_side = normalize_cursor_side_1 * step_over
                normalize_remainder = normalize_cursor_side % step_over
                normalize_remainder = 0 if normalize_remainder < 0.000001 else normalize_remainder # get rid of floating point junk
                normalize_cursor_side = normalize_cursor_side + step_over if normalize_remainder != 0 else normalize_cursor_side
                num_passes = int(math.floor(normalize_cursor_side / step_over)) + 1

            profile_path_generator.cursor._pass_count = num_passes

            profile_path_generator.cursor._cursor_tr_rect = { 'left':profile_rect['left'] - normalize_cursor_side - tool_radius,
                                                              'top':profile_rect['top'] + normalize_cursor_side + tool_radius,
                                                              'right':profile_rect['right'] + normalize_cursor_side + tool_radius,
                                                              'bottom':profile_rect['bottom'] - normalize_cursor_side - tool_radius }


            profile_path_generator.cursor._sides = sides

        def reset(self):
            profile_path_generator.cursor._num_passes = profile_path_generator.cursor._pass_count
            for side in profile_path_generator.cursor._sides:
                if side['increment_persist']:
                    side['increment'] = 1.0
                side['tool_edge'] = profile_path_generator.cursor._cursor_tr_rect[side['side']]
                side['increment'] = side['increment'] * profile_path_generator.cursor._stepover * side['dir_to_center']

        # sets and returns the current edge of the cursor rect
        @classmethod
        def side_to_index(cls, side = None):
            side = side if side else cls._curr_side
            return next(index for (index, dct) in enumerate(cls._sides) if dct['side'] == side)

        @classmethod
        def set_side(cls, side):
            if side == cls._curr_side:
                return
            cls._curr_side = side

        @classmethod
        def increment_tool_edges(cls):
            for side in cls._sides:
                incr = (cls._stepover * side['dir_to_center'])
                side['tool_edge'] += incr

        @classmethod
        def tool_edge(cls, side = None):
            side = side if side else cls._curr_side
            return cls._sides[cls.side_to_index(side)]['tool_edge']

        @classmethod
        def next_tool_edge(cls, side = None):
            side = side if side else cls._curr_side
            next_side = cls._next_side(side)
            next_tool_edge = cls._sides[cls.side_to_index(next_side)]['tool_edge']
            return (next_tool_edge + cls._sides[cls.side_to_index(next_side)]['increment'])

        @classmethod
        def last_tool_edge(cls, side = None):
            side = side if side else cls._curr_side
            last_side = cls._last_side(side)
            last_tool_edge = cls._sides[cls.side_to_index(last_side)]['tool_edge']
            increment = cls._sides[cls.side_to_index(last_side)]['increment']
            return (last_tool_edge - increment)

        @classmethod
        def val_in_rect(cls, rect, val, side = None):
            side = side if side else cls._curr_side
            rs = rect[side]
            ropp = rect[cls._sides[cls.side_to_index(side)]['opposite']]
            return (min(rs,ropp)) <= val <= (max(rs,ropp))

        @classmethod
        def tool_edge_in_rect(cls, rect, side = None):
            side = side if side else cls._curr_side
            return cls.val_in_rect(rect, cls._sides[cls.side_to_index(side)]['tool_edge'])

        @classmethod
        def side(cls):
            return cls._curr_side

        @classmethod
        def _next_side(cls, side = None):
            side = side if side else cls._curr_side
            return cls._sides[cls.side_to_index(side)]['next']


        @classmethod
        def _last_side(cls, side = None):
            side = side if side else cls._curr_side
            return cls._sides[cls.side_to_index(side)]['last']

        @classmethod
        def side_of_rect(cls,rect):
            return rect[cls._curr_side]

        @classmethod
        def num_passes_remaining(cls):
            retval = cls._num_passes
            cls._num_passes -= 1
            return retval

        @classmethod
        def reset_on_profile_rect(cls, final_rect, tool_radius, corner_radius):
            if corner_radius == 0:
                return False
            radius = tool_radius + corner_radius
            dist_1_sq = radius * radius
            dist_2 = math.sqrt(dist_1_sq + dist_1_sq)
            dist_diff = dist_2 - radius
            profile_path_generator.cursor._num_passes = int( math.floor(dist_diff / profile_path_generator.cursor._stepover) ) + 1
            rect_increase = profile_path_generator.cursor._num_passes * profile_path_generator.cursor._stepover
            profile_path_generator.cursor._cursor_radius_tr_rect = { 'left':final_rect['left'] - rect_increase,
                                    'top':final_rect['top'] + rect_increase,
                                    'right':final_rect['right'] + rect_increase,
                                    'bottom':final_rect['bottom'] - rect_increase }

            profile_path_generator.cursor._cursor_tr_one_stepover_rect = {'left':final_rect['left'] - cls._stepover,
                                                'top':final_rect['top'] + cls._stepover,
                                                'right':final_rect['right'] + cls._stepover,
                                                'bottom':final_rect['bottom'] - cls._stepover }
            for side in profile_path_generator.cursor._sides:
                side['tool_edge'] = profile_path_generator.cursor._cursor_radius_tr_rect[side['side']]

            return True

        @classmethod
        def reset_on_profile_rect_final(cls, final_rect):
            for side in profile_path_generator.cursor._sides:
                side['tool_edge'] = final_rect[side['side']]
        # end class cursor



    def __init__(self,
                 out_list,
                 x_start, x_end, y_start, y_end,
                 x_stk_start, x_stk_end, y_stk_start, y_stk_end,
                 tool_radius,
                 step_over,
                 corner_radius,
                 is_metric,
                 z_clear,
                 feed_rate,
                 z_feed ):

        self.stock_rect = {'right':x_stk_end,
                           'bottom':y_stk_end,
                           'left':x_stk_start,
                           'top':y_stk_start }

        self.profile_rect = {'right':x_end,
                             'bottom':y_end,
                             'left':x_start,
                             'top':y_start }

        # make a rectangle of the largest area possible between the starts and the profile starts...
        self.cursor = self.cursor(self._sides, self.stock_rect, self.profile_rect, step_over, tool_radius ) #, corner_radius )
        self.tool_radius = tool_radius
        self.corner_radius = corner_radius
        self.step_over = step_over
        self.tool_down_extra = tool_radius * .1

        # 'tr' rectangles have the tool radius included in them

        self.cut_stock_tr_rect = self.stock_rect.copy()
        increase_rect(self.cut_stock_tr_rect, tool_radius)

#       self.cut_stock_tr_extra_rect = self.cut_stock_tr_rect.copy()
#       increase_rect(self.cut_stock_tr_extra_rect, self.tool_down_extra)

        # increase the profile rect by the cutter radius
        self.profile_tr_rect = self.profile_rect.copy()
        increase_rect(self.profile_tr_rect, tool_radius)

        self.profile_tr_so_rect = self.profile_tr_rect.copy()
        increase_rect(self.profile_tr_so_rect, self.step_over)

        self.stock_tr_radius_rect = self.cut_stock_tr_rect.copy()
        increase_rect(self.stock_tr_radius_rect, self.cursor._radius_stepover_increase)

        self.stock_tr_arc_enter_rect = self.cut_stock_tr_rect.copy()
        increase_rect(self.stock_tr_arc_enter_rect, self.tool_down_extra)

        self.format_spec = ' %.3f' if is_metric else ' %.4f'
        self.z_feed_spec = ' %.1f' if is_metric else ' %.2f'
        self.out_list = out_list
        self.last_pass_count = 0
        self.z_up = True
        self.curr_z_depth = None
        self.initial_move = True
        self.z_retract = z_clear
        self.z_feed_rate = z_feed
        self.feed_rate = feed_rate
        self.in_z_feed = False
        self.z_pass_count = 0
        self.can_do_alt_opt_radial_corner = self.corner_radius > self.tool_radius and self.tool_radius <  (self.step_over * 1.2)


    def start_passes(self,z_depth):
        self.cursor.reset()
        self.z_pass_count += 1
        pass_comment = '(Z Level: %d)' % self.z_pass_count
        self.code_append(pass_comment)
        self.curr_z_depth = z_depth


    def _push_outlist(self,line):
        self.out_list.append(line)
        print line

    def _pop_last_contains(self, item):
        out_list_len = len(self.out_list)
        if out_list_len == 0: return
        if item in self.out_list[out_list_len-1]: self.out_list.pop()

    def _initial_move(self, item):
        if not self.initial_move:
            return
        if isinstance(item, str):
            return
        x, y, i, j, z, comment = item
        if x is None or y is None:
            return
        append_str = 'G0 X%s Y%s' % (self.format_spec,self.format_spec) % (x,y)
        self._push_outlist(append_str)
        append_str = 'G0 Z%s' % self.format_spec % self.z_retract
        self._push_outlist(append_str)
        self.initial_move = False
        return

    def code_append(self, item):
        self._initial_move(item)
        append_str = 'G1'
        if isinstance(item, str):
            self._push_outlist(item)
        elif isinstance(item, tuple):
            x, y, i, j, z, comment = item
            if x is not None and y is not None:
                if z is not None:
                    if z == self._z_dn_str:
                        append_str = 'G0'
                if i is not None:
                    append_str = 'G2'
                append_str += ' X%s Y%s ' % (self.format_spec,self.format_spec) % (x,y)
                if i is not None:
                    append_str += ' I%s J%s ' % (self.format_spec,self.format_spec) % (i,j)
                if self.in_z_feed:
                    append_str += ' F%s ' % (self.z_feed_spec) % (self.feed_rate)
                    self.in_z_feed = False
                if comment is not None:
                    append_str += comment
                self._push_outlist(append_str)

            if z is not None:
                append_str = 'G0' if self.z_up else 'G1'
                z_val = self.z_retract if self.z_up else self.curr_z_depth
                if self.z_up:
                    append_str += ' Z%s ' % self.format_spec % z_val
                else:
                    append_str += ' Z%s F%s' % (self.format_spec,self.z_feed_spec) % (z_val,self.z_feed_rate)
                    self.in_z_feed = True
                if comment is not None:
                    append_str += comment
                self._push_outlist(append_str)

    def _tool_edge_in_stock_tr(self, side = None):
        return self.cursor.tool_edge_in_rect(self.cut_stock_tr_rect, side)

    def _tool_edge_outside_profile(self, side = None):
        return not self.cursor.tool_edge_in_rect(self.profile_tr_rect, side)

    def _tool_edge_at_tr_profile(self, this_side):
        a = self.cursor.tool_edge()
        b = self.profile_tr_rect[this_side['side']]
        return real_eq(a, b)

    @staticmethod
    def _arc_rect(this_side, a,b,c,d):
        return  {
                    this_side['side']     : round(a,5),
                    this_side['next']     : round(b,5),
                    this_side['opposite'] : round(c,5),
                    this_side['last']     : round(d,5),
                }

    # check to see if there's an 'arc' enterring or leaving the
    # stock if the next cursor position is out of the stock. This
    # will prevent nubs
    def tool_enter_arc_in_stock(self, this_side):
        a = self.cursor.tool_edge()
        rect_edge = self.cut_stock_tr_rect[this_side['side']]
        if real_eq(a, rect_edge): return False
        b = self.cursor.next_tool_edge()
        c = a + (self.tool_radius * this_side['dir_to_center'])
        d = b + (self.tool_radius * this_side['dir_to_arc_start'])
        if real_eq(c, rect_edge): return False
        arc_rect = profile_path_generator._arc_rect(this_side,a,b,c,d)
        # adjust the arc rect by the 'next-side' increment
        next_side = self._sides[self.cursor.side_to_index(this_side['next'])]
        if next_side['increment'] != 0.0:
            incr = (self.cursor._stepover * next_side['dir_to_center'])
            arc_rect[this_side['next']] +=  incr
            arc_rect[this_side['last']] +=  incr

        if not intersect_rect(arc_rect, self.cut_stock_tr_rect) or \
           self._tool_edge_in_stock_tr():
            return False
        # see if just one corner of the tool radius rect is in the stock rect
        # in this case it's need to be ignored...
        in_pts = rect_pts_in_rect(arc_rect, self.cut_stock_tr_rect)
        number_pts = len(in_pts)
        if number_pts == 1:
            return False
        # check the arc_rect's next side is not in the profile rect
        na = arc_rect[this_side['next']]
        oa = arc_rect[this_side['opposite']]
        next_profile_rect_side = self.profile_tr_rect[this_side['next']]
        x,y = (na,oa) if this_side['side_is_x'] else (oa,na)
        if pt_in_rect((x,y), self.profile_tr_rect): return False
        if real_eq(na, next_profile_rect_side): return False
        return True

    def tool_exit_arc_in_stock(self, this_side):
        a = self.cursor.tool_edge()
        b = self.cursor.next_tool_edge()
        c = a + (self.tool_radius * this_side['dir_to_center'])
        d = b + (self.tool_radius * this_side['dir_to_arc_start'])
        arc_rect = profile_path_generator._arc_rect(this_side,a,b,c,d)
        if not intersect_rect(arc_rect, self.cut_stock_tr_rect): return False

        # attempt to create a point that is the intersection of the
        # 90 degree arc from opposing corners in the arc rect, from an extended
        # line formed the corner of the profile_rect and the one point of the arc_rect
        # insode the profile_rect...
        in_pts = rect_pts_in_rect(arc_rect, self.cut_stock_tr_rect)
        number_pts = len(in_pts)
        if number_pts != 2: return False
        next_side = self._sides[self.cursor.side_to_index(this_side['next'])]

        a_dir = this_side['dir_from_center']
        b_dir = next_side['dir_from_center']
        delt_a = (math.fabs(c) - math.fabs(self.profile_tr_rect[this_side['side']])) * a_dir
        delt_b = (math.fabs(d) - math.fabs(self.profile_tr_rect[this_side['next']])) * b_dir
        x,y = (delt_a,delt_b) if this_side['side_is_x'] else (delt_b,delt_a)
        hyp = math.hypot(x,y)
        scale_hyp = hyp / self.tool_radius
        x *= scale_hyp
        y *= scale_hyp
        if pt_in_rect((x,y), self.profile_tr_rect): return False
        return True

    def tool_edge_attempt_next(self, this_side):
        next_side_name = this_side['next']
        end_edge = self.cursor.next_tool_edge()
        if not self.cursor.val_in_rect(self.cut_stock_tr_rect, end_edge, next_side_name):
            return 'nogo'
        if self.cursor.val_in_rect(self.profile_tr_rect, end_edge, next_side_name):
            return 'final'
        return 'go'

    def zpoint_down(self, this_side, val):
        val *= this_side['dir_to_arc_start']
        a = self.stock_rect[this_side['last']] + val
        b = self.cursor.tool_edge()
        return (a,b) if this_side['side_is_x'] else (b,a)

    def zpoint_up(self, this_side, val):
        val *= this_side['dir_to_arc_start']
        a = self.stock_rect[this_side['next']] - val
        b = self.cursor.tool_edge()
        return (a,b) if this_side['side_is_x'] else (b,a)

    def move_to_arc_start(self, this_side):
        factor = this_side['dir_to_arc_start']
        arc_start = self.tool_radius * factor
        a = self.cursor.next_tool_edge() + arc_start
        b = self.cursor.tool_edge()
        return (a,b) if this_side['side_is_x'] else (b,a)

    def gen_partial_arc_start(self, this_side):
        next_side = self._sides[self.cursor.side_to_index(this_side['next'])]
        this_edge = self.cursor.tool_edge()
        next_edge = self.cursor.next_tool_edge()
        start_edge = self.cut_stock_tr_rect[this_side['side']] - (self.tool_down_extra * this_side['dir_to_center'])
        end_edge = this_edge + (self.tool_radius * this_side['dir_to_center'])
        radius = self.tool_radius
        distance = (start_edge-end_edge)*this_side['dir_from_center']
        if distance>radius: radius = distance
        x = end_edge
        y = next_edge
        i = distance*this_side['dir_to_center']
        j = (math.sqrt(radius**2-i**2) * this_side['dir_to_arc_start'])
        a = start_edge
        b = next_edge+((radius-math.fabs(j))*next_side['dir_to_center'])
        return (b,a,j,i,y,x) if this_side['side_is_x'] else (a,b,i,j,x,y)

    def gen_i_j(self, val, which_ij = 'i_j_next_corner', side = None):
        side = side if side else self.cursor.side()
        x,y = self._sides[self.cursor.side_to_index()][which_ij]
        return ((val * x), (val * y))

    def radial_validate(self, this_side, x, xd):
        a,b = (x,xd) if this_side['dir_to_arc_start'] > 0 else (xd,x)
        delt = a - b
        return delt > 0 and delt > self.tool_down_extra

    def gen_partial_tool_radius_arc(self, this_side):
        next_side = self._sides[self.cursor.side_to_index(this_side['next'])]
        this_edge = self.cursor.tool_edge()
        next_edge = self.cursor.next_tool_edge()
        end_edge = self.cut_stock_tr_rect[this_side['next']] - (self.tool_down_extra * next_side['dir_to_center'])
        tool_edge = self.cursor.next_tool_edge() + (self.tool_radius * next_side['dir_to_center'])
        radius = self.tool_radius
        distance = (tool_edge-end_edge)*next_side['dir_to_center']
        if distance>radius: radius = distance
        b = distance
        a = math.sqrt(radius**2-b**2)
        a = this_edge + ((radius-a)*this_side['dir_to_center'])
        b = end_edge
        i,j = self.gen_i_j(radius)
        return (b,a,i,j) if this_side['side_is_x'] else (a,b,i,j)

    def gen_tool_radius_arc(self, this_side):
        end_edge = self.cursor.next_tool_edge()
        end_offset = self.tool_radius * this_side['dir_to_center']
        a = self.cursor.tool_edge() + end_offset
        b = end_edge
        i,j = self.gen_i_j(self.tool_radius)
        return (b,a,i,j) if this_side['side_is_x'] else (a,b,i,j)

    def _radius_ctr(self, this_side):
        next_side = self._sides[self.cursor.side_to_index(this_side['next'])]
        a = self.profile_rect[this_side['next']] + (self.corner_radius * next_side['dir_to_center'])
        b = self.profile_rect[this_side['side']] + (self.corner_radius * this_side['dir_to_center'])
        return (next_side,a,b) if this_side['side_is_x'] else (next_side,b,a)


    def arc_end_radius(self, this_side, i, j):
        next_side,rad_ctr_x,rad_ctr_y = self._radius_ctr(this_side)
        x = rad_ctr_x - (j * this_side['dir_to_arc_end'])
        y = rad_ctr_y - (i * this_side['dir_to_arc_end'])
        return (x,y)


    def move_to_arc_start_radius(self, this_side):
        next_side,rad_ctr_x,rad_ctr_y = self._radius_ctr(this_side)
        corner_plus_tool = self.corner_radius + self.tool_radius
        radius = corner_plus_tool + ((self.cursor._num_passes + 1) * self.step_over) + self.tool_down_extra
        adj = corner_plus_tool
        opp = math.sqrt( (radius * radius) - (adj * adj) )
        a,b = (opp,adj) if this_side['side_is_x'] else (adj,opp)
        x = rad_ctr_x - (a * this_side['dir_to_center'])
        y = rad_ctr_y - (b * next_side['dir_to_center'])
        i = (a * this_side['dir_to_center'])
        j = (b * next_side['dir_to_center'])
        return (x,y,i,j)

    def cut_entry_arc(self, this_side):
        if self.z_up:
            if self.tool_enter_arc_in_stock(this_side):
                a,b,i,j,x,y = self.gen_partial_arc_start(this_side)
                self.code_append((a, b, None, None, self._z_down(), None))
                self.code_append((x,y,i,j,None,None))
                return True
        return False

    def cut_side_intper_corner(self, this_side):

        if not self._tool_edge_in_stock_tr():
            if not self.z_up:
                self.code_append((None, None, None, None, self._z_up(), None))
            return
        if not self._tool_edge_outside_profile():
            return
        if self._tool_edge_at_tr_profile(this_side):
            return

        tool_entry = self.tool_radius + self.tool_down_extra
        if self.z_up:
            # find the point less
            #the tool radius where the tool edge path will intersect the stock
            x,y = self.zpoint_down(this_side, tool_entry)
            self.code_append((x, y, None, None, self._z_down(), None))

        # get the next cursor edge an see if it's in the stock
        arc_case = self.tool_edge_attempt_next(this_side)
        if arc_case != 'nogo':
            x,y = self.move_to_arc_start(this_side)
            self.code_append((x, y, None, None, None, None))
            x,y,i,j = self.gen_tool_radius_arc(this_side)
            self.code_append((x, y, i, j, None, None))
        # see if an 'arc' exit to the stock is possible
        # this is to avoid 'nibs' in the z-plane surface
        elif self.tool_exit_arc_in_stock(this_side):
            x,y = self.move_to_arc_start(this_side)
            self.code_append((x, y, None, None, None, None))
            x,y,i,j = self.gen_partial_tool_radius_arc(this_side)
            self.code_append((x, y, i, j, self._z_up(), None))
        else:
            x,y = self.zpoint_up(this_side, tool_entry)
            self.code_append((x, y, None, None, self._z_up(), None))


    def _z_down(self):
        self.z_up = False
        return self._z_dn_str

    def _z_up(self):
        self.z_up = True
        return self._z_up_str

    def get_final_pass_start_side(self):
        min_side_diff = float(1000000)
        min_side = None
        for this_side in self._sides:
            side_diff = math.fabs(self.stock_tr_radius_rect[this_side['side']] - self.profile_tr_rect[this_side['side']])
            min_side_diff = min(min_side_diff,side_diff)
            if min_side_diff == side_diff:
                min_side = this_side['side']
        return min_side

    def _cutting_final_pass(self, pass_number):
        self._pop_last_contains('Level')
        self.code_append('(Finish Pass - Z Level %d)' % (pass_number))
        self.cursor.reset_on_profile_rect_final(self.profile_tr_rect)
        radius = (self.tool_radius + self.corner_radius)
        first = True
        start_side = self.get_final_pass_start_side()
        curr_side = 'top' if not start_side else start_side
        num_sides = len(self._sides)

        for counter in range(num_sides):
            self.cursor.set_side(curr_side)
            this_side = self._sides[self.cursor.side_to_index(curr_side)]
            next_side = self._sides[self.cursor.side_to_index(this_side['next'])]
            if this_side['last_edge']:
                next_side['increment'] = 0

            a = self.cursor.tool_edge()
            if first:
                if self.step_over > 0:
                    b = self.cursor.last_tool_edge()
                else:
                    b = self.cursor.last_tool_edge() - (radius * this_side['dir_to_arc_start'])
                x,y = (b,a) if this_side['side_is_x'] else (a,b)
                self.code_append((x, y, None, None, self._z_down(), None))
                first = False

            b = self.cursor.next_tool_edge() + (radius * this_side['dir_to_arc_start'])
            x,y = (b,a) if this_side['side_is_x'] else (a,b)
            self.code_append((x, y, None, None, None, None))
            a = self.cursor.tool_edge() + (radius * this_side['dir_to_center'])
            b = self.cursor.next_tool_edge()
            x,y = (b,a) if this_side['side_is_x'] else (a,b)
            i,j = self.gen_i_j(radius)
            self.code_append((x, y, i, j, None, None))
            curr_side = this_side['next']
        self.code_append((None, None, None, None, self._z_up(), None))

    def _cutting_optimized_radial_corner(self):
        for this_side in self._sides:
            self.cursor.set_side(this_side['side'])

            x,y,i,j = self.move_to_arc_start_radius(this_side)
            xd,yd = self.arc_end_radius(this_side, i, j)

            if self.radial_validate(this_side, x, xd) and self.z_up:
                self.code_append((x, y, None, None, self._z_down(), None))
                self.code_append((xd, yd, i, j, self._z_up(), None))
                self.can_do_alt_opt_radial_corner = False

            elif self.can_do_alt_opt_radial_corner:
                next_side = self._sides[self.cursor.side_to_index(this_side['next'])]
                if this_side['last_edge']:
                    break
                total_radius = self.step_over + self.corner_radius + self.tool_radius
                offset = total_radius * next_side['dir_to_center']
                a = self.profile_tr_so_rect[next_side['side']] + offset
                b = self.profile_tr_so_rect[this_side['side']]
                x,y = (a,b) if this_side['side_is_x'] else (b,a)
                self.code_append((x, y, None, None, self._z_down() if self.z_up else None, None))
                i,j = self.gen_i_j(total_radius)
                offset = total_radius * this_side['dir_to_center']
                a = self.profile_tr_so_rect[next_side['side']]
                b = self.profile_tr_so_rect[this_side['side']] + offset
                x,y = (a,b) if this_side['side_is_x'] else (b,a)
                self.code_append((x, y, i, j, self._z_up(), None))

    def _cutting_stock_to_profile_rect(self):
        for this_side in self._sides:
            self.cursor.set_side(this_side['side'])
            if self.cut_entry_arc(this_side):
                continue
            self.cut_side_intper_corner(this_side)

        self.cursor.increment_tool_edges()
        if profile_path_generator.cursor._num_passes == 0:
            if not self.z_up:
                self.code_append((None, None, None, None, self._z_up(), None))

    def run(self, z_depth, pass_number):
        self.start_passes(z_depth)
        if self.step_over > 0:
            while profile_path_generator.cursor.num_passes_remaining():
                self._cutting_stock_to_profile_rect()
            if self.cursor.reset_on_profile_rect(self.profile_tr_rect, self.tool_radius, self.corner_radius):
                while self.cursor.num_passes_remaining():
                    self._cutting_optimized_radial_corner()
        self._cutting_final_pass(pass_number)
