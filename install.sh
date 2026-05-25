#!/bin/sh

echo 'linking to .local/bin ... '

ln -f -s $(realpath src/waydrawer.py) ~/.local/bin/waydrawer

echo 'done.'
