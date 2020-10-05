#Training for GAN

from __future__ import print_function
import os

#--------------------------------------
# For Google Cloud Bucket
#--------------------------------------

import logging
import cloudstorage as gcs
import webapp2

from google.appengine.api import app_identity
#--------------------------------------

#os.environ["CUDA_VISIBLE_DEVICES"]="1"

## setting seed ###
#from numpy.random import seed
#seed(1)
#from tensorflow import set_random_seed
#set_random_seed(1)
#import random
#random.seed(1)
#os.environ['PYTHONHASHSEED'] = '0' 
##################

GLOBAL_BATCH_SIZE = 64

from collections import defaultdict
try:
    import cPickle as pickle
except ImportError:
    import pickle
#import keras
import argparse
import sys
import h5py 
import numpy as np
import time
import math
import tensorflow as tf
#os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2' 
import analysis.utils.GANutils as gan
import TfRecordConverter as tfconvert


# if '.cern.ch' in os.environ.get('HOSTNAME'): # Here a check for host can be used to set defaults accordingly
#     tlab = True
# else:
#     tlab= False
    
# try:
#     import setGPU #if Caltech
# except:
#     pass

#from memory_profiler import profile # used for memory profiling
import tensorflow.keras.backend as K
from tensorflow.keras.layers import Input
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adadelta, Adam, RMSprop
from tensorflow.keras.utils import Progbar

#Configs
config = tf.compat.v1.ConfigProto(log_device_placement=True)
#config.gpu_options.allow_growth = True
#main_session = tf.compat.v1.InteractiveSession(config=config)


#tf.config.experimental_run_functions_eagerly(True)


def main():
    #Architectures to import
    from ParallelAngleArch3dGAN import generator, discriminator #if there is any parallel changes to the architecture this needs to change
    
    #Values to be set by user
    parser = get_parser()
    params = parser.parse_args()
    nb_epochs = params.nbepochs #Total Epochs
    batch_size = params.batchsize #batch size
    latent_size = params.latentsize #latent vector size
    verbose = params.verbose
    datapath = params.datapath# Data path
    outpath = params.outpath # training output
    nEvents = params.nEvents# maximum number of events used in training
    ascale = params.ascale # angle scale
    yscale = params.yscale # scaling energy
    weightdir = 'weights/3dgan_weights_' + params.name
    pklfile = 'results/3dgan_history_' + params.name + '.pkl'# loss history
    resultfile = 'results/3dgan_analysis' + params.name + '.pkl'# optimization metric history
    prev_gweights = 'weights/' + params.prev_gweights
    prev_dweights = 'weights/' + params.prev_dweights
    xscale = params.xscale
    xpower = params.xpower
    analyse=params.analyse # if analysing
    loss_weights=[params.gen_weight, params.aux_weight, params.ang_weight, params.ecal_weight, params.hist_weight]
    dformat=params.dformat
    thresh = params.thresh # threshold for data
    angtype = params.angtype
    particle = params.particle
    warm = params.warm
    lr = params.lr
    events_per_file = 5000
    energies = [0, 110, 150, 190]

    # if tlab:
    #    if not warm:
    #      datapath = 'path4'
    #    outpath = '/gkhattak/'
         
    # if datapath=='path1':
    #    datapath = "/data/shared/gkhattak/*Measured3ThetaEscan/*.h5"  # Data path 100-200 GeV                                                         
    # elif datapath=='path2':
    #    datapath = "/bigdata/shared/LCDLargeWindow/LCDLargeWindow/varangle/*scan/*scan_RandomAngle_*.h5" # culture plate                              
    #    events_per_file = 10000
    #    energies = [0, 50, 100, 200, 250, 300, 400, 500]
    # elif datapath=='path3':
    #    datapath = "/data/shared/LCDLargeWindow/varangle/*scan/*scan_RandomAngle_*.h5" # caltech                                                      
    #    events_per_file = 10000
    #    energies = [0, 50, 100, 200, 250, 300, 400, 500]
    # elif datapath=='path4':
    #    datapath = "/eos/user/g/gkhattak/VarAngleData/*Measured3ThetaEscan/*.h5"  # Data path 100-200 GeV                                             
    # elif datapath=='path5':
    #    datapath = "/gkhattak/data/*RandomAngle100GeV/*.h5"
    #    energies = [0, 10, 50, 90]

    weightdir = outpath + 'weights/3dgan_weights_' + params.name
    pklfile = outpath + 'results/3dgan_history_' + params.name + '.pkl'# loss history
    resultfile = outpath + 'results/3dgan_analysis' + params.name + '.pkl'# optimization metric history   
    prev_gweights = outpath + 'weights/' + params.prev_gweights
    prev_dweights = outpath + 'weights/' + params.prev_dweights

    #setting up tpu strategy
    #tpu_address = 
    tpu_address = os.environ["TPU_NAME"]
    cluster_resolver = tf.distribute.cluster_resolver.TPUClusterResolver(tpu=tpu_address)
    tf.config.experimental_connect_to_cluster(cluster_resolver)
    tf.tpu.experimental.initialize_tpu_system(cluster_resolver)

    
    #setting up parallel strategy
    #strategy = tf.distribute.MirroredStrategy() #initialize parallel strategy
    #strategy = tf.distribute.MirroredStrategy(devices=["/gpu:0", "/gpu:1"]) #if there are more than one person using the cluster change to this
    strategy = tf.distribute.TPUStrategy(cluster_resolver)



    print ('Number of devices: {}'.format(strategy.num_replicas_in_sync))
    # global_batch_size = batch_size * strategy.num_replicas_in_sync

    BATCH_SIZE_PER_REPLICA = batch_size
    batch_size = batch_size * strategy.num_replicas_in_sync

    # Building discriminator and generator
    gan.safe_mkdir(weightdir)
    with strategy.scope():
        d=discriminator(xpower, dformat=dformat)
        g=generator(latent_size, dformat=dformat)


    # GAN training 
    Gan3DTrainAngle(strategy,d, g, datapath, nEvents, weightdir, pklfile, nb_epochs=nb_epochs, batch_size=batch_size, batch_size_per_replica=BATCH_SIZE_PER_REPLICA,
                    latent_size=latent_size, loss_weights=loss_weights, lr=lr, xscale = xscale, xpower=xpower, angscale=ascale,
                    yscale=yscale, thresh=thresh, angtype=angtype, analyse=analyse, resultfile=resultfile,
                    energies=energies, dformat=dformat, particle=particle, verbose=verbose, warm=warm,
                    prev_gweights= prev_gweights, prev_dweights=prev_dweights   )

