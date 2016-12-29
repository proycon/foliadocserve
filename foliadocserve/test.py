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
        elif testname == "classchange_token":
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.1.w.2'].annotation(folia.LemmaAnnotation).cls,"mijn", testmessage + "Testing class", testresult)
        elif testname == "classchange_span":
            try:
                e = next( doc['untitleddoc.p.3.s.1.w.3'].findspans(folia.Chunk) )
                testmessage = "Obtaining chunk: Ok!\n"
            except StopIteration:
                testmessage = "Obtaining chunk: Failed!\n"
                testresult = False
            if testresult:
                testresult, testmessage = testequal(e.cls, 'X',  testmessage + "Testing class", testresult)
        elif testname == "textmerge":
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.1.w.14'].text(),"wegreden", testmessage + "Testing text", testresult)
        elif testname == "correction_textmerge":
            try:
                e = next( doc['untitleddoc.p.3.s.1'].select(folia.Correction) )
                testmessage = "Testing presence of new correction: Ok!\n"
            except StopIteration:
                testmessage = "Testing presence of new correction: Failed!\n"
                testresult = False
            if testresult:
                testresult, testmessage = testequal(e.text(),"wegreden", testmessage + "Testing text", testresult)
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
            if testresult:
                testresult, testmessage = testequal(e.cls,"per", testmessage + "Testing class of new entity", testresult)
                testresult, testmessage = testequal(len(e.wrefs()),2, testmessage + "Testing span size", testresult)
                testresult, testmessage = testequal(e.wrefs(0).id, 'untitleddoc.p.3.s.1.w.12' , testmessage + "Testing order (1/2)", testresult)
                testresult, testmessage = testequal(e.wrefs(1).id, 'untitleddoc.p.3.s.1.w.12b' , testmessage + "Testing order (2/2)", testresult)
        elif testname == "worddelete":
            testresult, testmessage = testequal('untitleddoc.p.3.s.8.w.10' in doc,False, testmessage + "Testing absence of word in index", testresult)
        elif testname == "wordsplit":
            testresult, testmessage = testequal('untitleddoc.p.3.s.12.w.5' in doc,False, testmessage + "Testing absence of original word in index", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.17'].text(),"4", testmessage + "Testing new word (1/2)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.18'].text(),"uur", testmessage + "Testing new word (2/2)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.17'].next().id,"untitleddoc.p.3.s.12.w.18", testmessage + "Testing order (1/2)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.4'].next().id,"untitleddoc.p.3.s.12.w.17", testmessage + "Testing order (2/2)", testresult)
        elif testname == "wordinsertionright":
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.1'].text(),"en", testmessage + "Testing original word", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.17'].text(),"we", testmessage + "Testing new word", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.1'].next().id,"untitleddoc.p.3.s.12.w.17", testmessage + "Testing order", testresult)
        elif testname == "wordinsertionleft":
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.13.w.12'].text(),"hoorden", testmessage + "Testing original word", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.13.w.16'].text(),"we", testmessage + "Testing new word", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.13.w.16'].next().id,"untitleddoc.p.3.s.13.w.12", testmessage + "Testing order", testresult)
        elif testname in ("spanchange","spanclasschange"):
            try:
                e = next( doc['untitleddoc.p.3.s.9'].select(folia.Entity) )
                testmessage = "Testing presence of new entity: Ok!\n"
            except StopIteration:
                testmessage = "Testing presence of new entity: Failed!\n"
                testresult = False
            if testresult:
                testresult, testmessage = testequal(len(e.wrefs()),3, testmessage + "Testing span size", testresult)
                testresult, testmessage = testequal(e.wrefs(0).id, 'untitleddoc.p.3.s.9.w.7' , testmessage + "Testing order (1/3)", testresult)
                testresult, testmessage = testequal(e.wrefs(1).id, 'untitleddoc.p.3.s.9.w.8' , testmessage + "Testing order (2/3)", testresult)
                testresult, testmessage = testequal(e.wrefs(2).id, 'untitleddoc.p.3.s.9.w.9' , testmessage + "Testing order (3/3)", testresult)
            if testname == "spanclasschange":
                testresult, testmessage = testequal(e.cls, "org", testmessage + "Testing class", testresult)
        elif testname in ( "newoverlapspan", "correction_newoverlapspan"):
            gen =  doc['untitleddoc.p.3.s.9'].select(folia.Entity)
            try:
                e = next(gen)
                e2 = next(gen)
                testmessage = "Testing presence of new entities: Ok!\n"
            except StopIteration:
                testmessage = "Testing presence of new entities: Failed!\n"
                testresult = False
            if testresult:
                testresult, testmessage = testequal(len(e.wrefs()),2, testmessage + "Testing original span size", testresult)
                testresult, testmessage = testequal(e.wrefs(0).id, 'untitleddoc.p.3.s.9.w.8' , testmessage + "Testing original entity", testresult)
                testresult, testmessage = testequal(len(e2.wrefs()),3, testmessage + "Testing extra span size", testresult)
                testresult, testmessage = testequal(e2.wrefs(0).id, 'untitleddoc.p.3.s.9.w.7' , testmessage + "Testing extra entity", testresult)
        elif testname in ( "spandeletion"):
            try:
                e = next( doc['untitleddoc.p.3.s.9'].select(folia.Entity) )
                testmessage = "Testing absence of entity: Failed!\n"
                testresult = False
            except StopIteration:
                testmessage = "Testing absence of entity: Ok!\n"
                testresult = True
        elif testname in ( "tokenannotationdeletion", "correction_tokenannotationdeletion"):
            exceptionraised = False
            try:
                doc['untitleddoc.p.3.s.8.w.4'].lemma()
            except folia.NoSuchAnnotation:
                exceptionraised = True
            testresult, testmessage = testequal(exceptionraised,True, testmessage + "Testing absence of lemma", testresult)
        elif testname ==   "correction_worddelete":
            try:
                e = next( doc['untitleddoc.p.3.s.8'].select(folia.Correction) )
                testmessage = "Testing presence of new correction: Ok!\n"
            except StopIteration:
                testmessage = "Testing presence of new correction: Failed!\n"
                testresult = False
            testresult, testmessage = testequal(e.original(0).id, 'untitleddoc.p.3.s.8.w.10',  testmessage + "Testing whether original word is now under original in correction", testresult)
        elif testname ==  "correction_wordsplit":
            try:
                e = next( doc['untitleddoc.p.3.s.12'].select(folia.Correction) )
                testmessage = "Testing presence of new correction: Ok!\n"
            except StopIteration:
                testmessage = "Testing presence of new correction: Failed!\n"
                testresult = False
            #entity ID will be different!
            if testresult:
                testresult, testmessage = testequal(e.original(0).id, 'untitleddoc.p.3.s.12.w.5',  testmessage + "Testing whether original word is now under original in correction", testresult)
            testresult, testmessage = testequal(e.new(0).text(),"4", testmessage + "Testing new word (1/2)", testresult)
            testresult, testmessage = testequal(e.new(1).text(),"uur", testmessage + "Testing new word (2/2)", testresult)
            testresult, testmessage = testequal(e.new(0).next().id,e.new(1).id, testmessage + "Testing order (1/2)", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.4'].next().id,e.new(0).id, testmessage + "Testing order (2/2)", testresult)
        elif testname == "correction_wordinsertionright":
            try:
                e = next( doc['untitleddoc.p.3.s.12'].select(folia.Correction) )
                testmessage = "Testing presence of new correction: Ok!\n"
            except StopIteration:
                testmessage = "Testing presence of new correction: Failed!\n"
                testresult = False
            if testresult:
                testresult, testmessage = testequal(e.new(0).text(),"we", testmessage + "Testing word presence and text", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.12.w.1'].next().text(),"we", testmessage + "Testing order", testresult)
        elif testname == "correction_wordinsertionleft":
            try:
                e = next( doc['untitleddoc.p.3.s.13'].select(folia.Correction) )
                testmessage = "Testing presence of new correction: Ok!\n"
            except StopIteration:
                testmessage = "Testing presence of new correction: Failed!\n"
                testresult = False
            if testresult:
                testresult, testmessage = testequal(e.new(0).text(),"we", testmessage + "Testing word presence and text", testresult)
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.13.w.12'].previous().text(),"we", testmessage + "Testing order", testresult)
        elif testname == "correction_spanchange":
            try:
                e = next( doc['untitleddoc.p.3.s.9'].select(folia.Correction) )
                testmessage = "Testing presence of new correction: Ok!\n"
            except StopIteration:
                testmessage = "Testing presence of new correction: Failed!\n"
                testresult = False
            if testresult:
                try:
                    e2 = next(e.select(folia.Entity) )
                    testmessage = "Testing presence of corrected entity: Ok!\n"
                except StopIteration:
                    testmessage = "Testing presence of corrected entity: Failed!\n"
                    testresult = False
                testresult, testmessage = testequal(e.original(0).id, 'untitleddoc.p.3.s.9.entity.1',  testmessage + "Testing whether original span is now under original in correction", testresult)
                testresult, testmessage = testequal(len(e2.wrefs()),3, testmessage + "Testing span size", testresult)
                testresult, testmessage = testequal(e2.wrefs(0).id, 'untitleddoc.p.3.s.9.w.7' , testmessage + "Testing order (1/3)", testresult)
                testresult, testmessage = testequal(e2.wrefs(1).id, 'untitleddoc.p.3.s.9.w.8' , testmessage + "Testing order (2/3)", testresult)
                testresult, testmessage = testequal(e2.wrefs(2).id, 'untitleddoc.p.3.s.9.w.9' , testmessage + "Testing order (3/3)", testresult)
        elif testname ==  "correction_spandeletion":
            try:
                e = next( doc['untitleddoc.p.3.s.9'].select(folia.Correction) )
                testmessage = "Testing presence of new correction: Ok!\n"
            except StopIteration:
                testmessage = "Testing presence of new correction: Failed!\n"
                testresult = False
            if testresult:
                testresult, testmessage = testequal(e.original(0).id, 'untitleddoc.p.3.s.9.entity.1',  testmessage + "Testing whether original span is now under original in correction", testresult)
        elif testname ==  "comment_span":
            try:
                e = next( doc['untitleddoc.p.3.s.1.w.3'].findspans(folia.Chunk) )
                testmessage = "Obtaining chunk: Ok!\n"
            except StopIteration:
                testmessage = "Obtaining chunk: Failed!\n"
                testresult = False
            if testresult:
                try:
                    comment = e.annotation(folia.Comment)
                    testmessage = "Testing presence of new comment: Ok!\n"
                except:
                    testmessage = "Testing presence of new comment: Failed!\n"
                    testresult = False
                if testresult:
                    testresult, testmessage = testequal(comment.value, "This is a comment", testmessage+ "Testing comment value", testresult)
        elif testname == "confidence_set":
            lemma = doc['untitleddoc.p.3.s.1.w.3'].annotation(folia.LemmaAnnotation)
            testresult, testmessage = testequal(lemma.confidence, 0.88,  testmessage + "Testing confidence value", testresult)
        elif testname == "confidence_unset":
            try:
                e = next( doc['untitleddoc.p.3.s.1.w.3'].findspans(folia.Chunk) )
                testmessage = "Obtaining chunk: Ok!\n"
            except StopIteration:
                testmessage = "Obtaining chunk: Failed!\n"
                testresult = False
            if testresult:
                testresult, testmessage = testequal(e.confidence, None,  testmessage + "Testing absence of confidence value", testresult)
        elif testname == "confidence_edit":
            try:
                e = next( doc['untitleddoc.p.3.s.1.w.3'].findspans(folia.Chunk) )
                testmessage = "Obtaining chunk: Ok!\n"
            except StopIteration:
                testmessage = "Obtaining chunk: Failed!\n"
                testresult = False
            if testresult:
                testresult, testmessage = testequal(e.confidence, 0.88,  testmessage + "Testing confidence value", testresult)
        elif testname ==  "feature_edit":
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.1.w.11'].annotation(folia.PosAnnotation).feat('head'),"ADJX", testmessage + "Testing feature", testresult)
        elif testname ==  "feature_edit2":
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.1.w.11'].annotation(folia.PosAnnotation).feat('headX'),"ADJX", testmessage + "Testing feature", testresult)
        elif testname ==  "feature_add":
            testresult, testmessage = testequal(doc['untitleddoc.p.3.s.1.w.11'].annotation(folia.PosAnnotation).feat('testsubset'),"testvalue", testmessage + "Testing feature", testresult)
        elif testname ==  "feature_delete":
            try:
                doc['untitleddoc.p.3.s.1.w.11'].annotation(folia.PosAnnotation).feat('head')
                testresult = False
            except folia.NoSuchAnnotation:
                pass
            if testresult:
                testresult, testmessage = testequal(testresult, True,  testmessage + "Testing absence of feature", testresult)
        elif testname ==  "spanrole_respan":
            dependency = doc['untitleddoc.p.3.s.1.dependencies.1.dependency.10']
            testresult, testmessage = testequal(list(dependency.annotation(folia.Headspan).wrefs()), [ doc['untitleddoc.p.3.s.1.w.12'], doc['untitleddoc.p.3.s.1.w.12b'] ], testmessage + "Testing spanrole span", testresult )
        elif testname ==  "spanrole_delete":
            dependency = doc['untitleddoc.p.3.s.1.dependencies.1.dependency.10']
            testresult, testmessage = testequal(len(dependency), 1 , testmessage + "Testing only one child remains", testresult )
            testresult, testmessage = testequal(dependency[0].__class__, folia.DependencyDependent, testmessage + "Testing child is not the head", testresult )
        elif testname ==  "dependency_add":
            dependency = doc['untitleddoc.p.3.s.15.w.3']
            l = list(doc['untitleddoc.p.3.s.15.w.3'].findspans(folia.Dependency))
            testresult, testmessage = testequal(len(l), 2, testmessage + "Testing number of dependencies on targets word", testresult )
            testresult, testmessage = testequal(l[0].cls, "obj1", testmessage + "Testing already existing dependency class", testresult )
            testresult, testmessage = testequal(l[1].cls, "crd", testmessage + "Testing new dependency class", testresult )
            testresult, testmessage = testequal(l[1].annotation(folia.Headspan).wrefs() , [doc['untitleddoc.p.3.s.15.w.3']], testmessage + "Testing headspan", testresult )
            testresult, testmessage = testequal(l[1].annotation(folia.DependencyDependent).wrefs() , [doc['untitleddoc.p.3.s.15.w.1']], testmessage + "Testing dependent", testresult )
        elif testname == "syntax_add":
            dependency = doc['untitleddoc.p.3.s.15.w.1']
            l = list(doc['untitleddoc.p.3.s.15.w.1'].findspans(folia.SyntacticUnit))
            testresult, testmessage = testequal(len(l), 1, testmessage + "Testing number of syntactic units on targets word", testresult )
            testresult, testmessage = testequal(l[0].cls, "s", testmessage + "Testing class", testresult )
            testresult, testmessage = testequal(l[0].wrefs() , [doc['untitleddoc.p.3.s.15.w.1'],doc['untitleddoc.p.3.s.15.w.2'],doc['untitleddoc.p.3.s.15.w.3'],doc['untitleddoc.p.3.s.15.w.4'],doc['untitleddoc.p.3.s.15.w.5']], testmessage + "Testing span", testresult )
        else:
            testresult = False
            testmessage += "No such test: " + testname
    except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            formatted_lines = traceback.format_exc().splitlines()
            testresult = False
            testmessage += "Test raised Exception in backend: " + str(e) + " -- " "\n".join(formatted_lines)


    return (testresult, testmessage)
