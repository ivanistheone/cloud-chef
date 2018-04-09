import datetime
from io import BytesIO
from itertools import groupby
import json
import os
import pipes
import re
import time

from fabric.api import env, task, local, sudo, run
from fabric.api import get, put, require
from fabric.colors import red, green, blue, yellow
from fabric.context_managers import cd, prefix, show, hide, shell_env
from fabric.contrib.files import exists, sed, upload_template
from fabric.utils import puts



# FAB SETTTINGS
################################################################################
env.user = os.environ.get('USER')
env.password = os.environ.get('SUDO_PASSWORD')

env.roledefs = {
    'vader': {
        'hosts':['eslgenie.com:1'],           # because vader runs ssh on port 1
    },
    'cloud-kitchen': {
        'hosts': ['35.227.153.135'],
    },
}



# CHEF INVENTORY
################################################################################
from inventory import ( NICKNAME_KEY,
                        CHANNEL_ID_KEY,
                        CHANNEL_NAME_KEY,
                        GITHUB_REPO_URL_KEY,
                        POST_SETUP_COMMAND_KEY,
                        WORKING_DIRECTORY_KEY,
                        COMMAND_KEY,
                        CRONTAB_KEY,
                        CHEFDIRNAME_KEY)
from inventory import load_inventory
INVENTORY = load_inventory()


# GLOBAL CHEF SETTINGS
################################################################################
CHEF_USER = 'chef'
STUDIO_TOKEN = os.environ.get('STUDIO_TOKEN')
DEFAULT_GIT_BRANCH = 'master'
CHEFS_DATA_DIR = '/data'
CHEFS_LOGS_DIR = '/data/var/log'
CHEFS_PID_DIR = '/data/var/run'
CHEFS_CMDSOCKS_DIR = '/data/var/cmdsocks'



# CHEF RUN
################################################################################

@task
def run_chef(nickname, nohup=None):
    if STUDIO_TOKEN is None:
        raise ValueError('Must specify STUDIO_TOKEN env var on command line')
    nohup = (nohup == 'True' or nohup == 'true')

    chef_info = INVENTORY[nickname]
    CHEF_DATA_DIR = os.path.join(CHEFS_DATA_DIR, chef_info[CHEFDIRNAME_KEY])
    chef_cwd = chef_info[WORKING_DIRECTORY_KEY]

    if chef_cwd:
        chef_run_dir = os.path.join(CHEF_DATA_DIR, chef_cwd)
    else:
        chef_run_dir = CHEF_DATA_DIR

    with cd(chef_run_dir):
        with prefix('source ' + os.path.join(CHEF_DATA_DIR, 'venv/bin/activate')):
            if nohup == False:
                # Normal operation (blocking)
                cmd = chef_info[COMMAND_KEY].format(studio_token=STUDIO_TOKEN)
                sudo(cmd, user=CHEF_USER)
            else:
                # Run in background
                cmd_prefix = 'nohup '
                cmd = chef_info[COMMAND_KEY].format(studio_token=STUDIO_TOKEN)
                cmd_suffix = ' & '
                cmd_sleep = '(' + cmd_prefix + cmd + cmd_suffix + ') && sleep 1'
                sudo(cmd_sleep, user=CHEF_USER)  # via https://stackoverflow.com/a/43152236
                nohupout = os.path.join(chef_run_dir, 'nohup.out')
                puts(green('Chef started in backround. Use `tail -f ' + nohupout + '` to see logs.'))



# CHEF SETUP
################################################################################

