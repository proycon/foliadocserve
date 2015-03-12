import sys
import traceback
from pynlpl.formats import folia

def testequal(value, reference, testmessage,testresult=True):
    if value == reference:
        testmessage = testmessage + ": Ok!\n"
        if testresult:
            testresult = True
    else:
        testmessage = testmessage + ": Failed! Value \"" + str(value) + "\" does not match reference \"" + str(reference) + "\"\n"
        testresult = False
    return testresult, testmessage

def test(doc, testname, testmessage = ""):

    #load clean document
    #perform test
    testresult = True #must start as True for chaining
    try:
        if testname in ( "textchange", "correction_textchange"):
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.1.w.2'].text(),"mijn", testmessage + "Testing text", testresult)
        elif testname in ( "textmerge","correction_textmerge"):
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.1.w.14'].text(),"wegreden", testmessage + "Testing text", testresult)
        elif testname in ("multiannotchange"):
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.6.w.8'].text(),"het", testmessage + "Testing text", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.6.w.8'].pos(),"LID(onbep,stan,rest)", testmessage + "Testing pos class", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.6.w.8'].lemma(),"het", testmessage + "Testing lemma class", testresult)
        elif testname in ("correction_tokenannotationchange"):
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.6.w.8'].pos(),"LID(onbep,stan,rest)", testmessage + "Testing pos class", testresult)
        elif testname in ("addentity", "correction_addentity"):
            try:
                e = next( doc['untitleddoc.p.3.s.1'].select(folia.Entity) )
                testmessage = "Testing presence of new entity: Ok!\n"
            except StopIteration:
                testmessage = "Testing presence of new entity: Failed!\n"
                testresult = False
            testresult, testmessage = testequal(e.cls,"per", testmessage + "Testing class of new entity", testresult)
            testresult, testmessage = testequal(len(e.wrefs()),2, testmessage + "Testing span size", testresult)
            testresult, testmessage = testequal(e.wrefs(0).id, 'untitleddoc.p.3.s.1.w.12' , testmessage + "Testing order (1/2)", testresult)
            testresult, testmessage = testequal(e.wrefs(1).id, 'untitleddoc.p.3.s.1.w.12b' , testmessage + "Testing order (2/2)", testresult)
        elif testname in  ("worddelete"):
            testresult, testmessage = testequal('untitleddoc.p.3.s.8.w.10' in doc,False, testmessage + "Testing absence of word in index", testresult)
        elif testname in ( "wordsplit"):
            testresult, testmessage = testequal('untitleddoc.p.3.s.12.w.5' in doc,False, testmessage + "Testing absence of original word in index", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.18'].text(),"4", testmessage + "Testing new word (1/2)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.17'].text(),"uur", testmessage + "Testing new word (2/2)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.18'].next().id,"untitleddoc.p.3.s.12.w.17", testmessage + "Testing order (1/2)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.4'].next().id,"untitleddoc.p.3.s.12.w.18", testmessage + "Testing order (2/2)", testresult)
        elif testname in ("wordinsertionright", "correction_wordinsertionright"):
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.1'].text(),"en", testmessage + "Testing original word", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.17'].text(),"we", testmessage + "Testing new word", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.1'].next().id,"untitleddoc.p.3.s.12.w.17", testmessage + "Testing order", testresult)
        elif testname in ("wordinsertionleft", "correction_wordinsertionleft"):
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.13.w.12'].text(),"hoorden", testmessage + "Testing original word", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.13.w.16'].text(),"we", testmessage + "Testing new word", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.13.w.16'].next().id,"untitleddoc.p.3.s.13.w.12", testmessage + "Testing order", testresult)
        elif testname in ("spanchange"):
            testresult, testmessage = testequal(len(doc['untitleddoc.p.3.s.9.entity.1'].wrefs()),3, testmessage + "Testing span size", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.9.entity.1'].wrefs(0).id, 'untitleddoc.p.3.s.9.w.7' , testmessage + "Testing order (1/3)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.9.entity.1'].wrefs(1).id, 'untitleddoc.p.3.s.9.w.8' , testmessage + "Testing order (2/3)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.9.entity.1'].wrefs(2).id, 'untitleddoc.p.3.s.9.w.9' , testmessage + "Testing order (3/3)", testresult)
        elif testname in ( "newoverlapspan", "correction_newoverlapspan"):
            testresult, testmessage = testequal(len(doc['untitleddoc.p.3.s.9.entity.1'].wrefs()),2, testmessage + "Testing original span size", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.9.entity.1'].wrefs(0).id, 'untitleddoc.p.3.s.9.w.8' , testmessage + "Testing original entity", testresult)
            testresult, testmessage = testequal(len(doc['untitleddoc.p.3.s.9.entity.2'].wrefs()),3, testmessage + "Testing extra span size", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.9.entity.2'].wrefs(0).id, 'untitleddoc.p.3.s.9.w.7' , testmessage + "Testing extra entity", testresult)
        elif testname in ( "spandeletion"):
            testresult, testmessage = testequal('untitleddoc.p.3.s.9.entity.1' in doc,False, testmessage + "Testing absence of entity in index", testresult)
        elif testname in ( "tokenannotationdeletion", "correction_tokenannotationdeletion"):
            exceptionraised = False
            try:
                doc['untitleddoc.p.3.s.8.w.4'].lemma()
            except folia.NoSuchAnnotation:
                exceptionraised = True
            testresult, testmessage = testequal(exceptionraised,True, testmessage + "Testing absence of lemma", testresult)
        elif testname in  ("correction_worddelete"):
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.8.correction.1'].original(0).id, 'untitleddoc.p.3.s.8.w.10',  testmessage + "Testing whether original word is now under original in correction", testresult)
        elif testname in ( "correction_wordsplit"):
            #entity ID will be different!
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.correction.1'].original(0).id, 'untitleddoc.p.3.s.12.w.5',  testmessage + "Testing whether original word is now under original in correction", testresult)

            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.17'].text(),"4", testmessage + "Testing new word (1/2)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.18'].text(),"uur", testmessage + "Testing new word (2/2)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.17'].next().id,"untitleddoc.p.3.s.12.w.18", testmessage + "Testing order (1/2)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.4'].next().id,"untitleddoc.p.3.s.12.w.17", testmessage + "Testing order (2/2)", testresult)
        elif testname in ( "correction_wordinsertionright", "correction_wordinsertionleft"):
            pass
        elif testname in ("correction_spanchange"):
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.9.correction.1'].original(0).id, 'untitleddoc.p.3.s.9.entity.1',  testmessage + "Testing whether original span is now under original in correction", testresult)
            testresult, testmessage = testequal(len(doc['untitleddoc.p.3.s.9.entity.2'].wrefs()),3, testmessage + "Testing span size", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.9.entity.2'].wrefs(0).id, 'untitleddoc.p.3.s.9.w.7' , testmessage + "Testing order (1/3)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.9.entity.2'].wrefs(1).id, 'untitleddoc.p.3.s.9.w.8' , testmessage + "Testing order (2/3)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.9.entity.2'].wrefs(2).id, 'untitleddoc.p.3.s.9.w.9' , testmessage + "Testing order (3/3)", testresult)
        elif testname in ( "correction_spandeletion"):
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.9.correction.1'].original(0).id, 'untitleddoc.p.3.s.9.entity.1',  testmessage + "Testing whether original span is now under original in correction", testresult)
        else:
            testresult = False
            testmessage += "No such test: " + testname
    except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            formatted_lines = traceback.format_exc().splitlines()
            testresult = False
            testmessage += "Test raised Exception in backend: " + str(e) + " -- " "\n".join(formatted_lines)


    return (testresult, testmessage)
