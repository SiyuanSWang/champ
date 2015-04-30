"""
A space to create commonly used functions and classes for image processing.
"""
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
from scipy.signal import convolve2d
from multiprocessing import Pool
import imreg
import local_config


def signal_hist_and_func(pyplot_hist, plot_title='', plot_curves=True):
    """Determines empirical background noise curve and returns (good signal)/(all signal)
    interpolation function."""

    hy, bin_edges, _ = pyplot_hist
    hx = (bin_edges[:-1] + bin_edges[1:])/2

    mode_y = max(hy[:-1])
    mode_ind = list(hy).index(mode_y)

    gy = np.zeros(hx.shape)
    gy[:mode_ind+1] = hy[:mode_ind+1]
    gy[mode_ind+1 : 2*mode_ind+1] = hy[mode_ind-1::-1]

    sig_y = hy - gy
    sig_y[sig_y < 0] = 0

    ratio = sig_y / hy

    last_zero_ind = np.where(ratio == 0)[0][-1]
    first_one_ind = np.where(ratio >= 1)[0][0]
    ratio[:last_zero_ind] = 0.0
    ratio[first_one_ind:] = 1.0
    l_bnd = hx[last_zero_ind]
    u_bnd = hx[first_one_ind]
    print 'Non-trivial cdf range: %f - %f' % (l_bnd, u_bnd)

    delta_x = np.mean(hx[1:]-hx[:-1])
    print 'delta_x:', delta_x

    num_ext_points = 10
    extended_x = np.r_[[0], hx, 1.1*hx[-1]]
    extended_ratio = np.r_[[0], ratio, [1]]

    ratio_f_interp = interp1d(extended_x, extended_ratio, kind='cubic')

    if plot_curves:
        fig = plt.figure(figsize=(10,10))
        plt.plot(hx, hy, label='Data')
        plt.plot(hx, gy, label='Noise')
        plt.plot(hx, sig_y, label='Signal')
        plt.plot(hx, ratio, label='Ratio')
        plt.plot(extended_x, ratio_f_interp(extended_x), label='Ratio Interp', linewidth=3)
        plt.legend()
        if plot_title:
            plt.title(plot_title)

    return ratio_f_interp


def next_power_of_2(x):
    return 1<<(int(np.ceil(x))-1).bit_length()


def max_2d_idx(a):
    return np.unravel_index(a.argmax(), a.shape)


def pad_to_size(M, size):
    assert len(size) == 2, 'Row and column sizes needed.'
    left_to_pad = size - np.array(M.shape) 
    return np.pad(M, ((0, left_to_pad[0]), (0, left_to_pad[1])), mode='constant')


class FastqTileXYs(object):
    def __init__(self, key, tile):
        self.key = key
        self.xys = tile

    def set_fastq_image_data(self, offset, scale, scaled_dims, force=False, verbose=True):
        self.offset = offset
        self.scale = scale
        self.image_shape = scaled_dims
        self.mapped_xys = scale * (self.xys + np.tile(offset, (self.xys.shape[0], 1)))

    def image(self):
        image = np.zeros(self.image_shape)
        image[self.mapped_xys.astype(np.int)[:,0], self.mapped_xys.astype(np.int)[:,1]] += 1
        image[image > 1] = 1
        return image

    def imreg_align_with_im(self, im):
        fq_image = self.image()
        edge_len = next_power_of_2(np.r_[fq_image.shape, im.shape].max())
        sq_fq_im = pad_to_size(fq_image, (edge_len, edge_len))

        self.max_score = float('-inf')
        for flip in [False, True]:
            if flip:
                im = np.fliplr(im)
            sq_im = pad_to_size(im, (edge_len, edge_len))
            fq_match_im, scale, rot, tr = imreg.similarity(sq_im, sq_fq_im)
            score = (sq_im * fq_match_im).sum()

            if score > self.max_score:
                self.max_score = score
                self.best_match_im = fq_match_im
                self.align_scale = scale
                self.align_rot = rot
                self.align_tr = tr
        print self.key, score, scale, rot, tr

    def fft_align_with_im(self, image_data, verbose=True):
        im_data_im_shapes = set(a.shape for a in image_data.all_ffts.values())
        assert len(im_data_im_shapes) <= 2, im_data_im_shapes

        # Make the ffts
        if verbose:
            print 'Making ffts for', self.key
        fq_image = self.image()
        fq_im_fft_given_shape = {}
        for shape in im_data_im_shapes:
            padded_fq_im = pad_to_size(fq_image, shape)
            fq_im_fft_given_shape[shape] = np.fft.fft2(padded_fq_im)

        # Align
        self.best_max_corr = float('-inf')
        for im_key, im_data_fft in image_data.all_ffts.items():
            fq_im_fft = fq_im_fft_given_shape[im_data_fft.shape]
            cross_corr = abs(np.fft.ifft2(np.conj(fq_im_fft) * im_data_fft))
            max_corr = cross_corr.max()
            max_idx = max_2d_idx(cross_corr)

            if max_corr > self.best_max_corr:
                self.best_im_key = im_key
                self.best_max_corr = max_corr
                self.align_tr = np.array(max_idx) - fq_image.shape
        if verbose:
            print 'Result:', self.key, self.best_im_key, self.best_max_corr, self.align_tr

