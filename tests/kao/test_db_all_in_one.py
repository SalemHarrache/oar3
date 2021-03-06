# coding: utf-8
import pytest

import os
from codecs import open
from tempfile import mkstemp

from oar.lib import (db, config, GanttJobsPrediction, Resource)
from oar.lib.job_handling import (insert_job, set_jobs_start_time, set_job_state)
from oar.kao.meta_sched import meta_schedule

from ..fakezmq import FakeZmq

import oar.lib.tools  # for monkeypatching
from oar.lib.tools import get_date
import oar.kao.quotas as qts

import zmq

# import pdb

node_list = []

fakezmq = FakeZmq()
fakezmq.reset()

# Set undefined config value to default one
DEFAULT_CONFIG = {
    'HULOT_SERVER': 'localhost',
    'HULOT_PORT' : 6672,
}

@pytest.yield_fixture(scope='function', autouse=True)
def minimal_db_initialization(request):
    with db.session(ephemeral=True):
        db['Queue'].create(name='default', priority=3, scheduler_policy='kamelot', state='Active')
        # add some resources
        for i in range(5):
            db['Resource'].create(network_address="localhost" + str(int(i / 2)))
        yield


@pytest.fixture(scope="function")
def active_quotas(request):
    print('active_quotas')
    config['QUOTAS'] = 'yes'
    _, quotas_file_name = mkstemp()
    config['QUOTAS_FILE'] = quotas_file_name

    def teardown():
        config['QUOTAS'] = 'no'
        os.remove(config['QUOTAS_FILE'])
        del config['QUOTAS_FILE']

    request.addfinalizer(teardown)


@pytest.fixture(scope="function")
def active_energy_saving(request):
    config['ENERGY_SAVING_MODE'] = 'metascheduler_decision_making'
    config['SCHEDULER_NODE_MANAGER_SLEEP_CMD'] = 'sleep_node_command'
    config['SCHEDULER_NODE_MANAGER_SLEEP_TIME'] = '15'
    config['SCHEDULER_NODE_MANAGER_IDLE_TIME'] = '30'
    config['SCHEDULER_NODE_MANAGER_WAKEUP_TIME'] = '30'
    config['SCHEDULER_NODE_MANAGER_WAKE_UP_CMD'] = 'wakeup_node_command'

    def teardown():
        del config['SCHEDULER_NODE_MANAGER_SLEEP_CMD']
        del config['SCHEDULER_NODE_MANAGER_SLEEP_TIME']
        del config['SCHEDULER_NODE_MANAGER_IDLE_TIME']
        del config['SCHEDULER_NODE_MANAGER_WAKEUP_TIME']
        del config['SCHEDULER_NODE_MANAGER_WAKE_UP_CMD']
        del config['ENERGY_SAVING_MODE']

    request.addfinalizer(teardown)


def create_quotas_rules_file(quotas_rules):
    ''' create_quotas_rules_file('{"quotas": {"*,*,*,toto": [1,-1,-1],"*,*,*,john": [150,-1,-1]}}')
    '''
    with open(config['QUOTAS_FILE'], 'w', encoding="utf-8") as quotas_fd:
        quotas_fd.write(quotas_rules)
    qts.load_quotas_rules()


def insert_and_sched_ar(start_time, walltime=60):

    insert_job(res=[(walltime, [('resource_id=4', "")])],
               reservation='toSchedule', start_time=start_time,
               info_type='localhost:4242')

    meta_schedule('internal')

    return (db['Job'].query.one())


def assign_node_list(nodes):
    global node_list
    node_list = nodes


@pytest.fixture(scope='function', autouse=True)
def monkeypatch_tools(request, monkeypatch):
    monkeypatch.setattr(oar.lib.tools, 'create_almighty_socket', lambda: None)
    monkeypatch.setattr(oar.lib.tools, 'notify_almighty', lambda x: True)
    monkeypatch.setattr(oar.lib.tools, 'notify_tcp_socket', lambda addr, port, msg: len(msg))
    monkeypatch.setattr(oar.lib.tools, 'notify_user', lambda job, state, msg: len(state + msg))
    monkeypatch.setattr(oar.lib.tools, 'fork_and_feed_stdin',
                        lambda cmd, timeout_cmd, nodes: assign_node_list(nodes))
    monkeypatch.setattr(oar.lib.tools, 'send_checkpoint_signal', lambda job: None)
    monkeypatch.setattr(zmq, 'Context', FakeZmq)

@pytest.fixture(scope="function", autouse=True)
def setup(request):
    config.setdefault_config(DEFAULT_CONFIG)
    fakezmq.reset()
    oar.lib.tools.zmq_context = None
    oar.lib.tools.almighty_socket = None
    oar.lib.tools.bipbip_commander_socket = None
    
