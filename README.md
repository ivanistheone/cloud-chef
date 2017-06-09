Ansible Cloud Chef
==================
Basic ansible scripts to create a temporary ec2 instance running Debian GNU/Linux.
The latest version of `ricecooker` will be installed on the server so it's ready
to chef anything that needs chefing.


Install
-------
To install 

    virtualenv venv
    source venv/bin/activate
    pip install -r requirements.txt


Credentials
-----------
To use AWS APIs you'll need to obtain an AWS KEY + SECRET from the AWS console.
Choose a user that has `ec2` privileges and generate and access key for them
from the `IAM` console. Place the info in the file `credentials/aws.env` using
the same format as `credentials/aws.env.template`.

Run the command:

    source credentials/aws.env

to make these credentials available in your current shell.



Gimme chef server!
------------------
To create the VPC and a chefserver, run the command: 

    ansible-playbook -i inventory create.yml

You can look for the public ip of the newly created instance in `./inventory`.


I don't want it anymore
-----------------------
To delete the chefserver and the VPC, run the command: 

    ansible-playbook -i inventory destroy.yml



Customizing this repo
---------------------
Some things you might want to adjust is `aws/vars/vpc.yml`:
  - `vpc_name`: use a descriptive name specific to your project (default `chefsvpc`)
  - `vpc_region`: the AWS region where the server will be located (default `us-west-1`)


You might also want to change the settings for the virtual machine you'll be using,
which are specified in the file `aws/vars/ec2.yml`:
  - `image_id`: has the format `ami-xxxyyyzz` (default `ami-94bdeef4` latest Debian for the `us-west-1` region).
     Another popular choice is to use [Ubuntu AMIs](https://cloud-images.ubuntu.com/locator/ec2/).
  - `instance_type`: this setting determines the "size" of the virtual machine.
    The [AWS free tier](https://aws.amazon.com/free/) includes only `t2.micro`,
    but if you need more power, you can use one of the [other instance types](https://aws.amazon.com/ec2/instance-types/).


