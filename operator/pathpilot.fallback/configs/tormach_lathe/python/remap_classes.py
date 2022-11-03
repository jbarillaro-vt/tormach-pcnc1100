# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

#pylint: disable=import-error

#--------------------------------------------------------------------------
# define these BEFORE importing them from interpreter
# so that pylint doesn't false positive on undefined variable
# they will get overwritten by the interpreter from import syntax
INTERP_OK = 0
#--------------------------------------------------------------------------


from interpreter import *
import emccanon

from stdglue import cycle_prolog, cycle_epilog, init_stdglue

import linuxcnc
import inspect
import re
import math
import rs274
import redis
import sys
from outliner import ol

from pdb import set_trace as bp

class _g7x():

    _tool_radius_factor = 1.0
    _MODE,_LASTX,_LASTY,_X,_Y,_RADIUS,_XCENTER,_YCENTER = range(8)
    block_toks = re.compile('(\w)\s*([-+,\.\d]+)', re.S | re.I)
    planes = {170:('X','Y','I','J'), 180:('X','Z','I','K'), 190:('Y','Z','J','K'),
                  171:('U','V','',''), 181:('U','W','',''), 191:('V','W','','')}

    # Direction-aware versions of > < >= <= max() min()
    @staticmethod
    def GT(q, a, b): return (a > b) if q > 0 else (a < b)

    @staticmethod
    def LT(q, a, b): return (a < b) if q > 0 else (a > b)

    @staticmethod
    def GTE(q, a, b): return (a >= b) if q > 0 else (a <= b)

    @staticmethod
    def LTE(q, a, b): return (a >= b) if q > 0 else (a <= b)

    @staticmethod
    def MIN(q, *vals): return min(vals) if q >=0 else max(vals)

    @staticmethod
    def MAX(q, *vals): return max(vals) if q >= 0 else min(vals)

    @staticmethod
    def nearly_equal(x, y): return abs(x - y) < 1e-8

    @staticmethod
    def is_zero(x): return abs(x) < 1e-8

    @staticmethod
    def between(a, x, b): return x >= b and x <= a if a > b else x >= a and x <= b

    @staticmethod
    def outside_of(x, a, b): return x < b or x > a if a > b else x < a or x > b

    @staticmethod
    def center_pt_radius(sp, ep, r, e=1):
        #http://math.stackexchange.com/questions/27535
        dx, dy = (ep[0]-sp[0], ep[1]-sp[1])
        delta = math.hypot(dx,dy)
        u,v = (dx/delta, dy/delta)
        if delta > abs(2 * r): return "error: G71: Circle radius too small for end points"
        h = math.sqrt(r**2 - (delta**2 / 4))
        # negative R means choose the alternate arc
        # but negative R is troublesome later
        xsum, ysum = (sp[0] + ep[0], sp[1] + ep[1])
        if r < 0:
            xc = xsum / 2 + e * h * v
            yc = ysum / 2 - e * h * u
        else:
            xc = xsum / 2 - e * h * v
            yc = ysum / 2 + e * h * u
        return (xc, yc)

    class data:
        # I see this as a C-struct
        def __init__(self, interp):
            self.list = []
            self.rawpoints = []
            self.retracts = []
            self.Pword = 0     # Block Number of contour beginning (uses N word in beginning block)
            self.Dword = 0     # Roughing Depth per cut
            self.Rword = 0     # Retraction from each cut
            self.Jword = 0     # Overthickness before finishing X (diameter)   (U on other controllers)
            self.Lword = 0     # Overthickness before finishing Z              (W on other controllers)
            self.Iword = 0     # Thickness for finishing at X
            self.Kword = 0     # Thickness for finishing at Z
            self.Fword = 0     # Feedrate override between P and Q blocks
            self.Sword = 0     # Spindle speed override between P and Q blocks
            self.Tword = 0     # Tool for cycle
            self.pmax =  0     # top pocket number
            self.x_begin = 0.
            self.y_begin = 0.
            self.max_depth =  0.0   # maximum depth of profile
            self.miny =  0.0   # minimum y coordinate of profile
            self.mode = None   # rapid/feed mode
            self.oldpocket = 0
            self.int_ext = 0
            self.x_neg = 1.
            self.lathe_diam_mode = interp.params['_lathe_diameter_mode']
            self.lathe_abs_ijk = interp.params['_ijk_absolute_mode'] > 0.0
            self.pq_start = None
            self.pq_end = None
            self.pq_max = [-100000.,-100000.]
            self.pq_min = [100000.,100000.]
            self.approach = 1
            self.z_start = 0.
            self.cutting_x_plus = True
            self.error = ''
            self.warning = ''

        def clear(self):
            self.list = []
            self.rawpoints = []

        def push(self, mode, ps, qs, pe, qe, r, pc, qc, pr=False):
            pocket = 0
            self.max_depth = _g7x.MIN(-self.Dword, self.max_depth, pe + self.Jword, ps + self.Jword)
            # This needs a similar directionality fix
            self.miny = min(self.miny, qs, qe)

            if pr: self.rawpoints.append((mode, qs, ps, qe, pe, r, qc, pc))
            if _g7x.nearly_equal(ps, pe): return
            if _g7x.LT(-self.Dword, pe, ps):
                if self.oldpocket > 0: pocket = self.oldpocket
                self.pmax += 1
                pocket = self.pmax
                self.retracts.append(_g7x.MIN(-self.Dword, self.x_begin, ps - self.Dword + self.Jword))
            elif _g7x.GT(-self.Dword, pe, ps):
                pocket = -abs(self.oldpocket)

            self.oldpocket = pocket
            # X-allowance is added as a profile shift here (including the centre point, even for G0/G1
            # Z-allowance as a delta to cut start and end later
            self.list.append((mode, ps + self.Jword, qs, pe + self.Jword, qe, r, pc + self.Jword, qc, pocket))

    def __init__(self, interp, g7xmode, **words):
        self.d = _g7x.data(interp)
        self.interp = interp
        self.metric = self.interp.params['_metric'] > 1e-8
        self.g7xmode = g7xmode
        self.gcode =''
        self.pre_finish_path = list()
        self.axes = {'X':0, 'Y':1, 'Z':2, 'A':3, 'B':4, 'C':5, 'U':6, 'V':8, 'W':9}

        self.pose = [self.interp.params['_X'], self.interp.params['_Y'], self.interp.params['_Z'],
                     self.interp.params['_A'], self.interp.params['_B'], self.interp.params['_C'],
                     self.interp.params['_U'], self.interp.params['_V'], self.interp.params['_W']]

        self.regex= r'\O0*%(p)i\s*SUB(.*)O0*%(p)i\s*ENDSUB' % words
        self.tool_number = self.interp.params[5400]
        self.tool_radius = tool_radius = self.interp.params[5410]/2.
