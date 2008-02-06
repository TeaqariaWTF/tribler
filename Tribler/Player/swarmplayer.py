#!/usr/bin/python
# Written by Arno Bakker, Choopan RATTANAPOKA, Jie Yang
# see LICENSE.txt for license information
#

import os
import sys
import time
import commands
import tempfile
import urllib2
from threading import enumerate,currentThread,RLock
from traceback import print_exc
from systray import PlayerTaskBarIcon

if sys.platform == "darwin":
    # on Mac, we can only load VLC/OpenSSL libraries
    # relative to the location of tribler.py
    os.chdir(os.path.abspath(os.path.dirname(sys.argv[0])))
import wx
from wx import xrc
#import hotshot

from Tribler.Core.API import *
from Tribler.Core.Utilities.unicode import bin2unicode
from Tribler.Policies.RateManager import UserDefinedMaxAlwaysOtherwiseEquallyDividedRateManager

from Tribler.Video.EmbeddedPlayer import VideoFrame
from Tribler.Video.VideoServer import VideoHTTPServer
from Tribler.Video.VideoPlayer import VideoPlayer, VideoChooser, PLAYBACKMODE_INTERNAL
from Tribler.Utilities.Instance2Instance import *

from Tribler.Main.Utility.utility import Utility # TO REMOVE

DEBUG = True
ALLOW_MULTIPLE = False
RATELIMITADSL = False

DISKSPACE_LIMIT = 5L * 1024L * 1024L * 1024L  # 5 GB
I2I_LISTENPORT = 57894

closing = False

class PlayerFrame(VideoFrame):

    def __init__(self,parent):
        VideoFrame.__init__(self,parent,title='SwarmPlayer 0.0.6')
        
        self.Bind(wx.EVT_CLOSE, self.OnCloseWindow)
    
    def OnCloseWindow(self, event = None):
        global closing
        closing = True
        
        self.set_wxclosing()
        
        if event is not None:
            nr = event.GetEventType()
            lookup = { wx.EVT_CLOSE.evtType[0]: "EVT_CLOSE", wx.EVT_QUERY_END_SESSION.evtType[0]: "EVT_QUERY_END_SESSION", wx.EVT_END_SESSION.evtType[0]: "EVT_END_SESSION" }
            if nr in lookup: nr = lookup[nr]
            print "Closing due to event ",nr
            print >>sys.stderr,"Closing due to event ",nr
            event.Skip()
        else:
            print "Closing untriggered by event"
    
        

