#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim :set ft=py:

""" Simple interface for persistence using the Bloscpack format.

It can store and retrieve a list of data buffers and metadata into a
file on disk.  The format tries to adhere to the Bloscpack ([1]_)
specification.  This is currently in-flux, so not recommended for
production purposes yet.

.. [1] https://github.com/esc/bloscpack

"""

from __future__ import division

import sys
import os.path as path
import struct
import argparse
import math
import zlib
import hashlib
import itertools
from collections import OrderedDict
import blosc
import numpy as np
import json


__version__ = '0.3.0-dev'
__author__ = [ 'Valentin Haenel <valentin.haenel@gmx.de>',
               'Francesc Alted <francesc@continuum.io>' ]

EXTENSION = '.blp'
MAGIC = 'blpk'
BLOSCPACK_HEADER_LENGTH = 32
BLOSC_HEADER_LENGTH = 16
FORMAT_VERSION = 2
MAX_FORMAT_VERSION = 255
MAX_CHUNKS = (2**63)-1
DEFAULT_CHUNK_SIZE = '1M'
DEFAULT_OFFSETS = True
DEFAULT_OPTIONS = None  # created programatically later on
DEFAULT_TYPESIZE = 8
DEFAULT_CLEVEL = 7
DEFAULT_SHUFFLE = True
BLOSC_ARGS = ['typesize', 'clevel', 'shuffle']
DEFAULT_BLOSC_ARGS = dict(zip(BLOSC_ARGS,
                (DEFAULT_TYPESIZE, DEFAULT_CLEVEL, DEFAULT_SHUFFLE)))
NORMAL  = 'NORMAL'
VERBOSE = 'VERBOSE'
DEBUG   = 'DEBUG'
LEVEL = NORMAL
VERBOSITY_LEVELS = [NORMAL, VERBOSE, DEBUG]
PREFIX = "bloscpack.py"
SUFFIXES = OrderedDict((
             ("B", 2**0 ),
             ("K", 2**10),
             ("M", 2**20),
             ("G", 2**30),
             ("T", 2**40)))

# create a list to persist with 1K buffers (1M elements in total)
LIST_TO_PERSIST = [np.ones(1024).tostring() for x in range(1024)]

# meta info sample to persist with the buffers above
# beware: only JSON compatible objects supported
META_TO_PERSIST = {'dtype': 'float64', 'shape': [1024], 'others': []}

class Hash(object):
    """ Uniform hash object.

    Parameters
    ----------
    name : str
        the name of the hash
    size : int
        the length of the digest in bytes
    function : callable
        the hash function implementation

    Notes
    -----
    The 'function' argument should return the raw bytes as string.

    """

    def __init__(self, name, size, function):
        self.name, self.size, self._function = name, size, function

    def __call__(self, data):
        return self._function(data)

def zlib_hash(func):
    """ Wrapper for zlib hashes. """
    def hash_(data):
        # The binary OR is recommended to obtain uniform hashes on all python
        # versions and platforms. The type with be 'uint32'.
        return struct.pack('<I', func(data) & 0xffffffff)
    return 4, hash_

def hashlib_hash(func):
    """ Wrapper for hashlib hashes. """
    def hash_(data):
        return func(data).digest()
    return func().digest_size, hash_

CHECKSUMS = [Hash('None', 0, lambda data: ''),
     Hash('adler32', *zlib_hash(zlib.adler32)),
     Hash('crc32', *zlib_hash(zlib.crc32)),
     Hash('md5', *hashlib_hash(hashlib.md5)),
     Hash('sha1', *hashlib_hash(hashlib.sha1)),
     Hash('sha224', *hashlib_hash(hashlib.sha224)),
     Hash('sha256', *hashlib_hash(hashlib.sha256)),
     Hash('sha384', *hashlib_hash(hashlib.sha384)),
     Hash('sha512', *hashlib_hash(hashlib.sha512)),
    ]
CHECKSUMS_AVAIL = [c.name for c in CHECKSUMS]
CHECKSUMS_LOOKUP = dict(((c.name, c) for c in CHECKSUMS))
DEFAULT_CHECKSUM = 'adler32'

