#!/usr/bin/env python
# -*- coding: utf-8 -*-   

# This file tests the training results with the optimization function

from __future__ import print_function
import sys
import h5py
import os
import numpy as np
import glob
import numpy.core.umath_tests as umath
import time
import math
import ROOT
from scipy.stats import wasserstein_distance as wass
import ot
import scipy as sp

if os.environ.get('HOSTNAME') == 'tlab-gpu-gtx1080ti-06.cern.ch': # Here a check for host can be used
    tlab = True
else:
    tlab= False

try:
    import setGPU #if Caltech
except:
    pass

import utils.GANutils as gan
sys.path.insert(0,'../')

def main():
    from AngleArch3dGAN import generator
    weightdir= '3dgan_weights_gan_training_epsilon_2_500GeV/params_generator*.hdf5'
    if tlab:
      datapath = '/gkhattak/*Measured3ThetaEscan/*.h5'
      genpath = '/gkhattak/weights/' + weightdir
    else:
      datapath = "/data/shared/gkhattak/*Measured3ThetaEscan/*VarAngleMeas_*.h5" # path to data
      genpath = "../weights/" + weightdir # path to weights
    #datapath = "/data/shared/LCDLargeWindow/varangle/*scan/*scan_RandomAngle_*.h5" # culture plate 
    sorted_path = 'Anglesorted'  # where sorted data is to be placed
    plotsdir = 'results/optimization_gw_2_500' # plot directory
    particle = "Ele" 
    scale = 1
    threshold = 0
    ang = 1
    concat=2
    power=0.85
    g= generator(latent_size=256)
    start = 0
    stop = 120
    gen_weights=[]
    disc_weights=[]
    fits = ['pol1', 'pol2', 'expo']
    
    gan.safe_mkdir(plotsdir)
    for f in sorted(glob.glob(genpath)):
      gen_weights.append(f)
    gen_weights=gen_weights[start:stop]
    epoch = []
    for i in np.arange(len(gen_weights)):
      name = os.path.basename(gen_weights[i])
      num = int(filter(str.isdigit, name)[:-1])
      epoch.append(num)
    print("{} weights are found".format(len(gen_weights)))

    result = GetResults(metric, plotsdir, gen_weights, g, datapath, sorted_path, particle
                        , scale, power=power, thresh=threshold, ang=ang, concat=concat
            , preproc = taking_power, postproc=inv_power
             )
    print(result)
    PlotResultsRoot(result, plotsdir, start, epochs=epoch, fits=fits, ang=ang)

def sqrt(n, scale=1):
    return np.sqrt(n * scale)

def square(n, scale=1):
    return np.square(n)/scale

def taking_power(n, xscale=1, power=1):
    return np.power(n * xscale, power)

def inv_power(n, xscale=1, power=1.):
    return np.power(n, 1./power)/xscale
        
def normalize(array):
    mina = np.amin(array)
    maxa = np.amax(array)
    return (array - mina)/(maxa - mina)

#Plots results in a root file
def PlotResultsRoot(result, resultdir, start, epochs, fits, ang=1):
    c1 = ROOT.TCanvas("c1" ,"" ,200 ,10 ,700 ,500)
    legend = ROOT.TLegend(.5, .75, .9, .9)
    color = [2, 8, 4, 6, 7]
    minr = 100
    l=len(epochs)
    ep=np.zeros((l))
    res= np.zeros((l))
    minr_n = epochs[0]
    for i, epoch in enumerate(epochs):      
      if result[i]< minr:
         minr = result[i]
         minr_n = epoch
      ep[i]=epoch
      res[i]=result[i]
    print(ep)
    print(res)
    gw  = ROOT.TGraph(l , ep, res )
    gw.SetLineColor(color[0])
    legend.SetHeader('Smoothing(avg 5)', 'C')
    legend.AddEntry(gw, "Min Loss {:.4f} (epoch {})".format(minr, minr_n), "l")
    gw.SetTitle("Optimization function: Entropic Gromov Wasserstein;Epochs;loss")
    gw.Draw('ALP')
    c1.Update()
    legend.Draw()
    c1.Update()
    c1.Print(os.path.join(resultdir, "result.pdf"))

    fits = []#['pol1', 'pol2', 'expo']
    for i, fit in enumerate(fits):
      gw.Fit(fit)
      gw.GetFunction(fit).SetLineColor(color[i])
      gw.GetFunction(fit).SetLineStyle(2)
      if i == 0:
        legend.AddEntry(gt.GetFunction(fit), 'fit', "l")
      legend.Draw()
      c1.Update()
      c1.Print(os.path.join(resultdir, "result_{}.pdf".format(fit)))
      print ('The plot is saved to {}'.format(resultdir))