def get_parser():
    parser = argparse.ArgumentParser(description='3D GAN Params' )
    parser.add_argument('--nbepochs', action='store', type=int, default=60, help='Number of epochs to train for.')
    parser.add_argument('--batchsize', action='store', type=int, default=64, help='batch size per update')
    parser.add_argument('--latentsize', action='store', type=int, default=256, help='size of random N(0, 1) latent space to sample')
    parser.add_argument('--datapath', action='store', type=str, default='path2', help='HDF5 files to train from.')
    parser.add_argument('--outpath', action='store', type=str, default='', help='Dir to save output from a training.')
    parser.add_argument('--dformat', action='store', type=str, default='channels_last')
    parser.add_argument('--nEvents', action='store', type=int, default=400000, help='Maximum Number of events used for Training')
    parser.add_argument('--verbose', action='store_true', help='Whether or not to use a progress bar')
    parser.add_argument('--xscale', action='store', type=int, default=1, help='Multiplication factor for ecal deposition')
    parser.add_argument('--xpower', action='store', type=float, default=0.85, help='pre processing of cell energies by raising to a power')
    parser.add_argument('--yscale', action='store', type=int, default=100, help='Division Factor for Primary Energy.')
    parser.add_argument('--ascale', action='store', type=int, default=1, help='Multiplication factor for angle input')
    parser.add_argument('--analyse', action='store', default=False, help='Whether or not to perform analysis')
    parser.add_argument('--gen_weight', action='store', type=float, default=3, help='loss weight for generation real/fake loss')
    parser.add_argument('--aux_weight', action='store', type=float, default=0.1, help='loss weight for auxilliary energy regression loss')
    parser.add_argument('--ang_weight', action='store', type=float, default=25, help='loss weight for angle loss')
    parser.add_argument('--ecal_weight', action='store', type=float, default=0.1, help='loss weight for ecal sum loss')
    parser.add_argument('--hist_weight', action='store', type=float, default=0.1, help='loss weight for additional bin count loss')
    parser.add_argument('--thresh', action='store', type=int, default=0., help='Threshold for cell energies')
    parser.add_argument('--angtype', action='store', type=str, default='mtheta', help='Angle to use for Training. It can be theta, mtheta or eta')
    parser.add_argument('--particle', action='store', type=str, default='Ele', help='Type of particle')
    parser.add_argument('--lr', action='store', type=float, default=0.001, help='Learning rate')
    parser.add_argument('--warm', action='store', default=False, help='Start from pretrained weights or random initialization')
    parser.add_argument('--prev_gweights', type=str, default='3dgan_weights_gan_training_epsilon_k2/params_generator_epoch_131.hdf5', help='Initial generator weights for warm start')
    parser.add_argument('--prev_dweights', type=str, default='3dgan_weights_gan_training_epsilon_k2/params_discriminator_epoch_131.hdf5', help='Initial discriminator weights for warm start')
    parser.add_argument('--name', action='store', type=str, default='gan_training', help='Unique identifier can be set for each training')
    return parser

