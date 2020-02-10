# Copyright 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
libOpenCM3

The libOpenCM3 framework aims to create a free/libre/open-source
firmware library for various ARM Cortex-M0(+)/M3/M4 microcontrollers,
including ST STM32, Ti Tiva and Stellaris, NXP LPC 11xx, 13xx, 15xx,
17xx parts, Atmel SAM3, Energy Micro EFM32 and others.

http://www.libopencm3.org
"""

from __future__ import absolute_import

import re
from os import listdir, sep, walk
from os.path import isdir, isfile, join, normpath

from SCons.Script import DefaultEnvironment

from platformio.util import exec_command

env = DefaultEnvironment()

FRAMEWORK_DIR = env.PioPlatform().get_package_dir("framework-libopencm3")
assert isdir(FRAMEWORK_DIR)

PROJECT_DIR = env["PROJECT_DIR"]
assert isdir(PROJECT_DIR)

def find_ldscript(src_dir):
    ldscript = None
    matches = []

    # find any chip-specific ldscripts included with libopencm3 (it has many but not all)
    for item in sorted(listdir(src_dir)):
        _path = join(src_dir, item)
        if not isfile(_path) or not item.endswith(".ld"):
            continue
        matches.append(_path)

    board_ldscript = env.BoardConfig().get("build.ldscript", "")

    if isfile(join(PROJECT_DIR, board_ldscript)):
        # allow to supply an ldscript from the project directory
        ldscript = join(PROJECT_DIR, board_ldscript)
    elif len(matches) == 1:
        # if there was only one, assume it's good for the whole series (i guess?)
        ldscript = matches[0]
    elif isfile(join(src_dir, board_ldscript)):
        # if more/less than one, rely on the user specifying which to use
        ldscript = join(src_dir, board_ldscript)

    return ldscript

def generate_nvic_files():
    for root, _, files in walk(join(FRAMEWORK_DIR, "include", "libopencm3")):
        if "irq.json" not in files or isfile(join(root, "nvic.h")):
            continue

        exec_command(
            ["python", join("scripts", "irq2nvic_h"),
             join("." + root.replace(FRAMEWORK_DIR, ""),
                  "irq.json").replace("\\", "/")],
            cwd=FRAMEWORK_DIR
        )


def parse_makefile_data(makefile):
    data = {"includes": [], "objs": [], "vpath": ["./"]}

    with open(makefile) as f:
        content = f.read()

        # fetch "includes"
        re_include = re.compile(r"^include\s+([^\r\n]+)", re.M)
        for match in re_include.finditer(content):
            data['includes'].append(match.group(1))

        # fetch "vpath"s
        re_vpath = re.compile(r"^VPATH\s+\+?=\s+([^\r\n]+)", re.M)
        for match in re_vpath.finditer(content):
            data['vpath'] += match.group(1).split(":")

        # fetch obj files
        objs_match = re.search(
            r"^OBJS\s+\+?=\s+([^\.]+\.o\s*(?:\s+\\s+)?)+", content, re.M)
        assert objs_match
        data['objs'] = re.sub(
            r"(OBJS|[\+=\\\s]+)", "\n", objs_match.group(0)).split()
    return data


def get_source_files(src_dir):
    mkdata = parse_makefile_data(join(src_dir, "Makefile"))

    for include in mkdata['includes']:
        _mkdata = parse_makefile_data(normpath(join(src_dir, include)))
        for key, value in _mkdata.items():
            for v in value:
                if v not in mkdata[key]:
                    mkdata[key].append(v)

    sources = []
    for obj_file in mkdata['objs']:
        src_file = obj_file[:-1] + "c"
        for search_path in mkdata['vpath']:
            src_path = normpath(join(src_dir, search_path, src_file))
            if isfile(src_path):
                sources.append(join("$BUILD_DIR", "FrameworkLibOpenCM3",
                                    src_path.replace(FRAMEWORK_DIR + sep, "")))
                break
    return sources

#
# Processing ...
#

root_dir = join(FRAMEWORK_DIR, "lib")
if env.BoardConfig().get("build.core") == "tivac":
    env.Append(
        CPPDEFINES=["LM4F"]
    )
    root_dir = join(root_dir, "lm4f")
elif env.BoardConfig().get("build.core") == "stm32":
    root_dir = join(root_dir, env.BoardConfig().get("build.core"),
                    env.BoardConfig().get("build.mcu")[5:7])

env.Append(
    CPPPATH=[
        FRAMEWORK_DIR,
        join(FRAMEWORK_DIR, "include")
    ]
)

generate_nvic_files()

ldscript_path = find_ldscript(root_dir)
# override ldscript by libopencm3
assert "LDSCRIPT_PATH" in env
env.Replace(
    LDSCRIPT_PATH=ldscript_path
)

libs = []
env.VariantDir(
    join("$BUILD_DIR", "FrameworkLibOpenCM3"),
    FRAMEWORK_DIR,
    duplicate=False
)
libs.append(env.Library(
    join("$BUILD_DIR", "FrameworkLibOpenCM3"),
    get_source_files(root_dir)
))

env.Append(LIBS=libs)

# make sure gcc can find the ldscripts included in libopencm3
env.Append(
    LIBPATH=[
        join(FRAMEWORK_DIR, "lib")
    ]
)

env.Append(
    ASFLAGS=["-x", "assembler-with-cpp"],

    CCFLAGS=[
        "-fno-common", # place uninitialized global vars in BSS
        "-ffunction-sections",  # place each function in its own section
        "-fdata-sections", # same for data
        "-mthumb",
    ],

    LINKFLAGS=[
        "-Wl,--gc-sections",
        "-nostartfiles",
        "-nostdlib",
        "-mthumb",
    ],
)

if "BOARD" in env:
    env.Append(
        CCFLAGS=[
            "-mcpu=%s" % env.BoardConfig().get("build.cpu")
        ],
        LINKFLAGS=[
            "-mcpu=%s" % env.BoardConfig().get("build.cpu")
        ]
    )

# copy CCFLAGS to ASFLAGS (-x assembler-with-cpp mode)
env.Append(ASFLAGS=env.get("CCFLAGS", [])[:])
