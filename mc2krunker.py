import struct, zlib, nbt, io, sys, os, json, pyperclip

############################### CONSTANTS/ENUMS ###############################

# krunker textures
KRUNKER_DEFAULT = 5
KRUNKER_WALL = 0
KRUNKER_DIRT = 1
KRUNKER_WOOD = 2
KRUNKER_GRID = 3
KRUNKER_ROOF = 6
KRUNKER_GRASS = 8
KRUNKER_LIQUID = 13

# minecraft block ids
MINECRAFT_STONE = 1
MINECRAFT_GRASS = 2
MINECRAFT_DIRT = 3
MINECRAFT_COBBLESTONE = 4
MINECRAFT_OAKPLANK = 5
MINECRAFT_BEDROCK = 7
MINECRAFT_WATER = 9
MINECRAFT_SAND = 12
MINECRAFT_GRAVEL = 13
MINECRAFT_OAKWOOD = 17
MINECRAFT_OAKLEAVES = 18
MINECRAFT_SANDSTONE = 24

# minecraft to krunker dict
krunktextures = {
    MINECRAFT_DIRT: KRUNKER_DIRT,
    MINECRAFT_STONE: KRUNKER_WALL,
    MINECRAFT_OAKPLANK: KRUNKER_WOOD,
    MINECRAFT_GRASS: KRUNKER_GRASS,
    MINECRAFT_BEDROCK: KRUNKER_GRID,
    MINECRAFT_WATER: KRUNKER_LIQUID,
    MINECRAFT_SAND: KRUNKER_ROOF
}

############################### CONSTANTS/ENUMS END ###########################

# python version dependent print function
def Print(*args, end="\n"):
    if sys.version.info.major == 2: # python 2.7 (who's going to use this in py2.6???)
        print " ".join(args), end,
    else: # python 3.x
        print(*args, end=end)

# platform dependent minecraft save locations
def mcSavePath():
    path = ""
    if os.name == "nt":
        path = os.environ["appdata"]+"/.minecraft/saves/"
    elif os.name == "darwin":
        path = os.path.expanduser("~/Library/Application Support/minecraft/saves/")
    else:
        path = os.path.expanduser("~/.minecraft/saves/")
    return path if os.path.exists(path) else "./" # meh, return current directory

# taken from http://wiki.vg/Region_Files, useful
def chunk_location(l):
    offset = ((l > 8) & 0xffffff)
    size = l & 0xff

    return (offset * 4096, size * 4096)

# checks if a block has at least one side visible in the outside (not covered by blocks around it)
def blockNotInside(blockArray, x, y, z):
    pos1 = (y+1) + z*128 + x*128*16
    pos2 = (y-1) + z*128 + x*128*16
    pos3 = y + (z+1)*128 + x*128*16
    pos4 = y + (z-1)*128 + x*128*16
    pos5 = y + z*128 + (x+1)*128*16
    pos6 = y + z*128 + (x-1)*128*16
    bool1 = pos1 >= len(blockArray) or blockArray[pos1] == 0
    bool2 = blockArray[pos2] == 0
    bool3 = pos3 >= len(blockArray) or blockArray[pos3] == 0
    bool4 = blockArray[pos4] == 0
    bool5 = pos5 >= len(blockArray) or blockArray[pos5] == 0
    bool6 = blockArray[pos6] == 0
    return bool1 or bool2 or bool3 or bool4 or bool5 or bool6

# python 2 input() executes code, py3 doesn't have raw_input()
if sys.version_info.major == 2:
    input = raw_input

# actual converter code
# check for available worlds
worlds = []
for world in os.listdir(mcSavePath()):
    if os.path.exists(mcSavePath()+world+"/level.dat"): # valid
        worlds.append(world)

# pick a world
world = ""
while True:
    for _world in worlds:
        i = worlds.index(_world)
        Print("[%d]: %s" % (i, _world))
    a = input("Select a world by its' number > ")
    if not a.isdigit():
        continue

    a = int(a)
    if a < 0 or a >= len(worlds):
        Print("invalid world id")
        continue

    world = worlds[a]
    break

# open file
f = open(mcSavePath()+world+"/region/r.0.0.mcr", "rb")

chunk_offsets = []
chunks = []
timestamps = []
krunkblocks = []

for i in range(0, 1024):
    chunk_offsets.append(chunk_location(struct.unpack_from(">I", f.read(4))[0]))

for i in range(0, 1024):
    timestamps.append(struct.unpack_from(">I", f.read(4))[0])

remaining_data = f.read()
continuebytes = 0

for i in range(len(chunk_offsets)):
    if chunk_offsets[i][0] == 0 and chunk_offsets[i][1] == 0: continue

    chunkbytes = io.BytesIO(remaining_data[continuebytes+chunk_offsets[i][0] : continuebytes+chunk_offsets[i][0]+chunk_offsets[i][1]])

    chunk_length = struct.unpack_from(">I", chunkbytes.read(4))[0]
    compression = struct.unpack_from(">B", chunkbytes.read(1))[0]

    if chunk_length == 0 and compression == 0: continue
    elif compression > 3: Print("COMPRESSION > 3???", len(remaining_data), continuebytes, len(remaining_data[continuebytes+chunk_offsets[i][0] : continuebytes+chunk_offsets[i][0]+chunk_offsets[i][1]]))

    compressed_chunk = chunkbytes.read(chunk_length-1)
    if len(compressed_chunk) < chunk_length-1: continue
    nbtfile = nbt.nbt.NBTFile(buffer=io.BytesIO(zlib.decompress(compressed_chunk)))
    chunks.append(nbtfile)

    continuebytes += chunk_offsets[i][1]

# default Krunker JSON file albeit with a few changes
jsonfile = {
    "name": world,
    "welMsg": "Converted with MC2Krunker: github.com/headshot2017/mc2krunker",
    "ambient": "#97a0a8",
    "light": "#f2f8fc",
    "sky": "#dce8ed",
    "fog": "#8d9aa0",
    "fogD": 2000,
    "objects": [],
    "spawns": []
}

# not all chunks yet... gotta fix performance issues first
for ii in range(len(chunks[:16])):

    ch = chunks[ii]
    x, y, z = 0, 0, 0

    for i in range(len(ch["Level"]["Blocks"])):
        block = ch["Level"]["Blocks"][i]
        blockname = "???"

        # don't get from bedrock level too, unless you want caves
        if block != 0 and y > 48 and blockNotInside(ch["Level"]["Blocks"], x, y, z):
            for bl in dir():
                if "MINECRAFT_" in bl and getattr(sys.modules["__main__"], bl) == block:
                    blockname = bl
            jsonfile["objects"].append({"p": [x*8+(ch["Level"]["xPos"].value*8*16), y*8, z*8+(ch["Level"]["zPos"].value*8*16)], "s": [8, 8, 8], "t": krunktextures[block] if block in krunktextures else KRUNKER_DEFAULT})

        # read in yzx order
        y += 1
        if y > 127:
            y = 0
            z += 1
            if z > 15:
                z = 0
                x += 1

# save the file and additionally copy the contents to clipboard, you load the map by pasting the json on krunker editor
json.dump(jsonfile, open("jsonfile.txt", "wb"))
pyperclip.copy(open("jsonfile.txt", "rb").read())
print "done"
