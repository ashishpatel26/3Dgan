import sys
import h5py

from h5py import File as HDF5File
import numpy as np

import keras.backend as K
from keras.layers import (Input, Dense, Reshape, Flatten, Lambda, merge,
                          Dropout, BatchNormalization, Activation, Embedding)
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.convolutional import (UpSampling3D, Conv3D, ZeroPadding3D,
                                        AveragePooling3D)

from keras.models import Model, Sequential
import math
from tensorflow import py_func, float32, Tensor
import tensorflow as tf

if K.image_data_format() =='channels_last':
    daxis=(1,2,3)
else:
    daxis=(2,3,4)

# Summming cell energies
def ecal_sum(image, power):
    image = K.pow(image, 1./power)
    sum = K.sum(image, axis=daxis)
    return sum
   
# counting entries for different energy bins
def count(image, power):
    bin1 = K.sum(K.tf.where(image > 0.05**power, K.ones_like(image), K.zeros_like(image)), axis=daxis)
    bin2 = K.sum(K.tf.where(K.tf.logical_and(image < 0.05**power, image > 0.03**power), K.ones_like(image), K.zeros_like(image)), axis=daxis)
    bin3 = K.sum(K.tf.where(K.tf.logical_and(image < 0.03**power, image > 0.02**power), K.ones_like(image), K.zeros_like(image)), axis=daxis)
    bin4 = K.sum(K.tf.where(K.tf.logical_and(image < 0.02**power, image > 0.0125**power), K.ones_like(image), K.zeros_like(image)), axis=daxis)
    bin5 = K.sum(K.tf.where(K.tf.logical_and(image < 0.0125**power, image > 0.008**power), K.ones_like(image), K.zeros_like(image)), axis=daxis)
    bin6 = K.sum(K.tf.where(K.tf.logical_and(image < 0.008**power, image > 0.003**power), K.ones_like(image), K.zeros_like(image)), axis=daxis)
    bin7 = K.sum(K.tf.where(K.tf.logical_and(image < 0.003**power, image > 0.0), K.ones_like(image), K.zeros_like(image)), axis=daxis)
    bin8 = K.sum(K.tf.where(K.tf.equal(image, 0.0), K.ones_like(image), K.zeros_like(image)), axis=daxis)
    bins = K.expand_dims(K.concatenate([bin1, bin2, bin3, bin4, bin5, bin6, bin7, bin8], axis=1), -1)
    return bins

# Calculating angle from image
def ecal_angle(image, power):
    if K.image_data_format() =='channels_last':
       image = K.squeeze(image, axis=4)
    else: 
       image = K.squeeze(image, axis=1)
    image = K.pow(image, 1./power)
    # size of ecal
    x_shape= K.int_shape(image)[1]
    y_shape= K.int_shape(image)[2]
    z_shape= K.int_shape(image)[3]
    sumtot = K.sum(image, axis=(1,2,3))# sum of events
    # get 1. where event sum is 0 and 0 elsewhere
    amask = K.tf.where(K.equal(sumtot, 0.0), K.ones_like(sumtot) , K.zeros_like(sumtot))
    masked_events = K.sum(amask) # counting zero sum events
    
    # ref denotes barycenter as that is our reference point
    x_ref = K.sum(K.sum(image, axis=(2,3)) * (K.cast(K.expand_dims(K.arange(x_shape), 0), dtype='float32') + 0.5) , axis=1)# sum for x position * x index
    y_ref = K.sum(K.sum(image, axis=(1,3)) * (K.cast(K.expand_dims(K.arange(y_shape), 0), dtype='float32') + 0.5), axis=1)
    z_ref = K.sum(K.sum(image, axis=(1,2)) * (K.cast(K.expand_dims(K.arange(z_shape), 0), dtype='float32') + 0.5), axis=1)
    x_ref = K.tf.where(K.equal(sumtot, 0.0), K.ones_like(x_ref) , x_ref/sumtot)# return max position if sumtot=0 and divide by sumtot otherwise
    y_ref = K.tf.where(K.equal(sumtot, 0.0), K.ones_like(y_ref) , y_ref/sumtot)
    z_ref = K.tf.where(K.equal(sumtot, 0.0), K.ones_like(z_ref), z_ref/sumtot)
    #reshape    
    x_ref = K.expand_dims(x_ref, 1)
    y_ref = K.expand_dims(y_ref, 1)
    z_ref = K.expand_dims(z_ref, 1)

    sumz = K.sum(image, axis =(1,2)) # sum for x,y planes going along z

    # Get 0 where sum along z is 0 and 1 elsewhere
    zmask = K.tf.where(K.equal(sumz, 0.0), K.zeros_like(sumz) , K.ones_like(sumz))
        
    x = K.expand_dims(K.arange(x_shape), 0) # x indexes
    x = K.cast(K.expand_dims(x, 2), dtype='float32') + 0.5
    y = K.expand_dims(K.arange(y_shape), 0)# y indexes
    y = K.cast(K.expand_dims(y, 2), dtype='float32') + 0.5
  
    #barycenter for each z position
    x_mid = K.sum(K.sum(image, axis=2) * x, axis=1)
    y_mid = K.sum(K.sum(image, axis=1) * y, axis=1)
    x_mid = K.tf.where(K.equal(sumz, 0.0), K.zeros_like(sumz), x_mid/sumz) # if sum != 0 then divide by sum
    y_mid = K.tf.where(K.equal(sumz, 0.0), K.zeros_like(sumz), y_mid/sumz) # if sum != 0 then divide by sum

    #Angle Calculations
    z = (K.cast(K.arange(z_shape), dtype='float32') + 0.5)  * K.ones_like(z_ref) # Make an array of z indexes for all events
    zproj = K.sqrt(K.maximum((x_mid-x_ref)**2.0 + (z - z_ref)**2.0, K.epsilon()))# projection from z axis with stability check
    m = K.tf.where(K.equal(zproj, 0.0), K.zeros_like(zproj), (y_mid-y_ref)/zproj)# to avoid divide by zero for zproj =0
    m = K.tf.where(K.tf.less(z, z_ref),  -1 * m, m)# sign inversion
    ang = (math.pi/2.0) - tf.atan(m)# angle correction
    zmask = K.tf.where(K.equal(zproj, 0.0), K.zeros_like(zproj) , zmask)
    ang = ang * zmask # place zero where zsum is zero
    
    ang = ang * z  # weighted by position
    sumz_tot = z * zmask # removing indexes with 0 energies or angles

    #zunmasked = K.sum(zmask, axis=1) # used for simple mean 
    #ang = K.sum(ang, axis=1)/zunmasked # Mean does not include positions where zsum=0

    ang = K.sum(ang, axis=1)/K.sum(sumz_tot, axis=1) # sum ( measured * weights)/sum(weights)
    ang = K.tf.where(K.equal(amask, 0.), ang, 100. * K.ones_like(ang)) # Place 100 for measured angle where no energy is deposited in events
    
    ang = K.expand_dims(ang, 1)
    return ang

