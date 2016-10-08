from Bio import SeqIO
from champ import fastq
from champ.adapters_cython import simple_hamming_distance
from collections import defaultdict
import editdistance
import itertools
import logging
import numpy as np
import os
import pickle
import random
import yaml

log = logging.getLogger(__name__)


def main(clargs):
    # TODO: Move this to main.py
    #     min_len:            Minimum allowed overlap
    #     max_len:            Maximum allowed overlap
    #     max_mismatch:       Maximum allowed mismatch between reads
    #     out_file_path:          Location to write output file
    #     log_p_file_path:        Location of pickle file with probability struct
    #     fastq_file_paths:       List of all fastq files in run
    fastq_filenames = os.listdir(clargs.fastq_directory)
    fastq_files = fastq.FastqFiles(fastq_filenames)

    if clargs.log_p_file_path:
        log.debug("Determining probable sequence of each read name.")
        with open(clargs.log_p_file_path) as f:
            log_p_struct = pickle.load(f)

        read_names_given_seq = determine_sequences_of_read_names(clargs.min_len, clargs.max_len,
                                                                 clargs.max_hamming_distance, log_p_struct, fastq_files)
        write_read_names_by_sequence(read_names_given_seq, os.path.join(clargs.output_directory, 'read_names_by_seq.txt'))

        if clargs.target_sequence_file:
            with open(clargs.target_sequence_file) as f:
                targets = yaml.load(f)

            log.info("Creating perfect target read name files.")
            for target_name, perfect_read_names in determine_perfect_target_reads(targets, read_names_given_seq):
                formatted_name = 'perfect_target_%s' % target_name.replace('-', '_').lower()
                log.debug("Finding read names for %s" % formatted_name)
                write_read_names(perfect_read_names, formatted_name, clargs.output_directory)

            # find imperfect target reads
            log.info("Creating target read name files.")
            for target_name, perfect_read_names in determine_target_reads(targets, read_names_given_seq):
                formatted_name = 'target_%s' % target_name.replace('-', '_').lower()
                log.debug("Finding read names for %s" % formatted_name)
                write_read_names(perfect_read_names, formatted_name, clargs.output_directory)

    if clargs.phix_bamfiles:
        log.info("Finding phiX reads.")
        read_names = find_reads_using_bamfile(clargs.phix_bamfiles, fastq_files, clargs.output_directory)
        write_read_names(read_names, 'phix', clargs.output_directory)

    log.info("Parsing and saving all read names to disk.")
    write_all_read_names(fastq_files, os.path.join('all_read_names.txt'))


def find_reads_using_bamfile(bamfile_path, fastq_files, output_directory):
    classifier = fastq.FastqReadClassifier(bamfile_path)
    read_names = set()
    for file1, file2 in fastq_files.paired:
        for read in classifier.paired_call(file1, file2):
            read_names.add(read)
    return read_names


def get_max_edit_dist(target):
    dists = [editdistance.eval(target, rand_seq(target)) for _ in xrange(1000)]
    return min(10, np.percentile(dists, 0.5))


def rand_seq(target):
    seq_len = int(random.normalvariate(len(target), len(target) / 10))
    return ''.join(random.choice('ACGT') for _ in xrange(seq_len))


def determine_target_reads(targets, read_names_given_seq):
    for target_name, target_sequence in targets.items():
        max_edit_dist = get_max_edit_dist(target_sequence)
        for seq, read_names in read_names_given_seq.items():
            if editdistance.eval(target_sequence, seq) <= max_edit_dist:
                yield target_name, read_names


def write_read_names(read_names, target_name, output_directory):
    filename = os.path.join(output_directory, target_name + '_read_names.txt')
    with open(filename, 'w') as f:
        f.write('\n'.join(read_names) + '\n')


def write_read_names_by_sequence(read_names_given_seq, out_file_path):
    with open(out_file_path, 'w') as out:
        for seq, read_names in sorted(read_names_given_seq.items()):
            out.write('{}\t{}\n'.format(seq, '\t'.join(read_names)))


