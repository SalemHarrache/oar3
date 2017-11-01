#!/usr/bin/env python
# coding: utf-8

import os
import pkg_resources

from oar.lib import (config, get_logger)

from oar.lib.job_handling import (get_job, get_job_challenge, get_job_current_hostnames, check_end_of_job,
                                  get_current_moldable_job, set_job_state, archive_some_moldable_job_nodes)

from oar.lib.resource_handling import get_current_assigned_job_ressource

from oar.lib.tools import (DEFAULT_CONFIG, limited_dict2hash_perl)

from oar.lib.event import add_new_event

from oar.lib.tools import (Popen, TimeoutExpired, spawn, exceptions)
                           
logger = get_logger("oar.modules.bipbip", forward_stderr=True)

class BipBip(object):

    def __init__(self, args):
        config.setdefault_config(DEFAULT_CONFIG)
        self.server_prologue = config['SERVER_PROLOGUE_EXEC_FILE']
        self.server_epilogue = config['SERVER_EPILOGUE_EXEC_FILE']

        self.exit_code = 0

        self.job_id = args[0]

        self.oarexec_reattach_exit_value = None
        self.oarexec_reattach_script_exit_value = None
        self.oarexec_challenge = None
        if len(args) >= 2:
            
            self.oarexec_reattach_exit_value = args[1]
        if len(args) >= 3:
            self.oarexec_reattach_script_exit_value = args[2]
        if len(args) >= 4:
            self.oarexec_challenge = args[3]
            
        set_ssh_timeout(congig[OAR_SSH_CONNECTION_TIMEOUT]) # TODO ???
        
    def run(self):
        
        job_id = self.job_id

        node_file_db_field = config['NODE_FILE_DB_FIELD']
        node_file_db_field_distinct_values = config['NODE_FILE_DB_FIELD_DISTINCT_VALUES']

        cpuset_field = ''
        cpuset_name = ''
        if 'JOB_RESOURCE_MANAGER_PROPERTY_DB_FIELD' in config:
            cpuset_field = config['JOB_RESOURCE_MANAGER_PROPERTY_DB_FIELD'] 
            cpuset_name = get_job_cpuset_name(job_id)
        
        cpuset_file = config['JOB_RESOURCE_MANAGER_FILE']
        if not re.match(r'^\/', cpuset_file):
            if 'OARDIR' not in os.environ:
                msg = '$OARDIR variable envionment must be defined'
                logger.error(msg)
                raise (msg)
            cpuset_file = os.environ['OARDIR'] + '/' + cpuset_file

        cpuset_path = config['CPUSET_PATH']
        cpuset_full_path = cpuset_path +'/' + cpuset_name
        
        job_challenge, ssh_private_key, ssh_public_key = get_job_challenge(job_id)
        hosts = get_job_current_hostnames(job_id)
        job = get_job(job_id)
        
        #Check if we must treate the end of a oarexec
        if self.oarexec_reattach_exit_value and job.state in ['Launching', 'Running', 'Suspended', 'Resuming']:
            logger.debug('[' + str(job.id) + '] OAREXEC end: ' + self.oarexec_reattach_exit_value\
                         + ' ' + self.oarexec_reattach_script_exit_value)
            
            try: 
                int(self.oarexec_reattach_exit_value)
                
            except ValueError:
                logger.error('[' + str(job.id) + '] Bad argument for bipbip : ' + self.oarexec_reattach_exit_value)
                self.exit_code = 2
                return

            if self.oarexec_challenge == job_challenge:
                check_end_of_job(job_id, self.oarexec_reattach_script_exit_value, self.oarexec_reattach_exit_value,
                                 hosts, job.user, job.launching_directory, self.server_epilogue)
                return
            else:
                msg =  'Bad challenge from oarexec, perhaps a pirate attack??? ('\
                       + self.oarexec_challenge + '/' + job_challenge + ').'
                logger.error('[' + str(job.id) + '] ' + msg)
                add_new_event('BIPBIP_CHALLENGE', job_id, msg)
                self.exit_code = 2
                return

        if job.state == 'toLaunch':
            # Tell that the launching process is initiated
            set_job_state(job_id, 'Launching')
            job.state = 'Launching'
        else:
            logger.warning('[' + str(job.id) + '] Job already treated or deleted in the meantime')
            self.exit_code = 1
            return
        
        resources = get_current_assigned_job_resource(job.assigned_moldable_job)
        mold_job_description = get_current_moldable_job(job.assigned_moldable_job)
            
        # NOOP jobs
        job_types = get_job_types(job.id)
        if 'noop' in job_types.keys():
            set_job_state(job_id, 'Running')
            logger.debug('[' + str(job.id) + '] User: ' + job.user + ' Set NOOP job to Running')
            call_server_prologue()
            return
            
        # HERE we must launch oarexec on the first node
        logger.debug('[' + str(job.id) + '] User: ' + job.user + '; Command: ' + job.command\
                      + ' ==> hosts : ' + str(hosts))

        if (job.type == 'INTERACTIVE') and (job.reservation == 'None'):
            tools.notify_interactif_user(job, 'Starting...')

        if ('deploy' not in job_types.keys()) and ('cosystem' not in job_types.keys()) and (len(hosts) > 0):
            bad = []
            event_type = ''
            ###############
            # CPUSET PART #
            ###############
            nodes_cpuset_fields = None
            if cpuset_field:
                nodes_cpuset_fields = get_cpuset_values(self.cpuset_field, job.assigned_moldable_job)
                
            ssh_public_key = format_ssh_pub_key(ssh_public_key, cpuset_full_path, job.user, job.user)
            
            cpuset_data_hash = {
                'job_id': job.id,
                'name': cpuset_name,
                'nodes': cpuset_nodes,
                'cpuset_path': cpuset_path,
                'ssh_keys': {
                    'public': {
                        'file_name': config['OAR_SSH_AUTHORIZED_KEYS_FILE'],
                        'key': ssh_public_key
                    },
                    'private': {
                        'file_name': get_private_ssh_key_file_name(cpuset_name),
                        'key': ssh_private_key
                    },
                },
                'oar_tmp_directory': config['OAREXEC_DIRECTORY'],        
                'user': job_user,
                'job_user': job_user,
                'types': job_types,
                'resources': resources,
                'node_file_db_fields': node_file_db_field,
                'node_file_db_fields_distinct_values': node_file_db_field_distinct_values,
                'array_id': job.array_id,
                'array_index': job.array_index,
                'stdout_file': job.stdout_file.replace('%jobid%', str(job.id)),
                'stderr_file': job.stderr_file.replace('%jobid%', str(job.id)),
                'launching_directory': job.launching_directory,
                'job_name': job.name,
                'walltime_seconds': 'undef',
                'walltime': 'undef',
                'project': job.project,
                'log_level': config['LOG_LEVEL']
            }

            if len(nodes_cpuset_fields) > 0:
                taktuk_cmd = config['TAKTUK_CMD']
                cpuset_data_str = limited_dict2hash_perl(cpuset_data_hash)
                tag, bad_tmp = tools.manage_remote_commands(nodes_cpuset_fields.keys(),
                                                        cpuset_data_str, cpuset_file,
                                                        'init', openssh_cmd, taktuk_cmd)
                if tag == 0:
                    msg = '[JOB INITIATING SEQUENCE] [CPUSET] [' + str(job.id)\
                          + '] Bad cpuset file: ' + cpuset_file
                    logger.error(msg)
                    events.append(('CPUSET_MANAGER_FILE', msg, None))
                elif len(bad) > 0:
                    bad = bad + bad_tmp
                    event_type = 'CPUSET_ERROR'
                    # Clean already configured cpuset
                    tmp_array = nodes_cpuset_fields.keys()
                    if (len(bad) > 0) and (len(tmp_array) > len(bad)):
                        # Verify if the job is a reservation
                        if (job.reservation != 'None'):
                            # Look at if there is at least one alive node for the reservation
                            tmp_hosts = [h for h in hosts if h not in bad]
                            set_job_state(job_id, 'One or several nodes are not responding correctly(CPUSET_ERROR)')

                            add_new_event_with_host(event_type, job_id, '[bipbip] OAR cpuset suspects nodes for the job '\
                                                    + str(job_id) + ': ' + str(bad), bad)
                            archive_some_moldable_job_nodes(job.assigned_moldable_job, bad)
                            tools.notify_almighty('ChState')
                            hosts = tmp_hosts
                            bad = []
                        else:
                            # remove non initialized nodes
                            for h in bad:
                                nodes_cpuset_fields.pop(h)
                            cpuset_data_str = limited_dict2hash_perl(cpuset_data_hash)
                            tag, bad_tmp = tools.manage_remote_commands(nodes_cpuset_fields.keys(),
                                                                        cpuset_data_str, cpuset_file,
                                                                        'clean', openssh_cmd, taktuk_cmd)
                            bad = bad + bad_tmp
                
            #####################
            # CPUSET PART, END  #
            #####################

            # Check nodes
            if bad == []:
                # check nodes
                logger.debug('[' + str(job.id) + '] Check nodes: ' + str(hosts))
                event_type = 'PING_CHECKER_NODE_SUSPECTED'
                bad = tools.pingchecker(hosts)             

            if bad > 0:
                set_job_state(job_id, 'One or several nodes are not responding correctly')
                logger.error('[' + str(job.id) + ']  /!\ Some nodes are inaccessible (' + event_type\
                             + '):\n' + str(bad))
                exit_bipbip = 1
                if (job.type == 'INTERACTIVE') and (job.reservation == 'None'):
                    tools.notify_interactif_user(job, 'ERROR: some resources did not respond')
                else:
                    # Verify if the job is a reservation
                    if job.reservation != 'None':
                        # Look at if there is at least one alive node for the reservation
                        tmp_hosts = [h for h in hosts if h not in bad]
                        if tmp_hosts == []:
                            add_new_event('RESERVATION_NO_NODE', job_id, 'There is no alive node for the reservation '\
                                          + str(job_id) + '.')
                        else:
                            host = tmp_hosts
                            exit_bipbip = 0
                            
                add_new_event_with_host(event_type, job_id, '[bipbip] OAR suspects nodes for the job :'\
                                        + str(job_id) + ': ' + str(bad))
                tools.notify_almighty('ChState')
                if exit_bipbip == 1:
                    self.exit_code = 2
                    return
                
            else:
               logger.debug('[' + str(job.id) + '] No (enough) bad node')
            # end CHECK
            
        call_server_prologue(job)
        
        # CALL OAREXEC ON THE FIRST NODE
        pro_epi_timeout = config['PROLOGUE_EPILOGUE_TIMEOUT']
        prologue_exec_file = config['PROLOGUE_EXEC_FILE']
        epilogue_exec_file = config['EPILOGUE_EXEC_FILE']

        
        oarexec_files = (pkg_resources.resource_filename('oar', 'scripts/Tools.pm'),
                         pkg_resources.resource_filename('oar', 'scripts/oarexec'))
        
        head_node = hosts[0]
        
        #deploy, cosystem and no host part
        if ('cosystem' in job_types.keys()) or (len(hosts == 0)):
            head_node = config['COSYSTEM_HOSTNAME']
        elif 'deploy' in job_types.keys():
            head_node = config['DEPLOY_HOSTNAME']


        logger.debug('[' + str(job.id) + '] Execute oarexec on node: ' + head_node)

        oarexec_cpuset_path = ''
        if cpuset_full_path and ('cosystem' not in job_types.keys()) and ('deploy' not in job_types.keys()) and len(hosts > 0):
            # So oarexec will retry several times to contact Almighty until it will be
            # killed by the cpuset manager
            oarexec_cpuset_path = cpuset_full_path

            data_to_transfer = {
                'job_id': job_id,
                'array_id': job.array_id,
                'array_index': job.array_index,
                'stdout_file': job.stdout_file.replace('%jobid%', str(job.id)),
                'stderr_file': job.stderr_file.replace('%jobid%', str(job.id)),                
                'launching_directory': job.launching_directory,
                'job_env': job.env,
                'resources': resources,
                'node_file_db_fields': node_file_db_field,
                'node_file_db_fields_distinct_values': node_file_db_field_distinct_values,
                'user': job.user,
                'job_user': job.user,
                'types': types,
                'name': job.name,
                'project': job.project,
                'reservation': job.reservation,
                'walltime_seconds': mold_job_description.walltime,
                'command': job.command,
                'challenge': job.challenge,
                'almighty_hostname': config['SERVER_HOSTNAME'],
                'almighty_port': config['SERVER_PORT'],
                'checkpoint_signal': job.checkpoint_signal,
                'debug_mode': config['OAREXEC_DEBUG_MODE'],
                'mode': job.type,
                'pro_epi_timeout': pro_epi_timeout,
                'prologue': prologue_exec_file,
                'epilogue': epilogue_exec_file,
                'tmp_directory': config['OAREXEC_DIRECTORY'],  
                'detach_oarexec': config['DETACH_JOB_FROM_SERVER'],
                'cpuset_full_path': oarexec_cpuset_path
            }
        error = 50
        exit_script_value = 'N'
        init_done = 0

        #timeout = pro_epi_timeout + config['BIPBIP_OAREXEC_HASHTABLE_SEND_TIMEOUT'] + config['TIMEOUT_SSH']
        cmd = Openssh_cmd
        if cpuset_full_path and ('cosystem' not in job_types.keys()) and ('deploy' not in job_types.keys()) and len(hosts > 0):
            # for oarsh_shell connection
            os.environ['OAR_CPUSET'] = cpuset_full_path
            cmd = cmd +' -oSendEnv=OAR_CPUSET'
        else:
            os.environ['OAR_CPUSET'] = ''

        cmd = cmd + ' -x' +  ' -T ' + head_node + ' perl - ' + str(job_id) + 'OAREXEC'


        child = spawn(cmd)

        for filename in oarexec_files:
            with open(filename, 'r') as f:
                for line in f:
                    child.sendline(line)

        # End of oarexec script transfer
        child.sendline('__END__\n')

        # Check End of oarexec script transfer
        try:
            child.expect('__END__', timeout=int(config['TIMEOUT_SSH']))
        except exceptions.TIMEOUT as e:
            pass
        
        # Send data structure for oarexec
        try:
            child.sendline(limited_dict2hash_perl(data_to_transfer) + '\n',
                           timeout=int(config['BIPBIP_OAREXEC_HASHTABLE_SEND_TIMEOUT']))
        except exceptions.TIMEOUT as e:
            pass
        
        # Read oarexec output

        while True:
            if init_done == 0:
                index = child.expect([config['SSH_RENDEZ_VOUS'] + '\r\n', exceptions.TIMEOUT])
                if index == 0:
                    init_done = 1
            
                    set_job_state(job_id,'Running')

                    # Notify interactive oarsub
                    if (job.type == 'INTERACTIVE') and (job.reservation == 'None'):
                        logger.debug('[' + str(job.id) + '] Interactive request ;Answer to the client Qsub -I')
                        if tools.notify_interactif_user('GOOD JOB'):
                            logger.error('[' + str(job.id)\
                                         + '] Frag job because oarsub cannot be notified by the frontend. Check your network and firewall configuration\n')
                            tools.notify_almighty('Qdel')

                else:
                    # Timeout
                    pass
            else:
                try:
                    child.expect('OAREXEC_SCRIPT_EXIT_VALUE\s*(\d+|N)', timeout=pro_epi_timeout)
                    exit_script_value = child.match.group(1)
                except exceptions.TIMEOUT as e:
                    pass
                
        child.close()
        error = child.exitstatus
    
        if (detach_oarexec == 1) and (error == 0):
            logger.debug('[' + str(job.id) + '] Exit from bipbip normally')
        else:
            if init_done == 0:
                if (job.type == 'INTERACTIVE') and (job.reservation == 'None'):
                    tools.notify_interactif_user('ERROR: an error occured on the first job node')
                    
            check_end_of_job(job_id, self.oarexec_reattach_script_exit_value, error,
                             hosts, job.user, job.launching_directory, self.server_epilogue)
        return
        
        
    def call_server_prologue(job):
        # PROLOGUE EXECUTED ON OAR SERVER #
        # Script is executing with job id in arguments
        if self.server_prologue:
            timeout = config['SERVER_PROLOGUE_EPILOGUE_TIMEOUT']
            cmd = [self.server_prologue, str(job.id)]

            try:
                child = Popen(cmd)
                return_code = child.wait(timeout)

                if return_code:
                    msg = '[' + str(job.id) + '] Server prologue exit code: ' + str(return_code)\
                          + ' (!=0) (cmd: ' + str(cmd) + ')'
                    logger.error(msg)
                    add_new_event('SERVER_PROLOGUE_EXIT_CODE_ERROR', job.id, '[bipbip] ' + msg)
                    tools.notify_almighty('ChState')
                    if (job.type == 'INTERACTIVE') and (job.reservation == 'None'):
                        tools.notify_interactif_user(job, 'ERROR: SERVER PROLOGUE returned a bad value')
                    self.exit_code = 2
                    return 1
                
            except OSError as e:   
                logger.error('Cannot run: ' + str(cmd))
                
            except TimeoutExpired as e:
                tools.kill_child_processes(child.pid)
                msg = '[' + str(job.id) + '] Server prologue timeouted (cmd: ' + str(cmd)
                logger.error(msg)
                add_new_event('SERVER_PROLOGUE_TIMEOUT', job.id, '[bipbip] ' + msg)
                tools.notify_almighty('ChState')
                if (job.type == 'INTERACTIVE') and (job.reservation == 'None'):
                    tools.notify_interactif_user(job, 'ERROR: SERVER PROLOGUE timeouted')
                self.exit_code = 2
                return 1
            
            return 0
            
            
def main():
    bipbip = BipBip()
    bipbip.run()
    return bipbip.exit_code
    
if __name__ == '__main__':  # pragma: no cover
    if len(sys.argv) < 2:
        # TODO
        sys.exit(1)
        
    exit_code = main(sys.argv[1:])
    sys.exit(exit_code)