#!/usr/bin/env python3
#---------------------------------------------------------------
# FoLiA Document Server
#   by Maarten van Gompel
#   Centre for Language & Speech Technology, Radboud University Nijmegen
#   & KNAW Humanities Cluster
#   http://proycon.github.io/folia
#   http://github.com/proycon/foliadocserve
#   proycon AT anaproy DOT nl
#
# The FoLiA Document Server is a backend HTTP service to interact with
# documents in the FoLiA format, a rich XML-based format for linguistic
# annotation (http://proycon.github.io/folia). It provides an interface to
# efficiently edit FoLiA documents through the FoLiA Query Language (FQL).
#
#   Licensed under GPLv3
#
#----------------------------------------------------------------

#pylint: disable=too-many-nested-blocks, attribute-defined-outside-init

from __future__ import print_function, unicode_literals, division, absolute_import
import argparse
import time
import os
import json
import subprocess
import sys
import traceback
import threading
import datetime
import shutil
import queue
import re
from collections import defaultdict
from socket import getfqdn
import cherrypy
from jinja2 import Environment, FileSystemLoader
from folia import fql
import folia.main as folia
from pynlpl.formats import cql
from foliadocserve.flat import parseresults, getflatargs
from foliadocserve.test import test
from foliatools.foliatextcontent import cleanredundancy
from foliatools.foliaupgrade import upgrade
from foliatools import VERSION as FOLIATOOLSVERSION

syspath = os.path.dirname(os.path.realpath(__file__))
env = Environment(loader=FileSystemLoader(syspath + '/templates'))

def fake_wait_for_occupied_port(host, port): return

class NoSuchDocument(Exception):
    pass


VERSION = "0.7.6"
PROCESSOR_FOLIADOCSERVE = "PROCESSOR name \"foliadocserve\" version \"" + VERSION + "\" host \"" +getfqdn() + "\" folia_version \"" + folia.FOLIAVERSION + "\" src \"https://github.com/proycon/foliadocserve\""

logfile = None
def log(msg):
    if logfile:
        logfile.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " - " +  msg+"\n")
        logfile.flush()


def parsegitlog(data):
    commit = None
    date = None
    msg = None
    for line in data.split("\n"):
        line = line.strip()
        if line[0:6] == 'commit':
            #yield previous
            if commit and date and msg:
                yield commit, date, msg
            commit = line[7:]
            msg = None
            date = None
        elif line[0:7] == 'Author:':
            pass
        elif line[0:5] == 'Date:':
            date = line[6:].strip()
        elif line:
            msg = line
    if commit and date and msg:
        yield commit, date, msg



def cleantextredundancy(element):
    if not isinstance(element, folia.AbstractSpanAnnotation): #prevent infinite recursion
        for e in element:
            if isinstance(e, folia.AbstractElement):
                cleantextredundancy(e)
        if element.PRINTABLE:
            if isinstance(element,folia.AbstractStructureElement):
                for cls in element.doc.textclasses:
                    cleanredundancy(element, cls)

class BackgroundTaskQueue(cherrypy.process.plugins.SimplePlugin):
    """For background tasks that need not tie-up the request process"""

    thread = None
    def __init__(self, bus, qsize=100, qwait=2, safe_stop=True):
        cherrypy.process.plugins.SimplePlugin.__init__(self, bus)
        self.q = queue.Queue(qsize)
        self.qwait = qwait
        self.safe_stop = safe_stop

    def start(self):
        self.running = True
        if not self.thread:
            self.thread = threading.Thread(target=self.run)
            self.thread.start()

    def stop(self):
        self.bus.log("Stopping background task queue")
        if self.safe_stop:
            self.running = "draining"
        else:
            self.running = False

        if self.thread:
            self.thread.join()
            self.thread = None
        self.running = False

    def run(self):
        while self.running:
            try:
                try:
                    func, args, kwargs = self.q.get(block=True, timeout=self.qwait)
                except queue.Empty:
                    if self.running == "draining":
                        self.bus.log("Background queue drained succesfully")
                        return
                    continue
                else:
                    func(*args, **kwargs)
                    if hasattr(self.q, 'task_done'):
                        self.q.task_done()
            except:
                self.bus.log("Error in BackgroundTaskQueue %r." % self, level=40, traceback=True)

    def put(self, func, *args, **kwargs):
        """Schedule the given func to be run."""
        self.q.put((func, args, kwargs))

class AutoUnloader(cherrypy.process.plugins.SimplePlugin):
    """Calls docstore.autounload() every tick"""

    thread = None
    def __init__(self, bus, docstore, interval=60):
        self.docstore = docstore
        self.interval = interval
        self.safe_stop = True
        cherrypy.process.plugins.SimplePlugin.__init__(self, bus)

    def start(self):
        self.running = True
        if not self.thread:
            self.thread = threading.Thread(target=self.run)
            self.thread.start()

    def stop(self):
        self.bus.log("Stopping AutoUnloader")
        self.docstore.forceunload()
        self.running = False

        if self.thread:
            self.thread.join()
            self.thread = None

    def run(self):
        while self.running:
            self.docstore.autounload()
            i = 0
            while self.running and i < self.interval:
                time.sleep(1)
                i+=1