#       self._tool_number_fixup()
        if self.metric: tool_radius *= 25.4 # tool radius is in imperial units..
        self.calc_tool_radius = tool_radius
        self.tool_orientation = int(self.interp.params[5413])

        # query redis because gremlin may be running from ja..
        try:
            if not hasattr(self,'redis'): self.redis = redis.Redis()
            path = self.redis.hget('machine_prefs','ja_current_path')
            self.redis.hset('machine_prefs','ja_current_path','')
            if path is None or not any(path):
                path = self.interp.filename
            gcode = open(path).read()
            self.gcode = re.findall(self.regex, gcode, re.M | re.S | re.I)
#           self._tool_number_fixup(gcode)
        except IOError:
            t, value, traceback = sys.exc_info()
            print('Error opening %s: %s' % (value.filename, value.strerror))
        except:
            t, value, traceback = sys.exc_info()
            print('Error %s' % (value.strerror))
        if not any(self.gcode):
            self.d.error = "G71 reference P %(p)i but O%(p)i SUB not in file" % words
        else:
            self.gcode = self.gcode[0].split('\n')
        # Be agnostic about plane.
        # P and Q are the plane coordinate letters I and J the centre offsets
        # These are used in the Regex to find the axis letters
        # for G71 P is increment direction (x), Q is feed direction (y)
        # for G72 Q is increment direction (y), P is feed direction (x)

        if self.g7xmode in (710, 711):
            self.flip = 1
            self.P, self.Q, self.I, self.J = _g7x.planes[self.interp.params['_plane']]
        elif self.g7xmode in (720, 721):
            self.flip = -1
            self.Q, self.P, self.J, self.I = _g7x.planes[self.interp.params['_plane']]
        else:
            self.d.error = "G7x mode is not valid!"
            return


        #parse the params...
        if 'd' in words:
            self.d.Dword = abs(words['d'])
        else:
            self.d.error = "G71/72 error, can't work without parameter D"
            return
        self.d.Rword = words['r'] if 'r' in words else self.d.Dword
        if 'j' in words: self.d.Jword = words['j']
        if 'l' in words: self.d.Lword = words['l'] / 1000.0
        else: self.d.Lword = math.fabs(self.d.Jword)
        if 'i' in words: self.d.Iword = words['i']
        if 'k' in words: self.d.Kword = words['k']
        if 't' in words: self.d.Tword = words['t']
        if 'e' in words: self.d.approach = int(words['e'])

        self.d.x_begin = self.pose[self.axes[self.P]]
        self.d.y_begin = self.pose[self.axes[self.Q]]
        self.d.x_neg = -1. if self.d.x_begin < 0 else 1.
        self.d.x_begin *= self.d.x_neg
        self.d.retracts.append(self.d.x_begin)
        # end:.. __init__.......................................................


    @staticmethod
    def _find_intercept(block, x):
        if _g7x.outside_of(x, block[1], block[3]): return 0,0,0
        if block[0] in (0, 1): #  straight line
            #intercept of cut line with path segment
            # t is the normalised length along the line
            t = (x - block[1])/(block[3] - block[1])
            y = block[2] + t * (block[4] - block[2])
            angle = math.atan2(block[3] - block[1], block[4] - block[2]) % math.pi
        elif block[0] in (2, 3): # Arc moves here
            # a circle is x^2 + y^2 = r^2
            # (x - xc)^2 + (y - yc)^2 = r^2
            # (y - yc) = sqrt(r^2 - (x - xc)^2)
            # 2 solutions for a line through a circle
            # because we split the arcs into <= 90 degree sections it
            # is easy to check which solution is between the arc ends
            r = block[5]
            xc = block[6]
            yc = block[7]
            # The "abs" is a sign that there is a problem with rounding somewhere
            dy = math.sqrt(abs(r**2 - (x - xc)**2))
            y = yc + dy
            if (y - block[2]) * (y - block[4]) > 0: y = yc - dy
            if (y - block[2]) * (y - block[4]) > 0: return 0, 0, 0
            angle = (math.pi/2 - math.atan2(x - xc, yc - y)) % math.pi
        return block[8], y, angle