def preproc(n, scale=1):
    return n * scale

def postproc(n, scale=1):
    return n/scale
        
def norm(x, min_val, max_val):
    return (x-min_val)/(max_val-min_val)

def moving_average(iterable, n=5):
    d = deque(maxlen=n)
    for i in iterable:
        d.append(i)
        if len(d) == n:
            yield sum(d)/n

def moving_avg(result, num=5):
    avg =[]
    for i, r in enumerate(result):
        if i==0:
           avg.append(r)
        elif i < num:
           cumsum = np.sum(np.array(result[:i+1]))
           avg.append(cumsum/(i + 1))
        else:
           cumsum = np.sum(np.array(result[i-num:i]))
           avg.append(cumsum/num)
    return avg
                                     
# results are obtained using metric and saved to a log file
def GetResults(metric, resultdir, gen_weights, g, datapath, sorted_path, particle="Ele", scale=100, power=1, thresh=1e-6, ang=1, concat=1, preproc=preproc, postproc=postproc):
    resultfile = os.path.join(resultdir,  'result_log.txt')
    file = open(resultfile,'w')
    result = []
    for i in range(len(gen_weights)):
       if i==0:
         res = analyse(g, False, True, gen_weights[i], datapath, sorted_path, metric, scale, power, particle, thresh=thresh, ang=ang, concat=concat, postproc=postproc)
       else:
         res = analyse(g, True, False, gen_weights[i], datapath, sorted_path, metric, scale, power, particle, thresh=thresh, ang=ang, concat=concat, postproc=postproc)
       if np.isnan(res):
         if len(result) > 0:
           res = result[-1]
       else:
           res=0
          
       result.append(res)
       #file.write(len(result[i]) * '{:.4f}\t'.format(*result[i]))
       file.write('\t'.join(str(result[i])))
       file.write('\n')
                  
    #print all results together at end                                                                               
    for i in range(len(gen_weights)):                                                                                            
       print ('The results for ......',gen_weights[i])
       print (result[i])
    file.close
    smooth = np.array(moving_avg(result))
    
    print ('The results are saved to {}'.format(resultfile))
    return smooth

# If reduced data is to be used in analyse function the line:
#   var = ang.get_sorted_angle(data_files, energies, flag=False, num_events1=10000, num_events2=2000, thresh=thresh)
# has to be replaced with:
#   var = ang.get_sorted_angle(data_files, energies, flag=False, num_events1=10000, num_events2=2000, Data= GetAngleData_reduced, thresh=thresh)

def GetAngleData_reduced(datafile, thresh=1e-6):
    #get data for training
    print ('Loading Data from .....', datafile)
    f=h5py.File(datafile,'r')
    X=np.array(f.get('ECAL'))[:, 13:38, 13:38, :]
    Y=np.array(f.get('energy'))
    eta = np.array(f.get('eta')) + 0.6
    X[X < thresh] = 0
    X = np.expand_dims(X, axis=-1)
    X = X.astype(np.float32)
    Y = Y.astype(np.float32)
    ecal = np.sum(X, axis=(1, 2, 3))
    return X, Y, eta, ecal

def preproc(n, scale=1):
    return n * scale

def postproc(n, scale=1):
    return n/scale

