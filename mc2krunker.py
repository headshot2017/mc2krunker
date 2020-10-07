from __future__ import print_function
import struct, zlib, gzip, nbt, io, sys, os, json, pyperclip

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
    MINECRAFT_DIRT: [KRUNKER_DIRT, "#FFFFFF"],
    MINECRAFT_STONE: [KRUNKER_WALL, "#FFFFFF"],
    MINECRAFT_OAKWOOD: [KRUNKER_WOOD, "#6C5736"],
    MINECRAFT_OAKLEAVES: [KRUNKER_GRASS, "#57E03E"],
    MINECRAFT_OAKPLANK: [KRUNKER_WOOD, "#FFFFFF"],
    MINECRAFT_GRASS: [KRUNKER_GRASS, "#FFFFFF"],
    MINECRAFT_BEDROCK: [KRUNKER_GRID, "#FFFFFF"],
    MINECRAFT_WATER: [KRUNKER_LIQUID, "#FFFFFF"],
    MINECRAFT_SAND: [KRUNKER_ROOF, "#FFFFFF"],
}

############################### CONSTANTS/ENUMS END ###########################

chunk_offsets = []
chunks = {}
timestamps = []
krunkblocks = {}
krunkblocksScaled = {} # multiple krunker block objects together will be turned into a single one to help with performance and krunker's object limit

# krunkblocks dict:
# {
#    y_pos: KRUNKER_texture_id,
#    ...
# }
#
# krunkblocksScaled dict:
# {
#    y_pos: [
#        KRUNKER_texture_id,
#        x_size,
#        y_size,
#        z_size,
#        x_offset,
#        z_offset
#    ],
#    ...
# }


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

# if this block pos in krunkblocks[] dict isn't already inside a scaled object in krunkblocksScaled[]
def blockNotInRange(yy, xx, zz, tex):
    if not krunkblocksScaled[y]: return True

    for x0,z0 in krunkblocksScaled[y].keys():
        block = krunkblocksScaled[y][(x0,z0)]
        if block[0] != tex: continue # must be same texture

        x1,z1 = block[1] + x0, block[3] + z0
        if xx >= x0 and xx < x1 and zz >= z0 and zz < z1: return False

    return True
        

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
        print("[%d]: %s" % (i, _world))
    a = input("Select a world by its' number > ")
    if not a.isdigit():
        continue

    a = int(a)
    if a < 0 or a >= len(worlds):
        print("invalid world id")
        continue

    world = worlds[a]
    break

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

# open file
print("Opening world \"%s\"" % world)

# first get the player logout pos on level.dat
gz = gzip.GzipFile(mcSavePath()+world+"/level.dat")
leveldat = nbt.nbt.NBTFile(buffer=gz)
gz.close()
player_x, player_y, player_z = [p.value for p in leveldat["Data"]["Player"]["Pos"]]
playerchunk_x, playerchunk_z = int(player_x / 16), int(player_z / 16)
region_x, region_z = playerchunk_x/32, playerchunk_z/32

# use the extracted region coordinates
f = open(mcSavePath()+world+"/region/r.%d.%d.mcr" % (region_x, region_z), "rb")

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
    elif compression > 3: print("COMPRESSION > 3???", len(remaining_data), continuebytes, len(remaining_data[continuebytes+chunk_offsets[i][0] : continuebytes+chunk_offsets[i][0]+chunk_offsets[i][1]]))

    compressed_chunk = chunkbytes.read(chunk_length-1)
    if len(compressed_chunk) < chunk_length-1: continue
    nbtfile = nbt.nbt.NBTFile(buffer=io.BytesIO(zlib.decompress(compressed_chunk)))
    chunks[(nbtfile["Level"]["xPos"].value, nbtfile["Level"]["zPos"].value)] = nbtfile

    continuebytes += chunk_offsets[i][1]

# not all chunks yet... gotta fix performance issues first

x_max, z_max = 0, 0

