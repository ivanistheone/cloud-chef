import datetime
from github import Github
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

from libstudio import StudioApi
try:
    from notion.client import NotionClient
except ImportError as e:
    puts(red('Could not import NotionClient. Notion integrations will not work!'))


# FAB SETTTINGS
################################################################################
env.user = os.environ.get('USER')
env.password = os.environ.get('SUDO_PASSWORD')
env.notion_token = os.environ.get('NOTION_TOKEN')

# Studio
STUDIO_TOKEN = os.environ.get('STUDIO_TOKEN')
env.studio_user = os.environ.get('STUDIO_USER')
env.studio_pass = os.environ.get('STUDIO_PASS')
env.studio_url = os.environ.get('STUDIO_URL', 'https://studio.learningequality.org')

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
                        CHANNEL_NAME_KEY,
                        CHANNEL_ID_KEY,
                        GITHUB_REPO_URL_KEY,
                        POST_SETUP_COMMAND_KEY,
                        WORKING_DIRECTORY_KEY,
                        COMMAND_KEY,
                        CRONTAB_KEY,
                        COMMENTS_KEY,
                        CHEFDIRNAME_KEY)
from inventory import load_inventory
INVENTORY = load_inventory()


# GLOBAL CHEF SETTINGS
################################################################################
CHEF_USER = 'chef'
DEFAULT_GIT_BRANCH = 'master'
CHEFS_DATA_DIR = '/data'
CHEFS_LOGS_DIR = '/data/var/log'
CHEFS_PID_DIR = '/data/var/run'
CHEFS_CMDSOCKS_DIR = '/data/var/cmdsocks'



# CHEF RUN
################################################################################

@task
def run_chef(nickname, nohup=None, stage=False):
    if STUDIO_TOKEN is None:
        raise ValueError('Must specify STUDIO_TOKEN env var on command line')
    nohup = (nohup == 'True' or nohup == 'true')  # defaults to False
    stage = (stage == 'True' or stage == 'true')  # defaults to False

    chef_info = INVENTORY[nickname]
    CHEF_DATA_DIR = os.path.join(CHEFS_DATA_DIR, chef_info[CHEFDIRNAME_KEY])
    chef_cwd = chef_info[WORKING_DIRECTORY_KEY]
    cmd = chef_info[COMMAND_KEY].format(studio_token=STUDIO_TOKEN)
    if stage:
        cmd = add_args(cmd, {'--stage':None})

    if chef_cwd:
        chef_run_dir = os.path.join(CHEF_DATA_DIR, chef_cwd)
    else:
        chef_run_dir = CHEF_DATA_DIR

    with cd(chef_run_dir):
        with prefix('source ' + os.path.join(CHEF_DATA_DIR, 'venv/bin/activate')):
            if nohup == False:
                # Normal operation (blocking)
                sudo(cmd, user=CHEF_USER)
            else:
                # Run in background
                cmd_nohup = wrap_in_nohup(cmd)
                sudo(cmd_nohup, user=CHEF_USER)
                nohup_out_file = os.path.join(chef_run_dir, 'nohup.out')
                puts(green('Chef started in backround. Use `tail -f ' + nohup_out_file + '` to see logs.'))



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
                if chef_info[POST_SETUP_COMMAND_KEY] is not None:
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





# DAEMON CHEFS (triggerred by sushibar remote commands or local cronjobs)
################################################################################

@task
def start_chef_daemon(nickname):
    if STUDIO_TOKEN is None:
        raise ValueError('Must specify STUDIO_TOKEN env var on command line')
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
            orig_cmd = chef_info[COMMAND_KEY].format(studio_token=STUDIO_TOKEN)
            new_cmd = add_args(orig_cmd, {'--daemon':None, '--cmdsock':cmdsock_file})
            redirects = ' >>{log_file} 2>&1 '.format(log_file=log_file)
            cmd_nohup = wrap_in_nohup(new_cmd, redirects=redirects, pid_file=pid_file)
            puts(green('Starting ' + nickname + ' chef daemon...'))
            sudo(cmd_nohup, user=CHEF_USER)
            time.sleep(0.3)
            running = _check_process_running(pid_file)
            if running:
                pid_str = _read_pid_file_contents(pid_file)
                puts(green('Chef daemon started with PID=' + pid_str))
            else:
                puts(red('Chef daemon failed to start. Check /data/var/log/'))


