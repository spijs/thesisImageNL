__author__ = 'spijs'

import numpy as np
import code
import math
from nltk.stem.porter import *

from imagernn.utils import initw

class gLSTMGenerator:
  """
  A multimodal guided long short-term memory (gLSTM) generator
  """

  @staticmethod
  def init(input_size, hidden_size, guide_size, output_size):
    model = {}
    # Recurrent weights: take x_t, h_{t-1}, and bias unit
    # and produce the 3 gates and the input to cell signal
    print "input size " + str(input_size)
    print "hidden size " + str(hidden_size)
    print "guide size " + str(guide_size)
    model['WLSTM'] = initw(input_size + hidden_size + 1 + guide_size, 4 * hidden_size)
    # Decoder weights (e.g. mapping to vocabulary)
    model['Wd'] = initw(hidden_size, output_size) # decoder
    model['bd'] = np.zeros((1, output_size))
    model['input_size'] = input_size
    update = ['WLSTM', 'Wd', 'bd']
    regularize = ['WLSTM', 'Wd']
    return { 'model' : model, 'update' : update, 'regularize' : regularize }

  @staticmethod

  def forward(Xi, Xs, guide, model, params, **kwargs):
    """
    Xi is 1-d array of size D (containing the image representation)
    Xs is N x D (N time steps, rows are data containng word representations), and
    it is assumed that the first row is already filled in as the start token. So a
    sentence with 10 words will be of size 11xD in Xs.
    guide is a guide vector for the gLSTM model.
    """
    predict_mode = kwargs.get('predict_mode', False)

    # Google paper concatenates the image to the word vectors as the first word vector
    X = np.row_stack([Xi, Xs])

    # options
    # use the version of LSTM with tanh? Otherwise dont use tanh (Google style)
    # following http://arxiv.org/abs/1409.3215
    tanhC_version = params.get('tanhC_version', 0)
    drop_prob_encoder = params.get('drop_prob_encoder', 0.0)
    drop_prob_decoder = params.get('drop_prob_decoder', 0.0)

    if drop_prob_encoder > 0: # if we want dropout on the encoder
      # inverted version of dropout here. Suppose the drop_prob is 0.5, then during training
      # we are going to drop half of the units. In this inverted version we also boost the activations
      # of the remaining 50% by 2.0 (scale). The nice property of this is that during prediction time
      # we don't have to do any scailing, since all 100% of units will be active, but at their base
      # firing rate, giving 100% of the "energy". So the neurons later in the pipeline dont't change
      # their expected firing rate magnitudes
      if not predict_mode: # and we are in training mode
        scale = 1.0 / (1.0 - drop_prob_encoder)
        U = (np.random.rand(*(X.shape)) < (1 - drop_prob_encoder)) * scale # generate scaled mask
        X *= U # drop!

    # follows http://arxiv.org/pdf/1409.2329.pdf
    WLSTM = model['WLSTM']
    input_size = model['input_size']
    n = X.shape[0]
    d = model['Wd'].shape[0] # size of hidden layer
    Hin = np.zeros((n, WLSTM.shape[0])) # xt, ht-1, bias
    Hout = np.zeros((n, d))
    IFOG = np.zeros((n, d * 4))
    IFOGf = np.zeros((n, d * 4)) # after nonlinearity
    C = np.zeros((n, d))
    for t in xrange(n):
      # set input
      prev = np.zeros(d) if t == 0 else Hout[t-1]
      Hin[t,0] = 1
      Hin[t,1:1+d] = X[t]
      Hin[t,1+d:(1+d+input_size)] = prev
      Hin[t,1+d+input_size:] = guide

      # compute all gate activations. dots:
      IFOG[t] = Hin[t].dot(WLSTM)

      # non-linearities
      IFOGf[t,:3*d] = 1.0/(1.0+np.exp(-IFOG[t,:3*d])) # sigmoids; these are the gates
      IFOGf[t,3*d:] = np.tanh(IFOG[t, 3*d:]) # tanh

      # compute the cell activation
      C[t] = IFOGf[t,:d] * IFOGf[t, 3*d:]
      if t > 0: C[t] += IFOGf[t,d:2*d] * C[t-1]
      if tanhC_version:
        Hout[t] = IFOGf[t,2*d:3*d] * np.tanh(C[t])
      else:
        Hout[t] = IFOGf[t,2*d:3*d] * C[t]

    if drop_prob_decoder > 0: # if we want dropout on the decoder
      if not predict_mode: # and we are in training mode
        scale2 = 1.0 / (1.0 - drop_prob_decoder)
        U2 = (np.random.rand(*(Hout.shape)) < (1 - drop_prob_decoder)) * scale2 # generate scaled mask
        Hout *= U2 # drop!

    # decoder at the end
    Wd = model['Wd']
    bd = model['bd']
    # NOTE1: we are leaving out the first prediction, which was made for the image
    # and is meaningless.
    Y = Hout[1:, :].dot(Wd) + bd

    cache = {}
    if not predict_mode:
      # we can expect to do a backward pass
      cache['WLSTM'] = WLSTM
      cache['Hout'] = Hout
      cache['Wd'] = Wd
      cache['IFOGf'] = IFOGf # New for gLSTM
      cache['IFOG'] = IFOG # New for gLSTM
      cache['C'] = C
      cache['X'] = X
      cache['Hin'] = Hin
      cache['tanhC_version'] = tanhC_version
      cache['drop_prob_encoder'] = drop_prob_encoder
      cache['drop_prob_decoder'] = drop_prob_decoder
      if drop_prob_encoder > 0: cache['U'] = U # keep the dropout masks around for backprop
      if drop_prob_decoder > 0: cache['U2'] = U2

    return Y, cache

  @staticmethod
  def backward(dY, cache):

    Wd = cache['Wd']
    Hout = cache['Hout']
    IFOG = cache['IFOG']
    IFOGf = cache['IFOGf']
    C = cache['C']
    Hin = cache['Hin']
    WLSTM = cache['WLSTM']
    X = cache['X']
    tanhC_version = cache['tanhC_version']
    drop_prob_encoder = cache['drop_prob_encoder']
    drop_prob_decoder = cache['drop_prob_decoder']
    n,d = Hout.shape

    # we have to add back a row of zeros, since in the forward pass
    # this information was not used. See NOTE1 above.
    dY = np.row_stack([np.zeros(dY.shape[1]), dY])

    # backprop the decoder
    dWd = Hout.transpose().dot(dY)
    dbd = np.sum(dY, axis=0, keepdims = True)
    dHout = dY.dot(Wd.transpose())

    # backprop dropout, if it was applied
    if drop_prob_decoder > 0:
      dHout *= cache['U2']

    # backprop the LSTM
    dIFOG = np.zeros(IFOG.shape)
    dIFOGf = np.zeros(IFOGf.shape)
    dWLSTM = np.zeros(WLSTM.shape)
    dHin = np.zeros(Hin.shape)
    dC = np.zeros(C.shape)
    dX = np.zeros(X.shape)
    for t in reversed(xrange(n)):

      if tanhC_version:
        tanhCt = np.tanh(C[t]) # recompute this here
        dIFOGf[t,2*d:3*d] = tanhCt * dHout[t]
        # backprop tanh non-linearity first then continue backprop
        dC[t] += (1-tanhCt**2) * (IFOGf[t,2*d:3*d] * dHout[t])
      else:
        dIFOGf[t,2*d:3*d] = C[t] * dHout[t]
        dC[t] += IFOGf[t,2*d:3*d] * dHout[t]

      if t > 0:
        dIFOGf[t,d:2*d] = C[t-1] * dC[t]
        dC[t-1] += IFOGf[t,d:2*d] * dC[t]
      dIFOGf[t,:d] = IFOGf[t, 3*d:] * dC[t]
      dIFOGf[t, 3*d:] = IFOGf[t,:d] * dC[t]

      # backprop activation functions
      dIFOG[t,3*d:] = (1 - IFOGf[t, 3*d:] ** 2) * dIFOGf[t,3*d:]
      y = IFOGf[t,:3*d]
      dIFOG[t,:3*d] = (y*(1.0-y)) * dIFOGf[t,:3*d]

      # backprop matrix multiply
      dWLSTM += np.outer(Hin[t], dIFOG[t])
      dHin[t] = dIFOG[t].dot(WLSTM.transpose())

      # backprop the identity transforms into Hin
      dX[t] = dHin[t,1:1+d]
      if t > 0:
        dHout[t-1] += dHin[t,(1+d):(1+2*d)]

    if drop_prob_encoder > 0: # backprop encoder dropout
      dX *= cache['U']

    return { 'WLSTM': dWLSTM, 'Wd': dWd, 'bd': dbd, 'dXi': dX[0,:], 'dXs': dX[1:,:] }

  @staticmethod
  def predict(Xi, guide,  model, Ws, params, **kwargs):
    """
    Run in prediction mode with beam search. The input is the vector Xi, which
    should be a 1-D array that contains the encoded image vector. We go from there.
    Ws should be NxD array where N is size of vocabulary + 1. So there should be exactly
    as many rows in Ws as there are outputs in the decoder Y. We are passing in Ws like
    this because we may not want it to be exactly model['Ws']. For example it could be
    fixed word vectors from somewhere else.
    """
    tanhC_version = params['tanhC_version']
    beam_size = kwargs.get('beam_size', 1)
    normalization = kwargs.get('normalization',None)

    WLSTM = model['WLSTM']
    d = model['Wd'].shape[0] # size of hidden layer
    Wd = model['Wd']
    bd = model['bd']
    input_size = model['input_size']
    # lets define a helper function that does a single LSTM tick
    def LSTMtick(x, h_prev, c_prev):
      t = 0

      # setup the input vector
      Hin = np.zeros((1,WLSTM.shape[0])) # xt, ht-1, bias
      Hin[t,0] = 1
      Hin[t,1:1+d] = x
      Hin[t,1+d:(1+d+input_size)] = h_prev
      Hin[t,1+d+input_size:] = guide

      # LSTM tick forward
      IFOG = np.zeros((1, d * 4))
      IFOGf = np.zeros((1, d * 4))
      C = np.zeros((1, d))
      Hout = np.zeros((1, d))
      IFOG[t] = Hin[t].dot(WLSTM)
      IFOGf[t,:3*d] = 1.0/(1.0+np.exp(-IFOG[t,:3*d]))
      IFOGf[t,3*d:] = np.tanh(IFOG[t, 3*d:])
      C[t] = IFOGf[t,:d] * IFOGf[t, 3*d:] + IFOGf[t,d:2*d] * c_prev
      if tanhC_version:
        Hout[t] = IFOGf[t,2*d:3*d] * np.tanh(C[t])
      else:
        Hout[t] = IFOGf[t,2*d:3*d] * C[t]
      Y = Hout.dot(Wd) + bd
      return (Y, Hout, C) # return output, new hidden, new cell

    # forward prop the image
    (y0, h, c) = LSTMtick(Xi, np.zeros(d), np.zeros(d))

    # perform BEAM search. NOTE: I am not very confident in this implementation since I don't have
    # a lot of experience with these models. This implements my current understanding but I'm not
    # sure how to handle beams that predict END tokens. TODO: research this more.
    if beam_size > 1:
      #normalized log probability, log probability, indices of words predicted in this beam so far, and the hidden and cell states
      beams = [(0.0, 0.0, [], h, c)]
      nsteps = 0
      while True:
        beam_candidates = []
        for b in beams:
          ixprev = b[2][-1] if b[2] else 0 # start off with the word where this beam left off else first word is 0
          if ixprev == 0 and b[2]:
            # this beam predicted end token. Keep in the candidates but don't expand it out any more
            beam_candidates.append(b)
            continue
          (y1, h1, c1) = LSTMtick(Ws[ixprev], b[3], b[4])
          y1 = y1.ravel() # make into 1D vector
          maxy1 = np.amax(y1)
          e1 = np.exp(y1 - maxy1) # for numerical stability shift into good numerical range
          p1 = e1 / np.sum(e1)
          y1 = np.log(1e-20 + p1) # and back to log domain
          #TODO hier algemener maken
          top_indices = np.argsort(-y1)  # we do -y because we want decreasing order
          for i in xrange(beam_size):
            wordix = top_indices[i]
            beam_candidates.append(((b[1] + y1[wordix])/normalize(normalization,b[2],kwargs['idf'],kwargs['words']),b[1] + y1[wordix], b[2] + [wordix], h1, c1))
        beam_candidates.sort(reverse = True) # decreasing order
        beams = beam_candidates[:beam_size] # truncate to get new beams
        nsteps += 1
        if nsteps >= 20: # bad things are probably happening, break out
          break
      # strip the intermediates
      predictions = [(b[0], b[2]) for b in beams]
    else:
      # greedy inference. lets write it up independently, should be bit faster and simpler
      ixprev = 0
      nsteps = 0
      predix = []
      predlogprob = 0.0
      while True:
        (y1, h, c) = LSTMtick(Ws[ixprev], h, c)
        ixprev, ixlogprob = ymax(y1)
        predix.append(ixprev)
        predlogprob += ixlogprob
        nsteps += 1
        if ixprev == 0 or nsteps >= 20:
          break
      predictions = [(predlogprob, predix)]

    return predictions