#    def _tool_number_fixup(self, gcode=None):
#        # this is a record of old code that doesn't work and is not needed
#        # TODO: parse gcode to specific subroutine then go backwards to get tool number
#        if gcode is not None:
#            pass
#            tool = re.findall(r'^T\s*?\d{2}(\d{2})?', gcode, re.M | re.S | re.I)
#            if any(tool):
#                tool = tool[0]
#                if tool[1] == ' ' and len(tool) == 4: self.d.Tword = int(tool[2:4])
#                elif tool[0] == 'T': int(tool[1:3])
#                elif tool.isdigit: self.d.Tword = int(tool)
#        else:
#            pass
#        if self.d.Tword != 0 and self.d.Tword != self.tool_number:
#            emccanon.CHANGETOOL(self.d.Tword)


    def _update_tool_angles(self):
        if any(self.d.error): return

        self.frontangle = math.fabs(self.interp.params[5411])
        self.backangle =  math.fabs(self.interp.params[5412])

        self.y_dir = -1. if self.d.list[-1][4] < self.d.list[0][2] else 1.
         #front angle comp...
        dx = math.fabs(self.d.Dword)
        angle = math.fabs(math.radians(self.frontangle))-math.pi/2
        _fac = 0.0
        if angle > 0.: _fac = self.tool_radius + (self.tool_radius/math.cos(angle)+(dx*math.tan(angle)))
        _fac *= _g7x._tool_radius_factor
        self.d.z_start = max(self.d.y_begin,self.d.pq_max[1]+_fac)

    def _gen_pre_finish_path(self):
        if any(self.d.error): return
        del self.pre_finish_path[:]
        if ol._zero(self.d.Iword): return
        outliner = ol(self.metric,
                      self.d.rawpoints,
                      self.d.Iword * self.d.int_ext,
                      self.tool_radius,
                      self.interp.params[5411],    # tool front angle
                      self.interp.params[5412],    # tool back angle
                      self.d.approach,             # approach to the profile
                      self.d.z_start)
        try:
            self.pre_finish_path = outliner.offset_points() if self.d.Iword > 0.0 else self.d.rawpoints
        except FloatingPointError as e:
            del self.pre_finish_path[:]
            self.d.error = str(e)

    def _gen_profile_list(self):
        if any(self.d.error): return
        first_p = first_q = None
        last_p = last_q = None
        self.d.clear()
        x = self.d.x_begin
        y = self.d.y_begin
        self.d.max_depth = self.d.x_begin
        mode = -1

        for block in self.gcode:
            if any(self.d.error): break
            if not any(block): continue
            oldx = x
            oldy = y
            cmds = dict(_g7x.block_toks.findall(block.upper()))

            if self.P in cmds: # P = Z
                x = float(cmds[self.P])*self.d.x_neg
                if self.d.lathe_diam_mode: x = x / 2
                if first_p is None: first_p = x
                last_p = x
                self.d.pq_max[0] = max(self.d.pq_max[0],math.fabs(x))
                self.d.pq_min[0] = min(self.d.pq_min[0],math.fabs(x))
            if self.Q in cmds: #Q = X
                y = float(cmds[self.Q])
                if first_q is None: first_q = y
                last_q = y
                self.d.pq_max[1] = max(self.d.pq_max[1],y)
                self.d.pq_min[1] = min(self.d.pq_min[1],y)

            if 'G' in cmds:
                if cmds['G'] in ('0', '1', '2', '3', '00', '01', '02', '03'):
                    mode = int(cmds['G'])
                    if self.d.mode is None: # Then this is the first block, and sets the cut direction
                        self.d.mode = mode
                        mode = 0 # turn off offsetting on the entry line
                        if x < oldx: self.d.Dword = -1 * self.d.Dword
                        self.d.int_ext = -1. if math.fabs(x) > math.fabs(oldx) else 1.
                else:
                    self.d.error = "G71: invalid G-code G%s" % cmds['G']
                    return

            if mode in (0, 1):
                # simple case so push and continue...
                self.d.push(mode, oldx, oldy, x, y, 0, 0, 0, True)

            elif mode in (2, 3):
               # e is the winding direction
                if self.d.x_neg < 0.: mode = 3 if mode == 2 else 2
                e = 1 if mode == 2 else -1
                e = e * self.flip
                if 'R' in cmds:
                    if 'I' in cmds or 'J' in cmds or 'K' in cmds:
                        self.d.error = "G71: I J K and R are mutually exclusive"
                        return
                    #http://math.stackexchange.com/questions/27535
                    r = float(cmds['R'])
                    tmp = _g7x.center_pt_radius((oldx, oldy),(x, y), r, e)
                    if isinstance(tmp,str):
                        self.d.error = tmp
                        return                        
                    xc, yc = tmp

                else:
                    G901 = not self.d.lathe_abs_ijk
                    if self.I in cmds:
                        xc = oldx + float(cmds[self.I])*self.d.x_neg if G901 else float(cmds[self.I])*self.d.x_neg
                        del cmds[self.I]
                    if self.J in cmds:
                        yc = oldy + float(cmds[self.J]) if G901 else float(cmds[self.J])
                        del cmds[self.J]
                    r = math.hypot((xc - oldx),(yc - oldy))
                    r2 = math.hypot((xc - x), (yc - y))
                    if abs(r - r2) > 0.001:
                        self.d.error = "G71: inconsistent arc centre: r1 = %.4f  .. r2 = %.4f destination (x,z) = %.4f, %.4f" % (r, r2, y, x)
                        return

                # add cardinal points to arcs
                # There is scope for some confusion here about directions.
                # Lathe G-code has G2 (CW) and G3 (ACW) as viewed along positive Y
                # Plotting these curves to check points it is clear that ATAN2(+, +)
                # returns positive angles despite that this is anticlockwise looking
                # along positive Z
                # So, in the geometry here, CW and ACW are reversed compared to the
                # G2 G3 convention.

                a1 = math.atan2(oldx - xc, oldy - yc)
                a2 = math.atan2(x - xc, y - yc)

                d90 = math.pi/2
                if e > 0: # G2 arc Anticlocwise in this CS
                    nesw = d90 * math.ceil(a1 / d90) - d90
                    if a2 > a1:
                        a2 -= 2 * math.pi
                    while nesw > a2:
                        x1 = xc + r * math.sin(nesw)
                        y1 = yc + r * math.cos(nesw)
                        self.d.push(mode, oldx, oldy, x1, y1, r, xc, yc)
                        oldx, oldy = x1, y1
                        nesw -= d90

                elif e < 0: # G3 arc Clockwise in this CS
                    nesw = d90 * math.floor(a1 / d90) + d90
                    if a2 < a1:
                        a2 += 2 * math.pi
                    while nesw < a2:
                        x1 = xc + r * math.sin(nesw)
                        y1 = yc + r * math.cos(nesw)
                        self.d.push(mode, oldx, oldy, x1, y1, r, xc, yc)
                        oldx, oldy = x1, y1
                        nesw += d90
                else:
                    self.d.error = "G71: invalid arc - zero direction"
                    return
                self.d.push(mode, oldx, oldy, x, y, r, xc, yc, True)
        self.d.pq_start = (first_p,first_q)
        self.d.pq_end = (last_p,last_q)
        if not any(self.d.list): self.d.error = 'G71: empty profile'

    def _tool_radius_mod_cut(self, pocket, x, y0, y1, entry, exit, exit_radians, connect, block):
        def __metricise(_x):
            return _x*25.4 if self.metric else _x
        
        def __hyper(_a, _b, _c):
            # fudge factor worked out on desmos by curve fitting empirical
            # data... front angle on 2,3 orientations
            return (1.0/math.sqrt(self.tool_radius/_a))*_b+_c
        
        def __tr_arcsinh(_a, _b, _c):
            # fudge factor worked out on desmos by curve fitting empirical
            # data... front angle on 2,3 orientations
            return math.asinh(_a*self.tool_radius)*_b+_c
               
        def __2_3_exit(_y, _x):
            # fudge factor worked out on desmos by curve fitting empirical
            # data... front angle on 6,8 orientations
            slope = _y/_x
            _angle = math.atan2(_y, _x)-math.pi/4.0
            angle_skew = .8+(.25*self.tool_radius/.125)
            rv = math.tan(_angle)*angle_skew
            _a = .05+(.2-.02)*(self.tool_radius/.125)
            _b = .20+(.25-.10)*(self.tool_radius/.125)
            _c = .03+(.1-.01)*(self.tool_radius/.125)
            _h = __hyper(_a,_b,_c)
            if rv<0.0: rv *=(1.0+_h)
            if rv == 0.0: rv = 1e-8
