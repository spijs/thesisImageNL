__author__ = 'Wout & thijs'

import os
import sys
import argparse
import numpy as np
from nltk.stem.porter import *
# from sklearn.cross_decomposition import CCA
sys.path.append("..")
import rcca
import scipy.io
from scipy import spatial
import pickle
from PIL import Image
from imagernn.data_provider import getDataProvider
import sys

def preprocess():
    dataset = "flickr30k"
    os.chdir("..")
    dataprovider = getDataProvider(dataset, pert=1)
    os.chdir("cca")
    img_sentence_pair_generator = dataprovider.iterImageSentencePair()
    print "Reading Vocabulary..."
    vocabulary = readVocabulary("training_dictionary_pert.txt")
    print "Done"
    print "Creating sentence vectors..."
    occurrences, idf, images = getOccurenceVectorsAndImages(vocabulary, img_sentence_pair_generator)
    print "Done"
    print "Weighing vectors"
    weightedVectors = weight_tfidf(occurrences, idf)
    pair = image_sentence_matrix_pair(images, weightedVectors)
    pair_file = open("imagesentencematrix.p", 'wb')
    pickle.dump(pair, pair_file)
    pair_file.close()

def create_mat_files():
    print "Loading data into memory"
    load_from = open("imagesentencematrix.p", 'rb')
    matrixpair = pickle.load(load_from)
    load_from.close()
    images = np.array(matrixpair.images)
    print "Image dimensions " + str(images.shape)
    sentences = np.array(matrixpair.sentences)
    print "Sentence dimensions " + str(sentences.shape)
    np.savetxt("sentences.txt", sentences)
    np.savetxt("images.txt", images)
    # scipy.io.savemat('images.mat', {"images":images})
    # scipy.io.savemat('sentences.mat', {"sentences":sentences})

class image_sentence_matrix_pair:
    def __init__(self, images, sentences):
        self.images = images
        self.sentences = sentences


def main(params):
    print "Loading data into memory"
    load_from = open("imagesentencematrix.p", 'rb')
    matrixpair = pickle.load(load_from)
    load_from.close()
    images = np.array(matrixpair.images)
    print "Image dimensions " + str(images.shape)
    sentences = np.array(matrixpair.sentences)
    print "Sentence dimensions " + str(sentences.shape)
    print "Done"
    print "Learning CCA"
    # print str(len(images))
    cca = rcca.CCA(kernelcca=False, numCC=256, reg=0.)
    cca.train([images, sentences])
    # cca = CCA(n_components= 256, max_iter=700)
    # cca.fit(images, weightedVectors)
    # print "SIZE OF CCA:" + str(sys.getsizeof(cca))
    print "writing results to pickle"
    pickle_dump_file = open("../data/trainingCCA.p",'w+')
    pickle.dump(cca, pickle_dump_file)
    pickle_dump_file.close()
    print('finished')


'''Returns a list containing the most frequent english words'''
def getStopwords():
        stopwords = set()
        file=open('../lda_images/english')
        for line in file.readlines():
            stopwords.add(line[:-1])
        return stopwords

''' stems a word by using the porter algorithm'''
def stem(word):
    stemmer = PorterStemmer()
    return stemmer.stem(word)

def weight_tfidf(documents, inv_freq):
    result = []
    for i in range(len(documents)):
        doc = documents[i]
        result.append(doc * inv_freq)
    return result

'''
Given a sentence, return a copy of that sentence, stripped of words that are in the provided stopwords
'''
def remove_common_words(sentence,stopwords):
        #s = set(stopwords.words('english'))
        stopwords.add(' ') #add spaces to stopwords
        result = []
        for word in sentence:
            if not word.lower() in stopwords and len(word)>2:
                result.append(word.lower())
        return result

'''
Given a image-sentence pair generator and a vocabulary, this function returns TF vectors
for each sentence, the IDF for each word and a matrix containing all image representations.
'''
def getOccurenceVectorsAndImages(vocabulary, pairGenerator):
    stopwords = getStopwords()
    images = []
    idf = np.zeros(len(vocabulary))
    current = 0
    result = []
    for pair in pairGenerator:
        current+= 1
        if current % 1000 ==0:
            print "Processing pair " + str(current)
        sentence = remove_common_words(pair['sentence']['tokens'],stopwords)
        wordcount = 0
        row = np.zeros(len(vocabulary))
        for word in sentence:
            stemmed = stem(word.decode('utf-8')).lower()
            if stemmed in vocabulary:
                wordcount += 1
                i = vocabulary.index(stemmed.lower())
                row[i] += 1
            if wordcount:
                row = row / wordcount
            for w in range(len(row)):
                if row[w] > 0:
                    idf[w] += 1
        result.append(row)
        images.append(pair['image']['feat'])
    idf = len(result) / idf
    return result, idf, images

'''
Creates a vocabulary based on a folder. Returns a list of words
'''
def readVocabulary(filename):
    result = []
    voc = open(filename)
    line = voc.readline()
    while line:
        result.append(line[0:-1])
        line = voc.readline()
    return result

''' Parses the given arguments'''
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dataset', dest='dataset', default='flickr8k', help='dataset: flickr8k/flickr30k')


    args = parser.parse_args()
    params = vars(args) # convert to ordinary dict
    main(params)