def print_verbose(message, level=VERBOSE):
    """ Print message with desired verbosity level. """
    if level not in VERBOSITY_LEVELS:
        raise TypeError("Desired level '%s' is not one of %s" % (level,
            str(VERBOSITY_LEVELS)))
    if VERBOSITY_LEVELS.index(level) <= VERBOSITY_LEVELS.index(LEVEL):
        print('%s: %s' % (PREFIX, message))

def error(message, exit_code=1):
    """ Print message and exit with desired code. """
    for line in [l for l in message.split('\n') if l != '']:
        print('%s: error: %s' % (PREFIX, line))
    sys.exit(exit_code)

def pretty_size(size_in_bytes):
    """ Pretty print filesize.  """
    if size_in_bytes == 0:
        return "0B"
    for suf, lim in reversed(sorted(SUFFIXES.items(), key=lambda x: x[1])):
        if size_in_bytes < lim:
            continue
        else:
            return str(round(size_in_bytes/lim, 2))+suf

def double_pretty_size(size_in_bytes):
    """ Pretty print filesize including size in bytes. """
    return ("%s (%dB)" %(pretty_size(size_in_bytes), size_in_bytes))

def reverse_pretty(readable):
    """ Reverse pretty printed file size. """
    # otherwise we assume it has a suffix
    suffix = readable[-1]
    if suffix not in SUFFIXES.keys():
        raise ValueError(
                "'%s' is not a valid prefix multiplier, use one of: '%s'" %
                (suffix, SUFFIXES.keys()))
    else:
        return int(float(readable[:-1]) * SUFFIXES[suffix])

def decode_uint8(byte):
    return struct.unpack('<B', byte)[0]

def decode_uint32(fourbyte):
    return struct.unpack('<I', fourbyte)[0]

def decode_int32(fourbyte):
    return struct.unpack('<i', fourbyte)[0]

def decode_int64(eightbyte):
    return struct.unpack('<q', eightbyte)[0]

def decode_bitfield(byte):
    return bin(decode_uint8(byte))[2:].rjust(8,'0')

def encode_uint8(byte):
    return struct.pack('<B', byte)

def encode_int32(fourbyte):
    return struct.pack('<i', fourbyte)

def encode_int64(eightbyte):
    return struct.pack('<q', eightbyte)

class BloscPackCustomFormatter(argparse.HelpFormatter):
    """ Custom HelpFormatter.

    Basically a combination and extension of ArgumentDefaultsHelpFormatter and
    RawTextHelpFormatter. Adds default values to argument help, but only if the
    default is not in [None, True, False]. Also retains all whitespace as it
    is.

    """
    def _get_help_string(self, action):
        help_ = action.help
        if '%(default)' not in action.help \
                and action.default not in \
                [argparse.SUPPRESS, None, True, False]:
            defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
            if action.option_strings or action.nargs in defaulting_nargs:
                help_ += ' (default: %(default)s)'
        return help_

    def _split_lines(self, text, width):
        return text.splitlines()