@task
def setup_chef(nickname, branch_name=DEFAULT_GIT_BRANCH):
    chef_info = INVENTORY[nickname]
    CHEF_DATA_DIR = os.path.join(CHEFS_DATA_DIR, chef_info[CHEFDIRNAME_KEY])

    with cd(CHEFS_DATA_DIR):
        if exists(CHEF_DATA_DIR):
            puts(yellow('Directory ' + CHEF_DATA_DIR + ' already exists.'))
            return
        sudo('git clone  --quiet  ' + chef_info[GITHUB_REPO_URL_KEY])
        sudo('chown -R {}:{}  {}'.format(CHEF_USER, CHEF_USER, CHEF_DATA_DIR))
        # checkout the desired branch
        with cd(CHEF_DATA_DIR):
            sudo('git checkout ' + branch_name, user=CHEF_USER)
        # setup python virtualenv
        with cd(CHEF_DATA_DIR):
            sudo('virtualenv -p python3.5  venv', user=CHEF_USER)

        with cd(CHEF_DATA_DIR):
            activate_sh = os.path.join(CHEF_DATA_DIR, 'venv/bin/activate')
            reqs_filepath = os.path.join(CHEF_DATA_DIR, 'requirements.txt')
            # Nov 23: workaround____ necessary to avoid HOME env var being set wrong
            with prefix('export HOME=/data && source ' + activate_sh):
                # install requirements
                sudo('pip install --no-input --quiet -r ' + reqs_filepath, user=CHEF_USER)
                # run post-setup command
                sudo(chef_info[POST_SETUP_COMMAND_KEY], user=CHEF_USER)
        puts(green('Setup chef code from ' + chef_info[GITHUB_REPO_URL_KEY] + ' in ' + CHEF_DATA_DIR))

@task
def unsetup_chef(nickname):
    chef_info = INVENTORY[nickname]
    CHEF_DATA_DIR = os.path.join(CHEFS_DATA_DIR, chef_info[CHEFDIRNAME_KEY])
    sudo('rm -rf  ' + CHEF_DATA_DIR)
    puts(green('Removed chef direcotry ' + CHEF_DATA_DIR))


@task
def update_chef(nickname, branch_name=DEFAULT_GIT_BRANCH):
    chef_info = INVENTORY[nickname]
    CHEF_DATA_DIR = os.path.join(CHEFS_DATA_DIR, chef_info[CHEFDIRNAME_KEY])
    
    with cd(CHEF_DATA_DIR):
        sudo('git fetch origin  ' + branch_name, user=CHEF_USER)
        sudo('git checkout ' + branch_name, user=CHEF_USER)
        sudo('git reset --hard origin/' + branch_name, user=CHEF_USER)

    # update requirements
    activate_sh = os.path.join(CHEF_DATA_DIR, 'venv/bin/activate')
    reqs_filepath = os.path.join(CHEF_DATA_DIR, 'requirements.txt')
    with prefix('export HOME=/data && source ' + activate_sh):
        sudo('pip install -U --no-input --quiet -r ' + reqs_filepath, user=CHEF_USER)





# CHEF CRONJOB SCHEDULING 
################################################################################

def add_args(cmd, args_dict):
    """
    Insert the command line arguments from `args_dict` into a chef run command.
    Assumes `cmd` contains the substring `--token` and inserts args right before
    instead of appending to handle the case where cmd contains extra options. 
    """
    args_str = ''
    for argk, argv in args_dict.items():
        if argv is not None:
            args_str += ' ' + argk + '=' + argv + ' '
        else:
            args_str += ' ' + argk + ' '
    return cmd.replace('--token', args_str + ' --token')

def _read_pid_file_contents(pid_file):
    if not exists(pid_file):
        print('operational error: PID file missing in /data/var/run/')
        return None
    tmp_fd = BytesIO()
    with hide('running'):
        get(pid_file, tmp_fd)
    pid_str = tmp_fd.getvalue().decode('ascii').strip()
    return pid_str

def _check_process_running(pid_file):
    pid_str = _read_pid_file_contents(pid_file)
    if len(pid_str)==0:
        return False
    processes  = psaux()
    found = False
    for process in processes:
        if process['PID'] == pid_str:
            found = True
    return found

