#!/bin/bash

sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.6 python3.6-venv python3.6-dev
sudo apt-get install -y xvfb herbstluftwm libzbar0
