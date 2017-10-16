import ctypes
import functools
import io
import math
import queue



########################################################################################################################
####################################################   EXCEPTIONS   ####################################################
########################################################################################################################

class Ext4Error (Exception):
    """
    Base class for all custom errors
    """
    pass

class BlockMapError (Ext4Error):
    """
    Raised, when a requested file_block is not mapped to disk
    """
    pass

class EndOfStreamError (Ext4Error):
    """
    Raised, when BlockReader reads beyond the end of the volume's underlying stream
    """
    pass

class MagicError (Ext4Error):
    """
    Raised, when a structures magic value is wrong and ignore_magic is False
    """
    pass



########################################################################################################################
####################################################   LOW LEVEL    ####################################################
########################################################################################################################

class ext4_struct (ctypes.LittleEndianStructure):
    """
    Simplifies access to *_lo and *_hi fields
    """
    def __getattr__ (self, name):
        """
        Enables reading *_lo and *_hi fields together.
        """
        try:
            # Combining *_lo and *_hi fields
            lo_field = ctypes.LittleEndianStructure.__getattribute__(type(self), name + "_lo")
            size = lo_field.size

            lo = lo_field.__get__(self)
            hi = ctypes.LittleEndianStructure.__getattribute__(self, name + "_hi")

            return (hi << (8 * size)) | lo
        except AttributeError:
            return ctypes.LittleEndianStructure.__getattribute__(self, name)

    def __setattr__ (self, name, value):
        """
        Enables setting *_lo and *_hi fields together.
        """
        try:
            # Combining *_lo and *_hi fields
            lo_field = lo_field = ctypes.LittleEndianStructure.__getattribute__(type(self), name + "_lo")
            size = lo_field.size

            lo_field.__set__(self, value & ((1 << (8 * size)) - 1))
            ctypes.LittleEndianStructure.__setattr__(self, name + "_hi", value >> (8 * size))
        except AttributeError:
            ctypes.LittleEndianStructure.__setattr__(self, name, value)



class ext4_extent (ext4_struct):
    _fields_ = [
        ("ee_block", ctypes.c_uint),      # 0x0000
        ("ee_len", ctypes.c_ushort),      # 0x0004
        ("ee_start_hi", ctypes.c_ushort), # 0x0006
        ("ee_start_lo", ctypes.c_uint)    # 0x0008
    ]



class ext4_extent_header (ext4_struct):
    _fields_ = [
        ("eh_magic", ctypes.c_ushort),   # 0x0000, Must be 0xF30A
        ("eh_entries", ctypes.c_ushort), # 0x0002
        ("eh_max", ctypes.c_ushort),     # 0x0004
        ("eh_depth", ctypes.c_ushort),   # 0x0006
        ("eh_generation", ctypes.c_uint) # 0x0008
    ]



class ext4_extent_idx (ext4_struct):
    _fields_ = [
        ("ei_block", ctypes.c_uint),     # 0x0000
        ("ei_leaf_lo", ctypes.c_uint),   # 0x0004
        ("ei_leaf_hi", ctypes.c_ushort), # 0x0008
        ("ei_unused", ctypes.c_ushort)   # 0x000A
    ]



class ext4_group_descriptor (ext4_struct):
    _fields_ = [
        ("bg_block_bitmap_lo", ctypes.c_uint),        # 0x0000
        ("bg_inode_bitmap_lo", ctypes.c_uint),        # 0x0004
        ("bg_inode_table_lo", ctypes.c_uint),         # 0x0008
        ("bg_free_blocks_count_lo", ctypes.c_ushort), # 0x000C
        ("bg_free_inodes_count_lo", ctypes.c_ushort), # 0x000E
        ("bg_used_dirs_count_lo", ctypes.c_ushort),   # 0x0010
        ("bg_flags", ctypes.c_ushort),                # 0x0012
        ("bg_exclude_bitmap_lo", ctypes.c_uint),      # 0x0014
        ("bg_block_bitmap_csum_lo", ctypes.c_ushort), # 0x0018
        ("bg_inode_bitmap_csum_lo", ctypes.c_ushort), # 0x001A
        ("bg_itable_unused_lo", ctypes.c_ushort),     # 0x001C
        ("bg_checksum", ctypes.c_ushort),             # 0x001E

        # 64-bit fields
        ("bg_block_bitmap_hi", ctypes.c_uint),        # 0x0020
        ("bg_inode_bitmap_hi", ctypes.c_uint),        # 0x0024
        ("bg_inode_table_hi", ctypes.c_uint),         # 0x0028
        ("bg_free_blocks_count_hi", ctypes.c_ushort), # 0x002C
        ("bg_free_inodes_count_hi", ctypes.c_ushort), # 0x002E
        ("bg_used_dirs_count_hi", ctypes.c_ushort),   # 0x0030
        ("bg_itable_unused_hi", ctypes.c_ushort),     # 0x0032
        ("bg_exclude_bitmap_hi", ctypes.c_uint),      # 0x0034
        ("bg_block_bitmap_csum_hi", ctypes.c_ushort), # 0x0038
        ("bg_inode_bitmap_csum_hi", ctypes.c_ushort), # 0x003A
        ("bg_reserved", ctypes.c_uint),               # 0x003C
    ]



