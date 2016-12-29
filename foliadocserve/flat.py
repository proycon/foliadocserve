#---------------------------------------------------------------
# FoLiA Document Server - FLAT module
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

import json
import random
import sys
from pynlpl.formats import folia,fql
from foliatools.foliatextcontent import linkstrings


ELEMENTLIMIT = 5000 #structure elements only


ELEMENTMEMORYLIMIT = 10000000 #very hard abort (exception) after this many elements, to protect memory overflow

def getflatargs(params):
    """Get arguments specific to FLAT, will be passed to parseresults"""
    args = {}
    if 'declarations' in params:
        args['declarations'] = bool(int(params['declarations']))
    else:
        args['declarations'] = False
    if 'setdefinitions' in params:
        args['setdefinitions'] = bool(int(params['setdefinitions']))
    else:
        args['setdefinitions'] = False
    if 'metadata' in params:
        args['metadata'] = bool(int(params['metadata']))
    else:
        args['metadata'] = False
    if 'toc' in params:
        args['toc'] = bool(int(params['toc']))
    else:
        args['toc'] = False
    if 'slices' in params:
        args['slices'] = [ ( x.split(':')[0], int(x.split(':')[1])) for x in  params['slices'].split(',') ]  #comma separated list of xmltag:slicesize
    else:
        args['slices'] = ""
    if 'textclasses' in params:
        args['textclasses']= bool(int(params['declarations']))
    else:
        args['textclasses'] = False
    return args



def gettoc(element, processed = None):
    if processed is None: processed = set()
    toc = [] #nested recursive list of (div.id, headtext, [toc])   (where toc is the same recursive part)
    for head in element.select(folia.Head):
        division = head.ancestor(folia.Division)
        if division:
            if division.id not in processed:
                processed.add(division.id)
                toc.append( {'id': division.id, 'text': head.text(), 'toc': gettoc(division, processed)} )
    return toc


def isrtl(doc):
    """Checks if the document should be rendered in right-to-left fashion"""
    if doc.metadata:
        if doc.metadatatype == folia.MetaDataType.NATIVE:
            if 'direction' in doc.metadata and doc.metadata['direction'] == 'rtl':
                return True

        lang = doc.language()
        if lang:
            return lang.lower() in ('ar','fa','ur','ps','sd','he','yi','dv','ug','ara','fas','urd','pus','snd','heb','yid','arc','syc','syr','div','uig','arz','ary','auz','ayl','acm','acw','acx','aec','afb','ajp','apd','arb','arq','arabic','hebrew','urdu','persian','farsi')   #non-exhaustive list of ISO-639-1 and -3 language codes (and some names) that are written right-to-left
    return False



def getslices(doc, Class, size=100):
    for i, element in enumerate(doc.select(Class)):
        if i % size == 0:
            yield element.id