def create_parser():
    """ Create and return the parser. """
    parser = argparse.ArgumentParser(
            #usage='%(prog)s [GLOBAL_OPTIONS] (compress | decompress)
            # [COMMAND_OPTIONS] <in_file> [<out_file>]',
            description='command line de/compression with blosc',
            formatter_class=BloscPackCustomFormatter)
    ## print version of bloscpack, python-blosc and blosc itself
    parser.add_argument('--version',
            action='version',
            version='%(prog)s:\t' + ("'%s'\n" % __version__) +
                    "python-blosc:\t'%s'\n"   % blosc.version.__version__ +
                    "blosc:\t\t'%s'\n"        % blosc.BLOSC_VERSION_STRING)
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument('-v', '--verbose',
            action='store_true',
            default=False,
            help='be verbose about actions')
    output_group.add_argument('-d', '--debug',
            action='store_true',
            default=False,
            help='print debugging output too')
    global_group = parser.add_argument_group(title='global options')
    global_group.add_argument('-f', '--force',
            action='store_true',
            default=False,
            help='disable overwrite checks for existing files\n' +
            '(use with caution)')
    class CheckThreadOption(argparse.Action):
        def __call__(self, parser, namespace, value, option_string=None):
            if not 1 <= value <= blosc.BLOSC_MAX_THREADS:
                error('%s must be 1 <= n <= %d'
                        % (option_string, blosc.BLOSC_MAX_THREADS))
            setattr(namespace, self.dest, value)
    global_group.add_argument('-n', '--nthreads',
            metavar='[1, %d]' % blosc.BLOSC_MAX_THREADS,
            action=CheckThreadOption,
            default=blosc.ncores,
            type=int,
            dest='nthreads',
            help='set number of threads, (default: %(default)s (ncores))')

    subparsers = parser.add_subparsers(title='subcommands',
            metavar='', dest='subcommand')

    compress_parser = subparsers.add_parser('compress',
            formatter_class=BloscPackCustomFormatter,
            help='perform compression on file')
    c_parser = subparsers.add_parser('c',
            formatter_class=BloscPackCustomFormatter,
            help="alias for 'compress'")

    for p in [compress_parser, c_parser]:
        blosc_group = p.add_argument_group(title='blosc settings')
        blosc_group.add_argument('-t', '--typesize',
                metavar='<size>',
                default=DEFAULT_TYPESIZE,
                type=int,
                help='typesize for blosc')
        blosc_group.add_argument('-l', '--clevel',
                default=DEFAULT_CLEVEL,
                choices=range(10),
                metavar='[0, 9]',
                type=int,
                help='compression level')
        blosc_group.add_argument('-s', '--no-shuffle',
                action='store_false',
                default=DEFAULT_SHUFFLE,
                dest='shuffle',
                help='deactivate shuffle')
        bloscpack_group = p.add_argument_group(title='bloscpack settings')
        def join_with_eol(items):
            return ', '.join(items) + '\n'
        checksum_format = join_with_eol(CHECKSUMS_AVAIL[0:3]) + \
                join_with_eol(CHECKSUMS_AVAIL[3:6]) + \
                join_with_eol(CHECKSUMS_AVAIL[6:])
        checksum_help = 'set desired checksum:\n' + checksum_format
        bloscpack_group.add_argument('-k', '--checksum',
                metavar='<checksum>',
                type=str,
                choices=CHECKSUMS_AVAIL,
                default=DEFAULT_CHECKSUM,
                dest='checksum',
                help=checksum_help)
        bloscpack_group.add_argument('-o', '--no-offsets',
                action='store_false',
                default=DEFAULT_OFFSETS,
                dest='offsets',
                help='deactivate offsets')
        p.add_argument('out_file',
                metavar='<out_file>',
                type=str,
                nargs='?',
                default=None,
                help='file to compress to')

    decompress_parser = subparsers.add_parser('decompress',
            formatter_class=BloscPackCustomFormatter,
            help='perform decompression on file')

    d_parser = subparsers.add_parser('d',
            formatter_class=BloscPackCustomFormatter,
            help="alias for 'decompress'")

    for p in [decompress_parser, d_parser]:
        p.add_argument('-e', '--no-check-extension',
                action='store_true',
                default=False,
                dest='no_check_extension',
                help='disable checking input file for extension (*.blp)\n' +
                '(requires use of <out_file>)')
        p.add_argument('in_file',
                metavar='<in_file>',
                type=str,
                default=None,
                help='file to be decompressed')

    return parser

def decode_blosc_header(buffer_):
    """ Read and decode header from compressed Blosc buffer.

    Parameters
    ----------
    buffer_ : string of bytes
        the compressed buffer

    Returns
    -------
    settings : dict
        a dict containing the settings from Blosc

    Notes
    -----

    The Blosc 1.x header is 16 bytes as follows::

        |-0-|-1-|-2-|-3-|-4-|-5-|-6-|-7-|-8-|-9-|-A-|-B-|-C-|-D-|-E-|-F-|
        ^   ^   ^   ^ |     nbytes    |   blocksize   |    ctbytes    |
        |   |   |   |
        |   |   |   +--typesize
        |   |   +------flags
        |   +----------versionlz
        +--------------version

    The first four are simply bytes, the last three are are each unsigned ints
    (uint32) each occupying 4 bytes. The header is always little-endian.
    'ctbytes' is the length of the buffer including header and nbytes is the
    length of the data when uncompressed.

    """
    return {'version':   decode_uint8(buffer_[0]),
            'versionlz': decode_uint8(buffer_[1]),
            'flags':     decode_uint8(buffer_[2]),
            'typesize':  decode_uint8(buffer_[3]),
            'nbytes':    decode_uint32(buffer_[4:8]),
            'blocksize': decode_uint32(buffer_[8:12]),
            'ctbytes':   decode_uint32(buffer_[12:16])}

