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
    return args

def parseresults(results, doc, **kwargs):
    response = {}
    if 'declarations' in kwargs and kwargs['declarations']:
        response['declarations'] = tuple(getdeclarations(doc))
    if 'setdefinitions' in kwargs and kwargs['setdefinitions']:
        response['setdefinitions'] =  getsetdefinitions(doc)

    if results:
        response['elements'] = []
    for queryresults in results: #results are grouped per query, we don't care about the origin now
        for element in queryresults:
            if isinstance(element,fql.SpanSet):
                for e in element:
                    response['elements'].append({
                        'elementid': e.id if e.id else None,
                        'html': gethtml(e) if isinstance(e, folia.AbstractStructureElement) else None,
                        'annotations': list(getannotations(e)),
                    })
            else:
                response['elements'].append({
                    'elementid': element.id if element.id else None,
                    'html': gethtml(element) if isinstance(element, folia.AbstractStructureElement) else None,
                    'annotations': list(getannotations(element)),
                })
    return json.dumps(response).encode('utf-8')

def gethtmltext(element):
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
        return gethtmltext(element.textcontent()) #only explicit text!




def gethtml(element):
    """Converts the element to html skeleton"""
    if isinstance(element, folia.Correction):
        s = ""
        if element.hasnew():
            for child in element.new():
                if isinstance(child, folia.AbstractStructureElement) or isinstance(child, folia.Correction):
                    s += gethtml(child)
        elif element.hascurrent():
            for child in element.current():
                if isinstance(child, folia.AbstractStructureElement) or isinstance(child, folia.Correction):
                    s += gethtml(child)
        return s
    elif isinstance(element, folia.AbstractStructureElement):
        s = ""
        for child in element:
            if isinstance(child, folia.AbstractStructureElement) or isinstance(child, folia.Correction):
                s += gethtml(child)
        try:
            label = "<span class=\"lbl\">" + gethtmltext(element) + "</span>" #only when text is expliclity associated with the element
        except folia.NoSuchText:
            label = ""
        if not isinstance(element,folia.Word) or (isinstance(element, folia.Word) and element.space):
            label += " "

        if not element.id:
            element.id = element.doc.id + "." + element.XMLTAG + ".id" + str(random.randint(1000,999999999))
        if s:
            s = "<div id=\"" + element.id + "\" class=\"F " + element.XMLTAG + "\">" + label + s
        else:
            s = "<div id=\"" + element.id + "\" class=\"F " + element.XMLTAG + " deepest\">" + label
        if isinstance(element, folia.Linebreak):
            s += "<br />"
        if isinstance(element, folia.Whitespace):
            s += "<br /><br />"
        elif isinstance(element, folia.Figure):
            s += "<img src=\"" + element.src + "\">"
        s += "</div>"
        if isinstance(element, folia.List):
            s = "<ul>" + s + "</ul>"
        elif isinstance(element, folia.ListItem):
            s = "<li>" + s + "</li>"
        elif isinstance(element, folia.Table):
            s = "<table>" + s + "</table>"
        elif isinstance(element, folia.Row):
            s = "<tr>" + s + "</tr>"
        elif isinstance(element, folia.Cell):
            s = "<td>" + s + "</td>"
        return s
    else:
        raise Exception("Structure element expected, got " + str(type(element)))

def getannotations(element, previouswordid = None):
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
                for y in  getannotations(x):
                    if not 'incorrection' in y: y['incorrection'] = []
                    y['incorrection'].append(element.id)
                    correction_new.append(y)
                    yield y #yield as any other
        if element.hascurrent():
            for x in element.current():
                for y in  getannotations(x):
                    if not 'incorrection' in y: y['incorrection'] = []
                    y['incorrection'].append(element.id)
                    correction_current.append(y)
                    yield y #yield as any other
        if element.hasoriginal():
            for x in element.original():
                for y in  getannotations(x):
                    y['auth'] = False
                    if not 'incorrection' in y: y['incorrection'] = []
                    y['incorrection'].append(element.id)
                    correction_original.append(y)
        if element.hassuggestions():
            for x in element.suggestions():
                for y in  getannotations(x):
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
    elif isinstance(element, folia.AbstractTokenAnnotation) or isinstance(element,folia.TextContent):
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
        annotation = element.json()
        annotation['span'] = True
        annotation['targets'] = [ x.id for x in element.wrefs() ]
        assert isinstance(annotation, dict)
        yield annotation
    if isinstance(element, folia.AbstractStructureElement):
        annotation =  element.json(None, False) #no recursion
        annotation['self'] = True #this describes the structure element itself rather than an annotation under it
        annotation['targets'] = [ element.id ]
        yield annotation
    if isinstance(element, folia.AbstractStructureElement) or isinstance(element, folia.AbstractAnnotationLayer) or isinstance(element, folia.AbstractSpanAnnotation) or isinstance(element, folia.Suggestion):
        for child in element:
            for x in getannotations(child, previouswordid):
                assert isinstance(x, dict)
                if previouswordid and not 'previousword' in x:
                    x['previousword'] = previouswordid
                yield x
            if isinstance(child, folia.Word):
                previouswordid = child.id

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
