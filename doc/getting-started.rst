.. _getting-started:


.. |br| raw:: html

   <br />

***************
Getting Started
***************

This section covers the steps required to setup Copernicus.
After going through the instructions below you will have a running copernicus
server with a connected worker.

-------------
Prerequisites
-------------
Before we start installing there are some basic prerequisites that
has to be met. Apart from these listed below the server and the worker have some
additional prerequisites which we will cover in the setup sections for
the server and the worker.

^^^^^^
Python
^^^^^^
Copernicus requires python 2.7 to be installed.
The installation must also include openssl.
On \*nix systems python is usually preinstalled with openssl.
running the command ``python --version`` will show you what version is installed.

^^^^^^^^^^^^^
Network Ports
^^^^^^^^^^^^^
The default network ports that Copernicus communicates via is 14807 for HTTP and
13807 for HTTPS. Please ensure that these ports are open in the network.
These must be open for both inward and outward communication on any machine that
is running the client, worker or server. If these ports cannot be used it is
possible to specify other ports when setting up the server.

^^^
Git
^^^

Git is a tool to download software from a source code repository.
To see if it is installed try to run the command ``git`` from a terminal.
If an installation is needed please download it from http://git-scm.com/download

----------------------
Downloading Copernicus
----------------------

Copernicus can be downloaded from our public git repository. To download the source
, use the following command ``https://github.com/gromacs/copernicus.git``

Set the *CPC_HOME* environment variable to the location where copernicus is installed

* On UNIX/Linux systems this is usually done with ``export CPC_HOME=path/to/cpc``

* Now add *CPC_HOME* to your *PATH* variable. On UNIX/Linux systems this is
  usually done with ``export PATH=$PATH:$CPC_HOME``

You should preferably but this in the startup file of your shell. Otherwise you will
have to do this everytime you open up a terminal.

You should now be able to run the following three commands

* ```cpcc -h```
* ```cpc-server -h```
* ```cpc-worker -h```


------------
Server Setup
------------

^^^^^^^^^^^^^^^^^^^^^^^^
Additional prerequisites
^^^^^^^^^^^^^^^^^^^^^^^^

The server has some additional prerequisites.
if you are planning to run the prepackaged workflows GROMACS must be installed
and accessible for the server. The easiest way is if GROMACS is accessible from the path.
For other ways to specify this please refer to the section :ref:`server`.

Optionally, if you will use the MSM workflow
you will need to make sure that scipy, numpy and py-tables are installed.
You will also need to fetch the MSMbuilder source from https://simtk.org/home/msmbuilder.

^^^^^^^^^^^^
Installation
^^^^^^^^^^^^

To install the server run the command

 ``cpc-server setup <PROJECT_DIR>``

where ``PROJECT_DIR`` is the directory where the server will store project data
for all the projects that it will run. Make sure to specify the ``PROJECT_DIR``
in a writable location. Note that ``PROJECT_DIR`` is only specified during setup,
however the creation of the directory occurs when we first create a project.
During the setup, the server will ask for a password to the cpc-admin user (super user).
You will also notice that a directory named .copernicus is created in your home directory. This is where Copernicus will store its settings.


To ensure that the server is properly installed, call the command

``cpc-server start``

The server is will now run as a background process.
For the worker to be able to communicate with
the server a connection bundle must be created: this is a file with a description
of how to connect to a server together with a key pair.
During the server setup a bundle is alredy created and put under the .copernicus folder.
When we later on start a worker it will look for a connection bundle in the .copernicus folder,
unless a bundle is specified

If you need to create additional bundles you can create them with the command

``cpc-server bundle``

Which generates the bundle, with the name client.cnx.
This file can then be used on any machine to communicate with the server.


^^^^^^^^^^^^^^^^^^^^^^^^^^
Optmizing the server
^^^^^^^^^^^^^^^^^^^^^^^^^^
For larger workflows with thousands of jobs the load on the server can be rather heavy.
To optimize the code execution it is more efficient to not run those parts as ordinary
Python code
If you have Cython installed you can run the bash script ``compileLibraries.sh``
that is located in the  Copernicus installation folder:
This will generate C code from Python files that will then be compiled to shared libraries. The other Python files will automatically use these shared libraries instead of the corresponding Python code, which improves the server efficiency. Remember that if you modify any Python file in Copernicus it is best to rerun the script to regenerate the shared libraries if any of the relevant files have changed. There is no further optimization used when generating the C code from the Python code.


------------
Client Setup
------------
The client is a command line tool use to send commands to the server.
it can be run directly from your laptop. But before sending commands to a server
it needs to know its address
This is done with the``add-server`` command:

``cpcc add-server my.serverhostname.com``

``cpcc add-server my.serverhostname.com 14807``

^^^^^^^^^^
Logging in
^^^^^^^^^^
To start sending commands to the server you need to first login.
``cpcc login cpc-admin``

Then type the password you set for the user cpc-admin during setup.
After logging in you and will be able to send commands to the server.

To verify that you are logged in try the command ``cpcc server-info``.
This should display the server name and version.


------------
Worker Setup
------------

^^^^^^^^^^^^^
Prerequisites
^^^^^^^^^^^^^

The worker has 2 prerequisites

* A client.cnx file, If you are running the worker on a different machine than the server you probably do not have a .copernicus folder in you home directory. However you can create one manually and drop in the client.cnx file there. If you wish you can also specify the file manually as we will later below.

* GROMACS must be installed and accessible for the worker. The easiest way is if GROMACS is accessible from the path. For other ways to specify this please refer to the section :ref:`worker`.


^^^^^^^^^^^^
Installation
^^^^^^^^^^^^
Workers do not need any specific project directory. Provided that the prerequisites
are met no installation procedure is needed.
To verify that the worker can connect to a server start it with

``cpc-worker smp``

By default the worker looks in .copernicus for the connection bundle. however you can also specify
the location onf the connection bundle.

``cpc-worker -c client.cnx smp``

When started the worker will output its Worker Id, available executables and then start
requesting work from the server.
An example output is shown below

.. code-block:: none

   INFO, cpc.worker: Worker ID: 130-229-12-163-dhcp.wlan.ki.se-26108.
   Available executables for platform smp:
   gromacs/mdrun 4.5.3
   INFO, cpc.worker: Got 0 commands.
   INFO, cpc.worker: Have free resources. Waiting 30 seconds


you will notice the parameter ``smp`` in the above command. This means that we
start the worker with the platform type smp. We will cover this in greater detail
in the section :ref:`platformtypes`.

Shut down the worker simply hit ``CTRL-C``

In case you try to connect with the wrong connection bundle the following
error message will be displayed.

.. code-block:: none

   ERROR: [Errno 1] _ssl.c:503:error:14090086:
   SSL routines:SSL3_GET_SERVER_CERTIFICATE:certificate verify failed


--------
Summary
--------

After going throught the the installation process you should have one running
server with one worker connected to it.

you can check the status of the server with ``cpc-server status``
which will show you that the server is up and running and has one worker connected
to it.