class ext4_inode (ext4_struct):
    # i_mode
    S_IXOTH  =    0x1 # Others can execute
    S_IWOTH  =    0x2 # Others can write
    S_IROTH  =    0x4 # Others can read
    S_IXGRP  =    0x8 # Group can execute
    S_IWGRP  =   0x10 # Group can write
    S_IRGRP  =   0x20 # Group can read
    S_IXUSR  =   0x40 # Owner can execute
    S_IWUSR  =   0x80 # Owner can write
    S_IRUSR  =  0x100 # Owner can read
    S_ISVTX  =  0x200 # Sticky bit (only owner can delete)
    S_ISGID  =  0x400 # Set GID (execute with privileges of group owner of the file's group)
    S_ISUID  =  0x800 # Set UID (execute with privileges of the file's owner)
    S_IFIFO  = 0x1000 # FIFO device (named pipe)
    S_IFCHR  = 0x2000 # Character device (raw, unbuffered, aligned, direct access to hardware storage)
    S_IFDIR  = 0x4000 # Directory
    S_IFBLK  = 0x6000 # Block device (buffered, arbitrary access to storage)
    S_IFREG  = 0x8000 # Regular file
    S_IFLNK  = 0xA000 # Symbolic link
    S_IFSOCK = 0xC000 # Socket

    # i_flags
    EXT4_INDEX_FL       =     0x1000 # Uses hash trees
    EXT4_EXTENTS_FL     =    0x80000 # Uses extents
    EXT4_INLINE_DATA_FL = 0x10000000 # Has inline data

    _fields_ = [
        ("i_mode", ctypes.c_ushort),        # 0x0000
        ("i_uid", ctypes.c_ushort),         # 0x0002
        ("i_size_lo", ctypes.c_uint),       # 0x0004
        ("i_atime", ctypes.c_uint),         # 0x0008
        ("i_ctime", ctypes.c_uint),         # 0x000C
        ("i_mtime", ctypes.c_uint),         # 0x0010
        ("i_dtime", ctypes.c_uint),         # 0x0014
        ("i_gid", ctypes.c_ushort),         # 0x0018
        ("i_links_count", ctypes.c_ushort), # 0x001A
        ("i_blocks_lo", ctypes.c_uint),     # 0x001C
        ("i_flags", ctypes.c_uint),         # 0x0020
        ("osd1", ctypes.c_uint),            # 0x0024
        ("i_block", ctypes.c_uint * 15),    # 0x0028
        ("i_generation", ctypes.c_uint),    # 0x0064
        ("i_file_acl_lo", ctypes.c_uint),   # 0x0068
        ("i_size_hi", ctypes.c_uint),       # 0x006C, Originally named i_size_high
        ("i_obso_faddr", ctypes.c_uint),    # 0x0070
        ("osd2", ctypes.c_byte * 12),       # 0x0074
        ("i_extra_isize", ctypes.c_ushort), # 0x0080
        ("i_checksum_hi", ctypes.c_ushort), # 0x0082
        ("i_ctime_extra", ctypes.c_uint),   # 0x0084
        ("i_mtime_extra", ctypes.c_uint),   # 0x0088
        ("i_atime_extra", ctypes.c_uint),   # 0x008C
        ("i_crtime", ctypes.c_uint),        # 0x0090
        ("i_crtime_extra", ctypes.c_uint),  # 0x0094
        ("i_version_hi", ctypes.c_uint),    # 0x0098
        ("i_projid", ctypes.c_uint),        # 0x009C
    ]



