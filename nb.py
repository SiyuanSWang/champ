import glob
import itertools
import os
import random
import sys

import matplotlib.pyplot as plt
import numpy as np
from champ import misc, intensity

date = '20160609'
project_name = 'SA16105'
target_name = 'E'
target = "esequence"
off_target = "bsequence"
datadir = "/shared/160609/"
figdir = "/shared/160609/figs"
resultsdir = "/shared/160609/results"

print 'Image Collection Date:', date
print 'Sequencing Project Name:', project_name
print 'Target "{}":'.format(target_name), target
print 'Off target:', off_target

read_name_dir = '/shared/SA16105/read_names'
all_read_name_fpath = os.path.join(read_name_dir, 'all_read_names.txt')
target_read_name_fpath = os.path.join(read_name_dir, 'target_{}_read_names.txt'.format(target_name.lower()))
perfect_target_read_name_fpath = os.path.join(read_name_dir, 'perfect_target_{}_read_names.txt'.format(target_name.lower()))
phiX_read_name_fpath = os.path.join('/shared/SA16105' 'phiX_mappings', 'phiX_read_names.txt')

all_read_names = set(line.strip() for line in open(all_read_name_fpath))
target_read_names = set(line.strip() for line in open(target_read_name_fpath))
perfect_target_read_names = set(line.strip() for line in open(perfect_target_read_name_fpath))
phiX_read_names = set(line.strip() for line in open(phiX_read_name_fpath))

h5_fpaths = glob.glob(os.path.join(datadir, '*.h5'))
i = 0
while i < len(h5_fpaths):
    if 'PhiX' in h5_fpaths[i] or 'chip' in h5_fpaths[i]:
        h5_fpaths.pop(i)
    else:
        i += 1
h5_fpaths.sort(key=misc.parse_concentration)
for fpath in h5_fpaths:
    print(misc.parse_concentration(fpath), fpath)

results_dir_name = date
results_dirs = [
    os.path.join(resultsdir,
                 results_dir_name,
                 os.path.splitext(os.path.basename(h5_fpath))[0])
    for h5_fpath in h5_fpaths
]

print('Loading data...')
nonneg_lda_weights_fpath = '/shared/bLDA_coef_nonneg.txt'
int_scores = intensity.IntensityScores(h5_fpaths)
int_scores.get_LDA_scores(results_dirs, nonneg_lda_weights_fpath)

print 'Normalizing data...'
int_scores.normalize_scores()

int_scores.plot_aligned_images('br', 'o*')

int_scores.plot_normalization_constants()

int_scores.print_reads_per_channel()

good_num_ims_cutoff = len(h5_fpaths) - 1
int_scores.build_good_read_names(good_num_ims_cutoff)

good_read_names = int_scores.good_read_names

good_perfect_read_names = perfect_target_read_names & good_read_names
print 'Good Perfect Reads:', len(good_perfect_read_names)

bases = 'ACGT'


def dot():
    sys.stdout.write(".")
    sys.stdout.flush()


def get_sequences_given_ref_and_hamming_distance(ref_seq, ham):
    seqs = []
    for idxs in itertools.combinations(range(len(ref_seq)), ham):
        mm_bases = [bases.replace(ref_seq[idx], '') for idx in idxs]
        for new_bases in itertools.product(*mm_bases):
            new_seq = ref_seq[:idxs[0]]
            for i, new_base in enumerate(new_bases[:-1]):
                new_seq += new_base + ref_seq[idxs[i]+1:idxs[i+1]]
            new_seq += new_bases[-1] + ref_seq[idxs[-1]+1:]
            seqs.append(new_seq)
    return seqs

single_ham_seqs = get_sequences_given_ref_and_hamming_distance(target, 1)
double_ham_seqs = get_sequences_given_ref_and_hamming_distance(target, 2)
close_seqs = [target] + single_ham_seqs + double_ham_seqs

close_reads = {seq: set() for seq in close_seqs}
read_names_by_seq_fpath = os.path.join(read_name_dir, 'read_names_by_seq.txt')
for line in open(read_names_by_seq_fpath):
    words = line.strip().split()
    seq = words[0]
    read_names = words[1:]
    for close_seq in close_seqs:
        if close_seq in seq:
            close_reads[close_seq].update(rn for rn in read_names if rn in good_read_names)
            break

single_counts = [len(close_reads[seq]) for seq in single_ham_seqs]