class DocStore:
    def __init__(self, workdir, expiretime, git=False, gitmode="user", gitshare=True, ignorefail=False, debug=False):
        log("Initialising document store in " + workdir)
        self.workdir = workdir
        self.expiretime = expiretime
        self.data = {}
        self.updateq = defaultdict(lambda: defaultdict(set)) #update queue, (namespace,docid) => session_id => set(folia element id), for concurrency
        self.lastaccess = defaultdict(dict) # (namespace,docid) => session_id => time
        self.changelog = defaultdict(list) # (namespace,docid) => [changemessage]
        self.lastunloadcheck = time.time()

        self.ignorefail = ignorefail
        self.fail = False

        self.lock = set() #will contain (namespace,docid) of temporarily locked documents, loading/unloading/saving are blocking operations
        self.setdefinitions = {}
        self.git = git
        self.gitmode = gitmode
        self.gitshare = gitshare
        self.debug = debug
        super().__init__()

    def getfilename(self, key):
        assert isinstance(key, tuple) and len(key) == 2
        if key[0] == "testflat":
            return syspath + '/testflat.folia.xml'
        else:
            return self.workdir + '/' + key[0] + '/' + key[1] + '.folia.xml'

    def getpath(self, key, useronly=False):
        assert isinstance(key, tuple) and len(key) == 2
        if useronly:
            return self.workdir + '/' + key[0].split('/')[0]
        else:
            return self.workdir + '/' + key[0]

    def getkey(self, filename):
        """reverse of getfilename()"""
        return tuple(filename.replace(self.workdir,'').strip('/').rsplit('/'),1)



    def use(self, key):
        while key in self.lock:
            if self.debug >= 2: log("[waiting for lock " + "/".join(key)+"]")
            time.sleep(0.1)
        self.lock.add(key)
        if self.debug >= 2: log("[acquired lock " + "/".join(key)+"]")

    def done(self, key):
        if self.debug >= 2: log("[releasing lock " + "/".join(key)+"]")
        self.lock.remove(key)


    def load(self,key, forcereload=False):
        if key[0] == "testflat": key = ("testflat", "testflat")
        self.use(key)
        filename = self.getfilename(key)
        if time.time() - self.lastunloadcheck > 900: #no unload check for 15 mins? background thread seems to have crashed?
            self.fail = True #trigger lockdown
            self.forceunload() #force unload of everything
            raise NoSuchDocument("Document Server is in lockdown due to loss of contact with autoupdater thread, refusing to process new documents...")
        if key not in self or forcereload:
            if not os.path.exists(filename):
                log("File not found: " + filename)
                self.done(key)
                raise NoSuchDocument
            if self.fail and not self.ignorefail:
                raise NoSuchDocument("Document Server is in lockdown due to earlier failure during XML serialisation, refusing to process new documents...")
            log("Loading " + filename)
            mainprocessor = folia.Processor.create(name="foliadocserve", version=VERSION, host=getfqdn(), folia_version=folia.FOLIAVERSION, src="https://github.com/proycon/foliadocserve")
            try:
                self.data[key] = folia.Document(file=filename, setdefinitions=self.setdefinitions, loadsetdefinitions=True,autodeclare=True,allowadhocsets=True,processor=mainprocessor,fixunassignedprocessor=True,fixinvalidreferences=True)
                if folia.checkversion(self.data[key].version, "2.0.0") < 0:
                    log("Upgrading " + self.data[key].filename)
                    upgrader = folia.Processor("foliaupgrade", version=FOLIATOOLSVERSION, src="https://github.com/proycon/foliatools")
                    mainprocessor.append(upgrader)
                    upgrade(self.data[key],upgrader)
                self.data[key].changed = False #we do not count the above upgrade as a change yet (meaning it won't be saved unless an annotation is also added/edited)
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_tb(exc_traceback, limit=50, file=sys.stderr)
                log("ERROR reading file " + filename + ": " + str(e))
                if logfile: traceback.print_tb(exc_traceback, limit=50, file=logfile)
                self.done(key)
                raise
            self.lastaccess[key]['NOSID'] = time.time()
        self.done(key)
        return self.data[key]

    def gitcommit(self, key, message="", remove=False):
        if self.git:
            doinit = False
            if os.path.exists(self.workdir + '/.git'):
                # entire workdir is one git repo (old style)
                targetdir = self.workdir
            elif self.gitmode == "monolithic":
                doinit = True
                targetdir = self.workdir
            else:
                targetdir = self.getpath(key, useronly=(self.gitmode == 'user'))
                if not os.path.exists(targetdir + '/.git'):
                    doinit = True
            os.chdir(targetdir)
            if doinit:
                log("Initialising git repository in  " + targetdir)
                r = os.system("git init --shared \"" + self.gitshare + "\"")
                if r != 0:
                    log("ERROR during git init of " + targetdir)
                    self.done(key)
                    return
            message = "\n".join(self.changelog[key]) + "\n" + message
            self.changelog[key] = [] #reset changelog
            message = message.strip("\n")
            log("Doing git commit for " + self.getfilename(key) + " -- " + message.replace("\n", " -- "))
            action = "rm" if remove else "add"
            r = os.system("cd \"" + targetdir + "\" && git " + action + " \"" + self.getfilename(key) + "\" && git commit -m \"" + message.replace('"','') + "\"")
            if r != 0:
                log("ERROR during git " + action + "/commit of " + self.getfilename(key) + " in " + targetdir)

    def save(self, key, message = ""):
        doc = self[key]
        if key[0] == "testflat":
            #No need to save the document, instead we run our tests:
            log("Running test " + key[1])
            return test(doc, key[1])
        elif hasattr(doc,'changed') and doc.changed:
            self.use(key)
            log("Saving " + self.getfilename(key) + " - " + message)
            dirname = os.path.dirname(self.getfilename(key))
            if not os.path.exists(dirname):
                log("Directory does not exist yet, creating on the fly: " + dirname)
                os.makedirs(dirname)
            try:
                doc.save(self.getfilename(key) + '.tmp')
            except Exception as e:
                self.fail = True
                log("ERROR: Unable to save document " + self.getfilename(key) + ": [" + e.__class__.__name__ + "] " + str(e) )
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_tb(exc_traceback, limit=50, file=sys.stderr)
                if logfile: traceback.print_tb(exc_traceback, limit=50, file=logfile)
                return False
            try:
                os.rename(self.getfilename(key) + '.tmp', self.getfilename(key))
            except Exception as e:
                self.fail = True
                log("ERROR: Unable to complete saving of document " + self.getfilename(key) + ": ["  + e.__class__.__name__ + "] " + str(e) )
                return False
            self.gitcommit(key, message)
            self.done(key)
            return True


    def unload(self, key, save=True):
        if key in self:
            if save:
                self.save(key)
            self.use(key) #save set its own lock
            log("Unloading " + "/".join(key))
            del self.data[key]
            del self.lastaccess[key]
            if key in self.updateq:
                del self.updateq[key]
            if key in self.changelog:
                del self.changelog[key]
            self.done(key)

    def delete(self, key):
        self.unload(key,False)
        filename = self.getfilename(key)
        if os.path.exists(filename):
            log("Removing " + filename)
            os.unlink(self.getfilename(key))
            self.gitcommit(key, message="Removed document", remove=True)


    def copy(self, key, newkey):
        if key in self:
            self.save(key) #ensure latest changes are flushed to disk
        filename = self.getfilename(key)
        if os.path.exists(filename):
            newfilename = self.getfilename(newkey)
            if os.path.exists(newfilename): #never overwrites
                log("Target file already exists (" + newfilename + ")")
            else:
                log("Copying " + filename + " to " + newfilename)
                targetdir = self.getpath(newkey)
                shutil.copyfile(filename, newfilename)
                self.gitcommit(newkey, message="Adding copied document")


    def move(self, key, newkey):
        self.copy(key, newkey)
        self.delete(key)

        #self.unload(key)
        #filename = self.getfilename(key)
        #if os.path.exists(filename):
        #    newfilename = self.getfilename(newkey)
        #    if os.path.exists(newfilename): #never overwrites
        #        log("Target file already exists (" + newfilename + ")")
        #    else:
        #        if self.git:
        #            message = "Moving document"
        #            log("Doing git commit for " + newfilename + " -- " + message.replace("\n", " -- "))
        #            r = os.system("git mv " + filename + " " + newfilename + " && git commit -m \"" + message.replace('"','') + "\"")
        #            if r != 0:
        #                log("ERROR during git mv/commit of " +filename)
        #        else:
        #            log("Moving " + filename + " to " + newfilename)
        #            shutil.movefile(filename, newfilename)

    def __getitem__(self, key):
        assert isinstance(key, tuple) and len(key) == 2
        if key[0] == "testflat":
            key = ("testflat","testflat")
        self.load(key)
        return self.data[key]

    def __setitem__(self, key, doc):
        assert isinstance(key, tuple) and len(key) == 2
        assert isinstance(doc, folia.Document)
        doc.filename = self.getfilename(key)
        self.data[key] = doc

    def __contains__(self,key):
        assert isinstance(key, tuple) and len(key) == 2
        return key in self.data


    def __len__(self):
        return len(self.data)

    def keys(self):
        return self.data.keys()

    def items(self):
        return self.data.items()

    def values(self):
        return self.data.values()

    def __iter__(self):
        return iter(self.data)

    def autounload(self, save=True):
        log("Documents loaded: " + str(len(self)))
        self.lastunloadcheck = time.time()
        if self.fail and not self.ignorefail:
            self.forceunload() #if we enter a failed state, we forcibly unload everything (probably again and again until the problem is fixed)
        else:
            unload = []
            for d in self.lastaccess:
                if d not in unload:
                    dounload = True #falsify: all sessions must be expired before we can actually unload the document
                    for sid, t in self.lastaccess[d].items():
                        expirecheck = time.time() - t
                        if expirecheck < self.expiretime:
                            dounload = False

                    if dounload:
                        log("Triggering unload for " + "/".join(d) + " [" + str(expirecheck) + "s / " + sid + "]")
                        unload.append(d)

            if unload:
                for key in unload:
                    self.unload(key, save)

    def forceunload(self):
        """Called when the document server stops/reloads (SIGUSR1 will trigger this)"""
        log("Forcibly unloading all " + str(len(self)) + " documents...")
        for key in list(self.data.keys()):
            self.unload(key)

