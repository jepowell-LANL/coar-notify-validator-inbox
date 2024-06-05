import os
import sys
from flask import Flask, flash, request, redirect, url_for, render_template, make_response, send_from_directory, Response
 
import re
import json
import requests

import pyvis.network
import kglab
import networkx as nx
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
 
from link_header import *

import rdflib
from rdflib import URIRef, Literal, Namespace
from rdflib.namespace import RDF, DCTERMS

import signposting 
import uuid 
from pyshacl import validate

# usage:
#   python signposting-validator.py
#   access http://localhost:8078/

shapefiledir = './fair-signposting-shapes/'
patterns = {'author': ['author'], 'bibliographic metadata': ['describes', 'describedby'], 'identifier': ['cite-as'], 'publication boundary': ['item', 'collection'], 'resource type': ['type'], 'license': ['license']}

shapeFiles = {}

# author is rel=author and subject=<uri>
# bib_metadata is describedby or describes
# pub_boundary is item or collection
# identifier is cite-as and subject=<uri>
# resource_type is type and subject is a mimetype

# link headers may alternately be included in the html head element as link elements
# each link element will have a rel attribute, possibly a type, and an href for the object of rel

# Yet another alternative is a link element with rel="linkset", type="application/linkset"
# the uri associated with this link should be dereferenced to get link header equivalent values
# in one case, the contents returns as application/linkset will be like HTTP link headers
# there may be in addition to, or instead a json representation that can be retrieved
# the form of the linkset json object differs from the link headers, although the patterns remain the same

def saveResults(resultsString, resultsFilename):
  with open(resultsFilename, "a") as results:
    results.write(resultsString)
  results.close()

def get_signposts(url, retrieval):
  print('---> ' + str(url))
  if retrieval =='linkset':
    # s = signposting.find_signposting_linkset(url, acceptType='application/linkset+json')
    # s = signposting.find_signposting_linkset(url, 'application/linkset+json')
    s = signposting.find_signposting_linkset(url, acceptType='application/linkset+json')
  if retrieval =='link-headers':
    s = signposting.find_signposting_http(url)
  if retrieval =='html-elements':
    s = signposting.find_signposting_html(url)
  print(s)
  print('entries in signposting class')
  for entry in s:
    print(s)
  print('signposting class')
  print(s.signposts)
  print('list of signposts')
  print(list(s.signposts))
  example_filename = str(uuid.uuid4().hex) + '.json'
  saveResults(str(s.signposts), './sp-examples/' + example_filename)
  return s

def shacl_validate(g, shacl_graph='recipe-level1-shape.ttl'):
  print(shacl_graph)
  r = validate(g,
      shacl_graph=shacl_graph,
      ont_graph=None,
      inference='rdfs',
      abort_on_first=False,
      allow_infos=False,
      allow_warnings=False,
      meta_shacl=False,
      advanced=False,
      js=False,
      debug=False)

  conforms, results_graph, results_text = r
  print(conforms)
  return results_text, conforms

def shacl_validation_report(g, shacl_graph, shapefilename, url):
    results = validate(g,
      shacl_graph=shacl_graph,
      ont_graph=None,
      inference='rdfs',
      abort_on_first=False,
      allow_infos=False,
      allow_warnings=False,
      meta_shacl=False,
      advanced=False,
      js=False,
      debug=False)

    conforms, report_graph, report_text = results

    # report_g = kglab.Graph()
    # report_g.parse(data=report_graph, format="ttl", encoding="utf-8")
    # nm = report_g.namespace_manager
    
    report_text = report_text.replace('"','')
    report_text = report_text.replace('>','')
    message_viz_link = '/' + str(visualize_graph(g)) 
    print(message_viz_link)
    validation_viz_link = '/' + str(visualize_graph(report_graph))
    print(validation_viz_link)

    resp = make_response(render_template('validation-report.html', filename=url, shape_label=shapefilename, validation_viz_link=validation_viz_link, message_viz_link=message_viz_link, report_text=report_text))
    return resp

def get_http_headers(url):
    link_headers = {}
    all_link_headers = []
    try:
        response = requests.head(url)  # Send a HEAD request to retrieve only the headers
        response.raise_for_status()  # Raise an exception for bad responses (4xx or 5xx)
        
        # Display all the HTTP headers
        print("HTTP Headers:")
        for header, value in response.headers.items():
          if 'link' in header.lower():
            print(f"{header}: {value}\n")
            link_headers = parse_link_value(str(response.headers.items()))
            all_link_headers.append({header: value})
         
    except requests.exceptions.RequestException as e:
      pass
    print('Link headers parsed')
    print(link_headers)

    return link_headers, all_link_headers, response

 
def check_for_linkset(link_headers):
    print("HTTP Headers:")
    for header, value in response.headers.items():
      if 'link' in header.lower():
          print(f"{header}: {value}")
          link_headers = parse_link_value(str(response.headers.items()))
          print(link_headers)
          for key in link_headers:
            linkvalues = link_headers[key]
            print(str(linkvalues))
            if 'rel' in linkvalues.keys():
               print('rel type found')
               if linkvalues['rel'].lower()=='linkset':
                 print('linkset found')
                 print(key + ' ' + str(link_headers[key]))
                 linkset_url = key
                 print(linkset_url)
                 link_headers=get_http_headers(linkset_url)
    return link_headers

