from __future__ import print_function
import struct, zlib, gzip, nbt, io, sys, os, json, pyperclip
from region import Region

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
    MINECRAFT_DIRT: [KRUNKER_DIRT, None],
    MINECRAFT_STONE: [KRUNKER_WALL, None],
    MINECRAFT_OAKWOOD: [KRUNKER_WOOD, 2],
    MINECRAFT_OAKLEAVES: [KRUNKER_GRASS, 1],
    MINECRAFT_OAKPLANK: [KRUNKER_WOOD, None],
    MINECRAFT_GRASS: [KRUNKER_GRASS, None],
    MINECRAFT_BEDROCK: [KRUNKER_GRID, None],
    MINECRAFT_WATER: [KRUNKER_LIQUID, None],
    MINECRAFT_SAND: [KRUNKER_ROOF, None],
}

############################### CONSTANTS/ENUMS END ###########################

regions = {}
surfaceAreas = {}
krunkblocks = {y: {} for y in range(128)}
krunkblocksScaled = {y: {} for y in range(128)} # multiple krunker block objects together will be turned into a single one to help with performance and krunker's object limit

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

# in this air x,y,z position, checks if there is a block in any of the extra positions
def isSurfaceArea(x, y, z):
    positions = [(x, y+1, z),
                 (x, y-1, z),
                 (x+8, y, z),
                 (x-8, y, z),
                 (x, y, z+8),
                 (x, y, z-8)
                ]

    for pos_x, pos_y, pos_z in positions:
        if pos_y >= 0 and pos_y < len(krunkblocks) and (pos_x, pos_z) in krunkblocks[pos_y]: return True

    return False

# checks if there is one surface area in any of the positions around this block, to avoid removing it
def hasSurfaceArea(x, y, z):
    positions = [(x, y+1, z),
                 (x, y-1, z),
                 (x+8, y, z),
                 (x-8, y, z),
                 (x, y, z+8),
                 (x, y, z-8)
                ]

    for pos_x, pos_y, pos_z in positions:
        if (pos_x, pos_y, pos_z) in surfaceAreas: return True

    return False

# if this block pos in krunkblocks[] dict isn't already inside a scaled object in krunkblocksScaled[]
def blockNotInRange(yy, xx, zz, mcblock):
    if not krunkblocksScaled[y]: return True

    for x0,z0 in krunkblocksScaled[y].keys():
        block = krunkblocksScaled[y][(x0,z0)]
        if block[-1] != mcblock: continue # must be same texture

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

print("Selected world \"%s\"" % (world))

# pick chunk render distance
chunk_distance = 4
while True:
    a = input("How many chunks to grab from the player position?\nGo somewhere in the Minecraft world and log out from there.\nLeave empty for 4 chunks\n> ")
    if not a: a = "4"
    elif not a.isdigit():
        continue

    chunk_distance = int(a)
    if chunk_distance >= 8:
        input("Be careful, this might use up a lot of Krunker objects.\nPress ENTER to continue\n.")
    break

print("Chunk distance: %d" % (chunk_distance))

# default Krunker JSON file albeit with a few changes
jsonfile = {
    "name": world,
    "welMsg": "Converted with MC2Krunker: github.com headshot2017 mc2krunker",
    "ambient": "#97a0a8",
    "light": "#f2f8fc",
    "skyDome": True,
    "skyDomeCol0": "#6ABEFF",
    "skyDomeCol1": "#A6D0FF",
    "skyDomeCol2": "#0B36DC",
    "fog": "#8d9aa0",
    "fogD": 2000,
    "objects": [],
    "colors": ["#57E03E", "#6C5736"],
    "spawns": []
}

# open file
print("Opening world \"%s\"" % world)

extension = ".mcr"
isAnvil = False
for f in os.listdir(mcSavePath()+world+"/region"):
    if f.endswith(".mca"):
        # use Anvil format over McRegion
        print("Using Anvil format")
        extension = ".mca"
        isAnvil = True
        break

