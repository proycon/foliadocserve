#!/usr/bin/env python3

#---------------------------------------------------------------
# FoLiA Document Server
#   by Maarten van Gompel
#   Centre for Language Studies
#   Radboud University Nijmegen
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


from __future__ import print_function, unicode_literals, division, absolute_import
import cherrypy
import argparse
import time
import os
import json
import random
import datetime
import subprocess
import sys
import traceback
from copy import copy
from collections import defaultdict
from pynlpl.formats import folia, fql, cql
from foliadocserve.flat import parseresults, getflatargs
from foliadocserve.test import test

from jinja2 import Environment, FileSystemLoader
syspath = os.path.dirname(os.path.realpath(__file__))
env = Environment(loader=FileSystemLoader(syspath + '/templates'))

def fake_wait_for_occupied_port(host, port): return

class NoSuchDocument(Exception):
    pass


VERSION = "0.2.1"

logfile = None
def log(msg):
    global logfile
    if logfile:
        logfile.write(msg+"\n")
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


class DocStore:
    def __init__(self, workdir, expiretime):
        log("Initialising document store in " + workdir)
        self.workdir = workdir
        self.expiretime = expiretime
        self.data = {}
        self.lastchange = {}
        self.updateq = defaultdict(dict) #update queue, (namespace,docid) => session_id => [folia element id], for concurrency
        self.lastaccess = defaultdict(dict) # (namespace,docid) => session_id => time
        self.setdefinitions = {}
        if os.path.exists(self.workdir + "/.git"):
            self.git = True
        else:
            self.git = False
        super().__init__()

    def getfilename(self, key):
        assert isinstance(key, tuple) and len(key) == 2
        if key[0] == "testflat":
            return syspath + '/testflat.folia.xml'
        else:
            return self.workdir + '/' + key[0] + '/' + key[1] + '.folia.xml'

    def load(self,key, forcereload=False):
        if key[0] == "testflat": key = ("testflat", "testflat")
        filename = self.getfilename(key)
        if not key in self or forcereload:
            if not os.path.exists(filename):
                log("File not found: " + filename)
                raise NoSuchDocument
            log("Loading " + filename)
            self.data[key] = folia.Document(file=filename, setdefinitions=self.setdefinitions, loadsetdefinitions=True)
            self.lastchange[key] = time.time()
        return self.data[key]



    def save(self, key, message = "unspecified change"):
        doc = self[key]
        if key[0] == "testflat":
            #No need to save the document, instead we run our tests:
            doc.save("/tmp/testflat.xml")
            log("Running test " + key[1])
            return test(doc, key[1])
        else:
            log("Saving " + self.getfilename(key) + " - " + message)
            doc.save()
            if self.git:
                log("Doing git commit for " + self.getfilename(key) + " - " + message)
                os.chdir(self.workdir)
                r = os.system("git add " + self.getfilename(key) + " && git commit -m \"" + message + "\"")
                if r != 0:
                    log("Error during git add/commit of " + self.getfilename(key))


    def unload(self, key, save=True):
        if key in self:
            if save:
                self.save(key,"Saving unsaved changes")
            log("Unloading " + "/".join(key))
            del self.data[key]
            del self.lastchange[key]
        else:
            raise NoSuchDocument

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
        unload = []
        for key, t in self.lastchange.items():
            if t > time.time() + self.expiretime:
                unload.append(key)

        for key in unload:
            self.unload(key, save)



def getdocumentselector(query):
    if query.startswith("USE "):
        end = query[4:].index(' ') + 4
        if end >= 0:
            try:
                namespace,docid = query[4:end].split("/")
            except:
                raise fql.SyntaxError("USE statement takes namespace/docid pair")
            return (namespace,docid), query[end+1:]
        else:
            try:
                namespace,docid = query[4:end].split("/")
            except:
                raise fql.SyntaxError("USE statement takes namespace/docid pair")
            return (namespace,docid), ""
    return None, query