class ext4_superblock (ext4_struct):
    _fields_ = [
        ("s_inodes_count", ctypes.c_uint),                 # 0x0000
        ("s_blocks_count_lo", ctypes.c_uint),              # 0x0004
        ("s_r_blocks_count_lo", ctypes.c_uint),            # 0x0008
        ("s_free_blocks_count_lo", ctypes.c_uint),         # 0x000C
        ("s_free_inodes_count", ctypes.c_uint),            # 0x0010
        ("s_first_data_block", ctypes.c_uint),             # 0x0014
        ("s_log_block_size", ctypes.c_uint),               # 0x0018
        ("s_log_cluster_size", ctypes.c_uint),             # 0x001C
        ("s_blocks_per_group", ctypes.c_uint),             # 0x0020
        ("s_clusters_per_group", ctypes.c_uint),           # 0x0024
        ("s_inodes_per_group", ctypes.c_uint),             # 0x0028
        ("s_mtime", ctypes.c_uint),                        # 0x002C
        ("s_wtime", ctypes.c_uint),                        # 0x0030
        ("s_mnt_count", ctypes.c_ushort),                  # 0x0034
        ("s_max_mnt_count", ctypes.c_ushort),              # 0x0036
        ("s_magic", ctypes.c_ushort),                      # 0x0038, Must be 0xEF53
        ("s_state", ctypes.c_ushort),                      # 0x003A
        ("s_errors", ctypes.c_ushort),                     # 0x003C
        ("s_minor_rev_level", ctypes.c_ushort),            # 0x003E
        ("s_lastcheck", ctypes.c_uint),                    # 0x0040
        ("s_checkinterval", ctypes.c_uint),                # 0x0044
        ("s_creator_os", ctypes.c_uint),                   # 0x0048
        ("s_rev_level", ctypes.c_uint),                    # 0x004C
        ("s_def_resuid", ctypes.c_ushort),                 # 0x0050
        ("s_def_resgid", ctypes.c_ushort),                 # 0x0052
        ("s_first_ino", ctypes.c_uint),                    # 0x0054
        ("s_inode_size", ctypes.c_ushort),                 # 0x0058
        ("s_block_group_nr", ctypes.c_ushort),             # 0x005A
        ("s_feature_compat", ctypes.c_uint),               # 0x005C
        ("s_feature_incompat", ctypes.c_uint),             # 0x0060
        ("s_feature_ro_compat", ctypes.c_uint),            # 0x0064
        ("s_uuid", ctypes.c_ubyte * 16),                   # 0x0068
        ("s_volume_name", ctypes.c_char * 16),             # 0x0078
        ("s_last_mounted", ctypes.c_char * 64),            # 0x0088
        ("s_algorithm_usage_bitmap", ctypes.c_uint),       # 0x00C8
        ("s_prealloc_blocks", ctypes.c_ubyte),             # 0x00CC
        ("s_prealloc_dir_blocks", ctypes.c_ubyte),         # 0x00CD
        ("s_reserved_gdt_blocks", ctypes.c_ushort),        # 0x00CE
        ("s_journal_uuid", ctypes.c_ubyte * 16),           # 0x00D0
        ("s_journal_inum", ctypes.c_uint),                 # 0x00E0
        ("s_journal_dev", ctypes.c_uint),                  # 0x00E4
        ("s_last_orphan", ctypes.c_uint),                  # 0x00E8
        ("s_hash_seed", ctypes.c_uint * 4),                # 0x00EC
        ("s_def_hash_version", ctypes.c_ubyte),            # 0x00FC
        ("s_jnl_backup_type", ctypes.c_ubyte),             # 0x00FD
        ("s_desc_size", ctypes.c_ushort),                  # 0x00FE
        ("s_default_mount_opts", ctypes.c_uint),           # 0x0100
        ("s_first_meta_bg", ctypes.c_uint),                # 0x0104
        ("s_mkfs_time", ctypes.c_uint),                    # 0x0108
        ("s_jnl_blocks", ctypes.c_uint * 17),              # 0x010C

        # 64-bit fields
        ("s_blocks_count_hi", ctypes.c_uint),              # 0x0150
        ("s_r_blocks_count_hi", ctypes.c_uint),            # 0x0154
        ("s_free_blocks_count_hi", ctypes.c_uint),         # 0x0158
        ("s_min_extra_isize", ctypes.c_ushort),            # 0x015C
        ("s_want_extra_isize", ctypes.c_ushort),           # 0x015E
        ("s_flags", ctypes.c_uint),                        # 0x0160
        ("s_raid_stride", ctypes.c_ushort),                # 0x0164
        ("s_mmp_interval", ctypes.c_ushort),               # 0x0166
        ("s_mmp_block", ctypes.c_ulonglong),               # 0x0168
        ("s_raid_stripe_width", ctypes.c_uint),            # 0x0170
        ("s_log_groups_per_flex", ctypes.c_ubyte),         # 0x0174
        ("s_checksum_type", ctypes.c_ubyte),               # 0x0175
        ("s_reserved_pad", ctypes.c_ushort),               # 0x0176
        ("s_kbytes_written", ctypes.c_ulonglong),          # 0x0178
        ("s_snapshot_inum", ctypes.c_uint),                # 0x0180
        ("s_snapshot_id", ctypes.c_uint),                  # 0x0184
        ("s_snapshot_r_blocks_count", ctypes.c_ulonglong), # 0x0188
        ("s_snapshot_list", ctypes.c_uint),                # 0x0190
        ("s_error_count", ctypes.c_uint),                  # 0x0194
        ("s_first_error_time", ctypes.c_uint),             # 0x0198
        ("s_first_error_ino", ctypes.c_uint),              # 0x019C
        ("s_first_error_block", ctypes.c_ulonglong),       # 0x01A0
        ("s_first_error_func", ctypes.c_ubyte * 32),       # 0x01A8
        ("s_first_error_line", ctypes.c_uint),             # 0x01C8
        ("s_last_error_time", ctypes.c_uint),              # 0x01CC
        ("s_last_error_ino", ctypes.c_uint),               # 0x01D0
        ("s_last_error_line", ctypes.c_uint),              # 0x01D4
        ("s_last_error_block", ctypes.c_ulonglong),        # 0x01D8
        ("s_last_error_func", ctypes.c_ubyte * 32),        # 0x01E0
        ("s_mount_opts", ctypes.c_ubyte * 64),             # 0x0200
        ("s_usr_quota_inum", ctypes.c_uint),               # 0x0240
        ("s_grp_quota_inum", ctypes.c_uint),               # 0x0244
        ("s_overhead_blocks", ctypes.c_uint),              # 0x0248
        ("s_backup_bgs", ctypes.c_uint * 2),               # 0x024C
        ("s_encrypt_algos", ctypes.c_ubyte * 4),           # 0x0254
        ("s_encrypt_pw_salt", ctypes.c_ubyte * 16),        # 0x0258
        ("s_lpf_ino", ctypes.c_uint),                      # 0x0268
        ("s_prj_quota_inum", ctypes.c_uint),               # 0x026C
        ("s_checksum_seed", ctypes.c_uint),                # 0x0270
        ("s_reserved", ctypes.c_uint * 98),                # 0x0274
        ("s_checksum", ctypes.c_uint)                      # 0x03FC
    ]