def test_db_all_in_one_simple_1(monkeypatch):
    insert_job(res=[(60, [('resource_id=4', "")])], properties="")
    job = db['Job'].query.one()
    print('job state:', job.state)

    # pdb.set_trace()
    print("fakezmq.num_socket: ", fakezmq.num_socket)
    meta_schedule('internal')
    print("fakezmq.num_socket: ", fakezmq.num_socket)
    for i in db.query(GanttJobsPrediction).order_by(GanttJobsPrediction.moldable_id).all(): 
        print("moldable_id: ", i.moldable_id, ' start_time: ', i.start_time)

    job = db['Job'].query.one()
    print(job.state)
    assert (job.state == 'toLaunch')


def test_db_all_in_one_ar_1(monkeypatch):
    # add one job

    job = insert_and_sched_ar(get_date() + 10)
    print(job.state, ' ', job.reservation)

    assert ((job.state == 'Waiting') and (job.reservation == 'Scheduled'))


@pytest.mark.usefixtures("active_quotas")
def test_db_all_in_one_quotas_1(monkeypatch):
    """
    quotas[queue, project, job_type, user] = [int, int, float];
                                               |    |     |
              maximum used resources ----------+    |     |
              maximum number of running jobs -------+     |
              maximum resources times (hours) ------------+
    """

    create_quotas_rules_file('{"quotas": {"*,*,*,/": [-1, 1, -1], "/,*,*,*": [-1, -1, 0.55]}}')

    insert_job(res=[(100, [('resource_id=1', "")])], properties="", user="toto")
    insert_job(res=[(200, [('resource_id=1', "")])], properties="", user="toto")
    insert_job(res=[(200, [('resource_id=1', "")])], properties="", user="toto")

    # pdb.set_trace()
    now = get_date()
    meta_schedule('internal')

    res = []
    for i in db.query(GanttJobsPrediction).order_by(GanttJobsPrediction.moldable_id).all(): 
        print("moldable_id: ", i.moldable_id, ' start_time: ', i.start_time - now)
        res.append(i.start_time - now)

    assert res == [0, 160, 420]


@pytest.mark.usefixtures("active_quotas")
def test_db_all_in_one_quotas_2(monkeypatch):
    """
    quotas[queue, project, job_type, user] = [int, int, float];
                                               |    |     |
              maximum used resources ----------+    |     |
              maximum number of running jobs -------+     |
              maximum resources times (hours) ------------+
    """

    create_quotas_rules_file('{"quotas": {"*,*,*,/": [-1, 1, -1]}}')

    # Submit and allocate an Advance Reservation
    t0 = get_date()
    insert_and_sched_ar(t0 + 100)

    # Submit other jobs
    insert_job(res=[(100, [('resource_id=1', "")])], properties="", user="toto")
    insert_job(res=[(200, [('resource_id=1', "")])], properties="", user="toto")

    # pdb.set_trace()
    t1 = get_date()
    meta_schedule('internal')

    res = []
    for i in db.query(GanttJobsPrediction).order_by(GanttJobsPrediction.moldable_id).all(): 
        print("moldable_id: ", i.moldable_id, ' start_time: ', i.start_time - t1)
        res.append(i.start_time - t1)

    assert (res[1] - res[0]) == 120
    assert (res[2] - res[0]) == 280


@pytest.mark.usefixtures("active_quotas")
def test_db_all_in_one_quotas_AR(monkeypatch):

    create_quotas_rules_file('{"quotas": {"*,*,*,*": [1, -1, -1]}}')

    job = insert_and_sched_ar(get_date() + 10)
    print(job.state, ' ', job.reservation)

    assert job.state == 'Error'


def test_db_all_in_one_AR_2(monkeypatch):

    job = insert_and_sched_ar(get_date() - 1000)
    print(job.state, ' ', job.reservation)
    assert job.state == 'Error'


def test_db_all_in_one_AR_3(monkeypatch):

    now = get_date()
    job = insert_and_sched_ar(now + 1000)
    new_start_time = now - 2000

    set_jobs_start_time(tuple([job.id]), new_start_time)
    db.query(GanttJobsPrediction).update({GanttJobsPrediction.start_time: new_start_time},
                                         synchronize_session=False)
    db.commit()

    meta_schedule('internal')

    job = db['Job'].query.one()
    print('\n', job.id, job.state, ' ', job.reservation, job.start_time)

    assert job.state == 'Error'


def test_db_all_in_one_AR_4(monkeypatch):

    now = get_date()
    job = insert_and_sched_ar(now + 10)
    new_start_time = now - 20

    db.query(GanttJobsPrediction).update({GanttJobsPrediction.start_time: new_start_time},
                                         synchronize_session=False)
    db.commit()

    meta_schedule('internal')

    job = db['Job'].query.one()
    print('\n', job.id, job.state, ' ', job.reservation, job.start_time)

    assert job.state == 'toLaunch'


