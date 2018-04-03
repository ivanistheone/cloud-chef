import json
import os
import time

from fabric.api import env, task, local, sudo, run
from fabric.api import get, put, require
from fabric.colors import red, green, blue, yellow
from fabric.context_managers import cd, prefix, show, hide, shell_env
from fabric.contrib.files import exists, sed, upload_template
from fabric.utils import puts



# FAB SETTTINGS
################################################################################
env.user = 'chef'
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
                        CHEFDIRNAME_KEY)
from inventory import load_inventory
INVENTORY = load_inventory()


# GLOBAL CHEF SETTINGS
################################################################################
CHEF_USER = 'chef'
STUDIO_TOKEN = os.environ.get('STUDIO_TOKEN')
DEFAULT_GIT_BRANCH = 'master'
CHEFS_DATA_DIR = '/data'



# CHEF RUN
################################################################################

@task
def run_chef(nickname):
    if STUDIO_TOKEN is None:
        raise ValueError('Must specify STUDIO_TOKEN env var on command line')

    chef_info = INVENTORY[nickname]
    CHEF_DATA_DIR = os.path.join(CHEFS_DATA_DIR, chef_info[CHEFDIRNAME_KEY])
    chef_cwd = chef_info[WORKING_DIRECTORY_KEY]

    if chef_cwd:
        chef_run_dir = os.path.join(CHEF_DATA_DIR, chef_cwd)
    else:
        chef_run_dir = CHEF_DATA_DIR

    with cd(chef_run_dir):
        with prefix('source ' + os.path.join(CHEF_DATA_DIR, 'venv/bin/activate')):
            cmd = chef_info[COMMAND_KEY].format(studio_token=STUDIO_TOKEN)
            sudo(cmd, user=CHEF_USER)


# CHEF SETUP
################################################################################

@task
def print_info():
    with cd(CHEFS_DATA_DIR):
        sudo("ls")
        sudo("whoami")
        run("ls")
        run("whoami")


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

@task
def schedule_chef(nickname):
    pass

@task
def unschedule_chef(nickname):
    pass



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
        sudo('apt-get install -y netcat-openbsd')  # for 

    # 2. ADD SWAP
    if not exists('/var/swap.1'):
        puts('Adding 8G of swap file /var/swap.1')
        sudo('/bin/dd if=/dev/zero of=/var/swap.1 bs=1M count=8192')
        sudo('/sbin/mkswap /var/swap.1')
        sudo('chmod 600 /var/swap.1')
        sudo('/sbin/swapon /var/swap.1')
        sudo('echo "/var/swap.1  none  swap  sw  0  0" >> /etc/fstab')

    # # 3. ADD /data dir
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

    puts(green('Base install steps finished.'))
