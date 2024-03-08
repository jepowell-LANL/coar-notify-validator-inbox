from flask import *
import json
from datetime import datetime
import configparser

from rdflib import *
from rdflib.namespace import *
from rdflib.plugin import register, Serializer, Parser
from rdflib.extras import infixowl
from rdflib.extras.infixowl import manchesterSyntax

import pyvis.network
import kglab
import pyshacl
import os
import sys

from validator_utils import * 
from pyldn import *

import sqlite3

from werkzeug.utils import secure_filename
import logging
import requests

import uuid
import time
import urllib3

# Accepted content types
ACCEPTED_TYPES = ['application/ld+json',
                  'text/turtle',
                  'application/ld+json; profile="http://www.w3.org/ns/activitystreams', 'turtle', 'json-ld']

ALLOWED_EXTENSIONS = {'json', 'jsonld', 'ttl'}
    
shapeFiles = {}
http = urllib3.PoolManager()

arglist = sys.argv
configFilename = arglist[1]
config = configparser.ConfigParser()
config.read(configFilename)

database_path = config['db']['sqlliteDbPath']
base_uri = config['ldn']['basePath']
port = config['ldn']['port']
upload_folder = config['app']['uploadFolder']
inbox_path = config['ldn']['inboxPath']
           
base_url = base_uri + ':' + port
inbox_url = base_url + inbox_path
shape_files_dir = str(config['app']['shapefilesPath'])

logging_config_filename = str(config['app']['configFilename'])

logging.config.fileConfig(logging_config_filename)

# create logger
logger = logging.getLogger('basicLogger')

logger.debug('App restarted')

from pyldn import *
# The Flask app
app = Flask(__name__)

# sqlite db
dbConn = sqlite3.connect(database_path, check_same_thread=False)
dbCursor = dbConn.cursor()
dbCursor.execute('''CREATE TABLE IF NOT EXISTS messages 
                    (messageid TEXT,
                     hosturl TEXT,
                     timestamp TEXT,
                     messagecontent TEXT,
                     contenttype TEXT,
                     sender TEXT,
                     subject TEXT,
                     recipient TEXT,
                     coarnotify_action TEXT,
                     activitystreams_action TEXT)''')

dbCursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS ti ON messages(messageid)''')

# Server routes
@app.route('/', methods=['GET', 'POST', 'HEAD'])
def base():
    host = str(request.host)
    logger.info('web root page requested by ' + host)

    inbox_contents = get_messageids(dbConn)
    inboxDict = {}
    for messageid in inbox_contents:
      shape_filename = get_shape(messageid[0],shapeFiles,dbConn)
      rawmessagecontents = get_messagecontents(str(messageid[0]),dbConn)[0]
      rawresults = get_record(str(messageid[0]),dbConn)
      messagecontent = json.dumps(json.loads(rawresults[3]), indent=4, sort_keys=True)

      inboxDict[str(messageid[0])] = {'timestamp': rawresults[2], 'hosturl': rawresults[1], 'messagecontent': messagecontent, 'contenttype': rawresults[6], 'origin': rawresults[5], 'recipient': rawresults[7], 'shape_filename': shape_filename}

    resp = Response()
    resp.headers['X-Powered-By'] = 'https://github.com/albertmeronyo/pyldn'
    resp.headers['Link'] =  '<' + inbox_url + '>; rel="http://www.w3.org/ns/ldp#inbox", <http://www.w3.org/ns/ldp#Resource>; rel="type", <http://www.w3.org/ns/ldp#RDFSource>; rel="type"'

    if request.method == 'GET' or  request.method == 'POST':
      resp = make_response(render_template('index.html', inbox_contents=inboxDict))
    return resp

@app.route('/message', methods=['GET','POST'])
def show_message():
  # ?id={{message}}">Message Id: {{message}} </a>
  inboxDict = {}
  message_id = request.args.get('id')

  host = str(request.host)
  logger.info('message ' + message_id + ' requested by ' + host)

  shape_filename = request.args.get('shape_filename')
  rawmessagecontents = get_messagecontents(message_id,dbConn)[0]
  inboxDict[message_id] = json.dumps(json.loads(rawmessagecontents), indent=4, sort_keys=True)
  resp = make_response(render_template('one-message.html', message_id=message_id, inbox_contents=inboxDict, shape_filename=shape_filename))
  return resp

# this application is mostly using the pyldn implementation found at 
#    https://github.com/albertmeronyo/pyldn
# however, the original post_inbox function is modified as below to add functionality

@app.route(pyldnconf._inbox_path, methods=['POST'])
def post_inbox():
    pyldnlog.debug("Received request to create notification")
    pyldnlog.debug("Headers: {}".format(request.headers))
    # Check if there's acceptable content
    content_type = [s for s in ACCEPTED_TYPES if s in request.headers['Content-Type']]
    pyldnlog.debug("Interpreting content type as {}".format(content_type))
    if not content_type:
        return 'Content type not accepted', 500
    if not request.data:
        return 'Received empty payload', 500

    host = str(request.host)
    now = datetime.now()
    nowStr = now.strftime("%m/%d/%y %H:%M:%S")

    resp = make_response()

    payload = request.data
    pyldnlog.debug("payload: {}".format(payload))

    save_activity_to_db(host, nowStr, payload, content_type[0], dbConn)

    ldn_url = inbox_url
    pyldnlog.debug('Created notification {}'.format(ldn_url))

    inbox_graph.add((URIRef(inbox_url), ldp['contains'], URIRef(ldn_url)))
    resp.headers['Location'] = ldn_url

    return resp, 201

@app.route('/upload-validate/', methods=['GET', 'POST', 'HEAD'])
def upload_validate():

      report_text = ''

      if request.method == 'GET':
        resp = make_response(render_template('upload-validate.html', shapefiles_index=shapeFiles.keys()))
        return resp

      if request.method == 'POST':
        try:
          result = request.form
        except Exception as e:
          logger.debug(e)

        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        shape_label = request.form.get('shape_file')
        try:
          shacl_validation_graph = shapeFiles[request.form.get('shape_file')]
        except Exception as e:
          logger.debug(e)

        # if user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(upload_folder, filename))

        file = open(os.path.join(upload_folder, filename), 'r')
        payload_data = file.read()
        file.close()
        data_serialization = 'json-ld'

        shape_filename = 'test-announce-endorse-shape.ttl'
        f = open(shape_filename)
        shape_graph = f.read()
        f.close()

        try:
          instance_data_graph = Graph().parse(data=payload_data, format=data_serialization)
        except Exception as e:
          logger.debug(e)

        results = pyshacl.validate(
          instance_data_graph,
          shacl_graph=shacl_validation_graph,
          data_graph_format=data_serialization,
          shacl_graph_format="ttl",
          inference="rdfs",
          debug=True,
          meta_shacl=False,
          serialize_report_graph="ttl"
        )
        conforms, report_graph, report_text = results

        report_g = Graph()
        report_g.parse(data=report_graph, format="ttl", encoding="utf-8")
        nm = report_g.namespace_manager

      report_text = report_text.replace('"','')
      report_text = report_text.replace('>','')
      message_viz_link = str(visualize_graph(payload_data, serialization='json-ld')) 
      validation_viz_link = str(visualize_graph(report_graph))

      resp = make_response(render_template('validation-report.html', filename=filename, shape_label=shape_label, validation_viz_link=validation_viz_link, message_viz_link=message_viz_link, report_text=report_text))
      return resp

@app.route('/validate/', methods =['GET','POST'])
def validate():
  message_id = request.args.get('message_id')
  shape_filename = request.args.get('shape_filename')

  host = str(request.host)
  logger.info('validation request for ' + message_id + ' agaainst ' + shape_filename + ' requested by ' + host)

  data_serialization = 'json-ld'
  payload_data = get_record(message_id,dbConn)[3]

  try:
    shape_label = shapeFiles[shape_filename]['shape_label']
  except: 
    resp = make_response(render_template('no-shapefile-message.html'))
    logger.debug('No matching shapefile found')
    return resp

  f = open('./shapefiles/' + shape_filename)
  shape_graph = f.read()
  f.close()

  try:
      instance_data_graph = Graph().parse(data=payload_data, format=data_serialization)
  except Exception as e:
      logger.debug(e)

  shacl_validation_graph = shape_graph

  results = pyshacl.validate(
          instance_data_graph,
          shacl_graph=shacl_validation_graph,
          data_graph_format=data_serialization,
          shacl_graph_format="ttl",
          inference="rdfs",
          debug=True,
          meta_shacl=False,
          serialize_report_graph="ttl"
  )

  conforms, report_graph, report_text = results

  report_g = Graph()
  report_g.parse(data=report_graph, format="ttl", encoding="utf-8")
  nm = report_g.namespace_manager

  report_text = report_text.replace('"','')
  report_text = report_text.replace('>','')
  validation_viz_link = '/' + str(visualize_graph(report_graph))
  message_viz_link = '/' + str(visualize_graph(payload_data, serialization='json-ld')) 

  resp = make_response(render_template('validation-report.html', filename=filename, shape_label=shape_label, validation_viz_link=validation_viz_link, message_viz_link=message_viz_link, report_text=report_text))
  debug.info('validation report stored locally as ' + validation_viz_link)

  return resp

@app.route('/uploads/', methods=['GET', 'POST', 'HEAD'])
def upload_file():
    if request.method == 'POST':
        try:
          result = request.form
        except Exception as e:
          logger.debug(e)
      
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']

        # if user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(upload_folder, filename))
            persistentId =  baseUrl + '/perm/' + str(uuid.uuid4().hex)

    if request.method == 'GET':
      resp = make_response(render_template('upload-validate.html', shapefiles_index=shapeFiles.keys()))
      return resp

if __name__ == '__main__':
 
  for dirname, dirnames, filenames in os.walk(shape_files_dir):
    for filename in filenames:
          if filename.endswith('.ttl'):
            f = open(shape_files_dir + '/' + filename)
            shape_file_contents= f.read()
            f.close()
            shape_graph = Graph()
            shape_graph.parse(data=shape_file_contents, format="ttl", encoding="utf-8")
            nm = shape_graph.namespace_manager

            for s, p, o in sorted(shape_graph):
              if str(p)=='http://www.w3.org/2000/01/rdf-schema#label' and str(s)=='http://example.org#ValidationShape':
                shape_file_label = o.n3(nm)
                logger.debug('Shape file ' + shape_file_label + ' loaded.')
            for s, p, o in sorted(shape_graph):
              if str(p)=='http://www.w3.org/2000/01/rdf-schema#label' and str(s)=='http://example.org#COARAction': 
                coar_action = o.n3(nm)
            for s, p, o in sorted(shape_graph):
              if str(p)=='http://www.w3.org/2000/01/rdf-schema#label' and str(s)=='http://example.org#ActivityStreamsAction': 
                as2_action = o.n3(nm)
            shapeFiles[filename] = {'shape_label': shape_file_label.replace('"',''), 'graph': shape_graph, 'coar_action': str(coar_action).replace('"',''), 'as2_action': str(as2_action).replace('"','')}
    logger.info(str(len(shapeFiles)) + ' shapefiles loaded')


  app.run(debug=True,host='0.0.0.0', port='8090')