def test_db_all_in_one_AR_5(monkeypatch):

    now = get_date()
    job = insert_and_sched_ar(now + 10)
    new_start_time = now - 20

    set_jobs_start_time(tuple([job.id]), new_start_time)
    db.query(GanttJobsPrediction).update({GanttJobsPrediction.start_time: new_start_time},
                                         synchronize_session=False)
    db.commit()

    db.query(Resource).update({Resource.state: 'Suspected'}, synchronize_session=False)
    db.commit()
    
    meta_schedule('internal')

    job = db['Job'].query.one()
    print('\n', job.id, job.state, ' ', job.reservation, job.start_time)

    assert job.state == 'Waiting'


def test_db_all_in_one_AR_6(monkeypatch):

    now = get_date()
    job = insert_and_sched_ar(now + 10, 600)
    new_start_time = now - 350

    set_jobs_start_time(tuple([job.id]), new_start_time)
    db.query(GanttJobsPrediction).update({GanttJobsPrediction.start_time: new_start_time},
                                         synchronize_session=False)

    # db.query(Resource).update({Resource.state: 'Suspected'}, synchronize_session=False)

    meta_schedule('internal')

    job = db['Job'].query.one()
    print('\n', job.id, job.state, ' ', job.reservation, job.start_time)

    assert job.state == 'toLaunch'


def test_db_all_in_one_AR_7(monkeypatch):

    now = get_date()
    insert_job(res=[(60, [('resource_id=4', "")])],
               reservation='toSchedule', start_time=now+10,
               info_type='localhost:4242', types=["timesharing=*,*"])

    meta_schedule('internal')

    job = db['Job'].query.one()
    assert ((job.state == 'Waiting') and (job.reservation == 'Scheduled'))


def test_db_all_in_one_BE(monkeypatch):

    db['Queue'].create(name='besteffort', priority=3, scheduler_policy='kamelot', state='Active')

    insert_job(res=[(100, [('resource_id=1', "")])], queue_name='besteffort', types=['besteffort'])

    meta_schedule('internal')

    job = db['Job'].query.one()
    print(job.state)
    assert (job.state == 'toLaunch')

@pytest.mark.skip(reason='Bug occurs only in travis-CI upto now')
def test_db_all_in_one_BE_to_kill(monkeypatch):

    os.environ['USER'] = 'root'  # to allow fragging
    db['Queue'].create(name='besteffort', priority=3, scheduler_policy='kamelot', state='Active')

    insert_job(res=[(100, [('resource_id=2', "")])], queue_name='besteffort', types=['besteffort'])

    meta_schedule('internal')

    job = db['Job'].query.one()
    assert (job.state == 'toLaunch')

    insert_job(res=[(100, [('resource_id=5', "")])])

    meta_schedule('internal')
    
    jobs = db['Job'].query.order_by(db['Job'].id).all()
    print(jobs[0].state, jobs[1].state)

    print("frag...", db['FragJob'].query.one())
    frag_job = db['FragJob'].query.one()
    assert jobs[0].state == 'toLaunch'
    assert jobs[1].state == 'Waiting'
    assert frag_job.job_id == jobs[0].id

@pytest.mark.skip(reason='Bug occurs only in travis-CI upto now')
def test_db_all_in_one_BE_to_checkpoint(monkeypatch):

    os.environ['USER'] = 'root'  # to allow fragging
    db['Queue'].create(name='besteffort', priority=3, scheduler_policy='kamelot', state='Active')

    insert_job(res=[(100, [('resource_id=2', "")])], queue_name='besteffort',
               checkpoint=10, types=['besteffort'])

    meta_schedule('internal')

    job = db['Job'].query.one()
    assert (job.state == 'toLaunch')

    insert_job(res=[(100, [('resource_id=5', "")])])

    meta_schedule('internal')

    jobs = db['Job'].query.all()

    print(jobs[0].state, jobs[1].state)

    assert jobs[0].state == 'toLaunch'
    assert jobs[1].state == 'Waiting'

@pytest.mark.skip(reason='Bug occurs only in travis-CI upto now')
def test_db_all_in_one_BE_2(monkeypatch):
    # TODO TOFINISH
    db['Queue'].create(name='besteffort', priority=3, scheduler_policy='kamelot', state='Active')

    insert_job(res=[(100, [('resource_id=1', "")])], queue_name='besteffort',
               types=['besteffort', "timesharing=*,*"])

    meta_schedule('internal')
    job = db['Job'].query.one()

    set_job_state(job.id, 'Running')

    insert_job(res=[(50, [('resource_id=1', "")])], types=["timesharing=*,*"])

    meta_schedule('internal')

    jobs = db['Job'].query.all()
    print(jobs[1].id, jobs[1].state)
    # assert (jobs[1].state == 'toLaunch')
    assert (jobs[1].state == 'Waiting')