# A histogram function that counts cells in different bins
def hist_count(x, p=1.0, daxis=(1, 2, 3)):
    limits=np.array([0.05, 0.03, 0.02, 0.0125, 0.008, 0.003]) # bin boundaries used
    limits= np.power(limits, p)
    bin1 = np.sum(np.where(x>(limits[0]) , 1, 0), axis=daxis)
    bin2 = np.sum(np.where((x<(limits[0])) & (x>(limits[1])), 1, 0), axis=daxis)
    bin3 = np.sum(np.where((x<(limits[1])) & (x>(limits[2])), 1, 0), axis=daxis)
    bin4 = np.sum(np.where((x<(limits[2])) & (x>(limits[3])), 1, 0), axis=daxis)
    bin5 = np.sum(np.where((x<(limits[3])) & (x>(limits[4])), 1, 0), axis=daxis)
    bin6 = np.sum(np.where((x<(limits[4])) & (x>(limits[5])), 1, 0), axis=daxis)
    bin7 = np.sum(np.where((x<(limits[5])) & (x>0.), 1, 0), axis=daxis)
    bin8 = np.sum(np.where(x==0, 1, 0), axis=daxis)
    bins = np.concatenate([bin1, bin2, bin3, bin4, bin5, bin6, bin7, bin8], axis=1)
    bins[np.where(bins==0)]=1 # so that an empty bin will be assigned a count of 1 to avoid unstability
    return bins

#get data for training
def GetDataAngle(datafile, xscale =1, xpower=1, yscale = 100, angscale=1, angtype='theta', thresh=1e-4, daxis=-1):
    #print ('Loading Data from .....', datafile)
    f=h5py.File(datafile,'r')
    X=np.array(f.get('ECAL'))* xscale
    Y=np.array(f.get('energy'))/yscale
    X[X < thresh] = 0
    X = X.astype(np.float32)
    Y = Y.astype(np.float32)
    ecal = np.sum(X, axis=(1, 2, 3))
    indexes = np.where(ecal > 10.0)
    X=X[indexes]
    Y=Y[indexes]
    if angtype in f:
      ang = np.array(f.get(angtype))[indexes]
    else:
      ang = gan.measPython(X)
    ang= ang.astype(np.float32)
    X = np.expand_dims(X, axis=daxis)
    ecal=ecal[indexes]
    ecal=np.expand_dims(ecal, axis=daxis)
    if xpower !=1.:
        X = np.power(X, xpower)
    final_dataset = {'X': X,'Y': Y, 'ang': ang, 'ecal': ecal}

    return final_dataset


