**NOTE: This documentation describes a newer version than currently implemented!!**
 
*****************************************
FoLiA Document Server
*****************************************

The FoLiA Document Server is a backend HTTP service to interact with documents
in the FoLiA format, a rich XML-based format for linguistic annotation
(http://proycon.github.io/folia). It provides an interface to efficiently edit
FoLiA documents through the FoLiA Query Language (FQL).  However, it is not
designed as a multi-document search tool.

The FoLiA Document server is used by FLAT (https://github.com/flat)

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
(FQL). Responses are FoLiA XML or parsed into JSON (may contain HTML excerpts too).

Features:

* versioning control support using git
* full support for corrections
* support for concurrency 


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

FQL statements are separated by newlines and encoded in UTF-8.

-------------------
Global vaiables
-------------------

* ``SET <variable>=<value>`` - Sets global variables that apply to all statements that follow. String values need to be in double quotes. Available variables are:
* **annotator** - The name of the annotator 
* **annotatortype** - The type of the annotator, can be *auto* or *manual* 

-------------------
Document Selection
-------------------

Almost FQL statements start with a document selector, represented by the
keyword **IN**::

    IN <namespace>/<docid> 

This select what document to apply the query to, the document will be
automatically loaded and unloaded by the server as it sees fit.

---------
Actions
---------

The next part of an FQL statement consists of an action verb, the following are
available

* ``<document selector> **SELECT** <actor expression> [<target expression>]`` - Selects an annotation
* ``<document selector> **DELETE** <actor expression> [<target expression>]`` - Deletes an annotation
* ``<document selector> **EDIT** <actor expression> [<target expression>]`` - Edits an existing annotation
* ``<document selector> **ADD** <actor expression> <target expression>`` - Adds an annotation

Following the action verb is the actor expression, this starts with an
annotation type, which is equal to the FoLiA XML element tag. The set is
specified using ``OF <set>`` and/or the ID with ``ID <id>``. An example:

 pos OF "http://some.domain/some.folia.set.xml"

If an annotation type is already declared and there is only one in document, the **OF**
statement can be omitted and will be implied and detected automatically. If it
is ambiguous, an error will be raised (rather than applying the query
regardless of set).

To further filter a the actor, the expression may consist of a **WHERE** clause
that filters on one or more FoLiA attributes:

* **class**
* **annotator**
* **annotatortype**
* **n**
* **confidence**

The following attribute is also available on when the elements contains text:

* **text**

The **WHERE** statement requires an operator (=,!=,>,<,<=,>=), the **AND**,
**OR** and **NOT** operators are available (along with parentheses) for
grouping and boolean logic.i

We can now show some examples of full queries:

* ``IN somegroup/mydoc SELECT pos OF "http://some.domain/some.folia.set.xml"``
* ``IN somegroup/mydoc SELECT pos WHERE class="n" AND annotator="johndoe"``
* ``IN somegroup/mydoc DELETE pos WHERE class="n" AND annotator!="johndoe"``

The **ADD** and **EDIT** change actual attributes, this is done using the
**WITH** keyword. It applies to all the common FoLiA attributes like the
WHERE keyword, but has no operator or boolean logic, as it is a pure
assignment function.

SELECT and DELETE only support WHERE, EDIT supports both WHERE and WITH, and
ADD supports only WITH.

Here is an EDIT query that changes all nouns in the document to verbs::

 IN somegroup/mydoc EDIT pos WITH class "v" WHERE class="n" AND annotator="johndoe"

The query is fairly crude as it still lacks a *target expression*: A *target
expression* determines what elements the actor is applied to, rather than to
the document as a whole, it starts with the keyword **FOR** and is followed by
either an annotation type (i.e. a FoLiA XML element tag) *or* the ID of an
element.

The following FQL query shows how to get the part of speech tag for a
particular word::

 IN somegroup/mydoc SELECT pos FOR mydocument.word.3 

Or for all words::

 IN somegroup/mydoc SELECT pos FOR w

The **ADD** action almost always requires a target expression::

 IN somegroup/mydoc ADD pos WITH class "n" FOR mydocument.word.3

Multiple targets may be specified, space delimited::

 IN somegroup/mydoc ADD pos WITH class "n" FOR mydocument.word.3 myword.document.word.25

The target expression can again contain a **WHERE** filter::

 IN somegroup/mydoc SELECT pos FOR w WHERE class!="PUNCT"

Target expressions, starting with the **FOR** keyword, can be nested::

 IN somegroup/mydoc SELECT pos FOR w WHERE class!="PUNCT" FOR event WHERE class="tweet"

Target expressions are vital for span annotation, they keyword **SPAN** indicates
that the target is a span (to do multiple spans at once, repeat the SPAN
keyword again)::

 IN somegroup/mydoc ADD entity WITH class "person" FOR SPAN mydocument.word.3 myword.document.word.25 

The **HAS** keyword enables you to descend down in the document tree to
siblings.  Consider the following example that changes the part of speech tag
to "verb", for all occurrences of words that have lemma "fly". The parentheses
are mandatory for a **HAS** statement::

 IN somegroup/mydoc EDIT pos OF "someposset" WITH class="v" FOR w WHERE (lemma OF "somelemmaset" HAS class "fly") 


---------------
Query Response
---------------

We have shown how to do queries but not yet said anything on how the response is
returned.

If there is a target expression, those will be the elements that are returned,
rather than the actor expression. This implies that you will always get
context, which is most often want you want.

If the target expression is a SPAN expression, then the structure element that
embeds the span will be returned, i.e. the first common structural ancestor of
the elements in the span selection.

The return type can be set using the **RETURN** keyword:

* **RETURN xml** - Returns FoLiA XML, the response is contained in a simple
   ``<results><result/></results>`` structure. 
* **RETURN SINGLE xml** - Like above, but returns pure unwrapped FoLiA XML and
   therefore only works if the response only contains one element. An error
   will be raised otherwise.
* **RETURN json** - Returns JSON list
* **RETURN SINGLE json** - Like above, but return a single element rather than
  a list. An error will be raised if the response contains multiple.
* **RETURN flat** -  Returns a parsed format optimised for FLAT. This is a JSON reply
   containing an HTML skeleton of structure elements (key html), parsed annotations
   (key annotations). If the query returns a full FoLiA document, then the JSON object will include parsed set definitions, (key
   setdefinitions), and declarations.  

As context is returns, this can be quite big, you may constrain the type of
elements returned by using the **REQUEST** keyword, it takes the names of FoLiA XML elements. It can be used standalone so it applies to all subsequent queries::

 REQUEST w,t,pos,lemma

Or after a query::

 IN somegroup/mydoc SELECT pos FOR w WHERE class!="PUNCT" FOR event WHERE class="tweet" REQUEST w,pos,lemma

Two special uses of request are ``REQUEST ALL`` (default) and ``REQUEST
NOTHING``, the latter may be useful in combination with **ADD**, **EDIT** and
**DELETE**, by default it will return the updated state of the document.
 
Note that if you set request wrong you may quickly end up with empty results.

---------------
Corrections
---------------

TODO