class ChunkingException(BaseException):
    pass

class NoSuchChecksum(ValueError):
    pass

class ChecksumMismatch(RuntimeError):
    pass

class FileNotFound(IOError):
    pass

def check_range(name, value, min_, max_):
    """ Check that a variable is in range. """
    if not isinstance(value, (int, long)):
        raise TypeError("'%s' must be of type 'int'" % name)
    elif not min_ <= value <= max_:
        raise ValueError(
                "'%s' must be in the range %s <= n <= %s, not '%s'" %
                tuple(map(str, (name, min, max_, value))))

def _check_options(options):
    """ Check the options bitfield.

    Parameters
    ----------
    options : str

    Raises
    ------
    TypeError
        if options is not a string
    ValueError
        either if any character in option is not a zero or a one, or if options
        is not of length 8
    """

    if not isinstance(options, str):
        raise TypeError("'options' must be of type 'str', not '%s'" %
                type(options))
    elif (not len(options) == 8 or
            not all(map(lambda x: x in ['0', '1'], iter(options)))):
        raise ValueError(
                "'options' must be string of 0s and 1s of length 8, not '%s'" %
                options)

def create_options(offsets=DEFAULT_OFFSETS):
    """ Create the options bitfield.

    Parameters
    ----------
    offsets : bool
    """
    return "".join([str(int(i)) for i in
        [False, False, False, False, False, False, False, offsets]])

def decode_options(options):
    """ Parse the options bitfield.

    Parameters
    ----------
    options : str
        the options bitfield

    Returns
    -------
    options : dict mapping str -> bool
    """

    _check_options(options)
    return {'offsets': bool(int(options[7]))}

# default options created here programatically
DEFAULT_OPTIONS = create_options()


def create_bloscpack_header(format_version=FORMAT_VERSION,
        options='00000000',
        checksum=0,
        typesize=0,
        chunk_size=-1,
        last_chunk=-1,
        nchunks=-1):
    """ Create the bloscpack header string.

    Parameters
    ----------
    format_version : int
        the version format for the compressed file
    options : bitfield (string of 0s and 1s)
        the options for this file
    checksum : int
        the checksum to be used
    typesize : int
        the typesize used for blosc in the chunks
    chunk_size : int
        the size of a regular chunk
    last_chunk : int
        the size of the last chunk
    nchunks : int
        the number of chunks

    Returns
    -------
    bloscpack_header : string
        the header as string

    Notes
    -----

    See the file 'header_rfc.rst' distributed with the source code for
    details on the header format.

    Raises
    ------
    ValueError
        if any of the arguments have an invalid value
    TypeError
        if any of the arguments have the wrong type

    """
    check_range('format_version', format_version, 0, MAX_FORMAT_VERSION)
    _check_options(options)
    check_range('checksum',   checksum, 0, len(CHECKSUMS))
    check_range('typesize',   typesize,    0, blosc.BLOSC_MAX_TYPESIZE)
    check_range('chunk_size', chunk_size, -1, blosc.BLOSC_MAX_BUFFERSIZE)
    check_range('last_chunk', last_chunk, -1, blosc.BLOSC_MAX_BUFFERSIZE)
    check_range('nchunks',    nchunks,    -1, MAX_CHUNKS)

    format_version = encode_uint8(format_version)
    options = encode_uint8(int(options, 2))
    checksum = encode_uint8(checksum)
    typesize = encode_uint8(typesize)
    chunk_size = encode_int32(chunk_size)
    last_chunk = encode_int32(last_chunk)
    nchunks = encode_int64(nchunks)
    RESERVED = encode_int64(0)

    return (MAGIC + format_version + options + checksum + typesize +
            chunk_size + last_chunk +
            nchunks +
            RESERVED)

