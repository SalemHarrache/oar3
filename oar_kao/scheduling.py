from oar.kao.hierarchy import *
from oar.kao.job import *
from oar.kao.interval import intersec
from oar.kao.slot import Slot, SlotSet, intersec_itvs_slots, intersec_ts_ph_itvs_slots
from oar.lib import get_logger

log = get_logger("oar.kamelot")

def set_slots_with_prev_scheduled_jobs(slots_sets, jobs, job_security_time):

    jobs_slotsets = {0:[]}

    for job in jobs:

        if "container" in job.types:
            t_e = job.start_time + job.walltime - job_security_time
            #print "job.res_set, job.start_time, t_e", job.res_set, job.start_time, t_e
            slots_sets[job.id] = SlotSet(Slot(1, 0, 0, job.res_set, job.start_time, t_e))
            jobs_slotsets[job.id] = []

        ss_id = 0
        if "inner" in job.types:
            ss_id = int(job.types["inner"])

        jobs_slotsets[ss_id].append(job)

    for ss_id,slot_set in slots_sets.iteritems():
        slot_set.split_slots_prev_scheduled_jobs( jobs_slotsets[ss_id] )

def find_resource_hierarchies_job(itvs_slots, hy_res_rqts, hy):
    '''find resources in interval for all resource subrequests of a moldable instance
    of a job'''
    result = []
    for hy_res_rqt in hy_res_rqts:
        (hy_level_nbs, constraints) = hy_res_rqt
        hy_levels = []
        hy_nbs = []
        for hy_l_n in hy_level_nbs:
            (l_name, n) = hy_l_n
            hy_levels.append(hy[l_name])
            hy_nbs.append(n)

        itvs_cts_slots = intersec(constraints, itvs_slots)
        result.extend( find_resource_hierarchies_scattered(itvs_cts_slots, hy_levels, hy_nbs) )

    return result

def find_first_suitable_contiguous_slots(slots_set, job, res_rqt, hy, min_start_time):
    '''find first_suitable_contiguous_slot '''

    (mld_id, walltime, hy_res_rqts) = res_rqt

    itvs = []

    slots = slots_set.slots
    cache = slots_set.cache

    #updated_cache = False
    sid_left = 1
    if min_start_time < 0:
        # to not always begin by the first slots ( O(n^2) )
        #TODO cache_by_container/inner + moldable + time_sharing(?)
        if job.key_cache and job.key_cache in cache:
            sid_left = cache[job.key_cache]
        
    else:
        while slots[sid_left].b < min_start_time:
            sid_left = slots[sid_left].next
        #satisfy job dependencies converted in min start_time
        
    #sid_left = 1 # TODO no cache

    sid_right = sid_left
    slot_e = slots[sid_right].e

    #print 'first sid_left', sid_left

    while True:
        #find next contiguous slots_time
        #print "A: job.id:", job.id, "sid_left:", sid_left, "sid_right:", sid_right

        if sid_left != 0 and sid_right != 0:
            slot_b = slots[sid_left].b
        else:
            #TODO error
            #print "TODO error can't schedule job.id:", job.id 
            log.info( "can't schedule job with id:" + str(job.id) + ", due resources")
            return ([], -1, -1)

        while ( (slot_e-slot_b+1) < walltime):
            sid_right = slots[sid_right].next
            if sid_right != 0:
                slot_e = slots[sid_right].e
            else:
                log.info( "can't schedule job with id:" + str(job.id) + ", due time" )
                return ([], -1, -1)  
            
        #        if not updated_cache and (slots[sid_left].itvs != []):
        #            cache[walltime] = sid_left
        #            updated_cache = True

        if job.ts or (job.ph == USE_PLACEHOLDER):
            itvs_avail = intersec_ts_ph_itvs_slots(slots, sid_left, sid_right, job)
        else:
            itvs_avail = intersec_itvs_slots(slots, sid_left, sid_right)
        #print "itvs_avail", itvs_avail, "h_res_req", hy_res_rqts, "hy", hy
        itvs = find_resource_hierarchies_job(itvs_avail, hy_res_rqts, hy)

        if (itvs != []):
            break

        sid_left = slots[sid_left].next

    if job.key_cache and min_start_time > 0: #exclude job w/ dependencies
        cache[job.key_cache] = sid_left

    return (itvs, sid_left, sid_right)