# first get the player logout pos on level.dat
gz = gzip.GzipFile(mcSavePath()+world+"/level.dat")
leveldat = nbt.nbt.NBTFile(buffer=gz)
gz.close()
player_x, player_y, player_z = [p.value for p in leveldat["Data"]["Player"]["Pos"]]
playerchunk_x, playerchunk_z = int(player_x / 16), int(player_z / 16)
playerregion_x, playerregion_z = playerchunk_x/32, playerchunk_z/32
region, regionstr = [["region", "Overworld"], ["DIM1", "The End"], ["DIM-1", "Nether"]][leveldat["Data"]["Player"]["Dimension"].value]
jsonfile["spawns"].append([player_x*8, player_y*8, player_z*8, 0, 0, 0]) # last 3 zeroes are: team 0/1/2, direction 0/1/2/3, starting area 0/1

print("Player dimension:", regionstr)
# read all regions
for region in os.listdir(mcSavePath()+world+"/"+region):
    if not region.endswith(extension): continue
    i = 0

    f = open(mcSavePath()+world+"/region/"+region, "rb")
    x, z = region.split(".")[1:-1]
    regions[(int(x), int(z))] = region_obj = Region()

    # these 3 lines and both for loops below were borrowed from Minecraft Region Fixer
    f.seek(0, 2)
    fsize = f.tell()
    f.seek(0)

    for i in range(0, 4096, 4):
        f.seek(i)

        offset, length = struct.unpack(">IB", "\0"+f.read(4))
        region_obj.chunk_offsets.append((offset, length))

        f.seek(i + 4096)

        region_obj.timestamps.append(struct.unpack(">I", f.read(4))[0])

    for offset, length in region_obj.chunk_offsets:
        if offset == 0 or length == 0: continue

        try:
            f.seek(offset * 4096)
            chunk_length, compression = struct.unpack(">IB", f.read(5))
        except IOError:
            print(offset, length, "IOError")
            continue

        error = 0
        if offset*4096 + chunk_length + 4 > fsize:
            error = 1
        elif chunk_length <= 1:
            error = 2
        elif chunk_length+4 > length * 4096:
            error = 3

        f.seek(offset * 4096 + 5)
        chunk_length2 = min(chunk_length-1, fsize - (offset * 4096 + 5))
        chunk = f.read(chunk_length2)

        nbtfile = None
        if compression == 2:
            nbtfile = nbt.nbt.NBTFile(buffer=io.BytesIO(zlib.decompress(chunk)))
        elif compression == 1:
            nbtfile = nbt.nbt.NBTFile(buffer=gzip.GzipFile(chunk))
        else:
            print(chunk_length, chunk_length2, compression, fsize, offset, length)
            nbtfile = nbt.nbt.NBTFile(buffer=io.BytesIO(chunk))
        xx, zz = nbtfile["Level"]["xPos"].value, nbtfile["Level"]["zPos"].value
        region_obj.chunks[(xx,zz)] = nbtfile

    f.close()

x_min, x_max, y_min, y_max, z_min, z_max = None, None, None, None, None, None