# Discriminator
def discriminator(power=1.0):
    if K.image_data_format() =='channels_last':
        dshape=(51, 51, 25,1)
    else:
        dshape=(1, 51, 51, 25)
        daxis=(2,3,4)

    image = Input(shape=dshape) 

    x = Conv3D(16, 5, 6, 6, border_mode='same')(image)
    x = LeakyReLU()(x)
    x = Dropout(0.2)(x)

    x = ZeroPadding3D((0, 0, 1))(x)
    x = Conv3D(8, 5, 6, 6, border_mode='valid')(x)
    x = LeakyReLU()(x)
    x = BatchNormalization()(x)
    x = Dropout(0.2)(x)

    x = ZeroPadding3D((0, 0, 1))(x)
    x = Conv3D(8, 5, 6, 6, border_mode='valid')(x)
    x = LeakyReLU()(x)
    x = BatchNormalization()(x)
    x = Dropout(0.2)(x)

    x = Conv3D(8, 5, 6, 6, border_mode='valid')(x)
    x = LeakyReLU()(x)
    x = BatchNormalization()(x)
    x = Dropout(0.2)(x)

    x = AveragePooling3D((2, 2, 2))(x)
    h = Flatten()(x)

    dnn = Model(image, h)
    dnn.summary()

    dnn_out = dnn(image)
    fake = Dense(1, activation='sigmoid', name='generation')(dnn_out)
    aux = Dense(1, activation='linear', name='auxiliary')(dnn_out)
    ang = Lambda(ecal_angle, arguments={'power':power})(image)
    ecal = Lambda(ecal_sum, arguments={'power':power})(image)
    add_loss = Lambda(count, arguments={'power':power})(image)
    Model(input=[image], output=[fake, aux, ang, ecal, add_loss]).summary()
    return Model(input=[image], output=[fake, aux, ang, ecal, add_loss])

# Generator
def generator(latent_size=200, return_intermediate=False):
    if K.image_data_format() =='channels_last':
        dim = (9,9,8,8)
        baxis=-1 # axis for BatchNormalization
    else:
        dim = (8, 9, 9,8) 
        baxis=1 # axis for BatchNormalization
    loc = Sequential([
        Dense(5184, input_shape=(latent_size,)),
        Reshape(dim),
        UpSampling3D(size=(6, 6, 6)),
        
        Conv3D(8, (6, 6, 8), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        BatchNormalization(axis=baxis, epsilon=1e-6),
        
        ZeroPadding3D((2, 2, 1)),
        Conv3D(6, (4, 4, 6), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        BatchNormalization(axis=baxis, epsilon=1e-6),
        ####################################### added layers 
        
        ZeroPadding3D((2, 2, 1)),
        Conv3D(6, (4, 4, 6), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        BatchNormalization(axis=baxis, epsilon=1e-6),

        ZeroPadding3D((2, 2, 1)),
        Conv3D(6, (4, 4, 6), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        BatchNormalization(axis=baxis, epsilon=1e-6),

        ZeroPadding3D((1, 1, 0)),
        Conv3D(6, (3, 3, 5), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        BatchNormalization(axis=baxis, epsilon=1e-6),
        
        #####################################  
        
        ZeroPadding3D((1, 1,0)),
        Conv3D(6, (3, 3, 3), padding='valid', kernel_initializer='he_uniform'),
        Activation('relu'),
        
        Conv3D(1, (2, 2, 2),  padding='valid', kernel_initializer='glorot_normal'),
        Activation('relu')
    ])
    latent = Input(shape=(latent_size, ))   
    fake_image = loc(latent)
    loc.summary()
    Model(input=[latent], output=[fake_image]).summary()
    return Model(input=[latent], output=[fake_image])

# useful at design time
def main():
    g= generator()
    d=discriminator()

if __name__ == "__main__":
    main()


