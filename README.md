# ext4
Little library for reading ext4 file systems. Most of functions are documented, so simply use Python's help function. Here are some usage examples:

Opening a volume:

    import ext4
    file = open("example.img", "rb")
    volume = ext4.Volume(file, offset = 0)

    print(f"Volume {volume.uuid:s} has block size {volume.block_size:d}")

Iterating over directory entries:

    example_dir = volume.root.get_inode("example_dir")

    # on-disk order
    for file_name, inode_idx, file_type in example_dir.open_dir():
        print(file_name)

    # sorted
    for file_name, inode_idx, file_type in sorted(example_dir.open_dir(), key = ext4.Inode.directory_entry_key):
        print(file_name)

    # Fancy and customizable
    ext4.Tools.list_dir(volume, exmaple_dir)

Getting an inode by its index:

    root = volume.get_inode(ext4.Volume.ROOT_INODE) # == volume.root

Getting an inode by its path:

    # /example_dir/example_image.jpg
    example_image = root.get_inode("example_dir", "example_image.jpg")
    # or
    example_image = example_dir.get_inode("example_image.jpg")

Getting information like size or mode:

    print(f"example_img.jpg is {example_image.inode.i_size:d} bytes in size")
    print(f"example_img.jpg is {example_image.size_readable:s} in size")
    print(f"The mode of example_img.jpg is {example_image.mode_str:s}")

Reading the contents of an inode:

    reader = example_image.open_read() # Either ext4.BlockReader or io.BytesIO
    raw = reader.read()

    symbolic_link = root.get_inode("example_symlink")
    link_target = symbolic_link.open_read().read().decode("utf")