def validatenamespace(namespace):
    return namespace.replace('..','').replace('"','').replace(' ','_').replace(';','').replace('&','').strip('/')

def getdocumentselector(query):
    if query.startswith("USE "):
        end = query[4:].index(' ') + 4
        if end >= 0:
            try:
                namespace,docid = query[4:end].rsplit("/",1)
            except:
                raise fql.SyntaxError("USE statement takes namespace/docid pair")
            return (validatenamespace(namespace),docid), query[end+1:]
        else:
            try:
                namespace,docid = query[4:end].rsplit("/",1)
            except:
                raise fql.SyntaxError("USE statement takes namespace/docid pair")
            return (validatenamespace(namespace),docid), ""
    return None, query






class Root:
    def __init__(self,docstore,bgtask,args):
        self.docstore = docstore
        self.bgtask = bgtask
        self.workdir = args.workdir
        self.debug = args.debug
        self.allowtextredundancy = args.allowtextredundancy

    def setsession(self,namespace,docid, sid=None, results=None):
        """Create or update a session"""
        if sid != 'NOSID':
            log("Creating session " + sid + " for " + "/".join((namespace,docid)))
            self.docstore.lastaccess[(namespace,docid)][sid] = time.time()
            # v-- will create it if it does not exist yet, does nothing otherwise, other sessions will write here what we need to update
            self.docstore.updateq[(namespace,docid)][sid] #pylint: disable=pointless-statement
            #update the queue for other sessions with the results we just obtained for this one
            for othersid in self.docstore.updateq[(namespace,docid)]:
                if othersid != sid:
                    for queryresults in results: #results are grouped per query, we don't care about that here though
                        for result in queryresults:
                            if result.id:
                                self.docstore.updateq[(namespace,docid)][othersid].add(result.id)

    def addtochangelog(self, doc, query, docselector):
        if self.docstore.git:
            if query.action and query.action.action != "SELECT":
                if query.action.focus and query.action.focus.Class:
                    changemsg = query.action.action.lower() + " on " + query.action.focus.Class.XMLTAG
                    if query.action.assignments and 'processor' in query.action.assignments:
                        changemsg += " by " + query.action.assignments['processor'].id
                    if query.action.assignments and 'annotator' in query.action.assignments:
                        changemsg += " by " + query.action.assignments['annotator']
                    self.docstore.changelog[docselector].append(changemsg)

    @cherrypy.expose
    def createnamespace(self, *namespaceargs):
        namespace = validatenamespace('/'.join(namespaceargs))
        if not os.path.exists(self.workdir + '/' + namespace):
            try:
                os.makedirs(self.workdir + '/' + namespace)
            except:
                raise cherrypy.HTTPError(403, "Unable to create namespace: " + namespace)
        cherrypy.response.headers['Content-Type']= 'text/plain'
        return "ok"


    @cherrypy.expose
    def flush(self):
        log("Flush called")
        self.docstore.forceunload()
        cherrypy.response.headers['Content-Type']= 'text/plain'
        return "done"

    @cherrypy.expose
    def query(self, **kwargs):
        """Query method, all FQL queries arrive here"""

        if 'X-Sessionid' in cherrypy.request.headers:
            sid = cherrypy.request.headers['X-Sessionid']
        else:
            sid = 'NOSID'

        if 'query' in kwargs:
            rawqueries = kwargs['query'].split("\n")
        else:
            cl = cherrypy.request.headers['Content-Length']
            rawqueries = cherrypy.request.body.read(int(cl)).split("\n")

        if self.debug:
            for i,rawquery in enumerate(rawqueries):
                log("[QUERY INCOMING #" + str(i+1) + ", SID=" +sid + "] " + rawquery)

        #Get parameters for FLAT-specific return format
        flatargs = getflatargs(cherrypy.request.params)
        flatargs['debug'] = self.debug
        flatargs['logfunction'] = log
        flatargs['version'] = VERSION

        prevdocsel = None
        sessiondocsel = None
        queries = []
        metachanges = {}
        for rawquery in rawqueries:
            try:
                docsel, rawquery = getdocumentselector(rawquery)
                rawquery = rawquery.replace("$FOLIADOCSERVE_PROCESSOR", PROCESSOR_FOLIADOCSERVE)
                if not docsel: docsel = prevdocsel
                self.docstore.use(docsel)
                if self.debug >= 2: log("[acquired lock " + "/".join(docsel)+"]")
                if not sessiondocsel: sessiondocsel = docsel
                if rawquery == "GET":
                    query = "GET"
                elif rawquery == "PROBE":
                    query = "PROBE" #gets no content data at all, but allows returning associated metadata used by FLAT, forces FLAT format
                else:
                    if rawquery[:4] == "CQL ":
                        if rawquery.find('FORMAT') != -1:
                            end = rawquery.find('FORMAT')
                            format = rawquery[end+7:]
                        else:
                            end = 9999
                            format = 'xml'
                        try:
                            query = fql.Query(cql.cql2fql(rawquery[4:end]))
                            query.format = format
                        except cql.SyntaxError as e :
                            raise fql.SyntaxError("Error in CQL query: " + str(e))
                    elif rawquery[:5] == "META ":
                        try:
                            key, value = rawquery[5:].split('=',maxsplit=1)
                        except ValueError:
                            raise fql.SyntaxError("Expected key=value after META keyword")
                        key = key.strip()
                        value = value.strip()
                        metachanges[key] = value
                        query = None
                    else:
                        query = fql.Query(rawquery)
                    if query and query.format == "python":
                        query.format = "xml"
                    if query and query.action and not docsel:
                        raise fql.SyntaxError("Document Server requires USE statement prior to FQL query")
            except fql.SyntaxError as e:
                log("[QUERY ON " + "/".join(docsel)  + "] " + str(rawquery))
                log("[QUERY FAILED] FQL Syntax Error: " + str(e))
                raise cherrypy.HTTPError(404, "FQL syntax error: " + str(e))
            finally:
                if self.debug >= 2: log("[releasing lock " + "/".join(docsel))
                self.docstore.done(docsel)

            if query:
                queries.append( (query, rawquery))
            prevdocsel = docsel


        if metachanges:
            try:
                doc = self.docstore[docsel]
            except NoSuchDocument:
                log("[QUERY FAILED] No such document")
                raise cherrypy.HTTPError(404, "Document not found: " + docsel[0] + "/" + docsel[1])
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_tb(exc_traceback, limit=50, file=sys.stderr)
                print("[QUERY FAILED] FoLiA Error in " + "/".join(docsel) + ": [" + e.__class__.__name__ + "] " + str(e), file=sys.stderr)
                log("[QUERY FAILED] FoLiA Error in " + "/".join(docsel) + ": [" + e.__class__.__name__ + "] " + str(e))
                if logfile: traceback.print_tb(exc_traceback, limit=50, file=logfile)
                raise cherrypy.HTTPError(404, "FoLiA error in " + "/".join(docsel) + ": [" + e.__class__.__name__ + "] " + str(e) + "\n\nQuery was: " + rawquery)

            if doc.metadatatype == "native":
                doc.changed = True
                self.docstore.lastaccess[docsel][sid] = time.time()
                log("[METADATA EDIT ON " + "/".join(docsel)  + "]")
                for key, value in metachanges.items():
                    if value == 'NONE':
                        del doc.metadata[key]
                    else:
                        doc.metadata[key] = value
            else:
                raise cherrypy.HTTPError(404, "Unable to edit metadata on document with non-native metadata type (" + "/".join(docsel)+")")
        else:
            doc = None #initialize document only if not already initialized by metadta changes


        results = [] #stores all results
        xresults = [] #stores results that should be transferred to other sessions as well, i.e. results of adds/edits
        prevdocid = None
        multidoc = False #are the queries over multiple distinct documents?
        format = None
        for query, rawquery in queries:
            try:
                doc = self.docstore[docsel]
                self.docstore.lastaccess[docsel][sid] = time.time()
                log("[QUERY ON " + "/".join(docsel)  + "] " + str(rawquery))
                if isinstance(query, fql.Query):
                    if prevdocid and doc.id != prevdocid:
                        multidoc = True
                    result =  query(doc,False,self.debug >= 2)
                    results.append(result) #False = nowrap
                    if query.action and query.action.action in ('EDIT','ADD','DELETE', 'SUBSTITUTE','PREPEND','APPEND'):
                        #results of edits should be transferred to other open sessions
                        xresults.append(result)
                    if self.debug:
                        log("[QUERY RESULT] " + repr(result))
                    format = query.format
                    if query.action and query.action.action != "SELECT":
                        doc.changed = True
                        self.addtochangelog(doc, query, docsel)
                elif query == "GET":
                    results.append(doc.xmlstring())
                    format = "single-xml"
                elif query == "PROBE":
                    #no queries to perform
                    format = "flat"
                else:
                    raise Exception("Invalid query")
            except NoSuchDocument:
                if self.docstore.fail and not self.docstore.ignorefail:
                    log("[QUERY FAILED] Document server is in lockdown due to earlier failure. Restart required!")
                    raise cherrypy.HTTPError(403, "Document server is in lockdown due to earlier failure. Contact your FLAT administrator")
                else:
                    log("[QUERY FAILED] No such document")
                    raise cherrypy.HTTPError(404, "Document not found: " + docsel[0] + "/" + docsel[1])
            except fql.QueryError as e:
                log("[QUERY FAILED] FQL Query Error: " + str(e))
                raise cherrypy.HTTPError(404, "FQL query error: " + str(e))
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_tb(exc_traceback, limit=50, file=sys.stderr)
                log("[QUERY FAILED] FoLiA Error in " + "/".join(docsel) + ": [" + e.__class__.__name__ + "] " + str(e))
                print("[QUERY FAILED] FoLiA Error in " + "/".join(docsel) + ": [" + e.__class__.__name__ + "] " + str(e), file=sys.stderr)
                if logfile: traceback.print_tb(exc_traceback, limit=50, file=logfile)
                raise cherrypy.HTTPError(404, "FoLiA error in " + "/".join(docsel) + ": [" + e.__class__.__name__ + "] " + str(e) + "\n\nQuery was: " + rawquery)
            prevdocid = doc.id

        if not format:
            if metachanges:
                return "{\"version\":\"" + VERSION + "\"}"
            else:
                raise cherrypy.HTTPError(404, "No queries given")
        if format.endswith('xml'):
            cherrypy.response.headers['Content-Type']= 'text/xml'
        elif format.endswith('json'):
            cherrypy.response.headers['Content-Type']= 'application/json'


        if format == "xml":
            out = "<results>" + "\n".join(results) + "</results>"
        elif format == "json":
            out = "[" + ",".join(results) + "]"
        elif format == "flat":
            if sid != 'NOSID' and sessiondocsel:
                self.setsession(sessiondocsel[0],sessiondocsel[1],sid, xresults)
            cherrypy.response.headers['Content-Type']= 'application/json'
            if multidoc:
                raise "{\"version\":\""+VERSION +"\"} //multidoc response, not producing results"
            elif doc:
                log("[Parsing results for FLAT]")
                out =  parseresults(results, doc, **flatargs)
        else:
            if len(results) > 1:
                raise cherrypy.HTTPError(404, "Multiple results were obtained but format dictates only one can be returned!")
            out = results[0]


        if docsel[0] == "testflat":
            testresult = self.docstore.save(docsel) #won't save, will run tests instead
            log("Test result: " +str(repr(testresult)))


            if format == "flat":
                out = json.loads(str(out,'utf-8'))
                out['testresult'] = testresult[0]
                out['testmessage'] = testresult[1]
                out['queries'] = rawqueries
                out = json.dumps(out)

            #unload the document, we want a fresh copy every time
            del self.docstore.data[('testflat','testflat')]

        if self.debug:
            if isinstance(out,bytes):
                log("[FINAL RESULTS] " + str(out,'utf-8'))
            else:
                log("[FINAL RESULTS] " + out)

        if isinstance(out,str):
            return out.encode('utf-8')
        else:
            return out


    @cherrypy.expose
    def index(self):
        template = env.get_template('index.html')
        return template.render(VERSION=VERSION)


    @cherrypy.expose
    def getdochistory(self, *args):
        namespace, docid = self.docselector(*args)
        log("Returning history for document " + "/".join((namespace,docid)))
        cherrypy.response.headers['Content-Type'] = 'application/json'
        if not os.path.exists(self.docstore.getfilename((namespace,docid))):
            raise cherrypy.HTTPError(404, "Document not found")
        if self.docstore.git:
            log("Invoking git log " + namespace+"/"+docid + ".folia.xml")
            if os.path.exists(self.workdir + '/.git'):
                dir = self.workdir
            else:
                dir = self.docstore.getpath((namespace,docid))
            os.chdir(dir)
            proc = subprocess.Popen("git log " + docid + ".folia.xml", stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True,cwd=dir)
            outs, errs = proc.communicate()
            if errs: log("git log errors? " + errs.decode('utf-8'))
            d = {'history':[], 'version': VERSION}
            count = 0
            for commit, date, msg in parsegitlog(outs.decode('utf-8')):
                count += 1
                d['history'].append( {'commit': commit, 'date': date, 'msg':msg})
            if count == 0: log("git log output: " + outs.decode('utf-8'))
            log(str(count) + " revisions found - " + errs.decode('utf-8'))
            return json.dumps(d).encode('utf-8')
        else:
            return json.dumps({'history': [], 'version': VERSION}).encode('utf-8')

    @cherrypy.expose
    def save(self, *args, message=""):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        namespace, docid = self.docselector(*args)
        if (namespace,docid) in self.docstore:
            #self.bgtask.put( self.docstore.save, (namespace,docid), message)
            self.docstore.save( (namespace,docid), message)
            return b"{\"saved\":1, \"version\": \"" + VERSION.encode('utf-8')+ "\"}"
        else:
            return b"{\"saved\":0, \"version\": \"" + VERSION.encode('utf-8')+ "\"}"


    @cherrypy.expose
    def revert(self, *args, commithash=None):
        if not commithash:
            raise cherrypy.HTTPError(400, "Expected commithash")

        if not all([ x.isalnum() for x in commithash ]):
            return b"{\"version\": \"" + VERSION.encode('utf-8')+ "\"}"

        cherrypy.response.headers['Content-Type'] = 'application/json'
        if self.docstore.git:
            namespace, docid = self.docselector(*args)
            key = (namespace,docid)
            os.chdir(os.path.join(self.workdir,namespace))

            if key in self.docstore:
                #unload document (will even still save it if not done yet, cause we need a clean workdir)
                self.docstore.unload(key)

            log("Doing git revert for " + self.docstore.getfilename(key) )
            r = os.system("git checkout " + commithash + " " + self.docstore.getfilename(key) + " && git commit -m \"Reverting to commit " + commithash + "\"")
            if r != 0:
                log("Error during git revert of " + self.docstore.getfilename(key))
            return b"{\"version\": \"" + VERSION.encode('utf-8')+ "\"}"
        else:
            return b"{\"version\": \"" + VERSION.encode('utf-8')+ "\"}"



    def checkexpireconcurrency(self):
        """Delete concurrency information for sessions that fail to poll within the expiration time (they almost certainly closed the page/browser)"""
        deletelist = []
        for d in self.docstore.lastaccess:
            for sid in self.docstore.lastaccess[d]:
                lastaccess = self.docstore.lastaccess[d][sid]
                if time.time() - lastaccess > self.docstore.expiretime:
                    deletelist.append( (d,sid) )
        for d,sid in deletelist:
            if sid != 'NOSID':
                log("Expiring session " + sid + " for " + "/".join(d))
                del self.docstore.lastaccess[d][sid]
                if d in self.docstore.updateq:
                    if sid in self.docstore.updateq[d]:
                        del self.docstore.updateq[d][sid]
                    if len(self.docstore.updateq[d]) == 0:
                        del self.docstore.updateq[d]
                if len(self.docstore.lastaccess[d]) == 0:
                    del self.docstore.lastaccess[d]


    def docselector(self, *args):
        try:
            docid = args[-1]
            namespace = validatenamespace('/'.join(args[:-1]))
            if not namespace or not docid:
                raise NoSuchDocument()
        except:
            raise cherrypy.HTTPError(404, "Expected namespace/docid")
        docid = docid.replace('/','').replace('..','').replace(';','').replace('&','').replace(' ','_')
        return namespace, docid



    @cherrypy.expose
    def poll(self, *args):
        namespace, docid = self.docselector(*args)

        if 'X-Sessionid' in cherrypy.request.headers:
            sid = cherrypy.request.headers['X-Sessionid']
        else:
            raise cherrypy.HTTPError(404, "Expected X-Sessionid " + namespace + "/" + docid)

        #set last access
        log("Poll from session " + sid + " for " + "/".join((namespace,docid)))
        self.docstore.lastaccess[(namespace,docid)][sid] = time.time()

        if namespace == "testflat":
            return "{\"version\":\""+VERSION+"\"}" #no polling for testflat

        self.checkexpireconcurrency()

        if sid in self.docstore.updateq[(namespace,docid)]:
            ids = self.docstore.updateq[(namespace,docid)][sid]
            self.docstore.updateq[(namespace,docid)][sid] = set() #reset
            if ids:
                cherrypy.log("Successful poll from session " + sid + " for " + "/".join((namespace,docid)) + ", returning IDs: " + " ".join(ids))
                doc = self.docstore[(namespace,docid)]
                results = [[ doc[id] for id in ids if id in doc ]] #results are grouped by query, but we lose that distinction here and group them all in one, hence the double list
                return parseresults(results, doc, **{'version': VERSION, 'sid':sid, 'lastaccess': self.docstore.lastaccess[(namespace,docid)]})
            else:
                return json.dumps({'sessions': len([s for s in self.docstore.lastaccess[(namespace,docid)] if s != 'NOSID' ])}).encode('utf-8')
        else:
            return json.dumps({'sessions': len([s for s in self.docstore.lastaccess[(namespace,docid)] if s != 'NOSID' ])}).encode('utf-8')

    def listdir(self, rootdir, output):
        for d in os.listdir(os.path.join(self.docstore.workdir,rootdir)):
            if d != 'testflat' and d[0] != '.' and os.path.isdir(os.path.join(self.docstore.workdir, rootdir, d)):
                output.append(os.path.join(rootdir, d))
                self.listdir(os.path.join(rootdir, d), output)
        return output

    @cherrypy.expose
    def namespaces(self, *namespaceargs):
        rootdir = validatenamespace('/'.join(namespaceargs))
        namespaces = []
        try:
            self.listdir(rootdir, namespaces)
        except FileNotFoundError:
            raise cherrypy.HTTPError(404, "Namespace not found: " + str(rootdir))
        return json.dumps({
            'namespaces': namespaces
        })

    @cherrypy.expose
    def documents(self, *namespaceargs):
        namespace = validatenamespace('/'.join(namespaceargs))
        try:
            docs = [ x for x in os.listdir(self.docstore.workdir + "/" + namespace) if x[-10:] == ".folia.xml" ]
        except FileNotFoundError:
            raise cherrypy.HTTPError(404, "Namespace not found: " + str(namespace))
        return json.dumps({
            'documents': docs,
            'timestamp': { x:os.path.getmtime(self.docstore.workdir + "/" + namespace + "/"+ x) for x in docs  },
            'filesize': { x:os.path.getsize(self.docstore.workdir + "/" + namespace + "/"+ x) for x in docs  }
        })


    @cherrypy.expose
    def upload(self, *namespaceargs):
        namespace = validatenamespace('/'.join(namespaceargs))
        log("In upload, namespace=" + namespace)
        response = {'version':VERSION}
        cl = cherrypy.request.headers['Content-Length']
        data = cherrypy.request.body.read(int(cl))
        cherrypy.response.headers['Content-Type'] = 'application/json'
        #data =cherrypy.request.params['data']
        try:
            log("Loading document from upload")
            mainprocessor = folia.Processor.create(name="foliadocserve", version=VERSION, host=getfqdn(), folia_version=folia.FOLIAVERSION, src="https://github.com/proycon/foliadocserve")
            doc = folia.Document(string=data,setdefinitions=self.docstore.setdefinitions, loadsetdefinitions=True, autodeclare=True, allowadhocsets=True, fixunassignedprocessor=True, fixinvalidreferences=True, processor=mainprocessor)
            if needsfoliaupgrade(data):
                log("Upgrading " + doc.filename)
                upgrader = folia.Processor("foliaupgrade", version=FOLIATOOLSVERSION, src="https://github.com/proycon/foliatools")
                mainprocessor.append(upgrader)
                upgrade(doc, upgrader)
            if not self.allowtextredundancy:
                for e in doc.data:
                    cleantextredundancy(e)
            doc.changed = True
            response['docid'] = doc.id
            self.docstore[(namespace,doc.id)] = doc
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            formatted_lines = traceback.format_exc().splitlines()
            traceback.print_tb(exc_traceback, limit=50, file=sys.stderr)
            response['error'] = "Uploaded file is no valid FoLiA Document: " + str(e) + " -- " "\n".join(formatted_lines)
            log(response['error'])
            if logfile: traceback.print_tb(exc_traceback, limit=50, file=logfile)
            return json.dumps(response).encode('utf-8')

        filename = self.docstore.getfilename( (namespace, doc.id))
        i = 1
        while os.path.exists(filename):
            filename = self.docstore.getfilename( (namespace, doc.id + "." + str(i)))
            i += 1
        self.docstore.save((namespace,doc.id), "Initial upload")
        return json.dumps(response).encode('utf-8')

    @cherrypy.expose
    def delete(self, *args):
        namespace, docid = self.docselector(*args)
        log("Delete, namespace=" + namespace)
        self.docstore.delete((namespace,docid))
        return "{\"version\":\""+VERSION+"\"}"

    @cherrypy.expose
    def copy(self, *args,**params):
        if 'target' in params:
            key = self.docselector(*args)
            newkey = self.docselector(*params['target'].split('/'))
            self.docstore.copy(key,newkey)
            return "{\"version\":\""+VERSION+"\"}"
        else:
            raise cherrypy.HTTPError(404, "No target specified")

    @cherrypy.expose
    def move(self, *args,**params):
        if 'target' in params:
            key = self.docselector(*args)
            newkey = self.docselector(*params['target'].split('/'))
            self.docstore.move(key,newkey)
            return "{\"version\":\""+VERSION+"\"}"
        else:
            raise cherrypy.HTTPError(404, "No target specified")

