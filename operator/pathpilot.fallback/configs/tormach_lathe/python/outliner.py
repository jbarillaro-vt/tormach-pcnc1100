# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import math

# constants
MODE,LASTX,LASTY,X,Y,RADIUS,XCENTER,YCENTER = range(8)
mm_conv = 25.4

class ol():

    _std_base_extend = 1.5
    _std_base_thresh = 0.0002
    _std_extend = 0.0
    _std_thresh = 0.0
    _std_base_tolerance = 1e-8
    _std_fl_tolerance = 1e-8

    @classmethod
    def _zero(cls,x): return abs(x) < cls._std_fl_tolerance

    @classmethod
    def _equal(cls,x, y, tolerance=None):
        if tolerance is None: tolerance = cls._std_fl_tolerance
        return abs(x - y) < tolerance

    @staticmethod
    def gt_diameter(x1,x2):
        if ol._equal(x1,x2): return False
        return math.fabs(x1)>math.fabs(x2)

    @staticmethod
    def lt_diameter(x1,x2):
        if ol._equal(x1,x2): return False
        return math.fabs(x1)<math.fabs(x2)

    def __init__(self, metric, base_pts, offset, tool_radius=0., tool_frontangle=0., tool_backangle=0., approach = 1, z_start = 0.):
        ol._std_extend = ol._std_base_extend
        ol._std_thresh = ol._std_base_thresh
        ol._std_fl_tolerance = ol._std_base_tolerance
        if metric:
            ol._std_extend *= mm_conv
            ol._std_thresh *= mm_conv
            ol._std_fl_tolerance *= mm_conv
        self.base_pts = base_pts
        self.metric = metric
        if offset > 0. and base_pts[0][LASTY] < 0.: offset = -offset
        self.offset = offset
        self.tool_radius = tool_radius
        self.tool_frontangle = tool_frontangle
        self.tool_backangle = tool_backangle
        self.approach = 'Z' if approach == 1 else 'X'
        self.z_start = z_start
        self.use_pts = None

    def _offset_radius(self, seg):
        r = seg[RADIUS]
        if ol._zero(r): return 0.
        cw = seg[MODE] == 2
