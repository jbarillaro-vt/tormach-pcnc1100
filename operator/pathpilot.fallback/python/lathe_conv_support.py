# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

#
# Module for G-code generator support classes
#

# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

import gtk
import math
import cairo
import re
import ui_common
import tooltipmgr

#---------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------
# global functions...
#---------------------------------------------------------------------------------------------------
def remove_gcode_comment(line):
    if not any(line): return line
    start_pos = line.find('(')
    if start_pos < 0: return line
    end_pos = line.find(')')
    return line[:start_pos] + line[end_pos+1:]

def make_gcode_comment(lines):
    def __cmt(l): return '('+l+')'
    if isinstance(lines,str): return __cmt(lines)
    if not any(lines): return lines
    for n,l in enumerate(lines): lines[n] = __cmt(l)
    return lines

#---------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------
# LatheProfileRenderer
#---------------------------------------------------------------------------------------------------
class LatheProfileRenderer(gtk.DrawingArea):
    x_fac = .5             #.5 for diameter mode -  1.for radius mode
    _z_extra = 1.025
    _hit_rect_expand = 0.015
    shown_diameter = 0.575
    below_centerline = 0.075
    inset_percentage = 0.04
    line_color = [(1.0,1.0,0.0),(0.0,1.0,0.0),(0.0,0.0,1.0),(1.0,1.0,1.0),(.65,.65,.65)]
    err_color = (1.0,0.0,0.0)
    angular_clearance = 0. # per issue PP-1533 - [old] was 2 degrees: math.pi/180.*2 # 2 degrees of clearance for tools
    scale_bump = 1.25
    scroll_pt_range = 2
    background = 105.0/255.0 #.4118
    err_color = (1.0,0.,0.)
    hilite_color = (62./255.,224./255.,159./255.)

    def __init__(self, ui, width, height):
        gtk.DrawingArea.__init__(self)
        self.ui = ui
        self.tool = 0
        self.frontangle = 0.
        self.backangle = 0.
        self.orientation = 0
        self.z_len = 0.
        self.set_size_request(width, height)
        self.stock_diameter = 1.0
        inset = int((width / 2) * LatheProfileRenderer.inset_percentage)
        inset = inset + 1 if inset % 2 != 0 else inset
        stock_draw_width = width - 2*inset
        stock_draw_height = height - inset
        self.inset = inset
        self.zoom_level = 0
        self.zoom_bump = 1.
        self.total_diam_in_pixels = float(stock_draw_height) / LatheProfileRenderer.shown_diameter
        self.length_to_height_ratio = float(stock_draw_width) / float(stock_draw_height)
        self.x_draw_width = float(width) - float(inset)
        self.trans_x = self.x_draw_width
        self.trans_y = float(height - int((self.total_diam_in_pixels * LatheProfileRenderer.below_centerline) + 0.5))
        self.scale_x = self.scale_y = 0.
        self.trx = None
        self.scl = None
        self.scroll_pt = None
        self.mouse_pt = None
        self.current_color = None
        self.lines = None
        self.set_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.set_property('can-focus',True)
        self.connect('expose-event', self.__expose)
        self.connect('button-press-event', self.__on_button_press)
        self.connect('scroll-event', self.__on_scroll_event)
        self.connect('key-press-event', self.__on_key_press)
        self.old_focus = None
        self.gen_region_mode = False
        self.internal = False
        self.last_vector = None
        self.error_count = 0
        self.error = None
        self.hilite = None
        self.reset()

    #-----------------------------------------------------------------------------------------------
    # public methods ...
    #-----------------------------------------------------------------------------------------------
    def set_angles(self, tool, fa, ba, orientation=None):
        if orientation is None: orientation = self.orientation
        if orientation in [1,2,3,4,6,8,7]:
            if self.ui.conv_profile_ext != 'external':
                # normalize to positive angles...
                self.frontangle = math.radians(math.fabs(fa))
                self.backangle = math.radians(math.fabs(ba))
            else:
                # normalize to negative angles...
                if fa > 0.: fa = -fa
                if ba > 0.: ba = -ba
                self.frontangle = 2*math.pi + math.radians(fa)
                self.backangle = 2*math.pi + math.radians(ba)
            self.orientation = orientation
            self.tool = tool
        else: self.tool = 0

    def check_angular_error(self):
        ret_val = dict(count=self.error_count,error=self.error)
        self.error_count = 0
        self.error = None
        return ret_val

    def reset(self):
        self.mouse_pt = self.scroll_pt = self.scl = self.trx = None
        self.zoom_level = 0
        self.zoom_bump = 1

    def update(self,reset=True):
        if reset: self.reset()
        self.queue_draw()

    def set_hilite(self, item=None):
        self.hilite = None
        if item is not None and (any(item[0]) or any(item[1])):
            x = item[0] if any(item[0]) else item[2][0]
            if any(x): x = self.ui.dro_long_format % (float(x)*LatheProfileRenderer.x_fac)
            if any(x):
                z = item[1] if any(item[1]) else item[2][1]
                if any(z): self.hilite = (x,z)
        # needed to prevent an endless loop from '__draw_lines_with_color'
        self.update()


    def clr_hilite(self, mod=None):
        if mod is not None and mod == 'no_update':
            self.hilite = None
        else:
            self.set_hilite()

    @classmethod
    def start_pt(cls, pt, diam, z_start):
        x = LatheProfileRenderer.__set_x(float(pt[1])*cls.x_fac if any(pt[1]) else diam/2.)
        if any(pt[2]):
            z = float(pt[2])
            if math.fabs(x)<diam/2.:
                z = max(z,z_start)
        else: z = z_start
        return (z,x)
    
    @staticmethod
    def check_radius(pts, pte, r):
        if ui_common.iszero(r): return True
        try:
            cw,cp = LatheProfileRenderer.center_point_radius((pts[1],-pts[0]),(pte[1],-pte[0]),r)
        except TypeError:
            return False
        except ValueError,FloatingPointError:
            return False
        return True

    @staticmethod
    def min_radius(pts, pte):
        sp,ep = ((pts[1],-pts[0]),(pte[1],-pte[0]))
        dx,dy = dx,dy = (ep[0]-sp[0], ep[1]-sp[1])
        delta = math.hypot(dx,dy)
        return round(delta/2.0+1e-4,4)

    @staticmethod
    def center_point_radius(curr_pt, next_pt, r):
        flip = 1.
        cw = r > 0.
        if not cw:
            r = math.fabs(r)
            flip = -1.
        return (cw,LatheProfileRenderer.__ctr_pt_radius(curr_pt, next_pt, r, flip))

    @staticmethod
    def gcode_arc_data(cp, np, r, x_sign):
        ad = LatheProfileRenderer.__arc_data((cp[0],-cp[1]),(np[0],-np[1]),r)
        start_radians = ad[1] if x_sign > 0. else math.pi*2.-ad[1]
        final_radians = ad[2] if x_sign > 0. else math.pi*2.-ad[2]
        # invert the sign on the center point 'X' value to get from graphic space
        # to X+/X- space
        cp = (ad[0][0], -ad[0][1])
        cw = ad[3] if x_sign > 0. else not ad[3]
        # tweek start_radians if final_radians  == 0
        if start_radians == 0. and final_radians > math.pi: start_radians = 2.*math.pi
        return (cp, start_radians, final_radians, cw)

    # public_method
    @staticmethod
    def arc(cr, cp, cw, start_radians, final_radians, r):
        if cw:
            if final_radians == 0.0: final_radians = 2.0*math.pi
            cr.arc(cp[0], cp[1], math.fabs(r), start_radians, final_radians)
        else:
            if start_radians == 0.0: start_radians = 2.0*math.pi
            cr.arc_negative(cp[0], cp[1], math.fabs(r), start_radians, final_radians)

    @staticmethod
    def zero_distance_segment(pt_a, pt_b):
        # returns true is the deltas between points 'a' and 'b' are effectively zero...
        return ui_common.iszero(pt_a[0]-pt_b[0]) and ui_common.iszero(pt_a[1]-pt_b[1])

    #-----------------------------------------------------------------------------------------------
    # private methods ...
    #-----------------------------------------------------------------------------------------------
    def __update_zoom_pt(self, event):
        if self.scroll_pt is None: self.scroll_pt =  self.mouse_pt = (event.x,event.y)
        elif math.fabs(event.x-self.mouse_pt[0])>LatheProfileRenderer.scroll_pt_range or \
             math.fabs(event.y-self.mouse_pt[1])>LatheProfileRenderer.scroll_pt_range:
            dx,dy = ((event.x-self.mouse_pt[0])/self.zoom_bump,(event.y-self.mouse_pt[1])/self.zoom_bump)
            self.scroll_pt = (self.scroll_pt[0]+dx,self.scroll_pt[1]+dy)
            self.mouse_pt = (event.x,event.y)
