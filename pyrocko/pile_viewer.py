import os, sys, time, calendar, datetime, signal, re, math, scipy.stats, tempfile, logging, traceback, shlex, operator, copy

from optparse import OptionParser
import numpy as num 
from itertools import izip

import pyrocko.model, pyrocko.pile, pyrocko.shadow_pile, pyrocko.trace, pyrocko.util, pyrocko.plot, pyrocko.snuffling, pyrocko.snufflings

from pyrocko.util import TableWriter, TableReader, hpfloat

from pyrocko.gui_util import ValControl, LinValControl, Marker, EventMarker, PhaseMarker, make_QPolygonF, draw_label, Label, \
    gmtime_x, myctime, mystrftime, Progressbars

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtOpenGL import *
from PyQt4.QtSvg import *


logger = logging.getLogger('pyrocko.pile_viewer')

class Global:
    appOnDemand = None

class NSLC:
    def __init__(self, n,s,l=None,c=None):
        self.network = n
        self.station = s
        self.location = l
        self.channel = c

class m_float(float):
    
    def __str__(self):
        if abs(self) >= 10000.:
            return '%g km' % round(self/1000.,0)
        elif abs(self) >= 1000.:
            return '%g km' % round(self/1000.,1)
        else:
            return '%.5g m' % self
        
def m_float_or_none(x):
    if x is None:
        return None
    else:
        return m_float(x)

class deg_float(float):
    
    def __str__(self):
        return '%4.0f' % self

def deg_float_or_none(x):
    if x is None:
        return None
    else:
        return deg_float(x)

class sector_int(int):
    
    def __str__(self):
        return '[%i]' % self

def num_to_html(num):
    snum = '%g' % num
    m = re.match(r'(.+)[eE]([+-]?\d+)$', snum)
    if m:
        snum = m.group(1) + ' &times; 10<sup>%i</sup>' % int(m.group(2))

    return snum
 
gap_lap_tolerance = 5.

class Timer:
    def __init__(self):
        self._start = None
        self._stop = None
    
    def start(self):
        self._start = os.times()
    
    def stop(self):
        self._stop = os.times()

    def get(self):
        a = self._start
        b = self._stop
        if a is not None and b is not None:
            return tuple([ b[i] - a[i] for i in xrange(5) ])
        else:
            return tuple([ 0. ] * 5)
        
    def __sub__(self, other):
        a = self.get()
        b = other.get()
        return tuple( [ a[i] - b[i] for i in xrange(5) ] )

class Integrator(pyrocko.shadow_pile.ShadowPile):

    def process(self, iblock, tmin, tmax, traces):
        for trace in traces:
            trace.ydata -= trace.ydata.mean()
            trace.ydata = num.cumsum(trace.ydata)
        
        return traces
        
class ObjectStyle(object):
    def __init__(self, frame_pen, fill_brush):
        self.frame_pen = frame_pen
        self.fill_brush = fill_brush

box_styles = []
box_alpha = 100
for color in 'orange skyblue butter chameleon chocolate plum scarletred'.split():
    box_styles.append(ObjectStyle(
        QPen(QColor(*pyrocko.plot.tango_colors[color+'3'])),
        QBrush(QColor(*(pyrocko.plot.tango_colors[color+'1']+(box_alpha,)))),        
    ))
    
sday   = 60*60*24     # \ 
smonth = 60*60*24*30  #   > only used as approx. intervals...
syear  = 60*60*24*365 # /

acceptable_tincs = num.array([1, 2, 5, 10, 20, 30, 60, 60*5, 60*10, 60*20, 60*30, 60*60, 
                     60*60*3, 60*60*6, 60*60*12, sday, smonth, syear ],dtype=num.float)

def get_working_system_time_range():
    now = time.time()
    hi = now
    for ignore in range(200):
        now += syear
        try:
            tt = time.gmtime(now)
            time.strftime('', tt)
            hi = now
        except:
            break
        
    now = time.time()
    lo = now
    for ignore in range(200):    
        now -= syear
        try:
            tt = time.gmtime(now)
            time.strftime('',tt)
            lo = now
        except:
            break
    return lo, hi

working_system_time_range = get_working_system_time_range()

def is_working_time(t):
    return working_system_time_range[0] <= t and  t <= working_system_time_range[1]
        

def fancy_time_ax_format(inc):
    l0_fmt_brief = ''
    l2_fmt = ''
    l2_trig = 0
    if inc < 0.000001:
        l0_fmt = '.%n'
        l0_center = False
        l1_fmt = '%H:%M:%S'
        l1_trig = 6
        l2_fmt = '%b %d, %Y'
        l2_trig = 3
    elif inc < 0.001:
        l0_fmt = '.%u'
        l0_center = False
        l1_fmt = '%H:%M:%S'
        l1_trig = 6
        l2_fmt = '%b %d, %Y'
        l2_trig = 3
    elif inc < 1:
        l0_fmt = '.%r'
        l0_center = False
        l1_fmt = '%H:%M:%S'
        l1_trig = 6
        l2_fmt = '%b %d, %Y'
        l2_trig = 3
    elif inc < 60:
        l0_fmt = '%H:%M:%S'
        l0_center = False
        l1_fmt = '%b %d, %Y'
        l1_trig = 3
    elif inc < 3600:
        l0_fmt = '%H:%M'
        l0_center = False
        l1_fmt = '%b %d, %Y'
        l1_trig = 3
    elif inc < sday:
        l0_fmt = '%H:%M'
        l0_center = False
        l1_fmt = '%b %d, %Y'
        l1_trig = 3
    elif inc < smonth:
        l0_fmt = '%a %d'
        l0_fmt_brief = '%d'
        l0_center = True
        l1_fmt = '%b, %Y'
        l1_trig = 2
    elif inc < syear:
        l0_fmt = '%b'
        l0_center = True
        l1_fmt = '%Y'
        l1_trig = 1
    else:
        l0_fmt = '%Y'
        l0_center = False
        l1_fmt = ''
        l1_trig = 0
        
    return l0_fmt, l0_fmt_brief, l0_center, l1_fmt, l1_trig, l2_fmt, l2_trig

def day_start(timestamp):
   tt = time.gmtime(int(timestamp))
   tts = tt[0:3] + (0,0,0) + tt[6:9]
   return calendar.timegm(tts)

def month_start(timestamp):
   tt = time.gmtime(int(timestamp))
   tts = tt[0:2] + (1,0,0,0) + tt[6:9]
   return calendar.timegm(tts)

def year_start(timestamp):
    tt = time.gmtime(int(timestamp))
    tts = tt[0:1] + (1,1,0,0,0) + tt[6:9]
    return calendar.timegm(tts)

def time_nice_value(inc0):
    if inc0 < acceptable_tincs[0]:
        return pyrocko.plot.nice_value(inc0)
    elif inc0 > acceptable_tincs[-1]:
        return pyrocko.plot.nice_value(inc0/syear)*syear
    else:
        i = num.argmin(num.abs(acceptable_tincs-inc0))
        return acceptable_tincs[i]

class TimeScaler(pyrocko.plot.AutoScaler):
    def __init__(self):
        pyrocko.plot.AutoScaler.__init__(self)
        self.mode = 'min-max'
    
    def make_scale(self, data_range):
        assert self.mode in ('min-max', 'off'), 'mode must be "min-max" or "off" for TimeScaler'
        
        data_min = min(data_range)
        data_max = max(data_range)
        is_reverse = (data_range[0] > data_range[1])
        
        mi, ma = data_min, data_max
        nmi = mi
        if self.mode != 'off':
            nmi = mi - self.space*(ma-mi)
            
        nma = ma
        if self.mode != 'off':
            nma = ma + self.space*(ma-mi)
             
        mi, ma = nmi, nma
        
        if mi == ma and a != 'off':
            mi -= 1.0
            ma += 1.0
        
        mi = max(working_system_time_range[0],mi)
        ma = min(working_system_time_range[1],ma)
        
        # make nice tick increment
        if self.inc is not None:
            inc = self.inc
        else:
            if self.approx_ticks > 0.:
                inc = time_nice_value( (ma-mi)/self.approx_ticks )
            else:
                inc = time_nice_value( (ma-mi)*10. )
        
        if inc == 0.0:
            inc = 1.0
        
        if is_reverse:
            return ma, mi, -inc
        else:
            return mi, ma, inc


    def make_ticks(self, data_range):
        mi, ma, inc = self.make_scale(data_range)
        
        is_reverse = False
        if inc < 0:
            mi, ma, inc = ma, mi, -inc
            is_reverse = True
            
        ticks = []
        
        if inc < sday:
            mi_day = day_start(max(mi, working_system_time_range[0]+sday*1.5))
            if inc < 0.001:
                mi_day = hpfloat(mi_day)

            base = mi_day+num.ceil((mi-mi_day)/inc)*inc
            if inc < 0.001:
                base = hpfloat(base)

            base_day = mi_day
            i = 0
            while True:
                tick = base+i*inc
                if tick > ma: break
                tick_day = day_start(tick)
                if tick_day > base_day:
                    base_day = tick_day
                    base = base_day
                    i = 0
                else:
                    ticks.append(tick)
                    i += 1
                    
        elif inc < smonth:
            mi_day = day_start(max(mi, working_system_time_range[0]+sday*1.5))
            dt_base = datetime.datetime(*time.gmtime(mi_day)[:6])
            delta = datetime.timedelta(days=int(round(inc/sday)))
            if mi_day == mi: dt_base += delta
            i = 0
            while True:
                current = dt_base + i*delta
                tick = calendar.timegm(current.timetuple())
                if tick > ma: break
                ticks.append(tick)
                i += 1
            
        elif inc < syear:
            mi_month = month_start(max(mi, working_system_time_range[0]+smonth*1.5))
            y,m = time.gmtime(mi_month)[:2]
            while True:
                tick = calendar.timegm((y,m,1,0,0,0))
                m += 1
                if m > 12: y,m = y+1,1
                if tick > ma: break
                if tick >= mi: ticks.append(tick)
        
        else:
            mi_year = year_start(max(mi, working_system_time_range[0]+syear*1.5))
            incy = int(round(inc/syear))
            y = int(num.floor(time.gmtime(mi_year)[0]/incy)*incy)
            
            while True:
                tick = calendar.timegm((y,1,1,0,0,0))
                y += incy
                if tick > ma: break
                if tick >= mi: ticks.append(tick)
        
        if is_reverse: ticks.reverse()
        return ticks, inc

def need_l1_tick(tt, ms, l1_trig):
    return (0,1,1,0,0,0)[l1_trig:] == tt[l1_trig:6] and ms == 0.0
    
 
def tick_to_labels(tick, inc):
    tt, ms = gmtime_x(tick)
    l0_fmt, l0_fmt_brief, l0_center, l1_fmt, l1_trig, l2_fmt, l2_trig = fancy_time_ax_format(inc)
    l0 = mystrftime(l0_fmt, tt, ms)
    l0_brief = mystrftime(l0_fmt_brief, tt, ms)
    l1, l2 = None, None
    if need_l1_tick(tt, ms, l1_trig):
        l1 = mystrftime(l1_fmt, tt, ms)
    if need_l1_tick(tt, ms, l2_trig):
        l2 = mystrftime(l2_fmt, tt, ms)
        
    return l0, l0_brief, l0_center, l1, l2
    
def l1_l2_tick(tick, inc):
    tt, ms = gmtime_x(tick)
    l0_fmt, l0_fmt_brief, l0_center, l1_fmt, l1_trig, l2_fmt, l2_trig = fancy_time_ax_format(inc)
    l1 = mystrftime(l1_fmt, tt, ms)
    l2 = mystrftime(l2_fmt, tt, ms)
    return l1, l2
    