def decode_bloscpack_header(buffer_):
    """ Check that the magic marker exists and return number of chunks.

    Parameters
    ----------
    buffer_ : str of length 32 (but probably any sequence would work)
        the header

    Returns
    -------
    format_version : int
        the version format for the compressed file
    options : bitfield (string of 0s and 1s)
        the options for this file
    checksum : int
        the checksum to be used
    typesize : int
        the typesize used for blosc in the chunks
    chunk_size : int
        the size of a regular chunk
    last_chunk : int
        the size of the last chunk
    nchunks : int
        the number of chunks
    RESERVED : int
        the RESERVED field from the header, should be zero

    """
    if len(buffer_) != 32:
        raise ValueError(
            "attempting to decode a bloscpack header of length '%d', not '32'"
            % len(buffer_))
    elif buffer_[0:4] != MAGIC:
        raise ValueError(
            "the magic marker '%s' is missing from the bloscpack " % MAGIC +
            "header, instead we found: '%s'" % buffer_[0:4])

    return {'format_version': decode_uint8(buffer_[4]),
            'options':        decode_bitfield(buffer_[5]),
            'checksum':       decode_uint8(buffer_[6]),
            'typesize':       decode_uint8(buffer_[7]),
            'chunk_size':     decode_int32(buffer_[8:12]),
            'last_chunk':     decode_int32(buffer_[12:16]),
            'nchunks':        decode_int64(buffer_[16:24]),
            'RESERVED':       decode_int64(buffer_[24:32]),
            }

def process_compression_args(args):
    """ Extract and check the compression args after parsing by argparse.

    Parameters
    ----------
    args : argparse.Namespace
        the parsed command line arguments

    Returns
    -------
    out_file : str
        the out_file name
    blosc_args : tuple of (int, int, bool)
        typesize, clevel and shuffle
    """
    out_file = args.out_file
    if out_file is None:
        raise ValueError("you need to pass an out_file!")
    # check the extension for out file
    if not out_file.endswith(EXTENSION):
        out_file += EXTENSION
    blosc_args = dict((arg, args.__getattribute__(arg)) for arg in BLOSC_ARGS)
    return out_file, blosc_args

def process_decompression_args(args):
    """ Extract and check the decompression args after parsing by argparse.

    Warning: may call sys.exit()

    Parameters
    ----------
    args : argparse.Namespace
        the parsed command line arguments

    Returns
    -------
    in_file : str
        the input file name
    """
    in_file = args.in_file
    # check the extension for input file
    if not in_file.endswith(EXTENSION):
         error("input file '%s' does not end with '%s'" %
               (in_file, EXTENSION))
    return in_file

def check_files(in_file, out_file, args):
    """ Check files exist/don't exist.

    Parameters
    ----------
    in_file : str:
        the input file
    out_file : str
        the output file
    args : parser args
        any additional arguments from the parser

    Raises
    ------
    FileNotFound
        in case any of the files isn't found.

    """
    if in_file is not None and not path.exists(in_file):
        raise FileNotFound("input file '%s' does not exist!" % in_file)
    if out_file is not None and path.exists(out_file):
        if not args.force:
            raise FileNotFound("output file '%s' exists!" % out_file)
        else:
            print_verbose("overwriting existing file: %s" % out_file)
    print_verbose('input file is: %s' % in_file)
    print_verbose('output file is: %s' % out_file)

def process_nthread_arg(args):
    """ Extract and set nthreads. """
    if args.nthreads != blosc.ncores:
        blosc.set_nthreads(args.nthreads)
    print_verbose('using %d thread%s' %
            (args.nthreads, 's' if args.nthreads > 1 else ''))