def GetDataAngleParallel(dataset, xscale =1, xpower=1, yscale = 100, angscale=1, angtype='theta', thresh=1e-4, daxis=-1):
    X=np.array(dataset.get('ECAL'))* xscale
    Y=np.array(dataset.get('energy'))/yscale
    X[X < thresh] = 0
    X = X.astype(np.float32)
    Y = Y.astype(np.float32)
    ecal = np.sum(X, axis=(1, 2, 3))
    indexes = np.where(ecal > 10.0)
    X=X[indexes]
    Y=Y[indexes]
    if angtype in dataset:
      ang = np.array(dataset.get(angtype))[indexes]
    else:
      ang = gan.measPython(X)
    X = np.expand_dims(X, axis=daxis)
    ecal=ecal[indexes]
    ecal=np.expand_dims(ecal, axis=daxis)
    if xpower !=1.:
        X = np.power(X, xpower)

    final_dataset = {'X': X,'Y': Y, 'ang': ang, 'ecal': ecal}

    return final_dataset

#retrieved from google cloud tutorials
def list_bucket(bucket):
    """Create several files and paginate through them.

    Production apps should set page_size to a practical value.

    Args:
        bucket: bucket.
    """
    print('Listbucket result:\n')

    page_size = 1
    stats = gcs.listbucket(bucket + '/*tfrecords', max_keys=page_size)
    while True:
        count = 0
        for stat in stats:
            count += 1
            print(repr(stat))
            print('\n')

        if count != page_size or count == 0:
            break
        stats = gcs.listbucket(bucket + '/*tfrecords', max_keys=page_size,marker=stat.filename)