def parseresults(results, doc, **kwargs):
    response = {'version': kwargs['version']} #foliadocserve version
    if 'declarations' in kwargs and kwargs['declarations']:
        response['declarations'] = tuple(getdeclarations(doc))
    if 'setdefinitions' in kwargs and kwargs['setdefinitions']:
        response['setdefinitions'] =  getsetdefinitions(doc)
    if 'metadata' in kwargs and kwargs['metadata']:
        response['metadata'] =  getmetadata(doc)
    if 'toc' in kwargs and kwargs['toc']:
        response['toc'] =  gettoc(doc)
    if 'textclasses' in kwargs:
        response['textclasses'] = list(doc.textclasses)
    if 'slices' in kwargs and kwargs['slices']:
        response['slices'] = {}
        for tag, size in kwargs['slices']:
            Class = folia.XML2CLASS[tag]
            response['slices'][tag] = list(getslices(doc, Class, size))
    if 'debug' in kwargs and kwargs['debug']:
        debug = True
    else:
        debug = False
    if 'logfunction' in kwargs and kwargs['logfunction']:
        log = kwargs['logfunction']
    else:
        log = lambda s: print(s,file=sys.stderr)
    if debug: log("[Debugging for FLAT result parse enabled]")

    response['rtl'] = isrtl(doc)

    if 'customslicesize' in kwargs and kwargs['customslicesize']:
        customslicesize = int(kwargs['customslicesize'])
    else:
        customslicesize = 50


    if results:
        response['elements'] = []
        if customslicesize:
            response['customslices'] = []
            postponecustomslice = False

    bookkeeper = Bookkeeper() #will abort with partial result if too much data is returned
    for queryresults in results: #results are grouped per query, we don't care about the origin now
        for i, element in enumerate(queryresults):
            if debug: log("[Processing result from query]")

            if customslicesize and i % customslicesize == 0 or postponecustomslice: #custom slices of this result set, for pagination of search results
                if isinstance(element,fql.SpanSet):
                    id = element[0].id
                else:
                    id = element.id
                if not id:
                    postponecustomslice = True
                else:
                    response['customslices'].append(id)
                    postponecustomslice = False

            if not bookkeeper.stop:
                if isinstance(element,fql.SpanSet):
                    for e in element:
                        structure = {}
                        if isinstance(e, (folia.AbstractStructureElement, folia.Correction)):
                            html, _ = getstructure(e, structure, bookkeeper, debug=debug,log=log)
                        else:
                            html = None
                        response['elements'].append({
                            'elementid': e.id if e.id else None,
                            'html': html,
                            'structure': structure,
                            'annotations': getannotations(e.doc,structure,debug=debug,log=log),
                        })
                else:
                    structure = {}
                    if isinstance(element, (folia.AbstractStructureElement, folia.Correction)):
                        html, _ = getstructure(element, structure, bookkeeper, debug=debug,log=log)
                    else:
                        html = None
                    response['elements'].append({
                        'elementid': element.id if element.id else None,
                        'html': html,
                        'structure': structure,
                        'annotations': getannotations(element.doc,structure,debug=debug,log=log),
                    })
            if bookkeeper.stop:
                break
        if bookkeeper.elementcount > ELEMENTMEMORYLIMIT:
            raise Exception("Memory limit reached, aborting")

    response['aborted'] = bookkeeper.stop
    if 'lastaccess' in kwargs:
        response['sessions'] =  len([s for s in kwargs['lastaccess'] if s != 'NOSID' ])

    return json.dumps(response).encode('utf-8')

