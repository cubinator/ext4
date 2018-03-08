# ext4
Little library for reading ext4 file systems. Most of functions are documented, so simply use Python's help function. Here are some usage examples:

Opening a volume:

    >>> import ext4
    >>> file = open("example.img", "rb")
    >>> volume = ext4.Volume(file, offset = 0)

    >>> print(f"Volume {volume.uuid:s} has block size {volume.block_size:d}")
    Volume 3C09AE31-A105-45F9-80D0-6062DABDA0EE has block size 1024

Configure flag and magic checking:

	>>> volume.ignore_flags = False
	>>> volume.ignore_magic = False

Iterating over directory entries:

    >>> example_dir = volume.root.get_inode("example_dir")

    >>> # on-disk order
    >>> for file_name, inode_idx, file_type in example_dir.open_dir():
    ...     print(file_name)
    .
    ..
    example_file
    example_image.jpg

    >>> # sorted
    >>> for file_name, inode_idx, file_type in sorted(example_dir.open_dir(), key = ext4.Inode.directory_entry_key):
    >>>     print(file_name)

    >>> # Fancy and customizable
    >>> ext4.Tools.list_dir(volume, example_dir)
    drwxr-xr-x    1.00 KiB  .
    drwxr-xr-x    1.00 KiB  ..
    -rw-r--r--    12 bytes  example_file
    -rw-r--r--   66.69 KiB  example_image.jpg

Getting an inode by its index:

    >>> root = volume.get_inode(ext4.Volume.ROOT_INODE, ext4.InodeType.DIRECTORY) # == volume.root

Getting an inode by its path:

    >>> # /example_dir/example_image.jpg
    >>> example_image = root.get_inode("example_dir", "example_image.jpg")
    >>> # or
    >>> example_image = example_dir.get_inode("example_image.jpg")

Getting information like size or mode:

    >>> print(f"example_img.jpg is {example_image.inode.i_size:d} bytes in size")
    example_img.jpg is 68288 bytes in size
    >>> print(f"example_img.jpg is {example_image.size_readable:s} in size")
    example_img.jpg is 66.69 KiB in size
    >>> print(f"The mode of example_img.jpg is {example_image.mode_str:s}")
    The mode of example_img.jpg is -rw-r--r--

Reading the contents of an inode:

    >>> reader = example_image.open_read() # Either ext4.BlockReader or io.BytesIO
    >>> raw = reader.read()

    >>> symbolic_link = root.get_inode("example_symlink")
    >>> symbolic_link.open_read().read().decode("utf8")
	'example_dir/example_image.jpg'

Getting a list of all extended attributes:

	>>> list(example_dir.xattrs())
	[('user.example_attrib', b'some value'), ('security.unsecure', b'maybe')]