#           print 'slope = {:.2f}  exit_slope_offset = {:.3f}'.format(slope, rv)
            return rv

        def __6_8_exit(_y, _x):
            # fudge factor worked out on desmos by curve fitting empirical
            # data... front angle on 6,8 orientations
            slope = _y/_x
            _angle = math.atan2(_y, _x)-math.pi/4.0
            rv = math.tan(_angle)
            _a = .05+(.35-.05)*(self.tool_radius/.125)
            _b = .20+(.5-.20)*(self.tool_radius/.125)
            _c = .03+(.2-.03)*(self.tool_radius/.125)
            if rv<0.0: rv *=(1.0+__hyper(_a,_b,_c))
            if rv == 0.0: rv = 1e-8
#           print 'slope = {:.2f}  exit_slope_offset = {:.3f}'.format(slope, rv)
            return rv
        
        def __entry_exit_offset(fa_factor, ba_factor, _exit_f):
            entry_offset = 0.0
            entry_radians = math.atan2(entry-y0,self.d.Dword)
            entry_radians_pct = entry_radians/( math.pi/2.0)     
            entry_offset = entry_radians_pct*self.tool_radius*ba_factor
            _dx = math.fabs(self.d.Dword)
            _dy = math.fabs(exit-y1)
            exit_slope_offset = _exit_f(_dy,_dx)
            exit_offset = self.tool_radius*exit_slope_offset*fa_factor
            return (__metricise(entry_offset), __metricise(exit_offset))
            