def gethtmltext(element, textclass="current"):
    """Get the text of an element, but maintain markup elements and convert them to HTML"""

    checkstrings = folia.AnnotationType.STRING in element.doc.annotationdefaults

    s = ""
    if isinstance(element, folia.AbstractTextMarkup): #markup
        tag = "span"
        cls = None #CSS class, will be foliatype_foliaclass or foliatype if no folia class exists
        attribs = ""
        if isinstance(element, folia.TextMarkupStyle):
            #we guess how possible class names may be mapped to HTML directly, set-agnostic
            if element.cls == 'strong':
                tag = "strong"
            elif element.cls and element.cls[:2] == 'em':
                tag = "em"
            elif element.cls and (element.cls[:4] == 'bold' or element.cls == 'b'):
                tag = "b"
            elif element.cls and (element.cls[:6] == 'italic' or element.cls == 'i' or element.cls[:5] == 'slant'):
                tag = "i"
            elif element.cls and (element.cls[:3] == 'lit' or element.cls[:4] == 'verb' or element.cls[:4] == 'code'):
                tag = "tt"
            else:
                cls = "style"
        elif isinstance(element, folia.TextMarkupError):
            cls = "error"
        elif isinstance(element, folia.TextMarkupGap):
            cls = "gap"
        elif isinstance(element, folia.TextMarkupString):
            cls = "str"
            try:
                if element.idref:
                    if element.doc[element.idref].count(folia.Correction) or element.doc[element.idref].count(folia.ErrorDetection):
                        cls = "str correction"
            except:
                pass
        elif isinstance(element, folia.TextMarkupCorrection):
            cls = "correction"

        #hyperlinks
        if element.href:
            tag = "a"
            attribs += " href=\"" + element.href + "\""

        if tag == "span" and element.cls:
            if cls:
                cls += "_" + element.cls
            else:
                cls = element.cls

        if tag:
            s += "<" + tag
            if cls:
                s += " class=\"" + cls + "\""
            try:
                if element.idref:
                    s += " id=\"strref_" + element.idref + "\""
            except AttributeError:
                pass
            if attribs:
                s += attribs
            s += ">"
        for e in element:
            if isinstance(e,str):
                s += e
            elif isinstance(e, folia.Linebreak):
                s += "<br/>"
            elif isinstance(e, folia.AbstractTextMarkup) or isinstance(e, folia.Linebreak): #markup
                if s: s += e.TEXTDELIMITER #for AbstractMarkup, will usually be ""
                s += gethtmltext(e)
        if tag:
            s += "</" + tag + ">"
        return s
    elif isinstance(element, folia.Linebreak):
        return "<br/>"
    elif isinstance(element, folia.TextContent):
        if checkstrings and element.ancestor(folia.AbstractStructureElement).hasannotation(folia.String) and not any( isinstance(x,folia.TextMarkupString) for x in element):
            linkstrings(element.ancestor(folia.AbstractStructureElement), element.cls)

        for e in element:
            if isinstance(e,str):
                s += e
            elif isinstance(e, folia.AbstractTextMarkup) or isinstance(e, folia.Linebreak): #markup
                if s: s += e.TEXTDELIMITER #for AbstractMarkup, will usually be ""
                s += gethtmltext(e)
        #hyperlink
        if element.href:
            return "<a href=\"" + element.href + "\">" + s + "</a>"
        else:
            return s
    else:
        return gethtmltext(element.textcontent(textclass)) #only explicit text!

class Bookkeeper:
    def __init__(self):
        self.elementcount = 0
        self.stop = False
        self.stopat = None

    def reset(self):
        self.stop = False
        return self

def generate_id(element):
    candidateid = ":" #dummy
    while candidateid[0] == ':' or candidateid in element.doc:
        candidateid = element.doc.id + "." + element.XMLTAG + ".%032x" % random.getrandbits(128)
    element.id = candidateid
    element.doc.index[element.id] = element
    return element.id