@task
def start_chef_daemon(nickname):
    chef_info = INVENTORY[nickname]
    CHEF_DATA_DIR = os.path.join(CHEFS_DATA_DIR, chef_info[CHEFDIRNAME_KEY])
    chef_cwd = chef_info[WORKING_DIRECTORY_KEY]
    if chef_cwd:
        chef_run_dir = os.path.join(CHEF_DATA_DIR, chef_cwd)
    else:
        chef_run_dir = CHEF_DATA_DIR
    now = datetime.datetime.now()
    now_str = now.strftime('%Y-%m-%d')
    log_file = os.path.join(CHEFS_LOGS_DIR, nickname + 'd__started_' + now_str + '.log')
    pid_file = os.path.join(CHEFS_PID_DIR, nickname + 'd.pid')
    cmdsock_file = os.path.join(CHEFS_CMDSOCKS_DIR, nickname + 'd.sock')

    # Check if pid file exists
    if exists(pid_file):
        running = _check_process_running(pid_file)
        if running:
            puts(red('ERROR: the ' + nickname + ' daemon is already running, see ' + pid_file))
            return
        else:
            puts(yellow('WARNING: A PID file for the ' + nickname + ' daemon exists: ' + pid_file))
            puts(yellow('but a process with this PID is not running...'))
            puts(yellow('Deleting ' + pid_file + ' contrinuing noram operatoin...'))
            sudo('rm -f ' + pid_file)

    with cd(chef_run_dir):
        with prefix('source ' + os.path.join(CHEF_DATA_DIR, 'venv/bin/activate')):
            cmd_prefix = 'nohup '
            orig_cmd = chef_info[COMMAND_KEY].format(studio_token=STUDIO_TOKEN)
            new_cmd = add_args(orig_cmd, {'--daemon':None, '--cmdsock':cmdsock_file})
            cmd_suffix = ' > {log_file} 2>&1 & echo $! > {pid_file}'.format(log_file=log_file, pid_file=pid_file)
            cmd = cmd_prefix + new_cmd + cmd_suffix
            puts(green('Starting ' + nickname + ' chef daemon...'))
            sudo('(' + cmd + ') && sleep 1', user=CHEF_USER)  # via https://stackoverflow.com/a/43152236
            time.sleep(0.3)
            running = _check_process_running(pid_file)
            if running:
                pid_str = _read_pid_file_contents(pid_file)
                puts(green('Chef daemon started with PID=' + pid_str))
            else:
                puts(red('Chef daemon failed to start. Check /data/var/log/'))


@task
def stop_chef_daemon(nickname):
    chef_info = INVENTORY[nickname]
    pid_file = os.path.join(CHEFS_PID_DIR, nickname + 'd.pid')
    cmdsock_file = os.path.join(CHEFS_CMDSOCKS_DIR, nickname + 'd.sock')

    if exists(pid_file):
        running = _check_process_running(pid_file)
        if running:
            pid_str = _read_pid_file_contents(pid_file)
            sudo('kill -SIGTERM ' + pid_str)
            time.sleep(0.3)
            running = _check_process_running(pid_file)
            if not running:
                sudo('rm -f ' + pid_file)
                sudo('rm -f ' + cmdsock_file)
                puts(green('Successfully stopped ' + nickname + ' chef daemon.'))
            else:
                puts(red('Failed to kill chef daemon with PID=' + pid_str))
        else:
            puts(yellow('WARNING: A PID file for the ' + nickname + ' daemon exists: ' + pid_file))
            puts(yellow('but a process with this PID is not running...'))
            puts(yellow('Deleting ' + pid_file + ' contrinuing noram operatoin...'))
            sudo('rm -f ' + pid_file)
    else:
        puts(red('Chef daemon not running. PID file not found ' + pid_file))




@task
def list_scheduled_chefs(print_cronjobs=True):
    with hide('running', 'stdout'):
        result = sudo('crontab -l', user=CHEF_USER)
    cronjobs = [line for line in result.splitlines() if not line.startswith('#')]
    if print_cronjobs:
        for cronjob in cronjobs:
            print(cronjob)
    return cronjobs