def pack_list(in_list, meta_info, out_file, blosc_args,
              offsets=DEFAULT_OFFSETS, checksum=DEFAULT_CHECKSUM):
    """ Main function for compressing a list of buffers.

    Parameters
    ----------
    in_list : list
        the list of buffers
    meta_info : dict
        dictionary with the associated metainfo
    out_file : str
        the name of the output file
    blosc_args : dict
        dictionary of blosc keyword args
    offsets : bool
        Wheather to include offsets.
    checksum : str
        Which checksum to use.

    """
    # XXX Check for empty lists
    # calculate chunk sizes
    nchunks = len(in_list)
    chunk_size = len(in_list[0])
    last_chunk_size = len(in_list[-1])
    in_list_size = nchunks * chunk_size + last_chunk_size
    print_verbose('input file size: %s' % double_pretty_size(in_list_size))
    # calculate header
    options = create_options(offsets=offsets)
    if offsets:
        offsets_storage = list(itertools.repeat(0, nchunks))
    # set the checksum impl
    checksum_impl = CHECKSUMS_LOOKUP[checksum]
    raw_bloscpack_header = create_bloscpack_header(
        options=options,
        checksum=CHECKSUMS_AVAIL.index(checksum),
        typesize=blosc_args['typesize'],
        chunk_size=chunk_size,
        last_chunk=last_chunk_size,
        nchunks=nchunks
        )
    print_verbose('raw_bloscpack_header: %s' % repr(raw_bloscpack_header),
                  level=DEBUG)
    # write the chunks to the file
    with open(out_file, 'wb') as output_fp:
        output_fp.write(raw_bloscpack_header)
        # preallocate space for the offsets
        if offsets:
            output_fp.write(encode_int64(-1) * nchunks)
        # if nchunks == 1 the last_chunk_size is the size of the single chunk
        for i in xrange(nchunks):
            # store the current position in the file
            if offsets:
                offsets_storage[i] = output_fp.tell()
            current_chunk = in_list[i]
            # do compression
            compressed = blosc.compress(current_chunk, **blosc_args)
            # write compressed data
            output_fp.write(compressed)
            print_verbose("chunk '%d'%s written, in: %s out: %s ratio: %s" %
                    (i, ' (last)' if i == nchunks - 1 else '',
                    double_pretty_size(len(current_chunk)),
                    double_pretty_size(len(compressed)),
                    "%0.3f" % (len(compressed) / len(current_chunk))
                    if len(current_chunk) != 0 else "N/A"),
                    level=DEBUG)
            tail_mess = ""
            if checksum_impl.size > 0:
                # compute the checksum on the compressed data
                digest = checksum_impl(compressed)
                # write digest
                output_fp.write(digest)
                tail_mess += ('checksum (%s): %s ' % (checksum, repr(digest)))
            if offsets:
                tail_mess += ("offset: '%d'" % offsets_storage[i])
            if len(tail_mess) > 0:
                print_verbose(tail_mess, level=DEBUG)
        if offsets:
            # seek to 32 bits into the file
            output_fp.seek(BLOSCPACK_HEADER_LENGTH, 0)
            print_verbose("Writing '%d' offsets: '%s'" %
                    (len(offsets_storage), repr(offsets_storage)), level=DEBUG)
            # write the offsets encoded into the reserved space in the file
            encoded_offsets = "".join([encode_int64(i) for i in offsets_storage])
            print_verbose("Raw offsets: %s" % repr(encoded_offsets),
                    level=DEBUG)
            output_fp.write(encoded_offsets)
        # write the metadata at the end
        output_fp.seek(0, 2)
        json.dump(meta_info, output_fp)
    out_file_size = path.getsize(out_file)
    print_verbose('output file size: %s' % double_pretty_size(out_file_size))
    print_verbose('compression ratio: %f' % (out_file_size/in_list_size))