class Root:
    def __init__(self,docstore,args):
        self.docstore = docstore
        self.workdir = args.workdir
        self.debug = args.debug

    def createsession(self,namespace,docid, sid, results):
        if sid[-5:] != 'NOSID':
            log("Creating session " + sid + " for " + "/".join((namespace,docid)))
            self.docstore.lastaccess[(namespace,docid)][sid] = time.time()
            self.docstore.updateq[(namespace,docid)][sid] = [ result.id for result in results if result.id ]

    @cherrypy.expose
    def createnamespace(self, namespace):
        namepace = namespace.replace('/','').replace('..','')
        try:
            os.mkdir(self.workdir + '/' + namespace)
        except:
            pass
        cherrypy.response.headers['Content-Type']= 'text/plain'
        return "ok"

    ###NEW###

    @cherrypy.expose
    def query(self, **kwargs):
        """Query method, all FQL queries arrive here"""

        if 'X-sessionid' in cherrypy.request.headers:
            sid = cherrypy.request.headers['X-sessionid']
        else:
            sid = 'NOSID'

        if 'query' in kwargs:
            rawqueries = kwargs['query'].split("\n")
        else:
            cl = cherrypy.request.headers['Content-Length']
            rawqueries = cherrypy.request.body.read(int(cl)).split("\n")

        #Get parameters for FLAT-specific return format
        flatargs = getflatargs(cherrypy.request.params)

        prevdocselector = None
        sessiondocselector = None
        queries = []
        for rawquery in rawqueries:
            try:
                docselector, rawquery = getdocumentselector(rawquery)
                if not docselector: docselector = prevdocselector
                if not sessiondocselector: sessiondocselector = docselector
                if rawquery == "GET":
                    query = "GET"
                else:
                    if rawquery[:4] == "CQL ":
                        try:
                            query = fql.Query(cql.cql2fql(rawquery[4:]))
                        except cql.SyntaxError as e :
                            raise fql.SyntaxError("Error in CQL query: " + str(e))
                    else:
                        query = fql.Query(rawquery)
                    if query.format == "python":
                        query.format = "xml"
                    if query.action and not docselector:
                        raise fql.SyntaxError("Document Server requires USE statement prior to FQL query")
            except fql.SyntaxError as e:
                log("[QUERY ON " + "/".join(docselector)  + "] " + str(rawquery))
                log("[QUERY FAILED] FQL Syntax Error: " + str(e))
                raise cherrypy.HTTPError(404, "FQL syntax error: " + str(e))

            queries.append( (query, rawquery))
            prevdocselector = docselector

        results = []
        doc = None
        prevdocid = None
        multidoc = False #are the queries over multiple distinct documents?
        for query, rawquery in queries:
            try:
                doc = self.docstore[docselector]
                log("[QUERY ON " + "/".join(docselector)  + "] " + str(rawquery))
                if isinstance(query, fql.Query):
                    if prevdocid and doc.id != prevdocid:
                        multidoc = True
                    result =  query(doc,False,self.debug >= 2)
                    results.append(result) #False = nowrap
                    if self.debug:
                        log("[QUERY RESULT] " + result)
                    format = query.format
                elif query == "GET":
                    results.append(doc.xmlstring())
                    format = "single-xml"
                else:
                    raise Exception("Invalid query")
            except NoSuchDocument:
                log("[QUERY FAILED] No such document")
                raise cherrypy.HTTPError(404, "Document not found: " + docselector[0] + "/" + docselector[1])
            except fql.QueryError as e:
                log("[QUERY FAILED] FQL Query Error: " + str(e))
                raise cherrypy.HTTPError(404, "FQL query error: " + str(e))
            except Exception as e:
                log("[QUERY FAILED] FoLiA Error: " + str(e))
                raise cherrypy.HTTPError(404, "FoLiA error: " + str(e))
            prevdocid = doc.id

        if not format:
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
            if sid != 'NOSID' and sessiondocselector and not multidoc:
                self.createsession(sessiondocselector[0],sessiondocselector[1],sid, results)
            cherrypy.response.headers['Content-Type']= 'application/json'
            if multidoc:
                raise "{} //multidoc response, not producing results"
            elif doc:
                out =  parseresults(results, doc, **flatargs)
        else:
            if len(results) > 1:
                raise cherrypy.HTTPError(404, "Multiple results were obtained but format dictates only one can be returned!")
            out = results[0]


        if docselector[0] == "testflat":
            testresult = self.docstore.save(docselector) #won't save, will run tests instead
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
    def getdochistory(self, namespace, docid):
        namepace = namespace.replace('/','').replace('..','').replace(';','').replace('&','')
        docid = docid.replace('/','').replace('..','').replace(';','').replace('&','')
        log("Returning history for document " + "/".join((namespace,docid)))
        cherrypy.response.headers['Content-Type'] = 'application/json'
        if self.docstore.git and (namespace,docid) in self.docstore:
            log("Invoking git log " + namespace+"/"+docid + ".folia.xml")
            os.chdir(self.workdir)
            proc = subprocess.Popen("git log " + namespace + "/" + docid + ".folia.xml", stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True,cwd=self.workdir)
            outs, errs = proc.communicate()
            if errs: log("git log errors? " + errs.decode('utf-8'))
            d = {'history':[]}
            count = 0
            for commit, date, msg in parsegitlog(outs.decode('utf-8')):
                count += 1
                d['history'].append( {'commit': commit, 'date': date, 'msg':msg})
            if count == 0: log("git log output: " + outs.decode('utf-8'))
            log(str(count) + " revisions found - " + errs.decode('utf-8'))
            return json.dumps(d).encode('utf-8')
        else:
            return json.dumps({'history': []}).encode('utf-8')

    @cherrypy.expose
    def revert(self, namespace, docid, commithash):
        if not all([ x.isalnum() for x in commithash ]):
            return b"{}"

        cherrypy.response.headers['Content-Type'] = 'application/json'
        if self.docstore.git:
            if (namespace,docid) in self.docstore:
                os.chdir(self.workdir)
                #unload document (will even still save it if not done yet, cause we need a clean workdir)
                key = (namespace,docid)
                self.docstore.unload(key)

            log("Doing git revert for " + self.docstore.getfilename(key) )
            os.chdir(self.workdir)
            r = os.system("git checkout " + commithash + " " + self.docstore.getfilename(key) + " && git commit -m \"Reverting to commit " + commithash + "\"")
            if r != 0:
                log("Error during git revert of " + self.docstore.getfilename(key))
            return b"{}"
        else:
            return b"{}"



    def checkexpireconcurrency(self):
        #purge old buffer
        deletelist = []
        for d in self.docstore.updateq:
            if d in self.docstore.lastaccess:
                for s in self.docstore.updateq[d]:
                    if s in self.docstore.lastaccess[d]:
                        lastaccess = self.docstore.lastaccess[d][s]
                        if time.time() - lastaccess > 3600*12:  #expire after 12 hours
                            deletelist.append( (d,s) )
        for d,s in deletelist:
            log("Expiring session " + s + " for " + "/".join(d))
            del self.docstore.lastaccess[d][s]
            del self.docstore.updateq[d][s]
            if len(self.docstore.lastaccess[d]) == 0:
                del self.docstore.lastaccess[d]
            if len(self.docstore.updateq[d]) == 0:
                del self.docstore.updateq[d]



    @cherrypy.expose
    def poll(self, namespace, docid):
        if 'X-sessionid' in cherrypy.request.headers:
            sid = cherrypy.request.headers['X-sessionid']
        else:
            raise cherrypy.HTTPError(404, "Expected X-sessionid" + docselector[0] + "/" + docselector[1])

        if namespace == "testflat":
            return "{}" #no polling for testflat

        self.checkexpireconcurrency()
        if sid in self.docstore.updateq[(namespace,docid)]:
            ids = self.docstore.updateq[(namespace,docid)][sid]
            self.docstore.updateq[(namespace,docid)][sid] = []
            if ids:
                cherrypy.log("Succesful poll from session " + sid + " for " + "/".join((namespace,docid)) + ", returning IDs: " + " ".join(ids))
                doc = self.docstore[(namespace,docid)]
                results = [ doc[id] for id in ids if id in doc ]
                return parseresults(results, doc, **{'sid':sid})
            else:
                return "{}"
        else:
            return "{}"



    @cherrypy.expose
    def namespaces(self):
        namespaces = [ x for x in os.listdir(self.docstore.workdir) if x != "testflat" and x[0] != "." ]
        return json.dumps({
                'namespaces': namespaces
        })

    @cherrypy.expose
    def documents(self, namespace):
        namepace = namespace.replace('/','').replace('..','')
        docs = [ x for x in os.listdir(self.docstore.workdir + "/" + namespace) if x[-10:] == ".folia.xml" ]
        return json.dumps({
                'documents': docs,
                'timestamp': { x:os.path.getmtime(self.docstore.workdir + "/" + namespace + "/"+ x) for x in docs  },
                'filesize': { x:os.path.getsize(self.docstore.workdir + "/" + namespace + "/"+ x) for x in docs  }
        })


    @cherrypy.expose
    def upload(self, namespace):
        log("In upload, namespace=" + namespace)
        response = {}
        cl = cherrypy.request.headers['Content-Length']
        data = cherrypy.request.body.read(int(cl))
        cherrypy.response.headers['Content-Type'] = 'application/json'
        #data =cherrypy.request.params['data']
        try:
            log("Loading document from upload")
            doc = folia.Document(string=data,setdefinitions=self.docstore.setdefinitions, loadsetdefinitions=True)
            response['docid'] = doc.id
            self.docstore[(namespace,doc.id)] = doc
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            formatted_lines = traceback.format_exc().splitlines()
            traceback.print_tb(exc_traceback, limit=50, file=sys.stderr)
            response['error'] = "Uploaded file is no valid FoLiA Document: " + str(e) + " -- " "\n".join(formatted_lines)
            log(response['error'])
            return json.dumps(response).encode('utf-8')

        filename = self.docstore.getfilename( (namespace, doc.id))
        i = 1
        while os.path.exists(filename):
            filename = self.docstore.getfilename( (namespace, doc.id + "." + str(i)))
            i += 1
        self.docstore.save((namespace,doc.id), "Initial upload")
        return json.dumps(response).encode('utf-8')



def main():
    global logfile
    parser = argparse.ArgumentParser(description="", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-d','--workdir', type=str,help="Work directory", action='store',required=True)
    parser.add_argument('-p','--port', type=int,help="Port", action='store',default=8080,required=False)
    parser.add_argument('-l','--logfile', type=str,help="Log file", action='store',default="foliadocserve.log",required=False)
    parser.add_argument('-D','--debug', type=int,help="Debug level", action='store',default=0,required=False)
    parser.add_argument('--expirationtime', type=int,help="Expiration time in seconds, documents will be unloaded from memory after this period of inactivity", action='store',default=900,required=False)
    args = parser.parse_args()
    logfile = open(args.logfile,'w',encoding='utf-8')
    os.chdir(args.workdir)
    #args.storeconst, args.dataset, args.num, args.bar
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': args.port,
    })
    cherrypy.process.servers.wait_for_occupied_port = fake_wait_for_occupied_port
    docstore = DocStore(args.workdir, args.expirationtime)
    cherrypy.quickstart(Root(docstore,args))

if __name__ == '__main__':
    main()
