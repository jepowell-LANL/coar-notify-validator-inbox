from rdflib import * 
import rdflib
import uuid
import sqlite3
import kglab

def get_messageids(dbConn):
    messages = dbConn.execute('SELECT messageid FROM messages ORDER BY timestamp DESC').fetchall()
    return messages

def get_shape(messageid,shapeFiles,dbConn):
    # selectStatement = 'SELECT messagecontent FROM messages where messageid="' + messageid + '"'
    try:
      selectStatement = 'SELECT coarnotify_action, activitystreams_action FROM messages where messageid="' + messageid + '"'
      messageActions = dbConn.execute(selectStatement).fetchone()
      coar_action = str(messageActions[0])
      as2_action = str(messageActions[1])
      shape_filename = ''
      for index in shapeFiles.keys():
        if coar_action == shapeFiles[index]['coar_action'] and as2_action == shapeFiles[index]['as2_action']:
          shape_filename = index
    except Exception as e:
      print(str(e))
      shape_filename = 'test.ttl'
    return shape_filename

def get_messagecontents(messageid, dbConn):
    selectStatement = 'SELECT messagecontent FROM messages where messageid="' + messageid + '"'
    messagecontent = dbConn.execute(selectStatement).fetchone()
    return messagecontent

def get_record(messageid,dbConn):
    selectStatement = 'SELECT * FROM messages where messageid="' + messageid + '"'
    select_response = dbConn.execute(selectStatement).fetchone()
    return select_response

def save_message_to_db(host,nowStr,payload, content_type, dbConn):
    """
    Saves the activity to the db.
    :param payload: (str) the as2 payload.
    :return: (bool)
    """ 

    messageid = str(uuid.uuid1())
    dbCursor.execute('''INSERT INTO messages(messageid, hosturl, timestamp, messagecontent, contenttype) VALUES (?,?,?,?,?)''', (messageid,host,nowStr,payload,content_type,))
    dbConn.commit()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def visualize_graph(data_for_graph, serialization='ttl'):
  data_g = Graph()
  data_g.parse(data=data_for_graph, format=serialization)
  nm = data_g.namespace_manager

  for s, p, o in sorted(data_g):
    print(s.n3(nm), p.n3(nm), o.n3(nm))

  kg = kglab.KnowledgeGraph(import_graph=data_g)

  VIS_STYLE = {
    "sh": {
        "color": "red",
        "size": 20,
    },
    "_":{
        "color": "orange",
        "size": 30,
    },
  }

  subgraph = kglab.SubgraphTensor(kg)
  pyvis_graph = subgraph.build_pyvis_graph(notebook=True, style=VIS_STYLE)
  graph_viz_filename = 'static/tmp/' + str(uuid.uuid4().hex) + '.html'
  pyvis_graph.force_atlas_2based()
  pyvis_graph.save_graph(graph_viz_filename)
  return graph_viz_filename