#       return (pocket, x, y0, y1, entry, exit, exit_radians)
        tanrads = math.fabs(exit_radians) - math.pi/2.
        if self.tool_orientation in [2,3]:
            iword = self.d.Iword/25.4 if self.metric else self.d.Iword 
            _tro = .003-iword
            _tr_offset = (.0021 - _tro) if _tro>0.0 else 0.0021
            _t_extra = __metricise(__tr_arcsinh(25, 0.03, _tr_offset))
            entry_offset, exit_offset = __entry_exit_offset(__hyper(00.667, 0.099, 0.21), __hyper(0.0113, 0.15, 0.913), __2_3_exit)
            entry -= entry_offset
            y0 -= entry_offset
            exit -= exit_offset+_t_extra
            y1 -= exit_offset+_t_extra
        elif self.tool_orientation in [6,8]:
            _t_extra = __metricise(__tr_arcsinh(-63.0, 0.0103, 0.0065))
            entry_offset, exit_offset = __entry_exit_offset(__hyper(0.667, 0.099, 0.21), __hyper(0.33, 0.06, 0.285), __6_8_exit)
            entry -= entry_offset
            y0 -= entry_offset
            exit -= exit_offset+_t_extra
            y1 -= exit_offset+_t_extra
        elif self.tool_orientation in [1,4]:
            exit += self.tool_radius
            y1 += self.tool_radius
        # link the last 'y1' point with the exit point of this x level if the pocket 
        # is the same...
        pocket_str = str(int(pocket))
        if pocket_str in connect:
            _connect = connect[pocket_str]['last_yend']
            if _connect>exit: exit = _connect
        # adjust pocket 1 for entry (y0)
        if pocket == 1 and self.d.approach>0:
            y0 = entry = self.d.z_start
        # in rare cases when the 'exit' is trying to follow the angle
        # of the profile it can exceed the Z 'max' - so this needs to
        # constrained...
        last_pocket_min = exit
        _last_pocket = pocket
        if _last_pocket>1 and pocket_str not in connect:
            while (_last_pocket > 1):
                if str(int(pocket-1)) in connect:
                    last_pocket_min = connect[str(int(pocket-1))]['min_yend']
                    if last_pocket_min>y1: last_pocket_min = y1
                    break
                _last_pocket -= 1
        z_limit = block[4] + self.d.Lword
        _min_z_ = self.d.pq_min[1] + self.d.Jword;
        exit = max(exit, z_limit, _min_z_, last_pocket_min)
        y1 = max(y1, z_limit)
        return (pocket, x, y0, y1, entry, exit, exit_radians)

    def _gen_cuts(self):
        if any(self.d.error): return
        self.cuts = []
        x = self.d.x_begin
        connect = dict(last=-1e8)
        has_tool = self.interp.params[5400] != 0
        while _g7x.GTE(-self.d.Dword, x + self.d.Dword, self.d.max_depth):
            x = x + self.d.Dword
            y0 = self.d.y_begin - self.y_dir # notional cut-start point, outside the profile
            pocket = -1
            p = 0
            entry = y0
            exit = self.d.miny

            for _d_list_index in range(len(self.d.list)):
                block = self.d.list[_d_list_index]
                #[0]G-code [1]xs [2]ys [3]xe [4]ye [5]r [6]xc [7]yc [8]pocket
                #Find all lines and arcs which span the feed line

                intercept, y, tanangle = _g7x._find_intercept(block, x)
                if intercept == 0: continue

                if intercept < 0 and pocket > 0: # end-of pocket intercept
                    for j in range(_d_list_index, len(self.d.list), 1):
                        p, exit, angle = _g7x._find_intercept(self.d.list[j], x - self.d.Dword)
                        if p != 0: break
                    if math.tan(tanangle) != 0:

                        exit = _g7x.MIN(self.y_dir, exit, y - self.d.Dword/math.tan(tanangle))
                        # Adam kludge to force the first 'exit' to an appropriate value, so it
                        # doesn't do a retract at 'feed' to the Z start point...
                        if not any(self.cuts) and exit == 0.: exit = y - self.d.Dword/math.tan(tanangle)


                    if block[0] == 0:
                        y1 = y
                        exit = y
                    else:
                        y1 = y - self.d.Lword * self.y_dir
                        exit -= self.d.Lword * self.y_dir
                    # skip cuts that are "squeezed-out" by L
                    if _g7x.LT(self.y_dir, y0 , y1):
                        # sometimes we find a second terminator curve further down the profile, so replace the old one
                        if len(self.cuts) > 0 and self.cuts[-1][0] == pocket and self.cuts[-1][1] == x:
                            self.cuts.pop()
                        cutradians = math.atan2(-self.d.Dword, (exit - y1))
                        cut = self._tool_radius_mod_cut(pocket, x, y0, y1, entry, exit, cutradians, connect, block)
                        self.cuts.append(cut)
                        _pocket,_x,_ys,_yend,_entry,_exit,_ = cut
                        #[0]pocket [1]x [2]ystart [3]yend [4]entry [5]exit [6]angle
                        str_pocket = str(int(pocket))
                        if str_pocket not in connect: 
                            connect[str_pocket] = dict(last_yend=_yend, min_yend=_yend)
                        else:
                            connect[str_pocket]['last_yend'] = _yend
                            connect[str_pocket]['min_yend'] = min(_yend,connect[str_pocket]['min_yend'])
                        connect['last'] = _yend
                        # detect gouging, but not for G0 moves
                        cutangle = math.degrees(cutradians) % 360
                        # In / out swap GT / LT. Left / right swaps GT / LT _and_  front / back
