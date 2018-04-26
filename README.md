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
  - Github Repo: an URL of the form `https://github.com/{org}/{chefname}`, the
    code for this chef script will be cloned to `/data/{chefname}` during setup.
  - Command needed to run the chef, including all arguments and options:
     - use `--token={studio_token}` as part of the command, which will later be
       replaced with environment variable `STUDIO_TOKEN`.


### 2. Setup chef script

    fab -R cloud-kitchen  setup_chef:<nickname>

The above command will clone chef code, create a virtual environment, and install
the python packages in the `requirements.txt` for the project.

Run `update_chef` task to update chef code to latest version (`fetch` and `checkout --hard`).

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





Creating a github repo for a new chef
-------------------------------------
The code for each chef script lives in its own github repo under the `learnignequality` org.
Run the following command to create an empty github repo for a new chef:

    fab create_github_repo:chef-nickname,source_url="https://url_of_sourcewebsite.org"

This will create the github repository https://github.com/learningequality/sushi-chef-chef-nickname
and enable read/write access to this repo for the "Sushi Chefs" team.
The `source_url` argument is optional, but it's nice to have.
This command requires a github API key to be present in the `credentials/` dir.