@task
def schedule_chef(nickname):
    chef_info = INVENTORY[nickname]
    cronjobs = list_scheduled_chefs(print_cronjobs=False)
    if any([nickname in cronjob for cronjob in cronjobs]):
        puts(red('ERROR: chef is already scheduled! Current crontab contains:'))
        list_scheduled_chefs(print_cronjobs=True)
        return
    command = """/bin/echo '{"command":"start", "args":{"stage":true} }' | """ + \
              """/bin/nc -UN  /data/var/cmdsocks/{n}d.sock""".format(n=nickname)
    crontab_schedule = chef_info[CRONTAB_KEY]
    new_cronjob = crontab_schedule + ' ' + command
    cronjobs.append(new_cronjob)
    cronjobs_str = '\n'.join(cronjobs)
    escaped_str = pipes.quote(cronjobs_str)
    sudo("echo {} | crontab - ".format(escaped_str), user=CHEF_USER)

@task
def unschedule_chef(nickname):
    cronjobs = list_scheduled_chefs(print_cronjobs=False)    
    if not any([nickname in cronjob for cronjob in cronjobs]):
        puts(red('ERROR: chef not scheduled, so cannot unschedule.'))
        return
    newcronjobs = []
    for cronjob in cronjobs:
        if nickname not in cronjob:
            newcronjobs.append(cronjob)    
    newcronjobs_str = '\n'.join(newcronjobs)
    escaped_str = pipes.quote(newcronjobs_str)
    sudo("echo {} | crontab - ".format(escaped_str), user=CHEF_USER)



# INFO
################################################################################

@task
def print_info():
    with cd(CHEFS_DATA_DIR):
        sudo("ls")
        sudo("whoami")
        run("ls")
        run("whoami")

@task
def pstree():
    result = sudo('pstree -p')
    print(result.stdout)


def parse_psaux(psaux_str):
    """
    Parse the output of `ps aux` into a list of dictionaries representing the parsed
    process information from each row of the output. Keys are mapped to column names,
    parsed from the first line of the process' output.
    :rtype: list[dict]
    :returns: List of dictionaries, each representing a parsed row from the command output
    """
    lines = psaux_str.split('\n')
    # lines = subprocess.Popen(['ps', 'aux'], stdout=subprocess.PIPE).stdout.readlines()
    headers = [h for h in ' '.join(lines[0].strip().split()).split() if h]
    raw_data = map(lambda s: s.strip().split(None, len(headers) - 1), lines[1:])
    return [dict(zip(headers, r)) for r in raw_data]


@task
def psaux_str():
    with hide('running', 'stdout'):
        result = sudo('ps aux')
    print(result)

@task
def psaux():
    with hide('running', 'stdout'):
        result = sudo('ps aux')
    processes = parse_psaux(result)
    return processes

@task
def pypsaux():
    processes  = psaux()
    pyprocesses = []
    for process in processes:
        if 'python' in process['COMMAND']:
            pyprocesses.append(process)

    # detokenify
    TOKEN_PAT = re.compile(r'--token=(?P<car>[\da-f]{6})(?P<cdr>[\da-f]{34})')
    def _rmtoken_sub(match):
        return '--token=' +match.groupdict()['car'] + '...'
    for pyp in pyprocesses:
        pyp['COMMAND'] = TOKEN_PAT.sub(_rmtoken_sub, pyp['COMMAND'])

    # sort and enrich with current working dir (cwd)
    pyprocesses = sorted(pyprocesses, key=lambda pyp: pyp['COMMAND'])
    for cmd_str, process_group in groupby(pyprocesses, lambda vl: vl['COMMAND']):
        process_group = list(process_group)
        with hide('running', 'stdout'):
            cwd_str = sudo('pwdx {}'.format(process_group[0]['PID'])).split(':')[1].strip()
        for pyp in process_group:
            pyp['cwd'] = cwd_str

    # print tab-separated output
    for pyp in pyprocesses:
        output_vals = [
            pyp['PID'],
            pyp['START'],
            pyp['TIME'],
            pyp['COMMAND'],
            '(cwd='+pyp['cwd']+')',
        ]
        print('\t'.join(output_vals))