def Gan3DTrainAngle(strategy, discriminator, generator, datapath, nEvents, WeightsDir, pklfile, nb_epochs=30, batch_size=128, batch_size_per_replica=64 ,latent_size=200, loss_weights=[3, 0.1, 25, 0.1, 0.1], lr=0.001, rho=0.9, decay=0.0, g_weights='params_generator_epoch_', d_weights='params_discriminator_epoch_', xscale=1, xpower=1, angscale=1, angtype='theta', yscale=100, thresh=1e-4, analyse=False, resultfile="", energies=[], dformat='channels_last', particle='Ele', verbose=False, warm=False, prev_gweights='', prev_dweights=''):
    
    #define bucket name
    bucket_name = os.environ.get('BUCKET_NAME',app_identity.get_default_gcs_bucket_name())
    list_bucket(bucket_name)


    start_init = time.time()
    f = [0.9, 0.1] # train, test fractions 

    loss_ftn = hist_count # function used for additional loss
    
    # apply settings according to data format
    if dformat=='channels_last':
       daxis=4 # channel axis
       daxis2=(1, 2, 3) # axis for sum
    else:
       daxis=1 # channel axis
       daxis2=(2, 3, 4) # axis for sum

    with strategy.scope():
        # build the discriminator
        print('[INFO] Building discriminator')
        discriminator.compile(
            optimizer=RMSprop(lr),
            loss=['binary_crossentropy', 'mean_absolute_percentage_error', 'mae', 'mean_absolute_percentage_error', 'mean_absolute_percentage_error'],
            loss_weights=loss_weights
        )

        # build the generator
        print('[INFO] Building generator')
        generator.compile(
            optimizer=RMSprop(lr),
            loss='binary_crossentropy'
        )
 
    # build combined Model
    latent = Input(shape=(latent_size, ), name='combined_z')   
    fake_image = generator( latent)
    discriminator.trainable = False
    fake, aux, ang, ecal, add_loss = discriminator(fake_image) #remove add_loss
    with strategy.scope():
        combined = Model(
            inputs=[latent],
            outputs=[fake, aux, ang, ecal, add_loss], # remove add_loss
            name='combined_model'
        )
        combined.compile(
            optimizer=RMSprop(lr),
            loss=['binary_crossentropy', 'mean_absolute_percentage_error', 'mae', 'mean_absolute_percentage_error', 'mean_absolute_percentage_error'],
            loss_weights=loss_weights
        )


    #initialize with previous weights
    if warm:
        generator.load_weights(prev_gweights)
        print('Generator initialized from {}'.format(prev_gweights))
        discriminator.load_weights(prev_dweights)
        print('Discriminator initialized from {}'.format(prev_dweights))

    # Getting All available Data sorted in test train fraction
    Trainfiles, Testfiles = gan.DivideFiles(datapath, f, datasetnames=["ECAL"], Particles =[particle])
    discriminator.trainable = True # to allow updates to moving averages for BatchNormalization     
    print(Trainfiles)
    print(Testfiles)


    #------------------------------Probably not needed

    nb_Test = int(nEvents * f[1]) # The number of test events calculated from fraction of nEvents
    nb_Train = int(nEvents * f[0]) # The number of train events calculated from fraction of nEvents

    #The number of actual batches used will be min(available batches & nb_Train)
    nb_train_batches = int(nb_Train/batch_size)
    nb_test_batches = int(nb_Test/batch_size)
    print('The max train batches can be {} batches while max test batches can be {}'.format(nb_train_batches, nb_test_batches))  
    
    #------------------------------


    #create history and finish initiation
    train_history = defaultdict(list)
    test_history = defaultdict(list)
    init_time = time.time()- start_init
    analysis_history = defaultdict(list)
    print('Initialization time is {} seconds'.format(init_time))
    
    # Start training
    for epoch in range(nb_epochs):
        epoch_start = time.time()
        print('Epoch {} of {}'.format(epoch + 1, nb_epochs))


        #--------------------------------------------------------------------------------------------
        #------------------------------ Main Training Cycle -----------------------------------------
        #--------------------------------------------------------------------------------------------

        #Get the data for each training file

        nb_file=0
        epoch_gen_loss = []
        epoch_disc_loss = []
        index = 0
        file_index=0

        while nb_file < len(Trainfiles):
            #if index % 100 == 0:
            print('processed {} batches'.format(index + 1))
            print ('Loading Data from .....', Trainfiles[nb_file])
            
            # Get the dataset from the trainfile
            dataset = tfconvert.RetrieveTFRecord(Trainfiles[nb_file])

            # Get the train values from the dataset
            dataset = GetDataAngleParallel(dataset, xscale=xscale, xpower=xpower, angscale=angscale, angtype=angtype, thresh=thresh, daxis=daxis)
            nb_file+=1

            #create the dataset with tensors from the train values, and batch it using the global batch size
            dataset = tf.data.Dataset.from_tensor_slices(dataset).batch(batch_size)


            #Training
            for batch in dataset:

                #gets the size of the batch as it will be diferent for the last batch
                this_batch_size = tf.shape(batch.get('Y')).numpy()[0]

                #Discriminator Training
                real_batch_loss, fake_batch_loss = Discriminator_Train_steps(discriminator, generator, batch, nEvents, WeightsDir, pklfile, \
                    Trainfiles, nb_train_batches, daxis, daxis2, loss_ftn, combined, \
                    nb_epochs, this_batch_size, latent_size, loss_weights, lr, rho, decay, g_weights, d_weights, xscale, xpower, \
                    angscale, angtype, yscale, thresh, analyse, resultfile, energies, dformat, particle, verbose, \
                    warm, prev_gweights, prev_dweights)

                #if ecal sum has 100% loss(generating empty events) then end the training 
                if fake_batch_loss[3] == 100.0 and index >10:
                    print("Empty image with Ecal loss equal to 100.0 for {} batch".format(index))
                    generator.save_weights(WeightsDir + '/{0}eee.hdf5'.format(g_weights), overwrite=True)
                    discriminator.save_weights(WeightsDir + '/{0}eee.hdf5'.format(d_weights), overwrite=True)
                    print ('real_batch_loss', real_batch_loss)
                    print ('fake_batch_loss', fake_batch_loss)
                    sys.exit()
                # append mean of discriminator loss for real and fake events 
                epoch_disc_loss.append([
                    (a + b) / 2 for a, b in zip(real_batch_loss, fake_batch_loss)
                ])

                generator_loss = Generator_Train_steps(discriminator, generator, batch, nEvents, WeightsDir, pklfile, \
                    Trainfiles, nb_train_batches, daxis, daxis2, loss_ftn, combined, \
                    nb_epochs, this_batch_size, latent_size, loss_weights, lr, rho, decay, g_weights, d_weights, xscale, xpower, \
                    angscale, angtype, yscale, thresh, analyse, resultfile, energies, dformat, particle, verbose, \
                    warm, prev_gweights, prev_dweights)

                epoch_gen_loss.append(generator_loss)
                index +=1
        

        print('Time taken by epoch{} was {} seconds.'.format(epoch, time.time()-epoch_start))

        #--------------------------------------------------------------------------------------------
        #------------------------------ Main Testing Cycle ------------------------------------------
        #--------------------------------------------------------------------------------------------

        #read first test file
        disc_test_loss=[]
        gen_test_loss =[]
        nb_file=0
        index=0
        file_index=0

        # Test process will also be accomplished in batches to reduce memory consumption
        print('\nTesting for epoch {}:'.format(epoch))
        test_start = time.time()


        # repeat till data is available
        while nb_file < len(Testfiles):

            print('processed {} batches'.format(index + 1))
            print ('Loading Data from .....', Testfiles[nb_file])
            
            # Get the dataset from the Testfile
            dataset = tfconvert.RetrieveTFRecord(Testfiles[nb_file])

            # Get the Test values from the dataset
            dataset = GetDataAngleParallel(dataset, xscale=xscale, xpower=xpower, angscale=angscale, angtype=angtype, thresh=thresh, daxis=daxis)
            nb_file+=1

            #create the dataset with tensors from the Test values, and batch it using the global batch size
            dataset = tf.data.Dataset.from_tensor_slices(dataset).batch(batch_size)

            # Testing
            for batch in dataset:

                this_batch_size = tf.shape(batch.get('Y')).numpy()[0]

                disc_eval_loss, gen_eval_loss = Test_steps(discriminator, generator, batch, nEvents, WeightsDir, pklfile, \
                    Testfiles, nb_test_batches, daxis, daxis2, loss_ftn, combined, \
                    nb_epochs, this_batch_size, latent_size, loss_weights, lr, rho, decay, g_weights, d_weights, xscale, xpower, \
                    angscale, angtype, yscale, thresh, analyse, resultfile, energies, dformat, particle, verbose, \
                    warm, prev_gweights, prev_dweights)

                index +=1
                # evaluate discriminator loss           
                disc_test_loss.append(disc_eval_loss)
                # evaluate generator loss
                gen_test_loss.append(gen_eval_loss)


        #--------------------------------------------------------------------------------------------
        #------------------------------ Updates -----------------------------------------------------
        #--------------------------------------------------------------------------------------------


        # make loss dict 
        print('Total Test batches were {}'.format(index))
        discriminator_train_loss = np.mean(np.array(epoch_disc_loss), axis=0)
        discriminator_test_loss = np.mean(np.array(disc_test_loss), axis=0)
        generator_train_loss = np.mean(np.array(epoch_gen_loss), axis=0)
        generator_test_loss = np.mean(np.array(gen_test_loss), axis=0)
        train_history['generator'].append(generator_train_loss)
        train_history['discriminator'].append(discriminator_train_loss)
        test_history['generator'].append(generator_test_loss)
        test_history['discriminator'].append(discriminator_test_loss)
        # print losses
        print('{0:<20s} | {1:6s} | {2:12s} | {3:12s}| {4:5s} | {5:8s} | {6:8s}'.format(
            'component', *discriminator.metrics_names))
        print('-' * 65)
        ROW_FMT = '{0:<20s} | {1:<4.2f} | {2:<10.2f} | {3:<10.2f}| {4:<10.2f} | {5:<10.2f}| {6:<10.2f}'
        print(ROW_FMT.format('generator (train)',
                                *train_history['generator'][-1]))
        print(ROW_FMT.format('generator (test)',
                                *test_history['generator'][-1]))
        print(ROW_FMT.format('discriminator (train)',
                                *train_history['discriminator'][-1]))
        print(ROW_FMT.format('discriminator (test)',
                                *test_history['discriminator'][-1]))

        # save weights every epoch                                                                                                                                                                                                                                                    
        generator.save_weights(WeightsDir + '/{0}{1:03d}.hdf5'.format(g_weights, epoch),
                                overwrite=True)
        discriminator.save_weights(WeightsDir + '/{0}{1:03d}.hdf5'.format(d_weights, epoch),
                                    overwrite=True)

        epoch_time = time.time()-test_start
        print("The Testing for {} epoch took {} seconds. Weights are saved in {}".format(epoch, epoch_time, WeightsDir))

        
        # save loss dict to pkl file
        pickle.dump({'train': train_history, 'test': test_history}, open(pklfile, 'wb'))

        #--------------------------------------------------------------------------------------------
        #------------------------------ Analysis ----------------------------------------------------
        #--------------------------------------------------------------------------------------------

        
        # if a short analysis is to be performed for each epoch
        if analyse:
            print('analysing..........')
            atime = time.time()
            # load all test data
            for index, dtest in enumerate(Testfiles):
                if index == 0:
                   X_test, Y_test, ang_test, ecal_test = GetDataAngle(dtest, xscale=xscale, angscale=angscale, angtype=angtype, thresh=thresh, daxis=daxis)
                else:
                   if X_test.shape[0] < nb_Test:
                     X_temp, Y_temp, ang_temp,  ecal_temp = GetDataAngle(dtest, xscale=xscale, angscale=angscale, angtype=angtype, thresh=thresh, daxis=daxis)
                     X_test = np.concatenate((X_test, X_temp))
                     Y_test = np.concatenate((Y_test, Y_temp))
                     ang_test = np.concatenate((ang_test, ang_temp))
                     ecal_test = np.concatenate((ecal_test, ecal_temp))
            if X_test.shape[0] > nb_Test:
               X_test, Y_test, ang_test, ecal_test = X_test[:nb_Test], Y_test[:nb_Test], ang_test[:nb_Test], ecal_test[:nb_Test]
            else:
               nb_Test = X_test.shape[0] # the nb_test maybe different if total events are less than nEvents      
            var=gan.sortEnergy([np.squeeze(X_test), Y_test, ang_test], ecal_test, energies, ang=1)
            result = gan.OptAnalysisAngle(var, generator, energies, xpower = xpower, concat=2)
            print('{} seconds taken by analysis'.format(time.time()-atime))
            analysis_history['total'].append(result[0])
            analysis_history['energy'].append(result[1])
            analysis_history['moment'].append(result[2])
            analysis_history['angle'].append(result[3])
            print('Result = ', result)
            # write analysis history to a pickel file
            pickle.dump({'results': analysis_history}, open(resultfile, 'wb'))