def ymax(y):
  """ simple helper function here that takes unnormalized logprobs """
  y1 = y.ravel() # make sure 1d
  maxy1 = np.amax(y1)
  e1 = np.exp(y1 - maxy1) # for numerical stability shift into good numerical range
  p1 = e1 / np.sum(e1)
  y1 = np.log(1e-20 + p1) # guard against zero probabilities just in case
  ix = np.argmax(y1)
  return (ix, y1[ix])

# Flickr30k
# Mean: 12.315055172413793
# Std.Dev : 5.188878248688354
def gaussianNorm(length, mean=12.315 , dev=5.18887):
  '''
  Returns the value of the gaussian function given the mean and standard deviation of the training sentence lengths.
  :param length: length for which the function needs to be evaluated
  :param mean: mean of the training sentence lengths
  :param dev: standard deviation of the training sentence lengths
  :return: value of the gaussian
  '''
  var = pow(dev,2)
  norm = 1/(dev*math.sqrt(2*math.pi*var))
  return norm*math.exp(-pow(length-mean,2)/(2*var))

def minhinge(length, mean=12.315):
  '''
  :param length: length for which function needs to be evaluated
  :param mean: mean of the training sentence lengths
  :return: value of the minhinge function
  '''
  if length==0:
    return mean
  return min(mean,length*1.0)