def assign_resources_mld_job_split_slots(slots_set, job, hy, min_start_time):
    '''Assign resources to a job and update by spliting the concerned slots - moldable version'''
    prev_t_finish = 2**32-1 # large enough
    prev_res_set = []
    prev_res_rqt = []
    prev_id_slots = []

    slots = slots_set.slots
    prev_start_time = slots[1].b

    for res_rqt in job.mld_res_rqts:
        (mld_id, walltime, hy_res_rqts) = res_rqt
        (res_set, sid_left, sid_right) = find_first_suitable_contiguous_slots(slots_set, job, res_rqt, hy, min_start_time)
        if res_set == []: #no suitable time*resources found
            job.res_set = []
            job.start_time = -1
            job.moldable_id = -1
            return
        #print "after find fisrt suitable"
        t_finish = slots[sid_left].b + walltime
        if (t_finish < prev_t_finish):
            prev_start_time = slots[sid_left].b
            prev_t_finish = t_finish
            prev_res_set = res_set
            prev_res_rqt = res_rqt
            prev_sid_left = sid_left
            prev_sid_right = sid_right

    (mld_id, walltime, hy_res_rqts) = prev_res_rqt
    job.moldable_id = mld_id
    job.res_set = prev_res_set
    job.start_time = prev_start_time
    job.walltime = walltime

    #Take avantage of job.starttime = slots[prev_sid_left].b
    #print prev_sid_left, prev_sid_right, job.moldable_id , job.res_set, job.start_time , job.walltime, job.mld_id 

    slots_set.split_slots(prev_sid_left, prev_sid_right, job)

def schedule_id_jobs_ct(slots_sets, jobs, hy, id_jobs, job_security_time, jobs_dependencies):
    '''Schedule loop with support for jobs container - can be recursive (recursivity has not be tested)'''

    #    for k,job in jobs.iteritems():
    #print "*********j_id:", k, job.mld_res_rqts[0]

    for jid in id_jobs:

        #Dependencies 
        min_start_time = -1 
        to_skip = False
        if jid in jobs_dependencies:
            for j_dep in jobs_dependencies[jid]:
                jid_dep, state, exit_code = j_dep
                if state == "Error":
                    log.info("job(" + str(jid_dep) +") in dependencies for job("
                             + str(jid) + ") is in error state") 
                    #TODO  set job to ERROR"
                    to_skip = True
                    break
                elif state == "Waiting":
                    #determine endtime
                    if jid_dep in jobs:
                        job_dep = jobs[jid_dep]
                        job_stop_time = job.start_time + job.walltime
                        if job_stop_time > min_start_time:
                            min_start_tim = job_stop_time
                    else:
                        #TODO
                        to_skip = True
                        break
                elif state == "Terminated" and exit_code ==0:
                    next
                else:
                    to_skip = True
                    break
                    
        if to_skip:
            log.info("job(" + str(jid) + "can't be scheduled due to dependencies")
        else:
            job = jobs[jid]
            #print "j_id:", jid, job.mld_res_rqts[0]
            #TODO
            #if jobs_dependencies[j_id].has_key(j_id):
            #    continue
            #else:

            ss_id = 0
            if "inner" in job.types:
                ss_id = int(job.types["inner"])

            slots_set = slots_sets[ss_id]

            assign_resources_mld_job_split_slots(slots_set, job, hy, min_start_time)            

            if "container" in job.types:                
                slot = Slot(1, 0, 0, job.res_set[:], job.start_time,
                            job.start_time + job.walltime - job_security_time)
                #slot.show()
                slots_sets[job.id] = SlotSet(slot)