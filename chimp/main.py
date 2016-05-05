"""
Chip-Hybridized Interaction Mapping Platform

Usage:
  chimp convert HDF5_FILE_PATH TIF_FILE_PATHS ... [--flipud] [--fliplr] [-v | -vv | -vvv]
  chimp preprocess [-v | -vv | -vvv ]
  chimp map FASTQ_DIRECTORY PATHS_TO_BAMFILES ... [-v | -vv | -vvv]
  chimp align PROJECT_NAME ALIGNMENT_CHANNEL [--min-hits] [--snr-threshold] [-v | -vv | -vvv]

Options:
  -h --help     Show this screen.
  --version     Show version.

Commands:
  convert       creates an HDF5-formatted file from OME-TIFF files
  map           maps all the reads in the fastq files, typically for separating phiX
  preprocess    defines where points are in the microscope image data
  align         maps reads from the high-throughput sequencer to fluorescent
                points in microscope image data

"""
from chimp.controller import align, preprocess, mapreads, convert
from docopt import docopt
import logging
from chimp.config import CommandLineArguments
from chimp.constants import VERSION
import os


def main(**kwargs):
    arguments = CommandLineArguments(docopt(__doc__, version=VERSION), os.getcwd())

    log = logging.getLogger()
    log.addHandler(logging.StreamHandler())
    log.setLevel(arguments.log_level)

    # make some space to distinguish log messages from command prompt
    for _ in range(2):
        log.info('')

    commands = {'align': align,
                'preprocess': preprocess,
                'map': mapreads,
                'convert': convert
                }
    commands[arguments.command].main(arguments)


if __name__ == '__main__':
    main()