def readChunk(chunk_x, chunk_z):
    global x_min, x_max, y_min, y_max, z_min, z_max

    region_x, region_z = chunk_x/32, chunk_z/32
    chunks = regions[(region_x, region_z)].chunks

    if (chunk_x, chunk_z) not in chunks:
        print("Chunk %d,%d not found?? this chunk is in region %d,%d" % (chunk_x, chunk_z, region_x, region_z))
        return
    ch = chunks[(chunk_x, chunk_z)]
    chunk_x = ch["Level"]["xPos"].value
    chunk_z = ch["Level"]["zPos"].value

    if not isAnvil:
        x, y, z = 0, 0, 0

        for i in range(len(ch["Level"]["Blocks"])):
            block = ch["Level"]["Blocks"][i]
            blockname = "???"

            # don't get from bedrock level too, unless you want caves
            if block != 0 and y >= 60:
                for bl in dir():
                    if "MINECRAFT_" in bl and getattr(sys.modules["__main__"], bl) == block:
                        blockname = bl

                if y not in krunkblocks:
                    krunkblocks[y] = {}
                    krunkblocksScaled[y] = {}

                if not x_max or x_max < x*8+(chunk_x*8*16): x_max = x*8+(chunk_x*8*16)
                if not y_max or y_max < y: y_max = y
                if not z_max or z_max < z*8+(chunk_z*8*16): z_max = z*8+(chunk_z*8*16)
                if not x_min or x*8+(chunk_x*8*16) < x_min: x_min = x*8+(chunk_x*8*16)
                if not y_min or y < y_min: y_min = y
                if not z_min or z*8+(chunk_z*8*16) < z_min: z_min = z*8+(chunk_z*8*16)
                krunkblocks[y][(x*8+(chunk_x*8*16), z*8+(chunk_z*8*16))] = krunktextures[block]+[block] if block in krunktextures else [KRUNKER_DEFAULT, None, block]
                # sort by Y so i can then put similar blocks together into one easily by X and Z

            # read in yzx order
            y += 1
            if y > 127:
                y = 0
                z += 1
                if z > 15:
                    z = 0
                    x += 1

    else: # if isAnvil
        for i in range(len(ch["Level"]["Sections"])):
            section = ch["Level"]["Sections"][i]
            x, y, z = 0, 0, 0

            for block in section["Blocks"]:
                blockname = "???"

                if block != 0 and y + (section["Y"].value*16) >= 48:
                    for bl in dir():
                        if "MINECRAFT_" in bl and getattr(sys.modules["__main__"], bl) == block:
                            blockname = bl

                    if y not in krunkblocks:
                        krunkblocks[y] = {}
                        krunkblocksScaled[y] = {}

                    if x_max < x*8+(chunk_x*8*16): x_max = x*8+(chunk_x*8*16)
                    if z_max < z*8+(chunk_z*8*16): z_max = z*8+(chunk_z*8*16)
                    krunkblocks[y + (section["Y"].value*16)][(x*8+(chunk_x*8*16), z*8+(chunk_z*8*16))] = krunktextures[block]+[block] if block in krunktextures else [KRUNKER_DEFAULT, None, block]
                    # sort by Y so i can then put similar blocks together into one easily by X and Z

                y += 1
                if y > 15:
                    y = 0
                    z += 1
                    if z > 15:
                        z = 0
                        x += 1
                

print("Reading chunks")
for ii in range(chunk_distance):
    for x_loop in range(playerchunk_x-ii, playerchunk_x+ii+1):
        for z_loop in range(playerchunk_z-ii, playerchunk_z+ii+1):
            print("%d: %d (%d,%d) - %d (%d,%d)" % (ii, x_loop, playerchunk_x-ii, playerchunk_x+ii, z_loop, playerchunk_z-ii, playerchunk_z+ii), end="")
            if ii == 0 or not (x_loop != playerchunk_x-ii and x_loop != playerchunk_x+ii and z_loop != playerchunk_z-ii and z_loop != playerchunk_z+ii):
                print(" reading")
                readChunk(x_loop, z_loop)
            else:
                print("")

# find surface areas around the blocks. (borders not counted)
# these areas have at least one block next to them.
# they are accessible to players through normal means
print("Finding invisible/unnecessary blocks")
for y in range(y_min, y_max):
    for x in range(x_min, x_max+8, 8):
        for z in range(z_min, z_max+8, 8):
            #if x == -1032: print(x, y, z, (x,z) in krunkblocks[y], "surface area")
            if (x,z) not in krunkblocks[y] and isSurfaceArea(x, y, z):
                surfaceAreas[(x,y,z)] = True

# another loop again... but this time we remove blocks that don't have at least one surface area next to them
# these are the inaccessible blocks you will never see in the Krunker map
print("Removing invisible/unnecessary blocks")
for y in krunkblocks.keys():
    #print("Progress %d%% (%d/%d) krunkblocks[y] length %d" % (float(y) / len(krunkblocks) * 100, y, len(krunkblocks), len(krunkblocks[y])))
    for x,z in krunkblocks[y].keys():
        if not hasSurfaceArea(x, y, z):
            del krunkblocks[y][(x,z)] 