#           print '%.2f, %.2f dx: %.2f dy: %.2f'%(self.scroll_pt[0],self.scroll_pt[1],dx,dy)

    def __zoom(self, event):
        self.__update_zoom_pt(event)
        self.grab_focus()
        dx,dy = (self.trans_x-self.scroll_pt[0],self.trans_y-self.scroll_pt[1])
        self.zoom_bump *= LatheProfileRenderer.scale_bump if event.direction == gtk.gdk.SCROLL_UP else 1.0/LatheProfileRenderer.scale_bump
        self.scl = (self.scale_x*self.zoom_bump, self.scale_y*self.zoom_bump)
        self.trx = (self.trans_x+self.zoom_bump*dx-dx,self.trans_y+self.zoom_bump*dy-dy)
        self.set_can_focus(True)

    def __on_scroll_event(self, widget, event):
        if self.scl is None: return
        self.zoom_level += 1 if event.direction == gtk.gdk.SCROLL_UP else -1
        self.reset() if self.zoom_level <= 0 else self.__zoom(event)
        self.queue_draw()

    def __on_key_press(self, widget, event):
#       print 'got the key press'
        if event.keyval == gtk.keysyms.Escape:
            self.update()

    @staticmethod
    def __pt_in_rect(pt,rect):
        return pt[0]<rect[0] and pt[0]>=rect[2] and pt[1]>rect[1] and pt[1]<=rect[3]

    def __on_button_press(self, widget, event, data=None):
        # x,y - 0,0 is upper left corner of draw area...
        # all values are in terms of part dimensions...
        if not any(self.lines): return
        dx,dy = (self.trx[0]-event.x,self.trx[1]-event.y)
        z,x = (-dx/self.scl[0],dy/self.scl[1])
        lx = float(self.lines[0][1])*LatheProfileRenderer.x_fac if any(self.lines[0][1]) else 0.
        lz = self.z_start
        for n,line in enumerate(self.lines):
            if LatheProfileRenderer.__is_no_line(line): return
            cx = float(line[1])*LatheProfileRenderer.x_fac if any(line[1]) else lx
            cz = float(line[2]) if any(line[2]) else lz
            if not any(line[3]): rect = (lz,min(lx,cx),cz,max(lx,cx))  # simple rectangle
            else:
                # create a rectangle around an arc segment
                r = float(line[3])
                try:
                    cw,cp = LatheProfileRenderer.center_point_radius((lz,-lx),(cz,-cx),r)
                    ox = max(lx,cx) if r > 0. else min(lx,cx)
                    rx = math.fabs(cp[1])-r
                    rect = (lz,min(ox,rx),cz,max(ox,rx))
                except ValueError as e:
                    # the radius failed .. try to make a simple box
                    rect = (lz,min(lx,cx),cz,max(lx,cx))
            dz,dx = (cz-lz,cx-lx)
            hre = LatheProfileRenderer._hit_rect_expand / self.zoom_bump
            if dz<hre: rect = (rect[0]+hre,rect[1],  rect[2]-hre, rect[3])
            if dx<hre: rect = (rect[0], rect[1]-hre, rect[2], rect[3]+hre)