#                       print 'exit cutangle = %.2f...frontangle = %.2f' % (cutangle,frontangle)
                        if p != 0 and block[0] != 0 and has_tool and _g7x.LT(self.d.Dword * self.y_dir, cutangle, self.frontangle):
#                           print 'exit cutangle = %.1f...frontangle = %.1f' % (cutangle,self.frontangle)
                            self.d.warning = (("G71: The programmed profile has an exit ramp angle of %.1f and can not be cut "
                                          "with the active tool frontangle of %.1f") % (cutangle,  self.frontangle))

                elif intercept > 0 and intercept != pocket: # start of pocket intercept
                    # don't do pockets if Type1 mode has been forced (G71.1, G72.1)
                    if self.g7xmode in (711, 721) and intercept > 1: break
                    pocket = intercept
                    for j in range(_d_list_index, -1, -1):
                        p, entry, angle = _g7x._find_intercept(self.d.list[j], x - self.d.Dword)
                        if p != 0: break
                    if math.tan(tanangle) != 0:
                        entry = _g7x.MAX(self.y_dir, entry, y - self.d.Dword / math.tan(tanangle))


                    if block[0] == 0:
                        y0 = y
                        entry = y
                    else:
                        cutradians = math.atan2(-self.d.Dword, (entry - y0))
                        y0 = y
                        cutangle = math.degrees(cutradians) % 360