fig, ax = plt.subplots(figsize=(15, 6))
ax.hist(single_counts, 50, histtype='step')
ax.set_title('Good Ham=1 Reads Found')
ax.set_xlabel('Read Counts')
ax.set_ylabel('Number of Seqs')

fig, ax = plt.subplots()
ax.hist(single_counts, 50, histtype='step')
ax.set_title('Good Ham=1 Reads Found')
ax.set_xlabel('Read Counts')
ax.set_ylabel('Number of Seqs')
ax.set_xlim((0, 50))

double_counts = [len(close_reads[seq]) for seq in double_ham_seqs]

fig, ax = plt.subplots(figsize=(15, 6))
ax.hist(double_counts, 200, histtype='step')
ax.set_title('Good Ham=2 Reads Found')
ax.set_xlabel('Read Counts')
ax.set_ylabel('Number of Seqs')

fig, ax = plt.subplots()
ax.hist(double_counts, 200, histtype='step')
ax.set_title('Good Ham=2 Reads Found')
ax.set_xlabel('Read Counts')
ax.set_ylabel('Number of Seqs')
ax.set_xlim((0, 50))

custom_fig_dir = os.path.join(figdir, date, 'custom')
if not os.path.isdir(custom_fig_dir):
    os.makedirs(custom_fig_dir)

int_scores.build_score_given_read_name_given_channel()

from scipy.optimize import minimize, curve_fit
from matplotlib.ticker import MultipleLocator

bad_read_names = set()
for line in open(read_names_by_seq_fpath):
    words = line.strip().split()
    seq = words[0]
    read_names = words[1:]
    if off_target in seq:
        bad_read_names.update(rn for rn in read_names if rn in good_read_names)

cascade_channel = 'Alexa488_blue'
for h5_fpath in h5_fpaths:
    pM_conc = misc.parse_concentration(h5_fpath)
    if cascade_channel not in int_scores.score_given_read_name_in_channel[h5_fpath]:
        continue
    score_dict = int_scores.score_given_read_name_in_channel[h5_fpath][cascade_channel]
    intensities = []
    for read_name in bad_read_names:
        if read_name in score_dict:
            intensities.append(score_dict[read_name])
    if intensities:
        break

Fmin = np.average(intensities)
print 'Fmin:', Fmin

def Fobs(x, Kd, Fmax):
    return Fmax / (1.0 + (float(Kd)/x)) + Fmin

def make_Fobs_sq_error(concentrations, intensities):
    def Fobs_sq_error(params):
        Kd, Fmax = params
        return sum((Fobs(conc, Kd, Fmax) - obs_avg)**2 for conc, obs_avg in zip(concentrations, intensities))
    return Fobs_sq_error


def fit_curve_given_read_names(read_names):
    all_pM_concentrations = []
    all_intensities = []
    for h5_fpath in h5_fpaths:
        pM_conc = misc.pM_concentration_given_fpath(h5_fpath)
        if cascade_channel not in int_scores.score_given_read_name_in_channel[h5_fpath]:
            continue
        score_dict = int_scores.score_given_read_name_in_channel[h5_fpath][cascade_channel]
        for read_name in read_names:
            if read_name in score_dict:
                all_pM_concentrations.append(pM_conc)
                all_intensities.append(score_dict[read_name])
    return minimize(make_Fobs_sq_error(all_pM_concentrations, all_intensities), (500, 1), bounds=((0, None), (0, None)))

sample_size = min(2000, len(good_perfect_read_names))
all_res = fit_curve_given_read_names(random.sample(good_perfect_read_names, sample_size))

concentrations = [misc.pM_concentration_given_fpath(h5_fpath) for h5_fpath in h5_fpaths]
nM_concentrations = [conc / 1000.0 for conc in concentrations]
print concentrations

xx = np.logspace(1, 5, 200)
yy = Fobs(xx, *all_res.x)

fig, ax = plt.subplots(figsize=(10, 7))
if True:
    for read_name in random.sample(good_perfect_read_names, sample_size):
        intensities = [int_scores.score_given_read_name_in_channel[h5_fpath][cascade_channel][read_name]
                       if cascade_channel in int_scores.score_given_read_name_in_channel[h5_fpath]
                          and read_name in int_scores.score_given_read_name_in_channel[h5_fpath][cascade_channel]
                       else None
                       for h5_fpath in h5_fpaths]


