#!/usr/bin/env python 
import sys
from oar.lib import config, get_logger, Job
from oar.kao.platform import Platform
from oar.kao.job import NO_PLACEHOLDER, JobPseudo
from oar.kao.slot import SlotSet, Slot
from oar.kao.scheduling import set_slots_with_prev_scheduled_jobs, \
    schedule_id_jobs_ct 

# Initialize some variables to default value or retrieve from oar.conf configuration file *)

#config['LOG_FILE'] = '/dev/stdout'

log = get_logger("oar.kamelot")

max_time = 2147483648 #(* 2**31 *)
max_time_minus_one = 2147483647 #(* 2**31-1 *)
# Constant duration time of a besteffort job *)
besteffort_duration = 300 #TODO conf ???

#Set undefined config value to default one
default_config = {"HIERARCHY_LABEL": "resource_id,network_address",
                  "SCHEDULER_RESOURCE_ORDER": "resource_id ASC",
                  "SCHEDULER_JOB_SECURITY_TIME": "60",
                  "SCHEDULER_AVAILABLE_SUSPENDED_RESOURCE_TYPE": "default",
                  "FAIRSHARING_ENABLED": "no",
                  "SCHEDULER_FAIRSHARING_MAX_JOB_PER_USER": "30",
}
for k,v in default_config.iteritems():
    if not k in config:
        config[k] = k

def schedule_cycle(plt, now, queue = "default"):

    log.info("Begin scheduling....now: " + str(now) + ", queue: " + queue)
    #
    # Retrieve waiting jobs
    #
 
    waiting_jobs, waiting_jids, nb_waiting_jobs = plt.get_waiting_jobs(queue)
            

    if nb_waiting_jobs > 0:
        log.info("nb_waiting_jobs:" + str(nb_waiting_jobs))
        job_security_time = config["SCHEDULER_JOB_SECURITY_TIME"]

        #
        # Determine Global Resource Intervals and Initial Slot
        #
        resource_set = plt.resource_set()
        initial_slot_set = SlotSet(Slot(1, 0, 0, resource_set.roid_itvs, now, max_time))

        #
        #  Resource availabilty (Available_upto field) is integrated through pseudo job
        #
        pseudo_jobs = []
        for t_avail_upto in sorted(resource_set.available_upto.keys()):
            itvs = resource_set.available_upto[t_avail_upto]
            j = JobPseudo()
            print t_avail_upto, max_time - t_avail_upto, itvs
            j.start_time = t_avail_upto
            j.walltime = max_time - t_avail_upto
            j.res_set = itvs
            j.ts = False
            j.ph = NO_PLACEHOLDER

            pseudo_jobs.append(j)

        if pseudo_jobs != []:
            initial_slot_set.split_slots_prev_scheduled_jobs(pseudo_jobs)

        #
        # Get  additional waiting jobs' data
        #
        plt.get_data_jobs(waiting_jobs, waiting_jids, resource_set, job_security_time)

        #
        # Karma sorting (Fairsharing) 
        #
        if config["FAIRSHARING_ENABLED"] == "yes":
            karma_jobs_sorting(queue, now, jids, jobs, plt)

        #
        # Get already scheduled jobs advanced reservations and jobs from more higher priority queues
        #
        scheduled_jobs = plt.get_scheduled_jobs(resource_set, job_security_time, now)

        all_slot_sets = {0:initial_slot_set}
        
        if scheduled_jobs != []:
            set_slots_with_prev_scheduled_jobs(all_slot_sets, scheduled_jobs, job_security_time) 



        # Retreive jobs' dependencies
        jobs_dependencies = plt.get_current_jobs_dependencies()

        #
        # Scheduled
        #
        schedule_id_jobs_ct(all_slot_sets, waiting_jobs , resource_set.hierarchy,  
                            waiting_jids, job_security_time, jobs_dependencies)

        #
        # Save assignement
        #
        log.info("save assignement")
        
        plt.save_assigns(waiting_jobs, resource_set)
    else:
        log.info("no waiting jobs")

#
# Main function
#

if __name__ == '__main__':
    plt = Platform()
    log.info("argv..."+str(sys.argv))
    if len(sys.argv) > 2:
        schedule_cycle(plt, int(sys.argv[2]), sys.argv[1])
    elif (sys.argv) == 2:
        schedule_cycle(plt, plt.get_time(), sys.argv[1])
    else:
        schedule_cycle(plt, plt.get_time())
    log.info("That's all folks")