# This function will calculate two errors derived from position of maximum along an axis and the sum of ecal along the axis
def analyse(g, read_data, save_data, gen_weights, datapath, sorted_path, optimizer, xscale=100, power=1, particle="Ele", thresh=1e-6, ang=1, concat=1, preproc=preproc, postproc=postproc):
   print ("Started")
   num_events=2000
   num_data = 140000
   ascale = 1
   Test = True
   latent= 256
   m = 2
   var = {}
   energies = [0]#, 150, 190]
   #energies = [50, 100, 200, 300, 400]
   sorted_path= sorted_path 
   #g =generator(latent)
   if read_data:
     start = time.time()
     var = gan.load_sorted(sorted_path + "/*.h5", energies, ang = ang)
     sort_time = time.time()- start
     print ("Events were loaded in {} seconds".format(sort_time))
   else:
     Trainfiles, Testfiles = gan.DivideFiles(datapath, Fractions=[.9,.1], datasetnames=["ECAL"], Particles =[particle])
     if Test:
       data_files = Testfiles
     else:
       data_files = Trainfiles + Testfiles
     start = time.time()
     #energies = [50, 100, 200, 250, 300, 400, 500]
     var = gan.get_sorted_angle(data_files, energies, flag=False, num_events1=10000, num_events2=2000, thresh=thresh)
     data_time = time.time() - start
     print ("{} events were loaded in {} seconds".format(num_data, data_time))
     if save_data:
        gan.save_sorted(var, energies, sorted_path, ang=ang)        
   total = 0
   for energy in energies:
     var["index" + str(energy)]= var["energy" + str(energy)].shape[0]
     total += var["index" + str(energy)]
     data_time = time.time() - start
   print ("{} events were put in {} bins".format(total, len(energies)))
   g.load_weights(gen_weights)
              
   start = time.time()
   for energy in energies:
     if ang:
        var["events_gan" + str(energy)] = gan.generate(g, var["index" + str(energy)], [var["energy" + str(energy)]/100, var["angle" + str(energy)] * ascale], concat=concat, latent=latent)
     else:
        var["events_gan" + str(energy)] = gan.generate(g, var["index" + str(energy)], [var["energy" + str(energy)]/100], concat=concat, latent=latent, ang=ang) 
     var["events_gan" + str(energy)] = postproc(var["events_gan" + str(energy)], xscale=xscale, power=power)
   gen_time = time.time() - start
   print ("{} events were generated in {} seconds".format(total, gen_time))
   calc={}
   print("Weights are loaded in {}".format(gen_weights))
   for energy in energies:
     x = var["events_act" + str(energy)].shape[1]
     y = var["events_act" + str(energy)].shape[2]
     z = var["events_act" + str(energy)].shape[3]
     var["ecal_act"+ str(energy)] = np.sum(var["events_act" + str(energy)], axis = (1, 2, 3))
     var["ecal_gan"+ str(energy)] = np.sum(var["events_gan" + str(energy)], axis = (1, 2, 3))
     calc["sumsx_act"+ str(energy)], calc["sumsy_act"+ str(energy)], calc["sumsz_act"+ str(energy)] = gan.get_sums(var["events_act" + str(energy)])
     calc["sumsx_gan"+ str(energy)], calc["sumsy_gan"+ str(energy)], calc["sumsz_gan"+ str(energy)] = gan.get_sums(var["events_gan" + str(energy)])
     calc["momentX_act" + str(energy)], calc["momentY_act" + str(energy)], calc["momentZ_act" + str(energy)]= gan.get_moments(calc["sumsx_act"+ str(energy)], calc["sumsy_act"+ str(energy)], calc["sumsz_act"+ str(energy)], var["ecal_act"+ str(energy)], m, x=x, y=y, z=z)
     calc["momentX_gan" + str(energy)], calc["momentY_gan" + str(energy)], calc["momentZ_gan" + str(energy)] = gan.get_moments(calc["sumsx_gan"+ str(energy)], calc["sumsy_gan"+ str(energy)], calc["sumsz_gan"+ str(energy)], var["ecal_gan"+ str(energy)], m, x=x, y=y, z=z)
     if ang:
        calc["mtheta_act"+ str(energy)]= measPython(var["events_act" + str(energy)])
        calc["mtheta_gan"+ str(energy)]= measPython(var["events_gan" + str(energy)])
     calc["sf_act" + str(energy)] = np.divide(var["ecal_act"+ str(energy)], np.reshape(var["energy"+ str(energy)], (-1, 1)))
     calc["sf_gan" + str(energy)] = np.divide(var["ecal_gan"+ str(energy)], np.reshape(var["energy"+ str(energy)], (-1, 1)))
   return optimizer(calc, energies, m, x=x, y=y, z=z, ang=ang)                                        
 