#                       print 'entry cutangle = %.2f ... backangle = %.2f' % (cutangle, backangle)
                        if p != 0 and has_tool and _g7x.GT(self.d.Dword * self.y_dir, cutangle, self.backangle):
#                           print 'entry cutangle = %.1f ... backangle = %.1f' % (cutangle, self.backangle)
                            self.d.warning = (("G71: The programmed profile has an entry ramp angle of %.1f and can not be cut "
                                           "with the active tool backangle of %.1f") % (cutangle,  self.backangle))
        if not any(self.cuts):
            # 0 cuts can occur legitimately if the roughing DOC is greater than the minimal diameter on the profile
            self.d.warning = ("The combination of the start point, initial move and profile blocks "
                              "do not result in any roughing cuts being generated")

    def _cutter_comp(self):
        if self.d.int_ext > 0.: cutter_comp = 'G42' if self.d.x_neg > 0. else 'G41'
        else: cutter_comp = 'G42' if self.d.x_neg < 0. else 'G41'
        return cutter_comp

    def _print_cuts(self):
        print '__pocket__ __x__ __z0__ __z1__ __entry__ __exit__ __angle__'
        for cut in self.cuts: print '%.4f %.4f %.4f %.4f %.4f %.4f %.2f' % (cut)

    def _output_roughing_code(self):
        if any(self.d.error) or not any(self.cuts): return
#       self._print_cuts()
#       self.interp.execute('G42.1 D{:.4f} L{:d}'.format(self.tool_radius*2,self.tool_orientation))
        last_x=0.0
        doc = self.d.Dword*self.d.x_neg
        for p in range(0, self.d.pmax + 1):
            self.pose[self.axes[self.P]] = self.d.retracts[p]*self.d.x_neg
            if math.fabs(last_x)<math.fabs(self.pose[0]): emccanon.STRAIGHT_TRAVERSE(2, *self.pose)
            for c in self.cuts:
                #[0]pocket [1]x [2]ys [3]ye [4]entry [5]exit [6]angle
                pocket,x,ys,ye,entry,exit,a = c