def getstructure(element, structure, bookkeeper, incorrection=None, debug=False,log=lambda s: print(s,file=sys.stderr)):
    """Converts the element to html skeleton and structure datamodel

    HTML is returned, structure is appended to dictionary
    """
    if bookkeeper:
        bookkeeper.elementcount += 1
        if bookkeeper.elementcount > ELEMENTLIMIT:
            bookkeeper.stopat = element
            bookkeeper.stop = True
            return "",[]

    html = ""
    subids = [] #will hold IDs of embedded structural elements
    if debug:
         log("Processing structure " + element.XMLTAG + "; ID " + str(repr(element.id)))

    if isinstance(element, ( folia.Correction, folia.AbstractStructureElement)):
        if not element.id: #Auto-generate ID if missing, with collision protection (though very unlikely to collide with 128 bits)
            generate_id(element)
            if debug: log("Auto-generated ID " + element.id)

        if isinstance(element, folia.Correction):
            if element.hasnew():
                try:
                    for child in element.new():
                        if isinstance(child, folia.AbstractStructureElement) or isinstance(child, folia.Correction):
                            subhtml, _ = getstructure(child, structure, bookkeeper, incorrection=element.id, debug=debug,log=log)
                            html += subhtml
                except folia.NoSuchAnnotation:
                    pass
            elif element.hascurrent():
                try:
                    for child in element.current():
                        if isinstance(child, folia.AbstractStructureElement) or isinstance(child, folia.Correction):
                            subhtml, _ = getstructure(child, structure, bookkeeper, incorrection=element.id, debug=debug,log=log)
                            html += subhtml
                except folia.NoSuchAnnotation:
                    pass

            if element.hasoriginal():
                try:
                    for child in element.original():
                        if isinstance(child, folia.AbstractStructureElement) or isinstance(child, folia.Correction):
                            getstructure(child, structure, None, incorrection=element.id, debug=debug,log=log)
                except folia.NoSuchAnnotation:
                    pass

            if element.hassuggestions():
                for suggestion in element.suggestions():
                    try:
                        for child in suggestion:
                            if isinstance(child, folia.AbstractStructureElement) or isinstance(child, folia.Correction):
                                getstructure(child, structure, None, incorrection=element.id, debug=debug,log=log)
                    except folia.NoSuchAnnotation:
                        pass

            #The correction annotation itself will be outputted later by getannotations()

            if debug: log("Done processing " + element.XMLTAG + "; ID " + str(repr(element.id)))
            return html, []
        elif isinstance(element, folia.AbstractStructureElement):
            for child in element:
                if isinstance(child, (folia.AbstractStructureElement, folia.Correction)):
                    if bookkeeper and not bookkeeper.stop:
                        subhtml, newsubids  = getstructure(child, structure, bookkeeper, debug=debug,log=log)
                        if subhtml: html += subhtml
                        subids += newsubids
                elif isinstance(child, folia.MorphologyLayer) or isinstance(child, folia.PhonologyLayer):
                    for subchild in child:
                        if bookkeeper and not bookkeeper.stop:
                            _, newsubids  = getstructure(subchild, structure, bookkeeper, debug=debug,log=log)
                            #ignoring html
                            subids += newsubids

            try:
                label = "<span class=\"lbl\">" + gethtmltext(element) + "</span>" #only when text is explicitly associated with the element
                annotationbox = "<span class=\"ab\"></span>"
            except folia.NoSuchText:
                annotationbox = ""
                label = ""
            if isinstance(element, folia.Word):
                if element.space:
                    label += "&nbsp;"
            elif element.TEXTDELIMITER == " ":
                label += "&nbsp;"


            #inner wrap
            if isinstance(element, folia.Paragraph):
                htmltag = "div" #p doesn't allow div within it
            elif isinstance(element, folia.Table):
                htmltag = "table"
            elif isinstance(element, folia.List):
                htmltag = "ul"
            elif isinstance(element, folia.ListItem):
                htmltag = "li"
            elif isinstance(element, folia.Row):
                htmltag = "tr"
            elif isinstance(element, folia.Cell):
                htmltag = "td"
            else:
                htmltag = "div"

            if html:
                #has children
                html = "<" + htmltag + " id=\"" + element.id + "\" class=\"F " + element.XMLTAG + "\">" + annotationbox + label + html
            else:
                #no children
                html = "<" + htmltag + " id=\"" + element.id + "\" class=\"F " + element.XMLTAG + " deepest\">" + annotationbox
                if label:
                    html += label
                else:
                    html += "<span class=\"lbl\"></span>" #label placeholder

            #Specific content
            if isinstance(element, folia.Linebreak):
                html += "<br />"
            if isinstance(element, folia.Whitespace):
                html += "<br /><br />"
            elif isinstance(element, folia.Figure):
                html += "<img src=\"" + element.src + "\">"

            html += "</" + htmltag + ">"

            structure[element.id] =  element.json(ignorelist=(folia.AbstractStructureElement,folia.AbstractAnnotationLayer, folia.Correction, folia.AbstractTokenAnnotation, folia.AbstractExtendedTokenAnnotation, folia.AbstractSpanAnnotation, folia.TextContent, folia.PhonContent, folia.Alternative) )  #)recurse=False)
            if element.parent and element.parent.id:
                structure[element.id]['parent'] = element.parent.id
            if isinstance(element, (folia.Morpheme, folia.Phoneme)):
                structure[element.id]['parentstructure'] = element.ancestor(folia.Word).id
            #structure[element.id]['targets'] = [ element.id ]
            #structure[element.id]['scope'] = [ element.id ]
            structure[element.id]['structure'] = subids
            structure[element.id]['annotations'] = [] #will be set by getannotations() later
            if incorrection:
                structure[element.id]['incorrection'] = incorrection
            if isinstance(element, folia.Word):
                prevword = element.previous(folia.Word,None)
                if prevword:
                    structure[element.id]['previousword'] =  prevword.id
                else:
                    structure[element.id]['previousword'] = None
                nextword = element.next(folia.Word,None )
                if nextword:
                    structure[element.id]['nextword'] =  nextword.id
                else:
                    structure[element.id]['nextword'] = None
            #elif not isinstance(element, (folia.Text, folia.Division, folia.Speech, folia.Morpheme) ): #exclude elements that are generally too big or small
            #    structure[element.id]['wordorder'] = [ w.id for w in element.words() ]

            if debug: log("Done processing structure " + element.XMLTAG + "; ID " + str(repr(element.id)))
            return html, [element.id]

    if debug: log("ERROR: Structure element expected, got " + str(type(element)))
    raise Exception("Structure element expected, got " + str(type(element)))