class PlayerApp(wx.App):
    def __init__(self, x, params, single_instance_checker, installdir):
        self.params = params
        self.single_instance_checker = single_instance_checker
        self.installdir = installdir
        self.error = None
        self.s = None
        self.dlock = RLock()
        self.d = None # protected by dlock
        self.playermode = DLSTATUS_DOWNLOADING # protected by dlock
        self.said_start_playback = False
        
        
        wx.App.__init__(self, x)
        
    def OnInit(self):
        try:
            self.utility = Utility(self.installdir)
            self.utility.app = self
            print self.utility.lang.get('build')
            
            # Start server for instance2instance communication
            self.i2is = Instance2InstanceServer(I2I_LISTENPORT,self.i2icallback) 
            self.i2is.start()

            # Install systray icon
            # Note: setting this makes the program not exit when the videoFrame
            # is being closed.
            iconpath = os.path.join(self.installdir,'Tribler','Images','tribler.ico')
            self.tbicon = PlayerTaskBarIcon(self,iconpath)
            
            # Start video frame
            self.videoFrame = PlayerFrame(self)
            
            # Start HTTP server for serving video to player widget
            self.videoserv = VideoHTTPServer.getInstance() # create
            self.videoserv.background_serve()
            self.videoserv.register(self.videoserver_error_callback,self.videoserver_set_status_callback)

            # Fire up the player widget
            self.videoplay = VideoPlayer.getInstance()
            self.videoplay.register(self.utility)
            self.videoplay.set_parentwindow(self.videoFrame)
            # h4xor TEMP ARNO
            self.videoplay.playbackmode = PLAYBACKMODE_INTERNAL
            
            # Start Tribler Session
            state_dir = Session.get_default_state_dir('.SwarmPlayer')
            cfgfilename = Session.get_default_config_filename(state_dir)
            
            print >>sys.stderr,"main: Session config",cfgfilename
            try:
                self.sconfig = SessionStartupConfig.load(cfgfilename)
            except:
                print_exc()
                self.sconfig = SessionStartupConfig()
                self.sconfig.set_state_dir(state_dir)
                
            self.sconfig.set_overlay(False)
            self.sconfig.set_megacache(False)
            self.s = Session(self.sconfig)
            self.s.set_download_states_callback(self.sesscb_states_callback)

            if RATELIMITADSL:
                self.count = 0
                self.r = UserDefinedMaxAlwaysOtherwiseEquallyDividedRateManager()
                self.r.set_global_max_speed(DOWNLOAD,400)
                self.r.set_global_max_speed(UPLOAD,90)
                self.s.set_download_states_callback(self.ratelimit_callback,getpeerlist=False)
            
            # Load torrent
            if self.params[0] != "":
                torrentfilename = self.params[0]
            else:
                torrentfilename = self.select_torrent_from_disk()
                if torrentfilename is None:
                    print >>sys.stderr,"main: User selected no file"
                    self.OnExit()
                    return False

            # Arno: For extra robustness, ignore any errors related to restarting
            try:
                # Load all other downloads in cache, but in STOPPED state
                self.s.load_checkpoint(initialdlstatus=DLSTATUS_STOPPED)
            except:
                print_exc()

            # Start download
            if not self.start_download(torrentfilename):
                self.OnExit()
                return False
            
            self.Bind(wx.EVT_CLOSE, self.videoFrame.OnCloseWindow)
            self.Bind(wx.EVT_QUERY_END_SESSION, self.videoFrame.OnCloseWindow)
            self.Bind(wx.EVT_END_SESSION, self.videoFrame.OnCloseWindow)

            self.videoFrame.Show(True)
            
        except Exception,e:
            print_exc()
            self.show_error(str(e))
            self.OnExit()
            return False
        return True


    def select_torrent_from_disk(self):
        dlg = wx.FileDialog(self.videoFrame, 
                            'SwarmPlayer: Select torrent to play', 
                            '', # default dir
                            '', # default file
                            'TSTREAM and TORRENT files (*.tstream;*.torrent)|*.tstream;*.torrent', 
                            wx.OPEN|wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
        else:
            filename = None
        dlg.Destroy()
        return filename

    def ask_user_to_select_video(self,videofiles):
        dlg = VideoChooser(self.videoFrame,self.utility,videofiles,title='SwarmPlayer',expl='Select which file to play')
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            index = dlg.getChosenIndex()
            filename = videofiles[index]
        else:
            filename = None
        dlg.Destroy()
        return filename


    def start_download(self,torrentfilename):
        
        # What if DL already running?
        self.dlock.acquire()
        try:
            if self.d is not None:
                self.videoplay.stop_playback()
                self.d.stop()
        finally:
            self.dlock.release()
        
        tdef = TorrentDef.load(torrentfilename)
        print >>sys.stderr,"main: infohash is",`tdef.get_infohash()`
        
        # Select which video to play (if multiple)
        videofiles = tdef.get_video_files()
        print >>sys.stderr,"main: Found video files",videofiles
        
        if len(videofiles) == 0:
            print >>sys.stderr,"main: No video files found! Let user select"
            # Let user choose any file
            videofiles = tdef.get_video_files(videoexts=None)
            
        if len(videofiles) > 1:
            selectedvideofile = self.ask_user_to_select_video(videofiles)
            if selectedvideofile is None:
                print >>sys.stderr,"main: User selected no video"
                return False
            dlfile = selectedvideofile
        else:
            dlfile = videofiles[0]
        
        # Free diskspace, if needed
        destdir = os.path.join(self.s.get_state_dir(),'downloads')
        if not os.access(destdir,os.F_OK):
            os.mkdir(destdir)

        # Arno: For extra robustness, ignore any errors related to restarting
        try:
            if not self.free_up_diskspace_by_downloads(tdef.get_infohash(),tdef.get_length([dlfile])):
                print >>sys.stderr,"main: Not enough free diskspace, ignoring"
                #return False
                pass # Let it slide
        except:
            print_exc()
        
        # Setup how to download
        dcfg = DownloadStartupConfig()
        dcfg.set_video_start_callback(self.vod_ready_callback)
        dcfg.set_dest_dir(destdir)
        
        if tdef.is_multifile_torrent():
            dcfg.set_selected_files([dlfile])
        
        dcfg.set_max_conns_to_initiate(300)
        dcfg.set_max_conns(300)
        
        # Start download
        dlist = self.s.get_downloads()
        infohash = tdef.get_infohash()
        
        newd = None
        for d in dlist:
            if d.get_def().get_infohash() == infohash:
                # Download already exists.
                # One safe option is to remove it (but not its downloaded content)
                # so we can start with a fresh DownloadStartupConfig. However,
                # this gives funky concurrency errors and could prevent a
                # Download from starting without hashchecking (as its checkpoint
                # was removed) 
                # Alternative is to set VOD callback, etc. at Runtime:
                print >>sys.stderr,"main: Reusing old duplicate Download",`infohash`
                d.set_video_start_callback(self.vod_ready_callback)
                d.restart()
                newd = d
                #self.s.remove_download(d,removecontent=False)
                break
        
        if newd is None:
            newd = self.s.start_download(tdef,dcfg)
            
        self.dlock.acquire()
        self.d = newd
        self.dlock.release()

        print >>sys.stderr,"main: Saving content to",self.d.get_dest_files()

        cname = tdef.get_name_as_unicode()
        if len(videofiles) > 1:
            cname += u' - '+bin2unicode(dlfile)
        self.videoplay.set_content_name(cname)

        return True

    def i2icallback(self,cmd,param):
        """ Called by Instance2Instance thread """
        
        print >>sys.stderr,"main: Another instance called us with cmd",cmd,"param",param
        
        if cmd == 'START':
            torrentfilename = None
            if param.startswith('http:'):
                # Retrieve from web 
                f = tempfile.NamedTemporaryFile()
                n = urllib2.urlopen(url)
                data = n.read()
                f.write(data)
                f.close()
                n.close()
                torrentfilename = f.name
            else:
                torrentfilename = param
                
            # Switch to GUI thread
            start_download_lambda = lambda:self.start_download(torrentfilename)
            wx.CallAfter(start_download_lambda)

    def videoserver_error_callback(self,e,url):
        """ Called by HTTP serving thread """
        wx.CallAfter(self.videoserver_error_guicallback,e,url)
        
    def videoserver_error_guicallback(self,e,url):
        print >>sys.stderr,"main: Video server reported error",str(e)
        #global closing
        #if not closing:
        #    self.show_error(str(e))
        pass

    def videoserver_set_status_callback(self,status):
        global closing
        if not closing:
            self.videoFrame.set_player_status(status)
            
    
    def free_up_diskspace_by_downloads(self,infohash,needed):
        
        print >> sys.stderr,"main: free_up: needed",needed,DISKSPACE_LIMIT
        if needed > DISKSPACE_LIMIT:
            # Not cleaning out whole cache for bigguns
            print >> sys.stderr,"main: free_up: No cleanup for bigguns"
            return True 
        
        inuse = 0L
        timelist = []
        dlist = self.s.get_downloads()
        for d in dlist:
            hisinfohash = d.get_def().get_infohash()
            if infohash == hisinfohash:
                # Don't delete the torrent we want to play
                continue
            destfiles = d.get_dest_files()
            print >> sys.stderr,"main: free_up: Downloaded content",`destfiles`
            
            dinuse = 0L
            for (filename,savepath) in destfiles:
                stat = os.stat(savepath)
                dinuse += stat.st_size
            inuse += dinuse
            timerec = (stat.st_ctime,dinuse,d)
            timelist.append(timerec)
            
        if inuse+needed < DISKSPACE_LIMIT:
            # Enough available, done.
            print >> sys.stderr,"main: free_up: Enough avail",inuse
            return True
        
        # Policy: remove oldest till sufficient
        timelist.sort()
        print >> sys.stderr,"main: free_up: Found",timelist,"in dest dir"
        
        got = 0L
        for ctime,dinuse,d in timelist:
            print >> sys.stderr,"main: free_up: Removing",`d.get_def().get_name_as_unicode()`,"to free up diskspace, t",ctime
            self.s.remove_download(d,removecontent=True)
            got += dinuse
            if got > needed:
                return True
        # Deleted all, still no space:
        return False
        
        
    def show_error(self,msg):
        dlg = wx.MessageDialog(None, msg, "SwarmPlayer Error", wx.OK|wx.ICON_ERROR)
        result = dlg.ShowModal()
        dlg.Destroy()
        
    def OnExit(self):
        print >>sys.stderr,"main: ONEXIT"

        # To let Threads in Session finish their business before we shut it down.
        time.sleep(1) 
        
        if self.s is not None:
            self.s.shutdown()
        
        if self.tbicon is not None:
            self.tbicon.RemoveIcon()
            self.tbicon.Destroy()

        ts = enumerate()
        for t in ts:
            print >>sys.stderr,"main: ONEXIT: Thread still running",t.getName(),"daemon",t.isDaemon()
        
        if not ALLOW_MULTIPLE:
            del self.single_instance_checker
        ## TODO ClientPassParam("Close Connection")
        self.ExitMainLoop()


    def sesscb_states_callback(self,dslist):
        """ Called by Session thread """

        print >>sys.stderr,"main: Stats",`dslist`
        
        # See which Download is currently playing
        self.dlock.acquire()
        playermode = self.playermode
        d = self.d
        self.dlock.release()
        
        if playermode == DLSTATUS_SEEDING:
            for ds in dslist:
                print >>sys.stderr,"main: Stats: Seeding:",dlstatus_strings[ds.get_status()],ds.get_progress(),"%",ds.get_error()
            return (1.0,False)
        
        ds = None
        for ds2 in dslist:
            if ds2.get_download() == d:
                ds = ds2
            else:
                print >>sys.stderr,"main: Stats: Waiting:",dlstatus_strings[ds2.get_status()],ds2.get_progress(),"%",ds2.get_error()
                
        if ds is None:
            return (1.0,False)
        
        print >>sys.stderr,"main: Stats: DL:",dlstatus_strings[ds.get_status()],ds.get_progress(),"%",ds.get_error()
        
        global closing
        if closing:
            return (-1,False)

        # Display stats for currently playing Download
        logmsgs = ds.get_log_messages()
        if len(logmsgs) > 0:
            print >>sys.stderr,"main: Log",logmsgs[0]
        progress = ds.get_vod_prebuffering_progress()
        playable = ds.get_vod_playable()
        t = ds.get_vod_playable_after()
        print >>sys.stderr,"main: ETA is",t,"secs"
        if t > float(2 ** 30):
            intime = "inf"
        elif t == 0.0:
            intime = "now"
        else:
            h, t = divmod(t, 60.0*60.0)
            m, s = divmod(t, 60.0)
            if h == 0.0:
                if m == 0.0:
                    intime = "%ds" % (s)
                else:
                    intime = "%dm:%02ds" % (m,s)
            else:
                intime = "%dh:%02dm:%02ds" % (h,m,s)
                
        #print >>sys.stderr,"main: VODStats",progress,playable

        if ds.get_status() == DLSTATUS_HASHCHECKING:
            genprogress = ds.get_progress()
            pstr = str(int(genprogress*100))
            msg = "Checking already downloaded parts "+pstr+"% done"
        elif ds.get_status() == DLSTATUS_STOPPED_ON_ERROR:
            msg = 'Error playing: '+str(ds.get_error())
        elif ds.get_status() == DLSTATUS_SEEDING:
            npeerstr = str(ds.get_num_peers())
            msg = u"Helping "+npeerstr+" people to enjoy "+d.get_def().get_name_as_unicode()+". Please don't close the SwarmPlayer completely"

            # As we're seeding we can now restart any previous downloads to 
            # seed them.
            # Arno: For extra robustness, ignore any errors related to restarting
            wx.CallAfter(self.restart_other_downloads)
            
        elif progress != 1.0:
            pstr = str(int(progress*100))
            npeerstr = str(ds.get_num_peers())
            msg = "Prebuffering "+pstr+"% done, eta "+intime+'  (connected to '+npeerstr+' people)'
        elif playable:
            if not self.said_start_playback:
                msg = "Starting playback..."
                self.said_start_playback = True
            else:
                msg = ''
        else:
            msg = "Waiting for sufficient download speed... "+intime
        self.videoFrame.set_player_status(msg)
        
        if False: # Only works if the current method returns (x,True)
            peerlist = ds.get_peerlist()
            print >>sys.stderr,"main: Connected to",len(peerlist),"peers"
            for peer in peerlist:
                print >>sys.stderr,"main: Connected to",peer['ip'],peer['completed']
        
        return (1.0,False)
    
    def vod_ready_callback(self,d,mimetype,stream,filename):
        """ Called by Session thread """
        print >>sys.stderr,"main: VOD ready callback called",currentThread().getName(),"###########################################################",mimetype
    
        if filename:
            func = lambda:self.play_from_file(filename)
            wx.CallAfter(func)
        else:
            # HACK: TODO: make to work with file-like interface
            videoserv = VideoHTTPServer.getInstance()
            videoserv.set_movietransport(stream.mt)
            wx.CallAfter(self.play_from_stream)

    def play_from_stream(self):
        """ Called by MainThread """
        print >>sys.stderr,"main: Playing from stream"
        self.videoplay.play_url('http://127.0.0.1:6880/')
    
    def play_from_file(self,filename):
        """ Called by MainThread """
        print >>sys.stderr,"main: Playing from file",filename
        self.videoplay.play_url(filename)

    def ratelimit_callback(self,dslist):
        adjustspeeds = False
        if self.count % 4 == 0:
            adjustspeeds = True
        self.count += 1
        
        if not adjustspeeds:
            return (1.0,False)
        
        for ds in dslist:
            d = ds.get_download()
            complete = ds.get_pieces_complete()
            print >>sys.stderr,"main: Pieces completed",`d.get_def().get_name()`,"len",len(complete)
            
            if adjustspeeds:
                self.r.add_downloadstate(ds)
            
        if adjustspeeds:
            self.r.adjust_speeds()
        return (1.0,False)

    def restart_other_downloads(self):
        """ Called by GUI thread """
        self.dlock.acquire()
        self.playermode = DLSTATUS_SEEDING
        self.dlock.release()

        dlist = self.s.get_downloads()
        for d in dlist:
            d.restart() # checkpointed torrents always restarted in DLMODE_NORMAL
            
    
class DummySingleInstanceChecker:
    
    def __init__(self,basename):
        pass

    def IsAnotherRunning(self):
        "Uses pgrep to find other tribler.py processes"
        # If no pgrep available, it will always start tribler
        progressInfo = commands.getoutput('pgrep -fl tribler.py | grep -v pgrep')
        numProcesses = len(progressInfo.split('\n'))
        if DEBUG:
            print 'ProgressInfo: %s, num: %d' % (progressInfo, numProcesses)
        return numProcesses > 1
                
        
##############################################################
#
# Main Program Start Here
#
##############################################################
def run(params = None):
    if params is None:
        params = [""]
    
    if len(sys.argv) > 1:
        params = sys.argv[1:]
    
    # Create single instance semaphore
    # Arno: On Linux and wxPython-2.8.1.1 the SingleInstanceChecker appears
    # to mess up stderr, i.e., I get IOErrors when writing to it via print_exc()
    #
    # TEMPORARILY DISABLED on Linux
    if sys.platform != 'linux2':
        single_instance_checker = wx.SingleInstanceChecker("tribler-" + wx.GetUserId())
    else:
        single_instance_checker = DummySingleInstanceChecker("tribler-")

    #print "[StartUpDebug]---------------- 1", time()-start_time
    if not ALLOW_MULTIPLE and single_instance_checker.IsAnotherRunning():
        if params[0] != "":
            torrentfilename = params[0]
            i2ic = Instance2InstanceClient(I2I_LISTENPORT,'START',torrentfilename)
    else:
        arg0 = sys.argv[0].lower()
        if arg0.endswith('.exe'):
            installdir = os.path.abspath(os.path.dirname(sys.argv[0]))
        else:
            installdir = os.getcwd()  

        # Launch first abc single instance
        app = PlayerApp(0, params, single_instance_checker, installdir)
        app.MainLoop()
        
        print "Sleeping seconds to let other threads finish"
        time.sleep(2)

if __name__ == '__main__':
    run()