def wcscmp (str_a, str_b):
    """
    Standard library wcscmp
    """
    for a, b in zip(str_a, str_b):
        tmp = ord(a) - ord(b)
        if tmp != 0: return -1 if tmp < 0 else 1

    tmp = len(str_a) - len(str_b)
    return -1 if tmp < 0 else 1 if tmp > 0 else 0



########################################################################################################################
####################################################   HIGH LEVEL   ####################################################
########################################################################################################################

class MappingEntry:
    """
    Helper class: This class maps block_count file blocks indexed by file_block_idx to the associated disk blocks indexed
    by disk_block_idx.
    """
    def __init__ (self, file_block_idx, disk_block_idx, block_count = 1):
        self.file_block_idx = file_block_idx
        self.disk_block_idx = disk_block_idx
        self.block_count = block_count

    def __iter__ (self):
        """
        Can be used to convert an MappingEntry into a tuple (file_block_idx, disk_block_idx, block_count).
        """
        yield self.file_block_idx
        yield self.disk_block_idx
        yield self.block_count

    def __repr__ (self):
        return f"{type(self).__name__:s}({self.file_block_idx!r:s}, {self.disk_block_idx!r:s}, {self.block_count!r:s})"

    def copy (self):
        return MappingEntry(self.file_block_idx, self.disk_block_idx, self.block_count)

    def create_mapping (*entries):
        """
        Converts a list of 2-tuples (disk_block_idx, block_count) into a list of MappingEntry instances
        """
        file_block_idx = 0
        result = [None] * len(entries)

        for i, entry in enumerate(entries):
            disk_block_idx, block_count = entry
            result[i] = MappingEntry(file_block_idx, disk_block_idx, block_count)
            file_block_idx += block_count

        return result

    def optimize (entries):
        """
        Sorts and stiches together a list of MappingEntry instances
        """
        entries.sort(key = lambda entry: entry.file_block_idx)

        idx = 0
        while idx < len(entries):
            while idx + 1 < len(entries) and entries[idx].disk_block_idx + entries[idx].block_count == entries[idx + 1].disk_block_idx:
                tmp = entries.pop(idx + 1)
                entries[idx].block_count += tmp.block_count

            idx += 1

# None of the following classes preserve the underlying stream's current seek.