@pytest.mark.usefixtures("active_energy_saving")
def test_db_all_in_one_wakeup_node_1(monkeypatch):

    insert_job(res=[(60, [('resource_id=4', "")])], properties="")

    now = get_date()
    # Suspend nodes
    db.query(Resource).update({Resource.state: 'Absent', Resource.available_upto: now + 1000},
                              synchronize_session=False)
    db.commit()
    meta_schedule('internal')

    job = db['Job'].query.one()
    print(job.state)
    print(node_list)
    assert (job.state == 'Waiting')
    assert (node_list == [u'localhost0', u'localhost1'])


@pytest.mark.usefixtures("active_energy_saving")
def test_db_all_in_one_sleep_node_1(monkeypatch):
    
    now = get_date()

    insert_job(res=[(60, [('resource_id=1', "")])], properties="")

    # Suspend nodes
    # pdb.set_trace()
    db.query(Resource).update({Resource.available_upto: now + 50000},
                              synchronize_session=False)
    db.commit()
    meta_schedule('internal')

    job = db['Job'].query.one()
    print(job.state)
    print(node_list)
    assert (job.state == 'toLaunch')
    assert (node_list == [u'localhost2', u'localhost1'] or
            node_list == [u'localhost1', u'localhost2'])


@pytest.mark.usefixtures("active_energy_saving")
def test_db_all_in_one_wakeup_node_energy_saving_internal_1(monkeypatch):
    config['ENERGY_SAVING_INTERNAL'] = 'yes'

    insert_job(res=[(60, [('resource_id=4', "")])], properties="")

    now = get_date()
    # Suspend nodes
    db.query(Resource).update({Resource.state: 'Absent', Resource.available_upto: now + 1000},
                              synchronize_session=False)
    db.commit()
    meta_schedule('internal')

    job = db['Job'].query.one()
    print(job.state)
    print(node_list)
    print('fakezmq.sent_msgs', fakezmq.sent_msgs)
    assert (job.state == 'Waiting')
    assert fakezmq.sent_msgs == {0: [{'cmd': 'WAKEUP', 'nodes': ['localhost0', 'localhost1']}]}

@pytest.mark.usefixtures('active_energy_saving')
def test_db_all_in_one_sleep_node_energy_saving_internal_1(monkeypatch):
    config['ENERGY_SAVING_INTERNAL'] = 'yes'
    
    now = get_date()

    insert_job(res=[(60, [('resource_id=1', "")])], properties="")

    # Suspend nodes
    # pdb.set_trace()
    db.query(Resource).update({Resource.available_upto: now + 50000},
                              synchronize_session=False)
    db.commit()
    meta_schedule('internal')

    job = db['Job'].query.one()
    print(job.state)
    print(node_list)
    print('fakezmq.sent_msgs', fakezmq.sent_msgs)
    assert (job.state == 'toLaunch')

    assert fakezmq.sent_msgs[1][0]['cmd'] == 'HALT'
    fakezmq.sent_msgs[1][0]['nodes'].sort()
    assert fakezmq.sent_msgs[1][0]['nodes'] == ['localhost1', 'localhost2']

def test_db_all_in_one_simple_2(monkeypatch):
    insert_job(res=[(60, [('resource_id=4', "")])], properties="")
    job = db['Job'].query.one()
    print('job state:', job.state)

    os.environ['OARDIR'] = '/tmp/'

    meta_schedule('internal')

    for i in db.query(GanttJobsPrediction).order_by(GanttJobsPrediction.moldable_id).all(): 
        print("moldable_id: ", i.moldable_id, ' start_time: ', i.start_time)

    job = db['Job'].query.one()
    print(job.state)
    assert (job.state == 'toLaunch')


def test_db_all_in_one_simple_interactive_waiting_1(monkeypatch):
    insert_job(res=[(60, [('resource_id=4', "")])], properties="")
    insert_job(res=[(60, [('resource_id=4', "")])], properties="", job_type='INTERACTIVE',
               info_type="0.0.0.0:1234")

    meta_schedule('internal')

    for i in db.query(GanttJobsPrediction).order_by(GanttJobsPrediction.moldable_id).all(): 
        print("moldable_id: ", i.moldable_id, ' start_time: ', i.start_time)

    jobs = db['Job'].query.order_by(db['Job'].id).all()
    assert (jobs[0].state == 'toLaunch')
    assert (jobs[1].state == 'Waiting')
