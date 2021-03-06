__author__ = 'Thijs & Wout'

from evaluationStrategy import EvaluationStrategy
import subprocess as sp
import codecs
import nltk

class MeteorScore(EvaluationStrategy):
    ''' METEOR Scores as defined in https://www.cs.cmu.edu/~alavie/METEOR/ '''

    def evaluate_sentence(self,sentence,references,n=None):
        ''' Evaluates the METEOR score of a single sentence, given its references'''

        self.write_singlereferences(references)
        self.write_singlesentences(sentence)
        command = "java -Xmx2G -jar meteor/meteor-1.5.jar meteor_sentences.txt meteor_references.txt -l en -norm"
        process = sp.Popen(command,stdin=sp.PIPE, stdout=sp.PIPE, shell=True)
        lines_iterator = iter(process.stdout.readline, b"")
        fline = ""
        for line in lines_iterator:
            fline = line
        result = fline.split("            ")
        return result[1]

    def evaluate_total(self,sentences,references,n=None):
        ''' Evaluates the METEOR score of an entire corpus '''

        self.write_references(references)
        self.write_sentences(sentences)

        command = "java -Xmx2G -jar meteor/meteor-1.5.jar meteor_sentences meteor_references -r 5 -l en -norm"
        process = sp.Popen(command,stdin=sp.PIPE, stdout=sp.PIPE, shell=True)
        lines_iterator = iter(process.stdout.readline, b"")
        fline = ""
        for line in lines_iterator:
            print line
            fline = line
        result = fline.split("            ")
        return result[1]

    def write_references(self,references):
        ''' Writes a list containing lists of 5 references to a txt-file'''

        f= codecs.open('meteor_references','w','utf-8')
        i=0
        for lof_references in references:
            i= i+1
            j=0
            for reference in lof_references:
                j=j+1
                if(i==len(references) and j==5):
                    f.write(reference)
                else:
                    f.write(reference+'\n')
        f.close()

    def print_list(self,list):
        '''
        Prints elements of list separated by spaces.
        '''
        s = ""
        start = True
        for word in list:
            if start:
                s = word
            else:
                s= s + " " + word
            start=False
        return s

    def write_sentences(self,sentences):
        ''' Writes 5 copies of the sentences in a list to a txt-file '''

        f = codecs.open('meteor_sentences','w','utf-8')
        i = 0
        for sentence in sentences:
            i+=1
            if i==len(sentences):
                f.write(sentence)
            else:
                f.write(sentence+'\n')
        f.close()

    def write_singlesentences(self,sentence):
        ''' Writes one sentence 5 times to a txt-file'''
        f = open('meteor_sentences.txt','w')
        for i in range(5):
            f.write(sentence+'\n')
        f.close()

    def write_singlereferences(self,sentences):
        ''' Writes a list of references to a txt-file '''
        f = open('meteor_references.txt','w')
        for sentence in sentences:
            f.write(sentence+'\n')
        f.close()