class TimeAx(TimeScaler):
    def __init__(self, *args):
        TimeScaler.__init__(self, *args)
    
    
    def drawit( self, p, xprojection, yprojection ):
        pen = QPen(QColor(*pyrocko.plot.tango_colors['aluminium5']),1)
        p.setPen(pen)
        font = QFont()
        font.setBold(True)
        p.setFont(font)
        fm = p.fontMetrics()
        ticklen = 10
        pad = 10
        tmin, tmax = xprojection.get_in_range()
        ticks, inc = self.make_ticks((tmin,tmax))
        l1_hits = 0
        l2_hits = 0
        
        vmin, vmax = yprojection(0), yprojection(ticklen)
        uumin, uumax = xprojection.get_out_range()
        first_tick_with_label = None
        for tick in ticks:
            umin = xprojection(tick)
            
            umin_approx_next = xprojection(tick+inc)
            umax = xprojection(tick)
            
            pinc_approx = umin_approx_next - umin
            
            p.drawLine(QPointF(umin, vmin), QPointF(umax, vmax))
            l0, l0_brief, l0_center, l1, l2 = tick_to_labels(tick, inc)
            
            if l0_center:
                ushift = (umin_approx_next-umin)/2.
            else:
                ushift = 0.
            
            for l0x in (l0, l0_brief, ''):
                label0 = QString(l0x)
                rect0 = fm.boundingRect( label0 )
                if rect0.width() <= pinc_approx*0.9: break
            
            if uumin+pad < umin-rect0.width()/2.+ushift and umin+rect0.width()/2.+ushift < uumax-pad:
                if first_tick_with_label is None:
                    first_tick_with_label = tick
                p.drawText( QPointF(umin-rect0.width()/2.+ushift, vmin+rect0.height()+ticklen), label0 )
            
            if l1:
                label1 = QString(l1)
                rect1 = fm.boundingRect( label1 )
                if uumin+pad < umin-rect1.width()/2. and umin+rect1.width()/2. < uumax-pad:
                    p.drawText( QPointF(umin-rect1.width()/2., vmin+rect0.height()+rect1.height()+ticklen), label1 )
                    l1_hits += 1
                
            if l2:
                label2 = QString(l2)
                rect2 = fm.boundingRect( label2 )
                if uumin+pad < umin-rect2.width()/2. and umin+rect2.width()/2. < uumax-pad:
                    p.drawText( QPointF(umin-rect2.width()/2., vmin+rect0.height()+rect1.height()+rect2.height()+ticklen), label2 )
                    l2_hits += 1
        
        if first_tick_with_label is None:
            first_tick_with_label = tmin
            
        l1, l2 = l1_l2_tick(first_tick_with_label, inc)
        
        if l1_hits == 0 and l1:
            label1 = QString(l1)
            rect1 = fm.boundingRect( label1 )
            p.drawText( QPointF(uumin+pad, vmin+rect0.height()+rect1.height()+ticklen), label1 )
            l1_hits += 1
        
        if l2_hits == 0 and l2:
            label2 = QString(l2)
            rect2 = fm.boundingRect( label2 )
            p.drawText( QPointF(uumin+pad, vmin+rect0.height()+rect1.height()+rect2.height()+ticklen), label2 )
                
        v = yprojection(0)
        p.drawLine(QPointF(uumin, v), QPointF(uumax, v))
        
class Projection(object):
    def __init__(self):
        self.xr = 0.,1.
        self.ur = 0.,1.
        
    def set_in_range(self, xmin, xmax):
        if xmax == xmin: xmax = xmin + 1.
        self.xr = xmin, xmax

    def get_in_range(self):
        return self.xr

    def set_out_range(self, umin, umax):
        if umax == umin: umax = umin + 1.
        self.ur = umin, umax
        
    def get_out_range(self):
        return self.ur
        
    def __call__(self, x):
        umin, umax = self.ur
        xmin, xmax = self.xr
        return umin + (x-xmin)*((umax-umin)/(xmax-xmin))
    
    def clipped(self, x):
        umin, umax = self.ur
        xmin, xmax = self.xr
        return min(umax, max(umin, umin + (x-xmin)*((umax-umin)/(xmax-xmin))))
        
    def rev(self, u):
        umin, umax = self.ur
        xmin, xmax = self.xr
        return xmin + (u-umin)*((xmax-xmin)/(umax-umin))
    
    def copy(self):
        return copy.copy(self)

def add_radiobuttongroup(menu, menudef, obj, target):
    group = QActionGroup(menu)
    menuitems = []
    for l, v in menudef:
        k = QAction(l, menu)
        group.addAction(k)
        menu.addAction(k)
        k.setCheckable(True)
        obj.connect(group, SIGNAL('triggered(QAction*)'), target)
        menuitems.append((k,v))
            
    menuitems[0][0].setChecked(True)
    return menuitems

def sort_actions(menu):
    actions = menu.actions()
    for action in actions:
        menu.removeAction(action)

    actions.sort((lambda a,b: cmp(a.text(), b.text())))
    for action in actions:
        menu.addAction(action)

fkey_map = dict(zip((Qt.Key_F1, Qt.Key_F2, Qt.Key_F3, Qt.Key_F4, Qt.Key_F5, Qt.Key_F10),(1,2,3,4,5,0)))

class PileViewerMainException(Exception):
    pass

def MakePileViewerMainClass(base):
    
    class PileViewerMain(base):

        def __init__(self, pile, ntracks_shown_max, panel_parent, *args):
            if base == QGLWidget:
                apply(base.__init__, (self, QGLFormat(QGL.SampleBuffers)) + args)
            else:
                apply(base.__init__, (self,) + args)

            self.pile = pile
            self.ax_height = 80
            self.panel_parent = panel_parent 

            self.click_tolerance = 5
            
            self.ntracks_shown_max = ntracks_shown_max
            self.initial_ntracks_shown_max = ntracks_shown_max
            self.ntracks = 0
            self.show_all = True
            self.shown_tracks_range = None
            self.track_start = None
            self.track_trange = None
            
            self.lowpass = None
            self.highpass = None
            self.gain = 1.0
            self.rotate = 0.0
            self.markers = []
            self.picking_down = None
            self.picking = None
            self.floating_marker = None
            self.markers = []
            self.all_marker_kinds = (0,1,2,3,4,5)
            self.visible_marker_kinds = self.all_marker_kinds 
            self.active_event_marker = None
            self.ignore_releases = 0
            self.message = None
            self.reloaded = False
            self.pile_has_changed = False
            self.phase_names = { 1: 'P', 2: 'S', 3: 'R', 4: 'Q', 5: '?' } 

            self.tax = TimeAx()
            self.setBackgroundRole( QPalette.Base )
            self.setAutoFillBackground( True )
            poli = QSizePolicy( QSizePolicy.Expanding, QSizePolicy.Expanding )
            self.setSizePolicy( poli )
            self.setMinimumSize(300,200)
            self.setFocusPolicy( Qt.StrongFocus )
    
            self.menu = QMenu(self)
             