def getannotations(doc, structure, annotations = None,debug=False,log=lambda s: print(s,file=sys.stderr)):
    if not annotations: annotations = {}
    processed = set() #processed elements
    for id in structure:
        e = doc[id]
        processed.add(id)
        getannotations_in(e, structure, annotations, debug=debug,log=log)
        if isinstance(e, folia.Word) and e.parent:
            p = e.parent
            while p is not None:
                if isinstance(p, folia.AbstractStructureElement) and p.id and p.id not in structure and p.id not in processed:
                    processed.add(p.id)
                    #do we have span annotations?
                    if p.hasannotationlayer():
                        #yes, process them
                        getannotations_in(p, structure, annotations, debug=debug,log=log, spanonly=True)
                p = p.parent

    return annotations

def getannotations_in(parentelement, structure, annotations, incorrection=None, auth=True, debug=False,log=lambda s: print(s,file=sys.stderr),idprefix=None, spanonly=False):
    #Get annotations in the specified parentelement and add them to the annotations dictionary (passed as argument)
    #Structure dictionary is also passed and references for all found annotations are made
    idlist = []
    checkstrings = folia.AnnotationType.STRING in parentelement.doc.annotationdefaults
    if isinstance(parentelement, folia.AbstractStructureElement):
        structureelement = parentelement
    else:
        structureelement = parentelement.ancestor(folia.AbstractStructureElement)


    if debug: log("Processing annotations in " + parentelement.XMLTAG + "; ID " + str(repr(parentelement.id)))

    if not structureelement.id:
        log("Structural parent "  + structureelement.XMLTAG + " still lacks an ID and is absent in getstructure() result, generating ID...")
        generate_id(structureelement)
        structure[structureelement.id] = {'id':structureelement.id, 'type': structureelement.XMLTAG,'annotations':[]}


    for element in parentelement:
        #skip higher-order annotations; they are handled by their parents
        #also skip structure annotations, they are handled by getstructure()
        if not isinstance(element, folia.AbstractElement) or isinstance(element, (folia.AbstractStructureElement, folia.Feature, folia.AlignReference, folia.AbstractSpanRole, folia.Comment, folia.Description)): continue

        #Get the extended ID
        if element.id:
            extid = element.id
        elif isinstance(element, folia.Correction):
            #we require IDs on corrections, make one on the fly
            element.id = element.doc.id + ".correction.%032x" % random.getrandbits(128)
            element.doc.index[element.id] = element
            extid = element.id
        elif isinstance(element, folia.Suggestion):
            #we require IDs on suggestions, make one on the fly
            element.id = element.doc.id + ".suggestion.%032x" % random.getrandbits(128)
            element.doc.index[element.id] = element
            extid = element.id
        else:
            if idprefix:
                extid = idprefix + '/' + element.XMLTAG
            elif incorrection:
                extid = incorrection + '/' + element.XMLTAG
            else:
                extid = structureelement.id + '/' + element.XMLTAG
            if isinstance(element, (folia.TextContent, folia.PhonContent)):
                extid += '/' + element.cls
            elif element.set:
                extid += '/' + element.set
            else:
                extid += '/undefined'

        if debug:
            log("Processing annotation " + element.XMLTAG + " in " + parentelement.XMLTAG + "; extended ID " + extid)

        processed = False
        if isinstance(element, folia.Correction):
            processed = True
            getannotations_correction(element,structure,annotations, auth=auth, log=log,debug=debug)
            if auth and structureelement.id in structure:
                structure[structureelement.id]['annotations'].append(extid) #link structure to annotations
        elif isinstance(element,( folia.TextContent, folia.PhonContent, folia.AbstractTokenAnnotation, folia.String)) and not spanonly:
            processed = True
            annotations[extid] = element.json()
            annotations[extid]['targets'] = [ structureelement.id ]
            annotations[extid]['scope'] = [ structureelement.id ]
            if auth and structureelement.id in structure:
                structure[structureelement.id]['annotations'].append(extid) #link structure to annotations
            if isinstance(element,(folia.TextContent, folia.PhonContent)):
                if any( isinstance(x,folia.AbstractTextMarkup) for x in element) or checkstrings:
                    annotations[extid]['htmltext'] = gethtmltext(element,element.cls)
            #See if there is a correction element with only suggestions pertaining to this annotation, link to it using 'hassuggestions':
            for c in structureelement.select(folia.Correction):
                if c.hassuggestions():
                    #Do the suggestions describe this annotation type?
                    hassuggestions = False
                    for suggestion in c.suggestions():
                        for sa in suggestion:
                            if sa.__class__ is element.__class__ and sa.set == element.set:
                                hassuggestions = True
                                break #one is enough
                        if hassuggestions: break #one is enough
                    if hassuggestions:
                        if not 'hassuggestions' in annotations[extid]: annotations[extid]['hassuggestions'] = []
                        annotations[extid]['hassuggestions'].append(c.id)
        elif isinstance(element, folia.AbstractSpanAnnotation) and not isinstance(element, folia.AbstractSpanRole):
            processed = True
            if not element.id and ((element.REQUIRED_ATTRIBS and folia.Attrib.ID in element.REQUIRED_ATTRIBS) or (element.OPTIONAL_ATTRIBS and folia.Attrib.ID in element.OPTIONAL_ATTRIBS)):
                #span annotation elements must have an ID for the editor to work with them, let's autogenerate one:
                element.id = element.doc.data[0].generate_id(element)
                #and add to index
                element.doc.index[element.id] = element
                extid = element.id

            #also generate IDs for span roles prior to json serialisation:
            for child in element.select(folia.AbstractSpanRole, ignore=(folia.Word,folia.Morpheme)):
                if child.id is None:
                    child.id = element.generate_id(child)
                    child.doc.index[child.id] = child

            annotations[extid] = element.json(ignorelist=(folia.Word,folia.Morpheme,folia.Phoneme)) #don't descend into words (do descend for nested span annotations)
            annotations[extid]['span'] = True
            annotations[extid]['targets'] = [ x.id for x in element.wrefs(recurse=False) ]
            scope =  list(element.wrefs(recurse=True))
            annotations[extid]['scope'] = [ x.id for x in scope ]
            if auth:
                for x in scope:
                    if x.id in structure:
                        structure[x.id]['annotations'].append(extid) #link structure to annotations
            annotations[extid]['annotations'] = [] #for nested span annotations (not higher order, those are in 'children')
            #get all spanroles
            if 'children' in annotations[extid]:
                for child in annotations[extid]['children']:
                    if 'id' in child and child['id']:
                        role = element.doc[child['id']]
                        if isinstance(role, folia.AbstractSpanRole):
                            assert role.XMLTAG == child['type']
                            #set targets
                            child['isspanrole'] = True
                            child['targets'] = [x.id for x in role.wrefs(recurse=False)]
                            child['scope'] = [x.id for x in role.wrefs(recurse=True)]
            layerparent = element.ancestor(folia.AbstractAnnotationLayer).ancestor(folia.AbstractStructureElement).id
            try:
                parentspan = element.ancestor(folia.AbstractSpanAnnotation)
                annotations[extid]['parentspan'] = parentspan.id
            except folia.NoSuchAnnotation:
                annotations[extid]['parentspan'] = None
            annotations[extid]['layerparent'] = layerparent
            if auth:
                if layerparent in structure:
                    if 'spanannotations' not in structure[layerparent]:
                        structure[layerparent]['spanannotations'] = [extid]
                    else:
                        structure[layerparent]['spanannotations'].append(extid)

        if processed:
            if debug: log("(" + str(len(idlist)+1) + ") Successfully processed annotation " + element.XMLTAG + " in " + parentelement.XMLTAG + "; extended ID " + extid)
            if incorrection:
                annotations[extid]['incorrection'] = incorrection
            annotations[extid]['auth'] = auth
            idlist.append(extid)

        if isinstance(element, ( folia.AbstractAnnotationLayer, folia.AbstractSpanAnnotation, folia.Suggestion)): #folia.String should be added but this breaks stuff
            #descend into nested annotations
            subidlist = getannotations_in(element,structure, annotations,debug=debug,log=log)

            if processed:
                annotations[extid]['annotations'] = subidlist

            processed = True

        if not processed:
            if debug: log("Skipped annotation " + element.XMLTAG + " in " + parentelement.XMLTAG + "; extended ID " + extid + "; type " + str(type(element)) + " not handled directly")

    return idlist

