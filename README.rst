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