def combined(length,words,idf,nb_to_words, mean=12.315, dev=5.1887):
  '''
  First attempt of combining gaussian normalization with idf normalization.
  :param length: length of the sentence to be evaluated
  :param words: words in the current sentence
  :param idf: dictionary of word-idf pairs
  :param nb_to_words: dictionary of word id to number
  :param mean: mean of the training sentence lengths
  :param dev: standard deviation of the training sentence lengths
  '''
  gauss = gaussianNorm(length)
  sum = 1
  l = len(words)
  if l > mean:
    return gauss
  for ix in words:
    word = nb_to_words[ix]
    stemmed = stem(word.decode('utf-8')).lower()
    try:
       sum += idf[stemmed]
    except Exception:
       pass #Do nothing
  return gauss*sum

def idf_normalize(words,idf,nb_to_words,mean=12.315):
  '''
  Idf normalization function
  :param words: words in the current sentence
  :param idf: dictionary of word-idf pairs
  :param nb_to_words: dictionary of word id to number
  :param mean: mean of the training sentence lengths
  '''
  sum = 1
  l = len(words)
  if l > mean:
    return 1
  for ix in words:
    word = nb_to_words[ix]
    stemmed = stem(word.decode('utf-8')).lower()
    try:
       sum += idf[stemmed]
    except Exception:
       pass #Do nothing
  return sum

def normalize(form,words,idf,ixtoword):
  '''
  :param form: type of normalization to be used
  :param words: words in the current sentence
  :param idf: dictionary containing word idf pairs
  :param ixtoword: dictionary of word to number
  :return: the normalization value
  '''
  length = len(words)
  if form=="gauss":
      return gaussianNorm(length)
  elif form == "minhinge":
      return minhinge(length)
  elif form == "idf":
      return idf_normalize(words,idf,ixtoword)
  elif form == "combined":
      return combined(length,words,idf,ixtoword)
  else:
      return 1

def stem(word):
  ''' stems a word by using the porter algorithm'''
  stemmer = PorterStemmer()
  return stemmer.stem(word)