#---------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------

def Discriminator_Train_steps(discriminator, generator, dataset, nEvents, WeightsDir, pklfile, Trainfiles, nb_train_batches, daxis, daxis2, loss_ftn, combined, nb_epochs=30, batch_size=128, latent_size=200, loss_weights=[3, 0.1, 25, 0.1, 0.1], lr=0.001, rho=0.9, decay=0.0, g_weights='params_generator_epoch_', d_weights='params_discriminator_epoch_', xscale=1, xpower=1, angscale=1, angtype='theta', yscale=100, thresh=1e-4, analyse=False, resultfile="", energies=[], dformat='channels_last', particle='Ele', verbose=False, warm=False, prev_gweights='', prev_dweights=''):
    # Get a single batch    
    image_batch = dataset.get('X')#.numpy()
    energy_batch = dataset.get('Y')#.numpy()
    ecal_batch = dataset.get('ecal')#.numpy()
    ang_batch = dataset.get('ang')#.numpy()
    add_loss_batch = np.expand_dims(loss_ftn(image_batch, xpower, daxis2), axis=-1)

    # Generate Fake events with same energy and angle as data batch
    noise = np.random.normal(0, 1, (batch_size, latent_size-2)).astype(np.float32)
    generator_ip = tf.concat((tf.reshape(energy_batch, (-1,1)), tf.reshape(ang_batch, (-1, 1)), noise),axis=1)
    generated_images = generator.predict(generator_ip, verbose=0)

    # Train discriminator first on real batch and then the fake batch
    real_batch_loss = discriminator.train_on_batch(image_batch, [gan.BitFlip(np.ones(batch_size).astype(np.float32)), energy_batch, ang_batch, ecal_batch, add_loss_batch])  
    fake_batch_loss = discriminator.train_on_batch(generated_images, [gan.BitFlip(np.zeros(batch_size).astype(np.float32)), energy_batch, ang_batch, ecal_batch, add_loss_batch])

    return real_batch_loss, fake_batch_loss