@task
def stop_chef_daemon(nickname):
    """
    Read the PID file for the `nickname` chef and kill the chef process.
    The process id we read from the `pid_file` for this chef could be either of:
      A. the PID of the bash shell that started the chef daemons, or
      B. the python chef process itself, so we need to handle both cases.
    """
    chef_info = INVENTORY[nickname]
    pid_file = os.path.join(CHEFS_PID_DIR, nickname + 'd.pid')
    cmdsock_file = os.path.join(CHEFS_CMDSOCKS_DIR, nickname + 'd.sock')

    if exists(pid_file):
        running = _check_process_running(pid_file)
        if running:
            pid_str = _read_pid_file_contents(pid_file)

            # CASE A: kill child processes for the parent bash shell
            sudo('pkill --parent ' + pid_str + ' || true')
            # shell will exit by itself, since child process has exited...

            # CASE B: kill the python chef process itself
            running = _check_process_running(pid_file)
            if running:
                sudo('kill -SIGTERM ' + pid_str)

            # Make sure not running anymore, and cleanup
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




# CHEF CRONJOB SCHEDULING 
################################################################################

@task
def list_scheduled_chefs(print_cronjobs=True):
    with hide('running', 'stdout'):
        result = sudo('crontab -l', user=CHEF_USER)
    cronjobs = result.splitlines()
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
              """/bin/nc -U -q 1  /data/var/cmdsocks/{n}d.sock""".format(n=nickname)
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
EXCLUDE_PYPSAUX_PATTERNS = ['system-config', 'cinnamon-killer', 'apport-gtk', 'buildkite']

@task
def print_info():
    with cd(CHEFS_DATA_DIR):
        run("ls")
        run("whoami")
        sudo("ls")
        sudo("whoami")

@task
def pstree():
    result = sudo('pstree -p')
    print(result.stdout)

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
            if not any([pat in process['COMMAND'] for pat in EXCLUDE_PYPSAUX_PATTERNS]):
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




# GITHUB REPO
################################################################################
GITHUB_API_TOKEN_FILE = 'credentials/github_api.json'
GITHUB_API_TOKEN_NAME = 'cloud-chef-token'
GITHUB_SUSHI_CHEFS_TEAM_ID = 2590528  # "Sushi Chefs" team = all sushi chef devs

def get_github_client(token=None):
    """
    Returns a token-authenticated github client (to avoid code duplication).
    """
    if token is None:
        with open(GITHUB_API_TOKEN_FILE, 'r') as tokenf:
            token = json.load(tokenf)[GITHUB_API_TOKEN_NAME]
    return Github(token)


@task
def create_github_repo(nickname, source_url=None, init=True, private=False):
    """
    Create a github repo for chef given its `nickname` and `source_url`.
    """
    init = False if init=='False' or init=='false' else True
    private = True if private=='True' or private=='true' else False
    description = 'Sushi Chef script for importing {} content'.format(nickname)
    if source_url:
        description += ' from ' + str(source_url)
    repo_name = 'sushi-chef-' + nickname

    github = get_github_client()
    le_org = github.get_organization('learningequality')

    # 1. create repo
    create_repo_kwargs = dict(
        description=description,
        private=private,
        has_issues=True,
        has_wiki=False,
        auto_init=init
    )
    if init:
        create_repo_kwargs['license_template'] = 'mit'
        create_repo_kwargs['gitignore_template'] = 'Python'
    repo = le_org.create_repo(repo_name, **create_repo_kwargs)

    # 3. Give "Sushi Chefs" team read/write persmissions
    team = le_org.get_team(GITHUB_SUSHI_CHEFS_TEAM_ID)
    team.add_to_repos(repo)
    team.set_repo_permission(repo, 'push')
    puts(green('Chef repo succesfully created: {}'.format(repo.html_url)))