#           print 'hre: %.4f z: %.4f x: %.4f rct[0] %.4f rct[1] %.4f rct[2]: %.4f rct[3]: %.4f' % (hre,z,x, rect[0], rect[1], rect[2], rect[3])
            if LatheProfileRenderer.__pt_in_rect((z,x),rect):
                sel = self.ui.profile_treeview.get_selection()
                cols = self.ui.profile_treeview.get_columns()
                _stop = False
                for col in cols:
                    renderers = col.get_cell_renderers()
                    for renderer in renderers:
                        if renderer.get_property('editing'):
                            renderer.stop_editing(True)
#                           renderer.queue_draw()
                            _stop = True
                            break
                    if _stop: break
                sel.select_path(n)
                self.ui.dt_scroll_adjust(n)
                return
            lx = cx
            lz = cz

    def __is_hilite(self, cr, z, x):
        return not self.gen_region_mode and self.hilite and math.fabs(x) == float(self.hilite[0]) and z == float(self.hilite[1])

    def __get_current_stock_dims(self):
        stock_diameter_text = self.ui.profile_dro_list['profile_stock_x_dro'].get_text()
        if not any(stock_diameter_text): stock_diameter_text = '1.0'
        stock_z_start_text = self.ui.profile_dro_list['profile_stock_z_dro'].get_text()
        if not any(stock_z_start_text): stock_z_start_text = '0.0'
        return (stock_diameter_text, stock_z_start_text)

    def __min_x(self, lst):
        mx = self.stock_diameter
        for line in lst:
            if line[1] == '': continue
            mx = min(mx,float(line[1]))
        return mx if mx != self.stock_diameter else mx

    def __bump_error(self, local_error_str, line_number=None):
        self.error_count += 1
        if local_error_str: self.error = tooltipmgr.TTMgr().get_local_string(local_error_str)
        if line_number: self.error = self.error.format(line_number)
        #always return False
        return False

    @staticmethod
    def __min_z_list(mz, lst):
        for line in lst:
            if line[2] != '': mz = min(mz, float(line[2]))
        return mz

    def __min_z(self, draw_list):
        ret_z = float(self.ui.profile_dro_list['profile_stock_z_dro'].get_text())
        if isinstance(draw_list,list): return LatheProfileRenderer.__min_z_list(ret_z, draw_list)
        if isinstance(draw_list,tuple):
            for lst in draw_list: ret_z = LatheProfileRenderer.__min_z_list(ret_z, lst)
        return ret_z

    def __expose(self, widget, event):
        self.last_vector = None
        self.lines = self.ui.profile_liststore_to_list('compress')
        self.internal = self.ui.conv_profile_ext != 'external'
        cr = widget.window.cairo_create()
        width,height = widget.window.get_size()
        self.__profile_draw_backfill(cr, width, height)
        sd,sz = self.__get_current_stock_dims()
        self.stock_diameter = float(sd)
        self.z_start = float(sz)
        self.mz = self.__min_z(self.lines)
        self.z_len = (self.z_start - self.mz) * LatheProfileRenderer._z_extra # 1.025
        scale_x = self.total_diam_in_pixels / self.stock_diameter
        scale_z = scale_x if (self.z_len * scale_x ) < self.x_draw_width else self.x_draw_width / self.z_len
        self.scale_x = self.scale_y = min(scale_x, scale_z)
        self.trans_x = self.x_draw_width - (self.z_start * self.scale_x)
        # from here drawing will occure in transmuted coordinates
        if self.trx is None: self.trx = (self.trans_x, self.trans_y)
        if self.scl is None: self.scl = (self.scale_x, self.scale_y)
        self.__draw_all(cr)

    def __draw_all(self, cr):
        # from here drawing will occure in transmuted coordinates
        cr.translate(self.trx[0],self.trx[1])
        cr.scale(self.scl[0], self.scl[1])
        stock_length = max(self.z_len,self.stock_diameter * self.length_to_height_ratio)
        self.__profile_draw_stock(cr,stock_length,self.stock_diameter)
        self.__profile_draw(cr)

    def __profile_draw_backfill(self, cr, width, height):
        grey = LatheProfileRenderer.background
        cr.set_source_rgb(grey, grey, grey)
        cr.rectangle(0, 0, width,height)
        cr.fill()

    def __profile_gen_cutaway_region(self, cr, lines, diameter):
        if not any(lines) or LatheProfileRenderer.__is_no_line(lines[0]): return
        start_x = -diameter if self.ui.conv_profile_ext == 'external' else diameter
        self.gen_region_mode = True
        cr.new_path()
        cr.move_to(self.z_start, start_x)
        last_zx = self.__gen_lines(cr, lines)
        cr.line_to(last_zx[0], start_x)
        self.gen_region_mode = False

    def __profile_draw_cut_away(self, cr, length, diameter):
        lines = self.lines if isinstance(self.lines,list) else self.lines[0]
        mx = self.__min_x(lines)
        if mx == self.stock_diameter: mx = mx/4.
        grey = LatheProfileRenderer.background
        self.__profile_gen_cutaway_region(cr, lines, diameter)
        cr.set_source_rgb(grey, grey, grey)
        cr.fill()

    def __profile_draw_centerline(self, cr, length):
        cr.new_path()
        cr.set_source_rgba(1.0,1.0,1.0,0.6)
        cr.set_line_width( 1.0 / self.scale_y * 2)
        cr.set_dash([1.0 / self.scale_y * 6],0)
        cr.move_to(self.z_start,0)
        cr.line_to(-length,0)
        cr.stroke()

    def __profile_draw_X0(self, cr):
        cr.select_font_face('Bebas', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(10./self.scale_x)
        (x, y, width, height, dx, dy) = cr.text_extents("X0.0")
        x_start = -self.x_draw_width/self.scale_x+width/2.
        cr.set_source_rgba(1.0,1.0,1.0,0.6)
        cr.move_to(x_start,height/2.)
        cr.show_text('X0.0')
        cr.stroke()

    def __profile_draw_stock(self, cr, length, diameter):
        cr.save()
        cr.set_source_rgba(float(95/255), float(106/255), .5,.2)
        cr.rectangle(self.z_start, -diameter/2., -length, diameter )
        cr.fill()
        self.__profile_draw_cut_away(cr, length, diameter)
        self.__profile_draw_centerline(cr, length)
        self.__profile_draw_X0(cr)
        cr.restore()

    @staticmethod
    def __ctr_pt_radius(sp, ep, r, e=1.):
        #http://math.stackexchange.com/questions/27535
        dx,dy = (ep[0]-sp[0], ep[1]-sp[1])
        delta = math.hypot(dx,dy)
        if delta > abs(2 * r): raise ValueError('error: G71: Circle radius too small for end points')
        if delta == 0.0: raise ValueError('error: G71: start and end points identical')
        u,v = (dx/delta, dy/delta)
        h = math.sqrt(r**2 - (delta**2 / 4))
        # negative R means choose the alternate arc
        xsum, ysum = (sp[0] + ep[0], sp[1] + ep[1])
        return (xsum / 2 + e * h * v, ysum / 2 - e * h * u) if r < 0. \
        else (xsum / 2 - e * h * v, ysum / 2 + e * h * u)

    @staticmethod
    def __to_radians(cp, pt, r, cw, err=0.000225):
        i,k = (pt[0]-cp[0], pt[1]-cp[1])   # this is just the points works from the drawing
        if math.fabs(i) < err: i = 0.
        if math.fabs(k) < err: k = 0.
        if i == 0.: return (math.pi/2.,i,k) if cw else (math.pi*1.5,i,k)
        if k == 0.: return (0.,i,k) if cw else (math.pi,i,k)
        angle = math.asin(k/math.fabs(r)) # normalized opposite / hypot relative to center point
        return (angle,i,k)

    @staticmethod
    def __profiler_radians(cp, pt, r, cw):
        angle, i, k = LatheProfileRenderer.__to_radians(cp, pt, r, cw)
        if i < 0. and k > 0.: angle = math.pi - angle                           # quadrant 2
        elif i < 0. and k < 0.: angle = math.pi - angle                         # quadrant 3
        elif i > 0. and k < 0.: angle = 2*math.pi + angle                       # quadrant 4
        elif i == 0.: return math.pi/2. if k > 0. else math.pi*1.5
        elif k == 0.: return 0. if i > 0. else math.pi
        return angle


    @staticmethod
    def __arc_data(curr_pt, next_pt, r):
        cw,cp = LatheProfileRenderer.center_point_radius(curr_pt, next_pt, r)
        start_radians = LatheProfileRenderer.__profiler_radians(cp, curr_pt, r, cw)
        final_radians = LatheProfileRenderer.__profiler_radians(cp, next_pt, r, cw)
        return (cp, start_radians, final_radians, cw)

    @staticmethod
    def __is_no_line(line):
        return not any(line[1]) and not any(line[2]) and not any(line[3])

    @staticmethod
    def __raw_vector(line):
        sp,ep = (line[0], line[1])
        dz,dx = (ep[0]-sp[0],sp[1]-ep[1]) # X axis is inverted
        h = math.hypot(dz,dx)
        if h<1e-8: return None
        if math.fabs(dz)<1e-8: return math.pi/2. if dx<0. else math.pi*3./2.
        if math.fabs(dx)<1e-8: return math.pi if dz<0. else 0.
        _a = math.asin(dx/h)
        _b = math.pi/2.-(math.fabs(_a))
        if _a<0.:
            _a = math.fabs(_a)
            if dz>0.: return math.fabs(_a)
            else: return math.fabs(_a)+2.*_b
        elif dz>0: return math.pi*2.-_a
        return math.pi+_a

    def __color_seg(self, cr, col, last_zx, zx, data=None):
        cr.stroke()
        cr.move_to(last_zx[0], last_zx[1])
        cr.set_source_rgb(col[0],col[1],col[2])
        if not data: cr.line_to(zx[0],zx[1])
        else: LatheProfileRenderer.arc(cr, data[0], data[1], data[2], data[3], data[4])
        cr.stroke()
        cr.set_source_rgb(self.current_color[0],self.current_color[1],self.current_color[2])
        cr.move_to(zx[0],zx[1])


    def __valid_vector(self, line):
        if self.gen_region_mode: return True
        vec = LatheProfileRenderer.__raw_vector(line)
        if vec is None: return True
        ta = LatheProfileRenderer.angular_clearance
        if self.orientation in [2,3,6,8]:
            fa,ba = (self.frontangle+ta,self.backangle-ta) if self.internal else (self.frontangle-ta,self.backangle+ta)
        elif self.orientation in [1,4]:
            fa,ba = (self.backangle+ta,self.frontangle-ta) if self.internal else (self.backangle-ta,self.frontangle+ta)
        else:  # not supported tool angle
            return self.__bump_error('err_lathe_profile_tool_angle')
        if self.last_vector is None: self.last_vector = vec
        else:
            vec_diff = math.fabs(math.fabs(self.last_vector-vec)-math.pi)
#           print vec_diff*180/math.pi
            self.last_vector = vec
            if vec_diff>1e-8 and vec_diff <= math.fabs(fa-ba): return self.__bump_error('err_lathe_profile_combined_tool_angle')
        if self.internal:
            if vec <= fa: return self.__bump_error('err_lathe_profile_front_tool_angle')
            if vec >= ba+math.pi: return self.__bump_error('err_lathe_profile_rear_tool_angle')
            if fa>vec>ba: return self.__bump_error('err_lathe_profile_angle_not_compat')
        else:
            if vec >= fa: return self.__bump_error('err_lathe_profile_front_tool_angle')
            if vec <= ba-math.pi: return self.__bump_error('err_lathe_profile_rear_tool_angle')
            if fa<vec<ba: return self.__bump_error('err_lathe_profile_angle_not_compat')   # external so fail on vec >= leading edge
        return True

    @staticmethod
    def __tangent_vector(radian, r):
        half_pi = math.pi/2.
        sp = (0.,0.)
        if r < 0.:
            tr = radian - half_pi
            if round(tr-half_pi,6) == 0.: return (sp,(0.,1.))
        else:
            tr = radian + half_pi
            if round(tr-half_pi,6) == 0.: (sp,(0.,-1.))
        return (sp,(math.cos(tr),math.sin(tr)))

    def __valid_radians(self, start_radian, final_radian, r):
        sv = LatheProfileRenderer.__tangent_vector(start_radian, r)
        fv = LatheProfileRenderer.__tangent_vector(final_radian, r)
        # need to test both to setup 'last_vec' in '__valid_vector'
        ret_val = self.__valid_vector(sv)
        ret_val = self.__valid_vector(fv) and ret_val
        return ret_val

    def __add_line(self, cr, line_number, z ,x ,last_zx):
        if self.__valid_vector((last_zx,(z,x))):
            if self.__is_hilite(cr, z, x): self.__color_seg(cr, LatheProfileRenderer.hilite_color, last_zx, (z,x))
            else: cr.line_to(z,x)
        else:
            self.__color_seg(cr, LatheProfileRenderer.err_color, last_zx, (z,x))

    def __add_arc(self, cr, line_number, z, x, last_zx, r):
        if not r: return False
        r = round(float(r),5)
        if r == 0.0: return False
        try:
            ad = LatheProfileRenderer.__arc_data(last_zx, (z,x), r)
        except ValueError:
            return self.__bump_error('err_lathe_profile_full_cirle_arc', line_number)
        cp, start_radians, final_radians, cw = ad
        if round(start_radians,4) == 0. and final_radians > math.pi: start_radians = 2.*math.pi
        if self.__valid_radians(start_radians, final_radians, r):
            if self.__is_hilite(cr, z, x): self.__color_seg(cr, LatheProfileRenderer.hilite_color, last_zx, (z,x), (cp, cw, start_radians, final_radians, r))
            else: LatheProfileRenderer.arc(cr, cp, cw, start_radians, final_radians, r)
        else:
            self.__color_seg(cr, LatheProfileRenderer.err_color, last_zx, (z,x), (cp, cw, start_radians, final_radians, r))
        return True

    @staticmethod
    def __set_x(x):
        return -x

    def __add_path(self, cr, line, last_zx):
        z = float(line[2]) if any(line[2]) else last_zx[0]
        x = LatheProfileRenderer.__set_x(float(line[1])*LatheProfileRenderer.x_fac) if any(line[1]) else last_zx[1]
        if LatheProfileRenderer.__is_no_line(line): return None
        if not self.__add_arc(cr, line[0], z, x, last_zx, line[3]):
            self.__add_line(cr, line[0], z, x, last_zx)
        return (z,x)

    @staticmethod
    def __zero_distance_segment(line, last_zx):
        z = float(line[2] if any(line[2]) else last_zx[0])        
        x = LatheProfileRenderer.__set_x(float(line[1])*LatheProfileRenderer.x_fac) if any(line[1]) else last_zx[1]       
        return LatheProfileRenderer.zero_distance_segment((z,x), last_zx)
    
    def __gen_lines(self, cr, lst):
        last_zx = LatheProfileRenderer.start_pt(lst[0], self.stock_diameter, self.z_start)
        cr.line_to(last_zx[0], last_zx[1])
        for line in lst:
#           if LatheProfileRenderer.__zero_distance_segment(line, last_zx): continue
            last = self.__add_path(cr, line, last_zx)
            if last is None: break
            last_zx = last
        return last_zx

    def __draw_lines_with_color(self, cr, col_selector, lst):
        if not any(lst) or LatheProfileRenderer.__is_no_line(lst[0]):
            self.clr_hilite('no_update')
            return
        cr.new_path()
        self.current_color = LatheProfileRenderer.line_color[col_selector]
        cr.set_source_rgb(self.current_color[0],self.current_color[1],self.current_color[2])
        cr.set_line_width( 1.0 / self.scale_y * 1.5)
        self.__gen_lines(cr, lst)
        cr.stroke()


    def __profile_draw(self, cr=None, draw_list=None):
        self.error_count = 0
        self.error = None
        cr.save()
        col_selector = 0
        if draw_list is None: draw_list = self.lines
        if isinstance(draw_list, list): self.__draw_lines_with_color(cr, col_selector, draw_list)
        else:
            for lst in draw_list:
                self.__draw_lines_with_color(cr, col_selector, lst)
                col_selector = 0 if col_selector == len(LatheProfileRenderer.line_color)-1 else col_selector+1

        cr.restore()

#---------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------
# ListToGcode
#---------------------------------------------------------------------------------------------------

class ListToGcode():
    spec = re.compile(r'\s?\-?\d*\.\d+')
    block_toks = re.compile('(\w)\s*([-+,\.\d]+)', re.S | re.I)
    _blank = '       '
    _profile_list_tag = '(--profile list--)'
    _profile_list_end_tag = '(--profile list end--)'


    @staticmethod
    def _get_sub(gcode):
        _gcode = gcode.split('\n')
        g = []
        parsing = False

        for line in _gcode:
            line = remove_gcode_comment(line)
            if not any(line): continue
            if not parsing and 'SUB' in line: parsing = True
            elif parsing:
                if 'ENDSUB' in line: break
                g.append(line)
        return (g, len(g))

    @staticmethod
    def _get_profile_comments(gcode):
        _gcode = gcode.split('\n')
        g = []
        parsing = False

        for line in _gcode:
            if not any(line): continue
            if not parsing and ListToGcode._profile_list_tag in line: parsing = True
            elif parsing:
                if  ListToGcode._profile_list_end_tag in line: break
                line = line[1:-1]
                line = line.strip(')')
                line = line.strip()
                g.append(line)
        return (g, len(g))

    @staticmethod
    def to_true_list(gcode, points_limit, x_sign, format_spec):
        points_list = []
        x_fac = .5 if LatheProfileRenderer.x_fac>.5 else 1.
        try:
            _gcode,num_lines = ListToGcode._get_profile_comments(gcode)
            if not num_lines: return ListToGcode.to_list(gcode, points_limit, x_sign, format_spec)
            n = line_number = 0

            while n < num_lines:
                cmds = dict(ListToGcode.block_toks.findall(_gcode[n].upper()))
                x = format_spec % (float(cmds['X'])*x_fac) if 'X' in cmds else ''
                z = format_spec % (float(cmds['Z']))       if 'Z' in cmds else ''
                r = format_spec % (float(cmds['R']))       if 'R' in cmds else ''
                line_number += 1
                points_list.append((str(line_number),x,z,r))
                n += 1

            for n in range(line_number, points_limit):
                points_list.append((str(n+1),'','',''))
        except:
            print 'Exception ocurred in to_actual_list'
            return []
        return points_list

    @staticmethod
    def to_list(gcode, points_limit, x_sign, format_spec):
        points_list = []
        x_fac = .5 if LatheProfileRenderer.x_fac>.5 else 1.
        try:
            gcode,num_lines = ListToGcode._get_sub(gcode)
            n = line_number = 0

            while n < num_lines:
                cmds = dict(ListToGcode.block_toks.findall(gcode[n].upper()))
                cmds_next = dict(ListToGcode.block_toks.findall(gcode[n+1].upper())) if n+1 < num_lines else ''
                r = ''
                g = cmds['G']                                     if 'G' in cmds else ''
                x = format_spec % (float(cmds['X'])*x_fac*x_sign) if 'X' in cmds else ''
                z = format_spec % (float(cmds['Z']))              if 'Z' in cmds else ''
                i = format_spec % (float(cmds['I'])*x_sign)       if 'I' in cmds else ''
                k = format_spec % (float(cmds['K']))              if 'K' in cmds else ''
                if any (i) or any(k):
                    r = format_spec % math.hypot(float(i),float(k)) if any(k) and any(i) else ''
                    if any(cmds_next): # look ahead..
                        ng = cmds_next['G']                               if 'G' in cmds else ''
                        ni = format_spec % (float(cmds_next['I'])*x_sign) if 'I' in cmds_next else ''
                        nk = format_spec % (float(cmds_next['K'])*x_sign) if 'K' in cmds_next else ''
                        if any(ni) and any(nk):
                            nr = format_spec % math.hypot(float(ni),float(nk))
                            if nr == r and g == ng:
                                x = format_spec % (float(cmds_next['X'])*x_fac*x_sign) if 'X' in cmds_next else ''
                                z = format_spec % (float(cmds_next['Z']))              if 'Z' in cmds_next else ''
                                n += 1
                        if any(g):
                            if x_sign > 0. and g == '3': r = '-' + r
                            elif x_sign < 0. and g == '2': r = '-' + r
                n += 1
                if any(x) or any(z) or any(r):
                    line_number += 1
                    points_list.append((str(line_number),x,z,r))

            for n in range(line_number, points_limit):
                points_list.append((str(n+1),'','',''))
        except:
            print 'Exception ocurred in _ja_parse_profile'
            return []
        return points_list

    @staticmethod
    def __list_to_comment(model):
        out_list = []
        _X, _Z, _R = range(1,4)
        blank = '       '
        for row in model:
            if not any(row[_X]) and not any(row[_Z]) and not any(row[_R]): continue
            line = '('
            line += 'X'+row[_X]+' ' if any(row[_X]) else ''
            line += 'Z'+row[_Z]+' ' if any(row[_Z]) else ''
            line += 'R'+row[_R]+' ' if any(row[_R]) else ''
            line = line[:-1] + ')'
            out_list.append(line)
        if any(out_list):
            out_list.insert(0,ListToGcode._profile_list_tag)
            out_list.append(ListToGcode._profile_list_end_tag)
        return out_list

    @staticmethod
    def to_gcode(metric, is_external, model, x_sign, dro_fmt, stock_diam, stock_z, start_z, tool_clear_x):
        line_prefix = ' '
        len_line_prefix = len(line_prefix)
        profile_list = ListToGcode.__list_to_comment(model)
        _X, _Z, _R = range(1,4)
        subroutine_list = []
        last_valid_row = len(model)
        approach = ListToGcode.first_x(model, last_valid_row, stock_diam, stock_z)[0]
        one_half_pi = math.pi/2.
        three_half_pi = math.pi+one_half_pi
        arc_thresh = 0.00254 if metric else 0.0001
        diam_factor = 2.*x_sign
        factor = diam_factor*LatheProfileRenderer.x_fac # x_fac will be: .5 for diameter mode -  1.for radius mode
        # for determining an internal safe_x
        # start with a big'ol large number
        min_x = 10000000.

        # first line
        first_x = math.fabs(float(model[0][_X])) * factor
        first_z = float(model[0][_Z])
        curr_x = '%s' % (dro_fmt) % (first_x)
        curr_z = '%s' % (dro_fmt) % (stock_z)
        # insert a first Z move if *implied* by the drawing
        if first_x < stock_diam and approach >= stock_z:
            # check to see if the line wasn't already there...
            if start_z > first_z:
                subroutine_list.append(line_prefix+('G1 X%s Z%s' % (dro_fmt,dro_fmt) % (first_x,start_z)))
                curr_z = '%s' % (dro_fmt) % (start_z)
        # ** ALL x points from the liststore are X+
        for n in range(last_valid_row):
            x,z,r = (model[n][_X], model[n][_Z], model[n][_R])
            if not any(x) and not any(z): continue
            if any(x):
                x = (dro_fmt) % (float(x)*factor)
                min_x = min(min_x,float(x)*factor)
            # check the current and 'last' pts are different
            # if the are the same for any reason (radius doesn't matter) - skip
            test_x = x if any(x) else curr_x
            text_z = z if any(z) else curr_z
            if LatheProfileRenderer.zero_distance_segment((float(test_x),float(text_z)), (float(curr_x),float(curr_z))): continue
            # start a new line
            line = line_prefix
            if any(r) and float(r) == 0.0: r = ''
            if not any(r):
                rapid = n == 0 and any(z) and float(z) < stock_z and any(x) and float(x) >= stock_diam
                line += 'G0' if rapid else 'G1'
                i = k = ''
                line += ' X%s' % (x if any(x) else curr_x)
                line += ' Z%s' % (z if any(z) else curr_z)
            else:
                _lx = float(curr_x)
                _x = float(x) if any(x) else _lx
                _lz = float(curr_z)
                _z = float(z) if any(z) else _lz
                _r = float(r)
                
                try:
                    ad = LatheProfileRenderer.gcode_arc_data((_lz,_lx/diam_factor),(_z,_x/diam_factor),_r,x_sign)
                except ValueError as e:
                    raise ValueError('Line %d (or profile): %s'%(n+1,str(e)))
                cp, start_radians, final_radians, cw = ad
                ck, ci = cp
                _i = (ci-_lx/diam_factor)*x_sign
                _k = ck-_lz
                if math.fabs(_i) < arc_thresh: _i = 0.
                if math.fabs(_k) < arc_thresh: _k = 0.
                rotate = 'G2' if cw else 'G3'
                if cw and start_radians < one_half_pi and math.fabs(start_radians-one_half_pi)>1e-4 and final_radians > one_half_pi:
                    _lx,_lz = ((ci-_r)*diam_factor, ck)
                    line = line_prefix + rotate + ' X%s Z%s I%s K%s' % (dro_fmt,dro_fmt,dro_fmt,dro_fmt) % (_lx,_lz,_i,_k)
                    subroutine_list.append(line)
                    _i = math.fabs(_r)
                    _k = 0.
                elif not cw and start_radians > three_half_pi and math.fabs(start_radians-three_half_pi)>1e-4 and final_radians < three_half_pi:
                    _lx,_lz = ((ci-_r)*diam_factor, ck)
                    line = line_prefix + rotate + ' X%s Z%s I%s K%s' % (dro_fmt,dro_fmt,dro_fmt,dro_fmt) % (_lx,_lz,_i,_k)
                    subroutine_list.append(line)
                    _i = _r if _r < 0. else -_r
                    _k = 0.
                i = (dro_fmt) % (_i)
                k = (dro_fmt) % (_k)
                line = line_prefix + rotate
                line += ' X%s' % (x if any(x) else curr_x)
                line += ' Z%s' % (z if any(z) else curr_z)
            if any(i): line += ' I%s' % (i)
            if any(k): line += ' K%s' % (k)
            if any(x): curr_x = x
            if any(z): curr_z = z
            subroutine_list.append(line)
        # fixup last 'X' move if less than 'stock_diam'
        last_x = float(curr_x)
        if is_external:
            if math.fabs(last_x)<math.fabs(stock_diam):
                line = line_prefix + 'G1 X{}'.format(dro_fmt%(stock_diam*x_sign))
                subroutine_list.append(line)
        else:
            x_complete = min(first_x*x_sign, tool_clear_x)
            if last_x*x_sign>x_complete:
                line = line_prefix + 'G1 X{}'.format(dro_fmt%(x_complete*x_sign))
                subroutine_list.append(line)
        return (profile_list,subroutine_list, min_x, approach, len_line_prefix, last_x)

    @staticmethod
    def first_x(model, last_valid_row, diam, stock_z):
        if last_valid_row == 0: return (stock_z, diam)
        return LatheProfileRenderer.start_pt(model[0], diam, stock_z)

#---------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------
# ToolRenderer - and event box wrapper to allow tooltips
#---------------------------------------------------------------------------------------------------
class ToolRenderer(gtk.EventBox):

    def __init__(self, ui, wh):
        super(ToolRenderer,self).__init__()
        self.tr = ToolRenderer._toolrenderer(ui, wh)
        gtk.Buildable.set_name(self, 'profile_tool_renderer')
        self.set_size_request(wh, wh)
        self.set_visible_window(False)
        self.add(self.tr)
        self.set_above_child(True)
        self.connect('enter-notify-event', ui.on_mouse_enter)
        self.connect('leave-notify-event', ui.on_mouse_leave)

    def set_angles(self, tool, radius, fa, ba, orientation=None, update=True):
        self.tr.set_angles(tool, radius, fa, ba, orientation, update)

    #---------------------------------------------------------------------------------------------------
    # _toolrenderer -does the actual work
    #---------------------------------------------------------------------------------------------------
    class _toolrenderer(gtk.DrawingArea):

        _origin_factor = 8.
        _std_dim = .25
        _std_line_width = 0.01


        def __init__(self, ui, wh):
            gtk.DrawingArea.__init__(self)
            self.ui = ui
            self.tool = 0
            self.frontangle = 0.
            self.backangle = 0.
            self.orientation = 0
            self.width = self.height = wh
            self.scale = 1.
            self.dim = 0.
            self.set_size_request(self.width, self.height)
            self.connect('expose-event', self.__expose)
            self.tool = 0
            self.orientation = 0
            self.frontangle = 0.
            self.backangle = 0.
            self.tool_radius = 0.
            self.origins = None
            self.__set_dim(ToolRenderer._toolrenderer._std_dim)

        def __create_tool_renderer_evt_box(self):
            eb = gtk.EventBox()
            gtk.Buildable.set_name(eb, 'profile_tool_renderer')
            eb.set_size_request(self.width, self.height)
            eb.set_visible_window(False)
            eb.add(self)
            eb.set_above_child(True)
            eb.connect('enter-notify-event', self.ui.on_mouse_enter)
            eb.connect('leave-notify-event', self.ui.on_mouse_leave)
            return eb

        def __set_dim(self, dim):
            self.dim = dim
            self.scale = self.width/self.dim
            sw, sh = (self.dim/2.,self.dim/2.)
            to_fac = 3./ToolRenderer._toolrenderer._origin_factor*2
            self.origins = { '1': (float(sw*to_fac), float(sh*to_fac)),
                             '2': (float(-sw*to_fac), float(sh*to_fac)),
                             '3': (float(-sw*to_fac), float(-sh*to_fac)),
                             '4': (float(sw*to_fac), float(-sh*to_fac)),
                             '6': (0, float(sh*to_fac)),
                             '8': (0, float(-sh*to_fac))
                           }

        def __draw_bar_circle(self, cr, fade=0.65):
            r = self.dim/2.*.65
            pt = (r*math.sin(math.pi/4.),r*math.cos(math.pi/4.))
            cr.move_to(-pt[0],-pt[1])
            cr.line_to(pt[0],pt[1])
            cr.set_source_rgba(0.0, 1.0, 1.0,fade) #yellow
            cr.set_line_width(.01)
            cr.stroke()
            cr.move_to(r,0.)
            cr.set_source_rgba(1.0, 0, 0,fade)     #red
            cr.set_line_width(.012)
            LatheProfileRenderer.arc(cr,(0.,0.),True,0.,math.pi*2.,r)
            cr.stroke()

        def __gen_path(self, cr, p1, p2, p3, cp, fa, ba, r):
            cr.new_path()
            cw = self.orientation in [3,4,8]
            cr.move_to(p1[0],p1[1])
            cr.line_to(p2[0],p2[1])
            LatheProfileRenderer.arc(cr,cp,cw,fa,ba,r)
            cr.line_to(p3[0],p3[1])
            cr.line_to(p1[0],p1[1])

        def __draw_tool(self, cr, p1, p2, p3, cp, fa, ba, r):
            if self.orientation in [1,2,3,4,6,8]:
                self.__gen_path(cr, p1, p2, p3, cp, fa, ba, r)
                cr.set_source_rgba(.2, .2, .2, .7)
                cr.fill()
                self.__gen_path(cr, p1, p2, p3, cp, fa, ba, r)
                cr.set_source_rgba(1.0, 1.0, 1.0,.5)
                cr.set_line_width(ToolRenderer._toolrenderer._std_line_width)
                cr.stroke() #cr.fill()

        def __update(self):
            self.queue_draw()

        def __expose(self, widget, event):
            cr = widget.window.cairo_create()
            cr.translate(self.width/2.,self.height/2.)
            cr.scale(self.scale,self.scale)
            self.__draw(cr)

        def __draw_backfill(self, cr):
            grey = LatheProfileRenderer.background
            cr.set_source_rgb(grey, grey, grey)
            cr.rectangle(-self.dim/2., -self.dim/2., self.dim, self.dim)
            cr.fill()

        def __draw(self, cr):
            r = self.tool_radius
            self.__draw_backfill(cr)
            try:
                ctr_pt = self.origins[str(self.orientation)]
                if self.orientation in [1,2,6]: fr_angle = math.pi*2.-self.frontangle; bk_angle = math.pi*2.-self.backangle; y_sign = -1.
                else: fr_angle = self.frontangle; bk_angle = self.backangle; y_sign = +1.
                if self.orientation in[1,4]:
                    fa = bk_angle+y_sign*math.pi/2.
                    pt1 = (ctr_pt[0]+(r*math.cos(fa)),ctr_pt[1]+(r*math.sin(fa)))
                    ptl1 = (pt1[0]+math.cos(bk_angle),pt1[1]+math.sin(bk_angle))
                    ba = (fr_angle-y_sign*math.pi/2.)%(math.pi*2.)
                    pt2 = (ctr_pt[0]+(r*math.cos(ba)),ctr_pt[1]+(r*math.sin(ba)))
                    ptl2 = (pt2[0]+math.cos(fr_angle),pt2[1]+math.sin(fr_angle))
                elif self.orientation in [2,3,6,8]:
                    fa = fr_angle+y_sign*math.pi/2.
                    pt1 = (ctr_pt[0]+(r*math.cos(fa)),ctr_pt[1]+(r*math.sin(fa)))
                    ptl1 = (pt1[0]+math.cos(fr_angle),pt1[1]+math.sin(fr_angle))
                    ba = (bk_angle-y_sign*math.pi/2.)%(math.pi*2.)
                    pt2 = (ctr_pt[0]+(r*math.cos(ba)),ctr_pt[1]+(r*math.sin(ba)))
                    ptl2 = (pt2[0]+math.cos(bk_angle),pt2[1]+math.sin(bk_angle))

                self.__draw_tool(cr,ptl1,pt1,ptl2,ctr_pt,fa,ba,r)
                if not self.ui.validate_profile_tool_angles(self.orientation,self.frontangle,self.backangle): self.__draw_bar_circle(cr,.45)
            except KeyError:
                self.__draw_bar_circle(cr)

        # -- public methods ----------------------------------------------------------------------------
        def set_angles(self, tool, radius, fa, ba, orientation=None, update=True):
            if orientation is None: orientation = self.orientation
            if radius is None: radius = self.tool_radius
            self.frontangle = math.radians(math.fabs(fa))
            self.backangle = math.radians(math.fabs(ba))
            self.orientation = orientation
            self.tool = tool
            if self.ui.g21: radius /= 25.4
            self.tool_radius = radius
            if radius <= ToolRenderer._toolrenderer._std_dim/ToolRenderer._toolrenderer._origin_factor: self.__set_dim(ToolRenderer._toolrenderer._std_dim)
            else: self.__set_dim(radius*ToolRenderer._toolrenderer._origin_factor)
            if update: self.__update()