# put similar blocks into one
if "nogroup" not in sys.argv:
    print("Grouping similar blocks")
    for y in krunkblocks.keys():
        for mcblock in krunktextures.keys():
            tex, color = krunktextures[mcblock]
            for z in range(z_min, z_max+8, 8):
                for x in range(x_min, x_max+8, 8):
                    if (x,z) in krunkblocks[y] and not blockNotInRange(y, x, z, mcblock):
                        del krunkblocks[y][(x, z)]
                        continue

                    elif (x,z) in krunkblocks[y] and krunkblocks[y][(x,z)][2] == mcblock: # we can scale this block
                        x_size, y_size, z_size = 8, 1, 8
                        x_offset, z_offset = 0, 0

                        while (x+x_size, z) in krunkblocks[y] and krunkblocks[y][(x+x_size, z)][2] == mcblock:
                            x_size += 8

                        while (x, z+z_size) in krunkblocks[y] and krunkblocks[y][(x, z+z_size)][2] == mcblock:
                            stop = False

                            if x_size > 8:
                                for x_loop in range(x, x+x_size, 8):
                                    if (x_loop, z+z_size) not in krunkblocks[y] or krunkblocks[y][(x_loop, z+z_size)][2] != mcblock:
                                        stop = True
                                        break
                            elif ((x+x_size, z+z_size) not in krunkblocks[y] or krunkblocks[y][(x+x_size, z+z_size)][2] != mcblock) and not ((x+x_size, z+z_size) not in krunkblocks[y] and (x-x_size, z+z_size) not in krunkblocks[y]):
                                break
                        
                            if stop:
                                break
                            z_size += 8

                        # calculate offset: krunker editor scales blocks by its' center instead of top left corner so we want to adjust this
                        for i in range(8, x_size, 2):
                            x_offset += 1
                        for i in range(8, z_size, 2):
                            z_offset += 1

                        # finally, place the block and delete this in the original key
                        krunkblocksScaled[y][(x, z)] = [tex, x_size, y_size*8, z_size, x_offset, z_offset, color, mcblock]
                    
                        for del_x in range(x, x+x_size, 8):
                            for del_z in range(z, z+z_size, 8):
                                if (del_x, del_z) in krunkblocks[y] and krunkblocks[y][(del_x, del_z)][2] == mcblock:
                                    del krunkblocks[y][(del_x, del_z)]

# finally, put the blocks in the krunker JSON
print("Populating JSON file")
for y in krunkblocksScaled.keys():
    for x,z in krunkblocksScaled[y].keys():
        tex, x_size, y_size, z_size, x_offset, z_offset, color, mcblock = krunkblocksScaled[y][(x,z)]

        krunkObject = {
            "p": [(x + x_offset), y*8, (z + z_offset)], # position
            "s": [x_size, y_size, z_size], # size
            "t": tex
        }
        if color >= 0:
            krunkObject["ci"] = color-1

        jsonfile["objects"].append(krunkObject)

for y in krunkblocks.keys():
    for x,z in krunkblocks[y].keys():
        tex, color, mcblock = krunkblocks[y][(x,z)]

        krunkObject = {
            "p": [x, y*8, z],
            "s": [8, 8, 8],
            "t": tex,
        }
        if color >= 0:
            krunkObject["ci"] = color-1

        jsonfile["objects"].append(krunkObject)

objects = len(jsonfile["objects"])
print("Objects: %d" % objects)
if objects >= 7500:
    print("WARNING: This goes past the Krunker premium/verified object limit 7500! You cannot publish the map without making changes beforehand, or decrease the chunk distance.")
elif objects >= 5000:
    print("WARNING: This goes past the Krunker object limit 5000! You will only be able to publish this map if your account has Krunker Premium, or is verified. Delete some blocks in the editor by hand or decrease the chunk distance.")

# save the file and additionally copy the contents to clipboard, you load the map by pasting the json on krunker editor
jsonstr = json.dumps(jsonfile)
open("jsonfile.txt", "wb").write(jsonstr)
pyperclip.copy(jsonstr)
print("done. level JSON data copied to clipboard")