def write_all_read_names(fastq_files, out_file_path):
    # Opens all FastQ files, finds every read name, and saves it in a file without any other data
    with open(out_file_path, 'w+') as out:
        for filenames in fastq_files.paired:
            for filename in filenames:
                with open(filename) as f:
                    for record in parse_fastq_lines(f):
                        out.write(record.name)


def determine_perfect_target_reads(targets, read_names_by_seq):
    for target_name, target_sequence in targets.items():
        perfect_read_names = []
        for seq, read_names in read_names_by_seq.items():
            if target_sequence in seq:
                perfect_read_names += read_names
        yield target_name, perfect_read_names


def determine_sequences_of_read_names(min_len, max_len, max_ham, log_p_struct, fastq_files):
    # --------------------------------------------------------------------------------
    # Load log_p dict of dicts of lists. Addessed as follows:
    #
    #   log_p_struct[true_base][read_base][phred_score]
    # --------------------------------------------------------------------------------

    # --------------------------------------------------------------------------------
    # Pair fpaths and classify seqs
    # --------------------------------------------------------------------------------
    read_names_given_seq = defaultdict(list)
    for fpath1, fpath2 in fastq_files.paired:
        log.debug('{}, {}'.format(*map(os.path.basename, (fpath1, fpath2))))
        discarded = 0
        total = 0
        for i, (rec1, rec2) in enumerate(
                itertools.izip(parse_fastq_lines(fpath1),
                               parse_fastq_lines(fpath2))
        ):
            total += 1
            seq = classify_seq(rec1, rec2, min_len, max_len, max_ham, log_p_struct)
            if seq:
                read_names_given_seq[seq].append(str(rec1.id))
            else:
                discarded += 1
        log.debug('Discarded {} of {} ({:.1f}%)'.format(discarded, total, 100 * discarded / float(total)))
    return read_names_given_seq


def classify_seq(rec1, rec2, min_len, max_len, max_ham, log_p_struct):
    # Store as strings
    seq1 = str(rec1.seq)
    seq2_rc = str(rec2.seq.reverse_complement())

    # Find aligning sequence, indels are not allowed, starts of reads included
    hams = [simple_hamming_distance(seq1[:i], seq2_rc[-i:]) for i in range(min_len, max_len + 1)]
    if min(hams) > max_ham:
        return None

    seq2_len = min(range(min_len, max_len + 1), key=lambda i: hams[i - min_len])
    seq2_match = seq2_rc[-seq2_len:]
    seq1_match = seq1[:seq2_len]

    # Get corresponding quality scores
    quals1 = rec1.letter_annotations['phred_quality'][:seq2_len]
    quals2 = rec2.letter_annotations['phred_quality'][::-1][-seq2_len:]

    # Build concensus sequence
    bases = set('ACGT')
    ML_bases = []
    for r1, q1, r2, q2 in zip(seq1_match, quals1, seq2_match, quals2):
        if r1 in bases and r1 == r2:
            ML_bases.append(r1)
        elif set([r1, r2]) <= bases and q1 > 2 and q2 > 2:
            r1_score = log_p_struct[r1][r1][q1] + log_p_struct[r1][r2][q2]
            r2_score = log_p_struct[r2][r1][q1] + log_p_struct[r2][r2][q2]
            if r1_score > r2_score:
                ML_bases.append(r1)
            else:
                ML_bases.append(r2)
        elif r1 in bases and q1 > 2:
            ML_bases.append(r1)
        elif r2 in bases and q2 > 2:
            ML_bases.append(r2)
        else:
            return None
    return ''.join(ML_bases)


def parse_fastq_lines(fh):
    for record in SeqIO.parse(fh, 'fastq'):
        yield record


def isint(a):
    try:
        int(a)
        return float(a) == int(a)
    except:
        return False