def transform_link_headers(links, url, retrieval):
    print('starting transform of link headers for ' + url)
    patterns = {
        'author': ['author'],
        'bib_metadata': ['describes', 'describedby'],
        'identifier': ['cite-as'],
        'pub_boundary': ['item', 'collection'],
        'resource_type': ['type'],
        'license': ['license']
    }
    patterns_list = ['author', 'describes', 'describedby', 'cite-as', 'item', 'collection', 'type', 'license', 'identifier']
    
    EX = Namespace("http://example.org/")
    SCHEMA = Namespace("http://schema.org/")
    SP = Namespace("http://signposting.org/")
    
    g = rdflib.Graph()
    g.bind("ex", EX)
    g.bind("schema", SCHEMA)
    g.bind("sp", SP)
    
    aggregate_document = URIRef(url)
    g.add((aggregate_document, RDF.type, EX.AggregateDocument))
    
    print('Iterating through and mapping rel types')
    print(links)
    # for index in links:
    print(links)
    sp_links = []
    for s in links:
      sp_links.append(s)
    all_sp_links = [link for link in links]
    print(all_sp_links)
    # [<Signpost context=http://digital.ucd.ie/view/ucdlib:31122 rel=author target=http://orcid.org/0000-0001-6092-9741>, <Signpost context=http://digital.ucd.ie/view/ucdlib:31122 rel=author target=http://orcid.org/0000-0001-5134-5322>, <Signpost context=http://digital.ucd.ie/view/ucdlib:31122 rel=describedby target=https://digital.ucd.ie/citation/ucdlib:31122/ris type=application/x-research-info-systems>, <Signpost context=http://digital.ucd.ie/view/ucdlib:31122 rel=describedby target=https://digital.ucd.ie/citation/ucdlib:31122/btx type=application/x-bibtex>, <Signpost context=http://digital.ucd.ie/view/ucdlib:31122 rel=describedby target=https://doi.org/10.7925/drs1.ucdlib_31122 type=application/vnd.citationstyles.csl+json>]

    for link in all_sp_links:
         print(link)
         link_components = str(link).split(' ')
         if link_components[0]=='Link:':
           target_url = link_components[1].replace('<','').replace('>','').replace(';','')
           print('target_url ' + target_url)
           relation = ''
           rel_type = ''
           for index in range(1, len(link_components)):
             if "rel=" in link_components[index]:
               rel_type = link_components[index].replace('rel=','').replace(';','')
               print('relation ' + rel_type)
             if "type=" in link_components[index]:
               content_type = link_components[index].replace('type=','').replace(';','')
               print('type ' + content_type)

           try:
             if rel_type in patterns_list:
               if rel_type == 'author':
                     print('author found')
                     g.add((aggregate_document, SP.author, URIRef(target_url)))
               elif rel_type == 'cite-as':
                     print('identifier found')
                     g.add((aggregate_document, URIRef('http://signposting.org/cite-as'), URIRef(target_url)))
               elif rel_type == 'item':
                     print('collection item found')
                     g.add((aggregate_document, SP.item, URIRef(target_url)))
               elif rel_type == 'collection':
                     print('collection found')
                     g.add((URIRef(target_url), SP.collection, aggregate_document))
               elif rel_type == 'license':
                     print('license found')
                     g.add((aggregate_document, SP.license, URIRef(target_url)))
               elif rel_type == 'type':
                     print('type found')
                     g.add((URIRef(target_url), SP.type, Literal(entry[rel_type])))
               elif rel_type == 'describedby':
                     print('reference to metadata found')
                     g.add((aggregate_document, SP.describedby, URIRef(target_url)))
               elif rel_type == 'describes':
                     print('metadata found')
                     g.add((aggregate_document, SP.describes, URIRef(target_url)))
           except Exception as e:
             print(e)
                    

    # Save the graph to an RDF/XML file
    g.serialize("example.rdf", format="pretty-xml")
    g.serialize("example.ttl", format="turtle")
    
    # nx.draw(g, with_labels=True)
    # plt.savefig("headers-graph-object-example.png")

    return g

# Example usage
url = "https://digital.library.unt.edu/ark:/67531/metadc1477161/"
pattern = "bib_metadata"
# validate_link_headers(url, pattern)