#            self.menuitem_pick = QAction('Pick', self.menu)
#            self.menu.addAction(self.menuitem_pick)
#            self.connect( self.menuitem_pick, SIGNAL("triggered(bool)"), self.start_picking )

            mi = QAction('Open waveform files...', self.menu)
            self.menu.addAction(mi)
            self.connect(mi, SIGNAL("triggered(bool)"), self.open_waveforms )

            mi = QAction('Open waveform directory...', self.menu)
            self.menu.addAction(mi)
            self.connect(mi, SIGNAL("triggered(bool)"), self.open_waveform_directory )
            
            mi = QAction('Write markers...', self.menu)
            self.menu.addAction(mi)
            self.connect( mi, SIGNAL("triggered(bool)"), self.write_markers )
            
            mi = QAction('Write selected markers...', self.menu)
            self.menu.addAction(mi)
            self.connect( mi, SIGNAL("triggered(bool)"), self.write_selected_markers )
            
            mi = QAction('Read markers...', self.menu)
            self.menu.addAction(mi)
            self.connect( mi, SIGNAL("triggered(bool)"), self.read_markers )
            
            self.menu.addSeparator()
            
    
            menudef = [
                ('Indivdual Scale',            lambda tr: (tr.network, tr.station, tr.location, tr.channel)),
                ('Common Scale',               lambda tr: None),
                ('Common Scale per Station',   lambda tr: (tr.network, tr.station)),
                ('Common Scale per Component', lambda tr: (tr.channel)),
            ]
            
            self.menuitems_scaling = add_radiobuttongroup(self.menu, menudef, self, self.scalingmode_change)
            self.scaling_key = self.menuitems_scaling[0][1]
            self.scaling_hooks = {} 
            
            self.menu.addSeparator()
            
            menudef = [
                ('Scaling based on Minimum and Maximum', 'minmax'),
                ('Scaling based on Mean +- 2 x Std. Deviation', 2),
                ('Scaling based on Mean +- 4 x Std. Deviation', 4),
            ]
            
            self.menuitems_scaling_base = add_radiobuttongroup(self.menu, menudef, self, self.scaling_base_change)
            self.scaling_base = self.menuitems_scaling_base[0][1]
            
            self.menu.addSeparator()
 
            def sector_dist(sta):
                if sta.dist_m is None:
                    return None, None
                else:
                    return (sector_int(round((sta.azimuth+15.)/30.)), m_float(sta.dist_m))

            menudef = [
                ('Sort by Names',
                    lambda tr: () ),
                ('Sort by Distance',
                    lambda tr: self.station_attrib(tr, lambda sta: (m_float_or_none(sta.dist_m),), lambda tr: (None,) )),
                ('Sort by Azimuth',
                    lambda tr: self.station_attrib(tr, lambda sta: (deg_float_or_none(sta.azimuth),), lambda tr: (None,) )),
                ('Sort by Distance in 12 Azimuthal Blocks',
                    lambda tr: self.station_attrib(tr, sector_dist, lambda tr: (None,None) )),
                ('Sort by Backazimuth',
                    lambda tr: self.station_attrib(tr, lambda sta: (deg_float_or_none(sta.backazimuth),), lambda tr: (None,) )),
            ]
            self.menuitems_ssorting = add_radiobuttongroup(self.menu, menudef, self, self.s_sortingmode_change)
            
            self._ssort = lambda tr: ()
            
            self.menu.addSeparator()
            
            menudef = [
                ('Subsort by Network, Station, Location, Channel', 
                    ( lambda tr: self.ssort(tr) + tr.nslc_id,     # gathering
                    lambda a,b: cmp(a,b),      # sorting
                    lambda tr: tr.location )),  # coloring
                ('Subsort by Network, Station, Channel, Location', 
                    ( lambda tr: self.ssort(tr) + (tr.network, tr.station, tr.channel, tr.location),
                    lambda a,b: cmp(a,b),
                    lambda tr: tr.channel )),
                ('Subsort by Station, Network, Channel, Location', 
                    ( lambda tr: self.ssort(tr) + (tr.station, tr.network, tr.channel, tr.location),
                    lambda a,b: cmp(a,b),
                    lambda tr: tr.channel )),
                ('Subsort by Location, Network, Station, Channel', 
                    ( lambda tr: self.ssort(tr) + (tr.location, tr.network, tr.station, tr.channel),
                    lambda a,b: cmp(a,b),
                    lambda tr: tr.channel )),
                ('Subsort by Channel, Network, Station, Location', 
                    ( lambda tr: self.ssort(tr) + (tr.channel, tr.network, tr.station, tr.location),
                    lambda a,b: cmp(a,b),
                    lambda tr: (tr.network, tr.station, tr.location) )),
                ('Subsort by Network, Station, Channel (Grouped by Location)',
                    ( lambda tr: self.ssort(tr) + (tr.network, tr.station, tr.channel),
                    lambda a,b: cmp(a,b),
                    lambda tr: tr.location )),
                ('Subsort by Station, Network, Channel (Grouped by Location)',
                    ( lambda tr: self.ssort(tr) + (tr.station, tr.network, tr.channel),
                    lambda a,b: cmp(a,b),
                    lambda tr: tr.location )),
                
            ]
            self.menuitems_sorting = add_radiobuttongroup(self.menu, menudef, self, self.sortingmode_change)
            
            self.menu.addSeparator()
            
            self.menuitem_antialias = QAction('Antialiasing', self.menu)
            self.menuitem_antialias.setCheckable(True)
            self.menu.addAction(self.menuitem_antialias)
            
            self.menuitem_liberal_fetch = QAction('Liberal Fetch Optimization', self.menu)
            self.menuitem_liberal_fetch.setCheckable(True)
            self.menu.addAction(self.menuitem_liberal_fetch)
            
            self.menuitem_cliptraces = QAction('Clip Traces', self.menu)
            self.menuitem_cliptraces.setCheckable(True)
            self.menuitem_cliptraces.setChecked(True)
            self.menu.addAction(self.menuitem_cliptraces)
            
            self.menuitem_showboxes = QAction('Show Boxes', self.menu)
            self.menuitem_showboxes.setCheckable(True)
            self.menuitem_showboxes.setChecked(True)
            self.menu.addAction(self.menuitem_showboxes)
            
            self.menuitem_colortraces = QAction('Color Traces', self.menu)
            self.menuitem_colortraces.setCheckable(True)
            self.menuitem_colortraces.setChecked(False)
            self.menu.addAction(self.menuitem_colortraces)
            
            self.menuitem_showscalerange = QAction('Show Scale Ranges', self.menu)
            self.menuitem_showscalerange.setCheckable(True)
            self.menu.addAction(self.menuitem_showscalerange)

            self.menuitem_showscaleaxis = QAction('Show Scale Axes', self.menu)
            self.menuitem_showscaleaxis.setCheckable(True)
            self.menu.addAction(self.menuitem_showscaleaxis)

            self.menuitem_showzeroline = QAction('Show Zero Lines', self.menu)
            self.menuitem_showzeroline.setCheckable(True)
            self.menu.addAction(self.menuitem_showzeroline)
            
            self.menuitem_fixscalerange = QAction('Fix Scale Ranges', self.menu)
            self.menuitem_fixscalerange.setCheckable(True)
            self.menu.addAction(self.menuitem_fixscalerange)
                
            self.menuitem_allowdownsampling = QAction('Allow Downsampling', self.menu)
            self.menuitem_allowdownsampling.setCheckable(True)
            self.menuitem_allowdownsampling.setChecked(True)
            self.menu.addAction(self.menuitem_allowdownsampling)
            
            self.menuitem_degap = QAction('Allow Degapping', self.menu)
            self.menuitem_degap.setCheckable(True)
            self.menuitem_degap.setChecked(True)
            self.menu.addAction(self.menuitem_degap)
            
            self.menuitem_fft_filtering = QAction('FFT Filtering', self.menu)
            self.menuitem_fft_filtering.setCheckable(True)
            self.menuitem_fft_filtering.setChecked(False)
            self.menu.addAction(self.menuitem_fft_filtering)
            
            self.menuitem_lphp = QAction('Bandpass is Lowpass + Highpass', self.menu)
            self.menuitem_lphp.setCheckable(True)
            self.menuitem_lphp.setChecked(True)
            self.menu.addAction(self.menuitem_lphp)
            
            self.menuitem_watch = QAction('Watch Files', self.menu)
            self.menuitem_watch.setCheckable(True)
            self.menuitem_watch.setChecked(False)
            self.menu.addAction(self.menuitem_watch)


            self.visible_length_menu = QMenu('Visible Length', self.menu)
            menudef = [
                ('Short', 6000),
                ('Medium', 20000),
                ('Long', 60000),
            ]
            
            self.menuitems_visible_length = add_radiobuttongroup(self.visible_length_menu, menudef, self, self.visible_length_change)
            self.visible_length = menudef[0][1]
            self.menu.addMenu( self.visible_length_menu )
            
            self.menu.addSeparator()
            
            self.snufflings_menu = QMenu('Run Snuffling', self.menu)
            self.menu.addMenu(self.snufflings_menu)
            
            self.toggle_panel_menu = QMenu('Panels', self.menu)
            self.menu.addMenu(self.toggle_panel_menu)
            
            self.menuitem_reload = QAction('Reload Snufflings', self.menu)
            self.menu.addAction(self.menuitem_reload)
            self.connect( self.menuitem_reload, SIGNAL("triggered(bool)"), self.setup_snufflings )

            self.menu.addSeparator()

            self.menuitem_test = QAction('Test', self.menu)
            self.menuitem_test.setCheckable(True)
            self.menuitem_test.setChecked(False)
            self.menu.addAction(self.menuitem_test)
            self.connect( self.menuitem_test, SIGNAL("toggled(bool)"), self.toggletest )

            self.menuitem_print = QAction('Print', self.menu)
            self.menu.addAction(self.menuitem_print)
            self.connect( self.menuitem_print, SIGNAL("triggered(bool)"), self.printit )
            
            self.menuitem_svg = QAction('Save as SVG', self.menu)
            self.menu.addAction(self.menuitem_svg)
            self.connect( self.menuitem_svg, SIGNAL("triggered(bool)"), self.savesvg )
            
            self.menuitem_help = QAction('Help', self.menu)
            self.menu.addAction(self.menuitem_help)
            self.connect( self.menuitem_help, SIGNAL('triggered(bool)'), self.help )
            
            self.menuitem_about = QAction('About', self.menu)
            self.menu.addAction(self.menuitem_about)
            self.connect( self.menuitem_about, SIGNAL('triggered(bool)'), self.about )

            self.menuitem_close = QAction('Close', self.menu)
            self.menu.addAction(self.menuitem_close)
            self.connect( self.menuitem_close, SIGNAL("triggered(bool)"), self.myclose )
           
            self.menu.addSeparator()
            
            self.connect( self.menu, SIGNAL('triggered(QAction*)'), self.update )
                
            self.time_projection = Projection()
            self.set_time_range(self.pile.get_tmin(), self.pile.get_tmax())
            self.time_projection.set_out_range(0., self.width())
                
            self.gather = None
    
            self.trace_filter = None
            self.quick_filter = None
            self.quick_filter_patterns = None, None
            self.blacklist = []
            
            self.track_to_screen = Projection()
            self.track_to_nslc_ids = {}
        
            self.old_vec = None
            self.old_processed_traces = None
            
            self.timer = QTimer( self )
            self.connect( self.timer, SIGNAL("timeout()"), self.periodical ) 
            self.timer.setInterval(1000)
            self.timer.start()
            self.pile.add_listener(self)
            self.trace_styles = {}
            self.determine_box_styles()
            self.setMouseTracking(True)
            
            user_home_dir = os.environ['HOME']
            self.snuffling_modules = {}
            self.snuffling_paths = [ os.path.join(user_home_dir, '.snufflings') ]
            self.default_snufflings = None
            self.snufflings = []

            self.stations = {}
            
            self.timer_draw = Timer()
            self.timer_cutout = Timer()
            
            self.interactive_range_change_time = 0.0
            self.interactive_range_change_delay_time = 10.0
            self.follow_timer = None
            
            self.sortingmode_change_time = 0.0
            self.sortingmode_change_delay_time = None

            self.old_data_ranges = {}
            
            self.error_messages = {}
            self.return_tag = None
            self.wheel_pos = 60

            self.setAcceptDrops(True)
            self._paths_to_load = []

            self.automatic_updates = True

            self.closing = False

        def fail(self, reason):
            box = QMessageBox(self)
            box.setText(reason)
            box.exec_()
    
        def set_trace_filter(self, filter_func):
            self.trace_filter = filter_func
            self.sortingmode_change()

        def update_trace_filter(self):
            if self.blacklist:
                blacklist_func = lambda tr: not pyrocko.util.match_nslc(self.blacklist, tr.nslc_id)
            else:
                blacklist_func = None
            
            if self.quick_filter is None and blacklist_func is None:
                self.set_trace_filter( None )
            elif self.quick_filter is None:
                self.set_trace_filter( blacklist_func )
            elif blacklist_func is None:
                self.set_trace_filter( self.quick_filter )                
            else:
                self.set_trace_filter( lambda tr: blacklist_func(tr) and self.quick_filter(tr) )

        def set_quick_filter(self, filter_func):
            self.quick_filter = filter_func
            self.update_trace_filter()
            
        def set_quick_filter_patterns(self, patterns, inputline=None):
            if patterns is not None:
                self.set_quick_filter(lambda tr: pyrocko.util.match_nslc(patterns, tr.nslc_id))
            else:
                self.set_quick_filter(None)
                
            self.quick_filter_patterns = patterns, inputline
            
        def get_quick_filter_patterns(self):
            return self.quick_filter_patterns
            
        def add_blacklist_pattern(self, pattern):
            if pattern == 'empty':
                keys = set(self.pile.nslc_ids)
                trs = self.pile.all(tmin=self.tmin, tmax=self.tmax, load_data=False, degap=False)
                for tr in trs:
                    if tr.nslc_id in keys:
                        keys.remove(tr.nslc_id)

                for key in keys:
                    xpattern = '.'.join(key)
                    if xpattern not in self.blacklist:
                        self.blacklist.append(xpattern)

            else: 
                if pattern in self.blacklist:
                    self.blacklist.remove(pattern)

                self.blacklist.append(pattern)
            
            logger.info('Blacklist is [ %s ]' % ', '.join(self.blacklist))
            self.update_trace_filter()
            
        def remove_blacklist_pattern(self, pattern):
            if pattern in self.blacklist:
                self.blacklist.remove(pattern)
            else:
                raise PileViewerMainException('Pattern not found in blacklist.')
            
            logger.info('Blacklist is [ %s ]' % ', '.join(self.blacklist))
            self.update_trace_filter()
            
        def clear_blacklist(self):
            self.blacklist = []
            self.update_trace_filter()
            
        def ssort(self, tr):
            return self._ssort(tr)
        
        def station_key(self, x):
            return x.network, x.station
        
        def station_attrib(self, tr, getter, default_getter):
            sk = self.station_key(tr)
            if sk in self.stations:
                station = self.stations[sk]
                return getter(station)
            else:
                return default_getter(tr)
        
        def get_station(self, sk):
            return self.stations[sk]

        def has_station(self, station):
            sk = self.station_key(station)
            return sk in self.stations

        def station_latlon(self, tr, default_getter=lambda tr: (0.,0.)):
            return self.station_attrib(tr, lambda sta: (sta.lat, sta.lon), default_getter)

        def set_stations(self, stations):
            self.stations = {}
            self.add_stations(stations)
        
        def add_stations(self, stations):
            for station in stations:
                sk = self.station_key(station)
                self.stations[sk] = station
        
            ev = self.get_active_event()
            if ev:
                self.set_origin(ev)

        def add_event(self, event):
            marker = EventMarker(event)
            self.add_marker( marker )
       
        def set_event_marker_as_origin(self, ignore):
            selected = self.selected_markers()
            if not selected:
                self.fail('An event marker must be selected.')
                return

            m = selected[0]
            if not isinstance(m, EventMarker):
                self.fail('Selected marker is not an event.')
                return

            self.set_active_event_marker(m)

        def set_active_event_marker(self, event_marker):
            if self.active_event_marker:
                self.active_event_marker.set_active(False)
            self.active_event_marker = event_marker
            event_marker.set_active(True)
            event = event_marker.get_event()
            self.set_origin(event)
            self.emit(SIGNAL('active_event_changed()'))

        def set_active_event(self, event):
            for marker in self.markers:
                if isinstance(marker, EventMarker):
                    if marker.get_event() is event:
                        self.set_active_event_marker(marker)
        
        def get_active_event_marker(self):
            return self.active_event_marker
        
        def get_active_event(self):
            m = self.get_active_event_marker()
            if m is not None:
                return m.get_event()
            else:
                return None
        
        def set_origin(self, location):
            for station in self.stations.values():
                station.set_event_relative_data(location)
            self.sortingmode_change()
        
        def toggletest(self, checked):
            if checked:
                sp = Integrator()
                
                self.add_shadow_pile(sp)
            else:
                self.remove_shadow_piles()
        
        def add_shadow_pile(self, shadow_pile):
            shadow_pile.set_basepile(self.pile)
            shadow_pile.add_listener(self)
            self.pile = shadow_pile
        
        def remove_shadow_piles(self):
            self.pile = self.pile.get_basepile()
            
        def iter_snuffling_modules(self):
            for path in self.snuffling_paths:
                
                if not os.path.isdir(path): 
                    os.mkdir(path)
                
                for fn in os.listdir(path):
                    if not fn.endswith('.py'):
                        continue
                    
                    name = fn[:-3]
                    if (path, name) not in self.snuffling_modules:
                        self.snuffling_modules[path, name] = \
                            pyrocko.snuffling.SnufflingModule(path, name, self)
                    
                    yield self.snuffling_modules[path, name]
                    
        def setup_snufflings(self):
            # user snufflings
            for mod in self.iter_snuffling_modules():
                try:
                    mod.load_if_needed()
                except pyrocko.snuffling.BrokenSnufflingModule, e:
                    logger.warn( 'Snuffling module "%s" is broken' % e )

            # load the default snufflings on first run
            if self.default_snufflings is None:
                self.default_snufflings = pyrocko.snufflings.__snufflings__()
                for snuffling in self.default_snufflings:
                    self.add_snuffling(snuffling)
        
        def set_panel_parent(self, panel_parent):
            self.panel_parent = panel_parent 
        
        def get_panel_parent(self):
            return self.panel_parent

        def add_snuffling(self, snuffling, reloaded=False):
            snuffling.init_gui(self, self.get_panel_parent(), self, reloaded=reloaded)
            self.snufflings.append(snuffling)
            self.update()
            
        def remove_snuffling(self, snuffling):
            snuffling.delete_gui()
            self.update()
            self.snufflings.remove(snuffling)
            snuffling.pre_destroy()

        def add_snuffling_menuitem(self, item):
            self.snufflings_menu.addAction(item)
            item.setParent(self.snufflings_menu)
            sort_actions(self.snufflings_menu)

        def remove_snuffling_menuitem(self, item):
            self.snufflings_menu.removeAction(item)
        
        def add_panel_toggler(self, item):
            self.toggle_panel_menu.addAction(item)
            item.setParent(self.toggle_panel_menu)
            sort_actions(self.toggle_panel_menu)

        def remove_panel_toggler(self, item):
            self.toggle_panel_menu.removeAction(item)

        def load(self, paths, regex=None, format='from_extension', cache_dir=pyrocko.config.cache_dir, force_cache=False):

            if isinstance(paths, str):
                paths = [ paths ]
             
            fns = pyrocko.util.select_files(paths, selector=None, regex=regex, show_progress=False)
            if not fns:
                return

            cache = pyrocko.pile.get_cache(cache_dir)
            
            t = [ time.time() ]
            def update_bar(label, value):
                pbs = self.parent().get_progressbars()
                if label.lower() == 'looking at files':
                    label = 'Looking at %i files' % len(fns)
                else:
                    label = 'Scanning %i files' % len(fns)

                return pbs.set_status(label, value)

            def update_progress(label, i,n):
                abort = False
                
                qApp.processEvents()
                if n != 0:
                    perc = i*100/n
                else:
                    perc = 100
                abort |= update_bar(label, perc)
                abort |= self.window().is_closing()

                tnow = time.time()
                if t[0]+1. < tnow:
                    self.update()
                    t[0] = tnow

                return abort

            self.automatic_updates = False

            self.pile.load_files( sorted(fns), filename_attributes=regex, 
                    cache=cache, fileformat=format, 
                    show_progress=False, update_progress=update_progress)

            self.automatic_updates = True
            self.update()

        def load_queued(self):
            if not self._paths_to_load:
                return
            paths = self._paths_to_load
            self._paths_to_load = []
            self.load(paths)

        def load_soon(self, paths):
            self._paths_to_load.extend(paths)
            QTimer.singleShot( 200, self.load_queued )
        
        def open_waveforms(self, _=None):

            caption = 'Select one or more files to open'

            fns = QFileDialog.getOpenFileNames(
                self,
                caption)

            self.load(list(str(fn) for fn in fns))

        def open_waveform_directory(self, _=None):

            caption = 'Select directory to scan for waveform files'

            fn = QFileDialog.getExistingDirectory(
                self,
                caption)

            self.load([str(fn)])

        def add_traces(self, traces):
            if traces:
                mtf = pyrocko.pile.MemTracesFile(None, traces)
                self.pile.add_file(mtf)
                ticket = (self.pile, mtf)
                return ticket
            else:
                return (None,None)
            
        def release_data(self, tickets):
            for ticket in tickets:
                pile, mtf = ticket
                if pile is not None:
                     pile.remove_file(mtf)
                   
        def periodical(self):
            if self.menuitem_watch.isChecked():
                if self.pile.reload_modified():
                    self.update()
    
        def get_pile(self):
            return self.pile
        
        def pile_changed(self, what):
            self.pile_has_changed = True
            self.emit(SIGNAL('pile_has_changed_signal()'))
            if self.automatic_updates:
                self.update()
           
        def set_gathering(self, gather=None, order=None, color=None):
            
            if gather is None:
                gather = lambda tr: tr.nslc_id
                
            if order is None:
                order = lambda a,b: cmp(a, b)
            
            if color is None:
                color = lambda tr: tr.location
            
            self.gather = gather
            keys = self.pile.gather_keys(gather, self.trace_filter) 
            self.color_gather = color
            self.color_keys = self.pile.gather_keys(color)
            previous_ntracks = self.ntracks
            self.set_ntracks(len(keys))

            if self.shown_tracks_range is None or previous_ntracks == 0 or self.show_all:
                l, h = 0, min(self.ntracks_shown_max, self.ntracks)
                key_at_top = None
                n = h-l

            else:
                l, h = self.shown_tracks_range
                key_at_top = self.track_keys[l] 
                n = h-l

            self.track_keys = sorted(keys, cmp=order)

            if key_at_top is not None:
                try:
                    ind = self.track_keys.index(key_at_top)
                    l = ind
                    h = l+n
                except:
                    pass

            self.set_tracks_range((l,h))

            self.key_to_row = dict([ (key, i) for (i,key) in enumerate(self.track_keys) ])
            inrange = lambda x,r: r[0] <= x and x < r[1]
            
            def trace_selector(trace):
                gt = self.gather(trace)
                return (gt in self.key_to_row and
                   inrange(self.key_to_row[gt], self.shown_tracks_range))
        
            if self.trace_filter is not None:
                self.trace_selector = lambda x: self.trace_filter(x) and trace_selector(x)
            else:
                self.trace_selector = trace_selector

            if self.tmin == working_system_time_range[0] and self.tmax == working_system_time_range[1] or self.show_all:
                tmin, tmax = self.pile.get_tmin(), self.pile.get_tmax()
                if tmin is not None and tmax is not None:
                    tlen = (tmax - tmin)
                    tpad = tlen * 5./self.width()
                    self.set_time_range(tmin-tpad, tmax+tpad)
        
        def set_time_range(self, tmin, tmax):
            if tmin is None:
                tmin = working_system_time_range[0]

            if tmax is None:
                tmax = working_system_time_range[1]

            if tmin > tmax:
                tmin, tmax = tmax, tmin
                
            if tmin == tmax:
                tmin -= 1.
                tmax += 1.
            
            tmin = max(working_system_time_range[0], tmin)
            tmax = min(working_system_time_range[1], tmax)
            
            min_deltat = self.content_deltat_range()[0]
            if (tmax - tmin < min_deltat):
                m = (tmin + tmax) / 2.
                tmin = m - min_deltat/2.
                tmax = m + min_deltat/2.
                
            self.time_projection.set_in_range(tmin,tmax)
            self.tmin, self.tmax = tmin, tmax
        
        def get_time_range(self):
            return self.tmin, self.tmax
        
        def ypart(self, y):
            if y < self.ax_height:
                return -1
            elif y > self.height()-self.ax_height:
                return 1
            else:
                return 0

        def time_fractional_digits(self):
            min_deltat = self.content_deltat_range()[0]
            return min(9, max(1, int(-math.floor(math.log10(min_deltat)))+2))
    
        def write_markers(self):

            fn = QFileDialog.getSaveFileName(self,)
            if fn:
                Marker.save_markers(self.markers, fn,
                        fdigits=self.time_fractional_digits())

        def write_selected_markers(self):
            fn = QFileDialog.getSaveFileName(self,)
            if fn:
                Marker.save_markers(self.selected_markers(), fn,
                        fdigits=self.time_fractional_digits())

        def read_markers(self):
            fn = QFileDialog.getOpenFileName(self,)
            if fn:
                self.add_markers(Marker.load_markers(fn))

                self.associate_phases_to_events()

        def associate_phases_to_events(self):
            
            events = {}
            for marker in self.markers:
                if isinstance(marker, EventMarker):
                    events[marker.get_event_hash()] = marker.get_event()
            
            for marker in self.markers:
                if isinstance(marker, PhaseMarker):
                    h = marker.get_event_hash()
                    if marker.get_event() is None and h is not None and marker and h in events:
                        marker.set_event(events[h])
                        marker.set_event_hash(None)
        
        def add_marker(self, marker):
            self.markers.append(marker)
        
        def add_markers(self, markers):
            self.markers.extend(markers)
        
        def remove_marker(self, marker):
            try:
                self.markers.remove(marker)
                if marker is self.active_event_marker:
                    self.active_event_marker.set_active(False)
                    self.active_event_marker = None

            except ValueError:
                pass

        def remove_markers(self, markers):
            for marker in markers:
                self.remove_marker(marker)

        def set_markers(self, markers):
            self.markers = markers
    
        def selected_markers(self):
            return [ marker for marker in self.markers if marker.is_selected() ]
   
        def get_markers(self):
            return self.markers

        def mousePressEvent( self, mouse_ev ):
            self.show_all = False
            #self.setMouseTracking(False)
            point = self.mapFromGlobal(mouse_ev.globalPos())

            if mouse_ev.button() == Qt.LeftButton:
                marker = self.marker_under_cursor(point.x(), point.y())
                if self.picking:
                    if self.picking_down is None:
                        self.picking_down = self.time_projection.rev(mouse_ev.x()), mouse_ev.y()
                elif marker is not None:
                    if not (mouse_ev.modifiers() & Qt.ShiftModifier):
                        self.deselect_all()
                    marker.set_selected(True)
                    self.update()
                else:
                    self.track_start = mouse_ev.x(), mouse_ev.y()
                    self.track_trange = self.tmin, self.tmax
            
            if mouse_ev.button() == Qt.RightButton:
                self.menu.exec_(QCursor.pos())
            self.update_status()
    
        def mouseReleaseEvent( self, mouse_ev ):
            if self.ignore_releases:
                self.ignore_releases -= 1
                return
            
            if self.picking:
                self.stop_picking(mouse_ev.x(), mouse_ev.y())
            self.track_start = None
            self.track_trange = None
            self.update_status()
            
        def mouseDoubleClickEvent(self, mouse_ev):
            self.show_all = False
            self.start_picking(None)
            self.ignore_releases = 1
    
        def mouseMoveEvent( self, mouse_ev ):
            point = self.mapFromGlobal(mouse_ev.globalPos())
    
            if self.picking:
                self.update_picking(point.x(),point.y())
           
            elif self.track_start is not None:
                x0, y0 = self.track_start
                dx = (point.x() - x0)/float(self.width())
                dy = (point.y() - y0)/float(self.height())
                if self.ypart(y0) == 1: dy = 0
                
                tmin0, tmax0 = self.track_trange
                
                scale = math.exp(-dy*5.)
                dtr = scale*(tmax0-tmin0) - (tmax0-tmin0)
                frac = x0/float(self.width())
                dt = dx*(tmax0-tmin0)*scale
                
                self.interrupt_following()
                self.set_time_range(tmin0 - dt - dtr*frac, tmax0 - dt + dtr*(1.-frac))
                
                self.update()
            else:
                self.hoovering(point.x(),point.y())
                
            self.update_status()
       
       
        def nslc_ids_under_cursor(self, x,y):
            ftrack = self.track_to_screen.rev(y)
            nslc_ids = self.get_nslc_ids_for_track(ftrack)
            return nslc_ids
       
        def marker_under_cursor(self, x,y):
            mouset = self.time_projection.rev(x)
            deltat = (self.tmax-self.tmin)*self.click_tolerance/self.width()
            relevant_nslc_ids = None
            for marker in self.markers:
                if marker.kind not in self.visible_marker_kinds:
                    continue

                if (abs(mouset-marker.get_tmin()) < deltat or 
                    abs(mouset-marker.get_tmax()) < deltat):
                    
                    if relevant_nslc_ids is None:
                        relevant_nslc_ids = self.nslc_ids_under_cursor(x,y)
                    
                    marker_nslc_ids = marker.get_nslc_ids()
                    if not marker_nslc_ids:
                        return marker
                    
                    for nslc_id in marker_nslc_ids:
                        if nslc_id in relevant_nslc_ids:
                            return marker
       
        def hoovering(self, x,y):
            mouset = self.time_projection.rev(x)
            deltat = (self.tmax-self.tmin)*self.click_tolerance/self.width()
            needupdate = False
            haveone = False
            relevant_nslc_ids = self.nslc_ids_under_cursor(x,y)
            for marker in self.markers:
                if marker.kind not in self.visible_marker_kinds:
                    continue

                state = abs(mouset-marker.get_tmin()) < deltat or \
                        abs(mouset-marker.get_tmax()) < deltat and not haveone
                
                if state:
                    xstate = False
                    
                    marker_nslc_ids = marker.get_nslc_ids()
                    if not marker_nslc_ids:
                        xstate = True
                    
                    for nslc in relevant_nslc_ids:
                        if marker.match_nslc(nslc):
                            xstate = True
                            
                    state = xstate
                    
                if state:
                    haveone = True
                oldstate = marker.is_alerted()
                if oldstate != state:
                    needupdate = True
                    marker.set_alerted(state)
                    if state:
                        self.message = marker.hoover_message()

            if not haveone:
                self.message = None

            if needupdate:
                self.update()
                
        def keyPressEvent(self, key_event):
            dt = self.tmax - self.tmin
            tmid = (self.tmin + self.tmax) / 2.
           
            keytext = str(key_event.text())

            if keytext == '?':
                self.help()

            elif keytext == ' ':
                self.interrupt_following()
                self.set_time_range(self.tmin+dt, self.tmax+dt)
            
            elif keytext == 'b':
                dt = self.tmax - self.tmin
                self.interrupt_following()
                self.set_time_range(self.tmin-dt, self.tmax-dt)
            
            elif keytext in ('p', 'n', 'P', 'N'):
                smarkers = self.selected_markers()
                tgo = None
                dir = str(keytext)
                if smarkers:
                    tmid = smarkers[0].tmin
                    for smarker in smarkers:
                        if dir == 'n':
                            tmid = max(smarker.tmin, tmid)
                        else:
                            tmid = min(smarker.tmin, tmid)

                    tgo = tmid

                if dir.lower() == 'n':
                    for marker in sorted(self.markers, key=operator.attrgetter('tmin')):
                        t = marker.tmin
                        if t > tmid and marker.kind in self.visible_marker_kinds \
                                    and (dir == 'n' or isinstance(marker, EventMarker)):
                            self.deselect_all()
                            marker.set_selected(True)
                            tgo = t
                            break
                else: 
                    for marker in sorted(self.markers, key=operator.attrgetter('tmin'), reverse=True):
                        t = marker.tmin
                        if t < tmid and marker.kind in self.visible_marker_kinds \
                                    and (dir == 'p' or isinstance(marker, EventMarker)):
                            self.deselect_all()
                            marker.set_selected(True)
                            tgo = t
                            break
                        
                if tgo is not None:
                    self.interrupt_following()
                    self.set_time_range(tgo-dt/2.,tgo+dt/2.)
                        
            elif keytext == 'q' or keytext == 'x':
                self.myclose(keytext)
    
            elif keytext == 'r':
                if self.pile.reload_modified():
                    self.reloaded = True
   
            elif keytext == 'R':
                self.setup_snufflings() 

            elif key_event.key() == Qt.Key_Backspace:
                self.remove_markers(self.selected_markers())

            elif keytext == 'a':
                for marker in self.markers:
                    if ((self.tmin <= marker.get_tmin() <= self.tmax or
                        self.tmin <= marker.get_tmax() <= self.tmax) and
                        marker.kind in self.visible_marker_kinds):
                        marker.set_selected(True)
                    else:
                        marker.set_selected(False)

            elif keytext == 'A':
                for marker in self.markers:
                    if marker.kind in self.visible_marker_kinds:
                        marker.set_selected(True)

            elif keytext == 'd':
                self.deselect_all()
                    
            elif keytext == 'e':
                markers = self.selected_markers()
                event_markers_in_spe = [ marker for marker in markers if not isinstance(marker, PhaseMarker) ]
                phase_markers = [ marker for marker in markers if isinstance(marker, PhaseMarker) ]

                if len(event_markers_in_spe) == 1:
                    event_marker = event_markers_in_spe[0]
                    if not isinstance(event_marker, EventMarker):
                        nslcs = list(event_marker.nslc_ids)
                        lat, lon = 0.0, 0.0
                        old = self.get_active_event()
                        if len(nslcs) == 1:
                            lat,lon = self.station_latlon(NSLC(*nslcs[0]))
                        elif old is not None:
                            lat,lon = old.lat, old.lon

                        event_marker.convert_to_event_marker(lat,lon)
                        
                    self.set_active_event_marker(event_marker)
                    event = event_marker.get_event()
                    for marker in phase_markers:
                        marker.set_event(event)

                else:
                    for marker in event_markers_in_spe:
                        marker.convert_to_event_marker()
            
            elif keytext in ('0', '1', '2', '3', '4', '5'):
                for marker in self.selected_markers():
                    marker.set_kind(int(keytext))
    
            elif key_event.key() in fkey_map:
                self.set_phase_kind(self.selected_markers(), fkey_map[key_event.key()])
                
            elif key_event.key() == Qt.Key_Escape:
                if self.picking:
                    self.stop_picking(0,0,abort=True)
            
            elif key_event.key() == Qt.Key_PageDown:
                self.scroll_tracks(self.shown_tracks_range[1]-self.shown_tracks_range[0])
                
            elif key_event.key() == Qt.Key_PageUp:
                self.scroll_tracks(self.shown_tracks_range[0]-self.shown_tracks_range[1])
                
            elif keytext == '+':
                self.zoom_tracks(0.,1.)
            
            elif keytext == '-':
                self.zoom_tracks(0.,-1.)
                
            elif keytext == '=':
                ntracks_shown = self.shown_tracks_range[1]-self.shown_tracks_range[0]
                dtracks = self.initial_ntracks_shown_max - ntracks_shown 
                self.zoom_tracks(0.,dtracks)
            
            elif keytext == ':':
                self.emit(SIGNAL('want_input()'))

            elif keytext == 'f':
                if self.window().windowState() & Qt.WindowFullScreen:
                    self.window().showNormal()
                else:
                    self.window().showFullScreen()

            elif keytext == 'g':
                self.go_to_selection()
               
            elif key_event.key() in (Qt.Key_Left, Qt.Key_Right):
                dir = 1
                amount = 1
                if key_event.key() == Qt.Key_Left:
                    dir = -1
                if key_event.modifiers() & Qt.ShiftModifier:
                    amount = 10
                self.nudge_selected_markers(dir*amount)

            self.update()
            self.update_status()

        def nudge_selected_markers(self, npixels):
            a,b = self.time_projection.ur
            c,d = self.time_projection.xr
            for marker in self.selected_markers():
                if not isinstance(marker,EventMarker):
                    marker.tmin += npixels * (d-c)/b
                    marker.tmax += npixels * (d-c)/b
  
        def about(self):
            fn = pyrocko.util.data_file('snuffler.png')
            txt = open( pyrocko.util.data_file('snuffler_about.html') ).read()
            label = QLabel(txt % { 'logo': fn } )
            label.setAlignment( Qt.AlignVCenter | Qt.AlignHCenter )
            self.show_doc('About', [label], target='tab')

        def help(self):
            class MyScrollArea(QScrollArea):

                def sizeHint(self):
                    s = QSize()
                    s.setWidth(self.widget().sizeHint().width())
                    s.setHeight(self.widget().sizeHint().height())
                    return s

            hcheat = QLabel(open(pyrocko.util.data_file('snuffler_help.html')).read())
            hepilog = QLabel(open(pyrocko.util.data_file('snuffler_help_epilog.html')).read())
            for h in [ hcheat, hepilog ]:
                h.setAlignment( Qt.AlignTop | Qt.AlignHCenter )
                h.setWordWrap(True)

            self.show_doc('Help', [hcheat, hepilog], target='panel')

        def show_doc(self, name, labels, target='panel'):
            scroller = QScrollArea()
            frame = QFrame(scroller)
            frame.setLineWidth(0)
            layout = QVBoxLayout()
            layout.setContentsMargins(0,0,0,0)
            layout.setSpacing(0)
            frame.setLayout(layout)
            scroller.setWidget(frame)
            scroller.setWidgetResizable(True)
            frame.setBackgroundRole(QPalette.Base) 
            for h in labels:
                h.setParent(frame)
                h.setBackgroundRole( QPalette.Base )
                layout.addWidget(h)
                frame.connect(h, SIGNAL('linkActivated(QString)'), self.open_link)
            
            if self.panel_parent is not None:
                if target == 'panel':
                    self.panel_parent.add_panel(name, scroller, True, volatile=True)
                else:
                    self.panel_parent.add_tab(name, scroller)
                

        def open_link(self, link):
            QDesktopServices.openUrl( QUrl(link) )

        def wheelEvent(self, wheel_event):
            self.wheel_pos += wheel_event.delta()
            n = self.wheel_pos / 120
            self.wheel_pos = self.wheel_pos % 120
            if n == 0:
                return

            amount = max(1.,abs(self.shown_tracks_range[0]-self.shown_tracks_range[1])/5.)
            wdelta = amount * n
            
            trmin,trmax = self.track_to_screen.get_in_range()
            anchor = (self.track_to_screen.rev(wheel_event.y())-trmin)/(trmax-trmin)
            if wheel_event.modifiers() & Qt.ControlModifier:
                self.zoom_tracks( anchor, wdelta )
            else:
                self.scroll_tracks( -wdelta )

        def dragEnterEvent(self, event):
            if event.mimeData().hasUrls():
                if any(url.toLocalFile() for url in event.mimeData().urls()):
                    event.setDropAction(Qt.LinkAction)
                    event.accept()

        def dropEvent(self, event):
            if event.mimeData().hasUrls():
                paths = list(str(url.toLocalFile()) for url in event.mimeData().urls())
                event.acceptProposedAction()
                self.load(paths)

        def get_phase_name(self, kind):
            return self.phase_names.get(kind, 'Unknown')

        def set_phase_kind(self, markers, kind):
            phasename = self.get_phase_name(kind)

            for marker in markers:
                if isinstance(marker, PhaseMarker):
                    if kind == 0:
                        marker.convert_to_marker()
                    else:
                        marker.set_phasename(phasename)
                        marker.set_event(self.get_active_event())
                        
                elif isinstance(marker, EventMarker):
                    pass

                else:
                    if kind != 0:
                        event = self.get_active_event()
                        marker.convert_to_phase_marker(event, phasename, None, False)

        def set_ntracks(self, ntracks):
            if self.ntracks != ntracks:
                self.ntracks = ntracks
                if self.shown_tracks_range is not None:
                    l,h = self.shown_tracks_range
                else:
                    l,h = 0,self.ntracks

                self.emit(SIGNAL('tracks_range_changed(int,int,int)'), self.ntracks, l,h) 
        
        def set_tracks_range(self, range, start=None):
            
            l,h = range
            l = min(self.ntracks-1, l)
            h = min(self.ntracks, h)
            l = max(0,l)
            h = max(1,h)
            
            if start is None:
                start = float(l)
            
            if self.shown_tracks_range != (l,h):
                self.shown_tracks_range = l,h
                self.shown_tracks_start = start

                self.emit( SIGNAL('tracks_range_changed(int,int,int)'), self.ntracks, l,h)

        def scroll_tracks(self, shift):
            shown = self.shown_tracks_range
            shiftmin = -shown[0]
            shiftmax = self.ntracks-shown[1]
            shift = max(shiftmin, shift)
            shift = min(shiftmax, shift)
            shown = shown[0] + shift, shown[1] + shift
            
            self.set_tracks_range((int(shown[0]), int(shown[1])))

            self.update()
            
        def zoom_tracks(self, anchor, delta):
            ntracks_shown = self.shown_tracks_range[1]-self.shown_tracks_range[0]
            
            if (ntracks_shown == 1 and delta <= 0) or (ntracks_shown == self.ntracks and delta >= 0):
                return
            
            ntracks_shown += int(round(delta))
            ntracks_shown = min(max(1, ntracks_shown), self.ntracks)
            
            u = self.shown_tracks_start
            nu = max(0., u-anchor*delta)
            nv = nu + ntracks_shown
            if nv > self.ntracks:
                nu -= nv - self.ntracks
                nv -= nv - self.ntracks
            
            self.set_tracks_range((int(round(nu)), int(round(nv))), nu)
            
            self.ntracks_shown_max = self.shown_tracks_range[1]-self.shown_tracks_range[0] 
            
            self.update()

        def content_time_range(self):
            pile = self.get_pile()
            tmin, tmax = pile.get_tmin(), pile.get_tmax()
            if tmin is None:
                tmin = working_system_time_range[0]
            if tmax is None:
                tmax = working_system_time_range[1]

            return tmin, tmax

        def content_deltat_range(self):
            pile = self.get_pile()
            
            deltatmin, deltatmax = pile.get_deltatmin(), pile.get_deltatmax()

            if deltatmin is None:
                deltatmin = 0.001

            if deltatmax is None:
                deltatmax = 1000.0

            return deltatmin, deltatmax
       
        def make_good_looking_time_range(self, tmin, tmax):
            if tmax < tmin:
                tmin, tmax = tmax, tmin

            dt = self.see_data_params()[-1] * 0.95
            if dt == 0.0:
                dt = 1.0

            if tmax-tmin < dt:
                vmin, vmax = self.get_time_range()
                dt = min(vmax - vmin, dt)
                tcenter = (tmin+tmax)/2.
                etmin, etmax = tmin, tmax
                tmin = min(etmin, tcenter - 0.5*dt)
                tmax = max(etmax, tcenter + 0.5*dt)
                dtm = tmax-tmin
                if etmin == tmin:
                    tmin -= dtm*0.1
                if etmax == tmax:
                    tmax += dtm*0.1
                    
            else:
                dtm = tmax-tmin
                tmin -= dtm*0.1
                tmax += dtm*0.1

            return tmin, tmax
        
        def go_to_selection(self):
            markers = self.selected_markers()
            pile = self.get_pile()
            tmax, tmin = self.content_time_range()
            for marker in markers:
                tmin = min(tmin, marker.tmin)
                tmax = max(tmax, marker.tmax)

            tmin, tmax = self.make_good_looking_time_range(tmin, tmax) 
            self.interrupt_following()
            self.set_time_range(tmin,tmax)
            self.update()
            
        def go_to_time(self, t, tlen=None):
            tmax = t
            if tlen is not None:
                tmax = t+tlen
            tmin, tmax = self.make_good_looking_time_range(t,tmax)
            self.interrupt_following()
            self.set_time_range(tmin,tmax)
            self.update()

        def go_to_event_by_name(self, name):
            for marker in self.markers:
                if isinstance(marker, EventMarker):
                    event = marker.get_event()
                    if event.name.lower() == name.lower():
                        tmin, tmax = self.make_good_looking_time_range(event.time, event.time)
                        self.interrupt_following()
                        self.set_time_range(tmin, tmax)

        def printit(self):
            printer = QPrinter()
            printer.setOrientation(QPrinter.Landscape)
            
            dialog = QPrintDialog(printer, self)
            dialog.setWindowTitle('Print')
            
            if dialog.exec_() != QDialog.Accepted:
                return
            
            painter = QPainter()
            painter.begin(printer)
            page = printer.pageRect()
            self.drawit(painter, printmode=False, w=page.width(), h=page.height())
            painter.end()
            
            
        def savesvg(self):
            
            fn = QFileDialog.getSaveFileName(self, 
                'Save as SVG',
                os.path.join(os.environ['HOME'],  'untitled.svg'),
                'SVG (*.svg)'
            )
            
            generator = QSvgGenerator()
            generator.setFileName(fn)
            generator.setSize(QSize(842, 595))

            painter = QPainter()
            painter.begin(generator)
            self.drawit(painter, printmode=False, w=generator.size().width(), h=generator.size().height())
            painter.end()
            
        def paintEvent(self, paint_ev ):
            """Called by QT whenever widget needs to be painted"""
            painter = QPainter(self)
    
            if self.menuitem_antialias.isChecked():
                painter.setRenderHint( QPainter.Antialiasing )
            
            self.drawit( painter )
            
            logger.debug('Time spent drawing: %.3f %.3f %.3f %.3f %.3f' % (self.timer_draw - self.timer_cutout))
            logger.debug('Time spent processing: %.3f %.3f %.3f %.3f %.3f' % self.timer_cutout.get())
            
        def determine_box_styles(self):
            
            traces = list(self.pile.iter_traces())
            traces.sort( key=operator.attrgetter('full_id') ) 
            istyle = 0
            trace_styles = {}
            for itr, tr in enumerate(traces):
                if itr > 0:
                    other = traces[itr-1]
                    if not (other.nslc_id == tr.nslc_id and
                        other.deltat == tr.deltat and
                        abs(other.tmax - tr.tmin) < gap_lap_tolerance*tr.deltat): istyle+=1
            
                trace_styles[tr.full_id, tr.deltat] = istyle
            
            self.trace_styles = trace_styles
            
        def draw_trace_boxes(self, p, time_projection, track_projections):
            
            for v_projection in track_projections.values():
                v_projection.set_in_range(0.,1.)
            
            selector = lambda x: x.overlaps(*time_projection.get_in_range())
            if self.trace_filter is not None:
                tselector = lambda x: selector(x) and self.trace_filter(x)
            else:
                tselector = selector

            traces = list(self.pile.iter_traces(group_selector=selector, trace_selector=tselector))
            traces.sort( key=operator.attrgetter('full_id') ) 

            def drawbox(itrack, istyle, traces):
                v_projection = track_projections[itrack]
                dvmin = v_projection(0.)
                dvmax = v_projection(1.)
                dtmin = time_projection.clipped(traces[0].tmin)
                dtmax = time_projection.clipped(traces[-1].tmax)
                
                style = box_styles[istyle%len(box_styles)]
                rect = QRectF( dtmin, dvmin, float(dtmax-dtmin), dvmax-dvmin )
                p.fillRect(rect, style.fill_brush)
                p.setPen(style.frame_pen)
                p.drawRect(rect)

            
            traces_by_style = {}
            for itr, tr in enumerate(traces):
                gt = self.gather(tr)
                if gt not in self.key_to_row:
                    continue

                itrack = self.key_to_row[gt]
                if not itrack in track_projections: continue
               
                istyle = self.trace_styles.get((tr.full_id, tr.deltat), 0)
                
                
                if len(traces) < 500:
                    drawbox(itrack, istyle, [tr])
                else:
                    if (itrack, istyle) not in traces_by_style:
                        traces_by_style[itrack, istyle] = []
                    traces_by_style[itrack, istyle].append(tr)

            for (itrack, istyle), traces in traces_by_style.iteritems():
                drawbox(itrack, istyle, traces)
        
        def drawit(self, p, printmode=False, w=None, h=None):
            """This performs the actual drawing."""
            
            self.timer_draw.start()
    
            if self.gather is None:
                self.set_gathering()
    
            if self.pile_has_changed:

                if not self.sortingmode_change_delayed():
                    self.sortingmode_change()
                    
                    if self.menuitem_showboxes.isChecked():
                        self.determine_box_styles()
                
                    self.pile_has_changed = False

            if h is None: h = float(self.height())
            if w is None: w = float(self.width())
            
            if printmode:
                primary_color = (0,0,0)
                secondary_color = (0.5,0.5,0.5)
            else:
                primary_color = pyrocko.plot.tango_colors['aluminium5']
                secondary_color = pyrocko.plot.tango_colors['aluminium3']
            
            ax_h = float(self.ax_height)
            
            vbottom_ax_projection = Projection()
            vtop_ax_projection = Projection()
            vcenter_projection = Projection()
           
            self.time_projection.set_out_range(0., w)
            vbottom_ax_projection.set_out_range(h-ax_h, h)
            vtop_ax_projection.set_out_range(0., ax_h)
            vcenter_projection.set_out_range(ax_h, h-ax_h)
            vcenter_projection.set_in_range(0.,1.)
            self.track_to_screen.set_out_range(ax_h, h-ax_h)
            
            ntracks = self.ntracks
            self.track_to_screen.set_in_range(*self.shown_tracks_range)
            track_projections = {}
            for i in range(*self.shown_tracks_range):
                proj = Projection()
                proj.set_out_range(self.track_to_screen(i+0.05),self.track_to_screen(i+1.-0.05))
                track_projections[i] = proj
            
                    
            if self.tmin < self.tmax:
                self.time_projection.set_in_range(self.tmin, self.tmax)
                vbottom_ax_projection.set_in_range(0, ax_h)
    
                self.tax.drawit( p, self.time_projection, vbottom_ax_projection )
                
                yscaler = pyrocko.plot.AutoScaler()
                if not printmode and self.menuitem_showboxes.isChecked():
                    self.draw_trace_boxes(p, self.time_projection, track_projections)
                
                if self.floating_marker:
                    self.floating_marker.draw(p, self.time_projection, vcenter_projection)
                
                for marker in self.markers:
                    if marker.get_tmin() < self.tmax and self.tmin < marker.get_tmax():
                        if marker.kind in self.visible_marker_kinds:
                            marker.draw(p, self.time_projection, vcenter_projection)
                    
                primary_pen = QPen(QColor(*primary_color))
                secondary_pen = QPen(QColor(*secondary_color))
                p.setPen(primary_pen)
                
                font = QFont()
                font.setBold(True)

                axannotfont = QFont()
                axannotfont.setBold(True)
                axannotfont.setPointSize(8)

                p.setFont(font)
                label_bg = QBrush( QColor(255,255,255,100) )
                
                processed_traces = self.prepare_cutout2(self.tmin, self.tmax, 
                                                    trace_selector=self.trace_selector, 
                                                    degap=self.menuitem_degap.isChecked())
                
                color_lookup = dict([ (k,i) for (i,k) in enumerate(self.color_keys) ])
                
                self.track_to_nslc_ids = {}
                nticks = 0
                annot_labels = []
                if processed_traces:
                    show_scales = self.menuitem_showscalerange.isChecked() or self.menuitem_showscaleaxis.isChecked()

                    fm = QFontMetrics(axannotfont, p.device())
                    trackheight = self.track_to_screen(1.-0.05) - self.track_to_screen(0.05)
                    nlinesavail = trackheight/float(fm.lineSpacing())
                    if self.menuitem_showscaleaxis.isChecked():
                        nticks = max(3, min(nlinesavail * 0.5, 15))
                    else:
                        nticks = 15

                    yscaler = pyrocko.plot.AutoScaler(no_exp_interval=(-3,2), approx_ticks=nticks, 
                            snap=show_scales and not self.menuitem_showscaleaxis.isChecked())
                    data_ranges = pyrocko.trace.minmax(processed_traces, key=self.scaling_key, mode=self.scaling_base)
                    if not self.menuitem_fixscalerange.isChecked():
                        self.old_data_ranges = data_ranges
                    else:
                        data_ranges.update(self.old_data_ranges)
                    
                    self.apply_scaling_hooks(data_ranges)
                    
                    trace_to_itrack = {}
                    track_scaling_keys = {}
                    track_scaling_colors = {}
                    for trace in processed_traces:
                        gt = self.gather(trace)
                        if gt not in self.key_to_row:
                            continue
                        
                        itrack = self.key_to_row[gt]
                        if itrack not in track_projections:
                            continue

                        trace_to_itrack[trace] = itrack

                        if itrack not in self.track_to_nslc_ids:
                            self.track_to_nslc_ids[itrack] = set()

                        self.track_to_nslc_ids[itrack].add( trace.nslc_id )
                        scaling_keys = self.scaling_key(trace)
                        
                        if itrack not in track_scaling_keys:
                            track_scaling_keys[itrack] = set()
                        
                        scaling_key = self.scaling_key(trace)
                        track_scaling_keys[itrack].add(scaling_key)

                        color = pyrocko.plot.color(color_lookup[self.color_gather(trace)])
                        k = itrack, scaling_key
                        if k not in track_scaling_colors and self.menuitem_colortraces.isChecked():
                            track_scaling_colors[k] = color
                        else:
                            track_scaling_colors[k] = primary_color

                    ### y axes, zero lines 

                    trace_projections = {}
                    for itrack in track_projections.keys():
                        if itrack not in track_scaling_keys:
                            continue
                        uoff = 0 
                        for scaling_key in track_scaling_keys[itrack]:
                            data_range = data_ranges[scaling_key]
                            dymin, dymax = data_range
                            ymin, ymax, yinc = yscaler.make_scale( (dymin/self.gain, dymax/self.gain) )
                            iexp = yscaler.make_exp(yinc)
                            factor = 10**iexp
                            trace_projection = track_projections[itrack].copy()
                            trace_projection.set_in_range(ymax,ymin)
                            trace_projections[itrack,scaling_key] = trace_projection
                            nscalings = track_scaling_keys.get(itrack, 0)
                            umin, umax = self.time_projection.get_out_range()
                            vmin, vmax = trace_projection.get_out_range()
                            umax_zeroline = umax
                            uoffnext = uoff

                            if show_scales:
                                pen = QPen(primary_pen)
                                k = itrack, scaling_key
                                if k in track_scaling_colors:
                                    c =  QColor(*track_scaling_colors[itrack, scaling_key] )
                                    pen.setColor(c)

                                p.setPen(pen)
                                if nlinesavail > 3:
                                    if self.menuitem_showscaleaxis.isChecked():
                                        ymin_annot = math.ceil(ymin/yinc)*yinc
                                        ny_annot = int(math.floor(ymax/yinc)-math.ceil(ymin/yinc))+1
                                        for iy_annot in range(ny_annot):
                                            y = ymin_annot + iy_annot*yinc
                                            v = trace_projection(y)
                                            line = QLineF(umax-10-uoff,v,umax-uoff,v)
                                            p.drawLine(line)
                                            if iy_annot == ny_annot - 1 and iexp != 0:
                                                sexp = ' &times; 10<sup>%i</sup>' % iexp
                                            else:
                                                sexp = ''

                                            snum = num_to_html(y/factor)
                                            lab = Label(p, umax-20-uoff, v, '%s%s' % (snum, sexp), label_bg=None, anchor='MR', font=axannotfont, color=c)
                                            uoffnext = max(lab.rect.width()+30., uoffnext)
                                            annot_labels.append(lab)
                                            if y == 0.:
                                                umax_zeroline = umax-20-lab.rect.width()-10-uoff
                                    else:
                                        if not self.menuitem_showboxes.isChecked():
                                            qpoints = make_QPolygonF( [umax-20-uoff, umax-10-uoff, umax-10-uoff, umax-20-uoff], 
                                                                      [vmax, vmax, vmin, vmin] )
                                            p.drawPolyline(qpoints)

                                        snum = num_to_html(ymin)
                                        labmin = Label(p, umax-15-uoff, vmax, snum, label_bg=None, anchor='BR', font=axannotfont, color=c)
                                        annot_labels.append(labmin)
                                        snum = num_to_html(ymax)
                                        labmax = Label(p, umax-15-uoff, vmin, snum, label_bg=None, anchor='TR', font=axannotfont, color=c)
                                        annot_labels.append(labmax)

                                        for lab in (labmin, labmax):
                                            uoffnext = max(lab.rect.width()+10., uoffnext)

                            if self.menuitem_showzeroline.isChecked():
                                v = trace_projection(0.)
                                if vmin <= v <= vmax:
                                    line = QLineF(umin, v, umax_zeroline, v)
                                    p.drawLine(line)

                            uoff = uoffnext

                    
                    p.setFont(font)
                    p.setPen(primary_pen)
                    for trace in processed_traces:
                        if not trace in trace_to_itrack:
                            continue

                        itrack = trace_to_itrack[trace]
                        scaling_key = self.scaling_key(trace)
                        trace_projection = trace_projections[itrack,scaling_key]
                        
                        vdata = trace_projection( trace.get_ydata() )
                        
                        udata_min = float(self.time_projection(trace.tmin))
                        udata_max = float(self.time_projection(trace.tmin+trace.deltat*(vdata.size-1)))
                        udata = num.linspace(udata_min, udata_max, vdata.size)
                        
                        qpoints = make_QPolygonF( udata, vdata )

                        umin, umax = self.time_projection.get_out_range()
                        vmin, vmax = trace_projection.get_out_range()
                        
                        trackrect = QRectF(umin,vmin, umax-umin, vmax-vmin)
                            
                        if self.menuitem_cliptraces.isChecked(): p.setClipRect(trackrect)
                        if self.menuitem_colortraces.isChecked():
                            color = pyrocko.plot.color(color_lookup[self.color_gather(trace)])
                            pen = QPen(QColor(*color))
                            p.setPen(pen)
                        
                        p.drawPolyline( qpoints )
                        
                        if self.floating_marker:
                            self.floating_marker.draw_trace(self, p, trace, self.time_projection, trace_projection, 1.0)
                            
                        for marker in self.markers:
                            if marker.get_tmin() < self.tmax and self.tmin < marker.get_tmax():
                                if marker.kind in self.visible_marker_kinds:
                                    marker.draw_trace(self, p, trace, self.time_projection, trace_projection, 1.0)
                        p.setPen(primary_pen)
                            
                        if self.menuitem_cliptraces.isChecked():
                            p.setClipRect(0,0,w,h)
                            
                p.setPen(primary_pen)
                
                while font.pointSize() > 2:
                    fm = QFontMetrics(font, p.device())
                    trackheight = self.track_to_screen(1.-0.05) - self.track_to_screen(0.05)
                    nlinesavail = trackheight/float(fm.lineSpacing())
                    if nlinesavail > 1:
                        break

                    font.setPointSize(font.pointSize()-1)

                p.setFont(font)
                for key in self.track_keys:
                    itrack = self.key_to_row[key]
                    if itrack in track_projections:
                        plabel = ' '.join([ str(x) for x in key if x is not None ])
                        lx = 10
                        ly = self.track_to_screen(itrack+0.5)
                        draw_label( p, lx, ly, plabel, label_bg, 'ML')

                for lab in annot_labels:
                    lab.draw()
            
            self.timer_draw.stop()
        
        def see_data_params(self):
            
            min_deltat = self.content_deltat_range()[0]

            # determine padding and downampling requirements
            if self.lowpass is not None:
                deltat_target = 1./self.lowpass * 0.25
                ndecimate = min(50, max(1, int(round(deltat_target / min_deltat))))
                tpad = 1./self.lowpass * 2.
            else:
                ndecimate = 1
                tpad = min_deltat*5.
                
            if self.highpass is not None:
                tpad = max(1./self.highpass * 2., tpad)
            
            nsee_points_per_trace = 5000*10
            tsee = ndecimate*nsee_points_per_trace*min_deltat
            
            return ndecimate, tpad, tsee

        def clean_update(self):
            self.old_processed_traces = None
            self.update()


        def prepare_cutout2(self, tmin, tmax, trace_selector=None, degap=True, nmax=6000):

            nmax = self.visible_length

            self.timer_cutout.start()

            tsee = tmax-tmin
            min_deltat_wo_decimate = tsee/nmax
            min_deltat_w_decimate = min_deltat_wo_decimate / 32
            
            min_deltat_allow = min_deltat_wo_decimate
            if self.lowpass is not None:
                target_deltat_lp = 0.25/self.lowpass
                if target_deltat_lp > min_deltat_wo_decimate:
                    min_deltat_allow = min_deltat_w_decimate
          
            min_deltat_allow = math.exp(int(math.floor(math.log( min_deltat_allow) )) )

            tmin_ = tmin
            tmax_ = tmax

            # fetch more than needed?
            if self.menuitem_liberal_fetch.isChecked():
                tlen = pyrocko.trace.nextpow2((tmax-tmin)*1.5)
                tmin = math.floor(tmin/tlen) * tlen
                tmax = math.ceil(tmax/tlen) * tlen
                     
            fft_filtering = self.menuitem_fft_filtering.isChecked()
            lphp = self.menuitem_lphp.isChecked()
            ads = self.menuitem_allowdownsampling.isChecked()
            
            # state vector to decide if cached traces can be used
            vec = (tmin, tmax, trace_selector, degap, self.lowpass, self.highpass, fft_filtering, lphp,
                min_deltat_allow, self.rotate, self.shown_tracks_range,
                ads, self.pile.get_update_count())
                
            if (self.old_vec and 
                self.old_vec[0] <= vec[0] and vec[1] <= self.old_vec[1] and
                vec[2:] == self.old_vec[2:] and not (self.reloaded or self.menuitem_watch.isChecked()) and
                self.old_processed_traces is not None):

                logger.debug('Using cached traces')
                processed_traces = self.old_processed_traces
                
            else:
                self.old_vec = vec
                
                processed_traces = []
                
                if self.pile.deltatmax >= min_deltat_allow:
                    

                    group_selector = lambda gr: gr.deltatmax >= min_deltat_allow 
                    if trace_selector is not None:
                        trace_selectorx = lambda tr: tr.deltat >= min_deltat_allow and trace_selector(tr)
                    else:
                        trace_selectorx = lambda tr: tr.deltat >= min_deltat_allow

                    freqs = [ f for f in (self.highpass, self.lowpass) if f is not None ]
                    
                    tpad = 0
                    if freqs:
                        tpad = max(1./min(freqs), tsee) 
                    
                    for traces in self.pile.chopper( tmin=tmin, tmax=tmax, tpad=tpad,
                                                    want_incomplete=True,
                                                    degap=degap,
                                                    maxgap=gap_lap_tolerance,
                                                    maxlap=gap_lap_tolerance,
                                                    keep_current_files_open=True, 
                                                    group_selector=group_selector,
                                                    trace_selector=trace_selectorx,
                                                    accessor_id=id(self),
                                                    snap=(math.floor, math.ceil),
                                                    include_last=True):

                        traces = self.pre_process_hooks(traces)

                        for trace in traces:
                            
                            if not (trace.meta and 'tabu' in trace.meta and trace.meta['tabu']):
                            
                                if fft_filtering:
                                    if self.lowpass is not None or self.highpass is not None:
                                        high, low = 1./(trace.deltat*len(trace.ydata)),  1./(2.*trace.deltat)
                                        
                                        if self.lowpass is not None:
                                            low = self.lowpass
                                        if self.highpass is not None:
                                            high = self.highpass
                                            
                                        trace.bandpass_fft(high, low)
                                    
                                else:
                                    
                                    if self.menuitem_allowdownsampling.isChecked():
                                        while trace.deltat < min_deltat_wo_decimate:
                                            trace.downsample(2)

                                    
                                    if not lphp and (self.lowpass is not None and self.highpass is not None and
                                        self.lowpass < 0.5/trace.deltat and
                                        self.highpass < 0.5/trace.deltat and
                                        self.highpass < self.lowpass):
                                        trace.bandpass(2,self.highpass, self.lowpass)
                                    else:
                                        if self.lowpass is not None:
                                            if self.lowpass < 0.5/trace.deltat:
                                                trace.lowpass(4,self.lowpass)
                                        
                                        if self.highpass is not None:
                                            if self.lowpass is None or self.highpass < self.lowpass:
                                                if self.highpass < 0.5/trace.deltat:
                                                    trace.highpass(4,self.highpass)
                            
                            processed_traces.append(trace)
                    
                if self.rotate != 0.0:
                    phi = self.rotate/180.*math.pi
                    cphi = math.cos(phi)
                    sphi = math.sin(phi)
                    for a in processed_traces:
                        for b in processed_traces: 
                            if (a.network == b.network and a.station == b.station and a.location == b.location and
                                ((a.channel.lower().endswith('n') and b.channel.lower().endswith('e')) or
                                (a.channel.endswith('1') and b.channel.endswith('2'))) and
                                abs(a.deltat-b.deltat) < a.deltat*0.001 and abs(a.tmin-b.tmin) < a.deltat*0.01 and
                                len(a.get_ydata()) == len(b.get_ydata())):
                                
                                aydata = a.get_ydata()*cphi+b.get_ydata()*sphi
                                bydata =-a.get_ydata()*sphi+b.get_ydata()*cphi
                                a.set_ydata(aydata)
                                b.set_ydata(bydata)

                processed_traces = self.post_process_hooks(processed_traces)
                                
                self.old_processed_traces = processed_traces
            
            chopped_traces = []
            for trace in processed_traces:
                try:
                    ctrace = trace.chop(tmin_-trace.deltat*4.,tmax_+trace.deltat*4., inplace=False, )
                except pyrocko.trace.NoData:
                    continue
                    
                if ctrace.data_len() < 2: continue
                
                chopped_traces.append(ctrace)
            
            self.timer_cutout.stop()
            return chopped_traces
       
        def pre_process_hooks(self, traces):
            for snuffling in self.snufflings:
                if snuffling._pre_process_hook_enabled:
                    traces = snuffling.pre_process_hook(traces)

            return traces

        def post_process_hooks(self, traces):
            for snuffling in self.snufflings:
                if snuffling._post_process_hook_enabled:
                    traces = snuffling.post_process_hook(traces)

            return traces

        def visible_length_change(self, ignore=None):
            for menuitem, vlen in self.menuitems_visible_length:
                if menuitem.isChecked():
                    self.visible_length = vlen

        def scaling_base_change(self, ignore=None):
            for menuitem, scaling_base in self.menuitems_scaling_base:
                if menuitem.isChecked():
                    self.scaling_base = scaling_base
        
        def scalingmode_change(self, ignore=None):
            for menuitem, scaling_key in self.menuitems_scaling:
                if menuitem.isChecked():
                    self.scaling_key = scaling_key
   
        def apply_scaling_hooks(self, data_ranges):
            for k in sorted(self.scaling_hooks.keys()):
                    hook = self.scaling_hooks[k]
                    hook(data_ranges)

        def set_scaling_hook(self, k, hook):
            self.scaling_hooks[k] = hook

        def remove_scaling_hook(self, k):
            del self.scaling_hooks[k]
        
        def remove_scaling_hooks(self):
            self.scaling_hooks = {}

        def s_sortingmode_change(self, ignore=None):
            for menuitem, valfunc in self.menuitems_ssorting:
                if menuitem.isChecked():
                    self._ssort = valfunc
            
            self.sortingmode_change()
    
        def sortingmode_change(self, ignore=None):
            for menuitem, (gather, order, color) in self.menuitems_sorting:
                if menuitem.isChecked():
                    self.set_gathering(gather, order, color)
                    
            self.sortingmode_change_time = time.time()
            
        def lowpass_change(self, value, ignore=None):
            self.lowpass = value
            self.passband_check()
            self.update()
            
        def highpass_change(self, value, ignore=None):
            self.highpass = value
            self.passband_check()
            self.update()
    
        def passband_check(self):
            if self.highpass and self.lowpass and self.highpass >= self.lowpass:
                self.message = 'Corner frequency of highpass larger than corner frequency of lowpass! I will now deactivate the highpass.'
                self.update_status()
            else:
                oldmess = self.message
                self.message = None
                if oldmess is not None:
                    self.update_status()        
        
        def gain_change(self, value, ignore):
            self.gain = value
            self.update()
            
        def rot_change(self, value, ignore):
            self.rotate = value
            self.update()
        
        def deselect_all(self):
            for marker in self.markers:
                marker.set_selected(False)
        
        def animate_picking(self):
            point = self.mapFromGlobal(QCursor.pos())
            self.update_picking(point.x(), point.y(), doshift=True)
            
        def get_nslc_ids_for_track(self, ftrack):
            itrack = int(ftrack)
            if itrack in self.track_to_nslc_ids:
                return self.track_to_nslc_ids[int(ftrack)]
            else:
                return []
                
        def stop_picking(self, x,y, abort=False):
            if self.picking:
                self.update_picking(x,y, doshift=False)
                #self.picking.hide()
                self.picking = None
                self.picking_down = None
                self.picking_timer.stop()
                self.picking_timer = None
                if not abort:
                    tmi = self.floating_marker.tmin
                    tma = self.floating_marker.tmax
                    self.markers.append(self.floating_marker)
                    self.floating_marker.set_selected(True)
                    print self.floating_marker
                
                self.floating_marker = None
        
        
        def start_picking(self, ignore):
            
            if not self.picking:
                self.deselect_all()
                self.picking = QRubberBand(QRubberBand.Rectangle)
                point = self.mapFromGlobal(QCursor.pos())
                
                gpoint = self.mapToGlobal( QPoint(point.x(), 0) )
                self.picking.setGeometry( gpoint.x(), gpoint.y(), 1, self.height())
                t = self.time_projection.rev(point.x())
                
                ftrack = self.track_to_screen.rev(point.y())
                nslc_ids = self.get_nslc_ids_for_track(ftrack)
                self.floating_marker = Marker(nslc_ids, t,t)
                self.floating_marker.set_selected(True)
    
                ##self.picking.show()
                #self.setMouseTracking(True)
                
                self.picking_timer = QTimer()
                self.connect( self.picking_timer, SIGNAL("timeout()"), self.animate_picking )
                self.picking_timer.setInterval(50)
                self.picking_timer.start()
    
        
        def update_picking(self, x,y, doshift=False):
            if self.picking:
                mouset = self.time_projection.rev(x)
                dt = 0.0
                if mouset < self.tmin or mouset > self.tmax:
                    if mouset < self.tmin:
                        dt = -(self.tmin - mouset)
                    else:
                        dt = mouset - self.tmax 
                    ddt = self.tmax-self.tmin
                    dt = max(dt,-ddt/10.)
                    dt = min(dt,ddt/10.)
                    
                x0 = x
                if self.picking_down is not None:
                    x0 = self.time_projection(self.picking_down[0])
                
                w = abs(x-x0)
                x0 = min(x0,x)
                
                tmin, tmax = self.time_projection.rev(x0), self.time_projection.rev(x0+w)
                tmin, tmax = ( max(working_system_time_range[0], tmin),
                            min(working_system_time_range[1], tmax))
                                
                p1 = self.mapToGlobal( QPoint(x0, 0))
                
                self.picking.setGeometry( p1.x(), p1.y(), max(w,1), self.height())
                
                ftrack = self.track_to_screen.rev(y)
                nslc_ids = self.get_nslc_ids_for_track(ftrack)
                self.floating_marker.set(nslc_ids, tmin, tmax)
                
                if dt != 0.0 and doshift:
                    self.interrupt_following()
                    self.set_time_range(self.tmin+dt, self.tmax+dt)
                
                self.update()
    
        def update_status(self):
            
            if self.message is None:
                point = self.mapFromGlobal(QCursor.pos())
                
                mouse_t = self.time_projection.rev(point.x())
                if not is_working_time(mouse_t): return
                if self.floating_marker:
                    tmi, tma = self.floating_marker.tmin, self.floating_marker.tmax
                    tt, ms = gmtime_x(tmi)
                
                    if tmi == tma:
                        message = mystrftime(fmt='Pick: %Y-%m-%d %H:%M:%S .%r', tt=tt, milliseconds=ms)
                    else:
                        srange = '%g s' % (tma-tmi)
                        message = mystrftime(fmt='Start: %Y-%m-%d %H:%M:%S .%r Length: '+srange, tt=tt, milliseconds=ms)
                else:
                    tt, ms = gmtime_x(mouse_t)
                
                    message = mystrftime(fmt=None,tt=tt,milliseconds=ms)
            else:
                message = self.message
                
            sb = self.window().statusBar()
            sb.clearMessage()
            sb.showMessage(message)
            
        def set_sortingmode_change_delay_time(self, dt):
            self.sortingmode_change_delay_time = dt
            
        def sortingmode_change_delayed(self):
            now = time.time()
            return (self.sortingmode_change_delay_time is not None and 
                now - self.sortingmode_change_time < self.sortingmode_change_delay_time)
           
        def set_visible_marker_kinds(self, kinds):
            self.deselect_all()
            self.visible_marker_kinds = tuple(kinds)

        def following(self):
            return self.follow_timer is not None and not self.following_interrupted()
       
        def interrupt_following(self):
            self.interactive_range_change_time = time.time()

        def following_interrupted(self, now=None):
            if now is None:
                now = time.time()
            return now - self.interactive_range_change_time < self.interactive_range_change_delay_time

        def follow(self, tlen, interval=50):
            self.show_all = False
            self.follow_time = tlen
            self.follow_timer = QTimer(self)
            self.connect( self.follow_timer, SIGNAL("timeout()"), self.follow_update ) 
            self.follow_timer.setInterval(interval)
            self.follow_timer.start()
            
        def follow_update(self):
            now = time.time()
            if self.following_interrupted(now):
                return
            self.set_time_range(now-self.follow_time, now)
            self.update()
     
        def myclose(self, return_tag=''):
            self.timer.stop()
            if self.follow_timer is not None:
                self.follow_timer.stop()
            self.window().close()
            
            for snuffling in list(self.snufflings):
                self.remove_snuffling( snuffling )

            self.return_tag = return_tag

        def set_error_message(self, key, value):
            if value is None:
                if key in self.error_messages:
                    del self.error_messages[key]
            else:
                self.error_messages[key] = value
        
        def inputline_changed(self, text):
            pass

        def inputline_finished(self, text):
            line = str(text)

            toks = line.split()
            clearit, hideit, error = False, True, None
            if len(toks) >= 1:
                command = toks[0].lower()
                try:
                    quick_filter_commands = { 'n': '%s.*.*.*', 's': '*.%s.*.*', 'l': '*.*.%s.*', 'c': '*.*.*.%s' }
                    if command in quick_filter_commands:
                        if len(toks) >= 2:
                            patterns = [ quick_filter_commands[toks[0]] % pat for pat in toks[1:]  ]
                            self.set_quick_filter_patterns(patterns, line)
                        else:
                            self.set_quick_filter_patterns(None)
                        
                        self.update()

                    elif command in ('hide', 'unhide'):
                        if len(toks) >= 2:
                            patterns = []
                            if len(toks) == 2:
                                patterns = [ toks[1] ]
                            elif len(toks) >= 3:
                                x = { 'n': '%s.*.*.*', 's': '*.%s.*.*', 'l': '*.*.%s.*', 'c': '*.*.*.%s' }
                                if toks[1] in x:
                                    patterns.extend( x[toks[1]] % tok for tok in toks[2:] )

                            for pattern in patterns:
                                if command == 'hide':
                                    self.add_blacklist_pattern( pattern )
                                else:
                                    self.remove_blacklist_pattern( pattern )
                        
                        elif command == 'unhide' and len(toks) == 1:
                            self.clear_blacklist()
                        
                        clearit = True
                        
                        self.update()
                
                    elif command == 'markers':
                        if len(toks) == 2:
                            if toks[1] == 'all':
                                kinds = self.all_marker_kinds
                            else:
                                kinds = []
                                for x in toks[1]:
                                    try:
                                        kinds.append(int(x))
                                    except:
                                        pass

                            self.set_visible_marker_kinds(kinds)

                        elif len(toks) == 1:
                            self.set_visible_marker_kinds(())

                        self.update()

                    elif command == 'scaling':
                        if len(toks) >= 3:
                            vmin, vmax = [ pyrocko.model.float_or_none(x) for x in toks[-2:] ]

                        def upd(d,k,vmin,vmax):
                            if k in d:
                                if vmin is not None:
                                    d[k] = vmin, d[k][1]
                                if vmax is not None:
                                    d[k] = d[k][0], vmax

                        if len(toks) == 1:
                            self.remove_scaling_hooks()

                        elif len(toks) == 3:
                            def hook(data_ranges):
                                for k in data_ranges:
                                    upd(data_ranges, k, vmin, vmax)

                            self.set_scaling_hook('_', hook)
                            
                        elif len(toks) == 4:
                            pattern = toks[1]
                            def hook(data_ranges):
                                for k in pyrocko.util.match_nslcs(pattern, data_ranges.keys()):
                                    upd(data_ranges, k, vmin, vmax)
                            
                            self.set_scaling_hook(pattern, hook)

                    elif command == 'goto':
                        toks2 = line.split(None, 1)
                        if len(toks2) == 2:
                            arg = toks2[1]
                            m = re.match(r'^\d\d\d\d-\d\d(-\d\d( \d\d(:\d\d(:\d\d(.\d+)?)?)?)?)?$', arg)
                            if m:
                                tlen = None
                                if not m.group(1):
                                    tlen = 32*24*60*60
                                elif not m.group(2):
                                    tlen = 24*60*60
                                elif not m.group(3):
                                    tlen = 60*60
                                elif not m.group(4):
                                    tlen = 60
                                    
                                supl = '1970-01-01 00:00:00'
                                if len(supl) > len(arg):
                                    arg = arg + supl[-(len(supl)-len(arg)):]
                                t = pyrocko.util.str_to_time(arg)
                                self.go_to_time(t, tlen=tlen)
                            
                            elif re.match(r'^\d\d:\d\d(:\d\d(.\d+)?)?$', arg):
                                supl = '00:00:00'
                                if len(supl) > len(arg):
                                    arg = arg + supl[-(len(supl)-len(arg)):]
                                tmin, tmax = self.get_time_range()
                                sdate = pyrocko.util.time_to_str(tmin/2.+tmax/2., format='%Y-%m-%d')
                                t = pyrocko.util.str_to_time(sdate + ' ' + arg)
                                self.go_to_time(t)

                            else:
                                self.go_to_event_by_name(arg)
                    
                    else:
                        raise PileViewerMainException('No such command: %s' % command)
                        
                except PileViewerMainException, e:
                    error = str(e)
                    hideit = False
                
            return clearit, hideit, error
        
    return PileViewerMain

