Chefs' volume
=============
In order to preserve cached download data and compressed files,
we use a persistent EBS volume that gets attached to the instance.


Provision
---------
See screenshots.


Initial setup
--------------
Provision a 500G and attach it to a running instance, then run the commands:

    mkfs.ext4 /dev/xvdf -L CHEFS_VOLUME
    e2label /dev/xvdf CHEFS_VOLUME
    mount -L CHEFS_VOLUME /chefsvolume

The ansible scripts will automatically mount this volume every time a new instance is created.


Configs
-------
See [aws/vars/chefsvolume.yml](../../aws/vars/chefsvolume.yml).


Long term storage
-----------------
The volume doesn't need to be provisioned all the time.
To save money create a snapshot and delete the volum.
Then when you need it again, restore from snapshot.