def metric(var, energies, m, angtype='mtheta', x=25, y=25, z=25, ang=1):
   metricp = 0
   metrice = 0
   metrica = 0
   metrics = 0
         
   for i, energy in enumerate([energies[0]]):
     if i==0:
         moment_act=np.hstack((var["momentX_act" + str(energy)], var["momentY_act" + str(energy)], var["momentZ_act" + str(energy)]))
         shapes_act = np.hstack((var["sumsx_act"+ str(energy)], var["sumsy_act"+ str(energy)], var["sumsz_act"+ str(energy)]))
         if ang: angles_act= np.reshape(var["mtheta_act" + str(energy)], (-1, 1))
         sampfr_act = np.reshape(var["sf_act"+ str(energy)], (-1, 1))
         moment_gan=np.hstack((var["momentX_gan" + str(energy)], var["momentY_gan" + str(energy)], var["momentZ_gan" + str(energy)]))
         shapes_gan = np.hstack((var["sumsx_gan"+ str(energy)], var["sumsy_gan"+ str(energy)], var["sumsz_gan"+ str(energy)]))
         if ang: angles_gan= np.reshape(var["mtheta_gan" + str(energy)], (-1, 1))
         sampfr_gan = np.reshape(var["sf_gan"+ str(energy)], (-1, 1))
     metric_act = np.hstack((moment_act, shapes_act, angles_act, sampfr_act))
     metric_gan = np.hstack((moment_gan, shapes_gan, angles_gan, sampfr_gan))

     metric_a = np.transpose(metric_act)
     metric_g = np.transpose(metric_gan)
     a = (0.25 /127.)* np.ones(127)
     b = (0.25/6.) *np.ones(6)
     c = 0.25 *np.ones(2)
  
     p = np.concatenate((a, b, c))
     q = np.concatenate((a, b, c))
     C1 = sp.spatial.distance.cdist(metric_a, metric_a, 'correlation')
     C2 = sp.spatial.distance.cdist(metric_g, metric_g, 'correlation')
 
     C1 = C1/np.amax(C1)
     C2 = C2/np.amax(C2)
     #gw0, log0 = ot.gromov.gromov_wasserstein(C1, C2, p, q, 'square_loss', verbose=True, log=True)
     #gw, log = ot.gromov.entropic_gromov_wasserstein(C1, C2, p, q, 'kl_loss', epsilon=5e-2, log=True, verbose=True)
     gw, log = ot.gromov.entropic_gromov_wasserstein(C1, C2, p, q, 'square_loss', epsilon=5e-2, log=True, verbose=True)
     print('Gromov-Wasserstein distances: ' + str(log['gw_dist']))
   return log['gw_dist']

def measPython(image): # Working version:p1 and p2 are not used. 3D angle with barycenter as reference point
    image = np.squeeze(image)
    x_shape= image.shape[1]
    y_shape= image.shape[2]
    z_shape= image.shape[3]

    sumtot = np.sum(image, axis=(1, 2, 3))# sum of events
    indexes = np.where(sumtot > 0)
    amask = np.ones_like(sumtot)
    amask[indexes] = 0

    #amask = K.tf.where(K.equal(sumtot, 0.0), K.ones_like(sumtot) , K.zeros_like(sumtot))
    masked_events = np.sum(amask) # counting zero sum events

    x_ref = np.sum(np.sum(image, axis=(2, 3)) * np.expand_dims(np.arange(x_shape) + 0.5, axis=0), axis=1)
    y_ref = np.sum(np.sum(image, axis=(1, 3)) * np.expand_dims(np.arange(y_shape) + 0.5, axis=0), axis=1)
    z_ref = np.sum(np.sum(image, axis=(1, 2)) * np.expand_dims(np.arange(z_shape) + 0.5, axis=0), axis=1)

    x_ref[indexes] = x_ref[indexes]/sumtot[indexes]
    y_ref[indexes] = y_ref[indexes]/sumtot[indexes]
    z_ref[indexes] = z_ref[indexes]/sumtot[indexes]

    sumz = np.sum(image, axis =(1, 2)) # sum for x,y planes going along z

    x = np.expand_dims(np.arange(x_shape) + 0.5, axis=0)
    x = np.expand_dims(x, axis=2)
    y = np.expand_dims(np.arange(y_shape) + 0.5, axis=0)
    y = np.expand_dims(y, axis=2)
    x_mid = np.sum(np.sum(image, axis=2) * x, axis=1)
    y_mid = np.sum(np.sum(image, axis=1) * y, axis=1)
    indexes = np.where(sumz > 0)

    zmask = np.zeros_like(sumz)
    zmask[indexes] = 1
    zunmasked_events = np.sum(zmask, axis=1)

    x_mid[indexes] = x_mid[indexes]/sumz[indexes]
    y_mid[indexes] = y_mid[indexes]/sumz[indexes]
    z = np.arange(z_shape) + 0.5# z indexes
    x_ref = np.expand_dims(x_ref, 1)
    y_ref = np.expand_dims(y_ref, 1)
    z_ref = np.expand_dims(z_ref, 1)

    zproj = np.sqrt((x_mid-x_ref)**2.0  + (z - z_ref)**2.0)
    m = (y_mid-y_ref)/zproj
    z = z * np.ones_like(z_ref)
    indexes = np.where(z<z_ref)
    m[indexes] = -1 * m[indexes]
    ang = (math.pi/2.0) - np.arctan(m)
    ang = ang * zmask

    #ang = np.sum(ang, axis=1)/zunmasked_events #mean
    ang = ang * z # weighted by position
    sumz_tot = z * zmask
    ang = np.sum(ang, axis=1)/np.sum(sumz_tot, axis=1)

    indexes = np.where(amask>0)
    ang[indexes] = 100.
    return ang

if __name__ == "__main__":
    main()