PileViewerMain = MakePileViewerMainClass(QWidget)
GLPileViewerMain = MakePileViewerMainClass(QGLWidget)

class LineEditWithAbort(QLineEdit):

    def keyPressEvent(self, key_event):
        if key_event.key() == Qt.Key_Escape:
            self.emit( SIGNAL('aborted()') )
        else:
            return QLineEdit.keyPressEvent(self, key_event)

class PileViewer(QFrame):
    '''PileViewerMain + Controls + Inputline'''
    
    def __init__(self, pile, ntracks_shown_max=20, use_opengl=False, panel_parent=None, *args):
        apply(QFrame.__init__, (self,) + args)
        
        if use_opengl:
            self.viewer = GLPileViewerMain(pile, ntracks_shown_max=ntracks_shown_max, panel_parent=panel_parent)
        else:
            self.viewer = PileViewerMain(pile, ntracks_shown_max=ntracks_shown_max, panel_parent=panel_parent)
        
        layout = QGridLayout()
        self.setLayout( layout )
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        
        #self.setFrameShape(QFrame.StyledPanel)
        #self.setFrameShadow(QFrame.Sunken)

        self.input_area = QFrame(self)
        ia_layout = QGridLayout()
        ia_layout.setContentsMargins(11,11,11,11)
        self.input_area.setLayout(ia_layout)

        self.inputline = LineEditWithAbort(self.input_area)
        self.connect(self.inputline, SIGNAL('returnPressed()'), self.inputline_returnpressed)
        self.connect(self.inputline, SIGNAL('editingFinished()'), self.inputline_finished)
        self.connect(self.inputline, SIGNAL('aborted()'), self.inputline_aborted)
        self.connect(self.inputline, SIGNAL('textEdited(QString)'), self.inputline_changed)
        self.inputline.setFocusPolicy(Qt.ClickFocus)
        self.input_area.hide()
        
        self.inputline_error_str = None
        
        self.inputline_error = QLabel()
        self.inputline_error.hide()

        ia_layout.addWidget(self.inputline, 0, 0)
        ia_layout.addWidget(self.inputline_error, 1, 0)        
        layout.addWidget(self.input_area, 0,0,1,2)
        layout.addWidget( self.viewer, 1, 0 )

        pb = Progressbars(self)
        layout.addWidget(pb, 2,0,1,2)
        self.progressbars = pb
        
        scrollbar = QScrollBar(Qt.Vertical)
        self.scrollbar = scrollbar
        layout.addWidget( scrollbar, 1, 1 )
        self.connect(self.scrollbar, SIGNAL('valueChanged(int)'), self.scrollbar_changed)
        self.block_scrollbar_changes = False
        
        self.connect(self.viewer, SIGNAL('want_input()'), self.inputline_show)
        self.connect(self.viewer, SIGNAL('tracks_range_changed(int,int,int)'), self.tracks_range_changed)
        self.connect(self.viewer, SIGNAL('pile_has_changed_signal()'), self.adjust_controls)

    def get_progressbars(self):
        return self.progressbars

    def inputline_show(self):
        self.input_area.show()
        self.inputline.setFocus(Qt.OtherFocusReason)
        self.inputline.selectAll()
 
    def inputline_set_error(self, string):
        self.inputline_error_str = string
        self.inputline.setPalette( pyrocko.gui_util.get_err_palette() )
        self.inputline.selectAll()
        self.inputline_error.setText(string)
        self.input_area.show()
        self.inputline_error.show()
        
    def inputline_clear_error(self):
        if self.inputline_error_str:
            self.inputline.setPalette( QApplication.palette() )
            self.inputline_error_str = None
            self.inputline_error.clear()
            self.inputline_error.hide()
            
    def inputline_changed(self, line):
        self.viewer.inputline_changed(str(line))
        self.inputline_clear_error()
        
    def inputline_returnpressed(self):
        line = str(self.inputline.text())
        clearit, hideit, error = self.viewer.inputline_finished(line)

        if error:
            self.inputline_set_error(error)
        
        if clearit:
            self.inputline.blockSignals(True)
            qpat, qinp = self.viewer.get_quick_filter_patterns()
            if qpat is None:
                self.inputline.clear()
            else:
                self.inputline.setText(qinp)
            self.inputline.blockSignals(False)
        
        if hideit and not error:
            self.viewer.setFocus(Qt.OtherFocusReason) 
            self.input_area.hide()
       
    def inputline_aborted(self):
        self.viewer.setFocus(Qt.OtherFocusReason) 
        self.input_area.hide()

    def inputline_finished(self):
        pass

    def tracks_range_changed(self, ntracks, ilo, ihi):
        if self.block_scrollbar_changes:
            return
                
        self.scrollbar.blockSignals(True)
        self.scrollbar.setPageStep(ihi-ilo)
        vmax = max(0,ntracks-(ihi-ilo))
        self.scrollbar.setRange(0, vmax)
        self.scrollbar.setValue(ilo)
        self.scrollbar.setHidden(vmax == 0)
        self.scrollbar.blockSignals(False)

    def scrollbar_changed(self, value):
        self.block_scrollbar_changes = True
        ilo = value
        ihi = ilo + self.scrollbar.pageStep()
        self.viewer.set_tracks_range((ilo, ihi))
        self.block_scrollbar_changes = False
        self.update_contents()
        
    def controls(self):
        frame = QFrame(self)
        layout = QGridLayout()
        frame.setLayout(layout)

        minfreq = 0.001
        maxfreq = 1000.0
        self.lowpass_control = ValControl(high_is_none=True)
        self.lowpass_control.setup('Lowpass [Hz]:', minfreq, maxfreq, maxfreq, 0)
        self.highpass_control = ValControl(low_is_none=True)
        self.highpass_control.setup('Highpass [Hz]:', minfreq, maxfreq, minfreq, 1)
        self.gain_control = ValControl()
        self.gain_control.setup('Gain:', 0.001, 1000., 1., 2)
        self.rot_control = LinValControl()
        self.rot_control.setup('Rotate [deg]:', -180., 180., 0., 3)
        self.connect( self.lowpass_control, SIGNAL("valchange(PyQt_PyObject,int)"), self.viewer.lowpass_change )
        self.connect( self.highpass_control, SIGNAL("valchange(PyQt_PyObject,int)"), self.viewer.highpass_change )
        self.connect( self.gain_control, SIGNAL("valchange(PyQt_PyObject,int)"), self.viewer.gain_change )
        self.connect( self.rot_control, SIGNAL("valchange(PyQt_PyObject,int)"), self.viewer.rot_change )
       
        for icontrol, control in enumerate((self.highpass_control, self.lowpass_control, self.gain_control, self.rot_control)):
            for iwidget, widget in enumerate(control.widgets()):
                layout.addWidget( widget, icontrol, iwidget )
        
        spacer = QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addItem(spacer, 4,0, 1, 3)

        self.adjust_controls()
        return frame

    def adjust_controls(self):
        dtmin, dtmax = self.viewer.content_deltat_range()
        maxfreq = 0.5/dtmin
        minfreq = (0.5/dtmax)*0.001
        self.lowpass_control.set_range(minfreq, maxfreq)
        self.highpass_control.set_range(minfreq, maxfreq)
   
    def setup_snufflings(self):
        self.viewer.setup_snufflings()

    def get_view(self):
        return self.viewer
    
    def update_contents(self):
        self.viewer.update()
    
    def get_pile(self):
        return self.viewer.get_pile()