ax.plot(nM_concentrations, intensities, 'b', alpha=0.01)
ax.plot(xx / 1000, yy, 'r', label='Fit Curve', linewidth=2.5)
ax.set_xscale('log')
ax.grid(False)
Kd, Fmax = all_res.x
Kd /= 1000

ax.set_title('Fluorescence vs Concentration Curve')
ax.set_xlabel('Concentration (nM)')
ax.set_ylabel('Intensity')
xlim, ylim = ax.get_xlim(), ax.get_ylim()

inc = (ylim[1] - ylim[0]) / 3
oom = int(np.log10(inc))
inc -= inc % max(1, int(0.05 * 10 ** oom))
ax.yaxis.set_major_locator(MultipleLocator(inc))

ax.text(0.2, sum(ax.get_ylim()) / 2, '$K_d = %.2f$ nM\n$F_{max} = %.1f$\n$F_{min} = %.1f$' % (Kd, Fmax, Fmin), fontsize=20, va='center')
for item in ([ax.title, ax.xaxis.label, ax.yaxis.label] +
                 ax.get_xticklabels() + ax.get_yticklabels()):
    item.set_fontsize(18)

ax.set_axis_bgcolor('white')
fig.savefig(os.path.join(custom_fig_dir, 'Kd_curve_fit.png'))

def Fobs_fixed(x, Kd):
    return all_res.x[1] / (1.0 + (float(Kd)/x)) + Fmin

def make_Fobs_fixed_sq_error(concentrations, intensities):
    def Fobs_sq_error(Kd):
        return sum((Fobs_fixed(conc, Kd) - obs_avg)**2 for conc, obs_avg in zip(concentrations, intensities))
    return Fobs_sq_error

# def fit_Fobs_fixed_curve_given_read_names(read_names):
#     all_pM_concentrations = []
#     all_intensities = []
#     for nd2 in nd2s:
#         pM_conc = misc.parse_concentration(nd2._filename)
#         if cascade_channel_idx not in int_scores.score_given_read_name_in_channel[nd2]:
#             continue
#         score_dict = int_scores.score_given_read_name_in_channel[nd2][cascade_channel_idx]
#         for read_name in read_names:
#             all_pM_concentrations.append(pM_conc)
#             all_intensities.append(score_dict[read_name])
#     return minimize(make_Fobs_fixed_sq_error(all_pM_concentrations, all_intensities), (500,), bounds=((0, None),))

def curve_fit_Fobs_fixed_curve_given_read_names(read_names, verbose=False):
    all_pM_concentrations = []
    all_intensities = []
    for h5_fpath in h5_fpaths:
        pM_conc = misc.parse_concentration(h5_fpath)
        if cascade_channel not in int_scores.score_given_read_name_in_channel[h5_fpath]:
            continue
        score_dict = int_scores.score_given_read_name_in_channel[h5_fpath][cascade_channel]
        for read_name in read_names:
            if read_name in score_dict:
                all_pM_concentrations.append(pM_conc)
                all_intensities.append(float(score_dict[read_name]))
    if verbose:
        print all_pM_concentrations
        print all_intensities
    else:
        return curve_fit(Fobs_fixed, all_pM_concentrations, all_intensities)

R = 8.3144598

def delta_G(Kd):
    """Takes a Kd in pM and return delta_G in J/mol"""
    return R * 333 * np.log(Kd / 10**12)

ref_delta_G = delta_G(all_res.x[0])

def delta_delta_G(Kd, Kd_ref=None):
    """Returns delta_delta_G in J/mol"""
    if Kd_ref is None:
        return delta_G(Kd) - ref_delta_G
    else:
        return R * 333 * (np.log(Kd) - np.log(Kd_ref))

len(good_read_names)

seq_Kds = {}
seq_Kd_error = {}
seq_ddGs = {}
seq_ddG_error = {}
for i, (seq, read_names) in enumerate(close_reads.items()):
    if i % 100 == 0:
        dot()
    if len(read_names) < 5:
        continue
    read_names = list(read_names)
    popt, pcov = curve_fit_Fobs_fixed_curve_given_read_names(read_names)
    seq_Kds[seq] = popt[0]
    seq_ddGs[seq] = delta_delta_G(popt[0])

    bootstrap_Kds, bootstrap_ddGs = [], []
    for _ in range(50):
        resamp_read_names = np.random.choice(read_names, size=len(read_names), replace=True)
        try:
            popt, pcov = curve_fit_Fobs_fixed_curve_given_read_names(resamp_read_names)
        except:
            curve_fit_Fobs_fixed_curve_given_read_names(resamp_read_names)
            print seq, len(read_names), len(resamp_read_names)
            raise
        bootstrap_Kds.append(popt[0])
        bootstrap_ddGs.append(delta_delta_G(popt[0]))
    seq_Kd_error[seq] = np.std(bootstrap_Kds)
    seq_ddG_error[seq] = np.std(bootstrap_ddGs)