@task
def list_chef_repos():
    """
    Prints a list of all github repos that match the `sushi-chef-*` pattern.
    """
    CHEF_REPO_PATTERN = re.compile('.*sushi-chef-.*')
    github = get_github_client() 
    le_org = github.get_organization('learningequality')
    repos = le_org.get_repos()
    chef_repos = []
    for repo in repos:
        if CHEF_REPO_PATTERN.search(repo.name):
            chef_repos.append(repo)
    for repo in chef_repos:
        pulls = list(repo.get_pulls())
        issues = list(repo.get_issues())
        print(repo.name,
              '\t', repo.html_url,
              '\t', len(pulls), 'PRs',
              '\t', len(issues), 'Issues')

@task
def list_chef_issues(reponame):
    if reponame is None:
        return
    github = get_github_client() 
    repo = github.get_repo("learningequality/{}".format(reponame))
    open_issues = repo.get_issues(state='open')
    for issue in open_issues:
        print(issue.number, issue.state, issue.title, issue.comments, 'comments', issue.labels)



# HELPER METHODS
################################################################################

def wrap_in_nohup(cmd, redirects=None, pid_file=None):
    """
    This wraps the chef command `cmd` appropriately for it to run in background
    using the nohup to avoid being terminated when the HANGUP signal is received
    when shell exists. This function is necessary to support some edge cases:
      - composite commands, e.g. ``source ./c/keys.env && ./chef.py``
      - adds an extra sleep 1 call so commands doesn't exit too fast and confuse fabric
    Args:
      redirects (str):  options for redirecting command's stdout and stderr
      pid_file (str): path to pid file where to save pid of backgrdoun process (needed for stop command)
    """
    # prefixes
    cmd_prefix = ' ('            # wrapping needed for sleep suffix
    cmd_prefix += ' nohup '      # call cmd using nohup
    cmd_prefix += ' bash -c " '  # spawn subshell in case cmd has multiple parts
    # suffixes
    cmd_suffix = ' " '           # /subshell
    if redirects is not None:    # optional stdout/stderr redirects (e.g. send output to a log file)
        cmd_suffix += redirects
    cmd_suffix += ' & '          # put nohup command in background
    if pid_file is not None:     # optionally save nohup pid in  `pid_file`
         cmd_suffix += ' echo $! >{pid_file} '.format(pid_file=pid_file)
    cmd_suffix += ') && sleep 1' # via https://stackoverflow.com/a/43152236
    # wrap it yo!
    return cmd_prefix + cmd + cmd_suffix

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
    if pid_str is None or len(pid_str)==0:
        return False
    processes  = psaux()
    found = False
    for process in processes:
        if process['PID'] == pid_str:
            found = True
    return found

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





# NOTION INTEGRATION
################################################################################

@task
def update_notion_channels_info():
    """
    Update the "Studio Channels" notion board cards with latest info from Studio.
    """
    # Studio API client
    if os.path.exists('cache.sqlite3'):
        os.remove('cache.sqlite3')
    studio_api = StudioApi(studio_url=env.studio_url, token=STUDIO_TOKEN,
                           username=env.studio_user, password=env.studio_pass)

    # Notion API
    client = NotionClient(token_v2=env.notion_token, monitor=False)
    studio_channels_url = 'https://www.notion.so/learningequality/761249f8782c48289780d6693431d900?v=44827975ce5f4b23b5157381fac302c4'
    page = client.get_block(studio_channels_url)
    notion_channels = page.collection.get_rows()

    # Update Notion channels using info from Studio API
    for notion_channel in notion_channels:
        channel_id = notion_channel.get_property('channel_id')
        channel_name = notion_channel.get_property('name')
        if channel_id:
            puts(green('Updating notion card for channel ' + channel_name + ' channel_id=' + channel_id))
            # get info from Studio API
            channel_info_dict = studio_api.get_channel(channel_id)
            notion_channel.is_public = channel_info_dict['public']
            notion_channel.description = channel_info_dict['description']
            notion_channel.version = channel_info_dict['version']
            notion_channel.name = channel_info_dict['name']
        else:
            puts(yellow('Skipping channel named ' + channel_name))