#       e = -1.0 if cw else 1.0
        y_to = seg[Y]
        y_from = seg[LASTY]
        e = 1. if round(y_to,5) > round(y_from,5) else -1.
        if ol._equal(y_to, y_from,1e-6) and e>0 and cw: e = -1 
        return r - self.offset * e

    @staticmethod
    def _extend(sp,sq,ep,eq,extend):
        if ol._equal(sp,ep): return (sp,sq-extend,ep,eq+extend,False)  # vertical case
        if ol._equal(sq,eq): return (sp+extend,sq,ep-extend,eq,False)  # horizontal case
        dq,dp = (eq-sq,ep-sp)
        vec = math.atan(dq/dp)
        neg = sp < ep and math.fabs(eq) > math.fabs(sq)
        if neg: vec = vec - math.pi # vec over 270 degrees (or under 90)
        nsp,nep = (sp + extend, ep - extend)
        sq += ((nsp-sp)*math.tan(vec))
        eq += ((nep-ep)*math.tan(vec))
        return (nsp,sq,nep,eq,neg)

    def _line_intersect_arc(self, cp, cq, r, ls, le, close):
        fac = 25.4 if self.metric else 1.0
        dp,dq = (le[0]-ls[0],le[1]-ls[1])
        ll = math.hypot(dp,dq)
        tp,tq = (dp/ll, dq/ll)
        t = (tp*(cp-ls[0])) + (tq*(cq-ls[1]))
        ep,eq = (t*tp + ls[0],t*tq + ls[1])
        lc = math.hypot((ep-cp),(eq-cq))
        # check for tangency and return a 'practical'
        # tangent point...
        ap = aq = lp = lq = float('nan')
        if ol._equal(lc,r,close): lc = r-1e-8*fac
        if lc < r:
            dt = math.sqrt( r**2 - lc**2)
            ap = (t-dt)*tp + ls[0]
            aq = (t-dt)*tq + ls[1]
            lp = (t+dt)*tp + ls[0]
            lq = (t+dt)*tq + ls[1]
        return (ap,aq,lp,lq)

    def _create_extended_offset_line(self,seg,extend=None):
        if extend is None: extend = ol._std_extend
        sp0,sq0,ep0,eq0 = (seg[LASTX],seg[LASTY],seg[X],seg[Y])
        sp,sq,ep,eq,neg = ol._extend(sp0,sq0,ep0,eq0,extend)
        if ol._equal(sp,ep): # vertical line
            return ((sp-self.offset,sq),(ep-self.offset,eq)) if self.offset < 0. or math.fabs(sq0) > math.fabs(eq0) else \
                   ((sp+self.offset,sq),(ep+self.offset,eq))
        dq,dp = (eq-sq,ep-sp)
        vec = math.atan(dq/dp)
        if neg: vec = vec - math.pi # vec over 270 degrees
        e = -1. if neg else 1.
        sp -= self.offset*math.sin(vec)
        ep -= self.offset*math.sin(vec)
        sq += self.offset*math.cos(vec)
        eq += self.offset*math.cos(vec)
        return ((sp,sq),(ep,eq))

    def _closest_pt(self, mp, pt1, pt2):
        dpt1 = math.hypot(pt1[0]-mp[0],pt1[1]-mp[1]) # distance from sp to arc end
        dpt2 = math.hypot(pt2[0]-mp[0],pt2[1]-mp[1]) # distance from tp to arc end
        return pt1 if dpt1<dpt2 else pt2

    def _closest_line_arc_intersect_pt(self, line, arc, item='line'):
        r = math.fabs(self._offset_radius(arc))
        cp, cq = (arc[XCENTER], arc[YCENTER])
        ls,le = self._create_extended_offset_line(line,r*2.5)
        test_item = line if item=='line' else arc
        ap, aq, lp, lq = self._line_intersect_arc(cp, cq, r, ls, le, ol._std_thresh/2.)
        sp,tp = ((ap,aq),(lp,lq)) if ap <= lp else ((lp,lq),(ap,aq))
        rp = self._closest_pt((test_item[X],test_item[Y]), sp, tp)
        return (rp,r,(cp,cq))

    def _offset_line_intersect_arc(self, seg_index):
        line = self.use_pts[seg_index]
        arc = self.use_pts[seg_index+1]
        return self._closest_line_arc_intersect_pt(line, arc)[0]

    def _offset_arc_intersect_line(self, seg_index):
        arc = self.use_pts[seg_index]
        line = self.use_pts[seg_index+1]
        rp,r,cp = self._closest_line_arc_intersect_pt(line, arc, 'arc')
        return (rp[0], rp[1], r, cp[0], cp[1])

    @staticmethod
    def line_intersect_line(l1s, l1e, l2s, l2e):
        #compute the intersection ..
        # http://stackoverflow.com/questions/20677795
        l1_dx, l1_dy = (l1e[0]-l1s[0], l1e[1]-l1s[1])
        l2_dx, l2_dy = (l2e[0]-l2s[0], l2e[1]-l2s[1])
        div = l2_dy*l1_dx - l2_dx*l1_dy
        if ol._zero(div): raise ZeroDivisionError
        dx = l1s[0]*l1e[1] - l1s[1]*l1e[0]
        dy = l2s[0]*l2e[1] - l2s[1]*l2e[0]
        p = (dy*l1_dx - dx*l2_dx) / div
        q = (dy*l1_dy - dx*l2_dy) / div
        return (p,q)

    def _offset_line_intersect_line(self, seg_index):
        l1s,l1e = self._create_extended_offset_line(self.use_pts[seg_index])
        l2s,l2e = self._create_extended_offset_line(self.use_pts[seg_index+1])
        try:
            p,q = ol.line_intersect_line(l1s, l1e, l2s, l2e)
        except ZeroDivisionError:
            l1s,l1e = self._create_extended_offset_line(self.use_pts[seg_index],0)
            p,q = (l1e[0],l1e[1])
        return p,q

    def _arc_intersect_arc(self, c1, c2):
        x1,y1,r1 = c1
        x2,y2,r2 = c2
        fac = 25.4 if self.metric else 1.0
        # http://stackoverflow.com/a/3349134/798588
        dx,dy = x2-x1,y2-y1
        d = math.hypot(dx, dy)
        xs1 = ys1 = xs2 = ys2 = float('nan')
        if d > r1+r2 and not ol._equal(d,r1+r2,2.5e-5*fac): return (xs1,ys1),(xs2,ys2) # no solutions, the circles are separate
        if d+ol._std_thresh < math.fabs(r1-r2): return (xs1,ys1),(xs2,ys2) # no solutions because one circle is contained within the other
        if ol._zero(d) and ol._equal(r1,r2): return (xs1,ys1),(xs2,ys2) # it's the same circle
        a = (r1**2-r2**2+d**2)/(2*d)
        h = 0.0 if ol._equal(r1,a,1.75e-5*fac) else math.sqrt(r1**2-a**2)
        xm = x1 + a*dx/d
        ym = y1 + a*dy/d
        pt1 = (xm + h*dy/d),(ym - h*dx/d)
        pt2 = (xm - h*dy/d),(ym + h*dx/d)
        return (pt1,pt2)

    def _offset_arc_intersect_arc(self, seg_index):
        thresh = ol._std_thresh/2.
        arc1 = self.use_pts[seg_index]
        cp1,cq1,r1 = (arc1[XCENTER], arc1[YCENTER],math.fabs(self._offset_radius(arc1)))
        c1 = (cp1,cq1,r1)
        arc2 = self.use_pts[seg_index+1]
        cp2,cq2,r2 = (arc2[XCENTER], arc2[YCENTER],math.fabs(self._offset_radius(arc2)))
        c2 = (cp2,cq2,r2)
        if ol._equal(cp1,cp2,thresh) and ol._equal(cq1,cq2,thresh) and ol._equal(r1,r2,thresh): return (arc1[X], arc1[Y]+self.offset ,self._offset_radius(arc1) ,cp1 ,cq1)
        if math.fabs((cp1-cp2)+(cq1-cq2)+(r1-r2)) <= ol._std_thresh: return (arc1[X], arc1[Y]+self.offset ,self._offset_radius(arc1) ,cp1 ,cq1)
        pt1, pt2 = self._arc_intersect_arc(c1, c2)
        # so which point is it ?
        a1 = math.atan((cq2-pt1[1])/(cp2-pt1[0]))
        a2 = math.atan((cq2-pt2[1])/(cp2-pt2[0]))
        pt = pt1
        # ha! if a1 == a1 there is only one point and circle 1 is tangent
        # to circle 2
        if not ol._equal(a1,a2): pt = self._closest_pt((arc1[X],arc1[Y]), pt1, pt2)
        return (pt[0], pt[1] ,self._offset_radius(arc1) ,cp1 ,cq1)

    def _arc_too_small(self, lpt, npt, r, cpt):
        _t = ol._std_thresh*.75
        return ol._equal(lpt[0],npt[0],_t) and ol._equal(lpt[1],npt[1],_t)

    def _start_offset_pt(self):
        ls,le = self._create_extended_offset_line(self.use_pts[0],0)
        return (le[0],le[1],0.)

    def is_line(self, seg_index):
        return ol._zero(self.use_pts[seg_index][RADIUS])

    def _print_basepts(self):
        print '......base_pts................................'
        for item in self.use_pts: print '(%d, %.4f, %.4f, %.4f, %.4f, %.4f, %.4f, %.4f),' % (item)
        print '......base_pts................................'

    def _lead_out(self, out_list, last_p, last_q):
        if self.offset > 0.:
            if ol.gt_diameter(self.use_pts[0][2],last_q):
                out_list.append((1, last_p, last_q, last_p, self.use_pts[0][2], 0., 0., 0.))

    def _start_pt_fixup(self):
        # assume use_pts[0][1], use_pts[0][2] are safe z,x
        mode, lp, lq, p, q, r, cp, cq = self.use_pts[0]
        # if the first move has no x component but has a z component
        # then the procket starts back from z start...
        if self.approach == 'X': return (lp,lq)
        mode, lp, lq, p, q, r, cp, cq = self.use_pts.pop(0)
        s_p = p
        s_lp = lp
        s_lq = lq
        p= lp if ol._zero(self.tool_radius) else p+((self.tool_radius+self.offset)*2.)
        l0 = (mode, lp, lq, p, q, 0., 0., 0.)
        lp = p
        lq = q
        p = s_p
        l1 = (mode, lp, lq, p, q, r, cp, cq)
        if ol._equal(l0[4],l1[4]) and ol._equal(l0[4],self.use_pts[0][4]):
            mode, lp, lq, p, q, r, cp, cq = self.use_pts.pop(0)
            lp = l1[1]
            lq = l1[2]
            self.use_pts.insert(0, (mode, lp, lq, p, q, r, cp, cq))
        else:
            self.use_pts.insert(0,l1)
        self.use_pts.insert(0,l0)
        return (s_lp,s_lq)

    def _fixup(self):
        if not any(self.base_pts): return 0
        self.use_pts = list(self.base_pts)
