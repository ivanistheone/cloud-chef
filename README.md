Cloud Chef Fabric Tasks
=======================
Fabric scripts to create a temporary cheffing server running Debian GNU/Linux.
System prerequisites for `ricecooker` are installed, and the /data directory is
provisioned with lots of disk space.



Install
-------

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements.txt



Information
------------

    fab -R cloud-kitchen pypsaux    # shows all python processes on server cloud-kitchen
    fab -R cloud-kitchen psaux_str  # shows all processes on server cloud-kitchen



Basic usage
-----------

### 1. Edit the inventory file
https://docs.google.com/spreadsheets/d/1vx07agIPaboRHthtGGjJqiLQbXzzM1Mr5gUxxnrexq0/edit#gid=0

Must specify:
  - Nickname: short blurb-like string that identified a channel
  - Github Repo: 
  - Command needed to run the chef, including all arguments and options:
     - use `--token={studio_token}` as part of the command, which will later be
       replaced with environment variable `STUDIO_TOKEN`.


### 2. Setup chef script

    fab -R cloud-kitchen  setup_chef:<nickname>

The above command will clone chef code, create a virtual environment, and install
the requirements.txt.

Run `update_chef` task to update chef code to latest vestison (`fetch` and `checkout --hard`).

To remove chef code completely and start from scratch, use `unsetup_chef`.


### 3. Run it

    export STUDIO_TOKEN=<YOURSTUDIOTOKENGOESGHERE>
    fab -R cloud-kitchen  run_chef:<nickname>

You can also run chef in background

    fab -R cloud-kitchen run_chef:<nickname>,nohup=true



Daemon mode
-----------
Start chef with `--daemon` and `--cmdsock` options:

    export STUDIO_TOKEN=<YOURSTUDIOTOKENGOESGHERE>
    fab -R cloud-kitchen start_chef_daemon:<nickname>

To stop the chef daemon, run:

    fab -R cloud-kitchen stop_chef_daemon:<nickname>



Scheduled chef runs cronjob
---------------------------
Follow daemon mode setup to start a daemon chef, then call

    fab -R cloud-kitchen  list_scheduled_chefs
    fab -R cloud-kitchen  schedule_chef:<nickname>

To unschedule a chef use the `unschedule_chef` task.