def Generator_Train_steps(discriminator, generator, dataset, nEvents, WeightsDir, pklfile, Trainfiles, nb_train_batches, daxis, daxis2, loss_ftn, combined, nb_epochs=30, batch_size=128, latent_size=200, loss_weights=[3, 0.1, 25, 0.1, 0.1], lr=0.001, rho=0.9, decay=0.0, g_weights='params_generator_epoch_', d_weights='params_discriminator_epoch_', xscale=1, xpower=1, angscale=1, angtype='theta', yscale=100, thresh=1e-4, analyse=False, resultfile="", energies=[], dformat='channels_last', particle='Ele', verbose=False, warm=False, prev_gweights='', prev_dweights=''):
    # Get a single batch    
    image_batch = dataset.get('X')#.numpy()
    energy_batch = dataset.get('Y')#.numpy()
    ecal_batch = dataset.get('ecal')#.numpy()
    ang_batch = dataset.get('ang')#.numpy()
    add_loss_batch = np.expand_dims(loss_ftn(image_batch, xpower, daxis2), axis=-1)

    
    trick = np.ones(batch_size).astype(np.float32)
    gen_losses = []
    # Train generator twice using combined model
    for _ in range(2):
        noise = np.random.normal(0, 1, (batch_size, latent_size-2)).astype(np.float32)
        generator_ip = tf.concat((tf.reshape(energy_batch, (-1,1)), tf.reshape(ang_batch, (-1, 1)), noise),axis=1) # sampled angle same as g4 theta
        gen_losses.append(combined.train_on_batch(
            [generator_ip],
            [trick, tf.reshape(energy_batch, (-1,1)), ang_batch, ecal_batch, add_loss_batch]))
    generator_loss = [(a + b) / 2 for a, b in zip(*gen_losses)]


    return generator_loss

