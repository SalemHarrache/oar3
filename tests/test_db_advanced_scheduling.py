# coding: utf-8
from __future__ import unicode_literals, print_function
import pytest

from oar.lib import db
from oar.kao.job import insert_job
from oar.kao.meta_sched import meta_schedule

import oar.kao.utils  # for monkeypatching


@pytest.fixture(scope="function", autouse=True)
def minimal_db_initialization(request):
    db.delete_all()
    db.session.close()
    db['Queue'].create(name='default', priority=3, scheduler_policy='kamelot', state='Active')

    # add some resources
    for i in range(5):
        db['Resource'].create(network_address="localhost" + str(int(i / 2)))


@pytest.fixture(scope='function', autouse=True)
def monkeypatch_utils(request, monkeypatch):
    monkeypatch.setattr(oar.kao.utils, 'init_judas_notify_user', lambda: None)
    monkeypatch.setattr(oar.kao.utils, 'create_almighty_socket', lambda: None)
    monkeypatch.setattr(oar.kao.utils, 'notify_almighty', lambda x: len(x))
    monkeypatch.setattr(oar.kao.utils, 'notify_tcp_socket', lambda addr, port, msg: len(msg))
    monkeypatch.setattr(oar.kao.utils, 'notify_user', lambda job, state, msg: len(state + msg))


def test_db_all_in_assgin_legacy_simple_1(monkeypatch):
    insert_job(res=[(60, [('resource_id=4', "")])], properties="", types=["assign=assign_legacy"])
    job = db['Job'].query.one()
    print('job state:', job.state)

    # pdb.set_trace()
    meta_schedule('internal')

    for i in db['GanttJobsPrediction'].query.all():
        print("moldable_id: ", i.moldable_id, ' start_time: ', i.start_time)

    job = db['Job'].query.one()
    print(job.state)
    assert (job.state == 'toLaunch')


def test_db_all_in_find_legacy_simple_1(monkeypatch):
    insert_job(res=[(60, [('resource_id=4', "")])], properties="", types=["find=find_legacy"])
    job = db['Job'].query.one()
    print('job state:', job.state)

    # pdb.set_trace()
    meta_schedule('internal')

    for i in db['GanttJobsPrediction'].query.all():
        print("moldable_id: ", i.moldable_id, ' start_time: ', i.start_time)

    job = db['Job'].query.one()
    print(job.state)
    assert (job.state == 'toLaunch')