def validate_link_headers(url, pattern):
    link_headers = {}
    G = nx.Graph()
    G.add_node(url)
    valid = False
    try:
        response = requests.head(url)  # Send a HEAD request to retrieve only the headers
        response.raise_for_status()  # Raise an exception for bad responses (4xx or 5xx)

        # Display all the HTTP headers
        print("Validate Headers:")
        for header, value in response.headers.items():
          if 'link' in header.lower():
            print(f"{header}: {value}")
            link_headers = parse_link_value(str(response.headers.items()))
            # link_headers = check_for_linkset(link_headers)
            print(link_headers)
            for key in link_headers:
              linkvalues = link_headers[key]
              print(str(linkvalues))
              if 'rel' in linkvalues.keys():
                 print('rel type found')
                 if linkvalues['rel'] in patterns[pattern]:
                   print('pattern type found')
                   valid = True
                   print(key + ' ' + str(link_headers[key]))
                   print('Resource is associated with Link header for selected pattern')
                   G.add_edge(url, key, label=str(link_headers[key]))

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
    nx.draw(G, with_labels=True)
    plt.savefig("headers-graph-example.png")
    graph_page= ''
    graph_page = viz_graph(G)
              
    return link_headers, graph_page, valid
              


app = Flask(__name__)
 
@app.route('/validate-recipe/', methods=['GET','POST'])
def validate_recipe():
  start_url = request.args.get('start_url')
  resource = request.args.get('resource')
  shapefilename = 'Landing page validation'
  retrieval = request.args.get('retrieval')

  start_url_metadata = requests.get(start_url)
  # print(start_url_metadata.content)

  all_headers = start_url_metadata.headers

  if retrieval=='link-headers':
    all_headers, all_link_headers, response = get_http_headers(start_url)
    site_signposts = get_signposts(start_url, retrieval)

  if retrieval=='linkset':
    all_headers, all_link_headers, response = get_http_headers(start_url)
    print(all_link_headers)
    # 'link': '<https://zenodo.org/api/records/8030018> ; rel="linkset" ; type="application/linkset+json"'
    # [{'link': '<https://zenodo.org/api/records/8030018> ; rel="linkset" ; type="application/linkset+json"'}]
    # ---> <https://zenodo.org/api/records/8030018> ; rel="linkset" ; type="application/linkset+json"
    linkset_url = all_link_headers[0]['link'].split(';')[0].replace('>','').replace('<','').strip()
    site_signposts = get_signposts(linkset_url, retrieval)
    # site_signposts = get_signposts(start_url, retrieval)

  graph_page = transform_link_headers(site_signposts, start_url, retrieval)

  results_text, status = shacl_validate(graph_page, shapeFiles[shapefilename])
  resp = shacl_validation_report(graph_page, shapeFiles[shapefilename], shapefilename, start_url)

  # resp = make_response(render_template('validation-results.html', results=site_signposts, status=status, url=start_url, graph_link=graph_page, shacl_results=results_text, shapefilename=shapefilename))
  return resp

@app.route('/', methods=['GET','POST'])
def get_validate_form():
  resp = make_response(render_template('sp-validator.html'))
  return resp

@app.route('/get_link_headers/', methods=['GET','POST'])
def get_link_headers():
  start_url = request.args.get('start_url')
  retrieval = request.args.get('retrieval')
  pattern_name = request.args.get('pattern')
 
  start_url_metadata = requests.get(start_url)
  # print(start_url_metadata.content)
 
  site_signposts = get_signposts(start_url, retrieval)
  all_headers = start_url_metadata.headers
  all_link_headers, graph_page, status = validate_link_headers(start_url, pattern_name)
  all_headers, all_link_headers, response = get_http_headers(start_url)
  # graph_page = transform_link_headers(all_link_headers, start_url, pattern_name)
  print('All headers')
  print(all_headers)
  graph_page = transform_link_headers(site_signposts, start_url, pattern_name)
  shapefiles = ['recipe-level1-content-metadata-shape.ttl', 'recipe-level1-landing-shape.ttl']
  
  for shapefile in shapefiles:
    results_text = shacl_validate(graph_page, shapefiledir + shapefile)
    print(results_text)

  # text = processMetadataFromString(arxiv_metadata.content)
  # print(keyphrase_extraction((text)))
 
  resp = make_response(render_template('validation-results.html', results=site_signposts, pattern=pattern_name, status=status, url=start_url, graph_link=graph_page, shacl_results=results_text, shapefilename=shapefile))
  return resp

def visualize_graph(data_g):
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
  print(graph_viz_filename)
  pyvis_graph.force_atlas_2based()
  # pyvis_graph.show(graph_viz_filename)
  pyvis_graph.save_graph(graph_viz_filename)
  return graph_viz_filename

if __name__ == '__main__':
  for dirname, dirnames, filenames in os.walk(shapefiledir):
    for filename in filenames:
          if filename.endswith('.ttl'):
            f = open(shapefiledir + '/' + filename)
            shape_file_contents= f.read()
            f.close()
            shape_graph = rdflib.Graph()
            shape_graph.parse(data=shape_file_contents, format="ttl", encoding="utf-8")
            nm = shape_graph.namespace_manager

            for s, p, o in sorted(shape_graph):
              if str(p)=='http://www.w3.org/2000/01/rdf-schema#label':
                shape_file_label = o.n3(nm)
                print(shape_file_label)
                # print(s.n3(nm), p.n3(nm), o.n3(nm))
            shapeFiles[shape_file_label.replace('"','')] = shape_graph

  app.run(debug=True,host='0.0.0.0', port='8078')

