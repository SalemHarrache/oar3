# -*- coding: utf-8 -*-
from __future__ import division

from flask import url_for, g

from oar.lib import db, Job, Submission
#from oar.lib.submission import Submission

from . import Blueprint
from ..utils import Arg


app = Blueprint('jobs', __name__, url_prefix='/jobs')


@app.route('/', methods=['GET'])
@app.route('/<any(details, table):detailed>', methods=['GET'])
@app.route('/nodes/<string:network_address>', methods=['GET'])
@app.route('/ressources/<string:resource_id>/details', methods=['GET'])
@app.args({'offset': Arg(int, default=0),
           'limit': Arg(int),
           'user': Arg(str),
           'from': Arg(int, dest='start_time'),
           'to': Arg(int, dest='stop_time'),
           'state': Arg([str, ','], dest='states'),
           'array': Arg(int, dest='array_id'),
           'ids': Arg([int, ':'], dest='job_ids')})
# TOREMOVE @app.need_authentication()
#@app.need_authentication()
def index(offset, limit, user, start_time, stop_time, states, array_id,
          job_ids, detailed=None):
    query = db.queries.get_jobs_for_user(user, start_time, stop_time,
                                         states, array_id, job_ids, detailed)
    page = query.paginate(offset, limit)
    g.data['total'] = page.total
    g.data['links'] = page.links
    g.data['offset'] = offset
    g.data['items'] = []
    if detailed:
        jobs_resources = db.queries.get_assigned_jobs_resources(page.items)
    for item in page:
        attach_links(item)
        if detailed:
            attach_resources(item, jobs_resources)
            attach_nodes(item, jobs_resources)
        g.data['items'].append(item)

@app.route('/', methods=['POST'])
@app.args({'resource': Arg(str),
           'command': Arg(str),
           'workdir': Arg(str),
           'param_file': Arg(str)})
def submit(resource, command, workdir, param_file):
    """Job submission"""
    print("data:", resource, command, workdir, param_file)
    job_variables = {
        }
    submission = Submission(job_variables, cli=False)
    job_id = submission.submit()
    g.data['id'] = job_id


@app.route('/<int:job_id>/resources', methods=['GET'])
@app.args({'offset': Arg(int, default=0), 'limit': Arg(int)})
def resources(job_id, offset, limit):
    query = db.queries.get_job_resources()
    page = query.paginate(offset, limit)
    g.data['total'] = page.total
    g.data['links'] = page.links
    g.data['offset'] = offset
    g.data['items'] = []
    for item in page:
        attach_links(item)
        g.data['items'].append(item)


@app.route('/<int:job_id>', methods=['GET'])
@app.route('/<int:job_id>/<any(details, table):detailed>', methods=['GET'])
def show(job_id,detailed=None):
    job = db.query(Job).get_or_404(job_id)
    g.data.update(job.asdict())
    if detailed:
        job=Job()
        job.id=job_id
        job_resources = db.queries.get_assigned_jobs_resources([job])
        attach_resources(g.data, job_resources)
        attach_nodes(g.data, job_resources)
    attach_links(g.data)


@app.route('/<int:job_id>/nodes', methods=['GET'])
@app.args({'offset': Arg(int, default=0), 'limit': Arg(int)})
def nodes(job_id, offset, limit):
    pass


def attach_links(job):
    rel_map = (
        ("show", "self", "show"),
        ("nodes", "collection", "nodes"),
        ("resources", "collection", "resources"),
    )
    job['links'] = []
    for title, rel, endpoint in rel_map:
        url = url_for('%s.%s' % (app.name, endpoint), job_id=job['id'])
        job['links'].append({'rel': rel, 'href': url, 'title': title})


def attach_resources(job, jobs_resources):
    job['resources'] = []
    from .resource import attach_links
    for resource in jobs_resources[job['id']]:
        resource = resource.asdict(ignore_keys=('network_address',))
        attach_links(resource)
        job['resources'].append(resource)

def attach_nodes(job, jobs_resources):
    job['nodes'] = []
    network_addresses = []
    from .resource import attach_links
    for node in jobs_resources[job['id']]:
        node = node.asdict(ignore_keys=('id',))
        if node['network_address'] not in network_addresses:
            attach_links(node)
            job['nodes'].append(node)
            network_addresses.append(node['network_address'])


# @app.route('/', methods=['GET'])
# @app.args({'offset': int, 'limit': int})
# def index(offset=0, limit=None):
#     pass
#
#
# @app.route('/', methods=['GET'])
# @app.args({'offset': int, 'limit': int})
# def index(offset=0, limit=None):
#     pass
#
#
# @app.route('/', methods=['GET'])
# @app.args({'offset': int, 'limit': int})
# def index(offset=0, limit=None):
#     pass
#
#
# @app.route('/', methods=['GET'])
# @app.args({'offset': int, 'limit': int})
# def index(offset=0, limit=None):
#     pass