class ImageData(object):
    def __init__(self, im, objective):
        assert isinstance(im, np.ndarray), 'Image must be numpy ndarray'
        assert objective in set([40, 60]), 'Accepted objectives are 40 and 60'

        self.im = im
        self.objective = objective
        self.um_per_pixel = 16.0 / self.objective
        self.um_dims = self.um_per_pixel * np.array(self.im.shape)

    def D4_ffts(self, padding=(0, 0), force=False, verbose=True):
        """Makes images and ffts of all flips and 90 degree rotations (i.e. the 4th dihedral
        symmetry group."""
        if hasattr(self, 'all_ffts') and self.all_ffts and not force:
            return
        self.all_ffts = {}
        for flip in [True, False]:
            if flip:
                flip_im = np.fliplr(self.im)
            else:
                flip_im = self.im
            for rot in [0, 90, 180, 270]:
                idx = (flip, rot)
                if verbose:
                    print idx
                rot_im = np.rot90(flip_im, k=(rot%90))

                totalx, totaly = np.array(padding)+np.array(rot_im.shape)
                w = next_power_of_2(totalx)
                h = next_power_of_2(totaly)
                padded_im = np.pad(rot_im,
                                   ((padding[0], w-totalx), (padding[1], h-totaly)),
                                   mode='constant')

                self.all_ffts[idx] = np.fft.fft2(padded_im)


class FastqImageCorrelator(object):
    def __init__(self, project_name):
        self.project_name = project_name
        self.fastq_tiles = {}
        self.image_data = None
        self.w_fq_tile = 900  # um

    def load_phiX(self):
        for key, tile in local_config.phiX_xys_given_project_name(self.project_name).items():
            self.fastq_tiles[key] = FastqTileXYs(key, tile)

    def set_image_data(self, im):
        assert isinstance(im, ImageData), 'Object passed to set_image_data must be ImageData object.'
        self.image_data = im

    def set_image_data_from_ndarray(self, im, objective):
        self.image_data = ImageData(im, objective)

    def load_image_data_from_fpath(self, fpath):
        self.data_im = ImageData(np.load(fpath))

    def set_fastq_tile_mappings(self):
        """Before converting to images, we offset to the origin and scale to approximately match the
        image size."""
        assert self.image_data is not None, 'No image data loaded.'
        assert self.fastq_tiles != {}, 'No fastq data loaded.'

        self.all_data = np.concatenate([tile.xys for key, tile in self.fastq_tiles.items()])
    
        x_min, y_min = self.all_data.min(axis=0)
        x_max, y_max = self.all_data.max(axis=0)
    
        self.fq_im_offset = np.array([-x_min, -y_min])
        self.fq_im_scale = (float(self.w_fq_tile) / (x_max-x_min)) / self.image_data.um_per_pixel
        self.fq_im_scaled_maxes = self.fq_im_scale * np.array([x_max-x_min, y_max-y_min])
        self.fq_im_scaled_dims = (self.fq_im_scaled_maxes + [1, 1]).astype(np.int)

    def set_all_fastq_image_data(self, verbose=True):
        for key, tile in self.fastq_tiles.items():
            tile.set_fastq_image_data(self.fq_im_offset,
                                      self.fq_im_scale,
                                      self.fq_im_scaled_dims,
                                      verbose=verbose)

    def imreg_align(self):
        for key, tile in sorted(self.fastq_tiles.items()):
            tile.imreg_align_with_im(self.image_data.im)

    def fft_align(self, verbose=True):
        print 'Image D4 ffts'
        self.image_data.D4_ffts(padding=self.fq_im_scaled_dims, verbose=verbose)
        print 'Fastq images and ffts'
        self.set_all_fastq_image_data(verbose=True)
        print 'Aligning'
        for key, tile in sorted(self.fastq_tiles.items()):
            tile.fft_align_with_im(self.image_data, verbose=verbose)
