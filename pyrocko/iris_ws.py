import urllib, urllib2, logging, re
import util, model, pz

from xml.parsers.expat import ParserCreate

logger = logging.getLogger('pyrocko.iris_ws')

base_url = 'http://www.iris.edu/ws'


def tdate(s):
    return util.str_to_time(s, '%Y-%m-%d')

def sdate(t):
    return util.time_to_str(t, '%Y-%m-%d')

def tdatetime(s):
    return util.str_to_time(s, format='%Y-%m-%dT%H:%M:%S')

def sdatetime(t):
    return util.time_to_str(t, format='%Y-%m-%dT%H:%M:%S')

class Element(object):
    
    def __init__(self, name, depth, attrs): 
        self.name = name
        self.depth = depth
        self.attrs = attrs

    def __getattr__(self,k):
        return self.attrs[k]
    
    def __str__(self):
        return '%s:\n ' % self.name + '\n '.join( '%s : %s' % (k,v) for (k,v) in self.attrs.iteritems() )

class XMLZipHandler(object):
    
    def __init__(self, watch):
        self.watch = watch
        self.stack = []
        self.wstack = []
        self.outstack = []

    def startElement(self, name, attrs):
        self.stack.append((name, []))
        if len(self.wstack) < len(self.watch) and name == self.watch[len(self.wstack)]:
            el = Element(name, len(self.stack), dict(attrs.items()))
            self.wstack.append(el)

    def characters(self, content):
        if self.wstack and len(self.stack) == self.wstack[-1].depth + 1:
            if content.strip():
                self.stack[-1][1].append(content)

    def endElement(self, name):
        if self.wstack:
            if len(self.stack) == self.wstack[-1].depth + 1 and self.stack[-1][1]:
                self.wstack[-1].attrs[name] = ''.join(self.stack[-1][1])

            if name == self.watch[len(self.wstack)-1]:
                if len(self.wstack) == len(self.watch):
                    self.outstack.append(list(self.wstack))

                self.wstack.pop()

        self.stack.pop()

    def getQueuedElements(self):
        outstack = self.outstack
        self.outstack = []
        return outstack

def xmlzip(source, watch, bufsize=10000):
    parser = ParserCreate()
    handler = XMLZipHandler(watch)

    parser.StartElementHandler = handler.startElement
    parser.EndElementHandler = handler.endElement
    parser.CharacterDataHandler = handler.characters

    while True:
        data = source.read(bufsize)
        if not data:
            break

        parser.Parse(data, False)
        for elements in handler.getQueuedElements():
            yield elements

    parser.Parse('', True)
    for elements in handler.getQueuedElements():
        yield elements

class NotFound(Exception):
    def __init__(self, url):
        Exception.__init__(self)
        self._url = url
    
    def __str__(self):
        return 'No results for request %s' % self._url

def ws_request(url, post=False, **kwargs):
    url_values = urllib.urlencode(kwargs)
    url = url + '?' + url_values
    logger.debug('Accessing URL %s' % url)

    req = urllib2.Request(url)
    if post:
        req.add_data(post)

    req.add_header('Accept', '*/*')

    try:
        return urllib2.urlopen(req)

    except urllib2.HTTPError, e:
        if e.code == 404:
            raise NotFound(url)
        else:
            raise e 

def ws_station( **kwargs ):
    
    for k in 'startbefore', 'startafter', 'endbefore', 'endafter':
        if k in kwargs:
            kwargs[k] = sdate(kwargs[k])

    if 'timewindow' in kwargs:
        tmin, tmax = kwargs.pop('timewindow')
        kwargs['startbefore'] = sdate(tmin)
        kwargs['endafter'] = sdate(tmax)

    return ws_request(base_url + '/station/query', **kwargs)

def ws_virtualnetwork( **kwargs ):
    
    for k in 'starttime', 'endtime':
        if k in kwargs:
            kwargs[k] = sdate(kwargs[k])

    if 'timewindow' in kwargs:
        tmin, tmax = kwargs.pop('timewindow')
        kwargs['starttime'] = sdate(tmin)
        kwargs['endtime'] = sdate(tmax)

    return ws_request(base_url + '/virtualnetwork/query', **kwargs)

def ws_bulkdataselect( selection, quality=None, minimumlength=None, longestonly=False ):

    l = []
    if quality is not None:
        l.append('quality %s' % quality)
    if minimumlength is not None:
        l.append('minimumlength %s' % minimumlength)
    if longestonly:
        l.append('longestonly')

    for (network, station, location, channel, tmin, tmax) in selection:
        if location == '':
            location = '--'
        
        l.append(' '.join((network, station, location, channel, sdatetime(tmin), sdatetime(tmax))))
    
    return ws_request(base_url + '/bulkdataselect/query', post='\n'.join(l))

def ws_sacpz(network=None, station=None, location=None, channel=None, time=None, tmin=None, tmax=None):
    d = {}
    if network:
        d['network'] = network
    if station:
        d['station'] = station
    if location:
        d['location'] = location
    else:
        d['location'] = '--'
    if channel:
        d['channel'] = channel
    
    if tmin is not None and tmax is not None:
        d['starttime'] = sdatetime(tmin)
        d['endtime'] = sdatetime(tmax)
    elif time is not None:
        d['time'] = sdatetime(time)
    times = (tmin, tmax)
    
    return ws_request(base_url + '/sacpz/query', **d)