def getannotations_correction(element, structure, annotations, debug=False,log=lambda s: print(s,file=sys.stderr), auth=True):
    correction_new = []
    correction_current = []
    correction_original = []
    correction_suggestions = []
    correction_special_type = None
    correction_merge = None
    correction_split = None
    correction_structure = False

    #Is this a correction of structure?
    for attr in ('new','current','original'):
        try:
            for x in getattr(element,attr)():
                if isinstance(x, folia.AbstractStructureElement):
                    correction_structure = True
                    break
        except folia.NoSuchAnnotation:
            pass
        if correction_structure: break
    if not correction_structure:
        try:
            for suggestion in element.suggestions():
                for x in suggestion:
                    if isinstance(x, folia.AbstractStructureElement):
                        correction_structure = True
                        break
        except folia.NoSuchAnnotation:
            pass

    if element.hasnew():
        subids = getannotations_in(element.new(),structure,annotations, incorrection=element.id,auth=auth,debug=debug,log=log,idprefix=element.id + '/new')
        if correction_structure:
            for child in element.new():
                if isinstance(child,folia.AbstractStructureElement):
                    correction_new.append(child.id)
        else:
            for subid in subids:
                correction_new.append(subid)
    elif element.hasnew(True):
        #empty new, this is deletion
        correction_special_type = 'deletion'
    if element.hascurrent():
        subids = getannotations_in(element.current(),structure,annotations, incorrection=element.id,auth=auth,debug=debug,log=log,idprefix=element.id + '/current')
        try:
            if correction_structure:
                for child in element.current():
                    if isinstance(child,folia.AbstractStructureElement):
                        correction_current.append(child.id)
            else:
                for subid in subids:
                    correction_current.append(subid)
        except folia.NoSuchAnnotation:
            pass
    if element.hasoriginal():
        subids = getannotations_in(element.original(),structure,annotations, incorrection=element.id, auth=False,debug=debug,log=log,idprefix=element.id + '/original')
        if correction_structure:
            for child in element.original():
                if isinstance(child,folia.AbstractStructureElement):
                    correction_original.append(child.id)
        else:
            for subid in subids:
                correction_original.append(subid)
    elif element.hasoriginal(True):
        #empty original, this is an insertion
        if element.hasnew():
            correction_special_type = 'insertion'
    elif not element.hascurrent() and element.hascurrent(True):
        #empty current, this is a suggested insertion
        if element.hassuggestions():
            correction_special_type = 'suggest insertion'
    if element.hassuggestions():
        for i, suggestion in enumerate(element.suggestions()):
            suggestion_json = suggestion.json(recurse=False)
            if suggestion.merge:
                correction_merge = suggestion.merge.split(' ')
            if suggestion.split:
                correction_split = suggestion.split.split(' ')

            subids = getannotations_in(suggestion,structure,annotations, incorrection=element.id, auth=False,debug=debug,log=log,idprefix=element.id+'/suggestion.' + str(i+1))
            if correction_structure:
                subids = []
                for child in suggestion:
                    if isinstance(child,folia.AbstractStructureElement):
                        subids.append(child.id)
                suggestion_json['structure'] = subids
            else:
                suggestion_json['annotations'] = subids
            correction_suggestions.append(suggestion_json)
    elif element.hassuggestions(True):
        #suggestion for deletion
        correction_special_type = 'suggest deletion'

    annotations[element.id] = {'id': element.id ,'set': element.set, 'class': element.cls, 'structural': correction_structure, 'confidence': element.confidence, 'type': 'correction', 'new': correction_new,'current': correction_current, 'original': correction_original, 'suggestions': correction_suggestions}
    if element.annotator:
        annotations[element.id]['annotator'] = element.annotator
    if element.annotatortype == folia.AnnotatorType.AUTO:
        annotations[element.id]['annotatortype'] = "auto"
    elif element.annotatortype == folia.AnnotatorType.MANUAL:
        annotations[element.id]['annotatortype'] = "manual"
    if correction_special_type:
        annotations[element.id]['specialtype'] = correction_special_type
        if correction_split:
            annotations[element.id]['suggestsplit'] = correction_split
        if correction_merge:
            annotations[element.id]['suggestmerge'] = correction_merge

    annotations[element.id]['previous'] = None
    try:
        previous = element.previous(None,None)
        if isinstance(previous, folia.Correction): previous = next(previous.select(folia.AbstractStructureElement))
        if previous: annotations[element.id]['previous'] =  previous.id
    except StopIteration:
        pass
    annotations[element.id]['next'] = None
    try:
        successor = element.next(None,None )
        if isinstance(successor, folia.Correction): successor = next(successor.select(folia.AbstractStructureElement))
        if successor: annotations[element.id]['next'] =  successor.id
    except StopIteration:
        pass
    p = element.ancestor(folia.AbstractStructureElement)
    annotations[element.id]['targets'] = [ p.id ]
    annotations[element.id]['scope'] = [ p.id ]

def getdeclarations(doc):
    #resolve annotation type and return the XML tag that is primary for it
    for annotationtype, set in doc.annotations:
        if annotationtype in folia.ANNOTATIONTYPE2XML:
            xmltag = folia.ANNOTATIONTYPE2XML[annotationtype]
            C = folia.XML2CLASS[xmltag]
            if not issubclass(C, folia.AbstractTextMarkup):
                yield {'annotationtype': xmltag, 'set': set} #annotationtype as xmltag

def getsetdefinitions(doc):
    setdefs = {}
    for annotationtype, set in doc.annotations:
        if set in doc.setdefinitions:
            setdefs[set] = doc.setdefinitions[set].json()
    return setdefs

def getmetadata(doc):
    if doc.metadata:
        return dict(doc.metadata.items())
    else:
        return {}