def unpack_file(in_file):
    """ Main function for decompressing a file.  Returns a list of buffers.

    Parameters
    ----------
    in_file : str
        the name of the input file
    """
    out_list = []
    in_file_size = path.getsize(in_file)
    print_verbose('input file size: %s' % pretty_size(in_file_size))
    with open(in_file, 'rb') as input_fp:
        # read the bloscpack header
        print_verbose('reading bloscpack header', level=DEBUG)
        bloscpack_header_raw = input_fp.read(BLOSCPACK_HEADER_LENGTH)
        print_verbose('bloscpack_header_raw: %s' %
                repr(bloscpack_header_raw), level=DEBUG)
        bloscpack_header = decode_bloscpack_header(bloscpack_header_raw)
        for arg, value in bloscpack_header.iteritems():
            # hack the values of the bloscpack header into the namespace
            globals()[arg] = value
            print_verbose('\t%s: %s' % (arg, value), level=DEBUG)
        checksum_impl = CHECKSUMS[checksum]
        if FORMAT_VERSION != format_version:
            error("format version of file was not '%s' as expected, but '%d'" %
                    (FORMAT_VERSION, format_version))
        # read the offsets
        options = decode_options(bloscpack_header['options'])
        if options['offsets']:
            offsets_raw = input_fp.read(8 * nchunks)
            print_verbose('Read raw offsets: %s' % repr(offsets_raw),
                    level=DEBUG)
            offset_storage = [decode_int64(offsets_raw[j-8:j]) for j in
                    xrange(8, nchunks*8+1, 8)]
            print_verbose('Offsets: %s' % offset_storage, level=DEBUG)
        # decompress
        for i in range(nchunks):
            print_verbose("decompressing chunk '%d'%s" %
                    (i, ' (last)' if i == nchunks-1 else ''), level=DEBUG)
            # read blosc header
            blosc_header_raw = input_fp.read(BLOSC_HEADER_LENGTH)
            blosc_header = decode_blosc_header(blosc_header_raw)
            print_verbose('blosc_header: %s' % repr(blosc_header), level=DEBUG)
            ctbytes = blosc_header['ctbytes']
            # Seek back BLOSC_HEADER_LENGTH bytes in file relative to current
            # position. Blosc needs the header too and presumably this is
            # better than to read the whole buffer and then concatenate it...
            input_fp.seek(-BLOSC_HEADER_LENGTH, 1)
            # read chunk
            compressed = input_fp.read(ctbytes)
            if checksum_impl.size > 0:
                # do checksum
                expected_digest = input_fp.read(checksum_impl.size)
                received_digest = checksum_impl(compressed)
                if received_digest != expected_digest:
                    raise ChecksumMismatch(
                            "Checksum mismatch detected in chunk '%d' " % i +
                            "expected: '%s', received: '%s'" %
                            (repr(expected_digest), repr(received_digest)))
                else:
                    print_verbose('checksum OK (%s): %s ' %
                            (checksum_impl.name, repr(received_digest)),
                            level=DEBUG)
            # if checksum OK, decompress buffer
            decompressed = blosc.decompress(compressed)
            # write decompressed chunk
            out_list.append(decompressed)
            print_verbose("chunk append, in: %s out: %s" %
                          (pretty_size(len(compressed)),
                           pretty_size(len(decompressed))), level=DEBUG)
        # we are at the end of the data area. read the metadata appendix.
        meta_info = json.load(input_fp)
    out_list_size = sum(len(b) for b in out_list)
    print_verbose('output file size: %s' % pretty_size(out_list_size))
    print_verbose('decompression ratio: %f' % (out_list_size/in_file_size))
    return out_list, meta_info

if __name__ == '__main__':
    parser = create_parser()
    PREFIX = parser.prog
    args = parser.parse_args()
    if args.verbose:
        LEVEL = VERBOSE
    elif args.debug:
        LEVEL = DEBUG
    print_verbose('command line argument parsing complete', level=DEBUG)
    print_verbose('command line arguments are: ', level=DEBUG)
    for arg, val in vars(args).iteritems():
        if arg == 'chunk_size' and val is not None:
            print_verbose('\t%s: %s' % (arg, double_pretty_size(val)),
                    level=DEBUG)
        else:
            print_verbose('\t%s: %s' % (arg, str(val)), level=DEBUG)

    # compression and decompression handled via subparsers
    if args.subcommand in ['compress', 'c']:
        print_verbose('getting ready for compression')
        out_file, blosc_args = process_compression_args(args)
        print_verbose('blosc args are:', level=DEBUG)
        for arg, value in blosc_args.iteritems():
            print_verbose('\t%s: %s' % (arg, value), level=DEBUG)
        try:
            check_files(None, out_file, args)
        except FileNotFound as fnf:
            error(str(fnf))
        process_nthread_arg(args)
        try:
            pack_list(LIST_TO_PERSIST, META_TO_PERSIST, out_file, blosc_args,
                      offsets=args.offsets, checksum=args.checksum)
        except ChunkingException as e:
            error(e.message)
    elif args.subcommand in ['decompress', 'd']:
        print_verbose('getting ready for decompression')
        in_file = process_decompression_args(args)
        try:
            check_files(in_file, None, args)
        except FileNotFound as fnf:
            error(str(fnf))
        process_nthread_arg(args)
        try:
            out_list, meta_info = unpack_file(in_file)
        except ValueError as ve:
            error(ve.message)
        # Compare out buffers against the originals
        for b1,b2 in zip(LIST_TO_PERSIST, out_list):
            if b1 != b2:
                raise ValueError("Values '%s' and '%s' are not equal" %
                                 (b1, b2))
        # Compare out metadata against the original
        for key in META_TO_PERSIST.iterkeys():
            m1, m2 = META_TO_PERSIST[key], meta_info[key]
            if m1 != m2:
                raise ValueError("Values '%s' and '%s' are not equal" %
                                 (m1, m2))
        print_verbose("metadata is correct: %s" % meta_info)
    else:
        # we should never reach this
        error('You found the easter-egg, please contact the author')
    print_verbose('done')