#               print '%d,%.4f,%.4f,%.4f,%.4f,%.4f' % (pocket,x,ys,ye,entry,exit)
                x *= self.d.x_neg
                if pocket == p:
                    self.pose[self.axes[self.Q]] = entry
                    emccanon.STRAIGHT_TRAVERSE(p, *self.pose)
                    self.pose[self.axes[self.P]] = x - doc
                    emccanon.STRAIGHT_TRAVERSE(p, *self.pose)
                    self.pose[self.axes[self.P]] = x
                    self.pose[self.axes[self.Q]] = ys
                    emccanon.STRAIGHT_FEED(p, *self.pose)
                    self.pose[self.axes[self.Q]] = ye
                    emccanon.STRAIGHT_FEED(p, *self.pose)
                    self.pose[self.axes[self.P]] = x - doc
                    self.pose[self.axes[self.Q]] = exit
                    emccanon.STRAIGHT_FEED(p, *self.pose)
                    last_x = x-doc
                    # pre-load the retract in case end of pocket
                    # self.pose[self.axes[self.Q]] = ys

            if math.fabs(last_x)<math.fabs(self.pose[0]):
                emccanon.STRAIGHT_TRAVERSE(5, *self.pose)

        self.pose[self.axes[self.P]] = self.d.x_begin*self.d.x_neg
        emccanon.STRAIGHT_TRAVERSE(2, *self.pose)
        self.pose[self.axes[self.Q]] = self.d.y_begin
        emccanon.STRAIGHT_TRAVERSE(2, *self.pose)
#       self.interp.execute('G40')
        

    def _execute(self, dat):
        # pylint cannot see the interpreter module so it doesn't know about InterpreterException
        #pylint: disable=undefined-variable
        try:
            self.interp.execute(dat['blk'])
            dat['last_blk'] = dat['blk']
        except InterpreterException, e:
            p = 'interp exception between:\n%s and \n%s\n%s' % (dat['last_blk'],dat['blk'],e.error_message)
            if 'gouging' in p: p += ' Try smaller radius on tool %d' % self.tool_number
            self.interp.execute('G40')
            self.d.error = p
            raise Exception('')

    def _output_pre_finish_path(self):
        # p is the 'Z' value, i.e., X on XY
        # q if the 'X' value, i.e., Y on XY
        if any(self.d.error): return
        if self.d.Iword == 0.0: return
        if not any(self.pre_finish_path): return
        dat = { 'blk': '', 'last_blk': ''}
        factor = 2.0 if self.d.lathe_diam_mode else 1.0
        factor *= self.d.x_neg
        try:
            dat['blk'] = 'G0 X%.4f'%(self.d.x_begin*factor)
            self._execute(dat)
            dat['blk'] = 'Z%.4f'%self.d.y_begin
            lastp,lastq = (self.d.y_begin, self.d.x_begin)
            self._execute(dat)
            dat['blk'] = self._cutter_comp()
            self._execute(dat)
            for line in self.pre_finish_path:
                mode,oldp,oldq,p,q,r,cp,cq = line
                if self.d.x_neg < 0.:
                    mode = 2 if mode == 3 else 3
                    cq *= self.d.x_neg
                if ol._zero(r):
                    dat['blk'] = 'G1 X%.4f Z%.4f'%(q*factor,p)
                else:
                    if self.d.lathe_abs_ijk:
                        dat['blk'] = 'G%d X%.4f Z%.4f I%.4f K%.4f'%(mode,q*factor,p,cq,cp)
                    else:
                        dat['blk'] = 'G%d X%.4f Z%.4f I%.4f K%.4f'%(mode,q*factor,p,cq-lastq,cp-lastp)
                    r = math.hypot(cq-lastq,cp-lastp)
                    if r < self.tool_radius:
                        self.d.error = 'arc %s is too small for tool radius' % dat['blk']
                self._execute(dat)
                lastp,lastq = (p,q*self.d.x_neg)
            if self.d.int_ext > 0.:
                if math.fabs(q*factor)<math.fabs(self.d.x_begin*factor):
                    dat['blk'] = 'G1 X%.4f'%(self.d.x_begin*factor)
                    self._execute(dat)
                dat['blk'] = 'G40'
                self._execute(dat)
                dat['blk'] = 'G0 Z%.4f'%self.d.y_begin
                self._execute(dat)
            else:
                dat['blk'] = 'G40'
                self._execute(dat)
                dat['blk'] = 'G0 Z%.4f'%self.d.y_begin
                self._execute(dat)
                dat['blk'] = 'G1 X%.4f'%(self.d.x_begin*factor)
                self._execute(dat)
        except Exception as e:
            if not any(self.d.error): self.d.error = 'output_pre_finish_path: '+str(e)

    def _check_error(self):
        if not any(self.d.error): return INTERP_OK
        return self.d.error

    def run(self):
        # Note: all top level routines must be gated with:
        # 'if any(self.d.error): return'
        self._gen_profile_list()
        self._update_tool_angles()
        self._gen_cuts()
        self._gen_pre_finish_path()
        self._output_roughing_code()
        self._output_pre_finish_path()          
        return self._check_error()        
