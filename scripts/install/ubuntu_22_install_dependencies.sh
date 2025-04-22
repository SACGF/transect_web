#!/bin/bash

set -e # Fail on error
echo "Installing packages via apt-get"

# -y means automatically answer "YES" to prompts
apt-get update
apt-get install python3-pip
apt-get install -y nginx
apt-get install -y rabbitmq-server # celery message broker
apt-get install -y postgresql postgresql-contrib
apt-get install -y r-base # lots of libraries we need to install here as well
apt-get install -y libcurl4-openssl-dev # Needed to install Glimma
apt-get install -y libssl-dev # Needed to install Glimma
apt-get install -y libxml2-dev # Needed to install Glimma
apt-get install -y libfontconfig1-dev # Needed to install ggforce
apt-get install -y pandoc

# install Rstudio packages

Rscript /opt/sRT/scripts/install/install_R_packages.R

echo "Install python libraries"
python3 -m pip install --upgrade pip
sudo python3 -m pip install -r /opt/sRT/requirements.txt # use sudo to install it in the system path, otherwise it will install it into your local directory