# SYSADMIN TASKS (provision a new cloud chef host semi-automatically)
################################################################################

@task
def provision_cloud_kitchen():
    puts(blue('MANUAL STEPS REQUIRED:'))
    puts(blue('Use the Google Cloud Console to provision a new instance:'))
    puts(blue('https://console.cloud.google.com/compute/instancesAdd?project=kolibri-demo-servers'))
    puts(blue('Choose debian + add chef user + add a big disk to mount as /data'))


@task
def install_base():
    """
    Install base system pacakges, add swap, and create application user.
    """
    # 1. PKGS
    puts('Installing base system packages (this might take a few minutes).')
    with hide('running', 'stdout', 'stderr'):
        sudo('apt-get update -qq')
        # sudo('apt-get upgrade -y')  # no need + slows down process for nothing
        sudo('apt-get install -y build-essential gettext')
        sudo('apt-get install -y screen wget curl vim git sqlite3')
        sudo('apt-get install -y python3 python3-pip python3-dev python3-virtualenv virtualenv python3-tk')
        sudo('apt-get install -y linux-tools libfreetype6-dev libxft-dev libwebp-dev libjpeg-dev libmagickwand-dev')
        sudo('apt-get install -y ffmpeg psmisc pkg-config phantomjs')
        sudo('apt-get install -y netcat-openbsd')  # for cronjobs to sending commands to chefs via control socket
        # TODO: Add chef user

    # 2. ADD SWAP
    if not exists('/var/swap.1'):
        puts('Adding 8G of swap file /var/swap.1')
        sudo('/bin/dd if=/dev/zero of=/var/swap.1 bs=1M count=8192')
        sudo('/sbin/mkswap /var/swap.1')
        sudo('chmod 600 /var/swap.1')
        sudo('/sbin/swapon /var/swap.1')
        sudo('echo "/var/swap.1  none  swap  sw  0  0" >> /etc/fstab')

    # 3. ADD /data dir
    if not exists('/data'):
        puts(blue('MANUAL STEPS REQUIRED:'))
        dev = '/dev/sdb1'
        mountpoint = '/data'
        puts(blue('RUN mkdir -p {0}'.format(mountpoint)))
        puts(blue('USE fdisk /dev/sdb to create a partition /dev/sdb1'))
        puts(blue('RUN mkfs.ext4 {dev}'.format(dev=dev)))
        puts(blue('RUN mount {dev} {mnt}'.format(dev=dev, mnt=mountpoint)))
        puts(blue('RUN chown -R {user}:{user} {mnt}'.format(user='chef', mnt=mountpoint)))
        puts(blue('RUN echo "{dev}  /data  ext4  defaults   0   1" >> /etc/fstab'.format(dev=dev)))
        puts(blue('MOVE chef user home to /data'))

    # 4. Create working dirs, like /datavar/run/ = has deamonized chefs pid files
    if not exists(CHEFS_PID_DIR):
        sudo('mkdir -p ' + CHEFS_PID_DIR, user=CHEF_USER)
    # /data/var/log/ = daemonized chef's combined strout and stderr logs,
    if not exists(CHEFS_LOGS_DIR):
        sudo('mkdir -p ' + CHEFS_LOGS_DIR, user=CHEF_USER)
    # and /data/var/cmdsocks/ = command sockets used by cronjobs to `run` chefs
    if not exists(CHEFS_CMDSOCKS_DIR):
        sudo('mkdir -p ' + CHEFS_CMDSOCKS_DIR, user=CHEF_USER)

    puts(green('Base install steps finished.'))

