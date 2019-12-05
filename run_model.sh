#!/bin/bash
mkdir Data
mkdir Results
aws s3 cp --no-sign-request --endpoint-url=https://s3.cern.ch s3://gan-bucket/ Data/. --recursive --exclude "EleEscan_EleEscan*"
cd keras
python3 --datapath $PWD/Data --name='tpu_training' --nbepochs 120 AngleTrain3dGAN_tf.py