def needsfoliaupgrade(data):
    if isinstance(data, bytes):
        data = str(data,'utf-8')
    snippet = data[:512]
    regexp = re.compile('version="([0-9\.]+)"')
    match = regexp.search(data)
    if match:
        version = match.group(1)
    else:
        return True
    if folia.checkversion(version, "2.0.0") < 0:
        return True
    else:
        return False


def main():
    global logfile #pylint: disable=global-statement
    parser = argparse.ArgumentParser(description="FoLiA Document Server - Allows querying and manipulating FoLiA documents. Do not serve publicly in production use!", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-d','--workdir', type=str,help="Work directory", action='store',required=True)
    parser.add_argument('-p','--port', type=int,help="Port", action='store',default=8080,required=False)
    parser.add_argument('-l','--logfile', type=str,help="Log file", action='store',default="foliadocserve.log",required=False)
    parser.add_argument('-D','--debug', type=int,help="Debug level", action='store',default=0,required=False)
    parser.add_argument('--allowtextredundancy',help="Allow text redundancy (will be stripped from documents otherwise)", action='store_true',default=False)
    parser.add_argument('--git',help="Enable versioning control using git (separate git repositories will be automatically created for each namespace, OR you can make one global one in the workdir manually)", action='store_true',default=False)
    parser.add_argument('--gitshare', type=str, help="Sets the shared option when creating new git repository (git --shared). Valid values are: false|true|umask|group|all|world|everybody|0xxx, defaults to 'group'", action='store', default="group")
    parser.add_argument('--gitmode', type=str, help="Set git mode, values are: monolithic (ALL users share a single repository, NOT recommended because of scalability); user (each user/namespace is its own git repository; this is the default); nested (each subdirectory is its own git repository, maximum scalability)", action='store', default='user')
    parser.add_argument('--expirationtime', type=int,help="Expiration time in seconds, documents will be unloaded from memory after this period of inactivity", action='store',default=900,required=False)
    parser.add_argument('--interval', type=int,help="Interval at which the unloader checks documents (in seconds)", action='store',default=60,required=False)
    parser.add_argument('--ignorefail', help="Ignore failures when saving documents. By default, the document server will lock up and refuse to load new documents (requiring manual restart)", action='store_true',default=False,required=False)
    parser.add_argument('--host',type=str,help="Host/IP to listen for (defaults to all interfaces)", action='store',default="0.0.0.0")
    args = parser.parse_args()
    logfile = open(args.logfile,'a',encoding='utf-8')
    log("foliadocserve " + VERSION)
    try:
        args.workdir = os.path.realpath(args.workdir)
    except:
        log("ERROR: Document root directory " + str(args.workdir) + " does not exist")
        sys.exit(2)
    os.chdir(args.workdir)
    cherrypy.config.update({
        'server.socket_host': args.host,
        'server.socket_port': args.port,
        'server.max_request_body_size' : 1024*1024*1024, #max 1GB upload (that is a lot!)
        'server.socket_timeout': 30, #30s instead of default 10s
        'request.show_tracebacks':False,
    })
    cherrypy.process.servers.wait_for_occupied_port = fake_wait_for_occupied_port
    docstore = DocStore(args.workdir, args.expirationtime, args.git, args.gitmode, args.gitshare, args.ignorefail, args.debug)
    bgtask = BackgroundTaskQueue(cherrypy.engine)
    bgtask.subscribe()
    autounloader = AutoUnloader(cherrypy.engine, docstore, args.interval)
    autounloader.subscribe()
    def stop():
        log("Stop signal received")
        docstore.forceunload()
        bgtask.unsubscribe()
        autounloader.unsubscribe()
        log("Quitting")
        sys.exit(0)
    cherrypy.engine.subscribe('stop',  stop)
    cherrypy.engine.subscribe('graceful',  docstore.forceunload)
    cherrypy.quickstart(Root(docstore,bgtask,args))

if __name__ == '__main__':
    print("foliadocserve " + VERSION,file=sys.stderr)
    main()