class Volume:
    """
    Provides functionality for reading ext4 volumes
    """

    ROOT_INODE = 2

    def __init__ (self, stream, offset = 0, ignore_flags = False, ignore_magic = False):
        """
        Initializes a new ext4 reader at a given offset in stream. If ignore_magic is True, no exception will be thrown,
        when a structure with wrong magic number is found. Analogously passing True to ignore_flags suppresses Exception
        caused by wrong flags.
        """
        self.ignore_flags = ignore_flags
        self.ignore_magic = ignore_magic
        self.offset = offset
        self.stream = stream

        # Superblock
        self.superblock = self.read_struct(ext4_superblock, 0x400)

        if not ignore_magic and self.superblock.s_magic != 0xEF53:
            raise MagicError(f"Invalid magic value in superblock: 0x{self.superblock.s_magic:04X} (expected 0xEF53)")

        # Group descriptors
        self.group_descriptors = [None] * (self.superblock.s_inodes_count // self.superblock.s_inodes_per_group)

        group_desc_table_offset = (0x400 // self.block_size + 1) * self.block_size # First block after superblock
        for group_desc_idx in range(len(self.group_descriptors)):
            group_desc_offset = group_desc_table_offset + group_desc_idx * self.superblock.s_desc_size
            self.group_descriptors[group_desc_idx] = self.read_struct(ext4_group_descriptor, group_desc_offset)

    def __repr__ (self):
        return f"{type(self).__name__:s}(volume_name = {self.superblock.s_volume_name!r:s}, uuid = {self.uuid!r:s}, last_mounted = {self.superblock.s_last_mounted!r:s})"

    @property
    def block_size (self):
        """
        Returns the volume's block size in bytes.
        """
        return 1 << (10 + self.superblock.s_log_block_size)

    def get_inode (self, inode_idx):
        """
        Returns an Inode instance representing the inode specified by its index inode_idx.
        """
        group_idx, inode_table_entry_idx = self.get_inode_group(inode_idx)

        inode_table_offset = self.group_descriptors[group_idx].bg_inode_table * self.block_size
        inode_offset = inode_table_offset + inode_table_entry_idx * self.superblock.s_inode_size

        return Inode(self, inode_offset, inode_idx = inode_idx)

    def get_inode_group (self, inode_idx):
        """
        Returns a tuple (group_idx, inode_table_entry_idx)
        """
        group_idx = (inode_idx - 1) // self.superblock.s_inodes_per_group
        inode_table_entry_idx = (inode_idx - 1) % self.superblock.s_inodes_per_group
        return (group_idx, inode_table_entry_idx)

    def read (self, offset, byte_len):
        """
        Returns byte_len bytes at offset within this volume.
        """
        if self.offset + offset != self.stream.tell():
            self.stream.seek(self.offset + offset, io.SEEK_SET)

        return self.stream.read(byte_len)

    def read_struct (self, structure, offset):
        """
        Interprets the bytes at offset as structure and returns the interpreted instance
        """
        return structure.from_buffer_copy(self.read(offset, ctypes.sizeof(structure)))

    @property
    def root (self):
        """
        Returns the volume's root inode
        """
        return self.get_inode(Volume.ROOT_INODE)

    @property
    def uuid (self):
        """
        Returns the volume's UUID in the format XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX.
        """
        uuid = self.superblock.s_uuid
        uuid = [uuid[:4], uuid[4 : 6], uuid[6 : 8], uuid[8 : 10], uuid[10:]]
        return "-".join("".join(f"{c:02X}" for c in part) for part in uuid)



class Inode:
    """
    Provides functionality for parsing inodes and accessing their raw data
    """

    # dirent.file_type flags for open_dir
    IT_UNKNOWN          =  0x0
    IT_FILE             =  0x1
    IT_DIRECTORY        =  0x2
    IT_CHARACTER_DEVICE =  0x3
    IT_BLOCK_DEVICE     =  0x4
    IT_FIFO             =  0x5
    IT_SOCKET           =  0x6
    IT_SYMBOLIC_LINK    =  0x7
    IT_CHECKSUM         = 0xDE

    def __init__ (self, volume, offset, inode_idx = None, inode_name = None):
        """
        Initializes a new inode parser at the specified offset within the specified volume. inode_idx is just used to
        give the inode a readable representation.
        """
        self.inode_idx = inode_idx
        self.offset = offset
        self.volume = volume

        self.inode = volume.read_struct(ext4_inode, offset)

    def __len__ (self):
        """
        Returns the length in bytes of the content referenced by this inode.
        """
        return self.inode.i_size

    def __repr__ (self):
        if self.inode_idx != None:
            return f"{type(self).__name__:s}(inode_idx = {self.inode_idx!r:s}, offset = 0x{self.offset:X}, volume_uuid = {self.volume.uuid!r:s})"
        else:
            return f"{type(self).__name__:s}(offset = 0x{self.offset:X}, volume_uuid = {self.volume.uuid!r:s})"

    @functools.cmp_to_key
    def directory_entry_key (dir_a, dir_b):
        """
        Sort-key for directory entries. It sortes entries in a way that directories come before anything and within a group
        entries are sorted by their lower-case name. Entries whose lower-case names are equal are sorted by their case-
        sensitive names.
        """
        file_name_a, _, file_type_a = dir_a
        file_name_b, _, file_type_b = dir_b

        if file_type_a == Inode.IT_DIRECTORY == file_type_b or file_type_a != Inode.IT_DIRECTORY != file_type_b:
            tmp = wcscmp(file_name_a.lower(), file_name_b.lower())
            return tmp if tmp != 0 else wcscmp(file_name_a, file_name_b)
        else:
            return -1 if file_type_a == Inode.IT_DIRECTORY else 1

    def get_inode (self, *relative_path, decode_name = None):
        """
        Returns the inode specified by the path relative_path (list of entry names) relative to this inode. "." and ".."
        usually are supported too, however in special cases (e.g. manually crafted volumes) they might not be supported
        due to them being real on-disk directory entries that might be missing or pointing somewhere else.
        decode_name is directly passed to open_dir.
        NOTE: Whitespaces will not be trimmed off the path's parts and "\0" and "\0\0" as well as b"\0" and b"\0\0" are
        seen as different names (unless decode_name actually trims the name).
        NOTE: Along the path file_type != IT_DIRECTORY will be ignored, however i_flags will not be ignored.
        """
        if not self.is_dir:
            raise Ext4Error(f"Inode {self.inode_idx:d} is not a directory.")

        current_inode = self

        for i, part in enumerate(relative_path):
            if not self.volume.ignore_flags and not current_inode.is_dir:
                current_path = "/".join(relative_path[:i])
                raise Ext4Error(f"{current_path!r:s} (Inode {inode_idx:d}) is not a directory.")

            inode_idx = next((inode for file_name, inode, file_type in current_inode.open_dir(decode_name) if file_name == part), None)

            if inode_idx == None:
                current_path = "/".join(relative_path[:i])
                raise FileNotFoundError(f"{part!r:s} not found in {current_path!r:s} (Inode {current_inode.inode_idx:d}).")

            current_inode = current_inode.volume.get_inode(inode_idx)


        return current_inode

    @property
    def is_dir (self):
        """
        Indicates whether the inode is marked as a directory.
        """
        return (self.inode.i_mode & ext4_inode.S_IFDIR) != 0

    @property
    def is_file (self):
        """
        Indicates whether the inode is marker as a regular file.
        """
        return (self.inode.i_mode & ext4_inode.S_IFREG) != 0

    @property
    def is_in_use (self):
        """
        Indicates whether the inode's associated bit in the inode bitmap is set.
        """
        group_idx, bitmap_bit = self.volume.get_inode_group(self.inode_idx)

        inode_usage_bitmap_offset = self.volume.group_descriptors[group_idx].bg_inode_bitmap * self.volume.block_size
        inode_usage_byte = self.volume.read(inode_usage_bitmap_offset + bitmap_bit // 8, 1)[0]

        return ((inode_usage_byte >> (7 - bitmap_bit % 8)) & 1) != 0

    @property
    def mode_str (self):
        """
        Returns the inode's permissions in form of a unix string (e.g. "-rwxrw-rw" or "drwxr-xr--").
        """
        special_flag = lambda letter, execute, special: {
            (False, False): "-",
            (False, True): letter.upper(),
            (True, False): "x",
            (True, True): letter.lower()
        }[(execute, special)]

        try:
            device_type = {
                ext4_inode.S_IFIFO  : "p",
                ext4_inode.S_IFCHR  : "c",
                ext4_inode.S_IFDIR  : "d",
                ext4_inode.S_IFBLK  : "b",
                ext4_inode.S_IFREG  : "-",
                ext4_inode.S_IFLNK  : "l",
                ext4_inode.S_IFSOCK : "s",
            }[self.inode.i_mode & 0xF000]
        except KeyError:
            device_type = "?"

        return "".join([
            device_type,

            "r" if (self.inode.i_mode & ext4_inode.S_IRUSR) != 0 else "-",
            "w" if (self.inode.i_mode & ext4_inode.S_IWUSR) != 0 else "-",
            special_flag("s", (self.inode.i_mode & ext4_inode.S_IXUSR) != 0, (self.inode.i_mode & ext4_inode.S_ISUID) != 0),

            "r" if (self.inode.i_mode & ext4_inode.S_IRGRP) != 0 else "-",
            "w" if (self.inode.i_mode & ext4_inode.S_IWGRP) != 0 else "-",
            special_flag("s", (self.inode.i_mode & ext4_inode.S_IXGRP) != 0, (self.inode.i_mode & ext4_inode.S_ISGID) != 0),

            "r" if (self.inode.i_mode & ext4_inode.S_IROTH) != 0 else "-",
            "w" if (self.inode.i_mode & ext4_inode.S_IWOTH) != 0 else "-",
            special_flag("t", (self.inode.i_mode & ext4_inode.S_IXOTH) != 0, (self.inode.i_mode & ext4_inode.S_ISVTX) != 0),
        ])

    def open_dir (self, decode_name = None):
        """
        Generator: Yields the directory entries as tuples (decode_name(name), inode, file_type) in their on-disk order,
        where name is the raw on-disk directory entry name. For special cases (e.g. invalid utf8 characters in entry
        names) you can try a different decoder (e.g. decode_name = lambda raw: raw).
        Default of decode_name = lambda raw: raw.decode("utf8")
        """
        # Parse args
        if decode_name == None:
            decode_name = lambda raw: raw.decode("utf8")

        if not self.volume.ignore_flags and not self.is_dir:
            raise Ext4Error(f"Inode ({self.inode_idx:d}) is not a directory.")

        # # Hash trees are compatible with linear arrays
        # if (self.inode.i_flags & ext4_inode.EXT4_INDEX_FL) != 0:
        #     raise NotImplementedError("Hash trees are not implemented yet.")

        # Read raw directory content
        # TODO: Implement buffering
        raw_data = self.open_read().read()
        offset = 0

        while offset < len(raw_data):
            # ext4_dir_entry_2:
            #   0x0  __le32 inode           // Referenced inode
            #   0x4  __le16 rec_len         // Byte size of this entry's structure
            #   0x6  __u8   name_len        // Byte length of this entry's name
            #   0x7  __u8   file_type       // Type of this entry. See Inode.IT_* constants
            #   0x8  char   name[name_len]  // Name of this entry

            file_type = raw_data[offset + 7]
            rec_len = (raw_data[offset + 5] << 8) | raw_data[offset + 4]

            if file_type != Inode.IT_CHECKSUM:
                inode = int.from_bytes(raw_data[offset : offset + 4], "little")
                name_len = raw_data[offset + 6]
                name = decode_name(raw_data[offset + 8 : offset + 8 + name_len])

                yield (name, inode, file_type)

            offset += rec_len

    def open_read (self):
        """
        Returns an BlockReader instance for reading this inode's raw content.
        """
        # Obtain mapping from extents / hash tree or read inline data
        mapping = [] # List of MappingEntry instances
        if (self.inode.i_flags & ext4_inode.EXT4_EXTENTS_FL) != 0:
            # Uses extents
            nodes = queue.Queue()
            nodes.put_nowait(self.offset + ext4_inode.i_block.offset)

            while nodes.qsize() != 0:
                header_offset = nodes.get_nowait()
                header = self.volume.read_struct(ext4_extent_header, header_offset)

                if not self.volume.ignore_magic and header.eh_magic != 0xF30A:
                    raise MagicError(f"Invalid magic value in extent header at offset 0x{header_offset:X} of inode {self.inode_idx:d}: 0x{header.eh_magic:04X} (expected 0xF30A)")

                if header.eh_depth != 0:
                    indices = self.volume.read_struct(ext4_extent_idx * header.eh_entries, header_offset + ctypes.sizeof(ext4_extent_header))
                    for idx in indices: nodes.put_nowait(idx.ei_leaf * self.volume.block_size)
                else:
                    extents = self.volume.read_struct(ext4_extent * header.eh_entries, header_offset + ctypes.sizeof(ext4_extent_header))
                    for extent in extents: mapping.append(MappingEntry(extent.ee_block, extent.ee_start, extent.ee_len))

        elif (self.inode.I_flags & ext4_inode.EXT4_INLINE_DATA_FL) != 0:
            # Uses inline data
            return io.BytesIO(self.volume.read(self.offset + ext4_inode.i_block.offset, self.inode.i_size))

        else:
            raise Ext4Error("Unknown data storage mechanism.")

        MappingEntry.optimize(mapping)
        return BlockReader(self.volume, len(self), mapping)

    @property
    def size_readable (self):
        """
        Returns the inode's content length in a readable format (e.g. "123 bytes", "2.03 KiB" or "3.00 GiB"). Possible
        units are bytes, KiB, MiB, GiB, TiB, PiB, EiB, ZiB, YiB.
        """
        if self.inode.i_size < 1024:
            return f"{self.inode.i_size} bytes" if self.inode.i_size != 1 else "1 byte"
        else:
            units = ["KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"]
            unit_idx = min(int(math.log(self.inode.i_size, 1024)), len(units))

            return f"{self.inode.i_size / (1024 ** unit_idx):.2f} {units[unit_idx - 1]:s}"



class BlockReader:
    """
    Maps disk blocks into a linear byte stream.
    NOTE: This class does not implement buffering or caching.
    """

    # OSError
    EINVAL = 22

    def __init__ (self, volume, byte_size, block_map):
        """
        Initializes a new block reader on the specified volume. mapping must be a list of MappingEntry instances. If
        you prefer a way to use 2-tuples (disk_block_idx, block_count) with inferred file_block_index entries, see
        MappingEntry.create_mapping.
        """
        self.byte_size = byte_size
        self.volume = volume

        self.cursor = 0

        block_map = list(map(MappingEntry.copy, block_map))

        # Check block count
        block_count_sum = sum(entry.block_count for entry in block_map)
        if block_count_sum != (byte_size - 1) // volume.block_size + 1:
            raise BlockMapError("byte_size doesn't match up with count of mapped blocks")

        # Optimize mapping (stich together)
        MappingEntry.optimize(block_map)
        self.block_map = block_map

    def __repr__ (self):
        return f"{type(self).__name__:s}(byte_size = {self.byte_size!r:s}, block_map = {self.block_map!r:s}, volume_uuid = {self.volume.uuid!r:s})"

    def get_block_mapping (self, file_block_idx):
        """
        Returns the disk block index of the file block specified by file_block_idx.
        """
        disk_block_idx = None

        # Find disk block
        for entry in self.block_map:
            if entry.file_block_idx <= file_block_idx < entry.file_block_idx + entry.block_count:
                block_diff = file_block_idx - entry.file_block_idx
                disk_block_idx = entry.disk_block_idx + block_diff
                break

        if disk_block_idx == None:
            raise BlockMapError(f"File block 0x{file_block_idx:X} is not mapped to disk")

        return disk_block_idx

    def get_range_mapping (self, file_block_idx, block_count):
        """
        Returns a sequence of MappingEntry instances ordered by file_block_idx.
        """
        # Find intersections
        mapping = list(map(
            MappingEntry.copy,
            filter(
                lambda entry:
                    entry.file_block_idx <= file_block_idx < entry.file_block_idx + entry.block_count
                    or file_block_idx <= entry.file_block_idx < file_block_idx + block_count,
                self.block_map
            )
        ))

        if len(mapping) == 0:
            raise BlockMapError(f"File block 0x{file_block_idx:X} is not mapped to disk")

        # Trim left
        diff = file_block_idx - mapping[0].file_block_idx
        if diff > 0:
            mapping[0].file_block_idx += diff
            mapping[0].disk_block_idx += diff
            mapping[0].block_count -= diff

        # Trim right
        diff = (mapping[-1].file_block_idx + mapping[-1].block_count) - (file_block_idx + block_count)
        if diff > 0:
            mapping[-1].block_count -= diff

        return mapping

    def read (self, byte_len = -1):
        """
        Reades up to byte_len bytes from the block device beginning at the cursor's current position. This operation will
        not exceed the inode's size. If -1 is passed for byte_len, the inode is read to the end.
        """
        # Parse args
        if byte_len < -1: raise ValueError("byte_len must be non-negative or -1")

        bytes_remaining = self.byte_size - self.cursor
        byte_len = bytes_remaining if byte_len == -1 else max(0, min(byte_len, bytes_remaining))

        if byte_len == 0: return b""

        # Lookup optimization
        file_block_idx = self.cursor // self.volume.block_size
        offset = self.cursor % self.volume.block_size
        end_of_stream_check = byte_len

        if file_block_idx == (self.cursor + byte_len - 1) // self.volume.block_size:
            # Content within same block
            disk_block_idx = self.get_block_mapping(file_block_idx)
            result = self.volume.read(disk_block_idx * self.volume.block_size + offset, byte_len)
        else:
            block_count = (byte_len - 1) // self.volume.block_size + 1
            mapping = self.get_range_mapping(file_block_idx, block_count)

            if len(mapping) == 1:
                # Content within a single block chain
                result = self.volume.read(mapping[0].disk_block_idx * self.volume.block_size + offset, byte_len)
            else:
                # Content sprayed all over the place
                blocks = []

                blocks.append(self.volume.read(mapping[0].disk_block_idx * self.volume.block_size + offset, mapping[0].block_count * self.volume.block_size - offset))
                byte_len -= len(blocks[0])

                for i in range(1, len(mapping) - 1):
                    part = self.volume.read(mapping[i].disk_block_idx * self.volume.block_size, mapping[i].block_count * self.volume.block_size)
                    blocks.append(part)

                    byte_len -= len(part)

                blocks.append(self.volume.read(mapping[-1].disk_block_idx * self.volume.block_size, byte_len))

                result = b"".join(blocks)

        # Check whether the volume's underlying stream ended too early
        self.cursor += len(result)

        if len(result) != end_of_stream_check:
            raise EndOfStreamError(f"The volume's underlying stream ended {byte_len - len(result):d} bytes before the file.")

        return result

    def seek (self, seek, seek_mode = io.SEEK_SET):
        """
        Moves the internal cursor along the file (not the disk) and behaves like BufferedReader.seek
        """
        if seek_mode == io.SEEK_CUR:
            seek += self.cursor
        elif seek_mode == io.SEEK_END:
            seek += self.byte_size
        # elif seek_mode == io.SEEK_SET:
        #     seek += 0

        if seek < 0:
            raise OSError(BlockReader.EINVAL, "Invalid argument") # Exception behavior copied from IOBase.seek

        self.cursor = seek
        return seek

    def tell (self):
        """
        Returns the internal cursor's current file offset.
        """
        return self.cursor



class Tools:
    """
    Provides helpful utility functions
    """

    def list_dir (
        volume,
        identifier,
        decode_name = None,
        sort_key = Inode.directory_entry_key,
        line_format = "{inode.mode_str:s}  {file_name:s}",
        file_types = {0 : "unkn", 1 : "file", 2 : "dir", 3 : "chr", 4 : "blk", 5 : "fifo", 6 : "sock", 7 : "sym"}
    ):
        """
        Similar to "ls -la" this function lists all entries from a directory of volume.

        identifier might be an integer describing the directory's inode index, a str/bytes describing directory's full path or
        a list of entry names. decode_name is directly passed to open_dir. See Inode.get_inode for more details.

        sort_key is the key-function used for sorting the directories entries. If None is passed, the call to sorted is omitted.

        line_format is a format string specifying each line's format. It is used as follows:
        line_format.format(
            file_name = file_name, # Entry name
            inode = volume.get_inode(inode_idx), # Referenced inode
            file_type = file_type, # Entry type (int)
            file_type_str = file_types[file_type] if file_type in file_types else "?" # Entry type (str, see next paragraph)
        )

        file_types is a dictionary specifying the names of the different entry types.
        """
        if isinstance(identifier, int):
            inode = volume.get_inode(identifier)
        elif isinstance(identifier, str):
            inode = volume.root.get_inode(*identifier.strip(" /").split("/"))
        elif isinstance(identifier, list):
            inode = volume.root.get_inode(*identifier)

        entries = inode.open_dir(decode_name) if sort_key is None else sorted(inode.open_dir(decode_name), key = sort_key)
        for file_name, inode_idx, file_type in entries:
            print(line_format.format(
                file_name = file_name,
                inode = volume.get_inode(inode_idx),
                file_type = file_type,
                file_type_str = file_types[file_type] if file_type in file_types else "?"
            ))