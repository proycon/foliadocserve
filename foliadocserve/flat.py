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

from pynlpl.formats import folia,fql
import json
import random


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



def gettoc(element, processed = set()):
    toc = [] #nested recursive list of (div.id, headtext, [toc])   (where toc is the same recursive part)
    for head in element.select(folia.Head):
        division = head.ancestor(folia.Division)
        if division:
            if division.id not in processed:
                processed.add(division.id)
                toc.append( {'id': division.id, 'text': head.text(), 'toc': gettoc(division, processed)} )
    return toc


def getslices(doc, Class, size=100):
    for i, element in enumerate(doc.select(Class)):
        if i % size == 0:
            yield element.id



def parseresults(results, doc, **kwargs):
    response = {}
    if 'declarations' in kwargs and kwargs['declarations']:
        response['declarations'] = tuple(getdeclarations(doc))
    if 'setdefinitions' in kwargs and kwargs['setdefinitions']:
        response['setdefinitions'] =  getsetdefinitions(doc)
    if 'toc' in kwargs and kwargs['toc']:
        response['toc'] =  gettoc(doc)
    if 'textclasses' in kwargs:
        response['textclasses'] = list(doc.textclasses)
    if 'slices' in kwargs and kwargs['slices']:
        response['slices'] = {}
        for tag, size in kwargs['slices']:
            Class = folia.XML2CLASS[tag]
            response['slices'][tag] = list(getslices(doc, Class, size))

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
                        response['elements'].append({
                            'elementid': e.id if e.id else None,
                            'html': gethtml(e,bookkeeper) if isinstance(e, folia.AbstractStructureElement) else None,
                            'annotations': list(getannotations(e,bookkeeper.reset())),
                        })
                else:
                    response['elements'].append({
                        'elementid': element.id if element.id else None,
                        'html': gethtml(element,bookkeeper) if isinstance(element, folia.AbstractStructureElement) else None,
                        'annotations': list(getannotations(element,bookkeeper.reset())),
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


def gethtml(element, bookkeeper):
    """Converts the element to html skeleton"""
    bookkeeper.elementcount += 1
    if bookkeeper.elementcount > ELEMENTLIMIT:
        bookkeeper.stopat = element
        bookkeeper.stop = True
        return ""

    if isinstance(element, folia.Correction):
        s = ""
        if element.hasnew():
            for child in element.new():
                if isinstance(child, folia.AbstractStructureElement) or isinstance(child, folia.Correction):
                    s += gethtml(child, bookkeeper)
        elif element.hascurrent():
            for child in element.current():
                if isinstance(child, folia.AbstractStructureElement) or isinstance(child, folia.Correction):
                    s += gethtml(child, bookkeeper)
        return s
    elif isinstance(element, folia.AbstractStructureElement):
        s = ""
        for child in element:
            if isinstance(child, folia.AbstractStructureElement) or isinstance(child, folia.Correction):
                if not bookkeeper.stop:
                    s += gethtml(child, bookkeeper)


        try:
            label = "<span class=\"lbl\">" + gethtmltext(element) + "</span>" #only when text is expliclity associated with the element
            annotationbox = "<span class=\"ab\"></span>"
        except folia.NoSuchText:
            annotationbox = ""
            label = ""
        if isinstance(element, folia.Word):
            if element.space:
                label += "&nbsp;"
        elif element.TEXTDELIMITER == " ":
            label += "&nbsp;"

        if not element.id:
            element.id = element.doc.id + "." + element.XMLTAG + ".id" + str(random.randint(1000,999999999))

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

        if s:
            #has children
            s = "<" + htmltag + " id=\"" + element.id + "\" class=\"F " + element.XMLTAG + "\">" + annotationbox + label + s
        else:
            #no children
            s = "<" + htmltag + " id=\"" + element.id + "\" class=\"F " + element.XMLTAG + " deepest\">" + annotationbox
            if label:
                s += label
            else:
                s += "<span class=\"lbl\"></span>" #label placeholder

        #Specific content
        if isinstance(element, folia.Linebreak):
            s += "<br />"
        if isinstance(element, folia.Whitespace):
            s += "<br /><br />"
        elif isinstance(element, folia.Figure):
            s += "<img src=\"" + element.src + "\">"

        s += "</" + htmltag + ">"
        return s
    else:
        raise Exception("Structure element expected, got " + str(type(element)))

def getannotations(element,bookkeeper):
    if element is bookkeeper.stopat:
        bookkeeper.stop = True
    if not bookkeeper.stop:
        if isinstance(element, folia.Correction):
            if not element.id:
                #annotator requires IDS on corrections, make one on the fly
                hash = random.getrandbits(128)
                element.id = element.doc.id + ".correction.%032x" % hash
            correction_new = []
            correction_current = []
            correction_original = []
            correction_suggestions = []
            if element.hasnew():
                for x in element.new():
                    if x is bookkeeper.stopat: bookkeeper.stop = True #do continue with correction though
                    for y in  getannotations(x,bookkeeper):
                        if not 'incorrection' in y: y['incorrection'] = []
                        y['incorrection'].append(element.id)
                        correction_new.append(y)
                        yield y #yield as any other
            if element.hascurrent():
                for x in element.current():
                    if x is bookkeeper.stopat: bookkeeper.stop = True #do continue with correction though
                    for y in  getannotations(x,bookkeeper):
                        if not 'incorrection' in y: y['incorrection'] = []
                        y['incorrection'].append(element.id)
                        correction_current.append(y)
                        yield y #yield as any other
            if element.hasoriginal():
                for x in element.original():
                    if x is bookkeeper.stopat: bookkeeper.stop = True #do continue with correction though
                    for y in  getannotations(x,bookkeeper):
                        y['auth'] = False
                        if not 'incorrection' in y: y['incorrection'] = []
                        y['incorrection'].append(element.id)
                        correction_original.append(y)
            if element.hassuggestions():
                for x in element.suggestions():
                    if x is bookkeeper.stopat: bookkeeper.stop = True #do continue with correction though
                    for y in  getannotations(x,bookkeeper):
                        y['auth'] = False
                        if not 'incorrection' in y: y['incorrection'] = []
                        y['incorrection'].append(element.id)
                        correction_suggestions.append(y)

            annotation = {'id': element.id ,'set': element.set, 'class': element.cls, 'type': 'correction', 'new': correction_new,'current': correction_current, 'original': correction_original, 'suggestions': correction_suggestions}
            if element.annotator:
                annotation['annotator'] = element.annotator
            if element.annotatortype == folia.AnnotatorType.AUTO:
                annotation['annotatortype'] = "auto"
            elif element.annotatortype == folia.AnnotatorType.MANUAL:
                annotation['annotatortype'] = "manual"
            p = element.ancestor(folia.AbstractStructureElement)
            annotation['targets'] = [ p.id ]
            yield annotation
        elif isinstance(element,folia.TextContent):
            annotation = element.json()
            p = element.parent
            p = element.ancestor(folia.AbstractStructureElement)
            annotation['targets'] = [ p.id ]
            assert isinstance(annotation, dict)
            yield annotation
        elif isinstance(element, folia.AbstractTokenAnnotation):
            annotation = element.json()
            p = element.parent
            #log("Parent of " + str(repr(element))+ " is "+ str(repr(p)))
            p = element.ancestor(folia.AbstractStructureElement)
            annotation['targets'] = [ p.id ]
            assert isinstance(annotation, dict)
            yield annotation
        elif isinstance(element, folia.AbstractSpanAnnotation):
            if not element.id and (folia.Attrib.ID in element.REQUIRED_ATTRIBS or folia.Attrib.ID in element.OPTIONAL_ATTRIBS):
                #span annotation elements must have an ID for the editor to work with them, let's autogenerate one:
                element.id = element.doc.data[0].generate_id(element)
                #and add to index
                element.doc.index[element.id] = element

            annotation = element.json(ignorelist=(folia.Word,)) #don't descend into words (do descend for nested span annotations)
            annotation['span'] = True
            annotation['targets'] = [ x.id for x in element.wrefs() ]
            annotation['spanroles'] = [ {'type':role.XMLTAG, 'words': [x.id for x in role.wrefs()]} for role in element.select(folia.AbstractSpanRole) ]
            annotation['layerparent'] = element.ancestor(folia.AbstractAnnotationLayer).ancestor(folia.AbstractStructureElement).id
            assert isinstance(annotation, dict)
            yield annotation
        if isinstance(element, folia.AbstractStructureElement) and element is not bookkeeper.stopat:
            annotation =  element.json(recurse=False)
            annotation['self'] = True #this describes the structure element itself rather than an annotation under it
            annotation['targets'] = [ element.id ]
            if isinstance(element, folia.Word):
                prevword = element.previous(folia.Word,None)
                if prevword:
                    annotation['previousword'] =  prevword.id
                else:
                    annotation['previousword'] = None
                nextword = element.next(folia.Word,None )
                if nextword:
                    annotation['nextword'] =  nextword.id
                else:
                    annotation['nextword'] = None
            yield annotation
        if isinstance(element, folia.AbstractStructureElement) or isinstance(element, folia.AbstractAnnotationLayer) or isinstance(element, folia.AbstractSpanAnnotation) or isinstance(element, folia.Suggestion):
            for child in element:
                if child is bookkeeper.stopat:
                    bookkeeper.stop = True
                if bookkeeper.stop:
                    break
                else:
                    for x in getannotations(child,bookkeeper):
                        assert isinstance(x, dict)
                        yield x

def getdeclarations(doc):
    for annotationtype, set in doc.annotations:
        try:
            C = folia.ANNOTATIONTYPE2CLASS[annotationtype]
        except KeyError:
            pass
        #if (issubclass(C, folia.AbstractAnnotation) or C is folia.TextContent or C is folia.Correction) and not (issubclass(C, folia.AbstractTextMarkup)): #rules out structure elements for now
        if not issubclass(C, folia.AbstractTextMarkup) and annotationtype in folia.ANNOTATIONTYPE2XML:
            annotationtype = folia.ANNOTATIONTYPE2XML[annotationtype]
            yield {'annotationtype': annotationtype, 'set': set}

def getsetdefinitions(doc):
    setdefs = {}
    for annotationtype, set in doc.annotations:
        if set in doc.setdefinitions:
            setdefs[set] = doc.setdefinitions[set].json()
    return setdefs
