#!/bin/env bash

sudo apt update
sudo apt install python3-venv

pip install virtualenv
python -m venv ~/.local/python/venv/webscrapy
source  ~/.local/python/venv/webscrapy/bin/activate

pip install poetry
poetry export -f requirements.txt > requirements.txt
pip install -r requirements.txt
poetry install -vvv