def ws_resp(network=None, station=None, location=None, channel=None, time=None, tmin=None, tmax=None):
    d = {}
    if network:
        d['network'] = network
    if station:
        d['station'] = station
    if location:
        d['location'] = location
    else:
        d['location'] = '--'
    if channel:
        d['channel'] = channel
    
    if tmin is not None and tmax is not None:
        d['starttime'] = sdatetime(tmin)
        d['endtime'] = sdatetime(tmax)
    elif time is not None:
        d['time'] = sdatetime(time)
        
    return ws_request(base_url + '/resp/query', **d)

class ChannelInfo:
    def __init__(self, network, station, location, channel, start, end, azimuth, dip, elevation, depth, latitude, longitude, sample, input, output, zpk):
        self.network = network
        self.station = station
        self.location = location
        self.channel = channel
        self.start = start
        self.end = end
        self.azimuth = azimuth
        self.dip = dip
        self.elevation = elevation
        self.depth = depth
        self.latitude = latitude
        self.longitude = longitude
        self.sample = sample
        self.input = input
        self.output = output
        self.zpk = zpk

    def __str__(self):
        return '%s.%s.%s.%s' % (self.network, self.station, self.location, self.channel)

def nslc(x):
    return x.network, x.station, x.location, x.channel

def grok_sacpz(data):
    pzlines = []
    d = {}
    responses = []
    float_keys = ('latitude', 'longitude', 'elevation', 'depth', 'dip', 'azimuth', 'sample')
    string_keys = ('input', 'output', 'network', 'station', 'location', 'channel')
    time_keys = ('start', 'end')
    for line in data.splitlines():
        line = line.strip()
        if line.startswith('*'):
            if pzlines:
                if any(pzlines):
                    d['zpk'] = pz.read_sac_zpk(string='\n'.join(pzlines))
                    responses.append(d)
                d = {}
                pzlines = []

            m = re.match(r'^\* ([A-Z]+)[^:]*:(.*)$', line)
            if m:
                k,v = m.group(1).lower(), m.group(2).strip()
                if k in d:
                    assert False, 'duplicate entry? %s' % k

                if k in float_keys:
                    d[k] = float(v)
                elif k in string_keys:
                    d[k] = v
                elif k in time_keys:
                    d[k] = tdatetime(v)

        else:
            pzlines.append(line)

    if pzlines and any(pzlines):
        d['zpk'] = pz.read_sac_zpk(string='\n'.join(pzlines))
        responses.append(d)

    cis = {}
    for kwargs in responses:
        try:
            for k in float_keys + string_keys + time_keys:
                if k not in kwargs:
                    logger.error('Missing entry: %s' % k)
                    raise Exception()

            ci = ChannelInfo(**kwargs)

            cis[nslc(ci)] = ci
            
        except:
            logger.error('Error while parsing SACPZ data')

    return cis

def grok_station_xml( data, tmin, tmax ):
    
    stations = {}
    station_channels = {}

    for (sta, sta_epo, cha, cha_epo) in xmlzip(data, ('Station', 'StationEpoch', 'Channel', 'Epoch')):

        sta_beg, sta_end, cha_beg, cha_end = [ tdatetime(x) for x in 
                (sta_epo.StartDate, sta_epo.EndDate, cha_epo.StartDate, cha_epo.EndDate) ]

        if not (sta_beg <= tmin and tmax <= sta_end and cha_beg <= tmin and tmax <= cha_end):
            continue

        nslc = tuple([ str(x.strip()) for x in 
                (sta.net_code, sta.sta_code, cha.loc_code, cha.chan_code) ])

        lat, lon, ele, dep, azi, dip = [ float(cha_epo.attrs[x]) for x in 'Lat Lon Elevation Depth Azimuth Dip'.split() ]

        nsl = nslc[:3]
        if nsl not in stations:
            stations[nsl] = model.Station(nsl[0], nsl[1], nsl[2], lat, lon, ele, dep)
        
        stations[nsl].add_channel(model.Channel(nslc[-1], azi, dip))

    return stations.values()


def grok_virtualnet_xml(data):
    net_sta = set()

    for network, station in xmlzip(data, ('network', 'station')):
        net_sta.add((network.code, station.code))
   
    return net_sta

def data_selection(stations, tmin, tmax, channel_prio=[[ 'BHZ', 'HHZ' ],
            [ 'BH1', 'BHN', 'HH1', 'HHN' ], ['BH2', 'BHE', 'HH2', 'HHE']]):

    selection = []
    for station in stations:
        wanted = []
        for group in channel_prio:
            gchannels = []
            for channel in station.get_channels():
                if channel.name in group:
                    gchannels.append(channel)
            if gchannels:
                gchannels.sort(lambda a,b: cmp(group.index(a.name), group.index(b.name)) )
                wanted.append(gchannels[0])

        if wanted:
            for channel in wanted:
                selection.append((station.network, station.station, station.location, channel.name, tmin, tmax))

    return selection