def readChunk(chunk_x, chunk_z):
    global x_max, z_max

    if (chunk_x, chunk_z) not in chunks: return
    ch = chunks[(chunk_x, chunk_z)]
    chunk_x = ch["Level"]["xPos"].value
    chunk_z = ch["Level"]["zPos"].value
    x, y, z = 0, 0, 0

    for i in range(len(ch["Level"]["Blocks"])):
        block = ch["Level"]["Blocks"][i]
        blockname = "???"

        # don't get from bedrock level too, unless you want caves
        if block != 0 and y > 60 and blockNotInside(ch["Level"]["Blocks"], x, y, z):
            for bl in dir():
                if "MINECRAFT_" in bl and getattr(sys.modules["__main__"], bl) == block:
                    blockname = bl

            if y not in krunkblocks:
                krunkblocks[y] = {}
                krunkblocksScaled[y] = {}

            if x_max < x*8+(chunk_x*8*16): x_max = x*8+(chunk_x*8*16)
            if z_max < z*8+(chunk_z*8*16): z_max = z*8+(chunk_z*8*16)
            krunkblocks[y][(x*8+(chunk_x*8*16), z*8+(chunk_z*8*16))] = krunktextures[block] if block in krunktextures else [KRUNKER_DEFAULT, "#ffffff"]
            # sort by Y so i can then put similar blocks together into one easily by X and Z

        # read in yzx order
        y += 1
        if y > 127:
            y = 0
            z += 1
            if z > 15:
                z = 0
                x += 1

print("Reading chunks")
chunk_distance = 8
for ii in range(chunk_distance):

    for x_loop in range(playerchunk_x-ii, playerchunk_x+ii+1):
        for z_loop in range(playerchunk_z-ii, playerchunk_z+ii+1):
            print("%d: %d (%d,%d) - %d (%d,%d)" % (ii, x_loop, playerchunk_x-ii, playerchunk_x+ii, z_loop, playerchunk_z-ii, playerchunk_z+ii), end="")
            if ii == 0 or not (x_loop != playerchunk_x-ii and x_loop != playerchunk_x+ii and z_loop != playerchunk_z-ii and z_loop != playerchunk_z+ii):
                print(" reading")
                readChunk(x_loop, z_loop)
            else:
                print("")

# put similar blocks into one
print("Grouping similar blocks")
for y in krunkblocks.keys():
    for tex, color in krunktextures.values():
        for x in range(0, x_max, 8):
            for z in range(0, z_max, 8):
                if (x,z) in krunkblocks[y] and krunkblocks[y][(x,z)][0] == tex and blockNotInRange(y, x, z, tex): # we can scale this block
                    x_size, z_size = 8, 8
                    x_offset, z_offset = 0, 0

                    while (x+x_size, z) in krunkblocks[y] and krunkblocks[y][(x+x_size, z)][0] == tex:
                        x_size += 8

                    while (x, z+z_size) in krunkblocks[y]:
                        stop = False

                        for x_loop in range(x, x+x_size+8, 8):
                            if (x_loop, z+z_size) not in krunkblocks[y] or krunkblocks[y][(x_loop, z+z_size)][0] != tex:
                                stop = True
                                break
                            z_size += 8
                        
                        if stop:
                            break

                    # calculate offset: krunker editor scales blocks by its' center instead of top left corner so we want to adjust this
                    for i in range(8, x_size, 2):
                        x_offset += 1
                    for i in range(8, z_size, 2):
                        z_offset += 1

                    # finally, place the block and delete this in the original key
                    krunkblocksScaled[y][(x, z)] = [tex, x_size, 8, z_size, x_offset, z_offset, color]
                    
                    for del_x in range(x, x+x_size):
                        for del_z in range(z, z+z_size):
                            if (del_x, del_z) in krunkblocks[y]:
                                del krunkblocks[y][(del_x, del_z)]

#print(krunkblocksScaled)

# finally, put the blocks in the krunker JSON
for y in krunkblocksScaled.keys():
    for x,z in krunkblocksScaled[y].keys():
        tex, x_size, y_size, z_size, x_offset, z_offset, color = krunkblocksScaled[y][(x,z)]

        jsonfile["objects"].append(
            {"p": [(x + x_offset), y*8, (z + z_offset)], # position
             "s": [x_size, y_size, z_size], # size
             "t": tex,
             "ci": 0, # color index
             "colors": [color] # color hex code
            }
        )

for y in krunkblocks.keys():
    for x,z in krunkblocks[y].keys():
        tex, color = krunkblocks[y][(x,z)]

        jsonfile["objects"].append(
            {"p": [x, y*8, z],
             "s": [8, 8, 8],
             "t": tex,
             "ci": 0, # color index
             "colors": [color] # color hex code
            }
        )

# save the file and additionally copy the contents to clipboard, you load the map by pasting the json on krunker editor
jsonstr = json.dumps(jsonfile)
open("jsonfile.txt", "wb").write(jsonstr)
pyperclip.copy(jsonstr)
print("done. level JSON data copied to clipboard")
