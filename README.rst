**NOTE: This documentation describes a newer version than currently implemented!!**
 
*****************************************
FoLiA Document Server
*****************************************

The FoLiA Document Server is a backend HTTP service to interact with documents
in the FoLiA format, a rich XML-based format for linguistic annotation
(http://proycon.github.io/folia). It provides an interface to efficiently edit
FoLiA documents through the FoLiA Query Language (FQL).  However, it is not
designed as a multi-document search tool.

The FoLiA Document server is used by FLAT (https://github.com/proycon/flat)

The FoLiA Document Server is written in Python 3, using the FoLiA library in
pynlpl and cherrypy.


============================================
Architecture
============================================

The FoLiA Document Server consists of a document store that groups documents
into namespaces, a namespace can correspond for instance to a user ID or a
project. 

Documents are automatically loaded and unloaded as they are requested and
expire. Loaded documents are kept in memory fully to facilitate rapid access
and are serialised back to XML files on disk when unloaded.

The document server is a webservice that receives requests over HTTP. Requests
interacting with a FoLiA document consist of statements in FoLiA Query Language
(FQL). Responses are FoLiA XML or parsed into JSON (may contain HTML excerpts
too), as requested by the queries themselves.

Features:

* versioning control support using git
* full support for corrections, alternatives
* support for concurrency 
* usable from the command line as well as as a webservice

Note that this webservice is *NOT* intended to be publicly exposed, but rather
to be used as a back-end by another system. The document server does support
constraining namespaces to certain session ids, constraining FQL queries to not
violate their namespace, and constraining uploads by session id or namespace.
This is secure for public exposure only when explicitly enabled and used over
HTTPS.

=========================================
Webservice Specification
=========================================

Common variables in request URLs:

* **namespace** - A group identifier
* **docid** - The FoLiA document ID
* **sessionid** - A session ID, can be set to ``NOSID`` if no sessioning is
   desired. Usage of session IDs enable functionality such as caching and
   concurrency.

---------------------------
Querying & Annotating
---------------------------

* ``/query/<namespace>/`` (POST) - Content body consists of FQL queries, one per line (text/plain). The request header may contain ``X-sessionid``.
* ``/query/<namespace>/?query=`` (GET) -- HTTP GET alias for the above, limited to a single query

These URLs will return HTTP 200 OK, with data in the format as requested in the FQL
query if the query is succesful. If the query contains an error, an HTTP 404 response
will be returned. 

-------------
Versioning
-------------

* ``/getdochistory/<namespace>/<docid>`` (GET) - Obtain the git history for the specified document. Returns a JSON response:  ``{'history':[ {'commit': commithash, 'msg': commitmessage, 'date': commitdata } ] }``
* ``/revert/<namespace>/<docid>/<commithash>`` (GET) - Revert the document's state to the specified commit hash

---------------------------
Document Management
---------------------------

* ``/namespaces/`` (GET) -- List of all the namespaces
* ``/index/<namespace>/`` (GET) -- Document Index for the given namespace (JSON list)
* ``/upload/<namespace>/`` (POST) -- Uploads a FoLiA XML document to a namespace, request body contains FoLiA XML.


========================================
FoLiA Query Language (FQL)
========================================

FQL statements are separated by newlines and encoded in UTF-8. The expressions
are case sensitive, all keywords are in upper case, all element names and
attributes in lower case.

As a general rule, it is more efficient to do a single big query than multiple
standalone queries.

-------------------
Global variables
-------------------

* ``SET <variable>=<value>`` - Sets global variables that apply to all statements that follow. String values need to be in double quotes. Available variables are:
* **annotator** - The name of the annotator 
* **annotatortype** - The type of the annotator, can be *auto* or *manual* 

Usually your queries on a particular annotation type are limited to one
specific set. To prevent having to enter the set explicitly in your queries,
you can set defaults. The annotation type corresponds to a FoLiA element::

 DEFAULTSET entity https://raw.githubusercontent.com/proycon/folia/master/setdefinitions/namedentitycorrection.foliaset.xml

If the FoLiA document only has one set of that type anyway, then this is not even
necessary and the default will be automatically set.

-------------------
Document Selection
-------------------

Almost FQL statements start with a document selector, represented by the
keyword **USE**::

 USE <namespace>/<docid> 

This select what document to apply the query to, the document will be
automatically loaded and unloaded by the server as it sees fit. It can be
prepended to any action query or used standalone, in which case it will apply o
all subsequent queries.

Alternatively, the **LOAD** statement loads an arbitrary file from disk, but its use
is restricted to the command line version::

 LOAD <filename> 

---------
Actions
---------

The core part of an FQL statement consists of an action verb, the following are
available

* ``SELECT <actor expression> [<target expression>]`` - Selects an annotation
* ``DELETE <actor expression> [<target expression>]`` - Deletes an annotation
* ``EDIT <actor expression> [<assignment expression>] [<target expression>]`` - Edits an existing annotation
* ``ADD <actor expression> <assignment expression> <target expression>`` - Adds an annotation

Following the action verb is the actor expression, this starts with an
annotation type, which is equal to the FoLiA XML element tag. The set is
specified using ``OF <set>`` and/or the ID with ``ID <id>``. An example:

 pos OF "http://some.domain/some.folia.set.xml"

If an annotation type is already declared and there is only one in document, or
if the **DEFAULTSET** statement was used earlier, then the **OF** statement can
be omitted and will be implied and detected automatically. If it is ambiguous,
an error will be raised (rather than applying the query regardless of set).

To further filter a the actor, the expression may consist of a **WHERE** clause
that filters on one or more FoLiA attributes:

* **class**
* **annotator**
* **annotatortype**
* **n**
* **confidence**

The following attribute is also available on when the elements contains text:

* **text**

The **WHERE** statement requires an operator (=,!=,>,<,<=,>=,CONTAINS,MATCHES), the **AND**,
**OR** and **NOT** operators are available (along with parentheses) for
grouping and boolean logic. The operators must never be glued to the attribute
name or the value, but have spaces left and right.

We can now show some examples of full queries with some operators:

* ``SELECT pos OF "http://some.domain/some.folia.set.xml"``
* ``SELECT pos WHERE class = "n" AND annotator = "johndoe"``
* ``DELETE pos WHERE class = "n" AND annotator != "johndoe"``
* ``DELETE pos WHERE class = "n" AND annotator CONTAINS "john"``
* ``DELETE pos WHERE class = "n" AND annotator MATCHES "^john$"``

The **ADD** and **EDIT** change actual attributes, this is done in the
*assignment expression* that starts with the **WITH** keyword. It applies to
all the common FoLiA attributes like the *WHERE* keyword, but has no operator or
boolean logic, as it is a pure assignment function.

SELECT and DELETE only support WHERE, EDIT supports both WHERE and WITH, and
ADD supports only WITH. If an EDIT is done on an annotation that can not be
found, and there is no WHERE clause, then it will fall back to ADD.

Here is an **EDIT** query that changes all nouns in the document to verbs::

 EDIT pos WHERE class = "n" WITH class "v" AND annotator = "johndoe"

The query is fairly crude as it still lacks a *target expression*: A *target
expression* determines what elements the actor is applied to, rather than to
the document as a whole, it starts with the keyword **FOR** and is followed by
either an annotation type (i.e. a FoLiA XML element tag) *or* the ID of an
element. The target expression also determines what elements will be returned.
More on this in a later section.

The following FQL query shows how to get the part of speech tag for a
particular word::

 SELECT pos FOR mydocument.word.3 

Or for all words::

 SELECT pos FOR w

The **ADD** action almost always requires a target expression::

 ADD pos WITH class "n" FOR mydocument.word.3

Multiple targets may be specified, comma delimited::

 ADD pos WITH class "n" FOR mydocument.word.3 , myword.document.word.25

The target expression can again contain a **WHERE** filter::

 SELECT pos FOR w WHERE class != "PUNCT"

Target expressions, starting with the **FOR** keyword, can be nested::

 SELECT pos FOR w WHERE class != "PUNCT" FOR event WHERE class = "tweet"


Target expressions are vital for span annotation, the keyword **SPAN** indicates
that the target is a span (to do multiple spans at once, repeat the SPAN
keyword again), the operator ``&`` is used for consecutive spans, whereas ``,``
is used for disjoint spans::

 ADD entity WITH class "person" FOR SPAN mydocument.word.3 & myword.document.word.25 

This works with filters too, the ``&`` operator enforced a single consecutive span::

 ADD entity WITH class "person" FOR SPAN w WHERE text = "John" & w WHERE text = "Doe"

Remember we can do multiple at once::

 ADD entity WITH class "person" FOR SPAN w WHERE text = "John" & w WHERE text = "Doe" SPAN w WHERE text = "Jane" & w WHERE text = "Doe"

The **HAS** keyword enables you to descend down in the document tree to
siblings.  Consider the following example that changes the part of speech tag
to "verb", for all occurrences of words that have lemma "fly". The parentheses
are mandatory for a **HAS** statement::

 EDIT pos OF "someposset" WITH class = "v" FOR w WHERE (lemma OF "somelemmaset" HAS class "fly") 

Target expressions can be former with either **FOR** or with **IN**, the
difference is that **IN** is much stricter, the element has to be a direct
child of the element in the **IN** statement, whereas **FOR** may skip
intermediate elements. In analogy with XPath, **FOR** corresponds to ``//`` and
**IN** corresponds to ``/``. **FOR** and **IN** may be nested and mixed at
will. The following query would most likely not yield any results because there are
likely to be paragraphs and/or sentences between the wod and event structures::

 SELECT pos FOR w WHERE class != "PUNCT" IN event WHERE class = "tweet"


Multiple actions can be combined, all share the same target expressions::

 ADD pos WITH class "n" ADD lemma WITH class "house" FOR w WHERE text = "house" OR text = "houses"

It is also possible to nest actions, use parentheses for this::

 ADD w ID mydoc.sentence.1.word.1 (ADD t WITH text "house" ADD pos WITH class "n") FOR mydoc.sentence.1

Though explicitly specified here, IDs will be automatically generated when necessary and not specified.


---------
Text
---------

Our previous examples mostly focussed on part of speech annotation. In this
section we look at text content, which in FoLiA is an annotation element too
(t).

Here we change the text of a word::

 EDIT t WITH text = "house" FOR mydoc.word.45 

Here we edit or add (recall that EDIT falls back to ADD when not found and
there is no further selector) a lemma and check on text content::

 EDIT lemma WITH class "house" FOR w WHERE text = "house" OR text = "houses"


You can use WHERE text on all elements, it will cover both explicit text
content as well as implicit text content, i.e. inferred from child elements. If
you want to be really explicit you can do::

 EDIT lemma WITH class "house" FOR w WHERE (t HAS text = "house")


**Advanced**:

Such syntax is required when covering texts with custom classes, such as
OCRed or otherwise pre-normalised text. Consider the following OCR correction::

 ADD t WITH text = "spell" FOR w WHERE (t HAS text = "spe11" AND class = "OCR" )



---------------
Query Response
---------------

We have shown how to do queries but not yet said anything on how the response is
returned. This is regulated using the **RETURN** keyword:

* **RETURN actor** (default)
* **RETURN parent** - Returns the parent of the actor
* **RETURN target** or **RETURN inner-target**
* **RETURN outer-target**
* **RETURN ancestor-target**

The default actor mode just returns the actor. Sometimes, however, you may want
more context and may want to return the target expression instead. In the
following example returning only the pos-tag would not be so interesting, you
are most likely interested in the word to which it applies::

 SELECT pos WHERE class = "n" FOR w RETURN target

When there are nested FOR/IN loops, you can specify whether you want to return
the inner one (highest granularity, default) or the outer one (widest scope).
You can also decide to return the first common structural ancestor of the
(outer) targets, which may be specially useful in combination with the **SPAN**
keyword.

The return type can be set using the **FORMAT** statement:

* **FORMAT xml** - Returns FoLiA XML, the response is contained in a simple
   ``<results><result/></results>`` structure. 
* **FORMAT SINGLE xml** - Like above, but returns pure unwrapped FoLiA XML and
   therefore only works if the response only contains one element. An error
   will be raised otherwise.
* **FORMAT json** - Returns JSON list
* **FORMAT SINGLE json** - Like above, but returns a single element rather than
  a list. An error will be raised if the response contains multiple.
* **FORMAT flat** -  Returns a parsed format optimised for FLAT. This is a JSON reply
   containing an HTML skeleton of structure elements (key html), parsed annotations
   (key annotations). If the query returns a full FoLiA document, then the JSON object will include parsed set definitions, (key
   setdefinitions), and declarations.  
* **FORMAT python** - Returns a Python object, can only be used when
  directly querying the FQL library without the document server 

The **RETURN** statement may be used standalone or appended to a query, in
which case it applies to all subsequent queries. The same applies to the
**FORMAT** statement, though an error will be raised if distinct formats are
requested in the same HTTP request.

When context is returned in *target* mode, this can get quite big, you may
constrain the type of elements returned by using the **REQUEST** keyword, it
takes the names of FoLiA XML elements. It can be used standalone so it applies
to all subsequent queries::

 REQUEST w,t,pos,lemma

..or after a query::

 SELECT pos FOR w WHERE class!="PUNCT" FOR event WHERE class="tweet" REQUEST w,pos,lemma

Two special uses of request are ``REQUEST ALL`` (default) and ``REQUEST
NOTHING``, the latter may be useful in combination with **ADD**, **EDIT** and
**DELETE**, by default it will return the updated state of the document.
 
Note that if you set REQUEST wrong you may quickly end up with empty results.

---------------------
Span Annotation
---------------------

Selecting span annotations is identical to token annotation. You may be aware
that in FoLiA span annotation elements are technically stored in a separate
stand-off layers, but you forget this fact when composing FQL queries and can
access them right from the elements they apply to.

The following query selects all named entities (of an actual rather than a
fictitious set for a change) of people that have the name John::
 
 SELECT entity OF "https://github.com/proycon/folia/blob/master/setdefinitions/namedentities.foliaset.xml"
 WHERE class = "person" FOR w WHERE text = "John"

Or consider the selection of noun-phrase syntactic units (su) that contain the
word house::

 SELECT su WHERE class = "np" FOR w WHERE text CONTAINS "house"

Note that if the **SPAN** keyword were used here, the selection would be
exclusively constrained to single words "John"::

 SELECT entity WHERE class = "person" FOR SPAN w WHERE text = "John"

We can use that construct to select all people named John Doe for instance::

 SELECT entity WHERE class = "person" FOR SPAN w WHERE text = "John" & w WHERE text = "Doe"


 
Span annotations like syntactic units are typically nested trees, a tree query
such as "//pp/np/adj" can be represented as follows. Recall that the **IN**
statement starts a target expression like **FOR**, but is stricter on the
hierarchy, which is what we would want here::

 SELECT su WHERE class = "adj" IN su WHERE class = "np" IN su WHERE class = "pp"

In such instances we may be most interested in obtaining the full PP:: 

 SELECT su WHERE class = "adj" IN su WHERE class = "np" IN su WHERE class = "pp" RETURN outer-target
 



------------------------------
Corrections and Alternatives
------------------------------

Both FoLiA and FQL have explicit support for corrections and alternatives on
annotations. A correction is not a blunt substitute of an annotation of any
type, but the original is preserved as well. Similarly, an alternative
annotation is one that exists alongside the actual annotation of the same type
and set, and is not authoritative.

The following example is a correction but not in the FoLiA sense, it bluntly changes part-of-speech
annotation of all occurrences of the word "fly" from "n" to "v", for example to
correct erroneous tagger output::

 EDIT pos WITH class "v" WHERE class = "n" FOR w WHERE text = "fly"

Now we do the same but as an explicit correction::

 EDIT pos WITH class "v" WHERE class = "n" (AS CORRECTION OF "some/correctionset" WITH class = "wrongpos") FOR w WHERE text = "fly"

Another example in a spelling correction context, we correct the misspelling
*concous* to *conscious**::

 EDIT t WITH text "conscious" (AS CORRECTION OF "some/correctionset" WITH class = "spellingerror") FOR w WHERE text = "concous"

The **AS CORRECTION** keyword (always in a separate block within parentheses) is used to
initiate a correction. The correction is itself part of a set with a class that
indicates the type of correction.

Alternatives are simpler, but follow the same principle::

 EDIT pos WITH class "v" WHERE class = "n" (AS ALTERNATIVE) FOR w WHERE text = "fly"

Confidence scores are often associationed with alternatives::

 EDIT pos WITH class "v" WHERE class = "n" (AS ALTERNATIVE WITH confidence 0.6) FOR w WHERE text = "fly"

FoLiA does not just distinguish corrections, but also supports suggestions for
correction. Envision a spelling checker suggesting output for misspelled
words, but leaving it up to the user which of the suggestions to accept::

 EDIT t WITH text "conscious" (AS SUGGESTION OF "some/correctionset" WITH class = "spellingerror") FOR w WHERE text = "fly"


In the case of alternatives and suggestions, this syntax becomes inefficient if
you want to add muliple alternatives or suggestions at once, as you'd have to
repeat the query for each. Therefore, FQL allows you to omit the **WITH**
statement and replace it with the **ALTERNATIVE** or **SUGGEST** statement
within the **AS** clause.

An example for alternatives::

 EDIT pos WHERE class = "n" (AS ALTERNATIVE class "v" WITH confidence 0.6 ALTERNATIVE class "n" WITH confidence 0.4 ) FOR w WHERE text = "fly"

An example for suggestions for correction::

 EDIT pos WHERE class = "n" (AS CORRECTION OF "some/correctionset" WITH class = "wrongpos" SUGGEST class "v" WITH confidence 0.6 SUGGEST class "n" WITH confidence 0.4) FOR w WHERE text = "fly"

In a spelling correction context::

 EDIT t (AS CORRECTION OF "some/correctionset" WITH class = "spellingerror" SUGGEST text "conscious" WITH confidence 0.8 SUGGEST text "couscous" WITH confidence 0.2) FOR w WHERE text = "concous"


-------------------------------
I can haz context plz?
-------------------------------

We've seen that with the **FOR** keyword we can move to bigger elements in the FoLiA
document, and with the **HAS** keyword we can move to siblings. This **HAS**
keywords supports some modifiers that give us the tools we need to peek at the context. 

For instance, consider part-of-speech tagging scenario. If we have a word where the left neighbour is a determiner, and the
right neighbour a noun, we can be pretty sure the word under our consideration (our target expression) is an adjective. Let's add the pos tag::

 EDIT pos WITH class = "adj" FOR w WHERE (PREVIOUS w HAS pos WHERE class == "det") AND (NEXT w HAS pos WHERE class == "n")

You may append a number directly to the **PREVIOUS**/**NEXT** modifier if you're
interested in further context, or you may use **LEFTCONTEXT**/**RIGHTCONTEXT**/**CONTEXT** if you don't care at
what position something occurs::

 EDIT pos WITH class = "adj" FOR w WHERE (PREVIOUS2 w HAS pos WHERE class == "det") AND (PREVIOUS w HAS pos WHERE class == "adj") AND (RIGHTCONTEXT w HAS pos WHERE class == "n")

Ff you are now perhaps tempted to use the FoLiA document server and FQL for searching through
large corpora, then note that this is not a good idea. It will be prohibitively
slow on large datasets as this requires smart indexing, which this document
server does not provide.

Other modifiers are PARENT and and ANCESTOR. PARENT will at most go one element
up, whereas ANCESTOR will go on to the largest element::

 SELECT lemma FOR w WHERE (PARENT s HAS text CONTAINS "wine") 

Instead of **PARENT**, the use of a nested **FOR** is preferred and more efficient::

 SELECT lemma FOR w FOR s WHERE text CONTAINS "wine" 

Let's revisit syntax trees for a bit now we know how to obtain context. Imagine
we want an NP to the left of a PP::

 SELECT su WHERE class = "np" AND (NEXT su HAS class = "pp")

... and where the whole thing is part of a VP::

 SELECT su WHERE class = "np" AND (NEXT su HAS class = "pp") IN su WHERE class = "vp"

... and return that whole tree rather than just the NP we were looking for::

 SELECT su WHERE class = "np" AND (NEXT su HAS class = "pp") IN su WHERE class = "vp" RETURN target



