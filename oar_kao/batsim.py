import struct
import socket
import sys
import os
import json
#import collections
from sets import Set

from oar.kao.simsim import ResourceSetSimu, JobSimu
from oar.kao.helpers import plot_slots_and_job
from oar.kao.interval import itvs2ids
from oar.kao.kamelot import schedule_cycle
from oar.kao.platform import Platform
from oar.lib import config

config['LOG_FILE'] = '/tmp/yop'

jobs = {}
jobs_completed = []
jobs_waiting = []

sched_delay = 5.0

nb_completed_jobs = 0
nb_jobs = 0
nb_res = 0

def create_uds(uds_name):
    # Make sure the socket does not already exist
    try:
        os.unlink(uds_name)
    except OSError:
        if os.path.exists(uds_name):
            raise

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    
    # Bind the socket to the port
    print >>sys.stderr, 'starting up on %s' % uds_name
    sock.bind(uds_name)

    # Listen for incoming connections
    sock.listen(1)

    return sock

def read_bat_msg(connection):
    lg_str = connection.recv(4)
    
    if not lg_str:
        print "connection is closed by batsim core"
        exit(1)
        
    #print 'from client (lg_str): %r' % lg_str
    lg = struct.unpack("i",lg_str)[0]
    #print 'size msg to recv %d' % lg
    msg = connection.recv(lg)
    print 'from batsim : %r' % msg
    sub_msgs = msg.split('|')
    data = sub_msgs[-1].split(":")
    if data[2] != 'T':
        raise Exception("Terminal submessage must be T type")
    now = float(data[1])

    jobs_submitted = []
    new_jobs_completed = []
    for i in range(len(sub_msgs)-1):
        data = sub_msgs[i].split(':')
        if data[2] == 'S':
            jobs_submitted.append( int(data[3]) )
        elif data[2] == 'C':
            time = float(data[3])
            jid = int(data[3])
            jobs[jid].state = "Terminated"
            jobs[jid].run_time = time - jobs[jid].run_time
            new_jobs_completed.append(jid)
        else:
            raise Exception("Unknow submessage type" + data[2] )  

    return (now, jobs_submitted, new_jobs_completed)

def send_bat_msg(connection, now, jids_toLaunch, jobs):
    msg = "0:" + str(now)
    if jids_toLaunch:
        msg += ":J:" 
        for jid in jids_toLaunch:
            msg += str(jid) + "="
            for r in itvs2ids(jobs[jid].res_set):
               msg += str(r) + ","
            msg = msg[:-1] + ";" # replace last comma by semicolon separtor between jobs
        msg = msg[:-1] # remove last semicolon

    else: #Do nothing        
        msg += ":N"

    print msg
    lg = struct.pack("i",int(len(msg)))
    connection.sendall(lg)
    connection.sendall(msg)

def load_json_workload_profile(filename):
    wkp_file = open(filename)
    wkp = json.load(wkp_file)
    return wkp["jobs"], wkp["nb_res"] 

class BatEnv:
    def __init__(self, now):
        self.now = now

class BatSched:
    def __init__(self, res_set, jobs, sched_delay=5, uds_name = '/tmp/bat_socket', mode_platform = "simu"):

        self.sched_delay = sched_delay

        self.env = BatEnv(0)
        self.platform = Platform(mode_platform, env=self.env, resource_set=res_set, jobs=jobs )

        self.jobs = jobs
        self.nb_jobs = len(jobs)
        self.sock = create_uds(uds_name)
        print >>sys.stderr, 'waiting for a connection'
        self.connection, self.client_address = self.sock.accept()
        
        self.platform.running_jids = []
        self.waiting_jids = Set()
        self.platform.waiting_jids = self.waiting_jids
        self.platform.completed_jids = []

    def sched_loop(self):
        nb_completed_jobs = 0
        while nb_completed_jobs < self.nb_jobs:

            now_str, jobs_submitted, new_jobs_completed = read_bat_msg(self.connection)

            #now_str = "10"
            #jobs_submitted = [1]
            #new_jobs_completed = []

            if jobs_submitted:
                for jid in jobs_submitted:
                    self.waiting_jids.add(jid)

            nb_completed_jobs += len(new_jobs_completed)
            
            print "new job completed: ", new_jobs_completed

            for jid in new_jobs_completed:
                jobs_completed.append(jid)
                self.platform.running_jids.remove(jid)
                
            now = int(now_str)
            self.env.now = now #TODO can be remove ???

            print "jobs running:", self.platform.running_jids  
            print "jobs waiting:", self.waiting_jids
            print "jobs completed:", jobs_completed

            print "call schedule_cycle.... ", now
            schedule_cycle(self.platform, now, "test")

            #retrieve jobs to launch
            jids_toLaunch = [] 
            for jid, job in self.platform.assigned_jobs.iteritems():
                print ">>>>>>> job.start_time", job.start_time
                if job.start_time == now:
                    self.waiting_jids.remove(jid)
                    jids_toLaunch.append(jid)
                    job.state = "Running"
                    print "tolaunch:", jid
                    self.platform.running_jids.append(jid)

            now += self.sched_delay
            self.env.now = now

            send_bat_msg(self.connection, now, jids_toLaunch, self.jobs)
        
    def run(self):
        self. sched_loop()
            
##############


#
# Load workload
#

json_jobs, nb_res = load_json_workload_profile(sys.argv[1])

print "nb_res: ", nb_res, type(nb_res)

#
# generate ResourceSet
#

hy_resource_id = [[(i,i)] for i in range(nb_res)]
res_set = ResourceSetSimu(
    rid_i2o = range(nb_res),
    rid_o2i = range(nb_res),
    roid_itvs = [(0,nb_res-1)],
    hierarchy = {'resource_id': hy_resource_id},
    available_upto = {2147483600:[(0,nb_res-1)]}
)

#
# generate jobs
#

for j in json_jobs:
    print "retrieve jobjob"
    jid = int(j["id"])
    jobs[jid] = JobSimu( id = jid,
                         state = "Waiting",
                         queue = "test",
                         start_time = 0,
                         walltime = 0,
                         types = {},
                         res_set = [],
                         moldable_id = 0,
                         mld_res_rqts =  [(jid, j["walltime"] , 
                                           [([("resource_id", j["res"])], [(0,nb_res-1)])])],
                         run_time = 0,
                         key_cache = "",
                         ts=False, ph=0)

BatSched(res_set, jobs).run()