custom_results_dir = os.path.join(resultsdir, results_dir_name, 'custom')
if not os.path.isdir(custom_results_dir):
    os.makedirs(custom_results_dir)

for fname, Kds, Kd_error in [('target{}_close_seq_Kds_and_errors.txt'.format(target_name), seq_Kds, seq_Kd_error)]:
    fpath = os.path.join(custom_results_dir, fname)
    with open(fpath, 'w') as out:
        out.write('# Seq\tKd (pM)\tKd error (pM)\n')
        out.write('\n'.join(['%s\t%f\t%f' % (seq, Kds[seq], Kd_error[seq]) for seq in sorted(Kds.keys())]))

for fname, ddGs, ddG_error in [('target{}_close_seq_ddGs_and_errors.txt'.format(target_name), seq_ddGs, seq_ddG_error)]:
    fpath = os.path.join(custom_results_dir, fname)
    with open(fpath, 'w') as out:
        out.write('# Seq\tddG (J/mol)\tddG error (J/mol)\n')
        out.write('\n'.join(['%s\t%f\t%f' % (seq, ddGs[seq], ddG_error[seq]) for seq in sorted(ddGs.keys())]))

bases = 'ACGT'

single_Kd_list = np.array([seq_Kds[seq]/1000.0 for seq in single_ham_seqs if seq in seq_Kds])
single_Kd_list.sort()

fig, ax = plt.subplots(figsize=(15, 7))
ax.plot(single_Kd_list)
ax.set_yscale('log')
ax.set_xlabel('HamDist=1 Seqs Sorted by $K_d$')
ax.set_ylabel('$K_d$ (nM)')
ax.set_title('HamDist=1 Sorted $K_d$\'s')

double_Kd_list = np.array([seq_Kds[seq]/1000.0 for seq in double_ham_seqs if seq in seq_Kds])
double_Kd_list.sort()

fig, ax = plt.subplots(figsize=(15, 7))
ax.plot(range(len(double_Kd_list)), double_Kd_list)
ax.set_yscale('log')
ax.set_xlabel('HamDist=2 Seqs Sorted by $K_d$')
ax.set_ylabel('$K_d$ (nM)')
ax.set_title('HamDist=2 Sorted $K_d$\'s')

color_given_base = dict(A='b', C='darkgoldenrod', G='g', T='r')

fig, ax = plt.subplots(figsize=(15, 5))

idxs = np.arange(len(target))
w = 0.5

for j, c in enumerate(bases):
    loc_ddGs = []
    loc_ddG_error = []
    ticks = []
    for i, t in enumerate(target):
        seq = target[:i] + c + target[i+1:]
        if seq in seq_ddGs:
            loc_ddGs.append(seq_ddGs[seq]/1000.0)
            loc_ddG_error.append(seq_ddG_error[seq]/1000.0)
            ticks.append(idxs[i])
        else:
            print i, c, target[i]
    ticks = np.array(ticks)
    ax.bar(ticks - w/2.0 + w*j/4.0, loc_ddGs,
           width=w/4.0, yerr=loc_ddG_error,
           color=color_given_base[c], error_kw=dict(ecolor='k', alpha=0.6), label=c)
ax.xaxis.grid(False)
ax.set_xlim((-0.5, len(target)-0.5))
ax.set_xticks(range(len(target)))
ax.set_xticklabels(target)

ylim = ax.get_ylim()
for i, c in enumerate(target):
    ax.fill_between([i-0.5, i+0.5], [ylim[0]]*2, [ylim[1]]*2, color=color_given_base[c], alpha=0.07)
ax.set_ylim(ylim)

fs = 16
ax.set_title('Single Mismatch $\Delta \Delta G$\'s', fontsize=fs)
ax.set_xlabel('Target {} Reference Sequence (Background Color)'.format(target_name), fontsize=fs)
ax.set_ylabel(r'$\Delta \Delta G \left(\frac{kJ}{mol} \right)$', fontsize=fs)
ax.legend(loc='best')
fig.savefig(os.path.join(custom_fig_dir, 'doped_ham1.png'))
print