#       self._print_basepts()
        s_lp,s_lq = self._start_pt_fixup()
        # fixup radii for our style of drawing...
        pts = []
        for n,item in enumerate(self.use_pts):
            mode, lp, lq, p, q, r, cp, cq = item
            if mode in [2,3]:
                r = math.hypot(cp-lp,cq-lq)
                if r <= self.offset:
                    # do not like special cases .. but this is where radius is the first cut..
                    if n == 2:
                        m,lx,ly,x,y,r,p,q = pts[0]
                        y = self.use_pts[2][Y]
                        pts[0] = (m,lx,ly,x,y,r,p,q)
                        m,lx,ly,x,y,r,p,q = pts[1]
                        lx = pts[0][X]
                        ly = pts[0][Y]
                        y = self.use_pts[2][Y]
                        pts[1] = (m,lx,ly,x,y,r,p,q)
                    continue
                if mode == 2:                                 #arc is cw
                    if q < lq and r > 0.: r = -r
                    elif q > lq: r = math.fabs(r)
                elif mode == 3:                               #arc is ccw
                    if q > lq and r > 0: r = -r
                    elif q < lq: r = math.fabs(r)
            pts.append(( mode, lp, lq, p, q, r, cp, cq))
        # create a last line ..
        lp,lq = (pts[len(pts)-1][3],pts[len(pts)-1][4])
        pts.append(( 1, lp, lq, lp, s_lq, 0., 0., 0.))
        self.use_pts = pts
        return len(self.use_pts)

    def __zero_movement(self, points):
        return points[MODE] == 1 and points[X] == points[LASTX] and points[Y] == points[LASTY]

    def offset_points(self):
        out_list=[]
        if not any(self.base_pts): return out_list
        num_pts = self._fixup()
        if num_pts <= 2: return out_list
        last_p, last_q, r = self._start_offset_pt()
        last = num_pts-1
        for seg_index in range(last):
            next_seg_index = seg_index + 1
            mode = self.use_pts[seg_index][MODE]
            if self.__zero_movement(self.use_pts[seg_index]): continue
            try:
                if self.is_line(seg_index):             # seg_index is a line
                    p,q = self._offset_line_intersect_line(seg_index) if self.is_line(next_seg_index) else \
                          self._offset_line_intersect_arc(seg_index)
                    out_list.append((mode, last_p, last_q, p, q, 0., 0., 0.))
                else: # current seg_index is an arc
                    p,q,r,cp,cq = self._offset_arc_intersect_line(seg_index) if self.is_line(next_seg_index) else \
                                  self._offset_arc_intersect_arc(seg_index)
                    if self._arc_too_small((last_p,last_q),(p,q),r,(cp,cq)): continue
                    out_list.append((mode, last_p, last_q, p, q, r, cp, cq))
                last_p = p
                last_q = q
            except ArithmeticError as e:
                if isinstance(e,ZeroDivisionError):
                    fmt = '%.3f' if self.metric else '%.4f'
                    t = self.use_pts[seg_index]
                    msg = 'Pre-finish could not resolve move to X%s Z%s R%s' % (fmt,fmt,fmt) % (t[Y]*2.,t[X],math.fabs(t[RADIUS]))
                    raise FloatingPointError(msg)
            if math.isnan(p) or math.isnan(q): raise FloatingPointError('Pre-finish pass produced a -Nan- result at segment %d to X%.4f X%.4f' % (seg_index,self.use_pts[seg_index][Y],self.use_pts[seg_index][X]))
        self._lead_out(out_list, last_p, last_q)
        return out_list