#---------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------


def Test_steps(discriminator, generator, dataset, nEvents, WeightsDir, pklfile, Testfiles, nb_test_batches, daxis, daxis2, loss_ftn, combined, nb_epochs=30, batch_size=128, latent_size=200, loss_weights=[3, 0.1, 25, 0.1, 0.1], lr=0.001, rho=0.9, decay=0.0, g_weights='params_generator_epoch_', d_weights='params_discriminator_epoch_', xscale=1, xpower=1, angscale=1, angtype='theta', yscale=100, thresh=1e-4, analyse=False, resultfile="", energies=[], dformat='channels_last', particle='Ele', verbose=False, warm=False, prev_gweights='', prev_dweights=''):    
    # Get a single batch    
    image_batch = dataset.get('X')#.numpy()
    energy_batch = dataset.get('Y')#.numpy()
    ecal_batch = dataset.get('ecal')#.numpy()
    ang_batch = dataset.get('ang')#.numpy()
    add_loss_batch = np.expand_dims(loss_ftn(image_batch, xpower, daxis2), axis=-1)

    # Generate Fake events with same energy and angle as data batch
    noise = np.random.normal(0, 1, (batch_size, latent_size-2)).astype(np.float32)
    generator_ip = tf.concat((tf.reshape(energy_batch, (-1,1)), tf.reshape(ang_batch, (-1, 1)), noise),axis=1)
    generated_images = generator.predict(generator_ip, verbose=False)

    # concatenate to fake and real batches
    X = tf.concat((image_batch, generated_images), axis=0)
    y = np.array([1] * batch_size + [0] * batch_size).astype(np.float32)
    ang = tf.concat((ang_batch, ang_batch), axis=0)
    ecal = tf.concat((ecal_batch, ecal_batch), axis=0)
    aux_y = tf.concat((energy_batch, energy_batch), axis=0)
    add_loss= tf.concat((add_loss_batch, add_loss_batch), axis=0)

    disc_eval_loss = discriminator.evaluate( X, [y, aux_y, ang, ecal, add_loss], verbose=False, batch_size=batch_size)
    gen_eval_loss = combined.evaluate(generator_ip, [np.ones(batch_size), energy_batch, ang_batch, ecal_batch, add_loss_batch], verbose=False, batch_size=batch_size)

    return disc_eval_loss, gen_eval_loss
    


if __name__ == '__main__':
    main()